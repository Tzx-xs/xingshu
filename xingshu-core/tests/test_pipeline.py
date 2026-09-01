"""管线条（Orchestrator）骨架 + 可插拔 LLM 接口测试。

对应设计 `02` 章后管线 A→B→C、`07` 不变量阻断 && 三实体单向数据流。
"""
from __future__ import annotations

from xingshu.config import NovelMeta
from xingshu.core.invariants import InvariantChecker
from xingshu.fact_base import Fact, FactBase
from xingshu.llm.mock import MockLLM
from xingshu.pipeline.orchestrator import ChapterPlan, Orchestrator


def _orch(llm_text: str = "正文"):
    meta = NovelMeta(novel_id="n1", title="测试", total_chapters=5, chapter_word_target=500)
    return Orchestrator(
        llm=MockLLM(response=llm_text),
        facts=FactBase(),
        checker=InvariantChecker(),
        meta=meta,
    )


def test_mock_llm_records_and_returns() -> None:
    m = MockLLM(response="hello")
    assert m.complete("prompt") == "hello"
    assert m.calls == ["prompt"]


def test_mock_llm_carries_model() -> None:
    """MockLLM 与云端实现对齐：同样暴露 model 字段，便于上层统一显示/路由。"""
    m = MockLLM(response="x", model="mock-model")
    assert m.model == "mock-model"


def test_plan_returns_chapter_plan() -> None:
    orch = _orch()
    plan = orch.plan(3, chapter_type="战斗", pov="林远")
    assert isinstance(plan, ChapterPlan)
    assert plan.number == 3
    assert plan.type == "战斗"
    assert plan.pov == "林远"


def test_write_chapter_accepted_runs_abc_and_writes() -> None:
    orch = _orch()
    fact = Fact.new(
        system="characters", entity="char_001", attribute="mood",
        value="calm", source="第1章",
    )
    res = orch.write_chapter(
        1,
        known={"S1"},
        revealed={"S1"},
        facts_to_write=[fact],
        summary="第1章摘要",
    )
    assert res.accepted is True
    assert res.order == ["A", "B", "C"]
    assert len(orch.facts.recall(entity="char_001")) == 1
    assert orch.chapter_summary(1) == "第1章摘要"


def test_write_chapter_blocker_does_not_post() -> None:
    orch = _orch()
    res = orch.write_chapter(
        1,
        known=set(),
        revealed=set(),
        facts_to_write=[Fact.new(
            system="locations", entity="loc_1", attribute="state",
            value="废弃", source="第1章",
        )],
        summary="x",
        relation_changes={("A", "B")},
        relation_events=set(),  # 缺关联事件 → INV-004 blocker
    )
    assert res.accepted is False
    assert res.order == []            # 阻断，未进入章后管线
    assert orch.facts.recall(system="locations") == []  # 未写库
    assert any(v.invariant == "INV-004" for v in res.violations)
