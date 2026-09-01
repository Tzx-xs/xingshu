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
:root{
  --bg:#0a0d14;--bg2:#0e1220;--panel:#121827;--panel2:#0d1120;
  --line:#1f2740;--line-hi:#2a3456;--dim:#8b95ad;--faint:#5d6880;
  --txt:#e8e6df;--acc:#d8a552;--acc-hi:#f0c37a;--ink:#1b1508;
  --ok:#6fbf8f;--bad:#e0716b;--violet:#b093d6;
  --serif:"Noto Serif SC","Songti SC","STSong","SimSun",serif;
  --sans:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:"SFMono-Regular","Cascadia Mono",Consolas,monospace;
  --r:12px;--r-sm:8px;
  --shadow:0 18px 50px rgba(0,0,0,.45);
  --shadow-s:0 6px 18px rgba(0,0,0,.35);
}
*{box-sizing:border-box;margin:0;padding:0}
::selection{background:rgba(216,165,82,.28)}
body{background:var(--bg);color:var(--txt);
  font:14px/1.65 var(--sans);min-height:100vh;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;z-index:-2;pointer-events:none;
  background:
    radial-gradient(900px 500px at 82% -8%, rgba(216,165,82,.10), transparent 62%),
    radial-gradient(700px 420px at -8% 18%, rgba(103,132,186,.14), transparent 60%),
    linear-gradient(180deg,#0a0d14,#07090f 70%,#05060b);
}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.5;
  background-image:
    radial-gradient(1px 1px at 12% 18%, rgba(240,236,220,.9), transparent),
    radial-gradient(1px 1px at 34% 8%, rgba(240,236,220,.7), transparent),
    radial-gradient(1.4px 1.4px at 58% 26%, rgba(240,236,220,.8), transparent),
    radial-gradient(1px 1px at 76% 12%, rgba(240,236,220,.6), transparent),
    radial-gradient(1.2px 1.2px at 90% 34%, rgba(240,236,220,.75), transparent),
    radial-gradient(1px 1px at 22% 46%, rgba(240,236,220,.5), transparent),
    radial-gradient(1.4px 1.4px at 47% 60%, rgba(240,236,220,.55), transparent),
    radial-gradient(1px 1px at 66% 74%, rgba(240,236,220,.5), transparent),
    radial-gradient(1.2px 1.2px at 84% 58%, rgba(240,236,220,.6), transparent);
  background-size:340px 340px;animation:drift 90s linear infinite}
@keyframes drift{to{background-position:340px 340px}}
.wrap{max-width:1440px;margin:0 auto;padding:22px 26px 40px}
/* ---------- 顶栏 ---------- */
header{display:flex;align-items:center;gap:16px;margin-bottom:18px}
.logo{width:46px;height:46px;flex:none;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(145deg,#2a3350,#161c2e);border:1px solid var(--line-hi);
  box-shadow:var(--shadow-s), inset 0 1px 0 rgba(255,255,255,.06)}
.logo b{font:700 22px/1 var(--serif);color:var(--acc);text-shadow:0 0 18px rgba(216,165,82,.5)}
.titles h1{font:600 21px/1.2 var(--serif);letter-spacing:4px;color:var(--txt)}
.titles h1 em{font-style:normal;color:var(--acc)}
.titles .sub{display:flex;gap:10px;align-items:center;margin-top:3px;font-size:12px;color:var(--dim)}
.titles .sub b{color:var(--acc-hi);font-weight:600}
.top-right{margin-left:auto;display:flex;align-items:center;gap:8px}
.badge{font-size:12px;padding:5px 12px;border:1px solid var(--line);border-radius:999px;color:var(--dim);
  display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.badge::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--faint)}
.badge.cloud{color:var(--acc-hi);border-color:rgba(216,165,82,.4)}
.badge.cloud::before{background:var(--ok);box-shadow:0 0 10px var(--ok)}
/* ---------- 工作流步进 ---------- */
.steps{display:flex;gap:0;margin:0 0 20px;padding:14px 18px;border:1px solid var(--line);
  border-radius:var(--r);background:rgba(18,24,39,.6);backdrop-filter:blur(6px)}
.step{flex:1;display:flex;align-items:center;gap:10px;position:relative;color:var(--faint);
  font-size:13px;letter-spacing:.5px}
