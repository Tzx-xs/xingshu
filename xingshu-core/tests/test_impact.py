"""影响范围分析器测试（对应设计 `10` §5）。

用户修改某类内容后，自动确定受影响的数据与需重新同步/审计的范围。
"""
from __future__ import annotations

import pytest

from xingshu.impact import ImpactScope, impact_scope


def test_impact_scope_character_knowledge() -> None:
    scope = impact_scope("角色认知")
    assert "人物卡" in scope.affected
    assert "信息差追踪" in scope.affected
    assert any("重审" in r for r in scope.recheck)


def test_impact_scope_foreshadowing() -> None:
    scope = impact_scope("伏笔状态")
    assert scope.affected == ["伏笔台账", "隐藏设定", "convergence_point", "后续章纲"]
    assert scope.recheck == ["伏笔文件", "隐藏设定", "后续章纲重规划"]


def test_impact_scope_location() -> None:
    scope = impact_scope("地点状态")
    assert "地理卡" in scope.affected and "旅行矩阵" in scope.affected and "势力版图" in scope.affected


def test_impact_scope_chapter_text() -> None:
    scope = impact_scope("章节正文")
    assert "摘要" in scope.affected and "索引" in scope.affected
    assert "章后管线A/B/C重执行" in scope.recheck


def test_impact_scope_faction_relation() -> None:
    scope = impact_scope("势力关系")
    assert "势力卡" in scope.affected and "社会关系卡" in scope.affected


def test_unknown_change_raises() -> None:
    with pytest.raises(ValueError):
        impact_scope("未知修改类型")


def test_impact_scope_is_dataclass() -> None:
    scope = impact_scope("角色认知")
    assert isinstance(scope, ImpactScope)
    assert scope.change == "角色认知"