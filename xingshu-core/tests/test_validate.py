"""真相文件全量校验（零 LLM 确定性子集）测试（对应设计 `11` §3）。

幕/卷结束时的跨文件一致性检查；把 ADD-only 下仍同时 active 且取值冲突的
事实检出来——这是"错误跨章传播"的事实库层面的截断点（其余 LLM 语义
校验归 `07` audit_model 处理）。
"""
from __future__ import annotations

from xingshu.fact_base import Fact, FactBase
from xingshu.validate import check_active_fact_conflicts


def _fact(**overrides) -> Fact:
    fields = dict(system="characters", entity="char_001", attribute="eye_color",
                  value="黑", source="第1章")
    fields.update(overrides)
    return Fact.new(**fields)


def test_no_conflict_when_single_active() -> None:
    fb = FactBase()
    fb.remember(_fact())
    assert check_active_fact_conflicts(fb) == []


def test_no_conflict_when_old_version_superseded() -> None:
    fb = FactBase()
    old = fb.remember(_fact(value="黑"))
    fb.improve(old.id, source="第3章", value="紫")
    # 只剩一个 active（新版本）→ 无冲突
    assert check_active_fact_conflicts(fb) == []


def test_conflict_when_two_active_same_field() -> None:
    fb = FactBase()
    fb.remember(_fact(value="黑"))
    fb.remember(_fact(value="蓝"))  # 未失效的新事实（未走 improve）
    problems = check_active_fact_conflicts(fb)
    assert len(problems) == 1
    assert "characters/char_001: eye_color" in problems[0]


def test_conflict_in_different_systems_kept_separate() -> None:
    fb = FactBase()
    fb.remember(_fact())  # characters
    fb.remember(_fact(system="locations", entity="loc_001", attribute="state",
                      value="繁荣"))
    fb.remember(_fact(system="locations", entity="loc_001", attribute="state",
                      value="废弃"))
    problems = check_active_fact_conflicts(fb)
    assert len(problems) == 1  # locations 有一组冲突；characters 无
    assert "locations/loc_001: state" in problems[0]


def test_superseded_versions_do_not_participate() -> None:
    fb = FactBase()
    a = fb.remember(_fact(value="黑"))
    fb.improve(a.id, source="第2章", value="蓝")   # "黑"被 superseded，不参与
    fb.remember(_fact(value="红"))                  # 与当前 active "蓝"冲突
    assert len(check_active_fact_conflicts(fb)) == 1