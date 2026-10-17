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
    "ai": ("Claude（AI 編集）", "サブスク枠", "ai"),
    "repo": ("リポジトリ", "無料", "free"),
    "web": ("ウェブ・Supabase", "無料", "free"),
}

PROCESSES = [
    {
        "id": "emblem", "name": "小元素の選定", "en": "EMBLEM", "lane": "ai",
        "schedule": "edit",
        "when": "AI 編集の最初",
        "trigger": "新しい関注項が入ったとき ／ AI 編集の最初に毎回（足りない関注項だけ）",
        "summary": "各版面の右上に貼るステッカーを、作品の種類に合わせて自動で集める。足りない関注項を見つけて、決まった順で取り方を変えながら埋める。",
        "files": ["scripts/emblem_fill.py", "scripts/emblem.py", "scripts/face_id.py"], "doc": "TEMPLATES.md",
        "flow": [
            {"id": "audit", "kind": "step", "lane": "ai", "title": "状況を調べる（--audit）",
             "text": "全関注項の「種類・目標の枚数・いまの枚数」を出す。足りないものから順に処理する。"},
            {"id": "need", "kind": "decision", "lane": "ai", "title": "目標に届いている？", "text": "いまの枚数 ≥ 目標",
             "yes": "何もしない（その関注項は終わり）", "no": "次へ（emblem_skip は理由にならない）"},
            {"id": "kind", "kind": "table", "lane": "ai", "title": "種類で目標を決める",
             "text": "emblem_kind（なければ type から推定）。人物の多いものは最大 10 枚、ふつうは 6 枚まで。",
             "rows": [("person 本人", "別の写真 6（3〜10）"), ("group グループ", "メンバー全員（3〜10）"),
                      ("character キャラ・出演者", "6（3〜10。emblem_who で挙げた全員）"),
                      ("brand ブランド", "公式ロゴ 1"), ("topic 主題", "ロゴ・トロフィー・ボール・場所 3（2〜5）")]},
            {"id": "src", "kind": "fan", "lane": "ai", "title": "候補を集める（上から順、足りるまで）",
             "items": [("0", "直接指定", "emblem_urls に書いた公式画像"), ("1", "AniList", "アニメ・漫画の主役（人気順）"),
                       ("2", "Fandom", "キャラのページの代表画像"), ("3", "Wikidata / Wikipedia", "公式ロゴ（P154）・本人・メンバーの記事の画像"),
                       ("4", "Commons", "同じ名前の写真（ライセンス付き）"), ("5", "新聞の配図", "集めた記事の写真（題名に名前）"),
                       ("6", "公式サイト", "og:image と大きい画像"), ("7", "Web 画像検索", "最後の手段（要確認）"),
                       ("8", "Twemoji", "絵文字アイコン（0 枚を防ぐ最後の砦）")]},
            {"id": "ok", "kind": "step", "lane": "ai", "title": "使える画像か確かめる",
             "text": "短辺 160px 以上・開ける。ほぼ同じ画像（平均ハッシュ）は 1 枚に。"},
            {"id": "who", "kind": "decision", "lane": "ai", "title": "人物・グループ？", "text": "顔で確かめる対象か",
             "yes": "本人確認（下）", "no": "ロゴ・主題：ファイル名か記事名に名前が入っていること"},
            {"id": "face", "kind": "step", "lane": "ai", "title": "本人確認（face_id）",
             "text": "顔を検出（YuNet）→ 特徴量（SFace）。記事の代表画像と似ている（類似度 ≥ 0.363）ものだけ残す。"
                     "代表画像が合わないときは「いちばん大きい同じ顔の集まり」を本人とする。顔がない・別人・遠景は落とす。"},
            {"id": "pick", "kind": "step", "lane": "ai", "title": "一覧を作って選ぶ",
             "text": "番号付きの候補一覧を作る。AI が目で確かめて番号を選ぶ（--commit）。自動のとき（--auto）は上の順で選ぶ。"},
            {"id": "cut", "kind": "step", "lane": "ai", "title": "抠图して整える",
             "text": "rembg（birefnet）で人物だけ切り抜く。顔の大きさをそろえ、全身は上半身に、体が端で切れたものは外す。"},
            {"id": "done", "kind": "decision", "lane": "ai", "title": "目標に届いた？", "text": "届くまで次の取り方へ",
             "yes": "書き込みへ", "no": "上の「候補を集める」の次の取り方に戻る。最後は Twemoji で必ず 1 枚以上"},
            {"id": "write", "kind": "store", "lane": "repo", "title": "items.yaml に書く",
             "text": "emblem（出所つき）・theme。抠图した画像は docs/emblems/*.webp に保存。"},
            {"id": "page", "kind": "step", "lane": "web", "title": "網页に貼る",
             "text": "版面の右上に表示。開くたびにランダムで 1 枚。この管理ページの「小元素」で枚数を見られる。"},
        ],
    },
    {
        "id": "emblem-cron", "name": "小元素の自動補完（定時）", "en": "EMBLEM CRON", "lane": "ai",
        "schedule": [(h, 40) for h in range(0, 24, 4)],   # UTC（日本時間 1・5・9・13・17・21 時 40 分）。定時タスク「小元素 · 后台补全」
        "when": "4 時間ごと · 40 分 · 4 本並列",
        "trigger": "定時タスク（Claude のスケジュール）が呼ぶたび。1 回あたり約 40 分の予算",
        "summary": "目標の枚数に届いていない版面の小元素を、時間の予算の中で足りない順に埋める。確かな画像だけ自動で書き、"
                   "決めきれないものは「要確認」として AI が候補の一覧を目で見て選ぶ。進捗はこの管理ページの「小元素 → 進捗」。",
        "files": ["scripts/emblem_fill.py", "scripts/face_id.py", "state/emblem_progress.json"], "doc": "TEMPLATES.md",
        "flow": [
            {"id": "b1", "kind": "step", "lane": "ai", "title": "main を最新にして準備",
             "text": "抠图（rembg）と顔のモデル（YuNet・SFace、HuggingFace から）を入れる。--audit で全版面の缺口を見る。"},
            {"id": "b2", "kind": "step", "lane": "ai", "title": "後台モード（--background --minutes 40）",
             "text": "足りない枚数の多い順に、4 本並列（--workers、コンテナの 4 コアに合わせる）。候補集め・本人確認は同時に、"
                     "items.yaml への書き込みと抠图は 1 本ずつ。残り 2 分を切ったら次に入らず、続きは次の回。"},
            {"id": "b2l", "kind": "table", "lane": "ai", "title": "並列の限り（速さを決めるもの）",
             "text": "並列にしても、外のサイトの決まりは超えない。",
             "rows": [("Wikipedia・Wikidata・Commons", "同じサイトへは全スレッド合わせて 1.3 秒に 1 回。429 が続いたら 5 分休む"),
                      ("抠图（rembg）・items.yaml", "1 本ずつ（同時に書くと壊れる）"),
                      ("コンテナ", "4 コア・メモリ 15GB → 4 本まで"),
                      ("定時タスク", "最短 1 時間ごと・1 回 1 つのコンテナ（いまは 4 時間ごと）")]},
            {"id": "b3", "kind": "decision", "lane": "ai", "title": "24 時間以内に失敗した？", "text": "進捗の failed_at",
             "yes": "今回は飛ばす", "no": "候補を集める（「小元素の選定」と同じ順）"},
            {"id": "b4", "kind": "table", "lane": "ai", "title": "自動で選ぶ規則",
             "text": "Web 画像検索の結果は自動では使わない（出所が不確か）。",
             "rows": [("本人・グループ・出演者", "本人確認（face_id）を通ったものだけ"),
                      ("brand ブランド", "Wikidata の公式ロゴ（P154）→ 公式サイトのロゴ"),
                      ("topic 主題", "Wikidata → Commons → Twemoji"),
                      ("絵のキャラ", "直接指定（公式の立ち絵）・Fandom だけ、1 人 1 枚")]},
            {"id": "b5", "kind": "decision", "lane": "ai", "title": "目標に届いた？", "text": "自動で書いたあとの枚数",
             "yes": "そろっている", "no": "残りの候補があれば一覧を作り直して「要確認」、なければ「失敗」（24 時間後に再挑戦）"},
            {"id": "b6", "kind": "step", "lane": "ai", "title": "要確認を目で選ぶ",
             "text": "AI が一覧（/tmp/wishlist-emblem/<名>.jpg）を見て、本人・本作のものだけ番号で --commit。広告・別人・白紙は選ばない。"},
            {"id": "b7", "kind": "store", "lane": "repo", "title": "state/emblem_progress.json",
             "text": "版面ごとの状態・枚数・試した取り方・最近の結果、全体の開始時刻と最近の実行。1 版面ごとに保存。"
                     "1 行ずつの記録は state/log/emblem.json（管理ページ「バックグラウンド → ログ」）。"},
            {"id": "b8", "kind": "step", "lane": "ai", "title": "render して main に push",
             "text": "items.yaml・docs・state をコミット。網页と管理ページの進捗が更新される。"},
        ],
    },
    {
        "id": "collect", "name": "ニュース収集", "en": "COLLECT", "lane": "actions",
        "schedule": [(h, 17) for h in range(0, 24, 2)], "workflow": "digest.yml",
        "when": "2 時間ごと · 6 本並列",
        "trigger": "2 時間ごと（日本時間 奇数時 17 分）／ 毎週月曜 9:47 に周報",
        "summary": "関注項ごとにニュース・ SNS・価格を集めて inbox に溜め、簡報を出刊する。要紧消息は当日 Discord へ。",
        "files": [".github/workflows/digest.yml", "scripts/digest.py", "scripts/sources.py"], "doc": "README.md",
        "flow": [
            {"id": "c1", "kind": "step", "lane": "actions", "title": "収集して簡報を更新",
             "text": "関注項 6 本並列で抓取（同じサイトの間隔はスレッド全部で共有：Reddit 2 秒・Google / Bing 0.5 秒）。"
                     "去重は元の順番で。match / exclude の規則で拾い、heat 用の外部データも保存。"},
            {"id": "c2", "kind": "store", "lane": "repo", "title": "inbox/日付.json", "text": "その日の条目。AI 編集が読む元データ。"},
            {"id": "c3", "kind": "decision", "lane": "actions", "title": "要紧消息がある？", "text": "urgent_patterns に合う条目",
             "yes": "当日 Discord に通知", "no": "通知なし"},
            {"id": "c4", "kind": "step", "lane": "actions", "title": "Discord へ", "text": "機能更新・愿望清单・新関注項・周報（月曜）もここで。"},
            {"id": "c5", "kind": "step", "lane": "actions", "title": "コミット → GitHub Pages", "text": "docs/ を公開。"},
            {"id": "c6", "kind": "decision", "lane": "actions", "title": "新しい関注項が入った？", "text": "known_items にない名前",
             "yes": "AI 編集（Routine）をすぐ起動", "no": "定時の編排を待つ"},
        ],
    },
    {
        "id": "edit", "name": "AI 編集", "en": "EDIT", "lane": "ai",
        "schedule": [(4, 43), (15, 43)],   # 日本時間 13:43 / 0:43（北京時間 12:43 / 23:43）
        "when": "毎日 13:43 · 0:43（日本時間）",
        "trigger": "毎日 2 回（日本時間 13:43 / 0:43）／ 新しい関注項が入ったとき",
        "summary": "inbox の条目から重要なものを選び、同じ件を合わせて、見出しと配図を決めて出刊する。新しい関注項は版面も設計する。",
        "files": ["EDITING.md", "scripts/digest.py", "TEMPLATES.md"], "doc": "EDITING.md",
        "flow": [
            {"id": "e1", "kind": "step", "lane": "ai", "title": "版面の設計と小元素の補完", "text": "motif・theme・like_fx を決め、小元素が足りない関注項を埋める（「小元素の選定」）。"},
            {"id": "e2", "kind": "decision", "lane": "ai", "title": "編排が必要？", "text": "最新の inbox が今日で、新しい条目がある",
             "yes": "編排へ", "no": "何も変えずに終わり"},
            {"id": "e3", "kind": "step", "lane": "ai", "title": "編排して edit.json を書く", "text": "priority と notes を読み、同じ件を合わせ、見出しは原文のまま。篇幅は S / M / L に従う。"},
            {"id": "e4", "kind": "step", "lane": "ai", "title": "配図を選ぶ", "text": "候補の一覧を目で見て、顔が切れない・内容に合う 1 枚。"},
            {"id": "e5", "kind": "step", "lane": "ai", "title": "出刊してプッシュ", "text": "digest.py publish → inbox / reports / state / docs をコミット。"},
        ],
    },
    {
        "id": "render", "name": "ページ生成", "en": "RENDER", "lane": "actions",
        "workflow": "render.yml",
        "when": "push のたび",
        "trigger": "main に push されたとき（コード・items.yaml・愿望清单など）",
        "summary": "収集を待たず、網页だけを 1 分ほどで作り直して公開する。",
        "files": [".github/workflows/render.yml", "scripts/render.py"], "doc": "CLAUDE.md",
        "flow": [
            {"id": "r1", "kind": "step", "lane": "actions", "title": "PR を main に合流", "text": "scripts / templates / items.yaml などが変わったとき。"},
            {"id": "r2", "kind": "step", "lane": "actions", "title": "render だけ実行", "text": "篇幅（S / M / L）を Supabase から読み、docs/*.html を作る。"},
            {"id": "r3", "kind": "store", "lane": "repo", "title": "GitHub Pages に公開", "text": "約 1 分で反映。連続で合流したときは最後の 1 回だけ。"},
        ],
    },
    {
        "id": "requests", "name": "設定ページの依頼", "en": "REQUESTS", "lane": "web",
        "workflow": "requests.yml",
        "when": "依頼のたび",
        "trigger": "設定ページで関注項の追加・変更・篇幅の変更を送ったとき（待ち時間なし）",
        "summary": "設定ページの依頼を Supabase が受け、GitHub Actions を起こして items.yaml に反映する。",
        "files": [".github/workflows/requests.yml", "docs/additem.js", "db/instant.sql"], "doc": "CLAUDE.md",
        "flow": [
            {"id": "q1", "kind": "step", "lane": "web", "title": "設定ページで送信", "text": "一問一答のウィザードで関注項を作る。"},
            {"id": "q2", "kind": "store", "lane": "web", "title": "Supabase item_requests", "text": "依頼を保存し、GitHub を起動。"},
            {"id": "q3", "kind": "step", "lane": "actions", "title": "items.yaml に書いて render", "text": "写真・熱度など他の設定もここで。"},
            {"id": "q4", "kind": "decision", "lane": "actions", "title": "新しい関注項？", "text": "名前が既存にない",
             "yes": "すぐ収集 → AI 編集が版面を設計", "no": "網页の更新だけ"},
        ],
    },
    {
        "id": "photos", "name": "写真から愿望", "en": "PHOTOS", "lane": "ai",
        "schedule": [(1, 47), (5, 47), (9, 47), (13, 47)],   # 日本時間 10 / 14 / 18 / 22 時 47 分
        "when": "1 日 4 回",
        "trigger": "愿望清单ページで撮った写真が溜まったとき（Actions が 2 時間ごとに書き出し）",
        "summary": "写真に写っているものを認識して、愿望清单に 1 件として整理する。",
        "files": ["PHOTOS.md", "wishlist.yaml"], "doc": "PHOTOS.md",
        "flow": [
            {"id": "p1", "kind": "step", "lane": "web", "title": "写真を撮って送る", "text": "「想要 / 纠结」を選ぶ。Supabase に保存。"},
            {"id": "p2", "kind": "store", "lane": "actions", "title": "inbox/photos/", "text": "Actions が写真（.jpg）と .json を書き出す。"},
            {"id": "p3", "kind": "decision", "lane": "ai", "title": "写真がある？", "text": ".json が 1 つ以上",
             "yes": "認識へ", "no": "何も変えずに終わり"},
            {"id": "p4", "kind": "step", "lane": "ai", "title": "認識して wishlist.yaml に追加", "text": "名前・価格・規格・タグ。写真は物だけ切り抜く。"},
            {"id": "p5", "kind": "step", "lane": "actions", "title": "写真を消して push", "text": "「已加入」の印は次の Actions が付ける。"},
        ],
    },
]


