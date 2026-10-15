# -*- coding: utf-8 -*-
"""工具条复活 bug 二次修复: 保存/删除批注后点穿 mouseup 复活工具条.
1) closeEditor 统一打 350ms 复活抑制锁  2) saveEditor/deleteHl 清选区
3) onMouseUp 定时器检查锁. 诊断信息走 stderr, 不污染 stdout."""
import sys

src = sys.stdin.read()

# 1) 全局声明 _barLock
old1 = "let curSel = null, curHlId = null, curArtKey = null;"
new1 = old1 + "\nlet _barLock = 0;   /* 复活抑制锁：编辑器关闭时刻 +350ms 内 mouseup 定时器不弹任何条 */"
assert old1 in src, "锚点1缺失"
src = src.replace(old1, new1, 1)

# 2) closeEditor 打锁
old2 = "function closeEditor(){ $('#mask').hidden = true; $('#editor').hidden = true; curHlId = null; }"
new2 = ("function closeEditor(){ $('#mask').hidden = true; $('#editor').hidden = true; curHlId = null;\n"
        "  _barLock = Date.now() + 350;   /* 点穿 mouseup 防复活：mousedown 关编辑器时，同次点击的 mouseup 会落到正文 */ }")
assert old2 in src, "锚点2缺失"
src = src.replace(old2, new2, 1)

# 3) saveEditor 清选区
old3 = """  closeEditor(); hideBar();
  toast(note ? '已保存划线批注' : '已划线（未写批注）');
}"""
new3 = """  closeEditor(); hideBar();
  const _s = window.getSelection(); if(_s && _s.removeAllRanges) _s.removeAllRanges();   /* 保存完成即结束选区 */
  curSel = null;
  toast(note ? '已保存划线批注' : '已划线（未写批注）');
}"""
assert old3 in src, "锚点3缺失"
src = src.replace(old3, new3, 1)

# 4) deleteHl 清选区
old4 = """  closeEditor(); hideBar(); toast('已删除划线');
}"""
new4 = """  closeEditor(); hideBar();
  const _s = window.getSelection(); if(_s && _s.removeAllRanges) _s.removeAllRanges();
  curSel = null;
  toast('已删除划线');
}"""
assert old4 in src, "锚点4缺失"
src = src.replace(old4, new4, 1)

# 5) onMouseUp 定时器锁检查
old5 = """  setTimeout(function(){
    const s = readSel();"""
new5 = """  setTimeout(function(){
    if(Date.now() < _barLock) return;   /* 复活抑制窗内：编辑器刚被那次点击关掉，点穿 mouseup 不弹任何条 */
    const s = readSel();"""
assert old5 in src, "锚点5缺失"
src = src.replace(old5, new5, 1)

print("PATCH OK: 5 处替换全部完成", file=sys.stderr)
sys.stdout.write(src)
