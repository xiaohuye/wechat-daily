# -*- coding: utf-8 -*-
"""test_kw_sync.py — 「🧠 回灌划线」按钮端到端测试"""
import os, sys, time, json

PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = None
for p in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(p):
        CHROME = p
        break

HL_FILE = os.path.join(PY_DIR, "data", "highlights.json")
TEST_KEY = "测试|回灌按钮测试篇"

def main():
    from playwright.sync_api import sync_playwright
    html = os.path.join(PY_DIR, "output", "公众号日报-精读版-2026-10-13-1309.html")
    results = []
    def check(name, cond, extra=""):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "|", name, extra)

    # 备份现有 highlights.json（不破坏真实划线数据）
    backup = None
    if os.path.exists(HL_FILE):
        backup = open(HL_FILE, encoding="utf-8").read()

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, executable_path=CHROME)
        page = b.new_page()
        page.goto("file:///" + html.replace("\\", "/"))

        btn = page.query_selector('button:has-text("🧠 回灌划线")')
        check("页面存在「🧠 回灌划线」按钮", btn is not None)

        # 1. 无划线点按钮 → 提示
        btn.click()
        t = page.wait_for_selector(".toast.show")
        check("无划线提示", "还没有任何划线" in t.text_content(), t.text_content()[:20])

        # 2. 注入两条划线（一条带批注）
        key = page.eval_on_selector("#art-2", "e => e.dataset.key")
        page.evaluate("""([k]) => {
          localStorage.setItem('wxhl::' + k, JSON.stringify([
            {id:'k1', start:5, end:66, text:'企业级 Agent 记忆系统需要分层设计与混合检索。', note:'分层设计是重点', ts:Date.now()},
            {id:'k2', start:80, end:150, text:'编排框架要考虑任务分解与失败恢复。', note:'', ts:Date.now()}
          ]));
        }""", [key])
        btn.click()
        time.sleep(3)
        toasts = page.eval_on_selector_all(".toast", "els => els.map(e=>e.textContent)")
        ok = [t for t in toasts if "已回灌" in t]
        err = [t for t in toasts if "失败" in t or "连不上" in t]
        check("回灌成功提示", ok and not err, (ok[0] if ok else "无")[:40])

        # 3. 落盘验证：highlights.json 含该篇
        d = json.load(open(HL_FILE, encoding="utf-8"))
        hit = key in d.get("articles", {}) and len(d["articles"][key]["highlights"]) == 2
        check("落盘包含该篇划线", hit, f"{len(d.get('articles', {}))} 篇")
        b.close()

    # 4. 还原现场：删测试篇、恢复备份
    if backup is not None:
        open(HL_FILE, "w", encoding="utf-8").write(backup)
    else:
        d = json.load(open(HL_FILE, encoding="utf-8"))
        d.get("articles", {}).pop(key, None)
        json.dump(d, open(HL_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    check("还原测试数据", True)

    fails = [r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} 通过")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
