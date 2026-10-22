# -*- coding: utf-8 -*-
"""
weread_content.py — 抓取文章完整正文，用于「日报内直接阅读」

原理：调用微信读书内部接口 /web/mp/content?reviewId=<id>，
      返回的是完整的公众号原文 HTML（含 js_content 正文 + 图片），
      我们从中抽出正文片段 + 真实 og:url，落盘为可直接内嵌的 HTML。

为什么不用公众号原文链接：mp.weixin.qq.com 对非微信环境返回「环境异常」人机验证，
非本人环境基本打不开；所以直接把正文搬进日报，彻底免跳转。

输入：data/ranked-weread-*.json（取其 top 列表）
输出：data/articles-full-weread-<时间戳>.json
      { "<account>|<title>": {content_html, images, links, title, account, ts, read_num, ...} }

用法：
    python scripts/weread_content.py                    # 抓最新 ranked 的 top 30
    python scripts/weread_content.py --top 10
    python scripts/weread_content.py --ids data/ids.json
"""
import os, re, sys, json, time, glob, html as _html, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, "data", "weread_profile")
DATA = os.path.join(ROOT, "data")
EXE_CANDIDATES = [
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe",
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36")
TZ = datetime.timezone(datetime.timedelta(hours=8))

CONTENT_JS = """async (rid) => {
  try {
    const r = await fetch(`/web/mp/content?reviewId=${encodeURIComponent(rid)}`, {credentials:'include'});
    const t = await r.text();
    return {ok: true, len: t.length, html: t};
  } catch(e) { return {ok: false, err: String(e)}; }
}"""

# js_content 之后的结束锚点（按优先级找）
END_ANCHORS = ['id="js_tags"', 'rich_media_area_extra', 'id="js_pc_qr_code"',
               'class="rich_media_tool"', 'id="js_article_comment"']


def find_exe():
    for p in EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("未找到 Chromium 可执行文件")


# 保留的标签（其余统一下沉为纯文本）
KEEP_TAGS = {"p", "section", "div", "span", "img", "a", "h1", "h2", "h3", "h4", "h5", "h6",
             "ul", "ol", "li", "blockquote", "strong", "em", "b", "i", "br", "hr",
             "table", "thead", "tbody", "tr", "td", "th", "figure", "figcaption", "code", "pre"}
DROP_TAGS = {"script", "style", "iframe", "noscript", "mpvoice", "mp-common-videosnap",
             "qqmusic", "mpprofile", "mpcpc", "mp-common-mpaudioplayer", "svg", "input",
             "button", "form", "object", "embed", "video", "audio"}
# 媒体/小程序占位（微信常见噪音，直接删）
DROP_SELECTORS = ["mp-common-mpaudio", ".js_mpvedio", "#js_mpvedio", ".js_article_comment",
                  ".mpa", "mpa", "mpprofile", ".js_uneditable", ".rich_media_tool"]


def clean_fragment(frag):
    """用 BeautifulSoup 彻底清洗正文：只留安全标签，去掉所有内联样式与死链。

    目的：正文要能直接扫码在手机/浏览器里舒适阅读，且体积可控。
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(frag, "lxml")
    body = soup.find("div", class_="wx-article-body") or soup

    # 1) 删除噪音标签
    for t in body.find_all(list(DROP_TAGS)):
        t.decompose()
    # 2) 删除噪音选择器
    for sel in DROP_SELECTORS:
        try:
            for t in body.select(sel):
                t.decompose()
        except Exception:
            pass
    # 3) 图片：data-src -> src，仅保留 src/alt
    for img in body.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src or src.startswith("data:"):
            img.decompose(); continue
        img.attrs = {"src": src, "alt": img.get("alt", ""), "loading": "lazy"}
    # 4) 链接：公众号外链非本人环境打不开 → 去链接保留文字；微信读书页链接也跳过
    for a in body.find_all("a"):
        a.replace_with_children() if hasattr(a, "replace_with_children") else a.unwrap()
    # 5) 其余标签：保留下沉，只留结构标签；非白名单的 unwrap（img 已在步骤3处理，跳过）
    for t in list(body.find_all(True)):
        if t.name == "img":
            continue
        if t.name not in KEEP_TAGS:
            t.unwrap()
        else:
            t.attrs = {}     # 去掉所有内联样式/属性
    # 6) 去掉空段落
    for t in body.find_all(["p", "section", "div"]):
        if not t.get_text(strip=True) and not t.find("img"):
            t.decompose()
    # 7) 连续多个 <br> 合并
    txt = str(body)
    txt = re.sub(r"(?:<br\s*/?>\s*){3,}", "<br><br>", txt)
    txt = re.sub(r"\n{2,}", "\n", txt)
    return txt.strip()


def extract_body(full_html):
    """从完整页面 HTML 中抽出正文片段，并返回 (正文, 图片列表)"""
    i = full_html.find('id="js_content"')
    if i < 0:
        return None, []
    # 回到标签起点
    start = full_html.rfind("<", 0, i)
    end = -1
    for a in END_ANCHORS:
        j = full_html.find(a, i)
        if j > 0:
            end = full_html.rfind("<", i, j)
            break
    if end < 0:
        end = i + 400000
    frag = full_html[start:end]
    # 去掉开头的 id="js_content" 属性残留 -> 保留为 div 容器
    frag = re.sub(r'^<div[^>]*id="js_content"[^>]*>', '<div class="wx-article-body">', frag, count=1)
    if not frag.startswith('<div class="wx-article-body"'):
        frag = '<div class="wx-article-body">' + frag
    frag = clean_fragment(frag)
    if not frag.rstrip().endswith("</div>"):
        frag += "</div>"
    imgs = re.findall(r'<img[^>]+src="([^"]+)"', frag)
    return frag, imgs


def meta_of(full_html):
    def g(pat):
        m = re.search(pat, full_html, re.S)
        return _html.unescape(m.group(1).strip()) if m else ""
    return {
        "real_url": g(r'property="og:url" content="(.*?)"'),
        "og_title": g(r'property="og:title" content="(.*?)"'),
        "author": g(r'<meta name="author" content="(.*?)"'),
        "desc": g(r'<meta name="description" content="(.*?)"'),
        "nickname": g(r'id="js_name"[^>]*>\s*(.*?)\s*<'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="ranked JSON（默认取最新 ranked 的 top）")
    ap.add_argument("--all", action="store_true",
                    help="全量模式：抓 articles-weread-*.json 里的每一篇（不限于推荐）")
    ap.add_argument("--articles", default=None, help="配合 --all 指定 articles-weread-*.json")
    ap.add_argument("--ids", default=None, help="直接指定 [{review_id,account,title}]")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--reuse", action="store_true",
                    help="复用已有 articles-full-weread-*.json 里抓过的正文，只补缺的（加 --all 时有用）")
    args = ap.parse_args()

    reused = {}
    reused_unreadable = {}
    if args.reuse:
        prev = sorted(glob.glob(os.path.join(DATA, "articles-full-weread-*.json")))
        for f in prev:
            try:
                dprev = json.load(open(f, encoding="utf-8"))
                reused.update(dprev.get("articles", {}))
                # 无正文记录同样累积复用，避免每天重复抓取已知不可读的文章
                for u in dprev.get("unreadable", []) or []:
                    if u.get("key"):
                        reused_unreadable[u["key"]] = u
            except Exception:
                pass
        if reused:
            print(f"复用已有正文 {len(reused)} 篇")
        if reused_unreadable:
            print(f"复用已知无正文记录 {len(reused_unreadable)} 篇")

    if args.ids:
        items = json.load(open(args.ids, encoding="utf-8"))
    elif args.all:
        af = args.articles
        if not af:
            fs = sorted(glob.glob(os.path.join(DATA, "articles-weread-*.json")))
            if not fs:
                raise SystemExit("找不到 articles-weread-*.json")
            af = fs[-1]
        d = json.load(open(af, encoding="utf-8"))
        items = d["articles"]
        print(f"源: {os.path.basename(af)}（全量）→ 共 {len(items)} 篇")
    else:
        src = args.src
        if not src:
            fs = sorted(glob.glob(os.path.join(DATA, "ranked-weread-*.json")))
            if not fs:
                raise SystemExit("找不到 ranked-weread-*.json")
            src = fs[-1]
        rk = json.load(open(src, encoding="utf-8"))
        items = rk["top"][: args.top]
        print(f"源: {os.path.basename(src)} → 取前 {len(items)} 篇")

    # 复用：过滤掉已抓过的
    out, failed, unreadable = {}, [], []
    todo = []
    for a in items:
        k = f"{a.get('account','')}|{a.get('title','')}"
        if args.reuse and k in reused and reused[k].get("content_html"):
            out[k] = reused[k]
        elif args.reuse and k in reused_unreadable:
            # 已知无文字正文：直接沿用上次记录（含原文链接/摘要），不再重复抓
            unreadable.append(reused_unreadable[k])
            failed.append({"key": k, "error": "正文为空(复用)"})
        else:
            todo.append(a)
    if args.reuse and out:
        print(f"跳过已抓 {len(out)} 篇，待抓 {len(todo)} 篇")
    items = todo

    from playwright.sync_api import sync_playwright
    t0 = time.time()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, executable_path=find_exe(), headless=True,
            viewport={"width": 1400, "height": 900}, user_agent=UA, locale="zh-CN")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://weread.qq.com/", timeout=60000)
        pg.wait_for_timeout(1500)

        for i, a in enumerate(items, 1):
            rid = a.get("review_id") or ""
            key = f"{a.get('account','')}|{a.get('title','')}"
            if not rid:
                failed.append({"key": key, "error": "no review_id"})
                print(f"[{i:3}/{len(items)}] {a.get('account')}: 缺 review_id", flush=True)
                continue
            r = pg.evaluate(CONTENT_JS, rid)
            if not isinstance(r, dict) or not r.get("ok"):
                err = r.get("err") if isinstance(r, dict) else "bad resp"
                failed.append({"key": key, "error": str(err)})
                print(f"[{i:3}/{len(items)}] {a.get('account')}: 失败 {err}", flush=True)
                continue
            body, imgs = extract_body(r["html"])
            m = meta_of(r["html"])
            if not body or len(body) < 200:
                # 无文字正文（图片型文章走 common_share 分享模板 / 纯 SVG 交互排版）。
                # 仍尽量榨取可用信息：原文链接、摘要、模板类型，供日报列表降级展示。
                page_mid = ""
                pm = re.search(r'PAGE_MID\s*=\s*"([^"]+)"', r["html"])
                if pm:
                    page_mid = pm.group(1)
                unreadable.append({
                    "key": key, "account": a.get("account", ""), "title": a.get("title", ""),
                    "time": a.get("time"), "ts": a.get("ts"),
                    "read_num": a.get("read_num"), "like_num": a.get("like_num"),
                    "real_url": m["real_url"] or a.get("url", ""),
                    "digest": a.get("digest") or m["desc"],
                    "cover": a.get("cover", ""),
                    "page_mid": page_mid,
                    "reason": ("图片型分享页" if "common_share" in page_mid else
                               "SVG交互排版" if len(body or "") < 200 else "正文为空"),
                    "text_len": len(re.sub(r"<[^>]+>", "", body or "")),
                })
                failed.append({"key": key, "error": "正文为空"})
                print(f"[{i:3}/{len(items)}] {a.get('account')}: 正文为空({len(body or '')}) "
                      f"-> 记入 unreadable（url={bool(m['real_url'])}）", flush=True)
                time.sleep(args.sleep)
                continue
            out[key] = {
                "account": a.get("account", ""), "title": a.get("title", ""),
                "ts": a.get("ts"), "time": a.get("time"),
                "read_num": a.get("read_num"), "like_num": a.get("like_num"),
                "real_url": m["real_url"], "author": m["author"] or m["nickname"],
                "digest": a.get("digest") or m["desc"],
                "image_count": len(imgs),
                "text_len": len(re.sub(r"<[^>]+>", "", body)),
                "content_html": body,
            }
            print(f"[{i:3}/{len(items)}] {a.get('account')}: {len(body)} 字符 / {len(imgs)} 图", flush=True)
            time.sleep(args.sleep)
        ctx.close()

    os.makedirs(DATA, exist_ok=True)
    stamp = datetime.datetime.now(TZ).strftime("%Y-%m-%d-%H%M")
    outf = os.path.join(DATA, f"articles-full-weread-{stamp}.json")
    json.dump({"generated_at": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
               "count": len(out), "failed": failed,
               "unreadable": unreadable, "articles": out},
              open(outf, "w", encoding="utf-8"), ensure_ascii=False)
    tot = sum(v["text_len"] for v in out.values())
    print(f"\n成功 {len(out)} 篇（失败 {len(failed)}，其中 {len(unreadable)} 篇为无文字正文的图片/交互型）"
          f"，正文合计 {tot:,} 字符，耗时 {time.time()-t0:.0f}s")
    if unreadable:
        got = sum(1 for u in unreadable if u.get("real_url"))
        print(f"  无正文条目已记录原文链接 {got}/{len(unreadable)} 条（供日报降级展示）")
    print("已存:", outf)


if __name__ == "__main__":
    main()
