"""token 预算记账（对应设计 `12` §5）。

按 meta.budget 为 正文生成 / 审计 / 章后管线 分配单章 token 上限；
任一项超过上限 20% 触发告警（12 §5：超 20% 触发告警与分级降档）。
"""
from __future__ import annotations

from xingshu.config import NovelMeta

_BUDGET_STAGES = {
    "generation": "gen_tokens_per_chapter",
    "audit": "audit_tokens_per_chapter",
    "pipeline_ab": "pipeline_ab_tokens_per_chapter",
}


class BudgetTracker:
    """记录每章各环节的 token 用量，并对照预算告警。"""

    def __init__(self, meta: NovelMeta) -> None:
        self.meta = meta
        self._usage: dict[int, dict[str, int]] = {}

    def record(self, chapter: int, stage: str, tokens: int) -> None:
        self._usage.setdefault(chapter, {})
        self._usage[chapter][stage] = self._usage[chapter].get(stage, 0) + tokens

    def stage_total(self, chapter: int, stage: str) -> int:
        return self._usage.get(chapter, {}).get(stage, 0)

    def chapter_total(self, chapter: int) -> int:
        return sum(self._usage.get(chapter, {}).values())

    def alert(self, chapter: int, stage: str, tokens: int) -> str | None:
        """单环节 token 是否超过预算 120%；超则返回告警消息。"""
        field = _BUDGET_STAGES.get(stage)
        if field is None:
            return None
        budget = getattr(self.meta, field)
        if budget <= 0:
            return None
        limit = int(budget * 1.2)
        if tokens > limit:
            return f"第{chapter}章 {stage} 环节 token 超预算（{tokens} > {limit}）"
        return None