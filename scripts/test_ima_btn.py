# -*- coding: utf-8 -*-
"""test_ima_btn.py — 页面「☁ 存入 ima」按钮端到端测试"""
import os, sys, json, time, socket, subprocess

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
PORT = 8931
HL_FILE = os.path.join(PY_DIR, "data", "highlights.json")


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

    # 用户真实划线备份（mock 的 flushQueue 可能触达 highlights.json）
    hl_backup = open(HL_FILE, encoding="utf-8").read() if os.path.exists(HL_FILE) else None
    proc = None

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.goto("file:///" + html.replace("\\", "/"))

        # 1. 找到「批注入库」按钮
        btn = page.query_selector('button:has-text("🖍 批注入库")')
        check("页面存在「🖍 批注入库」按钮", btn is not None)

        # 2. 注入两条测试划线到 art-1（模拟用户划过线）
        key = page.eval_on_selector("#art-1", "e => e.dataset.key")
        page.evaluate("""([k]) => {
          localStorage.setItem('wxhl::' + k, JSON.stringify([
            {id:'t1', start:10, end:60, text:'（按钮链路测试）第一条测试划线句子。', note:'测试批注A', ts:Date.now()},
            {id:'t2', start:80, end:140, text:'（按钮链路测试）第二条测试划线句子。', note:'', ts:Date.now()}
          ]));
        }""", [key])
        # 拉起 mock 同步服务（自管理：/save 直接过、不落盘产生垃圾笔记）
        proc = subprocess.Popen([PY, os.path.join(PY_DIR, "scripts", "ima_sync.py"),
                                 "--mock", "--idle", "0"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not wait_port():
            print("FAIL | mock 服务 10s 内未就绪")
            sys.exit(2)
        # 服务在线 → 点按钮应直发（"正在写入 ima…"）
        btn.click()
        t0 = page.wait_for_selector(".toast.show")
        txt0 = t0.text_content()
        check("划线后才有内容可存", "ima" in txt0 or "正在" in txt0, txt0[:30])
        page.wait_for_timeout(1800)

        # 3. 等待写入完成，捕获 toast
        page.wait_for_selector(".toast.show", timeout=8000)
        time.sleep(1.5)
        toasts = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        ok_toast = [t for t in toasts if "已存入" in t or "失败" in t or "连不上" in t]
        check("写入完成提示", len(ok_toast) > 0, (ok_toast[0] if ok_toast else "无")[:44])

        # 4. 防重：再点一次应提示无新增
        page.wait_for_timeout(500)
        btn.click()
        t2 = page.wait_for_selector(".toast.show")
        txt2 = t2.text_content()
        check("再点提示无新增（防重）", "没有需要新增" in txt2, txt2[:30])

        # 5. 清理测试划线与已存标记
        page.evaluate("([k]) => { localStorage.removeItem('wxhl::'+k); localStorage.removeItem('wximsaved::'+k); }", [key])
        check("清理测试数据", True)
        b.close()

    if proc:
        proc.terminate()

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
