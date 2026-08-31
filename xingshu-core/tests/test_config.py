"""novel_meta 配置加载测试（对应设计 `12` §2）。"""
from __future__ import annotations

import pytest

from xingshu.config import NovelMeta, parse_novel_meta


def test_parse_requires_novel_id() -> None:
    with pytest.raises(ValueError):
        parse_novel_meta({"novel": {"title": "无id"}, "creation": {}})


def test_parse_requires_title() -> None:
    with pytest.raises(ValueError):
        parse_novel_meta({"novel": {"id": "n1"}, "creation": {}})


def test_parse_fills_defaults() -> None:
    meta = parse_novel_meta(
        {"novel": {"id": "n1", "title": "测试"}, "creation": {"total_chapters": 30}}
    )
    assert meta.novel_id == "n1"
    assert meta.title == "测试"
    assert meta.total_chapters == 30
    assert meta.chapter_word_target == 3000      # 默认
    assert meta.audit_threshold == 75
    assert meta.temperature == 0.8


def test_parse_recognizes_budget_and_llm(tmp_path, monkeypatch) -> None:
    meta = parse_novel_meta(
        {
            "novel": {"id": "n1", "title": "t", "genre": "玄幻", "language": "zh"},
            "creation": {"total_volumes": 2, "total_chapters": 60, "chapter_word_target": 2000},
            "quality": {"audit_threshold": 80, "revision_max_attempts": 2},
            "progress": {"current_volume": 1, "current_chapter": 12},
            "budget": {"gen_tokens_per_chapter": 10000},
            "llm": {"model": "deepseek", "audit_model": "gpt", "temperature": 0.5},
        }
    )
    assert meta.genre == "玄幻"
    assert meta.total_volumes == 2
    assert meta.audit_threshold == 80
    assert meta.current_chapter == 12
    assert meta.gen_tokens_per_chapter == 10000
    assert meta.model == "deepseek"
    assert meta.temperature == 0.5
