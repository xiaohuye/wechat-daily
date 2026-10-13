# 公众号日报（wechat-daily）

每天自动抓取你在微信读书里关注的公众号更新 → 分类分析 → 输出一份带「推荐阅读」的 HTML 日报。

## 整体链路

```
① 关注全集（一次性）
   微信读书 Agent 网关 /shelf/sync —— 官方只读接口，零封号风险
      → config/wechat_accounts.json      124 个公众号（name / book_id / last_read）

② 分类画像（一次性，可迭代）
   scripts/wx_classify.py —— 人工 TYPE_MAP 把 124 个号分成 9 类 + 关注强度分层
      → config/accounts_classified.json  +  output/公众号关注画像.html

③ 抓取更新（每日）
   scripts/weread_login.py   扫码登录一次，持久化 profile（data/weread_profile）
   scripts/weread_fetch.py   页面内同源 fetch 调 /web/mp/articles，批量抓全部号
      → data/articles-weread-<时间戳>.json

④ 推荐排序 + 分析（每日）
   scripts/wx_rank.py     启发式打分（类型权重 / 热度 / 时效 / 关键词）
      → data/ranked-weread-<时间戳>.json
   scripts/wx_insight.py  汇总概览 / 主题分布 / 推荐清单
      → data/insights-weread-<时间戳>.json

⑤ 抓正文（每日）—— 免跳转阅读的关键
   scripts/weread_content.py  调 /web/mp/content?reviewId=，把整篇正文搬回本地
      → data/articles-full-weread-<时间戳>.json

⑥ 生成精读版日报（每日）
   scripts/wx_reader.py   正文内嵌 + 划线批注 + 求解释 + 批注抽屉
      → output/公众号日报-精读版-YYYY-MM-DD-HHMM.html

⑦ 批注入 ima（手动触发）
   scripts/ima_save.py    把精读页导出的批注 md（划线+批注+原文）成对写入 ima 笔记/知识库
```

## 🔴 为什么必须内嵌正文（重要）

微信公众号原文链接在**非作者环境**会触发「环境异常」人机验证，即使链接完全正确也打不开；
而用微信读书内部 hash（originalId）直拼的 `mp.weixin.qq.com/s/<hash>` 更是直接返回「参数错误」。

实测三种形态：

| 链接形态 | 结果 |
|---|---|
| `mp.weixin.qq.com/s/<originalId>` | ❌ 参数错误（页面无正文） |
| `mp.weixin.qq.com/s?__biz=...&mid=...&sn=...`（真实链接） | ❌ 环境异常，要求人机验证 |
| `weread.qq.com/web/mp/content?reviewId=...` | ✅ **完整正文 HTML**，807ms/篇，含图片 |

因此本方案的阅读闭环是：**把正文直接搬进日报页面**，你打开就能读，不用跳转。

## ⚡ 一键运行

```bash
cd E:/wokrbudy/wechat-daily
bash scripts/run_daily.sh                    # 默认：1 天窗口 / 推荐 30 篇 / 抓 25 篇正文
DAYS=3 TOP=30 FULL=20 bash scripts/run_daily.sh
```

## 快速使用（分步）

```bash
cd E:/wokrbudy/wechat-daily
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 首次（或登录态失效时）扫码登录
$PY scripts/weread_login.py

$PY scripts/weread_fetch.py --days 1
$PY scripts/wx_rank.py --days 1 --top 30
$PY scripts/wx_insight.py
$PY scripts/weread_content.py --top 25        # 抓正文
$PY scripts/wx_reader.py --top 25             # 生成精读版
```

### 常用参数

| 脚本 | 参数 | 说明 |
|---|---|---|
| weread_fetch.py | `--days N` | 只保留最近 N 天（默认 3） |
|               | `--pages N` | 每个号翻几页（默认 1，每页约 20 条） |
|               | `--limit N` | 只抓前 N 个号（调试用） |
| wx_rank.py | `--days N` / `--top N` | 时间窗 + Top 数量 |
| weread_content.py | `--top N` | 抓前 N 篇正文 |
|                   | `--ids file.json` | 指定篇目 |
| wx_reader.py | `--top N` | 精读页收录篇数 |
| ima_save.py | `--md <随笔.md>` | 从精读页导出的随笔批量入库 |
|             | `--dry-run` | 只预览不写入 |

## 📚 读 + 划线批注 + 存进 ima（完整闭环）

1. **打开** `output/公众号日报-精读版-*.html`，点「📖 展开正文」直接读（正文已内嵌，无需跳转）
2. **划线批注**：在正文里**选中任意句子** → 弹出工具条 →
   - 🖍 **划线批注** → 写你对这句话的批注（Ctrl+Enter 保存）
   - 💡 **求解释** → 一键复制「解释请求」（含划线 + 上下文 + 原文链接），粘到对话里我就帮你讲清楚
   - 📋 **复制** → 只复制选中句子
