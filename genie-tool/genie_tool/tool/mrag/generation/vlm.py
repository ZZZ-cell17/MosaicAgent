import base64
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from openai import OpenAI
from PIL import Image

from genie_tool.tool.mrag.utils import download_utils
from genie_tool.tool.mrag.utils.logger_utils import logger
from genie_tool.tool.mrag.utils.url_utils import hosts_from_env, hosts_from_urls

class VLLMClient:
    """大模型客户端类"""

    # 配置环境变量
    # API_KEY llm 大模型apikey
    # LLM_MODEL_NAME 大模型名称
    # LLM_MODEL_BASE_URL 大模型地址
    def __init__(self, base_url=None, model_name=None, api_key=None):
        self.api_key = api_key or os.getenv("VLM_API_KEY")
        self.model_name = model_name or os.getenv("VLM_MODEL_NAME")
        self.model_base_url = base_url or os.getenv("VLM_MODEL_BASE_URL")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.model_base_url
        )
        logger.info(f"VLM Client {self.model_base_url}")

    @staticmethod
    def convert_messages(prompt, image_url):
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ]

    @staticmethod
    def convert_messages_with_image_path(prompt, image_path: str):
        image_url = image_path
        temporary_dir = None
        if image_path.startswith("http"):
            remote_name = Path(unquote(urlparse(image_url).path)).name or f"{uuid.uuid4().hex}.img"
            temp_dir = tempfile.gettempdir()
            uid = uuid.uuid4().hex
            temporary_dir = os.path.join(temp_dir, uid)
            os.makedirs(temporary_dir, exist_ok=True)
            image_path = os.path.join(temporary_dir, remote_name)
            trusted_hosts = hosts_from_urls((
                os.getenv("SERVER_BASE_URL", "http://127.0.0.1:1601"),
                os.getenv("OSS_SERVER_BASE_URL"),
            )) | hosts_from_env("QUERY_IMAGE_ALLOWED_HOSTS")
            download_utils.download_file(
                image_url,
                image_path,
                allowed_hosts=trusted_hosts,
            )

        def _encode_image() -> str:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')

        def _get_image_mime_type() -> str:
            try:
                with Image.open(image_path) as image:
                    detected = Image.MIME.get(image.format)
                if detected:
                    return detected
            except (OSError, ValueError):
                pass
            suffix = Path(image_path).suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }
            return mime_types.get(suffix, 'image/jpeg')

        try:
            base64_image = "data:" + _get_image_mime_type() + ";base64," + _encode_image()
        finally:
            if temporary_dir:
                shutil.rmtree(temporary_dir, ignore_errors=True)

        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image
                        }
                    }
                ]
            }
        ]

    def completions(self, messages, temperature=0, stream=False, max_tokens: int = None):
        request = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "max_tokens": max_tokens,
        }
        if os.getenv("VLM_SEND_THINKING_OPTIONS", "true").lower() == "true":
            request["extra_body"] = {"enable_thinking": False}
        completion = self.client.chat.completions.create(**request)
        if stream:
            return completion
        return completion.choices[0].message.content

    def chat(self, prompt, image_url):
        messages = self.convert_messages(prompt, image_url)
        return self.completions(messages)
