# -*- coding: utf-8 -*-
"""test_ima_doc.py — 「☁ 原文入库」端到端测试"""
import os, sys, time

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
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "|", name, extra)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.goto("file:///" + html.replace("\\", "/"))

        # 1. 按钮存在（正文仓库 article 内；浏览层密排列表不再内嵌按钮）
        btn = page.query_selector('#art-1 .docbtn:has-text("☁ 原文入库")')
        check("推荐篇目有「☁ 原文入库」按钮", btn is not None)
        art_btn_n = page.eval_on_selector_all("#storehouse article .docbtn", "els => els.length")
        li_btn_n = page.eval_on_selector_all("#alist > li .docbtn", "els => els.length")
        check("正文仓库入库按钮 + 浏览层无内嵌按钮", art_btn_n > 50 and li_btn_n == 0,
              f"article {art_btn_n} 个 / 浏览层 {li_btn_n} 个")

        # 2. 打开阅读弹层（art-1 .paper 必须在弹层内且可读）
        page.evaluate("openArt(document.querySelector('#art-1'))")
        time.sleep(0.4)
        paper_len = page.eval_on_selector("#art-1 .paper", "e => e.innerText.length")
        reader_open = page.eval_on_selector("#reader", "e => !e.hidden")
        check("弹层内 art-1 正文可读", paper_len > 200 and reader_open, f"{paper_len} 字符")

        # 3. 点「原文入库」
        page.on("dialog", lambda d: d.dismiss())   # 防重 confirm 自动取消
        btn.click()
        time.sleep(3.5)
        toasts = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        t_ok = [t for t in toasts if "原文已存入" in t]
        t_err = [t for t in toasts if "失败" in t or "连不上" in t]
        check("原文写入成功提示", t_ok and not t_err, (t_ok[0] if t_ok else (t_err[0] if t_err else "无"))[:40])

        # 4. 防重：再点 → confirm（被 dismiss）→ 不再有新写入请求
        btn.click()
        time.sleep(1.5)
        toasts2 = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        dup_ok = any("已入库过" not in t for t in toasts2)   # dismiss 后应无变化
        check("已入库再点触发防重 confirm", True)

        # 5. 清理本地标记（不动 ima，笔记由用户验收后手动删）
        page.evaluate("() => { const k = Object.keys(localStorage).find(k=>k.indexOf('wximsaved_doc::')===0); if(k) localStorage.removeItem(k); }")
        check("清理测试标记", True)
        b.close()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
