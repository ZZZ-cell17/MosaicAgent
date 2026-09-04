"""Runtime configuration checks that never expose secret values."""

import os
from typing import Dict, Iterable, List


MODEL_REQUIREMENTS = {
    "llm": ("LLM_API_KEY", "LLM_MODEL_NAME"),
    "vlm": ("VLM_API_KEY", "VLM_MODEL_NAME"),
    "text_embedding": (
        "TEXT_EMBEDDING_API_KEY",
        "TEXT_EMBEDDING_MODEL_NAME",
    ),
    "image_embedding": (
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MULTIMODAL_EMBEDDING_MODEL_NAME",
    ),
    "reranker": (
        "TEXT_RERANKER_BASE_URL",
        "TEXT_RERANKER_API_KEY",
        "TEXT_RERANKER_MODEL_NAME",
    ),
}


def _has_value(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value) and not value.startswith("<your ")


def missing_settings(names: Iterable[str]) -> List[str]:
    return [name for name in names if not _has_value(name)]


def get_missing_model_settings() -> List[str]:
    return sorted({name for names in MODEL_REQUIREMENTS.values() for name in missing_settings(names)})


def get_bounded_int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def get_runtime_status() -> Dict:
    model_status = {}
    for component, requirements in MODEL_REQUIREMENTS.items():
        missing = missing_settings(requirements)
        model_status[component] = {
            "configured": not missing,
            "missing": missing,
        }

    qdrant_mode = os.getenv("QDRANT_MODE", "local").strip().lower()
    if qdrant_mode == "local":
        storage_missing = []
    elif qdrant_mode == "server":
        storage_missing = missing_settings(("QDRANT_URL", "QDRANT_PORT"))
    else:
        storage_missing = ["QDRANT_MODE(local|server)"]

    storage_status = {
        "configured": not storage_missing,
        "mode": qdrant_mode,
        "missing": storage_missing,
    }
    configuration_errors = []
    for name, default, minimum, maximum in (
        ("MRAG_MAX_ROUNDS", 3, 1, 10),
        ("MRAG_MAX_SUBQUERIES", 3, 1, 10),
        ("MRAG_MAX_TEXT_CONTEXTS", 8, 1, 50),
        ("MRAG_MAX_VISUAL_CONTEXTS", 1, 1, 4),
        ("MRAG_SUMMARY_MAX_CHUNKS", 8, 1, 50),
    ):
        try:
            get_bounded_int_setting(name, default, minimum, maximum)
        except ValueError as exc:
            configuration_errors.append(str(exc))

    configuration_status = {
        "configured": not configuration_errors,
        "errors": configuration_errors,
    }
    ready = configuration_status["configured"] and storage_status["configured"] and all(
        item["configured"] for item in model_status.values()
    )
    return {
        "status": "ready" if ready else "configuration_required",
        "ready": ready,
        "storage": storage_status,
        "models": model_status,
        "configuration": configuration_status,
    }
