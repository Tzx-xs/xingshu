"""事实库落盘（对应设计 `05` §9 存储演化 / `12` §7：MVP 阶段用 YAML 文件承载 fact）。

目录约定：
    {novel_dir}/truth_files/_facts/facts.yaml

落盘保留全部 fact（含 superseded 历史，ADD-only 可审计）；回读后 recall 行为与内存版一致。
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from xingshu.fact_base import Fact, FactBase

DEFAULT_FACTS_RELPATH = Path("truth_files") / "_facts" / "facts.yaml"


def default_facts_path(novel_dir: str | Path) -> Path:
    """novel 目录下事实文件的默认路径。"""
    return Path(novel_dir) / DEFAULT_FACTS_RELPATH


def _fact_to_dict(fact: Fact) -> dict:
    return dataclasses.asdict(fact)


def _fact_from_dict(data: dict) -> Fact:
    return Fact(**{k: v for k, v in data.items() if k in {f.name for f in dataclasses.fields(Fact)}})


def _all_facts(fb: FactBase) -> list[Fact]:
    # 公开 API 即可取全量（含 superseded），按创建时间稳定排序保证可复现
    return sorted(fb.recall(include_superseded=True), key=lambda f: f.created_at)


def save_factbase(fb: FactBase, novel_dir: str | Path) -> Path:
    """将事实库全量（含历史）写入 novel 目录的 facts.yaml，返回该文件路径。"""
    path = default_facts_path(novel_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [_fact_to_dict(f) for f in _all_facts(fb)]
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.write_text(text, encoding="utf-8")
    return path


def load_factbase(novel_dir: str | Path) -> FactBase:
    """从 novel 目录读取 facts.yaml 还原事实库；文件不存在时抛 FileNotFoundError。"""
    path = default_facts_path(novel_dir)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    fb = FactBase()
    for item in data:
        fb.remember(_fact_from_dict(item))
    return fb