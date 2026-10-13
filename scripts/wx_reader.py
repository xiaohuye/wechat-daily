# -*- coding: utf-8 -*-
"""
wx_reader.py — 生成「公众号日报 · 精读版」页面

核心能力：
  1. 正文内嵌，免跳转直接阅读（公众号原文链接非作者环境会触发人机验证，打不开）
  2. 句级划线批注：选中正文任意句子 → 高亮 + 写批注
  3. 划线查询：批注抽屉支持全文搜索，点击可跳回原文位置
  4. 划线解释：选中 → 一键生成「解释请求」复制到剪贴板，粘到对话即可让 AI 解释
  5. 导出/复制：批注以 markdown 形式导出，可交给 ima_save.py 存进 ima 知识库

输入:
  data/articles-full-weread-*.json   正文（weread_content.py 产出）
  data/ranked-weread-*.json          可选，补评分 / 类型 / 推荐理由
  data/insights-weread-*.json        可选，补概览 / 主题
  data/articles-weread-*.json        可选，末尾全量清单
输出:
  output/公众号日报-精读版-YYYY-MM-DD-HHMM.html

用法:
  python scripts/wx_reader.py --top 15
"""
import os, re, json, glob, html, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
DATA = os.path.join(ROOT, "data")
TZ = datetime.timezone(datetime.timedelta(hours=8))


def esc(s):
    return html.escape(str(s or ""), quote=True)


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(DATA, pattern)))
    return fs[-1] if fs else None


