"""浏览器写作台服务（零第三依赖，标准库 http.server）。

本地启动后在浏览器打开：填章纲 → 生成正文 → 看事实库 → 保存本章
（正文落盘 + 事实落盘 + checkpoint）。模型走 `llm/factory.build_llm`：
配了云端模型且有 Key 则调云端，否则 Mock 离线可跑。
"""
from __future__ import annotations

import dataclasses
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from xingshu.auditor import LLMAuditor
from xingshu.config import NovelMeta
from xingshu.core.invariants import InvariantChecker
from xingshu.fact_base import FactBase
from xingshu.llm.base import LLMError
from xingshu.llm.factory import build_llm
from xingshu.llm.http import OpenAICompatibleLLM
from xingshu.outlines import ChapterOutline, Setting
from xingshu.pipeline.orchestrator import Orchestrator
from xingshu.storage import (
    create_checkpoint,
    default_facts_path,
    ensure_novel_structure,
    load_factbase,
    save_chapter,
    save_factbase,
)

_PAGE_CSS = """
:root{--bg:#111318;--panel:#1a1d24;--panel2:#20242e;--line:#2b3040;--txt:#e8e6e1;
--dim:#9aa3b2;--acc:#e0a458;--ok:#7fbf7f;--bad:#e0716b;--mono:"SFMono-Regular","Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:20px}
header{display:flex;align-items:center;gap:14px;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}
h1{font-size:20px;margin:0;letter-spacing:2px}h1 b{color:var(--acc)}.sub{color:var(--dim);font-size:12px}
.badge{margin-left:auto;font-size:12px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;color:var(--dim)}
.badge.on{border-color:var(--acc);color:var(--acc)}
.grid{display:grid;grid-template-columns:320px 1fr 280px;gap:16px}
@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;display:flex;flex-direction:column;min-height:70vh}
h2{font-size:13px;color:var(--acc);margin:0 0 10px;letter-spacing:1px;text-transform:uppercase}
label{display:block;font-size:12px;color:var(--dim);margin:10px 0 4px}
input,select,textarea{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);
border-radius:6px;padding:7px 9px;font:inherit}
textarea{resize:vertical;min-height:64px}
.row{display:flex;gap:8px}.row>*{flex:1}
button{cursor:pointer;border:none;border-radius:7px;font:inherit}
.primary{background:var(--acc);color:#1a1508;font-weight:600;padding:10px;margin-top:14px;letter-spacing:2px}
.ghost{background:transparent;border:1px solid var(--line);color:var(--dim);padding:6px 12px}
#body{flex:1;white-space:pre-wrap;line-height:1.9;font-family:var(--mono);font-size:14px;
background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:16px;margin-top:12px;
min-height:320px;color:#d8d6cf}
#body.placeholder{color:var(--dim)}
.audit{margin-top:12px;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13px}
.audit .line{display:flex;justify-content:space-between;align-items:center}
.audit .score{font-size:26px;font-weight:700;color:var(--acc)}
.audit .conclusion{font-size:12px;padding:3px 8px;border-radius:999px;border:1px solid var(--line)}
.conclusion.pass{color:var(--ok);border-color:var(--ok)}.conclusion.fail{color:var(--bad);border-color:var(--bad)}
.audit ul{margin:8px 0 0;padding-left:18px;color:var(--dim)}
.audit li.creative{color:#c9a5e8}
.facts{font-size:12px;color:var(--dim);overflow:auto}
.fact{border-top:1px solid var(--line);padding:8px 0}
.fact .head{color:var(--txt)}.fact .meta{color:var(--dim);font-size:11px}
.toast{position:fixed;right:18px;bottom:18px;background:#232838;border:1px solid var(--line);border-radius:8px;
padding:10px 16px;font-size:13px;opacity:0;transition:.25s;pointer-events:none}
.toast.show{opacity:1}
"""

