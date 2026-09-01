"""浏览器写作台服务（零第三依赖，标准库 http.server）。

本地启动后在浏览器打开：填章纲 → 生成正文 → 看事实库 → 保存本章
（正文落盘 + 事实落盘 + checkpoint）。模型走 `llm/factory.build_llm`：
配了云端模型且有 Key 则调云端，否则 Mock 离线可跑。

前端为「白纸星尘」单屏工作台：纯白纸基 + 自研 3D 粉彩粒子画布（种子随机、
可交互），章纲 / 正文 / 真相文件 三栏同屏，无需上下滚动；按视口宽度呈现
三栏、右侧抽屉、单栏页签三套布局。
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
:root{
  --paper:#f7f5f0;--card:#ffffff;--card2:#fdfcf9;
  --line:#e9e2d6;--line-hi:#dacfbe;--ink:#2c2731;--dim:#8b8492;--faint:#bcb5c1;
  --pink:#f5c0cf;--lilac:#d3c4f2;--mint:#bfe9d3;--peach:#ffd5b3;--sky:#c2e0f7;--butter:#f8e6a6;
  --acc:#e67f9d;--acc-hi:#f59bb5;--acc-ink:#7c2538;
  --ok:#5fa97c;--bad:#d96a63;--violet:#9f7fc8;
  --serif:"Noto Serif SC","Songti SC","STSong","SimSun",serif;
  --sans:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"SFMono-Regular","Cascadia Mono",Consolas,monospace;
  --r:14px;--r-sm:9px;
  --shadow:0 18px 48px rgba(120,106,138,.16);
  --shadow-s:0 6px 20px rgba(120,106,138,.10);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--paper);color:var(--ink);
  font:14px/1.6 var(--sans);overflow:hidden;position:relative}
::selection{background:rgba(230,127,157,.25)}
/* ---------- 3D 粉彩粒子画布（白纸之上的一层星尘） ---------- */
#dust{position:fixed;inset:0;pointer-events:none;z-index:0}
/* ---------- 单屏应用骨架 ---------- */
.app{position:relative;z-index:1;height:100dvh;display:flex;flex-direction:column;
  background:linear-gradient(180deg,rgba(247,245,240,.72),rgba(247,245,240,.55) 60%,rgba(247,245,240,.88))}
/* ---------- 顶栏 ---------- */
.top{flex:none;display:flex;align-items:center;gap:14px;padding:10px 18px;
  background:rgba(255,255,255,.62);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--line)}
.logo{width:40px;height:40px;flex:none;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--pink),var(--lilac) 55%,var(--sky));
  box-shadow:var(--shadow-s);position:relative}
.logo b{font:700 19px/1 var(--serif);color:#fff;text-shadow:0 1px 6px rgba(124,37,56,.35)}
.titles h1{font:600 19px/1.1 var(--serif);letter-spacing:3px;color:var(--ink)}
.titles h1 em{font-style:normal;background:linear-gradient(90deg,var(--acc),var(--violet));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.titles .sub{display:flex;gap:8px;align-items:center;margin-top:2px;font-size:11.5px;color:var(--dim)}
.titles .sub b{color:var(--acc-ink);font-weight:600}
.top-right{margin-left:auto;display:flex;align-items:center;gap:8px;flex:none}
.badge{font-size:11.5px;padding:5px 12px;border:1px solid var(--line-hi);border-radius:999px;color:var(--dim);
  display:inline-flex;align-items:center;gap:6px;white-space:nowrap;background:#fff}
.badge::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--faint)}
.badge.cloud{color:var(--acc-ink);border-color:rgba(230,127,157,.4)}
.badge.cloud::before{background:var(--ok);box-shadow:0 0 8px var(--ok)}
/* ---------- 步进条（极细，节省纵向空间） ---------- */
.steps{flex:none;display:flex;gap:0;margin:10px 18px 0;padding:8px 10px;
  border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.66);
  backdrop-filter:blur(8px)}
.step{flex:1;display:flex;align-items:center;gap:9px;position:relative;color:var(--faint);
  font-size:12px;letter-spacing:.5px}
.step:not(:last-child)::after{content:"";position:absolute;top:14px;left:calc(30px + 9px);right:calc(30px + 9px);
  height:2px;background:var(--line);border-radius:2px}
.step .num{width:28px;height:28px;flex:none;border-radius:50%;display:grid;place-items:center;
  background:#fff;border:1.5px solid var(--line-hi);color:var(--dim);
  font:600 13px var(--serif);transition:.25s}
.step .label{line-height:1.15}.step .label small{display:block;font-size:10.5px;color:var(--faint)}
.step.on{color:var(--ink)}
.step.on .num{background:linear-gradient(135deg,var(--acc-hi),var(--acc));border-color:transparent;color:#fff;
  box-shadow:0 0 14px rgba(230,127,157,.5)}
.step.on:not(:last-child)::after{background:linear-gradient(90deg,var(--acc),var(--line))}
.step.done{color:var(--ink)}
.step.done .num{background:var(--mint);border-color:transparent;color:#2c6b4f}
.step.done:not(:last-child)::after{background:var(--mint)}
/* ---------- 工作区（三栏，占满剩余高度，不滚动） ---------- */
.work{flex:1;min-height:0;display:grid;gap:12px;padding:12px 18px;
  grid-template-columns:minmax(292px,336px) minmax(0,1fr) minmax(272px,312px)}
.col{min-width:0;display:flex;flex-direction:column;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow-s);
  overflow:hidden}
.col-head{flex:none;display:flex;align-items:baseline;gap:8px;padding:13px 16px 10px}
.col-head h2{font:600 13px/1 var(--serif);letter-spacing:3px;color:var(--ink)}
.col-head h2::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;
  margin-right:8px;vertical-align:1px}
.col-form .col-head h2::before{background:var(--pink)}
.col-main .col-head h2::before{background:var(--sky)}
.col-facts .col-head h2::before{background:var(--mint)}
.col-head .cnt{margin-left:auto;font-size:11px;color:var(--faint)}
.col-body{flex:1;min-height:0;overflow-y:auto;padding:0 16px 16px;scrollbar-width:thin;
  scrollbar-color:var(--line-hi) transparent}
.col-body::-webkit-scrollbar{width:8px}
.col-body::-webkit-scrollbar-thumb{background:var(--line-hi);border-radius:4px}
/* ---------- 章纲表单 ---------- */
label{display:block;font-size:11.5px;color:var(--dim);margin:10px 0 4px;letter-spacing:.4px}
label b{color:var(--ink);font-weight:600}
label .opt{color:var(--faint);font-weight:400;font-size:10.5px;margin-left:6px}
input,select,textarea{width:100%;background:var(--card2);border:1px solid var(--line);color:var(--ink);
  border-radius:var(--r-sm);padding:7px 9px;font:13px/1.5 var(--sans);
  transition:border .18s, box-shadow .18s}
input:focus,select:focus,textarea:focus{outline:none;border-color:rgba(230,127,157,.6);
  box-shadow:0 0 0 3px rgba(230,127,157,.14);background:#fff}
textarea{resize:vertical;min-height:52px}
.row{display:flex;gap:8px}.row>*{flex:1;min-width:0}
#summaries,#settings{font-family:var(--mono);font-size:11.5px}
details.adv{margin-top:10px;border-top:1px dashed var(--line-hi);padding-top:2px}
details.adv summary{cursor:pointer;font-size:11.5px;color:var(--dim);letter-spacing:1px;
  list-style:none;user-select:none;padding:8px 0;transition:color .15s}
details.adv summary::before{content:"▸ ";color:var(--acc)}
details.adv[open] summary::before{content:"▾ "}
details.adv summary:hover{color:var(--acc-ink)}
.envelope{flex:none;padding:2px 16px 16px}
/* ---------- 按钮 ---------- */
.ghost{background:#fff;border:1px solid var(--line-hi);color:var(--dim);padding:6px 13px;
  border-radius:999px;cursor:pointer;font:12.5px var(--sans);transition:.2s;white-space:nowrap}
.ghost:hover{color:var(--ink);border-color:var(--faint);transform:translateY(-1px)}
.primary{width:100%;cursor:pointer;border:none;border-radius:11px;font:600 14px/1 var(--sans);
  color:#fff;background:linear-gradient(135deg,var(--acc-hi),var(--acc) 60%,var(--acc));
  padding:12px;margin-top:14px;letter-spacing:5px;text-indent:5px;transition:.22s;
  box-shadow:0 6px 20px rgba(230,127,157,.38);position:relative;overflow:hidden}
.primary:hover{transform:translateY(-1px);box-shadow:0 9px 28px rgba(230,127,157,.5)}
.primary:active{transform:translateY(0)}
.primary:disabled{opacity:.55;cursor:wait;transform:none}
.primary:disabled::after{content:"";position:absolute;inset:0;
  background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.5) 50%,transparent 70%);
  animation:shine 1.2s infinite}
@keyframes shine{to{transform:translateX(100%)}}
.save-btn{width:auto;margin:0;padding:9px 16px;font-size:12.5px;letter-spacing:1px;text-indent:0;
  background:linear-gradient(135deg,#7fc39b,#61a87c);box-shadow:0 6px 16px rgba(95,169,124,.35)}
.save-btn:hover{box-shadow:0 9px 24px rgba(95,169,124,.45)}
.save-btn:disabled{opacity:.5;cursor:wait}
/* ---------- 正文 ---------- */
#body{flex:1;min-height:0;overflow-y:auto;white-space:pre-wrap;line-height:2;font-family:var(--serif);
  font-size:15px;background:linear-gradient(180deg,#fffdf9,#fffefb);border:1px solid var(--line);
  border-radius:11px;padding:18px 20px;color:#3a3340;outline:none;transition:border .2s, box-shadow .2s;
  letter-spacing:.01em;scrollbar-width:thin;scrollbar-color:var(--line-hi) transparent}
#body:focus{border-color:rgba(230,127,157,.45);box-shadow:0 0 0 3px rgba(230,127,157,.12)}
#body .ph{color:var(--faint);font-family:var(--sans);font-size:12.5px;letter-spacing:.6px;
  text-align:center;padding:26px 8px;line-height:1.9}
#body .ph em{display:block;font-family:var(--serif);font-size:19px;color:var(--acc);
  font-style:normal;letter-spacing:5px;margin-bottom:8px}
/* ---------- 审计 ---------- */
.audit{margin-top:12px;border:1px solid var(--line);border-radius:11px;padding:12px;
  background:var(--card2);display:none}
.audit.show{display:block;animation:rise .3s ease}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.audit-top{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.score-ring{--p:50;--col:var(--faint);width:52px;height:52px;flex:none;border-radius:50%;
  background:conic-gradient(var(--col) calc(var(--p)*1%),rgba(0,0,0,.06) 0);
  display:grid;place-items:center;position:relative}
.score-ring::before{content:"";position:absolute;inset:5px;border-radius:50%;background:var(--card2)}
.score-ring b{position:relative;font:700 14px var(--mono)}
.audit-title{font:600 13.5px var(--serif);color:var(--ink)}
.audit-title .verdict{display:inline-block;margin-left:8px;font:500 11px var(--sans);padding:2px 9px;
  border-radius:999px;border:1px solid var(--line)}
.verdict.pass{color:var(--ok);border-color:rgba(95,169,124,.5);background:rgba(191,233,211,.3)}
.verdict.fail{color:var(--bad);border-color:rgba(217,106,99,.5);background:rgba(245,192,207,.25)}
.audit-top .meta{margin-left:auto;font-size:10.5px;color:var(--faint);text-align:right;line-height:1.5}
.audit ul{list-style:none;margin-top:4px}
.audit li{font-size:12px;color:var(--dim);padding:3px 0 3px 15px;position:relative;line-height:1.55}
.audit li::before{content:"·";position:absolute;left:3px;color:var(--acc)}
.audit li.creative{color:var(--violet)}
/* ---------- 事实库 ---------- */
.facts{font-size:12px}
.facts .empty-note{color:var(--faint);text-align:center;padding:26px 0;line-height:1.9;
  border:1.5px dashed var(--line-hi);border-radius:10px;font-size:11.5px}
.fact{border-bottom:1px solid rgba(233,226,214,.7);padding:9px 2px;animation:rise .3s ease}
.fact:last-child{border-bottom:none}
.fact .head{color:var(--ink);word-break:break-all;margin-bottom:3px;font-size:12.5px}
.fact .head b{color:var(--acc-ink);font-weight:600}
.fact .meta{color:var(--faint);font-size:10.5px}
.fact .meta .sys{display:inline-block;font-size:9.5px;padding:1px 7px;border-radius:999px;
  border:1px solid var(--line-hi);color:var(--dim);margin-right:6px;background:#fff}
/* ---------- 状态栏 ---------- */
.status{flex:none;display:flex;align-items:center;gap:14px;padding:8px 20px;
  background:rgba(255,255,255,.62);backdrop-filter:blur(12px);border-top:1px solid var(--line);
  font-size:11.5px;color:var(--faint)}
.status kbd{font:10px var(--mono);padding:1px 5px;border:1px solid var(--line-hi);border-radius:5px;
  background:#fff;color:var(--dim);margin:0 2px}
.status .right{margin-left:auto;display:flex;gap:12px;align-items:center}
.status .dot{width:7px;height:7px;border-radius:50%;background:var(--mint);box-shadow:0 0 8px var(--mint)}
/* ---------- 移动端页签（≤880px 显示） ---------- */
.tabs{display:none}
.toast{position:fixed;top:22px;right:22px;z-index:99;background:#fff;border:1px solid var(--line-hi);
  color:var(--ink);border-radius:11px;padding:11px 16px;font-size:12.5px;box-shadow:var(--shadow);
  opacity:0;transform:translateY(-8px);transition:.25s;pointer-events:none;max-width:340px}
.toast.show{opacity:1;transform:none}
.toast.err{border-color:rgba(217,106,99,.45)}
/* ---------- 响应式：三种比例呈现 ---------- */
.mini,.fab{display:none}
@media(max-width:1180px){ /* 中屏：两栏 + 事实库右抽屉 */
  .work{grid-template-columns:minmax(280px,320px) minmax(0,1fr)}
  .col-facts{position:fixed;top:0;right:0;bottom:0;width:min(320px,84vw);z-index:30;
    border-radius:16px 0 0 16px;transform:translateX(103%);transition:.28s;box-shadow:var(--shadow)}
  .col-facts.open{transform:none}
  .fab{display:inline-flex}
}
@media(max-width:880px){ /* 窄屏：单栏 + 顶部页签 + 底部快捷操作 */
  .work{display:block;padding:10px 12px}
  .col{display:none;height:100%}
  .col.active{display:flex}
  .tabs{flex:none;display:flex;gap:6px;margin:10px 12px 0;padding:5px;
    background:rgba(255,255,255,.7);border:1px solid var(--line);border-radius:12px}
  .tabs button{flex:1;border:none;background:transparent;padding:7px;border-radius:9px;cursor:pointer;
    font:12.5px var(--sans);color:var(--dim);transition:.2s}
  .tabs button.on{background:#fff;color:var(--acc-ink);box-shadow:var(--shadow-s)}
  .mini{flex:none;display:flex;gap:8px;margin:0 12px 10px}
  .mini .primary{margin:0}
  .mini .save-btn{background:linear-gradient(135deg,#7fc39b,#61a87c);width:auto;font-size:12.5px}
  .logo{width:36px;height:36px}.titles h1{font-size:17px}
  .ghost.jr{display:none}
  .fab{display:none}
}
@media(max-width:480px){
  .top{padding:8px 12px;gap:10px}.titles .sub{display:none}
  .badge{font-size:10.5px;padding:4px 9px}
  .status{display:none}
}
@media (prefers-reduced-motion: reduce){
  #dust{display:none}
  *{transition:none!important;animation:none!important}
}
"""

