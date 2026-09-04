"""
基础检索器模块

该模块定义检索器的基础接口和通用功能：
- 检索器抽象基类
- 通用检索逻辑
- 检索结果处理
- 检索性能监控

主要功能：
1. 定义检索器标准接口
2. 提供通用检索流程
3. 检索结果格式化
4. 检索性能统计和优化
5. 缓存机制
"""
import concurrent.futures
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .image_retriever import ImageRetriever
from .text_retriever import TextRetriever
from ..utils.logger_utils import logger


@dataclass
class RetrievalChannelResult:
    """Results and operational metadata for one retrieval channel."""

    name: str
    results: list[list[dict]]
    duration_ms: int
    error: str | None = None

    def trace_data(self) -> dict:
        counts = [len(items) for items in self.results]
        return {
            "counts": counts,
            "total": sum(counts),
            "duration_ms": self.duration_ms,
            "status": "degraded" if self.error else "ok",
            "error_type": self.error,
        }


@dataclass
class RetrievalBatch:
    """Merged hits plus the per-channel data needed for observability."""

    results: list[list[dict]]
    channels: dict[str, RetrievalChannelResult]

    def trace_data(self) -> dict:
        return {
            "merged_counts": [len(items) for items in self.results],
            "channels": {
                name: result.trace_data()
                for name, result in self.channels.items()
            },
        }


class BaseRetriever:
    """基础检索器抽象类"""

    def __init__(self):
        self._image_retriever = ImageRetriever()
        self._text_retriever = TextRetriever()

    def retrieval_by_texts(self, kb_id: str, queries: list[str]):

        return self.retrieval_by_texts_with_trace(kb_id, queries).results

    @staticmethod
    def _run_channel(
        name: str,
        query_count: int,
        operation: Callable[[], list[list[dict]]],
    ) -> RetrievalChannelResult:
        started_at = perf_counter()
        try:
            results = operation() or [[] for _ in range(query_count)]
            if len(results) != query_count:
                raise ValueError(
                    f"retrieval channel returned {len(results)} result groups for {query_count} queries"
                )
            return RetrievalChannelResult(
                name=name,
                results=results,
                duration_ms=round((perf_counter() - started_at) * 1000),
            )
        except Exception as exc:
            logger.exception("Retrieval channel {} failed", name)
            return RetrievalChannelResult(
                name=name,
                results=[[] for _ in range(query_count)],
                duration_ms=round((perf_counter() - started_at) * 1000),
                error=type(exc).__name__,
            )

    def retrieval_by_texts_with_trace(self, kb_id: str, queries: list[str]) -> RetrievalBatch:
        """Run the four original MRAG retrieval channels concurrently."""

        if not queries:
            return RetrievalBatch(results=[], channels={})

        text_threshold = float(os.getenv("RETRIEVAL_TEXT_THRESHOLD", "0.7"))
        image_threshold = float(os.getenv("RETRIEVAL_IMAGE_THRESHOLD", "0.6"))
        page_threshold = float(os.getenv("RETRIEVAL_PAGE_THRESHOLD", "0.35"))
        operations = {
            "text_dense": lambda: self._text_retriever.vector_search(
                kb_id, queries, score_threshold=text_threshold
            ),
            "text_sparse": lambda: self._text_retriever.sparse_search(kb_id, queries),
            "image_dense": lambda: self._image_retriever.text2image_search(
                kb_id, queries, score_threshold=image_threshold
            ),
            "page_dense": lambda: self._image_retriever.text2page_search(
                kb_id, queries, score_threshold=page_threshold
            ),
        }

        channel_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            tasks = {
                executor.submit(self._run_channel, name, len(queries), operation): name
                for name, operation in operations.items()
            }
            for task in concurrent.futures.as_completed(tasks):
                result = task.result()
                channel_results[result.name] = result

        ordered_channels = {
            name: channel_results[name]
            for name in operations
        }
        merged = [[] for _ in queries]
        for channel in ordered_channels.values():
            for index, hits in enumerate(channel.results):
                merged[index].extend(hits)

        return RetrievalBatch(results=merged, channels=ordered_channels)
