import hashlib
import os
import pathlib
import shutil
from urllib import request
from urllib.parse import quote
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .logger_utils import logger

router = APIRouter(prefix="/storage", tags=["OSS"])


def get_local_storage_root() -> pathlib.Path:
    configured_path = os.getenv("LOCAL_STORAGE_PATH")
    if configured_path:
        return pathlib.Path(configured_path).expanduser().resolve()
    return (pathlib.Path(__file__).resolve().parents[4] / "data" / "files").resolve()


def get_local_storage_file(file_id: str, filename: str, *, require_exists: bool = True) -> pathlib.Path:
    """Resolve one uploaded file without allowing path traversal."""

    safe_file_id = pathlib.Path(file_id).name
    safe_filename = pathlib.Path(filename).name
    if not file_id or not filename or safe_file_id != file_id or safe_filename != filename:
        raise ValueError("非法文件路径")

    storage_root = get_local_storage_root()
    file_path = (storage_root / safe_file_id / safe_filename).resolve()
    if not file_path.is_relative_to(storage_root):
        raise ValueError("非法文件路径")
    if require_exists and not file_path.is_file():
        raise FileNotFoundError("上传文件不存在")
    return file_path


def build_local_storage_url(file_id: str, filename: str) -> str:
    server_base_url = os.getenv("SERVER_BASE_URL", "http://127.0.0.1:1601").rstrip("/")
    return (
        f"{server_base_url}/v1/storage/local/"
        f"{quote(file_id, safe='')}/{quote(filename, safe='')}"
    )


def get_file_extension(file_path):
    # 普通后缀处理
    extension = pathlib.Path(file_path).suffix

    # 加密链接处理
    if "?" in extension:
        extension = extension.split("?")[0]

    return extension


def upload_oss(file_path, dir_, is_delete=True):
    # bucket_name, access_key, secret_key, endpoint,
    bucket = os.getenv("S3_BUCKET_NAME")
    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    endpoint = os.getenv("S3_ENDPOINT")
    return upload_s3(file_path, bucket, access_key, secret_key, endpoint, dir_, is_delete)


def upload_s3(file_path, bucket_name, access_key, secret_key, endpoint, dir_, is_delete=True):
    import boto3

    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint
        )
        oss_name = dir_ + "/" + os.path.basename(file_path)
        # 上传文件
        with open(file_path, 'rb') as file_handle:
            resp = s3.put_object(
                Bucket=bucket_name,
                Key=oss_name,
                Body=file_handle,
                StorageClass='STANDARD',
            )
        return_code = resp["ResponseMetadata"]["HTTPStatusCode"]
        if return_code == 200:
            upload_url = create_permanent_download_url(bucket_name, oss_name)
            # s3生成链接
            presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': oss_name
                },
                ExpiresIn=3600 * 24 * 365
            )
            return True, upload_url, presigned_url
        return False, None
        # 获得外链
    finally:
        if is_delete:
            # 检查文件是否存在
            if file_path is not None and os.path.isfile(file_path):
                # 存在，则删除
                os.remove(file_path)


def generate_secure_token(bucket_name, object_key, secret_key):
    """
    为对象生成安全令牌，用于永久访问链接

    参数:
        bucket_name: S3存储桶名称
        object_key: 对象的键（路径）
        secret_key: 用于签名的密钥

    返回:
        安全令牌
    """
    # 组合信息并加盐
    data = f"{bucket_name}:{object_key}:{secret_key}"
    # 使用SHA-256生成哈希
    token = hashlib.sha256(data.encode()).hexdigest()
    return token


def create_permanent_download_url(bucket_name, object_key, access_key=None, secret_key=None):
    """
    创建对象的永久下载链接（通过服务器代理访问）

    参数:
        bucket_name: S3存储桶名称
        object_key: 对象的键（路径）
        access_key: S3访问密钥（可选，默认使用环境变量）
        secret_key: S3秘密密钥（可选，默认使用环境变量）

    返回:
        永久下载链接
    """
    if not secret_key:
        secret_key = os.getenv("S3_SECRET_KEY")

    # 生成安全令牌
    token = generate_secure_token(bucket_name, object_key, secret_key)

    # 构建API端点URL（需要在服务器端实现对应的API）
    api_base_url = os.getenv("OSS_SERVER_BASE_URL", "http://127.0.0.1:7861/oss")
    permanent_url = f"{api_base_url}/download/{bucket_name}/{quote(object_key)}/{token}"

    return permanent_url


def download(file_url, save_path):
    logger.info(file_url)
    logger.info("文件开始下载... 来源:{}".format(file_url))
    # 获取文件扩展名
    extension = get_file_extension(file_url)
    file_name = save_path + extension
    try:
        request.urlretrieve(file_url, file_name)
        logger.info("文件下载完成,地址:{}".format(save_path))
        return "success", save_path
    except:
        logger.info("文件下载失败!")
        return "failed", ""


def verify_token(bucket_name, object_key, token):
    """验证访问令牌是否有效"""
    secret_key = os.getenv("S3_SECRET_KEY")
    expected_token = generate_secure_token(bucket_name, object_key, secret_key)
    return token == expected_token


@router.get("/download/{bucket_name}/{object_key:path}/{token}")
def download_file(bucket_name: str, object_key: str, token: str):
    """
    通过安全令牌提供S3对象的永久下载

    参数:
        bucket_name: S3存储桶名称
        object_key: 对象的键（路径，URL编码）
        token: 安全访问令牌
    """
    try:
        import boto3

        # URL解码对象键
        object_key = unquote(object_key)

        # 验证令牌
        if not verify_token(bucket_name, object_key, token):
            logger.warning(f"无效的访问令牌: {token} 用于 {bucket_name}/{object_key}")
            raise HTTPException(status_code=403, detail="无效的访问令牌")

        # 获取S3客户端
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            endpoint_url=os.getenv("S3_ENDPOINT")
        )

        # 检查对象是否存在
        try:
            response = s3.head_object(Bucket=bucket_name, Key=object_key)
        except Exception as e:
            logger.error(f"对象不存在或无法访问: {bucket_name}/{object_key}, 错误: {str(e)}")
            raise HTTPException(status_code=404, detail="文件不存在或无法访问")

        # 获取对象内容
        obj = s3.get_object(Bucket=bucket_name, Key=object_key)
        content_type = obj.get('ContentType', 'application/octet-stream')

        # 获取文件名（从对象键中提取）
        filename = os.path.basename(object_key)

        # 创建流式响应
        def iterfile():
            yield from obj['Body'].iter_chunks()

        # 返回流式响应
        return StreamingResponse(
            iterfile(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/local/{file_id}/{filename}")
def download_local_file(file_id: str, filename: str):
    """Serve a file produced or uploaded by the local MRAG pipeline."""
    try:
        file_path = get_local_storage_file(file_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法文件路径")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(file_path, filename=filename)


def upload_local_storage(file_path: str, file_id: str = None, filename: str = None):
    """Copy a file into MosaicAgent's local storage and return its HTTP URL."""
    import uuid

    source = pathlib.Path(file_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Local file does not exist: {source}")

    safe_file_id = file_id or uuid.uuid4().hex
    safe_filename = filename or source.name
    target = get_local_storage_file(safe_file_id, safe_filename, require_exists=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target:
        shutil.copy2(source, target)

    return build_local_storage_url(safe_file_id, safe_filename)
