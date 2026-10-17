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
- **开 PR 前先改架构图**：改了逻辑（规则、算法、阈值、流程、定时）就同一个 PR 里改 `scripts/processes.py`（`COMPONENTS` 加 / 改札，对应 `PROCESSES` 的 `flow` 加步骤、`uses` 连上），见下「架构图・流程图的规矩」。
  CI 的 `scripts/check_arch.py` 会拦：改了 `scripts/*.py` 或 workflow 却没改 `processes.py` 的 PR 不通过。确实不影响图的，在 PR 说明里写一行「架构图：不用改（理由）」。（2026-10-17 连着漏了两次后加的）

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
补上 `subs`（小分类，每种分法都写）、判断 `parent`（见下「判断上下级」），补上 `similar`、`status`、`theme`，缺的 `steam_appid` / `anilist_id` / `tmdb` / `site` / `wiki`（维基词条，話題度用）也补上，并把 `notes` 改成真正的背景说明。
向导的问题和选项（关注哪方面、要紧消息的词、不想看的词）都在 `docs/additem.js` 开头的 KINDS / EXCLUDES 里，要加选项改那里。
选项上 `rec: true` = 「不确定，你帮我定」时替我选它；`when: about(/…/)` = 只在名字或维基数据说明里有这些词时才出现（比如「猫相关的」只给跟猫有关的东西），别再给所有东西都出同一套选项。

## 新增关注项时：小分类（subs）必填，分法由用户选

**每个板块、每个领域都一定要有小分类**，加关注项时一定写 `subs`，哪怕某个小分类里只有它一项。
一个板块有几种「分法」（`sections.yaml` 的 `schemes`，例：ゲーム = 状態 / プラットフォーム，映像 = 種類 / 地域，
ライブ = シーン / 形態，スポーツ = 種目 / 楽しみ方，グッズ = 種類 / ブランド・キャラ）。**每种分法都要写**：`subs: {status: 運営中, platform: スマホ}`。
先用 `sections.yaml` 里的常用值（`values`），放不进去再起新名字（日语，短）。
**用哪种分法由用户在 ⚙ 设置页选**（板块ごと，存 Supabase 的 `nav_schemes` 表，`db/nav_schemes.sql`；选了立刻重新生成网页）。没选的板块用第一种。
要加新的分法：在 `sections.yaml` 这个板块的 `schemes` 里加一项 `{id: 英小写, label: 日语, values: [...]}`，再给这个板块的所有关注项补上这个分法的值。

## 板块一览（sections.yaml，2026-10-17 定）

**板块事先定全，新关注项只是「对号入座」，不临时开新板块、不为建板块叫 AI。**参考 IAB Content Taxonomy 3.1 的大类，按日本网站的叫法合并成 17 个：
游戏 ゲーム・影视 映像・运动 スポーツ・演出 ライブ・好物 グッズ・时尚 ファッション・书刊 本・マンガ・宠物 ペット・美食 グルメ・数码 テック・
出行 おでかけ・艺术 アート・爱好 ホビー・家居 暮らし・健康 健康・汽车 乗り物・其他 その他。没有关注项的板块网页上不显示。
- 每个板块在 `sections.yaml` 里有：日语名・英文标签・颜色（过 AA）・图标・向导的默认类型・**对号入座的词**（`words`）・两种分法和常用值（`schemes`）。
  `scripts/taxonomy.py` 读它（`render` 的 `SECTIONS` / `SECTION_JA` / `SECTION_EN` / `SECTION_ICON`、`digest` 的 `sub_schemes` 都从这里来），设置页的向导用同一张表。
- 对号入座（全是规则）：维基数据的说明・名字里的词，按表从上到下先命中的板块（`taxonomy.classify`）；小分类选说明里出现的值，没有就第一个（`guess_subs`，值可以写成 `{v: 雑誌, re: magazine|杂志}` 带外语说法）。都没命中按 type，再没有就「其他」。
- 设置页提交的 `section` 只收表里的板块，`subs` 一起写进 items.yaml。
- 判断不准时改 `words` / `re`（加词、调顺序：宠物在美食前面，所以「dog food」是宠物），在 `tests/test_taxonomy.py` 加一个例子。要新板块就在 `sections.yaml` 加一项（颜色先过 AA），不用改代码。

