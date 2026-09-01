"""LLM 语义复核与评分（对应设计 `07` §1② / §5 / §6 / §8）。

确定性不变量引擎（`core/invariants.py`，零 LLM）之后的第二道门槛：
由**独立的 audit_model**（07 §8 双模型独立仲裁）复核结构性存疑项并给
主观维度/反AI味打分，再按五级严重度规则落到审计结论。

结论分级（07 §5）：
    有 Blocker            → 回炉重写（无论得分）
    有 Major 无 Blocker   → 得分封顶 74 → 修复后通过
    得分 ≥75             → 通过
    60 ≤ 得分 < 75       → 修复后通过
    得分 <60             → 回炉重写
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Sequence

from xingshu.fact_base import Fact
from xingshu.llm.base import LLMClient


@dataclass(frozen=True, slots=True)
class AuditReport:
    score: int
    conclusion: str
    issues: list[str] = field(default_factory=list)


def grade(score: int, *, blocker_count: int = 0, major_count: int = 0) -> str:
    """按 07 §5/§6 的评分分级规则得出审计结论。"""
    if blocker_count > 0:
        return "回炉重写"
    effective = min(score, 74) if major_count > 0 else score
    if effective >= 75:
        return "通过"
    if effective >= 60:
        return "修复后通过"
    return "回炉重写"


def parse_report(raw: str) -> tuple[int, list[str]]:
    """解析审计模型返回的 JSON：{"score": int, "issues": [...]}。"""
    text = raw.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            raise ValueError("审计模型未返回结构化 JSON") from None
        obj = json.loads(match.group())
    if not isinstance(obj, dict) or "score" not in obj:
        raise ValueError(f"审计 JSON 缺少 score 字段: {text[:120]}")
    issues = obj.get("issues") or []
    return int(obj["score"]), [str(i) for i in issues]


def build_audit_prompt(
    chapter_type: str,
    text: str,
    facts: Sequence[Fact],
) -> str:
    lines = [
        "# 审计任务（Layer 5 — 由独立 audit_model 复核）",
        "## 待审计内容",
        text,
        "",
        "## 参考事实（仅 active）",
    ]
    for f in facts:
        lines.append(f"- {f.system}/{f.entity}: {f.attribute}={f.value} 来源「{f.source}」")
    lines += [
        "",
        f"## 复核指令（章节类型：{chapter_type}）",
        "重点检查：事实锁定(C1)、关系锁定(C2)、时间线一致(C6)、反AI味(P1-P8)。",
        '请只输出严格 JSON：{"score": 整数0-100, "issues": ["维度: 问题", ...]}，不要输出任何其它内容。',
    ]
    return "\n".join(lines)


class LLMAuditor:
    """使用独立 audit_model 执行语义复核。"""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def evaluate(
        self,
        text: str,
        *,
        chapter_type: str = "常规",
        blocker_count: int = 0,
        major_count: int = 0,
        facts: Sequence[Fact] = (),
    ) -> AuditReport:
        prompt = build_audit_prompt(chapter_type, text, facts)
        score, issues = parse_report(self.llm.complete(prompt))
        return AuditReport(
            score=score,
            conclusion=grade(score, blocker_count=blocker_count, major_count=major_count),
            issues=issues,
        )