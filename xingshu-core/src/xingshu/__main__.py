"""星枢写作台一键启动命令行入口。

用法（在 xingshu-core 目录下）：
    python -m xingshu                       # 默认演示小说，端口 8899
    python -m xingshu --port 9000           # 指定端口
    python -m xingshu <novel_dir>           # 指定小说目录（含 novel_meta.yaml）
    python -m xingshu --no-browser          # 启动后不自动打开浏览器

云端模型：仅当 novel_meta 配了非 mock 模型且有环境变量 Key 才走云端
（LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY / AGNES_API_KEY 之一），
否则自动回退 Mock，离线可跑（纯本地工具的降级策略）。
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from xingshu.config import NovelMeta, load_novel_meta
from xingshu.web import create_server, serve_url

DEFAULT_NOVEL_DIR = (
    Path(__file__).resolve().parents[2] / "sandbox_novels" / "demo_novel"
)


def _novel_meta_path(novel_dir: Path) -> Path:
    path = novel_dir / "novel_meta.yaml"
    if not path.exists():
        sys.exit(f"找不到小说元数据: {path}\n请先创建该小说目录（含 novel_meta.yaml），或换个目录。")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m xingshu",
        description="星枢渐进式叙事引擎 · 写作台（浏览器打开后填章纲→生成→审计→保存）",
    )
    parser.add_argument(
        "novel_dir",
        nargs="?",
        type=Path,
        default=DEFAULT_NOVEL_DIR,
        help=f"小说目录（含 novel_meta.yaml），默认: {DEFAULT_NOVEL_DIR}",
    )
    parser.add_argument("--port", type=int, default=8899, help="监听端口，默认 8899")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument(
        "--no-browser", action="store_true", help="启动后不自动打开浏览器"
    )
    args = parser.parse_args(argv)

    meta: NovelMeta = load_novel_meta(_novel_meta_path(args.novel_dir))
    httpd = create_server(args.novel_dir, meta, host=args.host, port=args.port)
    url = serve_url(httpd)

    if meta.model and meta.model != "mock":
        print(f"模型: {meta.model}（云端，经 {meta.base_url or '默认 OpenAI 兼容地址'}）")
    else:
        print("模型: mock（离线回退；配置云端模型 + 环境变量 Key 后自动切云端）")

    print(f"星枢写作台已启动: {url}  （小说《{meta.title}》）")
    print("按 Ctrl+C 停止。")

    if not args.no_browser:
        # 稍等 1s 让端口就绪，再拉起默认浏览器（失败静默，不影响服务）
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()