_PAGE_BODY = """
<header><h1>星枢<b>写作台</b></h1><span class="sub" id="sub">-</span>
<span class="badge" id="model">模型: -</span>
<button class="ghost" onclick="loadFacts()">刷新事实库</button>
<button class="ghost" onclick="commit()">保存本章</button></header>
<div class="grid">
  <div class="panel"><h2>章纲</h2>
    <div class="row"><div><label>章号</label><input id="number" type="number" value="1"></div>
    <div><label>类型</label><select id="ctype">
      <option>常规</option><option>战斗</option><option>对话</option><option>探索</option>
      <option>日常</option><option>转折</option><option>文艺</option></select></div></div>
    <div><label>标题</label><input id="title" placeholder="本章标题"></div>
    <div><label>梗概</label><textarea id="summary" placeholder="本章一句话梗概"></textarea></div>
    <div><label>核心冲突</label><input id="conflict" placeholder="本章矛盾"></div>
    <div><label>叙事目标</label><input id="narrative_goal" placeholder="在整体叙事中达成什么"></div>
    <div class="row"><div><label>POV</label><input id="pov" placeholder="视角角色"></div>
    <div><label>氛围</label><input id="atmosphere" placeholder="压抑/紧张/温馨"></div></div>
    <div><label>前情摘要（每行一章）</label><textarea id="summaries" placeholder="第1章：林远入山门。\n第2章：……"></textarea></div>
    <div><label>明面设定（可注入，每行一条）</label><textarea id="settings" placeholder="明面规则：灵气分五行"></textarea></div>
    <button class="primary" onclick="writeChapter()">创作本章</button>
  </div>
  <div class="panel"><h2>正文</h2>
    <div id="body" class="placeholder">点「创作本章」开始。审读后点「保存本章」落盘。</div>
    <div class="audit" id="audit" style="display:none">
      <div class="line"><span class="score" id="score">-</span>
      <span class="conclusion" id="conclusion">-</span></div>
      <ul id="issues"></ul>
      <ul id="choices"></ul>
    </div>
  </div>
  <div class="panel"><h2>真相文件（active）</h2><div class="facts" id="facts">加载中…</div></div>
</div>
<div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);
const api={write:{method:'POST'},...{}};
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});return r.json()}
async function writeChapter(){
  const settings=($('settings').value||'').split('\\n').map(s=>s.trim()).filter(Boolean)
   .map((text,i)=>({sid:'PUB'+(i+1),is_public:true,text}));
  const summaries=($('summaries').value||'').split('\\n').map(s=>s.trim()).filter(Boolean);
  const data={number:+$('number').value||1,title:$('title').value,summary:$('summary').value,
   conflict:$('conflict').value,narrative_goal:$('narrative_goal').value,
   chapter_type:$('ctype').value,pov:$('pov').value,atmosphere:$('atmosphere').value,
   settings,summaries};
  const res=await post('/api/write',data);
  const body=$('body');body.classList.remove('placeholder');body.textContent=res.text||'(空)';
  renderAudit(res);toast('生成完成');
}
function renderAudit(res){
  const a=$('audit');
  if(res.violations&&res.violations.length){a.style.display='block';
    $('score').textContent='×';$('conclusion').textContent='阻断';
    $('conclusion').className='conclusion fail';
    $('issues').innerHTML=res.violations.map(v=>'<li>'+v.invariant+' '+v.message+'</li>').join('');
    $('choices').innerHTML='';return}
  const au=res.audit;
  if(!au){a.style.display='none';return}
  a.style.display='block';$('score').textContent=au.score;
  $('conclusion').textContent=au.conclusion;
  $('conclusion').className='conclusion '+(au.conclusion==='通过'?'pass':'fail');
  $('issues').innerHTML=(au.issues||[]).map(i=>'<li>'+i+'</li>').join('')||'<li>无</li>';
  $('choices').innerHTML=(au.creative_choices||[]).map(c=>'<li class="creative">创作选择：'+c+'</li>').join('');
}
async function commit(){
  const number=+$('number').value||1;
  const res=await post('/api/commit',{number,text:$('body').textContent||'',summary:$('summary').value});
  toast('已保存：'+res.body);loadFacts();
}
async function loadFacts(){
  const r=await fetch('/api/facts');const d=await r.json();
  $('facts').innerHTML=d.facts.length?d.facts.map(f=>
    '<div class="fact"><div class="head">'+f.entity+' · '+f.attribute+'='+f.value+'</div>'+
    '<div class="meta">'+f.system+' ｜ 来源《'+f.source+'》</div></div>').join(''):'（暂无事实）';
}
let t;function toast(m){const e=$('toast');e.textContent=m;e.classList.add('show');
  clearTimeout(t);t=setTimeout(()=>e.classList.remove('show'),1600)}
loadFacts();
</script>
"""

