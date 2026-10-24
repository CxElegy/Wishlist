# 管理ページ・架构图

## 管理ページ（docs/admin.html）

只看不改、不用口令（`render.render_admin` + `digest.admin_data`）：运行状况（最新一期、收集条数、哪几天还没 AI 编辑、几天没新消息的关注项、周报）、
打开时实时读取的 GitHub Actions 结果 / 设置页的关注项请求（`list_item_requests()`）/ 照片收件箱（`get_photo_inbox()`）、
各关注项的篇幅・7 天记事数・速報数・最新记事・話題度・缺的字段、投票统计（来自 `state/feedback.json`）。要加新数字就在 `admin_data` 里算、在 `render_admin` 里显示。
- **AI 編集の前後**（運行状況の下）：最新号で、作品ごとに「集めた件数（横棒）のうち AI 編集が記事に使った件数（青）→ 載せた記事の本数・重大／頭・未編集の新着」を 1 枚の図で見せる（`digest.edit_diff` + `render._admin_edit_diff`，`tests/test_edit_diff.py`）。
- **バックグラウンド**（管理ページ最上部）：裏で動く仕組みの「次の実行」（前回・次回・あと何分，页面打开时按 `processes.py` 的 `schedule` 实时算）
  + 版面（行）× 流程（列：収集・AI 編集・版面の設計・小元素）的状态表（済 / 待ち / 要確認 / 失敗，小元素写排第几）。数据在 `digest.backend_cells`。
  还有「待ち行列」（之后 24 小时的每次运行、那次要处理哪些版面，`digest.backend_todo`）和「ログ」（`scripts/runlog.py`：
  每个仕组み写自己的 `state/log/<proc>.json`——收集・出刊（Actions）、AI 编辑、小元素补全——分开写避免 push 冲突）。进度条带条纹动画（减少动画设定时不动）。
  版面ごとの状態 的每行：现有小元素的缩略图（行内最多 10 张 + 「+N」，展开「小元素の探し方」后看全部）+ 折叠的「小元素の探し方」（① 种类・目标 → ② 取法按顺序・各自找到几张（`emblem_fill.source_chain`，
  要和 `gather` 的顺序一致）→ ③ 本人确认・目视排除 → ④ 结果 → ⑤ 下次几点・失败时的建议），数据在 `digest.emblem_detail`。
  新加定时的仕组み：在 `PROCESSES` 里写 `schedule`（UTC 的 (时, 分)），在 `backend_todo` 写它下次做什么，运行时 `runlog.add("<proc>", "…")`；
  要加一列就在 `render.BG_COLS` 和 `backend_cells` 各加一项。
- **管理页最上面的「ライブログ」**（`scripts/livelog.py`，2026-10-19，用户定的）：像终端一样自己滚的小窗口。版面开始・进到下一段・完成（`live_boards()` 每 20 秒比前一次）、Actions 开始・成功・失败（每 3 分）、仓库 `state/log/*.json` 的新行（raw.githubusercontent.com 每 2 分）都一行一行流出来；
  **作业的一行一行（2026-10-22，用户定的）**：小元素的自动补完把每个候补外した理由・段・结果写进 Supabase `live_log`（`db/live_log.sql`，`livestatus.Lines` 每 1.5 秒一批，2 天前的行开始时删），页面 3 秒读一次 `live_log_since()`——「今すぐ再挑戦」30 秒就跑完的作业也看得见。不用 AI 的作业以后也用 `livestatus.Lines` 往这里写。
  看过的行存在 localStorage（`wl-term`，600 行），页面自动重载也不断。有「一時停止」，往上翻时不自动滚到底。原来「バックグラウンド」里的「ログ」列表移到这里。
- **管理页的「しくみの全体図」**（`scripts/overview.py`，2026-10-18）：5 页（全体 / ニュース収集 / AI 編集 / 小元素 / ページ更新），每页 ≤ 8 列、一屏放得下；点部品开 `processes.detail` 的详细流程。
  动效：`live_boards()` 每 30 秒 + Actions 实行中每 3 分，动着的部品光圈 + 斜线条（`prefers-reduced-motion` 时不动），AI 编辑／小元素按阶段（note 里的词、`found=1〜3`）分别发光；
  「反映待ち」超过 30 分的标红「止まっているかも」（push 没通的话会这样）。下方「いま待っているもの」用话说清 什么・为什么・怎么办（`overview.waits`，带「AI 编辑をもう一度起こす」「今すぐ再挑戦」按钮）。
  新增仕组み／步骤时：在 `overview.PAGES` 加部件（`proc` 必须是 `PROCESSES` 里有的），测试在 `tests/test_design.py` 的 Overview。旧的大图（「全体の構成（詳しい図）」）还在下面。
