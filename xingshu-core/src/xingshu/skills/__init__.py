"""技能系统最小集（对应设计 `09`）。

- `Skill`：09 §2 定义格式的子集（id/category/prompt_directive/examples/rules 等）
- `load_skill`：从 YAML 技能文件读取并校验必填字段
- `SkillLibrary`：技能库 + 按 题材/注入点 筛选（09 §4：≤5 个、同分类同注入点
  只激活其一——冲突矩阵在确定性子集的落地）
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

# 09 §3 技能 8 分类；09 §2 injection_points 可取值；examples 上限（09 §2）
CATEGORIES = {
    "narrative_technique", "style_template", "plot_device", "character_method",
    "dialogue_technique", "pacing_control", "worldbuilding", "revision_method",
}
INJECTION_POINTS = {"planning", "generation", "audit", "revision"}
MAX_EXAMPLES = 3


def validate_skill(skill: Skill) -> list[str]:
    """入库门禁的确定性校验（09 §5②③ 格式验证/质量门禁在确定性子集）。"""
    problems: list[str] = []
    if skill.category not in CATEGORIES:
        problems.append(f"category 非法: {skill.category}（可选 {sorted(CATEGORIES)}）")
    bad_points = [p for p in skill.injection_points if p not in INJECTION_POINTS]
    if bad_points:
        problems.append(f"injection_points 含非法值: {bad_points}")
    if len(skill.examples) > MAX_EXAMPLES:
        problems.append(f"examples 超过 {MAX_EXAMPLES} 个上限")
    return problems


def _conflict_pair(a: Skill, b: Skill) -> dict:
    """09 §6 冲突度（确定性近似：同分类=方向冲突强；共享规则=语义重叠）。

    对齐公式"方向性冲突率×0.6 + 语义向量距离×0.4"的确定性子集：
    同分类视为方向冲突；rules 重叠视为语义重叠。
    """
    same_category = a.category == b.category
    shared_rules = len(set(a.rules) & set(b.rules))
    if same_category:
        score = 0.8
        reason = f"同分类 {a.category}：方向性冲突概率高"
    elif shared_rules:
        score = 0.5
        reason = f"共享 {shared_rules} 条规则，语义重叠"
    else:
        score = 0.2
        reason = "分类不同且无规则重叠"
    level = "high" if score >= 0.7 else ("medium" if score >= 0.4 else "low")
    return {
        "skill_a": a.id, "skill_b": b.id,
        "conflict_score": score, "level": level, "reason": reason,
    }


def conflict_matrix(skills: Sequence[Skill], *, threshold: float = 0.7) -> dict:
    """技能库冲突矩阵：返回 medium 及以上的技能对（09 §6 JSON 结构）。"""
    matrix = {
        "version": "1.0",
        "updated_at": "",
        "threshold": threshold,
        "pairs": [],
    }
    for i, a in enumerate(skills):
        for b in skills[i + 1:]:
            pair = _conflict_pair(a, b)
            if pair["conflict_score"] >= threshold - 0.3:  # 收录 medium+ (≥0.4)
                matrix["pairs"].append(pair)
    return matrix


@dataclass(frozen=True, slots=True)
class Skill:
    id: str
    name: str
    category: str
    prompt_directive: str          # 注入 Layer4（09 §2 content.prompt_directive）
    applicable_genres: tuple[str, ...] = ()
    injection_points: tuple[str, ...] = ()  # planning/generation/audit/revision
    author: str = "user"
    version: str = "1.0"
    trigger: str = "manual"
    description: str = ""
    examples: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()    # 确定性检查，注入审计层（零 token）


def load_skill(path: str | Path) -> Skill:
    """从技能 YAML 文件读取；缺 id / prompt_directive 抛 ValueError。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    s = data.get("skill", data) if isinstance(data, dict) else {}
    if not isinstance(s, dict):
        raise ValueError(f"技能文件必须是 YAML 映射（含 skill 段）: {path}")
    sid = s.get("id")
    content = s.get("content") or {}
    directive = content.get("prompt_directive")
    if not sid or not directive:
        raise ValueError(f"技能缺少必填字段 id / content.prompt_directive: {path}")
    trigger = s.get("trigger")
    trigger = trigger.get("type", "manual") if isinstance(trigger, dict) else (trigger or "manual")
    return Skill(
        id=str(sid),
        name=str(s.get("name") or sid),
        category=str(s.get("category", "narrative_technique")),
        prompt_directive=str(directive),
        applicable_genres=tuple(s.get("applicable_genres") or ()),
        injection_points=tuple(s.get("injection_points") or ()),
        author=str(s.get("author", "user")),
        version=str(s.get("version", "1.0")),
        trigger=str(trigger),
        description=str(s.get("description", "")),
        examples=tuple(content.get("examples") or ()),
        rules=tuple(content.get("rules") or ()),
    )


class SkillLibrary:
    """内存技能库：add 蓄库，select 按 题材+注入点 消费（≤limit 个）。"""

    def __init__(self) -> None:
        self._skills: list[Skill] = []

    def add(self, skill: Skill) -> None:
        self._skills.append(skill)

    def all(self) -> list[Skill]:
        return list(self._skills)

    def select(
        self,
        genre: str = "",
        injection_point: str = "generation",
        *,
        limit: int = 5,
    ) -> list[Skill]:
        chosen: list[Skill] = []
        seen: set[tuple[str, str]] = set()
        for s in self._skills:
            if s.applicable_genres and genre and genre not in s.applicable_genres:
                continue
            if injection_point not in s.injection_points:
                continue
            key = (s.category, injection_point)
            if key in seen:  # 同分类同注入点不重复激活（冲突矩阵约束）
                continue
            seen.add(key)
            chosen.append(s)
            if len(chosen) >= limit:
                break
        return chosen