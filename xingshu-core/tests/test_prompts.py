"""五层提示词组装测试（对应设计 `08`）。

验证：L1 系统层（作家锚点/叙事宪法/反AI味）→ L2 上下文层（大纲+事实+前情）
→ L3 任务层（章纲六维）→ L4 技能层（无技能时跳过）的组装，以及反AI味
强度按章节类型动态配置（08 §5）。
"""
from __future__ import annotations

from xingshu.config import NovelMeta
from xingshu.fact_base import Fact
from xingshu.outlines import ChapterOutline, Setting, VolumeOutline
from xingshu.prompts import PromptBuilder, anti_ai_intensity


def _meta(**overrides) -> NovelMeta:
    fields = dict(novel_id="n1", title="测试", chapter_word_target=500)
    fields.update(overrides)
    return NovelMeta(**fields)


def _facts() -> list[Fact]:
    return [
        Fact.new(system="characters", entity="char_001", attribute="mood",
                 value="警惕", source="第1章"),
        Fact.new(system="locations", entity="loc_001", attribute="state",
                 value="废弃", source="第1章"),
    ]


def _chapter() -> ChapterOutline:
    return ChapterOutline(
        number=2, title="入夜", summary="林远夜探山门", roles=("林远",),
        atmosphere="压抑", conflict="遭袭", narrative_goal="揭示住所",
        chapter_type="探索", pov="林远",
    )


def test_anti_ai_intensity_by_chapter_type() -> None:
    assert anti_ai_intensity("战斗") == "strong"
    assert anti_ai_intensity("转折") == "strong"
    assert anti_ai_intensity("对话") == "moderate"
    assert anti_ai_intensity("探索") == "moderate"
    assert anti_ai_intensity("日常") == "subtle"
    assert anti_ai_intensity("文艺") == "subtle"
    assert anti_ai_intensity("未知类型") == "moderate"  # 兜底


def test_layer1_contains_anchors_and_constitution() -> None:
    prompt = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"),
        chapter=_chapter(),
        facts=_facts(),
        summaries=("第1章：林远入山门。",),
        settings=(),
    )
    assert "作家身份" in prompt
    assert "叙事宪法" in prompt
    assert "反AI味" in prompt


def test_intensity_mapped_to_layer1_text() -> None:
    # 战斗章 → strong 文案（强制执行）
    strong = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"), chapter=ChapterOutline(1, chapter_type="战斗"),
        facts=(), summaries=(), settings=(),
    )
    assert "强制执行" in strong
    # 文艺段落 → subtle 文案
    subtle = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"), chapter=ChapterOutline(1, chapter_type="文艺"),
        facts=(), summaries=(), settings=(),
    )
    assert "建议提及" in subtle


def test_layer2_includes_facts_summaries_and_goal() -> None:
    prompt = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷", reveal_density=0.3),
        chapter=_chapter(),
        facts=_facts(),
        summaries=("第1章：林远入山门。",),
        settings=(),
    )
    # 事实切片：entity 与 attribute=value 可见，且带来源
    assert "char_001" in prompt
    assert "mood=警惕" in prompt
    assert "第1章" in prompt
    # 前情摘要
    assert "第1章：林远入山门。" in prompt
    # 章纲六维字段进入任务层
    assert "入夜" in prompt and "遭袭" in prompt and "探索" in prompt
    # 字数目标
    assert "500" in prompt


def test_layer2_only_contains_filtered_settings() -> None:
    prompt = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"),
        chapter=_chapter(),
        facts=(),
        summaries=(),
        settings=(Setting(sid="HS_PUB", is_public=True, text="明面规则：灵气分五行"),),
    )
    assert "明面规则：灵气分五行" in prompt


def test_layer4_absorbed_when_no_skills() -> None:
    prompt = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"), chapter=_chapter(),
        facts=(), summaries=(), settings=(),
    )
    # 无技能时不注入 Layer4 内容
    assert "# 激活技能" not in prompt