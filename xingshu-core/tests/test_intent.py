"""作者意图声明测试（对应设计 `06` §3 / `07` Creative Choice 可操作化）。

用户可在暂停状态为某章声明"此现象是有意为之的文学手法"；声明进入审计
提示词后，审计不得将相关内容判为 Blocker/Major，只能记 Creative Choice。
"""
from __future__ import annotations

import pytest

from xingshu.auditor import build_audit_prompt, parse_report
from xingshu.intent import AuthorIntent, IntentBook, declare_intent
from xingshu.llm.mock import MockLLM

_INTENT_JSON = (
    '{"score": 80, "issues": ["I6 线性时间线被打断"], '
    '"creative_choices": ["I6 非线性叙事（作者声明）"]}'
)


def test_declare_and_query_intent() -> None:
    book = IntentBook()
    declare_intent(book, chapter=3, target="时间线跳跃",
                   reason="第三章为非线性叙事")
    assert len(book.by_chapter(3)) == 1
    intent = book.by_chapter(3)[0]
    assert intent.target == "时间线跳跃"
    assert book.by_chapter(4) == []


def test_author_intent_fields() -> None:
    i = AuthorIntent(chapter=3, target="诡叙", reason="不可靠叙述者")
    assert i.target == "诡叙" and i.reason == "不可靠叙述者"


def test_declared_intents_injected_into_audit_prompt() -> None:
    prompt = build_audit_prompt(
        "战斗", "正文……", (),
        declared_intents=(AuthorIntent(chapter=1, target="时间线交错", reason="双线叙事"),),
    )
    assert "作者意图声明" in prompt
    assert "时间线交错" in prompt


def test_no_intents_section_when_none_declared() -> None:
    prompt = build_audit_prompt("战斗", "正文……", ())
    assert "作者意图声明" not in prompt


def test_parse_report_extracts_creative_choices() -> None:
    score, issues, choices = parse_report(_INTENT_JSON)
    assert score == 80
    assert issues == ["I6 线性时间线被打断"]
    assert choices == ["I6 非线性叙事（作者声明）"]


def test_parse_report_no_choices_by_default() -> None:
    score, issues, choices = parse_report('{"score": 75, "issues": []}')
    assert choices == []


def test_evaluate_carries_declared_intents(monkeypatch) -> None:
    from xingshu.auditor import LLMAuditor
    m = MockLLM(response=_INTENT_JSON)
    auditor = LLMAuditor(llm=m)
    report = auditor.evaluate(
        "正文", chapter_type="战斗",
        declared_intents=(AuthorIntent(chapter=1, target="时间线交错", reason="双线叙事"),),
    )
    assert report.creative_choices == ["I6 非线性叙事（作者声明）"]
    assert "作者意图声明" in m.calls[0]


def test_grade_unchanged_by_creative_choices() -> None:
    """声明只影响分级口径（转 Creative Choice，不阻断），不影响分数本身。"""
    from xingshu.auditor import grade
    assert grade(80) == "通过"