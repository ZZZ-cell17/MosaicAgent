from types import SimpleNamespace

from genie_tool.tool.mrag.query.agent import AgenticRAG
from genie_tool.tool.mrag.query.models import AgentEventType
from genie_tool.tool.mrag.query.query_processor import QueryProcessor
from genie_tool.tool.mrag.retrieval.retriever import (
    BaseRetriever,
    RetrievalBatch,
    RetrievalChannelResult,
)


def completion_chunk(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )


def text_hit(score: float = 0.9):
    return {
        "id": "point-1",
        "score": score,
        "payload": {
            "chunk_type": "text",
            "chunk_id": "chunk-1",
            "file_sorted": "file-1-0",
            "file_id": "file-1",
            "filename": "guide.md",
            "file_url": "http://testserver/files/guide.md",
            "text": "MosaicAgent uses multimodal retrieval.",
        },
    }


def test_query_normalization_deduplicates_and_limits(monkeypatch):
    monkeypatch.setenv("MRAG_MAX_SUBQUERIES", "2")

    result = QueryProcessor.normalize_queries([
        "- first query",
        "1. second query",
        "first query",
        "* third query",
    ])

    assert result == ["first query", "second query"]


def test_json_parser_accepts_plain_and_fenced_json():
    assert QueryProcessor.parse_json_object('{"is_answer": 1}')["is_answer"] == 1
    assert QueryProcessor.parse_json_object(
        '```json\n{"route": "llm", "reason": "text is enough"}\n```'
    )["route"] == "llm"


def test_summary_context_deduplicates_and_limits(monkeypatch):
    monkeypatch.setenv("MRAG_SUMMARY_MAX_CHUNKS", "1")
    duplicate = text_hit()
    another = {**text_hit(), "id": "point-2"}
    another["payload"] = {**text_hit()["payload"], "chunk_id": "chunk-2", "text": "second"}

    context = QueryProcessor.build_context([duplicate, duplicate, another])

    assert context.count("[文本片段开始]") == 1
    assert "MosaicAgent uses multimodal retrieval." in context
    assert "second" not in context


def test_retriever_reports_each_channel_and_degrades_independently(monkeypatch):
    class FakeTextRetriever:
        @staticmethod
        def vector_search(*_args, **_kwargs):
            return [[text_hit()]]

        @staticmethod
        def sparse_search(*_args, **_kwargs):
            raise TimeoutError("sparse timeout")

    class FakeImageRetriever:
        @staticmethod
        def text2image_search(*_args, **_kwargs):
            return [[]]

        @staticmethod
        def text2page_search(*_args, **_kwargs):
            return [[]]

    retriever = BaseRetriever.__new__(BaseRetriever)
    retriever._text_retriever = FakeTextRetriever()
    retriever._image_retriever = FakeImageRetriever()

    batch = retriever.retrieval_by_texts_with_trace("kb", ["question"])

    assert list(batch.channels) == [
        "text_dense",
        "text_sparse",
        "image_dense",
        "page_dense",
    ]
    assert batch.channels["text_dense"].trace_data()["total"] == 1
    assert batch.channels["text_sparse"].trace_data()["status"] == "degraded"
    assert batch.results == [[text_hit()]]


def test_agent_stream_exposes_original_mrag_decision_path(monkeypatch):
    from genie_tool.tool.mrag.query import agent as agent_module

    channel = RetrievalChannelResult(
        name="text_dense",
        results=[[text_hit()]],
        duration_ms=4,
    )

    class FakeRetriever:
        @staticmethod
        def retrieval_by_texts_with_trace(_kb_id, _queries):
            return RetrievalBatch(results=[[text_hit()]], channels={"text_dense": channel})

    class FakeReranker:
        @staticmethod
        def rerank(_question, texts):
            return [0.88 for _ in texts]

    class FakeLLMClient:
        @staticmethod
        def convert_messages(prompt):
            return [{"role": "user", "content": prompt}]

        @staticmethod
        def completions(_messages, **kwargs):
            assert kwargs["stream"] is True
            return iter([completion_chunk("grounded answer")])

    monkeypatch.setattr(QueryProcessor, "simple_query_check", staticmethod(lambda _q: False))
    monkeypatch.setattr(QueryProcessor, "extend_questions", staticmethod(lambda _q: ["planned query"]))
    monkeypatch.setattr(
        QueryProcessor,
        "summarize_subquery",
        staticmethod(lambda _q, _chunks: "enough evidence"),
    )
    monkeypatch.setattr(
        QueryProcessor,
        "generate_next_instruction",
        staticmethod(lambda *_args: {
            "is_answer": True,
            "rewrite_query": "",
            "reason": "evidence covers the question",
        }),
    )
    monkeypatch.setattr(
        QueryProcessor,
        "select_generation_route",
        staticmethod(lambda *_args, **_kwargs: {
            "route": "llm",
            "reason": "text evidence is sufficient",
        }),
    )
    monkeypatch.setattr(agent_module, "get_text_reranker", lambda: FakeReranker())
    monkeypatch.setattr(agent_module, "LLMClient", FakeLLMClient)

    agent = AgenticRAG.__new__(AgenticRAG)
    agent._n_round = 2
    agent._kb_id = "demo-kb"
    agent._retriever = FakeRetriever()
    events = list(agent.run_events("What is MosaicAgent?"))

    event_names = [event.event for event in events]
    assert event_names == [
        AgentEventType.RUN_STARTED,
        AgentEventType.QUERY_PLANNED,
        AgentEventType.RETRIEVAL_COMPLETED,
        AgentEventType.EVIDENCE_EVALUATED,
        AgentEventType.RERANK_COMPLETED,
        AgentEventType.ROUTE_SELECTED,
        AgentEventType.GENERATION_STARTED,
        AgentEventType.ANSWER_DELTA,
        AgentEventType.RUN_COMPLETED,
    ]
    assert events[2].data["channels"]["text_dense"]["total"] == 1
    assert events[3].data["sufficient"] is True
    assert events[5].data["retrieved_visual_evidence_count"] == 0
    assert events[5].data["used_visual_evidence_count"] == 0
    assert events[6].data["references"][0]["filename"] == "guide.md"
    assert events[7].data["content"] == "grounded answer"
    assert events[8].data["stop_reason"] == "evidence_sufficient"


