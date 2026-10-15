# -*- coding: utf-8 -*-
"""内嵌诊断面板：JS错误红条 + 右下角实时事件状态条"""
import io
P = r"E:/wokrbuddy/wechat-daily/scripts/wx_reader.py"
src = io.open(P, encoding="utf-8").read()

# 1) saveEditor 入口计数
old1 = """function saveEditor(){
  if($('#editor').hidden) return;"""
new1 = """function saveEditor(){
  if(window._diag) window._diag.saves++;
  if($('#editor').hidden) return;"""
assert old1 in src, "saveEditor 未找到"
src = src.replace(old1, new1, 1)

# 2) onMouseUp 入口计数 + 选区命中计数
old2 = """function onMouseUp(){
  setTimeout(function(){
    const s = readSel();
    if(s){ curSel = s; showBar(s.rect, 'new', null); }"""
new2 = """function onMouseUp(){
  if(window._diag) window._diag.mups++;
  setTimeout(function(){
    const s = readSel();
    if(s){ if(window._diag) window._diag.sels++; curSel = s; showBar(s.rect, 'new', null); }"""
assert old2 in src, "onMouseUp 未找到"
src = src.replace(old2, new2, 1)

# 3) edBtn（mousedown 触发器）计数
old3 = """function edBtn(fn){ return function(e){ e.preventDefault(); fn(); }; }"""
new3 = """function edBtn(fn){ return function(e){ if(window._diag) window._diag.edBtns++; e.preventDefault(); fn(); }; }"""
assert old3 in src, "edBtn 未找到"
src = src.replace(old3, new3, 1)

# 4) document click 委托（划线/面板操作）入口计数
old4 = """document.addEventListener('click', function(e){
  const bar = $('#selbar');
  if(bar && !bar.hidden && bar.contains(e.target)) return;

  const mk = e.target.closest ? e.target.closest('mark.hl') : null;"""
new4 = """document.addEventListener('click', function(e){
  if(window._diag) window._diag.clicks++;
  const bar = $('#selbar');
  if(bar && !bar.hidden && bar.contains(e.target)) return;

  const mk = e.target.closest ? e.target.closest('mark.hl') : null;"""
assert old4 in src, "click 委托未找到"
src = src.replace(old4, new4, 1)

# 5) 诊断面板本体（DOMContentLoaded 注册之前）
old5 = """document.addEventListener('DOMContentLoaded', function(){"""
new5 = """/* ---------------- 诊断面板（交互问题排查取证用，定位后移除） ---------------- */
window._diag = {clicks:0, saves:0, edBtns:0, mups:0, sels:0, errs:0};
window.onerror = function(msg, src2, line){
  window._diag.errs++;
  var d = document.getElementById('_derr');
  if(!d){ d = document.createElement('div'); d.id = '_derr';
    d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:999;background:#c7250e;color:#fff;font:12px/1.6 monospace;padding:5px 12px;white-space:pre-wrap;word-break:break-all;pointer-events:none';
    (document.body || document.documentElement).appendChild(d); }
  d.textContent = 'JS错误#' + window._diag.errs + ': ' + msg + (line ? ' @line ' + line : '');
  return false;
};
setInterval(function(){
  var el = document.getElementById('_dbar');
  if(!el){ el = document.createElement('div'); el.id = '_dbar';
    el.style.cssText = 'position:fixed;right:8px;bottom:8px;z-index:999;background:rgba(38,42,50,.93);color:#8ce99a;font:11px/1.7 Consolas,monospace;padding:6px 10px;border-radius:8px;pointer-events:none;max-width:72vw;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,.28)';
    (document.body || document.documentElement).appendChild(el); }
  var d = window._diag;
  var ed = document.getElementById('editor'), mk = document.getElementById('mask'), sb = document.getElementById('selbar');
  el.textContent = '弹:' + (ed && !ed.hidden ? '开' : '关') + ' 罩:' + (mk && !mk.hidden ? '开' : '关')
    + ' 条:' + (sb && !sb.hidden ? '开' : '关') + (curSel ? ' 选:有' : ' 选:无')
    + ' | 点' + d.clicks + ' 存' + d.saves + ' 按下' + d.edBtns + ' 抬' + d.mups + ' 选中' + d.sels
    + (d.errs ? ' ⚠错' + d.errs : '');
}, 300);

document.addEventListener('DOMContentLoaded', function(){"""
assert old5 in src, "DOMContentLoaded 锚点未找到"
src = src.replace(old5, new5, 1)

io.open(P, "w", encoding="utf-8", newline="\n").write(src)
print("诊断面板已内嵌")
