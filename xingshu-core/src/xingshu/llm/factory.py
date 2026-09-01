"""LLM 工厂：按 novel_meta 构造可用的 LLMClient。

云端优先（配置了非 mock 模型且有环境变量 Key → OpenAI 兼容云端模型）；
缺 Key 或无配置时回退 MockLLM，保证离线可跑（纯本地工具的降级策略）。
"""
from __future__ import annotations

from xingshu.config import NovelMeta
from xingshu.llm.base import LLMClient
from xingshu.llm.http import OpenAICompatibleLLM
from xingshu.llm.mock import MockLLM

_OFFLINE_BODY = "晨雾里，山门前立着一个疏朗少年。他抬起眼，恰好对上石阶尽头那道目光……"


def build_llm(meta: NovelMeta) -> LLMClient:
    """构建正文生成 LLM：云端可配则云端，否则 Mock（离线可跑）。"""
    if meta.model and meta.model != "mock":
        try:
            return OpenAICompatibleLLM.from_meta(meta)
        except ValueError:
            pass  # 缺 Key 等 → 回退 Mock
    return MockLLM(_OFFLINE_BODY)