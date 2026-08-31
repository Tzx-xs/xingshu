"""事实库（FactBase）核心协议测试。

对应设计：`05_记忆与状态管理.md` 的写入协议三条铁律 + 四段操作 API。
铁律：ADD-only 不覆盖 / 显式时效窗口 / 强制溯源。
"""
from __future__ import annotations

import pytest

from xingshu.fact_base import Fact, FactBase


def _new_fact(**overrides) -> Fact:
    """构造一个合法的测试事实，可覆盖字段。"""
    fields = dict(
        system="characters",
        entity="char_001",
        attribute="mood",
        value="calm",
        source="第1章",
    )
    fields.update(overrides)
    return Fact.new(**fields)


def test_remember_without_source_is_rejected() -> None:
    fb = FactBase()
    with pytest.raises(ValueError):
        fb.remember(_new_fact(source=""))


def test_remember_stores_active_fact() -> None:
    fb = FactBase()
    stored = fb.remember(_new_fact())
    assert stored.status == "active"
    assert stored.valid_until is None
    assert fb.get(stored.id) is stored


def test_recall_only_returns_active_facts() -> None:
    fb = FactBase()
    fb.remember(_new_fact())
    gone = fb.remember(_new_fact(entity="char_002"))
    fb.forget(gone.id, reason="已删")
    # 只有 char_001 那条保持 active
    assert len(fb.recall()) == 1


def test_recall_filters_by_system_and_entity() -> None:
    fb = FactBase()
    fb.remember(_new_fact(entity="char_001", attribute="mood"))
    fb.remember(_new_fact(entity="char_001", attribute="health"))
    fb.remember(_new_fact(entity="loc_001", system="locations", attribute="state",
                          source="第1章"))
    assert {f.attribute for f in fb.recall(entity="char_001")} == {"mood", "health"}
    assert {f.attribute for f in fb.recall(system="locations")} == {"state"}


def test_improve_supersedes_old_and_creates_new_version() -> None:
    fb = FactBase()
    old = fb.remember(_new_fact(value="calm"))
    new = fb.improve(old.id, source="第2章", value="angry")
    # ADD-only：旧记录保留但失效
    assert old.status == "superseded"
    assert old.valid_until is not None
    # 新记录 active
    assert new.status == "active"
    assert new.value == "angry"
    assert new.source == "第2章"
    # 检索只返回新版本
    assert [f.value for f in fb.recall(entity="char_001")] == ["angry"]


def test_improve_unknown_id_raises() -> None:
    fb = FactBase()
    with pytest.raises(KeyError):
        fb.improve("does_not_exist", source="第2章", value="x")


def test_forget_marks_superseded_and_optional_include() -> None:
    fb = FactBase()
    f = fb.remember(_new_fact())
    fb.forget(f.id, reason="作者修正")
    assert f.status == "superseded"
    assert fb.recall(entity="char_001") == []
    # include_superseded 时可见
    assert [x.id for x in fb.recall(entity="char_001", include_superseded=True)] == [f.id]
