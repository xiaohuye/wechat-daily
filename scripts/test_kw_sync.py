# -*- coding: utf-8 -*-
"""test_kw_sync.py — 同步徽章「立即全量同步」端到端测试（原「🧠 回灌划线」按钮的替代链路）

验证：syncAllNow 把全部划线+反馈全量推到本地服务；highlights.json / feedback.json 落盘；
服务用 --mock 自管理（不真实写 ima）。
"""
import os, sys, time, json, socket, subprocess

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break
PY = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

HL_FILE = os.path.join(PY_DIR, "data", "highlights.json")
FB_FILE = os.path.join(PY_DIR, "data", "feedback.json")
PORT = 8931


def port_busy():
    s = socket.socket()
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


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

    hl_backup = open(HL_FILE, encoding="utf-8").read() if os.path.exists(HL_FILE) else None
    fb_backup = open(FB_FILE, encoding="utf-8").read() if os.path.exists(FB_FILE) else None

    proc = subprocess.Popen([PY, os.path.join(PY_DIR, "scripts", "ima_sync.py"),
                             "--mock", "--idle", "0"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1.5)

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.goto("file:///" + html.replace("\\", "/"))

        badge = page.query_selector("#syncBadge")
        check("页面存在同步状态徽章", badge is not None)

        # 1. 无划线无反馈点徽章 → 提示
        badge.click()
        t = page.wait_for_selector(".toast.show")
        check("无内容点徽章提示", "先读一篇" in t.text_content(), t.text_content()[:20])

        # 2. 注入两条划线 + 一条 👍（saveHL/fbMark 真实入口）
        key = page.eval_on_selector("#art-2", "e => e.dataset.key")
        page.evaluate("""([k]) => saveHL(k, [
          {id:'k1', start:5, end:66, text:'企业级 Agent 记忆系统需要分层设计与混合检索。', note:'分层设计是重点', ts:Date.now()},
          {id:'k2', start:80, end:150, text:'编排框架要考虑任务分解与失败恢复。', note:'', ts:Date.now()}
        ])""", [key])
        # fb 按钮在阅读弹层内：先打开 art-2 弹层，点赞后关弹层露出头部徽章
        page.evaluate("openArt(document.querySelector('#art-2'))")
        time.sleep(0.3)
        page.click('#art-2 .fb[data-fb="like"]')
        page.keyboard.press("Escape")
        time.sleep(0.3)

        # 3. 点徽章 → 全量同步 → toast + 两个文件落盘
        time.sleep(0.5)
        page.click("#syncBadge")
        time.sleep(3)
        toasts = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        ok = [t for t in toasts if "全量同步" in t]
        check("全量同步提示", len(ok) > 0, (ok[0] if ok else "无")[:40])

        d = json.load(open(HL_FILE, encoding="utf-8"))
        hit = key in d.get("articles", {}) and len(d["articles"][key]["highlights"]) == 2
        check("highlights.json 落盘该篇划线", hit, f"{len(d.get('articles', {}))} 篇")

        d = json.load(open(FB_FILE, encoding="utf-8"))
        marks = {f["key"]: f["mark"] for f in d.get("feedback", [])}
        check("feedback.json 落盘该篇反馈", marks.get(key) == "like", f"{len(marks)} 条")
        b.close()

    if proc and proc.poll() is None:
        proc.kill()

    # 4. 还原现场
    if hl_backup is not None:
        open(HL_FILE, "w", encoding="utf-8").write(hl_backup)
    elif os.path.exists(HL_FILE):
        os.remove(HL_FILE)
    if fb_backup is not None:
        open(FB_FILE, "w", encoding="utf-8").write(fb_backup)
    elif os.path.exists(FB_FILE):
        os.remove(FB_FILE)
    check("还原测试数据", True)

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
