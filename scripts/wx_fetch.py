# -*- coding: utf-8 -*-
"""
wx_fetch.py — 抓取已关注公众号的最新推文

用法:
    python scripts/wx_fetch.py                 # 默认抓最近 2 天
    python scripts/wx_fetch.py --days 3        # 抓最近 3 天
    python scripts/wx_fetch.py --all           # 不过滤时间，每个号取最新 N 条

输出:
    data/articles-YYYY-MM-DD-HHMM.json
仅依赖 Python 标准库。
"""
import json, os, re, sys, html, time, argparse
import urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "accounts.json")
DATA = os.path.join(ROOT, "data")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
TZ = timezone(timedelta(hours=8))


def http_get(url, timeout=30, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, application/rss+xml, */*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5)
    raise last


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\u00a0]+")


def html_to_text(h):
    if not h:
        return ""
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</p>|</div>|</h\d>", "\n", h, flags=re.I)
    h = _TAG.sub(" ", h)
    h = html.unescape(h)
    h = _WS.sub(" ", h)
    lines = [ln.strip() for ln in h.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def snippet(text, n=260):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")


def extract_time(item, fallback_ts):
    """尽量从条目里取发布时间，取不到用抓取时间兜底。"""
    for k in ("date_published", "date_modified"):
        if item.get(k):
            try:
                return datetime.fromisoformat(item[k].replace("Z", "+00:00")).astimezone(TZ)
            except Exception:
                pass
    # 微信正文里常带 "2026-10-09 19:24"
    m = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})[日\s]+(\d{1,2}):(\d{2})",
                  html_to_text(item.get("content_html", ""))[:400])
    if m:
        try:
            y, mo, d, hh, mm = map(int, m.groups())
            return datetime(y, mo, d, hh, mm, tzinfo=TZ)
        except Exception:
            pass
    return datetime.fromtimestamp(fallback_ts, TZ)


def fetch_account(acc, days, limit):
    """返回该公众号的文章列表（JSON Feed 或 RSS 自动识别）。"""
    url = acc.get("url")
    raw = http_get(url)
    now_ts = time.time()
    cutoff = datetime.now(TZ) - timedelta(days=days)
    items = []
    try:
        data = json.loads(raw)
        for it in data.get("items", [])[:limit]:
            body = html_to_text(it.get("content_html") or it.get("summary") or "")
            dt = extract_time(it, now_ts)
            items.append({
                "account": acc["name"], "tag": acc.get("tag", ""),
                "title": (it.get("title") or "").strip(),
                "url": it.get("url") or it.get("external_url") or "",
                "time": dt.strftime("%Y-%m-%d %H:%M"),
                "ts": int(dt.timestamp()),
                "digest": snippet(body),
            })
    except json.JSONDecodeError:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        for it in root.iter("item"):
            def t(tag):
                el = it.find(tag)
                return (el.text or "") if el is not None else ""
            body = html_to_text(t("{http://purl.org/rss/1.0/modules/content/}encoded") or t("description"))
            dt = extract_time({"content_html": body}, now_ts)
            items.append({
                "account": acc["name"], "tag": acc.get("tag", ""),
                "title": t("title").strip(), "url": t("link"),
                "time": dt.strftime("%Y-%m-%d %H:%M"), "ts": int(dt.timestamp()),
                "digest": snippet(body),
            })
    if days:
        items = [x for x in items if datetime.fromtimestamp(x["ts"], TZ) >= cutoff]
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--all", action="store_true", help="不按时间过滤")
    ap.add_argument("--limit", type=int, default=15, help="每个号最多取多少条")
    args = ap.parse_args()

    accounts = json.load(open(CONFIG, encoding="utf-8"))
    days = 0 if args.all else args.days
    all_items, failed = [], []
    for i, acc in enumerate(accounts, 1):
        try:
            got = fetch_account(acc, days, args.limit)
            all_items.extend(got)
            print(f"[{i:2}/{len(accounts)}] {acc['name']}: {len(got)} 条")
        except Exception as e:  # noqa
            failed.append({"account": acc["name"], "error": str(e)})
            print(f"[{i:2}/{len(accounts)}] {acc['name']}: 失败 {e}")

    # 去重 + 按时间倒序
    seen, uniq = set(), []
    for x in sorted(all_items, key=lambda k: -k["ts"]):
        key = (x["account"], x["title"])
        if key not in seen:
            seen.add(key)
            uniq.append(x)

    os.makedirs(DATA, exist_ok=True)
    out = os.path.join(DATA, datetime.now(TZ).strftime("articles-%Y-%m-%d-%H%M.json"))
    json.dump({
        "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "window_days": days, "total": len(uniq),
        "failed": failed, "articles": uniq,
    }, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n共 {len(uniq)} 篇（失败 {len(failed)} 个源）-> {out}")


if __name__ == "__main__":
    main()
