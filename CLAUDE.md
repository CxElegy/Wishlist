# 给 Claude 的约定

## 主动告诉我有哪些 MCP 连接器能用

- 任务能靠某个 MCP 连接器更方便地完成时（比如改数据库用 Supabase、看 PR 用 GitHub），**先告诉我有这个连接器**，
  不要让我自己去 SQL Editor / 网页手动操作。
- 连接器已经连上：直接说「可以用 XX 连接器帮你做」，然后去做。
- 还没连上：说清楚是哪个连接器、能帮上什么，并给出连接地址 https://claude.ai/customize/connectors
  （连好后要开新会话才会加载）。
- 已连上的连接器：Supabase（项目 `bzokpnbcjscbcehdxtjq`，表 `feedback` / `news` / `sizes` / `item_requests`）、GitHub。
  （函数 `my_votes()` = 网页读回我的投票）

## 篇幅 S / M / L

每个关注项的篇幅存在 Supabase 的 `sizes` 表，我自己在网页的 ⚙ 设置页（docs/settings.html，不用口令）也能改。
我说「把 XX 改成 L」时，用 Supabase 连接器直接改表；
连接器不可用时改 `items.yaml` 里的 `size`，下次出刊会自动同步进数据库。

## 改完自动合并

- 改动做完、测试通过后，**直接开 PR 并合并**，不用再问我「要不要合并」。合并后确认网页已更新，再附链接告诉我。

## 我的 👍 / 👎 要记住

- 投票存在 Supabase 的 `feedback` 表；网页打开时用 `my_votes()`（`db/my_votes.sql`）读回每条消息的最后一票，按钮显示成按过的样子，
  换浏览器、换手机也一样。改投票相关的代码时别丢掉这一步；推荐（`digest.py recommend`）也用这些票学习喜好。

## 每次回复都贴链接

- 回复里只要提到网页、PR、设置页，就把可以直接点开的链接贴上：
  简报 https://cxelegy.github.io/Wishlist/ 、设置页 https://cxelegy.github.io/Wishlist/settings.html 、
  愿望清单 https://cxelegy.github.io/Wishlist/wishlist.html 、話題度分析 https://cxelegy.github.io/Wishlist/heat.html 、テーマ見本 https://cxelegy.github.io/Wishlist/themes.html 、管理ページ https://cxelegy.github.io/Wishlist/admin.html 、テストグラウンド https://cxelegy.github.io/Wishlist/testground/ 、PR 用完整网址。
- 合并 PR 后网页大约 1 分钟更新（`.github/workflows/render.yml` 只重新生成网页）；
  确认网页已经更新了再告诉我，并附上链接。收集新闻、发通知仍由「关注清单通信」慢慢跑。

## 完善关注项

设置页上「新增关注项」（一问一答的向导，docs/additem.js）加进来的关注项，`notes` 里写着「从网页设置页加进来的」。
我说「完善关注项」时，找出这些项，检查向导生成的 `match`、`urgent_patterns`（正则是按选项拼的，可能太宽或太窄；`match` 按下面「匹配词的写法」改，跑 `audit-match` 看有没有误收），
补上 `similar`、`status`、`theme`，缺的 `steam_appid` / `anilist_id` / `tmdb` / `site` / `wiki`（维基词条，話題度用）也补上，并把 `notes` 改成真正的背景说明。
向导的问题和选项（关注哪方面、要紧消息的词、不想看的词）都在 `docs/additem.js` 开头的 KINDS / EXCLUDES 里，要加选项改那里。
选项上 `rec: true` = 「不确定，你帮我定」时替我选它；`when: about(/…/)` = 只在名字或维基数据说明里有这些词时才出现（比如「猫相关的」只给跟猫有关的东西），别再给所有东西都出同一套选项。

## 匹配词（match）的写法：防止误收

收进版面的消息，标题或摘要里必须有 `match` 里的某个词（忽略大小写和空格，所以「FROM season」也会命中「…from season 10 of …」）。
加关注项、改 `match` / `exclude`、「完善关注项」时都按这几条写，写完跑一次检查：

- **名字是常用词或缩写时不要直接写**：剧名 From、缩写 MCU（也是微控制器）这类，用 `re:` 开头的正则（区分大小写、照原文匹配），
  只认确定是它的写法（全大写的 `re:\bFROM\b`、标题开头的 `re:^From Season \d`）；或者把撞名的领域写进 `exclude`（MCU → 晶片、MPU、飆股）。
