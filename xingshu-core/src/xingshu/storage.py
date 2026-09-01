"""事实库与小说目录持久化（对齐 `05` §9 / `12` §1、§7）。

目录约定（12 §1）：
    {novel_dir}/truth_files/_facts/facts.yaml   事实落库
    {novel_dir}/chapters/ch_XXX.md              章正文
    {novel_dir}/chapters/ch_XXX_summary.md      章摘要（章后管线-C）

落盘保留全部 fact（含 superseded 历史，ADD-only 可审计）；回读后 recall
行为与内存版一致。
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from xingshu.fact_base import Fact, FactBase

DEFAULT_FACTS_RELPATH = Path("truth_files") / "_facts" / "facts.yaml"
NOVEL_SUBDIRS = (
    "outlines", "truth_files", "chapters", "audits", "reports", "checkpoints", "settings",
)


def default_facts_path(novel_dir: str | Path) -> Path:
    """novel 目录下事实文件的默认路径。"""
    return Path(novel_dir) / DEFAULT_FACTS_RELPATH


def default_chapter_path(novel_dir: str | Path, number: int) -> Path:
    """第 number 章正文的默认路径。"""
    return Path(novel_dir) / "chapters" / f"ch_{number:03d}.md"


def ensure_novel_structure(novel_dir: str | Path) -> None:
    """创建 12 §1 的标准小说目录（幂等）。"""
    root = Path(novel_dir)
    for sub in NOVEL_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    default_facts_path(root).parent.mkdir(parents=True, exist_ok=True)


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


def save_chapter(
    novel_dir: str | Path,
    number: int,
    text: str,
    *,
    summary: str | None = None,
) -> Path:
    """保存章正文到 chapters/ch_XXX.md（章后管线-C 摘要存 ch_XXX_summary.md）。"""
    root = Path(novel_dir)
    chapters = root / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    body = chapters / f"ch_{number:03d}.md"
    body.write_text(f"# 第{number}章\n\n{text}\n", encoding="utf-8")
    if summary is not None:
        (chapters / f"ch_{number:03d}_summary.md").write_text(summary, encoding="utf-8")
    return body


def save_audit_report(
    novel_dir: str | Path,
    number: int,
    content: str,
    *,
    kind: str = "audit",
) -> Path:
    """审计/修订记录落盘：audits/{kind}_ch_XXX.md（07 §5 / 02 §7）。"""
    root = Path(novel_dir)
    audits = root / "audits"
    audits.mkdir(parents=True, exist_ok=True)
    path = audits / f"{kind}_ch_{number:03d}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---- Checkpoint / 定点回滚（05 §7 / 10 §6 的简化落地） ----

import time as _time


def create_checkpoint(novel_dir: str | Path) -> Path:
    """把当前 facts.yaml 快照到 checkpoints/checkpoint_<ts>/（须先有落盘事实）。"""
    root = Path(novel_dir)
    source = default_facts_path(root)
    ckpt = root / "checkpoints" / f"checkpoint_{int(_time.time())}"
    (ckpt / "facts.yaml").parent.mkdir(parents=True, exist_ok=True)
    (ckpt / "facts.yaml").write_bytes(source.read_bytes())
    return ckpt


def latest_checkpoint(novel_dir: str | Path) -> Path | None:
    """最新 checkpoint 目录；无则 None。"""
    checkpoints = sorted(
        (Path(novel_dir) / "checkpoints").glob("checkpoint_*"), key=lambda p: p.name
    )
    return checkpoints[-1] if checkpoints else None


def restore_checkpoint(novel_dir: str | Path, checkpoint: str | Path) -> Path:
    """定点回滚：用 checkpoint 的 facts.yaml 覆盖当前落库（10 §6 restore）。"""
    root = Path(novel_dir)
    source = Path(checkpoint) / "facts.yaml"
    if not source.exists():
        raise FileNotFoundError(f"checkpoint 缺少 facts.yaml: {source}")
    target = default_facts_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target