CSS = """
:root{
  --bg:#f6f6f8; --card:#ffffff; --paper:#fdfdfc; --paper-line:#eceae4;
  --ink:#1a1c21; --ink-2:#4a4f57; --sub:#878c95; --line:#e7e8ec; --line-2:#d9dce1;
  --red:#e14d5a; --blue:#2f6fed; --blue-soft:#eef3ff; --blue-ink:#244d9e;
  --amber:#b8860b; --amber-bg:#fff9e6; --amber-line:#efd98a;
  --hl:#fff0b3; --hl-2:#ffe27a; --hl-ink:#5c4a12;
  --shadow-sm:0 1px 2px rgba(18,20,24,.05);
  --shadow-md:0 4px 16px rgba(18,20,24,.07);
  --shadow-lg:0 16px 48px rgba(18,20,24,.16);
  --r-lg:16px; --r-md:12px; --r-sm:9px;
  --ff:-apple-system,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --fw:700px; /* 正文最大宽度 */
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 var(--ff);
     -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}

/* ---------- 阅读进度条 ---------- */
#pbar{position:fixed;top:0;left:0;height:3px;width:0;z-index:100;
      background:linear-gradient(90deg,var(--blue),#5b8df5);transition:width .12s ease-out;
      box-shadow:0 1px 4px rgba(47,111,237,.4)}

.wrap{max-width:900px;margin:0 auto;padding:30px 20px 110px}

/* ---------- 顶部标题区 ---------- */
.hero{margin-bottom:22px}
.hero .eyebrow{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;
  letter-spacing:.06em;color:var(--blue);background:var(--blue-soft);
  padding:4px 12px;border-radius:999px;margin-bottom:12px}
.hero .eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--blue)}
h1.top{font-size:30px;font-weight:800;margin:0 0 8px;letter-spacing:-.02em;line-height:1.25}
.subtop{color:var(--sub);font-size:13.5px;line-height:1.7}
.subtop b{color:var(--ink-2);font-weight:600}

/* ---------- 工具条 ---------- */
.bar{position:sticky;top:14px;z-index:30;display:flex;gap:9px;flex-wrap:wrap;align-items:center;
     background:rgba(255,255,255,.85);backdrop-filter:blur(14px) saturate(1.4);
     border:1px solid var(--line);border-radius:var(--r-lg);
     padding:10px 13px;margin:20px 0 26px;box-shadow:var(--shadow-md)}
.bar button{font:600 13px/1 var(--ff);border:1px solid var(--line);background:#fff;
     color:var(--ink-2);border-radius:var(--r-sm);padding:9px 14px;cursor:pointer;
     transition:all .18s ease;display:inline-flex;align-items:center;gap:6px}
.bar button:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px);
     box-shadow:0 3px 10px rgba(47,111,237,.14)}
.bar button:active{transform:translateY(0)}
.bar button.pri{background:var(--blue);border-color:var(--blue);color:#fff}
.bar button.pri:hover{background:#2559c9;color:#fff;box-shadow:0 4px 14px rgba(47,111,237,.35)}
.bar .grp{display:flex;gap:5px;align-items:center;background:#f3f4f6;border-radius:var(--r-sm);
     padding:3px;margin-left:2px}
.bar .grp button{border:0;background:transparent;padding:7px 10px;color:var(--ink-2)}
.bar .grp button.on{background:#fff;color:var(--blue);box-shadow:var(--shadow-sm);transform:none}
.bar .grp button:hover{color:var(--blue);transform:none;box-shadow:none}
.tip{font-size:12px;color:var(--sub);margin-left:auto;display:flex;align-items:center;gap:5px}
.tip kbd{background:#f1f2f4;border:1px solid var(--line-2);border-bottom-width:2px;border-radius:5px;
     padding:1px 6px;font:600 11px/1.6 var(--ff);color:var(--ink-2)}

/* ---------- 概览/目录卡片 ---------- */
.idx{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
     padding:18px 20px;margin-bottom:18px;box-shadow:var(--shadow-sm)}
.idx h3{margin:0 0 11px;font-size:13px;color:var(--sub);font-weight:700;
        letter-spacing:.05em;text-transform:uppercase}
.idx p{margin:0 0 12px;font-size:14.5px;line-height:1.75;color:var(--ink-2)}
.idx ol{margin:0;padding-left:22px;counter-reset:x}
.idx li{margin:5px 0;font-size:13.8px;line-height:1.6}
.idx li::marker{color:var(--sub);font-weight:600}
.idx a{color:var(--ink);text-decoration:none;transition:color .15s}
.idx a:hover{color:var(--blue)}
.idx .who{color:var(--sub);font-size:12px;margin-left:7px}
.theme-chip{display:inline-flex;align-items:center;gap:6px;background:var(--blue-soft);
     color:var(--blue-ink);border-radius:999px;padding:5px 13px;font-size:12.5px;
     margin:0 8px 9px 0;transition:transform .15s}
.theme-chip:hover{transform:translateY(-1px)}
.theme-chip b{font-weight:700}

/* ---------- 文章卡片 ---------- */
article{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
        padding:24px 26px;margin-bottom:20px;scroll-margin-top:86px;
        box-shadow:var(--shadow-sm);transition:box-shadow .25s ease,transform .25s ease}
article:hover{box-shadow:var(--shadow-md)}
article.open{box-shadow:var(--shadow-md)}
article .head{display:flex;gap:11px;align-items:center;flex-wrap:wrap;margin-bottom:13px}
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:28px;height:28px;
      background:linear-gradient(135deg,#f0565f,var(--red));color:#fff;border-radius:9px;
      font-size:13.5px;font-weight:800;padding:0 8px;box-shadow:0 3px 8px rgba(225,77,90,.3);
      letter-spacing:.01em}
.acc{font-weight:700;font-size:14.5px;letter-spacing:.01em}
.tag{font-size:11.5px;color:var(--sub);border:1px solid var(--line-2);border-radius:6px;
     padding:2px 9px;background:#fafafa;transition:.15s}
.meta{margin-left:auto;color:var(--sub);font-size:12.5px;white-space:nowrap;
      display:flex;align-items:center;gap:6px}
.meta .dot{width:3px;height:3px;border-radius:50%;background:var(--line-2)}
.meta b{color:var(--blue);font-weight:700}
article h2{font-size:22px;line-height:1.4;margin:4px 0 14px;font-weight:800;
           letter-spacing:-.01em;color:var(--ink)}
article h2::after{content:"";display:block;width:44px;height:3px;margin-top:12px;
      background:linear-gradient(90deg,var(--red),transparent);border-radius:2px}
.reasons{background:linear-gradient(135deg,#f7faff,#f2f6ff);border:1px solid #e3ecff;
     border-left:3px solid var(--blue);border-radius:0 var(--r-md) var(--r-md) 0;
     padding:11px 15px;font-size:13.5px;color:var(--blue-ink);margin-bottom:16px;line-height:1.65}
.reasons::before{content:"💡 ";font-size:13px}

.acts{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:4px}
.acts button{font:600 13px/1 inherit;border:1px solid var(--line);background:#fff;
     border-radius:var(--r-sm);padding:9px 15px;cursor:pointer;color:var(--ink-2);
     transition:all .18s;display:inline-flex;align-items:center;gap:6px}
.acts button:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px);
     box-shadow:0 3px 10px rgba(47,111,237,.13)}
.acts button.on{background:var(--blue-soft);border-color:var(--blue);color:var(--blue)}
.hlbtn.has{background:var(--amber-bg);border-color:var(--amber-line);color:var(--amber)}
.hlbtn .hlcnt{background:var(--hl-2);color:var(--hl-ink);border-radius:8px;min-width:20px;
     padding:1px 6px;font-size:11px;font-weight:700;text-align:center;margin-left:2px}

/* ---------- 正文 ---------- */
.read{display:none;border-top:1px dashed var(--line-2);margin-top:14px;padding-top:8px;
      animation:fadeIn .35s ease}
article.open .read{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.paper{max-width:var(--fw);margin:0 auto;background:var(--paper);border:1px solid var(--paper-line);
       border-radius:var(--r-md);padding:30px 34px;margin-top:16px;
       font-size:17px;line-height:1.9;color:#26282d;letter-spacing:.012em;
       box-shadow:inset 0 1px 0 #fff, var(--shadow-sm)}
.paper img{max-width:100%;height:auto;border-radius:8px;display:block;margin:20px auto;
           box-shadow:0 2px 12px rgba(0,0,0,.08)}
.paper p{margin:0 0 18px;text-align:justify}
.paper section{margin:0}
.paper span{display:inline}
.paper blockquote{border-left:4px solid var(--blue-soft);background:#fafbff;
      margin:16px 0;padding:12px 0 12px 16px;color:#5a6170;border-radius:0 8px 8px 0;
      font-style:normal}
.paper blockquote p{margin-bottom:8px}
.paper h1,.paper h2,.paper h3,.paper h4{font-size:19px;margin:28px 0 12px;font-weight:800;
      line-height:1.5;letter-spacing:-.01em}
.paper h2::after,.paper h3::after{content:"";display:block;width:28px;height:2px;margin-top:7px;
      background:var(--blue);border-radius:2px}
.paper strong{font-weight:700;color:#15171b}
.paper code{background:#eef1f4;padding:2px 7px;border-radius:5px;font-size:.88em;
      font-family:ui-monospace,"SF Mono",Consolas,monospace;color:#d6336c}
.paper pre{background:#26282d;color:#e6e8ec;padding:16px;border-radius:10px;overflow-x:auto;
      font-size:.86em;line-height:1.6}
.paper pre code{background:transparent;color:inherit;padding:0}
.paper table{border-collapse:collapse;margin:16px 0;display:block;overflow-x:auto;max-width:100%;
      font-size:.92em}
.paper td,.paper th{border:1px solid #dfe3e8;padding:8px 12px}
.paper th{background:#f4f6f8;font-weight:700}
.paper ul,.paper ol{padding-left:26px;margin:0 0 18px}
.paper li{margin:6px 0}
.paper li::marker{color:var(--blue)}
.paper hr{border:0;height:1px;margin:26px auto;width:70px;
      background:linear-gradient(90deg,transparent,var(--line-2),transparent)}

/* ---------- 划线 ---------- */
mark.hl{background:linear-gradient(180deg,transparent 58%,var(--hl) 58%);
        border-radius:2px;cursor:pointer;padding:1px 0;
        border-bottom:2px solid transparent;transition:all .15s}
mark.hl:hover{background:linear-gradient(180deg,transparent 40%,var(--hl) 40%)}
mark.hl.hasnote{background:linear-gradient(180deg,transparent 50%,var(--hl-2) 50%);
        border-bottom-color:#e0b90a}
mark.hl.active{background:var(--hl-2);box-shadow:0 0 0 3px rgba(255,214,74,.45)}

/* ---------- 批注面板 ---------- */
.hlpanel{margin-top:20px;border-top:1px dashed var(--line-2);padding-top:16px}
.hlpanel .hlhd{font-size:13px;font-weight:700;color:var(--amber);margin-bottom:11px;
               display:flex;align-items:center;gap:8px;letter-spacing:.02em}
.hlpanel .hlhd .cnt{background:var(--amber-bg);color:var(--amber);border:1px solid var(--amber-line);
      border-radius:8px;min-width:20px;padding:1px 7px;font-size:11.5px;text-align:center}
.hlpanel .hlempty{font-size:12.5px;color:var(--sub);line-height:1.8;
      background:#fafafa;border-radius:var(--r-sm);padding:12px 14px}
.hllist{margin:0;padding:0;list-style:none}
.hllist li{background:var(--amber-bg);border:1px solid var(--amber-line);border-radius:var(--r-md);
           padding:11px 14px;margin-bottom:9px;transition:transform .15s,box-shadow .15s}
.hllist li:hover{transform:translateX(2px);box-shadow:0 3px 12px rgba(184,134,11,.12)}
.hllist .q{font-size:13.8px;color:var(--hl-ink);line-height:1.7;
           border-left:3px solid var(--hl-line,#e8cd5a);padding-left:11px}
.hllist .n{font-size:13.8px;color:#26282d;margin-top:8px;white-space:pre-wrap;line-height:1.65}
.hllist .n.empty{color:#b3a06a;font-style:italic;font-size:13px}
.hllist .ops{margin-top:9px;display:flex;gap:14px}
.hllist .ops a{font-size:12.3px;color:var(--blue);cursor:pointer;text-decoration:none;
      display:inline-flex;align-items:center;gap:4px;opacity:.85;transition:.15s}
.hllist .ops a:hover{opacity:1;text-decoration:underline}
.hllist .ops a.dan{color:var(--red)}

/* ---------- 浮动工具条 ---------- */
.selbar{position:absolute;z-index:80;background:#22252b;border-radius:11px;padding:6px;
        display:flex;gap:3px;box-shadow:var(--shadow-lg);
        animation:popIn .16s cubic-bezier(.34,1.56,.64,1)}
@keyframes popIn{from{opacity:0;transform:scale(.9) translateY(4px)}to{opacity:1;transform:none}}
.selbar::after{content:"";position:absolute;left:50%;bottom:-5px;transform:translateX(-50%);
      border:6px solid transparent;border-top-color:#22252b;border-bottom:0}
.selbar button{font:600 13px/1 inherit;background:transparent;border:0;color:#e8eaee;
               padding:9px 12px;border-radius:8px;cursor:pointer;white-space:nowrap;
               transition:background .13s;display:inline-flex;align-items:center;gap:5px}
.selbar button:hover{background:rgba(255,255,255,.16)}

/* ---------- 编辑器 ---------- */
.mask{position:fixed;inset:0;background:rgba(22,24,28,.5);backdrop-filter:blur(3px);z-index:85;
      animation:fadeIn .18s ease}
.editor{position:fixed;z-index:90;left:50%;top:50%;transform:translate(-50%,-50%);
        width:min(580px,93vw);background:#fff;border-radius:var(--r-lg);
        box-shadow:var(--shadow-lg);padding:20px 22px;overflow:hidden;
        animation:slideUp .22s cubic-bezier(.34,1.3,.64,1)}
@keyframes slideUp{from{opacity:0;transform:translate(-50%,-47%)}to{opacity:1;transform:translate(-50%,-50%)}}
.editor .qh{font-size:12px;color:var(--sub);margin-bottom:8px;font-weight:600;letter-spacing:.04em}
.editor .q{background:var(--amber-bg);border-left:3px solid var(--hl-line,#e8cd5a);
           padding:10px 14px;border-radius:0 var(--r-sm) var(--r-sm) 0;font-size:14px;
           color:var(--hl-ink);max-height:130px;overflow:auto;margin-bottom:14px;line-height:1.75}
.editor textarea{width:100%;min-height:96px;border:1px solid var(--line);border-radius:var(--r-sm);
                 padding:12px 14px;font:14.5px/1.7 inherit;resize:vertical;color:var(--ink);
                 background:#fafbfc;transition:border-color .15s,box-shadow .15s}
.editor textarea:focus{outline:none;border-color:var(--blue);background:#fff;
      box-shadow:0 0 0 3px rgba(47,111,237,.12)}
.editor .row{display:flex;gap:9px;justify-content:flex-end;margin-top:14px;align-items:center}
.editor .row .sp{flex:1}
.editor .row button{font:600 13.5px/1 inherit;border-radius:var(--r-sm);padding:10px 18px;
                    cursor:pointer;border:1px solid var(--line);background:#fff;color:var(--ink-2);
                    transition:all .16s}
.editor .row button:hover{border-color:var(--blue);color:var(--blue)}
.editor .row button.pri{background:var(--blue);border-color:var(--blue);color:#fff}
.editor .row button.pri:hover{background:#2559c9;color:#fff}
.editor .row button.dan{color:var(--red);border-color:#f6ccd0}
.editor .row button.dan:hover{border-color:var(--red);background:#fff5f5}
.editor .kshort{font-size:11px;color:var(--sub);margin-right:8px}

/* ---------- 抽屉 ---------- */
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,95vw);background:#fff;z-index:95;
        box-shadow:-16px 0 48px rgba(0,0,0,.18);transform:translateX(102%);
        transition:transform .3s cubic-bezier(.32,.72,.35,1);display:flex;flex-direction:column}
.drawer.open{transform:none}
.dhd{padding:17px 18px;border-bottom:1px solid var(--line);display:flex;gap:9px;
     align-items:center;font-weight:800;font-size:15px;background:var(--card)}
.dhd .t{display:inline-flex;align-items:center;gap:8px}
.dhd input{flex:1;font:13.5px/1 inherit;border:1px solid var(--line);border-radius:var(--r-sm);
           padding:9px 12px;background:#fafbfc;transition:.15s}
.dhd input:focus{outline:none;border-color:var(--blue);background:#fff;
      box-shadow:0 0 0 3px rgba(47,111,237,.12)}
.dhd button{border:0;background:#f1f3f5;border-radius:8px;width:30px;height:30px;
            cursor:pointer;font-size:17px;color:#555;line-height:1;transition:.15s}
.dhd button:hover{background:#e4e7ea;color:#222}
.dstat{padding:10px 18px;font-size:12px;color:var(--sub);border-bottom:1px solid var(--line);
       background:#fafbfc}
.dlist{flex:1;overflow:auto;padding:14px 16px}
.dgrp{margin-bottom:18px}
.dgrp h4{margin:0 0 8px;font-size:13.5px;color:var(--ink);line-height:1.5;font-weight:700;
         padding-bottom:8px;border-bottom:1px solid var(--line)}
.dgrp .ditem{background:var(--amber-bg);border:1px solid var(--amber-line);border-radius:var(--r-md);
             padding:10px 13px;margin-bottom:8px;cursor:pointer;transition:all .15s}
.dgrp .ditem:hover{border-color:var(--amber);background:#fff6d5;transform:translateX(3px);
      box-shadow:0 3px 12px rgba(184,134,11,.14)}
.dgrp .dq{font-size:13.3px;color:var(--hl-ink);line-height:1.68}
.dgrp .dn{font-size:12.8px;color:#3f4650;margin-top:6px;white-space:pre-wrap;line-height:1.6}
.dgrp .dn.empty{color:#b3a06a;font-style:italic}
.empty-all{color:var(--sub);font-size:13.5px;text-align:center;padding:40px 14px;line-height:2}
.empty-all .big{font-size:34px;display:block;margin-bottom:10px;opacity:.5}

footer{color:var(--sub);font-size:12.5px;text-align:center;margin-top:34px;line-height:2;
       padding-top:24px;border-top:1px solid var(--line)}

.toast{position:fixed;left:50%;bottom:34px;transform:translateX(-50%) translateY(20px);
       background:#22252b;color:#fff;padding:11px 20px;border-radius:11px;font-size:13.5px;
       opacity:0;transition:all .28s cubic-bezier(.34,1.3,.64,1);pointer-events:none;z-index:99;
       max-width:88vw;text-align:center;line-height:1.65;box-shadow:var(--shadow-lg)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

/* 回到顶部 */
#totop{position:fixed;right:26px;bottom:30px;z-index:60;width:44px;height:44px;border-radius:50%;
     background:var(--card);border:1px solid var(--line);box-shadow:var(--shadow-md);
     color:var(--ink-2);font-size:19px;cursor:pointer;display:none;align-items:center;
     justify-content:center;transition:all .2s}
#totop.show{display:flex}
#totop:hover{background:var(--blue);color:#fff;border-color:var(--blue);transform:translateY(-3px)}

/* 响应式 */
@media (max-width:680px){
  .wrap{padding:20px 14px 90px}
  h1.top{font-size:25px}
  .bar{top:8px;padding:9px 10px}
  .tip{display:none}
  article{padding:19px 18px}
  .paper{padding:22px 20px;font-size:16px}
  .meta{margin-left:0;width:100%;justify-content:flex-start}
}
"""

