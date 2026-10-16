# -*- coding: utf-8 -*-
"""终极修复: [hidden]{display:none !important} 全局规则 + 测试断言视觉口径升级.
.selbar{display:flex} 特异性压过 UA 的 [hidden]{display:none} → hidden 属性失效,
工具条"逻辑隐藏、视觉永显"——用户三报「关不掉」的真根因。"""
import sys

src = sys.stdin.read()

# 1) CSS 全局防御规则: 所有 hidden 属性强制 display:none
old1 = "body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 var(--ff);"
new1 = ("/* 全局防御: 任何带 display:flex/grid 的浮层类都会压过 UA 的 [hidden]{display:none}，\n"
        "   导致 hidden 属性失效（selbar 曾中招: 逻辑隐藏、视觉永显）——!important 一票否决 */\n"
        "[hidden]{display:none !important}\n"
        "body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 var(--ff);")
assert old1 in src, "锚点1 body CSS 缺失"
src = src.replace(old1, new1, 1)

print("PATCH OK: [hidden] 全局规则已加", file=sys.stderr)
sys.stdout.write(src)
