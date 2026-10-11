# Wishlist · 关注清单通信

每周自动收集你关注的**游戏、动画、影视剧、商品**的最新消息，编成一张报纸式的简报网页：每个作品用它自己的配色，新一期总在最上面。

思路参考 [agents-radar](https://github.com/duanyytop/agents-radar)：**信息由脚本从免费 RSS / API 抓取，AI 只负责把抓到的标题编排成几条报道**，不让 AI 自己联网搜索，token 消耗很低。

## 流程

分两步，中间用 `inbox/` 里的数据文件衔接：

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
       输出  reports/YYYY-MM-DD.json + docs/index.html（GitHub Pages）+ GitHub Issue 提醒
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
      - Subject prefix：`repo:CxElegy/Wishlist:ref:refs/heads/claude/sharp-gauss-osunmb`
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

3. **其它 Secrets（可选）**，在 **Secrets** 标签页添加：

   | 名称 | 用途 |
   |---|---|
   | `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit 常拦截云服务器的匿名请求，用官方 API 才稳定。在 [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) 创建一个 *script* 类型的应用即可（免费） |
   | `TMDB_API_KEY` | 关注影视剧时需要，在 themoviedb.org 的账号设置里免费申请 |

4. **运行**：Actions → 关注清单简报 → Run workflow。之后每周一北京时间 08:17 自动运行；想改频率，改 `.github/workflows/digest.yml` 里的 `cron`。

## 添加关注项

编辑 [`items.yaml`](items.yaml)，文件开头有每个字段的说明。最重要的几个：

- `keywords`：各语言的正式名称都写上
- `priority`：你最关心它的什么，比如「什么时候能玩」「第二季什么时候播」「什么时候降价」
- `type`：`game` / `anime` / `show` / `product` / `category`
- `theme`：可选，手写配色；不写就从封面自动取色

## 本地运行

```bash
pip install -r requirements.txt
python scripts/digest.py --dry-run   # 只看抓到了什么，不写文件
python scripts/digest.py             # 收集 + 出刊
python scripts/digest.py ingest      # 只收集到 inbox/
python scripts/digest.py publish     # 只出刊（用最新一份 inbox，有 .edit.json 就按它编排）
python scripts/digest.py render      # 改了版式后，用已有数据重新生成网页
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
| `scripts/digest.py` | 主流程：抓取 → 过滤 → 编辑 → 输出 |
| `scripts/theme.py` | 从封面图提取板块配色 |
| `scripts/render.py` | 简报网页的版式 |
| `inbox/` | 每期收集到的原始条目；`.edit.json` 是对应的编排 |
| `reports/` | 每期出刊的数据（JSON） |
| `docs/` | 简报网页，由 GitHub Pages 发布 |
| `state/` | 已报道的链接、上期状态、配色缓存，请勿手动修改 |
