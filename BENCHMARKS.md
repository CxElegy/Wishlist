# ウォッチリスト通信：似たサービス・更新の技術・受賞デザインの調べ（2026-10-24）

調べた範囲：WebSearch / WebFetch。各行の終わりに出典の網址を付けた。
「（推測）」と書いたものは出典に書いていない、私の読み取り。古い記事（2008〜2021 年）にしか載っていないものはその年を書いた。

---

## 0. まとめ（先に結論）

- 似たサービスはどれも「**同じ出来事を 1 つにまとめる**（何社が報じたかを見せる）」をやっている。私たちは記事を 1 件ずつ並べていて、まとめは AI 編集まかせ。ここを規則でやると、画面もトークンも良くなる。
- 更新を速く・安くする一番の近道は「**変わっていないものを取り直さない・AI に見せない**」。2 時間ごとの全部取り直しと、1 日 2 回の全部編集の両方に効く。
- 受賞サイトに共通するのは「**1 ページに見せ場を 1 つ**」「動きは速い端末でなくても滑らか」「本物の写真と文字」。P5 の手法は、全部に効かせるより「ポスターの 1 瞬」に集めたほうが強い。
- Artifact（Instagram 創業者のニュースアプリ）は 1 年で終了。理由は「市場が小さい」と「コメント欄の見張りに人手が要る」。私たちは SNS 機能を足さず、「店長」という語り手で差をつけるのが安全。

---

## 1. 似たサイト・アプリ（10 個）

### 1-1. 一覧（何をしているか・集め方・好みの合わせ方）

