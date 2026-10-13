# -*- coding: utf-8 -*-
"""diag_failed.py — 诊断 5 篇取不到正文的真实原因"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weread_content import CONTENT_JS, find_exe, PROFILE

from playwright.sync_api import sync_playwright

KEYS = [
    ("赛博禅心", "已预约！", "MP_WXS_3934419561_WR11MBEQKBTSAGrAaPELTFXQ42FFqSCU56R627SDHi2pn28T1aq5LNG5M6hQ9N8CA9DHBFVA7J1"),
    ("孤独大脑", "赌一口气，值多少钱？", "MP_WXS_2398022876_WR1AfIF5X2wmEYzAL95YE0iCBNv7sl3Fv8YN0O8AKsCzq3nJAYd82Z97p7mmFLj5YwD5JCX21CF"),
    ("生财有术", "用AI赚钱的红利赛道，强烈推荐你看看亦仁分享的这3个超级标。", "MP_WXS_3891906515_WR1FrWAAK0GUFP75CO7fHAjr3f7D7tGSJ1VgBOLFh86cr54H6lsCz118R6Uf48x7ztFGY0hvGmK"),
]

with sync_playwright() as pw:
    b = pw.chromium.launch_persistent_context(PROFILE, executable_path=find_exe(), headless=True)
    pg = b.pages[0] if b.pages else b.new_page()
    pg.goto("https://weread.qq.com/")
    for acc, title, rid in KEYS:
        r = pg.evaluate(CONTENT_JS, rid)
        if not r.get("ok"):
            print(f"[{acc}] 接口失败: {r.get('err')}")
            continue
        h = r["html"]
        has_js = 'id="js_content"' in h
        # 删除/违规提示特征
        deleted = any(x in h for x in ["该内容已被发布者删除", "此内容因违规", "已删除", "环境异常", "参数错误"])
        # 视频号/音频特征
        import re
        m = re.search(r'<meta property="og:(?:url|title)" content="([^"]*)"', h)
        og = m.group(1)[:70] if m else "(无 og)"
        # js_content 内部样本
        i = h.find('id="js_content"')
        sample = h[i:i+600].replace("\n", " ") if i >= 0 else "(无 js_content)"
        n_img = h.count('data-src') if has_js else 0
        print(f"[{acc} | {title[:20]}] len={r['len']:,} js_content={'有' if has_js else '无'} "
              f"疑似删除/违规={'是' if deleted else '否'} imgs={n_img}")
        print(f"   og: {og}")
        print(f"   js_content 片段: {sample[:300]}")
        print()
    b.close()
