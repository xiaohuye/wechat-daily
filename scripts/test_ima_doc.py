# -*- coding: utf-8 -*-
"""test_ima_doc.py — 「☁ 原文入库」端到端测试"""
import os, sys, time, socket, subprocess

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
PORT = 8931


def port_busy():
    s = socket.socket()
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def wait_port(timeout=10):
    """轮询等待 mock 服务端口就绪（venv 冷启动可能 >1s，固定 sleep 会竞态）"""
    dl = time.time() + timeout
    while time.time() < dl:
        if port_busy():
            return True
        time.sleep(0.3)
    return False


def main():
    if port_busy():
        print(f"FAIL | 端口 {PORT} 已有服务在跑（上次测试残留？），请先关闭再测")
        sys.exit(2)

    from playwright.sync_api import sync_playwright
    html = os.path.join(PY_DIR, "output", "公众号日报-精读版-2026-10-13-1309.html")
    results = []
    def check(name, cond, extra=""):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "|", name, extra)

    proc = None
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

        # 拉起 mock 同步服务（自管理：/save_doc 直接过、不落盘）——此前该测试
        # 依赖系统里残留的外部服务才偶然全绿，清理残留后必走离线路径而 FAIL
        proc = subprocess.Popen([PY, os.path.join(PY_DIR, "scripts", "ima_sync.py"),
                                 "--mock", "--idle", "0"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not wait_port():
            print("FAIL | mock 服务 10s 内未就绪")
            sys.exit(2)

        # 3. 点「原文入库」（服务在线 → 直发 → "✓ 原文已存入 ima"）
        page.on("dialog", lambda d: d.dismiss())   # 防重 confirm 自动取消
        btn.click()
        time.sleep(3.5)
        toasts = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        t_ok = [t for t in toasts if "原文已存入" in t]
        t_err = [t for t in toasts if "失败" in t or "连不上" in t]
        check("原文写入成功提示", bool(t_ok) and not t_err, (t_ok[0] if t_ok else (t_err[0] if t_err else "无"))[:40])

        # 4. 防重：再点 → confirm（被 dismiss）→ 无重复写入（toast 文字应保持不变）
        t_before = page.eval_on_selector(".toast", "e => e.textContent")
        btn.click()
        time.sleep(1.5)
        t_after = page.eval_on_selector(".toast", "e => e.textContent")
        check("已入库再点触发防重 confirm 且无重复写入", t_before == t_after and "原文已存入" in t_after)

        # 5. 清理本地标记（不动 ima，笔记由用户验收后手动删）
        page.evaluate("() => { const k = Object.keys(localStorage).find(k=>k.indexOf('wximsaved_doc::')===0); if(k) localStorage.removeItem(k); }")
        check("清理测试标记", True)
        b.close()

    if proc:
        proc.terminate()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
