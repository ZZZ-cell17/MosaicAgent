"""MRAG query API."""

import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse, ServerSentEvent

from ...query import AgenticRAG
from ...config import get_bounded_int_setting, get_missing_model_settings
from ...utils.logger_utils import logger
from ...utils.url_utils import hosts_from_env, hosts_from_urls, validate_http_url


router = APIRouter(prefix="/mrag", tags=["mrag query"])


class MultimodalRAGRequest(BaseModel):
    question: str = Field(..., min_length=1)
    image_urls: List[str] = Field(default_factory=list, max_length=4)
    kb_id: Optional[str] = None
    include_trace: bool = True


@router.post("/query")
async def query(request: MultimodalRAGRequest):
    """Run the AgenticRAG query loop and stream the final answer."""
    missing_settings = get_missing_model_settings()
    if missing_settings:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "MRAG model configuration is incomplete",
                "missing": missing_settings,
            },
        )

    kb_id = request.kb_id or os.getenv("DEFAULT_KB_ID")
    if not kb_id:
        raise HTTPException(
            status_code=422,
            detail="kb_id is required when DEFAULT_KB_ID is not configured",
        )
    allowed_image_hosts = hosts_from_urls((
        os.getenv("SERVER_BASE_URL", "http://127.0.0.1:1601"),
        os.getenv("OSS_SERVER_BASE_URL"),
    )) | hosts_from_env("QUERY_IMAGE_ALLOWED_HOSTS")
    try:
        image_urls = [
            validate_http_url(url, allowed_hosts=allowed_image_hosts)
            for url in request.image_urls
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        n_round = get_bounded_int_setting("MRAG_MAX_ROUNDS", 3, 1, 10)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("MRAG query kb_id={} question={}", kb_id, request.question)
    agent = AgenticRAG(kb_id=kb_id, n_round=n_round)

    def generator():
        always_visible = {"answer_delta", "run_completed", "run_failed"}
        for event in agent.run_events(request.question, image_urls):
            event_name = event.event.value
            if request.include_trace or event_name in always_visible:
                yield ServerSentEvent(
                    event=event_name,
                    data=event.model_dump_json(exclude_none=True),
                )
        yield ServerSentEvent(event="done", data="[DONE]")

    return EventSourceResponse(generator())
