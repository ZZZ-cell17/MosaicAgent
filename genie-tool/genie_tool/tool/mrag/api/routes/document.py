import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from ...document import DocumentProcessor
from ...enums.source_type_enums import SourceTypeEnum
from ...enums.task_status_enums import TaskStatusEnum
from ...storage import VectorStore
from ...storage.models.kb_file_model import KBFileModel
from ...storage.models.kb_model import KBModel
from ...storage.store_factory import get_kb_store, get_kb_file_store
from ...utils import download_utils, crawl_utils
from ...utils.logger_utils import logger
from ...utils.oss_utils import (
    build_local_storage_url,
    get_local_storage_file,
    upload_local_storage,
)
from ...utils.url_utils import hosts_from_env, validate_http_url

router = APIRouter(prefix="/documents", tags=["文档处理"])

# These are the formats implemented by document.parser.get_document_parser.
SUPPORTED_FILE_EXTENSIONS = {'.pdf', '.docx', '.md', '.txt', '.png', '.jpg', '.jpeg'}

# 最大文件大小 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024
KB_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


def validate_filename(filename: str) -> str:
    safe_filename = Path(filename).name
    if safe_filename != filename or safe_filename in {"", ".", ".."}:
        raise ValueError("文件名包含非法路径")
    extension = Path(safe_filename).suffix.lower()
    if extension not in SUPPORTED_FILE_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {extension or '未知'}")
    return safe_filename


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档或图片到本地存储并返回访问链接。
    
    支持的文件类型: 
    - 文档: PDF, DOCX, Markdown, TXT
    - 图片: JPG, JPEG, PNG
    最大文件大小: 50MB
    
    返回:
        - document_id: 文档唯一标识
        - filename: 原始文件名
        - file_size: 文件大小(字节)
        - content_type: 文件类型
        - upload_time: 上传时间
        - permanent_url: 本地文件访问链接
    """
    try:
        file_extension = Path(file.filename or "").suffix.lower()
        if file_extension not in SUPPORTED_FILE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"不支持的文件类型: {file_extension or '未知'}。"
                    f"支持的类型: {', '.join(sorted(SUPPORTED_FILE_EXTENSIONS))}"
                )
            )

        # 读取文件内容并验证大小
        file_content = await file.read()
        file_size = len(file_content)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制。最大允许: {MAX_FILE_SIZE // (1024 * 1024)}MB，当前文件: {file_size // (1024 * 1024)}MB"
            )

        if file_size == 0:
            raise HTTPException(status_code=400, detail="文件为空")

        # 生成文档ID和文件名
        document_id = str(uuid.uuid4())
        original_filename = file.filename
        safe_filename = validate_filename(original_filename)

        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        logger.info(f"文件暂存到: {temp_file_path}")
        try:
            upload_date = datetime.now()
            logger.info(f"开始保存文档: {safe_filename}, 大小: {file_size} bytes")
            permanent_url = upload_local_storage(
                temp_file_path,
                file_id=document_id,
                filename=safe_filename,
            )
            logger.info(f"文档保存成功: {document_id}, 链接: {permanent_url}")

            # 返回上传结果
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "文档上传成功",
                    "data": {
                        "document_id": document_id,
                        "filename": safe_filename,
                        "original_filename": original_filename,
                        "file_size": file_size,
                        "content_type": file.content_type,
                        "upload_time": upload_date.isoformat(),
                        "permanent_url": permanent_url,
                        "storage_path": f"{document_id}/{safe_filename}"
                    }
                }
            )

        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文档上传过程中发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


class CreateKnowledgeBaseRequest(BaseModel):
    kb_id: Optional[str] = Field(default=None, min_length=1, max_length=64, pattern=KB_ID_PATTERN)
    kb_name: Optional[str] = Field(default=None, max_length=100)
    kb_desc: Optional[str] = Field(default=None, max_length=500)
    chunk_type: Literal["default", "markdown"] = "markdown"
    chunk_size: Optional[int] = Field(default=None, ge=1, le=10000)
    chunk_overlap_size: Optional[int] = Field(default=None, ge=0, le=5000)

    @model_validator(mode="after")
    def validate_overlap(self):
        if (
            self.chunk_size is not None
            and self.chunk_overlap_size is not None
            and self.chunk_overlap_size >= self.chunk_size
        ):
            raise ValueError("chunk_overlap_size 必须小于 chunk_size")
        return self


@router.post("/create_knowledge_base")
async def create_knowledge_base(request: CreateKnowledgeBaseRequest):
    kb_store = get_kb_store()
    if not request.kb_id:
        request.kb_id = uuid.uuid4().hex
    kb_id = request.kb_id
    kb_model = KBModel(
        kb_id=kb_id,
        kb_name=request.kb_name,
        kb_desc=request.kb_desc,
        chunk_type=request.chunk_type,
        chunk_size=request.chunk_size,
        chunk_overlap_size=request.chunk_overlap_size,
        create_time=datetime.now(),
        modify_time=datetime.now(),
    )
    try:
        created = kb_store.create_kb(kb_model)
    except Exception as exc:
        logger.exception("Create knowledge base failed: {}", kb_id)
        raise HTTPException(status_code=500, detail="创建知识库失败") from exc
    if not created:
        raise HTTPException(status_code=409, detail="知识库已存在")

    res = {
        "code": 200,
        "msg": "success",
        "data": kb_model.model_dump()
    }
    logger.info(f"create knowledge base, {res}")
    return res


class DeleteKnowledgeBaseRequest(BaseModel):
    kb_id: str = Field(..., min_length=1, max_length=64, pattern=KB_ID_PATTERN)


@router.post("/delete_knowledge_base")
async def delete_knowledge_base(request: DeleteKnowledgeBaseRequest):
    kb_store = get_kb_store()
    kb_model = KBModel(kb_id=request.kb_id)
    try:
        deleted = kb_store.delete_kb(kb_model)
    except Exception as exc:
        logger.exception("Delete knowledge base failed: {}", request.kb_id)
        raise HTTPException(status_code=500, detail="删除知识库失败") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="知识库不存在")

    try:
        vector_store = VectorStore()
        vectors_deleted = [
            vector_store.delete_text_by_kb_id(request.kb_id),
            vector_store.delete_image_by_kb_id(request.kb_id),
            vector_store.delete_page_by_kb_id(request.kb_id),
        ]
        if not all(vectors_deleted):
            raise RuntimeError("至少一个向量集合清理失败")
        deleted_files = get_kb_file_store().delete_by_kb_id(request.kb_id)
    except Exception as exc:
        logger.exception("Delete knowledge base vectors failed: {}", request.kb_id)
        raise HTTPException(status_code=500, detail="知识库已删除，但关联数据清理失败") from exc

    return {
        "code": 200,
        "msg": "success",
        "data": {"deleted_files": deleted_files}
    }


class ListKnowledgeBaseRequest(BaseModel):
    page_no: int = Field(1, ge=1, description="page_no")
    page_size: int = Field(10, ge=1, le=100, description="page_size")


@router.post("/list_knowledge_base")
async def list_knowledge_base(request: ListKnowledgeBaseRequest):
    kb_store = get_kb_store()
    kb_models = kb_store.get_kbs(request.page_no, request.page_size)
    res = {
        "code": 200,
        "msg": "success",
        "data": {
            "list": [kb_model.model_dump() for kb_model in kb_models],
            "page_no": request.page_no,
            "page_size": request.page_size,
        }
    }
    logger.info(f"list knowledge base, {res}")
    return res


class FileReference(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255, description="文件名")
    document_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    file_url: Optional[str] = Field(default=None, min_length=1, description="受控远程文件 URL")
    file_type: Literal["file"] = "file"

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        return validate_filename(value)

    @field_validator("document_id")
    @classmethod
    def safe_document_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (Path(value).name != value or value in {".", ".."}):
            raise ValueError("document_id 非法")
        return value

    @model_validator(mode="after")
    def require_one_source(self):
        if bool(self.document_id) == bool(self.file_url):
            raise ValueError("document_id 和 file_url 必须且只能提供一个")
        if self.file_url:
            validate_http_url(self.file_url)
        return self


def build_file_record(kb_id: str, file_id: str, file_url: str, title: str, source_type: str) -> KBFileModel:
    now = datetime.now()
    return KBFileModel(
        kb_id=kb_id,
        file_id=file_id,
        file_url=file_url,
        title=title,
        source_type=source_type,
        task_status={"global_status": TaskStatusEnum.PENDING.value},
        file_status=TaskStatusEnum.PENDING.value,
        doc_count=0,
        create_time=now,
        modify_time=now,
        deleted=0,
    )


def add_file(file_id, filename, file_url, kb_id, source_file_path=None, remote_hosts=None):
    tempdir = tempfile.gettempdir()
    work_dir = f"{tempdir}/{file_id}"
    os.makedirs(os.path.join(tempdir, file_id), exist_ok=True)

    kb_file = build_file_record(kb_id, file_id, file_url, filename, SourceTypeEnum.FILE.value)
    kb_file_store = get_kb_file_store()

    local_file_path = source_file_path or os.path.join(tempdir, file_id, filename)
    try:
        if not source_file_path:
            download_utils.download_file(
                file_url,
                local_file_path,
                allowed_hosts=set(remote_hosts or []),
                max_bytes=MAX_FILE_SIZE,
            )

        kb_file.file_status = TaskStatusEnum.RUNNING.value
        kb_file.task_status = {"global_status": TaskStatusEnum.RUNNING.value}
        kb_file_store.update_file(kb_file)
        processor = DocumentProcessor(kb_id, file_id, work_dir, local_file_path, file_url)
        processor.process()

        kb_file.file_status = TaskStatusEnum.SUCCESS.value
        kb_file.task_status = {"global_status": TaskStatusEnum.SUCCESS.value}
        kb_file_store.update_file(kb_file)
    except Exception as exc:
        logger.exception(f"文件入库失败: {filename}")
        kb_file.file_status = TaskStatusEnum.FAILED.value
        kb_file.task_status = {
            "global_status": TaskStatusEnum.FAILED.value,
            "error": str(exc)[:500],
        }
        kb_file_store.update_file(kb_file)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


class AddFilesRequest(BaseModel):
    files: List[FileReference] = Field(..., min_length=1, description="文件列表")
    kb_id: str = Field(..., min_length=1, max_length=64, pattern=KB_ID_PATTERN, description="知识库id")


@router.post("/add_files")
async def add_files(request: AddFilesRequest, background_tasks: BackgroundTasks):
    kb_file_store = get_kb_file_store()
    tasks = []
    for file in request.files:
        filename = file.filename
        source_file_path = None
        remote_hosts = None
        if file.document_id:
            try:
                source_file_path = str(get_local_storage_file(file.document_id, filename))
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=f"上传文件不存在: {filename}") from exc
            file_url = build_local_storage_url(file.document_id, filename)
        else:
            if os.getenv("ENABLE_REMOTE_FILE_IMPORT", "false").lower() != "true":
                raise HTTPException(status_code=403, detail="远程文件导入未启用")
            remote_hosts = hosts_from_env("REMOTE_FILE_ALLOWED_HOSTS")
            try:
                file_url = validate_http_url(file.file_url, allowed_hosts=remote_hosts)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        file_id = uuid.uuid4().hex
        kb_file_store.add_file(
            build_file_record(
                request.kb_id,
                file_id,
                file_url,
                filename,
                SourceTypeEnum.FILE.value,
            )
        )

        background_tasks.add_task(
            add_file,
            file_id=file_id,
            filename=filename,
            file_url=file_url,
            kb_id=request.kb_id,
            source_file_path=source_file_path,
            remote_hosts=remote_hosts,
        )
        tasks.append({"file_id": file_id, "filename": filename})

    return {
        "code": 200,
        "msg": "success",
        "data": {"tasks": tasks}
    }


def add_web_url(file_id, url, kb_id):
    tempdir = tempfile.gettempdir()
    work_dir = f"{tempdir}/{file_id}"
    os.makedirs(os.path.join(tempdir, file_id), exist_ok=True)

    kb_file = build_file_record(kb_id, file_id, url, url, SourceTypeEnum.URL.value)
    kb_file_store = get_kb_file_store()

    local_file_path = os.path.join(tempdir, file_id, f"{file_id}.md")
    try:
        markdown_content = crawl_utils.crawl(url)
        if not markdown_content:
            raise RuntimeError("网页内容为空")

        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        kb_file.file_status = TaskStatusEnum.RUNNING.value
        kb_file.task_status = {"global_status": TaskStatusEnum.RUNNING.value}
        kb_file_store.update_file(kb_file)
        processor = DocumentProcessor(kb_id, file_id, work_dir, local_file_path, url)
        processor.process()

        kb_file.file_status = TaskStatusEnum.SUCCESS.value
        kb_file.task_status = {"global_status": TaskStatusEnum.SUCCESS.value}
        kb_file_store.update_file(kb_file)
    except Exception as exc:
        logger.exception(f"网页入库失败: {url}")
        kb_file.file_status = TaskStatusEnum.FAILED.value
        kb_file.task_status = {
            "global_status": TaskStatusEnum.FAILED.value,
            "error": str(exc)[:500],
        }
        kb_file_store.update_file(kb_file)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


class AddWebUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, description="url")
    kb_id: str = Field(..., min_length=1, max_length=64, pattern=KB_ID_PATTERN, description="知识库id")


@router.post("/add_web_url")
async def async_add_web_url(request: AddWebUrlRequest, background_tasks: BackgroundTasks):
    kb_id = request.kb_id
    if os.getenv("ENABLE_WEB_IMPORT", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="网页导入未启用")
    try:
        url = validate_http_url(
            request.url,
            allowed_hosts=hosts_from_env("WEB_IMPORT_ALLOWED_HOSTS"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_id = uuid.uuid4().hex
    get_kb_file_store().add_file(
        build_file_record(kb_id, file_id, url, url, SourceTypeEnum.URL.value)
    )
    background_tasks.add_task(
        add_web_url,
        file_id, url, kb_id,
    )

    return {
        "code": 200,
        "msg": "success",
        "data": {"task": {"file_id": file_id, "url": url}},
    }


class DeleteFileRequest(BaseModel):
    file_ids: List[str] = Field(..., min_length=1, description="文件id")
    kb_id: str = Field(..., min_length=1, max_length=64, pattern=KB_ID_PATTERN, description="知识库id")


@router.post("/delete_files")
async def delete_files(request: DeleteFileRequest):
    file_ids = request.file_ids
    kb_id = request.kb_id

    kb_file_store = get_kb_file_store()
    deleted_files = kb_file_store.delete_by_file_ids(kb_id, file_ids)
    if deleted_files == 0:
        raise HTTPException(status_code=404, detail="未找到可删除的文件")

    vector_store = VectorStore()
    if not vector_store.delete_by_file_ids(kb_id, file_ids):
        raise HTTPException(status_code=500, detail="文件元数据已删除，但向量清理失败")

    return {
        "code": 200,
        "msg": "success",
        "data": {"deleted_files": deleted_files}
    }


class ListKBFilesRequest(BaseModel):
    kb_id: str = Field(..., min_length=1, max_length=64, pattern=KB_ID_PATTERN)
    page_no: int = Field(1, ge=1, description="page_no")
    page_size: int = Field(10, ge=1, le=100, description="page_size")


@router.post("/list_kb_files")
async def list_kb_files(request: ListKBFilesRequest):
    kb_id = request.kb_id
    page_no = request.page_no
    page_size = request.page_size
    kb_file_store = get_kb_file_store()
    records = kb_file_store.list_kb_files(kb_id, page_no, page_size)
    total = kb_file_store.count_kb_files(kb_id)
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "total": total,
            "records": records,
            "page_no": page_no,
            "page_size": page_size,
        }
    }
