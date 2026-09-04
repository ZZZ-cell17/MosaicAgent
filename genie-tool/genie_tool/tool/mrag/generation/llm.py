import os

import dotenv
from openai import OpenAI
from ..utils.logger_utils import logger
dotenv.load_dotenv()


class LLMClient:
    """大模型客户端类"""

    # 配置环境变量
    # API_KEY llm 大模型apikey
    # LLM_MODEL_NAME 大模型名称
    # LLM_MODEL_BASE_URL 大模型地址
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.model_name = os.getenv("LLM_MODEL_NAME")
        self.model_base_url = os.getenv("LLM_MODEL_BASE_URL")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.model_base_url
        )
        logger.info("init LLM client, {base_url}".format(base_url=self.model_base_url))

    @staticmethod
    def convert_messages(prompt):
        return [{"role": "user", "content": prompt}]

    def completions(self, messages, max_tokens=8192, temperature=0, stream=False):
        logger.info(
            "Chat completion model={} messages={} stream={}",
            self.model_name,
            len(messages),
            stream,
        )
        request = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            "max_tokens": max_tokens,
        }
        if os.getenv("LLM_SEND_THINKING_OPTIONS", "true").lower() == "true":
            request["extra_body"] = {
                "enable_thinking": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        completion = self.client.chat.completions.create(**request)
        if stream:
            return completion
        return completion.choices[0].message.content

    def chat(self, prompt, image_url):
        messages = self.convert_messages(prompt)
        return self.completions(messages)
