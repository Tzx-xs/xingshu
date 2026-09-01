"""小说元数据配置加载与校验（对应设计 `12` §2 的 novel_meta.yaml）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _need(d: dict[str, Any], path: str) -> Any:
    """按点分路径取必填值，缺失抛 ValueError。"""
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            raise ValueError(f"novel_meta 缺少必填字段: {path}")
        cur = cur[key]
    return cur


def _get(d: dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


@dataclass(frozen=True, slots=True)
class NovelMeta:
    """必填 + 默认值齐全的元数据快照（冻结、紧凑）。"""

    novel_id: str
    title: str
    genre: str = "未知"
    language: str = "zh"
    total_volumes: int = 1
    total_chapters: int = 1
    chapter_word_target: int = 3000
    audit_threshold: int = 75
    revision_max_attempts: int = 3
    current_volume: int = 1
    current_arc: int = 1
    current_chapter: int = 0
    engine_state: str = "idle"
    gen_tokens_per_chapter: int = 8000
    audit_tokens_per_chapter: int = 6000
    pipeline_ab_tokens_per_chapter: int = 4000
    context_slice_budget: int = 12000
    model: str = ""
    audit_model: str = ""
    base_url: str = ""
    temperature: float = 0.8


def parse_novel_meta(data: dict[str, Any]) -> NovelMeta:
    novel = _need(data, "novel")
    creation = data.get("creation", {})
    quality = data.get("quality", {})
    progress = data.get("progress", {})
    budget = data.get("budget", {})
    llm = data.get("llm", {})
    import math

    def _int(v: Any) -> int:
        return int(v)

    def _float(v: Any) -> float:
        f = float(v)
        if not math.isfinite(f):
            raise ValueError(f"非法数值: {v}")
        return f

    novel_id = _need(data, "novel.id")
    title = _need(data, "novel.title")
    if not str(novel_id).strip() or not str(title).strip():
        raise ValueError("novel.id / novel.title 不能为空")

    return NovelMeta(
        novel_id=str(novel_id),
        title=str(title),
        genre=str(novel.get("genre", "未知")),
        language=str(novel.get("language", "zh")),
        total_volumes=_int(creation.get("total_volumes", 1)),
        total_chapters=_int(creation.get("total_chapters", 1)),
        chapter_word_target=_int(creation.get("chapter_word_target", 3000)),
        audit_threshold=_int(quality.get("audit_threshold", 75)),
        revision_max_attempts=_int(quality.get("revision_max_attempts", 3)),
        current_volume=_int(progress.get("current_volume", 1)),
        current_arc=_int(progress.get("current_arc", 1)),
        current_chapter=_int(progress.get("current_chapter", 0)),
        engine_state=str(progress.get("engine_state", "idle")),
        gen_tokens_per_chapter=_int(budget.get("gen_tokens_per_chapter", 8000)),
        audit_tokens_per_chapter=_int(budget.get("audit_tokens_per_chapter", 6000)),
        pipeline_ab_tokens_per_chapter=_int(
            budget.get("pipeline_ab_tokens_per_chapter", 4000)
        ),
        context_slice_budget=_int(budget.get("context_slice_budget", 12000)),
        model=str(llm.get("model", "")),
        audit_model=str(llm.get("audit_model", "")),
        base_url=str(llm.get("base_url", "")),
        temperature=_float(llm.get("temperature", 0.8)),
    )


def load_novel_meta(path: str | Path) -> NovelMeta:
    """从 YAML 文件加载元数据。"""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"novel_meta 必须是 YAML 映射: {path}")
    return parse_novel_meta(data)