- **泛词必须和主题词同时出现**：「マグ」「感染症」「獣医」「ペット用品」单独出现会混进别家、别的动物，
  写成一条 `re:(?is)(?=.*(主题词…))(?=.*(泛词…))`（例：星巴克马克杯、猫用品）。只有专有名词（作品名、牌子名、人名）才单独写。
- **数字、年份、季号不单独当匹配词**：「26/27」也是音乐节 COUNTDOWN JAPAN 26/27，「Season 5」到处都是。
- **名字是常用词的作品不做 Reddit 全站搜索**：`use: [google, bing]`，社区讨论只看它自己的版块（`subreddits`）。
- **网店、二手的商品页**（「本物」「定番新品」「au PAY マーケット」）写进 `exclude`。
- **检查**：`python scripts/digest.py audit-match`（`--only "名字、名字"` 只看几项）把最近几天收进来的条目按「靠哪个词进来的」列出来，
  ✗ 是按现在的规则已经不会再收的。每组看一眼标题，有不相关的就收紧那个词；误收已经上了版面的，
  从当天还没有 `.edit.json` 的 inbox 里删掉、把报告里那条拿掉，再重新出刊。`tests/test_match.py` 有这几种写法的例子。

## 网页设计：加新内容时的规则（设计框架）

网页是公开的，以后会不断加新内容。新东西**套进现有框架**，不要每次另起一套：

- **产品事实**在 `PRODUCT.md`（读者、语言、原则）；改网页前先看。界面文字（标题、按钮、说明）一律日语，消息内容保持原语言。
- **颜色、字体**只用 `scripts/render.py` 开头 `:root` 里的设计令牌（`--ink` `--paper` `--rose` `--sheet` `--card` `--gold` `--alert`、
  `--font-sans/serif/mono`、`--fs-label`）。要新颜色先加令牌，不要在 CSS 里直接写十六进制。
- **新板块（ジャンル）**：只要在 `items.yaml` 的 `section` 写新名字。颜色自动从 `GENRE_EXTRA` 里分配（都过 AA），
  日语名默认就是写的名字；想要固定的颜色 / 日语名 / 英文标签，加进 `SECTIONS` / `SECTION_JA` / `SECTION_EN`。
- **新类型的消息信息**（价格、日程、视频、图集）：已经有部件，AI 编辑在 edit.json 里写 `price` / `event` / `video` / `gallery`
  （见 `EDITING.md`「追加字段」）就会显示；头版「これからの予定」自动汇总将来的 `event`。
- **真正的新部件**：在 `render.py` 里写一个函数（参照 `_extras` / `_agenda`：没有数据就返回空字符串、链接只收 http(s)、文字都转义），
  CSS 只用令牌，在 `tests/test_design.py` 加测试，再在 `EDITING.md` 写清字段。
- **检查**：`python -m unittest discover -s tests`（`test_design.py` 检查字号 ≥10px、令牌、板块色对比度、部件）；
  改完界面再跑一次 `.claude/skills/impeccable/scripts/impeccable detect --json <生成的 html>`，并在 1400 / 390 / 320 px 宽截图确认不换行、不横向滚动。
- **现在的视觉（2026-10-16 定）**：配色就是原版令牌；骨架借 P5 的手法但不照搬：文字箱后面硬阴影（`--shadow`）、标题和框只倾斜 1〜2.5°（`--tilt`）、
  标签是平行四辺形（`.tg`，`--skew`）。正文、列表、作品版面不倾斜。トップ是「每天刷新的海报」：底色由当天头条的配图取色
  （`_poster_colors`，缓存在 `state/themes.json` 的 `hero|图片URL`）；「ほかの注目ニュース」= 照片墙 + 各板块的「棚」（不放纯文字列表；手机上棚竖着叠、每个板块最多 3 个作品，不横向滚动）；
  「気になるかも？」是店长 POP 卡。图片规则：比例接近框的铺满，不接近的放在模糊底上完整显示（`FIT_JS`），所以任何配图都能放进同一个模板。
  **不要留空、要对齐**：照片墙的小卡片照片框统一 16:10 铺满裁边、标题留 3 行高，同一段的卡片底边对齐；`SPOT_COUNT` 是候选张数，`FIT_JS` 里的 `wall()` 只显示放得进右列高度的整段，剩下的高度平均加给照片，墙底和右列底边齐平。
  各作品版面的普通消息一排最多 3 张、连着的几张平均分行（4 张 = 2+2，`_layout`），只剩一张时做横长卡片，不让一张小卡片占整行；日程・价格（`xevent` / `xprice`）放在字的下面。
  左边的目录（`NAV_JS` 的 `pick`）亮的是「屏幕里露出标题、最靠上的」版面，一个标题都看不到时是盖住屏幕顶边的那个。
  Bing 新闻缩略图（`bing.com/th?…&w=1200`）原图小时会补白边，`_img_url` 去掉 w/h 用原尺寸。