# ---------------------------------------------------------------- 全体の構成図（アーキテクチャ）
# 枠（zone）：style = ext（外のサービス）/ temp（その都度立ち上がる環境・破線）/ keep（ずっと残る場所・実線）。
# 枠の中の部品：proc = プロセスの id（クリックで流れが開く）、それ以外は保存先・外部サービス（説明だけ）。
# 矢印（EDGES）：(番号, 元, 先, 説明, 色)。色 = data（収集）/ web（網页）/ ai（AI）/ notify（Discord）/ db（データベース）。
ARCH = [
    {"id": "src", "title": "インターネット", "note": "ニュースと画像の出どころ", "cost": "無料", "style": "ext", "nodes": [
        {"id": "n-news", "label": "ニュース", "text": "Google ニュース・Bing・Reddit・RSS"},
        {"id": "n-api", "label": "作品データ", "text": "Steam・AniList・TMDB・Wikipedia 閲覧数"},
        {"id": "n-img", "label": "画像", "text": "Wikidata・Commons・Fandom・公式サイト"},
    ]},
    {"id": "act", "title": "GitHub Actions", "note": "毎回新しいサーバー · 終わったら消える", "cost": "無料", "style": "temp", "nodes": [
        {"id": "p-collect", "proc": "collect"}, {"id": "p-requests", "proc": "requests"}, {"id": "p-render", "proc": "render"}]},
    {"id": "repo", "title": "GitHub リポジトリ", "note": "ずっと残る · 全部の元データ", "cost": "無料", "style": "keep", "nodes": [
        {"id": "s-inbox", "label": "inbox/", "text": "集めた記事・edit.json・写真"},
        {"id": "s-items", "label": "items.yaml", "text": "関注項・版面・小元素"},
        {"id": "s-wish", "label": "wishlist.yaml", "text": "愿望清单"},
        {"id": "s-state", "label": "state/", "text": "進捗・ログ・話題度・投票の控え"}]},
    {"id": "ai", "title": "Anthropic · Claude", "note": "定時タスク · 毎回新しいコンテナ（4 コア）", "cost": "サブスク枠", "style": "temp", "nodes": [
        {"id": "p-edit", "proc": "edit", "sub": "emblem"}, {"id": "p-emblem-cron", "proc": "emblem-cron"}, {"id": "p-photos", "proc": "photos"}]},
    {"id": "db", "title": "Supabase", "note": "データベース", "cost": "無料枠", "style": "keep", "nodes": [
        {"id": "s-db", "label": "feedback · sizes · item_requests · photo_inbox", "text": "👍👎・篇幅・設定ページの依頼・写真"}]},
    {"id": "pages", "title": "GitHub Pages", "note": "公開の網页", "cost": "無料", "style": "keep", "nodes": [
        {"id": "s-pages", "label": "網页", "text": "簡報・設定・愿望清单・管理ページ"}]},
    {"id": "dc", "title": "Discord", "note": "通知", "cost": "無料", "style": "ext", "nodes": [
        {"id": "s-discord", "label": "あなたのチャンネル", "text": "要紧消息は当日・周報は月曜"}]},
    {"id": "you", "title": "あなた", "note": "スマホ・パソコン", "cost": "", "style": "you", "nodes": [
        {"id": "s-you", "label": "見る・押す・撮る", "text": "簡報を読む・👍👎・関注項の追加・写真"}]},
]
EDGES = [
    (1, "n-news", "p-collect", "記事を集める", "data"),
    (2, "n-api", "p-collect", "話題度・現状", "data"),
    (3, "p-collect", "s-inbox", "inbox に書く", "data"),
    (4, "p-collect", "s-discord", "要紧消息", "notify"),
    (5, "s-inbox", "p-edit", "読む", "ai"),
    (6, "p-edit", "s-inbox", "edit.json・出刊", "ai"),
    (7, "n-img", "p-emblem-cron", "画像を探す", "ai"),
    (8, "p-emblem-cron", "s-items", "小元素を書く", "ai"),
    (9, "s-items", "p-render", "push", "web"),
    (10, "p-render", "s-pages", "公開", "web"),
    (11, "s-pages", "s-you", "見る", "web"),
    (12, "s-you", "s-db", "👍・設定・写真", "db"),
    (13, "s-db", "p-requests", "依頼", "db"),
    (14, "p-requests", "s-items", "items.yaml に反映", "db"),
    (15, "s-db", "p-collect", "写真・投票を取り込む", "db"),
    (16, "s-inbox", "p-photos", "写真", "ai"),
    (17, "p-photos", "s-wish", "愿望を足す", "ai"),
    (18, "s-discord", "s-you", "通知", "notify"),
]
# 並列で動かすときの限り（管理ページ「バックグラウンド → 並列と制限」）。(仕組み, いまの並列, 限り・理由)
LIMITS = [
    ("ニュース収集", "6 本並列", "GitHub Actions のサーバーは 4 コア。待ちが多いので 6 本。同じサイトの間隔は全スレッドで共有（Reddit 2 秒・Google / Bing 0.5 秒）"),
    ("小元素の自動補完", "4 本並列", "定時タスクのコンテナは 4 コア・メモリ 15GB。抠图（rembg）と items.yaml への書き込みは 1 本ずつ"),
    ("Wikipedia・Wikidata・Commons", "1.3 秒に 1 回", "全スレッド合わせて。続けて叩くと 429（多すぎ）になり、続いたら 5 分休む → ここは並列でも速くならない"),
    ("Claude の定時タスク", "1 回 1 コンテナ", "最短 1 時間ごと。1 回の中で並列はできるが、同じタスクを同時に 2 つは動かない（いまは 4 時間ごと・40 分）"),
    ("GitHub Actions", "同じワークフローは 1 本ずつ", "収集・依頼は前の回が終わるまで待つ（concurrency）。ページ生成は新しい回が来たら古い回を止める"),
    ("AI 編集・写真から愿望", "1 本", "1 日の決まった時刻に 1 回ずつ。同じ inbox を書くので並列にしない"),
]
EDGE_JA = {"data": "収集", "web": "網页", "ai": "AI", "notify": "Discord", "db": "データベース"}


