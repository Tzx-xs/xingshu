"""影响范围分析器（对应设计 `10` §5）。

用户修改某类内容后，自动给出受影响的数据范围与需重新同步/审计的目标。
数据来自 10 §5 的映射表。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 修改类型 → (自动影响范围, 需重新同步/审计)（10 §5 表）
_IMPACT_TABLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "角色认知": (
        ("人物卡", "信息差追踪", "相关章节审计", "后续视角段"),
        ("信息差记录", "相关章重审"),
    ),
    "伏笔状态": (
        ("伏笔台账", "隐藏设定", "convergence_point", "后续章纲"),
        ("伏笔文件", "隐藏设定", "后续章纲重规划"),
    ),
    "地点状态": (
        ("地理卡", "旅行矩阵", "势力版图", "时间线"),
        ("地理卡", "时间线重校验"),
    ),
    "章节正文": (
        ("摘要", "关键事件", "人物状态", "索引", "文风向量"),
        ("章后管线A/B/C重执行", "索引重建"),
    ),
    "势力关系": (
        ("势力卡", "社会关系卡", "人物所属势力", "冲突检测"),
        ("势力卡", "关系卡", "冲突检测"),
    ),
}


@dataclass(frozen=True, slots=True)
class ImpactScope:
    change: str
    affected: list[str] = field(default_factory=list)   # 自动影响范围
    recheck: list[str] = field(default_factory=list)    # 需重新同步/审计


def impact_scope(change: str) -> ImpactScope:
    if change not in _IMPACT_TABLE:
        raise ValueError(f"未知修改类型: {change}（可选 {sorted(_IMPACT_TABLE)}）")
    affected, recheck = _IMPACT_TABLE[change]
    return ImpactScope(change=change, affected=list(affected), recheck=list(recheck))