JS = r"""
const HKEY = 'wxhl::';
let curSel = null, curHlId = null, curArtKey = null;

const $  = (s,r)=> (r||document).querySelector(s);
const $$ = (s,r)=> Array.prototype.slice.call((r||document).querySelectorAll(s));

function escHtml(s){
  return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function toast(msg){
  let t = $('.toast');
  if(!t){ t = document.createElement('div'); t.className='toast'; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(()=>t.classList.remove('show'), 2200);
}
function artByKey(k){ return $$('article[data-key]').find(a=>a.dataset.key===k); }

/* ---------------- 阅读进度 + 回顶 ---------------- */
function bindScroll(){
  const pbar = $('#pbar'), totop = $('#totop');
  function upd(){
    const h = document.documentElement;
    const max = h.scrollHeight - h.clientHeight;
    const pct = max > 0 ? (h.scrollTop / max) * 100 : 0;
    pbar.style.width = pct + '%';
    totop.classList.toggle('show', h.scrollTop > 600);
  }
  window.addEventListener('scroll', upd, {passive:true});
  upd();
  totop.addEventListener('click', ()=>window.scrollTo({top:0, behavior:'smooth'}));
}

/* ---------------- 字号调节 ---------------- */
function setFont(delta){
  const cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--fw')) || 700;
  const next = Math.min(860, Math.max(560, cur + delta));
  document.documentElement.style.setProperty('--fw', next + 'px');
  localStorage.setItem('wxfw', next);
  toast(delta > 0 ? '正文加宽' : '正文收窄');
}
function setFontSize(delta){
  const p = getComputedStyle(document.body).getPropertyValue('font-size');
  $$('.paper').forEach(el=>{
    const cur = parseFloat(getComputedStyle(el).getPropertyValue('font-size'));
    el.style.fontSize = Math.min(21, Math.max(14.5, cur + delta)) + 'px';
  });
  localStorage.setItem('wxfs', parseFloat(getComputedStyle($('.paper') || document.body).getPropertyValue('font-size')));
  toast(delta > 0 ? '字号调大' : '字号调小');
}
function restoreView(){
  const fw = localStorage.getItem('wxfw');
  if(fw) document.documentElement.style.setProperty('--fw', fw + 'px');
  const fs = localStorage.getItem('wxfs');
  if(fs) $$('.paper').forEach(el=>el.style.fontSize = fs + 'px');
}

/* ---------------- 存储 ---------------- */
function loadHL(key){
  try{ return JSON.parse(localStorage.getItem(HKEY+key) || '[]'); }catch(e){ return []; }
}
function saveHL(key, arr){
  localStorage.setItem(HKEY+key, JSON.stringify(arr));
  renderPanel(key); renderDrawer($('#dsearch') ? $('#dsearch').value : '');
}
function newId(){ return 'h'+Date.now().toString(36)+Math.floor(Math.random()*46656).toString(36); }

/* ---------------- 文本偏移 ---------------- */
function textMap(root){
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  const out = []; let pos=0, n;
  while((n = w.nextNode())){ const L = n.nodeValue.length; out.push({node:n, s:pos, e:pos+L}); pos += L; }
  return out;
}
function offsetOf(root, node, off){
  const nodes = textMap(root);
  for(let i=0;i<nodes.length;i++){ if(nodes[i].node === node) return nodes[i].s + off; }
  return -1;
}
function markRange(root, s, e, id, hasNote){
  const nodes = textMap(root);
  const tg = nodes.filter(x=> x.e > s && x.s < e);
  for(let i=tg.length-1;i>=0;i--){
    const t = tg[i];
    let ns = Math.max(s - t.s, 0);
    let ne = Math.min(e - t.s, t.node.nodeValue.length);
    if(ns >= ne) continue;
    let node = t.node;
    if(ne < node.nodeValue.length) node.splitText(ne);
    if(ns > 0) node = node.splitText(ns);
    const mk = document.createElement('mark');
    mk.className = 'hl' + (hasNote ? ' hasnote' : '');
    mk.dataset.hlid = id;
    node.parentNode.insertBefore(mk, node);
    mk.appendChild(node);
  }
}
function unwrapMarks(root){
  $$('mark.hl', root).forEach(function(m){
    const p = m.parentNode;
    while(m.firstChild) p.insertBefore(m.firstChild, m);
    p.removeChild(m);
  });
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  let n; const list=[];
  while((n=w.nextNode())) list.push(n);
  list.forEach(x=>x.parentNode && x.parentNode.normalize());
}
function applyHighlights(key){
  const art = artByKey(key); if(!art) return;
  const root = $('.paper', art); if(!root) return;
  unwrapMarks(root);
  const list = loadHL(key).slice().sort((a,b)=>b.start - a.start);
  list.forEach(h=> markRange(root, h.start, h.end, h.id, !!(h.note && h.note.trim())));
}
function applyAll(){
  $$('article[data-key]').forEach(a=>{ if(loadHL(a.dataset.key).length) applyHighlights(a.dataset.key); });
}

/* ---------------- 选区 ---------------- */
/* 注意：函数名不能叫 getSelection —— 顶层 function 声明会挂到 window 上，
   覆盖浏览器原生的 window.getSelection，导致无限递归。*/
function readSel(){
  const sel = window.getSelection();
  if(!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const r = sel.getRangeAt(0);
  let root = null;
  $$('article[data-key]').forEach(function(a){
    const p = $('.paper', a);
    if(p && p.contains(r.startContainer) && p.contains(r.endContainer)) root = p;
  });
  if(!root) return null;
  const s = offsetOf(root, r.startContainer, r.startOffset);
  const e = offsetOf(root, r.endContainer, r.endOffset);
  if(s < 0 || e < 0 || e <= s) return null;
  const text = root.textContent.slice(s, e).trim();
  if(text.length < 2 || text.length > 1200) return null;
  const art = root.closest('article');
  return {key: art.dataset.key, start:s, end:e, text:text, rect:r.getBoundingClientRect()};
}

/* ---------------- 浮动工具条 ---------------- */
function showBar(rect, mode, hlid){
  const bar = $('#selbar');
  bar.innerHTML = (mode === 'edit')
    ? '<button data-a="note">✏️ 编辑批注</button><button data-a="ask">💡 解释</button><button data-a="del">🗑 删除划线</button>'
    : '<button data-a="note">🖍 划线批注</button><button data-a="ask">💡 求解释</button><button data-a="copy">📋 复制</button>';
  bar.dataset.mode = mode; bar.dataset.hlid = hlid || '';
  bar.hidden = false;
  const w = bar.offsetWidth, h = bar.offsetHeight;
  let x = rect.left + window.scrollX + rect.width/2 - w/2;
  let y = rect.top + window.scrollY - h - 10;
  let flip = false;
  if(y < window.scrollY + 8){ y = rect.bottom + window.scrollY + 10; flip = true; }
  x = Math.max(10, Math.min(x, (document.documentElement.clientWidth - w - 10)));
  bar.style.left = x + 'px'; bar.style.top = y + 'px';
  bar.classList.toggle('flip', flip);
}
function hideBar(){ const b = $('#selbar'); if(b) b.hidden = true; }

/* ---------------- 批注编辑器 ---------------- */
function openEditor(hlid, artKey, quote){
  curHlId = hlid || null; curArtKey = artKey;
  const list = loadHL(artKey);
  const h = hlid ? list.find(x=>x.id === hlid) : null;
  $('#edQuote').textContent = h ? h.text : (quote || '');
  $('#edNote').value = h ? (h.note || '') : '';
  $('#edDel').style.display = h ? '' : 'none';
  $('#mask').hidden = false; $('#editor').hidden = false;
  setTimeout(()=>$('#edNote').focus(), 60);
}
function closeEditor(){ $('#mask').hidden = true; $('#editor').hidden = true; curHlId = null; }
function saveEditor(){
  const note = ($('#edNote').value || '').trim();
  const list = loadHL(curArtKey);
  if(curHlId){
    const h = list.find(x=>x.id === curHlId);
    if(h) h.note = note;
  }else if(curSel){
    list.push({id:newId(), start:curSel.start, end:curSel.end, text:curSel.text, note:note, ts:Date.now()});
  }
  list.sort((a,b)=>a.start - b.start);
  saveHL(curArtKey, list);
  applyHighlights(curArtKey);
  closeEditor(); hideBar();
  toast(note ? '已保存划线批注' : '已划线（未写批注）');
}
function deleteHl(){
  const k = curArtKey;
  const list = loadHL(k).filter(x=>x.id !== curHlId);
  saveHL(k, list);
  applyHighlights(k);
  closeEditor(); hideBar(); toast('已删除划线');
}

/* ---------------- 面板 / 抽屉 ---------------- */
function renderPanel(key){
  const art = artByKey(key); if(!art) return;
  const box = $('.hlpanel', art); if(!box) return;
  const list = loadHL(key).slice().sort((a,b)=>a.start - b.start);
  const cnt = $('.cnt', box); if(cnt) cnt.textContent = list.length;
  const btn = $('.hlbtn', art);
  if(btn){ $('.hlcnt', btn).textContent = list.length; btn.classList.toggle('has', list.length>0); }
  const ol = $('.hllist', box);
  ol.innerHTML = '';
  const emp = $('.hlempty', box);
  if(emp) emp.style.display = list.length ? 'none' : '';
  list.forEach(function(h){
    const li = document.createElement('li');
    li.dataset.hlid = h.id;
    li.innerHTML = '<div class="q">' + escHtml(h.text) + '</div>'
      + (h.note ? '<div class="n">' + escHtml(h.note) + '</div>'
                : '<div class="n empty">（暂无批注）</div>')
      + '<div class="ops"><a data-a="ask">💡 解释</a><a data-a="note">✏️ 编辑批注</a>'
      + '<a class="dan" data-a="del">🗑 删除</a></div>';
    ol.appendChild(li);
  });
}
function renderDrawer(filter){
  const box = $('#dlist'); if(!box) return;
  const q = (filter || '').trim().toLowerCase();
  let total = 0, groups = 0, html = '';
  $$('article[data-key]').forEach(function(art){
    const list = loadHL(art.dataset.key).slice().sort((a,b)=>a.start - b.start);
    const hits = list.filter(h=> !q ||
      (h.text + ' ' + (h.note||'')).toLowerCase().indexOf(q) >= 0);
    if(!hits.length) return;
    groups++; total += hits.length;
    html += '<div class="dgrp"><h4>' + escHtml(art.dataset.title || art.dataset.key)
         + ' <span style="color:#9aa0a6;font-weight:400">· '
         + escHtml(art.dataset.account || '') + '</span></h4>';
    hits.forEach(function(h){
      html += '<div class="ditem" data-hlid="' + h.id + '" data-akey="'
           + escHtml(art.dataset.key) + '">'
           + '<div class="dq">' + escHtml(h.text) + '</div>'
           + (h.note ? '<div class="dn">' + escHtml(h.note) + '</div>'
                     : '<div class="dn empty">（暂无批注）</div>')
           + '</div>';
    });
    html += '</div>';
  });
  box.innerHTML = html || ('<div class="empty-all"><span class="big">✏️</span>'
      + (q ? '没有匹配的划线批注' : '还没有任何划线批注<br>在正文里选中句子，即可划线、写批注或求解释')
      + '</div>');
  const st = $('#dstat');
  if(st) st.textContent = q ? ('匹配 ' + total + ' 条') : ('共 ' + total + ' 条 · ' + groups + ' 篇');
}
function openDrawer(){ renderDrawer($('#dsearch').value); $('#drawer').classList.add('open'); }
function closeDrawer(){ $('#drawer').classList.remove('open'); }

function jumpTo(akey, hlid){
  const art = artByKey(akey); if(!art) return;
  closeDrawer();
  if(!art.classList.contains('open')) openArt(art);
  setTimeout(function(){
    const mk = $('mark[data-hlid="' + hlid + '"]', art);
    if(mk){
      mk.scrollIntoView({behavior:'smooth', block:'center'});
      mk.classList.add('active');
      setTimeout(()=>mk.classList.remove('active'), 1700);
    }else{
      art.scrollIntoView({behavior:'smooth', block:'start'});
    }
  }, 100);
}

/* ---------------- 解释 ---------------- */
function copyText(txt, okMsg){
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(()=>toast(okMsg || '已复制'), ()=>fallbackCopy(txt, okMsg));
  }else{ fallbackCopy(txt, okMsg); }
}
function fallbackCopy(txt, okMsg){
  const ta = document.createElement('textarea');
  ta.value = txt; ta.style.position='fixed'; ta.style.left='-9999px';
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); toast(okMsg || '已复制'); }catch(e){ toast('复制失败，请手动选择'); }
  ta.remove();
}
function askExplain(text, akey, start, end){
  const art = artByKey(akey); if(!art) return;
  const root = $('.paper', art);
  const full = root ? root.textContent : '';
  const ctx = full.slice(Math.max(0, start - 220), Math.min(full.length, end + 220));
  const prompt = '帮我解释这段划线内容。\n\n'
    + '文章：《' + (art.dataset.title||'') + '》（' + (art.dataset.account||'') + '）\n'
    + '原文链接：' + (art.dataset.url || '（无）') + '\n\n'
    + '【划线内容】\n' + text + '\n\n'
    + '【上下文】\n' + ctx + '\n\n'
    + '请说明：这段话在讲什么、涉及的关键概念、以及对我做 AI 产品/Agent 方向有什么启发。';
  copyText(prompt, '已复制「解释请求」，粘贴到对话框发给我即可');
}

/* ---------------- 导出 ---------------- */
function collect(){
  const items = [];
  $$('article[data-key]').forEach(function(art){
    const list = loadHL(art.dataset.key).slice().sort((a,b)=>a.start - b.start);
    if(list.length) items.push({art:art, list:list});
  });
  return items;
}
function buildMd(){
  const items = collect();
  if(!items.length) return null;
  const d = new Date().toLocaleDateString('zh-CN');
  let md = '# 公众号精读批注 · ' + d + '\n\n';
  items.forEach(function(o, i){
    const a = o.art;
    md += '## ' + (i+1) + '. ' + (a.dataset.title || '') + '\n\n';
    md += '- 公众号：' + (a.dataset.account || '') + '\n';
    if(a.dataset.time) md += '- 发布：' + a.dataset.time + '\n';
    if(a.dataset.url)  md += '- 原文：' + a.dataset.url + '\n';
    md += '\n### 划线批注\n\n';
    o.list.forEach(function(h){
      md += '**划线**：' + h.text + '\n\n';
      md += '**批注**：' + (h.note && h.note.trim() ? h.note : '（无）') + '\n\n';
    });
    md += '---\n\n';
  });
  return md;
}
function copyAll(){
  const md = buildMd();
  if(!md){ toast('还没有任何划线批注'); return; }
  const n = collect().reduce((s,o)=>s+o.list.length, 0);
  copyText(md, '已复制 ' + n + ' 条批注，粘贴到对话即可存入 ima');
}
function exportNotes(){
  const md = buildMd();
  if(!md){ toast('还没有任何划线批注'); return; }
  const b = new Blob([md], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b);
  a.download = '公众号精读批注-' + new Date().toLocaleDateString('zh-CN').replace(/\//g,'-') + '.md';
  a.click(); URL.revokeObjectURL(a.href);
  const n = collect().reduce((s,o)=>s+o.list.length, 0);
  toast('已导出 ' + n + ' 条批注');
}

/* ---------------- 展开/折叠 ---------------- */
function openArt(art){
  if(!art.classList.contains('open')){
    art.classList.add('open');
    const b = $('.acts .tg', art);
    if(b){ b.textContent = '📖 收起正文'; b.classList.add('on'); }
    applyHighlights(art.dataset.key);
  }
}
function toggleBody(btn){
  const art = btn.closest('article');
  if(art.classList.contains('open')){
    art.classList.remove('open');
    btn.textContent = '📖 展开正文'; btn.classList.remove('on');
  }else{ openArt(art); }
}
function toggleAll(){
  const arts = $$('article');
  const anyClosed = arts.some(a=>!a.classList.contains('open'));
  arts.forEach(function(a){
    if(anyClosed){ openArt(a); }
    else{
      a.classList.remove('open');
      const b = $('.acts .tg', a);
      if(b){ b.textContent = '📖 展开正文'; b.classList.remove('on'); }
    }
  });
}

/* ---------------- 事件 ---------------- */
function onMouseUp(){
  setTimeout(function(){
    const s = readSel();
    if(s){ curSel = s; showBar(s.rect, 'new', null); }
    else if(!$('#selbar').matches(':hover')) hideBar();
  }, 10);
}
document.addEventListener('mouseup', onMouseUp);
document.addEventListener('touchend', onMouseUp);

document.addEventListener('click', function(e){
  const bar = $('#selbar');
  if(bar && !bar.hidden && bar.contains(e.target)) return;

  const mk = e.target.closest ? e.target.closest('mark.hl') : null;
  if(mk){
    const art = mk.closest('article');
    const r = mk.getBoundingClientRect();
    curSel = null;
    showBar(r, 'edit', mk.dataset.hlid);
    curArtKey = art.dataset.key;
    return;
  }
  const li = e.target.closest ? e.target.closest('.hllist li') : null;
  if(li){
    const art = li.closest('article');
    curArtKey = art.dataset.key;
    if(e.target.dataset.a === 'ask'){
      const h = loadHL(curArtKey).find(x=>x.id === li.dataset.hlid);
      if(h) askExplain(h.text, curArtKey, h.start, h.end);
      return;
    }
    if(e.target.dataset.a === 'del'){
      const list = loadHL(curArtKey).filter(x=>x.id !== li.dataset.hlid);
      saveHL(curArtKey, list); applyHighlights(curArtKey); toast('已删除划线'); return;
    }
    openEditor(li.dataset.hlid, curArtKey);
    return;
  }
  if(!e.target.closest || !e.target.closest('.paper')){ hideBar(); }
});

/* 浮动条自身 */
document.addEventListener('mousedown', function(e){
  const bar = $('#selbar');
  if(bar && !bar.hidden && bar.contains(e.target)){ e.preventDefault(); }
});
$('#selbar').addEventListener('click', function(e){
  const a = e.target.dataset.a; if(!a) return;
  const mode = this.dataset.mode, hlid = this.dataset.hlid;
  if(mode === 'edit'){
    const h = loadHL(curArtKey).find(x=>x.id === hlid);
    if(a === 'note'){ this.hidden = true; openEditor(hlid, curArtKey); }
    else if(a === 'del'){
      const list = loadHL(curArtKey).filter(x=>x.id !== hlid);
      saveHL(curArtKey, list); applyHighlights(curArtKey); this.hidden = true; toast('已删除划线');
    }
    else if(a === 'ask'){ if(h) askExplain(h.text, curArtKey, h.start, h.end); this.hidden = true; }
  }else{
    if(!curSel){ this.hidden = true; return; }
    if(a === 'note'){ this.hidden = true; openEditor(null, curSel.key, curSel.text); }
    else if(a === 'copy'){ copyText(curSel.text, '已复制划线内容'); this.hidden = true; }
    else if(a === 'ask'){ askExplain(curSel.text, curSel.key, curSel.start, curSel.end); this.hidden = true; }
  }
});

/* 编辑器按钮 */
$('#edSave').addEventListener('click', saveEditor);
$('#edCancel').addEventListener('click', closeEditor);
$('#edDel').addEventListener('click', deleteHl);
$('#mask').addEventListener('click', closeEditor);
document.addEventListener('keydown', function(e){
  if(e.key === 'Escape'){ if(!$('#editor').hidden) closeEditor(); hideBar(); closeDrawer(); }
  if((e.ctrlKey||e.metaKey) && e.key === 'Enter' && !$('#editor').hidden){ saveEditor(); }
});

/* 抽屉 */
$('#dclose').addEventListener('click', closeDrawer);
$('#dsearch').addEventListener('input', function(){ renderDrawer(this.value); });
$('#dlist').addEventListener('click', function(e){
  const it = e.target.closest('.ditem'); if(!it) return;
  jumpTo(it.dataset.akey, it.dataset.hlid);
});

/* 字号/宽度 */
$('#fsw').addEventListener('click', function(e){
  const d = e.target.dataset.d; if(d) setFont(parseInt(d));
});
$('#fss').addEventListener('click', function(e){
  const d = e.target.dataset.d; if(d) setFontSize(parseInt(d));
});

/* 初始化 */
document.addEventListener('DOMContentLoaded', function(){
  bindScroll();
  restoreView();
  $$('article[data-key]').forEach(a=>renderPanel(a.dataset.key));
  renderDrawer('');
  applyAll();
});
"""


