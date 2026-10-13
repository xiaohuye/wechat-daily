# -*- coding: utf-8 -*-
"""
ima_sync.py — 本地 ima 同步服务（日报页「☁ 存入 ima」按钮的后端）

为什么需要它：日报是本地 HTML（file://），浏览器直接调 ima.qq.com 会被 CORS 拦截，
自定义 header（ima-openapi-clientid 等）必然触发失败的 preflight。
所以页面把批注 POST 给本服务（127.0.0.1:8931），由本服务转发给 ima OpenAPI。

用法：
    python scripts/ima_sync.py            # 前台启动（Ctrl+C 停止）
    python scripts/ima_sync.py --port 8932

接口：
    GET  /ping            健康检查
    POST /save            body: {"items": [{title, account, time, read, url, note, highlights:[{text,note}]}]}
                          返回: {"ok": n, "fail": n, "done": [...], "errors": [...]}
    会话级去重：同一批划线（标题+首条划线文本）本次服务生命周期内只写一次。

依赖：scripts/ima_save.py（凭证与写入逻辑）、凭证 ~/.config/ima/
"""
import os, sys, json, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ima_save import call, build_note  # noqa: E402

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

_seen = set()   # 会话级去重：本次服务生命周期内已入库的 (title|首条划线)


class Handler(BaseHTTPRequestHandler):

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/ping"):
            self._send(200, {"ok": True, "ts": datetime.datetime.now().strftime("%H:%M:%S")})
        else:
            self._send(404, {"ok": False, "msg": "not found"})

    def do_POST(self):
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

    def log_message(self, *a):   # 静音访问日志
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8931)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"ima 同步服务已启动: http://127.0.0.1:{args.port}  （Ctrl+C 停止）")
    print("日报页点「☁ 存入 ima」前请保持本服务运行；run_daily.sh 会自动后台拉起。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
