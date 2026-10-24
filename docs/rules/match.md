# 匹配词・垃圾站・情報源・情報員

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
- **垃圾站**（被黑的网站批量生成的页面，标题塞作品名骗搜索，会命中 match）：`digest.is_spam` 按标题写法（「在线看」、末尾 10 位随机码 `(gQvzdvbtKG)`）和链接网域（`SPAM_HOSTS`，Unisba Media = `unisba.ac.id`）认；
  收集・整理待ち・出刊・页面・推荐・話題度的报道量都过这一个函数，新发现一个垃圾站就在那里加写法 / 网域，在 `tests/test_match.py` 加真实标题。
- **网店、二手的商品页**（「本物」「定番新品」「au PAY マーケット」「最終値下げ」）写进 `exclude`。
- **不是新闻的网站按网域丢**（2026-10-22）：`exclude_hosts`（settings 全体：readyfor.jp・camp-fire.jp 众筹 = 整个网域；攻略 wiki 的 gamewith.jp・game8.jp・altema.jp 写成 `{host, title}`，只丢标题是攻略页形状的（「【あつ森】…【あつまれどうぶつの森】」「【ゼンゼロ】…は引くべき？」），编辑部的新闻（新作发表・试玩评测）留着——收集时链接是 Google 的跳转、看不到路径，所以按标题分；escorenews 的比赛直播页由 dota2 的 exclude「match stream」丢，网域不丢；关注项也能各自写），网域和下级网域，看 `e.link`（还原的原文）・`e.url`・Google 新闻的 `<source url>`（`Entry.site`，收集时链接还是 Google 的跳转；inbox 里也写 `site`）。「気になるかも？」的候选也过出典名・网域。
  `exclude_sources`（媒体名）是**前方一致**：「YouTube」也丢「YouTube on MSN」（后面接 ASCII 英数字的不算：「note」不丢「Notebookcheck」，「note株式会社」丢；官方频道 RSS「YouTube · 名字」不丢）。
  设置页能改的 `keywords` / `match` / `exclude` 上限是 40 / 80 / 80 个（`digest.ITEM_FIELDS`）：items.yaml 里写的要都在上限内，否则店长改一个词就被拒（`tests/test_match.py` 的 ItemFieldsLimitTest）。`set_item_fields` 换写多行的 `[ … ]` 时连闭括号的行一起换（以前留下 `    ]` 把 YAML 弄坏，依頼被 skipped：SetItemFieldsRoundTripTest 把每一项都写一遍再读）。
  滑雪的英文词（CAPiTA・Burton・ski）用 `(?<![A-Za-z])…(?![A-Za-z])` 不用 `\b`：Python 的 `\b` 把假名・汉字也算单词字，「CAPiTAの」就不命中。
  这几条和垃圾站・`exclude`・`match` 都在 `digest.drop_reason` 一个函数里，收集和 `audit-match` 用同一个。
- **情報源（2026-10-22，用户定的：都要，不用 AI 所以 CPU・时间可以多用）**：Google・Bing・Reddit・Steam・RSS 之外，`sources.gdelt`（世界 65 言語のニュース索引，读者的语言，5 秒 1 回・429 重试，重试后还被拒这次就不再问（2026-10-22 本番：Actions 的共享 IP 几乎都被拒，空等 10 分钟），`use` 有 google 的关注项，每项前 2 个词）、
  `sources.youtube_channel`（公式チャンネルの RSS，チャンネル = items.yaml 的 `youtube` 或 `wiki` → Wikidata P2397，缓存 `state/youtube_channels.json` 30 天）、
  `sources.bluesky`・`sources.mastodon_tag`（`use` 有 reddit 的关注项；和 Reddit 一样只放火的帖子：Bluesky ♥50 / 转发＋引用 15，Mastodon ♥20 / ブースト 10，其余只算話題度；匹配词必须在帖子正文；网址开头的自动转载 bot 帖丢掉）。
  都过同样的 match・exclude・垃圾站・去重；`sources.is_sns` = Reddit・Bluesky・Mastodon（不当报道・不当推荐）。
- **地域ごとの情報員（2026-10-22，用户定的）**：今の「情報源」は全世界共通の汎用的な仕組みでしかない。**地域ごとの専門の情報員**を作る：
  まず**日本の情報員**（日本のサイト・日本のニュースに詳しい）、それから**国内（中国）を中心にアジア地域の情報員**（台湾・香港・韓国・東南アジアも）。
  情報員 = その地域の情報源を分類（作品・ゲーム・音楽・スポーツ・グッズ・暮らし・おでかけ）ごとに持ち、関注項の言語・地域・分類で担当が決まる。集めた記事は今までどおり match・exclude・垃圾站・去重を通す。
  情報源は無料・鍵なし・robots / 利用規約で自動の読み取りが許されているもの（RSS / Atom / JSON 優先）。作るときは find-skills で地域向けのスキルを探し、スキルの中身を取り込んで設計する（調査：ワークフロー regional-intel-research）。
  **作り（第 1 段・日本、2026-10-22）**：`intel/<地域>.yaml`（データだけ：id・ja・langs・sources〔id・name・url・cats・exclude・terms〕、足すのにコードは要らない）＋ `scripts/intel.py`（`collect()` から 1 行）。
  開關 = `items.yaml` の `settings.intel: [japan]`。担当 = 関注項が**自分で書いた** `news_langs` と地域の `langs` が重なる（settings の既定の言語は数えない）・`intel: [korea]` で指定・`intel: []` で止める；読むのは `cats` が関注項の板块（section 無しは type から・also も）と重なる情報源。同じフィードは 1 回の収集で 1 回だけ取る。
  情報源ごとの様子（ok・blocked・timeout…）は収集のログに「情報員 日本の情報員：17/17 本・…件」。`python scripts/intel.py --fetch` で担当と取れ具合を見る。読み取りの共通部分：RSS 1.0（RDF）・宣言のない `media:` も読む、ホストごとの UA `sources.HOST_UA`（ナタリーは Mozilla を 405）。
  入れないもの：Yahoo!ニュース RSS・CNA・SCMP・RTHK（「個人・非営利のみ」）、B站・知乎（robots で禁止）、微博・小紅書・Dcard（ログイン）。次：日本の残り（はてブ検索・PR TIMES 企業別）→ 韓国 → 台湾・香港 → 中国 → 東南アジア（設計案は調査の結果）。
- **检查**：`python scripts/digest.py audit-match`（`--only "名字、名字"` 只看几项）把最近几天收进来的条目按「靠哪个词进来的」列出来，
  ✗ 是按现在的规则已经不会再收的（后面写理由：match・exclude・垃圾・exclude_sources・exclude_hosts；最后一行是 link・site 都没有、网域判断不了的 Google 跳转件数，和其中出典名跟被丢网域同一媒体的件数）。每组看一眼标题，有不相关的就收紧那个词；误收已经上了版面的，
  从当天还没有 `.edit.json` 的 inbox 里删掉、把报告里那条拿掉，再重新出刊。`tests/test_match.py` 有这几种写法的例子。
