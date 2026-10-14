# -*- coding: utf-8 -*-
"""test_reader.py — 两级架构（浏览层模块化 + 阅读弹层）回归测试

验证：深色 Top3 精选、storehouse 正文仓库（浏览层无内嵌正文）、
弹层打开/关闭/Esc/换篇归位、密排全部视图、旧 backIdx 体系移除。
"""
import os, sys

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break

def main():
    from playwright.sync_api import sync_playwright
    html = os.path.join(PY_DIR, "output", "公众号日报-精读版-2026-10-14-1100.html")
    results = []
    def check(name, cond, extra=""):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "|", name, extra)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto("file:///" + html.replace("\\", "/"))

        # 1. 浏览层结构：Top3 深色区 + 榜单 + storehouse + 无内嵌正文
        t3 = page.evaluate("() => document.querySelectorAll('.dark-top .t3card').length")
        sh = page.evaluate("() => document.querySelectorAll('#storehouse article').length")
        gitem_n = page.evaluate("() => document.querySelectorAll('#recView .gitem').length")
        shx = page.evaluate("() => !!document.querySelector('#storehouse-x')")
        inline_arts = page.evaluate("() => Array.from(document.querySelectorAll('#recView article')).filter(a=>a.offsetParent!==null).length")
        check("深色 Top3 精选卡", t3 == 3, f"{t3} 张")
        check("storehouse 正文仓库=榜单+额外篇目", sh >= gitem_n and not shx,
              f"storehouse {sh} / 榜单 {gitem_n}, storehouse-x 已移除={not shx}")
        check("浏览层无内嵌正文", inline_arts == 0, f"可见 article {inline_arts} 个")

        # 2. 速览条目点击 → 阅读弹层
        page.evaluate("() => document.querySelector('.gitem[data-rank=\"1\"]').click()")
        page.wait_for_timeout(400)
        vis = page.evaluate("() => !document.querySelector('#reader').hidden")
        title = page.evaluate("() => document.querySelector('#rdTitle').textContent")
        in_reader = page.evaluate("() => !!document.querySelector('#rdBody #art-1')")
        paper_vis = page.evaluate("() => { const p = document.querySelector('#rdBody .paper'); return !!p && p.offsetParent !== null; }")
        check("速览点击打开弹层", vis, title[:24])
        check("article 已移入弹层且正文可见", in_reader and paper_vis)

        # 3. 弹层内 fb 按钮可用（测试结束统一清理）
        page.click("#rdBody #art-1 .fb[data-fb='like']")
        page.wait_for_timeout(600)
        fbk = page.evaluate("() => { const a = document.querySelector('#rdBody #art-1'); return !!localStorage.getItem('wxfb::' + a.dataset.key); }")
        check("弹层内反馈按钮工作", fbk)

        # 4. 弹层开着换篇：openArt 另一篇 → 旧篇归位 storehouse，rdBody 唯一
        swap = page.evaluate("""() => {
          const cur = document.querySelector('#rdBody article');
          const nxt = Array.from(document.querySelectorAll('#storehouse article')).find(a => a !== cur);
          if(!cur || !nxt) return null;
          const prevId = cur.id;
          openArt(nxt);
          return { prev: prevId, now: nxt.id };
        }""")
        page.wait_for_timeout(300)
        n_in_body = page.evaluate("() => document.querySelectorAll('#rdBody article').length")
        prev_back = page.evaluate("([s]) => !!document.querySelector('#storehouse #' + s.prev)", [swap]) if swap else False
        now_in = page.evaluate("([s]) => !!document.querySelector('#rdBody #' + s.now)", [swap]) if swap else False
        check("弹层换篇旧篇归位", bool(swap) and n_in_body == 1 and prev_back and now_in,
              f"prev 归位={prev_back}, rdBody {n_in_body} 篇")

        # 5. Esc 关闭弹层 → article 回仓库
        page.evaluate("() => document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))")
        page.wait_for_timeout(300)
        closed = page.evaluate("() => document.querySelector('#reader').hidden")
        back_home = page.evaluate("""() => {
          const els = document.querySelectorAll('#rdBody article');
          return els.length === 0 && document.querySelectorAll('#storehouse article').length > 0;
        }""")
        body_unlocked = page.evaluate("() => !document.body.classList.contains('reading')")
        check("Esc 关闭弹层且正文归位", closed and back_home and body_unlocked)

        # 6. 全部视图密排 + 点击进弹层
        page.evaluate("() => setView('all')")
        page.wait_for_timeout(300)
        grid = page.evaluate("() => getComputedStyle(document.querySelector('#alist')).display")
        lis = page.evaluate("() => document.querySelectorAll('#alist li[data-key]:not([data-nobody])').length")
        li_has_ops = page.evaluate("() => !!document.querySelector('#alist .ops')")
        check("全部视图密排 grid", grid == "grid", f"display={grid}, {lis} 条可点")
        check("li 无旧按钮组", not li_has_ops)
        page.evaluate("() => document.querySelector('#alist li[data-key]:not([data-nobody])').click()")
        page.wait_for_timeout(400)
        allvis = page.evaluate("() => !document.querySelector('#reader').hidden")
        rd_in = page.evaluate("() => document.querySelectorAll('#rdBody article').length")
        check("密排条目点击进弹层", allvis and rd_in == 1, f"rdBody {rd_in} 篇")
        page.evaluate("() => closeReader()")

        # 7. 旧 backIdx 体系已移除 + 清理测试反馈
        nobackidx = page.evaluate("() => !document.querySelector('#backIdx')")
        check("backIdx 悬浮已移除", nobackidx)
        page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).forEach(k=>localStorage.removeItem(k))")
        b.close()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
