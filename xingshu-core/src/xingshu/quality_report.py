"""幕/卷文学质量报告（对应设计 `11` §1-2）。

确定性部分：章节数量 / active 事实规模 / 伏笔状态分布；
六维文学评估（节奏曲线、角色成长弧、伏笔回收率、文风漂移、读者预期管理、
总体评估与建议）：缺省时占位，提供独立 audit_model 时逐维评估后嵌入。
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence

from xingshu.fact_base import FactBase
from xingshu.llm.base import LLMClient

SIX_DIMENSIONS = (
    "节奏曲线分析", "角色成长弧", "伏笔回收率", "文风漂移",
    "读者预期管理", "总体评估与建议",
)


def evaluate_arc(
    llm: LLMClient,
    *,
    arc_title: str,
    chapter_summaries: Sequence[str],
) -> dict[str, str]:
    """由独立审计模型对六维做文学评估，返回 {维度: 评语}。"""
    prompt = "\n".join(
        [
            f"请对《{arc_title}》做幕间文学质量评估（11 §2 六维）。",
            "## 章节摘要",
            *(f"- {s}" for s in (chapter_summaries or ())),
            "",
            '只输出严格 JSON：{"节奏曲线分析": "...", "角色成长弧": "...", '
            '"伏笔回收率": "...", "文风漂移": "...", "读者预期管理": "...", '
            '"总体评估与建议": "..."}，不要输出任何其它内容。',
        ]
    )
    payload = json.loads(llm.complete(prompt))
    result: dict[str, str] = {}
    for dim in SIX_DIMENSIONS:
        result[dim] = str(payload.get(dim, "（缺省）"))
    return result


def build_arc_report(
    *,
    arc_title: str,
    chapter_summaries: Sequence[str],
    factbase: FactBase,
    arc_eval: dict[str, str] | None = None,
) -> str:
    """组装幕间报告全文。"""
    lines = [
        f"# 幕间文学质量报告 — {arc_title}",
        "",
        "## 基础数据",
        f"- 章节数量：{len(chapter_summaries)}",
        f"- active 事实总数：{len(factbase.recall())}",
    ]
    fs = [f.value for f in factbase.recall(system="foreshadowing")]
    if fs:
        lines.append("## 伏笔状态分布")
        for state, count in Counter(fs).most_common():
            lines.append(f"- {state}: {count}")
    lines.append("")
    lines.append("## 六维文学评估")
    if arc_eval:
        for dim in SIX_DIMENSIONS:
            lines.append(f"- **{dim}**：{arc_eval.get(dim, '（缺省）')}")
    else:
        lines.append("- 待审计模型复核（`07` audit_model）")
    return "\n".join(lines)