_PAGE_BODY = """
<canvas id="dust"></canvas>
<div class="app">
  <header class="top">
    <div class="logo"><b>枢</b></div>
    <div class="titles">
      <h1>星枢<em>写作台</em></h1>
      <div class="sub"><b id="novelTitle">…</b><span id="genres">-</span></div>
    </div>
    <div class="top-right">
      <span class="badge" id="model"></span>
      <button class="ghost jr" onclick="loadFacts()">刷新事实库</button>
      <button class="ghost fab" onclick="flickFacts()" id="factsToggle">真相文件</button>
      <button class="primary save-btn" onclick="commit()" id="saveBtn">保存本章</button>
    </div>
  </header>
  <nav class="steps" id="steps">
    <div class="step on" data-step="1"><span class="num">1</span><span class="label">填章纲<small>定局面</small></span></div>
    <div class="step" data-step="2"><span class="num">2</span><span class="label">生成正文<small>起笔</small></span></div>
    <div class="step" data-step="3"><span class="num">3</span><span class="label">审读校验<small>过审</small></span></div>
    <div class="step" data-step="4"><span class="num">4</span><span class="label">保存落盘<small>生成检查点</small></span></div>
  </nav>
  <nav class="tabs" id="tabs">
    <button class="on" data-tab="form" onclick="tab('form')">章纲</button>
    <button data-tab="main" onclick="tab('main')">正文</button>
    <button data-tab="facts" onclick="tab('facts')">真相文件</button>
  </nav>
  <main class="work">
    <section class="col col-form active" id="pane-form">
      <div class="col-head"><h2>章纲</h2><span class="cnt">必填：梗概</span></div>
      <div class="col-body">
        <div class="row"><div><label><b>章号</b></label><input id="number" type="number" value="1" min="1"></div>
        <div><label><b>类型</b></label><select id="ctype">
          <option>常规</option><option>战斗</option><option>对话</option><option>探索</option>
          <option>日常</option><option>转折</option><option>文艺</option></select></div></div>
        <label><b>标题</b><span class="opt">可选</span></label><input id="title" placeholder="本章标题">
        <label><b>梗概</b></label><textarea id="summary" placeholder="本章发生了什么（一句话）"></textarea>
        <label><b>核心冲突</b><span class="opt">可选</span></label><input id="conflict" placeholder="例如：借剑被拒">
        <label><b>叙事目标</b><span class="opt">可选</span></label><input id="narrative_goal" placeholder="例如：立主角人设">
        <div class="row"><div><label><b>视角 POV</b></label><input id="pov" placeholder="视角角色"></div>
        <div><label><b>氛围</b></label><input id="atmosphere" placeholder="压抑 / 温暖"></div></div>
        <details class="adv">
          <summary>高级上下文（可选，注入灵感）</summary>
          <label><b>前情摘要</b><span class="opt">每行一章</span></label>
          <textarea id="summaries" placeholder="第1章：林远入山门，初遇周宁。"></textarea>
          <label><b>明面设定</b><span class="opt">每行一条，可揭示</span></label>
          <textarea id="settings" placeholder="明面规则：灵气分五行"></textarea>
        </details>
      </div>
      <div class="envelope"><button class="primary" onclick="writeChapter()" id="writeBtn">创作本章</button></div>
    </section>
    <section class="col col-main" id="pane-main">
      <div class="col-head"><h2>正文</h2><span class="cnt">生成后可编辑润色</span></div>
      <div class="col-body">
        <div id="body" contenteditable="true" spellcheck="false"><div class="ph"><em>起 笔</em>在左侧填好章纲，点击「创作本章」开始生成。<br>正文将在此处展开，审读通过后点右上「保存本章」落盘。</div></div>
        <div class="audit" id="audit">
          <div class="audit-top">
            <div class="score-ring" id="ring"><b id="score">-</b></div>
            <div>
              <div class="audit-title">审计结论 <span class="verdict" id="conclusion">-</span></div>
              <ul id="issues"></ul>
            </div>
            <div class="meta">LLM 独立复核<br>七维评分</div>
          </div>
          <ul id="choices"></ul>
        </div>
      </div>
    </section>
    <section class="col col-facts" id="pane-facts">
      <div class="col-head"><h2>真相文件</h2><span class="cnt" id="factCnt">0</span></div>
      <div class="col-body"><div class="facts" id="facts"><div class="empty-note">暂无事实，生成全文后将自动沉淀设定。</div></div></div>
    </section>
  </main>
  <div class="mini">
    <button class="primary" onclick="writeChapter()">创作本章</button>
    <button class="primary save-btn" onclick="commit()">保存本章</button>
  </div>
  <footer class="status">
    <span class="dot"></span><span id="engineState">引擎就绪</span>
    <span class="right">快捷键 <kbd>Ctrl</kbd>+<kbd>Enter</kbd> 创作本章　<kbd>Ctrl</kbd>+<kbd>S</kbd> 保存落盘</span>
  </footer>
</div>
<div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);
const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
const ct=$('dust');
/* ===== 3D 粉彩粒子：种子随机 + 缓慢自转 + 鼠标排斥（白纸星尘） ===== */
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const PALETTE=[['#f5c0cf','#f399b6'],['#d3c4f2','#b79de6'],['#bfe9d3','#8fd9b4'],
               ['#ffd5b3','#ffb483'],['#c2e0f7','#93c8f0'],['#f8e6a6','#f2d56a']];
const sprites=PALETTE.map(c=>{const s=document.createElement('canvas');s.width=s.height=96;
  const g=s.getContext('2d'),rg=g.createRadialGradient(48,48,2,48,48,46);
  rg.addColorStop(0,c[0]);rg.addColorStop(.5,c[1]);rg.addColorStop(1,'rgba(255,255,255,0)');
  g.fillStyle=rg;g.fillRect(0,0,96,96);return s});
const rnd=mulberry32(20240901);
let parts=[],W=0,H=0,DPR=1,mx=innerWidth/2,my=innerHeight/2;
const SIZE=()=>Math.round(Math.min(130,Math.max(46,innerWidth*innerHeight/8800)));
function resetDust(){
  DPR=Math.min(devicePixelRatio||2,2);W=innerWidth;H=innerHeight;
  ct.width=W*DPR;ct.height=H*DPR;ct.style.width=W+'px';ct.style.height=H+'px';
  ctx.setTransform(DPR,0,0,DPR,0,0);
  parts=[];const n=SIZE();
  for(let i=0;i<n;i++){
    // 粒子位于归一化单位球（半径 0.12~1.0），投影后恰好铺满视口
    const rr=0.12+Math.pow(rnd(),1.6)*0.88, th=rnd()*6.283, ph=Math.acos(2*rnd()-1),
      ci=(rnd()*PALETTE.length)|0;
    parts.push({x:Math.sin(ph)*Math.cos(th)*rr,y:Math.sin(ph)*Math.sin(th)*rr,z:Math.cos(ph)*rr,
      sprite:sprites[ci],size:9+rnd()*30,phase:rnd()*6.283,sp:.5+rnd()*1.1,tw:rnd()*1.6});
  }
}
function dustFrame(){
  const g=ctx||(ctx=ct.getContext('2d'));g.clearRect(0,0,W,H);
  const a=t*0.00016,b=t*0.00010,ca=Math.cos(a),sa=Math.sin(a),cb=Math.cos(b),sb=Math.sin(b);
  const cx=W/2,cy=H/2,R=Math.max(W,H)*0.62,persp=2.6;
  parts.forEach(p=>{
    const x1=p.x*ca+p.z*sa,z1=-p.x*sa+p.z*ca;
    const y1=p.y*cb-z1*sb,z2=p.y*sb+z1*cb;
    const scale=persp/(persp+z2);
    const sx=cx+x1*scale*R, sy=cy+y1*scale*R;
    const dx=sx-mx,dy=sy-my,d2=dx*dx+dy*dy;
    let ox=0,oy=0;
    if(d2<22500){const d=Math.sqrt(d2)||1,k=(150-d)/150;ox=dx/d*k*38;oy=dy/d*k*38;}
    const tw=0.5+0.5*Math.sin(t*p.sp+p.phase);
    const dep=Math.max(0.25,Math.min(1,(z2+persp)/3.6));
    const sz=(p.size*scale+4);
    if(sx+ox<-140||sx+ox>W+140||sy+oy<-140||sy+oy>H+140)return;
    g.globalAlpha=dep*tw*0.48;g.drawImage(p.sprite,sx+ox-sz/2,sy+oy-sz/2,sz,sz);
  });
  g.globalAlpha=1;
}
let t=0,ctx=ct.getContext('2d');
function loop(tms){t=tms*0.001;dustFrame();ray=requestAnimationFrame(loop);}
let ray=null;
function startDust(){
  resetDust();
  if(reduced){dustFrame();return;}
  if(ray)cancelAnimationFrame(ray);ray=requestAnimationFrame(loop);
}
addEventListener('pointermove',e=>{mx=e.clientX;my=e.clientY});
addEventListener('resize',()=>{if(reduced)dustFrame();else{resetDust();}});
/* ===== 单屏页签 / 右抽屉 ===== */
function tab(n){
  document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===n));
  ['form','main','facts'].forEach(k=>{$('pane-'+k).classList.toggle('active',k===n)});
  $('pane-facts').classList.remove('open');
}
function flickFacts(){$('pane-facts').classList.toggle('open')}
function setStep(n){document.querySelectorAll('#steps .step').forEach(s=>{
  const i=+s.dataset.step;
  s.classList.toggle('on',i===n);s.classList.toggle('done',i<n);
});}
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});return r.json()}
function loading(on){
  const btn=$('writeBtn');const body=$('body');
  if(on){btn.disabled=true;btn.textContent='生成中…';
    body.childNodes.forEach(n=>n.nodeType===1&&n.classList&&body.removeChild(n));
    const d=document.createElement('div');d.className='ph';d.id='progress';
    d.innerHTML='<em>构 思 中</em>· 拟定骨架 → 展开叙事 → 复核设定 ……';body.appendChild(d);
    setStep(2);}else{btn.disabled=false;btn.textContent='创作本章';
    const p=document.getElementById('progress');if(p)p.remove();}
}
async function writeChapter(){
  const settings=($('settings').value||'').split('\\n').map(s=>s.trim()).filter(Boolean)
   .map((text,i)=>({sid:'PUB'+(i+1),is_public:true,text}));
  const summaries=($('summaries').value||'').split('\\n').map(s=>s.trim()).filter(Boolean);
  const data={number:+$('number').value||1,title:$('title').value,summary:$('summary').value,
   conflict:$('conflict').value,narrative_goal:$('narrative_goal').value,
   chapter_type:$('ctype').value,pov:$('pov').value,atmosphere:$('atmosphere').value,
   settings,summaries};
  loading(true);
  try{
    const res=await post('/api/write',data);
    loading(false);
    const body=$('body');
    if(innerWidth<=880)tab('main');
    if(res.violations&&res.violations.length){
      body.textContent=res.text||'(被阻断，未生成正文)';
      renderViolations(res);return;
    }
    setStep(res.audit?3:2);
    if(res.text!==undefined&&res.text){body.textContent=res.text;}else{body.textContent='（未生成内容）';}
    renderAudit(res);toast('生成完成 — 审读结果见下方');
  }catch(e){loading(false);toast('生成失败：'+e.message,'err');}
}
function renderViolations(res){
  const a=$('audit');a.classList.add('show');
  const ring=$('ring');ring.style.setProperty('--p','0');ring.style.setProperty('--col','var(--bad)');
  $('score').textContent='×';
  $('conclusion').textContent='叙事不变量阻断';
  $('conclusion').className='verdict fail';
  $('issues').innerHTML=res.violations.map(v=>'<li><b>'+v.invariant+'</b> '+v.message+'</li>').join('');
  $('choices').innerHTML='';
  setStep(3);
}
function renderAudit(res){
  const a=$('audit');
  if(!res.audit){a.classList.remove('show');return;}
  a.classList.add('show');
  const au=res.audit;const p=Math.max(0,Math.min(100,au.score));
  const ring=$('ring');ring.style.setProperty('--p',p);
  ring.style.setProperty('--col',p>=75?'var(--ok)':p>=55?'var(--acc)':'var(--bad)');
  $('score').textContent=au.score;
  $('conclusion').textContent=au.conclusion==='通过'?'通过 ✓':'待修订';
  $('conclusion').className='verdict '+(au.conclusion==='通过'?'pass':'fail');
  $('issues').innerHTML=(au.issues||[]).map(i=>'<li>'+i+'</li>').join('')||'<li>未发现明显问题。</li>';
  $('choices').innerHTML=(au.creative_choices||[]).map(c=>'<ul><li class="creative">创作选择：'+c+'</li></ul>').join('');
}
async function commit(){
  const number=+$('number').value||1;
  const txt=$('body').innerText||$('body').textContent||'';
  if(!txt.trim()||$('body').querySelector('.ph')){toast('没有可保存的正文','err');return;}
  const btn=$('saveBtn');btn.disabled=true;
  try{
    const res=await post('/api/commit',{number,text:txt,summary:$('summary').value});
    toast('已保存 '+res.body.split('/').pop());setStep(4);loadFacts();$('engineState').textContent='已生成检查点';
  }catch(e){toast('保存失败：'+e.message,'err');}
  finally{btn.disabled=false;}
}
async function loadFacts(){
  const r=await fetch('/api/facts');const d=await r.json();
  $('factCnt').textContent=d.facts.length+' 条';
  $('facts').innerHTML=d.facts.length?
    d.facts.slice().reverse().map(f=>
      '<div class="fact"><div class="head"><b>'+f.entity+'</b> · '+f.attribute+' = '+f.value+'</div>'+
      '<div class="meta"><span class="sys">'+f.system+'</span>来源《'+f.source+'》'+
      (f.status==='superseded'?' · 已被更替':'')+'</div></div>').join('')
    :'<div class="empty-note">暂无事実，生成正文后将自动沉淀设定。</div>';
}
async function boot(){
  const d=await (await fetch('/api/meta')).json();
  $('novelTitle').textContent='《'+d.title+'》';
  $('genres').textContent='· '+d.genre+' · 第 '+(d.current_chapter+1)+'/'+d.total_chapters+' 章';
  document.title=('星枢写作台 · '+d.title);
  const m=$('model');
  if(d.cloud){m.className='badge cloud';m.textContent='云端 · '+d.model;}
  else{m.className='badge';m.textContent='离线模式 · '+d.model;}
}
let ttime;function toast(m,kind){const e=$('toast');e.textContent=m;e.className='toast show'+(kind?' err':'');
  clearTimeout(ttime);ttime=setTimeout(()=>e.classList.remove('show'),2600)}
document.addEventListener('keydown',e=>{
  if(e.target.isContentEditable&&e.key==='Enter')return;
  if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();writeChapter();}
  if(e.key.toLowerCase()==='s'&&(e.ctrlKey||e.metaKey)){e.preventDefault();commit();}
});
boot();loadFacts();startDust();
</script>
"""

