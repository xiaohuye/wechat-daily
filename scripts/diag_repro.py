# -*- coding: utf-8 -*-
"""诊断复现：全流程模拟用户操作，捕获 JS 错误红条内容。
用法: python diag_repro.py [html路径]
"""
import sys, pathlib
from playwright.sync_api import sync_playwright

HTML = sys.argv[1] if len(sys.argv) > 1 else r"E:\wokrbudy\wechat-daily\output\公众号日报-精读版-2026-10-15-诊断版.html"
phtml = pathlib.Path(HTML)
url = phtml.as_uri()

errors = []          # pageerror 收集
console_errs = []

def snap(page, step):
    st = page.evaluate("""() => {
      const d = window._diag || {};
      const err = document.getElementById('_derr');
      return {errs: d.errs||0, clicks: d.clicks||0, saves: d.saves||0, mups: d.mups||0,
              sels: d.sels||0, edBtns: d.edBtns||0,
              errText: err ? err.textContent : '', title: document.title};
    }""")
    mark = "  <<<<<< JS错误!" if st["errs"] else ""
    print(f"[{step}] 错{st['errs']} 点{st['clicks']} 存{st['saves']} 抬{st['mups']} 选{st['sels']} 按钮{st['edBtns']} | {st['title'][:40]}{mark}")
    if st["errText"]:
        print(f"    红条: {st['errText']}")
    return st

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 786, "height": 960})   # 786 宽=用户截图同宽
    page = ctx.new_page()
    page.on("pageerror", lambda e: (errors.append(str(e)), print(f"    [pageerror] {e}")))
    page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)

    print("打开:", url[:80])
    page.goto(url)
    page.wait_for_timeout(1500)
    snap(page, "加载后")

    # ---- 1. 首页交互 ----
    page.evaluate("() => { const li = document.querySelector('#recView .gitem, #alist li[data-key]'); if(li) li.click(); }")
    page.wait_for_timeout(600)
    snap(page, "打开阅读弹层")

    # ---- 2. 弹层内滚动 ----
    page.evaluate("() => { const rb = document.querySelector('#rdBody'); rb.scrollTo({top: 300, behavior:'instant'}); }")
    page.wait_for_timeout(300)
    snap(page, "弹层内滚动300")

    # ---- 3. 划线 → 工具条 → 批注 → 保存 ----
    page.evaluate("""() => {
      const paper = document.querySelector('#rdBody .paper');
      const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
      let t = w.nextNode();
      while(t && t.nodeValue.trim().length < 40) t = w.nextNode();
      const rb = document.querySelector('#rdBody');
      const er = t.parentElement.getBoundingClientRect();
      const br = rb.getBoundingClientRect();
      rb.scrollTo({top: rb.scrollTop + er.top - br.top - br.height/2, behavior:'instant'});
    }""")
    page.wait_for_timeout(200)
    page.evaluate("""() => {
      const paper = document.querySelector('#rdBody .paper');
      const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
      let t = w.nextNode();
      while(t && t.nodeValue.trim().length < 40) t = w.nextNode();
      const n = Math.min(30, t.nodeValue.trim().length);
      const r = document.createRange();
      r.setStart(t, 0); r.setEnd(t, n);
      const s = window.getSelection();
      s.removeAllRanges(); s.addRange(r);
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    }""")
    page.wait_for_timeout(300)
    snap(page, "划线选区")
    bar = page.evaluate("() => { const b=document.querySelector('#selbar'); return b && !b.hidden; }")
    print("    工具条弹出:", bar)
    if bar:
        page.click("#selbar button[data-a='note']")
        page.wait_for_timeout(300)
        snap(page, "点批注按钮")
        page.fill("#edNote", "诊断复现批注")
        page.wait_for_timeout(200)
        page.mouse.click(*page.evaluate("""() => {
          const b = document.querySelector('#edSave').getBoundingClientRect();
          return [b.left + b.width/2, b.top + b.height/2];
        }"""))
        page.wait_for_timeout(500)
        snap(page, "点保存(真实鼠标)")
        mk = page.evaluate("() => document.querySelectorAll('#rdBody .paper mark.hl').length")
        print("    高亮 mark 数:", mk)

    # ---- 4. 划线 → 复制 ----
    page.evaluate("""() => {
      const paper = document.querySelector('#rdBody .paper');
      const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
      let t = w.nextNode();
      while(t && (t.nodeValue.trim().length < 40 || t.parentElement.closest('mark'))) t = w.nextNode();
      if(!t) return;
      const n = Math.min(20, t.nodeValue.trim().length);
      const r = document.createRange();
      r.setStart(t, 0); r.setEnd(t, n);
      const s = window.getSelection();
      s.removeAllRanges(); s.addRange(r);
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    }""")
    page.wait_for_timeout(300)
    if page.evaluate("() => { const b=document.querySelector('#selbar'); return b && !b.hidden; }"):
        page.click("#selbar button[data-a='copy']")
        page.wait_for_timeout(300)
        snap(page, "点复制按钮")

    # ---- 5. 划线 → 求解释 ----
    page.evaluate("""() => {
      const paper = document.querySelector('#rdBody .paper');
      const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
      let t = w.nextNode();
      while(t && (t.nodeValue.trim().length < 40 || t.parentElement.closest('mark'))) t = w.nextNode();
      if(!t) return;
      const n = Math.min(20, t.nodeValue.trim().length);
      const r = document.createRange();
      r.setStart(t, 0); r.setEnd(t, n);
      const s = window.getSelection();
      s.removeAllRanges(); s.addRange(r);
      document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
    }""")
    page.wait_for_timeout(300)
    if page.evaluate("() => { const b=document.querySelector('#selbar'); return b && !b.hidden; }"):
        page.click("#selbar button[data-a='ask']")
        page.wait_for_timeout(300)
        snap(page, "点求解释按钮")

    # ---- 6. 点已有划线高亮（真实鼠标）→ edit 条 → 批注 ----
    pos = page.evaluate("""() => {
      const m = document.querySelector('#rdBody .paper mark.hl');
      if(!m) return null;
      const r = m.getBoundingClientRect();
      return {x: r.left + 5, y: r.top + 5};
    }""")
    if pos:
        page.mouse.click(pos["x"], pos["y"])
        page.wait_for_timeout(300)
        snap(page, "点已有划线(真实鼠标)")
        mode = page.evaluate("() => { const b=document.querySelector('#selbar'); return b && !b.hidden ? b.dataset.mode : 'hidden'; }")
        print("    工具条 mode:", mode)
        if mode == "edit":
            page.click("#selbar button[data-a='note']")
            page.wait_for_timeout(300)
            snap(page, "edit条点批注")
            page.fill("#edNote", "编辑批注追加")
            page.mouse.click(*page.evaluate("""() => {
              const b = document.querySelector('#edSave').getBoundingClientRect();
              return [b.left + b.width/2, b.top + b.height/2];
            }"""))
            page.wait_for_timeout(500)
            snap(page, "edit保存")

    # ---- 7. 点正文空白（工具条应消失）----
    page.mouse.click(*page.evaluate("""() => {
      const rb = document.querySelector('#rdBody');
      return [rb.getBoundingClientRect().left + 60, rb.getBoundingClientRect().top + 40];
    }"""))
    page.wait_for_timeout(300)
    snap(page, "点正文空白")

    # ---- 8. 反馈按钮 / Esc 关弹层 ----
    page.evaluate("() => { const b = document.querySelector('#rdBody article .fb .like, #rdBody [data-fb=like]'); if(b) b.click(); }")
    page.wait_for_timeout(300)
    snap(page, "点赞")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    snap(page, "Esc关弹层")

    # ---- 9. 首页其余交互：下拉菜单 / chips / 抽屉 ----
    page.evaluate("() => { const b = document.querySelector('.dd > button, .ddbtn'); if(b) b.click(); }")
    page.wait_for_timeout(300)
    snap(page, "点下拉菜单")
    page.evaluate("() => document.body.click()")
    page.wait_for_timeout(200)
    page.evaluate("() => { const c = document.querySelector('.chips button, .chip'); if(c) c.click(); }")
    page.wait_for_timeout(300)
    snap(page, "点chips过滤")

    print()
    print("=" * 60)
    print(f"pageerror 共 {len(errors)} 个:")
    for e in errors:
        print("  -", e)
    print(f"console.error 共 {len(console_errs)} 个:")
    for c in console_errs[:10]:
        print("  -", c[:200])
    browser.close()
