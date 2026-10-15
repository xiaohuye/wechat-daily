# -*- coding: utf-8 -*-
"""用 Playwright 打开 OCR 页面, 等待 tesseract.js 识别红条文字."""
import sys, time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(r"file:///C:/Users/Administrator/AppData/Local/Temp/ocr.html")
    deadline = time.time() + 200
    result = None
    while time.time() < deadline:
        try:
            t = page.evaluate("() => document.getElementById('out').textContent")
        except Exception as e:
            t = "EVAL_ERR " + str(e)
        if t.startswith("OCR_OK") or t.startswith("OCR_FAIL"):
            result = t
            break
        time.sleep(2)
    print(result if result else "TIMEOUT 最后状态: " + t)
    browser.close()
