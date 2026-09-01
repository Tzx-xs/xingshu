"""五层提示词组装（对应设计 `08`）。

Layer1 系统层（作家身份锚点/叙事宪法/反AI味协议，按章节类型调强度）
Layer2 上下文层（已过滤的设定切片 + active 事实切片 + 前情摘要）
Layer3 任务层（章纲六维度 + 字数目标）
Layer4 技能层（有技能时注入，否则整层省略）
Layer5 审计层（审计时独立组装，不进入生成提示词）
"""
from __future__ import annotations

from collections.abc import Sequence

from xingshu.config import NovelMeta
from xingshu.fact_base import Fact
from xingshu.outlines import ChapterOutline, Setting, VolumeOutline

# 反AI味强度：章节类型 → 强度（08 §5 默认映射表）
_INTENSITY_BY_TYPE = {
    "战斗": "strong",
    "转折": "strong",
    "对话": "moderate",
    "探索": "moderate",
    "日常": "subtle",
    "文艺": "subtle",
}
_INTENSITY_EXEC = {
    "subtle": "建议提及（审计仅标记）",
    "moderate": "明确要求并给 1 个示例（审计标记并修订）",
    "strong": "强制执行并给 2 个示例（不达标打回重写）",
}
_P1P8 = [
    "P1 信息密度：每段≥2个有效信息单元",
    "P2 感官优先：每场景≥3种感官描写",
    "P3 角色差异：不同角色语言风格必须区分",
    "P4 节奏控制：长短句交替，避免匀速",
    "P5 衔接自然：避免机械过渡词（然后/接着/于是）",
    "P6 解释句式禁令：禁「也就是说/换句话说/简单来说」",
    "P7 展示不讲述：展示占比≥60%",
    "P8 情感克制：直白情感词≤20%",
]


def anti_ai_intensity(chapter_type: str) -> str:
    """按章节类型返回反AI味协议强度（未知类型兜底 moderate）。"""
    return _INTENSITY_BY_TYPE.get(chapter_type, "moderate")


class PromptBuilder:
    """组装生成章节所需的五层提示词。"""

    def __init__(self, meta: NovelMeta) -> None:
        self.meta = meta

    # ---- Layer 1：系统层（不变 + 强度化反AI味） ----

    def layer1(self, chapter_type: str) -> str:
        intensity = anti_ai_intensity(chapter_type)
        lines = [
            "## 作家身份锚点",
            "你是一位经验丰富的长篇小说创作者，精通类型文学叙事技法：",
            "1. 信息密度优先：每段推进剧情/角色/悬念/信息差，没发生的段落直接删掉",
            "2. 感官先行：先感官→再动作→后对话，禁止跳过感官直写情绪标签",
            "3. 角色差异：反应=背景×身体状态×利益关系，两个角色不能用同一种方式恐惧",
            "4. 因果严锁：一切转折对应前文细节，禁止「突然/意外/不知为何」",
            "5. 留白信任读者：不解释角色为什么这么做，用行为展示动机",
            "",
            "## 叙事宪法（全局不可变）",
            "- FACT_LOCK：标 [FACT_LOCK] 的事实不可违背；角色只知道 knows+partial（认知边界）",
            "- 关系锁定：按视角注入 subjective 关系，不越界写客观事实",
            "- 伏笔纪律：生成阶段不自行创造新伏笔，偷换靠铺垫，渐进揭示不超额",
            "- 禁止事项：不私创未登记角色、禁用上帝视角、禁段尾哲学总结、禁开头介绍背景",
            "- 章节连贯性：开头延续上章余韵，结尾悬在「未完成」",
            "",
            f"## 反AI味协议（强度：{intensity} — {_INTENSITY_EXEC[intensity]}）",
        ]
        return "\n".join(lines + [f"- {rule}" for rule in _P1P8])

    # ---- Layer 2：上下文层 ----

    def layer2(
        self,
        *,
        volume: VolumeOutline,
        facts: Sequence[Fact],
        summaries: Sequence[str],
        settings: Sequence[Setting],
    ) -> str:
        lines = [
            "## 上下文",
            f"### 卷纲（reveal_density={volume.reveal_density}）",
            f"卷名：{volume.title}",
            (
                "### 设定接入（已按 reveal_density 过滤，仅本章可见）"
                if settings else "### 设定接入（无）"
            ),
        ]
        for s in settings:
            lines.append(f"- {s.sid}：{s.text}" if s.text else f"- {s.sid}")
        lines.append("")
        lines.append("### 真相文件切片（仅 active 事实，带来源）")
        for f in facts:
            lines.append(
                f"- {f.system}/{f.entity}: {f.attribute}={f.value} 来源「{f.source}」"
            )
        lines.append("")
        lines.append("### 前情摘要（前 3-5 章）")
        if summaries:
            lines.extend(f"- {s}" for s in summaries)
        else:
            lines.append("-（无）")
        return "\n".join(lines)

    # ---- Layer 3：任务层 ----

    def layer3(self, chapter: ChapterOutline) -> str:
        roles = "、".join(chapter.roles)
        return "\n".join(
            [
                "## 本章任务",
                "### 章纲（六维度）",
                f"- 章节：第{chapter.number}章 {chapter.title}",
                f"- 梗概：{chapter.summary}",
                f"- 角色行为：{roles or '未指定'}",
                f"- 场景氛围：{chapter.atmosphere}",
                f"- 核心冲突：{chapter.conflict}",
                f"- 叙事目标：{chapter.narrative_goal}",
                f"- 章节类型：{chapter.chapter_type}",
                f"- POV：{chapter.pov or '未指定'}",
                f"- 伏笔操作：{chapter.foreshadowing_ops or '无'}",
                "",
                f"### 字数目标",
                f"本章目标 {self.meta.chapter_word_target} 字。",
            ]
        )

    # ---- 组装 ----

    def build_generation(
        self,
        *,
        volume: VolumeOutline,
        chapter: ChapterOutline,
        facts: Sequence[Fact],
        summaries: Sequence[str],
        settings: Sequence[Setting],
        skills: Sequence[object] = (),
    ) -> str:
        """组装生成正文用的完整提示词（L1+L2+L3+L4；无技能时省略 L4）。"""
        l1 = self.layer1(chapter.chapter_type)
        l2 = self.layer2(volume=volume, facts=facts, summaries=summaries, settings=settings)
        l3 = self.layer3(chapter)
        parts = [f"# 系统提示（Layer 1）\n{l1}", f"# 上下文（Layer 2）\n{l2}", f"# 任务（Layer 3）\n{l3}"]
        if skills:
            l4_lines = ["# 激活技能（Layer 4）"]
            for s in skills:
                l4_lines.append(f"## 技能：{s.name}（{s.category}）")
                l4_lines.append(s.prompt_directive)
                for ex in (s.examples or ()):
                    l4_lines.append(f"- 示例：{ex}")
            parts.append("\n".join(l4_lines))
        return "\n\n".join(parts)