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
    "haar": {"kind": "model", "name": "OpenCV Haar frontalface + LBP animeface", "spec": "scale 1.1 · minNeighbors 4〜5",
             "what": "切り抜きの構図と顔の位置（emblem.face_box / face_crop）。顔モデルがないときの代わり"},
    "claude": {"kind": "model", "name": "Claude（定時タスク）", "spec": "編集・写真の認識・一覧の目視 · サブスク枠",
               "what": "AI 編集・写真から愿望・小元素の要確認を、画面を見て判断する"},
    "claude-api": {"kind": "model", "name": "Claude API claude-haiku-5-5", "spec": "summarize: false（いまは使わない）· 4000 tokens",
                   "what": "Actions から編集するときだけ（digest.edit_stories）。使ったトークンは数える"},
    # ---- アルゴリズム
    "pace": {"kind": "algo", "name": "サイトごとの間隔（全スレッド共有）", "spec": "Reddit 2 秒 · Google / Bing 0.5 秒 · Wiki 1.3 秒",
             "what": "sources._pace / emblem_fill._throttled_get。並列でもサイトから見た間隔は同じ"},
    "dedupe": {"kind": "algo", "name": "タイトルの重複判定", "spec": "完全一致 + 文字 bigram 重なり > 0.75 · 14 日分",
               "what": "digest.filter_entries：作品名を除いて比べる。転載・題名の切れ端も 1 件に"},
    "match": {"kind": "rule", "name": "match / exclude", "spec": "部分一致（空白・大小無視）· re: は正規表現",
              "what": "items.yaml の match にある語がタイトルか要約にないと収めない（digest.match_hit）"},
    "spam": {"kind": "rule", "name": "スパム判定 SPAM_PATTERNS", "spec": "漢字の間の ❌ · 在线看・高清完整・免费全集 等 · 末尾「〜网」· exclude_sources",
             "what": "digest.is_spam：乗っ取られたサイトの成人・海賊版「在线看」ページを捨てる（作品名を詰めているので match を通ってしまう）"},
    "urgent": {"kind": "rule", "name": "要紧の判定 urgent_patterns", "spec": "タイトルに正規表現 · Reddit・補完分は除く",
               "what": "当日 Discord に送る記事（digest.is_urgent）"},
    "fallback": {"kind": "algo", "name": "キーワード編集 fallback_stories", "spec": "重複 bigram > 0.5 · 4 媒体以上で話題 · 最大 7 件",
                 "what": "AI 編集がまだの新着を、規則で記事にまとめる"},
    "imgpick": {"kind": "algo", "name": "配図の選び方 images.pick", "spec": "短辺 ≥200 · 長辺 ≥300 · 8MB まで · 1 件 60 秒・12 枚まで",
                "what": "AI 指定 → 記事の画像 → og:image → JSON-LD → 本文 → 転載ページ。ロゴ・既定画像は除く"},
    "heat": {"kind": "algo", "name": "話題度 6 次元", "spec": "報道量 20・広がり 15・出来事 20・勢い 15・一般の関心 20・ファン 10",
             "what": "heat.py：各次元 = 60% 自分の平常比 + 40% 共通の尺度。取れない次元は分母から外す"},
    "octree": {"kind": "algo", "name": "減色 FASTOCTREE 16 色", "spec": "背景 = 最多色 · 強調 = 彩度^1.5 · WCAG 4.5:1",
               "what": "theme.from_image：Pillow quantize。読めるまで明るさを ±0.04 ずつ動かす"},
    "fit": {"kind": "algo", "name": "写真のはめ方 FIT_JS", "spec": "|ln(画像比 / 枠比)| < 0.27 は裁ち切り · ほかはぼかし背景 · 気になるかも？は < 0.08、スマホは枠を写真の比率に",
            "what": "render.py：どんな比率の配図でも同じ枠に入れる。おすすめカードは文字入りバナーが多いので切らず、下に重なる札の分は写真の外に空ける"},
    "ahash": {"kind": "algo", "name": "差分ハッシュ 9×8", "spec": "ハミング距離 ≤ 4 は同じ画像",
              "what": "emblem_fill._hash：網址が違う同じ写真を 1 枚に"},
    "cutcheck": {"kind": "algo", "name": "切り抜きの検査 check_whole", "spec": "左右の端 >10% · 面積 <12% · 半透明 >18% は外す",
                 "what": "emblem.check_whole：体が枠で切れた・輪郭がにじんだものを使わない"},
    "facefit": {"kind": "algo", "name": "顔の大きさをそろえる", "spec": "顔 = 高さの 32% · 全身は上 46% · 胸像があれば全身は外す",
                "what": "emblem.face_fit / upper_body / keep_framing"},
    "facerule": {"kind": "rule", "name": "写真の規則 photo_problem", "spec": "顔の高さ ≥ 10% · 2 番目の顔 < 60% · 基準なしは同じ顔 2 枚以上",
                 "what": "face_id.py：前は Claude が目で見ていた「遠景・集合写真・別人」を数で判断する"},
    "holes": {"kind": "rule", "name": "切り抜きの穴 hole_share", "spec": "実在の人の写真で体の中の穴 > 3% は外す（絵は除く）",
              "what": "emblem.check_whole：服が背景と同じ色で抜けた切り抜きを落とす"},
    "gate": {"kind": "algo", "name": "ゲート gate.py", "spec": "仕事の指紋が同じなら 6 時間は起こし直さない",
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
        "id": "emblem", "name": "小元素の選定", "en": "EMBLEM", "lane": "ai", "schedule": "edit", "when": "AI 編集の最初",
        "trigger": "新しい関注項が入ったとき ／ AI 編集の最初に毎回（足りない関注項だけ）",
        "summary": "各版面の右上に貼るステッカーを、作品の種類に合わせて集める。AI 編集の中で、足りない関注項だけ。",
        "files": ["scripts/emblem_fill.py", "scripts/emblem.py", "scripts/face_id.py"], "doc": "TEMPLATES.md",
        "uses": ["wiki", "fandom", "yunet", "sface", "rembg"],
        "flow": [
            {"id": "audit", "kind": "step", "lane": "ai", "title": "缺口を調べる --audit", "text": "種類・目標・いまの枚数"},
            {"id": "need", "kind": "decision", "lane": "ai", "title": "目標に届いていない？", "no": "その版面は終わり"},
            {"id": "kind", "kind": "table", "lane": "ai", "title": "種類 → 目標の枚数（最少〜最大）",
             "rows": [("本人", "6（3〜10）"), ("グループ", "全員（3〜10）"), ("キャラ・出演者", "6 か emblem_who 全員"),
                      ("ブランド", "公式ロゴ 1"), ("主題", "代表作の数か 3（2〜5）")]},
            {"id": "src", "kind": "fan", "lane": "ai", "title": "候補を集める", "mode": "上から順に · 足りるまで",
             "items": [("0", "直接指定", "emblem_urls"), ("0", "代表作", "主題の下の一段"), ("1", "Fandom", "立ち絵 → 代表画像", "fandom"), ("2", "Wikidata", "P154・P18", "wiki"),
                       ("3", "Wikipedia", "記事 ≤10", "wiki"), ("4", "Commons", "≤8", "wiki"), ("5", "記事の配図", "14 日 ≤12"),
                       ("6", "公式サイト", "og:image"), ("7", "Twemoji", "主題", "twemoji"), ("8", "Bing 画像", "目で見るだけ", "bingimg")]},
            {"id": "ok", "kind": "step", "lane": "ai", "title": "使える画像か", "text": "6MB まで · 短辺 160 · 白紙・同じ画像を除く", "uses": ["ahash"]},
            {"id": "face", "kind": "step", "lane": "ai", "title": "本人確認（人物だけ）", "uses": ["yunet", "sface"]},
            {"id": "pick", "kind": "step", "lane": "ai", "title": "一覧を目で見て番号を選ぶ", "uses": ["claude"]},
            {"id": "cut", "kind": "step", "lane": "ai", "title": "切り抜いて顔の大きさをそろえる", "uses": ["rembg", "cutcheck", "facefit"]},
            {"id": "write", "kind": "store", "lane": "repo", "title": "items.yaml · docs/emblems/*.webp"},
        ],
    },
    {
        "id": "emblem-cron", "name": "小元素の自動補完", "en": "EMBLEM", "lane": "actions",
        "schedule": "gate", "when": "ゲートが仕事ありのとき · 6 本並列 · 3 段 · AI なし",
        "trigger": "後台のゲート（毎時・収集のあと）が「足りない版面がある」と判断したとき。GitHub Actions で Python だけで動く",
        "summary": "目標に届いていない版面の小元素を、足りない順に 4 本並列で埋める。前は Claude が目で見ていた判断（別人・遠景・集合写真・"
                   "切り抜きの穴・重複）は全部規則にしたので、AI は使わない。取れなかった版面は理由ごとに助言を出す。",
        "files": ["scripts/emblem_fill.py", "scripts/emblem.py", "scripts/face_id.py", ".github/workflows/background.yml"], "doc": "TEMPLATES.md",
        "uses": ["rembg", "yunet", "sface", "facerule", "holes", "wiki", "fandom"],
        "flow": [
            {"id": "b1", "kind": "decision", "lane": "actions", "title": "ゲート：足りない版面がある？",
             "text": "目標未満 · 失敗した版面は「新しい記事・手がかりが来た」か「6 時間たった」ら対象に戻る",
             "uses": ["gate"], "no": "何もしない（Actions 20 秒で終わり）"},
            {"id": "b2", "kind": "step", "lane": "actions", "title": "準備", "text": "モデルはキャッシュから（初回だけダウンロード）",
             "uses": ["rembg", "yunet", "sface"]},
            {"id": "b2s", "kind": "table", "lane": "actions", "title": "取り方の段（同じ回の中で、届くまで上がる）",
             "rows": [("① 標準", "下の順（直接指定 → Fandom → Wikidata → Wikipedia → Commons → 記事の配図 → 公式サイト → Twemoji）"),
                      ("② 名前を広げる", "作品名をつけて全言語の Wikipedia・Commons（12 枚）· 記事 30 日分・要約にも名前 · Fandom の別のページ名"),
                      ("③ 公式・記事のページ", "公式サイトの画像（メンバー名のファイル）· 名前が出る記事の本文ページの og:image（8 本）")]},
            {"id": "b3", "kind": "fan", "lane": "ext", "title": "① 標準で候補を集める", "x": "×6 版面を同時に", "mode": "上から順に · 足りるまで",
             "items": [("0", "直接指定", "公式の立ち絵"), ("1", "Fandom", "立ち絵 → 代表画像", "fandom"), ("2", "Wikidata", "P154・P18", "wiki"),
                       ("3", "Wikipedia", "≤10", "wiki"), ("4", "Commons", "≤8", "wiki"), ("5", "記事の配図", "≤12"),
                       ("6", "公式サイト", "ロゴ"), ("7", "Twemoji", "主題", "twemoji")],
             "uses": ["pace"]},
            {"id": "b4", "kind": "step", "lane": "actions", "title": "使える画像か", "text": "6MB まで · 短辺 160（横長ロゴは長辺 300）· 白紙・同じ画像を除く",
             "uses": ["ahash"]},
            {"id": "b5", "kind": "table", "lane": "actions", "title": "人物の写真の規則（前は目で見ていた）",
             "rows": [("顔なし", "観客席・絵画・物"), ("遠景", "顔の高さ < 画像の 10%"), ("何人も写っている", "2 番目の顔 ≥ 60%"),
                      ("別人", "記事の代表画像と cos < 0.363 · 基準なしは同じ顔 2 枚以上")],
             "uses": ["yunet", "sface", "facerule"]},
            {"id": "b6", "kind": "decision", "lane": "actions", "title": "確かな取り方？", "text": "人物 = 規則を通った写真 · キャラ = 直接指定・Fandom · 主題 = Wikidata・Commons・Twemoji",
             "no": "理由をつけて外す（確かでない取り方・重複・目標を超える）"},
            {"id": "b7", "kind": "step", "lane": "repo", "title": "書いて切り抜く", "x": "1 枚ずつ（WRITE_LOCK）",
             "uses": ["rembg", "cutcheck", "holes", "facefit"]},
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
                   "AI が要る仕事（AI 編集・写真）は仕事があるときだけ Claude を起こす。Claude は起きるたびにトークンを使うので、空振りをなくす。",
        "files": ["scripts/gate.py", ".github/workflows/background.yml", "state/gate.json"], "doc": "CLAUDE.md", "uses": ["gate"],
        "flow": [
            {"id": "g1", "kind": "fan", "lane": "actions", "title": "仕事を調べる", "mode": "全部を毎回",
             "items": [("1", "小元素", "目標未満の版面（6 時間以内の失敗で材料が同じものは除く）"), ("2", "AI 編集", "今日の inbox で _covered より新しい記事"),
                       ("3", "写真", "inbox/photos/*.json")]},
            {"id": "g2", "kind": "decision", "lane": "actions", "title": "小元素の仕事がある？", "no": "飛ばす"},
            {"id": "g3", "kind": "step", "lane": "actions", "title": "その場で Python で埋める", "x": "AI なし · 4 本並列", "text": "「小元素の自動補完」"},
            {"id": "g4", "kind": "decision", "lane": "actions", "title": "AI が要る仕事がある？", "text": "AI 編集・写真", "no": "Claude は起こさない（トークン 0）"},
            {"id": "g5", "kind": "decision", "lane": "actions", "title": "同じ仕事で 6 時間以内に起こしていない？", "text": "仕事の指紋（sig）を比べる",
             "uses": ["gate"], "no": "起こさない（二重に使わない）"},
            {"id": "g6", "kind": "step", "lane": "ai", "title": "Claude の定時タスクを API で起こす", "text": "定時タスクごとのトークン（Secret）が要る · GATE_FIRE=1 のとき",
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
            {"id": "c9", "kind": "step", "lane": "actions", "title": "出刊 → 通知 → push", "text": "push に失敗したら 3 回まで取り直す",
             "uses": ["fallback", "discord"]},
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
        "id": "edit", "name": "AI 編集", "en": "EDIT", "lane": "ai", "schedule": [(4, 43), (15, 43)],   # 日本時間 13:43 / 0:43（北京時間 12:43 / 23:43）
        "when": "毎日 13:43 · 0:43（日本時間）",
        "trigger": "毎日 2 回（日本時間 13:43 / 0:43）／ 新しい関注項が入ったとき",
        "summary": "inbox の記事から重要なものを選び、同じ件を合わせて、見出しと配図を決めて出刊する。新しい関注項は版面も設計する。",
        "files": ["EDITING.md", "scripts/digest.py", "TEMPLATES.md"], "doc": "EDITING.md", "uses": ["claude", "imgpick", "fallback"],
        "flow": [
            {"id": "e1", "kind": "step", "lane": "ai", "title": "最新の inbox を読む"},
            {"id": "e2", "kind": "decision", "lane": "ai", "title": "今日の新着がある？", "text": "_covered より新しい記事", "no": "何も変えずに終わり"},
            {"id": "e3", "kind": "step", "lane": "ai", "title": "版面の設計・小元素", "text": "motif・theme・like_fx · 足りない小元素（「小元素の選定」）"},
            {"id": "e4", "kind": "step", "lane": "ai", "title": "編集して edit.json", "text": "同じ件を合わせる · 見出しは原文 · S 3 / M 5 / L 8 件",
             "uses": ["claude"]},
            {"id": "e5", "kind": "step", "lane": "ai", "title": "配図を目で選ぶ", "text": "1 件 12 枚まで · 4 列の一覧", "uses": ["imgpick", "claude"]},
            {"id": "e6", "kind": "step", "lane": "actions", "title": "出刊 publish", "text": "AI のあとに来た新着は規則で", "uses": ["fallback"]},
            {"id": "e7", "kind": "store", "lane": "repo", "title": "inbox/*.edit.json · reports/"},
        ],
    },
    {
        "id": "images", "name": "記事の配図", "en": "IMAGES", "lane": "actions", "when": "出刊のたび",
        "trigger": "出刊のとき（1 件ずつ）。AI 編集は候補の一覧を見て選ぶ",
        "summary": "記事ごとに、顔や内容が切れない 1 枚を選ぶ。号の中で同じ画像は使わない。",
        "files": ["scripts/images.py", "scripts/digest.py"], "doc": "EDITING.md", "uses": ["imgpick"],
        "flow": [
            {"id": "i1", "kind": "fan", "lane": "ext", "title": "候補の順", "mode": "上から順に · 1 件 60 秒・12 枚まで",
             "items": [("1", "AI の指定", ""), ("2", "記事の画像", ""), ("3", "og:image", ""), ("4", "JSON-LD", ""),
                       ("5", "本文の img", "6 枚"), ("6", "転載ページ", "Bing 8 · Google")]},
            {"id": "i2", "kind": "step", "lane": "actions", "title": "検査", "text": "8MB まで · 短辺 200 · 長辺 300 · Pillow で開ける · ロゴ・既定画像を除く",
             "uses": ["imgpick"]},
            {"id": "i3", "kind": "decision", "lane": "actions", "title": "見つかった？", "no": "その作品の表紙"},
            {"id": "i4", "kind": "step", "lane": "actions", "title": "号の中で同じ画像を使わない", "text": "海外の出所を先に"},
            {"id": "i5", "kind": "step", "lane": "web", "title": "枠にはめる", "uses": ["fit"]},
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
        "files": ["scripts/render.py（LIVE_JS / BUSY_JS / stamp / busy_plan）", "scripts/digest.py（write_page / live_mark）", "db/live_status.sql", "docs/version.json"], "doc": "CLAUDE.md",
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
             "text": "帯は小元素の下（重なったら小元素が上）。ページがその回より後に作られていれば出さない。",
             "rows": [("ニュース収集", "その版面を探し始めたら「記事を探しています」→ その版面を探し終えたらすぐ：新着なし＝消える／新着あり＝「新着 N 件 · 反映まであと約 N 分」"
                                    "（収集が Supabase live_status に書き、網页が 30 秒ごとに読む）"),
                      ("AI 編集", "編集待ちの新着がある版面だけ · 定時から約 30 分"),
                      ("小元素の自動補完", "待ち行列の先頭 4 版面（4 本並列）· 定時から約 45 分"),
                      ("ページ生成", "帯なし（中身ではなく見た目の変更。下の「新しい内容があります」で知らせる）")]},
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
            {"id": "q6", "kind": "step", "lane": "actions", "title": "すぐ収集 → AI 編集が版面を設計"},
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
            {"id": "f6", "kind": "step", "lane": "ai", "title": "物だけ切り取る", "uses": ["crop"]},
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
    (25, "p-gate", "p-edit", "仕事があるときだけ起こす", "ai"),
    (26, "p-gate", "p-photos", "写真があるときだけ起こす", "ai"),
]
# 並列で動かすときの限り（管理ページ「バックグラウンド → 並列と制限」）。(仕組み, いまの並列, 限り・理由)
LIMITS = [
    ("ニュース収集", "6 本並列", "GitHub Actions のサーバーは 4 コア。待ちが多いので 6 本。同じサイトの間隔は全スレッドで共有（Reddit 2 秒・Google / Bing 0.5 秒）"),
    ("小元素の自動補完", "6 本並列", "GitHub Actions（4 コア・16GB・1 回 60 分まで、続けて 3 回まで）。集めるのは待ちが多いので 6 本、抠图（rembg）と items.yaml への書き込みは 1 本ずつ"),
    ("抠图のモデル（rembg）", "1 枚ずつ", "birefnet は 1 枚で数 GB のメモリを使う。onnxruntime のメモリ池を切って、1 枚ごとに返す（前は 13GB まで溜まった）"),
    ("Wikipedia・Wikidata・Commons", "1.3 秒に 1 回", "全スレッド合わせて。続けて叩くと 429（多すぎ）になり、続いたら 5 分休む → ここは並列でも速くならない"),
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
    ("記事の重複・要紧・おすすめ・配色・配図の候補", "rule", "前から規則（bigram・正規表現・好みの学習・減色・画像の検査）"),
    ("AI 編集：同じ件を合わせて、どれを載せるか", "gate", "意味の判断（違う言語の同じ件・重要度）は規則だと外れが多い。規則の下書き（fallback_stories）は残し、仕上げは AI。仕事があるときだけ起こす"),
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
            f'<small>{e(q.get("when", ""))}</small>{_chips(_own(q))}</button>'
            for q in (by.get(x) for x in n.get("subs", [])) if q)
        return (f'<div class="an an-p" id="{e(n["id"])}"><button type="button" class="an-b" data-open="proc-{e(p["id"])}">'
                f'<b>{e(p["name"])}</b><small>{e(p.get("when", ""))}</small>{_chips(_own(p))}<i>流れの図を見る ›</i></button>{subs}</div>')
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
            '<span>番号の矢印 = データの流れ · 四角い部品をクリックで流れの図</span></p>'
            f'<div class="arch dgb" id="arch" data-edges="arch-edges"><svg class="dg-svg" aria-hidden="true"></svg>{zones}</div>'
            f'<details class="arch-list"><summary>矢印の一覧（{len(EDGES)}）</summary><ol>{lst}</ol></details>'
            f'<script type="application/json" id="arch-edges">{_edges_json([list(x) for x in EDGES])}</script>')


def _lane_tag(lane):
    name, cost, kind = LANES.get(lane, (lane, "", "free"))
    return f'<span class="pl pl-{kind}">{e(name)}</span>'


def _dg_node(pid, n, row, col, ncols):
    """流れの図の 1 つの部品（手順・判断・並べて試す・表・保存先）。"""
    k, nid = n["kind"], f'dg-{pid}-{n["id"]}'
    badge = f'<span class="dn-x">{e(n["x"])}</span>' if n.get("x") else ""
    head = f'<b class="dn-t">{e(n["title"])}</b>{badge}'
    text = f'<small class="dn-s">{e(n["text"])}</small>' if n.get("text") else ""
    span = f"grid-row:{row};grid-column:{'1 / -1' if k in ('fan', 'table') else col}"
    lane = f'<span class="dn-l">{e(LANES.get(n.get("lane"), (n.get("lane") or "",))[0])}</span>'
    if k == "fan":
        items = "".join(
            f'<li id="{nid}-{j}"><i>{e(it[0])}</i><b>{e(it[1])}</b><small>{e(it[2])}</small>{_chips(it[3:4] and [it[3]])}</li>'
            for j, it in enumerate(n["items"]))
        mode = n.get("mode", "上から順に · 足りるまで")
        return (f'<div class="dn dn-fan" id="{nid}" style="{span}">{lane}<div class="dn-h">{head}<span class="dn-m">{e(mode)}</span></div>'
                f'{text}<ol class="dn-row">{items}</ol>{_chips(n.get("uses"))}</div>')
    if k == "table":
        rows = "".join(f'<div class="dt-c"><b>{e(a)}</b><span>{e(b)}</span></div>' for a, b in n["rows"])
        return f'<div class="dn dn-table" id="{nid}" style="{span}">{lane}<div class="dn-h">{head}</div>{text}<div class="dt">{rows}</div>{_chips(n.get("uses"))}</div>'
    shape = {"decision": "dn-dec", "store": "dn-store"}.get(k, "dn-step")
    inner = f'{lane}<div class="dn-h">{head}</div>{text}{_chips(n.get("uses"))}'
    if k == "decision":
        yes = f'<small class="dn-s dn-yes">はい → {e(n["yes"])}</small>' if n.get("yes") else ""
        inner = (f'{lane}<div class="dn-dia"><span>{head}</span></div>'   # ひし形には問いだけ。条件と「はい」の行き先は下に
                 + (f'<div class="dn-cap">{text}{yes}</div>' if text or yes else "") + _chips(n.get("uses")))
    out = f'<div class="dn {shape}" id="{nid}" style="{span}">{inner}</div>'
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
            + f'{flow_diagram(p)}<p class="pd-files"><b>仕組みの場所</b>{files}</p></dialog>')


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