def _arch_node(n, by):
    if n.get("proc"):
        p = by[n["proc"]]
        sub = by.get(n.get("sub")) if n.get("sub") else None
        subb = (f'<button type="button" class="an-sub" data-open="proc-{e(sub["id"])}">＋ {e(sub["name"])}'
                f'<small>{e(sub.get("when", ""))}</small></button>') if sub else ""
        return (f'<div class="an an-p" id="{e(n["id"])}"><button type="button" class="an-b" data-open="proc-{e(p["id"])}">'
                f'<b>{e(p["name"])}</b><small>{e(p.get("when", ""))}</small><i>流れを見る ›</i></button>{subb}</div>')
    return f'<div class="an an-s" id="{e(n["id"])}"><b>{e(n["label"])}</b><small>{e(n["text"])}</small></div>'


def _arch_zone(z, by):
    head = (f'<div class="az-h"><b>{e(z["title"])}</b><small>{e(z.get("note", ""))}</small>'
            + (f'<span class="az-c{" ai" if "サブスク" in z.get("cost", "") else ""}">{e(z["cost"])}</span>' if z.get("cost") else "") + "</div>")
    inner = "".join(_arch_node(n, by) for n in z.get("nodes", []))
    inner += "".join(_arch_zone(b, by) for b in z.get("boxes", []))
    return f'<section class="az az-{e(z["style"])}" style="grid-area:{e(z["id"])}" data-z="{e(z["id"])}">{head}<div class="az-b">{inner}</div></section>'