- **AI 编辑列的倒计时・失败的「今すぐ再挑戦」**：AI 编辑列表头显示「次回 9:00 / 18:00（あと N 分）」，版面の設計列显示「次の収集のあと HH:MM」+ 整理待ち件数 + ゲート前回叫起的时刻（`backend_todo` 的 edit.n / fired）；
  小元素「失败」的格子显示自动再挑战的时刻和倒计时，并有「今すぐ再挑戦」按钮（= `run_now('background')`，带 retry_now，失败的版面不等；3 分钟 1 次）。按了以后作业一行一行流进「ライブログ」（见下）。
- **今すぐ実行**（「次の実行」のカードのボタン）：後台作業・ニュース収集・ページ生成を定時を待たずに起こす。网页上没有令牌：
  按钮 → Supabase `run_now(job)`（`db/run_now.sql`，Vault 的 `github_dispatch_token`）→ GitHub workflow_dispatch。
  只能起这 3 个，每个有间隔（3 分 / 10 分 / 1 分）。GitHub 的定时（cron）忙时会迟到・漏掉（2026-10-17 漏了 2 小时），
  所以后台作業还有第 2 个时钟：Supabase pg_cron 每小时 17 分 `run_now('tick')`（和按钮同一条路，但不带 retry_now，守失败的等待）。后台作業从按钮起时带 `retry_now`（失败的版面也不等）。加新按钮：`render.RUN_JOBS` 和 `run_now` 的 case 各加一项。
- **リソース・並列と制限**（バックグラウンドの中）：容量（リポジトリ・公开页 vs 1GB 上限）、各仕组み最近一次运行时的服务器（内存・磁盘・CPU・用时，
  `scripts/resources.py` 的 `snapshot()` 附在 runlog 里）、トークン（Claude API 自动数；定时任务的 Claude 结束时自己写：
  `python scripts/runlog.py emblem "…" --tokens N`；订阅额度的余量程序读不到，只能看 https://claude.ai/settings/usage ）。
  并行：收集 6 本（`digest.COLLECT_WORKERS`，同一网站的间隔在线程间共享 `sources._pace`）、小元素 4 本（`emblem_fill.WORKERS`，
  写 items.yaml・抠图用 `WRITE_LOCK` 一本一本来）。限制写在 `processes.LIMITS`，改并行数时一起改。
- **時刻**：网页上的时间都用 `settings.display_timezone`（现在 Asia/Tokyo，用户住在日本；以后多用户按各自时区）。
  `settings.timezone`（Asia/Shanghai）只管「每天一期」的日期分界——AI 编辑的定时任务按北京时间判断「今天」，要改得两边一起改。
- **流程图每一步都标「AI が判断」还是「ルール」（用户定的）**：`processes.judged_by` 自动判断（用到 Claude = AI，用学习模型 = 「ルール＋モデル」，其他 = ルール），
  AI 的步骤是紫色粗框斜线底、规则是绿色左边条，构成图的框里写「AI n · ルール n」。Claude 判断但没挂 `claude` 札的步骤写 `"by": "ai"`。
  小元素的判断只有一张表（详细见 `docs/rules/emblem.md`） `scripts/emblem_rules.py`（流程图下的「判断の一覧」），新判断加在那里，不要在别处另写一套。
- **架构图・流程图的规矩（用户定的）**：① **精确到算法**：用到的模型、算法、API、规则都要画进去，写正确的名字和数字
  （模型名・大小、阈值、同时处理几个、间隔、每次几张），登记在 `processes.COMPONENTS`，在图上是 MODEL / ALGO / API / RULE 的札；
  改了代码里的数字，同步改这里。② **全部是图**：详细流程也画成泳道图（列 = 在哪里跑，判断 = 菱形「はい ↓ / いいえ →」，
  依次尝试 / 并行 = 横排的箱子 + 「×N 並列」），不要写成从上到下的文字列表。③ 新加仕组み、新用的模型 / 算法，加完检查图里有没有。
- **全体の構成**（管理ページ，原来的プロセス缩图一览）：整体架构图——外部服务・GitHub Actions・仓库・Pages・Claude 定时任务・Supabase・Discord・你，
  编号箭头是数据流向（`processes.ARCH` / `EDGES`，线由 JS 按部件位置画；手机上看「矢印の一覧」）。点任务的框打开那个仕组み的详细流程（`PROCESSES` 的 flow）。
  **新加一个仕组み就在 `PROCESSES` 里加一项，再放进 `ARCH` 的某个框、在 `EDGES` 连上线**；改了某个仕组み的逻辑，也同步改它的流程。
