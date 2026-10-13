# -*- coding: utf-8 -*-
"""
wx_rank.py — 推荐排序引擎 v1（启发式）

输入: data/articles-weread-*.json + config/accounts_classified.json
输出: data/ranked-<同时间戳>.json（含每篇的分数与打分理由）+ 控制台 Top 列表

打分维度（后续用你的阅读反馈迭代权重）:
  1. 账号类型权重 —— 与你「AI 产品/工具实践 + 大厂工程 + 创业观察」画像的贴合度
  2. 热度 —— log(阅读数)，10万+ 封顶
  3. 时效 —— 越新越高
  4. 关键词命中 —— 命中你的兴趣词加分，命中噪声词减分
  5. 去重 —— 同号/同主题高度重复的降权
用法:
    python scripts/wx_rank.py [--days 3] [--top 30]
"""
import json, os, re, glob, math, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))

# 1) 类型权重（越贴近你的画像越高）
TYPE_W = {
    "AI 产品与工具实践": 1.00,
    "大厂官方技术号": 0.95,
    "AI 创业与产业观察": 0.90,
    "AI 媒体与资讯": 0.68,
    "论文与科研": 0.62,
    "技术社区与工程": 0.55,
    "投资商业与出海": 0.45,
    "AIGC 与视频创作": 0.40,
    "个人 IP 与随笔": 0.30,
}

# 4) 关键词
KW_GOOD = ["agent","智能体","skill","mcp","工作流","workflow","产品","大模型","prompt","rag",
           "ai编程","自动化","aigc","copilot","harness","开源","架构","实践","复盘","方法论",
           "落地","实测","教程","拆解","范式","上下文","to b","效率"]
KW_BAD = ["倒闭潮","ipo","房价","股市","涨停","跑鞋","社交法则","找对象","带货","优惠","抽奖",
          "招聘","活动预告","报名","直播预告","读者来信","山姆","种草"]

W_TYPE, W_HEAT, W_FRESH, W_KW = 1.0, 1.6, 1.1, 0.9


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(ROOT, "data", pattern)))
    return fs[-1] if fs else None


def score_one(a, type_map, now):
    reasons = []
    t = type_map.get(a["account"], "")
    s_type = TYPE_W.get(t, 0.4)
    if s_type >= 0.9:
        reasons.append(f"账号类型高度贴合（{t}）")

    rn = a.get("read_num") or 0
    s_heat = math.log10(max(rn, 1) + 1) / 5.0          # 10万 -> ~1.0
    if rn >= 50000:
        reasons.append(f"高热度（阅读 {rn}）")

    hours = max((now - a["ts"]) / 3600.0, 0.1)
    s_fresh = max(0.0, 1.0 - hours / 168.0)             # 7 天内线性衰减
    if hours <= 24:
        reasons.append("24 小时内新发")

    low = (a["title"] + " " + (a.get("digest") or "")).lower()
    hit = [k for k in KW_GOOD if k in low]
    bad = [k for k in KW_BAD if k in low]
    s_kw = min(len(hit), 4) / 4.0 - min(len(bad), 2) * 0.5
    if hit:
        reasons.append("命中兴趣词：" + "、".join(hit[:3]))
    if bad:
        reasons.append("命中噪声词：" + "、".join(bad[:2]))

    total = W_TYPE * s_type + W_HEAT * s_heat + W_FRESH * s_fresh + W_KW * s_kw
    return round(total, 3), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--src", default=None)
    args = ap.parse_args()

    src = args.src or latest("articles-weread-*.json")
    if not src:
        raise SystemExit("找不到抓取结果，先跑 weread_fetch.py")
    d = json.load(open(src, encoding="utf-8"))
    cl = json.load(open(os.path.join(ROOT, "config", "accounts_classified.json"), encoding="utf-8"))
    type_map = {r["name"]: r["type"] for r in cl["accounts"]}

    now = int(datetime.datetime.now(TZ).timestamp())
    cutoff = now - args.days * 86400
    arts = [a for a in d["articles"] if a["ts"] >= cutoff]

    # 同号同主题去重：标题前 12 字相同的只留最高分
    seen_title, deduped = {}, []
    for a in arts:
        a["_score"], a["_reasons"] = score_one(a, type_map, now)
        a["_type"] = type_map.get(a["account"], "")
    arts.sort(key=lambda x: -x["_score"])
    for a in arts:
        k = (a["account"], re.sub(r"[^\w\u4e00-\u9fff]", "", a["title"])[:12])
        if k in seen_title:
            continue
        seen_title[k] = 1
        deduped.append(a)

    top = deduped[:args.top]
    out = os.path.join(ROOT, "data", os.path.basename(src).replace("articles-", "ranked-"))
    json.dump({"generated_at": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
               "source": os.path.basename(src), "window_days": args.days,
               "candidates": len(arts), "top": top},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"候选 {len(arts)} 篇（最近 {args.days} 天）→ Top {len(top)}\n")
    for i, a in enumerate(top, 1):
        print(f"{i:2}. [{a['_score']:.2f}] {a['account']} | {a['_type']}")
        print(f"     {a['title']}")
        print(f"     阅读 {a.get('read_num')} 赞 {a.get('like_num')} · {a['time']} · {'；'.join(a['_reasons'])}")
    print("\n已存:", out)


if __name__ == "__main__":
    main()
