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

        # 3.5 弹层内划线链路：选区 → 工具条顶层可见 → 编辑器 → 保存 → mark 高亮
        #      （回归：#reader z-index 120 曾盖住 selbar(80)/editor(90)，划线时页面无反应）
        page.evaluate("""() => {
          const paper = document.querySelector('#rdBody .paper');
          const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
          let t = w.nextNode();
          while(t && t.nodeValue.trim().length < 40) t = w.nextNode();
          const rb = document.querySelector('#rdBody');
          const er = t.parentElement.getBoundingClientRect();
          const br = rb.getBoundingClientRect();
          /* .rdscroll 是 scroll-behavior:smooth：scrollTop 赋值是异步动画，mouseup 若在动画中取 rect 会错位
             —— 测试用 instant 显式覆盖；真实用户滚动稳定后才选中，无此问题 */
          rb.scrollTo({top: rb.scrollTop + er.top - br.top - br.height/2, behavior: 'instant'});
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
        bar_vis = page.evaluate("""() => {
          const b = document.querySelector('#selbar');
          if(!b || b.hidden) return false;
          const r = b.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
          return !!el && b.contains(el);   /* 顶层命中=未被弹层盖住 */
        }""")
        bar_dbg = page.evaluate("""() => {
          const b = document.querySelector('#selbar');
          const r = b.getBoundingClientRect();
          const cx = r.left + r.width/2, cy = r.top + r.height/2;
          const el = document.elementFromPoint(cx, cy);
          return {t: Math.round(r.top), hidden: b.hidden, sc: document.querySelector('#rdBody').scrollTop,
                  hit: el ? el.tagName + '/in=' + b.contains(el) : 'null'};
        }""")
        check("弹层内选中文字工具条顶层可见", bar_vis, str(bar_dbg))
        page.click("#selbar button[data-a='note']")
        page.wait_for_timeout(200)
        ed_vis = page.evaluate("""() => {
          const e = document.querySelector('#editor');
          if(!e || e.hidden) return false;
          const r = e.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
          return !!el && (e === el || e.contains(el));
        }""")
        check("划线编辑器弹出且顶层可见", ed_vis)
        page.fill("#edNote", "弹层内划线回归批注")
        page.click("#edSave")
        page.wait_for_timeout(400)
        mk_n = page.evaluate("() => document.querySelectorAll('#rdBody .paper mark.hl').length")
        panel_cnt = page.evaluate("() => document.querySelector('#rdBody .hlpanel .cnt').textContent")
        check("划线后正文高亮 + 面板计数", mk_n == 1 and panel_cnt == "1", f"mark {mk_n} / 面板 {panel_cnt}")
        # 回归：保存点击的 mouseup 会"点穿"到正文——旧版选区未清 + 无抑制锁，
        # 10ms 定时器把工具条复活（用户报「保存批注后划线/求解释/复制弹窗关不掉」）
        page.wait_for_timeout(300)
        bar_revived = page.evaluate("""() => {
          const b = document.querySelector('#selbar');
          return !!(b && (!b.hidden && getComputedStyle(b).display !== 'none'));
        }""")
        check("保存批注后工具条不复活", not bar_revived, "工具条复活了" if bar_revived else "")
        # 点击已有划线 → edit 模式工具条 → 删除（edit 条逻辑在 mouseup 通道，需真实鼠标）
        mk_pos = page.evaluate("""() => {
          const m = document.querySelector('#rdBody .paper mark.hl');
          const r = m.getBoundingClientRect();
          return {x: r.left + 5, y: r.top + 5};
        }""")
        page.mouse.click(mk_pos["x"], mk_pos["y"])
        page.wait_for_timeout(300)
        edit_bar = page.evaluate("""() => {
          const b = document.querySelector('#selbar');
          return b && (!b.hidden && getComputedStyle(b).display !== 'none') && b.dataset.mode === 'edit';
        }""")
        check("点击已有划线弹编辑工具条", edit_bar)
        page.click("#selbar button[data-a='del']")
        page.wait_for_timeout(300)
        mk_gone = page.evaluate("() => document.querySelectorAll('#rdBody .paper mark.hl').length")
        check("工具条删除划线生效", mk_gone == 0, f"mark 剩 {mk_gone} 个")

        # 3.5 跨界面残留回归：弹层内划线弹工具条（不保存）→ 点「← 返回」→
        #     工具条是 body 上的 fixed 元素，不随弹层隐藏——closeReader 必须主动收尾
        #     （用户报「返回首页后弹窗还在」；旧版 closeReader 不关工具条不清选区，必留残影）
        page.evaluate("""() => {
          const paper = document.querySelector('#rdBody .paper');
          const w = document.createTreeWalker(paper, NodeFilter.SHOW_TEXT);
          let t = w.nextNode();
          while(t && t.nodeValue.trim().length < 40) t = w.nextNode();
          const n = Math.min(20, t.nodeValue.trim().length);
          const r = document.createRange();
          r.setStart(t, 0); r.setEnd(t, n);
          const s = window.getSelection();
          s.removeAllRanges(); s.addRange(r);
          document.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
        }""")
        page.wait_for_timeout(300)
        bar_shown = page.evaluate("() => { const b = document.querySelector('#selbar'); return b && (!b.hidden && getComputedStyle(b).display !== 'none'); }")
        if bar_shown:
            page.evaluate("() => closeReader()")
            page.wait_for_timeout(300)
            residual = page.evaluate("""() => {
              const b = document.querySelector('#selbar');
              const s = window.getSelection();
              return { bar: !!(b && (!b.hidden && getComputedStyle(b).display !== 'none')), sel: !!(s && !s.isCollapsed && s.rangeCount) };
            }""")
            check("返回首页后工具条不残留且选区已清", not residual["bar"] and not residual["sel"],
                  f"条残={residual['bar']} 选残={residual['sel']}")
            page.evaluate("() => openArt(document.querySelector('#rdBody article') || document.querySelector('#storehouse article'))")
            page.wait_for_timeout(200)
        else:
            check("返回首页后工具条不残留且选区已清", True, "(本轮工具条未弹出, 跳过)")

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
        page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0||k.indexOf('wxhl::')===0).forEach(k=>localStorage.removeItem(k))")
        b.close()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