def architecture(processes=None):
    """全体の構成図：どの仕組みがどこで動き、データがどう流れるか。プロセスの部品をクリックすると、その流れ（detail）が開く。
    矢印は JS（ARCH_JS）が部品の位置から描く。狭い画面では矢印の代わりに番号つきの一覧を読む。"""
    by = {p["id"]: p for p in PROCESSES + list(processes or [])}   # 図の部品はいつもの PROCESSES から
    placed = {n.get(k) for z in ARCH for n in z["nodes"] for k in ("proc", "sub")}
    extra = [p for p in PROCESSES if p["id"] not in placed]   # ARCH にまだ置いていない仕組みは「そのほか」に（図から開けないものを作らない）
    zones = "".join(_arch_zone(z, by) for z in ARCH + ([{"id": "etc", "title": "そのほかの仕組み", "note": "図の場所がまだ決まっていないもの",
                                                           "style": "keep", "nodes": [{"id": f"p-{p['id']}", "proc": p["id"]} for p in extra]}] if extra else []))
    edges = json.dumps([list(x) for x in EDGES], ensure_ascii=False).replace("</", "<\\/")
    legend = "".join(f'<span class="ae-{k}"><i></i>{e(v)}</span>' for k, v in EDGE_JA.items())
    names = {}
    for z in ARCH:
        for n in z.get("nodes", []) + [m for b in z.get("boxes", []) for m in b["nodes"]]:
            names[n["id"]] = by[n["proc"]]["name"] if n.get("proc") else n["label"]
    lst = "".join(f'<li class="ae-{c}"><em>{i}</em>{e(names[a])} → {e(names[b])}<small>{e(t)}</small></li>' for i, a, b, t, c in EDGES)
    return (f'<p class="arch-lg"><span class="lg-z temp">破線 = その都度立ち上がる環境</span><span class="lg-z keep">実線 = ずっと残る場所</span>{legend}'
            '<span>番号の矢印 = データの流れ · 四角い部品をクリックで流れ</span></p>'
            f'<div class="arch" id="arch"><svg class="arch-svg" aria-hidden="true"></svg>{zones}</div>'
            f'<details class="arch-list"><summary>矢印の一覧（{len(EDGES)}）</summary><ol>{lst}</ol></details>'
            f'<script type="application/json" id="arch-edges">{edges}</script>')


