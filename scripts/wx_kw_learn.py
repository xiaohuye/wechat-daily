# -*- coding: utf-8 -*-
"""
wx_kw_learn.py — 从划线/批注语料学习兴趣关键词（隐性兴趣挖掘）

输入: data/highlights.json（页面「🧠 回灌划线」按钮 → ima_sync.py /save_highlights 落盘）
输出: data/learned_kw.json {"updated_at","total","words":{词:权重}}，由 wx_rank.py 打分时自动读取

原理: 你划线的句子、写的批注，是最真实的兴趣信号（比阅读量/点赞强得多）。
      用 jieba TF-IDF 提取语料关键词，过滤停用词/单字/纯数字，
      划线文本权重 1.0、批注权重 1.5（你自己的思考更代表你），低频词过滤（总语料
      少于 10 条时放宽），保留 Top N 供推荐加权。

用法:
    python scripts/wx_kw_learn.py             # 提取并落盘
    python scripts/wx_kw_learn.py --top 30    # 词表容量
    python scripts/wx_kw_learn.py --dry-run   # 只打印不落盘
"""
import os, json, argparse, datetime, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TZ = datetime.timezone(datetime.timedelta(hours=8))

W_NOTE = 1.5    # 批注权重 > 划线权重（自己写的思考信号更强）
W_HL = 1.0

STOP = set("""的 了 和 是 就 都 而 及 与 或 在 对 从 被 把 给 向 跟 但 不过 因此 所以 如果 因为
这个 那个 什么 怎么 我们 你们 他们 它们 一个 一些 一些 还有 不是 没有 可以 应该 需要 就是 的话 这样 那样
我们 你 我 他 她 它 也很 都会 的话 觉得 知道 可能 比如 例如 以及 关于 通过 进行 开始 实现 这个 那个
the a an of to and or in on for is are be with this that it as
系统 方案 机制 考虑 关注 值得 关键 边界 问题 效果 内容 时候 方式 方法 角度 维度 东西
""".split())
MIN_LEN = 2          # 词最短长度（中英文都适用）
LOW_FREQ = 2         # 出现次数下限；语料条数 < 10 时放宽为 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(DATA, "highlights.json"))
    ap.add_argument("--out", default=os.path.join(DATA, "learned_kw.json"))
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit("没有 data/highlights.json —— 在日报页点「🧠 回灌划线」后产生")

    d = json.load(open(args.src, encoding="utf-8"))
    arts = d.get("articles", {})
    n_hl = sum(len(v.get("highlights") or []) for v in arts.values())
    if not n_hl:
        raise SystemExit("highlights.json 里没有划线")

    import jieba.analyse
    # 语料：划线句 + 批注（批注重复 W_NOTE/W_HL 次以提升其 TF-IDF 权重）
    docs = []
    n_note = 0
    for v in arts.values():
        for h in v.get("highlights") or []:
            t = re.sub(r"\s+", " ", (h.get("text") or "").strip())
            if t:
                docs.append(t)
            note = (h.get("note") or "").strip()
            if note:
                n_note += 1
                for _ in range(round(W_NOTE / W_HL)):
                    docs.append(note)
    corpus = "\n".join(docs)
    min_freq = LOW_FREQ if len(docs) >= 10 else 1

    words = jieba.analyse.extract_tags(corpus, topK=args.top * 3, withWeight=True,
                                       allowPOS=("n", "nr", "ns", "nt", "nz", "vn", "v", "eng"))
    # 过滤：停用词 / 长度 / 纯数字纯标点 / 频次
    from collections import Counter
    tokens = jieba.lcut(corpus)
    freq = Counter(tokens)
    min_freq = LOW_FREQ if len(docs) >= 10 else 1
    kept = {}
    for w, s in words:
        if w in STOP or len(w) < MIN_LEN or w.isdigit() or re.fullmatch(r"[\W_]+", w):
            continue
        if freq.get(w, 0) < min_freq:
            continue
        kept[w] = round(s, 3)
        if len(kept) >= args.top:
            break

    print(f"语料：{len(arts)} 篇 / {n_hl} 条划线 / {n_note} 条批注，共 {len(docs)} 段")
    print(f"学习词表 Top {len(kept)}：")
    for i, (w, s) in enumerate(sorted(kept.items(), key=lambda x: -x[1]), 1):
        print(f"  {i:2}. {w:<14} {s}")
    if not kept:
        raise SystemExit("没提取到可用关键词（语料太少或全是停用词）")

    if args.dry_run:
        print("(--dry-run，未落盘)")
        return
    out = {"updated_at": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
           "total_highlights": n_hl, "words": kept}
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已存:", args.out, "→ 下次跑 wx_rank.py 自动生效")


if __name__ == "__main__":
    main()