def test_agent_stops_after_configured_round_limit(monkeypatch):
    from genie_tool.tool.mrag.query import agent as agent_module

    empty_channel = RetrievalChannelResult(
        name="text_dense",
        results=[[]],
        duration_ms=1,
    )

    class EmptyRetriever:
        @staticmethod
        def retrieval_by_texts_with_trace(_kb_id, _queries):
            return RetrievalBatch(results=[[]], channels={"text_dense": empty_channel})

    class FakeLLMClient:
        @staticmethod
        def convert_messages(prompt):
            return [{"role": "user", "content": prompt}]

        @staticmethod
        def completions(_messages, **_kwargs):
            return iter([completion_chunk("no evidence")])

    monkeypatch.setattr(QueryProcessor, "simple_query_check", staticmethod(lambda _q: False))
    monkeypatch.setattr(QueryProcessor, "extend_questions", staticmethod(lambda q: [q]))
    monkeypatch.setattr(
        QueryProcessor,
        "generate_next_instruction",
        staticmethod(lambda *_args: {
            "is_answer": False,
            "rewrite_query": "try another query",
            "reason": "evidence is incomplete",
        }),
    )
    monkeypatch.setattr(agent_module, "LLMClient", FakeLLMClient)

    agent = AgenticRAG.__new__(AgenticRAG)
    agent._n_round = 2
    agent._kb_id = "demo-kb"
    agent._retriever = EmptyRetriever()
    events = list(agent.run_events("missing topic"))

    planned = [event for event in events if event.event == AgentEventType.QUERY_PLANNED]
    completed = next(event for event in events if event.event == AgentEventType.RUN_COMPLETED)
    assert [event.round_no for event in planned] == [1, 2]
    assert completed.data["round_count"] == 2
    assert completed.data["stop_reason"] == "no_evidence"
    assert completed.data["retrieval_stop_reason"] == "max_rounds_reached"


def test_agent_reports_all_channel_failures_before_run_failed(monkeypatch):
    failed_channels = {
        name: RetrievalChannelResult(
            name=name,
            results=[[]],
            duration_ms=1,
            error="TimeoutError",
        )
        for name in ("text_dense", "text_sparse", "image_dense", "page_dense")
    }

    class FailedRetriever:
        @staticmethod
        def retrieval_by_texts_with_trace(_kb_id, _queries):
            return RetrievalBatch(results=[[]], channels=failed_channels)

    monkeypatch.setattr(QueryProcessor, "simple_query_check", staticmethod(lambda _q: False))
    monkeypatch.setattr(QueryProcessor, "extend_questions", staticmethod(lambda q: [q]))

    agent = AgenticRAG.__new__(AgenticRAG)
    agent._n_round = 1
    agent._kb_id = "demo-kb"
    agent._retriever = FailedRetriever()
    events = list(agent.run_events("question"))

    assert [event.event for event in events] == [
        AgentEventType.RUN_STARTED,
        AgentEventType.QUERY_PLANNED,
        AgentEventType.RETRIEVAL_COMPLETED,
        AgentEventType.RUN_FAILED,
    ]
    assert all(
        channel["status"] == "degraded"
        for channel in events[2].data["channels"].values()
    )
    assert events[3].data["error_code"] == "agent_execution_failed"


def test_reranker_failure_uses_retrieval_order(monkeypatch):
    from genie_tool.tool.mrag.query import agent as agent_module

    class BrokenReranker:
        @staticmethod
        def rerank(_question, _texts):
            raise TimeoutError("reranker unavailable")

    monkeypatch.setattr(agent_module, "get_text_reranker", lambda: BrokenReranker())
    chunks = [text_hit(0.9), {**text_hit(0.8), "id": "point-2"}]

    selected, trace = AgenticRAG._rerank_text_chunks("question", chunks)

    assert selected == chunks
    assert trace["status"] == "degraded"
    assert trace["fallback"] == "retrieval_order"