def _lane_tag(lane):
    name, cost, kind = LANES.get(lane, (lane, "", "free"))
    return f'<span class="pl pl-{kind}">{e(name)}</span>'


def _node(i, n):
    k = n["kind"]
    head = f'<div class="pn-h"><em>{i}</em><b>{e(n["title"])}</b>{_lane_tag(n.get("lane"))}</div>'
    body = f'<p>{e(n["text"])}</p>' if n.get("text") else ""
    if k == "decision":
        body += (f'<div class="pn-br"><span class="pn-y"><i>はい</i>{e(n["yes"])}</span>'
                 f'<span class="pn-n"><i>いいえ</i>{e(n["no"])}</span></div>')
    elif k == "fan":
        body += '<ol class="pn-opts">' + "".join(
            f'<li><i>{e(a)}</i><b>{e(b)}</b><span>{e(c)}</span></li>' for a, b, c in n["items"]) + "</ol>"
    elif k == "table":
        body += '<dl class="pn-tbl">' + "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in n["rows"]) + "</dl>"
    return f'<li class="pn pn-{k}">{head}{body}</li>'


def detail(p):
    lane = LANES.get(p["lane"], (p["lane"], "", "free"))
    files = " ".join(f"<code>{e(f)}</code>" for f in p.get("files", []))
    return (f'<dialog class="pdlg" id="proc-{e(p["id"])}" aria-label="{e(p["name"])}の流れ">'
            f'<div class="pd-h"><div><small>{e(p["en"])}</small><h3>{e(p["name"])}</h3></div>'
            f'<button type="button" class="pd-x" data-close aria-label="閉じる">×</button></div>'
            f'<p class="pd-sum">{e(p["summary"])}</p>'
            f'<div class="pd-meta"><span><b>いつ</b>{e(p["trigger"])}</span>'
            f'<span><b>どこで</b>{e(lane[0])}</span><span><b>費用</b>{e(lane[1])}</span></div>'
            f'<ol class="pd-flow">{"".join(_node(i + 1, n) for i, n in enumerate(p["flow"]))}</ol>'
            f'<p class="pd-files"><b>仕組みの場所</b>{files}</p></dialog>')


