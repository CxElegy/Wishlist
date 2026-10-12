# Wishlist · 关注清单通信

每 2 小时自动收集你关注的**游戏、动画、影视剧、商品、艺人演出**的最新消息，编成报纸式的简报网页（GitHub Pages）。每个作品一个固定版面、用它自己的配色，新消息直接更新进各自的版面：一周内的按重要度和时间显示，更早的收进可展开的「更多消息」，旧消息永远保留。
有要紧消息（定档、开放预约、下次测试公布……）**当天立刻**通过 Discord 通知；其余的**每周一**发一次周报。

思路参考 [agents-radar](https://github.com/duanyytop/agents-radar)：**信息由脚本从免费 RSS / API 抓取，AI 只负责把抓到的标题编排成几条报道**，不让 AI 自己联网搜索，token 消耗很低。

## 愿望清单

看到喜欢的东西，跟 Claude 说「加进 wishlist」并附上截图或链接就行（做法写在 `.claude/skills/wishlist/SKILL.md`）。
数据在 `wishlist.yaml`，图片在 `docs/wishlist/`；网页上是单独的子页面（[wishlist.html](https://cxelegy.github.io/Wishlist/wishlist.html)，主页报头右上角有入口，可按 想要 / 已入手 / 没买到 筛选），推送后 Discord 会收到一条带大图的通知。
填了 `watch`（关联的关注项）的，版面上会顺带显示那个关注项的最新消息。
主页的「**我会喜欢？**」角落有两部分，每条都写明推荐理由，都不让 AI 联网：
- 按愿望清单里每件东西的 `likes`（喜好标签），从最近两周收集到的所有消息里挑 5 条；
- 「同类新发现」：按 `items.yaml` 里每个关注项的 `similar`（同类搜索词），每天搜一次 Google 新闻，去掉已经在关注的作品，每个关注项挑一条（最多 4 条）。

每条推荐下面有 **👍 喜欢 / 👎 不感兴趣**，投票存进 Supabase（Postgres 数据库，设置见下面「投票数据库」），每次出刊时从投票学习口味：
- 赞过的推荐命中的喜好标签、具体关键词（如「猫」「Snoopy」）各 +1，踩过的各 −1，累加起来给之后的候选加减分（最多 +4 / −6）；
- 踩过的那条消息、和别家报道的同一件事不再推荐；
- 「同类新发现」常赞的同类排前面，净踩两次以上的同类先不推荐；
- 卡片上写明起作用的投票，如「按你的投票：猫 +2」。再点一次已选中的按钮是撤销。

## 流程

**图解**（开启 GitHub Pages 后可直接打开网页版）：

| 图 | 网页 | 图片 |
|---|---|---|
| 流程图（含时间轴、费用、GitHub 限制附录） | [flow.html](https://cxelegy.github.io/Wishlist/design/flow.html) | [flow.png](docs/design/flow.png) |
| 架构图（哪个任务在哪个环境） | [architecture.html](https://cxelegy.github.io/Wishlist/design/architecture.html) | [architecture.png](docs/design/architecture.png) |
| 工作流程图解 | [guide.html](https://cxelegy.github.io/Wishlist/design/guide.html) | [guide.png](docs/design/guide.png) |
| 合并图（分支怎么合、合并之后的流程） | [merge.html](https://cxelegy.github.io/Wishlist/design/merge.html) | [merge.png](docs/design/merge.png) |
| 编排逻辑（一条新闻怎么变成网页上的卡片、三条编排路、去重的四道关） | [editing.html](https://cxelegy.github.io/Wishlist/design/editing.html) | [editing.png](docs/design/editing.png) |

设计稿源文件在 `design/`（Claude 设计画布格式，修改时用）。

分两步，中间用 `inbox/` 里的数据文件衔接。

GitHub Actions 的安排：

| 时间 | 做什么 |
|---|---|
| 每 2 小时 | 收集 → 更新当天的简报网页 → 命中 `urgent_patterns` 的要紧消息立刻发 Discord（发过的不重发） |
| 每周一 08:47（北京时间） | 发 Discord 周报：过去 7 天每个关注项的要点 + 网页链接 |
| 每天 12:43 · 23:43（北京时间） | Claude 定时任务（AI 编辑）把当天的条目编成中文报道、合并同一件事 |
| 新加关注项推送后 | 收集到消息就立刻叫 AI 编辑编一次，不等定时（需要仓库 Secret `ROUTINE_FIRE_TOKEN`：claude.ai/code/routines → 「关注清单通信 · AI 编辑」→ 编辑 → 添加触发器 → API → 生成令牌） |

```
items.yaml
  │
  ├─ ingest（收集，免费）
  │    抓取  Google 新闻 / Bing 新闻 / Reddit / Steam / AniList / TMDB / 任意 RSS
  │    过滤  时间窗口 + 关键词 + 与往期去重
  │    输出  inbox/YYYY-MM-DD.json（原始条目、状态变化、封面）
  │
  └─ publish（出刊）
       编排  按优先级：inbox/YYYY-MM-DD.edit.json（人工或 Claude 写的）
                     > Claude API（summarize: true 时）
                     > 关键词规则 priority_keywords（免费，默认）
       配图  Reddit 图 / 文章预览图 / 作品封面；配色取自作品主视觉
       输出  reports/YYYY-MM-DD.json + docs/index.html（GitHub Pages）→ Discord 通知
```

版面规则：
- 直接回答你最关心问题的新消息（例如公布了测试时间、上线日期）标为**重大**，单独占满一整行
- 其余第一条做头条大图，后面两条放侧栏，剩下的三栏一排
- 没有新消息的关注项本期不出现；播出状态、价格等只在有变化时才显示

## 第一次设置

1. **开启 GitHub Pages**：仓库 Settings → Pages → Build and deployment → Source 选 *Deploy from a branch*，分支选默认分支，文件夹选 `/docs`。
   简报地址：`https://cxelegy.github.io/Wishlist/`
2. **连接 Claude API（可选，默认不用）**：只有 `summarize: true` 时才需要，二选一

   **A. Workload Identity Federation（推荐，不需要存任何 Key）**
   1. 在 [Claude Console](https://platform.claude.com) → Settings → Workload identity → **Connect workload** → 选 **GitHub Actions**
   2. 按向导填写，匹配条件这样填（只允许这个仓库的默认分支）：
      - Subject prefix：`repo:CxElegy/Wishlist:ref:refs/heads/main`
      - Audience：`https://api.anthropic.com`
      - Claims：`repository_owner` = `CxElegy`
   3. 向导完成后会给出 federation rule ID（`fdrl_` 开头）和 service account ID（`svac_` 开头）；organization ID 在 Settings → Organization
   4. 回到 GitHub：仓库 Settings → Secrets and variables → Actions → **Variables** 标签页 → New repository variable，添加：

      | Name | Value |
      |---|---|
      | `ANTHROPIC_FEDERATION_RULE_ID` | `fdrl_...` |
      | `ANTHROPIC_ORGANIZATION_ID` | 组织 ID（UUID） |
      | `ANTHROPIC_SERVICE_ACCOUNT_ID` | `svac_...` |

      这些只是 ID，不是密码，所以放 Variables 而不是 Secrets。

   **B. API Key**：在 **Secrets** 标签页添加 `ANTHROPIC_API_KEY`。

   不配置就用关键词规则编排，直接用原标题。

3. **Discord 通知**：在 Discord 频道 → 编辑频道 → 整合 → Webhook → 新建 Webhook → 复制 Webhook 网址，
   然后在 GitHub 仓库 Settings → Secrets and variables → Actions → **Secrets** 添加 `DISCORD_WEBHOOK_URL`。

   其它可选的 Secrets：

   | 名称 | 用途 |
   |---|---|
   | `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit 常拦截云服务器的匿名请求，用官方 API 才稳定。在 [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) 创建一个 *script* 类型的应用即可（免费） |
   | `TMDB_API_KEY` | 关注影视剧时需要，在 themoviedb.org 的账号设置里免费申请 |

4. **投票数据库（可选，「我会喜欢？」的 👍 / 👎 用）**：没设置时网页上不显示按钮。
   1. 在 [supabase.com](https://supabase.com) 注册（免费），New project 新建一个项目（名字随意，数据库密码自己记下）。
   2. 左侧 **SQL Editor** → 把 [`db/feedback.sql`](db/feedback.sql) 整段粘贴进去 → Run。建好 `feedback` 表：网页只能往里新增投票，读不到也改不了。
   3. 项目的 **Connect** 按钮（或 Project Settings → Data API）里复制 Project URL；Project Settings → **API Keys** 里复制 publishable key（`sb_publishable_` 开头）和 secret key（`sb_secret_` 开头）。
   4. 把 Project URL 和 publishable key 填进 `items.yaml` 的 `settings` → `supabase_url` / `supabase_key`（publishable key 本来就是公开给网页用的）。
   5. secret key 放进 GitHub 仓库 Settings → Secrets and variables → Actions → **Secrets**，名字 `SUPABASE_SERVICE_KEY`。**不要**写进任何文件。

   投票在每次出刊（每 2 小时）时读出来学习，同时存一份到 `state/feedback.json`。
   注意：网页是公开的，知道网址的人理论上也能投票（只能新增）；真有乱投，在 Supabase 的 Table Editor 里删掉那几行即可。

5. **运行**：Actions → 关注清单通信 → Run workflow（勾选“顺便发一次周报”可以测试 Discord）。之后会自动运行；想改频率，改 `.github/workflows/digest.yml` 里的 `cron`。

## 添加关注项

编辑 [`items.yaml`](items.yaml)，文件开头有每个字段的说明。最重要的几个：

- `keywords`：各语言的正式名称都写上
- `priority`：你最关心它的什么，比如「什么时候能玩」「第二季什么时候播」「什么时候降价」
- `type`：`game` / `anime` / `show` / `product` / `category`
- `urgent_patterns`：什么样的标题算要紧消息（正则），命中就当天通知 Discord
- `theme`：可选，手写配色；不写就从封面自动取色

## 本地运行

```bash
pip install -r requirements.txt
python scripts/digest.py --dry-run   # 只看抓到了什么，不写文件
python scripts/digest.py             # 收集 + 出刊
python scripts/digest.py ingest      # 只收集到 inbox/
python scripts/digest.py publish     # 只出刊（用最新一份 inbox，有 .edit.json 就按它编排）
python scripts/digest.py render      # 改了版式后，用已有数据重新生成网页
python scripts/digest.py notify-urgent   # 把还没通知过的要紧消息发到 Discord
python scripts/digest.py notify-weekly   # 发过去 7 天的周报
python -m unittest discover tests       # 运行测试（本地假网站，不联网）
```

## 成本

默认完全免费：收集、关键词编排、配图、取色都不调用任何付费接口。

想让 AI 把标题翻成中文、按关注重点挑选和合并，有两种方式：
- 在 Claude 里让 Claude 读 `inbox/` 写 `.edit.json`（用你的 Claude 订阅，不另外付费）
- 打开 `summarize: true` 并配置 Claude API（按量付费，默认 `claude-haiku-5-5`，十几个关注项每周大约几美分）

## 目录

| 路径 | 说明 |
|---|---|
| `items.yaml` | 关注清单和设置 |
| `scripts/sources.py` | 各数据源的抓取，新增数据源加在这里 |
| `scripts/images.py` | 配图：找候选图、实际下载检查、按顺序回退，记录没图的原因（Actions 日志里的 `[配图]` 行和「配图汇总」） |
| `scripts/digest.py` | 主流程：抓取 → 过滤 → 编辑 → 输出 |
| `scripts/theme.py` | 从封面图提取板块配色 |
| `scripts/render.py` | 简报网页的版式 |
| `scripts/notify.py` | Discord 通知（要紧消息 / 周报） |
| `tests/` | 测试 |
| `inbox/` | 每期收集到的原始条目；`.edit.json` 是对应的编排 |
| `reports/` | 每期出刊的数据（JSON） |
| `docs/` | 简报网页，由 GitHub Pages 发布；`docs/design/` 是流程图和架构图 |
| `design/` | 流程图、架构图、简报样式的设计稿源文件 |
| `EDITING.md` | AI 编辑的工作规则 |
| `db/feedback.sql` | 投票数据库（Supabase）的建表语句 |
| `state/` | 已报道的链接、上期状态、配色缓存，请勿手动修改 |