| サービス | 何をしているか | ニュースの集め方・更新 | 好みの合わせ方 | 出典 |
|---|---|---|---|---|
| Google ニュース「フォロー中」・フルカバレッジ | 話題・媒体・地域をフォロー。続いている話題は「フルカバレッジ」で 1 か所に全部集める | 機械学習で同じ話題の記事を自動でまとめる（媒体ごとでなく話題ごと）。フルカバレッジは同じ話題なら全員に同じ中身 | 「For you」とフォロー中の話題は行動で個人向け、フルカバレッジは個人向けにしない | https://support.google.com/googlenews/answer/9005749 ・ https://news.googleblog.com/2008/05/keeping-good-news-stories-together-just.html ・ https://www.searchenginejournal.com/google-search-results-updated-with-full-coverage-for-news/398254/ ・ https://uxdesign.cc/google-news-the-full-coverage-feature-d83a9e92b714 |
| Feedly（AI の Leo） | RSS 読み。AI に「何が要らないか」を教えて絞る | RSS ＋キーワード警報。**ほぼ同じ記事を 1 本に**（転載・プレスリリースの重複）。ミュートは語・題名・網域で | 「興味ない」を 10〜20 件押すと学ぶ。網域ごとのミュート | https://blog.feedly.com/?p=11707 ・ https://docs.feedly.com/category/706-mute-filters |
| Inoreader | RSS 読み・自動化 | **WebSub（新しい記事が出たら向こうから知らせてくる仕組み）で即時更新**＋定期の見回り。重複は「同じ網址・同じ題名・ほぼ同じ題名」、比べる期間 6 時間〜1 か月、裏でずっと動く | 絞り込み（題名・本文・著者・言語・網址の AND/OR）、規則で通知・Webhook | https://status.inoreader.com/ ・ https://www.inoreader.com/blog/2020/08/win-the-clone-wars-with-duplicate-filters.html ・ https://innoreader.com/blog/2023/06/streamline-content-discovery-with-filters-and-rules.html ・ https://innoreader.com/blog/2026/01/save-time-with-automations.html |
| Flipboard | 雑誌の形でめくる。人が編む「マガジン」 | 媒体と編集部（News Desk 等）が選ぶ。2025 年は Mastodon など分散 SNS へ 1,241 媒体を流す | 話題・マガジン・人をフォロー | https://about.flipboard.com/fediverse/flipboard-federates-250-publishers/ ・ https://about.flipboard.com/inside-flipboard/how-flipboard-is-using-our-new-federated-magazines/ |
| Artifact（2024 年 2 月に終了） | AI が記事を推薦・要約。釣り見出しを AI が書き直す | 機械学習の推薦。見出しの書き直しは、まず頼んだ人だけ → 頼む人が多いと人が確認して全員に。書き直した見出しに★印 | 読んだ・止まった時間で学ぶ | https://techcrunch.com/2023/06/02/artifact-news-app-now-uses-ai-to-rewrite-headline-of-a-clickbait-article ・ https://sixcolors.com/post/2025/01/llms-arent-always-bad-at-writing-news-headlines/ |
| SmartNews | 日本発のニュースアプリ。チャンネル（タブ）で分ける | 3,000 超の媒体を機械学習で。媒体は先に人が審査。速報性を重視。政治の偏りを均す部品あり（2018〜2021 年の記事） | いいね・クリック等の行動 | https://techcrunch.com/2020/09/17/smartnews-kaisei-hamamoto-on-how-the-app-deals-with-media-polarization ・ https://ijnet.org/en/story/smartnews-app-drives-traffic-will-it-drive-revenue |
| Ground News | 同じ出来事を何社がどの立場で報じたかを見せる | 1 日 3 万件の出来事に、各社の記事をまとめて 1 話。「Blindspot」= 片側だけが報じている話 | 媒体の立場の評価（外部 3 団体）で色分け | https://help.ground.news/en/articles/485057 ・ https://about.ground.news/blindspot |
| Particle | AI が複数の記事から 1 つの「話」を書く | 複数媒体の要点を合成、元記事へのリンク付き。AI の確認＋人の目。2025 年 5 月にウェブ版 | 話題のフォロー、立場の違う見方の表示 | https://techcrunch.com/2025/05/06/particle-brings-its-ai-powered-news-reader-to-the-web ・ https://techradar.com/computing/artificial-intelligence/a-news-app-is-using-ai-to-curate-clarity-over-clickbait |
| Perplexity Discover | AI 要約の話題一覧（Top・技術・金融・スポーツ…） | AI が記事を合成。元記事が小さな脚注だけで批判された（2024 年） | 話題と言語を選ぶ、Pro は行動でも | https://alternativeto.net/news/2024/9/perplexity-ai-launches-personalized-discover-feed ・ https://bworldonline.com/?p=601045 |
| Yahoo!ニュース トピックス | 人が選んで見出しを付ける | 約 25 人の編集部が 1 日約 4,000 本から選ぶ（2015 年）。見出しは最大 15.5 字（2022 年 1 月から、それまで 13.5→14.5 字） | ほぼ全員に同じ | https://ipsj.ixsq.nii.ac.jp/record/141494/files/IPSJ-MGN560402.pdf ・ https://scan.netsecurity.ne.jp/article/2021/04/15/45531.html ・ https://webtan.impress.co.jp/n/2022/01/28/42279 |
| 参考：Gunosy・Techmeme・IGDB | Gunosy＝約 600 媒体から規則で選ぶ・釣り記事を避ける研究。Techmeme＝規則が先、人の編集は「古い話を早く外す・速報を上げる・関連記事をまとめる」。IGDB＝ゲームの情報が変わると Webhook（向こうから知らせる）で届く | — | — | https://internet.watch.impress.co.jp/docs/news/1057945.html ・ https://venturebeat.com/business/news-aggregator-techmeme-melds-algorithms-and-humans ・ https://news.techmeme.com/081203/automated ・ https://discuss.dev.twitch.com/t/igdb-store-all-games-in-local-database/47241 |

Artifact が終わった理由：創業者 Kevin Systrom「市場の機会が投資を続けるほど大きくない」。コメント・投稿は「見張りに人手が要り、続ける人がいない」ので先に止めた。8 人のチーム。
出典：https://medium.com/artifact-news/shutting-down-artifact-1e70de46d419 ・ https://en.wikipedia.org/wiki/Artifact_(app)

