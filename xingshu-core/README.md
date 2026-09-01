# 星枢渐进式叙事引擎（初版骨架）

对应设计文档 `/workspace/xingshu-engine` 的可运行初步实现。技术栈采用**最新稳定版 Python 3.14**（3.14.7）。

## 技术栈

- Python `>=3.14`（本机 UA 环境经 `uv` 部署 3.14.7）

- PyYAML + 标准库，最小依赖

- pytest（测试驱动开发）

## 目录结构

```
xingshu-core/
├── pyproject.toml
├── README.md
├── scripts/demo.py                # 端到端骨架演示
├── src/xingshu/
│   ├── config.py                  # novel_meta 配置加载与校验（对齐 12 §2）
│   ├── fact_base.py               # FactBase 事实库（对齐 05：ADD-only/溯源/时效）
│   ├── core/invariants.py         # 8 条叙事不变量确定性检查（对齐 07 §4）
│   ├── pipeline/orchestrator.py   # 章级管线条 A→B→C（对齐 02）
│   └── llm/{base,mock}.py         # 可插拔 LLM 接口 + Mock 实现（对齐 07 双模型解耦）
├── tests/                         # 33 个测试
└── sandbox_novels/demo_novel/     # 演示小说目录（novel_meta.yaml）
```

## 快速开始

```bash
uv venv .venv --python 3.14.7
uv pip install --python .venv -e ".[dev]"

# 运行测试
.venv/bin/python -m pytest -q

# 端到端骨架演示
.venv/bin/python scripts/demo.py

# 一键启动写作台（浏览器自动打开 http://127.0.0.1:8899）
./start.sh
# 指定端口 / 指定小说目录 / 只起服务不弹浏览器
./start.sh --port 9000
./start.sh <小说目录> --port 9000
./start.sh --no-browser
```

## 已实现（初版核心，严格 TDD）

| 模块                 | 文档来源  | 说明                                                                      |
| ------------------ | ----- | ----------------------------------------------------------------------- |
| `FactBase`         | 05    | 三条铁律：ADD-only 不覆盖 / 显式时效窗口 / 强制溯源；四段 API remember/recall/forget/improve |
| `InvariantChecker` | 07 §4 | 8 条不变量确定性检查（零 LLM），违反即 Blocker                                          |
| `config`           | 12 §2 | 加载/校验 `novel_meta.yaml`，缺必填报错，余项走默认                                     |
| `Orchestrator`     | 02    | 规划→生成→审计→章后管线 A→B→C；Blocker 阻断不写库                                       |
| `llm`              | 07    | `LLMClient` 协议 + `MockLLM`，任意模型实现协议即可接入                                 |

## 设计上的落地要点

- **错误防扩散**：事实库 `improve` 只新增新版本并标记旧版 `superseded`（记录时效/来源），便于审计与未来定点回滚（05/10）。

- **审计分级化**：不变量走确定性引擎、零 LLM、零 token；LLM 只处理语义存疑项，审计成本可控（07/12）。

- **可插拔模型**：正文模型与审计模型通过实现 `LLMClient` 解耦，支持双模型独立仲裁（07 §8）。

## 下一步（对齐 `14` 阶段一之后）

- 真相文件到 `novels/` 的 YAML/Markdown 持久化与卡片解析（04）

- 45 维 LLM 审计 + 评分与分级降档（07）

- 双设定 / reveal\_density 上下文过滤（03/06）

- Checkpoint 与定点回滚（05 §7 / 10）

- 技能库与冲突矩阵（09）