# -*- coding: utf-8 -*-
# =====================
# 
# 
# Author: liumin.423
# Date:   2025/7/7
# =====================
import os
from contextlib import asynccontextmanager
from optparse import OptionParser
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

load_dotenv()


def log_setting():
    log_path = os.getenv("LOG_PATH", Path(__file__).resolve().parent / "logs" / "server.log")
    log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} {level} {module}.{function} {message}"
    logger.add(log_path, format=log_format, rotation="200 MB")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log_setting()
    try:
        yield
    finally:
        from genie_tool.tool.mrag.storage import VectorStore

        VectorStore().close()


def create_app() -> FastAPI:
    _app = FastAPI(
        title="MosaicAgent",
        description="Multimodal RAG-powered knowledge agent",
        lifespan=lifespan,
    )

    register_middleware(_app)
    register_router(_app)

    @_app.get("/health")
    async def health():
        return JSONResponse({"status": "ok", "service": "mosaic-agent"})

    @_app.get("/ready")
    async def ready():
        from genie_tool.tool.mrag.config import get_runtime_status

        status = get_runtime_status()
        return JSONResponse(status, status_code=200 if status["ready"] else 503)

    return _app

def register_middleware(app: FastAPI):
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOW_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )


def register_router(app: FastAPI):
    from genie_tool.api import api_router
    app.include_router(api_router)


app = create_app()


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("--host", dest="host", type="string", default="0.0.0.0")
    parser.add_option("--port", dest="port", type="int", default=1601)
    parser.add_option("--workers", dest="workers", type="int", default=1)
    (options, args) = parser.parse_args()

    print(f"Start params: {options}")

    uvicorn.run(
        app="server:app",
        host=options.host,
        port=options.port,
        workers=options.workers,
        reload=os.getenv("ENV", "local") == "local",
    )
