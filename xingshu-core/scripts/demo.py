"""端到端骨架演示。

串起：加载元数据 → 事实库 → 不变量检查 → 章级管线条（MockLLM）。
先创建演示目录：
    uv venv .venv --python 3.14.7 && uv pip install --python .venv -e ".[dev]"
    .venv/bin/python scripts/demo.py
"""
from __future__ import annotations

from pathlib import Path

from xingshu.config import load_novel_meta
from xingshu.core.invariants import InvariantChecker
from xingshu.fact_base import Fact, FactBase
from xingshu.llm.mock import MockLLM
from xingshu.pipeline.orchestrator import Orchestrator

META = Path(__file__).resolve().parents[1] / "sandbox_novels" / "demo_novel" / "novel_meta.yaml"


def main() -> None:
    meta = load_novel_meta(META)
    facts = FactBase()
    checker = InvariantChecker()
    llm = MockLLM("晨雾里，山门前立着一个疏朗少年。他抬起眼，恰好对上石阶尽头那道目光……")

    orch = Orchestrator(llm=llm, facts=facts, checker=checker, meta=meta)

    # 审计通过 → 校验 INV-004（关系变化缺事件）阻断路径
    for label, kwargs in {
        "通过": dict(
            known={"HS-1"}, revealed={"HS-1"},
            facts_to_write=[Fact.new(
                system="characters", entity="lin_yuan", attribute="mood",
                value="警惕", source="第1章",
            )],
            summary="林远入山门，初见周宁。",
        ),
        "阻断(缺关系事件)": dict(
            known=set(), revealed=set(),
            facts_to_write=[Fact.new(
                system="locations", entity="loc_shanmen", attribute="state",
                value="废弃", source="第1章",
            )],
            summary="x",
            relation_changes={("lin_yuan", "zhou_ning")},
            relation_events=set(),
        ),
    }.items():
        res = orch.write_chapter(1, **kwargs)
        print(f"[{label}] accepted={res.accepted}  order={res.order}  "
              f"violations={[v.invariant for v in res.violations]}")

    print("事实库 active:")
    for f in facts.recall():
        print(f"  - {f.system}/{f.entity}: {f.attribute}={f.value}  source=《{f.source}》")


if __name__ == "__main__":
    main()