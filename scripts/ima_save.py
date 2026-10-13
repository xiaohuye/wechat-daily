# -*- coding: utf-8 -*-
"""
ima_save.py — 把「文章 + 划线批注」成对写入 ima 知识库/笔记

用途：配合 output/公众号日报-精读版-*.html 使用。
      你在精读页里读文章、划线、写批注 → 点「📋 复制全部批注」或「📤 导出 .md」
      → 本脚本把这份 markdown 连同对应原文，一起存进 ima。

依赖 ima-skills（本地已装于 ~/.workbuddy/skills/ima-skills/）。
需先在 https://ima.qq.com/agent-interface 获取 API Key 并配置凭证：
    mkdir -p ~/.config/ima
    echo "<client_id>" > ~/.config/ima/client_id
    echo "<api_key>"   > ~/.config/ima/api_key

用法：
    # 1) 从精读页导出的批注 md（含划线+批注+原文）批量入库
    python scripts/ima_save.py --md "公众号精读批注-2026-10-13.md"

    # 2) 直接用 articles-full JSON 生成「原文+空批注」的笔记骨架
    python scripts/ima_save.py --full data/articles-full-weread-*.json --top 10

    # 3) 只读体检：不写库，打印将创建的内容
    python scripts/ima_save.py --md xxx.md --dry-run

    # 4) 只入库有划线批注的（跳过空篇）
    python scripts/ima_save.py --md xxx.md --only-with-note
"""
import os, re, sys, json, glob, html, argparse, subprocess, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SKILL_DIR = os.path.expanduser(r"~/.workbuddy/skills/ima-skills")
API = os.path.join(SKILL_DIR, "ima_api.cjs")
NODE = r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"

TZ = datetime.timezone(datetime.timedelta(hours=8))


def creds():
    cid = os.environ.get("IMA_OPENAPI_CLIENTID") or os.environ.get("IMA_CLIENT_ID") or ""
    key = os.environ.get("IMA_OPENAPI_APIKEY") or os.environ.get("IMA_API_KEY") or ""
    if not cid:
        p = os.path.expanduser("~/.config/ima/client_id")
        cid = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""
    if not key:
        p = os.path.expanduser("~/.config/ima/api_key")
        key = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""
    return cid, key


def call(api_path, body):
    """调用 ima OpenAPI，返回 (ok, data_or_msg)"""
    cid, key = creds()
    if not cid or not key:
        return False, ("未配置 ima 凭证。请先到 https://ima.qq.com/agent-interface 获取，"
                       "并写入 ~/.config/ima/client_id 与 ~/.config/ima/api_key。")
    node = NODE if os.path.exists(NODE) else "node"
    opts = json.dumps({"clientId": cid, "apiKey": key})
    r = subprocess.run([node, API, api_path, json.dumps(body, ensure_ascii=False), opts],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "unknown error").strip()
    try:
        resp = json.loads(r.stdout or "{}")
    except Exception:
        return False, f"返回非 JSON: {(r.stdout or '')[:200]}"
    if resp.get("code", 0) != 0:
        return False, resp.get("msg", "后端业务错误")
    return True, resp.get("data", {})


def to_utf8(s):
    """确保字符串是合法 UTF-8（ima 写入强制要求）"""
    if isinstance(s, bytes):
        return s.decode("utf-8", "ignore")
    return str(s).encode("utf-8", "ignore").decode("utf-8")


def parse_md(md_text):
    """解析精读页导出的 markdown。

    支持两种格式：
      A. 划线批注版（当前）：每篇下含 ### 划线批注 + 多条「**划线**：/ **批注**：」
      B. 整篇随笔版（旧）：每篇下含 **我的随笔**

    返回 [{title, account, time, read, url, note, highlights:[{text,note}]}]
    """
    items = []
    blocks = re.split(r"\n##\s+", "\n" + md_text)
    for b in blocks[1:]:
        lines = b.split("\n")
        head = lines[0].strip()
        m = re.match(r"^\d+\.\s*(.+)$", head)
        title = m.group(1).strip() if m else head
        account = time_s = read = url = ""
        note_lines = []      # 整篇随笔
        highlights = []      # 划线批注
        cur = None           # 当前正在组装的划线
        mode = None          # 'note' | 'hl'
        for ln in lines[1:]:
            s = ln.strip()
            if s.startswith("### 划线批注"):
                mode = "hl"; continue
            if s.startswith("**我的随笔**"):
                mode = "note"; continue
            if mode == "hl":
                if s.startswith("**划线**："):
                    if cur: highlights.append(cur)
                    cur = {"text": s[len("**划线**："):].strip(), "note": ""}
                elif s.startswith("**批注**："):
                    val = s[len("**批注**："):].strip()
                    if cur and val and val != "（无）":
                        cur["note"] = val
                elif s == "---":
                    mode = None
                continue
            if mode == "note":
                if s == "---":
                    mode = None
                    continue
                note_lines.append(ln)
                continue
            if s.startswith("- 公众号："): account = s[len("- 公众号："):].strip()
            elif s.startswith("- 发布："): time_s = s[len("- 发布："):].strip()
            elif s.startswith("- 阅读："): read = s[len("- 阅读："):].strip()
            elif s.startswith("- 原文："): url = s[len("- 原文："):].strip()
        if cur: highlights.append(cur)
        items.append({"title": title, "account": account, "time": time_s,
                      "read": read, "url": url, "note": "\n".join(note_lines).strip(),
                      "highlights": highlights})
    return items


