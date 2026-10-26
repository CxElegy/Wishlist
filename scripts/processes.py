"""管理ページの「プロセス一覧」：サイトの裏で動いている仕組みを、部品（プロセス）ごとに見られるようにする。

プロセスは PROCESSES に 1 つずつ書く（データだけ）。管理ページは
  ・一覧：プロセスごとに小さな縮図（thumbnail）・いつ・どこで・いくら
  ・縮図をクリック：そのプロセスの詳しい流れ（flow）
を、このデータから自動で作る。仕組みを足したら、ここに 1 項目足すだけで管理ページに出る。

flow は上から下へ読む。ノードの kind：
  step      手順（title / text）
  decision  判断（title / text に条件、yes / no にそれぞれの行き先）
  fan       並列の選択肢（items のうち、上から順に試す。足りるまで次へ）
  store     保存先のファイル・データ
  table     小さな表（rows = [(見出し, 内容)]）
lane は「どこで動くか」：actions（GitHub Actions）/ ai（Claude・サブスク枠）/ repo（仕組みの置き場）/ web（網页・Supabase）。
schedule は定時で動くものの時刻（UTC の (時, 分) のリスト。別のプロセスと同じ回に動くものはその id）。管理ページの
「バックグラウンド」が、ここから前回・次回の時刻と残り時間を出す。workflow は GitHub Actions のファイル名（実行中かを読む）。
"""

import html
import json
import re

e = html.escape

LANES = {
    "actions": ("GitHub Actions", "無料", "free"),
    "ai": ("Claude（定時タスク）", "サブスク枠", "ai"),
    "repo": ("リポジトリ", "無料", "free"),
    "web": ("ウェブ・Supabase", "無料", "free"),
    "ext": ("外のサービス", "無料", "free"),
}

