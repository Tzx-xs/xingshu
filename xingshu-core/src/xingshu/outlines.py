"""四层大纲与 reveal_density 渐进放行（对应设计 `03`）。

卷纲 / 幕纲 / 章纲 / 场景纲四层结构；揭示量逐层递增（0.3 / 0.5 / 0.7 / 0.9），
但"低层不得越过高层"——最终生效密度取链条最小值（由最严的父层卡上限），
防止只在高层放行、父层未放行的隐藏设定提前进入生成上下文（防剧透，见 `06`）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class VolumeOutline:
    """卷纲（03 §2）：主题方向/核心冲突/伏笔清单，只给方向不剧透。"""

    title: str
    reveal_density: float = 0.3
    themes: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    foreshadowing_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArcOutline:
    """幕纲：幕级剧情线与角色弧光阶段。"""

    title: str
    reveal_density: float = 0.5
    plot_lines: tuple[str, ...] = ()
    role_arcs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SceneOutline:
    """场景纲（03 §2 场景纲）：最小可执行场景单元。"""

    name: str = ""
    location: str = ""
    time: str = ""
    roles: tuple[str, ...] = ()
    pov: str = ""
    objective: str = ""
    actions: tuple[tuple[str, str], ...] = ()
    dialogue_points: tuple[tuple[str, str], ...] = ()
    emotional_beats: tuple[str, ...] = ()
    reveal_density: float = 0.9


@dataclass(frozen=True, slots=True)
class ChapterOutline:
    """章纲（03 §2 章纲，六维度）。"""

    number: int
    title: str = ""
    summary: str = ""
    roles: tuple[str, ...] = ()
    atmosphere: str = ""
    conflict: str = ""
    narrative_goal: str = ""
    chapter_type: str = "常规"
    pov: str = ""
    foreshadowing_ops: tuple[tuple[str, str], ...] = ()  # (伏笔ID, 操作)
    setting_reveals: tuple[str, ...] = ()
    scenes: tuple[SceneOutline, ...] = ()
    reveal_density: float = 0.7


@dataclass(frozen=True, slots=True)
class Setting:
    """一条设定：明面（is_public）恒可见；隐藏设定需密度达标才揭示。

    默认 reveal_density_required=1.0（保守）：未显式标注门槛的隐藏设定默认不揭示。
    """

    sid: str
    is_public: bool = False
    reveal_density_required: float = 1.0
    text: str = ""


def effective_density(
    volume: VolumeOutline,
    arc: ArcOutline,
    chapter: ChapterOutline,
    scene: SceneOutline | None = None,
) -> float:
    """链条各层 reveal_density 的最小值：低层不得越过高层，最严父层卡上限。"""
    densities = [volume.reveal_density, arc.reveal_density, chapter.reveal_density]
    if scene is not None:
        densities.append(scene.reveal_density)
    return min(densities)


def select_settings(settings: Sequence[Setting], *, density: float) -> list[Setting]:
    """按密度过滤：明面设定恒可见，隐藏设定需 reveal_density_required <= density。"""
    return [
        s for s in settings
        if s.is_public or s.reveal_density_required <= density
    ]


def settings_for_chapter(
    volume: VolumeOutline,
    arc: ArcOutline,
    chapter: ChapterOutline,
    scene: SceneOutline | None,
    settings: Sequence[Setting],
) -> list[Setting]:
    """生成本章时注入的设定切片：先算链条生效密度，再过滤可见性。"""
    return select_settings(settings, density=effective_density(volume, arc, chapter, scene))