def md_from_full(full_file, top):
    """从正文 JSON 生成「原文信息 + 空批注」骨架 md（用于预演/手动补批注）"""
    d = json.load(open(full_file, encoding="utf-8"))
    date = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    out = [f"# 公众号精读批注 · {date}\n"]
    for i, (k, v) in enumerate(list(d["articles"].items())[:top], 1):
        out.append(f"## {i}. {v.get('title','')}\n")
        out.append(f"- 公众号：{v.get('account','')}")
        out.append(f"- 发布：{v.get('time','')}")
        if v.get("read_num"):
            out.append(f"- 阅读：{v['read_num']}")
        if v.get("internal_id"):
            out.append(f"- 原文：https://weread.qq.com/web/mp/reader/{v['internal_id']}")
        out.append("\n### 划线批注\n")
        out.append("**划线**：（在此粘贴原文句子）")
        out.append("**批注**：（写下你的批注）")
        out.append("\n---\n")
    return "\n".join(out), date


def build_note(item, date):
    """组装一篇笔记的 title + content（markdown），划线批注按引用块呈现"""
    title = f"[{item['account']}] {item['title']}" if item.get("account") else item["title"]
    if len(title) > 60:
        title = title[:60]
    lines = [f"# {item['title']}", ""]
    if item.get("account"): lines.append(f"> 公众号：{item['account']}")
    if item.get("time"):    lines.append(f"> 发布：{item['time']}")
    if item.get("read"):    lines.append(f"> 阅读：{item['read']}")
    if item.get("url"):     lines.append(f"> 原文：{item['url']}")
    lines.append("")
    hls = item.get("highlights") or []
    if hls:
        lines.append("## 划线批注")
        lines.append("")
        for i, h in enumerate(hls, 1):
            lines.append(f"{i}. > {h['text']}")
            lines.append("")
            lines.append(f"   **批注**：{h['note'] or '（无）'}")
            lines.append("")
    if item.get("note"):
        lines.append("## 整篇随笔")
        lines.append("")
        lines.append(item["note"])
        lines.append("")
    if not hls and not item.get("note"):
        lines.append("_（本篇暂无批注）_")
    return to_utf8(title), to_utf8("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=None, help="精读页导出的随笔 markdown")
    ap.add_argument("--full", default=None, help="articles-full-weread-*.json")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-with-note", action="store_true", help="只入库写了随笔的")
    args = ap.parse_args()

    date = datetime.datetime.now(TZ).strftime("%Y-%m-%d")
    if args.md:
        items = parse_md(open(args.md, encoding="utf-8").read())
        src = args.md
    else:
        full = args.full
        if not full:
            fs = sorted(glob.glob(os.path.join(DATA, "articles-full-weread-*.json")))
            if not fs:
                raise SystemExit("找不到正文 JSON，先跑 weread_content.py")
            full = fs[-1]
        md, date = md_from_full(full, args.top)
        items = parse_md(md)
        src = os.path.basename(full)

    if args.only_with_note:
        items = [x for x in items if x.get("note") or x.get("highlights")]

    print(f"来源: {src}")
    nh = sum(len(x.get('highlights') or []) for x in items)
    print(f"将从 {len(items)} 篇生成笔记（共 {nh} 条划线批注）\n")

    if not os.path.exists(API):
        raise SystemExit(f"未找到 ima skill: {API}")

    cid, key = creds()
    have_cred = bool(cid and key)
    print("凭证:", "已配置" if have_cred else "⚠️ 未配置（需先在 ima.qq.com/agent-interface 获取）")

    ok_n, fail_n = 0, 0
    for i, it in enumerate(items, 1):
        title, content = build_note(it, date)
        nh = len(it.get("highlights") or [])
        nnote = len((it.get("note") or "").strip())
        tag = f"{nh}条划线" if nh else ("随笔" if nnote else "空")
        if args.dry_run or not have_cred:
            print(f"[{i:2}] ({tag}) {title}")
            continue
        ok, data = call("openapi/note/v1/import_doc",
                        {"title": title, "content": content, "content_format": 1})
        if ok:
            ok_n += 1
            nid = data.get("note_id") or data.get("doc_id") or ""
            print(f"[{i:2}] ✓ ({tag}) {title} {('→ '+str(nid)) if nid else ''}")
        else:
            fail_n += 1
            print(f"[{i:2}] ✗ ({tag}) {title}\n       {data}")
    if not args.dry_run and have_cred:
        print(f"\n完成：成功 {ok_n} / 失败 {fail_n}")

    if args.dry_run and have_cred:
        print("\n(--dry-run，未实际写入)")


if __name__ == "__main__":
    main()
