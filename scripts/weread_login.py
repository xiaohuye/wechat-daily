# -*- coding: utf-8 -*-
"""
weread_login.py — 用持久化浏览器完成一次微信读书网页登录

原理: 用一个独立 Chromium 打开 weread.qq.com，你扫码登录，
      登录态保存在 data/weread_profile（Chromium 自己加密管理，无需解密 cookie）。
      之后 weread_fetch.py 直接复用该 profile 调内部接口。

用法:
    python scripts/weread_login.py            # 交互等待扫码（最长 6 分钟）
    python scripts/weread_login.py --check    # 只检查当前是否已登录
"""
import os, sys, time, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, "data", "weread_profile")
QR = os.path.join(ROOT, "output", "weread_qr.png")
STATUS = os.path.join(ROOT, "data", "weread_login_status.txt")

EXE_CANDIDATES = [
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe",
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36")

PROBE_JS = """async () => {
  try {
    const r = await fetch('/web/mp/articles?bookId=MP_WXS_2398602260&offset=0', {credentials:'include'});
    const j = await r.json();
    return j.errCode === undefined || j.errCode === 0 ? 'IN' : 'OUT';
  } catch(e) { return 'ERR'; }
}"""


def find_exe():
    for p in EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("未找到 Chromium 可执行文件")


def log(msg):
    print(msg, flush=True)
    try:
        open(STATUS, "w", encoding="utf-8").write(msg)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--timeout", type=int, default=360)
    args = ap.parse_args()

    os.makedirs(PROFILE, exist_ok=True)
    os.makedirs(os.path.dirname(QR), exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, executable_path=find_exe(), headless=True,
            viewport={"width": 1400, "height": 900}, user_agent=UA, locale="zh-CN")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://weread.qq.com/", timeout=60000)
        pg.wait_for_timeout(2500)

        if pg.evaluate(PROBE_JS) == "IN":
            log("ALREADY_LOGGED_IN")
            ctx.close()
            return

        if args.check:
            log("NOT_LOGGED_IN")
            ctx.close()
            return

        # 打开登录弹窗
        try:
            pg.get_by_text("登录", exact=True).first.click(timeout=8000)
        except Exception:
            pass
        pg.wait_for_timeout(3000)

        def snap_qr():
            try:
                img = pg.locator("[class*=qr] img").first
                img.screenshot(path=QR)
                return True
            except Exception:
                return False

        snap_qr()
        log("WAITING_QR")   # 二维码已生成到 output/weread_qr.png

        t0 = time.time()
        last_snap = time.time()
        while time.time() - t0 < args.timeout:
            st = pg.evaluate(PROBE_JS)
            if st == "IN":
                pg.wait_for_timeout(1200)
                log("LOGIN_OK")
                ctx.close()
                return
            # 每 25 秒刷新一次二维码截图（页面会自动换码）
            if time.time() - last_snap > 25:
                snap_qr()
                last_snap = time.time()
            time.sleep(3)

        log("TIMEOUT")
        ctx.close()


if __name__ == "__main__":
    main()