# 部品：仕組みが使うモデル・アルゴリズム・API・ルール。name は正確な名前、spec は数字（大きさ・しきい値・同時にいくつ）。
# 図の札（chip）と流れの図に出る。数字を変えたらここも変える（コードの場所は what に書く）。
KIND_LABEL = {"model": "MODEL", "algo": "ALGO", "api": "API", "rule": "RULE"}
COMPONENTS = {
    # ---- モデル
    "rembg": {"kind": "model", "name": "rembg birefnet-general-lite", "spec": "ONNX 224MB · 1 枚ずつ · 出力 420×520 WEBP",
              "what": "人物・キャラを背景から切り抜く（emblem.cut_out）。onnxruntime のメモリ池は切ってある"},
    "yunet": {"kind": "model", "name": "YuNet face_detection_yunet_2023mar", "spec": "入力 320×320 · score 0.8 · NMS 0.3",
              "what": "顔を見つける（face_id.py、OpenCV FaceDetectorYN、HuggingFace から）"},
    "sface": {"kind": "model", "name": "SFace face_recognition_sface_2021dec", "spec": "128 次元 · cos ≥ 0.363 で本人",
              "what": "顔の特徴量で同じ人か比べる（face_id.py）。基準 = 記事の代表画像、合わなければ多数決"},
    "roles": {"kind": "rule", "name": "実写の作品は役の姿 gather_roles", "spec": "出演者 → 役（Fandom の出演者の記事・表・検索、役の記事で演者を確かめる）→ 出演者の記事・ファイル検索の「X as 役」の写真（作り直しの剧は役の記事が前の映画の役者）→ 役の記事の画像・作品の動画の場面（出演者の顔の基準がないときは、ファイル名に出演者・作品の略号〔HPTV〕がある・作品の始まりの 2 年前より後に上がった画像だけ：emblem_fill.tied。前からの小元素も untied_roles で外す・哈利波特 Padma の映画の写真）→ 作品の記事の剧照（ファイル名に役名がない HBO Max Still）は名簿の出演者ぜんぶの顔の基準と比べ、いちばん近い人へ（cos ≥ 0.363・2 番目と 0.08 以上の差：emblem_fill.assign_stills。暗さは顔が見えれば顔の明るさ 10% で：emblem.FACE_DARK）· 生活の写真は基準だけ",
              "what": "剧・映画の小元素を、出演者の写真ではなく役の剧照にする（emblem_fill.role_of / role_images）"},
    "pose": {"kind": "model", "name": "YOLOv8m-pose（ultralytics）", "spec": "53MB · 目・足首の確かさ ≥ 0.5 · なければ輪郭から推定（Actions には入れていない）",
             "what": "全身の立ち絵の目の高さと足の裏・重心を測り、背の高さをそろえる。腰が体の 60% より上（ふつうの人の体つき）だけ腰のあたり（目から足の 40%）で上半身に切り、頭の大きいキャラ・動物・マスコット（目印の確かさ < 0.6）は全身のまま（emblem.body_marks / real_body / bust_from_body）"},
    "haar": {"kind": "model", "name": "OpenCV Haar frontalface + LBP animeface", "spec": "scale 1.1 · minNeighbors 4〜5",
             "what": "切り抜きの構図と顔の位置（emblem.face_box / face_crop）。顔モデルがないときの代わり"},
    "claude": {"kind": "model", "name": "Claude（定時タスク）", "spec": "編集・写真の認識・一覧の目視 · サブスク枠",
               "what": "AI 編集・写真から愿望・小元素の要確認を、画面を見て判断する"},
    "claude-api": {"kind": "model", "name": "Claude API claude-haiku-5-5", "spec": "summarize: false（いまは使わない）· 4000 tokens",
                   "what": "Actions から編集するときだけ（digest.edit_stories）。使ったトークンは数える"},
    # ---- アルゴリズム
    "pace": {"kind": "algo", "name": "サイトごとの間隔（全スレッド共有）", "spec": "Reddit 2 秒 · Google / Bing 0.5 秒 · Wikimedia 同じホスト 1 本ずつ・1.3 秒 + 全体 0.4 秒（毎分 150）",
             "what": "sources._pace / wikihttp.get。並列でもサイトから見た間隔は同じ"},
    "wikiua": {"kind": "rule", "name": "Wikimedia の決まり（wikihttp）", "spec": "UA「WishlistEmblemBot/1.1 (repo; Issues) python-requests」· WIKIMEDIA_TOKEN があれば API に OAuth 2.0 Bearer（上限が共有 IP でなくアカウントごと）· "
               "Wikidata の項目は Special:EntityData（CDN）· api.php に maxlag=5（Wikidata は WDQS の遅れまで数えるので付けない）· "
               "429 / 503 / maxlag は Retry-After（なければ 5・15・45 秒）で 3 回まで · Retry-After > 120 秒か続く 429 → そのホスト 5 分休む · titles は 50 件ずつ",
               "what": "scripts/wikihttp.py（小元素・話題度の閲覧数）。ブラウザのふりの UA（Mozilla/…）は 403、名乗らないと毎分 10 回まで。守ったボットは全サイト合わせて毎分 200。"
                       "クラウドのコンテナ・Actions は IP を共有していて 1 回目から 429 のことがあるので、トークンで名乗る"},
    "httpcache": {"kind": "algo", "name": "requests-cache（SQLite）", "spec": "~/.cache/wishlist-http · api.php 3 日 · 画像 14 日 · 200 だけ（maxlag の断りは残さない）",
                  "what": "同じ網址は取り直さない。Actions では actions/cache で次の回へ持ち越す"},
    "dedupe": {"kind": "algo", "name": "タイトルの重複判定", "spec": "完全一致 + 文字 bigram 重なり > 0.75 · 14 日分",
               "what": "digest.filter_entries：作品名を除いて比べる。転載・題名の切れ端も 1 件に"},
    "match": {"kind": "rule", "name": "match / exclude", "spec": "部分一致（空白・大小無視）· re: は正規表現（数字・泛詞・常用語は主題の語と一緒のときだけ：滑雪の 26/27・早割・Burton、MMO は単語）· exclude は標題の部分一致",
              "what": "items.yaml の match にある語がタイトルか要約にないと収めない（digest.match_hit）。収集と audit-match は同じ digest.drop_reason"},
    "srcfilter": {"kind": "rule", "name": "出典名・網域の除外", "spec": "exclude_sources は前方一致（YouTube → YouTube on MSN、続きが ASCII の英数字なら別名・公式チャンネル YouTube · 名前 は除く）· exclude_hosts は網域と下位網域（settings：readyfor.jp・camp-fire.jp は網域まるごと、攻略 wiki の gamewith.jp・game8.jp・altema.jp は {host, title} で攻略頁の標題の形「【略称】…【正式名】」「【略称】…の評価・攻略・一覧・引くべき…」だけ、編集部のニュースは残す。escorenews の配信頁は dota2 の exclude「match stream」で。関注項ごとにも）· e.link・e.url・Google ニュースの <source url>（Entry.site、inbox にも書く）で見る · 収集・audit-match・「気になるかも？」の候補で同じ",
                  "what": "攻略 wiki・クラファン・試合の自動頁など「ニュースではない」サイトを収集で落とす（digest.drop_reason・audit-match の ✗）"},
    "spam": {"kind": "rule", "name": "スパム判定 SPAM_PATTERNS", "spec": "漢字の間の ❌ · 在线看・高清完整・免费全集 等 · 末尾「〜网」· 網址の参数に「伴游・微信・加V」と data: の動画（?&xml=data:video…）など（SPAM_URL）· 末尾の「(10 桁の随機コード)」（小文字あり・大文字＋数字 3 以上）· リンクが垃圾サイトの網域（SPAM_HOSTS = unisba.ac.id）· 収集・inbox の合併・整理待ち・出刊・ページ生成・おすすめ・話題度の報道量から落とす",
             "what": "digest.is_spam：乗っ取られたサイトの垃圾ページ（成人・海賊版「在线看」、Unisba Media の「別の記事の標題 + 作品名 + 随機コード」）を捨てる（作品名を詰めているので match を通ってしまう）。AI 編集は末尾の随機コードを削るので、リンクの網域でも見る"},
    "taxonomy": {"kind": "rule", "name": "板块の対号入座 sections.yaml", "spec": "大類 8（IAB Content Taxonomy 3.1 の大類を 2026-10-19 にまとめた：作品・ゲーム・音楽・スポーツ・ショッピング・暮らし・おでかけ・その他）· 各 2 つの分け方と常用の値 · ゲームを先に（prio）、あとは上から先に当たった語 · 旧い 17 板块の名前は LEGACY で大類へ · 同じ板块に媒体 2 つ以上 = 小分類「シリーズ」",
                 "what": "維基データの説明・名前の語で板块と小分類を推す（taxonomy.classify / guess_subs、ウィザードも同じ表）。新しい板块は臨時に作らない、当たらなければ「その他」"},
    "lang": {"kind": "rule", "name": "言語違いの同じニュース lang.dedupe", "spec": "主言語 ja → 副言語 en・zh・ko（settings.languages）· 仮名 2 字 = ja・ハングル 2 字 = ko・漢字 2 字 = zh・ローマ字 3 字 = en · "
             "同じ作品で 10 日以内かつ（バージョン番号 / 見出しの月日 / 予定の日付＋ラベル）が同じ = 同じニュース · 主言語・副言語以外は載せない",
             "what": "scripts/lang.py：同じニュースが何語でも来たら主言語の 1 本だけ残し、消す方の重み・予定・出典を引き継ぐ。出刊（号の中）とページ生成（号をまたぐ）の 2 か所。"
                     "refs に好みの言語の出典があれば見出しをその原題に（lang.prefer_ref）。予定の欄は同じ作品・同じ日・同じラベルも 1 回"},
    "urgent": {"kind": "rule", "name": "要紧の判定 urgent_patterns", "spec": "タイトルに正規表現 · Reddit・補完分は除く",
               "what": "当日 Discord に送る記事（digest.is_urgent）"},
    "fallback": {"kind": "algo", "name": "キーワード編集 fallback_stories", "spec": "重複 bigram > 0.5 · 4 媒体以上で話題 · 最大 7 件",
                 "what": "AI 編集がまだの新着のうち、要紧（urgent_patterns）のものだけを規則で「重大」にまとめて先に載せる"},
    "pending": {"kind": "rule", "name": "整理待ち split_unedited", "spec": "_covered より後 · edit.json にない版面 → 版面に載せない · 原題 20 件まで表示",
                "what": "digest.split_unedited / render._pending：版面には AI 編集が整理した記事だけ。未整理の新着は版面の下の折りたたみ「整理待ち N 件」に原題・出典だけ"},
    "batch": {"kind": "rule", "name": "AI 編集の順番と開関 edit_next", "spec": "やり直し → 整理待ちの多い順 · 1 版面ずつ出刊・push · 管理ページの開関 run / step / pause（Supabase edit_control）· トークンはセッションの記録から（usage.py）",
              "what": "digest.edit_queue / edit_brief / _log_edit_batch：編集が終わった版面から順に網页に出す。読ませる一覧は網址を省いて短く"},
    "bundle": {"kind": "algo", "name": "出来事の束 bundle.bundles", "spec": "版面ごと · 語（story_tokens − 版面の名前・出典名・末尾の（媒体）［大会］・記事の 2 割を超える語）の重なり 重み ≥ 2・少ないほうの 4 割・合わせた語の 2 割（MinHash と同じ考え）· 日付 3 日以内 · 言語違いはバージョン・月日が同じ · 束どうしは近い組 5 割以上（平均のつながり）· スコア・バージョン・月日・第 N 話・勝ち上がりの回が食い違えばつながない",
               "what": "edit-brief を束ごとに並べ（2 本目からは題 60 字だけ）、前回の編集（_covered）のあとは新しい束と記事が増えた束だけ・今の記事は 1 行ずつ。過去 7 日（4,707 件）で束 3,936・誤まとめ 6〜8、AI に渡す字数 29% 減（1 日 2 回の編集で試算）"},
    "imgpick": {"kind": "algo", "name": "配図の選び方 images.pick", "spec": "短辺 ≥200 · 長辺 ≥300 · 8MB まで · 1 件 60 秒・12 枚まで · TLS は ALPN http/1.1（ブラウザと同じ。ないと i0.wp.com が 404）· おすすめの「図なし」は翌日もう一度探す · おすすめカードは図が全部開けなくても来源サイトの图标に退ける（空の枠にしない）",
                "what": "AI 指定 → 記事の画像 → og:image → JSON-LD → 動画の表紙（<video poster>：虎扑の動画帖など）→ 本文 → Bing の縮小画像 → 転載ページ。ロゴ・既定画像（logo / noimage / placeholder / default_image / no_photo / NowPrinting / blank.png：サイトの占位図）は除く。作品の表紙にも使わない。"
                        "Bing の縮小画像（bing.com/th）は Bing が切った一部分なので原文の図の後ろ。repair-images（収集の手動実行）で既刊も直す"},
    "imgsibling": {"kind": "rule", "name": "別のサイトへ回る same_event / retry_images", "spec": "同じ出来事 = 作品名を除いた共通の語 ≥ 2（StoryDeduper と同じ）· 別の記事 4 本まで · 引用された原題「…」でも転載を探す · 図なし・図が開けなくなった（dead）は 6 時間ごとに出刊のたび再探し（1 回 6 件・1 件 25 秒・直近 8 日）· 単色の空白図（標準偏差 < 3）は使わない",
                   "what": "原文が人機検証・限流・一時的に開けない（ナタリーの 405 など）ときも止まらず、同じ出来事を報じた別のサイトの記事の図 → 転載へ進む。それでもないものは後の出刊で自動でもう一度（state/img_retry.json）"},
    "imgsharp": {"kind": "rule", "name": "より大きい予告画像 / 防盗链の再試行", "spec": "og:image・JSON-LD の長辺 < 1000 なら同じページの大きい方 · 403 は原文ページを Referer に 3 枚まで",
                 "what": "images.pick：同じ記事の大きい版（JSON-LD の 1920×1080 など）を先に。新浪 sinaimg など Referer がないと 403 の図は「（本站保存）」として hdimg が本站に置く"},
    "scrapling": {"kind": "algo", "name": "拒まれたときの取り直し scrapling", "spec": "① Fetcher（Chrome と同じ TLS・HTTP/2、curl_cffi。記事の頁だけブラウザらしいヘッダー、画像は付けない）→ ② StealthyFetcher（本物の Chromium・Cloudflare の確認画面も待つ、Actions で SCRAPLING_BROWSER=1・1 回 10 頁・合わせて 180 秒まで・1 頁は別プロセスで 45 秒で必ず打ち切り・開けなかった頁は 24 時間開き直さない）· 対象 = 202/401/403/405/429/503 か確認画面の文 · 有料記事・ログインの壁は越えない · 取り直しでしか取れない画像は本站に保存",
                  "what": "防機器人・限流で開けない記事の頁と画像（2026-10-22 の測定：図の再挑戦待ち 36 件のうち ① だけで +3〜4 件）"},
    "keyimg": {"kind": "rule", "name": "代表の 1 枚 key_score", "spec": "正文図は最初の 1 枚で決めず 6 枚まで確かめる · 点数 = log(面積) − 2×|log(横÷縦 ÷ 1.6)| − 0.35×順番 · 横÷縦 > 3 か < 0.4（帯・広告・区切り）は −10",
               "what": "写真がたくさんある記事から、大きく・カードの窓に近く・記事の上のほうの 1 枚"},
    "hdimg": {"kind": "algo", "name": "看不清の判定と OpenCV 高清化 hdimg", "spec": "写真のない記事は版面の頭にせず（render._photo_head：頭条・重大が写真なしなら普通の記事に下げ、写真のある新しい記事を頭条へ）、アイコンの札でなく字だけの形（.nophoto）で出す · 表示で 1.6 倍以上に引き伸ばす かつ 表示サイズでの模糊度 > 0.42（Crété-Roffet re-blur 法・1×9 平均）· 大きい枠 1280px（各作品の新しい 2 本・頭条・おすすめカード）・カード 720px · NLMeans h=3 → Lanczos4（最大 3 倍）→ 輝度 USM 0.7 · webp 82 · 6 並列",
              "what": "hdimg.py：看得清の図は触らない（ファイルも作らない）。Bing の 100×100 縮小画像は w=1200 版を取り白い余白を切る。防盗链の図と期限付きの網址（Yahoo の ?exp=）は出刊時に本站に置く。開けなくなった図（404・1×1 の空白）は dead にして探し直しへ。docs/home/pics/ を render が元の網址の前に差し込む。8 日を過ぎた図は消す"},
    "reddithot": {"kind": "rule", "name": "Reddit の「火」と削除 reddit_hot / reddit_removed", "spec": "版块の今週の人気 上位 5 · 全站検索は人気順の上位 5 · API の数字があれば 赞 ≥100 か 评论 ≥30 · 本文 [removed]/[deleted]・404 は削除",
                  "what": "火でない帖子は版面に載せず reddit_cold として帖子数（話題度のファンの反応）だけに数える。載った帖子は毎日 1 回、削除・人気から落ちたかを見て撤去（prune_reddit · state/reddit_check.json）"},
    "heat": {"kind": "algo", "name": "話題度 6 次元", "spec": "報道量 20・広がり 15・出来事 20・勢い 15・一般の関心 20・ファン 10",
             "what": "heat.py：各次元 = 60% 自分の平常比 + 40% 共通の尺度。取れない次元は分母から外す"},
    "octree": {"kind": "algo", "name": "減色 FASTOCTREE 16 色", "spec": "背景 = 最多色 · 強調 = 彩度^1.5 · WCAG 4.5:1",
               "what": "theme.from_image：Pillow quantize。読めるまで明るさを ±0.04 ずつ動かす"},
    "fit": {"kind": "algo", "name": "写真のはめ方 FIT_JS", "spec": "|ln(画像比 / 枠比)| < 0.08 のときだけ埋める（切れるのは 8% まで）· ほかはぼかし背景に全体 · 気になるかも？はスマホで枠を写真の比率に",
            "what": "render.py：どんな比率の配図でも同じ枠に入れ、写真は切らない（文字・ロゴ入りのバナーが欠けるため）。枠の大きさは変えないので壁の段はそろう"},
    "ahash": {"kind": "algo", "name": "差分ハッシュ 9×8", "spec": "ハミング距離 ≤ 4 は同じ画像",
              "what": "emblem_fill._hash：網址が違う同じ写真を 1 枚に"},
    "roster": {"kind": "rule", "name": "上限 = 主要な要素の数（emblem_fill.roster / rule）", "spec": "キャラ ≤200（主要キャラ全員）· グループ ≤50 · 主題 ≤10 · 本人 10 · ブランド 1 · 1 回の後台で 10 人ずつ足す · 名簿に入れない：まとめ・一覧（…List）・Player・Parents・別の作品の姿（括弧に Smash Bros・vs.）・分類の名前の単数（Special character）＝emblem.not_character、新しく足す名前にも前から名簿にいる名前にも（集める対象 subjects でも外す）",
               "what": "Wiki の分類（emblem_category）か AniList の主役を数えて emblem_pool に。名前は参照の多い順に全員 emblem_who へ。まだいない人から 10 人ずつ集める（emblem_fill.STEP）"},
    "cutcheck": {"kind": "algo", "name": "切り抜きの検査 check_whole", "spec": "上の端 >50%（コマの切り抜き）· 上の端に当たり額まで切れた（YuNet の目が目〜口 ×1.4 より上：emblem.forehead_cut、前からの小元素も drop_broken で外す・哈利波特 Dominic 197×101。前からの小元素も上の端に 3% 以上当たったときだけ見る〔check_whole と同じ〕。上の端の 50% 超が人物 TOP_MAX も前からの小元素を drop_broken で外し次の候補で取り直す〔BLEACH Mirrors High Muramasa〕。規則の版 BROKEN_V を上げると前の版で外した小元素を今の規則で見直して戻す：emblem_fill.unbreak・state/emblem_broken.json・The Mandalorian Gideon・Mayfeld）· 頭のてっぺんが切れた（上 3px に横幅の 20% 以上：emblem.head_cut、顔が全部入っていても ✗・前からの小元素も drop_broken で外す。壊れた小元素のある版面は失敗の待ち〔RETRY_HOURS〕も待たない・BLEACH Mirrors High）· 写真で顔がなく横長（横 > 縦×1.3）= 髪・額だけの切れ端は ✗（emblem.faceless_scrap・BROKEN_V 3・哈利波特剧集 Hermione 194×92。縦長の兜は残す）· 写真は顔の幅 ≥80px・顔の輪郭の鋭さ ≥1.0（emblem.face_sharp：拡大したぼやけた剧照を使わない・哈利波特剧集 Oliver Wood）· 形の健康（scripts/cutshape.py・emblem.trim_flat：左右の端にそって高さの 15% を超えてまっすぐ続く直線の切り口は、切り口が始まる行で下を切り落として半身に〔残り ≥40%・顔の下まで〕、直せなければ ✗ で次の候補・上の端に横幅の 25% を超えて直線・面積 ÷ 凸包 <0.30 の凹みすぎも ✗。顔の大きさをそろえる face_fit の横の切り口も同じ trim_flat。前からの小元素は emblem_fill.repair_flat が半身に直し、直せないものは drop_broken が外す：哈利波特剧集 Gregory Goyle・BROKEN_V 4〔凹みの閾値は 5 で 0.45→0.30〕、お客さまの版面は bv が古いので 1 回見直す）· 左右の端 >10% · 面積 <12% · 半透明 >18% · 写真は切り抜きに顔が残ること・明るさ ≥16%（暗い場面は使わない）· 外れた画像は emblem_reject へ · 同じファイル（Wikimedia の網址違い）は 1 枚 · 書き出す切り抜きは短い辺 ≥64px・横 ≤ 縦×3（emblem.save_cut：切れ端は書かず前の画像を残す）、fit_all は自分の前の出力（emblems/ の cutout）を整え直さない〔commit のたびに縮んだ。作り直すなら元の画像 source から〕、前からの切れ端・読めない（0 バイト）切り抜きは外して emblem_reject へ（emblem_fill.drop_broken、due にも入る：漫威电影 Black Panther 60×10・BLEACH Mirrors High 209×45・0 バイトの nianzol-weizol）· 元の画像のファイル名が大乱闘のフィギュア・持ち物（Trophy・SSBB・Item_…：emblem.BAD_SOURCE）は取らず、前からのものは broken_cuts／library_emblem.unbroken が外す（BROKEN_V 6・あつ森 Redd・原神 Kaeya）· 同じ image・同じ元のファイル・同じ見た目（差分ハッシュ、透明は灰の上で測る）は 1 枚（emblem_fill.drop_same・unbroken：Vaundy 3 本・Stella Fortuna 3 人。背の高い細い立ち絵どうしを同じと誤る E8 も直した：呪術廻戦）",
                 "what": "emblem.check_whole：体が枠で切れた・輪郭がにじんだものを使わない"},
    "facefit": {"kind": "algo", "name": "顔の大きさをそろえる", "spec": "胸像：顔 = 高さの 32% · 公式の立ち絵は全身のまま · 胸像と全身は多いほうに",
                "what": "emblem.face_fit / upper_body / keep_framing"},
    "facerule": {"kind": "rule", "name": "写真の規則 photo_problem", "spec": "顔の高さ ≥ 10% · 2 番目の顔 < 60% · 基準なしは同じ顔 2 枚以上",
                 "what": "face_id.py：前は Claude が目で見ていた「遠景・集合写真・別人」を数で判断する"},
    "holes": {"kind": "rule", "name": "切り抜きの穴 hole_share", "spec": "実在の人の写真で体の中の穴 > 3% は外す（絵は除く）",
              "what": "emblem.check_whole：服が背景と同じ色で抜けた切り抜きを落とす"},
    "gate": {"kind": "algo", "name": "ゲート gate.py", "spec": "AI 編集は版面ごとに溜まったら（edit_ripe：整理待ち 3 件以上・いちばん古いもの〔収集した時刻 seen〕が 2 時間・初めての版面。収集のあと・後台作業で。9:00・18:00 は待たない）· 1 日（北京時間）のトークン上限 100 万（新規入力＋出力、ボタンは別）· 一時停止中は起こさない · 起こして 60 分あけて、編集済みが増えなければ「停滞」→ 起こし直す（3 回まで・そのあと 6 時間待つ）· 起こしたのが前の日（北京時間・fired.day）なら停滞と数えず定時を待つ · 北京 0 時すぎに前の日の 18:00 の回は拾わない（9:00 を待つ）· 「動いている」は今回起こしたあとの最後のバッチから 30 分以内（起こしたあと出刊がないまま 60 分 → 「出刊されていない」）· 新関注項の「すぐ AI 編集」（GATE_NOW）は定時だけ飛ばす：60 分以内で止められたら jobs.edit.now_pending に残し、後台作業が 60 分後に起こす（12 時間で捨てる）· 変数 GATE_FIRE = edit / 1",
             "what": "仕事があるか・AI が要るかをプログラムだけで決める。AI の要らない仕事はその場で済ませる"},
    "userfeed": {"kind": "rule", "name": "お客さまの版面の記事集め userfeed.py", "spec": "だれの分：userfeed_users()（Auth のユーザーがいて一度はログインした人だけ・登録の古い順・1000 行ずつ）· app_users.prefs.picks のうち店長のページに版面がないもの（docs/home/index.html の section.sec[data-k] と shop_hit = 網页の shopHit と同じ規則：同じ名前か、かな・漢字 2 字以上が含まれるか、英数字は前後が英数字でないとき）· 1 人 100 版面まで（app_users.board_limit と同じ、超えた分は state=limit の行）· 1 人 1 回 10 版面（全員の 1 つ目から順に）· まだ集めていない人は 1 回 15 人まで · 1 回 80 版面・8 分（job の timeout 40 分の 3 分前まで）・4 本並列 · 前に探してから 90 分は飛ばす · 同じ名前・同じ言語・同じ匹配词は 1 回で · 匹配词：英数字は記号のゆれを許した句（語の境あり）、数字のない 14 字以下は英語のよく使う語（scripts/data/en_common.txt.gz：wordfreq zipf ≥ 3.0・27811 語）でない 4 字以上の語があれば名前だけ（ILLIT・Vaundy・Astrae Oratio：10 月の inbox 7512 件で 208/208・48/48・37/40）、全部よく使う語なら板块の語（CONTEXT_EXTRA、前後が英字でないときだけ・update / PC / open など普通の語は入れない）と一緒のとき（2 語以上の句はかな・漢字・ハングルの記事でも）・数字だけの名前はいつも語と一緒・記号だけの名前は集めない（0 件の行 1 つ）、かな・漢字 1 語で末尾がジャンルの語（広島旅行）なら前の部分＋同じジャンルの語でも、® ™・末尾の「第2期」は外す · Google・Bing・情報員（SNS の全体検索・GDELT はしない）· 店長と同じ drop_reason・重複・fallback_stories・lang.dedupe · 1 版面 12 件・14 日（日付のない記事は見つけた日から）· 検索が 429・時間切れで 1 件も来なかった回も失敗（sources.fetch_fails）· 失敗した版面は記事をそのまま fails+1・探した時刻を進める（列の後ろへ。0 件で 5 回未満は「集めています」）· 時間切れは探した印を付けない · ログは数だけ（選んだものの名前は出さない：Actions・ライブログは公開）· つながらない・時間切れも失敗として続ける · 書けない行は 1 行ずつ書き直す · 一覧を全部読めなかった回は行を消さない · Supabase user_boards（account = u_ + md5(メール) 16 字）· 本人は my_boards() で自分の行だけ · 写真と原文の網址：1 回のうち 150 秒（MEDIA_S）を取っておき、書く行と 90 分以内に探して今回は飛ばした行のうちまだのものに、店長と同じ sources.resolve_url（Google の跳转を原文に、1 回だけ試す・続けて 4 本断られたらこの回はやめる）と images.pick（1 版面の記事を新しい順に全部・1 本 20 秒・同じ写真は 1 版面 1 回・本站保存が要る写真は使わない・見つからなければ 3 時間あけて探し直す・3 回〔img_n〕で諦める）· 期限付きの網址の写真（?exp=、images.expiring）は 6 時間ごと（EXP_CHECK_H）に images.check で開けるか確かめ、404・空白なら外して原文から探し直す（時間切れ・つながらないは消さない）· 本物のブラウザは使わない（記事の網址が公開のログに出るので）· AI なし",
                 "what": "お客さまが自分で選んだものの記事。網页（AUTH_JS の showMine）が店長のページと同じ「板块 → 小分類」の位置に版面を描き、目次（線路・スマホの上の帯）に駅を足す（NAV_JS は 'wl-nav' で数え直す）· 店長のトップのポスターと「気になるかも？」は同じ作りのまま自分の版面の記事・カードだけに絞る（頭条が自分の版面でなければ箱の「今日の主なニュース」・「気になるかも？」に替える）"},
    "userpages": {"kind": "rule", "name": "お客さまのページ user_pages.py", "spec": "digest.yml の別の job（needs: run・!cancelled・12 分）· userfeed_users() の全員 · 版面と置き方 = ライブラリの本人の follows（並び pos・板块 section・小分類 subs → 本人が選んだ分け方〔nav_schemes の本人の行、なければ 1 つ目〕で目次の札と本文の小見出し・篇幅 size、なければ prefs.sizes）。設定ページ = 店長と同じ render.render_settings（own：日本語・向導と删なし・各行「外す」= my_keywords_set）を pages/<account>/settings.html に、me.html?p=settings で読む。S/M/L → my_size_set（follows.size＋prefs.sizes、sizes 表には書かない）・分け方 → my_nav_scheme_set（nav_schemes の本人の行）、db/my_layout.sql、どちらも押すたびに render.yml を起こす（cancel-in-progress で最後の回が勝つ・1 人 10 分 30 回まで private.render_kicks）。並びは板块 → 小分類 → pos）、follows にまだないもの（library.py --users の回の前）は app_users.prefs.picks から板块だけ · 出すのは picks にある名前だけ（設定の「外す」で picks から消えたものは follows に行が残っていても出さない）· 版面の中身（店長と同じ名前 = 店長の設定と最新号の版面、ほか = user_boards の記事・小元素と配色はライブラリの boards.config〔library_emblem.py〕。どちらも本人の篇幅で S 3・M 5・L 8 本まで（digest.SIZE_STORIES）・種類から render.template_for・写真から theme.resolve）· 写真のない記事は images.pick（1 版面の頭 3 本・合わせて 240 秒）· render.render → <meta name=wl-own> · Supabase Storage pages/<u_+md5(メール)16字>/index.html（db/user_pages.sql：本人のフォルダか is_admin() だけ読める・書くのは secret key）· 網页：店長のページの AUTH_JS はお客さまを殻のページ me.html へ送るだけ（30 秒に 3 回まで）。me.html（render.render_me、ほかの JS なし）が my_page_path() → storage download → そのページに替え、網址を ./ に戻す。読めなければ ./?own=0 で前の画面。本人のページでは版の確かめ（LIVE_JS）をせず、ログアウトのときだけ開き直す · render.yml でも作り直す（部品が変わったら同じ回で） · 版面 0 個の人も同じ枠組み（静かな版面「はじめに」から ../?add へ）· ログインしたお客さまはだれでもまず本人のページ・本人の設定ページ（版面の数によらない）· 1 人の失敗でほかを止めない · AI なし",
     "what": "お客さまのページも店長と同じ部品で作り、本人だけが読める場所に置く"},
    "collectwatch": {"kind": "rule", "name": "収集の控えの時計 collect_watch.py", "spec": "後台作業のたび（pg_cron で毎時必ず）· 最後の収集から 150 分 → digest.yml を workflow_dispatch · 走っている・並んでいる・60 分以内に始まった回（timeout 40 分より長く）があれば起こさない",
                     "what": "GitHub の定時（17 */2）が抜けても収集が何時間も止まらないように。起こした・起こせなかった・回の様子が読めなかったら state/log/gate.json に 1 行（同じ失敗の続きは書き足さない）"},
    "libwatch": {"kind": "rule", "name": "ライブラリの控えの時計 library_watch.py", "spec": "後台作業のたび（pg_cron で毎時必ず）· library.yml の最後に成功した回（gh run list）から 80 分 → workflow_dispatch（users_only：お客さまの選んだものだけ、番号の引き直しはしない）· 走っている・並んでいる・30 分以内に始まった回（timeout 15 分より長く）があれば起こさない",
                 "what": "GitHub の定時（毎時 41 分）が抜けても、お客さまが新しく選んだものが 2 時間以内に follows に入るように。起こした・起こせなかった・読めなかったら state/log/gate.json に 1 行（同じ失敗の続きは書き足さない）"},
    "deadline": {"kind": "rule", "name": "収集の締め切り COLLECT_DEADLINE_MIN", "spec": "18 分 · 過ぎたら新しい版面を始めない · 始まった版面も 23 分（＋5 分）で待つのをやめる · 残りは次の回に先に取る（deferred）· 初めて取る版面（新関注項）も先に · 過ぎてからの封面はネットに出ない · 1 版面の取得・処理の例外はその版面だけ空で続ける · timeout 40 分",
                 "what": "digest.ingest：timeout で push の前に切れて、その回の分が全部消えないように"},
    "taste": {"kind": "algo", "name": "好みの学習", "spec": "ラベルごと ±1 · 上限 −6〜+4 · 出すのは 5 点以上",
              "what": "digest.learn_taste：👍👎 の最後の一票から"},
    "softalt": {"kind": "rule", "name": "鮮やかな副色の広い面を落ち着かせる _loud / .softalt",
                "spec": "色度 ≥ 0.45 かつ 明るさ ≥ 0.12 → 「もっと見る」の背景 = 主面 + 副色 20% · 強調文字 4.5:1 以上",
                "what": "render._loud が副色（alt_bg）を判定し、鮮やかな作品の版面に softalt を付ける。副色そのものは上の線・＋ボタン・札だけに残す。暗い・淡い副色は変えない"},
    "frontpick": {"kind": "rule", "name": "トップの選び方 _front_pick", "spec": "作品ごとに 1 本目が先 · 同じ写真 1 回 · 同じ作品で話題語が重なれば出さない",
                  "what": "render._front_pick：ポスター＋写真の壁 15 本。数日続けて同じ出来事が並ばない。借りた作品の表紙は版面ごとに 1 本、ポスターは自分の写真を優先"},
    "storydedupe": {"kind": "algo", "name": "StoryDeduper union-find + OpenCC", "spec": "共有トークン ≥ 2（漢字 2 文字 = 0.5）· 繁→簡",
                    "what": "おすすめの同じ話をまとめる。どこにでも出る語は数えない"},
    "crop": {"kind": "algo", "name": "Pillow の切り取り", "spec": "モデルなし · 品質 90",
             "what": "写真から愿望：物の範囲を Claude が決めて切り取る"},
    # ---- API・外のサービス
    "gnews": {"kind": "api", "name": "Google ニュース RSS", "spec": "5 言語 · 7 日（初回 42 日）",
              "what": "sources.google_news。リンクは batchexecute で原文に戻す（3 回まで）"},
    "bing": {"kind": "api", "name": "Bing ニュース RSS", "spec": "空なら 3 回まで · 画像 1200px",
             "what": "sources.bing_news"},
    "reddit": {"kind": "api", "name": "Reddit OAuth / RSS", "spec": "新着 25 件 ＋ 今週の人気（top?t=week）· 429 が 2 回で今回は止める",
               "what": "sources.reddit_search / reddit_sub"},
    "steam": {"kind": "api", "name": "Steam Web API", "spec": "ニュース 10 件 · 価格 · 同時接続",
              "what": "GetNewsForApp・appdetails・GetNumberOfCurrentPlayers"},
    "anilist": {"kind": "api", "name": "AniList GraphQL", "spec": "続編 10 期まで · 人気・トレンド",
                "what": "放送状態・主役キャラ・話題度"},
    "tmdb": {"kind": "api", "name": "TMDB API", "spec": "放送状態 · popularity", "what": "ドラマ・映画の状態と話題度"},
    "gdelt": {"kind": "api", "name": "GDELT DOC 2.0", "spec": "世界 65 言語のニュース索引 · 読者の言語だけ（sourcelang）· 最大 50 件 · 5 秒に 1 回（5.5 秒）· 429 は 6 秒あけて 3 回まで・それでも断られたらこの回はもう聞かない（Actions の共有 IP ではほぼ断られる）· 記号は抜く · 関注項ごとに最初の 2 語",
              "what": "Google・Bing に出ない各国の地方紙・専門サイトの記事（配図 socialimage つき）。use に google がある関注項"},
    "intel": {"kind": "rule", "name": "地域ごとの情報員 intel", "spec": "intel/<地域>.yaml（今は日本：専門サイトの RSS・Atom 17 本、ゲーム 4・作品 4・音楽 3・スポーツ 1・ショッピング 3・おでかけ 2）· 開關 settings.intel · 担当 = 関注項が自分で書いた news_langs と地域の言語が重なる（intel: [] で止める）· 読むのは cats が関注項の板块（section・also）と重なる情報源 · 同じフィードは 1 回の収集で 1 回 · RSS 1.0（RDF）も読む · ナタリーは Python-urllib の UA（HOST_UA）· 情報源ごとの様子（ok・blocked・timeout…）をログに",
              "what": "全世界共通の検索に出てこない、その地域の専門サイトの記事。match・exclude・垃圾站・去重は今までどおり"},
    "youtube": {"kind": "api", "name": "YouTube チャンネル RSS", "spec": "公式チャンネルの新着 15 本 · チャンネルは items.yaml の youtube か wiki → Wikidata P2397（30 日ごとに見直し）· サムネイル hqdefault",
                "what": "公式の予告・発表動画。use に関係なく"},
    "bluesky": {"kind": "api", "name": "Bluesky 検索 API", "spec": "人気順 25 件 × 読者の言語 · 火 = ♥ 50 か 再投稿＋引用 15 · 標題（投稿の文）に名前",
                "what": "ファンの反応。use に reddit がある関注項。火でない投稿は版面に出さず話題度だけ"},
    "mastodon": {"kind": "api", "name": "Mastodon ハッシュタグ", "spec": "mastodon.social の #名前 40 件 · 読者の言語だけ · 火 = ♥ 20 か ブースト 10 · 網址から始まる投稿（自動転載 bot）は捨てる",
                 "what": "ファンの反応。use に reddit がある関注項"},
    "wikipv": {"kind": "api", "name": "Wikipedia 閲覧数", "spec": "60 日分 · 50 記事ずつ · 1 日 1 回 · wikihttp 経由（トークン・Retry-After・12 時間キャッシュ）",
               "what": "話題度の「一般の関心」"},
    "wiki": {"kind": "api", "name": "Wikidata / Wikipedia / Commons", "spec": "P154 ロゴ · P18 写真 · ≥300×300",
             "what": "小元素の候補（en / ja / zh / ko）"},
    "fandom": {"kind": "api", "name": "Fandom MediaWiki API", "spec": "キャラのページの代表画像", "what": "絵のキャラの小元素"},
    "twemoji": {"kind": "api", "name": "Twemoji 15.1.0", "spec": "SVG アイコン · 0 枚を防ぐ最後の砦", "what": "主題の小元素"},
    "youtube": {"kind": "api", "name": "YouTube 検索ページ（ytInitialData）", "spec": "1 人 4 本 · 題名にグループ名と名前 · 직캠・fancam を先に · 動画の場面 hq1・hq2・hq3（480×360、投稿者のサムネイルは字が載るので使わない）",
                "what": "メンバー・出演者の写真（Commons にない人）。本人確認は顔の規則"},
    "bingimg": {"kind": "api", "name": "Bing 画像検索", "spec": "一覧に載せるだけ · 自動では選ばない", "what": "出所が不確かなので目で見る"},
    "supabase": {"kind": "api", "name": "Supabase REST / RPC", "spec": "アカウントごと（account 列・p_account つきの関数、db/accounts.sql：店長 = account test1（網址は /home/）・試験の版 test2 は別のアカウント）· news を 500 件ずつ upsert · my_votes · set_size",
                 "what": "投票・篇幅・依頼・写真・記事の控え"},
    "pgnet": {"kind": "api", "name": "pg_net → GitHub dispatch", "spec": "20 秒に 1 回まで", "what": "設定ページの依頼ですぐ Actions を起こす"},
    "discord": {"kind": "api", "name": "Discord Webhook", "spec": "要紧 ≤6 行 · 埋め込み ≤10 · 30 日は二重に送らない",
                "what": "notify.py"},
    "confetti": {"kind": "api", "name": "canvas-confetti 1.9.3", "spec": "👍 の演出 20 種", "what": "likefx.py"},
    "maillink": {"kind": "api", "name": "だれでもメールアドレス＋パスワード（Supabase Auth signInWithPassword・bcrypt・supabase-js 2.45.4）",
                 "spec": "だれでもメール＋パスワード（2026-10-21，用户定的：メールは送らない・再発行なし・退会の機能なし）· 新しく始める＝メール・パスワード（8 文字以上）・規約・好みを user_signup で一度に → Supabase Auth のユーザーを確認済みで作る（private.make_auth_user）→ そのままログイン · ログイン中のメニューで自分のパスワードを変える · 店長は管理ページでお客さまのパスワードを変える（admin_users / admin_user_password）· テスト用 5 つはパスワード 0000",
                 "what": "render.AUTH_JS（右上の「ログイン」）。Google ログインは保留（PENDING.md）"},
    "welcome": {"kind": "rule", "name": "入口と新しく始める（scripts/welcome.py）",
                "spec": "言語 = 地域ごと MECE 56 言語（よく使う 6 つ＋ブラウザの言語を先に）· カード 16 枚まで・最初の版面 5 つまで · 候補は規則（AniList TRENDING・Steam featuredcategories・archive/test1 の関注項）· 24 時間ごとに作り直す",
                "what": "docs/index.html（本番）・docs/testground/welcome.html。登録は public.user_signup、好みは app_users.prefs"},
    "terms": {"kind": "rule", "name": "利用規約・プライバシーポリシー（render.render_terms・TERMS_VERSION）",
              "spec": "第 1 版 · 新しく始めるときに同意必須 · 版が上がったらもう一度 · 集める情報・使い道・預け先（Supabase＝豪・GitHub/Anthropic＝米）・退会",
              "what": "docs/<account>/terms.html。同意は app_users.agreed_version / agreed_at"},
    "invite": {"kind": "rule", "name": "管理者のメール（public.invites の role=admin）",
               "spec": "だれでもメールで登録できる（招待制にしない）· 表にあるメールは管理者 · 5 人まで · 最初の管理者 c.elegy@outlook.com",
               "what": "db/auth.sql（登録時の trigger が役割を決める）。追加は管理ページ「ユーザーと管理者」（admin_invite）"},
    "roles": {"kind": "rule", "name": "身份と開關（can_edit / is_admin / auth_flags.enforce）",
              "spec": "访客 = 見るだけ · ユーザー = 自分の account だけ · 管理者 = 全部と管理ページ · 開關が閉じている間は前と同じ",
              "what": "db/auth_guard.sql（書く関数の 1 行目で確かめる）・db/auth_enforce.sql（開關）"},
}