def render(processes=None):
    """管理ページに入れる HTML（全体の構成図 + 各プロセスの詳細ダイアログ）。"""
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
.arch-svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none;z-index:2}
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
.an-b i{font:700 var(--fs-label) var(--font-sans);font-style:normal;color:var(--rose)}
.an-sub{border-top:1.5px dashed var(--ink);font:700 12px/1.4 var(--font-sans);background:var(--sheet)}
.an-b:focus-visible,.an-sub:focus-visible{outline:3px solid var(--gold);outline-offset:-3px}
.an-b:hover b,.an-sub:hover{text-decoration:underline}
.az-you .an{background:transparent;color:var(--card);border-color:var(--card)}
.arch .hl{outline:3px solid var(--gold);outline-offset:2px}
.arch-svg path{fill:none;stroke-width:2.2}
.arch-svg .dim{opacity:.15}
.arch-svg text{font:900 11px var(--font-mono);fill:var(--card);text-anchor:middle;dominant-baseline:central}
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
 .arch-svg{display:none}
 .az[data-z=you]>.az-b{flex-direction:column}
}
.pcs{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}
.pc{display:flex;flex-direction:column;gap:4px;text-align:left;padding:10px 12px 12px;background:var(--card);color:var(--ink);cursor:pointer;
 border:2px solid var(--ink);box-shadow:var(--shadow);font:inherit;transition:transform .1s,box-shadow .1s}
