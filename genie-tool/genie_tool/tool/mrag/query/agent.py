"""Observable single-Agent orchestration built from the original JDGenie MRAG loop."""

import concurrent.futures
import os
import uuid
from time import perf_counter
from typing import Dict, Iterator, List, Tuple

from .models import AgentEvent, AgentEventType, AgentReference
from .query_processor import QueryProcessor
from ..generation import PromptManager
from ..generation.llm import LLMClient
from ..generation.vlm import VLLMClient
from ..rerank.text_reranker import get_text_reranker
from ..retrieval import BaseRetriever
from ..retrieval.retriever import RetrievalBatch
from ..utils.logger_utils import logger


class AgenticRAG:
    """A bounded, observable single Agent for multimodal knowledge retrieval."""

    def __init__(self, kb_id: str, n_round: int = 3):
        self._n_round = max(1, n_round)
        self._retriever = BaseRetriever()
        self._kb_id = kb_id

    @staticmethod
    def _event(
        event: AgentEventType,
        run_id: str,
        data: dict | None = None,
        round_no: int | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            event=event,
            run_id=run_id,
            round_no=round_no,
            data=data or {},
        )

    @staticmethod
    def _chunk_content(chunk) -> str:
        try:
            return chunk.choices[0].delta.content or ""
        except (AttributeError, IndexError, TypeError):
            return ""

    def retrieval(self, questions: list[str]) -> List[List[Dict]]:
        """Compatibility entry point for callers that only need merged hits."""

        return self._retriever.retrieval_by_texts(self._kb_id, questions)

    def multi_retrieval(self, questions: List[str]) -> RetrievalBatch:
        return self._retriever.retrieval_by_texts_with_trace(self._kb_id, questions)

    @staticmethod
    def merge_retrieval_results(
        responses: List[Dict],
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Deduplicate the original text, independent-image and page result types."""

        text_chunk_map = {}
        image_chunk_map = {}
        page_chunk_map = {}
        for result in responses:
            payload = result.get("payload", {})
            chunk_type = payload.get("chunk_type")
            if chunk_type == "text":
                key = payload.get("file_sorted") or payload.get("chunk_id") or result.get("id")
                text_chunk_map.setdefault(key, result)
            elif chunk_type in {"image", "ocr_text", "caption"}:
                if payload.get("image_id"):
                    image_chunk_map.setdefault(payload["image_id"], result)
                elif payload.get("page_id"):
                    page_chunk_map.setdefault(payload["page_id"], result)
            elif chunk_type == "page":
                key = payload.get("page_id") or payload.get("page_path") or result.get("id")
                page_chunk_map.setdefault(key, result)

        sort_by_score = lambda item: item.get("score", 0.0)
        return (
            sorted(text_chunk_map.values(), key=sort_by_score, reverse=True),
            sorted(image_chunk_map.values(), key=sort_by_score, reverse=True),
            sorted(page_chunk_map.values(), key=sort_by_score, reverse=True),
        )

    @staticmethod
    def build_ref_context(docs: List[Dict]) -> str:
        context_parts = []
        for index, doc in enumerate(docs, start=1):
            text = doc.get("payload", {}).get("text")
            if text:
                context_parts.append(f"〔{index}〕\n{text}")
        return "\n\n".join(context_parts)

    @staticmethod
    def _build_references(
        text_chunks: List[Dict],
        visual_chunks: List[Dict],
    ) -> List[AgentReference]:
        references = []
        for index, chunk in enumerate(text_chunks, start=1):
            payload = chunk.get("payload", {})
            references.append(AgentReference(
                ref_id=f"ref-{index}",
                content_type="text",
                filename=payload.get("filename"),
                file_id=payload.get("file_id"),
                url=payload.get("file_url"),
                score=chunk.get("score"),
                text_preview=(payload.get("text") or "")[:160] or None,
            ))

        for index, chunk in enumerate(visual_chunks, start=1):
            payload = chunk.get("payload", {})
            references.append(AgentReference(
                ref_id=f"visual-{index}",
                content_type="page" if payload.get("chunk_type") == "page" else "image",
                filename=payload.get("filename"),
                file_id=payload.get("file_id"),
                url=payload.get("image_url"),
                score=chunk.get("score"),
                text_preview=(payload.get("text") or "")[:160] or None,
            ))
        return references

    @staticmethod
    def _select_visual_chunks(
        image_chunks: List[Dict],
        page_chunks: List[Dict],
    ) -> List[Dict]:
        limit = max(1, int(os.getenv("MRAG_MAX_VISUAL_CONTEXTS", "1")))
        candidates = sorted(
            [*image_chunks, *page_chunks],
            key=lambda item: item.get("score", 0.0),
            reverse=True,
        )
        selected = []
        seen_urls = set()
        for candidate in candidates:
            image_url = candidate.get("payload", {}).get("image_url")
            if not image_url or image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _summarize_subqueries(
        sub_questions: List[str],
        current_chunks: List[List[Dict]],
    ) -> List[str]:
        summaries = {question: "" for question in sub_questions}
        tasks = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(sub_questions))) as executor:
            for sub_question, chunks in zip(sub_questions, current_chunks):
                if not QueryProcessor.build_context(chunks):
                    continue
                task = executor.submit(QueryProcessor.summarize_subquery, sub_question, chunks)
                tasks[task] = sub_question

            for future in concurrent.futures.as_completed(tasks):
                sub_question = tasks[future]
                try:
                    summaries[sub_question] = future.result()
                except Exception as exc:
                    logger.warning(
                        "Subquery summary failed for {!r}: {}",
                        sub_question,
                        type(exc).__name__,
                    )
        return [summaries[question] for question in sub_questions]

    @staticmethod
    def _rerank_text_chunks(question: str, chunks: List[Dict]) -> Tuple[List[Dict], dict]:
        threshold = float(os.getenv("RERANK_SCORE_THRESHOLD", "0.3"))
        limit = max(1, int(os.getenv("MRAG_MAX_TEXT_CONTEXTS", "8")))
        if not chunks:
            return [], {
                "status": "skipped",
                "input_count": 0,
                "output_count": 0,
                "threshold": threshold,
                "top_scores": [],
            }

        texts = [chunk.get("payload", {}).get("text", "") for chunk in chunks]
        try:
            scores = get_text_reranker().rerank(question, texts)
            if len(scores) != len(chunks):
                raise ValueError("reranker returned an unexpected score count")

            reranked = []
            for chunk, score in zip(chunks, scores):
                item = dict(chunk)
                item["retrieval_score"] = chunk.get("score")
                item["score"] = float(score)
                reranked.append(item)
            reranked.sort(key=lambda item: item["score"], reverse=True)
            selected = [item for item in reranked if item["score"] > threshold][:limit]
            return selected, {
                "status": "ok",
                "input_count": len(chunks),
                "output_count": len(selected),
                "threshold": threshold,
                "top_scores": [round(item["score"], 4) for item in reranked[:limit]],
            }
        except Exception as exc:
            logger.exception("Reranker failed; keep retrieval order")
            selected = chunks[:limit]
            return selected, {
                "status": "degraded",
                "input_count": len(chunks),
                "output_count": len(selected),
                "threshold": threshold,
                "top_scores": [],
                "error_type": type(exc).__name__,
                "fallback": "retrieval_order",
            }

    @staticmethod
    def llm_answer(question: str):
        prompt = PromptManager.DEFAULT_PROMPT.format(question=question)
        messages = LLMClient.convert_messages(prompt)
        return LLMClient().completions(messages, stream=True)

    @staticmethod
    def vlm_answer(question: str, image_urls: List[str]):
        prompt = f"根据图片回答问题：{question}"
        client = VLLMClient()
        messages = client.convert_messages_with_image_path(prompt, image_urls[0])
        return client.completions(messages, stream=True)

    def _execute(self, question: str, image_urls: List[str], run_id: str) -> Iterator:
        started_at = perf_counter()
        round_count = 0
        answer_length = 0
        stop_reason = "completed"
        route = "llm"
        references: List[AgentReference] = []

        yield self._event(
            AgentEventType.RUN_STARTED,
            run_id,
            {
                "kb_id": self._kb_id,
                "question": question,
                "max_rounds": self._n_round,
                "image_count": len(image_urls),
            },
        )

        image_descs = [
            QueryProcessor.extract_image_content(uuid.uuid4().hex, image_url)
            for image_url in image_urls
        ]

        if QueryProcessor.simple_query_check(question):
            route = "llm"
            stop_reason = "retrieval_not_required"
            yield self._event(
                AgentEventType.ROUTE_SELECTED,
                run_id,
                {"route": route, "reason": "问题不需要知识库检索"},
            )
            yield self._event(
                AgentEventType.GENERATION_STARTED,
                run_id,
                {"route": route, "grounded": False, "references": []},
            )
            for chunk in self.llm_answer(question):
                answer_length += len(self._chunk_content(chunk))
                yield chunk
            yield self._completed_event(
                run_id, started_at, stop_reason, round_count, route, references, answer_length
            )
            return

        if image_urls and QueryProcessor.simple_image_query_check(question, image_descs):
            route = "vlm"
            stop_reason = "direct_image_answer"
            references = [
                AgentReference(ref_id=f"input-image-{index}", content_type="input_image", url=url)
                for index, url in enumerate(image_urls, start=1)
            ]
            yield self._event(
                AgentEventType.ROUTE_SELECTED,
                run_id,
                {"route": route, "reason": "问题只依赖用户上传图片"},
            )
            yield self._event(
                AgentEventType.GENERATION_STARTED,
                run_id,
                {
                    "route": route,
                    "grounded": True,
                    "references": [item.model_dump(exclude_none=True) for item in references],
                },
            )
            for chunk in self.vlm_answer(question, image_urls):
                answer_length += len(self._chunk_content(chunk))
                yield chunk
            yield self._completed_event(
                run_id, started_at, stop_reason, round_count, route, references, answer_length
            )
            return

        answer_question = question
        total_sub_questions = []
        total_sub_summaries = []
        total_chunks = []

        for round_no in range(1, self._n_round + 1):
            round_count = round_no
            logger.info("Agent run {} round {}", run_id, round_no)
            if round_no == 1 and image_urls:
                generated_questions = QueryProcessor.expand_question_with_images(
                    answer_question, image_descs
                )
            else:
                generated_questions = QueryProcessor.extend_questions(answer_question)

            candidates = [question, *generated_questions] if round_no == 1 else generated_questions
            sub_questions = QueryProcessor.normalize_queries(candidates)
            if not sub_questions:
                sub_questions = [answer_question]
            total_sub_questions.extend(sub_questions)

            yield self._event(
                AgentEventType.QUERY_PLANNED,
                run_id,
                {"input_query": answer_question, "sub_queries": sub_questions},
                round_no,
            )

            retrieval_batch = self.multi_retrieval(sub_questions)
            channel_failures = [
                name
                for name, channel in retrieval_batch.channels.items()
                if channel.error
            ]
            for query_chunks in retrieval_batch.results:
                total_chunks.extend(query_chunks)
            retrieval_trace = retrieval_batch.trace_data()
            retrieval_trace["total_hits"] = sum(
                len(query_chunks) for query_chunks in retrieval_batch.results
            )
            yield self._event(
                AgentEventType.RETRIEVAL_COMPLETED,
                run_id,
                retrieval_trace,
                round_no,
            )
            if retrieval_batch.channels and len(channel_failures) == len(retrieval_batch.channels):
                raise RuntimeError("all retrieval channels failed")

            summaries = self._summarize_subqueries(sub_questions, retrieval_batch.results)
            total_sub_summaries.extend(summaries)
            decision = QueryProcessor.generate_next_instruction(
                question,
                total_sub_questions,
                total_sub_summaries,
            )
            sufficient = bool(decision["is_answer"])
            rewrite_query = str(decision.get("rewrite_query") or "").strip()
            will_continue = (
                not sufficient
                and round_no < self._n_round
                and bool(rewrite_query)
            )
            if sufficient:
                stop_reason = "evidence_sufficient"
            elif round_no >= self._n_round:
                stop_reason = "max_rounds_reached"
            elif not rewrite_query:
                stop_reason = "missing_rewrite_query"

            yield self._event(
                AgentEventType.EVIDENCE_EVALUATED,
                run_id,
                {
                    "sufficient": sufficient,
                    "reason": decision.get("reason", ""),
                    "rewrite_query": rewrite_query or None,
                    "will_continue": will_continue,
                    "stop_reason": None if will_continue else stop_reason,
                },
                round_no,
            )

            if not will_continue:
                break
            answer_question = rewrite_query

        retrieval_stop_reason = stop_reason
        text_chunks, image_chunks, page_chunks = self.merge_retrieval_results(total_chunks)
        text_chunks, rerank_trace = self._rerank_text_chunks(question, text_chunks)
        yield self._event(AgentEventType.RERANK_COMPLETED, run_id, rerank_trace)

        visual_chunks = self._select_visual_chunks(image_chunks, page_chunks)
        if not text_chunks and not visual_chunks:
            route_decision = {
                "route": "llm",
                "reason": "没有检索到可用证据，进入受约束的无证据回答",
            }
            stop_reason = "no_evidence"
        else:
            route_decision = QueryProcessor.select_generation_route(
                question,
                has_text=bool(text_chunks),
                visual_types=[
                    chunk.get("payload", {}).get("chunk_type", "image")
                    for chunk in visual_chunks
                ],
            )
        route = route_decision["route"]
        used_visual_chunks = visual_chunks if route == "vlm" else []
        references = self._build_references(text_chunks, used_visual_chunks)

        yield self._event(
            AgentEventType.ROUTE_SELECTED,
            run_id,
            {
                **route_decision,
                "text_evidence_count": len(text_chunks),
                "retrieved_visual_evidence_count": len(visual_chunks),
                "used_visual_evidence_count": len(used_visual_chunks),
            },
        )
        yield self._event(
            AgentEventType.GENERATION_STARTED,
            run_id,
            {
                "route": route,
                "grounded": bool(references),
                "references": [item.model_dump(exclude_none=True) for item in references],
            },
        )

        context = self.build_ref_context(text_chunks)
        if not references:
            prompt = PromptManager.NO_EVIDENCE_PROMPT.format(question=question)
            messages = LLMClient.convert_messages(prompt)
            response = LLMClient().completions(messages, stream=True)
        elif route == "llm":
            prompt = PromptManager.TEXT_PROMPT.format(context=context, question=question)
            messages = LLMClient.convert_messages(prompt)
            response = LLMClient().completions(messages, stream=True)
        else:
            prompt = PromptManager.IMAGE_PROMPT.format(context=context, question=question)
            image_url = used_visual_chunks[0]["payload"]["image_url"]
            client = VLLMClient()
            messages = client.convert_messages_with_image_path(prompt, image_url)
            response = client.completions(messages, stream=True)

        for chunk in response:
            answer_length += len(self._chunk_content(chunk))
            yield chunk

        yield self._completed_event(
            run_id,
            started_at,
            stop_reason,
            round_count,
            route,
            references,
            answer_length,
            retrieval_stop_reason=retrieval_stop_reason,
        )

    def _completed_event(
        self,
        run_id: str,
        started_at: float,
        stop_reason: str,
        round_count: int,
        route: str,
        references: List[AgentReference],
        answer_length: int,
        retrieval_stop_reason: str | None = None,
    ) -> AgentEvent:
        data = {
            "stop_reason": stop_reason,
            "round_count": round_count,
            "route": route,
            "reference_count": len(references),
            "answer_length": answer_length,
            "duration_ms": round((perf_counter() - started_at) * 1000),
        }
        if retrieval_stop_reason:
            data["retrieval_stop_reason"] = retrieval_stop_reason
        return self._event(
            AgentEventType.RUN_COMPLETED,
            run_id,
            data,
        )

    def run_events(
        self,
        question: str,
        image_urls: List[str] | None = None,
    ) -> Iterator[AgentEvent]:
        """Stream provider-independent Agent events for the API and evaluators."""

        run_id = uuid.uuid4().hex
        try:
            for item in self._execute(question, image_urls or [], run_id):
                if isinstance(item, AgentEvent):
                    yield item
                    continue
                content = self._chunk_content(item)
                if content:
                    yield self._event(
                        AgentEventType.ANSWER_DELTA,
                        run_id,
                        {"content": content},
                    )
        except GeneratorExit:
            raise
        except Exception:
            logger.exception("Agent run {} failed", run_id)
            yield self._event(
                AgentEventType.RUN_FAILED,
                run_id,
                {
                    "error_code": "agent_execution_failed",
                    "message": "Agent 执行失败，请查看服务日志",
                },
            )

    def run(self, question: str, image_urls: List[str] | None = None):
        """Backward-compatible stream of raw OpenAI completion chunks."""

        run_id = uuid.uuid4().hex
        for item in self._execute(question, image_urls or [], run_id):
            if not isinstance(item, AgentEvent):
                yield item