PROCESSES = [
    {
        "id": "emblem", "name": "小元素の選定（AI の分）", "en": "EMBLEM", "lane": "ai", "schedule": "edit", "when": "新しい関注項が入ったとき",
        "trigger": "新しい関注項が入ったとき（AI 編集）／ 手で「この版面の小元素を見て」と頼んだとき",
        "summary": "AI がするのは「何を集めるか決める」と「手で頼まれたときに一覧を目で見る」の 2 つだけ。集める・確かめる・選ぶ・切り抜くは"
                   "全部「小元素の自動補完」の規則（下の判断の一覧）で、AI は使わない。",
        "files": ["scripts/emblem_fill.py", "scripts/emblem_rules.py"], "doc": "TEMPLATES.md", "rules": "emblem",
        "uses": ["claude", "roster"],
        "flow": [
            {"id": "plan", "kind": "step", "lane": "ai", "title": "何を集めるか決める", "by": "ai",
             "text": "種類（emblem_kind）・名前（emblem_who）・代表作（emblem_examples）・分類（emblem_category）を items.yaml に書く", "uses": ["claude"]},
            {"id": "count", "kind": "step", "lane": "actions", "title": "主要な要素を数える（--roster）",
             "text": "分類の人数（AniList の番号があっても分類が先）→ なければ AniList の主役の人数 · 実写（emblem_people）は出演者の人数（作品の Wikidata P161 → wiki: の記事の作品の P161〔フランチャイズ〕→ 記事の「Cast」の節の「X as 役」〔wiki: がなければ Wikidata の英語の記事・役の中の <!-- --> は消す〕、役は emblem_roles へ・名字を足しただけの書き方〔Tenoch Huerta ＝ Tenoch Huerta Mejía〕は同じ人）→ emblem_pool（上限）· そろったキャラの版面も名簿の規則の版（NAMES_V、いま 7：Cast の節を Wikidata の記事からも・名字の足し書きは同じ人。6：Unnamed・集まりのページを数から外す）が上がったら 1 回数え直す（名簿が上限までそろっていても roster を呼ぶ：fill_one の _recount）（手がかり：Fandom・分類・AniList・Wikidata のどれか。分類があるのに数えられなかった〔429〕版面は次の回も）· 手で数えた人数（dota2 のヒーロー 126）があれば分類を探さない · 分類は作品の登場人物（Wikidata P674、wikihttp で引く）が 1 人は入っているものだけ（GTA 6 の wiki の Playable characters は GTA IV・V の主役 → 外してその分類の名前を名簿から抜き、Wikidata の wiki gta の Characters in GTA VI へ）· 手で数えた人数（dota2 のヒーロー 126）があれば、その ±10% の分類だけ（Characters 196 は×、Heroes 127 は○）· 名簿（emblem_who）にいない人・名前のない端役（Unnamed …）の小元素は外す（実写は除く）· 分類の中の集まりのページ（そのページの分類が Music bands・Gangs・Organizations など、emblem.groups）は名簿・前の名簿・人数（emblem_pool）から外す（GTA 6 の 39 → 27）", "uses": ["roster"]},
            {"id": "auto", "kind": "decision", "lane": "actions", "title": "自動補完で目標に届いた？",
             "text": "「小元素の自動補完」が規則だけで集める", "no": "失敗の理由と助言が管理ページに出る。手で頼まれたら下へ"},
            {"id": "pick", "kind": "step", "lane": "ai", "title": "一覧を目で見て番号を選ぶ（頼まれたときだけ）", "by": "ai",
             "text": "外した画像は emblem_reject に書く（二度と自動で選ばれない）", "uses": ["claude"]},
            {"id": "write", "kind": "store", "lane": "repo", "title": "items.yaml · docs/home/emblems/*.webp"},
        ],
    },
    {
        "id": "emblem-cron", "name": "小元素の自動補完", "en": "EMBLEM", "lane": "actions",
        "schedule": "gate", "when": "ゲートが仕事ありのとき · 6 本並列 · 3 段 · AI なし",
        "trigger": "後台のゲート（毎時・収集のあと）が「足りない版面がある」と判断したとき。GitHub Actions で Python だけで動く",
        "summary": "目標に届いていない版面の小元素を、足りない順に 4 本並列で埋める。前は Claude が目で見ていた判断（別人・遠景・集合写真・"
                   "切り抜きの穴・重複）は全部規則にしたので、AI は使わない。取れなかった版面は理由ごとに助言を出す。",
        "files": ["scripts/emblem_fill.py", "scripts/emblem.py", "scripts/face_id.py", "scripts/emblem_rules.py", ".github/workflows/background.yml"],
        "doc": "TEMPLATES.md", "rules": "emblem",
        "uses": ["roster", "rembg", "yunet", "sface", "facerule", "holes", "wiki", "wikiua", "httpcache", "fandom"],
        "flow": [
            {"id": "b1", "kind": "decision", "lane": "actions", "title": "ゲート：足りない版面がある？",
             "text": "目標未満 · 失敗した版面は「新しい記事・手がかりが来た」か「1 時間たった」（毎時の後台）ら対象に戻る",
             "uses": ["gate"], "no": "何もしない（Actions 20 秒で終わり）"},
            {"id": "b1f", "kind": "step", "lane": "actions", "title": "取り方を探す（キャラ）", "text": "名簿の上の 5 人（主役）は毎回先に、残りは回ごとに試す幅（STEP − 5）ずつずらす（名簿の全員に順に届く。STEP ずつだと 60 人の半分に届かなかった）· もう小元素のいる人は試さない（実写の「役（出演者）」は出演者の名前で見る）· emblem_fandom が空か開けない（gtawiki 404）なら名前・副題・搜索词の英語名から <名>.fandom.com を探す（wiki の名前に作品名が入っているときだけ）→ Wikidata の P4073（シリーズ P179 も、ライブラリと同じ）→ emblem_category が空なら ① 作品の名前の付いた分類（検索：Characters in GTA VI）② その作品の wiki のときだけ（wiki の名前か番号が作品名に入る：Bleach Wiki ○・Hello Kitty Wiki とぐでたま ×）分類 Main characters → Playable characters → Playable Characters → Characters（3 件以上）。AniList の番号があっても探す・手で書いた分類が先・実写は分類を使わない。名簿の順＝参照の数（emblem.category_top：分類は 200 人ずつ続きも 1000 人まで・参照は 500 ずつ続きも 2000 まで・分類の説明の記事「Character」と下位のページ「…/Storyline」は除く）。書いておく（find_sources、AI の設計が飛ばされても埋まる）",
             "uses": ["fandom"]},
            {"id": "b1r", "kind": "step", "lane": "actions", "title": "要る枚数を決める", "text": "上限 = 主要な要素の数（まだ数えていなければ先に --roster。「Secondary Characters」のようなまとめの記事は数えない）",
             "uses": ["roster"]},
            {"id": "b2", "kind": "step", "lane": "actions", "title": "準備", "text": "モデルはキャッシュから（初回だけダウンロード）",
             "uses": ["rembg", "yunet", "sface"]},
            {"id": "b2s", "kind": "table", "lane": "actions", "title": "取り方の段（同じ回の中で、届くまで上がる）",
             "rows": [("① 標準", "下の順（直接指定 → Fandom → Wikidata → Wikipedia → Commons → 記事の配図 → 公式サイト → Twemoji）"),
                      ("② 名前を広げる", "作品名をつけて全言語の Wikipedia・Commons（12 枚）· 記事 30 日分・要約にも名前 · Fandom の別のページ名"),
                      ("③ 公式・記事のページ", "公式サイトの画像（メンバー名のファイル）· 名前が出る記事の本文ページの og:image（8 本）· 人物は YouTube の動画の場面（字のない hq1〜3）")],
             "uses": ["youtube"]},
            {"id": "b3", "kind": "fan", "lane": "ext", "title": "① 標準で候補を集める", "x": "×6 版面を同時に", "mode": "上から順に · 足りるまで",
             "items": [("0", "直接指定", "公式の立ち絵"), ("0", "役の記事・作品の動画", "実写：役の姿（剧照）", "fandom"), ("1", "代表作", "主題の下の一段"), ("2", "AniList", "アニメの主役"),
                       ("3", "Fandom", "立ち絵 → 代表画像", "fandom"), ("4", "Wikidata", "P154・P18", "wiki"),
                       ("5", "Wikipedia", "≤10", "wiki"), ("6", "Commons", "≤8", "wiki"), ("7", "記事の配図", "≤12"),
                       ("8", "公式サイト", "ロゴ"), ("9", "Twemoji", "主題", "twemoji")],
             "uses": ["pace", "roles"]},
            {"id": "b3w", "kind": "step", "lane": "ext", "title": "Wikimedia は決まりどおりに取る",
             "text": "名乗った UA · 1 本ずつ · maxlag · Retry-After を待つ · 取ったものはキャッシュ（次の回も）",
             "uses": ["wikiua", "httpcache", "pace"]},
            {"id": "b4", "kind": "step", "lane": "actions", "title": "使える画像か", "text": "6MB まで · 短辺 160（横長ロゴは長辺 300）· 白紙・同じ画像を除く",
             "uses": ["ahash"]},
            {"id": "b5", "kind": "step", "lane": "actions", "title": "人物の写真の規則（前は目で見ていた）",
             "text": "顔なし・遠景・何人も・別人を数で外す（数は下の「判断の一覧 ④」）", "uses": ["yunet", "sface", "facerule"]},
            {"id": "b6", "kind": "decision", "lane": "actions", "title": "確かな取り方？", "text": "人物 = 規則を通った写真 · キャラ = 直接指定・Fandom · 主題 = Wikidata・Commons・Twemoji",
             "no": "理由をつけて外す（確かでない取り方・重複・目標を超える）"},
            {"id": "b7", "kind": "step", "lane": "repo", "title": "書いて切り抜く", "x": "1 枚ずつ（WRITE_LOCK）",
             "text": "検査で外れたら同じページの公式イラストで取り直す · 公式の立ち絵は全身で測ってから、ふつうの体つきだけ上半身に切る（どのキャラも体の同じところ。デフォルメ・マスコットは全身）· ロゴは地を抜いて切らない",
             "uses": ["rembg", "cutcheck", "holes", "facefit", "pose"]},
            {"id": "b8", "kind": "decision", "lane": "actions", "title": "目標に届いた？", "no": "次の段へ（② → ③）。全部だめなら失敗",
             "no_to": "b2s"},
            {"id": "b8f", "kind": "table", "lane": "actions", "title": "失敗したら・待っていたら",
             "rows": [("失敗（3 段とも届かない）", "新しい記事・手がかり（材料の指紋）が来たらすぐ、来なくても 1 時間後（毎時の後台）に再挑戦 · 管理ページに理由と助言"),
                      ("順番待ち", "毎時と収集のあとに 6 本並列で処理 · 40 分で終わらなければ続けてもう一度（3 回まで）"),
                      ("いま処理中", "版面と段（① ② ③）を live_status に書く → 管理ページ「いま動いているもの」に 30 秒ごと")]},
            {"id": "b8l", "kind": "step", "lane": "web", "title": "作業の 1 行 1 行をライブログへ",
             "text": "候補ごとに外した理由・段・結果を Supabase の live_log に（1.5 秒ごとにまとめて送る）→ 管理ページのライブログが 3 秒ごとに読む · 2 日より前の行は始めに消す · 「今すぐ再挑戦」から起きたときはそう書く",
             "uses": ["supabase"]},
            {"id": "b9", "kind": "store", "lane": "repo", "title": "items.yaml · docs/home/emblems · state/emblem_progress.json · state/log",
             "text": "変わったときだけコミット → ページ生成"},
        ],
    },
    {
        "id": "gate", "name": "後台のゲート", "en": "GATE", "lane": "actions", "workflow": "background.yml",
        "schedule": sorted([(h, m) for h in range(24) for m in (17, 47)] + [(0, 7), (9, 7)]),   # 17 分 = Supabase pg_cron、47 分 = GitHub の定時（抜けることがあるので 2 つの時計）、0:07 / 9:07 UTC = AI 編集の回（9:00 / 18:00 を過ぎてから。0 分ちょうどは GitHub が混む）
        "when": "毎時 · 収集のあとすぐ · 残れば続けて",
        "trigger": "毎時 17 分（Supabase pg_cron）と 47 分（GitHub の定時）・日本時間 9:07 / 18:07（AI 編集の回）／ ニュース収集が終わるたび（新しい材料）／ 時間の予算を使い切って仕事が残っていれば続けてもう一度（3 回まで）／ 管理ページの「今すぐ実行」・失敗した版面の「今すぐ再挑戦」（失敗の待ち時間を飛ばす）",
        "summary": "仕事があるか、AI が要るかをプログラムだけで決める。AI の要らない仕事（小元素）はその場で Python で済ませ、"
                   "AI が要る仕事（AI 編集・写真）は仕事があるときだけ Claude を起こす。Claude は起きるたびにトークンを使うので、空振りをなくす。"
                   "版面には AI が整理した記事しか載らないので、収集で整理待ちが増えたらすぐ AI 編集を起こす（リポジトリ変数 GATE_FIRE で開け閉め）。",
        "files": ["scripts/gate.py", "scripts/collect_watch.py", "scripts/library_watch.py", ".github/workflows/background.yml", "state/gate.json"], "doc": "docs/rules/background.md", "uses": ["gate"],
        "flow": [
            {"id": "g1", "kind": "fan", "lane": "actions", "title": "仕事を調べる", "mode": "全部を毎回",
             "items": [("1", "小元素", "目標未満の版面（1 時間以内の失敗で材料が同じものは除く）"), ("2", "AI 編集", "今日の inbox の整理待ち（_covered より後・edit.json にない版面）"),
                       ("3", "写真", "inbox/photos/*.json")]},
            {"id": "g1c", "kind": "decision", "lane": "actions", "title": "最後の収集から 150 分たった？", "text": "state/log/collect.json · GitHub の定時（17 */2）は抜けることがある · この段は pg_cron で毎時必ず通る（判断の段より前：判断が落ちてもここは通る）",
             "uses": ["collectwatch"], "yes": "収集の回が走っていない・並んでいない・60 分以内に始まっていなければ digest.yml を起こす（workflow_dispatch）。起こせなかったら記録して管理ページへ", "no": "何もしない"},
            {"id": "g1l", "kind": "decision", "lane": "actions", "title": "ライブラリの最後の回から 80 分たった？", "text": "library.yml の成功した回（gh run list）· 毎時 41 分の定時は抜けることがある（2026-10-24 00:41 は来なかった）",
             "uses": ["libwatch"], "yes": "走っていない・並んでいない・30 分以内に始まっていなければ library.yml を users_only で起こす（お客さまの選んだもの → follows）", "no": "何もしない"},
            {"id": "g2", "kind": "decision", "lane": "actions", "title": "小元素の仕事がある？", "no": "飛ばす"},
            {"id": "g3", "kind": "step", "lane": "actions", "title": "その場で Python で埋める", "x": "AI なし · 6 本並列", "text": "「小元素の自動補完」· 失敗しても次の段（AI 編集を起こす・提交）へ進む（continue-on-error）· items.yaml は一時ファイルから置き換える · 提交の前に items.yaml が読めなければ書き込みを戻す · 落ちた回は続けて起こし直さない · items.yaml を変えた回は library.yml を users_only で起こす（bot の push では起きない：ライブラリの店長の版面の写しを新しく）"},
            {"id": "g4", "kind": "decision", "lane": "actions", "title": "AI が要る仕事がある？", "text": "AI 編集・写真", "no": "Claude は起こさない（トークン 0）"},
            {"id": "g4r", "kind": "decision", "lane": "actions", "title": "溜まった版面がある？", "text": "整理待ち 3 件以上 · いちばん古いものが 2 時間 · 初めての版面（前の 3 日の edit.json にない）· 今日のトークンが 100 万未満",
             "uses": ["gate"], "no": "起こさない（溜まるか 2 時間たつのを待つ・上限なら明日）"},
            {"id": "g5", "kind": "decision", "lane": "actions", "title": "前に起こしてから 60 分たった？", "text": "起こした直後は編集中のはず。重ねて起こさない · 新関注項の「すぐ AI 編集」がここで止まったら頼み（now_pending）を残す",
             "uses": ["gate"], "no": "待つ（管理ページ：編集中のはず）· すぐの頼みは残して、60 分たった後台作業が定時を待たずに起こす"},
            {"id": "g5d", "kind": "decision", "lane": "actions", "title": "起こしたのは今日（北京時間）？", "text": "編集済みの数は日付が変わると 0 から数え直す · 起こした日を fired.day に残す（ない古い記録は起こした時刻から）",
             "uses": ["gate"], "no": "前の日の記録とは比べない（停滞と数えない）→ ↓ 9:00 / 18:00 の回の確認へ（夜中に起こさない）"},
            {"id": "g5b", "kind": "decision", "lane": "actions", "title": "起こしたあと編集済みの数（_covered の合計）が増えた？",
             "text": "API が 200 を返しただけでは「動いた」とは言わない · 増えていなければ停滞 · 返事の id も記録（resp）· 管理ページの「動いている」は今回起こしたあとの最後のバッチ（state/log/edit.json）から 30 分以内だけ、過ぎたら「前回 HH:MM に終わった・次は HH:MM」（今の回がまだなら「まもなく」・残り時間は網页が数える）· 起こしたあとバッチがないまま 60 分 → 「出刊されていない」（最後の失敗の行つき）",
             "uses": ["gate"], "yes": "動いている → 残りがあれば新しい状況として起こす", "no": "停滞：3 回まで起こし直す・そのあと 6 時間待つ（管理ページに「起こしても動かない」）"},
            {"id": "g5c", "kind": "decision", "lane": "actions", "title": "GATE_FIRE で開けている？", "text": "リポジトリ変数 · 未設定 = edit（AI 編集だけ・既定）· 0 = 閉 · 1 = 全部 · 管理ページの「AI 編集をもう一度起こす」は変数・間隔・停滞の判断を飛ばす",
             "no": "起こさない（記録だけ・定時を待つ）"},
            {"id": "g6", "kind": "step", "lane": "ai", "title": "Claude の定時タスクを API で起こす", "text": "定時タスクごとのトークン（Secret ROUTINE_FIRE_TOKEN など）が要る · AI 編集は溜まった版面だけ編集する（edit-queue = edit_ripe ＋ やり直し）",
             "uses": ["claude"]},
            {"id": "g7", "kind": "store", "lane": "repo", "title": "state/gate.json · state/log/gate.json", "text": "判断が変わったとき（最初の判断・小元素のあとの判断）・Claude を本当に起こしたとき・収集を起こそうとしたとき（起こせなかったときも）だけコミット（GATE_FIRE が開いているだけでは足さない）"},
        ],
    },
    {
        "id": "collect", "name": "ニュース収集", "en": "COLLECT", "lane": "actions",
        "schedule": [(h, 17) for h in range(0, 24, 2)], "workflow": "digest.yml", "when": "2 時間ごと · 関注清单・愿望清单を変えた合併のとき（コードだけの合併では集めない、網页は render.yml）· 6 本並列",
        "trigger": "2 時間ごと（日本時間 奇数時 17 分）／ 定時が抜けて 150 分あいたら後台のゲートが起こす（collect_watch）／ 毎週月曜 9:47 に周報",
        "summary": "関注項ごとにニュース・SNS・価格を集めて inbox に溜め、出刊・通知・ページ生成までつなぐ。",
        "files": [".github/workflows/digest.yml", "scripts/digest.py", "scripts/sources.py", "scripts/intel.py", "intel/japan.yaml", "scripts/userfeed.py", "db/user_boards.sql"], "doc": "README.md",
        "uses": ["gnews", "bing", "reddit", "steam", "gdelt", "youtube", "bluesky", "mastodon", "intel", "dedupe", "spam", "srcfilter", "match", "userfeed"],
        "flow": [
            {"id": "c1", "kind": "step", "lane": "actions", "title": "起動", "text": "Ubuntu 4 コア · 40 分まで · 同時に 1 本 · 前の回に時間切れで残った版面・初めて取る版面（新関注項）を先に取る"},
            {"id": "c1d", "kind": "decision", "lane": "actions", "title": "始めてから 18 分たっていない？", "text": "版面ごとに、取り始める前に見る（COLLECT_DEADLINE_MIN）· 始まった版面が 23 分たっても終わらなければ待たずに先へ（固まった版面も次の回へ。そのスレッドがあとで終わっても帯は立て直さない・情報員の様子は写しを読む）",
             "uses": ["deadline"], "yes": "↓ その版面を取る", "no": "その版面は始めない → 次の回に先に取る（ログ「時間切れで N 版面を次の回へ」）"},
            {"id": "c2", "kind": "fan", "lane": "ext", "title": "記事を集める", "x": "×6 関注項を同時に", "mode": "それぞれのサイトへ",
             "items": [("G", "Google ニュース", "5 言語", "gnews"), ("B", "Bing ニュース", "3 回まで", "bing"),
                       ("R", "Reddit", "25 件", "reddit"), ("S", "Steam", "10 件", "steam"), ("F", "RSS", "feeds"),
                       ("D", "GDELT", "各国 · 5 秒に 1 回", "gdelt"), ("Y", "YouTube 公式", "15 本", "youtube"),
                       ("BS", "Bluesky", "人気順", "bluesky"), ("M", "Mastodon", "#タグ", "mastodon"),
                       ("J", "日本の情報員", "専門サイト 17 本 · 1 回だけ", "intel")],
             "uses": ["pace"]},
            {"id": "c2e", "kind": "decision", "lane": "actions", "title": "その版面の取得・処理で例外が出なかった？", "text": "取得（並列）と、そのあとの順番の処理（去重・match の正規表現・状態・封面）",
             "uses": ["deadline"],
             "no": "その版面だけ空にして続ける（途中で書いた状態は戻す・ログ「取得・処理に失敗した N 版面は空で続けた」）· 収集全体は止めない"},
            {"id": "c3", "kind": "step", "lane": "actions", "title": "重複を落とす", "x": "元の順番で", "uses": ["dedupe"]},
            {"id": "c3s", "kind": "decision", "lane": "actions", "title": "スパム・止めた来源ではない？", "text": "成人・海賊版の「在线看」ページ · 出典名（前方一致）· 網域（クラファン・攻略 wiki の攻略頁）",
             "uses": ["spam", "srcfilter"], "no": "捨てる"},
            {"id": "c4", "kind": "step", "lane": "actions", "title": "その作品の記事か", "uses": ["match"]},
            {"id": "c4r", "kind": "decision", "lane": "actions", "title": "Reddit の帖子は火？", "text": "今週の人気の上位 5（API があれば 赞 100・评论 30）",
             "no": "版面に載せず帖子数だけ数える（reddit_cold）", "uses": ["reddithot"]},
            {"id": "c5", "kind": "decision", "lane": "actions", "title": "新しい記事・状態の変化がある？", "no": "その関注項は書かない"},
            {"id": "c6", "kind": "step", "lane": "ext", "title": "いまの状態", "text": "価格・放送・状態の変化", "uses": ["steam", "anilist", "tmdb"]},
            {"id": "c7", "kind": "store", "lane": "repo", "title": "inbox/日付.json", "text": "1 関注項 30 件・Reddit 10 件まで"},
            {"id": "c7c", "kind": "decision", "lane": "actions", "title": "前の日の整理待ちが残っている？", "text": "その日の最初の 1 回だけ（_carried）· 2 日前まで · _covered より後・要紧でないもの · 前の日に持ち越した記事（carried）はもう持ち越さない · 今日と前の 3 日の reports に載った記事（同じ網址・同じ見出し。持ち越す側だけ媒体名を除いた形も、12 字・6 割以上残るときは比べる）は除く · 1 版面 篇幅 × 2 件（S 6・M 10・L 16、新しいほうから）",
             "yes": "今日の inbox に持ち越す（AI 編集は最新の日しか見ないので、JST 18:00 のあと〜1:00 の分が消えないように）", "no": "そのまま"},
            {"id": "c8", "kind": "step", "lane": "actions", "title": "話題度の数字・Supabase に控え", "uses": ["wikipv", "supabase"]},
            {"id": "c9a", "kind": "decision", "lane": "actions", "title": "AI 編集が整理した記事？", "text": "edit.json にある版面の _covered まで",
             "yes": "版面に載せる", "no": "↓ 要紧か見る"},
            {"id": "c9b", "kind": "decision", "lane": "actions", "title": "要紧の記事？", "text": "urgent_patterns に当たる",
             "uses": ["urgent", "fallback"], "yes": "すぐ「重大」で載せる＋Discord", "no": "版面の下の「整理待ち N 件」（折りたたみ・原題だけ）"},
            {"id": "c9", "kind": "step", "lane": "actions", "title": "出刊 → 通知 → push", "text": "push に失敗したら 3 回まで取り直す · 網页の生成に失敗してもデータは push（WL_RENDER_SOFT、次の生成で作り直す）· このあとゲートが AI 編集を起こす",
             "uses": ["pending", "discord"]},
            {"id": "c10", "kind": "step", "lane": "actions", "title": "お客さまの版面を集める", "x": "×4 · 8 分まで",
             "text": "一度はログインした人だけ · 選んだもののうち店長のページに版面がないものだけ（店長にあるものは店長の版面を見せる）· 1 人 1 回 10 版面・全員の 1 つ目から · ログは数だけ · 同じ規則で集めて Supabase の user_boards に本人の account で · 前の段が失敗しても走る・失敗しても止めない（continue-on-error）· job の timeout の 3 分前に締め切る · 様子はライブログへ",
             "uses": ["userfeed", "gnews", "bing", "intel", "match", "spam", "fallback", "lang", "supabase"]},
            {"id": "c10m", "kind": "step", "lane": "actions", "title": "お客さまの記事に写真と原文の網址", "x": "×4 · 150 秒",
             "text": "Google の跳转を原文に（sources.resolve_url を 1 回）· 1 版面の記事に新しい順で店長と同じ images.pick（1 本 20 秒、見つからなければ 3 時間あけて探し直す・3 回〔img_n〕で諦める）· 期限付きの網址（?exp=）の写真は 6 時間ごとに開けるか確かめ、開けなければ探し直す · 今回は探さなかった版面のまだのものも · 写真のある記事が頭条（ポスター）・ほかの注目ニュースに上がる",
             "uses": ["userfeed", "imgpick", "supabase"]},
            {"id": "c11", "kind": "step", "lane": "actions", "title": "お客さまのページを作る", "x": "別の job · 12 分まで",
             "text": "収集の job のあと（失敗しても）· 店長と同じ render.render で 1 人 1 ページ（頭条の黄色の帯・版面の主題・配色・小元素・目次）· 店長と同じ名前の版面は店長の設定と最新号の版面、ほかは user_boards の記事・種類から主題・写真から配色 · 写真は images.pick（1 版面 3 本・合わせて 240 秒）· Supabase Storage の非公開の箱 pages/<account>/index.html（本人と店長だけが読める）· 網页はログインした本人の鍵で読んで替える · ログは数だけ",
             "uses": ["userpages", "imgpick", "supabase"]},
        ],
    },
    {
        "id": "heat", "name": "話題度", "en": "HEAT", "lane": "actions", "when": "収集のたびに数字 · ページ生成で計算",
        "trigger": "数字は収集のとき（1 日 1 回）、点数はページを作るとき（ネットに出ない）",
        "summary": "作品ごとの盛り上がりを 0〜100 で出す。6 つの次元を、自分の平常と比べた分と共通の尺度で混ぜる。",
        "files": ["scripts/heat.py", "state/heat_signals.json"], "doc": "docs/rules/design.md", "uses": ["heat", "wikipv", "wikiua", "steam", "anilist", "tmdb"],
        "flow": [
            {"id": "h1", "kind": "fan", "lane": "ext", "title": "外の数字を取る", "mode": "1 日 1 回 · 70 日分残す",
             "items": [("W", "Wikipedia 閲覧数", "60 日", "wikipv"), ("S", "Steam 同時接続", "", "steam"),
                       ("A", "AniList 人気", "", "anilist"), ("T", "TMDB 人気", "", "tmdb")]},
            {"id": "h2", "kind": "store", "lane": "repo", "title": "state/heat_signals.json"},
            {"id": "h3", "kind": "table", "lane": "actions", "title": "6 つの次元（重み）",
             "rows": [("報道量 20", "記事数（新しいほど重い）"), ("広がり 15", "媒体 × 地域"), ("出来事 20", "要紧・状態の変化・予定"),
                      ("勢い 15", "直近 2 日 ÷ その前 5 日"), ("一般の関心 20", "Wikipedia 閲覧数"), ("ファン 10", "Reddit・Steam・AniList・TMDB")]},
            {"id": "h4", "kind": "step", "lane": "actions", "title": "各次元 = 60% 自分比 + 40% 共通の尺度",
             "text": "自分比 = 50 + 25·log2((今+1)/(平常 4 週+1)) · 共通 = 100·log10(1+x)/log10(1+満点線)", "uses": ["heat"]},
            {"id": "h5", "kind": "decision", "lane": "actions", "title": "その次元の数字が取れた？", "no": "0 点ではなく分母から外す"},
            {"id": "h6", "kind": "table", "lane": "web", "title": "等級", "rows": [("≥85", "沸騰"), ("≥60", "盛り上がり"), ("≥30", "話題"), ("≥1", "静か")]},
            {"id": "h7", "kind": "step", "lane": "web", "title": "版面の数字・ランキング・分析ページ"},
        ],
    },
    {
        "id": "notify", "name": "Discord 通知", "en": "NOTIFY", "lane": "actions", "when": "収集のあと · 月曜に周報",
        "trigger": "収集のたび（要紧・変更・愿望・新関注項）／ 毎週月曜 9:47 に周報",
        "summary": "要紧の記事は当日、ほかは周報で。同じものは 30 日のあいだ二重に送らない。",
        "files": ["scripts/notify.py", "state/notified.json"], "doc": "README.md", "uses": ["urgent", "discord"],
        "flow": [
            {"id": "n1", "kind": "decision", "lane": "actions", "title": "要紧の記事・状態の変化がある？", "text": "直近 2 回の収集から",
             "uses": ["urgent"], "no": "周報まで待つ"},
            {"id": "n2", "kind": "decision", "lane": "repo", "title": "30 日以内に送っていない？", "text": "state/notified.json", "no": "送らない"},
            {"id": "n3", "kind": "step", "lane": "ext", "title": "Discord に送る", "text": "6 行・埋め込み 10 まで · メンション", "uses": ["discord"]},
            {"id": "n4", "kind": "table", "lane": "ext", "title": "ほかに送るもの",
             "rows": [("機能の更新", "機能のコミット"), ("愿望清单", "新しい愿望 10 件まで"), ("新関注項", "増えた・減った"), ("周報", "月曜・直近 7 日 · 1 通 embed 10 個・5,800 字までに分けて送る · 送れなかったら心拍に「发送失败」")]},
        ],
    },
    {
        "id": "edit", "name": "AI 編集", "en": "EDIT", "lane": "ai",
        "schedule": [(0, 0), (9, 0)],   # 日本時間 9:00 / 18:00（ユーザーが決めた）。ゲート（gate.SLOTS）が整理待ちがあるときだけ起こす
        "when": "版面に整理待ちが溜まったら（収集のあと・後台作業）",
        "trigger": "版面ごとに整理待ちが 3 件以上・いちばん古いものが 2 時間・初めての版面になったら、収集のあと（digest.yml）と後台作業（毎時）のゲートが起こす（9:00・18:00 は待たない・1 日のトークン上限 100 万）（動かなければ 60 分あけて起こし直す）／ 管理ページの「今すぐ実行」「AI 編集をもう一度起こす」でいつでも ／ 新しい関注項が入ったとき（収集のあと、ゲート経由 GATE_NOW：1 日 2 回の定時だけ飛ばし、編集中〔60 分以内に起こし済み〕・停滞・一時停止・GATE_FIRE は守り、起こしたことを記録）",
        "summary": "inbox の記事から重要なものを選び、同じ件を合わせて（言語違いは主言語の 1 本に）、見出しと配図を決めて出刊する。新しい関注項は版面も設計する。"
                   "版面に載るのは AI 編集が整理した記事だけ（それまでは「整理待ち」、要紧だけ先に載る）。",
        "files": ["EDITING.md", "scripts/digest.py", "scripts/lang.py", "TEMPLATES.md"], "doc": "EDITING.md", "uses": ["claude", "imgpick", "pending", "lang"],
        "flow": [
            {"id": "e1", "kind": "step", "lane": "ai", "title": "最新の inbox を読む"},
            {"id": "e2", "kind": "decision", "lane": "ai", "title": "今日の整理待ちがある？", "text": "_covered より後の記事・edit.json にない版面", "no": "何も変えずに終わり"},
            {"id": "e3", "kind": "step", "lane": "ai", "title": "版面の設計・小元素", "by": "ai", "text": "motif・theme・like_fx · 足りない小元素（「小元素の選定」）"},
            {"id": "e3q", "kind": "decision", "lane": "actions", "title": "次の版面は？ edit-next", "text": "管理ページの開関（edit_control）：一時停止 → 止める · 1 版面ずつで 1 つ済 → 止めて pause に · 設定ページで足して設計（motif・theme）がまだの関注項があれば DESIGN（設計が終わるまで記事の編集に進まない）· やり直しの版面が最初、あとは整理待ちの多い順に 1 版面（規則・トークン 0）",
             "uses": ["batch"], "no": "止める（一時停止・1 版面ずつ・全部済）"},
            {"id": "e4", "kind": "step", "lane": "ai", "title": "編集して edit.json（この版面だけ・短い一覧 edit-brief を読む）", "text": "一覧は規則で出来事ごとに束ねてある · 前回のあとは増えた束だけ（今の記事は残して refs に足す）· 同じ件を合わせる（言語違いも 1 本・主言語の原題）· 見出しは原文 · S 3 / M 5 / L 8 件",
             "uses": ["bundle", "claude"]},
            {"id": "e5", "kind": "step", "lane": "ai", "title": "配図を目で選ぶ（重大・頭だけ）", "text": "1 件 8 枚まで · 270×180 の 4 列 ≈ 570 トークン · 普通の記事は規則（images.pick）", "uses": ["imgpick", "claude"]},
            {"id": "e6", "kind": "step", "lane": "actions", "title": "出刊 publish", "text": "AI のあとに来た新着は「整理待ち」（要紧だけ先に重大）", "uses": ["pending", "fallback"]},
            {"id": "e6l", "kind": "decision", "lane": "actions", "title": "言語違いの同じニュース？", "text": "バージョン番号・月日・予定の日付が同じ · 10 日以内",
             "yes": "主言語（ja）の 1 本にまとめる", "no": "そのまま", "uses": ["lang"]},
            {"id": "e6r", "kind": "decision", "lane": "actions", "title": "載っている Reddit 帖子は生きていて火？", "text": "1 日 1 回 · 直近 8 日",
             "no": "版面から撤去", "uses": ["reddithot"]},
            {"id": "e7", "kind": "store", "lane": "repo", "title": "inbox/*.edit.json · reports/", "text": "バッチごとに push → 1〜2 分でその版面だけ網页に · 使ったトークンを state/log/edit.json に（usage.py・本物の数字）"},
            {"id": "e8", "kind": "step", "lane": "ai", "title": "↑ edit-next に戻る", "text": "1 版面ごとに push → 1〜2 分でその版面だけ網页に · 使ったトークンを記録 · この出刊の時刻が「最後のバッチ」（管理ページの「動いている」は 30 分以内だけ・ゲートの gate.last_batch）"},
        ],
    },
    {
        "id": "images", "name": "記事の配図", "en": "IMAGES", "lane": "actions", "when": "出刊のたび",
        "trigger": "出刊のとき（1 件ずつ）。AI 編集は候補の一覧を見て選ぶ",
        "summary": "記事ごとに、顔や内容が切れない 1 枚を選ぶ。号の中で同じ画像は使わない。",
        "files": ["scripts/images.py", "scripts/hdimg.py", "scripts/digest.py", "state/hdimg.json"], "doc": "EDITING.md", "uses": ["imgpick", "imgsharp", "imgsibling", "scrapling", "keyimg", "hdimg"],
        "flow": [
            {"id": "i1", "kind": "fan", "lane": "ext", "title": "候補の順", "mode": "上から順に · 1 件 60 秒・12 枚まで",
             "items": [("1", "AI の指定", ""), ("2", "記事の画像", "Bing の縮小画像は除く"), ("3", "og:image", ""), ("4", "JSON-LD", ""),
                       ("5", "動画の表紙", "<video poster>"),
                       ("6", "本文の img", "6 枚"), ("7", "Bing の縮小画像", "Bing が切った一部分"),
                       ("8", "同じ出来事の別のサイトの記事", "4 本まで", "imgsibling"), ("9", "転載ページ", "Bing 8 · Google · 引用された原題でも", "imgsibling")]},
            {"id": "i1s", "kind": "decision", "lane": "ext", "title": "記事の頁・画像が拒まれた？", "text": "202/401/403/405/429/503 か確認画面（Cloudflare・captcha・人機検証）",
             "yes": "① scrapling Fetcher で取り直す → まだ拒まれた頁は ② 本物のブラウザ（Actions・10 頁・180 秒まで・1 頁 45 秒で打ち切り・失敗した頁は 1 日休む）· 取り直しでしか取れない画像は本站に保存", "no": "そのまま", "uses": ["scrapling"]},
            {"id": "i1k", "kind": "step", "lane": "actions", "title": "正文図は代表の 1 枚を点数で", "text": "6 枚まで確かめ、大きい・カードの形・記事の上のほう", "uses": ["keyimg"]},
            {"id": "i2", "kind": "step", "lane": "actions", "title": "検査", "text": "8MB まで · 短辺 200 · 長辺 300 · Pillow で開ける · ロゴ・サイトの占位図（default_image など）を除く",
             "uses": ["imgpick"]},
            {"id": "i2b", "kind": "decision", "lane": "actions", "title": "予告画像が小さい？", "text": "長辺 < 1000",
             "no": "そのまま", "uses": ["imgsharp"]},
            {"id": "i2c", "kind": "step", "lane": "ext", "title": "同じページの大きい版を先に", "text": "og:image → JSON-LD", "uses": ["imgsharp"]},
            {"id": "i3", "kind": "decision", "lane": "actions", "title": "見つかった？", "no": "403 の原文の図を Referer つきで再試行 → だめなら作品の表紙",
             "uses": ["imgsharp"]},
            {"id": "i4", "kind": "step", "lane": "actions", "title": "号の中で同じ画像を使わない", "text": "海外の出所を先に"},
            {"id": "i4r", "kind": "decision", "lane": "actions", "title": "図なしの記事が直近 8 日にある？", "text": "出刊のたび · 同じ記事は 6 時間おき · 1 回 6 件",
             "no": "何もしない", "uses": ["imgsibling"]},
            {"id": "i4b", "kind": "decision", "lane": "actions", "title": "看不清？",
             "text": "1.6 倍以上に引き伸ばす かつ 表示サイズで模糊度 > 0.42 · Bing の 100×100 · Referer が要る図 · 期限付きの網址（?exp=）", "no": "元の網址のまま（何もしない）", "uses": ["hdimg"]},
            {"id": "i4c", "kind": "fan", "lane": "actions", "title": "OpenCV で高清化", "mode": "順に · ×6 並列",
             "items": [("1", "ノイズ除去", "NLMeans h=3"), ("2", "拡大", "Lanczos4 · 最大 3 倍"), ("3", "シャープ", "輝度だけ USM 0.7")],
             "uses": ["hdimg"]},
            {"id": "i4d", "kind": "store", "lane": "repo", "title": "docs/home/pics/*.webp · state/hdimg.json", "text": "8 日を過ぎたら消す"},
            {"id": "i5", "kind": "step", "lane": "web", "title": "枠にはめる", "text": "本站の高清版 → 元の網址 → 表紙", "uses": ["fit"]},
        ],
    },
    {
        "id": "colors", "name": "トップの配色", "en": "COLORS", "lane": "actions", "when": "ページ生成のたび",
        "trigger": "ページを作るとき。同じ画像の色は state/themes.json に残して使い回す",
        "summary": "その日の頭条の写真から、トップの地色と強調色を取る。字が必ず読めるように明るさを直す。",
        "files": ["scripts/theme.py", "scripts/render.py", "state/themes.json"], "doc": "docs/rules/design.md", "uses": ["octree"],
        "flow": [
            {"id": "t1", "kind": "step", "lane": "actions", "title": "頭条の写真", "text": "200×200 に縮める"},
            {"id": "t2", "kind": "decision", "lane": "repo", "title": "前に取った色がない？", "text": "state/themes.json の hero|URL", "no": "それを使う"},
            {"id": "t3", "kind": "step", "lane": "actions", "title": "16 色に減らす", "uses": ["octree"]},
            {"id": "t4", "kind": "table", "lane": "actions", "title": "色の決め方",
             "rows": [("地色", "いちばん多い色 · 明るさ 0.11 か 0.93"), ("強調色", "彩度^1.5 ×（0.5 + 0.5√割合）が最大")]},
            {"id": "t5", "kind": "step", "lane": "actions", "title": "読めるまで明るさを動かす", "text": "±0.04 ずつ · WCAG 4.5:1"},
        ],
    },
    {
        "id": "recommend", "name": "おすすめ", "en": "RECOMMEND", "lane": "actions", "when": "収集のたび",
        "trigger": "収集のたび（新しい候補を探すのは 12 時間ごと）",
        "summary": "👍👎 から好みを学び、関注項の外も探して「気になるかも？」に出す。同じ話はまとめる。",
        "files": ["scripts/digest.py", "state/recommend.json"], "doc": "docs/rules/design.md", "uses": ["taste", "storydedupe", "gnews", "spam", "srcfilter"],
        "flow": [
            {"id": "r1", "kind": "step", "lane": "web", "title": "👍👎 を読む", "text": "記事ごとに最後の一票", "uses": ["supabase"]},
            {"id": "r2", "kind": "step", "lane": "actions", "title": "好みを学ぶ", "uses": ["taste"]},
            {"id": "r3", "kind": "step", "lane": "ext", "title": "外を探す", "x": "6 本 · 20 件ずつ", "text": "ランダムな種 · 好みの重み", "uses": ["gnews"]},
            {"id": "r3s", "kind": "decision", "lane": "actions", "title": "スパム・止めた来源ではない？", "text": "出典名（前方一致）· 網域（settings の exclude_hosts）",
             "uses": ["spam", "srcfilter"], "no": "候補にしない"},
            {"id": "r4", "kind": "step", "lane": "actions", "title": "同じ話をまとめる", "uses": ["storydedupe"]},
            {"id": "r5", "kind": "decision", "lane": "actions", "title": "点数 ≥ 5？", "text": "好みの語 2 点 · 同じ作品 +1", "no": "出さない（探索枠は ≥4）"},
            {"id": "r6", "kind": "store", "lane": "repo", "title": "state/recommend.json", "text": "5 件 × 6 組"},
        ],
    },
    {
        "id": "progress", "name": "進み具合を Discord へ", "en": "PROGRESS", "lane": "actions", "workflow": "progress.yml", "when": "合併したとき（画面の更新あり／なし・本番で新しくなったら「🟢 公開を確かめました」、2026-10-25）（Before / After は変わった所を赤い枠で囲む：24px のマスで比べ、隣どうしをまとめる）· 会話の Claude が選んでもらう質問を出したら ask_remind.yml（cmd=ask）が @ 付きで知らせ、返事がなければ最初の 1 時間は 5 分おき・そのあと 30 分おき・夜（日本時間 0〜8 時）は休む。答えたら cmd=clear。2 時間ごとの 30 字の報告は cmd=say（2026-10-24） · 画面に関わる PR の合併は Before（合併の直後の本番）と After（render.yml のあと）を撮って左右に並べた画像を送る（harness/before_after.py：ログインなし 1400・test-a 1400・390）",
        "trigger": "pull_request（opened・closed で merged）・main の BACKLOG.md への push・后台作業／ライブラリの小元素／关注清单通信の回が終わったとき＋30 分ごと（後で撮る After：bot が起こした回の終わりでは workflow_run が起きないため）",
        "summary": "何時に何ができたか・どこが変わったかを Discord で知らせる（2026-10-23）。ハーネスのループが PR を出す・合併する・一覧を更新するたびに届く。",
        "files": [".github/workflows/progress.yml", "scripts/progress_notify.py", "harness/before_after.py", "harness/claims.py", ".github/workflows/ask_remind.yml", "harness/ask_remind.py"], "doc": "HARNESS.md", "uses": ["discord"],
        "flow": [
            {"id": "pg1", "kind": "step", "lane": "actions", "title": "PR を出した／合併した", "text": "題名・本文の最初の 4 行・変えたファイル数・リンク・日本時間"},
            {"id": "pg2", "kind": "step", "lane": "actions", "title": "一覧（BACKLOG.md）の前と今を比べる", "text": "[~] の持ち主（持ち主 係の名前・最終 時刻）が動いていない・60 分たったものは harness/claims.py が「持ち主のいない」と数え、次の係が取り直す（2026-10-25）· 済み [x]・あなた待ち [?]・進行中 [~]・足した段（1 回 10 件まで）"},
            {"id": "pg3", "kind": "step", "lane": "ext", "title": "Discord に送る", "uses": ["discord"], "text": "速報・週報と同じ Webhook"},
            {"id": "pg4", "kind": "step", "lane": "actions", "title": "画面の更新あり／なし・公開を確かめる", "text": "合併の知らせに「画面の更新：なし（文書・点検の道具だけ）／あり」（progress_notify.page_effect）。ありのときは before_after.py が render.yml を待ち（回が 3 分見つからなければ待たない）、本番の version.json の指紋が変わったページの HTML の wl-ver が同じになるまで・直接変えた docs/ のファイルが倉庫と同じになるまで 20 秒おき 6 分まで確かめて「🟢 公開を確かめました：新しくなったページ」を送る（2026-10-25）", "uses": ["discord"]},
            {"id": "pg5", "kind": "step", "lane": "actions", "title": "何が変わったか一目で（切り抜き・差 0 は写真なし）", "text": "撮る場所は PR の説明の「画面：<ページ> <セレクタ> — <どこを見る>」（その欄だけ切り抜き・img の数の前→後）、なければページ全体 8000px まで比べて変わった一番大きい所を真ん中に切り抜く。乱数は決まった種・動きは止める。差がなければ写真なしで「画面の変化なし」。小元素・名簿・記事集め・AI 編集の PR（LATER）は Before を artifact ba-pending-<番号> に置き、その回が終わったら（workflow_run、bot が起こした回では起きないので 30 分ごとの見回りで最後に成功した回も見る）After を撮って送る、2 日で諦める。高さが変わったページは大きい方に合わせて灰色で埋めて比べ、両方にある所の変化を真ん中に。切り抜きに入りきらない変化（行が増えて下が全部ずれた）は変わり始めを上に。欄が前か後にしかない＝新しい欄・消えた欄は「ない」と比べて送り、前も後も撮れなければ「変化なし」と言わず「撮れませんでした」。後で撮る After は成功した回のあとだけ（workflow_run の conclusion・見回りの status=success）、取れない artifact が 1 つあってもほかは続ける（2026-10-25）", "uses": ["discord"]},
        ],
    },
    {
        "id": "library", "name": "ライブラリへ写す", "en": "LIBRARY", "lane": "actions", "workflow": "library.yml", "when": "items.yaml が変わったとき（後台作業の bot の push では起きないので、items.yaml を変えた後台作業の回が起こす）· 1 時間ごと（毎時 41 分、お客さまの版面。抜けたら後台作業が起こす）· 週 1 回（月曜 12:41 JST、番号の引き直し）· 手でも",
        "trigger": "main の items.yaml・scripts/library.py が変わったとき、1 時間ごと（毎時 41 分）、週 1 回の定時（月曜 3:41 UTC）、手で起こす、または定時が抜けて 80 分あいたら後台のゲートが users_only で起こす（library_watch）",
        "summary": "みんなの版面の置き場（ライブラリ：Supabase の boards・follows）へ、店長の版面を写す。記事集め・AI 編集・デザインを版面ごとに 1 回にし、店長もお客さまも同じ版面を受け取るための土台（2026-10-23）。",
        "files": [".github/workflows/library.yml", "scripts/library.py", "db/library.sql"], "doc": "docs/rules/library.md", "uses": ["supabase"],
        "flow": [
            {"id": "lb1", "kind": "step", "lane": "actions", "title": "items.yaml を読む", "text": "店長の版面 1 つずつ"},
            {"id": "lb2", "kind": "step", "lane": "actions", "title": "同じものかどうかの印", "text": "Wikidata の番号（wd:Q…）／なければ名前をそろえたもの（全角半角・大小・空白・記号）"},
            {"id": "lb2r", "kind": "decision", "lane": "actions", "title": "週 1 回の定時・手で起こした回？", "text": "items.yaml が変わっただけの回・後台の控えの時計が users_only で起こした回は引き直さない",
             "no": "番号はそのまま（lb2 へ）"},
            {"id": "lb2w", "kind": "step", "lane": "ext", "title": "番号のない版面の Wikidata を規則で引き直す（library.refresh → find_wikidata）",
             "x": "1 版面ずつ · 間 1 秒",
             "text": "お客さまの版面と同じ 1 つの規則（lb6 の ②）。候補 = Wikipedia の記事名（wiki）を書いた版面はその記事の項目だけ／書いていなければ名前・検索語（3 つまで）で検索して名前・別名が版面の名前か検索語と同じものだけ。点 = 言語数 ×2（名前が同じ）×2（説明が板块に入る）。題材（category）は番号なし（小分類 owner がブランドのものは名前だけで引く・検索語は数えない）。手で compare を付けて起こすと引き直して今の番号と比べるだけ（library.compare_shop）。429 は 5・10・15・20 秒待って 4 回まで、それでも断られたら WdBlocked"},
            {"id": "lb2c", "kind": "table", "lane": "actions", "title": "結果を分けて数える（state/log/library.json）",
             "rows": [("見つかった", "items.yaml の `- name:` の次の行に wikidata: Q… を書いて push（「# wikidata: なし」の行は入れ替え）"),
                      ("項目なし", "聞いて 0 件・名前が合わない → 名前の印のまま、来週また"),
                      ("断られた", "429・5xx・時間切れ → その回は残りを聞かない（来週また）"),
                      ("題材で引かない", "category で記事名がないもの（MMORPG 新作・猫用品…）")]},
            {"id": "lb2b", "kind": "step", "lane": "web", "title": "名前の印の行を番号の印に書き換える", "uses": ["supabase"], "text": "n:… → wd:…（行を増やさない）"},
            {"id": "lb3", "kind": "step", "lane": "actions", "title": "共有の設定と人ごとの置き方に分ける", "text": "板块・小分類・乗換・篇幅・優先 = 人ごと（follows）、ほか = 版面（boards.config）"},
            {"id": "lb4", "kind": "store", "lane": "web", "title": "boards・follows（test1）に上書き", "uses": ["supabase"], "text": "何度流しても同じ。追いかけている人数はトリガーで数える"},
            {"id": "lb5", "kind": "step", "lane": "web", "title": "お客さまの選んだものを読む（userfeed_users）", "uses": ["supabase"], "text": "一度はログインした人の app_users.prefs.picks · 1 人 100 個まで（MAX_FOLLOWS）"},
            {"id": "lb6", "kind": "step", "lane": "ext", "title": "1 つずつ版面に決める（library.plan_users）", "x": "間 1 秒",
             "text": "① もうある版面と名前（そろえたもの）が同じ → その版面 ② 店長の版面と同じ library.find_wikidata（名前だけの版面として）：Wikidata を名前で検索（ja → en、7 件）、候補の項目を引き（検索の返事は前方一致の名前だけで別名が見えない：京都市の別名「京都」）、名前か別名が同じ候補のうち、点 = Wikipedia の言語数 ×2（名前 label が同じ）×2（説明が選んだ板块に入る taxonomy.classify。メディアミックスの作品全体は作品・ゲーム・グッズ・音楽・おでかけのどれにも入る）が一番高いもの（3 字までの英数字は別名だけなら板块に入るときだけ、曖昧さ回避・一覧は除く）→ wd:Q… ③ なければ名前の印 n:…。断られたら残りは次の回"},
            {"id": "lb6s", "kind": "step", "lane": "ext", "title": "小分類を Wikidata の事実で決める（library.subs_for）", "x": "1 項目 2 回 · 30 日 cache",
             "text": "名前＋項目の説明（ja・en）＋種類 P31・上位 P279・ジャンル P136・競技 P641・機種 P400・業種 P452・国 P495/P17/P27 の名前で taxonomy.guess_subs。ゲームは機種が 2 種類以上 → マルチ、発売日 P577/P571 が過ぎた → 発売済み。引いた結果は state/wd_facts.json（Actions の cache、倉庫に入れない）。前に名前だけで決めた小分類（どの値も 1 つ目か名前だけの値）の follows も直す（resubs、1 回 60 項目まで）"},
            {"id": "lb6r", "kind": "step", "lane": "ext", "title": "お客さまが足した版面を今の規則で引き直す（library.recheck_plan → recheck_apply）", "x": "1 回 25 版面 · 1 版面 1 度（RECHECK_VER）",
             "text": "created_by = user の版面を lb6 と同じ規則（板块はその版面の follows）で引き直す。番号が変わったら boards の key・wd を書き換える（新しい番号の版面がもうあれば follows をそちらへ付け替え、古い行は消さない）。付け替えたお客さまの小分類は、前の番号から機械が決めた値のままなら新しい番号の事実で決め直す。引き直した印は wd_facts.json の _recheck"},
            {"id": "lb7", "kind": "store", "lane": "web", "title": "新しい版面と follows（u_…）を足す", "uses": ["supabase"],
             "text": "もうある版面の設定・本人の置き方は書き換えない（ignore-duplicates）。boards にはだれが足したかを書かない（created_by = user）。ログは数だけ"},
        ],
    },
    {
        "id": "libemblem", "name": "ライブラリの小元素", "en": "LIB EMBLEM", "lane": "actions", "workflow": "library_emblem.yml",
        "when": "2 時間ごと（偶数時 29 分）· 手で起こす",
        "trigger": "定時（29 */2 * * *）か workflow_dispatch（minutes、既定 30 分）",
        "summary": "お客さまの版面（ライブラリの版面のうち店長の版面でないもの）にも、店長と同じ規則（emblem_fill.fill_one）で小元素を版面ごとに 1 回。画像は Supabase Storage の公開の箱、全員で同じものを共有。AI なし",
        "files": [".github/workflows/library_emblem.yml", "scripts/library_emblem.py", "db/emblems.sql"], "doc": "docs/rules/emblem.md",
        "uses": ["supabase", "roster", "cutcheck", "facefit", "facerule"],
        "flow": [
            {"id": "le1", "kind": "step", "lane": "web", "title": "対象の版面を読む", "uses": ["supabase"],
             "text": "boards の followers > 0 で test1 が追いかけていないもの · 順：一度も試していない → 0 枚の版面（途中・届かなかったもの）→ 名簿の規則の版が古い届かなかったキャラの版面（数え直し）→ 途中（running）→ 届かなかったものは 24 時間後 · 済み（ok）は飛ばす（名簿の規則の版 emblem_state.nv が古ければ最後に 1 回数え直す。届かなかったキャラの版面〔Fandom・分類・名簿・AniList の手がかりあり〕も nv が古ければ 24 時間を待たずに数え直す）· 前の版の規則（RULES、いま 7：頭のてっぺんが切れた絵・ぼやけた写真を外す）で作った版面は済みでもすぐ作り直す：名簿・分類・小元素（REDO）を捨てて規則から（新しい規則が書いた値は前と同じでも消さない）、キャラもほかも新しい規則で 1 枚も取れなければ前のものを残す（字だけ・図・古い写真は外す）· 同じ画像（公開の箱の指紋が同じ）は 1 枚、キャラの版面はキャラでないページ（emblem.not_character）を外す · 公開の箱へ上げた前の回の小元素も店長と同じ壊れ方の規則（emblem_fill.broken_image：切れ端・頭のてっぺん・額が上の端で切れた・ぼやけた写真）で見直す（library_emblem.unbroken、前のものを残すときも）。emblem_state.bv が BROKEN_V より古い版面は届かなかった・済みでも待たずに 1 回"},
            {"id": "le1b", "kind": "step", "lane": "actions", "title": "管理ページの依頼を反映（apply_requests）", "uses": ["supabase"],
             "text": "管理ページ「小元素」から店長が押した 替える・固定・外す（RPC board_emblem_request → config.emblem_requests）を先に反映：外す・替える = 小元素から抜いて元の画像を emblem_reject へ、替える は人を emblem_redo に残して emblem_state を running に（次の段で同じ人の別の写真）、固定 = lock: true（規則の版が上がっても残す）"},
            {"id": "le2", "kind": "step", "lane": "ext", "title": "種類を規則で（library_emblem.kind_for）",
             "text": "小分類 form=グループ → group · Wikidata P31=Q5（人）か 演出のソロ → person · 游戏・影视 → character · 好物 → brand · ほか → topic。記事名は Wikidata の en/ja/zh/ko の記事。キャラの版面の名簿の手がかりも Wikidata から：anilist_id = AniList のアニメ（P8729）→ 漫画（P8731）、emblem_fandom = Fandom の wiki（P4073、言語の前置きなし）→ なければシリーズ（P179）の P4073 → なければ emblem_fill.fandom_api が名前から（続けた形・ハイフンの形・「:」のあと、転送先の本当の名前）。題材（topic）の版面は emblem_icon も規則で（library_emblem.icons_for：名前・小分類の言葉 → Twemoji の記号〔サッカー ⚽・台風 🌀・旅行 🗺 …〕、当たらなければ板块の記号）＝店長の滑雪の手書きと同じ最後の砦。Wikidata の画像（P154 ロゴ・P18）は版面の番号で直接引く（名前で検索しない：iPhone で Linksys iPhone のロゴ）、字だけ・説明の図・1950 年より前の写真や絵は外す（emblem_fill.not_emblem）· Commons の「名前 logo」はロゴのファイル（logo・wordmark・emblem、SVG も）で、名前とロゴの言葉のほかに何も残らないものだけ（emblem_fill.own_logo：「Logo of the Linksys iPhone」は落ちる。前は logo の名前を落としていたので京都に決済の案内板・電車の写真）· ロゴ（P154）のない製品（iPhone）は Wikidata の代表画像（P18）· Wikidata に断られた版面は書かずに次の回"},
            {"id": "le3", "kind": "step", "lane": "actions", "title": "店長と同じ emblem_fill を一時の items.yaml で",
             "text": "版面 1 つだけの items.yaml と docs/emblems を一時の場所に（sandbox）。集める → 確かめる → 選ぶ → 切り抜く · 本物の items.yaml には触れない · print とライブの帯に名前を出さない", "uses": ["roster", "cutcheck", "facefit", "facerule"]},
            {"id": "le4", "kind": "store", "lane": "web", "title": "公開の箱 emblems と boards.config", "uses": ["supabase"],
             "text": "画像 = emblems/<Wikidata の番号か b+id>-<中身の指紋 10 字>.webp（版面の名前は出さない）· config.emblem・theme・emblem_*（手がかり）・emblem_state {state, have, at, note}（note の「もう一度」は店長の毎時ではなく RETRY_HOURS 24 時間に書き換える）"},
            {"id": "le5", "kind": "step", "lane": "actions", "title": "お客さまのページを作り直す（user_pages.py）",
             "text": "follows の boards(name,config) から emblem・theme を版面に（店長の版面と同じ render._emblem）"},
        ],
    },
    {
        "id": "render", "name": "ページ生成", "en": "RENDER", "lane": "actions", "workflow": "render.yml", "when": "push のたび · 約 1 分",
        "trigger": "main に push されたとき（コード・items.yaml・愿望清单など）",
        "summary": "収集を待たず、網页だけを 1 分ほどで作り直して公開する。話題度・配色・版面の組み方もここで決まる。",
        "files": [".github/workflows/render.yml", "scripts/render.py", "scripts/lang.py"], "doc": "docs/rules/design.md", "uses": ["heat", "octree", "softalt", "frontpick", "fit", "confetti", "lang"],
        "flow": [
            {"id": "p1", "kind": "step", "lane": "actions", "title": "main に push", "x": "新しい回が来たら古い回を止める"},
            {"id": "p2", "kind": "step", "lane": "web", "title": "篇幅を読む", "text": "S / M / L", "uses": ["supabase"]},
            {"id": "p2b", "kind": "decision", "lane": "actions", "title": "報告が最新の edit.json を取り込んでいる？",
             "text": "reports の edit_sig（edit.json の SHA-1 先頭 12 桁）と比べる。収集が古い checkout で出刊している間に AI 編集が push した／競合で報告だけ相手側が残った場合は「いいえ」",
             "no": "publish(heal) で出刊し直す（edit.json を取り込むだけ・おすすめや配図の再探しは飛ばす）"},
            {"id": "p3", "kind": "step", "lane": "actions", "title": "話題度を計算", "uses": ["heat"]},
            {"id": "p4", "kind": "step", "lane": "actions", "title": "トップの配色", "uses": ["octree"]},
            {"id": "p4c", "kind": "step", "lane": "actions", "title": "版面の副色が鮮やかなら広い面を落ち着かせる", "x": "作品ごと",
             "text": "「もっと見る」の背景 = 主面 + 副色 20%（例：濃い色の版面）", "uses": ["softalt"]},
            {"id": "p3l", "kind": "step", "lane": "actions", "title": "号をまたいだ言語違いを 1 本に", "x": "作品ごと",
             "text": "主言語 → 副言語の順で残す · 予定の欄は同じ日・同じラベル 1 回", "uses": ["lang"]},
            {"id": "p4b", "kind": "step", "lane": "actions", "title": "トップの記事を選ぶ", "x": "直近 7 日の全号から",
             "text": "作品ごとに 1 本目 → 2 本目 · 同じ写真・同じ出来事は 1 回", "uses": ["frontpick"]},
            {"id": "p5", "kind": "table", "lane": "actions", "title": "版面の組み方",
             "rows": [("写真の壁", "15 枚（スマホ 6）· 16:10"), ("普通の記事", "1 行 3 枚まで · 4 枚 = 2 + 2"), ("篇幅", "S 3 / M 4 / L 10 件"),
                      ("本文の区切り", "目次と同じ 板块 → 小分類 の順に並べ、小分類が変わる所に細い見出し（板块の札・件数）"),
                      ("目次：シリーズの中身", "items.yaml の media（マンガ・アニメ・映画…）を駅の下に枝で · 直近 7 日の記事で媒体の語に当たる件数を +n"),
                      ("目次：たたんだ板块", "駅が 1 つも出ず高さ 84px 以上の空きに作品名を薄く 1〜2 行（新着の多い順・8 件まで）"),
                      ("目次：通り過ぎた駅", "読んでいる駅より目次の並びで前の駅を板块の色で塗る（版面の番号ではなく目次の順）")]},
            {"id": "p6", "kind": "store", "lane": "repo", "title": "docs/home/*.html", "text": "店長のページ（網址 /home/ はみんな同じ・中身はログインした人で決まる、旧 /test1/・/shop/ は飛ぶだけ）· docs/test2/ は 2026-10-19〜21 の凍結した写し · docs/index.html は入口"},
            {"id": "p6a", "kind": "store", "lane": "repo", "title": "管理ページ 7 枚", "x": "render.ADMIN_PAGES",
             "text": "admin.html（トップ：6 枚のカードと数）＋ admin-now（①いま）・admin-boards（②版面）・admin-emblem（③エンブレム）・admin-ai（④AI 編集）・admin-system（⑤しくみ）・admin-members（⑥お客さまと店長）。"
                     "どのページにも 7 つの切り替え · 前の網址 admin.html#欄 はトップがその欄のページへ送る · ux_check が 7 枚と「なくした欄 0」を見る"},
            {"id": "p7", "kind": "step", "lane": "web", "title": "GitHub Pages に公開", "text": "約 1 分", "uses": ["fit", "confetti"]},
        ],
    },
    {
        "id": "login", "name": "ログインと権限", "en": "LOGIN", "lane": "web",
        "when": "ページを開いたとき · ログイン・ログアウトしたとき",
        "trigger": "どのページでも右上の「ログイン」（メールアドレスだけ）。開いたときに身份を確かめ、見るだけかどうかを決める",
        "summary": "访客は見るだけ（👍・設定・写真・ボタンは止まる、管理ページは見えない）。だれでもメールアドレスだけで始められ（重ならない・規約に同意・ブラウザが覚える。管理者のメールを名前にしたときだけ最初の 1 回メールで確認）、ユーザーは自分の account だけ、管理者は全部を変えられる。門番はデータベース。",
        "files": ["scripts/render.py（AUTH_JS / AUTH_CSS / _auth_tag / AUTH_LOCK）", "db/my_page.sql", "db/auth.sql", "db/auth_guard.sql", "db/auth_enforce.sql", "db/auth_delete.sql"], "doc": "docs/rules/login.md",
        "flow": [
            {"id": "a0", "kind": "step", "lane": "web", "title": "入口（docs/index.html）→「新しく始める」",
             "text": "何のサイトか・店長のページの本物の画面。メール・パスワードと規約 → ニュースの言語（よく使う 6 つ＋地域ごとの 56 言語、検索できる）→ 好きなジャンル → 候補のタイルを押して選ぶ・名前でも足せる（AniList の話題・Steam の売れ筋・店長がフォローしてきたもの）→ 最初の版面 5 つまで → user_signup（名前・同意・好みを一度に）。覚えているブラウザは入口を飛ばして自分のページへ（いまは店長のページ）。入口は digest render のたびに 24 時間より古ければ作り直す", "uses": ["maillink", "terms", "welcome"]},
            {"id": "a1", "kind": "step", "lane": "web", "title": "右上の「はじめのページ」（入口 ../?stay、見るだけでもログイン中でもいつも見える）/「ログイン」",
             "text": "だれでもメールアドレス＋パスワード（2026-10-21：ユーザー名 → メールだけ → メール＋パスワード）。ログイン = signInWithPassword → user_login（規約の版）。新しく始める（入口）＝メールが未登録かを打つたびに確かめ（name_available）、パスワード 8 文字以上を 2 回、規約に同意 → user_signup（p_password つき）→ そのままログイン。このブラウザが覚える（ログアウトまで）。退会の機能はなし", "uses": ["maillink", "terms"]},
            {"id": "a1b", "kind": "decision", "lane": "web", "title": "同意した版 ＜ いまの版？",
             "text": "開くたびに user_login で確かめる（TERMS_VERSION）",
             "yes": "同意の画面（同意しないならログアウトして見るだけ）", "no": "そのまま"},
            {"id": "a2", "kind": "decision", "lane": "web", "title": "管理者のメール？",
             "text": "is_admin_email が invites 表（role=admin）を見る",
             "yes": "パスワードの欄を出す（まだ決めていなければ、はじめの 1 回ここで決める）→ signInWithPassword で管理者のセッション（Supabase が覚える・メールは送らない）", "no": "そのまま一般ユーザー（運営者のページは見るだけ）", "uses": ["invite"]},
            {"id": "a3", "kind": "step", "lane": "web", "title": "身份を確かめる",
             "text": "auth_enforced・my_role・can_edit(このページの account) を読み、<html> に data-role / data-lock を付ける。ページの JS の Supabase 呼び出しにログインした人の鍵を付ける", "uses": ["roles"]},
            {"id": "a3m", "kind": "decision", "lane": "web", "title": "お客さま（店長でない人）がログインしている？",
             "text": "簡報・欲しい物・話題度・設定。アカウントは 1 つずつ独立（2026-10-22）。ログインを覚えているブラウザは、決まるまで店長の中身を隠す",
             "yes": "自分のページ：my_page()（本人の行だけ）→「〇〇さんのページ」・自分のキーワード（prefs.picks）。設定でキーワードを足す・外す・元に戻す（my_keywords_set、200 個まで）。目次は「ページ」「キーワード」だけ（まだ使えないものは出さない）。仕組みの説明・準備中・店長のページへの切り替えは出さない（impeccable clarify・distill、onboarding の空の状態）。ログインの知らせからの呼び出しは setTimeout で後に回す（Supabase 公式）",
             "no": "店長のページ（访客は見るだけ・店長は全部）", "uses": ["supabase"]},
            {"id": "a4", "kind": "decision", "lane": "web", "title": "このページを変えられる？",
             "text": "開關が開いていて、ログインしていない・自分の account でない",
             "yes": "そのまま使える", "no": "見るだけ：👍・設定・写真・ボタンを押すと「見るだけです」。設定ページは上に注意書き"},
            {"id": "a5", "kind": "decision", "lane": "web", "title": "管理ページ：管理者？",
             "text": "開關が開いているときだけ確かめる",
             "yes": "表示＋「ユーザーと管理者」（管理者のメール・登録済みの人の名前だけ・管理者を足すフォーム）", "no": "「管理者だけが見られます」の画面だけ"},
            {"id": "a6", "kind": "table", "lane": "web", "title": "データベースの門番（本物の制限）",
             "text": "画面のボタンを止めるのは案内だけ。書く関数の 1 行目で can_edit / is_admin を確かめる",
             "rows": [("篇幅・分け方・関注項の依頼・写真・AI 編集の開關", "can_edit(p_account)：管理者か、その account の持ち主"),
                      ("👍👎（feedback）", "ログインした人：can_edit(account) · ログインしていない人：開關が閉じている間だけ"),
                      ("今すぐ実行（run_now）", "管理者だけ（pg_cron の tick は除く）"),
                      ("管理者の追加・ユーザー一覧", "管理者だけ（メールは管理者の表だけ、ユーザー一覧は名前だけ）"),
                      ("開關（auth_flags.enforce）", "閉 = 前と同じ（だれでも変えられる）· 開 = 上の制限が効く（db/auth_enforce.sql で開く）")]},
        ],
    },
    {
        "id": "live", "name": "ページの自動更新", "en": "LIVE", "lane": "web",
        "when": "開いている間 · 1 分ごと",
        "trigger": "簡報・管理ページを開いているあいだ、1 分ごと（タブが裏にあるときも戻ったときにすぐ）",
        "summary": "開いたままのページに、新しい記事や数字を自分で出す。裏である版面を作り直している間は、その版面だけ枠に「更新中」の帯と残り時間。",
        "files": ["scripts/render.py（LIVE_JS / BUSY_JS / stamp / page_marks / busy_plan）", "scripts/digest.py（write_page / live_mark / live-edit）", "scripts/livestatus.py", "scripts/runlog.py（typical）", "db/live_status.sql", "docs/home/version.json"], "doc": "docs/rules/live.md",
        "flow": [
            {"id": "l1", "kind": "step", "lane": "actions", "title": "ページを作るたびに指紋を付ける",
             "text": "収集・AI 編集・ページ生成が docs/*.html を書くとき、中身の指紋（「更新」の時刻は除く）を計算。"},
            {"id": "l2", "kind": "store", "lane": "repo", "title": "docs/home/version.json",
             "text": "{index: 指紋, admin: 指紋, admin-now など管理ページ 6 枚の指紋, index_marks: {版面の id: [名前, 版面の指紋]}}。ページの <meta name=\"wl-ver\"> と各版面・パネルの data-h にも同じ指紋。"
                     "簡報の版面の指紋は AI 編集が整理した記事（article）だけ：整理待ち・話題度の数字・小元素が変わっても「更新」にしない。"},
            {"id": "l3", "kind": "step", "lane": "web", "title": "開いたらすぐ・その後 1 分ごとに version.json を見る",
             "text": "キャッシュを避けて読む（?t=時刻）。タブを表に戻したときもすぐ見る。開いて 15 秒以内・入力前に古いと分かったら ?v=新しい指紋 で開き直す（GitHub Pages はブラウザに 10 分残すため。着いたら ?v= を消す・同じ v で古いままなら繰り返さない）。入口（docs/index.html）も index.ver.json で同じことをする"},
            {"id": "l4", "kind": "decision", "lane": "web", "title": "指紋が変わった？", "text": "version.json ≠ 自分の指紋",
             "yes": "名前を挙げられる変化（AI 編集した記事の増減）があれば、下に「新しい内容があります：作品 A、作品 B…」の帯（クリックでその版面へ）。なければ帯を出さず、静かに読み直すだけ", "no": "何もしない"},
            {"id": "l5", "kind": "decision", "lane": "web", "title": "いま操作していない？",
             "text": "20 秒触っていない、またはタブが裏。入力中・流れの図を開いているあいだは待つ",
             "yes": "読み直す", "no": "待つ（帯の「今すぐ表示」で即時）"},
            {"id": "l6", "kind": "step", "lane": "web", "title": "見ていた場所のまま新しい版に",
             "text": "読み直す前の位置（見ていた板块）に戻す。増えた記事に「たった今」を付け、帯に「更新しました：作品 A 新着 2 件、作品 B 新着 1 件、作品 C 更新」"
                     "（記事が増えた版面は件数、記事は同じで中身だけ変わった版面・パネルは「更新」。名前をクリックでその版面へ）。"},
            {"id": "l8", "kind": "decision", "lane": "web", "title": "裏でこの版面を作り直している？",
             "text": "版面ごとに判断。ほかの版面には帯を出さない",
             "yes": "その版面の上の枠に帯（版面の色）＋「あと約 N 分」", "no": "帯なし"},
            {"id": "l9", "kind": "table", "lane": "web", "title": "どの版面に・いつ帯を出すか",
             "text": "推定はしない：仕組み自身が Supabase live_status に版面ごとに書き、網页が 30 秒ごとに読む（live_boards）。"
                     "「あと約 N 分」は各仕組みの最近 10 回の実際の長さの中央値（runlog.typical）。帯は小元素の下。ページがその作業より後に作られていれば出さない。",
             "rows": [("ニュース収集", "探し始め「記事を探しています」→ その版面を探し終えたらすぐ：新着なし＝消える／新着あり＝「新着 N 件 · AI 整理待ち · 一覧まで約 N 分」（出刊後は版面の下の「整理待ち」に並ぶ。secret key で直接）"),
                      ("AI 編集", "live-edit で今日まだ編集していない版面に「AI が編集しています」→ pick-images「配図を選んでいます」→ publish「反映を待っています」（live_report）"),
                      ("小元素の自動補完", "処理を始めた版面に「小元素を集めています」→ 増えた版面だけ「反映を待っています」、増えなければ消える（live_report）"),
                      ("ページ生成", "帯なし（中身ではなく見た目の変更。下の「新しい内容があります」で知らせる）"),
                      ("反映待ちを消す", "GitHub Pages の公開が終わるたび（page_build → live_clear.yml）に、公開の 30 秒前より前に始まった「反映を待っています」（state=wait）の行を消す（livestatus.clear_waits、2026-10-25）。作業中のまま 90 分たった行は図で「途中で止まった（次の回で続きから）」"),
                      ("live_report の制限", "proc は edit / emblem・版面は sizes にある名前・言葉 40 字・予想 90 分まで（secret key なしで書けるので）")]},
            {"id": "l7", "kind": "table", "lane": "web", "title": "管理ページの「いまの状況」",
             "text": "ページの再読込とは別に、外のデータを開いている間ずっと読み直す。",
             "rows": [("ライブログ（管理ページの一番上）", "ターミナル風の窓。live_boards() の差（20 秒：版面が始めた・段が進んだ・終えた）、Actions の開始・成功・失敗（3 分）、state/log の新しい行（raw.githubusercontent.com、2 分）を流す。見た行は localStorage に 300 行残す（livelog.py）"),
                      ("しくみの全体図（管理ページの一番上）", "5 ページ（全体・収集・AI 編集・小元素・ページ更新）が 1 画面ずつ。live_boards()（30 秒）と Actions の実行中（3 分）で、動いている部品が光る・止まって見えるものは赤。待ちの意味は下の「いま待っているもの」に（overview.py）"),
                      ("ウォッチ項目の依頼・写真の受付", "Supabase · 1 分ごと"), ("GitHub Actions", "3 分ごと（1 時間 60 回の制限内）"),
                      ("次の実行・待ち行列", "1 分ごとに数え直し")]},
        ],
    },
    {
        "id": "requests", "name": "設定ページの依頼", "en": "REQUESTS", "lane": "web", "workflow": "requests.yml", "when": "依頼のたび · 待ちなし",
        "trigger": "設定ページで関注項の追加・変更・篇幅の変更を送ったとき（待ち時間なし）",
        "summary": "設定ページの依頼を Supabase が受け、すぐ GitHub Actions を起こして items.yaml に反映する。",
        "files": [".github/workflows/requests.yml", "docs/home/additem.js", "db/instant.sql", "sections.yaml", "scripts/taxonomy.py"], "doc": "docs/rules/wizard.md", "uses": ["supabase", "pgnet", "taxonomy"],
        "flow": [
            {"id": "qp", "kind": "step", "lane": "web", "title": "上級を推す", "text": "今ある・上級のない関注項の名前・搜索词が新項の名前・維基データに出てくる → 推薦 · 維基データの系列（P179 / P8345 / P361）がまだ関注清单になければ「上級の系列も一緒に追加」を選べる（系列 → この項の順に送る、系列は小分類シリーズ）· 1 層だけ · シリーズになる項は選んだ面を media（目次の枝）に"},
            {"id": "qr", "kind": "step", "lane": "web", "title": "同じ系列のほかのものを推す", "x": "維基データ 2 回",
             "text": "系列を P179 / P8345 / P361 / P921 / P144 / P1441 に持つ条目（haswbstatement）＋名前に系列名が入った条目（全文検索）· 人・キャラ・一覧は除く · 説明の語で板块・小分類に対号入座（スタジオツアー・展覧会 → おでかけ）· 板块ごとに 4 件まで・選んだものは系列の下級として各自の板块に", "uses": ["taxonomy"]},
            {"id": "qt", "kind": "step", "lane": "web", "title": "加えた後の目次を樹形図で見せる", "text": "板块 → 小分類 → 関注項（新しい版面・下級・乗換站、同じ小分類の既存の項を 2 件）· 選び直すとすぐ描き直す"},
            {"id": "qf", "kind": "step", "lane": "web", "title": "「面」を全部並べて推す", "text": "選んだ条目そのものは名前が違っても自分の面の依拠（「ハリー・ポッター TV」→ ドラマ）· 本体の面が決まらないときは条目の説明 → 作品の層を先に · 第 4 問「何を先に出すか」は目次の枝ごとに小さな勾選框、ほかの勾いた面の話はその面だけに（同じことを 2 回聞かない）· 加えた後の樹形図は 1 つの版面＋枝（乗換駅なし）· 検索語から維基の括弧を外す · test2 の画面：上に「加えた後」（版面 1 つ＋目次の枝、勾で即更新）、下に層ごと（作品＝維基データ確認／展開＝規則で推定）1 行 1 面・勾選框・札はメイン／推定／情報少なめだけ（「推荐」の札はなし＝既定の勾が推薦）・見つけたもの 1 行・検索語は「詳細」に · 作品・IP 型：アニメ・映画・ドラマ・漫画（→作品）・ゲーム・グッズ（→ショッピング）・舞台・ライブ（→音楽）・イベント・カフェ・展示（→おでかけ）の 8 面、維基データの同名の条目と、その条目を原作 P144・媒体系列 P8345・系列 P179 に持つ派生作品・自分の派生作品 P4969（AniList / TMDB / Steam の番号・説明の語）で「怎么放」は聞かず板块ごとに版面 1 つで固定 · additem.js は中身の指紋つき URL で読む · 多選の質問は「全選」つき・「関注する方面」は既定で全選 · 面を選んだら小分類は聞かず規則で決める · 同じ系列の一問は面にあるものを除く。「要紧消息 → Discord」の質問は保留中（聞かない・PENDING.md）。依拠は 4 つ（名前検索・派生作品 P144/P8345/P179/P361/P921/P4969・名前の全文検索・維基百科の目次の節）、条目も節も 1 つの面だけに入れる。面は MECE：作品 6 面は維基データで確認・展開 2 面（グッズ・イベント）は 2 媒体以上の作品／キャラ IP なら推定、語はほかの面と重ならない。状態は 確認・推定・情報少なめ・見つからず のどれか 1 つ。依拠のある面だけ並べる（見つからない面は最後に名前だけ・維基百科の言語が 3 未満の条目しかない面は「情報少なめ」で勾なし。同じ系列のもの・上級の系列も同じ基準）、具体的な作品名も検索語に。2 面以上あればグッズも並べる · 題材型（短い普通の語「猫」）：sections.yaml の facets（なければ第一の分け方の値）、名前と面の語が同時に出たときだけ収める · 全部選べる", "uses": ["taxonomy"]},
            {"id": "qm", "kind": "step", "lane": "web", "title": "1 つの名前 = 1 つの版面（test2）",
             "text": "版面は選んだ維基データの条目そのものが依拠になっている面の板块（ちいかわ = 漫画の条目 → 作品 › シリーズ、種類はその板块の面の アニメ > 漫画…）。ほかの面（グッズ・イベント…）は検索語を広げ、目次の枝（media：マンガ → アニメ → 映画 → グッズ → イベント）になるだけ · 乗換駅は置かない（板块は 1 つだけ選ぶ）"},
            {"id": "qs", "kind": "decision", "lane": "web", "title": "確認画面で「グッズ・イベントを別の版面にする」に勾？（既定は勾なし）", "no": "1 つの版面のまま"},
            {"id": "qk", "kind": "step", "lane": "web", "title": "ほかの板块の面を下級に", "text": "同じ板块の面は 1 つにまとめ「名前 グッズ」…を parent = 本体で本体と同じ板块へ（目次で本体の下の枝、小分類の第一の分け方は自分の面）· 本体の枝は本体の板块の面だけ · 主項の後に続けて送る"},
            {"id": "q0", "kind": "step", "lane": "web", "title": "板块・小分類を推す", "text": "上級があれば上級の板块・ほかの分け方も上級と同じ、1 つ目の分け方は自分の類別 · なければ「角色 / IP」はグッズ、ほかは維基データの説明・名前の語 → sections.yaml の表（当たらなければ type → その他）", "uses": ["taxonomy"]},
            {"id": "q1", "kind": "step", "lane": "web", "title": "設定ページで送る", "text": "一問一答のウィザード", "uses": ["supabase"]},
            {"id": "q2", "kind": "step", "lane": "web", "title": "Supabase が GitHub を起こす", "uses": ["pgnet"]},
            {"id": "q3", "kind": "decision", "lane": "actions", "title": "待ちの依頼がある？", "no": "何もしない"},
            {"id": "q4", "kind": "step", "lane": "actions", "title": "検査して items.yaml に書く", "text": "「删」（edit ＋ _delete）はその 1 段を消し、下級は parent を外して残す · 管理ページの小元素の「違う」（押して理由を選ぶ：emblem_rules.REJECT_REASONS の 10 種＋ひとこと · edit ＋ _emblem_reject、版面ごとに 1 件・50 枚まで）はその小元素を外して元の画像を emblem_reject に・倉庫の webp も消す・理由と取り方（why）・網域を state/emblem_rejects.json に（管理ページ「「違う」の理由」で数え、溜まった理由の近い判断を締める）（足りない分は次の後台で別の画像）・同じ依頼で _emblem_swap（同じ人の別の写真に替える：元の画像は emblem_reject・人は emblem_redo で次の集めの先頭に）と _emblem_lock（lock: true の固定：名簿外し・検査外し・作り直しで替えない）も · 使える項目だけ · 板块は表にあるものだけ · 上級は今ある・上級のない項だけ、板块は上級に合わせる · 済み・見送りを返す", "uses": ["taxonomy"]},
            {"id": "q5", "kind": "decision", "lane": "actions", "title": "新しい関注項？", "no": "ページ生成だけ"},
            {"id": "q6", "kind": "step", "lane": "actions", "title": "すぐ収集 → AI 編集が版面を設計", "by": "ai"},
        ],
    },
    {
        "id": "photos", "name": "写真から愿望", "en": "PHOTOS", "lane": "ai", "schedule": [(1, 47), (5, 47), (9, 47), (13, 47)],   # 日本時間 10 / 14 / 18 / 22 時 47 分
        "when": "1 日 4 回",
        "trigger": "愿望清单ページで撮った写真が溜まったとき（Actions が 2 時間ごとに書き出し）",
        "summary": "写真に写っているものを Claude が見て認識し、愿望清单に 1 件として整理する。",
        "files": ["PHOTOS.md", "wishlist.yaml"], "doc": "PHOTOS.md", "uses": ["claude", "crop", "supabase"],
        "flow": [
            {"id": "f1", "kind": "step", "lane": "web", "title": "写真を撮って送る", "text": "長辺 1600（2.9MB 超は 1200）· 縮図 240", "uses": ["supabase"]},
            {"id": "f2", "kind": "store", "lane": "web", "title": "photo_inbox", "x": "未処理 20 枚まで"},
            {"id": "f3", "kind": "step", "lane": "actions", "title": "inbox/photos に書き出す", "text": "収集のたびに"},
            {"id": "f4", "kind": "decision", "lane": "ai", "title": "写真がある？", "no": "何も変えずに終わり"},
            {"id": "f5", "kind": "step", "lane": "ai", "title": "見て認識する", "text": "名前・価格・規格・タグ", "uses": ["claude"]},
            {"id": "f6", "kind": "step", "lane": "ai", "title": "物だけ切り取る", "by": "ai", "uses": ["crop"]},
            {"id": "f7", "kind": "store", "lane": "repo", "title": "wishlist.yaml"},
        ],
    },
]


