# -*- coding: utf-8 -*-
"""
ima_sync.py — 本地 ima 同步服务（日报页「☁ 存入 ima」按钮的后端）

为什么需要它：日报是本地 HTML（file://），浏览器直接调 ima.qq.com 会被 CORS 拦截，
自定义 header（ima-openapi-clientid 等）必然触发失败的 preflight。
所以页面把批注 POST 给本服务（127.0.0.1:8931），由本服务转发给 ima OpenAPI。

用法：
    python scripts/ima_sync.py            # 启动（默认闲置 180 秒无请求自动退出）
    python scripts/ima_sync.py --idle 0   # 永不自动退出
    python scripts/ima_sync.py --port 8932
    python scripts/ima_sync.py --mock     # 测试模式：不真实写 ima（回归测试用，避免产生垃圾笔记）

生命周期（短驻模式）：
    平时不需要挂着。页面端「入库/回灌」在服务不在线时自动进离线暂存队列；
    需要同步时（run_daily.sh 拉起 / 手动启动 / 喊一声 AI），打开着的日报页
    会在 15 秒内探测到服务并自动冲刷队列；闲置 --idle 秒后本服务自动退出。

接口：
    GET  /ping            健康检查
    POST /save            body: {"items": [{title, account, time, read, url, note, highlights:[{text,note}]}]}
                          批注维度 → 每篇一篇「[公众号] 标题」笔记
    POST /save_doc        body: {"title","account","time","read","url","content_md"}
                          原文维度 → 单篇全文存档「[存档] 标题」笔记
    POST /save_highlights body: {"items": [{"key","account","title","highlights":[{text,note,ts}]}]}
                          回灌维度 → 不写 ima，落盘 data/highlights.json（按 key 增量合并），
                          供 wx_kw_learn.py 提取兴趣关键词
                          返回: {"ok": n, "fail": n, "done": [...], "errors": [...]}
    POST /save_feedback   body: {"feedback": [{"key","account","title","mark","ts"}]}
                          阅读反馈 → 整体替换 data/feedback.json（页面反馈全集为准），
                          供 wx_rank.py 排序加权（页面 fbMark 后自动调用）
    会话级去重：批注（标题+首条划线文本）/ 原文（标题）本次服务生命周期内只写一次。

依赖：scripts/ima_save.py（凭证与写入逻辑）、凭证 ~/.config/ima/
"""
import os, sys, json, time, argparse, datetime, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ima_save import call, build_note, to_utf8  # noqa: E402

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

MAX_DOC = 60000   # 原文存档单篇上限（字符），超长截断


def build_doc_note(d):
    """原文维度：全文存档笔记（markdown）。ima 的显示标题取正文 H1，前缀要写进 H1"""
    title = to_utf8(d.get("title") or "")
    head = f"[存档] {title}"
    if len(head) > 60:
        head = head[:60]
    lines = [f"# [存档] {title}", ""]
    if d.get("account"): lines.append(f"> 公众号：{d['account']}")
    if d.get("time"):    lines.append(f"> 发布：{d['time']}")
    if d.get("read"):    lines.append(f"> 阅读：{d['read']}")
    if d.get("url"):     lines.append(f"> 原文：{d['url']}")
    lines.append("")
    md = to_utf8(d.get("content_md") or "")
    if len(md) > MAX_DOC:
        md = md[:MAX_DOC] + "\n\n_（正文超长已截断）_"
    lines.append("## 原文")
    lines.append("")
    lines.append(md or "_（正文为空）_")
    return head, to_utf8("\n".join(lines))

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

_seen = set()   # 会话级去重：本次服务生命周期内已入库的 (title|首条划线)


