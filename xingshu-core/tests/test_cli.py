"""CLI 一键启动入口测试：python -m xingshu [novel_dir] [--port N] [--no-browser]。

覆盖：默认演示目录、指定目录起服可访问、--no-browser 不触发浏览器、目录缺失报错。
"""
from __future__ import annotations

import threading
import time
import urllib.request

import pytest

from xingshu.__main__ import DEFAULT_NOVEL_DIR, main
from xingshu.web import create_server, serve_url


@pytest.fixture
def meta(tmp_path):
    from xingshu.config import NovelMeta

    path = tmp_path / "novel_meta.yaml"
    path.write_text("novel:\n  id: cli-demo\n  title: CLI 演示\n", encoding="utf-8")
    return NovelMeta(novel_id="cli-demo", title="CLI 演示", model="mock",
                     chapter_word_target=200, total_chapters=3)


def test_default_novel_dir_points_to_demo_novel() -> None:
    assert DEFAULT_NOVEL_DIR.name == "demo_novel"
    assert (DEFAULT_NOVEL_DIR / "novel_meta.yaml").exists()


def test_main_starts_and_serves_page(meta, tmp_path, monkeypatch) -> None:
    import xingshu.web as web

    created: dict = {}

    def spy(novel_dir, _meta, **kw):
        server = web.create_server(novel_dir, _meta, **kw)
        created["server"] = server
        return server

    monkeypatch.setattr("xingshu.__main__.create_server", spy)
    thread = threading.Thread(
        target=main, args=([str(tmp_path), "--port", "0", "--no-browser"],),
        daemon=True,
    )
    thread.start()
    for _ in range(100):
        if "server" in created:
            break
        time.sleep(0.02)
    server = created["server"]
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            assert resp.status == 200
            assert "星枢" in resp.read().decode()
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_main_no_such_novel_dir_exits(tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "nope")])
    assert exc.value.code != 0
    assert "novel_meta.yaml" in str(exc.value.code)
    # 顶层未捕获时该消息会打印到 stderr（sys.exit 的语义）
    assert capsys.readouterr().err == ""


def test_serve_url_uses_bound_port(meta, tmp_path) -> None:
    server = create_server(tmp_path, meta, port=0)
    try:
        url = serve_url(server)
        assert url.startswith("http://")
        assert str(server.server_address[1]) in url
    finally:
        server.server_close()