## 新增关注项时：判断上下级（parent）

加关注项（设置页的向导、我说「加进关注清单」、「完善关注项」）时，**先看它和已有关注项是不是上下级**，是就在下级那一项写 `parent: 上级的名字`：
- **新项是已有项的下级**：同一系列 / 品牌 / 联赛 / 艺人里的一部作品、一个商品、一次巡演（スパイダーマン → 漫威电影、Galaxy S27 → 三星手机、某次巡演 → 周杰伦）。
- **新项是已有项的上级**：后加的是系列本身（先有スパイダーマン，后加漫威电影）→ 回头给已有的下级项写 `parent`。
- **怎么判断**：维基数据的「系列（P179）」「属于（P361）」「媒体系列（P8345）」、名字和 `keywords` 是否包含上级的名字、官网是否同一个。拿不准就问我，别硬挂。
- **只做一层**：没有「孙」（漫威 › スパイダーマン › 续集 不做，续集挂到漫威或スパイダーマン其中一个）。
- 下级项的 `section` 和上级相同；`subs`（小分类）写它自己真实的类别（デアデビル是剧集 → `subs: {kind: ドラマ, …}`）。目次上下级跟着上级放（案 A），自己的类别和上级不同时，名字旁标一个小的类别标签。
- **同一条新闻不出现两次**（PRODUCT.md 原则 4）：下级的新闻也会命中上级的 `match`（「スパイダーマン 新作」里常有「Marvel」）。上下级都收到时只放进下级的版面，上级版面只放系列整体的消息。
- 目录上的显示定为**案 A 枝分かれ**（2026-10-17）：上级是普通的站，下级挂在从上级那一站分出的支线（拐角 └）上。
  上下级都是关注项、地位一样：下级**不缩小、不特别折叠**，大小和普通的站一样，隐藏与否照 v6 的规则。2026-10-17 已接进本番（`render._nav`），见 テストグラウンド https://cxelegy.github.io/Wishlist/testground/franchise.html 。
  「同一条新闻不出现两次」的去重在 `render._dedupe_parents`（上下级都收到的新闻只留在下级的版面）。

## 匹配词（match）的写法：防止误收

收进版面的消息，标题或摘要里必须有 `match` 里的某个词（忽略大小写和空格，所以「FROM season」也会命中「…from season 10 of …」）。
加关注项、改 `match` / `exclude`、「完善关注项」时都按这几条写，写完跑一次检查：

- **名字是常用词或缩写时不要直接写**：剧名 From、缩写 MCU（也是微控制器）这类，用 `re:` 开头的正则（区分大小写、照原文匹配），
  只认确定是它的写法（全大写的 `re:\bFROM\b`、标题开头的 `re:^From Season \d`）；或者把撞名的领域写进 `exclude`（MCU → 晶片、MPU、飆股）。
- **泛词必须和主题词同时出现**：「マグ」「感染症」「獣医」「ペット用品」单独出现会混进别家、别的动物，
  写成一条 `re:(?is)(?=.*(主题词…))(?=.*(泛词…))`（例：星巴克马克杯、猫用品）。只有专有名词（作品名、牌子名、人名）才单独写。
- **数字、年份、季号不单独当匹配词**：「26/27」也是音乐节 COUNTDOWN JAPAN 26/27，「Season 5」到处都是。
- **名字是常用词的作品不做 Reddit 全站搜索**：`use: [google, bing]`，社区讨论只看它自己的版块（`subreddits`）。
- **Reddit 只放真的火的帖子（用户定的，2026-10-17）**：版块看本周最热榜（`/top?t=week`）前 5，全站搜索看按热度排的前 5；配了 Reddit API 时还要赞 ≥100 或评论 ≥30。
  不火的不上版面，只记进 inbox 的 `reddit_cold` 给話題度数帖子数。已经上了版面的帖子每天复查一次：被删（[removed]/[deleted]）或掉出榜就撤掉（`digest.prune_reddit`）。
