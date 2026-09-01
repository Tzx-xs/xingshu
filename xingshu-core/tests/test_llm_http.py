"""云端大模型接入测试（OpenAI 兼容 Chat Completions，零第三依赖）。

对应设计 `07` §8（可插拔/双模型）：模型名与 base_url 来自 novel_meta，
API Key 从环境变量读取；用本地假 HTTP 服务器做真实请求验证。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from xingshu.config import NovelMeta
from xingshu.llm.base import LLMError
from xingshu.llm.http import OpenAICompatibleLLM


class _Recorder:
    def __init__(self) -> None:
        self.bodies: list[dict] = []
        self.status: int = 200
        self.content: str = "假模型回复"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        rec = self.server.recorder
        rec.bodies.append(body)
        if rec.status != 200:
            self.send_response(rec.status)
            self.end_headers()
            self.wfile.write(b"{}")
            return
        payload = {
            "choices": [{"message": {"role": "assistant", "content": rec.content}}]
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # 静默，避免测试噪音
        pass


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.recorder = _Recorder()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.recorder, httpd
    httpd.shutdown()


def _url(httpd) -> str:
    host, port = httpd.server_address
    return f"http://{host}:{port}"


def test_complete_posts_chat_completions_payload(server) -> None:
    rec, httpd = server
    llm = OpenAICompatibleLLM(base_url=_url(httpd), api_key="k", model="deepseek-chat")
    llm.complete("你好", temperature=0.5, max_tokens=100)
    assert len(rec.bodies) == 1
    body = rec.bodies[0]
    assert body["model"] == "deepseek-chat"
    assert body["messages"] == [{"role": "user", "content": "你好"}]
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 100


def test_complete_omits_optional_fields(server) -> None:
    rec, httpd = server
    llm = OpenAICompatibleLLM(base_url=_url(httpd), api_key="k", model="m")
    assert llm.complete("hi") == "假模型回复"
    body = rec.bodies[0]
    assert "temperature" not in body
    assert "max_tokens" not in body


def test_http_error_raises_llmerror(server) -> None:
    rec, httpd = server
    rec.status = 401
    llm = OpenAICompatibleLLM(base_url=_url(httpd), api_key="bad", model="m")
    with pytest.raises(LLMError, match="401"):
        llm.complete("x")


def test_from_meta_selects_writer_and_audit_model(server, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "k")
    rec, httpd = server
    meta = NovelMeta(
        novel_id="n1", title="t",
        model="deepseek-chat", audit_model="qwen-max",
        base_url=_url(httpd),
    )
    writer = OpenAICompatibleLLM.from_meta(meta)
    audit = OpenAICompatibleLLM.from_meta(meta, audit=True)
    assert writer.model == "deepseek-chat"
    assert audit.model == "qwen-max"
    assert writer.base_url == _url(httpd)


def test_from_meta_reads_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    meta = NovelMeta(novel_id="n1", title="t", model="m")
    llm = OpenAICompatibleLLM.from_meta(meta)
    assert llm.api_key == "secret"


def test_from_meta_reads_agnes_api_key(monkeypatch) -> None:
    monkeypatch.setenv("AGNES_API_KEY", "sk-agnes")
    meta = NovelMeta(novel_id="n1", title="t", model="agnes-2.5-flash",
                     base_url="https://apihub.agnes-ai.cn/v1")
    llm = OpenAICompatibleLLM.from_meta(meta)
    assert llm.api_key == "sk-agnes"
    assert llm.base_url == "https://apihub.agnes-ai.cn/v1"
    assert llm.model == "agnes-2.5-flash"


def test_from_meta_missing_api_key_raises(monkeypatch) -> None:
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "AGNES_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    meta = NovelMeta(novel_id="n1", title="t", model="m")
    with pytest.raises(ValueError, match="API"):
        OpenAICompatibleLLM.from_meta(meta)


def test_from_meta_default_base_url(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    meta = NovelMeta(novel_id="n1", title="t", model="m")
    assert OpenAICompatibleLLM.from_meta(meta).base_url == "https://api.openai.com/v1"