- **版面主题（motif）**：`items.yaml` 里给作品写 `motif:`，主题在 `templates/`（`index.yaml` 一览 + 每套一份 `<id>.css`，只用作品自己的配色变量）。
  现在有 **30 套**（背景花纹、题字形状、照片边框、标题旁装饰字），每套带一个 **👍 演出**（`fx`，`scripts/likefx.py` 的 20 种：大拇指的动作 + 飞散的形状 + 文字）。
  一览和试玩：テーマ見本 https://cxelegy.github.io/Wishlist/themes.html （`render.render_themes`）。
  **每个新关注项加进来时，AI 都要把版面设计一遍**（`TEMPLATES.md` 开头的表）：① 主题 `motif` ② 配色 `theme`（暗底 / 浅底按作品气质，字一定要看得清）
  ③ 作品小元素 `emblem`（`scripts/emblem.py` 找现有的、认得出的图，可多张、每次打开随机一张；不自己画、不改原图）④ 点 👍 的演出 `like_fx`（不写就用主题的 fx）；
  设置页加进来的由「AI 编辑」设计（工作流在加进来后叫它）；设计好之前先按 `type` 借用 `index.yaml` 里 `defaults` 对得上的主题。
  点 👍 的演出按版面（`data-fx`）选：同一套主题的版面演出一样。新演出：在 `likefx.py` 的 `FX_JS` 和 `FX` 各加一行。
  **演出别自己从零做**：粒子用 canvas-confetti、擬音按漫画的作法（Dela Gothic One・双层描边・ウニフラ・逐字砸下・震动），参照成熟的前端设计。
  **配色要协调**：版面配色跟作品的代表色（主视觉、角色、小元素）搭，不让补色强色打架（例：橙色的ポチタ配深蓝就不行），见 `TEMPLATES.md`「配色的协调」。
- **話題度（热度指数）**：`scripts/heat.py` 用 6 个维度算 0〜100（報道量・広がり・出来事・勢い・一般の関心〔维基浏览量〕・ファンの反応），
  每维 = 60% 跟自己平常比 + 40% 同一把尺子；拿不到的维度不算 0 分而是从分母去掉。外部数据随收集存进 `state/heat_signals.json`，
  分数在生成网页时算（不联网）。网页：各版面标题栏的数字（点开看内訳）+ トップ右列「話題度ランキング」，
  两处都能进分析页 `docs/heat.html`（`render.render_heat`：KPI・ヒートマップ表・前週比・作品ごとの内訳とグラフ・計算方法）。
  分析页的图表按 dataviz 规范：颜色只用 `--viz-*`（指标）/ `--seq-*`（点数浓淡）/ `--up` `--down`，文字用 HTML 叠在 SVG 上。
  改权重 / 满分线 / 等级改 `heat.py` 开头的 `DIMS` / `REF` / `LEVELS`，测试在 `tests/test_heat.py`。
- **大改视觉**用 impeccable 的 new-work 流程（`/impeccable`），做完写 `DESIGN.md`。

## 管理ページ（docs/admin.html）

只看不改、不用口令（`render.render_admin` + `digest.admin_data`）：运行状况（最新一期、收集条数、哪几天还没 AI 编辑、几天没新消息的关注项、周报）、
打开时实时读取的 GitHub Actions 结果 / 设置页的关注项请求（`list_item_requests()`）/ 照片收件箱（`get_photo_inbox()`）、
各关注项的篇幅・7 天记事数・速報数・最新记事・話題度・缺的字段、投票统计（来自 `state/feedback.json`）。要加新数字就在 `admin_data` 里算、在 `render_admin` 里显示。
- **バックグラウンド**（管理ページ最上部）：裏で動く仕組みの「次の実行」（前回・次回・あと何分，页面打开时按 `processes.py` 的 `schedule` 实时算）
  + 版面（行）× 流程（列：収集・AI 編集・版面の設計・小元素）的状态表（済 / 待ち / 要確認 / 失敗，小元素写排第几）。数据在 `digest.backend_cells`。
  还有「待ち行列」（之后 24 小时的每次运行、那次要处理哪些版面，`digest.backend_todo`）和「ログ」（`scripts/runlog.py`：
  每个仕组み写自己的 `state/log/<proc>.json`——收集・出刊（Actions）、AI 编辑、小元素补全——分开写避免 push 冲突）。进度条带条纹动画（减少动画设定时不动）。
  新加定时的仕组み：在 `PROCESSES` 里写 `schedule`（UTC 的 (时, 分)），在 `backend_todo` 写它下次做什么，运行时 `runlog.add("<proc>", "…")`；
  要加一列就在 `render.BG_COLS` 和 `backend_cells` 各加一项。
