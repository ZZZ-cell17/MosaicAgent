"""Stable public models for the single-Agent execution stream."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentEventType(str, Enum):
    RUN_STARTED = "run_started"
    ROUTE_SELECTED = "route_selected"
    QUERY_PLANNED = "query_planned"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    EVIDENCE_EVALUATED = "evidence_evaluated"
    RERANK_COMPLETED = "rerank_completed"
    GENERATION_STARTED = "generation_started"
    ANSWER_DELTA = "answer_delta"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class AgentReference(BaseModel):
    """A provider-independent reference returned with the answer trace."""

    ref_id: str
    content_type: str
    filename: str | None = None
    file_id: str | None = None
    url: str | None = None
    score: float | None = None
    text_preview: str | None = None


class EvidenceDecision(BaseModel):
    is_answer: bool
    rewrite_query: str = ""
    reason: str = ""


class GenerationRouteDecision(BaseModel):
    route: Literal["llm", "vlm"]
    reason: str = ""


class AgentEvent(BaseModel):
    """One observable state transition in an Agent run."""

    event: AgentEventType
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    round_no: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
