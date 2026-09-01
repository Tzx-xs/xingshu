"""Web 写作台服务测试（零第三依赖，标准库 http.server）。

提供 JSON API：POST /api/write（生成章节）、GET /api/facts（事实库）、
POST /api/commit（保存正文+事实+检查点）；GET / 返回写作台页面。
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from xingshu.config import NovelMeta
from xingshu.web import EngineServer, NovelHandler


@pytest.fixture
def server(tmp_path):
    meta = NovelMeta(novel_id="demo", title="演示", model="mock",
                     chapter_word_target=200, total_chapters=3)
    engine = EngineServer(novel_dir=tmp_path, meta=meta)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), NovelHandler)
    httpd.engine = engine
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, engine
    httpd.shutdown()


def _post(base: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or b"{}")


def test_index_serves_writing_page(server) -> None:
    base, _ = server
    with urllib.request.urlopen(base + "/") as resp:
        assert resp.status == 200
        assert "星枢" in resp.read().decode()


def test_api_facts_empty_initially(server) -> None:
    base, _ = server
    with urllib.request.urlopen(base + "/api/facts") as resp:
        assert json.loads(resp.read()) == {"facts": []}


def test_api_write_returns_text_and_accepted(server) -> None:
    base, engine = server
    res = _post(base, "/api/write", {
        "number": 1, "title": "入门", "summary": "林远入山门",
        "conflict": "借剑被拒", "narrative_goal": "立人设",
        "chapter_type": "对话", "pov": "林远",
    })
    assert res["accepted"] is True
    assert res["text"]
    assert res["violations"] == []


def test_api_write_accepts_settings_and_summaries(server) -> None:
    base, _ = server
    res = _post(base, "/api/write", {
        "number": 1, "title": "入门", "chapter_type": "探索",
        "summaries": ["第0章：序章。"],
        "settings": [{"sid": "明面规则", "is_public": True, "text": "灵气分五行"}],
    })
    prompt = engine_prompt(server[1])
    assert "灵气分五行" in prompt


def engine_prompt(engine) -> str:
    return engine.orch.llm.calls[-1]


def test_api_commit_persists_chapter_and_checkpoint(server) -> None:
    base, engine = server
    res = _post(base, "/api/commit", {"number": 1, "text": "正文……", "summary": "第1章摘要"})
    assert res["body"].endswith("chapters/ch_001.md")
    assert (engine.novel_dir / "chapters" / "ch_001.md").exists()
    assert (engine.novel_dir / "truth_files" / "_facts" / "facts.yaml").exists()
    assert "checkpoint" in res


def test_unknown_route_returns_404(server) -> None:
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(base + "/nope")
    assert exc.value.code == 404