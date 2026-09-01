"""四层大纲与 reveal_density 渐进放行测试（对应设计 `03`）。

验证：卷/幕/章/场景四层结构的密度链（低层不得越过高层，取最小生效密度），
以及按密度过滤隐藏设定的可见性（明面设定永远可见）。
"""
from __future__ import annotations

from xingshu.outlines import (
    ArcOutline,
    ChapterOutline,
    SceneOutline,
    Setting,
    VolumeOutline,
    effective_density,
    select_settings,
    settings_for_chapter,
)


def test_volume_outline_default_density_is_0_3() -> None:
    v = VolumeOutline(title="第一卷", themes=("成长",), conflicts=("借剑",))
    assert v.title == "第一卷"
    assert v.reveal_density == 0.3
    assert v.foreshadowing_ids == ()


def test_arc_outline_default_density_is_0_5() -> None:
    a = ArcOutline(title="第一幕", plot_lines=("入山",))
    assert a.reveal_density == 0.5
    assert a.plot_lines == ("入山",)


def test_chapter_outline_six_dimensions_and_default_0_7() -> None:
    ch = ChapterOutline(
        number=1, title="入门", summary="林远入山门",
        roles=("林远", "周宁"), atmosphere="压抑", conflict="借剑被拒",
        narrative_goal="立人设", chapter_type="对话", pov="林远",
    )
    assert ch.chapter_type == "对话"
    assert ch.reveal_density == 0.7
    assert ch.scenes == ()
    assert ch.setting_reveals == ()


def test_scene_outline_default_density_is_0_9() -> None:
    sc = SceneOutline(
        name="山门", location="loc_shanmen", time="晨",
        roles=("林远",), pov="林远", objective="入山叩门",
    )
    assert sc.reveal_density == 0.9
    assert sc.actions == ()


def test_effective_density_is_min_of_chain() -> None:
    v = VolumeOutline("卷", reveal_density=0.3)
    a = ArcOutline("幕", reveal_density=0.5)
    ch = ChapterOutline(number=1, reveal_density=0.7)
    sc = SceneOutline(reveal_density=0.9)
    # 低层不得越过高层：最终生效密度 = 各层最小
    assert effective_density(v, a, ch, sc) == 0.3
    # 章层设得更低时，章层成为约束
    assert effective_density(v, a, ChapterOutline(1, reveal_density=0.2), sc) == 0.2
    # 未提供场景层时只取 卷/幕/章
    assert effective_density(v, a, ch) == 0.3


def test_select_settings_public_always_visible() -> None:
    settings = [Setting(sid="HS-1", is_public=True), Setting(sid="HS-2")]
    visible = select_settings(settings, density=0.0)
    assert [s.sid for s in visible] == ["HS-1"]


def test_select_settings_by_required_density() -> None:
    settings = [
        Setting(sid="HS-3", reveal_density_required=0.8),
        Setting(sid="HS-4", reveal_density_required=0.3),
    ]
    assert [s.sid for s in select_settings(settings, density=0.3)] == ["HS-4"]
    assert [s.sid for s in select_settings(settings, density=0.8)] == ["HS-3", "HS-4"]


def test_settings_for_chapter_combines_chain_and_filter() -> None:
    v = VolumeOutline("卷", reveal_density=0.3)
    a = ArcOutline("幕", reveal_density=0.5)
    ch = ChapterOutline(number=1, reveal_density=0.7)
    sc = SceneOutline(reveal_density=0.9)
    settings = [
        Setting(sid="PUB", is_public=True),
        Setting(sid="HS_A", reveal_density_required=0.3),  # 0.3 阈值，恰好放行
        Setting(sid="HS_B", reveal_density_required=0.8),  # 高层级设定，卷层不放行
    ]
    visible = settings_for_chapter(v, a, ch, sc, settings)
    assert [s.sid for s in visible] == ["PUB", "HS_A"]