### 1-2. 画面の作り・私たちとの違い・借りられること

| サービス | 画面の作り | 私たちとの違い | 借りられること |
|---|---|---|---|
| Google ニュース | 1 話 = 見出し＋「ほかの媒体」の小さな列。フルカバレッジは時系列・解説・意見の段 | 話題が流れていく。私たちは 1 つの追いかけるもの＝固定の版面 | **同じ出来事を 1 枚に**して「ほか 4 社」と出す。続いている話は版面の中で時系列の段に |
| Feedly | 一覧＋AI の札（「重複」「ミュート済み」） | 好みを学ばせるのは読者自身 | 「違う」の理由を数えて規則を締める（小元素でもうやっている）を記事にも：「この記事いらない」の理由ボタン |
| Inoreader | 規則の画面（もし〜なら〜） | 即時（WebSub）＋見回りの 2 本立て | 見回りの間隔を情報源ごとに変える・重複を「網址・題名・ほぼ同じ題名」の 3 段で |
| Flipboard | めくる雑誌・大きな写真 | 人のマガジン | 版面を「雑誌の 1 号」に見せる表紙の作り（ポスターに近い） |
| Artifact | 1 記事ずつ縦に、AI 要約 | 終了。SNS 機能が重荷 | 釣り見出しの書き直しに**★印**（AI が直した見出しだと見せる）。コメント欄は作らない |
| SmartNews | 上のタブ（チャンネル）で切り替え | 機械学習の推薦 | スマホの上の帯＝タブの手触り（すでに近い） |
| Ground News | 1 話に「何社・どの立場」の横棒 | 政治の立場が主題 | 「何社が報じた」の横棒を話題度の見せ方に。「店長の版面には来ているが、あなたは追っていない」＝自分の盲点（Blindspot） |
| Particle | 1 話の合成要約＋元記事 | AI が合成 | 合成した文には元記事を必ず並べる（Perplexity が批判された点を避ける） |
| Perplexity | カード一覧 | 元記事が目立たない | （反面教師）元記事の媒体名・網址を見出しの近くに |
| Yahoo!トピックス | 短い見出し 15.5 字以内 | 人の編集 | 目次・棚の見出しに字数の上限（例：16 字）を決めて AI 編集に書かせる |

---

## 2. ニュースを効率よく更新する技術（私たちに効く順：トークン・時間が下がる順）

私たちの今：GitHub Actions で 2 時間ごとに全部の版面を取り直す（Google・Bing・Reddit・RSS・情報員）→ 規則で絞る → AI 編集は 1 日 2 回（9:00 / 18:00）。

