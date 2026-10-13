# -*- coding: utf-8 -*-
"""
wx_classify.py — 对「我关注的公众号全集」做类型 / 风格 / 关注强度分析

输入: config/wechat_accounts.json（来自微信读书 /shelf/sync）
输出: config/accounts_classified.json + output/公众号关注画像.html
"""
import json, os, html, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "config", "wechat_accounts.json")
OUTJ = os.path.join(ROOT, "config", "accounts_classified.json")
OUTH = os.path.join(ROOT, "output", "公众号关注画像.html")

# 类型映射（人工判定，按内容定位而非名称关键词）
TYPE_MAP = {
    "大厂官方技术号": ["腾讯研究院","腾讯混元","腾讯技术工程","腾讯云开发者","大淘宝技术","千问AI平台","火山引擎Agent社区","抖音精选App"],
    "AI 媒体与资讯": ["机器之心","量子位","新智元","AI科技评论","智东西","AI前线","甲子光年","极客公园","虎嗅APP","APPSO","智能涌现","财联社AI daily","天下网商","AIBase基地","AI评论员","夕小瑶科技说"],
    "AI 产品与工具实践": ["数字生命卡兹克","赛博禅心","歸藏的AI工具箱","TRAE.ai","扣子Coze","Dify","花叔","橘AI","AI产品白皮书","AI产品阿颖","AI产品黄叔","AI产品银海","云舒的AI实践笔记","AI大模型应用实践","AI大模型工场","AI范儿","AI信息Gap","AI云枢","AI修猫Prompt","AI编程实验室","AI陈工","AI算法之道","智能体AI","喜新","苍何","小曾AI笔记","阿伦AI学习笔记","Draco正在VibeCoding","AI大模型智能","看图学","soft张三丰","秋芝2046","InkFlow惜阅","别偷着学了带带我啊","云中江树"],
    "技术社区与工程": ["JavaGuide","HelloGitHub","逛逛GitHub","架构师","架构师带你玩转AI","程序员鱼皮","Java一条人","BestBlogs","技术极简主义","MacTalk","八一菜刀","哥飞","Datawhale"],
    "论文与科研": ["刘聪NLP","PaperAgent","AIML实验室","吴师兄学大模型","AI修猫Prompt"],
    "AIGC 与视频创作": ["安与梦AI视频","行者AI视频","80后的AIGC时代","海辛和阿文","优设AIGC","蔚公子说AI","硅基鹿鸣","硅基观察Pro","硅星人Pro"],
    "投资商业与出海": ["格隆","梅森投研","生财有术","橙哥出海","孤独大脑","崔鹏的二手经济学","人类搞钱聚集地","中年人的逆天改命记","Z Finance","Z Potentials","海外独角兽","逛GitHub"],
    "个人 IP 与随笔": ["管三","力哥","赛文乔伊","魔宙","向阳乔木推荐看","赵晗","易芝YZ","沈粒子","饶秋1023","歪斯Wise","塔罗烩","喜新"],
    "AI 创业与产业观察": ["Founder Park","AGI Hunt","十字路口Crossing","01Founder","卡尔的AI沃茨","饼干哥哥AGI","杰克船长的AIGC","袋鼠帝","摸鱼小李","太阳照常升起","刘小排r","阿真Irene","小林AI实验","小黑黑讲AI","龙龙AI副业","飞跑的鹿","AIGCRank","超Ji图解","超级图解","AI大模型工场","智东西"],
}
name2type = {}
for t, names in TYPE_MAP.items():
    for n in names:
        name2type.setdefault(n, t)

# 风格：按类型给出主导风格（首期基于类型推断，后续用真实文章语料校正）
TYPE_STYLE = {
    "大厂官方技术号": "深度工程文 / 方法论沉淀，信息密度高、偏权威",
    "AI 媒体与资讯": "快讯+深度稿，追热点快、覆盖广",
    "AI 产品与工具实践": "实操教程 + 产品测评，重上手、重 prompt/流程",
    "技术社区与工程": "开源项目 / 面试八股 / 工程经验，工具属性强",
    "论文与科研": "论文速读 + 算法解析，门槛高、偏学术",
    "AIGC 与视频创作": "案例展示 + 效果向，视觉驱动",
    "投资商业与出海": "观点评论 + 商业拆解，强判断、强立场",
    "个人 IP 与随笔": "个人叙事 / 行业随笔，观点色彩浓",
    "AI 创业与产业观察": "访谈 + 产业趋势，看赛道和产品",
}

TIERS = [(7, "高频", "#e34d59"), (30, "活跃", "#f59e0b"), (90, "低频", "#8b93a1"), (99999, "沉寂", "#c3c8cf")]