.pc:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
.pc:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.pc-t svg{display:block;width:100%;height:100%}
.pc-t{display:block;height:150px;overflow:hidden;background:var(--sheet);border:1px solid var(--ink);padding:4px;color:var(--ink)}
.pc b{font:900 15px/1.3 var(--font-sans);margin-top:4px}
.pc small{font:700 10px var(--font-mono);letter-spacing:.2em;opacity:.7}
.pc-w{font-size:12px;line-height:1.5;opacity:.85}
.pl{display:inline-block;align-self:flex-start;font:700 10px var(--font-mono);letter-spacing:.04em;padding:1px 8px;transform:skewX(var(--skew));background:var(--ink);color:var(--card);white-space:nowrap}
.pl-ai{background:var(--gold);color:var(--ink)}.pl-free{background:var(--good);color:var(--card)}
.pdlg{width:min(860px,calc(100vw - 24px));max-height:calc(100vh - 24px);padding:0;border:3px solid var(--ink);box-shadow:8px 8px 0 var(--ink);background:var(--paper);color:var(--ink)}
.pdlg::backdrop{background:rgba(26,28,34,.55)}
.pd-h{display:flex;justify-content:space-between;gap:12px;padding:14px 18px;background:var(--ink);color:var(--card);position:sticky;top:0;z-index:2}
.pd-h small{font:700 10px var(--font-mono);letter-spacing:.3em;opacity:.7}
.pd-h h3{margin:0;font:900 22px/1.3 var(--font-sans)}
.pd-x{font:900 22px/1 var(--font-sans);background:none;border:2px solid var(--card);color:var(--card);width:38px;height:38px;cursor:pointer}
.pd-x:hover{background:var(--alert);border-color:var(--alert)}
.pd-sum{margin:0;padding:14px 18px 6px;font-size:14px;line-height:1.7}
.pd-meta{display:flex;flex-wrap:wrap;gap:6px 18px;padding:0 18px 14px;font-size:13px}
.pd-meta b{font:700 10px var(--font-mono);letter-spacing:.15em;margin-right:6px;padding:1px 6px;background:var(--ink);color:var(--card)}
.pd-flow{list-style:none;margin:0;padding:6px 18px 8px;display:flex;flex-direction:column;gap:0}
.pn{position:relative;background:var(--card);border:2px solid var(--ink);padding:10px 14px 12px;margin-bottom:22px;box-shadow:var(--shadow)}
.pn::after{content:"▼";position:absolute;left:50%;bottom:-20px;transform:translateX(-50%);font-size:12px;color:var(--alert)}
.pn:last-child{margin-bottom:6px}.pn:last-child::after{display:none}
.pn-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.pn-h em{font:900 13px var(--font-mono);font-style:normal;background:var(--ink);color:var(--card);min-width:26px;height:26px;display:grid;place-items:center;transform:skewX(var(--skew))}
.pn-h b{font:900 15px/1.4 var(--font-sans);flex:1;min-width:0}
.pn p{margin:6px 0 0;font-size:13px;line-height:1.7}
.pn-decision{background:var(--sheet);border-style:dashed}
.pn-br{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
.pn-br span{display:flex;flex-direction:column;gap:2px;font-size:13px;padding:6px 10px;border:2px solid var(--ink);background:var(--card)}
.pn-br i{font:700 10px var(--font-mono);font-style:normal;letter-spacing:.1em}
.pn-y i{color:var(--good)}.pn-n i{color:var(--alert)}
.pn-opts{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px}
.pn-opts li{display:grid;grid-template-columns:22px 92px 1fr;gap:6px;align-items:baseline;font-size:12px;line-height:1.5;padding:4px 8px;border:1px solid var(--ink);background:var(--paper)}
.pn-opts i{font:900 11px var(--font-mono);font-style:normal;color:var(--alert)}.pn-opts b{font-weight:900}
.pn-tbl{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;margin:8px 0 0;font-size:13px}
.pn-tbl dt{font-weight:900}.pn-tbl dd{margin:0}
.pd-files{margin:0;padding:6px 18px 16px;font-size:12px;display:flex;gap:6px 10px;flex-wrap:wrap;align-items:baseline}
.pd-files b{font:700 10px var(--font-mono);letter-spacing:.15em}
.pd-files code{font:700 11px var(--font-mono);background:var(--card);border:1px solid var(--ink);padding:0 6px}
@media (max-width:640px){.pdlg{width:100vw;max-width:100vw;height:100vh;max-height:100vh;margin:0;border-width:0}.pn-br{grid-template-columns:1fr}.pn-opts li{grid-template-columns:22px 82px 1fr}}
"""

JS = """
(() => {
  // 構成図の矢印：部品の位置から、直角に折れる線を描く。番号の丸は線の途中。部品にマウスを乗せると関係する線だけ濃く
  const arch = document.getElementById('arch'), data = document.getElementById('arch-edges');
  if (arch && data) {
    const EDGES = JSON.parse(data.textContent), svg = arch.querySelector('.arch-svg'), NS = 'http://www.w3.org/2000/svg';
    const COL = {data: 'var(--ink)', web: 'var(--rose)', ai: 'var(--good)', notify: 'var(--discord)', db: 'var(--viz-1)'};
    const draw = () => {
      if (getComputedStyle(svg).display === 'none') return;
      const box = arch.getBoundingClientRect();
      svg.setAttribute('viewBox', `0 0 ${box.width} ${box.height}`);
      let defs = '<defs>' + Object.keys(COL).map(k => `<marker id="ah-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" style="fill:${COL[k]};stroke:none"/></marker>`).join('') + '</defs>';
      const seen = {}, placed = [];
      const out = EDGES.map(([n, a, b, label, c]) => {
        const A = document.getElementById(a), B = document.getElementById(b);
        if (!A || !B) return '';
        const r1 = A.getBoundingClientRect(), r2 = B.getBoundingClientRect();
        const s = {l: r1.left - box.left, r: r1.right - box.left, t: r1.top - box.top, b: r1.bottom - box.top};
        const d = {l: r2.left - box.left, r: r2.right - box.left, t: r2.top - box.top, b: r2.bottom - box.top};
        const key = [a, b].sort().join('|'), off = (seen[key] = (seen[key] || 0) + 1) > 1 ? 14 : 0;   // 行きと帰りは少しずらす
        let p, mx, my;
        if (s.r + 8 < d.l || d.r + 8 < s.l) {   // 左右に離れている：横から出て、真ん中で縦に折れる
          const x1 = s.r < d.l ? s.r : s.l, x2 = s.r < d.l ? d.l : d.r;
          const y1 = (s.t + s.b) / 2 + off, y2 = (d.t + d.b) / 2 + off;
          mx = (x1 + x2) / 2 + off; my = (y1 + y2) / 2;
          p = `M${x1} ${y1}H${mx}V${y2}H${x2}`;
        } else {   // 上下：縦に出て、真ん中で横に折れる
          const down = s.b < d.t, y1 = down ? s.b : s.t, y2 = down ? d.t : d.b;
          const x1 = (s.l + s.r) / 2 + off, x2 = (d.l + d.r) / 2 + off;
          my = (y1 + y2) / 2 + off; mx = (x1 + x2) / 2;
          p = `M${x1} ${y1}V${my}H${x2}V${y2}`;
        }
        while (placed.some(([x, y]) => Math.abs(x - mx) < 22 && Math.abs(y - my) < 22)) my += 24;   // 番号の丸が重ならないように
        placed.push([mx, my]);
        return `<g data-a="${a}" data-b="${b}"><path d="${p}" style="stroke:${COL[c]}" marker-end="url(#ah-${c})"/>` +
               `<circle cx="${mx}" cy="${my}" r="10" style="fill:${COL[c]}"/><text x="${mx}" y="${my}">${n}</text><title>${n}. ${label}</title></g>`;
      });
      svg.innerHTML = defs + out.join('');
    };
    const hl = id => svg.querySelectorAll('g').forEach(g => g.classList.toggle('dim', !!id && g.dataset.a !== id && g.dataset.b !== id));
    arch.querySelectorAll('.an').forEach(n => { n.addEventListener('mouseenter', () => hl(n.id)); n.addEventListener('mouseleave', () => hl(null)); });
    draw(); addEventListener('resize', draw); if (document.fonts) document.fonts.ready.then(draw);
    if (window.ResizeObserver) new ResizeObserver(draw).observe(arch);
  }
  document.addEventListener('click', ev => {
    const open = ev.target.closest('[data-open]');
    if (open) { const d = document.getElementById(open.dataset.open); if (d && d.showModal) d.showModal(); return; }
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