- **网店、二手的商品页**（「本物」「定番新品」「au PAY マーケット」）写进 `exclude`。
- **检查**：`python scripts/digest.py audit-match`（`--only "名字、名字"` 只看几项）把最近几天收进来的条目按「靠哪个词进来的」列出来，
  ✗ 是按现在的规则已经不会再收的。每组看一眼标题，有不相关的就收紧那个词；误收已经上了版面的，
  从当天还没有 `.edit.json` 的 inbox 里删掉、把报告里那条拿掉，再重新出刊。`tests/test_match.py` 有这几种写法的例子。

## 网页设计：加新内容时的规则（设计框架）

网页是公开的，以后会不断加新内容。新东西**套进现有框架**，不要每次另起一套：

- **产品事实**在 `PRODUCT.md`（读者、语言、原则）；改网页前先看。界面文字（标题、按钮、说明）一律日语，消息内容保持原语言。
- **颜色、字体**只用 `scripts/render.py` 开头 `:root` 里的设计令牌（`--ink` `--paper` `--rose` `--sheet` `--card` `--gold` `--alert`、
  `--font-sans/serif/mono`、`--fs-label`）。要新颜色先加令牌，不要在 CSS 里直接写十六进制。
- **新板块（ジャンル）**：板块事先定全在 `sections.yaml`（见上「板块一览」），`items.yaml` 的 `section` 只写表里的 key。
  真要加板块就在 `sections.yaml` 加一项（日语名・英文标签・颜色・图标・分法），不用改 `render.py`。
- **新类型的消息信息**（价格、日程、视频、图集）：已经有部件，AI 编辑在 edit.json 里写 `price` / `event` / `video` / `gallery`
  （见 `EDITING.md`「追加字段」）就会显示；头版「これからの予定」自动汇总将来的 `event`。
- **真正的新部件**：在 `render.py` 里写一个函数（参照 `_extras` / `_agenda`：没有数据就返回空字符串、链接只收 http(s)、文字都转义），
  CSS 只用令牌，在 `tests/test_design.py` 加测试，再在 `EDITING.md` 写清字段。
- **检查**：`python -m unittest discover -s tests`（`test_design.py` 检查字号 ≥10px、令牌、板块色对比度、部件）；
  改完界面再跑一次 `.claude/skills/impeccable/scripts/impeccable detect --json <生成的 html>`，并在 1400 / 390 / 320 px 宽截图确认不换行、不横向滚动。
