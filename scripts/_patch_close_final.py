# -*- coding: utf-8 -*-
"""工具条跨界面残留终局修复: closeReader 收尾 + readSel 视口校验(幽灵选区过滤) + 弹条事件日志."""
import sys

src = sys.stdin.read()

# 1) closeReader 全面收尾
old1 = """function closeReader(){
  const art = $('#rdBody article');
  if(art){ $('#storehouse').appendChild(art); }
  $('#reader').hidden = true;
  document.body.classList.remove('reading');
}"""
new1 = """function closeReader(){
  const art = $('#rdBody article');
  if(art){ $('#storehouse').appendChild(art); }
  $('#reader').hidden = true;
  document.body.classList.remove('reading');
  /* 返回浏览层即收尾全部浮层：工具条是 body 上的 fixed 元素，不随弹层隐藏——
     不主动关会跨界面残留（用户报「返回首页后弹窗还在」）；残留选区指向
     storehouse(hidden) 内的文章，是 showBar 复活的弹药库，一并清除 */
  closeEditor(); hideBar();
  const _s = window.getSelection(); if(_s && _s.removeAllRanges) _s.removeAllRanges();
  curSel = null;
}"""
assert old1 in src, "锚点1 closeReader 缺失"
src = src.replace(old1, new1, 1)

# 2) openReader 换篇也收尾（防换篇残留浮层/选区）
old2 = """  $('#reader').hidden = false;
  document.body.classList.add('reading');
  $('#rdBody').scrollTop = 0;
}"""
new2 = """  $('#reader').hidden = false;
  document.body.classList.add('reading');
  $('#rdBody').scrollTop = 0;
  closeEditor(); hideBar();   /* 换篇/新开弹层：旧篇的浮层与选区一并收尾，防跨篇残留 */
}"""
assert old2 in src, "锚点2 openReader 缺失"
src = src.replace(old2, new2, 1)

# 3) readSel 视口校验（过滤 storehouse 幽灵选区）
old3 = """  const art = root.closest('article[data-key]') || root.closest('#alist > li[data-key]');
  return {key: art.dataset.key, start:s, end:e, text:text, rect:r.getBoundingClientRect()};
}"""
new3 = """  const art = root.closest('article[data-key]') || root.closest('#alist > li[data-key]');
  const rect = r.getBoundingClientRect();
  /* 视口校验：弹层关闭后 article 移回 storehouse(hidden)，残留选区的 rect 全为 0
     ——幽灵选区不该触发工具条复活（用户报「返回首页后弹窗还在、关不掉」）。
     正常选区必然在视口内；不可见的选区一律视为无效 */
  if(rect.height < 1 || rect.width < 1 || rect.bottom < 0 || rect.top > window.innerHeight) return null;
  return {key: art.dataset.key, start:s, end:e, text:text, rect:rect};
}"""
assert old3 in src, "锚点3 readSel 缺失"
src = src.replace(old3, new3, 1)

# 4) 弹条事件日志（showBar/hideBar/弹层开关全打点，右下角状态条滚动显示）
old4 = """/* ---------------- 浮动工具条 ---------------- */
function showBar(rect, mode, hlid){
  const bar = $('#selbar');"""
new4 = """/* ---------------- 浮动工具条 ---------------- */
/* 弹条事件日志：复现类问题一图定案。window._barLog 最近 12 条，F12 可查；
   诊断版右下角状态条滚动展示 */
window._barLog = [];
function barLog(t){
  try{
    window._barLog.unshift(new Date().toISOString().slice(11,23) + ' ' + t);
    if(window._barLog.length > 12) window._barLog.length = 12;
  }catch(e){}
}
function showBar(rect, mode, hlid){
  barLog('show:' + mode);
  const bar = $('#selbar');"""
assert old4 in src, "锚点4 showBar 缺失"
src = src.replace(old4, new4, 1)

old5 = "function hideBar(){ const b = $('#selbar'); if(b) b.hidden = true; }"
new5 = """function hideBar(){ const b = $('#selbar'); if(b && !b.hidden){ barLog('hide'); b.hidden = true; } }"""
assert old5 in src, "锚点5 hideBar 缺失"
src = src.replace(old5, new5, 1)

print("PATCH OK: 5 处替换完成", file=sys.stderr)
sys.stdout.write(src)
