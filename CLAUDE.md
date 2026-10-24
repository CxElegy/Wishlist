# 给 Claude 的约定

@WORKING.md
（↑ 仕事の進め方：言われたこと＋次の一手・反論・提案・影響表・自分で確かめる。毎回読む）

## 詳しい仕様は docs/rules/（その分野を触る前に必ず読む）

ここは毎回要る決まりだけ。細かい仕様は下のファイルへ移した（2026-10-24，用户定的：決まりは 1 つも消さない）。
「CLAUDE.md「○○」」と書いてある参照は、この表で節の名前から探す。

| ファイル | 中の節 | 読むとき |
|---|---|---|
| `docs/rules/accounts.md` | test1 / test2（全文） | account・test2・sitedir・`p_account`・Supabase の `account` 列を触る |
| `docs/rules/sections.md` | 小分类（subs）必填・板块一览・シリーズ・上级系列・面・判断上下级（parent） | 関注項を足す・板块 / 小分類 / 面 / parent・`sections.yaml`・`taxonomy.py` |
| `docs/rules/match.md` | 匹配词（match）的写法・垃圾站・exclude_hosts・情報源・地域ごとの情報員・audit-match | `match` / `exclude`・収集・`sources.py`・`intel/`・`drop_reason` |
| `docs/rules/wizard.md` | 完善关注项・向导的小规则 | 「完善关注项」・`docs/home/additem.js`・设置页の依頼 |
| `docs/rules/design.md` | 网页设计（设计框架・视觉・配图・hdimg・scrapling・motif・話題度）・目次のロゴと炎・目次のアイコン・テストグラウンド（各ページ・新闻语言・目次 v6） | 画面・CSS・`render.py`・画像・テーマ・`heat.py`・目次・入口 `welcome.py` |
| `docs/rules/live.md` | 页面自动更新・「更新中」条 | `LIVE_JS` / `BUSY_JS`・`version.json`・`live_status` |
| `docs/rules/admin.md` | 管理ページ・バックグラウンド表・ライブログ・しくみの全体図・今すぐ実行・リソース・時刻・AI/ルールの札・架构图・流程图的规矩・全体の構成 | 管理ページ・`processes.py`・`overview.py`・`run_now` |
| `docs/rules/background.md` | 收集不停・省 token（规则化）・小元素补全の再試行・后台的ゲート・整理待ち・持ち越し・AI 编辑（2 回 / 停滞 / 分批 / 暂停・重做 / token） | `gate.py`・`background.yml`・`digest.yml`・AI 编辑・`edit-next` |
| `docs/rules/emblem.md` | 小元素の「違う」・全身 / 半身・小元素（emblem）の規矩 | `emblem*.py`・`face_id.py`・小元素 |
| `docs/rules/library.md` | ライブラリ・お客さまのアカウント（全文） | `library.py`・`db/library.sql`・お客さまの版面 |
| `docs/rules/login.md` | ログイン（全文）・お客さまの記事集め（`userfeed.py`） | ログイン・`AUTH_JS`・`db/auth*.sql`・`userfeed.py`・`user_boards` |
| `docs/rules/lang.md` | 读者的语言：主言語・副言語 | `lang.py`・言語の去重 |

## スキル（2026-10-22，用户定的）

- 設計・実装の前に `find-skills`（`npx skills find …`）で合うスキルを探し、インストール数・出どころを確かめて入れる（`.claude/skills/`、出どころと指紋は `skills-lock.json`）。直す前に、スキルの考え方（他の人の framework・設計理念）に照らして直し方を決める。
- トークンの節約（2026-10-24）：ponytail（コードは最小の完全な変更）・caveman（係どうしの報告を短く、ユーザーへの返事は普通の日本語）・caveman-compress（長いファイルを短く、使う前に確かめる）。HARNESS.md「トークンを節約する」。
- デザイン（2026-10-24）：emil-design-eng・review-animations・improve-animations（Emil Kowalski）・impeccable・design-taste-frontend（Taste）。
- 入れてあるもの：find-skills・supabase・supabase-postgres-best-practices・web-design-guidelines・frontend-design・webapp-testing・web-perf・seo-audit・signup・onboarding・site-architecture・improve-codebase-architecture・python-testing-patterns（＋前からの impeccable・diagram・wishlist）。

- 画面を作る・変える段は HARNESS.md「どこにでもある AI っぽさから抜け出す・自分で設計して確かめる」の順で（参考 → 作りの決まり（emil-design-eng・impeccable・review-animations）→ 考え（Taste）→ 設計（Figma MCP）→ 作る → 確かめる（Playwright MCP・inspect.mjs・impeccable detect）→ 見せる）。`.mcp.json` に Playwright MCP。

## 主动告诉我有哪些 MCP 连接器能用

- 连接器能更方便完成时（改数据库 = Supabase、看 PR = GitHub），**先告诉我有这个连接器**，不让我去 SQL Editor / 网页手动操作。
- 已连上：说「可以用 XX 连接器帮你做」，然后去做。没连上：说哪个连接器、能帮什么，给 https://claude.ai/customize/connectors （连好后开新会话才加载）。
- 已连上：Supabase（项目 `bzokpnbcjscbcehdxtjq`，表 `feedback` / `news` / `sizes` / `item_requests`；函数 `my_votes()` = 网页读回我的投票）、GitHub。

## 篇幅 S / M / L

篇幅存 Supabase `sizes` 表，我也能在 ⚙ 设置页（docs/settings.html，不用口令）改。我说「把 XX 改成 L」→ 用 Supabase 连接器直接改表；连接器不可用 → 改 `items.yaml` 的 `size`，下次出刊自动同步进数据库。