PAGE = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星枢写作台</title><style>{_PAGE_CSS}</style></head>
<body><div class="wrap">{_PAGE_BODY}</div></body></html>"""


class EngineServer:
    """写作台引擎：持有 novel 会话，提供 生成/事实/保存 三类操作。"""

    def __init__(self, *, novel_dir: str | Path, meta: NovelMeta) -> None:
        self.novel_dir = Path(novel_dir)
        self.meta = meta
        ensure_novel_structure(self.novel_dir)
        facts_path = default_facts_path(self.novel_dir)
        self.facts = load_factbase(self.novel_dir) if facts_path.exists() else FactBase()
        self.llm = build_llm(meta)
        self.orch = Orchestrator(
            llm=self.llm, facts=self.facts,
            checker=InvariantChecker(), meta=meta,
        )

    # ---- API ----

    def api_write(self, data: dict) -> dict:
        chapter = ChapterOutline(
            number=int(data.get("number", self.meta.current_chapter + 1)),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            roles=tuple(data.get("roles") or ()),
            atmosphere=str(data.get("atmosphere", "")),
            conflict=str(data.get("conflict", "")),
            narrative_goal=str(data.get("narrative_goal", "")),
            chapter_type=str(data.get("chapter_type", "常规")),
            pov=str(data.get("pov", "")),
        )
        settings = [
            Setting(sid=str(s["sid"]), is_public=bool(s.get("is_public", False)),
                    text=str(s.get("text", "")),
                    reveal_density_required=float(s.get("reveal_density_required", 1.0)))
            for s in (data.get("settings") or [])
        ]
        summaries = [str(s) for s in (data.get("summaries") or [])]
        result = self.orch.write_chapter(
            chapter.number, known=set(), revealed=set(),
            chapter=chapter, summaries=summaries, settings=settings,
        )
        audit = None
        if isinstance(self.llm, OpenAICompatibleLLM):  # 云端模式下走 07 §8 独立复核
            try:
                audit_llm = OpenAICompatibleLLM.from_meta(self.meta, audit=True)
                report = LLMAuditor(audit_llm).evaluate(
                    result.text, chapter_type=chapter.chapter_type,
                    blocker_count=len(result.violations), facts=self.facts.recall(),
                )
                audit = {"score": report.score, "conclusion": report.conclusion,
                         "issues": report.issues, "creative_choices": report.creative_choices}
            except (ValueError, LLMError):
                audit = None
        return {
            "accepted": result.accepted,
            "text": result.text,
            "order": result.order,
            "violations": [{"invariant": v.invariant, "message": v.message}
                           for v in result.violations],
            "audit": audit,
        }

    def api_facts(self) -> dict:
        return {"facts": [dataclasses.asdict(f) for f in self.facts.recall()]}

    def api_commit(self, data: dict) -> dict:
        number = int(data["number"])
        text = str(data["text"])
        summary = str(data.get("summary", ""))
        body = save_chapter(self.novel_dir, number, text, summary=summary or None)
        facts_path = save_factbase(self.facts, self.novel_dir)
        checkpoint = create_checkpoint(self.novel_dir)
        return {"body": str(body), "facts": str(facts_path), "checkpoint": str(checkpoint)}


class NovelHandler(BaseHTTPRequestHandler):
    """路由：GET / 与 /api/facts；POST /api/write 与 /api/commit。"""

    engine: EngineServer

    def _engine(self) -> EngineServer:
        return self.server.engine

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("", "/"):
            self._send(200, PAGE, "text/html; charset=utf-8")
            return
        if self.path == "/api/facts":
            self._send(200, json.dumps(self._engine().api_facts(), ensure_ascii=False))
            return
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:  # noqa: N802
        try:
            size = int(self.headers.get("Content-Length", 0) or 0)
            data = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "bad json"}))
            return
        engine = self._engine()
        if self.path == "/api/write":
            self._send(200, json.dumps(engine.api_write(data), ensure_ascii=False))
            return
        if self.path == "/api/commit":
            self._send(200, json.dumps(engine.api_commit(data), ensure_ascii=False))
            return
        self._send(404, json.dumps({"error": "not found"}))

    def _send(self, code: int, payload: str, ctype: str = "application/json") -> None:
        body = payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # 静默，避免测试噪音
        pass


def run_server(novel_dir: str | Path, meta: NovelMeta, *, port: int = 8899) -> ThreadingHTTPServer:
    """启动写作台（阻塞）。浏览器打开 http://127.0.0.1:{port}。"""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), NovelHandler)
    httpd.engine = EngineServer(novel_dir=novel_dir, meta=meta)
    print(f"星枢写作台已启动: http://127.0.0.1:{port}")
    httpd.serve_forever()
    return httpd