- **现在的视觉（2026-10-16 定）**：配色就是原版令牌；骨架借 P5 的手法但不照搬：文字箱后面硬阴影（`--shadow`）、标题和框只倾斜 1〜2.5°（`--tilt`）、
  标签是平行四辺形（`.tg`，`--skew`）。正文、列表、作品版面不倾斜。トップ是「每天刷新的海报」：底色由当天头条的配图取色
  （`_poster_colors`，缓存在 `state/themes.json` 的 `hero|图片URL`）；「ほかの注目ニュース」= 照片墙 + 各板块的「棚」（不放纯文字列表；手机上棚竖着叠、每个板块最多 3 个作品，不横向滚动）；
  「気になるかも？」是店长 POP 卡。图片规则：**配图不裁切**（文字・ロゴ入りのバナーが欠ける）：比例几乎一样（|ln 比| < 0.08，最多切 8%）才铺满，其余放在模糊底上完整显示（`FIT_JS`），所以任何配图都能放进同一个模板。
  **不要留空、要对齐**：照片墙的小卡片照片框统一 16:10（框的大小统一，照片不裁，比例不合的放模糊底上）、标题留 3 行高，同一段的卡片底边对齐；`SPOT_COUNT` 是候选张数，`FIT_JS` 里的 `wall()` 只显示放得进右列高度的整段，剩下的高度平均加给照片，墙底和右列底边齐平。
  各作品版面的普通消息一排最多 3 张、连着的几张平均分行（4 张 = 2+2，`_layout`），只剩一张时做横长卡片，不让一张小卡片占整行；日程・价格（`xevent` / `xprice`）放在字的下面。
  左边的目录（`NAV_JS` 的 `pick`）亮的是「屏幕里露出标题、最靠上的」版面，一个标题都看不到时是盖住屏幕顶边的那个。
  Bing 新闻缩略图（`bing.com/th?…&w=1200`）原图小时会补白边，`_img_url` 去掉 w/h 用原尺寸。
  **配图清晰度・显示不出来（2026-10-17 定，全是规则、不用 AI）**：`images.pick` 原文的预览图长边 < 1000 时先换同一页更大的版（JSON-LD 的 1920×1080）；
  MSN 的视频（`vi-`）・图集读接口的 `thumbnail` / `slides`；新浪 sinaimg 这类防盗链（不带 Referer 就 403）的原文图，带原文网页作 Referer 再试，来源名加「（本站保存）」。
  出刊时 `hdimg.py` 用 OpenCV 判断「看不清吗」：**原图看得清就不动、不花资源**（用户定的）。只有网页上要放大 1.6 倍以上、而且放到显示大小后模糊度 > 0.42（无参考 re-blur 法）的图
  才去噪 NLMeans → Lanczos4 放大（最多 3 倍）→ 亮度 USM；Bing 只给 100×100 的缩略图改取 w=1200 版切白边；防盗链的图存一份。都放 `docs/pics/`（`state/hdimg.json` 记对应关系，过 8 天删），`render._img_url` 优先用本站的、打不开再用原图。手动：`digest.py hd-images`。
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

## 目次のロゴと炎（2026-10-17）

目次の左上に仮の名前「TBD」のロゴ（サイト名が決まったら `render._nav` の `wm` を差し替え）と炎（`render.FLAME_SVG`、試作は テストグラウンド https://cxelegy.github.io/Wishlist/testground/flame.html ）。
- 形：先の尖った涙形を 4 層（上へ透ける縦グラデーション）。話題度 25 を超えると左右に舌が出る。
- **色は温度**：冷めた火＝暗い赤の熾火（`--ember`）→ 赤 → 橙 `--flame` → 金 `--gold` → 白い芯（`--card`）、沸騰に近づくと底に青い炎（`--blueflame`）。層ごとの色は `--fo` `--fm` `--fi` `--fc`（`color-mix`、`--hc` は NAV_JS が毎フレーム滑らかに入れる）。
- **不規則さ**：縁は SVG の乱流（feTurbulence → feDisplacementMap、雑音の細かさもゆっくり変える）、層ごとの伸び縮み・傾き・揺れは周期の割り切れない 4 つの波の和（`NAV_JS` の `wob`）、火の粉は 1 粒ずつ道筋と寿命が違う。
- **話題度で燃え方**（読んでいる作品の `data-heat`、heat.py の 0〜100）：大きさ・揺れの速さと大きさ・舌・後ろの光・火の粉の数。**読んでいる間ずっとその強さで燃える**（切り替えは 0.5 秒で滑らかに、跳ねない）。トップでは全体の最高点を小さめの火で。右に点数と等級（`heat.LEVELS`）。
- 動かすのは宽屏・タブが見えている・動きを減らす設定でないときだけ（rAF を止める）。スマホでは出さない。`burst` はトップの「重大」の札のクラスなので使わない。

## 目次のアイコン（items.yaml の `icon`）

