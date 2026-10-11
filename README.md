# Wishlist · 关注清单简报

定期抓取你关注的**商品、产品类别、游戏、动画漫画、影视剧**的最新消息，整理成简报。

思路参考 [agents-radar](https://github.com/duanyytop/agents-radar)：**信息由脚本从免费 RSS / API 抓取，AI 只负责把抓到的标题归纳成几句话**，不让 AI 自己联网搜索，token 消耗很低。

## 工作流程

```
items.yaml ──► 抓取（Google/Bing 新闻 / Steam / AniList / TMDB / Reddit / RSS）← 免费
          ──► 过滤（时间窗口 + 关键词匹配 + 和往期去重）                    ← 免费
          ──► AI 归纳（只发标题和摘要，引用只写编号）                      ← 很少的 token
          ──► reports/YYYY-MM-DD.md + reports/LATEST.md + GitHub Issue
```

## 使用

1. **编辑 [`items.yaml`](items.yaml)**，写上你的关注项。文件开头有每个字段的说明。
   - `type: product`：具体商品，例如某款耳机
   - `type: category`：一整类产品，例如 OLED 显示器
   - `type: game`：游戏；填上 `steam_appid` 会额外抓 Steam 官方公告和当前价格，并对比上期价格
   - `type: anime`：动画或漫画；会从 AniList 抓播出状态，自动追到最新一季，新季官宣、开播、完结时会标出变化
   - `type: show`：电影或剧集；填上 `tmdb` 后会从 TMDB 抓播出状态和下一集时间，需要免费的 `TMDB_API_KEY`
2. **添加 API Key**（可选）：仓库 Settings → Secrets and variables → Actions → New repository secret，名称填 `ANTHROPIC_API_KEY`。
   不设置也能跑，只是不做 AI 归纳，直接列出链接。
   关注剧集或电影时，再添加一个 `TMDB_API_KEY`，在 themoviedb.org 的账号设置里免费申请。
3. **运行**：每周一自动运行，也可以在 Actions → 关注清单简报 → Run workflow 手动触发。

想改运行频率，就改 `.github/workflows/digest.yml` 里的 `cron`，例如每天运行：`17 0 * * *`。

## 本地运行

```bash
pip install -r requirements.txt
python scripts/digest.py --dry-run   # 只看抓到了什么，不调用 AI、不写文件
ANTHROPIC_API_KEY=... python scripts/digest.py
```

## 成本

- 抓取、过滤、去重、Steam 价格都不花钱。
- AI 每个关注项调用一次，只发送最多 `max_entries_per_item` 条标题。默认模型 `claude-haiku-5-5`（$0.10 / 百万输入 token），十几个关注项每周花费大约几美分。
- 设置 `summarize: false` 可以完全不调用 AI。

## 目录

| 路径 | 说明 |
|---|---|
| `items.yaml` | 关注清单和设置 |
| `scripts/sources.py` | 各数据源的抓取函数，新增数据源就加在这里 |
| `scripts/digest.py` | 主流程：抓取 → 过滤 → 归纳 → 输出 |
| `reports/` | 历次简报，`LATEST.md` 是最新一期 |
| `state/` | 已报道过的链接和上期价格，用于去重和比价，请勿手动修改 |
