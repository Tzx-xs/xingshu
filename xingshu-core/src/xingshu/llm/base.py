"""LLM 客户端可插拔接口。

对应设计：主系统与审计模型解耦（`07` 双模型独立仲裁），任何实现只需实现
`complete`。本包是抽象契约层，具体实现（OpenAI/DeepSeek/本地）可后续接入。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """LLM 调用失败或返回异常。"""


@runtime_checkable
class LLMClient(Protocol):
    """生成文本的接口。实现方负责鉴权、重试与超时。"""

    def complete(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...
