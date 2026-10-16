# -*- coding: utf-8 -*-
"""1) 移除沙箱黄条提示 2) 无正文文章不进全部清单 3) 计数口径同步. (v2: 修正 f-string 转义锚点)"""
import sys

src = sys.stdin.read()

old1 = """/* 沙箱提示（一次性，仅环境受限时显示） */
setTimeout(function(){
  if(lsProbe() === false && document.body){
    const b = document.createElement('div');
    b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:998;background:#a56a00;color:#fff;font:12px/1.7 sans-serif;padding:5px 12px;pointer-events:none';
    b.textContent = '⚠ 沙箱预览：划线/批注暂存于本页，页面关闭前喊「保存批注」即可同步落盘；完整自动保存请用 Chrome/Edge 打开本地文件。';
    document.body.appendChild(b);
  }
}, 600);
"""
assert old1 in src, "锚点1 黄条段缺失"
src = src.replace(old1, "", 1)

old2 = """        fv = a.get("_full") or {}
        has = bool(fv.get("content_html"))
        star = ' ⭐' if k in rec_keys else ''
"""
new2 = """        fv = a.get("_full") or {}
        has = bool(fv.get("content_html"))
        if not has:
            continue   # 未取到正文: 不进清单(展示也读不了, 无意义)
        star = ' ⭐' if k in rec_keys else ''
"""
assert old2 in src, "锚点2 清单has行缺失"
src = src.replace(old2, new2, 1)

old3 = """             f'<span class="cinfo" id="acInfo">共 {n_total} 篇 · {n_full} 篇可读全文 · 点条目进入专注阅读</span>'"""
new3 = """             f'<span class="cinfo" id="acInfo">共 {n_full} 篇' + (f'（{n_total - n_full} 篇未取到正文已略过）' if n_total > n_full else '') + ' · 点条目进入专注阅读</span>'"""
assert old3 in src, "锚点3 acInfo缺失"
src = src.replace(old3, new3, 1)

old4 = r"""             f'<button id="tabAll" onclick="setView(\'all\')">📚 全部更新<span class="n">{n_total}</span></button>'"""
new4 = r"""             f'<button id="tabAll" onclick="setView(\'all\')">📚 全部更新<span class="n">{n_full}</span></button>'"""
assert old4 in src, "锚点4 tabAll缺失"
src = src.replace(old4, new4, 1)

print("PATCH OK: 4 处替换完成", file=sys.stderr)
sys.stdout.write(src)
