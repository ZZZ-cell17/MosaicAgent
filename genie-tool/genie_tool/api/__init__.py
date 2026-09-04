# -*- coding: utf-8 -*-
# =====================
# 
# 
# Author: liumin.423
# Date:   2025/7/7
# =====================
from fastapi import APIRouter

from ..tool.mrag.api.routes.document import router as document_router
from ..tool.mrag.api.routes.query import router as query_router
from ..tool.mrag.utils.oss_utils import router as storage_router

api_router = APIRouter(prefix="/v1")

api_router.include_router(document_router)
api_router.include_router(query_router)
api_router.include_router(storage_router)
