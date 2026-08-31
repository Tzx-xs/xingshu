"""8 条叙事不变量 —— 确定性、零 LLM 的硬约束检查。

对应设计 `07_审计与质量系统.md` §4。每条不变量违反即为 Blocker，阻断入库。
本模块是审计的第一道门槛（确定性引擎前置），LLM 复核只处理存疑项。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Collection, Literal


@dataclass(frozen=True)
class Violation:
    invariant: str
    severity: Literal["blocker"] = "blocker"
    message: str = ""


# 伏笔状态单向序（05/06 定义），数值越大越靠后，禁止回退
_FS_RANK: dict[str, int] = {
    "planted": 0,
    "progressing": 1,
    "converging": 2,
    "revealed": 3,
    "resolved": 4,
}

# 时间戳 / 地点等位置记录类型
Position = tuple[str, str, str]          # (time, role, place)
LocationEvent = tuple[str, str, bool]    # (location, state, has_repair)


class InvariantChecker:
    """对给定创作数据执行不变量检查，返回违规清单。"""

    def inv001(self, known: Collection[str], revealed: Collection[str]) -> list[Violation]:
        """角色不能知道未揭示事实，除非有揭示事件。"""
        leaked = set(known) - set(revealed)
        if leaked:
            return [Violation("INV-001", message=f"角色知道了未揭示事实: {sorted(leaked)}")]
        return []

    def inv002(self, positions: Collection[Position]) -> list[Violation]:
        """同一角色不能在同一时间位于两地点。"""
        spots: dict[tuple[str, str], set[str]] = defaultdict(set)
        for time, role, place in positions:
            spots[(time, role)].add(place)
        return [
            Violation(
                "INV-002",
                message=f"角色 {r} 在 {t} 同时位于多个地点: {sorted(p)}",
            )
            for (t, r), p in spots.items()
            if len(p) > 1
        ]

    def inv003(self, events: Collection[LocationEvent]) -> list[Violation]:
        """地点状态不能倒退，除非有修复事件（repair）。"""
        seen: dict[str, set[str]] = defaultdict(set)
        violations: list[Violation] = []
        for ev in events:
            loc, state, has_repair = (list(ev) + [False])[:3]
            if state in seen[loc] and not has_repair:
                violations.append(
                    Violation("INV-003", message=f"地点 {loc} 状态回退至 {state}，但无修复事件")
                )
            seen[loc].add(state)
        return violations

    def inv004(
        self,
        has_changed: Collection[tuple[str, str]],
        has_event: Collection[tuple[str, str]],
    ) -> list[Violation]:
        """关系强度变化必须有关联事件。"""
        missing = set(has_changed) - set(has_event)
        return [
            Violation("INV-004", message=f"关系 {a}->{b} 强度变化但缺少关联事件")
            for a, b in sorted(missing)
        ]

    def inv005(self, ops: Collection[tuple[str, str]]) -> list[Violation]:
        """resolved 伏笔不能再作为未解状态推进（状态总序单向、不可回退）。"""
        peak: dict[str, int] = {}
        violations: list[Violation] = []
        for fs_id, state in ops:
            rank = _FS_RANK.get(state)
            if rank is None:
                continue
            prev = peak.get(fs_id, -1)
            if rank < prev:
                violations.append(
                    Violation(
                        "INV-005",
                        message=f"伏笔 {fs_id} 状态回退（当前 {state} < 先前 {prev}）",
                    )
                )
            peak[fs_id] = max(prev, rank)
        return violations

    def inv006(
        self,
        retired: Collection[str],
        reactivated: Collection[tuple[str, str]],
        confirmed: Collection[str],
    ) -> list[Violation]:
        """已 retired 的隐藏设定不能自动重新激活，除非用户确认。"""
        retired_set = set(retired)
        confirmed_set = set(confirmed)
        return [
            Violation(
                "INV-006",
                message=f"隐藏设定 {sid} 已 retired 却未获用户确认被重新激活（{chapter}）",
            )
            for chapter, sid in reactivated
            if sid in retired_set and sid not in confirmed_set
        ]

    def inv007(self, index_version: int, body_version: int) -> list[Violation]:
        """索引版本不能高于正文版本。"""
        if index_version > body_version:
            return [
                Violation(
                    "INV-007", message=f"索引版本 {index_version} 高于正文版本 {body_version}"
                )
            ]
        return []

    def inv008(self, steps: Collection[str]) -> list[Violation]:
        """章后管线必须满足 A→B→C 顺序。"""
        a_idx = [i for i, s in enumerate(steps) if s == "A"]
        b_idx = [i for i, s in enumerate(steps) if s == "B"]
        c_idx = [i for i, s in enumerate(steps) if s == "C"]
        bad: list[str] = []
        if b_idx and (not a_idx or min(b_idx) < min(a_idx)):
            bad.append("B 不能早于 A（章后管线须 A→B→C）")
        if c_idx and (not b_idx or min(c_idx) < min(b_idx)):
            bad.append("C 不能早于 B（章后管线须 A→B→C）")
        return [Violation("INV-008", message="; ".join(bad))] if bad else []
