# -*- coding: utf-8 -*-
"""沙箱环境专项测试：模拟 WorkBuddy 预览面板（sandboxed iframe, 无 allow-same-origin）。
验证: 1) 无 JS 错误  2) 沙箱黄条提示出现  3) 划线/批注/保存链路内存降级可用  4) 内存数据不持久(刷新即失)
     5) 诊断版红条不出现
"""
import http.server, socketserver, threading, functools, pathlib, urllib.parse
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(r"E:\wokrbudy\wechat-daily\output")
PORT = 8950

def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    ok = 0; bad = []
    def check(name, cond, extra=""):
        nonlocal ok
        if cond: ok += 1; print(f"  PASS {name}")
        else: bad.append(name); print(f"  FAIL {name} {extra}")

    def u(fname):
        return "http://127.0.0.1:%d/%s" % (PORT, urllib.parse.quote(fname))

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)

        # ---------- Case A: 正式版在沙箱 iframe ----------
        pg = b.new_page(viewport={"width": 1000, "height": 900})
        host = pathlib.Path(OUT) / "_host_sbx.html"
        host.write_text('<!DOCTYPE html><html><body><iframe id="f" sandbox="allow-scripts" '
                        'src="%s" style="width:960px;height:860px;border:0"></iframe></body></html>' % u("公众号日报-精读版-2026-10-15-1228.html"),
                        encoding="utf-8")
        console_errs = []
        pg.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)
        page_errors = []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.goto(u("_host_sbx.html"))
        pg.wait_for_timeout(2000)
        frame = next(f for f in pg.frames if f != pg.main_frame)
        try:
            frame.wait_for_selector("body", timeout=5000)
        except Exception:
            pass

        # A1: 沙箱黄条提示出现 (style.background 归一化为 rgb)
        yellow = frame.evaluate("""() => {
          const els = Array.from(document.querySelectorAll('div'));
          return els.some(d => (d.style.background||'').indexOf('165, 106, 0') >= 0);
        }""")
        check("沙箱环境黄条提示出现", yellow)
        # A2: 无 JS 错误(加载后 2s 内)
        check("沙箱环境无 pageerror", len(page_errors) == 0, str(page_errors[:2]))
        check("沙箱环境无 console error", len([e for e in console_errs if "favicon" not in e]) == 0, str(console_errs[:2]))
        # A3: 划线链路(内存降级)——先开阅读弹层(两级架构: 正文在 storehouse) → 选区→工具条→批注→保存→高亮
        opened = frame.evaluate("""() => {
          const li = document.querySelector('#recView .gitem[data-key], #alist li[data-key]:not(.nobody), .gitem');
          if(!li) return false;
          li.click();
          return !!document.querySelector('#rdBody .paper');
        }""")
        check("沙箱内打开阅读弹层", opened)
        pg.wait_for_timeout(500)   # 等弹层布局稳定：立即取 rect 会拿到中间态，滚动错位→选区落视口外→readSel 视口校验拦下（旧版无校验时此处是“视口外弹条”假绿）
        # 滚动到目标节点居中(readSel 有视口校验: 选区不可见不弹条——直接 scrollTo 300 会把首节点留在视口外)
        frame.evaluate("""() => {
          const paper = document.querySelector('#rdBody .paper');
          const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
          let t = w.nextNode();
          while(t && t.nodeValue.trim().length < 40) t = w.nextNode();
          const rb = document.querySelector('#rdBody');
          const er = t.parentElement.getBoundingClientRect();
          const br = rb.getBoundingClientRect();
          rb.scrollTo({top: rb.scrollTop + er.top - br.top - br.height/2, behavior: 'instant'});
        }""")
        pg.wait_for_timeout(250)
        frame.evaluate("""() => {
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
        pg.wait_for_timeout(400)
        bar = frame.evaluate("() => { const b = document.querySelector('#selbar'); return b && (!b.hidden && getComputedStyle(b).display !== 'none'); }")
        check("沙箱内划线工具条弹出", bar)
        if bar:
            frame.click("#selbar button[data-a='note']")
            pg.wait_for_timeout(300)
            ed = frame.evaluate("() => { const e = document.querySelector('#editor'); return e && (!e.hidden && getComputedStyle(e).display !== 'none'); }")
            check("沙箱内编辑器弹出", ed)
            frame.fill("#edNote", "沙箱环境批注")
            frame.click("#edSave")
            pg.wait_for_timeout(500)
            mk = frame.evaluate("() => document.querySelectorAll('#rdBody .paper mark.hl').length")
            cnt = frame.evaluate("() => { const c = document.querySelector('#rdBody .hlpanel .cnt'); return c ? c.textContent : '-'; }")
            check("沙箱内保存→高亮+面板计数(内存模式)", mk == 1 and cnt == "1", f"mark {mk} cnt {cnt}")
        # A4: 内存数据不持久——重新打开(新 iframe 会话)后无高亮
        pg.evaluate("() => { const f = document.getElementById('f'); f.src = f.src; }")
        pg.wait_for_timeout(2000)
        frame2 = next(f for f in pg.frames if f != pg.main_frame)
        mk2 = frame2.evaluate("() => document.querySelectorAll('#rdBody .paper mark.hl').length")
        check("沙箱内数据不持久(刷新后无高亮)", mk2 == 0, f"mark {mk2}")

        # ---------- Case B: 诊断版在沙箱 iframe 无红条 ----------
        host.write_text('<!DOCTYPE html><html><body><iframe id="f" sandbox="allow-scripts" '
                        'src="%s" style="width:960px;height:860px;border:0"></iframe></body></html>' % u("公众号日报-精读版-2026-10-15-诊断版.html"),
                        encoding="utf-8")
        pg.reload()
        pg.wait_for_timeout(2000)
        frame3 = next(f for f in pg.frames if f != pg.main_frame)
        red = frame3.evaluate("() => !!document.getElementById('_derr')")
        check("诊断版沙箱内无红条", not red)

        # ---------- Case C: 非沙箱(file://)不受影响——既有 80/80 覆盖, 这里抽检加载无错 ----------
        pg2 = b.new_page()
        errs2 = []
        pg2.on("pageerror", lambda e: errs2.append(str(e)))
        pg2.goto(u("公众号日报-精读版-2026-10-15-1228.html"))
        pg2.wait_for_timeout(1500)
        check("http直开无 pageerror", len(errs2) == 0, str(errs2[:2]))

        host.unlink()
        b.close()
    httpd.shutdown()

    print()
    total = ok + len(bad)
    print(f"沙箱专项 {ok}/{total}")
    if bad:
        print("失败项:", bad)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