| 順 | 技術（やさしく言うと） | 何が減るか | 私たちの作りへの当て方 | 出典 |
|---|---|---|---|---|
| 1 | **同じ出来事のまとめ（クラスタリング）を規則で先にやる**。題名の言葉の重なりを数える方法（MinHash＝言葉の組の重なり率、SimHash＝文の指紋の近さ）。ニュース 3,932 件の試験で MinHash は「頑丈」、MinHash 0.783 対 SimHash 0.695 | **トークン大**（AI に渡す件数が「記事の数」→「出来事の数」に） | `same_event`・`lang.dedupe` を広げ、版面ごとに「出来事」単位に束ねてから AI に渡す。見出しは短いので語の組の取り方を調整（推測） | https://thesis.unipd.it/handle/20.500.12608/96063 ・ https://arxiv.org/pdf/2311.17264 |
| 2 | **増分の AI 要約**：前回まとめた出来事は要約を取っておき、新しく来た記事の分だけ「付け足す」 | トークン大 | edit.json に出来事ごとの要約と依拠した記事の番号を残し、次の回は「新しい記事＋前の要約 1 行」だけ見せる（`_covered` の考えを出来事単位に） | （考え方。Techmeme の「古い話を早く外す・関連記事をまとめる」） https://news.techmeme.com/081203/automated |
| 3 | **AI の前置きの使い回し（プロンプトキャッシュ）と一括処理（Batch）**：同じ指示文は 2 回目から 1 割の値段、急がない仕事は半額 | トークン代（API で呼ぶ部分だけ） | 今の AI 編集は Claude の定時タスク（会話）なので直接は効かない。API で呼ぶ部分（ゲート・将来のお客さま用の Haiku / Sonnet）で、EDITING.md の規則を前に固定して置く | https://docs.claude.com/en/docs/build-with-claude/message-batches ・ https://docs.claude.com/en/docs/build-with-claude/prompt-caching |
| 4 | **条件付き取得**：前回もらった印（ETag・Last-Modified）を付けて頼むと、変わっていなければ中身なしの「304」が返る | 時間・通信 | 情報員の RSS・公式チャンネル RSS・ナタリー等の固定フィードに効く。印を `state/` に保存。Google・Bing の検索 RSS は毎回作られるので効かないことが多い（推測） | https://openrss.org/guides/developers-guide-to-open-rss-feeds ・ https://docs.s9y.org/docs/developers/conditional-get.html |
| 5 | **見回りの間隔を版面ごとに変える**：よく動く版面は 2 時間、何日も新着のない版面は 6〜12 時間 | 時間（締め切り 18 分に当たりにくい） | 「几天没新消息的关注项」はもう数えている。`fetch_order` に「最近 7 日の新着数」で間隔を決める 1 行 | （考え方。Inoreader の見回り＋即時の 2 本立て） https://status.inoreader.com/ |
| 6 | **WebSub（向こうから知らせてくれる）**：YouTube はチャンネルの新しい動画を Google のハブ経由で知らせる | 時間（即時になる） | 受け口が要る → Supabase の Edge Function を受け口にし、来たら `run_now` で収集を起こす。公式チャンネルのある版面だけ | https://developers.google.com/youtube/v3/guides/push_notifications ・ https://www.w3.org/TR/websub/ |
| 7 | **データベース側の知らせ（Webhook）**：IGDB はゲーム情報の変更を知らせる | 時間 | 発売日の変更をすぐ拾える。まずは全部読み込み → 以後は知らせだけ、が定石 | https://discuss.dev.twitch.com/t/igdb-store-all-games-in-local-database/47241 |
| 8 | **重複の 3 段**（同じ網址 → 同じ題名 → ほぼ同じ題名、期間を決める） | AI の読む量・画面の重複 | 今ある去重の順番を Inoreader の 3 段にそろえて、期間（6 時間〜）を版面の動きで変える | https://www.inoreader.com/blog/2020/08/win-the-clone-wars-with-duplicate-filters.html |

**注意**：1・2 は AI が「同じ出来事」と見ていたものを規則に移すので、CLAUDE.md の「AI の判断を規則に」の方針に合う。ただし `carry_over` の調べで「StoryDeduper が別の試合を同じ出来事にした」前例があるので、**同じ出来事の判断は「同じ作品・日付・数字（話数・版）」の条件を付け、試す前に過去 7 日の inbox で誤まとめを数える**。

---

## 3. 賞を取ったウェブデザイン（2024〜2026 年、ニュース・雑誌・ゲーム的なもの 9 個）

Awwwards＝毎日 1 つ選ぶ「Site of the Day（SOTD）」、年間の「Site of the Year（SOTY）」、点数 6.5 以上の「Honorable Mention（HM）」。

