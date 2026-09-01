"""幕/卷六维质量报告测试（对应设计 `11` §1-2）。

报告含确定性基础数据（章节数/事实规模/伏笔状态分布）+ 六维文学评估
（缺省时占位，提供独立审计 LLM 时逐维评估）。
"""
from __future__ import annotations

from xingshu.fact_base import Fact, FactBase
from xingshu.llm.mock import MockLLM
from xingshu.quality_report import SIX_DIMENSIONS, build_arc_report, evaluate_arc

_ARC_JSON = (
    '{"节奏曲线分析": "稳步上升", "角色成长弧": "林远完成初步成长", '
    '"伏笔回收率": "3/5", "文风漂移": "稳定", "读者预期管理": "到位", '
    '"总体评估与建议": "下一幕提升张力"}'
)


def _fb() -> FactBase:
    fb = FactBase()
    fb.remember(Fact.new(system="foreshadowing", entity="FS-1", attribute="status",
                         value="planted", source="第1章"))
    fb.remember(Fact.new(system="foreshadowing", entity="FS-2", attribute="status",
                         value="progressing", source="第2章"))
    fb.remember(Fact.new(system="characters", entity="char_001", attribute="mood",
                         value="calm", source="第1章"))
    return fb


def test_arc_report_contains_deterministic_metrics() -> None:
    text = build_arc_report(arc_title="第一幕", chapter_summaries=("s1", "s2", "s3"), factbase=_fb())
    assert "第一幕" in text
    assert "章节数量：3" in text
    assert "active 事实总数：3" in text
    assert "planted" in text and "progressing" in text


def test_arc_report_placeholder_without_llm() -> None:
    text = build_arc_report(arc_title="第一幕", chapter_summaries=(), factbase=FactBase())
    assert "待审计模型复核" in text


def test_evaluate_arc_with_llm_returns_six_dimensions() -> None:
    llm = MockLLM(response=_ARC_JSON)
    result = evaluate_arc(llm, arc_title="第一幕", chapter_summaries=("第1章摘要",))
    assert set(result) == set(SIX_DIMENSIONS)
    assert result["节奏曲线分析"] == "稳步上升"
    assert "第一幕" in llm.calls[0]


def test_arc_report_embeds_six_dimension_eval() -> None:
    eval_map = dict.fromkeys(SIX_DIMENSIONS, "评价")
    text = build_arc_report(arc_title="第一幕", chapter_summaries=(), factbase=FactBase(),
                            arc_eval=eval_map)
    for dim in SIX_DIMENSIONS:
        assert dim in text