"""引擎状态机与进度持久化（对应设计 `10` §1）。

状态迁移（10 §1）：idle → running → paused ⇄ reviewing → running。
非法迁移抛 ValueError；进度（引擎状态/当前章节）写回 novel_meta.yaml。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from xingshu.config import NovelMeta

# 合法迁移表（10 §1 表）
_ALLOWED_TRANSITIONS = {
    ("idle", "running"),       # 开始创作
    ("running", "paused"),     # 用户暂停（须等完整单元完成，由上层把关）
    ("paused", "reviewing"),   # 用户保存修改 → 复审
    ("reviewing", "running"),  # 复审通过 → 继续
    ("reviewing", "paused"),   # 复审不通过 → 回暂停修改
}


def transition(current: str, target: str) -> str:
    """按状态机校验并返回目标状态；非法迁移抛 ValueError。"""
    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise ValueError(f"非法状态迁移: {current} → {target}")
    return target


def save_progress(
    meta: NovelMeta,
    novel_dir: str | Path,
    *,
    target: str,
    current_chapter: int | None = None,
) -> None:
    """把引擎推进到 target 状态（校验迁移合法性），并持久化进度到 novel_meta.yaml。"""
    final_state = transition(meta.engine_state, target)
    path = Path(novel_dir) / "novel_meta.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    progress = data.setdefault("progress", {})
    progress["engine_state"] = final_state
    if current_chapter is not None:
        progress["current_chapter"] = current_chapter
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")