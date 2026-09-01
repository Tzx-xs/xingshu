"""OpenAI 兼容 Chat Completions 客户端（零第三依赖，标准库 urllib）。

对应设计 `07` §8：writer / audit 双模型经同一协议解耦，模型名来自
novel_meta，API Key 从环境变量读取（纯本地工具：Key 不出本地、不进仓库）。
任何兼容 OpenAI /chat/completions 的服务（DeepSeek、通义、Moonshot、
OpenAI 等）均可通过 base_url + model 直接接入。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from xingshu.config import NovelMeta
from xingshu.llm.base import LLMError

DEFAULT_BASE_URL = "https://api.openai.com/v1"
API_KEY_ENV_VARS = ("LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "AGNES_API_KEY")


class OpenAICompatibleLLM:
    """通过 OpenAI 兼容 /chat/completions 接口调用云端大模型。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_meta(cls, meta: NovelMeta, *, audit: bool = False) -> "OpenAICompatibleLLM":
        """从 novel_meta 构造：正文用 model、审计用 audit_model（07 §8 独立仲裁）。"""
        if audit:
            model = meta.audit_model or meta.model
        else:
            model = meta.model
        return cls(
            base_url=os.environ.get("LLM_BASE_URL") or meta.base_url or DEFAULT_BASE_URL,
            api_key=cls._api_key(),
            model=model,
        )

    @staticmethod
    def _api_key() -> str:
        for name in API_KEY_ENV_VARS:
            value = os.environ.get(name)
            if value:
                return value
        raise ValueError(
            "缺少 LLM API Key：请设置环境变量 "
            "LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY / AGNES_API_KEY 之一"
        )

    def complete(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise LLMError(f"LLM HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM 请求失败: {exc.reason}") from exc
        return payload["choices"][0]["message"]["content"]