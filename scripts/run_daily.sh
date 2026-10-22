#!/usr/bin/env bash
# run_daily.sh — 公众号日报「一键跑通」
# 抓取 → 排序 → 分析 → 抓正文 → 生成精读版日报（正文内嵌，免跳转）
#
# 用法：
#   bash scripts/run_daily.sh                    # 默认：最近 1 天，推荐 30 篇，抓【全部更新】正文
#   FULL=25 bash scripts/run_daily.sh            # 只抓推荐前 25 篇正文（更快，其余仅标题+摘要）
#   FULL=0 TOP=30 bash scripts/run_daily.sh      # 同默认：全量抓取（推荐 + 其它全部更新）
#   DAYS=3 TOP=30 bash scripts/run_daily.sh
#
# 说明：默认 FULL=0（全量）时，日报「全部更新」列表里的每篇都会尝试抓正文；
#       抓不到文字正文的（图片型 / SVG 交互排版）会在列表中保留标题+摘要+原文链接，不再丢弃。
#
# 退出码：
#   0  成功
#   2  抓取失败
#   3  登录态失效（需重新扫码：python scripts/weread_login.py）
set -u
cd "$(dirname "$0")/.."

PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
DAYS="${DAYS:-1}"
TOP="${TOP:-30}"
FULL="${FULL:-0}"

log(){ echo "[$(date '+%H:%M:%S')] $*"; }

# ---------- 前置：登录态体检 ----------
# 抓取脚本在登录失效时会以退出码 2 结束；这里先做一次轻量探测，
# 让定时任务能在「一开始」就明确报出「需要重新扫码」，而不是跑一半才断。
if [ "${SKIP_LOGIN_CHECK:-0}" != "1" ]; then
  log "登录态检查…"
  if ! "$PY" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath("scripts")), "scripts"))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sys.exit(0)   # 没有 playwright 就跳过体检，交给正式抓取去报错
ROOT = os.path.abspath(".")
PROFILE = os.path.join(ROOT, "data", "weread_profile")
EXE = None
for c in (r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
          r"C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe"):
    if os.path.exists(c):
        EXE = c; break
if not EXE or not os.path.isdir(PROFILE):
    sys.exit(1)   # 从未登录过
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0 Safari/537.36")
JS = """async () => {
  try {
    const r = await fetch('/web/mp/articles?bookId=MP_WXS_2398602260&offset=0', {credentials:'include'});
    const j = await r.json();
    return j.errCode === -2010 ? 'OUT' : 'IN';
  } catch(e) { return 'ERR'; }
}"""
try:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, executable_path=EXE, headless=True,
              viewport={"width":1280,"height":800}, user_agent=UA, locale="zh-CN")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://weread.qq.com/", timeout=45000)
        pg.wait_for_timeout(1200)
        st = pg.evaluate(JS)
        ctx.close()
    sys.exit(0 if st in ("IN", "ERR") else 1)
except Exception:
    sys.exit(0)   # 探测本身出错就不拦，交给正式抓取
PYEOF
  then
    echo ""
    echo "!!! 登录态已失效，需要重新扫码 !!!"
    echo "    请运行： $PY scripts/weread_login.py"
    echo "    然后用微信扫描 output/weread_qr.png"
    echo ""
    exit 3
  fi
  log "登录态正常"
fi

# ---------- 1/5 抓取 ----------
log "=== [1/5] 抓取公众号更新（最近 ${DAYS} 天）==="
if ! "$PY" scripts/weread_fetch.py --days "$DAYS"; then
  rc=$?
  if [ "$rc" = "3" ] || [ "$rc" = "2" ]; then
    echo ""
    echo "!!! 抓取失败（退出码 $rc）——很可能是登录态失效 !!!"
    echo "    请运行： $PY scripts/weread_login.py"
    echo ""
    exit 3
  fi
  exit 2
fi

ART=$(ls -t data/articles-weread-*.json 2>/dev/null | head -1)
[ -n "$ART" ] || { echo "未生成抓取结果"; exit 2; }
log "→ $ART"

# ---------- 2/5 排序 ----------
log "=== [2/5] 推荐排序 ==="

# ---------- 先拉起 ima 同步服务：页面挂着的用户，昨天的划线/反馈在排序前自动冲刷落盘 ----------
if "$PY" -c "import socket;s=socket.socket();s.settimeout(1);raise SystemExit(0 if s.connect_ex(('127.0.0.1',8931))==0 else 1)" 2>/dev/null; then
  log "ima 同步服务已在运行 (127.0.0.1:8931)"
else
  nohup "$PY" scripts/ima_sync.py >/dev/null 2>&1 &
  sleep 1
  log "ima 同步服务已拉起 (8931) —— 日报页开着时自动冲刷暂存队列（划线/反馈即生效）"
fi
log "--- 等待 25s 冲刷窗口（页面 watcher 15s 轮询 + 发送）---"
sleep 25

# ---------- 3/3 排序（先学习划线关键词，再打分） ----------
log "--- 划线关键词学习 + 排序推荐 ---"
if [ -f data/highlights.json ]; then
  "$PY" scripts/wx_kw_learn.py || echo "(关键词学习失败，跳过)"
else
  log "无划线语料（highlights.json 不存在），跳过关键词学习"
fi
"$PY" scripts/wx_rank.py --days "$DAYS" --top "$TOP" || exit 2

# ---------- 3/5 分析 ----------
log "=== [3/5] 生成分析（概览/主题/推荐）==="
"$PY" scripts/wx_insight.py --top "$TOP" || exit 2

# ---------- 4/5 抓正文 ----------
# FULL=0 表示全量抓取（推荐 + 其它全部更新），配合 --reuse 避免重复下载
if [ "$FULL" = "0" ]; then
  log "=== [4/5] 抓取全部更新正文（复用已抓过的）==="
  "$PY" scripts/weread_content.py --all --reuse || exit 2
else
  log "=== [4/5] 抓取推荐篇目正文（前 ${FULL} 篇，复用已抓过的）==="
  "$PY" scripts/weread_content.py --top "$FULL" --reuse || exit 2
fi

FULLJSON=$(ls -t data/articles-full-weread-*.json 2>/dev/null | head -1)
[ -n "$FULLJSON" ] || { echo "未生成正文结果"; exit 2; }
log "→ $FULLJSON"
RANKJSON=$(ls -t data/ranked-weread-*.json 2>/dev/null | head -1)
INSJSON=$(ls -t data/insights-weread-*.json 2>/dev/null | head -1)
log "→ ${RANKJSON:-（无）} / ${INSJSON:-（无）}"

# ---------- 5/5 生成日报 ----------
log "=== [5/5] 生成精读版日报 ==="
if [ "$FULL" = "0" ]; then
  "$PY" scripts/wx_reader.py --top "$TOP" --full "$FULLJSON" --articles "$ART" --rank "$RANKJSON" --insights "$INSJSON" || exit 2
else
  "$PY" scripts/wx_reader.py --top "$FULL" --full "$FULLJSON" --articles "$ART" --rank "$RANKJSON" --insights "$INSJSON" || exit 2
fi

echo
log "=== 完成 ==="
ls -t output/公众号日报-精读版-*.html 2>/dev/null | head -1
echo
log "附带生成旧版清单日报（无正文）："
"$PY" scripts/wx_report.py "$ART" || true