def esc(s):
    return html.escape(str(s or ""), quote=True)


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    accs = data["accounts"]
    today = datetime.date.today()

    rows = []
    for a in accs:
        t = name2type.get(a["name"], "未归类")
        try:
            d = datetime.date.fromisoformat(a["last_read"])
            days = (today - d).days
        except Exception:
            days = None
        tier = next(name for lim, name, _ in TIERS if days is not None and days <= lim) if days is not None else "未知"
        color = next(c for lim, name, c in TIERS if tier == name) if tier != "未知" else "#c3c8cf"
        rows.append({**a, "type": t, "style": TYPE_STYLE.get(t, ""), "days_ago": days,
                     "tier": tier, "tier_color": color})

    rows.sort(key=lambda r: (r["days_ago"] if r["days_ago"] is not None else 99999))

    # 统计
    by_type, by_tier = {}, {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
        by_tier.setdefault(r["tier"], []).append(r)

    json.dump({"generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
               "total": len(rows), "by_type": {k: len(v) for k, v in by_type.items()},
               "by_tier": {k: len(v) for k, v in by_tier.items()},
               "accounts": rows},
              open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # HTML
    W = []
    W.append(f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>公众号关注画像</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--line:#e6e8eb;--ink:#1c1f23;--sub:#6b7280;--red:#e34d59;--blue:#2f6fed}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 6px}}
.sub{{color:var(--sub);font-size:13px;margin-bottom:22px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:18px}}
.card h2{{font-size:17px;margin:0 0 14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}
.tile{{border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.tile .n{{font-size:24px;font-weight:700;color:var(--blue)}}
.tile .l{{font-size:13px;color:var(--sub);margin-top:2px}}
.row{{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px dashed var(--line)}}
.row:first-of-type{{border-top:0}}
.dot{{width:8px;height:8px;border-radius:50%;flex:0 0 auto}}
.nm{{font-weight:600;min-width:150px}}
.tp{{font-size:12.5px;color:#2f6fed;background:#eef3ff;border-radius:5px;padding:1px 8px}}
.tm{{color:var(--sub);font-size:12.5px;margin-left:auto;white-space:nowrap}}
.st{{font-size:13px;color:#374151;margin:4px 0 0}}
.grp{{margin:18px 0 8px;font-weight:700;display:flex;align-items:center;gap:8px}}
.pill{{font-size:11.5px;font-weight:700;color:#fff;border-radius:6px;padding:2px 8px}}
footer{{color:var(--sub);font-size:12.5px;text-align:center;margin-top:30px}}
</style></head><body><div class="wrap">""")
    W.append(f"<h1>我的公众号关注画像</h1><div class='sub'>共 {len(rows)} 个公众号 ｜ 数据源：微信读书书架 ｜ 生成于 {esc(json.load(open(OUTJ,encoding='utf-8'))['generated_at'])}</div>")

    W.append("<div class='card'><h2>关注强度分布</h2><div class='grid'>")
    for lim, name, color in TIERS:
        n = len(by_tier.get(name, []))
        W.append(f"<div class='tile'><div class='n' style='color:{color}'>{n}</div><div class='l'>{name}（{lim if lim<99999 else '90+'} 天内）</div></div>")
    W.append("</div></div>")

    W.append("<div class='card'><h2>类型分布</h2><div class='grid'>")
    for t, v in sorted(by_type.items(), key=lambda x: -len(x[1])):
        W.append(f"<div class='tile'><div class='n'>{len(v)}</div><div class='l'>{esc(t)}</div></div>")
    W.append("</div></div>")

    W.append("<div class='card'><h2>类型 → 风格</h2>")
    for t, v in sorted(by_type.items(), key=lambda x: -len(x[1])):
        W.append(f"<div class='row'><span class='dot' style='background:#2f6fed'></span><span class='nm'>{esc(t)}</span><span class='tp'>{len(v)} 个</span></div><p class='st'>{esc(TYPE_STYLE.get(t,''))}</p>")
    W.append("</div>")

    for lim, tname, color in TIERS:
        group = by_tier.get(tname, [])
        if not group:
            continue
        W.append(f"<div class='card'><div class='grp'><span class='pill' style='background:{color}'>{tname}</span>{len(group)} 个</div>")
        for r in group:
            dia = f"{r['days_ago']} 天前" if r['days_ago'] is not None else "未知"
            W.append(f"<div class='row'><span class='dot' style='background:{color}'></span>"
                     f"<span class='nm'>{esc(r['name'])}</span><span class='tp'>{esc(r['type'])}</span>"
                     f"<span class='tm'>{esc(r['last_read'])} · {dia}</span></div>")
        W.append("</div>")

    W.append("<footer>WorkBuddy 生成 ｜ bookId 前缀 MP_WXS_ 判定为公众号</footer></div></body></html>")
    open(OUTH, "w", encoding="utf-8").write("".join(W))

    print(f"共 {len(rows)} 个账号")
    print("按类型:", json.dumps({k: len(v) for k, v in sorted(by_type.items(), key=lambda x: -len(x[1]))}, ensure_ascii=False, indent=1))
    print("按强度:", json.dumps({k: len(v) for k, v in by_tier.items()}, ensure_ascii=False))
    print("未归类:", [r['name'] for r in rows if r['type'] == '未归类'])
    print("已生成:", OUTJ, "|", OUTH)


if __name__ == "__main__":
    main()
