"""章级管线编排器（骨架）。

对应设计 `02`：规划 → 生成 → 确定性与不变量审计 → 章后管线 A→B→C。
- A：伏笔/演化分析（LLM，骨架由生成阶段承担）
- B：真相文件确定性更新（零 LLM，写 FactBase）
- C：摘要 / 索引记录（零 LLM）

审计阶段若存在 Blocker 不变量（`07`），章节不通过、不进入章后管线。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from xingshu.config import NovelMeta
from xingshu.core.invariants import InvariantChecker, Violation
from xingshu.fact_base import Fact, FactBase
from xingshu.llm.base import LLMClient


@dataclass(frozen=True, slots=True)
class ChapterPlan:
    number: int
    type: str
    pov: str


@dataclass(slots=True)
class ChapterResult:
    number: int
    text: str
    accepted: bool
    violations: list[Violation]
    order: list[str]


class Orchestrator:
    """依赖注入 LLM / 事实库 / 不变量检查器 / 元数据，三者即插即换。"""

    def __init__(
        self,
        *,
        llm: LLMClient,
        facts: FactBase,
        checker: InvariantChecker,
        meta: NovelMeta,
    ) -> None:
        self.llm = llm
        self.facts = facts
        self.checker = checker
        self.meta = meta
        self._summaries: dict[int, str] = {}

    # ---- 步骤 ----

    def plan(self, number: int, *, chapter_type: str = "常规", pov: str = "") -> ChapterPlan:
        return ChapterPlan(number=number, type=chapter_type, pov=pov)

    def generate(self, plan: ChapterPlan) -> str:
        prompt = (
            f"请创作第 {plan.number} 章（类型：{plan.type}，POV：{plan.pov or '未指定'}）。"
            f"目标字数：{self.meta.chapter_word_target}。"
        )
        return self.llm.complete(prompt)

    def post_b(self, number: int, facts_to_write: list[Fact]) -> None:
        for fact in facts_to_write:
            self.facts.remember(fact)

    def post_c(self, number: int, summary: str) -> None:
        self._summaries[number] = summary

    def chapter_summary(self, number: int) -> str | None:
        return self._summaries.get(number)

    # ---- 主流程 ----

    def write_chapter(
        self,
        number: int,
        *,
        known: set[str],
        revealed: set[str],
        facts_to_write: list[Fact] | None = None,
        summary: str = "",
        relation_changes: set[tuple[str, str]] | None = None,
        relation_events: set[tuple[str, str]] | None = None,
    ) -> ChapterResult:
        plan = self.plan(number)
        text = self.generate(plan)

        # 确定性与不变量审计（Blocker 阻断）
        violations: list[Violation] = []
        violations += self.checker.inv001(known, revealed)
        violations += self.checker.inv004(
            relation_changes or set(), relation_events or set()
        )
        if violations:
            return ChapterResult(
                number=number, text=text, accepted=False,
                violations=violations, order=[],
            )

        # 章后管线 A→B→C
        order = ["A", "B", "C"]
        self.post_b(number, facts_to_write or [])
        self.post_c(number, summary)
        return ChapterResult(
            number=number, text=text, accepted=True,
            violations=[], order=order,
        )
