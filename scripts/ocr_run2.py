# -*- coding: utf-8 -*-
"""本地HTTP服务 + Playwright 跑 tesseract.js OCR 红条文字."""
import subprocess, sys, time, os
from playwright.sync_api import sync_playwright

TMP = r"C:\Users\Administrator\AppData\Local\Temp"
PORT = 8944

# 检查图片就绪
img = os.path.join(TMP, "dbar_ocr2.png")
if not os.path.exists(img):
    print("缺少 dbar_ocr2.png"); sys.exit(1)

# 启动 http 服务
proc = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", TMP],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(f"http://127.0.0.1:{PORT}/ocr.html")
        deadline = time.time() + 240
        result = None
        while time.time() < deadline:
            try:
                t = page.evaluate("() => document.getElementById('out').textContent")
            except Exception as e:
                t = ""
            if t.startswith("OCR_OK") or t.startswith("OCR_FAIL"):
                result = t
                break
            time.sleep(2)
        print(result if result else "TIMEOUT")
        b.close()
finally:
    proc.terminate()
