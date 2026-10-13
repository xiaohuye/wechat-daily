# -*- coding: utf-8 -*-
"""
wx_report.py — 把抓取结果 + AI 分析结果渲染成一份 HTML 日报

用法:
    python scripts/wx_report.py data/articles-XXXX.json
    python scripts/wx_report.py data/articles-XXXX.json --insights data/insights-XXXX.json

insights JSON 结构（可选，没有就只出清单）:
{
  "overview": "今天整体的 2-3 句判断",
  "themes": [{"name":"主题", "desc":"一句话"}],
  "recommend": ["公众号|标题", ...],          // 推荐阅读，按优先级
  "articles": {
     "公众号|标题": {"summary":"一句话摘要","score":4,"reason":"为什么值得看"}
  }
}
"""
import json, os, sys, re, argparse, html
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
TZ = timezone(timedelta(hours=8))


def esc(s):
    return html.escape(str(s or ""), quote=True)


def build(articles_file, insights_file=None):
    data = json.load(open(articles_file, encoding="utf-8"))
    arts = data["articles"]
    ins = json.load(open(insights_file, encoding="utf-8")) if insights_file else {}

    # 用分类结果补 tag（weread 源没有 tag 字段）
    type_map = {}
    cls = os.path.join(ROOT, "config", "accounts_classified.json")
    if os.path.exists(cls):
        for r in json.load(open(cls, encoding="utf-8"))["accounts"]:
            type_map[r["name"]] = r["type"]
    for a in arts:
        if not a.get("tag"):
            a["tag"] = type_map.get(a["account"], "")

    meta = ins.get("articles", {})
    rec = ins.get("recommend", [])
    themes = ins.get("themes", [])
    overview = ins.get("overview", "")

    def key(a):
        return f"{a['account']}|{a['title']}"

    by_rec = {k: i for i, k in enumerate(rec)}

    # 统计
    per_account = {}
    for a in arts:
        per_account.setdefault(a["account"], []).append(a)

    W = []
    W.append(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>公众号日报 · {esc(data.get('generated_at','')[:10])}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--line:#e6e8eb;--ink:#1c1f23;--sub:#6b7280;--red:#e34d59;--blue:#2f6fed;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:var(--sub);font-size:13px;margin-bottom:22px}}
.stat{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}}
.stat div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;font-size:13px}}
.stat b{{font-size:19px;color:var(--blue);font-weight:700;margin-right:4px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:18px}}
.card h2{{font-size:17px;margin:0 0 12px;display:flex;align-items:center;gap:8px}}
.badge{{background:var(--red);color:#fff;font-size:11px;font-weight:700;border-radius:6px;padding:2px 7px}}
.badge.gray{{background:#eceef1;color:#5b6067}}
.theme{{display:inline-block;background:#eef3ff;color:#2f6fed;border-radius:999px;padding:3px 12px;font-size:12.5px;margin:0 8px 8px 0}}
.item{{border-top:1px dashed var(--line);padding:14px 0}}
.item:first-of-type{{border-top:0}}
.item .top{{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}}
.item a.t{{font-weight:600;color:var(--ink);text-decoration:none;font-size:15.5px}}
.item a.t:hover{{color:var(--blue)}}
.src{{color:var(--sub);font-size:12.5px;white-space:nowrap}}
.sm{{color:#374151;font-size:14px;margin:6px 0 0}}
.rs{{color:var(--red);font-size:13px;margin:4px 0 0}}
.dg{{color:var(--sub);font-size:13px;margin:4px 0 0}}
.rank{{display:inline-block;width:20px;height:20px;line-height:20px;text-align:center;background:var(--red);color:#fff;border-radius:6px;font-size:12px;font-weight:700;margin-right:8px}}
.tag{{font-size:11.5px;color:#8a8f98;border:1px solid var(--line);border-radius:5px;padding:1px 7px;margin-left:8px}}
footer{{color:var(--sub);font-size:12.5px;text-align:center;margin-top:30px}}
</style></head><body><div class="wrap">""")

    W.append(f"<h1>公众号日报</h1><div class='sub'>生成时间 {esc(data.get('generated_at',''))} ｜ 抓取窗口 最近 {data.get('window_days')} 天 ｜ 共 {len(per_account)} 个号 / {len(arts)} 篇</div>")

    W.append("<div class='stat'>"
             f"<div><b>{len(arts)}</b>篇更新</div>"
             f"<div><b>{len(per_account)}</b>个号有新文</div>"
             f"<div><b>{len(rec)}</b>篇推荐</div>"
             f"<div><b>{sum(1 for a in arts if meta.get(key(a),{}).get('score',0)>=4)}</b>篇高分</div>"
             "</div>")

    if overview or themes:
        W.append("<div class='card'><h2>今日概览</h2>")
        if overview:
            W.append(f"<p style='margin:0 0 10px'>{esc(overview)}</p>")
        if themes:
            W.append("<div>" + "".join(
                f"<span class='theme'><b>{esc(t.get('name'))}</b> · {esc(t.get('desc'))}</span>" for t in themes
            ) + "</div>")
        W.append("</div>")

    if rec:
        W.append("<div class='card'><h2>⭐ 推荐阅读</h2>")
        amap = {key(a): a for a in arts}
        for i, k in enumerate(rec, 1):
            a = amap.get(k)
            if not a:
                continue
            m = meta.get(k, {})
            W.append(f"""<div class="item"><div class="top">
<span><span class="rank">{i}</span><a class="t" href="{esc(a['url'])}" target="_blank">{esc(a['title'])}</a>
<span class="tag">{esc(a['tag'])}</span></span>
<span class="src">{esc(a['account'])} · {esc(a['time'])}</span></div>
{f"<p class='sm'>{esc(m.get('summary'))}</p>" if m.get('summary') else ''}
{f"<p class='rs'>▸ {esc(m.get('reason'))}</p>" if m.get('reason') else ''}
</div>""")
        W.append("</div>")

    # 按公众号分组全量清单
    W.append("<div class='card'><h2>全部更新（按公众号）</h2>")
    for acc in sorted(per_account, key=lambda x: -len(per_account[x])):
        items = sorted(per_account[acc], key=lambda k: -k["ts"])
        W.append(f"<div style='margin:14px 0 6px;font-weight:700'>{esc(acc)} <span class='badge gray'>{len(items)}</span></div>")
        for a in items:
            m = meta.get(key(a), {})
            tag = " ⭐" if by_rec.get(key(a)) is not None else ""
            score = f" · {m.get('score')}/5" if m.get("score") else ""
            stat = ""
            if a.get("read_num"):
                stat = f" · 阅读 {a['read_num']}"
                if a.get("like_num"):
                    stat += f" / 赞 {a['like_num']}"
            W.append(f"""<div class="item"><div class="top">
<a class="t" href="{esc(a['url'])}" target="_blank">{esc(a['title'])}{tag}</a>
<span class="src">{esc(a['time'])}{stat}{score}</span></div>
{f"<p class='sm'>{esc(m.get('summary'))}</p>" if m.get('summary') else f"<p class='dg'>{esc((a.get('digest') or '')[:140])}</p>"}
</div>""")
    W.append("</div>")

    if data.get("failed"):
        W.append("<div class='card'><h2>抓取失败的源</h2><p class='dg'>" +
                 "、".join(esc(f["account"]) for f in data["failed"]) + "</p></div>")

    W.append(f"<footer>由 WorkBuddy 自动生成 · 数据来源 {esc(data.get('source',''))}</footer></div></body></html>")
    return "".join(W)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("articles")
    ap.add_argument("--insights", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ins = args.insights
    if ins is None:
        guess = os.path.join(ROOT, "data",
                             "insights-" + os.path.basename(args.articles).split("articles-")[-1])
        ins = guess if os.path.exists(guess) else None
    htm = build(args.articles, ins)
    os.makedirs(OUT, exist_ok=True)
    stamp = os.path.basename(args.articles).replace("articles-", "").replace(".json", "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})(?:-(\d{4}))?", stamp)
    if m:
        day = m.group(1)
        clock = f"-{m.group(2)}" if m.group(2) else ""
    else:
        day, clock = stamp, ""
    outf = args.out or os.path.join(OUT, f"公众号日报-{day}{clock}.html")
    open(outf, "w", encoding="utf-8").write(htm)
    print("已生成:", outf)


if __name__ == "__main__":
    main()
