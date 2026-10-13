#!/usr/bin/env bash
# run_daily.sh — 公众号日报「一键跑通」
# 抓取 → 排序 → 分析 → 抓正文 → 生成精读版日报（正文内嵌，免跳转）
#
# 用法：
#   bash scripts/run_daily.sh              # 默认：最近 1 天，推荐 30 篇，抓前 25 篇正文
#   DAYS=3 TOP=30 FULL=20 bash scripts/run_daily.sh
set -u
cd "$(dirname "$0")/.."

PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
DAYS="${DAYS:-1}"
TOP="${TOP:-30}"
FULL="${FULL:-25}"

echo "=== [1/5] 抓取公众号更新（最近 ${DAYS} 天）==="
"$PY" scripts/weread_fetch.py --days "$DAYS" || exit 2

ART=$(ls -t data/articles-weread-*.json | head -1)
echo "→ $ART"

echo "=== [2/5] 推荐排序 ==="
"$PY" scripts/wx_rank.py --days "$DAYS" --top "$TOP"

echo "=== [3/5] 生成分析（概览/主题/推荐）==="
"$PY" scripts/wx_insight.py --top "$TOP"

echo "=== [4/5] 抓取推荐篇目正文（前 ${FULL} 篇，免跳转阅读用）==="
"$PY" scripts/weread_content.py --top "$FULL"

FULLJSON=$(ls -t data/articles-full-weread-*.json | head -1)
echo "→ $FULLJSON"

echo "=== [5/5] 生成精读版日报 ==="
"$PY" scripts/wx_reader.py --top "$FULL"

echo
echo "=== 完成 ==="
ls -t output/公众号日报-精读版-*.html | head -1
echo
echo "旧版清单日报（无正文）："
"$PY" scripts/wx_report.py "$ART" || true
