"""token 预算记账与引擎状态机测试（对应设计 `12` §5 / `10` §1）。

预算：正文/审计/章后管线的单章 token 上限，任一项超 20% 触发告警。
状态机：idle→running→paused⇄reviewing→running，非法迁移抛错；
进度持久化：novel_meta.progress 随状态更新落盘。
"""
from __future__ import annotations

import pytest
import yaml

from xingshu.budget import BudgetTracker
from xingshu.config import NovelMeta, load_novel_meta
from xingshu.engine_state import save_progress, transition


def _meta() -> NovelMeta:
    return NovelMeta(novel_id="n1", title="测试",
                     gen_tokens_per_chapter=8000, audit_tokens_per_chapter=6000)


def test_budget_records_and_totals() -> None:
    tracker = BudgetTracker(_meta())
    tracker.record(1, "generation", 5000)
    tracker.record(1, "generation", 1000)
    tracker.record(1, "audit", 6000)
    assert tracker.chapter_total(1) == 12000
    assert tracker.stage_total(1, "generation") == 6000


def test_budget_alert_when_over_120_percent() -> None:
    tracker = BudgetTracker(_meta())
    # 8000 * 1.2 = 9600；9500 通过，10000 告警
    assert tracker.alert(1, "generation", 9500) is None
    message = tracker.alert(1, "generation", 10000)
    assert message and "超预算" in message


def test_budget_no_alert_within_budget() -> None:
    tracker = BudgetTracker(_meta())
    assert tracker.alert(1, "audit", 6000) is None


def test_transition_follows_state_machine() -> None:
    assert transition("idle", "running") == "running"
    assert transition("running", "paused") == "paused"
    assert transition("paused", "reviewing") == "reviewing"
    # 复审不通过回暂停；通过回运行
    assert transition("reviewing", "paused") == "paused"
    assert transition("reviewing", "running") == "running"


def test_transition_invalid_raises() -> None:
    with pytest.raises(ValueError):
        transition("paused", "running")     # 暂停必须经复审
    with pytest.raises(ValueError):
        transition("idle", "reviewing")     # 直接进复审非法


def test_save_progress_persists_to_yaml(tmp_path) -> None:
    meta_file = tmp_path / "novel_meta.yaml"
    meta_file.write_text(
        yaml.safe_dump({
            "novel": {"id": "n1", "title": "测试"},
            "creation": {},
            "quality": {},
            "progress": {"engine_state": "idle", "current_chapter": 0,
                         "current_arc": 1, "current_volume": 1},
            "budget": {}, "llm": {},
        }, allow_unicode=True), encoding="utf-8")
    save_progress(load_novel_meta(meta_file), tmp_path, target="running",
                  current_chapter=3)
    reloaded = load_novel_meta(meta_file)
    assert reloaded.engine_state == "running"
    assert reloaded.current_chapter == 3