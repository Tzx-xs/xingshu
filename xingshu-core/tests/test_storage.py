"""事实库落盘测试（对应设计 `05` §9 存储演化 / `12` §7 MVP=Markdown+YAML）。

验证：FactBase（含 superseded 历史）可经 YAML 文件持久化并无损回读。
"""
from __future__ import annotations

import pytest

from xingshu.fact_base import Fact, FactBase
from xingshu.storage import (
    create_checkpoint,
    default_chapter_path,
    default_facts_path,
    ensure_novel_structure,
    latest_checkpoint,
    load_factbase,
    restore_checkpoint,
    save_audit_report,
    save_chapter,
    save_factbase,
)


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


def test_ensure_novel_structure_creates_directories(tmp_path) -> None:
    """对齐 12 §1：novel 目录下的标准子目录与 _facts 落库目录。"""
    ensure_novel_structure(tmp_path)
    for name in ("outlines", "truth_files", "chapters", "audits",
                 "reports", "checkpoints", "settings"):
        assert (tmp_path / name).is_dir()
    assert (tmp_path / "truth_files" / "_facts").is_dir()


def test_ensure_novel_structure_is_idempotent(tmp_path) -> None:
    ensure_novel_structure(tmp_path)
    ensure_novel_structure(tmp_path)  # 不报错


def test_default_chapter_path_layout(tmp_path) -> None:
    assert default_chapter_path(tmp_path, 3) == tmp_path / "chapters" / "ch_003.md"


def test_save_chapter_writes_body_and_summary(tmp_path) -> None:
    body_path = save_chapter(tmp_path, 1, "正文内容……", summary="第1章摘要")
    assert body_path == default_chapter_path(tmp_path, 1)
    body = body_path.read_text(encoding="utf-8")
    assert "# 第1章" in body and "正文内容……" in body
    summary_path = tmp_path / "chapters" / "ch_001_summary.md"
    assert summary_path.read_text(encoding="utf-8") == "第1章摘要"


def test_save_chapter_without_summary_skips_summary_file(tmp_path) -> None:
    save_chapter(tmp_path, 2, "正文")
    assert not (tmp_path / "chapters" / "ch_002_summary.md").exists()


def test_save_audit_report_writes_audit_file(tmp_path) -> None:
    # 07 §5：审计报告落盘 audits/audit_ch_XXX.md
    path = save_audit_report(tmp_path, 1, "综合评分：78\n问题：无")
    assert path == tmp_path / "audits" / "audit_ch_001.md"
    assert "综合评分：78" in path.read_text(encoding="utf-8")


def test_save_audit_report_revision_kind(tmp_path) -> None:
    # 02 §7：修订记录落盘 audits/revision_ch_XXX.md
    path = save_audit_report(tmp_path, 3, "第1轮修订记录", kind="revision")
    assert path == tmp_path / "audits" / "revision_ch_003.md"


def test_create_checkpoint_snapshots_facts(tmp_path) -> None:
    fb = FactBase()
    fb.remember(_new_fact(value="calm"))
    f = fb.remember(_new_fact(entity="char_002", value="hopeful"))
    fb.improve(f.id, source="第2章", value="angry")  # 产生 superseded 历史
    save_factbase(fb, tmp_path)
    ckpt = create_checkpoint(tmp_path)
    assert ckpt.name.startswith("checkpoint_")
    assert (ckpt / "facts.yaml").exists()
    assert ckpt == latest_checkpoint(tmp_path)


def test_no_checkpoint_yet_returns_none(tmp_path) -> None:
    assert latest_checkpoint(tmp_path) is None


def test_restore_checkpoint_restores_facts(tmp_path) -> None:
    fb = FactBase()
    fb.remember(_new_fact(value="calm"))
    save_factbase(fb, tmp_path)
    create_checkpoint(tmp_path)
    # 之后事实演进到另一个状态
    fb2 = load_factbase(tmp_path)
    old = fb2.recall()[0]
    fb2.improve(old.id, source="第5章", value="rage")
    save_factbase(fb2, tmp_path)
    assert load_factbase(tmp_path).recall()[0].value == "rage"
    # 定点回滚到 checkpoint
    restore_checkpoint(tmp_path, latest_checkpoint(tmp_path))
    assert load_factbase(tmp_path).recall()[0].value == "calm"