# ---------------------------------------------------------------- 全体の構成図（アーキテクチャ）
# 枠（zone）：style = ext（外のサービス）/ temp（その都度立ち上がる環境・破線）/ keep（ずっと残る場所・実線）。
# 枠の中の部品：proc = プロセスの id（クリックで流れが開く）、それ以外は保存先・外部サービス（説明だけ）。
# 矢印（EDGES）：(番号, 元, 先, 説明, 色)。色 = data（収集）/ web（網页）/ ai（AI）/ notify（Discord）/ db（データベース）。
ARCH = [
    {"id": "src", "title": "インターネット", "note": "ニュース・数字・画像・モデルの出どころ", "cost": "無料", "style": "ext", "nodes": [
        {"id": "n-news", "label": "ニュース", "text": "記事の一覧（RSS・API）", "uses": ["gnews", "bing", "reddit"]},
        {"id": "n-api", "label": "作品データ", "text": "価格・放送・人気・閲覧数", "uses": ["steam", "anilist", "tmdb", "wikipv"]},
        {"id": "n-img", "label": "画像", "text": "小元素の候補", "uses": ["wiki", "fandom", "twemoji", "bingimg"]},
        {"id": "n-model", "label": "モデルの配布元", "text": "GitHub Releases（rembg）・HuggingFace（顔のモデル）"},
        {"id": "n-mail", "label": "メール", "text": "店長はパスワード（メールは送らない）", "uses": ["maillink"]},
    ]},
    {"id": "act", "title": "GitHub Actions", "note": "毎回新しいサーバー（4 コア）· 終わったら消える", "cost": "無料", "style": "temp", "nodes": [
        {"id": "p-collect", "proc": "collect", "subs": ["heat", "recommend", "notify", "images"]},
        {"id": "p-gate", "proc": "gate", "subs": ["emblem-cron"]},
        {"id": "p-requests", "proc": "requests"},
        {"id": "p-library", "proc": "library"},
        {"id": "p-libemblem", "proc": "libemblem"},
        {"id": "p-progress", "proc": "progress"},
        {"id": "p-render", "proc": "render", "subs": ["colors"]}]},
    {"id": "repo", "title": "GitHub リポジトリ", "note": "ずっと残る · 全部の元データ", "cost": "無料", "style": "keep", "nodes": [
        {"id": "s-inbox", "label": "inbox/", "text": "集めた記事・edit.json・写真"},
        {"id": "s-items", "label": "items.yaml", "text": "関注項・版面・小元素"},
        {"id": "s-wish", "label": "wishlist.yaml", "text": "愿望清单"},
        {"id": "s-state", "label": "state/", "text": "進捗・ログ・話題度・おすすめ・通知済み"}]},
    {"id": "ai", "title": "Anthropic · Claude", "note": "定時タスク · 毎回新しいコンテナ（4 コア · 15GB）", "cost": "サブスク枠", "style": "temp", "nodes": [
        {"id": "p-edit", "proc": "edit", "subs": ["emblem"]}, {"id": "p-photos", "proc": "photos"},
        {"id": "s-model", "label": "画像のモデル（Actions のキャッシュ）", "text": "抠图は 1 枚ずつ · 顔のモデルは 1 つを順番に",
         "uses": ["rembg", "yunet", "sface", "haar"], "model": True}]},
    {"id": "db", "title": "Supabase", "note": "データベース", "cost": "無料枠", "style": "keep", "nodes": [
        {"id": "s-db", "label": "feedback · sizes · item_requests · photo_inbox · news · live_status · user_boards", "text": "👍👎・篇幅・依頼・写真・記事の控え・版面の更新状態・お客さまの版面",
         "uses": ["supabase", "pgnet"]}]},
    {"id": "pages", "title": "GitHub Pages", "note": "公開の網页", "cost": "無料", "style": "keep", "nodes": [
        {"id": "s-pages", "label": "網页", "text": "簡報・設定・愿望清单・話題度・管理ページ・version.json", "uses": ["fit", "confetti"]},
        {"id": "p-live", "proc": "live"}, {"id": "p-login", "proc": "login"}]},
    {"id": "dc", "title": "Discord", "note": "通知", "cost": "無料", "style": "ext", "nodes": [
        {"id": "s-discord", "label": "あなたのチャンネル", "text": "要紧は当日・周報は月曜", "uses": ["discord"]}]},
    {"id": "you", "title": "あなた", "note": "スマホ・パソコン", "cost": "", "style": "you", "nodes": [
        {"id": "s-you", "label": "見る・押す・撮る", "text": "簡報を読む・👍👎・関注項の追加・写真"}]},
]
EDGES = [
    (1, "n-news", "p-collect", "記事を集める（6 本並列）", "data"),
    (2, "n-api", "p-collect", "話題度・現状", "data"),
    (3, "p-collect", "s-inbox", "inbox に書く", "data"),
    (4, "p-notify", "s-discord", "要紧・周報", "notify"),
    (5, "s-inbox", "p-edit", "読む", "ai"),
    (6, "p-edit", "s-inbox", "edit.json・出刊", "ai"),
    (7, "n-img", "p-emblem-cron", "画像を探す（4 本並列・AI なし）", "data"),
    (8, "p-emblem-cron", "s-items", "小元素を書く", "data"),
    (9, "s-items", "p-render", "push", "web"),
    (10, "p-render", "s-pages", "公開", "web"),
    (11, "s-pages", "s-you", "見る", "web"),
    (12, "s-you", "s-db", "👍・設定・写真", "db"),
    (13, "s-db", "p-requests", "依頼（pg_net）", "db"),
    (14, "p-requests", "s-items", "items.yaml に反映", "db"),
    (15, "s-db", "p-collect", "写真・投票を取り込む", "db"),
    (16, "s-inbox", "p-photos", "写真", "ai"),
    (17, "p-photos", "s-wish", "愿望を足す", "ai"),
    (18, "s-discord", "s-you", "通知", "notify"),
    (19, "n-model", "s-model", "ダウンロード", "ai"),
    (20, "s-model", "p-emblem-cron", "抠图・本人確認", "data"),
    (21, "s-pages", "p-live", "version.json を 1 分ごと", "web"),
    (22, "p-live", "s-you", "新着を自動で表示・更新中の帯", "web"),
    (23, "p-collect", "s-db", "版面ごとの状態（探している・新着）", "db"),
    (24, "s-db", "p-live", "live_status を 30 秒ごと", "db"),
    (25, "p-gate", "p-edit", "版面に整理待ちが溜まったら起こす", "ai"),
    (26, "p-gate", "p-photos", "写真があるときだけ起こす", "ai"),
    (27, "p-edit", "s-db", "編集中の版面（live_report）", "db"),
    (28, "p-emblem-cron", "s-db", "処理中の版面（live_report）", "db"),
    (29, "p-login", "n-mail", "管理者のメールだけ確認のリンク", "web"),
    (30, "n-mail", "s-you", "リンクを押す → 本人の鍵", "web"),
    (31, "p-login", "s-db", "身份を確かめる・書くときに鍵を付ける", "db"),
    (32, "p-gate", "p-collect", "定時が抜けて 150 分あいたら収集を起こす", "data"),
    (33, "p-collect", "s-db", "お客さまの版面（user_boards・本人だけ読める）", "db"),
    (34, "n-img", "p-libemblem", "お客さまの版面の画像を探す（店長と同じ規則）", "data"),
    (35, "p-libemblem", "s-db", "boards.config.emblem・Storage の公開の箱", "db"),
]
# 並列で動かすときの限り（管理ページ「バックグラウンド → 並列と制限」）。(仕組み, いまの並列, 限り・理由)
LIMITS = [
    ("ニュース収集", "6 本並列 · 18 分で締め切り", "GitHub Actions のサーバーは 4 コア。待ちが多いので 6 本。18 分を過ぎたら新しい版面を始めず次の回へ（1 回 40 分まで：出刊・通知・push の分を残す）。同じサイトの間隔は全スレッドで共有（Reddit 2 秒・Google / Bing 0.5 秒・GDELT 5.5 秒・Bluesky / Mastodon 1 秒・YouTube 0.5 秒）。AI を使わないので時間は使ってよい（GDELT で 25 関注項 約 5 分増える）"),
    ("小元素の自動補完", "6 本並列", "GitHub Actions（4 コア・16GB・1 回 60 分まで、続けて 3 回まで）。集めるのは待ちが多いので 6 本、抠图（rembg）と items.yaml への書き込みは 1 本ずつ"),
    ("抠图のモデル（rembg）", "1 枚ずつ", "birefnet は 1 枚で数 GB のメモリを使う。onnxruntime のメモリ池を切って、1 枚ごとに返す（前は 13GB まで溜まった）"),
    ("Wikipedia・Wikidata・Commons", "ホストごと 1 本ずつ · 全体で毎分 150", "Wikimedia の上限は名乗ったボットで全サイト毎分 200（名乗らないと 10）。"
     "429 は Retry-After を守り、続いたら 5 分休む → ここは並列でも速くならない。取ったものはキャッシュ（~/.cache/wishlist-http）"),
    ("Claude の定時タスク", "仕事があるときだけ", "起きるたびにトークンを使う。ゲートが仕事を確かめてから起こす（AI 編集・写真）。小元素は AI を使わない"),
    ("GitHub Actions", "同じワークフローは 1 本ずつ", "収集・依頼は前の回が終わるまで待つ（concurrency）。ページ生成は新しい回が来たら古い回を止める。"
                       "定時（cron）は混むと遅れる・抜ける（2 時間抜けたことがある）ので、後台作業は Supabase pg_cron（17 分）も 2 つ目の時計に。"
                       "収集の時計は後台作業が兼ねる（最後の収集から 150 分で digest.yml を起こす）"),
    ("お客さまの版面の記事集め", "4 本並列 · 1 回 80 版面・8 分", "店長の収集のあと同じ job で（timeout 40 分の 3 分前までに自分で終える）。同じサイトの間隔は店長の収集と共有（sources._pace）。1 人 1 回 10 版面・まだ集めていない人は 1 回 15 人まで（大量の登録で先にいる人を止めない）"),
    ("AI 編集・写真から愿望", "1 本", "1 日の決まった時刻に 1 回ずつ。同じ inbox を書くので並列にしない"),
]
# AI（Claude）を使うか：前に AI でやっていた判断ごとに、規則（プログラム）にできたか・AI のままか・その理由。
# (仕事, いま, 判断の理由)。いま = rule（規則にした・AI なし）/ gate（AI のまま、ただし仕事があるときだけ）/ ai（AI のまま）
AI_TASKS = [
    ("小元素：候補を集めて選ぶ", "rule", "取り方の順・種類ごとの確かな取り方・同じ人は 1 枚。決まった手順なので規則で足りる"),
    ("小元素：写真が本人か・使えるか（前は目で見ていた）", "rule", "顔の大きさ < 10% = 遠景、2 番目の顔 ≥ 60% = 何人も、SFace cos < 0.363 = 別人、基準なしは同じ顔 2 枚以上"),
    ("小元素：切り抜きがきれいか（前は目で見ていた）", "rule", "端で切れた・にじみ・実在の人の写真の穴 > 3% を数で判断"),
    ("後台：今日やる仕事があるか", "rule", "inbox の _covered・写真のファイル・小元素の缺口を数えるだけ（ゲート）"),
    ("出刊：未整理の新着を版面に載せるか", "rule", "載せない（「整理待ち」の折りたたみに原題だけ）。例外の要紧は urgent_patterns の正規表現で決まるので規則"),
    ("記事の重複・要紧・おすすめ・配色・配図の候補", "rule", "前から規則（bigram・正規表現・好みの学習・減色・画像の検査）"),
    ("配図の高清化（小さい・ぼやけた図）", "rule", "AI の超解像は使わない。看不清かは「引き伸ばす倍率」と「表示サイズでの模糊度（re-blur 法）」の 2 つの数で決め、看得清の図は触らない"),
    ("AI 編集：同じ件を合わせて、どれを載せるか", "gate", "意味の判断（違う言語の同じ件・重要度）は規則だと外れが多いので、版面に載るのは AI が整理した記事だけ。収集で整理待ちが増えたときだけ起こす（最多 2 時間に 1 回）"),
    ("言語違いの同じニュースを 1 本に（主言語を残す）", "rule", "AI 編集にも頼むが、すり抜け・号をまたぐ分は規則で：言語の判定は文字の種類、同じかはバージョン番号・月日・予定の日付（lang.py）"),
    ("AI 編集：配図を目で選ぶ", "gate", "候補の検査は規則、顔や内容が切れていないかの最後の確認は AI。2026-10-19 から重大・頭の記事だけ（ほかは規則）、一覧も小さく（1 枚 ≈ 1,500 → 570 トークン）"),
    ("AI 編集：読む一覧", "rule", "inbox の JSON をそのまま読まず、edit-brief（番号・日付・出典・題・要約 120 字、網址なし）で半分以下の量に。出来事ごとに束ね（bundle.py）、前回のあとは増えた束だけ"),
    ("写真から愿望：写っている物の認識", "gate", "画像の中身の認識はモデルが要る（Claude が見る）。写真が来たときだけ起こす"),
    ("新しい関注項の板块・小分類を決める", "rule", "板块は sections.yaml に先に全部決めてある（IAB の大類から 17）。維基データの説明・名前の語で対号入座し、新しい板块は作らない"),
    ("新しい関注項の版面の設計（テーマ・配色・小元素の種類）", "ai", "作品の気質の判断。type から借りる既定値は規則であるので、AI は新しい関注項が入ったときだけ"),
    ("関注項の完善（match の正規表現・誤収の確認）", "ai", "言葉の意味の判断。audit-match（どの語で入ったかの一覧）は規則で出し、直すのは AI"),
]
AI_STATE_JA = {"rule": "規則にした（AI なし）", "gate": "AI のまま · 仕事があるときだけ", "ai": "AI のまま"}

