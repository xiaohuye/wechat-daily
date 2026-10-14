# -*- coding: utf-8 -*-
"""test_ui.py — 精读日报交互冒烟测试（筛选/排序/反馈标记）"""
import os, sys, json

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break

def main():
    from playwright.sync_api import sync_playwright
    html = os.path.join(PY_DIR, "output", "公众号日报-精读版-2026-10-13-1309.html")
    results = []

    def check(name, cond, extra=""):
        results.append((name, bool(cond), extra))
        print(("PASS" if cond else "FAIL"), "|", name, extra)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.goto("file:///" + html.replace("\\", "/"))

        # 1. 切到全部视图
        page.click("#tabAll")
        check("切到全部更新视图", "mode-all" in (page.get_attribute("body", "class") or ""))

        lis = page.query_selector_all("#alist > li")
        total = len(lis)
        check("全部清单加载", total > 50, f"{total} 篇")

        # 2. 分类筛选
        page.select_option("#typeFilter", "AI 产品与工具实践")
        n_type = page.eval_on_selector_all("#alist > li",
            "els => els.filter(e => e.style.display !== 'none').length")
        check("分类=AI 产品与工具实践", n_type > 0 and n_type < total, f"{n_type}/{total}")
        # 验证隐藏的都是非该类
        wrong = page.eval_on_selector_all("#alist > li",
            "els => els.filter(e => e.style.display !== 'none' && e.dataset.type !== 'AI 产品与工具实践').length")
        check("非该类全部隐藏", wrong == 0)

        # 3. 叠加评分筛选
        page.select_option("#scoreFilter", "3.5")
        n_score = page.eval_on_selector_all("#alist > li",
            "els => els.filter(e => e.style.display !== 'none').length")
        allpass = page.eval_on_selector_all("#alist > li",
            "els => els.filter(e => e.style.display !== 'none' && parseFloat(e.dataset.score||0) < 3.5).length")
        check("叠加评分≥3.5", n_score > 0 and n_score <= n_type, f"{n_score} 篇")
        check("低于3.5全部隐藏", allpass == 0)

        # 4. 阅读量筛选 + 排序
        page.select_option("#readFilter", "5000")
        page.select_option("#sortBy", "read")
        first_rn = page.eval_on_selector("#alist > li:first-child", "e => e.dataset.rn")
        check("按阅读量降序（首个 rn）", int(first_rn or 0) >= 5000, f"rn={first_rn}")

        # 5. 重置
        page.click("text=⟲ 重置")
        n_reset = page.eval_on_selector_all("#alist > li",
            "els => els.filter(e => e.style.display !== 'none').length")
        check("重置后恢复全量", n_reset == total, f"{n_reset}/{total}")

        # 6. 反馈标记：全部视图点条目 → 打开阅读弹层 → 弹层内点 👍
        page.query_selector_all("#alist > li:not([data-nobody])")[0].click()
        page.wait_for_timeout(400)
        reader_open = page.eval_on_selector("#reader", "e => !e.hidden")
        has_paper = page.eval_on_selector("#rdBody article", "e => !!e.querySelector('.paper')")
        check("列表条目点击打开阅读弹层", reader_open and has_paper)
        page.click("#rdBody .fb[data-fb='like']")
        fb1 = page.evaluate("() => JSON.parse(Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).map(k=>localStorage[k])[0] || 'null')")
        check("👍 写入 localStorage", fb1 and fb1.get("mark") == "like", str(fb1)[:80])
        on_like = page.eval_on_selector_all("#rdBody .fb.on-like", "els => els.length")
        check("按钮变色 on-like", on_like >= 1, f"{on_like} 个")

        # 7. 返回按钮关弹层 → 正文归位 storehouse，标记保留
        page.click(".rdclose")
        page.wait_for_timeout(300)
        rd_hidden = page.eval_on_selector("#reader", "e => e.hidden")
        rec_like = page.eval_on_selector_all("#storehouse article .fb.on-like", "els => els.length")
        check("关闭弹层正文归位且标记保留", rd_hidden and rec_like >= 1, f"on-like {rec_like} 个")

        # 8. 重新打开弹层再点一次取消
        page.query_selector_all("#alist > li:not([data-nobody])")[0].click()
        page.wait_for_timeout(400)
        page.click("#rdBody .fb[data-fb='like']")
        fb_left = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).length")
        check("再点取消标记", fb_left == 0)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 9. 推荐视图打开弹层：👍 后改 👎 覆盖语义
        page.click("#tabRec")
        page.evaluate("() => gotoArt(1)")
        page.wait_for_timeout(400)
        page.click("#rdBody .fb[data-fb='like']")
        page.click("#rdBody .fb[data-fb='dislike']")
        fb2 = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).map(k=>JSON.parse(localStorage[k]))")
        check("👍 后改 👎 覆盖", len(fb2) == 1 and fb2[0]["mark"] == "dislike")
        # 取消掉，不留测试数据
        page.click("#rdBody .fb[data-fb='dislike']")
        clean = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).length")
        check("清理测试标记", clean == 0)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 10. 分类 chip 过滤推荐榜单（chips 作用于浏览层榜单条目）
        chips = page.query_selector_all(".theme-chip")
        check("概览分类 chips 存在", len(chips) >= 3, f"{len(chips)} 个")
        total_rec = page.eval_on_selector_all("#recView .gitem", "els => els.length")
        check("推荐榜单加载", total_rec > 20, f"{total_rec} 篇")
        chips[0].click()
        chip_name = chips[0].get_attribute("data-tname")
        vis_g = page.eval_on_selector_all("#recView .gitem",
            "els => els.filter(e => e.style.display !== 'none').length")
        wrong_g = page.eval_on_selector_all("#recView .gitem",
            f"els => els.filter(e => e.style.display !== 'none' && (',' + e.dataset.themes + ',').indexOf(',{chip_name},') < 0).length")
        on_chip = page.eval_on_selector_all(".theme-chip.on", "els => els.length")
        check("chip 主题过滤生效", vis_g > 0 and wrong_g == 0 and on_chip == 1,
              f"「{chip_name}」: {vis_g} 篇命中")
        # 再点取消
        chips[0].click()
        vis_all = page.eval_on_selector_all("#recView .gitem",
            "els => els.filter(e => e.style.display !== 'none').length")
        off_chip = page.eval_on_selector_all(".theme-chip.on", "els => els.length")
        check("再点取消过滤", vis_all == total_rec and off_chip == 0, f"恢复 {vis_all} 篇")

        # 11. 速览点击 → 打开阅读弹层 + flash 高亮
        g1 = page.query_selector('#recView .gitem[data-rank="1"]')
        g1.click()
        page.wait_for_timeout(800)
        is_open = page.eval_on_selector("#reader", "e => !e.hidden")
        paper_ok = page.eval_on_selector("#rdBody article", "e => !!e.querySelector('.paper')")
        is_flash = page.eval_on_selector('#recView .gitem[data-rank="1"]', "e => e.classList.contains('flash')")
        check("速览点击打开阅读弹层", is_open and paper_ok and is_flash)

        # 12. Esc 关闭弹层 → 正文归位 storehouse
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        esc_hidden = page.eval_on_selector("#reader", "e => e.hidden")
        art_back = page.eval_on_selector_all("#storehouse article .paper", "els => els.length")
        check("Esc 关闭弹层正文归位", esc_hidden and art_back > 20, f"storehouse 正文 {art_back} 篇")

        # 13. 深色精选 Top3 卡片 → 点击打开弹层
        t3 = page.query_selector_all(".t3card")
        check("今日精选 Top3 存在", len(t3) == 3, f"{len(t3)} 张")
        t3[1].click()
        page.wait_for_timeout(400)
        t3_open = page.eval_on_selector("#reader", "e => !e.hidden")
        t3_title = page.eval_on_selector("#rdTitle", "e => e.textContent.slice(0, 20)")
        check("精选卡点击打开弹层", t3_open, f"标题={t3_title}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 14. 弹层内 tag 点击 → 浏览层榜单同分类过滤（与主题互斥）
        page.evaluate("() => gotoArt(1)")
        page.wait_for_timeout(300)
        page.eval_on_selector("#rdBody article .tag", "e => e.click()")
        hint_txt = page.eval_on_selector(".ghint", "e => e.textContent")
        vis_tag = page.eval_on_selector_all("#recView .gitem",
            "els => els.filter(e => e.style.display !== 'none').length")
        check("tag 分类过滤生效", vis_tag > 0 and vis_tag < total_rec and hint_txt.find("分类「") >= 0,
              f"{vis_tag} 篇, hint={hint_txt[:24]}")
        # 关闭弹层回浏览层，tag 与主题互斥：过滤状态下点主题 chip → 切到主题过滤
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if len(chips) > 1:
            chips[1].click()
            page.wait_for_timeout(200)
            hint_txt2 = page.eval_on_selector(".ghint", "e => e.textContent")
            check("主题/分类过滤互斥", hint_txt2.find("主题「") >= 0, hint_txt2[:24])

        b.close()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
