"""FactBase —— 事实库，整套系统的一致性底座。

对应设计文档 `05_记忆与状态管理.md`。三条铁律：
1. ADD-only：只累积不覆盖，修改=新版本 + 旧版本标记失效
2. 显式时效窗口：查询只返回 active 且未失效的事实
3. 强制溯源：source 必填，无来源的事实禁止写入

四段 API：remember / recall / forget / improve。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

# 六系统事实类型（PEP 695 类型别名，Python 3.12+）
type System = Literal[
    "characters", "relations", "factions", "locations", "timeline", "foreshadowing"
]

_SYSTEMS: frozenset[str] = frozenset(
    {"characters", "relations", "factions", "locations", "timeline", "foreshadowing"}
)


def _default_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Fact:
    """真相文件中的一条最小事实单元（对齐 05 §2 结构）。"""

    system: System
    entity: str
    attribute: str
    value: str
    source: str
    valid_from: str
    id: str = field(default_factory=lambda: f"fact_{uuid4().hex[:12]}")
    valid_until: str | None = None
    status: Literal["active", "superseded"] = "active"
    confidence: float = 1.0
    created_at: str = field(default_factory=_default_now)
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.system not in _SYSTEMS:
            raise ValueError(f"未知 system: {self.system}")
        if self.status not in ("active", "superseded"):
            raise ValueError(f"未知 status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence 必须在 0-1 之间")

    @classmethod
    def new(
        cls,
        *,
        system: System,
        entity: str,
        attribute: str,
        value: str,
        source: str,
        valid_from: str | None = None,
        confidence: float = 1.0,
    ) -> Fact:
        return cls(
            system=system,
            entity=entity,
            attribute=attribute,
            value=value,
            source=source,
            valid_from=valid_from if valid_from is not None else _default_now(),
            confidence=confidence,
        )


class FactBase:
    """内存版事实库。后续可扩展为文件 / SQLite 持久化（对齐 `12` §7）。"""

    def __init__(self, *, now: Callable[[], str] | None = None) -> None:
        self._now = now or _default_now
        self._facts: dict[str, Fact] = {}

    # ---- 四段 API ----

    def remember(self, fact: Fact) -> Fact:
        if not (fact.source or "").strip():
            raise ValueError("事实必须有 source（强制溯源铁律）")
        self._facts[fact.id] = fact
        return fact

    def get(self, fact_id: str) -> Fact:
        try:
            return self._facts[fact_id]
        except KeyError:
            raise KeyError(f"无此事实: {fact_id}") from None

    def recall(
        self,
        *,
        system: System | None = None,
        entity: str | None = None,
        attribute: str | None = None,
        include_superseded: bool = False,
    ) -> list[Fact]:
        result = []
        for f in self._facts.values():
            if not include_superseded and not self._is_active(f):
                continue
            if system is not None and f.system != system:
                continue
            if entity is not None and f.entity != entity:
                continue
            if attribute is not None and f.attribute != attribute:
                continue
            result.append(f)
        return result

    def forget(self, fact_id: str, *, reason: str) -> None:
        f = self.get(fact_id)
        f.status = "superseded"
        f.valid_until = self._now()
        f.reason = reason

    def improve(
        self,
        fact_id: str,
        *,
        source: str,
        value: str | None = None,
        attribute: str | None = None,
        confidence: float | None = None,
    ) -> Fact:
        old = self.get(fact_id)
        if not (source or "").strip():
            raise ValueError("improve 必须提供 source")
        if not self._is_active(old):
            raise ValueError("只能 improve 一个 active 的事实")
        # ADD-only：旧记录标记失效
        old.status = "superseded"
        old.valid_until = self._now()
        # 新版本
        new = Fact(
            system=old.system,
            entity=old.entity,
            attribute=attribute if attribute is not None else old.attribute,
            value=value if value is not None else old.value,
            source=source,
            valid_from=self._now(),
            confidence=confidence if confidence is not None else old.confidence,
        )
        self._facts[new.id] = new
        return new

    # ---- helpers ----

    @staticmethod
    def _is_active(f: Fact) -> bool:
        return f.status == "active" and f.valid_until is None