| サイト | 何の賞 | 網址 | 手法 | 私たち（P5・版面・ポスター）に取り入れること |
|---|---|---|---|---|
| Igloo Inc（abeto） | Awwwards SOTD 2024-07-23・**SOTY 2024** | https://www.igloo.inc （賞：https://www.awwwards.com/sites/igloo-inc ・ https://www.awwwards.com/websites/sites_of_the_year/ ） | 3D・切れ目のないスクロール・動きの点数 9.6/10。色は灰青と濃紺の **2 色だけ** | 版面の配色は「作品の 2 色」に絞ると P5 の赤黒のような強さが出る。今の `theme` を 2 色＋紙色に |
| Messenger（abeto） | SOTD 2025-11-10・**SOTY 2025** | https://messenger.abeto.co （https://www.awwwards.com/sites/messenger ） | 小さな星で配達するゲーム。キャラで進む案内、複数人がリアルタイム | 目次（路線図）を「キャラが駅を進む」案内に。版面の emblem を目次の現在地の印に |
| Lando Norris（OFF+BRAND.） | SOTD 2025-11-17・SOTY 2025 の一覧 | https://landonorris.com （https://www.awwwards.com/sites/lando-norris ） | 黄緑 #D2FF00 と黒の 2 色、GSAP の動き、触ると反応 | スポーツ選手の版面の作り方の見本：蛍光の 1 色＋黒＋大きな写真 |
| Vogue Business｜Archrival（Noomo） | SOTD 2026-01-04（雑誌・新聞部門） | https://www.vogue.com/article/gen-z-broke-the-marketing-funnel-part-ii-what-now （https://www.awwwards.com/sites/vogue-business-archrival ） | 雑誌の長い記事に、スクロールで着替える人物・動くコラージュ・グラフ。紫と黄緑の 2 色 | 話題度分析ページ（heat.html）を「読む記事」にする：スクロールで数字が出る。ポスターのコラージュ |
| The Lookback（Better Off） | SOTD 2026-03-27（雑誌部門） | https://tlb.betteroff.studio/ （https://www.awwwards.com/sites/the-lookback ） | これまでの仕事の「振り返り」。横スクロール・画廊 | 週報・月の振り返りを「横に流れる画廊」で。版面の過去記事の書庫に |
| The Tie-break（Merci Michel） | SOTD 2026-09-25（ゲーム・娯楽部門） | https://thetiebreak.merci-michel.com/ （https://www.awwwards.com/sites/the-tie-break ） | 遊べる商品紹介（WebGL）。動きの点数 9.2 | 「気になるかも？」を遊べるカード（左右に払う）にした今の方向は合っている。払った瞬間の演出を 1 つ |
| Overwatch（The Lobby News、Nuclassic） | Awwwards HM 2026-04-22（雑誌部門） | https://thelobbynews.com/overwatch （一覧：https://www.awwwards.com/websites/magazine-newspaper-blog/?page=2 ） | ゲームごとのニュース頁（私たちの版面にいちばん近い。詳細は未確認） | 1 作品 = 1 ニュース頁の「同業」。一度画面を見比べる価値あり |
| 日暮里ゼミナール（lamm_tokyo） | Awwwards Typography Honors 2026-01 | https://nippori.lamm.tokyo/ （同上の一覧） | 日本語の組版で賞（詳細は未確認） | 日本語見出しの組み方（字詰め・縦組み）を見る。P5 の傾けた見出しを和文で美しく |
| BMSG FES'25 / SIRUP OWARI DIARY（tote、東京） | Awwwards HM 2025-10-12 / 2025-10-18 | https://bmsgfes.tokyo/2025 ・ https://sirup.online/owaridiary （https://www.awwwards.com/tote_webdesign/ ） | 音・動き・遊べる UI（スタジオの紹介文） | 音楽・ライブの版面の見本。日本のスタジオで P5 系の「遊び」に近い |
| 参考：The Pudding・NYT | SND47（2025 年の作品）Best in Show：The Pudding・Washington Post／デジタルの最優秀：NYT | https://snd.org/ ・ https://pudding.cool/faq/ | データで語る記事 | 話題度の図（heat.html）の作り方の手本 |

受賞に共通する手法（日本のスタジオ Utsubo のまとめ）：見せ場を 1 つ／スクロールで物語を進める／**速さ（読み込み 1.5 秒・ずれ 0.05・反応 100ms 以内、動きは 1 秒 60 コマ）**／普通の端末でも滑らか／スマホは別に設計／本物の写真と文／下の階層まで同じ質。
出典：https://www.utsubo.com/ja/blog/award-winning-website-design-guide

---

## 4. 私たちが次にやるとよいこと（効き目の大きい順）

