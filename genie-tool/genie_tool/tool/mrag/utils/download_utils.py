import os
from pathlib import Path
from urllib.parse import urljoin

import requests

from .logger_utils import logger
from .url_utils import validate_http_url


def download_file(
        url: str,
        filename: str,
        *,
        allowed_hosts: set[str] | None = None,
        max_bytes: int | None = None,
):
    """Download an HTTP(S) resource with TLS, redirect and size checks."""

    byte_limit = max_bytes or int(os.getenv("MAX_REMOTE_FILE_SIZE", 50 * 1024 * 1024))
    timeout = int(os.getenv("API_TIMEOUT", "300"))
    target = Path(filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    current_url = url

    try:
        for _ in range(6):
            validate_http_url(current_url, allowed_hosts=allowed_hosts)
            logger.info("Downloading {} -> {}", current_url, target)
            response = requests.get(
                current_url,
                stream=True,
                verify=True,
                timeout=timeout,
                allow_redirects=False,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise RuntimeError("下载重定向缺少 Location")
                current_url = urljoin(current_url, location)
                continue

            try:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > byte_limit:
                    raise ValueError(f"远程文件超过 {byte_limit} 字节限制")

                downloaded = 0
                with partial.open("wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > byte_limit:
                            raise ValueError(f"远程文件超过 {byte_limit} 字节限制")
                        file_handle.write(chunk)
            finally:
                response.close()
            os.replace(partial, target)
            logger.info("Downloaded {} bytes -> {}", downloaded, target)
            return str(target)

        raise ValueError("下载重定向次数超过限制")
    except Exception:
        partial.unlink(missing_ok=True)
        raise
