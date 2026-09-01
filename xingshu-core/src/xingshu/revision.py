"""回炉修订循环（对应设计 `02` §7）。

审计结论为"修复后通过 / 回炉重写"时进入修订：writer 模型按问题清单
定向修订 → 重新审计；达 revision_max_attempts（novel_meta 配置）后升级，
标记"需人工干预"（不无限空转，保证生成可控收敛）。

修订记录由上层（Orchestrator/持久化层）落盘到 audits/revision_ch_XXX.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from xingshu.auditor import AuditReport, LLMAuditor
from xingshu.config import NovelMeta
from xingshu.fact_base import Fact
from xingshu.llm.base import LLMClient


@dataclass(frozen=True, slots=True)
class RevisionResult:
    accepted: bool
    attempts: int
    escalated: bool
    report: AuditReport


def build_revision_prompt(original: str, report: AuditReport) -> str:
    """按审计问题清单生成定向修订指令（02 §7 修订策略：最小改动）。"""
    issues = "\n".join(f"- {i}" for i in report.issues) or "-（未给出具体问题）"
    return "\n".join(
        [
            "# 修订指令（02 §7 定向修订）",
            f"## 审计结论：{report.conclusion}（score={report.score}）",
            f"## 待修订正文",
            original,
            "",
            "## 问题清单",
            issues,
            "",
            "## 要求",
            "只修改问题段落的「最小改动」。若结论为回炉重写，则保留章纲与节拍整体重写。",
            "输出修订后的完整章节正文，不要输出任何解释。",
        ]
    )


class RevisionLoop:
    """审计-修订-重审循环，直到通过或达到最大尝试次数。"""

    def __init__(self, *, writer: LLMClient, auditor: LLMAuditor, meta: NovelMeta) -> None:
        self.writer = writer
        self.auditor = auditor
        self.max_attempts = meta.revision_max_attempts

    def run(
        self,
        text: str,
        *,
        chapter_type: str = "常规",
        blocker_count: int = 0,
        major_count: int = 0,
        facts: Sequence[Fact] = (),
    ) -> RevisionResult:
        current = text
        last_report: AuditReport | None = None
        attempts = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts = attempt
            report = self.auditor.evaluate(
                current, chapter_type=chapter_type,
                blocker_count=blocker_count, major_count=major_count, facts=facts,
            )
            last_report = report
            if report.conclusion == "通过":
                return RevisionResult(accepted=True, attempts=attempts,
                                      escalated=False, report=report)
            if attempt < self.max_attempts:
                current = self.writer.complete(build_revision_prompt(current, report))
        assert last_report is not None
        return RevisionResult(accepted=False, attempts=attempts,
                              escalated=True, report=last_report)