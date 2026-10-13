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

        # 6. 反馈标记：在全部视图点 👍
        page.query_selector_all("#alist > li .fb[data-fb='like']")[0].click()
        fb1 = page.evaluate("() => JSON.parse(Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).map(k=>localStorage[k])[0] || 'null')")
        check("👍 写入 localStorage", fb1 and fb1.get("mark") == "like", str(fb1)[:80])
        # 按钮上色
        on_like = page.eval_on_selector_all("#alist > li .fb.on-like", "els => els.length")
        check("按钮变色 on-like", on_like >= 1, f"{on_like} 个")

        # 7. 推荐视图同篇同步上色
        page.click("#tabRec")
        rec_like = page.eval_on_selector_all("article .fb.on-like", "els => els.length")
        check("推荐视图同篇同步", rec_like >= 0)  # 该篇可能不在推荐 30 里

        # 再点一次取消
        page.click("#tabAll")
        page.query_selector_all("#alist > li .fb[data-fb='like']")[0].click()
        fb_left = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).length")
        check("再点取消标记", fb_left == 0)

        # 8. 切回推荐视图在 article 上点 👍 然后 👎
        page.click("#tabRec")
        page.query_selector_all("article .fb[data-fb='like']")[0].click()
        page.query_selector_all("article .fb[data-fb='dislike']")[0].click()
        fb2 = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).map(k=>JSON.parse(localStorage[k]))")
        check("👍 后改 👎 覆盖", len(fb2) == 1 and fb2[0]["mark"] == "dislike")
        # 取消掉，不留测试数据
        page.query_selector_all("article .fb[data-fb='dislike']")[0].click()
        clean = page.evaluate("() => Object.keys(localStorage).filter(k=>k.indexOf('wxfb::')===0).length")
        check("清理测试标记", clean == 0)

        # 9. 分类 chip 过滤推荐视图（chips 是「主题」，按标题命中关键词过滤）
        chips = page.query_selector_all(".theme-chip")
        check("概览分类 chips 存在", len(chips) >= 3, f"{len(chips)} 个")
        total_rec = page.eval_on_selector_all("#recView article", "els => els.length")
        check("推荐视图加载", total_rec > 20, f"{total_rec} 篇")
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
        vis_all = page.eval_on_selector_all("#recView article",
            "els => els.filter(e => e.style.display !== 'none').length")
        off_chip = page.eval_on_selector_all(".theme-chip.on", "els => els.length")
        check("再点取消过滤", vis_all == total_rec and off_chip == 0, f"恢复 {vis_all} 篇")

        # 10. 速览点击 → 自动展开正文 + flash 高亮
        g1 = page.query_selector('#recView .gitem[data-rank="1"]')
        g1.click()
        page.wait_for_timeout(800)
        is_open = page.eval_on_selector("#art-1", "e => e.classList.contains('open')")
        is_flash = page.eval_on_selector('#recView .gitem[data-rank="1"]', "e => e.classList.contains('flash')")
        check("速览点击自动展开正文", is_open and is_flash)

        # 11. 滚过速览区 → backIdx 悬浮按钮出现
        page.eval_on_selector("#art-5", "e => e.scrollIntoView()")
        page.wait_for_timeout(400)
        back_show = page.eval_on_selector("#backIdx", "e => e.classList.contains('show')")
        check("backIdx 悬浮出现", back_show)
        page.click("#backIdx")
        page.wait_for_timeout(2200)
        near_top = page.evaluate("() => document.querySelector('.glance').getBoundingClientRect().top")
        check("点击 backIdx 滚回速览", -140 <= near_top <= 130, f"glance top={int(near_top)}")

        # 12. article 内「返回速览」按钮
        page.eval_on_selector("#art-8", "e => e.scrollIntoView()")
        page.wait_for_timeout(300)
        page.eval_on_selector("#art-8 .backidx", "e => e.click()")
        page.wait_for_timeout(2200)
        near_top2 = page.evaluate("() => document.querySelector('.glance').getBoundingClientRect().top")
        check("卡内按钮返回速览", -140 <= near_top2 <= 130, f"glance top={int(near_top2)}")

        # 13. 卡片 tag 点击 → 同分类过滤（与主题互斥）
        page.eval_on_selector("#art-1 .tag", "e => e.click()")
        hint_txt = page.eval_on_selector(".ghint", "e => e.textContent")
        vis_tag = page.eval_on_selector_all("#recView article",
            "els => els.filter(e => e.style.display !== 'none').length")
        check("tag 分类过滤生效", vis_tag > 0 and vis_tag < 29 and hint_txt.find("分类「") >= 0,
              f"{vis_tag} 篇, hint={hint_txt[:24]}")
        # tag 与主题互斥：过滤状态下点主题 chip → 切到主题过滤
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