## 改完自动合并

- 做完、测试通过 → **直接开 PR 并合并**，不问「要不要合并」。合并后确认网页已更新，附链接告诉我。
- **开 PR 前先改架构图**：改了逻辑（规则・算法・阈值・流程・定时）→ 同一个 PR 改 `scripts/processes.py`（`COMPONENTS` 加 / 改札，`PROCESSES` 的 `flow` 加步骤、`uses` 连上），规矩见 `docs/rules/admin.md`「架构图・流程图的规矩」。
  CI `scripts/check_arch.py` 拦：改了 `scripts/*.py` 或 workflow 没改 `processes.py` 的 PR 不通过。不影响图的，PR 说明写一行「架构图：不用改（理由）」。（2026-10-17 连着漏两次后加的）

## 我的 👍 / 👎 要记住

投票存 Supabase `feedback` 表；网页打开时 `my_votes()`（`db/my_votes.sql`）读回每条消息的最后一票，按钮显示成按过的样子，换浏览器・手机也一样。改投票代码时别丢这一步；推荐（`digest.py recommend`）也用这些票学喜好。

## 每次回复都贴链接

- 回复提到网页・PR・设置页，就贴能点开的链接：
  简报（店長のページ）https://cxelegy.github.io/Wishlist/home/ 、设置页 https://cxelegy.github.io/Wishlist/home/settings.html 、
  愿望清单 https://cxelegy.github.io/Wishlist/home/wishlist.html 、話題度分析 https://cxelegy.github.io/Wishlist/home/heat.html 、テーマ見本 https://cxelegy.github.io/Wishlist/home/themes.html 、管理ページ https://cxelegy.github.io/Wishlist/home/admin.html 、テストグラウンド https://cxelegy.github.io/Wishlist/testground/ 、PR 用完整网址。
  入口 https://cxelegy.github.io/Wishlist/ ，存档 test2 https://cxelegy.github.io/Wishlist/test2/ 。
- 合并 PR 后网页约 1 分钟更新（`.github/workflows/render.yml` 只重新生成网页）；确认更新了再告诉我、附链接。收集新闻・发通知仍由「关注清单通信」慢慢跑。

## test1 / test2・account（要点。全文 `docs/rules/accounts.md`）

- **test1 = 店長のページ**（2026-10-21，用户定的）：`items.yaml`・`wishlist.yaml`・`inbox/`・`reports/`・`state/` が店長のもの。网页 `docs/home/`（`sitedir.SLUG = "home"`）。**网址不出现 test1・人名・「店長」**（用户定的）；大家同一个网址，内容由登录的人决定。Supabase account 名 `test1`（`sitedir.NAME`，以后换成 `user_id`）。店長は `c.elegy@outlook.com` でログイン。
- **test2** = 冻结在 `docs/test2/`，数据 `archive/test2/`，不再生成。test2 で決めた規則（一个名字一个版面・向导・入口）は店長のページでも使う。
- 根 `docs/index.html` = 入口（`scripts/welcome.py` 生成）。
- **account 各自分开、互不相通**（用户定的，2026-10-19）：Supabase 的表都有 `account` 列（`db/accounts.sql`）；网页只用带 `p_account` 的函数（`window.WL_ACCOUNT`）；Actions 经 `scope_account` 只读写自己的行。页面里不留别的 account 的痕迹。

## ライブラリ・お客さま（要点。全文 `docs/rules/library.md`，2026-10-23，用户定的：作り直し中）

- 店長もお客さまも**同じ仕組み・同じ画面の作り**。前の「お客さま用の別の仕組み」（`userfeed.py`・`user_boards`・JS で描いた版面・左右に払うカード）は間違いで、外す。
- ライブラリ（`db/library.sql`：`boards`・`board_stories`・`follows`）= みんなの版面の置き場。記事集め・AI 編集・デザインは版面ごとに 1 回、全員が同じものを受け取る。版面の設定の本物はライブラリ。
- 人ごと：👍👎・欲しい物・置き方・篇幅・画面の言語。お客さまのページとデータは本人と店長だけ（公開のリポジトリ・Pages に置かない）。

## ログイン（要点。全文 `docs/rules/login.md`，2026-10-20，用户定的）

- 访客 = 見るだけ。お客さま = 邮箱＋密码（テスト用 `test-a〜e@example.com` 密码 `0000`）。店長 = `invites` の role=admin（最多 5 个），邮箱＋密码。
- 门番は数据库（`db/auth.sql`・`db/auth_guard.sql`：`can_edit(p_account)` / `is_admin()`）、网页（`render.AUTH_JS`）は按钮を拦めて理由を言うだけ。**开关 enforce は 2026-10-21 に打开**。
- 改登录相关的东西时同步改 `processes.py` 的 `login`。设定步骤は `LOGIN.md`。

## 保留中のこと

（2026-10-19 追加）向导は「要紧消息 → Discord」を問わない（`additem.js` の `URGENT_ASK = false`）、新しい関注項は `urgent_patterns` が空。詳しくは `PENDING.md`。
ユーザーが「あとでやる」と決めたものは `PENDING.md` に書く（何を止めたか・なぜ・試作の場所・わかったこと）。本番からは外し、試作はテストグラウンドに残す。炎の演出も保留中（`render.NAV_FLAME = False`，`docs/rules/design.md`）。

## テストグラウンド（docs/testground/）

本番に入れる前に部品を試すページ。入口 https://cxelegy.github.io/Wishlist/testground/ （`index.html`）。消さずに残し、新しい試作もここに足す（入口に 1 枚カードを足す）。各ページの説明は `docs/rules/design.md`「テストグラウンド」。