3. **管理批注**：点每条划线可再次编辑 / 删除；顶部「🖍 划线批注」打开右侧抽屉，支持**全文搜索**划线内容与批注，点击可**跳回原文位置**并高亮
4. **带走**：顶部「📋 复制全部批注」（直接粘贴给 AI 顺手入库）或「📤 导出 .md」
5. **入库**：把内容粘回对话，或直接跑
   ```bash
   $PY scripts/ima_save.py --md 公众号精读批注-2026-10-13.md
   ```
   脚本会把「文章标题 + 公众号 + 原文链接 + 每条划线及其批注」组装成一篇 ima 笔记。

> 划线批注自动保存在浏览器本地（`localStorage`，key 前缀 `wxhl::`），刷新、下次打开都还在；
> 同一篇文章的划线以「字符偏移量」定位，所以即使重新生成日报（内容不变）也能对上。
> 有批注的划线是**深黄色**，纯划线是**浅黄色**。

> ima 写入需先在 https://ima.qq.com/agent-interface 获取 Client ID / API Key，然后
> ```bash
> mkdir -p ~/.config/ima
> echo "<client_id>" > ~/.config/ima/client_id
> echo "<api_key>"   > ~/.config/ima/api_key
> ```
> 未配置时 `ima_save.py` 会提示并支持 `--dry-run` 预览将要入库的内容。


## 推荐引擎 v1 打分口径

```
总分 = 1.0 × 账号类型权重 + 1.6 × log10(阅读数) + 1.1 × 时效衰减 + 0.9 × 关键词命中
```

- **账号类型权重**：`AI 产品与工具实践 1.0 / 大厂官方技术号 0.95 / AI 创业与产业观察 0.9 … 个人 IP 0.3`
- **热度**：`log10(read_num+1)/5`，10 万+ 约合 1.0
- **时效**：7 天内线性衰减
- **关键词**：命中 `agent / skill / mcp / workflow …` 加分，命中 `抽奖 / 优惠 / 招聘 …` 减分
- **去重**：同号 + 标题前 12 字相同的只保留最高分

> 权重集中在 `scripts/wx_rank.py` 顶部常量 `TYPE_W / KW_GOOD / KW_BAD / W_*`，
> 后续根据你的阅读反馈直接改这几个值即可迭代。
> 进阶：把「你点开/收藏/跳过」的记录攒成反馈集，用逻辑回归/GBDT 学权重替换启发式。

## 数据源说明（为什么最终选微信读书）

| 方案 | 结论 |
|---|---|
| 读本地微信数据库（pywxdump） | ❌ pywxdump 3.1.46 不支持微信 4.x；有封号风险，用户否决 |
| 读浏览器 Cookie | ❌ Chrome 154 使用 v20 app-bound 加密，密钥绑定提权服务，离线解密不可行 |
| CookieCloud（mcp-server-weread） | ❌ `cc.chenge.ink` 本机不可达（代理 502 / 直连超时） |
| wechat2rss 公共源 | ⚠️ 可用但覆盖低：实测 68 个常见号仅命中 14 个（21%），无法自助加号 |
| **微信读书书架（当前方案）** | ✅ 官方只读接口，124 个号全覆盖，零封号风险 |

## 目录结构

```
wechat-daily/
├─ config/
│   ├─ wechat_accounts.json          ① 微信读书书架 124 个公众号
│   ├─ accounts_classified.json      ② 分类 + 关注强度分层
│   ├─ accounts.json                 备用：wechat2rss 订阅清单
│   └─ wechat2rss_catalog.json       备用：395 个公共源目录
├─ scripts/
│   ├─ run_daily.sh        ⚡ 一键跑通 ③~⑥
│   ├─ weread_login.py     ③ 扫码登录
│   ├─ weread_fetch.py     ③ 批量抓取文章列表
│   ├─ wx_rank.py          ④ 推荐排序
│   ├─ wx_insight.py       ④ 生成 insights
│   ├─ weread_content.py   ⑤ 抓正文（免跳转关键）
│   ├─ wx_reader.py        ⑥ 生成精读版日报（划线批注）
│   ├─ ima_save.py         ⑦ 批注 + 原文 写入 ima
│   ├─ wx_report.py        备用：纯清单日报（无正文）
│   ├─ wx_classify.py      ② 分类画像
│   └─ wx_fetch.py         备用：wechat2rss 抓取
├─ data/      抓取 / 排序 / insights / 正文 JSON + weread_profile（登录态）
└─ output/    公众号关注画像.html / 公众号日报-精读版-*.html
```

## 自动化

已配置每日 08:30 定时任务「公众号日报（微信读书源）」，执行 `run_daily.sh` 全链路
（抓取 → 排序 → 分析 → 抓正文 → 生成精读版），并推送推荐 Top10。
登录态过期时任务会提示重新扫码（`output/weread_qr.png`）。