- **リソース・並列と制限**（バックグラウンドの中）：容量（リポジトリ・公开页 vs 1GB 上限）、各仕组み最近一次运行时的服务器（内存・磁盘・CPU・用时，
  `scripts/resources.py` 的 `snapshot()` 附在 runlog 里）、トークン（Claude API 自动数；定时任务的 Claude 结束时自己写：
  `python scripts/runlog.py emblem "…" --tokens N`；订阅额度的余量程序读不到，只能看 https://claude.ai/settings/usage ）。
  并行：收集 6 本（`digest.COLLECT_WORKERS`，同一网站的间隔在线程间共享 `sources._pace`）、小元素 4 本（`emblem_fill.WORKERS`，
  写 items.yaml・抠图用 `WRITE_LOCK` 一本一本来）。限制写在 `processes.LIMITS`，改并行数时一起改。
- **時刻**：网页上的时间都用 `settings.display_timezone`（现在 Asia/Tokyo，用户住在日本；以后多用户按各自时区）。
  `settings.timezone`（Asia/Shanghai）只管「每天一期」的日期分界——AI 编辑的定时任务按北京时间判断「今天」，要改得两边一起改。
- **全体の構成**（管理ページ，原来的プロセス缩图一览）：整体架构图——外部服务・GitHub Actions・仓库・Pages・Claude 定时任务・Supabase・Discord・你，
  编号箭头是数据流向（`processes.ARCH` / `EDGES`，线由 JS 按部件位置画；手机上看「矢印の一覧」）。点任务的框打开那个仕组み的详细流程（`PROCESSES` 的 flow）。
  **新加一个仕组み就在 `PROCESSES` 里加一项，再放进 `ARCH` 的某个框、在 `EDGES` 连上线**；改了某个仕组み的逻辑，也同步改它的流程。
- **小元素（emblem）**：每个版面右上的贴纸。规矩（种类 → 目标枚数 → 取法的顺序 → 本人确认）在 `scripts/emblem_fill.py`、`scripts/face_id.py`，说明在 `TEMPLATES.md`；
  管理页「小元素」列出每个版面的种类・目标・现有枚数，没到目标的 AI 编辑会自动补（`python scripts/emblem_fill.py --audit`）。


## テストグラウンド（docs/testground/）

本番の简报に入れる前に部品を試すページ。入口 https://cxelegy.github.io/Wishlist/testground/ （`index.html`）。消さずに残し、新しい試作もここに足す（入口に 1 枚カードを足す）。
- `compare.html`：左の目次 v1〜v6 の見比べ（条件 10 パターン・画面の高さ・「ダミーで試す」で作品数 2〜1000）
- `rails.html`：目次の見本 10 パターン ／ `nav.html`：本文つきで 1 本
- **左の目次は v6 に決定（2026-10-17）**：パソコンは「少ないうちは隠さない・段階的に隠す」（隠し始めるのは既定 24 件、件数で／自動。隠す前に行を 22px まで詰める → ①ほかの板块は新着順に数件 ②ほかは見出しだけ ③いまの小分類だけ ④入るだけ＋「ほか N 件」）。
  小分類の札は必ず出す。見た目は線路（原版）＋作品アイコン（emblem → 記事の写真 → 頭文字）＋板块アイコン。スマホは上に 2 段の横帯だけの簡単な形。2026-10-17 に本番（`render._nav` / `NAV_JS` / `NAV_STYLES["line"]`）へ移した。
  隠し始める件数は `items.yaml` の `settings.nav_hide`（既定 24、`auto` で画面の高さ）。件数以内でも行を 30px まで詰めて入らなければ隠す（窮屈にしない）。小分類は関注項に `sub:`（例 `sub: ドラマ`）を書くと目次に札が出る（板块内に 2 つ以上あるとき）。
