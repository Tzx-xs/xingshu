"""真相文件全量校验（零 LLM 确定性子集，对齐 `11` §3）。

幕/卷结束时的跨文件一致性检查。本模块负责"事实库内部一致性"的确定性
部分：ADD-only 下同一 (system, entity, attribute) 不允许存在多个取值
不同的 active 事实（否则后续生成将无所适从，即为错误跨章传播的源头）。
其余跨文件语义一致性交由 `07` 的审计模型复核（LLM）。
"""
from __future__ import annotations

from collections import defaultdict

from xingshu.fact_base import FactBase


def check_active_fact_conflicts(fb: FactBase) -> list[str]:
    """返回有冲突的 active 事实描述（空 = 通过）。"""
    groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for f in fb.recall():  # 仅 active（含有效窗口）
        groups[(f.system, f.entity, f.attribute)].add(f.value)
    return [
        f"{key[0]}/{key[1]}: {key[2]} 存在多个互斥 active 取值 {sorted(values)}"
        for key, values in groups.items()
        if len(values) > 1
    ]