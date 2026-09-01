"""事实库落盘测试（对应设计 `05` §9 存储演化 / `12` §7 MVP=Markdown+YAML）。

验证：FactBase（含 superseded 历史）可经 YAML 文件持久化并无损回读。
"""
from __future__ import annotations

import pytest

from xingshu.fact_base import Fact, FactBase
from xingshu.storage import default_facts_path, load_factbase, save_factbase


def _new_fact(**overrides) -> Fact:
    fields = dict(
        system="characters",
        entity="char_001",
        attribute="mood",
        value="calm",
        source="第1章",
    )
    fields.update(overrides)
    return Fact.new(**fields)


def test_default_facts_path_layout(tmp_path) -> None:
    assert default_facts_path(tmp_path) == tmp_path / "truth_files" / "_facts" / "facts.yaml"


def test_save_creates_facts_yaml(tmp_path) -> None:
    fb = FactBase()
    fb.remember(_new_fact())
    path = save_factbase(fb, tmp_path)
    assert path == default_facts_path(tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip()


def test_roundtrip_preserves_active_facts(tmp_path) -> None:
    fb = FactBase()
    fb.remember(_new_fact())
    fb.remember(_new_fact(system="locations", entity="loc_001", attribute="state", value="废弃"))
    save_factbase(fb, tmp_path)
    loaded = load_factbase(tmp_path)
    assert {f.entity for f in loaded.recall()} == {"char_001", "loc_001"}


def test_roundtrip_preserves_superseded_history(tmp_path) -> None:
    """ADD-only 历史的版本链必须随落盘保留。"""
    fb = FactBase()
    old = fb.remember(_new_fact(value="calm"))
    fb.improve(old.id, source="第2章", value="angry")
    save_factbase(fb, tmp_path)
    loaded = load_factbase(tmp_path)
    # 检索只看到新版本
    assert [f.value for f in loaded.recall(entity="char_001")] == ["angry"]
    # 历史完整保留（旧版本被标 superseded）
    hist = loaded.recall(entity="char_001", include_superseded=True)
    assert len(hist) == 2
    assert any(f.status == "superseded" and f.valid_until is not None for f in hist)


def test_roundtrip_preserves_forget(tmp_path) -> None:
    fb = FactBase()
    f = fb.remember(_new_fact())
    fb.forget(f.id, reason="作者修正")
    save_factbase(fb, tmp_path)
    loaded = load_factbase(tmp_path)
    assert loaded.recall(entity="char_001") == []
    gone = loaded.recall(entity="char_001", include_superseded=True)
    assert len(gone) == 1
    assert gone[0].reason == "作者修正"


def test_roundtrip_preserves_metadata(tmp_path) -> None:
    fb = FactBase()
    fb.remember(_new_fact(confidence=0.6, attribute="relation", value="师敌"))
    save_factbase(fb, tmp_path)
    loaded = load_factbase(tmp_path)
    f = loaded.recall()[0]
    assert (f.system, f.entity, f.attribute, f.value) == (
        "characters", "char_001", "relation", "师敌",
    )
    assert f.confidence == 0.6
    assert f.source == "第1章"
    assert f.created_at  # 时间戳保留


def test_load_missing_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_factbase(tmp_path / "nope")