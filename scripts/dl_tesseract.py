# -*- coding: utf-8 -*-
"""通过 Chromium 页面网络栈下载 tesseract.js 全套文件(走与 page.goto 相同的通路)."""
import base64, os

TMP = r"C:\Users\Administrator\AppData\Local\Temp\tesseract"
FILES = {
    "tesseract.min.js": ("text", "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"),
    "worker.min.js": ("text", "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/worker.min.js"),
    "tesseract-core-simd.wasm.js": ("text", "https://cdn.jsdelivr.net/npm/tesseract.js-core@5/tesseract-core-simd.wasm.js"),
    "tesseract-core.wasm.js": ("text", "https://cdn.jsdelivr.net/npm/tesseract.js-core@5/tesseract-core.wasm.js"),
    "eng.traineddata.gz": ("bin", "https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng/1.0.0/eng.traineddata.gz"),
}

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    for name, (kind, url) in FILES.items():
        if kind == "text":
            js = page.evaluate("u => fetch(u).then(r => r.text())", url)
            with open(os.path.join(TMP, name), "w", encoding="utf-8", newline="") as f:
                f.write(js)
            print(name, len(js), "chars")
        else:
            b64 = page.evaluate(
                "u => fetch(u).then(r => r.arrayBuffer()).then(b => { const u8 = new Uint8Array(b);"
                " let s = ''; const CH = 0x8000;"
                " for(let i=0;i<u8.length;i+=CH){ s += String.fromCharCode.apply(null, u8.subarray(i, i+CH)); }"
                " return btoa(s); })", url)
            data = base64.b64decode(b64)
            with open(os.path.join(TMP, name), "wb") as f:
                f.write(data)
            print(name, len(data), "bytes")
    b.close()
print("全部下载完成")