EDGE_JA = {"data": "収集", "web": "網页", "ai": "AI", "notify": "Discord", "db": "データベース"}


def _chips(ids):
    """部品（モデル・アルゴリズム・API）の札。名前と数字（大きさ・しきい値・同時にいくつ）。"""
    out = []
    for cid in ids or []:
        c = COMPONENTS.get(cid)
        if not c:
            continue
        out.append(f'<span class="cp cp-{e(c["kind"])}" title="{e(c.get("what", ""))}"><em>{e(KIND_LABEL[c["kind"]])}</em>'
                   f'<b>{e(c["name"])}</b>' + (f'<i>{e(c["spec"])}</i>' if c.get("spec") else "") + "</span>")
    return f'<span class="cps">{"".join(out)}</span>' if out else ""


def _own(p):
    """構成図のプロセスの箱に出す札：その仕組み自身のアルゴリズム・ルール（と Claude）。API は外のサービスの箱、
    画像のモデルは「画像のモデル」の箱に出しているので、ここでは重ねない（流れの図には全部出る）。"""
    return [c for c in p.get("uses", []) if c in COMPONENTS and (COMPONENTS[c]["kind"] in ("algo", "rule") or c in ("claude", "claude-api"))]


def _arch_node(n, by):
    if n.get("proc"):
        p = by[n["proc"]]
        subs = "".join(
            f'<button type="button" class="an-sub" id="p-{e(q["id"])}" data-open="proc-{e(q["id"])}">＋ {e(q["name"])}'
            f'<small>{e(q.get("when", ""))}</small>{_by_sum(q)}{_chips(_own(q))}</button>'
            for q in (by.get(x) for x in n.get("subs", [])) if q)
        return (f'<div class="an an-p" id="{e(n["id"])}"><button type="button" class="an-b" data-open="proc-{e(p["id"])}">'
                f'<b>{e(p["name"])}</b><small>{e(p.get("when", ""))}</small>{_by_sum(p)}{_chips(_own(p))}<i>流れの図を見る ›</i></button>{subs}</div>')
    return (f'<div class="an an-s{" an-m" if n.get("model") else ""}" id="{e(n["id"])}"><b>{e(n["label"])}</b>'
            f'<small>{e(n["text"])}</small>{_chips(n.get("uses"))}</div>')


