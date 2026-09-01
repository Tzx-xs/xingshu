"""LLM 语义复核与评分测试（对应设计 `07` §1②/§5/§6/§8）。

确定性不变量（零 LLM）之后的 LLM 阶段：由独立 audit_model 复核存疑项、
给主观维度打分，再按五级严重度规则得出审计结论。
"""
from __future__ import annotations

import pytest

from xingshu.auditor import AuditReport, LLMAuditor, build_audit_prompt, grade, parse_report
from xingshu.fact_base import Fact
from xingshu.llm.mock import MockLLM

_AUDIT_JSON = '{"score": 78, "issues": ["P1 信息密度不足", "L3 情感略浅"]}'


def test_grade_passed_when_high_and_no_blocker() -> None:
    assert grade(82) == "通过"


def test_grade_repair_when_medium() -> None:
    assert grade(74) == "修复后通过"
    assert grade(60) == "修复后通过"


def test_grade_rewrite_when_low() -> None:
    assert grade(59) == "回炉重写"


def test_grade_blocker_forces_rewrite_even_high_score() -> None:
    assert grade(90, blocker_count=1) == "回炉重写"


def test_grade_major_caps_at_repair() -> None:
    """有 Major 无 Blocker → 上限 74（07 §6 评分规则）。"""
    assert grade(90, major_count=1) == "修复后通过"


def test_parse_report_extracts_score_and_issues() -> None:
    score, issues, choices = parse_report(_AUDIT_JSON)
    assert score == 78
    assert issues == ["P1 信息密度不足", "L3 情感略浅"]
    assert choices == []


def test_parse_report_invalid_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_report("这不是 JSON")


def test_build_audit_prompt_includes_body_and_facts() -> None:
    facts = [Fact.new(system="characters", entity="char_001", attribute="mood",
                      value="警惕", source="第1章")]
    prompt = build_audit_prompt("战斗", "正文段落……", facts)
    assert "战斗" in prompt and "正文段落……" in prompt
    assert "characters/char_001" in prompt
    assert '"score"' in prompt  # 要求结构化输出


def test_evaluate_uses_independent_audit_llm() -> None:
    """07 §8：审计模型独立于正文模型。"""
    m = MockLLM(response=_AUDIT_JSON, model="audit-mock")
    auditor = LLMAuditor(llm=m)
    report = auditor.evaluate("正文", chapter_type="战斗")
    assert isinstance(report, AuditReport)
    assert report.score == 78
    assert report.issues == ["P1 信息密度不足", "L3 情感略浅"]
    assert report.conclusion == "通过"
    assert "audit-mock" == m.model


def test_evaluate_wires_blocker_and_major_counts() -> None:
    m = MockLLM(response=_AUDIT_JSON)
    auditor = LLMAuditor(llm=m)
    assert auditor.evaluate("x", chapter_type="战斗", blocker_count=1).conclusion == "回炉重写"
    assert auditor.evaluate("x", chapter_type="战斗",
                            major_count=1).conclusion == "修复后通过"