"""回炉修订循环测试（对应设计 `02` §7）。

审计结论为"修复后通过/回炉重写"时，按 revision_max_attempts 实施定向
修订（writer 模型）并重审；达最大尝试次数后升级为"需人工干预"。
"""
from __future__ import annotations

import pytest

from xingshu.auditor import AuditReport, build_audit_prompt, grade, parse_report
from xingshu.config import NovelMeta
from xingshu.llm.mock import MockLLM
from xingshu.revision import RevisionLoop, build_revision_prompt

_GOOD = '{"score": 82, "issues": []}'
_MEH = '{"score": 65, "issues": ["P1 信息密度不足"]}'


def _meta(revision_max_attempts: int = 3) -> NovelMeta:
    return NovelMeta(novel_id="n1", title="测试", revision_max_attempts=revision_max_attempts)


def test_revision_prompt_contains_original_and_issues() -> None:
    report = AuditReport(score=65, conclusion="修复后通过",
                         issues=["P1 信息密度不足", "L3 情感略浅"])
    prompt = build_revision_prompt("原文段落", report)
    assert "原文段落" in prompt
    assert "P1 信息密度不足" in prompt
    assert "L3 情感略浅" in prompt


def test_loop_accepts_on_first_pass() -> None:
    writer = MockLLM("x")
    auditor = _SeqAuditor([_GOOD])
    loop = RevisionLoop(writer=writer, auditor=auditor, meta=_meta())
    result = loop.run("正文", chapter_type="战斗")
    assert result.accepted is True
    assert result.attempts == 1
    assert result.escalated is False
    assert writer.calls == []  # 第一轮即通过，无需修订


def test_loop_revises_then_accepts() -> None:
    writer = MockLLM("修订版正文")
    auditor = _SeqAuditor([_MEH, _GOOD])
    loop = RevisionLoop(writer=writer, auditor=auditor, meta=_meta())
    result = loop.run("初稿", chapter_type="战斗")
    assert result.accepted is True
    assert result.attempts == 2
    assert len(writer.calls) == 1  # 仅修订一次
    assert "初稿" in writer.calls[0]  # 修订提示词带原稿
    assert "P1 信息密度不足" in writer.calls[0]  # 带问题清单


def test_loop_escalates_after_max_attempts() -> None:
    meta = _meta(revision_max_attempts=2)
    writer = MockLLM("修订版")
    auditor = _SeqAuditor([_MEH, _MEH])
    loop = RevisionLoop(writer=writer, auditor=auditor, meta=meta)
    result = loop.run("初稿", chapter_type="战斗")
    assert result.accepted is False
    assert result.escalated is True
    assert result.attempts == 2
    assert len(writer.calls) == 1  # 第1轮后修订1次，第2轮仍不过 → 升级


# ---------- 测试用计数器审计 ----------


class _SeqAuditor:
    """按顺序消费固定响应文本的审计 Double（复用 LLMAuditor 的解析逻辑）。

    用真实 parse_report / grade 走"真实代码"，仅替换 LLM 响应来源。
    """

    def __init__(self, raws: list[str]) -> None:
        self._raws = list(raws)

    def evaluate(self, text, *, chapter_type="常规", blocker_count=0,
                 major_count=0, facts=()):
        raw = self._raws.pop(0)
        score, issues, choices = parse_report(raw)
        return AuditReport(score=score, conclusion=grade(score, blocker_count=blocker_count,
                                                         major_count=major_count),
                           issues=issues, creative_choices=choices)