def _arch_zone(z, by):
    head = (f'<div class="az-h"><b>{e(z["title"])}</b><small>{e(z.get("note", ""))}</small>'
            + (f'<span class="az-c{" ai" if "サブスク" in z.get("cost", "") else ""}">{e(z["cost"])}</span>' if z.get("cost") else "") + "</div>")
    inner = "".join(_arch_node(n, by) for n in z.get("nodes", []))
    return f'<section class="az az-{e(z["style"])}" style="grid-area:{e(z["id"])}" data-z="{e(z["id"])}">{head}<div class="az-b">{inner}</div></section>'


def _edges_json(edges):
    return json.dumps(edges, ensure_ascii=False).replace("</", "<\\/")


def architecture(processes=None):
    """全体の構成図：どの仕組みがどこで動き、データがどう流れるか。部品には使うモデル・アルゴリズムと数字の札。
    プロセスの部品をクリックすると、その流れの図（detail）が開く。矢印は JS（DG）が部品の位置から描く。"""
    by = {p["id"]: p for p in PROCESSES + list(processes or [])}   # 図の部品はいつもの PROCESSES から
    placed = {n.get("proc") for z in ARCH for n in z["nodes"]} | {x for z in ARCH for n in z["nodes"] for x in n.get("subs", [])}
    extra = [p for p in PROCESSES if p["id"] not in placed]   # ARCH にまだ置いていない仕組みは「そのほか」に（図から開けないものを作らない）
    zones = "".join(_arch_zone(z, by) for z in ARCH + ([{"id": "etc", "title": "そのほかの仕組み", "note": "図の場所がまだ決まっていないもの",
                                                           "style": "keep", "nodes": [{"id": f"p-{p['id']}", "proc": p["id"]} for p in extra]}] if extra else []))
    legend = "".join(f'<span class="ae-{k}"><i></i>{e(v)}</span>' for k, v in EDGE_JA.items())
    kinds = "".join(f'<span class="cp cp-{k}"><em>{e(v)}</em></span>' for k, v in KIND_LABEL.items())
    names = {}
    for z in ARCH:
        for n in z["nodes"]:
            names[n["id"]] = by[n["proc"]]["name"] if n.get("proc") else n["label"]
            for x in n.get("subs", []):
                names[f"p-{x}"] = by[x]["name"]
    lst = "".join(f'<li class="ae-{c}"><em>{i}</em>{e(names[a])} → {e(names[b])}<small>{e(t)}</small></li>' for i, a, b, t, c in EDGES)
    return (f'<p class="arch-lg"><span class="lg-z temp">破線 = その都度立ち上がる環境</span><span class="lg-z keep">実線 = ずっと残る場所</span>{legend}'
            f'<span class="lg-k">{kinds} = 使っているモデル・アルゴリズム・API（数字つき）</span>'
            f'<span class="lg-by">{_by_tag("ai")} = Claude が判断（トークンを使う） {_by_tag("rule")} = プログラムの規則 {_by_tag("model")} = 学習済みモデルの数値で規則どおりに判断</span>'
            '<span>番号の矢印 = データの流れ · 四角い部品をクリックで流れの図</span></p>'
            f'<div class="arch dgb" id="arch" data-edges="arch-edges"><svg class="dg-svg" aria-hidden="true"></svg>{zones}</div>'
            f'<details class="arch-list"><summary>矢印の一覧（{len(EDGES)}）</summary><ol>{lst}</ol></details>'
            f'<script type="application/json" id="arch-edges">{_edges_json([list(x) for x in EDGES])}</script>')