class Handler(BaseHTTPRequestHandler):

    def _send(self, code, payload, touch=True):
        if touch:
            self.server.last_active = time.time()      # 供 watchdog 判闲置；/ping 探测不算业务活动
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.server.last_active = time.time()
        self.send_response(204)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/ping"):
            # touch=False：页面 watcher 每 15s 一次的 ping 探测不能阻止闲置退出
            self._send(200, {"ok": True, "ts": datetime.datetime.now().strftime("%H:%M:%S")}, touch=False)
        else:
            self._send(404, {"ok": False, "msg": "not found"})

    def do_POST(self):
        if self.path.startswith("/save_doc"):
            return self._do_save_doc()
        if self.path.startswith("/save_highlights"):
            return self._do_save_highlights()
        if self.path.startswith("/save_feedback"):
            return self._do_save_feedback()
        if not self.path.startswith("/save"):
            self._send(404, {"ok": False, "msg": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8", "ignore"))
        except Exception as e:
            self._send(400, {"ok": 0, "fail": 0, "errors": [f"bad body: {e}"]})
            return
        items = data.get("items") or []
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        ok_n, fail_n, done, errors = 0, 0, [], []
        for it in items:
            hls = it.get("highlights") or []
            if not hls and not (it.get("note") or "").strip():
                continue                      # 没批注的不写
            sig = f"{it.get('title','')}|{(hls[0]['text'] if hls else (it.get('note') or '')[:30])}"
            if sig in _seen:
                done.append(f"[跳过·已入库] {it.get('title','')}")
                continue
            title, content = build_note(it, date)
            ok, resp = call("openapi/note/v1/import_doc",
                            {"title": title, "content": content, "content_format": 1})
            if ok:
                _seen.add(sig)
                ok_n += 1
                done.append(f"✓ {title} → {resp.get('note_id', '')}")
            else:
                fail_n += 1
                errors.append(f"{title}: {resp}")
        self._send(200, {"ok": ok_n, "fail": fail_n, "done": done, "errors": errors})

    def _do_save_doc(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n).decode("utf-8", "ignore"))
        except Exception as e:
            self._send(400, {"ok": 0, "fail": 1, "errors": [f"bad body: {e}"]})
            return
        if not (d.get("title") or "").strip():
            self._send(400, {"ok": 0, "fail": 1, "errors": ["缺 title"]})
            return
        sig = "[doc]" + d.get("title", "")
        if sig in _seen:
            self._send(200, {"ok": 0, "fail": 0, "done": ["[跳过·已入库] " + d.get("title", "")], "errors": []})
            return
        title, content = build_doc_note(d)
        ok, resp = call("openapi/note/v1/import_doc",
                        {"title": title, "content": content, "content_format": 1})
        if ok:
            _seen.add(sig)
            self._send(200, {"ok": 1, "fail": 0,
                             "done": [f"✓ {title} → {resp.get('note_id', '')}"], "errors": []})
        else:
            self._send(200, {"ok": 0, "fail": 1, "done": [], "errors": [f"{title}: {resp}"]})

    def _do_save_feedback(self):
        """阅读反馈自动同步：整体替换 data/feedback.json（页面 localStorage 即反馈全集，
        取消标记也随全量覆盖自然生效），格式与 wx_rank.load_feedback 兼容"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8", "ignore"))
        except Exception as e:
            self._send(400, {"ok": 0, "fail": 1, "errors": [f"bad body: {e}"]})
            return
        fb = [f for f in (data.get("feedback") or [])
              if isinstance(f, dict) and f.get("mark") in ("like", "dislike")]
        from ima_save import DATA
        f = os.path.join(DATA, "feedback.json")
        tmp = f + ".tmp"
        json.dump({"generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "count": len(fb), "feedback": fb},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, f)
        self._send(200, {"ok": len(fb), "fail": 0,
                         "done": [f"✓ 落盘 {f}"], "errors": []})

    def _do_save_highlights(self):
        """划线回灌：不写 ima，落盘 data/highlights.json（按 key 增量合并）"""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8", "ignore"))
        except Exception as e:
            self._send(400, {"ok": 0, "fail": 1, "errors": [f"bad body: {e}"]})
            return
        items = data.get("items") or []
        if not items:
            self._send(200, {"ok": 0, "fail": 0, "done": [], "errors": []})
            return
        from ima_save import DATA
        f = os.path.join(DATA, "highlights.json")
        old = {}
        if os.path.exists(f):
            try:
                old = (json.load(open(f, encoding="utf-8")) or {}).get("articles", {}) or {}
            except Exception:
                old = {}
        for it in items:
            k = it.get("key") or f"{it.get('account','')}|{it.get('title','')}"
            old[k] = {"account": it.get("account", ""), "title": it.get("title", ""),
                      "highlights": it.get("highlights") or []}
        tmp = f + ".tmp"
        json.dump({"updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "count": sum(1 for v in old.values() if v.get("highlights")),
                   "articles": old},
                  open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, f)
        self._send(200, {"ok": len(items), "fail": 0, "done": [f"✓ 落盘 {f}"], "errors": []})

    def log_message(self, *a):   # 静音访问日志
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8931)
    ap.add_argument("--idle", type=int, default=180,
                    help="闲置多少秒无请求自动退出（0=永不退出，默认 180）")
    ap.add_argument("--mock", action="store_true",
                    help="测试模式：不真实写 ima，/save /save_doc 直接返回成功")
    args = ap.parse_args()
    if args.mock:
        def _mock_call(path, payload):
            return True, {"note_id": "mock_" + str(int(time.time() * 1000) % 100000), "mock": True}
        global call
        call = _mock_call                       # Handler 内对 call 的引用走模块全局，mock 即生效
        print("[MOCK] 测试模式：不真实写 ima，只验证链路与生命周期")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True                   # 卡住的转发线程不阻塞「闲置自动退出」
    srv.last_active = time.time()
    if args.idle > 0:
        def watchdog():
            while True:
                time.sleep(5)
                if time.time() - srv.last_active > args.idle:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 闲置 {args.idle}s 无请求，自动退出")
                    srv.shutdown()
                    return
        threading.Thread(target=watchdog, daemon=True).start()
    print(f"ima 同步服务已启动: http://127.0.0.1:{args.port}"
          + (f"（闲置 {args.idle}s 自动退出）" if args.idle > 0 else "（常驻，Ctrl+C 停止）"))
    print("日报页有暂存时会自动同步过来；同步完成后本服务自动退出，无需手动关闭。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
