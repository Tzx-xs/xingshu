"""技能系统最小集测试（对应设计 `09`）。

YAML 技能定义（§2 格式子集）、技能库存取与按题材/注入点筛选（§4 消费
规则：≤5 个、同分类避免冲突）、以及 Layer4 注入（§2 content.prompt_directive）。
"""
from __future__ import annotations

import yaml

from xingshu.config import NovelMeta
from xingshu.outlines import ChapterOutline, VolumeOutline
from xingshu.prompts import PromptBuilder
from xingshu.skills import Skill, SkillLibrary, load_skill


def _meta() -> NovelMeta:
    return NovelMeta(novel_id="n1", title="测试", chapter_word_target=500)


def _chapter() -> ChapterOutline:
    return ChapterOutline(
        number=2, title="入夜", summary="林远夜探山门", roles=("林远",),
        atmosphere="压抑", conflict="遭袭", narrative_goal="揭示住所",
        chapter_type="探索", pov="林远",
    )

_SKILL_YAML = {
    "skill": {
        "id": "skill_pacing_control",
        "name": "节奏控制",
        "category": "pacing_control",
        "description": "控制段落节奏",
        "author": "builtin",
        "version": "1.0",
        "trigger": {"type": "auto"},
        "content": {
            "prompt_directive": "动作/紧张场景使用短句提速，抒情场景放长句。",
            "examples": ["快：追！脚步声砸在耳膜上。"],
            "rules": ["句长分布 > 30% 短句"],
        },
        "applicable_genres": ["玄幻", "仙侠"],
        "injection_points": ["generation", "audit"],
    }
}


def _write_skill(tmp_path) -> object:
    path = tmp_path / "skill_pacing_control.yaml"
    path.write_text(yaml.safe_dump(_SKILL_YAML, allow_unicode=True), encoding="utf-8")
    return path


def test_load_skill_from_yaml(tmp_path) -> None:
    skill = load_skill(_write_skill(tmp_path))
    assert skill.id == "skill_pacing_control"
    assert skill.category == "pacing_control"
    assert skill.prompt_directive
    assert skill.rules == ("句长分布 > 30% 短句",)


def test_load_skill_requires_id_and_directive(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"skill": {"name": "x"}}), encoding="utf-8")
    try:
        load_skill(bad)
        assert False, "应拒绝缺 id 的技能"
    except ValueError:
        pass


def test_library_selects_by_genre_and_injection_point() -> None:
    lib = SkillLibrary()
    lib.add(Skill(id="s1", name="a", category="narrative_technique",
                  prompt_directive="d1", applicable_genres=("玄幻",),
                  injection_points=("generation",)))
    lib.add(Skill(id="s2", name="b", category="pacing_control",
                  prompt_directive="d2", applicable_genres=("科幻",),
                  injection_points=("generation",)))
    picked = lib.select(genre="玄幻", injection_point="generation")
    assert [s.id for s in picked] == ["s1"]  # s2 题材不匹配


def test_library_avoids_conflicting_category_pair() -> None:
    """09 §4：同分类同注入点不重复激活（冲突矩阵约束的确定性实现）。"""
    lib = SkillLibrary()
    for i, sid in enumerate(("s1", "s2")):
        lib.add(Skill(id=sid, name=sid, category="pacing_control",
                      prompt_directive="d", applicable_genres=("玄幻",),
                      injection_points=("generation",)))
    picked = lib.select(genre="玄幻", injection_point="generation", limit=5)
    assert len(picked) == 1  # 只激活一个节奏控制技能


def test_library_select_caps_at_five() -> None:
    lib = SkillLibrary()
    for i in range(7):
        lib.add(Skill(id=f"s{i}", name=f"n{i}", category=f"cat{i % 3}",
                      prompt_directive="d", applicable_genres=("玄幻",),
                      injection_points=("generation",)))
    assert len(lib.select("玄幻", "generation", limit=5)) <= 5


def test_layer4_injected_when_skills_present() -> None:
    skill = Skill(id="s1", name="节奏", category="pacing_control",
                  prompt_directive="秘密指令：短句提速。", applicable_genres=("玄幻",),
                  injection_points=("generation",))
    prompt = PromptBuilder(_meta()).build_generation(
        volume=VolumeOutline("第一卷"), chapter=_chapter(),
        facts=(), summaries=(), settings=(),
        skills=(skill,),
    )
    assert "# 激活技能" in prompt
    assert "秘密指令：短句提速。" in prompt