# だれが決めるか：AI（Claude が見て・読んで判断）か、規則（プログラム。学習済みモデルの数値を使うものも、決め方は規則）
BY = {"ai": ("AI が判断", "Claude が読んで・見て決める（トークンを使う）"),
      "model": ("ルール＋モデル", "学習済みモデル（顔・切り抜き）の数値を、決まったしきい値で判断する。AI の判断ではない"),
      "rule": ("ルール", "プログラムの規則・計算で決まる（AI なし・無料）")}


def judged_by(n):
    """流れの図の 1 手順を、だれが決めるか。by を書いていればそれ。保存先は手順ではないので None。
    使う部品に Claude があれば ai、学習済みモデル（rembg・YuNet・SFace…）があれば model、それ以外は rule。"""
    if n.get("by"):
        return n["by"]
    if n["kind"] == "store":
        return None
    uses = list(n.get("uses", [])) + [it[3] for it in n.get("items", []) if len(it) > 3]
    if {"claude", "claude-api"} & set(uses):
        return "ai"
    if any(COMPONENTS.get(c, {}).get("kind") == "model" for c in uses):
        return "model"
    return "rule"


def _by_tag(by):
    if not by:
        return ""
    label, what = BY[by]
    return f'<span class="by by-{by}" title="{e(what)}">{e(label)}</span>'


def by_count(p):
    """→ {"ai": n, "rule": n}（model は rule に数える：決め方は規則）。"""
    out = {"ai": 0, "rule": 0}
    for n in p["flow"]:
        b = judged_by(n)
        if b:
            out["ai" if b == "ai" else "rule"] += 1
    return out


def _by_sum(p):
    """構成図の箱に出す「AI n · ルール n」。"""
    n = by_count(p)
    ai = f'<span class="by by-ai">AI {n["ai"]}</span>' if n["ai"] else '<span class="by by-none">AI なし</span>'
    return f'<span class="by-sum">{ai}<span class="by by-rule">ルール {n["rule"]}</span></span>'


def _by_legend(p=None):
    n = by_count(p) if p else None
    cnt = (lambda k: f'<b>{n[k]}</b>') if n else (lambda k: "")
    return (f'<p class="by-lg">{_by_tag("ai")}{cnt("ai")}<small>{e(BY["ai"][1])}</small>'
            f'{_by_tag("rule")}{cnt("rule")}<small>{e(BY["rule"][1])}</small>'
            f'{_by_tag("model")}<small>{e(BY["model"][1])}</small></p>')


def _ex_fig(f, cap, cls=""):
    import emblem_rules
    return (f'<figure class="ex-f{cls}"><span class="ex-i"><img src="{e(emblem_rules.EX + f)}.webp" alt="{e(cap)}" loading="lazy" decoding="async"></span>'
            f'<figcaption>{e(cap)}</figcaption></figure>')


def examples_panel(names=None):
    """管理ページ「小元素の判断の例」：判断ごとに、本物の画像で 前 → 後（使わなかったものは「外す」の札）。
    names = 今の関注清单の名前：今ある版面の例だけ出す。"""
    import emblem_rules
    by_rule = {r["title"]: r for r in emblem_rules.rules()}
    cards = []
    for x in emblem_rules.EXAMPLES:
        if names is not None and not any(n in names for n in re.split(r"\s*[·・（）()]\s*", x["item"]) if n):
            continue
        r = by_rule[x["rule"]]
        before = "".join(_ex_fig(f, c) for f, c in x["before"])
        after = ("".join(_ex_fig(f, c, " ex-ok") for f, c in x["after"]) if x["after"]
                 else '<figure class="ex-f ex-no"><span class="ex-i"><b>外す</b></span><figcaption>使わない</figcaption></figure>')
        cards.append(f'<article class="ex ex-{e(r["by"])}"><header>{_by_tag(r["by"])}<b>{e(r["title"])}</b><small>{e(r["stage"])} · {e(x["item"])}</small></header>'
                     f'<div class="ex-row"><div class="ex-side"><em>前</em>{before}</div><span class="ex-arrow" aria-hidden="true">→</span>'
                     f'<div class="ex-side"><em>後</em>{after}</div></div>'
                     f'<p class="ex-v">{e(x["verdict"])}<small>{e(r["rule"])}</small></p></article>')
    if not cards:
        return '<p class="ex-none">いまの関注項にはまだ例がありません。判断の規則は下の「判断の一覧」。</p>'
    return f'<div class="exs">{"".join(cards)}</div>'


def rules_table(kind):
    """判断の一覧（emblem_rules.py が 1 つだけの元）を、段ごとに AI / ルールの札つきの表にする。"""
    if kind != "emblem":
        return ""
    import emblem_rules
    rows, cur = [], None
    for r in emblem_rules.rules():
        if r["stage"] != cur:
            cur = r["stage"]
            rows.append(f'<tr class="rt-s"><th colspan="3">{e(cur)}</th></tr>')
        rows.append(f'<tr class="rt-{e(r["by"])}"><td>{_by_tag(r["by"])}</td><td><b>{e(r["title"])}</b><small>{e(r["rule"])}</small></td>'
                    f'<td><code>{e(r["code"])}</code></td></tr>')
    n = {k: sum(1 for r in emblem_rules.rules() if r["by"] == k) for k in BY}
    return (f'<details class="rt" open><summary>判断の一覧（全部で {sum(n.values())}：AI が判断 {n["ai"]} · ルール {n["rule"] + n["model"]}）'
            f'<small>数はコードの定数をそのまま読んでいる（scripts/emblem_rules.py）</small></summary>'
            f'<div class="rt-w"><table><tbody>{"".join(rows)}</tbody></table></div></details>')


def _lane_tag(lane):
    name, cost, kind = LANES.get(lane, (lane, "", "free"))
    return f'<span class="pl pl-{kind}">{e(name)}</span>'


def _dg_node(pid, n, row, col, ncols):
    """流れの図の 1 つの部品（手順・判断・並べて試す・表・保存先）。"""
    k, nid = n["kind"], f'dg-{pid}-{n["id"]}'
    badge = f'<span class="dn-x">{e(n["x"])}</span>' if n.get("x") else ""
    by = judged_by(n)
    head = f'{_by_tag(by)}<b class="dn-t">{e(n["title"])}</b>{badge}'
    text = f'<small class="dn-s">{e(n["text"])}</small>' if n.get("text") else ""
    span = f"grid-row:{row};grid-column:{'1 / -1' if k in ('fan', 'table') else col}"
    lane = f'<span class="dn-l">{e(LANES.get(n.get("lane"), (n.get("lane") or "",))[0])}</span>'
    if k == "fan":
        items = "".join(
            f'<li id="{nid}-{j}"><i>{e(it[0])}</i><b>{e(it[1])}</b><small>{e(it[2])}</small>{_chips(it[3:4] and [it[3]])}</li>'
            for j, it in enumerate(n["items"]))
        mode = n.get("mode", "上から順に · 足りるまで")
        return (f'<div class="dn dn-fan dn-by-{by}" id="{nid}" style="{span}">{lane}<div class="dn-h">{head}<span class="dn-m">{e(mode)}</span></div>'
                f'{text}<ol class="dn-row">{items}</ol>{_chips(n.get("uses"))}</div>')
    if k == "table":
        rows = "".join(f'<div class="dt-c"><b>{e(a)}</b><span>{e(b)}</span></div>' for a, b in n["rows"])
        return f'<div class="dn dn-table dn-by-{by}" id="{nid}" style="{span}">{lane}<div class="dn-h">{head}</div>{text}<div class="dt">{rows}</div>{_chips(n.get("uses"))}</div>'
    shape = {"decision": "dn-dec", "store": "dn-store"}.get(k, "dn-step")
    inner = f'{lane}<div class="dn-h">{head}</div>{text}{_chips(n.get("uses"))}'
    if k == "decision":
        yes = f'<small class="dn-s dn-yes">はい → {e(n["yes"])}</small>' if n.get("yes") else ""
        inner = (f'{lane}<div class="dn-dia"><span>{head}</span></div>'   # ひし形には問いだけ。条件と「はい」の行き先は下に
                 + (f'<div class="dn-cap">{text}{yes}</div>' if text or yes else "") + _chips(n.get("uses")))
    out = f'<div class="dn {shape} dn-by-{by}" id="{nid}" style="{span}">{inner}</div>'
    if k == "decision":   # いいえ の行き先：となりの列に小さな箱
        bcol = ncols
        out += f'<div class="dn dn-no" id="{nid}-no" style="grid-row:{row};grid-column:{bcol}"><i>いいえ</i><span>{e(n["no"])}</span></div>'
    return out


def flow_diagram(p):
    """プロセスの流れを図にする：列 = どこで動くか（レーン）、行 = 順番。判断はひし形（はい = 下へ、いいえ = 右の箱へ）、
    「上から順に試す / 並列」は横に並べた箱、使うモデル・アルゴリズムは札。矢印は JS（DG）が描く。"""
    pid, flow = p["id"], p["flow"]
    lanes = []
    for n in flow:
        if n.get("lane") not in lanes:
            lanes.append(n.get("lane"))
    has_no = any(n["kind"] == "decision" for n in flow)
    ncols = len(lanes) + (1 if has_no else 0)
    heads = "".join(f'<div class="dg-lh" style="grid-column:{i + 1}">{_lane_tag(l)}</div>' for i, l in enumerate(lanes))
    if has_no:
        heads += f'<div class="dg-lh dg-lh-no" style="grid-column:{ncols}"><span class="pl">分かれ道</span></div>'
    cells, edges = [], []
    for i, n in enumerate(flow):
        cells.append(_dg_node(pid, n, i + 2, lanes.index(n.get("lane")) + 1, ncols))
        nid = f'dg-{pid}-{n["id"]}'
        if i + 1 < len(flow):
            label = "はい" if n["kind"] == "decision" else (n.get("out") or "")
            edges.append([None, nid, f'dg-{pid}-{flow[i + 1]["id"]}', label, "ai" if n.get("lane") == "ai" else "data", 0])
        if n["kind"] == "decision":
            edges.append([None, nid, f"{nid}-no", "いいえ", "web", 1])
            if n.get("no_to"):
                edges.append([None, f"{nid}-no", f'dg-{pid}-{n["no_to"]}', "戻る", "web", 1])
    cols = " ".join(["minmax(0,1fr)"] * len(lanes) + (["minmax(120px,.7fr)"] if has_no else []))
    eid = f"dge-{pid}"
    return (f'<div class="dg dgb" data-edges="{eid}" style="grid-template-columns:{cols}"><svg class="dg-svg" aria-hidden="true"></svg>'
            f'{heads}{"".join(cells)}</div><script type="application/json" id="{eid}">{_edges_json(edges)}</script>')


def detail(p):
    lane = LANES.get(p["lane"], (p["lane"], "", "free"))
    files = " ".join(f"<code>{e(f)}</code>" for f in p.get("files", []))
    return (f'<dialog class="pdlg" id="proc-{e(p["id"])}" aria-label="{e(p["name"])}の流れ">'
            f'<div class="pd-h"><div><small>{e(p["en"])}</small><h3>{e(p["name"])}</h3></div>'
            f'<button type="button" class="pd-x" data-close aria-label="閉じる">×</button></div>'
            f'<p class="pd-sum">{e(p["summary"])}</p>'
            f'<div class="pd-meta"><span><b>いつ</b>{e(p["trigger"])}</span>'
            f'<span><b>どこで</b>{e(lane[0])}</span><span><b>費用</b>{e(lane[1])}</span></div>'
            + (f'<div class="pd-uses"><b>使うもの</b>{_chips(p.get("uses"))}</div>' if p.get("uses") else "")
            + f'{_by_legend(p)}{flow_diagram(p)}{rules_table(p.get("rules"))}<p class="pd-files"><b>仕組みの場所</b>{files}</p></dialog>')


def render(processes=None):
    """管理ページに入れる HTML（全体の構成図 + 各プロセスの流れの図のダイアログ）。"""
    processes = processes or PROCESSES
    return architecture(processes) + "".join(detail(p) for p in processes)


