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
    "pose": {"kind": "model", "name": "YOLOv8m-pose（ultralytics）", "spec": "53MB · 目・足首の確かさ ≥ 0.5 · なければ輪郭から推定（Actions には入れていない）",
             "what": "全身の立ち絵の目の高さと足の裏・重心を測り、背の高さをそろえてから腰のあたり（目から足の 40%）で上半身に切る（emblem.body_marks / bust_from_body）"},
    "haar": {"kind": "model", "name": "OpenCV Haar frontalface + LBP animeface", "spec": "scale 1.1 · minNeighbors 4〜5",
             "what": "切り抜きの構図と顔の位置（emblem.face_box / face_crop）。顔モデルがないときの代わり"},
    "claude": {"kind": "model", "name": "Claude（定時タスク）", "spec": "編集・写真の認識・一覧の目視 · サブスク枠",
               "what": "AI 編集・写真から愿望・小元素の要確認を、画面を見て判断する"},
    "claude-api": {"kind": "model", "name": "Claude API claude-haiku-5-5", "spec": "summarize: false（いまは使わない）· 4000 tokens",
                   "what": "Actions から編集するときだけ（digest.edit_stories）。使ったトークンは数える"},
    # ---- アルゴリズム
    "pace": {"kind": "algo", "name": "サイトごとの間隔（全スレッド共有）", "spec": "Reddit 2 秒 · Google / Bing 0.5 秒 · Wikimedia 同じホスト 1 本ずつ・1.3 秒 + 全体 0.4 秒（毎分 150）",
             "what": "sources._pace / wikihttp.get。並列でもサイトから見た間隔は同じ"},
    "wikiua": {"kind": "rule", "name": "Wikimedia の決まり（wikihttp）", "spec": "UA「WishlistEmblemBot/1.1 (repo; Issues) python-requests」· api.php に maxlag=5 · "
               "429 / 503 / maxlag は Retry-After（なければ 5・15・45 秒）で 3 回まで · Retry-After > 120 秒か続く 429 → そのホスト 5 分休む · titles は 50 件ずつ",
               "what": "scripts/wikihttp.py。ブラウザのふりの UA（Mozilla/…）は 403、名乗らないと毎分 10 回まで。守ったボットは全サイト合わせて毎分 200"},
    "httpcache": {"kind": "algo", "name": "requests-cache（SQLite）", "spec": "~/.cache/wishlist-http · api.php 3 日 · 画像 14 日 · 200 だけ（maxlag の断りは残さない）",
                  "what": "同じ網址は取り直さない。Actions では actions/cache で次の回へ持ち越す"},
    "dedupe": {"kind": "algo", "name": "タイトルの重複判定", "spec": "完全一致 + 文字 bigram 重なり > 0.75 · 14 日分",
               "what": "digest.filter_entries：作品名を除いて比べる。転載・題名の切れ端も 1 件に"},
    "match": {"kind": "rule", "name": "match / exclude", "spec": "部分一致（空白・大小無視）· re: は正規表現",
              "what": "items.yaml の match にある語がタイトルか要約にないと収めない（digest.match_hit）"},
    "spam": {"kind": "rule", "name": "スパム判定 SPAM_PATTERNS", "spec": "漢字の間の ❌ · 在线看・高清完整・免费全集 等 · 末尾「〜网」· exclude_sources · 収集・inbox の合併・出刊・ページ生成の 4 か所で落とす",
             "what": "digest.is_spam：乗っ取られたサイトの成人・海賊版「在线看」ページを捨てる（作品名を詰めているので match を通ってしまう）"},
    "urgent": {"kind": "rule", "name": "要紧の判定 urgent_patterns", "spec": "タイトルに正規表現 · Reddit・補完分は除く",
               "what": "当日 Discord に送る記事（digest.is_urgent）"},
    "fallback": {"kind": "algo", "name": "キーワード編集 fallback_stories", "spec": "重複 bigram > 0.5 · 4 媒体以上で話題 · 最大 7 件",
                 "what": "AI 編集がまだの新着のうち、要紧（urgent_patterns）のものだけを規則で「重大」にまとめて先に載せる"},
    "pending": {"kind": "rule", "name": "整理待ち split_unedited", "spec": "_covered より後 · edit.json にない版面 → 版面に載せない · 原題 20 件まで表示",
                "what": "digest.split_unedited / render._pending：版面には AI 編集が整理した記事だけ。未整理の新着は版面の下の折りたたみ「整理待ち N 件」に原題・出典だけ"},
    "imgpick": {"kind": "algo", "name": "配図の選び方 images.pick", "spec": "短辺 ≥200 · 長辺 ≥300 · 8MB まで · 1 件 60 秒・12 枚まで · TLS は ALPN http/1.1（ブラウザと同じ。ないと i0.wp.com が 404）· おすすめの「図なし」は翌日もう一度探す",
                "what": "AI 指定 → 記事の画像 → og:image → JSON-LD → 本文 → Bing の縮小画像 → 転載ページ。ロゴ・既定画像は除く。"
                        "Bing の縮小画像（bing.com/th）は Bing が切った一部分なので原文の図の後ろ。repair-images（収集の手動実行）で既刊も直す"},
    "imgsharp": {"kind": "rule", "name": "より大きい予告画像 / 防盗链の再試行", "spec": "og:image・JSON-LD の長辺 < 1000 なら同じページの大きい方 · 403 は原文ページを Referer に 3 枚まで",
                 "what": "images.pick：同じ記事の大きい版（JSON-LD の 1920×1080 など）を先に。新浪 sinaimg など Referer がないと 403 の図は「（本站保存）」として hdimg が本站に置く"},
    "hdimg": {"kind": "algo", "name": "看不清の判定と OpenCV 高清化 hdimg", "spec": "表示で 1.6 倍以上に引き伸ばす かつ 表示サイズでの模糊度 > 0.42（Crété-Roffet re-blur 法・1×9 平均）· 大きい枠 1280px・カード 720px · NLMeans h=3 → Lanczos4（最大 3 倍）→ 輝度 USM 0.7 · webp 82 · 6 並列",
              "what": "hdimg.py：看得清の図は触らない（ファイルも作らない）。Bing の 100×100 縮小画像は w=1200 版を取り白い余白を切る。防盗链の図は本站に置く。docs/pics/ を render が元の網址の前に差し込む。8 日を過ぎた図は消す"},
    "heat": {"kind": "algo", "name": "話題度 6 次元", "spec": "報道量 20・広がり 15・出来事 20・勢い 15・一般の関心 20・ファン 10",
             "what": "heat.py：各次元 = 60% 自分の平常比 + 40% 共通の尺度。取れない次元は分母から外す"},
    "octree": {"kind": "algo", "name": "減色 FASTOCTREE 16 色", "spec": "背景 = 最多色 · 強調 = 彩度^1.5 · WCAG 4.5:1",
               "what": "theme.from_image：Pillow quantize。読めるまで明るさを ±0.04 ずつ動かす"},
    "fit": {"kind": "algo", "name": "写真のはめ方 FIT_JS", "spec": "|ln(画像比 / 枠比)| < 0.08 のときだけ埋める（切れるのは 8% まで）· ほかはぼかし背景に全体 · 気になるかも？はスマホで枠を写真の比率に",
            "what": "render.py：どんな比率の配図でも同じ枠に入れ、写真は切らない（文字・ロゴ入りのバナーが欠けるため）。枠の大きさは変えないので壁の段はそろう"},
    "ahash": {"kind": "algo", "name": "差分ハッシュ 9×8", "spec": "ハミング距離 ≤ 4 は同じ画像",
              "what": "emblem_fill._hash：網址が違う同じ写真を 1 枚に"},
    "roster": {"kind": "rule", "name": "上限 = 主要な要素の数（emblem_fill.roster / rule）", "spec": "キャラ・グループ ≤20 · 主題 ≤10 · 本人 10 · ブランド 1",
               "what": "Wiki の分類（emblem_category）か AniList の主役を数えて emblem_pool に。名前は参照の多い順に emblem_who へ"},
    "cutcheck": {"kind": "algo", "name": "切り抜きの検査 check_whole", "spec": "上の端 >50%（コマの切り抜き）· 左右の端 >10% · 面積 <12% · 半透明 >18% は外す",
                 "what": "emblem.check_whole：体が枠で切れた・輪郭がにじんだものを使わない"},
    "facefit": {"kind": "algo", "name": "顔の大きさをそろえる", "spec": "胸像：顔 = 高さの 32% · 公式の立ち絵は全身のまま · 胸像と全身は多いほうに",
                "what": "emblem.face_fit / upper_body / keep_framing"},
    "facerule": {"kind": "rule", "name": "写真の規則 photo_problem", "spec": "顔の高さ ≥ 10% · 2 番目の顔 < 60% · 基準なしは同じ顔 2 枚以上",
                 "what": "face_id.py：前は Claude が目で見ていた「遠景・集合写真・別人」を数で判断する"},
    "holes": {"kind": "rule", "name": "切り抜きの穴 hole_share", "spec": "実在の人の写真で体の中の穴 > 3% は外す（絵は除く）",
              "what": "emblem.check_whole：服が背景と同じ色で抜けた切り抜きを落とす"},
    "gate": {"kind": "algo", "name": "ゲート gate.py", "spec": "同じ指紋は 6 時間起こし直さない · 前回から 60 分あける · 変数 GATE_FIRE = edit / 1",
             "what": "仕事があるか・AI が要るかをプログラムだけで決める。AI の要らない仕事はその場で済ませる"},
    "taste": {"kind": "algo", "name": "好みの学習", "spec": "ラベルごと ±1 · 上限 −6〜+4 · 出すのは 5 点以上",
              "what": "digest.learn_taste：👍👎 の最後の一票から"},
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
    "reddit": {"kind": "api", "name": "Reddit OAuth / RSS", "spec": "25 件 · 429 が 2 回で今回は止める",
               "what": "sources.reddit_search / reddit_sub"},
    "steam": {"kind": "api", "name": "Steam Web API", "spec": "ニュース 10 件 · 価格 · 同時接続",
              "what": "GetNewsForApp・appdetails・GetNumberOfCurrentPlayers"},
    "anilist": {"kind": "api", "name": "AniList GraphQL", "spec": "続編 10 期まで · 人気・トレンド",
                "what": "放送状態・主役キャラ・話題度"},
    "tmdb": {"kind": "api", "name": "TMDB API", "spec": "放送状態 · popularity", "what": "ドラマ・映画の状態と話題度"},
    "wikipv": {"kind": "api", "name": "Wikipedia 閲覧数", "spec": "60 日分 · 50 記事ずつ · 1 日 1 回",
               "what": "話題度の「一般の関心」"},
    "wiki": {"kind": "api", "name": "Wikidata / Wikipedia / Commons", "spec": "P154 ロゴ · P18 写真 · ≥300×300",
             "what": "小元素の候補（en / ja / zh / ko）"},
    "fandom": {"kind": "api", "name": "Fandom MediaWiki API", "spec": "キャラのページの代表画像", "what": "絵のキャラの小元素"},
    "twemoji": {"kind": "api", "name": "Twemoji 15.1.0", "spec": "SVG アイコン · 0 枚を防ぐ最後の砦", "what": "主題の小元素"},
    "youtube": {"kind": "api", "name": "YouTube 検索ページ（ytInitialData）", "spec": "1 人 4 本 · 題名にグループ名と名前 · 직캠・fancam を先に · 動画の場面 hq1・hq2・hq3（480×360、投稿者のサムネイルは字が載るので使わない）",
                "what": "メンバー・出演者の写真（Commons にない人）。本人確認は顔の規則"},
    "bingimg": {"kind": "api", "name": "Bing 画像検索", "spec": "一覧に載せるだけ · 自動では選ばない", "what": "出所が不確かなので目で見る"},
    "supabase": {"kind": "api", "name": "Supabase REST / RPC", "spec": "news を 500 件ずつ upsert · my_votes · set_size",
                 "what": "投票・篇幅・依頼・写真・記事の控え"},
    "pgnet": {"kind": "api", "name": "pg_net → GitHub dispatch", "spec": "20 秒に 1 回まで", "what": "設定ページの依頼ですぐ Actions を起こす"},
    "discord": {"kind": "api", "name": "Discord Webhook", "spec": "要紧 ≤6 行 · 埋め込み ≤10 · 30 日は二重に送らない",
                "what": "notify.py"},
    "confetti": {"kind": "api", "name": "canvas-confetti 1.9.3", "spec": "👍 の演出 20 種", "what": "likefx.py"},
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
             "text": "分類の人数か AniList の主役の人数 → emblem_pool（上限）", "uses": ["roster"]},
            {"id": "auto", "kind": "decision", "lane": "actions", "title": "自動補完で目標に届いた？",
             "text": "「小元素の自動補完」が規則だけで集める", "no": "失敗の理由と助言が管理ページに出る。手で頼まれたら下へ"},
            {"id": "pick", "kind": "step", "lane": "ai", "title": "一覧を目で見て番号を選ぶ（頼まれたときだけ）", "by": "ai",
             "text": "外した画像は emblem_reject に書く（二度と自動で選ばれない）", "uses": ["claude"]},
            {"id": "write", "kind": "store", "lane": "repo", "title": "items.yaml · docs/emblems/*.webp"},
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
             "text": "目標未満 · 失敗した版面は「新しい記事・手がかりが来た」か「6 時間たった」ら対象に戻る",
             "uses": ["gate"], "no": "何もしない（Actions 20 秒で終わり）"},
            {"id": "b1r", "kind": "step", "lane": "actions", "title": "要る枚数を決める", "text": "上限 = 主要な要素の数（まだ数えていなければ先に --roster）",
             "uses": ["roster"]},
            {"id": "b2", "kind": "step", "lane": "actions", "title": "準備", "text": "モデルはキャッシュから（初回だけダウンロード）",
             "uses": ["rembg", "yunet", "sface"]},
            {"id": "b2s", "kind": "table", "lane": "actions", "title": "取り方の段（同じ回の中で、届くまで上がる）",
             "rows": [("① 標準", "下の順（直接指定 → Fandom → Wikidata → Wikipedia → Commons → 記事の配図 → 公式サイト → Twemoji）"),
                      ("② 名前を広げる", "作品名をつけて全言語の Wikipedia・Commons（12 枚）· 記事 30 日分・要約にも名前 · Fandom の別のページ名"),
                      ("③ 公式・記事のページ", "公式サイトの画像（メンバー名のファイル）· 名前が出る記事の本文ページの og:image（8 本）· 人物は YouTube の動画の場面（字のない hq1〜3）")],
             "uses": ["youtube"]},
            {"id": "b3", "kind": "fan", "lane": "ext", "title": "① 標準で候補を集める", "x": "×6 版面を同時に", "mode": "上から順に · 足りるまで",
             "items": [("0", "直接指定", "公式の立ち絵"), ("1", "代表作", "主題の下の一段"), ("2", "AniList", "アニメの主役"),
                       ("3", "Fandom", "立ち絵 → 代表画像", "fandom"), ("4", "Wikidata", "P154・P18", "wiki"),
                       ("5", "Wikipedia", "≤10", "wiki"), ("6", "Commons", "≤8", "wiki"), ("7", "記事の配図", "≤12"),
                       ("8", "公式サイト", "ロゴ"), ("9", "Twemoji", "主題", "twemoji")],
             "uses": ["pace"]},
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
             "text": "検査で外れたら同じページの公式イラストで取り直す · 公式の立ち絵は全身で測ってから上半身に切る（どのキャラも体の同じところ）· ロゴは地を抜いて切らない",
             "uses": ["rembg", "cutcheck", "holes", "facefit", "pose"]},
            {"id": "b8", "kind": "decision", "lane": "actions", "title": "目標に届いた？", "no": "次の段へ（② → ③）。全部だめなら失敗",
             "no_to": "b2s"},
            {"id": "b8f", "kind": "table", "lane": "actions", "title": "失敗したら・待っていたら",
             "rows": [("失敗（3 段とも届かない）", "新しい記事・手がかり（材料の指紋）が来たらすぐ、来なくても 6 時間後に再挑戦 · 管理ページに理由と助言"),
                      ("順番待ち", "毎時と収集のあとに 6 本並列で処理 · 40 分で終わらなければ続けてもう一度（3 回まで）"),
                      ("いま処理中", "版面と段（① ② ③）を live_status に書く → 管理ページ「いま動いているもの」に 30 秒ごと")]},
            {"id": "b9", "kind": "store", "lane": "repo", "title": "items.yaml · docs/emblems · state/emblem_progress.json · state/log",
             "text": "変わったときだけコミット → ページ生成"},
        ],
    },
    {
        "id": "gate", "name": "後台のゲート", "en": "GATE", "lane": "actions", "workflow": "background.yml",
        "schedule": [(h, m) for h in range(24) for m in (17, 47)],   # 17 分 = Supabase pg_cron、47 分 = GitHub の定時（抜けることがあるので 2 つの時計）
        "when": "毎時 · 収集のあとすぐ · 残れば続けて",
        "trigger": "毎時 17 分（Supabase pg_cron）と 47 分（GitHub の定時）／ ニュース収集が終わるたび（新しい材料）／ 時間の予算を使い切って仕事が残っていれば続けてもう一度（3 回まで）／ 管理ページの「今すぐ実行」",
        "summary": "仕事があるか、AI が要るかをプログラムだけで決める。AI の要らない仕事（小元素）はその場で Python で済ませ、"
                   "AI が要る仕事（AI 編集・写真）は仕事があるときだけ Claude を起こす。Claude は起きるたびにトークンを使うので、空振りをなくす。"
                   "版面には AI が整理した記事しか載らないので、収集で整理待ちが増えたらすぐ AI 編集を起こす（リポジトリ変数 GATE_FIRE で開け閉め）。",
        "files": ["scripts/gate.py", ".github/workflows/background.yml", "state/gate.json"], "doc": "CLAUDE.md", "uses": ["gate"],
        "flow": [
            {"id": "g1", "kind": "fan", "lane": "actions", "title": "仕事を調べる", "mode": "全部を毎回",
             "items": [("1", "小元素", "目標未満の版面（6 時間以内の失敗で材料が同じものは除く）"), ("2", "AI 編集", "今日の inbox の整理待ち（_covered より後・edit.json にない版面）"),
                       ("3", "写真", "inbox/photos/*.json")]},
            {"id": "g2", "kind": "decision", "lane": "actions", "title": "小元素の仕事がある？", "no": "飛ばす"},
            {"id": "g3", "kind": "step", "lane": "actions", "title": "その場で Python で埋める", "x": "AI なし · 4 本並列", "text": "「小元素の自動補完」"},
            {"id": "g4", "kind": "decision", "lane": "actions", "title": "AI が要る仕事がある？", "text": "AI 編集・写真", "no": "Claude は起こさない（トークン 0）"},
            {"id": "g5", "kind": "decision", "lane": "actions", "title": "同じ仕事で 6 時間以内に起こしていない？", "text": "仕事の指紋（sig）を比べる",
             "uses": ["gate"], "no": "起こさない（二重に使わない）"},
            {"id": "g5b", "kind": "decision", "lane": "actions", "title": "前に起こしてから 60 分たった？", "text": "新着で指紋が変わっても、編集中に重ねない",
             "uses": ["gate"], "no": "次の回まで待つ"},
            {"id": "g5c", "kind": "decision", "lane": "actions", "title": "GATE_FIRE で開けている？", "text": "リポジトリ変数 · 未設定 = edit（AI 編集だけ・既定）· 0 = 閉 · 1 = 全部",
             "no": "起こさない（記録だけ・定時を待つ）"},
            {"id": "g6", "kind": "step", "lane": "ai", "title": "Claude の定時タスクを API で起こす", "text": "定時タスクごとのトークン（Secret ROUTINE_FIRE_TOKEN など）が要る · 最多 2 時間に 1 回（収集ごと）",
             "uses": ["claude"]},
            {"id": "g7", "kind": "store", "lane": "repo", "title": "state/gate.json · state/log/gate.json", "text": "判断が変わったときだけコミット"},
        ],
    },
    {
        "id": "collect", "name": "ニュース収集", "en": "COLLECT", "lane": "actions",
        "schedule": [(h, 17) for h in range(0, 24, 2)], "workflow": "digest.yml", "when": "2 時間ごと · 6 本並列",
        "trigger": "2 時間ごと（日本時間 奇数時 17 分）／ 毎週月曜 9:47 に周報",
        "summary": "関注項ごとにニュース・SNS・価格を集めて inbox に溜め、出刊・通知・ページ生成までつなぐ。",
        "files": [".github/workflows/digest.yml", "scripts/digest.py", "scripts/sources.py"], "doc": "README.md",
        "uses": ["gnews", "bing", "reddit", "steam", "dedupe", "spam", "match"],
        "flow": [
            {"id": "c1", "kind": "step", "lane": "actions", "title": "起動", "text": "Ubuntu 4 コア · 30 分まで · 同時に 1 本"},
            {"id": "c2", "kind": "fan", "lane": "ext", "title": "記事を集める", "x": "×6 関注項を同時に", "mode": "それぞれのサイトへ",
             "items": [("G", "Google ニュース", "5 言語", "gnews"), ("B", "Bing ニュース", "3 回まで", "bing"),
                       ("R", "Reddit", "25 件", "reddit"), ("S", "Steam", "10 件", "steam"), ("F", "RSS", "feeds")],
             "uses": ["pace"]},
            {"id": "c3", "kind": "step", "lane": "actions", "title": "重複を落とす", "x": "元の順番で", "uses": ["dedupe"]},
            {"id": "c3s", "kind": "decision", "lane": "actions", "title": "スパム・止めた来源ではない？", "text": "成人・海賊版の「在线看」ページ",
             "uses": ["spam"], "no": "捨てる"},
            {"id": "c4", "kind": "step", "lane": "actions", "title": "その作品の記事か", "uses": ["match"]},
            {"id": "c5", "kind": "decision", "lane": "actions", "title": "新しい記事・状態の変化がある？", "no": "その関注項は書かない"},
            {"id": "c6", "kind": "step", "lane": "ext", "title": "いまの状態", "text": "価格・放送・状態の変化", "uses": ["steam", "anilist", "tmdb"]},
            {"id": "c7", "kind": "store", "lane": "repo", "title": "inbox/日付.json", "text": "1 関注項 30 件・Reddit 10 件まで"},
            {"id": "c8", "kind": "step", "lane": "actions", "title": "話題度の数字・Supabase に控え", "uses": ["wikipv", "supabase"]},
            {"id": "c9a", "kind": "decision", "lane": "actions", "title": "AI 編集が整理した記事？", "text": "edit.json にある版面の _covered まで",
             "yes": "版面に載せる", "no": "↓ 要紧か見る"},
            {"id": "c9b", "kind": "decision", "lane": "actions", "title": "要紧の記事？", "text": "urgent_patterns に当たる",
             "uses": ["urgent", "fallback"], "yes": "すぐ「重大」で載せる＋Discord", "no": "版面の下の「整理待ち N 件」（折りたたみ・原題だけ）"},
            {"id": "c9", "kind": "step", "lane": "actions", "title": "出刊 → 通知 → push", "text": "push に失敗したら 3 回まで取り直す · このあとゲートが AI 編集を起こす",
             "uses": ["pending", "discord"]},
        ],
    },
    {
        "id": "heat", "name": "話題度", "en": "HEAT", "lane": "actions", "when": "収集のたびに数字 · ページ生成で計算",
        "trigger": "数字は収集のとき（1 日 1 回）、点数はページを作るとき（ネットに出ない）",
        "summary": "作品ごとの盛り上がりを 0〜100 で出す。6 つの次元を、自分の平常と比べた分と共通の尺度で混ぜる。",
        "files": ["scripts/heat.py", "state/heat_signals.json"], "doc": "CLAUDE.md", "uses": ["heat", "wikipv", "steam", "anilist", "tmdb"],
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
             "rows": [("機能の更新", "機能のコミット"), ("愿望清单", "新しい愿望 10 件まで"), ("新関注項", "増えた・減った"), ("周報", "月曜・直近 7 日")]},
        ],
    },
    {
        "id": "edit", "name": "AI 編集", "en": "EDIT", "lane": "ai",   # 定時はなし（2026-10-17 に毎日 2 回の定時を止めた）：ゲートが起こす
        "when": "整理待ちがあるとき（収集のあと）",
        "trigger": "ゲート：収集で整理待ちが増えたとき（最多 2 時間に 1 回）／ 新しい関注項が入ったとき",
        "summary": "inbox の記事から重要なものを選び、同じ件を合わせて、見出しと配図を決めて出刊する。新しい関注項は版面も設計する。"
                   "版面に載るのは AI 編集が整理した記事だけ（それまでは「整理待ち」、要紧だけ先に載る）。",
        "files": ["EDITING.md", "scripts/digest.py", "TEMPLATES.md"], "doc": "EDITING.md", "uses": ["claude", "imgpick", "pending"],
        "flow": [
            {"id": "e1", "kind": "step", "lane": "ai", "title": "最新の inbox を読む"},
            {"id": "e2", "kind": "decision", "lane": "ai", "title": "今日の整理待ちがある？", "text": "_covered より後の記事・edit.json にない版面", "no": "何も変えずに終わり"},
            {"id": "e3", "kind": "step", "lane": "ai", "title": "版面の設計・小元素", "by": "ai", "text": "motif・theme・like_fx · 足りない小元素（「小元素の選定」）"},
            {"id": "e4", "kind": "step", "lane": "ai", "title": "編集して edit.json", "text": "同じ件を合わせる · 見出しは原文 · S 3 / M 5 / L 8 件",
             "uses": ["claude"]},
            {"id": "e5", "kind": "step", "lane": "ai", "title": "配図を目で選ぶ", "text": "1 件 12 枚まで · 4 列の一覧", "uses": ["imgpick", "claude"]},
            {"id": "e6", "kind": "step", "lane": "actions", "title": "出刊 publish", "text": "AI のあとに来た新着は「整理待ち」（要紧だけ先に重大）", "uses": ["pending", "fallback"]},
            {"id": "e7", "kind": "store", "lane": "repo", "title": "inbox/*.edit.json · reports/"},
        ],
    },
    {
        "id": "images", "name": "記事の配図", "en": "IMAGES", "lane": "actions", "when": "出刊のたび",
        "trigger": "出刊のとき（1 件ずつ）。AI 編集は候補の一覧を見て選ぶ",
        "summary": "記事ごとに、顔や内容が切れない 1 枚を選ぶ。号の中で同じ画像は使わない。",
        "files": ["scripts/images.py", "scripts/hdimg.py", "scripts/digest.py", "state/hdimg.json"], "doc": "EDITING.md", "uses": ["imgpick", "imgsharp", "hdimg"],
        "flow": [
            {"id": "i1", "kind": "fan", "lane": "ext", "title": "候補の順", "mode": "上から順に · 1 件 60 秒・12 枚まで",
             "items": [("1", "AI の指定", ""), ("2", "記事の画像", "Bing の縮小画像は除く"), ("3", "og:image", ""), ("4", "JSON-LD", ""),
                       ("5", "本文の img", "6 枚"), ("6", "Bing の縮小画像", "Bing が切った一部分"), ("7", "転載ページ", "Bing 8 · Google")]},
            {"id": "i2", "kind": "step", "lane": "actions", "title": "検査", "text": "8MB まで · 短辺 200 · 長辺 300 · Pillow で開ける · ロゴ・既定画像を除く",
             "uses": ["imgpick"]},
            {"id": "i2b", "kind": "decision", "lane": "actions", "title": "予告画像が小さい？", "text": "長辺 < 1000",
             "no": "そのまま", "uses": ["imgsharp"]},
            {"id": "i2c", "kind": "step", "lane": "ext", "title": "同じページの大きい版を先に", "text": "og:image → JSON-LD", "uses": ["imgsharp"]},
            {"id": "i3", "kind": "decision", "lane": "actions", "title": "見つかった？", "no": "403 の原文の図を Referer つきで再試行 → だめなら作品の表紙",
             "uses": ["imgsharp"]},
            {"id": "i4", "kind": "step", "lane": "actions", "title": "号の中で同じ画像を使わない", "text": "海外の出所を先に"},
            {"id": "i4b", "kind": "decision", "lane": "actions", "title": "看不清？",
             "text": "1.6 倍以上に引き伸ばす かつ 表示サイズで模糊度 > 0.42 · Bing の 100×100 · Referer が要る図", "no": "元の網址のまま（何もしない）", "uses": ["hdimg"]},
            {"id": "i4c", "kind": "fan", "lane": "actions", "title": "OpenCV で高清化", "mode": "順に · ×6 並列",
             "items": [("1", "ノイズ除去", "NLMeans h=3"), ("2", "拡大", "Lanczos4 · 最大 3 倍"), ("3", "シャープ", "輝度だけ USM 0.7")],
             "uses": ["hdimg"]},
            {"id": "i4d", "kind": "store", "lane": "repo", "title": "docs/pics/*.webp · state/hdimg.json", "text": "8 日を過ぎたら消す"},
            {"id": "i5", "kind": "step", "lane": "web", "title": "枠にはめる", "text": "本站の高清版 → 元の網址 → 表紙", "uses": ["fit"]},
        ],
    },
    {
        "id": "colors", "name": "トップの配色", "en": "COLORS", "lane": "actions", "when": "ページ生成のたび",
        "trigger": "ページを作るとき。同じ画像の色は state/themes.json に残して使い回す",
        "summary": "その日の頭条の写真から、トップの地色と強調色を取る。字が必ず読めるように明るさを直す。",
        "files": ["scripts/theme.py", "scripts/render.py", "state/themes.json"], "doc": "CLAUDE.md", "uses": ["octree"],
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
        "files": ["scripts/digest.py", "state/recommend.json"], "doc": "CLAUDE.md", "uses": ["taste", "storydedupe", "gnews"],
        "flow": [
            {"id": "r1", "kind": "step", "lane": "web", "title": "👍👎 を読む", "text": "記事ごとに最後の一票", "uses": ["supabase"]},
            {"id": "r2", "kind": "step", "lane": "actions", "title": "好みを学ぶ", "uses": ["taste"]},
            {"id": "r3", "kind": "step", "lane": "ext", "title": "外を探す", "x": "6 本 · 20 件ずつ", "text": "ランダムな種 · 好みの重み", "uses": ["gnews"]},
            {"id": "r4", "kind": "step", "lane": "actions", "title": "同じ話をまとめる", "uses": ["storydedupe"]},
            {"id": "r5", "kind": "decision", "lane": "actions", "title": "点数 ≥ 5？", "text": "好みの語 2 点 · 同じ作品 +1", "no": "出さない（探索枠は ≥4）"},
            {"id": "r6", "kind": "store", "lane": "repo", "title": "state/recommend.json", "text": "5 件 × 6 組"},
        ],
    },
    {
        "id": "render", "name": "ページ生成", "en": "RENDER", "lane": "actions", "workflow": "render.yml", "when": "push のたび · 約 1 分",
        "trigger": "main に push されたとき（コード・items.yaml・愿望清单など）",
        "summary": "収集を待たず、網页だけを 1 分ほどで作り直して公開する。話題度・配色・版面の組み方もここで決まる。",
        "files": [".github/workflows/render.yml", "scripts/render.py"], "doc": "CLAUDE.md", "uses": ["heat", "octree", "frontpick", "fit", "confetti"],
        "flow": [
            {"id": "p1", "kind": "step", "lane": "actions", "title": "main に push", "x": "新しい回が来たら古い回を止める"},
            {"id": "p2", "kind": "step", "lane": "web", "title": "篇幅を読む", "text": "S / M / L", "uses": ["supabase"]},
            {"id": "p3", "kind": "step", "lane": "actions", "title": "話題度を計算", "uses": ["heat"]},
            {"id": "p4", "kind": "step", "lane": "actions", "title": "トップの配色", "uses": ["octree"]},
            {"id": "p4b", "kind": "step", "lane": "actions", "title": "トップの記事を選ぶ", "x": "直近 7 日の全号から",
             "text": "作品ごとに 1 本目 → 2 本目 · 同じ写真・同じ出来事は 1 回", "uses": ["frontpick"]},
            {"id": "p5", "kind": "table", "lane": "actions", "title": "版面の組み方",
             "rows": [("写真の壁", "15 枚（スマホ 6）· 16:10"), ("普通の記事", "1 行 3 枚まで · 4 枚 = 2 + 2"), ("篇幅", "S 3 / M 4 / L 10 件")]},
            {"id": "p6", "kind": "store", "lane": "repo", "title": "docs/*.html"},
            {"id": "p7", "kind": "step", "lane": "web", "title": "GitHub Pages に公開", "text": "約 1 分", "uses": ["fit", "confetti"]},
        ],
    },
    {
        "id": "live", "name": "ページの自動更新", "en": "LIVE", "lane": "web",
        "when": "開いている間 · 1 分ごと",
        "trigger": "簡報・管理ページを開いているあいだ、1 分ごと（タブが裏にあるときも戻ったときにすぐ）",
        "summary": "開いたままのページに、新しい記事や数字を自分で出す。裏である版面を作り直している間は、その版面だけ枠に「更新中」の帯と残り時間。",
        "files": ["scripts/render.py（LIVE_JS / BUSY_JS / stamp / busy_plan）", "scripts/digest.py（write_page / live_mark / live-edit）", "scripts/livestatus.py", "scripts/runlog.py（typical）", "db/live_status.sql", "docs/version.json"], "doc": "CLAUDE.md",
        "flow": [
            {"id": "l1", "kind": "step", "lane": "actions", "title": "ページを作るたびに指紋を付ける",
             "text": "収集・AI 編集・ページ生成が docs/*.html を書くとき、中身の指紋（「更新」の時刻は除く）を計算。"},
            {"id": "l2", "kind": "store", "lane": "repo", "title": "docs/version.json",
             "text": "{index: 指紋, admin: 指紋}。ページの <meta name=\"wl-ver\"> にも同じ指紋。"},
            {"id": "l3", "kind": "step", "lane": "web", "title": "1 分ごとに version.json を見る",
             "text": "キャッシュを避けて読む（?t=時刻）。タブを表に戻したときもすぐ見る。"},
            {"id": "l4", "kind": "decision", "lane": "web", "title": "指紋が変わった？", "text": "version.json ≠ 自分の指紋",
             "yes": "下に「新しい内容があります」の帯", "no": "何もしない"},
            {"id": "l5", "kind": "decision", "lane": "web", "title": "いま操作していない？",
             "text": "20 秒触っていない、またはタブが裏。入力中・流れの図を開いているあいだは待つ",
             "yes": "読み直す", "no": "待つ（帯の「今すぐ表示」で即時）"},
            {"id": "l6", "kind": "step", "lane": "web", "title": "見ていた場所のまま新しい版に",
             "text": "読み直す前の位置（見ていた板块）に戻す。簡報は増えた記事に「たった今」、管理ページは変わったパネルに「更新」。"},
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
                      ("live_report の制限", "proc は edit / emblem・版面は sizes にある名前・言葉 40 字・予想 90 分まで（secret key なしで書けるので）")]},
            {"id": "l7", "kind": "table", "lane": "web", "title": "管理ページの「いまの状況」",
             "text": "ページの再読込とは別に、外のデータを開いている間ずっと読み直す。",
             "rows": [("ウォッチ項目の依頼・写真の受付", "Supabase · 1 分ごと"), ("GitHub Actions", "3 分ごと（1 時間 60 回の制限内）"),
                      ("次の実行・待ち行列", "1 分ごとに数え直し")]},
        ],
    },
    {
        "id": "requests", "name": "設定ページの依頼", "en": "REQUESTS", "lane": "web", "workflow": "requests.yml", "when": "依頼のたび · 待ちなし",
        "trigger": "設定ページで関注項の追加・変更・篇幅の変更を送ったとき（待ち時間なし）",
        "summary": "設定ページの依頼を Supabase が受け、すぐ GitHub Actions を起こして items.yaml に反映する。",
        "files": [".github/workflows/requests.yml", "docs/additem.js", "db/instant.sql"], "doc": "CLAUDE.md", "uses": ["supabase", "pgnet"],
        "flow": [
            {"id": "q1", "kind": "step", "lane": "web", "title": "設定ページで送る", "text": "一問一答のウィザード", "uses": ["supabase"]},
            {"id": "q2", "kind": "step", "lane": "web", "title": "Supabase が GitHub を起こす", "uses": ["pgnet"]},
            {"id": "q3", "kind": "decision", "lane": "actions", "title": "待ちの依頼がある？", "no": "何もしない"},
            {"id": "q4", "kind": "step", "lane": "actions", "title": "検査して items.yaml に書く", "text": "使える項目だけ · 済み・見送りを返す"},
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
    ]},
    {"id": "act", "title": "GitHub Actions", "note": "毎回新しいサーバー（4 コア）· 終わったら消える", "cost": "無料", "style": "temp", "nodes": [
        {"id": "p-collect", "proc": "collect", "subs": ["heat", "recommend", "notify", "images"]},
        {"id": "p-gate", "proc": "gate", "subs": ["emblem-cron"]},
        {"id": "p-requests", "proc": "requests"},
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
        {"id": "s-db", "label": "feedback · sizes · item_requests · photo_inbox · news · live_status", "text": "👍👎・篇幅・依頼・写真・記事の控え・版面の更新状態",
         "uses": ["supabase", "pgnet"]}]},
    {"id": "pages", "title": "GitHub Pages", "note": "公開の網页", "cost": "無料", "style": "keep", "nodes": [
        {"id": "s-pages", "label": "網页", "text": "簡報・設定・愿望清单・話題度・管理ページ・version.json", "uses": ["fit", "confetti"]},
        {"id": "p-live", "proc": "live"}]},
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
    (25, "p-gate", "p-edit", "整理待ちがあるときだけ起こす（収集のすぐ後）", "ai"),
    (26, "p-gate", "p-photos", "写真があるときだけ起こす", "ai"),
    (27, "p-edit", "s-db", "編集中の版面（live_report）", "db"),
    (28, "p-emblem-cron", "s-db", "処理中の版面（live_report）", "db"),
]
# 並列で動かすときの限り（管理ページ「バックグラウンド → 並列と制限」）。(仕組み, いまの並列, 限り・理由)
LIMITS = [
    ("ニュース収集", "6 本並列", "GitHub Actions のサーバーは 4 コア。待ちが多いので 6 本。同じサイトの間隔は全スレッドで共有（Reddit 2 秒・Google / Bing 0.5 秒）"),
    ("小元素の自動補完", "6 本並列", "GitHub Actions（4 コア・16GB・1 回 60 分まで、続けて 3 回まで）。集めるのは待ちが多いので 6 本、抠图（rembg）と items.yaml への書き込みは 1 本ずつ"),
    ("抠图のモデル（rembg）", "1 枚ずつ", "birefnet は 1 枚で数 GB のメモリを使う。onnxruntime のメモリ池を切って、1 枚ごとに返す（前は 13GB まで溜まった）"),
    ("Wikipedia・Wikidata・Commons", "ホストごと 1 本ずつ · 全体で毎分 150", "Wikimedia の上限は名乗ったボットで全サイト毎分 200（名乗らないと 10）。"
     "429 は Retry-After を守り、続いたら 5 分休む → ここは並列でも速くならない。取ったものはキャッシュ（~/.cache/wishlist-http）"),
    ("Claude の定時タスク", "仕事があるときだけ", "起きるたびにトークンを使う。ゲートが仕事を確かめてから起こす（AI 編集・写真）。小元素は AI を使わない"),
    ("GitHub Actions", "同じワークフローは 1 本ずつ", "収集・依頼は前の回が終わるまで待つ（concurrency）。ページ生成は新しい回が来たら古い回を止める。"
                       "定時（cron）は混むと遅れる・抜ける（2 時間抜けたことがある）ので、後台作業は Supabase pg_cron（17 分）も 2 つ目の時計に"),
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
    ("AI 編集：配図を目で選ぶ", "gate", "候補の検査は規則、顔や内容が切れていないかの最後の確認は AI。頭条だけ AI にする余地あり"),
    ("写真から愿望：写っている物の認識", "gate", "画像の中身の認識はモデルが要る（Claude が見る）。写真が来たときだけ起こす"),
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


def examples_panel():
    """管理ページ「小元素の判断の例」：判断ごとに、本物の画像で 前 → 後（使わなかったものは「外す」の札）。"""
    import emblem_rules
    by_rule = {r["title"]: r for r in emblem_rules.rules()}
    cards = []
    for x in emblem_rules.EXAMPLES:
        r = by_rule[x["rule"]]
        before = "".join(_ex_fig(f, c) for f, c in x["before"])
        after = ("".join(_ex_fig(f, c, " ex-ok") for f, c in x["after"]) if x["after"]
                 else '<figure class="ex-f ex-no"><span class="ex-i"><b>外す</b></span><figcaption>使わない</figcaption></figure>')
        cards.append(f'<article class="ex ex-{e(r["by"])}"><header>{_by_tag(r["by"])}<b>{e(r["title"])}</b><small>{e(r["stage"])} · {e(x["item"])}</small></header>'
                     f'<div class="ex-row"><div class="ex-side"><em>前</em>{before}</div><span class="ex-arrow" aria-hidden="true">→</span>'
                     f'<div class="ex-side"><em>後</em>{after}</div></div>'
                     f'<p class="ex-v">{e(x["verdict"])}<small>{e(r["rule"])}</small></p></article>')
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
 grid-template-areas:"src act repo ai" "db pages repo dc" "you you you you";gap:40px 64px;align-items:start}
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
.arch-list{margin-top:14px;font-size:13px}.arch-list summary{cursor:pointer;font:700 13px var(--font-sans)}
.arch-list ol{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:4px 16px}
.arch-list li{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;padding:4px 0;border-bottom:1px solid var(--hair);color:var(--ink)}
.arch-list li em{font:900 11px var(--font-mono);font-style:normal;min-width:22px;text-align:center;color:var(--card);background:currentColor;border-radius:50%}
.arch-list li.ae-data em{background:var(--ink)}.arch-list li.ae-web em{background:var(--rose)}.arch-list li.ae-ai em{background:var(--good)}
.arch-list li.ae-notify em{background:var(--discord)}.arch-list li.ae-db em{background:var(--viz-1)}
.arch-list li em{color:var(--card)}.arch-list li small{font-size:var(--fs-label);opacity:.8}
.az-you{grid-column:1/-1}.az[data-z=etc]{grid-column:1/-1}.az[data-z=etc]>.az-b{flex-direction:row;flex-wrap:wrap}
@media (max-width:980px){
 .arch{grid-template-columns:minmax(0,1fr);grid-template-areas:"src" "act" "repo" "ai" "db" "pages" "dc" "you";gap:16px}
 .arch .dg-svg{display:none}
 .az[data-z=you]>.az-b{flex-direction:column}
}
 border:2px solid var(--ink);box-shadow:var(--shadow);font:inherit;transition:transform .1s,box-shadow .1s}
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