| 順 | やること | 効くところ | 中身 | 手間 |
|---|---|---|---|---|
| 1 | **出来事ごとに束ねてから AI に渡す（規則）**＋**増分だけ編集** | トークン ◎・更新の速さ ○・お客さま ○（同じ話が何度も出ない） | 版面ごとに「同じ作品・日付・数字が同じ・題名の言葉の重なり」で束ねる。AI は「新しい束」と「記事が増えた束」だけ見る。前の要約を残して付け足す。束ねの誤りは過去 7 日の inbox で先に数える | 中 |
| 2 | **「ほか N 社」の 1 枚**（Google・Ground News 型） | お客さま ◎・見た目 ○ | 束ねた結果を画面に：見出しは主言語の 1 本、下に媒体名の小さな列と「N 社」の細い横棒（話題度の「広がり」と同じ数） | 小（1 のあと） |
| 3 | **見回り間隔を版面ごとに**＋**変わっていないフィードは取らない（304）** | 更新の速さ ◎（締め切り 18 分で「次の回へ」が減る）・時間 | 新着の多い版面は 2 時間、静かな版面は 6〜12 時間。情報員・公式 RSS に ETag を保存。新しい関注項は最優先のまま | 小 |
| 4 | **お客さま用の「あなたの盲点」**（Ground News の Blindspot 型） | お客さま ◎ | 選んだジャンルで、店長の版面に今日大きく来ているのにまだ追っていないもの → 「＋ 追いかける」。今の「気になるかも？」に「なぜ出たか」（N 社が報道・話題度 xx）を 1 行 | 小 |
| 5 | **YouTube の WebSub を受ける口**（Supabase Edge Function） | 更新の速さ ○（公式動画が数分で） | 公式チャンネルのある版面だけ。届いたら `run_now('collect')` で、その版面だけ取りに行く。期限（リース）を後台で更新 | 中 |
| 6 | **見出しの字数の上限と★印**（Yahoo!・Artifact 型） | 見た目 ○・お客さま ○ | 棚・目次の見出しは 16 字以内を AI 編集の規則に。AI が書き直した見出しは小さな★、元の題は押すと出る | 小 |
| 7 | **ポスターの「見せ場」を 1 つに絞る・2 色配色**（Igloo・Lando Norris・Vogue Business） | 見た目 ◎ | トップは頭条 1 枚に P5 の演出（傾き・硬い影・札）を集め、ほかは静かに。版面の配色を「作品の 2 色＋紙」に整理。速さの目標（読み込み 1.5 秒）を `tests/test_perf.py` に | 中 |
| 8 | **話題度ページを「読む記事」に**（Vogue Business・The Pudding） | 見た目 ○ | スクロールで週の動きが 1 つずつ出る形。数字は今のまま、見せ方だけ | 中 |

やらないほうがよいこと：コメント欄・お客さま同士の SNS 機能（Artifact が止めた理由そのもの）。AI 合成の文だけ見せて元記事を隠すこと（Perplexity が批判された）。

---

## 5. 確かめられなかったこと

- Webby Awards 2025 の「ニュース・雑誌サイト」部門の受賞者（公式一覧に届かず）。2026 年の「ニュース・政治」は The Trace（https://www.factcheck.org/2026/04/we-won-a-webby-peoples-voice-award/ ）。
- CSS Design Awards の 2024・2025 年の年間賞（候補 24 件までしか見えず：https://workspace.ru/blog/nominanty-na-sayt-goda-2024-dizayn-daydzhest-css-design-awards/ ）。FWA は今回見ていない。
- P5 風の UI で賞を取ったサイトは見つからなかった（Metaphor: ReFantazio は日本ゲーム大賞 2025 で UI を評価されたが、ゲームの賞：https://awards.cesa.or.jp/2025/en/year/prize/ ）。
- The Lobby News・日暮里ゼミナールの画面の中身は未確認（一覧の札だけ）。
- SmartNews・Gunosy の仕組みは 2013〜2021 年の記事しかない。