CSS = """
.arch-lg{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 12px;font:500 var(--fs-label)/1.6 var(--font-sans)}
.arch-lg span{display:inline-flex;align-items:center;gap:6px}
.arch-lg i{display:inline-block;width:22px;height:0;border-top:3px solid currentColor}
.lg-z{padding:0 8px;border:2px dashed var(--ink)}.lg-z.keep{border-style:solid}
.ae-data{color:var(--ink)}.ae-web{color:var(--rose)}.ae-ai{color:var(--good)}.ae-notify{color:var(--discord)}.ae-db{color:var(--viz-1)}
.arch{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
 grid-template-areas:"src act act ai" "db act act repo" "pages act act dc" "etc etc etc etc" "you you you you";gap:40px 64px;align-items:start}
.az[data-z=act]>.az-b{display:block;column-count:2;column-gap:12px}   /* 仕組みが 7 つで一番高い枠：2 列・2 段ぶん使い、ほかの枠が下へ押されない（2026-10-25 1 列だと 5,129px） */
.az[data-z=act]>.az-b>.an{break-inside:avoid;margin:0 0 10px}
.az{border:2px solid var(--ink);background:var(--paper);padding:10px 12px 12px;min-width:0}
.az-temp{border-style:dashed;background:var(--sheet)}
.az-ext{border-style:dotted;border-width:3px}
.az-you{background:var(--ink);color:var(--card);border-color:var(--ink)}
.az-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;margin-bottom:10px}
.az-h b{font:900 15px/1.3 var(--font-sans)}.az-h small{font:500 var(--fs-label)/1.4 var(--font-sans);opacity:.8;flex:1 1 auto}
.az-c{font:700 var(--fs-label) var(--font-mono);padding:0 7px;background:var(--good);color:var(--card);transform:skewX(var(--skew))}
.az-c.ai{background:var(--gold);color:var(--ink)}
.az-b{display:flex;flex-direction:column;gap:10px}
.az[data-z=you]>.az-b{flex-direction:row}
.an{position:relative;z-index:3;background:var(--card);color:var(--ink);border:2px solid var(--ink);min-width:0}
.an-s{padding:7px 10px;display:flex;flex-direction:column;gap:2px}
.an-s b{font:900 13px/1.35 var(--font-mono);overflow-wrap:anywhere}.an-s small{font:500 var(--fs-label)/1.45 var(--font-sans);opacity:.85}
.an-p{box-shadow:var(--shadow);transition:transform .1s,box-shadow .1s}
.an-p:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
.an-b,.an-sub{all:unset;box-sizing:border-box;display:flex;flex-direction:column;gap:2px;width:100%;padding:9px 11px;cursor:pointer}
.an-b b{font:900 14px/1.35 var(--font-sans)}.an-b small,.an-sub small{font:500 var(--fs-label)/1.45 var(--font-sans);opacity:.85}
.an-b>i{font:700 var(--fs-label) var(--font-sans);font-style:normal;color:var(--rose)}
.an-sub{border-top:1.5px dashed var(--ink);font:700 12px/1.4 var(--font-sans);background:var(--sheet)}
.an-b:focus-visible,.an-sub:focus-visible{outline:3px solid var(--gold);outline-offset:-3px}
.an-b:hover b,.an-sub:hover{text-decoration:underline}
.az-you .an{background:transparent;color:var(--card);border-color:var(--card)}
.arch .hl{outline:3px solid var(--gold);outline-offset:2px}
.arch .cp{overflow-wrap:anywhere;min-width:0}
.arch .cp i{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}   /* 図では 3 行まで。全文は札の title と流れの図 */
.arch-list{margin-top:14px;font-size:13px}.arch-list summary{cursor:pointer;font:700 13px var(--font-sans)}
.arch-list ol{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:4px 16px}
.arch-list li{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;padding:4px 0;border-bottom:1px solid var(--hair);color:var(--ink)}
.arch-list li em{font:900 11px var(--font-mono);font-style:normal;min-width:22px;text-align:center;color:var(--card);background:currentColor;border-radius:50%}
.arch-list li.ae-data em{background:var(--ink)}.arch-list li.ae-web em{background:var(--rose)}.arch-list li.ae-ai em{background:var(--good)}
.arch-list li.ae-notify em{background:var(--discord)}.arch-list li.ae-db em{background:var(--viz-1)}
.arch-list li em{color:var(--card)}.arch-list li small{font-size:var(--fs-label);opacity:.8}
.az-you{grid-column:1/-1}.az[data-z=etc]{grid-column:1/-1}.az[data-z=etc]>.az-b{flex-direction:row;flex-wrap:wrap}
@media (max-width:980px){
 .arch{grid-template-columns:minmax(0,1fr);grid-template-areas:"src" "act" "repo" "ai" "db" "pages" "dc" "etc" "you";gap:16px}
 .arch .dg-svg{display:none}
 .az[data-z=you]>.az-b{flex-direction:column}
 .az[data-z=act]>.az-b{column-count:1}
}
.pl{display:inline-block;align-self:flex-start;font:700 10px var(--font-mono);letter-spacing:.04em;padding:1px 8px;transform:skewX(var(--skew));background:var(--ink);color:var(--card);white-space:nowrap}
.pl-ai{background:var(--gold);color:var(--ink)}.pl-free{background:var(--good);color:var(--card)}
.pdlg{width:min(1100px,calc(100vw - 24px));max-height:calc(100vh - 24px);padding:0;border:3px solid var(--ink);box-shadow:8px 8px 0 var(--ink);background:var(--paper);color:var(--ink)}
.pdlg::backdrop{background:rgba(26,28,34,.55)}
.pd-h{display:flex;justify-content:space-between;gap:12px;padding:14px 18px;background:var(--ink);color:var(--card);position:sticky;top:0;z-index:2}
.pd-h small{font:700 10px var(--font-mono);letter-spacing:.3em;opacity:.7}
.pd-h h3{margin:0;font:900 22px/1.3 var(--font-sans)}
.pd-x{font:900 22px/1 var(--font-sans);background:none;border:2px solid var(--card);color:var(--card);width:38px;height:38px;cursor:pointer}
.pd-x:hover{background:var(--alert);border-color:var(--alert)}
.pd-sum{margin:0;padding:14px 18px 6px;font-size:14px;line-height:1.7}
.pd-meta{display:flex;flex-wrap:wrap;gap:6px 18px;padding:0 18px 14px;font-size:13px}
.pd-meta b{font:700 10px var(--font-mono);letter-spacing:.15em;margin-right:6px;padding:1px 6px;background:var(--ink);color:var(--card)}
.pd-files{margin:0;padding:6px 18px 16px;font-size:12px;display:flex;gap:6px 10px;flex-wrap:wrap;align-items:baseline}
.pd-files b{font:700 10px var(--font-mono);letter-spacing:.15em}
.pd-files code{font:700 11px var(--font-mono);background:var(--card);border:1px solid var(--ink);padding:0 6px}
@media (max-width:640px){.pdlg{width:100vw;max-width:100vw;height:100vh;max-height:100vh;margin:0;border-width:0}}
.dgb{position:relative}
.dg-svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;z-index:2}
.dg-svg path{fill:none;stroke-width:2.2}.dg-svg .dash{stroke-dasharray:6 4}
.dg-svg .dim{opacity:.15}
.dg-svg text{font:900 11px var(--font-mono);fill:var(--card);text-anchor:middle;dominant-baseline:central}
.dg-svg .lbl rect{fill:var(--card);stroke:currentColor;stroke-width:1.5}.dg-svg .lbl text{fill:currentColor;font:700 11px var(--font-sans)}
.cps{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.cp{display:inline-flex;flex-wrap:wrap;align-items:baseline;gap:0 6px;max-width:100%;padding:2px 7px;border:1.5px solid var(--ink);background:var(--paper);
 font:500 var(--fs-label)/1.45 var(--font-sans);color:var(--ink);text-align:left}
.cp em{font:900 var(--fs-tag)/1.6 var(--font-mono);font-style:normal;letter-spacing:.06em;padding:0 4px;color:var(--card);background:var(--ink)}
.cp b{font:700 var(--fs-label)/1.45 var(--font-mono)}.cp i{font-style:normal;opacity:.85}
.cp-model em{background:var(--rose)}.cp-algo em{background:var(--good)}.cp-api em{background:var(--viz-1)}.cp-rule em{background:var(--ink)}
.cp-model{border-color:var(--rose)}
.lg-k{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px}.lg-k .cp{padding:0 2px}
.an-m{border-color:var(--rose);border-width:3px}
.pd-uses{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;padding:0 18px 12px}
.pd-uses>b{font:700 10px var(--font-mono);letter-spacing:.15em;padding:1px 6px;background:var(--ink);color:var(--card)}
.pd-uses .cps{margin:0}
/* だれが決めるか：AI（紫・太枠・斜線の帯）とルール（緑・左の帯）。ひと目で分かるように枠ごと色を変える */
.by{display:inline-block;align-self:flex-start;font:900 var(--fs-label)/1.5 var(--font-sans);padding:0 8px;letter-spacing:.04em;
 transform:skewX(var(--skew));white-space:nowrap}
.by-ai{background:var(--by-ai);color:var(--card)}
.by-rule{background:var(--by-rule);color:var(--card)}
.by-model{background:var(--card);color:var(--by-rule);border:2px solid var(--by-rule)}
.by-none{background:var(--card);color:var(--ink);border:1.5px dashed var(--ink)}
.dn-h>.by{order:-1;flex-basis:100%;width:max-content}
.dn.dn-by-ai{border:4px solid var(--by-ai);box-shadow:6px 6px 0 var(--by-ai);
 background:repeating-linear-gradient(-45deg,color-mix(in srgb,var(--by-ai) 9%,var(--card)) 0 8px,var(--card) 8px 16px)}
.dn.dn-by-rule,.dn.dn-by-model{border-left:8px solid var(--by-rule)}
.dn-dec.dn-by-ai .dn-dia::before{background:color-mix(in srgb,var(--by-ai) 35%,var(--gold))}
.dn-dec.dn-by-rule,.dn-dec.dn-by-model{border-left:0}
.dn-dia .by{margin-bottom:3px}
.by-lg{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0;padding:0 18px 12px;font-size:12px}
.by-lg b{font:900 15px var(--font-num);margin-right:2px}.by-lg small{font:500 var(--fs-label)/1.4 var(--font-sans);margin-right:10px}
.lg-by{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px 6px}
.by-sum{display:flex;gap:4px;margin:4px 0 2px}
.rt{margin:4px 18px 14px;border:2px solid var(--ink);background:var(--card)}
.rt summary{cursor:pointer;padding:8px 12px;font:900 14px var(--font-sans);display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.rt summary small{font:500 var(--fs-label) var(--font-sans);opacity:.8}
.rt-w{overflow-x:auto}
.rt table{width:100%;border-collapse:collapse;font-size:12px}
.rt td{padding:6px 10px;border-top:1px solid var(--hair);vertical-align:top}
.rt td:first-child{width:1%;white-space:nowrap}
.rt td b{display:block;font:900 13px/1.4 var(--font-sans)}.rt td small{display:block;font:500 12px/1.55 var(--font-sans)}
.rt td code{font:700 var(--fs-label) var(--font-mono);overflow-wrap:anywhere}
.rt-s th{text-align:left;padding:8px 10px 4px;font:900 13px var(--font-sans);background:var(--sheet);border-top:2px solid var(--ink)}
.rt-ai td{background:color-mix(in srgb,var(--by-ai) 10%,var(--card))}
.rt-ai td:first-child{box-shadow:inset 6px 0 0 var(--by-ai)}
.rt-rule td:first-child,.rt-model td:first-child{box-shadow:inset 6px 0 0 var(--by-rule)}
@media (max-width:640px){.rt td:last-child{display:none}}
/* 小元素の判断の例（前 → 後） */
.exs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:16px}
.ex{border:2px solid var(--ink);background:var(--card);box-shadow:var(--shadow);display:flex;flex-direction:column;min-width:0}
.ex.ex-ai{border-color:var(--by-ai)}
.ex header{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;padding:8px 10px;border-bottom:1.5px solid var(--hair)}
.ex header b{font:900 14px/1.35 var(--font-sans)}.ex header small{flex-basis:100%;font:500 var(--fs-label)/1.4 var(--font-sans);opacity:.8}
.ex-row{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:6px;padding:10px}
.ex-side{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start;min-width:0}
.ex-side>em{flex-basis:100%;font:900 var(--fs-label) var(--font-mono);font-style:normal;letter-spacing:.2em}
.ex-arrow{font:900 22px var(--font-mono);color:var(--rose)}
.ex-f{margin:0;flex:1 1 90px;min-width:0;display:flex;flex-direction:column;gap:3px}
.ex-i{display:grid;place-items:center;aspect-ratio:1;border:2px solid var(--alert);overflow:hidden;
 background:conic-gradient(var(--sheet) 25%,var(--card) 0 50%,var(--sheet) 0 75%,var(--card) 0) 0 0/14px 14px}
.ex-ok .ex-i{border-color:var(--by-rule)}
.ex-i img{max-width:100%;max-height:100%;object-fit:contain;display:block}
.ex-f figcaption{font:500 var(--fs-label)/1.45 var(--font-sans)}
.ex-no{flex:0 1 110px;align-self:center}
.ex-no .ex-i{border-style:dashed;background:var(--paper);aspect-ratio:auto;min-height:84px}
.ex-no b{font:900 20px var(--font-sans);color:var(--alert);transform:rotate(var(--tilt));border:3px solid var(--alert);padding:2px 10px}
.ex-v{margin:auto 0 0;padding:8px 10px 10px;border-top:1.5px solid var(--hair);font:700 13px/1.5 var(--font-sans)}
.ex-v small{display:block;font:500 var(--fs-label)/1.45 var(--font-sans);opacity:.8;margin-top:2px}
.dg{display:grid;gap:30px 26px;padding:6px 18px 18px;align-items:start}
.dg-lh{grid-row:1;position:sticky;top:66px;z-index:4;padding:4px 0;border-bottom:3px double var(--ink);background:var(--paper)}
.dg-lh-no .pl{background:var(--alert);color:var(--card)}
.dn{position:relative;z-index:3;background:var(--card);border:2px solid var(--ink);padding:8px 10px;min-width:0;box-shadow:var(--shadow)}
.dn-l{display:none;font:700 var(--fs-tag) var(--font-mono);letter-spacing:.06em;opacity:.7}
.dn-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px}
.dn-t{font:900 14px/1.35 var(--font-sans)}
.dn-x{font:700 var(--fs-label) var(--font-mono);padding:0 6px;background:var(--gold);color:var(--ink);transform:skewX(var(--skew))}
.dn-m{font:700 var(--fs-label) var(--font-sans);color:var(--rose)}
.dn-s{display:block;margin-top:3px;font:500 12px/1.55 var(--font-sans)}
.dn-store{border-radius:14px/10px;background:var(--sheet);box-shadow:none;border-style:solid}
.dn-dec{background:transparent;border:0;box-shadow:none;padding:0}
.dn-dia{position:relative;display:grid;place-items:center;min-height:84px;padding:14px 40px;text-align:center}
.dn-dia::before{content:"";position:absolute;inset:0;background:var(--gold);border:2px solid var(--ink);clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);z-index:-1}
.dn-dia::after{content:"";position:absolute;inset:-2px;background:var(--ink);clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%,0 50%,2.4% 50%,50% 97%,97.6% 50%,50% 3%,2.4% 50%,0 50%);z-index:-1}
.dn-dia span{display:block;max-width:220px}.dn-cap{margin:4px auto 0;max-width:340px;text-align:center}.dn-yes{color:var(--good);font-weight:700}.dn-dia .dn-t{font-size:13px}.dn-dia .dn-s{font-size:var(--fs-label)}
.dn-no{background:var(--paper);border:2px dashed var(--alert);box-shadow:none;font:500 12px/1.5 var(--font-sans);align-self:center}
.dn-no i{display:block;font:900 var(--fs-label) var(--font-mono);font-style:normal;color:var(--alert)}
.dn-fan,.dn-table{background:var(--paper)}
.dn-row{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}
.dn-row li{position:relative;padding:6px 8px;background:var(--card);border:1.5px solid var(--ink);display:flex;flex-direction:column;gap:1px;min-width:0}
.dn-row li:not(:last-child)::after{content:"›";position:absolute;right:-8px;top:50%;transform:translate(50%,-50%);font:900 14px var(--font-mono);color:var(--rose)}
.dn-row i{font:900 var(--fs-label) var(--font-mono);font-style:normal;color:var(--rose)}
.dn-row b{font:900 12px/1.3 var(--font-sans)}.dn-row small{font:500 var(--fs-label)/1.4 var(--font-sans);opacity:.85}
.dn-row .cps{margin-top:3px}.dn-row .cp i{display:none}
.dt{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:6px;margin-top:8px}
.dt-c{display:flex;flex-direction:column;padding:5px 8px;border:1.5px solid var(--ink);background:var(--card)}
.dt-c b{font:900 12px var(--font-sans)}.dt-c span{font:500 var(--fs-label)/1.45 var(--font-sans)}
@media (max-width:640px){
 .dg{grid-template-columns:minmax(0,1fr)!important;gap:26px}
 .dg-lh{display:none}.dn-l{display:block}
 .dg>.dn{grid-column:1!important;grid-row:auto!important}
 .dn-row{grid-template-columns:repeat(2,minmax(0,1fr))}
 .dn-row li::after{display:none}
 .dg>.dn-no{justify-self:end;width:46%}
}
"""

JS = """
(() => {
  // 図の矢印（全体の構成図・流れの図で共通）：data-edges の JSON = [番号 or null, 元の id, 先の id, 説明, 色, 破線]。
  // 部品の位置から直角に折れる線を描く。番号は丸、番号なしは説明の札。部品にマウスを乗せると関係する線だけ濃く
  const COL = {data: 'var(--ink)', web: 'var(--rose)', ai: 'var(--good)', notify: 'var(--discord)', db: 'var(--viz-1)'};
  const esc = t => String(t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const draw = box => {
    const svg = box.querySelector(':scope > .dg-svg'), data = document.getElementById(box.dataset.edges);
    if (!svg || !data || getComputedStyle(svg).display === 'none' || !box.offsetWidth) return;
    const B = box.getBoundingClientRect(), EDGES = JSON.parse(data.textContent), seen = {}, placed = [];
    svg.setAttribute('viewBox', `0 0 ${B.width} ${B.height}`);
    const defs = '<defs>' + Object.keys(COL).map(k => `<marker id="ah-${k}-${box.dataset.edges}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" style="fill:${COL[k]};stroke:none"/></marker>`).join('') + '</defs>';
    const out = EDGES.map(([n, a, b, label, c, dash]) => {
      const A = document.getElementById(a), Z = document.getElementById(b);
      if (!A || !Z || !A.offsetWidth || !Z.offsetWidth) return '';
      const r1 = A.getBoundingClientRect(), r2 = Z.getBoundingClientRect();
      const s = {l: r1.left - B.left, r: r1.right - B.left, t: r1.top - B.top, b: r1.bottom - B.top};
      const d = {l: r2.left - B.left, r: r2.right - B.left, t: r2.top - B.top, b: r2.bottom - B.top};
      const key = [a, b].sort().join('|'), off = (seen[key] = (seen[key] || 0) + 1) > 1 ? 14 : 0;   // 行きと帰りは少しずらす
      let p, mx, my;
      if (s.r + 8 < d.l || d.r + 8 < s.l) {   // 左右に離れている：横から出て、真ん中で縦に折れる
        const x1 = s.r < d.l ? s.r : s.l, x2 = s.r < d.l ? d.l : d.r;
        const y1 = (s.t + s.b) / 2 + off, y2 = (d.t + d.b) / 2 + off;
        mx = (x1 + x2) / 2 + off; my = (y1 + y2) / 2;
        p = `M${x1} ${y1}H${mx}V${y2}H${x2}`;
      } else {   // 上下：縦に出て、真ん中で横に折れる
        const down = s.b < d.t, y1 = down ? s.b : s.t, y2 = down ? d.t : d.b;
        const x1 = (Math.max(s.l, d.l) + Math.min(s.r, d.r)) / 2 + off, x2 = x1;   // 重なっている幅の真ん中をまっすぐ
        my = (y1 + y2) / 2; mx = x1;
        p = (Math.min(s.r, d.r) - Math.max(s.l, d.l) > 20) ? `M${x1} ${y1}V${y2}`
          : `M${(s.l + s.r) / 2 + off} ${y1}V${my}H${(d.l + d.r) / 2 + off}V${y2}`;
      }
      while (placed.some(([x, y]) => Math.abs(x - mx) < 24 && Math.abs(y - my) < 20)) my += 22;   // 札が重ならないように
      placed.push([mx, my]);
      const tag = n != null ? `<circle cx="${mx}" cy="${my}" r="10" style="fill:${COL[c]}"/><text x="${mx}" y="${my}">${n}</text>`
        : (label ? `<g class="lbl" style="color:${COL[c]}"><rect x="${mx - (label.length * 6 + 8)}" y="${my - 9}" width="${label.length * 12 + 16}" height="18" rx="9"/><text x="${mx}" y="${my}">${esc(label)}</text></g>` : '');
      return `<g data-a="${a}" data-b="${b}"><path class="${dash ? 'dash' : ''}" d="${p}" style="stroke:${COL[c]}" marker-end="url(#ah-${c}-${box.dataset.edges})"/>${tag}<title>${n != null ? n + '. ' : ''}${esc(label)}</title></g>`;
    });
    svg.innerHTML = defs + out.join('');
  };
  const all = () => document.querySelectorAll('[data-edges]').forEach(draw);
  document.querySelectorAll('[data-edges]').forEach(box => {
    const svg = box.querySelector(':scope > .dg-svg');
    box.querySelectorAll('.an,.dn').forEach(n => {
      n.addEventListener('mouseenter', () => svg && svg.querySelectorAll('g[data-a]').forEach(g => g.classList.toggle('dim', g.dataset.a !== n.id && g.dataset.b !== n.id)));
      n.addEventListener('mouseleave', () => svg && svg.querySelectorAll('g[data-a]').forEach(g => g.classList.remove('dim')));
    });
    if (window.ResizeObserver) new ResizeObserver(() => draw(box)).observe(box);
  });
  all(); addEventListener('resize', all); if (document.fonts) document.fonts.ready.then(all);
  document.addEventListener('click', ev => {
    const open = ev.target.closest('[data-open]');
    if (open) { const d = document.getElementById(open.dataset.open); if (d && d.showModal) { d.showModal(); d.querySelectorAll('[data-edges]').forEach(draw); } return; }
    if (ev.target.closest('[data-close]')) { const d = ev.target.closest('dialog'); if (d) d.close(); return; }
    if (ev.target.tagName === 'DIALOG') ev.target.close();   // 外側（暗い部分）をクリックしても閉じる
  });
})();
"""


def slots(p):
    """→ そのプロセスの定時（UTC の [時, 分] のリスト）。別のプロセスと同じ回に動くものはそちらの時刻。"""
    sch = p.get("schedule")
    if isinstance(sch, str):
        sch = next((q.get("schedule") for q in PROCESSES if q["id"] == sch), None)
    return sorted([list(x) for x in sch]) if isinstance(sch, list) else []
