# -*- coding: utf-8 -*-
"""test_auto_sync.py — 划线/反馈自动保存全流程测试

验证：划线增删(saveHL)后 2s 防抖自动回灌、fbMark 后自动同步反馈、队列按 kind+ded 收敛、
徽章状态流转；服务在线时自动直发落盘（mock，不真实写 ima），feedback.json 与 wx_rank.load_feedback 兼容。
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


def q(page):
    return page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]')")


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
    proc = None

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto("file:///" + html.replace("\\", "/"))

        k1 = page.eval_on_selector("#art-1", "e => e.dataset.key")
        k2 = page.eval_on_selector("#art-2", "e => e.dataset.key")

        # 1. 头部重组：旧手动按钮已删，徽章存在
        has_old = page.evaluate("""() => ['回灌划线','导出反馈'].some(t =>
            Array.from(document.querySelectorAll('.bar button')).some(b => b.textContent.indexOf(t) >= 0))""")
        badge_el = page.query_selector("#syncBadge")
        check("头部旧按钮已删且徽章存在", (not has_old) and badge_el is not None)

        # 2. 划线(saveHL 真实入口) → 2s 防抖 → 自动入队（离线）
        page.evaluate("""([k]) => saveHL(k, [
          {id:'a1', start:5, end:66, text:'自动同步测试：分层记忆与混合检索是 Agent 演进的两大主线。', note:'重点', ts:Date.now()}
        ])""", [k1])
        time.sleep(2.8)
        e1 = [e for e in q(page) if e["kind"] == "save_highlights"]
        check("划线后自动入队（防抖 2s）", len(e1) == 1, f"{len(e1)} 条")

        # 3. 同篇再划一条 → 队列按 key 收敛仍 1 条
        page.evaluate("""([k]) => saveHL(k, [
          {id:'a1', start:5, end:66, text:'自动同步测试：分层记忆与混合检索。', note:'重点', ts:1},
          {id:'a2', start:80, end:150, text:'第二条：任务分解与失败恢复同样关键。', note:'', ts:2}
        ])""", [k1])
        time.sleep(2.8)
        e2 = [e for e in q(page) if e["kind"] == "save_highlights"]
        n_hl = len(e2[0]["payload"]["items"][0]["highlights"]) if e2 else 0
        check("同篇收敛且内容为最新", len(e2) == 1 and n_hl == 2, f"{len(e2)} 条/{n_hl} 划线")

        # 4. 👍 → 立即自动入队反馈（全量单条）——fb 按钮在阅读弹层内
        page.evaluate("openArt(document.querySelector('#art-1'))")
        time.sleep(0.3)
        page.click('#art-1 .fb[data-fb="like"]')
        time.sleep(1.5)
        fb1 = [e for e in q(page) if e["kind"] == "save_feedback"]
        ok4 = len(fb1) == 1 and fb1[0]["payload"]["feedback"][0]["mark"] == "like"
        check("点赞后反馈自动入队", ok4, f"{len(fb1)} 条")

        # 5. 改 👎 → 全量替换仍 1 条且 mark 更新
        page.click('#art-1 .fb[data-fb="dislike"]')
        time.sleep(1.5)
        fb2 = [e for e in q(page) if e["kind"] == "save_feedback"]
        ok5 = len(fb2) == 1 and fb2[0]["payload"]["feedback"][0]["mark"] == "dislike"
        check("改踩后反馈收敛为最新", ok5, f"{len(fb2)} 条")

        # 6. 徽章显示待同步数
        txt6 = page.eval_on_selector("#syncBadge", "e => e.textContent")
        check("徽章显示待同步", "待同步" in txt6, txt6.strip()[:20])

        # 7. 拉起 mock 服务 → 划线在线直发落盘（不走队列）
        proc = subprocess.Popen([PY, os.path.join(PY_DIR, "scripts", "ima_sync.py"),
                                 "--mock", "--idle", "0"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(1.5)
        page.evaluate("""([k]) => saveHL(k, [
          {id:'b1', start:10, end:88, text:'在线直发测试：反馈闭环让推荐持续贴合兴趣。', note:'', ts:Date.now()}
        ])""", [k2])
        time.sleep(3.0)
        hit7 = False
        if os.path.exists(HL_FILE):
            d = json.load(open(HL_FILE, encoding="utf-8"))
            hit7 = k2 in d.get("articles", {})
        check("服务在线划线自动直发落盘", hit7)

        # 8. 👍 在线直发 → feedback.json 落盘 + wx_rank.load_feedback 兼容
        page.evaluate("openArt(document.querySelector('#art-2'))")
        time.sleep(0.3)
        page.click('#art-2 .fb[data-fb="like"]')
        time.sleep(2.0)
        ok8 = False
        if os.path.exists(FB_FILE):
            d = json.load(open(FB_FILE, encoding="utf-8"))
            marks = {f["key"]: f["mark"] for f in d.get("feedback", [])}
            ok8 = marks.get(k1) == "dislike" and marks.get(k2) == "like"
        check("反馈落盘且取消/覆盖语义正确", ok8)
        # load_feedback 结构兼容
        sys.path.insert(0, os.path.join(PY_DIR, "scripts"))
        from wx_rank import load_feedback
        art_fb, acc_adj, _ = load_feedback()
        check("wx_rank.load_feedback 兼容", art_fb.get(k2) == "like" and art_fb.get(k1) == "dislike",
              f"{len(art_fb)} 篇反馈")

        # 9. 徽章恢复「已自动同步」（离线残留队列被 watcher 自动冲刷）
        flushed = False
        for _ in range(22):
            time.sleep(1)
            if len(q(page)) == 0:
                flushed = True
                break
        txt9 = page.eval_on_selector("#syncBadge", "e => e.textContent") if flushed else ""
        check("残留队列自动冲刷且徽章恢复", flushed and "已自动同步" in txt9, txt9.strip()[:16])

        if proc and proc.poll() is None:
            proc.kill()
        b.close()

    # 还原现场
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
