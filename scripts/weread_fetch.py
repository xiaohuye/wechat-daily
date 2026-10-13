# -*- coding: utf-8 -*-
"""
weread_fetch.py — 通过持久化浏览器批量抓取「我关注的公众号」的最新文章

复用 weread_login.py 建立的登录态（data/weread_profile），
在页面内同源调用微信读书内部接口，无需处理 cookie。

输出: data/articles-weread-<时间戳>.json

用法:
    python scripts/weread_fetch.py                  # 默认每个号抓 1 页(20篇)，过滤最近 3 天
    python scripts/weread_fetch.py --pages 2 --days 7
    python scripts/weread_fetch.py --all            # 不过滤时间
"""
import os, sys, json, time, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "wechat_accounts.json")
PROFILE = os.path.join(ROOT, "data", "weread_profile")
DATA = os.path.join(ROOT, "data")
EXE_CANDIDATES = [
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
    r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe",
]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36")
TZ = datetime.timezone(datetime.timedelta(hours=8))

FETCH_JS = """async (args) => {
  const [bid, off] = args;
  try {
    const r = await fetch(`/web/mp/articles?bookId=${bid}&offset=${off}`, {credentials:'include'});
    return await r.json();
  } catch(e) { return {__err: String(e)}; }
}"""


def find_exe():
    for p in EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("未找到 Chromium 可执行文件")


def clean_title(t):
    """清洗标题：接口偶尔会把正文混进 title，取首个换行前的部分并限长"""
    t = (t or "").strip()
    if not t:
        return ""
    t = t.split("\n")[0].split("\r")[0].strip()
    if len(t) > 100:
        t = t[:100].rstrip() + "…"
    return t


def parse(d):
    """从接口回包中提取文章条目"""
    out = []
    for rv in (d.get("reviews") or []):
        subs = rv.get("subReviews")
        candidates = subs if subs else [rv]
        for s in candidates:
            r = s.get("review") or {}
            mp = r.get("mpInfo") or {}
            if not mp:
                continue
            oid = mp.get("originalId") or ""
            out.append({
                "account": mp.get("mp_name") or "",
                "title": clean_title(mp.get("title")),
                "digest": (mp.get("content") or "").strip(),
                "ts": int(mp.get("time") or r.get("createTime") or 0),
                "read_num": mp.get("readNum"),
                "like_num": mp.get("likeNum"),
                # 注意：originalId 无法拼成可打开的公众号链接（会「参数错误」），
                # 真实链接在 weread_content.py 抓正文时从 og:url 补全。
                "url": "",
                "internal_id": oid,
                "review_id": r.get("reviewId") or "",
                "cover": mp.get("pic_url") or "",
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1, help="每个号抓几页，每页约 20 篇")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 个号（调试用）")
    ap.add_argument("--sleep", type=float, default=0.35, help="每次请求间隔秒数")
    args = ap.parse_args()

    accounts = json.load(open(CONFIG, encoding="utf-8"))["accounts"]
    if args.limit:
        accounts = accounts[:args.limit]

    from playwright.sync_api import sync_playwright

    all_items, failed = [], []
    t0 = time.time()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, executable_path=find_exe(), headless=True,
            viewport={"width": 1400, "height": 900}, user_agent=UA, locale="zh-CN")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://weread.qq.com/", timeout=60000)
        pg.wait_for_timeout(2000)

        # 登录态检查
        chk = pg.evaluate(FETCH_JS, ["MP_WXS_2398602260", 0])
        if isinstance(chk, dict) and chk.get("errCode") == -2010:
            print("!! 登录已失效，请先运行: python scripts/weread_login.py")
            ctx.close()
            sys.exit(3)   # 3 = 登录态失效，供 run_daily.sh / 定时任务识别

        for i, a in enumerate(accounts, 1):
            got, err = [], None
            for pgno in range(args.pages):
                d = pg.evaluate(FETCH_JS, [a["book_id"], pgno * 20])
                if isinstance(d, dict) and d.get("__err"):
                    err = d["__err"]; break
                if isinstance(d, dict) and d.get("errCode"):
                    err = f"errCode={d['errCode']} {d.get('errMsg','')}"; break
                rows = parse(d)
                if not rows:
                    break
                got.extend(rows)
                time.sleep(args.sleep)
            if err:
                failed.append({"account": a["name"], "error": err})
                print(f"[{i:3}/{len(accounts)}] {a['name']}: 失败 {err}", flush=True)
            else:
                all_items.extend(got)
                print(f"[{i:3}/{len(accounts)}] {a['name']}: {len(got)} 篇", flush=True)

        ctx.close()

    # 去重
    seen, uniq = set(), []
    for x in all_items:
        k = (x["account"], x["title"], x["url"])
        if k not in seen and x["title"]:
            seen.add(k); uniq.append(x)

    # 时间过滤
    if not args.all:
        cutoff = int((datetime.datetime.now(TZ) - datetime.timedelta(days=args.days)).timestamp())
        uniq = [x for x in uniq if x["ts"] >= cutoff]

    uniq.sort(key=lambda k: -k["ts"])
    for x in uniq:
        x["time"] = datetime.datetime.fromtimestamp(x["ts"], TZ).strftime("%Y-%m-%d %H:%M")

    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, datetime.datetime.now(TZ).strftime("articles-weread-%Y-%m-%d-%H%M.json"))
    json.dump({"generated_at": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
               "source": "weread /web/mp/articles", "accounts": len(accounts),
               "window_days": 0 if args.all else args.days,
               "total": len(uniq), "failed": failed, "articles": uniq},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n共 {len(uniq)} 篇（失败 {len(failed)} 个号，耗时 {time.time()-t0:.0f}s）-> {out}")


if __name__ == "__main__":
    main()