.step:not(:last-child)::after{content:"";position:absolute;top:16px;left:calc(42px + 10px);right:calc(42px + 10px);
  height:1px;background:var(--line)}
.step .num{width:32px;height:32px;flex:none;border-radius:50%;display:grid;place-items:center;
  background:var(--panel2);border:1px solid var(--line);color:var(--faint);
  font:600 14px var(--serif);transition:.25s}
.step .label{line-height:1.25}.step .label small{display:block;font-size:11px;color:var(--faint);
  letter-spacing:0;margin-top:1px}
.step.on{color:var(--txt)}
.step.on .num{background:linear-gradient(145deg,var(--acc),#c08a3a);border-color:transparent;color:var(--ink);
  box-shadow:0 0 18px rgba(216,165,82,.45)}
.step.on:not(:last-child)::after{background:linear-gradient(90deg,var(--acc),var(--line))}
.step.done{color:var(--txt)}
.step.done .num{background:rgba(111,191,143,.12);border-color:var(--ok);color:var(--ok)}
.step.done:not(:last-child)::after{background:var(--ok)}
/* ---------- 主栅格 ---------- */
.grid{display:grid;grid-template-columns:336px minmax(0,1fr) 300px;gap:16px;align-items:start}
@media(max-width:1240px){.grid{grid-template-columns:300px 1fr}}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.panel{background:linear-gradient(180deg,rgba(18,24,39,.92),rgba(15,19,31,.92));
  border:1px solid var(--line);border-radius:var(--r);padding:16px;box-shadow:var(--shadow-s);
  display:flex;flex-direction:column;gap:0}
.panel-head{display:flex;align-items:baseline;gap:8px;margin-bottom:12px;flex:none}
.panel-head h2{font:600 13px/1 var(--serif);letter-spacing:3px;color:var(--acc)}
.panel-head .cnt{margin-left:auto;font-size:11px;color:var(--faint)}
.ghost{background:transparent;border:1px solid var(--line);color:var(--dim);padding:6px 13px;
  border-radius:var(--r-sm);cursor:pointer;font:13px var(--sans);transition:.2s}
.ghost:hover{color:var(--txt);border-color:var(--line-hi);transform:translateY(-1px)}
/* ---------- 章纲表单 ---------- */
label{display:block;font-size:12px;color:var(--dim);margin:11px 0 5px;letter-spacing:.5px}
label b{color:var(--txt);font-weight:600}
label .opt{color:var(--faint);font-weight:400;font-size:11px;margin-left:6px}
input,select,textarea{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  border-radius:var(--r-sm);padding:8px 10px;font:13.5px/1.5 var(--sans);transition:border .18s, box-shadow .18s}
input:focus,select:focus,textarea:focus{outline:none;border-color:rgba(216,165,82,.55);
  box-shadow:0 0 0 3px rgba(216,165,82,.12)}
textarea{resize:vertical;min-height:58px}
.row{display:flex;gap:10px}.row>*{flex:1;min-width:0}
#summaries,#settings{font-family:var(--mono);font-size:12px}
details.adv{margin-top:12px;border-top:1px dashed var(--line);padding-top:4px}
details.adv summary{cursor:pointer;font-size:12px;color:var(--faint);letter-spacing:1px;
  list-style:none;user-select:none;padding:8px 0}
details.adv summary::before{content:"▸ ";color:var(--acc)}
details.adv[open] summary::before{content:"▾ "}
details.adv summary:hover{color:var(--dim)}
/* ---------- 主按钮 ---------- */
.primary{width:100%;cursor:pointer;border:none;border-radius:10px;font:600 15px/1 var(--sans);
  color:var(--ink);background:linear-gradient(135deg,var(--acc-hi),var(--acc) 55%,#b9852f);
  padding:13px;margin-top:16px;letter-spacing:6px;text-indent:6px;transition:.22s;
  box-shadow:0 4px 18px rgba(216,165,82,.35);position:relative;overflow:hidden}
.primary:hover{transform:translateY(-1px);box-shadow:0 8px 26px rgba(216,165,82,.45)}
.primary:active{transform:translateY(0)}
.primary:disabled{opacity:.55;cursor:wait;transform:none}
.primary:disabled::after{content:"";position:absolute;inset:0;
  background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%);
  animation:shine 1.2s infinite}
@keyframes shine{to{transform:translateX(100%)}}
.save-btn{width:auto;margin:0;padding:9px 16px;font-size:13px;letter-spacing:1px;text-indent:0;
  background:linear-gradient(135deg,#7fae8f,#4d8f66);box-shadow:0 4px 14px rgba(111,191,143,.25)}
.save-btn:hover{box-shadow:0 6px 20px rgba(111,191,143,.35)}
.save-btn:disabled{opacity:.5;cursor:wait}
.btns{display:flex;gap:10px;margin-top:16px}
.btns .primary{flex:1;margin-top:0}
/* ---------- 正文 ---------- */
#body{flex:1;white-space:pre-wrap;line-height:2;font-family:var(--serif);font-size:15.5px;
  background:
    linear-gradient(180deg,rgba(232,230,223,.028),transparent 40%),
    var(--panel2);
  border:1px solid var(--line);border-radius:10px;padding:22px 24px;min-height:340px;
  color:#d9d5ca;overflow-y:auto;transition:.3s;letter-spacing:.015em}
#body:focus{outline:none;border-color:rgba(216,165,82,.4)}
#body .ph{color:var(--faint);font-family:var(--sans);font-size:13px;letter-spacing:.6px;
  text-align:center;padding-top:16px;line-height:1.9}
#body .ph em{display:block;font-family:var(--serif);font-size:20px;color:var(--acc);
  font-style:normal;letter-spacing:4px;margin-bottom:10px}
/* ---------- 审计 ---------- */
.audit{margin-top:14px;border:1px solid var(--line);border-radius:10px;padding:14px;background:var(--panel2);
  display:none}
.audit.show{display:block;animation:rise .3s ease}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.audit-top{display:flex;align-items:center;gap:14px;margin-bottom:10px}
.score-ring{--p:50;--col:var(--faint);width:56px;height:56px;flex:none;border-radius:50%;
  background:conic-gradient(var(--col) calc(var(--p)*1%),rgba(255,255,255,.06) 0);
  display:grid;place-items:center;position:relative}
.score-ring::before{content:"";position:absolute;inset:5px;border-radius:50%;background:var(--panel2)}
.score-ring b{position:relative;font:700 15px var(--mono)}
.audit-title{font:600 14px var(--serif);color:var(--txt)}
.audit-title .verdict{display:inline-block;margin-left:8px;font:500 11px var(--sans);padding:2px 9px;
  border-radius:999px;border:1px solid var(--line)}
.verdict.pass{color:var(--ok);border-color:rgba(111,191,143,.5)}
.verdict.fail{color:var(--bad);border-color:rgba(224,113,107,.5)}
.audit-top .meta{margin-left:auto;font-size:11px;color:var(--faint);text-align:right}
.audit ul{list-style:none;margin-top:6px}
.audit li{font-size:12.5px;color:var(--dim);padding:4px 0 4px 16px;position:relative;line-height:1.6}
.audit li::before{content:"·";position:absolute;left:4px;color:var(--acc)}
.audit li.creative{color:var(--violet)}
/* ---------- 事实库 ---------- */
.facts{flex:1;overflow:auto;font-size:12.5px}
.facts .empty-note{color:var(--faint);text-align:center;padding:28px 0;line-height:1.9;
  border:1px dashed var(--line);border-radius:10px;font-size:12px}
.fact{border-bottom:1px solid rgba(31,39,64,.6);padding:10px 2px;animation:rise .3s ease}
.fact:last-child{border-bottom:none}
.fact .head{color:var(--txt);word-break:break-all;margin-bottom:4px}
.fact .head b{color:var(--acc-hi);font-weight:600}
.fact .meta{color:var(--faint);font-size:11px}
.fact .meta .sys{display:inline-block;font-size:10px;padding:1px 7px;border-radius:999px;
  border:1px solid var(--line);color:var(--dim);margin-right:6px}
/* ---------- Toast ---------- */
.toast{position:fixed;top:22px;right:22px;z-index:99;background:#1b2133;border:1px solid var(--line-hi);
  color:var(--txt);border-radius:10px;padding:12px 18px;font-size:13px;box-shadow:var(--shadow);
  opacity:0;transform:translateY(-8px);transition:.25s;pointer-events:none;max-width:340px}
.toast.show{opacity:1;transform:none}
.toast.err{border-color:rgba(224,113,107,.5)}
kbd{display:inline-block;font:10px var(--mono);padding:1px 5px;margin-left:6px;
  border:1px solid rgba(27,21,8,.4);border-radius:4px;background:rgba(27,21,8,.22);
  color:var(--ink);vertical-align:1px}
.save-btn kbd{border-color:rgba(255,255,255,.35);background:rgba(255,255,255,.18);color:#eaf3ec}
.hintbar{margin-top:14px;padding:9px 14px 9px 0;font-size:11.5px;color:var(--faint);
  display:flex;align-items:center;gap:4px;letter-spacing:.5px}
.hintbar>span{color:var(--dim);margin-right:4px}
.hintbar kbd{margin-left:4px;color:var(--dim);border-color:var(--line);background:var(--panel2)}
@media (prefers-reduced-motion: reduce){
  body::after,body::after{animation:none}
  *{transition:none!important;animation:none!important}
}
"""

_PAGE_BODY = """
<header>
  <div class="logo"><b>枢</b></div>
  <div class="titles">
    <h1>星枢<em>写作台</em></h1>
    <div class="sub" id="sub"><b id="novelTitle">…</b><span id="genres">-</span></div>
  </div>
  <div class="top-right">
    <span class="badge" id="model"></span>
    <button class="ghost" onclick="loadFacts()">刷新事实库</button>
    <button class="primary save-btn" onclick="commit()" id="saveBtn">保存本章 </button>
  </div>
</header>
<div class="steps" id="steps">
  <div class="step on" data-step="1"><span class="num">1</span><span class="label">填章纲<small>定局面</small></span></div>
  <div class="step" data-step="2"><span class="num">2</span><span class="label">生成正文<small>起笔</small></span></div>
  <div class="step" data-step="3"><span class="num">3</span><span class="label">审读校验<small>过审</small></span></div>
  <div class="step" data-step="4"><span class="num">4</span><span class="label">保存落盘<small>生成检查点</small></span></div>
</div>
<div class="grid">
  <div class="panel">
    <div class="panel-head"><h2>章纲</h2><span class="cnt">必填：梗概</span></div>
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
    <button class="primary" onclick="writeChapter()" id="writeBtn">创作本章 </button>
  </div>
  <div class="panel" style="min-height:72vh">
    <div class="panel-head"><h2>正文</h2><span class="cnt">生成后可编辑润色</span></div>
    <div id="body"><div class="ph"><em>起 笔</em>在左侧填好章纲，点击「创作本章」开始生成。<br>正文将在此处展开，审读通过后点右上「保存本章」落盘。</div></div>
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
  <div class="panel" style="min-height:72vh">
    <div class="panel-head"><h2>真相文件</h2><span class="cnt" id="factCnt">0</span></div>
    <div class="facts" id="facts"><div class="empty-note">暂无事实，生成全文后将自动沉淀设定。</div></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="hintbar"><span>快捷键</span><kbd>Ctrl</kbd>+<kbd>Enter</kbd> 创作本章　<kbd>Ctrl</kbd>+<kbd>S</kbd> 保存落盘　·　正文区域可直接编辑润色</div>
<script>
const $=id=>document.getElementById(id);
function setStep(n){document.querySelectorAll('#steps .step').forEach(s=>{
  const i=+s.dataset.step;
  s.classList.toggle('on',i===n);s.classList.toggle('done',i<n);
});}
async function post(path,data){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});return r.json()}
function loading(on,msg){
  const btn=$('writeBtn');const body=$('body');
  if(on){btn.disabled=true;btn.textContent=msg||'生成中…';
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
  if(!$('body').textContent.trim()){toast('没有可保存的正文','err');return;}
  const btn=$('saveBtn');btn.disabled=true;
  try{
    const res=await post('/api/commit',{number,text:$('body').textContent,summary:$('summary').value});
    toast('已保存 '+res.body.split('/').pop());setStep(4);loadFacts();
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
let t;function toast(m,kind){const e=$('toast');e.textContent=m;e.className='toast show'+(kind?' err':'');
  clearTimeout(t);t=setTimeout(()=>e.classList.remove('show'),2600)}
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();writeChapter();}
  if(e.key.toLowerCase()==='s'&&(e.ctrlKey||e.metaKey)){e.preventDefault();commit();}
});
boot();loadFacts();
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