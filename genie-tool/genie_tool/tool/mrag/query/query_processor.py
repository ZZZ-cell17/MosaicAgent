"""
查询预处理模块

该模块负责对用户查询进行预处理和优化：
- 查询理解和分析
- 查询改写和扩展
- 意图识别
- 多轮对话管理

主要功能：
1. 查询文本清洗和标准化
2. 查询意图识别和分类
3. 查询改写和扩展
4. 实体识别和链接
5. 多轮对话上下文管理
6. 查询质量评估和过滤
"""
import json
import os
import re
from typing import List, Dict

from .models import EvidenceDecision, GenerationRouteDecision
from ..generation import PromptManager
from ..generation.llm import LLMClient
from ..utils import caption_utils
from ..utils.logger_utils import logger
from ..utils.time_utils import time_it

tools = [
    {
        "code": "1",
        "name": "图片问答",
        "description": "直接对图片内容进行理解、总结、问答、翻译等；如果用户输入包含图片附件，且问题和图片相关，请选择此工具。"
    },
    {
        "code": "3",
        "name": "文本检索",
        "description": "根据输入文本，搜索相关文本或图片；如果用户输入问题不为空，且进行额外搜索可能对回答问题有帮助，请选择此工具。"
    }
]


class QueryProcessor:
    """查询处理器类"""

    @staticmethod
    def normalize_queries(queries: List[str], limit: int | None = None) -> List[str]:
        """Normalize model-generated query lines and remove duplicates."""

        max_queries = limit or max(1, int(os.getenv("MRAG_MAX_SUBQUERIES", "3")))
        normalized = []
        seen = set()
        for query in queries:
            query = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", query).strip()
            if not query or query in seen:
                continue
            seen.add(query)
            normalized.append(query)
            if len(normalized) >= max_queries:
                break
        return normalized

    @staticmethod
    def parse_json_object(response: str) -> dict:
        """Parse either plain JSON or JSON wrapped in a Markdown fence."""

        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*", "", response, count=1, flags=re.IGNORECASE)
            response = re.sub(r"\s*```$", "", response, count=1)

        try:
            parsed = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", response, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))

        if not isinstance(parsed, dict):
            raise ValueError("model response must be a JSON object")
        return parsed

    @staticmethod
    @time_it
    def extend_questions(question: str):
        prompt = PromptManager.QUERY_EXTEND_PROMPT.format(question=question)
        messages = LLMClient.convert_messages(prompt)
        response = LLMClient().completions(messages,
                                           stream=False,
                                           temperature=0.01,
                                           max_tokens=256,
                                           )
        resp = response

        return QueryProcessor.normalize_queries(resp.splitlines())

    @staticmethod
    @time_it
    def extract_image_content(_filename, image_url: str):
        return caption_utils.generate_caption(image_url)

    @staticmethod
    @time_it
    def get_pre_think_results(question: str):
        prompt = PromptManager.PRE_THINK_PROMPT.format(task=question)
        messages = LLMClient.convert_messages(prompt)
        response = LLMClient().completions(messages,
                                           stream=False,
                                           temperature=0.01,
                                           max_tokens=256,
                                           )
        return response

    @staticmethod
    def build_context(docs: List[Dict]):
        max_chunks = max(1, int(os.getenv("MRAG_SUMMARY_MAX_CHUNKS", "8")))
        context_parts = []
        seen = set()
        for doc in docs:
            payload = doc.get("payload", {})
            text = payload.get("text")
            if not text:
                continue
            key = payload.get("chunk_id") or payload.get("file_sorted") or text
            if key in seen:
                continue
            seen.add(key)
            context_parts.append("[文本片段开始]\n" + text + "\n[文本片段结束]")
            if len(context_parts) >= max_chunks:
                break

        return "\n".join(context_parts)

    @staticmethod
    @time_it
    def summarize_subquery(question, chunks: List[Dict]):
        context = QueryProcessor.build_context(chunks)
        prompt = PromptManager.SUMMARIZE_PROMPT.format(context=context, question=question)
        messages = LLMClient.convert_messages(prompt)
        response = LLMClient().completions(messages,
                                           stream=False,
                                           temperature=0.01,
                                           max_tokens=512)
        return response

    @staticmethod
    @time_it
    def generate_next_instruction(question: str, sub_questions: List[str], summarized_contexts: List[str]):
        prompt = PromptManager.POST_CHECK_PROMPT.format(
            question=question,
            sub_questions="\n".join(sub_questions),
            context="\n".join(summarized_contexts)
        )
        messages = LLMClient.convert_messages(prompt)
        resp = LLMClient().completions(messages,
                                       stream=False,
                                       temperature=0.01,
                                       max_tokens=256,
                                       )

        try:
            decision = EvidenceDecision.model_validate(QueryProcessor.parse_json_object(resp))
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid evidence decision, stop safely: {}", type(exc).__name__)
            decision = EvidenceDecision(
                is_answer=True,
                reason="充分性判断输出无法解析，采用安全停止策略",
            )

        logger.info("next_instruction: {}", decision.model_dump())
        return decision.model_dump()

    @staticmethod
    @time_it
    def select_generation_route(
        question: str,
        has_text: bool,
        visual_types: List[str],
    ) -> Dict:
        """Choose LLM or VLM after retrieval using a constrained model decision."""

        if not visual_types:
            return GenerationRouteDecision(
                route="llm",
                reason="检索结果不包含视觉证据",
            ).model_dump()
        if not has_text:
            return GenerationRouteDecision(
                route="vlm",
                reason="仅检索到视觉证据",
            ).model_dump()

        prompt = PromptManager.GENERATION_ROUTE_PROMPT.format(
            question=question,
            visual_types=", ".join(sorted(set(visual_types))),
        )
        messages = LLMClient.convert_messages(prompt)
        response = LLMClient().completions(
            messages,
            stream=False,
            temperature=0.01,
            max_tokens=128,
        )
        try:
            decision = GenerationRouteDecision.model_validate(
                QueryProcessor.parse_json_object(response)
            )
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid generation route, preserve visual evidence: {}", type(exc).__name__)
            decision = GenerationRouteDecision(
                route="vlm",
                reason="路由输出无法解析，回退到可处理全部证据的 VLM",
            )
        return decision.model_dump()

    @staticmethod
    def expand_question_with_images(question: str, image_descs: List[str]):
        logger.info("开始前置的思考")
        pre_think_results = QueryProcessor.get_pre_think_results(question)
        logger.info(f"前置思考结果: {pre_think_results}")

        logger.info("开始基于图片生成子查询")
        if image_descs:
            full_image_desc = "\n".join(image_descs)
            full_input = f"输入:\n{pre_think_results}\n<图片描述>{full_image_desc}</图片描述>"
        else:
            full_input = f"输入:\n{pre_think_results}"

        prompt = PromptManager.QUERY_EXTEND_WITH_PRE_THINK_PROMPT.format(pre_think_result_reminder=full_input)
        messages = LLMClient.convert_messages(prompt)
        resp = LLMClient().completions(messages,
                                       stream=False,
                                       temperature=0.01,
                                       max_tokens=256,
                                       )

        logger.info(f"expand_question_with_images: {resp}")
        return QueryProcessor.normalize_queries(resp.splitlines())

    @staticmethod
    @time_it
    def simple_query_check(question: str):
        prompt = PromptManager.SIMPLE_QUERY_CHECK_PROMPT.format(question=question)
        client = LLMClient()
        messages = client.convert_messages(prompt)
        resp = LLMClient().completions(messages, stream=False, max_tokens=10)

        logger.info(f"simple_query_check: {resp}")
        return resp.strip().startswith("0")

    @staticmethod
    @time_it
    def simple_image_query_check(question: str, image_descs: List[str]):
        prompt = PromptManager.SIMPLE_IMAGE_QUERY_CHECK_PROMPT.format(
            tools_info=json.dumps(tools, ensure_ascii=False),
            question=question,
            image_desc="\n".join(image_descs)
        )
        messages = LLMClient.convert_messages(prompt)
        resp = LLMClient().completions(messages, stream=False, max_tokens=10)

        logger.info(f"simple_image_query_check: {resp}")
        try:
            tool_ids = [tool_id.strip() for tool_id in resp.split(",")]
            if len(tool_ids) == 1 and tool_ids[0] == "1":
                return True
        except (AttributeError, TypeError):
            return False

        return False
