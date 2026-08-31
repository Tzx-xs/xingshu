"""Mock LLM —— 测试 / 骨架阶段使用，返回固定文本并记录调用。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockLLM:
    response: str = ""
    calls: list[str] = field(default_factory=list)

    def complete(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append(prompt)
        return self.response