def build(full_file, rank_file, top, insights_file=None, articles_file=None):
    d = json.load(open(full_file, encoding="utf-8"))
    arts = list(d.get("articles", {}).items())[:top]

    meta = {}
    if rank_file and os.path.exists(rank_file):
        rk = json.load(open(rank_file, encoding="utf-8"))
        for a in rk.get("top", []):
            k = f"{a.get('account','')}|{a.get('title','')}"
            meta[k] = a

    ins = {}
    if insights_file and os.path.exists(insights_file):
        ins = json.load(open(insights_file, encoding="utf-8"))
    overview = ins.get("overview", "")
    themes = ins.get("themes", [])
    imeta = ins.get("articles", {})

    all_arts = []
    if articles_file and os.path.exists(articles_file):
        all_arts = json.load(open(articles_file, encoding="utf-8")).get("articles", [])

    stamp_raw = os.path.basename(full_file).split("articles-full-weread-")[-1].replace(".json", "")
    try:
        dt = datetime.datetime.strptime(stamp_raw, "%Y-%m-%d-%H%M")
        gen = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        gen = stamp_raw

    W = []
    W.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>公众号日报 · 精读版 {esc(gen)}</title><style>{CSS}</style></head>'
             '<body><div id="pbar"></div><div class="wrap">')
    W.append('<div class="hero"><span class="eyebrow">公众号精读</span>'
             f'<h1 class="top">今日推荐 · 可读可批注</h1>'
             f'<div class="subtop">生成 <b>{esc(gen)}</b> ｜ 推荐 <b>{len(arts)}</b> 篇'
             + (f' ｜ 全量更新 <b>{len(all_arts)}</b> 篇' if all_arts else '')
             + '<br>正文已内嵌，点「📖 展开正文」直接读；<b>选中句子</b>即可划线批注或求解释。</div></div>')

    W.append('<div class="bar">'
             '<button onclick="toggleAll()">⇅ 展开/折叠</button>'
             '<button onclick="openDrawer()">🖍 划线批注</button>'
             '<span class="grp" id="fss" title="字号">'
             '<button data-d="-1">A−</button><button data-d="1">A+</button></span>'
             '<span class="grp" id="fsw" title="正文宽度">'
             '<button data-d="-40">窄</button><button data-d="40">宽</button></span>'
             '<button class="pri" onclick="copyAll()">📋 复制全部批注</button>'
             '<button onclick="exportNotes()">📤 导出 .md</button>'
             '<span class="tip"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> 存批注 · <kbd>Esc</kbd> 关闭</span>'
             '</div>')

    # 今日概览 + 主题
    if overview or themes:
        W.append('<div class="idx"><h3>今日概览</h3>')
        if overview:
            W.append(f'<p>{esc(overview)}</p>')
        if themes:
            W.append('<div>' + "".join(
                f'<span class="theme-chip"><b>{esc(t.get("name"))}</b>·{esc(t.get("desc"))}</span>'
                for t in themes) + '</div>')
        W.append('</div>')

    # 目录
    W.append('<div class="idx"><h3>推荐目录</h3><ol>')
    for i, (k, v) in enumerate(arts, 1):
        if not v.get("content_html"):
            continue
        W.append(f'<li><a href="#art-{i}">{esc(v.get("title") or k)}</a>'
                 f'<span class="who">{esc(v.get("account"))}</span></li>')
    W.append('</ol></div>')

    for i, (k, v) in enumerate(arts, 1):
        body = v.get("content_html") or ""
        if not body:
            continue
        m = meta.get(k, {})
        typ = m.get("_type", "")
        score = m.get("_score")
        reasons = m.get("_reasons") or []
        keep = [r for r in reasons if "类型高度贴合" not in r]
        reason_txt = "；".join(keep) if keep else ""
        if not reason_txt:
            reason_txt = (imeta.get(k, {}) or {}).get("reason", "").split("｜")[0]
        stat = ""
        if v.get("read_num"):
            stat = f"阅读 {v['read_num']}"
            if v.get("like_num"):
                stat += f" / 赞 {v['like_num']}"
        inner_id = v.get("internal_id") or ""
        rlink = f"https://weread.qq.com/web/mp/reader/{inner_id}" if inner_id else ""

        W.append(f'<article id="art-{i}" data-key="{esc(k)}" data-rank="{i}" '
                 f'data-account="{esc(v.get("account"))}" data-title="{esc(v.get("title"))}" '
                 f'data-time="{esc(v.get("time"))}" data-read="{esc(stat)}" data-url="{esc(rlink)}">')
        W.append('<div class="head">'
                 f'<span class="rank">{i}</span><span class="acc">{esc(v.get("account"))}</span>'
                 f'<span class="tag">{esc(typ or "未分类")}</span>'
                 f'<span class="meta">{esc(v.get("time"))}'
                 + (f'<span class="dot"></span>{esc(stat)}' if stat else '')
                 + (f'<span class="dot"></span><b>评分 {score}</b>' if score else '') + '</span></div>')
        W.append(f'<h2>{esc(v.get("title"))}</h2>')
        if reason_txt:
            W.append(f'<div class="reasons">为什么推给你：{esc(reason_txt)}</div>')
        elif v.get("digest"):
            W.append(f'<div class="reasons">{esc(v["digest"][:120])}</div>')
        W.append('<div class="acts">'
                 '<button class="tg" onclick="toggleBody(this)">📖 展开正文</button>'
                 '<button class="hlbtn" onclick="openDrawer()">🖍 批注 <span class="hlcnt">0</span></button>'
                 '</div>')
        W.append('<div class="read"><div class="paper">')
        W.append(body)
        W.append('</div>')
        W.append('<div class="hlpanel">'
                 '<div class="hlhd">🖍 本篇划线批注 <span class="cnt">0</span> 条</div>'
                 '<div class="hlempty">在正文里选中任意句子，即可划线、写批注或求解释。</div>'
                 '<ol class="hllist"></ol></div>')
        W.append('</div>')
        W.append('</article>')

    # 全量更新清单（折叠）
    if all_arts:
        per = {}
        for a in all_arts:
            per.setdefault(a.get("account", ""), []).append(a)
        rec_keys = set(k for k, _ in arts)
        W.append('<div class="idx"><h3 style="cursor:pointer" onclick="'
                 "const x=document.getElementById('allList');"
                 "x.style.display=x.style.display==='none'?'block':'none'\">"
                 f'▸ 全部更新清单（{len(all_arts)} 篇 / {len(per)} 个号）· 点击展开</h3>')
        W.append('<div id="allList" style="display:none">')
        for acc in sorted(per, key=lambda x: -len(per[x])):
            items = sorted(per[acc], key=lambda k: -(k.get("ts") or 0))
            W.append(f'<div style="margin:13px 0 5px;font-weight:700;font-size:13.8px">'
                     f'{esc(acc)} <span style="color:#9aa0a6;font-weight:400">（{len(items)}）</span></div>')
            for a in items:
                kk = f'{a.get("account","")}|{a.get("title","")}'
                star = ' ⭐' if kk in rec_keys else ''
                rn = f' · 阅读 {a["read_num"]}' if a.get("read_num") else ''
                W.append(f'<div style="font-size:13.6px;color:#3a3f47;padding:4px 0 4px 16px;line-height:1.55">'
                         f'· {esc(a.get("title"))}{star}'
                         f'<span style="color:#9aa0a6;font-size:12px;margin-left:6px">{esc(a.get("time",""))}{esc(rn)}</span></div>')
        W.append('</div></div>')

    if d.get("failed"):
        names = "、".join(esc(f.get("key", "").split("|")[0]) for f in d["failed"])
        W.append(f'<div class="idx"><h3>未取到正文（可在微信读书里搜标题阅读）</h3>'
                 f'<p style="margin:0">{names}</p></div>')

    # 浮层组件
    W.append('<div id="selbar" class="selbar" hidden></div>')
    W.append('<div id="mask" class="mask" hidden></div>')
    W.append('<div id="editor" class="editor" hidden>'
             '<div class="qh">选中的句子</div>'
             '<div class="q" id="edQuote"></div>'
             '<textarea id="edNote" placeholder="写下你对这句话的批注、疑问或联想…"></textarea>'
             '<div class="row"><button id="edDel" class="dan" style="display:none">删除划线</button>'
             '<span class="sp"></span><span class="kshort">Ctrl+Enter 保存</span>'
             '<button id="edCancel">取消</button>'
             '<button id="edSave" class="pri">保存批注</button></div></div>')
    W.append('<div id="drawer" class="drawer">'
             '<div class="dhd"><span class="t">🖍 划线批注</span>'
             '<input id="dsearch" placeholder="搜索划线 / 批注…">'
             '<button id="dclose">×</button></div>'
             '<div id="dstat" class="dstat"></div>'
             '<div class="dlist" id="dlist"></div></div>')

    W.append('<div id="totop" title="回到顶部">↑</div>')
    W.append('<footer>'
             f'数据来源 {esc(d.get("source", "微信读书 /web/mp/content"))} · 正文由 WorkBuddy 内嵌，无需跳转<br>'
             '划线批注自动保存在本地浏览器 · 点「📋 复制全部批注」粘到对话，即可与原文一起存入 ima 知识库'
             '</footer>')
    W.append(f'</div><script>{JS}</script></body></html>')
    return "".join(W)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", default=None)
    ap.add_argument("--rank", default=None)
    ap.add_argument("--insights", default=None)
    ap.add_argument("--articles", default=None)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    full = args.full or latest("articles-full-weread-*.json")
    if not full:
        raise SystemExit("找不到 data/articles-full-weread-*.json，先跑 weread_content.py")
    rank = args.rank or latest("ranked-weread-*.json")
    insights = args.insights or latest("insights-weread-*.json")
    articles = args.articles or latest("articles-weread-*.json")

    htm = build(full, rank, args.top, insights, articles)
    os.makedirs(OUT, exist_ok=True)
    stamp = os.path.basename(full).split("articles-full-weread-")[-1].replace(".json", "")
    outf = args.out or os.path.join(OUT, f"公众号日报-精读版-{stamp}.html")
    open(outf, "w", encoding="utf-8").write(htm)
    print("已生成:", outf)
    print(f"  正文 {os.path.basename(full)} ｜ 推荐 {args.top} 篇 ｜ 全量清单 "
          f"{os.path.basename(articles) if articles else '无'} ｜ {len(htm):,} 字符")


if __name__ == "__main__":
    main()
