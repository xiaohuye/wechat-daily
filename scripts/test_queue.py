# -*- coding: utf-8 -*-
"""test_queue.py — 离线暂存 + 按需唤醒自动同步 + 闲置退出 全流程测试

服务以 --mock 启动：不真实写 ima（避免测试产生垃圾笔记），只验证链路与生命周期。
等待逻辑全部为轮询（不依赖 toast 的 2.2s 显示时效，也不受 watcher 15s 轮询相位影响）。
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
    proc = None

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto("file:///" + html.replace("\\", "/"))

        # 0. 注入一条划线（服务离线状态）
        key = page.eval_on_selector("#art-1", "e => e.dataset.key")
        page.evaluate("""([k]) => {
          localStorage.setItem('wxhl::' + k, JSON.stringify([
            {id:'q1', start:5, end:60, text:'队列测试划线：分层记忆架构与混合检索。', note:'队列批注', ts:Date.now()}
          ]));
        }""", [key])

        # 1. 离线：批注入库 → 暂存
        page.click('button:has-text("🖍 批注入库")')
        t = page.wait_for_selector(".toast.show")
        qn1 = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
        check("离线批注入库→暂存", "暂存" in t.text_content() and qn1 == 1, t.text_content()[:26])

        # 2. 离线：原文入库 → 暂存（confirm 自动接受）
        page.evaluate("openArt(document.querySelector('#art-1'))")
        time.sleep(0.3)
        page.click('#art-1 button:has-text("☁ 原文入库")')
        time.sleep(1.5)
        qn2 = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
        check("离线原文入库→暂存", qn2 == 2, f"队列 {qn2} 条")

        # 3. 离线：划线 → 自动回灌入队（防抖 2s，无按钮，saveHL 真实入口）
        page.evaluate("""([k]) => saveHL(k, [
          {id:'q1', start:5, end:60, text:'队列测试划线：分层记忆架构与混合检索。', note:'队列批注', ts:Date.now()}
        ])""", [key])
        time.sleep(2.8)
        qn3 = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
        check("离线划线自动回灌→暂存", qn3 == 3, f"队列 {qn3} 条")

        # 4. 同篇再划 → 队列按 key 收敛不重复
        page.evaluate("""([k]) => saveHL(k, [
          {id:'q1', start:5, end:60, text:'队列测试划线：分层记忆架构与混合检索。', note:'队列批注', ts:1},
          {id:'q2', start:70, end:120, text:'第二条划线：任务分解与失败恢复。', note:'', ts:2}
        ])""", [key])
        time.sleep(2.8)
        qn4 = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
        hl_n = page.evaluate("() => { const q = JSON.parse(localStorage.getItem('wxqueue')||'[]');"
                            " const e = q.find(x => x.kind==='save_highlights');"
                            " return e ? e.payload.items[0].highlights.length : 0; }")
        check("同篇重复划线收敛仍 1 条", qn4 == 3 and hl_n == 2, f"队列仍 {qn4} 条/划线 {hl_n} 条")

        # 5. 拉起 mock 服务（--idle 12s）→ 页面开着，15s 轮询内自动探测冲刷
        proc = subprocess.Popen([PY, os.path.join(PY_DIR, "scripts", "ima_sync.py"),
                                 "--mock", "--idle", "12"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(1)                       # 等 Python 进程起来、bind 完成
        flushed = False
        for i in range(30):                # 轮询最多 30s：覆盖 15s watcher 周期任意相位 + 发送耗时
            time.sleep(1)
            qn = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
            if qn == 0 and os.path.exists(HL_FILE):
                try:
                    d = json.load(open(HL_FILE, encoding="utf-8"))
                except Exception:
                    continue
                if key in d.get("articles", {}):
                    flushed = True
                    break
        check("服务唤醒后自动冲刷（30s 内队列自动清空）", flushed)

        # 6. 队列终态干净
        qn5 = page.evaluate("() => JSON.parse(localStorage.getItem('wxqueue')||'[]').length")
        check("队列清空", qn5 == 0, f"剩 {qn5} 条")

        # 7. 冲刷后补写防重标记（下次点按钮不会重复排队）
        if flushed:
            m1 = page.evaluate("k => localStorage.getItem('wximsaved::' + k)", key)
            m2 = page.evaluate("k => localStorage.getItem('wximsaved_doc::' + k)", key)
            check("冲刷后补写批注防重标记", m1 is not None)
            check("冲刷后补写原文防重标记", bool(m2))
        else:
            check("冲刷后补写批注防重标记", False, "未冲刷")
            check("冲刷后补写原文防重标记", False, "未冲刷")

        # 8. 服务闲置自动退出（12s 无业务请求；ping 探测不得阻止退出）
        exited = False
        for i in range(20):                # idle 12s + watchdog 5s 检查周期 + 余量
            time.sleep(1)
            if proc.poll() is not None:
                exited = True
                break
        check("服务闲置自动退出", exited, f"poll={proc.poll()}")
        if not exited:
            proc.kill()
        b.close()

    # 还原现场
    if hl_backup is not None:
        open(HL_FILE, "w", encoding="utf-8").write(hl_backup)
    check("还原测试数据", True)

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