左の目次で**読んでいる作品にだけ**出る 1 枚（白フチ・少し傾けたカットイン）。版面の emblem（キャラのステッカー、何枚でもランダム）とは別物で、
「これを見ればどの作品・ブランドか一目でわかる」唯一の 1 枚を選ぶ。種類ごとの選び方：
- **フランチャイズ・レーベル**（漫威など）：公式ロゴ。人物は使わない
- **ブランド・商品**（星巴克、三星、gelato pique）：ブランドロゴ。キャラ商品（ぐでたま）はキャラ本人の公式の絵
- **ゲーム**：パッケージ／キービジュアル（ロゴが入る部分を正方形に）。アプリアイコンになっているロゴがあればそれ（绝区零）
- **アニメ**：AniList のカバーかタイトルロゴ ／ **ドラマ・映画**：タイトルロゴかタイトルカード
- **音楽家・グループ**：Spotify のアーティスト写真（宣伝用に撮られたものなのできれい。Spotify 連接器でアーティストを探し、`open.spotify.com/artist/<id>` の og:image）。
  人物が小さすぎるとき（全身・引きの写真）は報道写真の顔のアップでもよい。顔を真ん中に、あごや頭を切らない。
  多人数のグループは Spotify の写真のまま人が小さくてもよい。グループの文字ロゴ（ワードマーク）を使ってもよい
- **文字だけのロゴ・タイトルも立派なアイコン**（FROM・ハリー・ポッター・マンダロリアン）。無理に人物や写真に替えない
- **カテゴリ・スポーツ**（猫用品、MMORPG 新作、滑雪、网球）：twemoji の記号
画像は 256×256 の正方形 webp にして `docs/icons/<slug>.webp` に置く（外部の画像は消えたり http で出せなかったりするので必ず倉庫に置く）。
**欠けない・傾かない・顔やロゴが真ん中**：作ったら 44px でも何かわかるか必ず見る。`icon: {image, kind, why, source}` に出典と理由を書く。
新しい関注項が入ったときに自動で作る仕組みはまだない（あとで追加する。今は手で作る）。

## 页面自动更新（开着的页面自己出新内容）

- 每次生成网页时，`render.stamp` 给简报・管理页・愿望清单・話題度分析算「内容指纹」（去掉更新时间），写进页面的 `<meta name="wl-ver">` 和 `docs/version.json`。
  页面（`render.LIVE_JS`）每分钟读 `version.json`，指纹变了就在用户 20 秒没操作（或标签页在后台）时无缝重载：保持阅读位置，
  新增的记事 / 愿望打「たった今」（愿望清单页是中文「刚刚」），面板内容变了打「更新」；标签页在后台时标题前出件数「(3) …」，回到页面就消。
  对话框开着、在输入框里、**有没保存的输入或选好的照片**时等待，底部提示条有「今すぐ表示」。
- 管理页「いまの状況」开着时一直重读：依頼・写真每 1 分，GitHub Actions 每 3 分（未登录 API 每小时 60 次；所有标签页共用 3 分钟内的结果，`localStorage`）。
- **版面的「更新中」条**（`render.BUSY_JS` / `busy_plan`）：**只在正在更新的那个版面**上边框出一条用版面 `--acc` 色往返的细条 + 进度 + 「あと約 N 分」，其他版面不出。
  图层：条 z-index 4，在小元素（`.emb`，z-index 5）下面。**不推算**：各仕组み自己往 Supabase `live_status` 表写，网页 30 秒读一次 `live_boards()`（`db/live_status.sql`）。没有 AI 参与。
  - 收集（`digest.live_mark`，Actions 有 secret key 直接写）：开始抓「記事を探しています」→ **这个版面一抓完就**判断：没新记事删掉（条消失），有就「新着 N 件 · AI 整理待ち · 一覧まで約 N 分」（新记事 AI 编辑后才成报道）；按顺序去重后件数变了再改（`tests/test_live.py`）。
  - AI 编辑（Claude 定时任务，没有 secret key → `scripts/livestatus.py` 调 `live_report()`）：`EDITING.md` 第 2 步 `digest.py live-edit`「AI が編集しています」→ `pick-images`「配図を選んでいます」→ `publish`「反映を待っています」。
  - 小元素补全（`emblem_fill.background`，同上 `live_report()`）：处理中「小元素を集めています」→ 增加了的版面「反映を待っています」，没增加就删。
  - `live_report()` 只收 proc = edit / emblem、版面名必须在 `sizes` 表里、文字 40 字・预计 90 分以内（不用密钥就能写，所以限得很窄；被滥用最多是假的条出 45 分钟）。
  - 「あと約 N 分」= 各仕组み最近 10 回实际用时的中位数（`runlog.typical`：收集 `secs`、AI 编辑 `secs`、小元素每个版面 `item_secs`），越跑越准。页面生成（代码变更）不出条。
  - 连接器注意：Supabase 连接器执行 `DELETE` / `DROP` 这类破坏性语句要用户确认，云端会话里没人点会超时 → 改表结构用不删东西的写法（`create or replace`、新函数名）。
