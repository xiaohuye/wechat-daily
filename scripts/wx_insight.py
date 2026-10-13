# -*- coding: utf-8 -*-
"""
wx_insight.py — 基于抓取结果 + 排序结果，自动生成日报所需的 insights JSON

输入: data/articles-weread-*.json  (+ 可选 data/ranked-weread-*.json)
输出: data/insights-weread-<同时间戳>.json

insights 结构（供 wx_report.py 消费）:
{
  "overview": "...",
  "themes":   [{"name","desc"}],
  "recommend":["公众号|标题", ...],
  "articles": {"公众号|标题": {"summary","score","reason"}}
}
用法:
    python scripts/wx_insight.py [--src data/articles-weread-xxx.json] [--top 30]
"""
import json, os, re, glob, argparse, datetime
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))

# 主题识别词表（按顺序匹配，命中即归类）
THEME_RULES = [
    ("Agent / 智能体", ["agent", "智能体", "多智能体", "multi-agent", "自主"],
     "Agent 架构与企业级落地"),
    ("MCP / Skill / 工具链", ["mcp", "skill", "工具调用", "function call", "插件"],
     "模型与外部能力的连接层"),
    ("大模型与基座", ["大模型", "llm", "gpt", "claude", "gemini", "qwen", "deepseek", "开源模型"],
     "模型能力与选型"),
    ("AI 编程", ["编程", "coding", "copilot", "cursor", "代码", "ide", "vibe"],
     "AI 辅助研发"),
    ("产品与商业化", ["产品", "商业化", "增长", "pmf", "付费", "收入", "商业模式"],
     "AI 产品与变现"),
    ("创业与融资", ["创业", "融资", "估值", "ipo", "投资", "赛道", "公司"],
     "创业公司与资本市场"),
    ("出海与全球化", ["出海", "全球化", "海外", "跨境"],
     "海外市场机会"),
    ("AIGC 与内容创作", ["aigc", "视频", "绘画", "图像", "生成", "剪辑", "midjourney", "sora"],
     "多模态内容生产"),
    ("工程与架构", ["架构", "工程", "性能", "重构", "分布式", "并发", "稳定性"],
     "后端与系统工程"),
    ("效率与方法论", ["效率", "方法论", "工作流", "workflow", "自动化", "工具"],
     "个人与团队提效"),
]


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(ROOT, "data", pattern)))
    return fs[-1] if fs else None


def to_stars(score):
    if score >= 3.80:
        return 5
    if score >= 3.50:
        return 4
    if score >= 3.15:
        return 3
    return 2


def brief(text, n=60):
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t[:n] + ("…" if len(t) > n else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--rank", default=None)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    src = args.src or latest("articles-weread-*.json")
    if not src:
        raise SystemExit("找不到抓取结果 data/articles-weread-*.json")
    stamp = os.path.basename(src).split("articles-weread-")[-1].replace(".json", "")

    rank = args.rank or os.path.join(ROOT, "data", f"ranked-weread-{stamp}.json")
    if not os.path.exists(rank):
        rank = latest("ranked-weread-*.json")

    d = json.load(open(src, encoding="utf-8"))
    arts = d["articles"]
    rk = json.load(open(rank, encoding="utf-8")) if rank and os.path.exists(rank) else {"top": []}
    top = rk.get("top", [])[: args.top]

    # 类型映射
    cl = json.load(open(os.path.join(ROOT, "config", "accounts_classified.json"), encoding="utf-8"))
    type_map = {r["name"]: r["type"] for r in cl["accounts"]}

    # ---------- themes ----------
    cnt = Counter()
    for a in arts:
        low = (a["title"] + " " + (a.get("digest") or "")).lower()
        for name, kws, _ in THEME_RULES:
            if any(k in low for k in kws):
                cnt[name] += 1
    themes = [{"name": n, "desc": f"{c} 篇 · {desc}"}
              for (n, _, desc), c in
              sorted(((rule, cnt[rule[0]]) for rule in THEME_RULES), key=lambda x: -x[1])
              if c > 0][:6]

    # ---------- overview ----------
    acc_n = len(set(a["account"] for a in arts))
    total = len(arts)
    days = d.get("window_days", 3)
    hot = sorted(arts, key=lambda a: -(a.get("read_num") or 0))[:1]
    hot_s = f"，最热一篇来自「{hot[0]['account']}」（阅读 {hot[0]['read_num']}）" if hot else ""
    type_cnt = Counter(type_map.get(a["account"], "未分类") for a in arts)
    top_types = "、".join(f"{k} {v} 篇" for k, v in type_cnt.most_common(3))
    overview = (f"最近 {days} 天，{acc_n} 个公众号共更新 {total} 篇{hot_s}。"
                f"更新最集中的方向是：{top_types}。共筛出 {len(top)} 篇推荐。")

    # ---------- recommend + articles meta ----------
    recommend, meta = [], {}
    for a in top:
        k = f"{a['account']}|{a['title']}"
        recommend.append(k)
        rs = a.get("_reasons") or []
        # 去掉「账号类型高度贴合」这种泛描述，保留有信息量的
        keep = [r for r in rs if "类型高度贴合" not in r]
        reason = "；".join(keep) if keep else "；".join(rs) or "综合评分靠前"
        meta[k] = {
            "summary": brief(a.get("digest") or a["title"], 70),
            "score": to_stars(a.get("_score", 0)),
            "reason": f"{reason}｜评分 {a.get('_score')}",
        }

    out = os.path.join(ROOT, "data", f"insights-weread-{stamp}.json")
    json.dump({"generated_at": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
               "overview": overview, "themes": themes,
               "recommend": recommend, "articles": meta},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("已生成:", out)
    print("\n[概览]", overview)
    print("\n[主题]")
    for t in themes:
        print("  ·", t["name"], "—", t["desc"])
    print(f"\n[推荐 {len(recommend)} 篇]")
    for i, k in enumerate(recommend[:10], 1):
        print(f"  {i:2}. {k}")


if __name__ == "__main__":
    main()
