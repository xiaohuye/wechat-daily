# -*- coding: utf-8 -*-
"""把「腾讯WorkBuddy FDE人才培养计划」纯图片型文章拼接为一张长图。"""
import json
import re
import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

DATA = "data/articles-full-weread-2026-10-25-0901.json"
KEY = "腾讯云开发者|腾讯WorkBuddy FDE人才培养计划暨FDE精英班正式启动"
OUT = "output/腾讯WorkBuddy-FDE人才培养计划-长图.png"
TMP = "tmp/fde"

W = 1080
PAD = 56          # 左右留白
GAP = 0           # 图片间距（原文图片自带留白，无需额外间隙）
HDR_BG = (255, 255, 255)
TITLE_C = (26, 26, 26)
META_C = (140, 140, 140)
LINE_C = (232, 232, 232)


def pick_font(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


FONT_B = ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc"]
FONT_R = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"]


def main():
    art = json.load(open(DATA, encoding="utf-8"))["articles"][KEY]
    title, account, date = art["title"], art["account"], art.get("time", "")

    imgs = re.findall(r'<img[^>]+src="([^"]+)"', art["content_html"])
    os.makedirs(TMP, exist_ok=True)
    hdr_req = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": "https://mp.weixin.qq.com/",
    }
    paths = []
    for i, u in enumerate(imgs, 1):
        p = os.path.join(TMP, f"{i:02d}.jpg")
        if not (os.path.exists(p) and os.path.getsize(p) > 10000):
            r = requests.get(u.replace("&amp;", "&"), headers=hdr_req, timeout=30)
            r.raise_for_status()
            open(p, "wb").write(r.content)
        paths.append(p)

    tiles = [Image.open(p).convert("RGB") for p in paths]
    tiles = [t.resize((W, round(t.height * W / t.width)), Image.LANCZOS) if t.width != W else t for t in tiles]

    body_h = sum(t.height for t in tiles) + GAP * (len(tiles) - 1)

    # ---- header 尺寸测算 ----
    f_title = pick_font(FONT_B, 52)
    f_meta = pick_font(FONT_R, 30)
    tmp = Image.new("RGB", (W, 10), HDR_BG)
    d = ImageDraw.Draw(tmp)

    def tokenize(text):
        """把连续 ASCII 字母数字（含 . - _）视为不可拆分的最小单元，避免 FDE 被拦腰截断。"""
        out, buf = [], ""
        for ch in text:
            if ch.isascii() and (ch.isalnum() or ch in ".-_"):
                buf += ch
            else:
                if buf:
                    out.append(buf)
                    buf = ""
                out.append(ch)
        if buf:
            out.append(buf)
        return out

    def wrap(text, font, maxw):
        lines, cur = [], ""
        for tk in tokenize(text):
            if d.textlength(cur + tk, font=font) <= maxw:
                cur += tk
            else:
                if cur:
                    lines.append(cur)
                cur = tk
        if cur:
            lines.append(cur)
        return lines

    tl = wrap(title, f_title, W - PAD * 2)
    lh = 52 + 26
    hdr_h = PAD + lh * len(tl) + 16 + 34 + PAD - 10

    H = hdr_h + body_h
    canvas = Image.new("RGB", (W, H), HDR_BG)
    dr = ImageDraw.Draw(canvas)

    # ---- 头部 ----
    y = PAD
    for line in tl:
        dr.text((PAD, y), line, font=f_title, fill=TITLE_C)
        y += lh
    y += 8
    meta = f"{account}　·　{date}"
    dr.text((PAD, y), meta, font=f_meta, fill=META_C)
    y += 34 + 22
    dr.line([(PAD, y), (W - PAD, y)], fill=LINE_C, width=2)

    # ---- 正文图片 ----
    y = hdr_h
    for i, t in enumerate(tiles):
        canvas.paste(t, (0, y))
        y += t.height + GAP
        if i < len(tiles) - 1 and GAP:
            y += GAP

    os.makedirs("output", exist_ok=True)
    canvas.save(OUT, "PNG", optimize=True)
    print(f"saved {OUT}")
    print(f"size {canvas.width}x{canvas.height}  {os.path.getsize(OUT)/1024/1024:.2f} MB  imgs={len(tiles)}")


if __name__ == "__main__":
    main()
