"""LLM 工厂测试：按配置构造可用的 LLMClient（云端优先 / 离线回退 Mock）。"""
from __future__ import annotations

from xingshu.config import NovelMeta
from xingshu.llm.factory import build_llm
from xingshu.llm.http import OpenAICompatibleLLM
from xingshu.llm.mock import MockLLM


def test_mock_when_model_is_mock() -> None:
    meta = NovelMeta(novel_id="n1", title="t", model="mock")
    llm = build_llm(meta)
    assert isinstance(llm, MockLLM)


def test_mock_when_model_unset() -> None:
    assert isinstance(build_llm(NovelMeta(novel_id="n1", title="t")), MockLLM)


def test_mock_fallback_without_api_key(monkeypatch) -> None:
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "AGNES_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    meta = NovelMeta(novel_id="n1", title="t", model="agnes-2.5-flash")
    assert isinstance(build_llm(meta), MockLLM)  # 有配置但缺 Key → 离线回退


def test_cloud_when_key_and_model_configured(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-test")
    meta = NovelMeta(novel_id="n1", title="t", model="agnes-2.5-flash",
                     base_url="https://api.agnes-ai.cn/v1")
    llm = build_llm(meta)
    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.model == "agnes-2.5-flash"