PAGE = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星枢写作台</title><style>{_PAGE_CSS}</style></head>
<body>{_PAGE_BODY}</body></html>"""


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

    def api_meta(self) -> dict:
        """界面顶部展示的小说与模型信息（一眼上手：当前写哪本书、什么模型）。"""
        return {
            "novel_id": self.meta.novel_id,
            "title": self.meta.title,
            "genre": self.meta.genre,
            "language": self.meta.language,
            "current_chapter": self.meta.current_chapter,
            "total_chapters": self.meta.total_chapters,
            "cloud": isinstance(self.llm, OpenAICompatibleLLM),
            "model": self.meta.model
            if isinstance(self.llm, OpenAICompatibleLLM)
            else "mock（离线）",
        }

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
        if self.path == "/api/meta":
            self._send(200, json.dumps(self._engine().api_meta(), ensure_ascii=False))
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


def create_server(
    novel_dir: str | Path,
    meta: NovelMeta,
    *,
    host: str = "127.0.0.1",
    port: int = 8899,
) -> ThreadingHTTPServer:
    """创建写作台服务器（不阻塞，serve_forever 由调用方决定）。"""
    httpd = ThreadingHTTPServer((host, port), NovelHandler)
    httpd.engine = EngineServer(novel_dir=novel_dir, meta=meta)
    return httpd


def serve_url(httpd: ThreadingHTTPServer) -> str:
    """httpd 可直接由浏览器打开的本机地址。"""
    host, port = httpd.server_address[:2]
    return f"http://{host}:{port}"


def run_server(novel_dir: str | Path, meta: NovelMeta, *, port: int = 8899) -> ThreadingHTTPServer:
    """启动写作台（阻塞）。浏览器打开 http://127.0.0.1:{port}。"""
    httpd = create_server(novel_dir, meta, port=port)
    print(f"星枢写作台已启动: {serve_url(httpd)}")
    httpd.serve_forever()
    return httpd