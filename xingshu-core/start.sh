#!/usr/bin/env bash
# 星枢写作台 · 一键启动脚本
#
# 用法：
#   ./start.sh                        # 默认演示小说，浏览器自动打开 http://127.0.0.1:8899
#   ./start.sh --port 9000            # 指定端口
#   ./start.sh <小说目录> [--port N]  # 指定另一部小说
#   ./start.sh --no-browser           # 只起服务，不自动开浏览器
#
# 云端模型：预设环境变量 Key（LLM_API_KEY/OPENAI_API_KEY/DEEPSEEK_API_KEY/AGNES_API_KEY）
# 且 novel_meta.yaml 配了非 mock 模型时自动走云端，否则 Mock 离线可跑。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON_CONFIG:-.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "[xingshu] 未找到 .venv，先安装依赖：" >&2
  echo "  uv venv .venv --python 3.14.7 && uv pip install --python .venv -e '.[dev]'" >&2
  exit 1
fi

exec "$PY" -m xingshu "$@"