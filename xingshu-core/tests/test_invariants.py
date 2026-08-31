"""8 条叙事不变量确定性检查测试。

对应设计 `07_审计与质量系统.md` §4。这些是零 LLM 的硬约束，违反即阻断入库。
"""
from __future__ import annotations

from xingshu.core.invariants import InvariantChecker, Violation


def test_inv001_clean() -> None:
    assert InvariantChecker().inv001(
        known={"S1", "S2"}, revealed={"S1", "S2"}
    ) == []


def test_inv001_knows_unrevealed_is_violation() -> None:
    vs = InvariantChecker().inv001(known={"S1", "S2"}, revealed={"S1"})
    assert len(vs) == 1
    assert vs[0].invariant == "INV-001"


def test_inv002_clean() -> None:
    positions = [("T1", "A", "广场"), ("T1", "B", "酒馆")]
    assert InvariantChecker().inv002(positions) == []


def test_inv002_same_role_two_places_is_violation() -> None:
    positions = [("T1", "A", "广场"), ("T1", "A", "酒馆")]
    vs = InvariantChecker().inv002(positions)
    assert vs and vs[0].invariant == "INV-002"


def test_inv003_clean_advance() -> None:
    events = [("湖心镇", "繁荣"), ("湖心镇", "被毁")]
    assert InvariantChecker().inv003(events) == []


def test_inv003_state_rollback_without_repair_is_violation() -> None:
    events = [("湖心镇", "繁荣"), ("湖心镇", "被毁"), ("湖心镇", "繁荣")]
    vs = InvariantChecker().inv003(events)
    assert vs and vs[0].invariant == "INV-003"


def test_inv003_rollback_with_repair_is_ok() -> None:
    events = [("湖心镇", "繁荣"), ("湖心镇", "被毁"), ("湖心镇", "繁荣", True)]
    assert InvariantChecker().inv003(events) == []


def test_inv004_clean() -> None:
    assert InvariantChecker().inv004(
        has_changed={"A", "B"}, has_event={"A", "B"}
    ) == []


def test_inv004_relation_change_without_event_is_violation() -> None:
    vs = InvariantChecker().inv004(has_changed={("A", "B")}, has_event=set())
    assert vs and vs[0].invariant == "INV-004"


def test_inv005_clean_no_rollback() -> None:
    ops = [("FS-1", "planted"), ("FS-1", "progressing"), ("FS-1", "resolved")]
    assert InvariantChecker().inv005(ops) == []


def test_inv005_resolved_then_rollback_is_violation() -> None:
    ops = [("FS-1", "planted"), ("FS-1", "resolved"), ("FS-1", "progressing")]
    vs = InvariantChecker().inv005(ops)
    assert vs and vs[0].invariant == "INV-005"


def test_inv006_reactivate_retired_without_confirmation_is_violation() -> None:
    vs = InvariantChecker().inv006(
        retired={"HS-1"}, reactivated=[("第5章", "HS-1")], confirmed=set()
    )
    assert vs and vs[0].invariant == "INV-006"


def test_inv006_reactivate_with_confirmation_is_ok() -> None:
    assert InvariantChecker().inv006(
        retired={"HS-1"}, reactivated=[("第5章", "HS-1")], confirmed={"HS-1"}
    ) == []


def test_inv007_index_above_body_is_violation() -> None:
    vs = InvariantChecker().inv007(index_version=2, body_version=1)
    assert vs and vs[0].invariant == "INV-007"


def test_inv007_equal_or_below_is_ok() -> None:
    assert InvariantChecker().inv007(index_version=1, body_version=2) == []
    assert InvariantChecker().inv007(index_version=2, body_version=2) == []


def test_inv008_clean_order() -> None:
    assert InvariantChecker().inv008(["A", "B", "C"]) == []


def test_inv008_c_before_b_is_violation() -> None:
    vs = InvariantChecker().inv008(["A", "C", "B"])
    assert vs and vs[0].invariant == "INV-008"


def test_inv008_b_before_a_is_violation() -> None:
    vs = InvariantChecker().inv008(["B", "A", "C"])
    assert vs and vs[0].invariant == "INV-008"