- 这套逻辑在管理页「全体の構成」里是「ページの自動更新」（`processes.py` 的 `live`，箭头 21〜24・27・28），改逻辑时同步改那里。

## 管理ページ（docs/admin.html）

只看不改、不用口令（`render.render_admin` + `digest.admin_data`）：运行状况（最新一期、收集条数、哪几天还没 AI 编辑、几天没新消息的关注项、周报）、
打开时实时读取的 GitHub Actions 结果 / 设置页的关注项请求（`list_item_requests()`）/ 照片收件箱（`get_photo_inbox()`）、
各关注项的篇幅・7 天记事数・速報数・最新记事・話題度・缺的字段、投票统计（来自 `state/feedback.json`）。要加新数字就在 `admin_data` 里算、在 `render_admin` 里显示。
- **AI 編集の前後**（運行状況の下）：最新号で、作品ごとに「集めた件数（横棒）のうち AI 編集が記事に使った件数（青）→ 載せた記事の本数・重大／頭・未編集の新着」を 1 枚の図で見せる（`digest.edit_diff` + `render._admin_edit_diff`，`tests/test_edit_diff.py`）。
- **バックグラウンド**（管理ページ最上部）：裏で動く仕組みの「次の実行」（前回・次回・あと何分，页面打开时按 `processes.py` 的 `schedule` 实时算）
  + 版面（行）× 流程（列：収集・AI 編集・版面の設計・小元素）的状态表（済 / 待ち / 要確認 / 失敗，小元素写排第几）。数据在 `digest.backend_cells`。
  还有「待ち行列」（之后 24 小时的每次运行、那次要处理哪些版面，`digest.backend_todo`）和「ログ」（`scripts/runlog.py`：
  每个仕组み写自己的 `state/log/<proc>.json`——收集・出刊（Actions）、AI 编辑、小元素补全——分开写避免 push 冲突）。进度条带条纹动画（减少动画设定时不动）。
  版面ごとの状態 的每行：现有小元素的缩略图 + 折叠的「小元素の探し方」（① 种类・目标 → ② 取法按顺序・各自找到几张（`emblem_fill.source_chain`，
  要和 `gather` 的顺序一致）→ ③ 本人确认・目视排除 → ④ 结果 → ⑤ 下次几点・失败时的建议），数据在 `digest.emblem_detail`。
  新加定时的仕组み：在 `PROCESSES` 里写 `schedule`（UTC 的 (时, 分)），在 `backend_todo` 写它下次做什么，运行时 `runlog.add("<proc>", "…")`；
  要加一列就在 `render.BG_COLS` 和 `backend_cells` 各加一项。
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
- **省 token：AI 做过的判断，能写成规则的就写成规则（用户定的）**：以前用 AI（Claude）做的判断，逐个看能不能变成程序的规则；
  能的就改成 Python（不花 token），太复杂的（意思的判断、图里是什么东西）继续用 AI，但只在有活的时候叫。
  一览和理由在 `processes.AI_TASKS`（管理页「バックグラウンド → AI を使うか」），新加 / 改了判断时同步改。
  **小元素补全不要停着等**：每小时 + 每次收集完马上 + 40 分钟用完还有活就自己接着跑（最多 3 次），6 个版面并行；
  每个版面在同一回里按「① 标准 → ② 名前を広げる → ③ 公式・記事のページ」逐段试，到目标为止；三段都不行才算失败，
  失败的版面只要有新材料（新记事・新线索，`emblem_fill.material` 的指纹变了）就马上再试，没有也最多等 6 小时。
  正在处理的版面和段写进 Supabase `live_status`（proc=emblem），管理页「いま動いているもの」每 30 秒读一次。
  **后台的ゲート**（`scripts/gate.py` + `.github/workflows/background.yml`）：先数有没有活；小元素补全直接在 Actions 用 Python 做（不用 AI，
  原来要目视的「别人・远景・合照・抠图有洞・重复」都改成规则了）；AI 编辑・照片加愿望只在有活时用 API 叫 Claude（同一份活 6 小时内不重复叫，
  需要各定时任务的 API 令牌 Secret；**仓库变量** `GATE_FIRE`（Settings → Secrets and variables → Actions → Variables）打开才真的叫：
  没设 = `edit`（默认，2026-10-17 打开）、`0` = 不叫、`edit` = 只叫 AI 编辑、`1` = AI 编辑和照片都叫。AI 编辑自己的定时 2026-10-17 已停（cron 改成只在 2/29 跑），现在只靠ゲート叫）。
- **版面只放 AI 整理过的报道（2026-10-17 定）**：收集（Actions）出刊时，没被 AI 编辑覆盖的条目（编号 > `_covered`、或 edit.json 里没有的关注项）
  不上版面，放进版面底部折叠的「整理待ち N 件」（`digest.split_unedited` → 报告的 `pending` → `render._pending`）；例外是要紧消息，马上做「重大」+ Discord。
  ゲート看到今天有整理待ち（`gate.edit_work`）就叫 AI 编辑（同一份活 6 小时不重复、两次至少隔 60 分钟），所以最多每 2 小时一次 AI 编辑。
- **流程图每一步都标「AI が判断」还是「ルール」（用户定的）**：`processes.judged_by` 自动判断（用到 Claude = AI，用学习模型 = 「ルール＋モデル」，其他 = ルール），
  AI 的步骤是紫色粗框斜线底、规则是绿色左边条，构成图的框里写「AI n · ルール n」。Claude 判断但没挂 `claude` 札的步骤写 `"by": "ai"`。
  小元素的判断只有一张表 `scripts/emblem_rules.py`（流程图下的「判断の一覧」），新判断加在那里，不要在别处另写一套。
  **全身还是半身（用户定的）**：游戏・动画的官方立绘（原图透明背景）先按全身测量，再裁成上半身（`emblem.bust_from_body`：从眼睛往下「眼睛到脚底」的 40%，腰附近）——全身贴纸太小看不清脸；
  照片・漫画格子・视频画面按脸裁成半身（`emblem.want_full`）。
  测量：「眼睛到脚底」长度每个角色一样（裁后脚底在图外，网页仍按这个长度缩放 → 体的同一处切开、脸和其他半身像一样大）、按重心对齐（`body_marks`：YOLOv8m-pose 找眼睛和脚踝，从脚踝往下找脚底；尾巴・武器・裙摆・台座不算脚；蹲着的按面积量）。
  Logo 不裁（去掉纯色底存进仓库）；卡片只在比例接近 4:5 时裁。**只改规则、从头重跑，不单独修某一张图**。
  管理页「小元素の判断の例」用真实图片放「前 → 後」对比（`emblem_rules.EXAMPLES`，图在 `docs/emblems/examples/`）：加新判断或修了一个坏例子时，把那次的前后图也放进去。
- **架构图・流程图的规矩（用户定的）**：① **精确到算法**：用到的模型、算法、API、规则都要画进去，写正确的名字和数字
  （模型名・大小、阈值、同时处理几个、间隔、每次几张），登记在 `processes.COMPONENTS`，在图上是 MODEL / ALGO / API / RULE 的札；
  改了代码里的数字，同步改这里。② **全部是图**：详细流程也画成泳道图（列 = 在哪里跑，判断 = 菱形「はい ↓ / いいえ →」，
  依次尝试 / 并行 = 横排的箱子 + 「×N 並列」），不要写成从上到下的文字列表。③ 新加仕组み、新用的模型 / 算法，加完检查图里有没有。
- **全体の構成**（管理ページ，原来的プロセス缩图一览）：整体架构图——外部服务・GitHub Actions・仓库・Pages・Claude 定时任务・Supabase・Discord・你，
  编号箭头是数据流向（`processes.ARCH` / `EDGES`，线由 JS 按部件位置画；手机上看「矢印の一覧」）。点任务的框打开那个仕组み的详细流程（`PROCESSES` 的 flow）。
  **新加一个仕组み就在 `PROCESSES` 里加一项，再放进 `ARCH` 的某个框、在 `EDGES` 连上线**；改了某个仕组み的逻辑，也同步改它的流程。
- **小元素（emblem）**：每个版面右上的贴纸。规矩（种类 → 目标枚数 → 取法的顺序 → 本人确认）在 `scripts/emblem_fill.py`、`scripts/face_id.py`，说明在 `TEMPLATES.md`；
  **选图先想「下一层」**：类别・题材（MMORPG 新作、猫用品、滑雪）贴的是它下面的具体作品 / 品牌 / 选手（`emblem_examples`，我喜欢的放第一个，例：剑灵），
  记号（Twemoji）只垫底。角色不用漫画格子・截图，先找官方立绘 / 插画；抠图后上边缘一半以上是人（连框切的特写）就不用；
  **枚数的上限由内容的主要元素数决定**（用户定的，不只是游戏）：1 个元素 1 张，天井 20——角色多的游戏 20 张、主角 4 人的动画 4 张、5 人团 5 张、
  主题按代表作数。元素数是 `emblem_pool`（`emblem_fill.py --roster` 从 `emblem_category` 分类或 AniList 主角数出来，并补名字）；
  管理页「小元素」列出每个版面的种类・目标・现有枚数，没到目标的 AI 编辑会自动补（`python scripts/emblem_fill.py --audit`）。


## テストグラウンド（docs/testground/）

本番の简报に入れる前に部品を試すページ。入口 https://cxelegy.github.io/Wishlist/testground/ （`index.html`）。消さずに残し、新しい試作もここに足す（入口に 1 枚カードを足す）。
- `compare.html`：左の目次 v1〜v6 の見比べ（条件 10 パターン・画面の高さ・「ダミーで試す」で作品数 2〜1000）
- `rails.html`：目次の見本 10 パターン ／ `nav.html`：本文つきで 1 本
- **左の目次は v6 に決定（2026-10-17）**：パソコンは「少ないうちは隠さない・段階的に隠す」（隠し始めるのは既定 24 件、件数で／自動。隠す前に行を 22px まで詰める → ①ほかの板块は新着順に数件 ②ほかは見出しだけ ③いまの小分類だけ ④入るだけ＋「ほか N 件」）。
  小分類の札は必ず出す。見た目は線路（原版）＋作品アイコン（emblem → 記事の写真 → 頭文字）＋板块アイコン。スマホは上に 2 段の横帯だけの簡単な形。2026-10-17 に本番（`render._nav` / `NAV_JS` / `NAV_STYLES["line"]`）へ移した。
  隠し始める件数は `items.yaml` の `settings.nav_hide`（既定 24、`auto` で画面の高さ）。件数以内でも行を 30px まで詰めて入らなければ隠す（窮屈にしない）。小分類は関注項に `subs:`（分け方ごと、例 `subs: {kind: ドラマ, origin: 海外}`）。**どの板块にも必ず小分類を付ける**（1 つしかなくても）。どの分け方を使うかは ⚙ 設定ページで板块ごとに選ぶ。
