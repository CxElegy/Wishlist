"""小元素の判断の一覧：どの段で・何を・どの数で決めるか・AI か規則か。ここが 1 つだけの一覧。

判断のコードは emblem_fill.py（集める・確かめる・選ぶ）・face_id.py（人物の写真）・emblem.py（切り抜き・整える）に分かれているが、
数はそれぞれの定数をここから読むので、コードの数を変えれば一覧（管理ページの流れの図・TEMPLATES.md の説明）も変わる。
新しい判断を足したら、ここに 1 行足す（tests/test_emblem_fill.py が「コードの落とす理由が全部ここにあるか」を確かめる）。

by：ai = Claude が見て・読んで決める（トークンを使う）／ model = 学習済みモデルの数値を決まったしきい値で判断（規則）／ rule = プログラムの規則
"""

STAGES = ["① 何枚要るか", "② どこで探すか", "③ 使える画像か", "④ 人物の写真", "⑤ どれを選ぶか", "⑥ 切り抜き", "⑦ 整える", "⑧ 届かなかったら"]


def rules():
    """→ [{stage, title, rule, by, code, reason}]。reason は、その判断で落としたときの理由の言葉（ログ・管理ページに出る）。"""
    import emblem
    import emblem_fill as ef
    import face_id
    pct = lambda x: f"{x:.0%}"
    ceil = ef.CEIL
    return [
        # ① 何枚要るか
        {"stage": STAGES[0], "title": "種類を決める", "by": "ai", "code": "items.yaml emblem_kind",
         "rule": "新しい関注項が入ったとき、AI 編集が本人・グループ・キャラ・ブランド・主題を決め、名前（emblem_who）・代表作（emblem_examples）・分類（emblem_category）を書く。"
                 "書いていなければ type から規則で推定"},
        {"stage": STAGES[0], "title": "主要な要素を数える", "by": "rule", "code": "emblem_fill.roster",
         "rule": "emblem_category の分類の人数、なければ AniList の主役の人数を emblem_pool に。名前はほかのページから多く参照される順に足す"},
        {"stage": STAGES[0], "title": "上限 = 要素の数", "by": "rule", "code": "emblem_fill.rule",
         "rule": f"1 要素 1 枚。天井：キャラ・グループ {ceil['character']}・主題 {ceil['topic']}・本人 {ceil['person']}（別の写真）・ブランド {ceil['brand']}"},
        # ② どこで探すか
        {"stage": STAGES[1], "title": "取り方の順", "by": "rule", "code": "emblem_fill.gather / PICK_ORDER",
         "rule": "直接指定 → 代表作 → AniList → Fandom（透明な立ち絵 → 代表画像）→ Wikidata → Wikipedia → Commons → 記事の配図 → 公式サイト → YouTube → Twemoji。"
                 "足りなければ ② 名前を広げる → ③ 公式・記事のページ（同じ回の中で）"},
        {"stage": STAGES[1], "title": "実写の作品は役の姿", "by": "rule", "code": "emblem_fill.gather_roles",
         "rule": "剧・映画（emblem_people）は出演者の生活の写真を使わない。出演者 → 役（Fandom の出演者の記事の character/role 欄 → 出演作の表の役の列 → 検索。"
                 "役の記事に「演じた人 = 出演者」とあるものだけ。実在の人の記事・回の名前・出演者名を含む記事は除く）→ 役の記事の代表画像と剧照・作品の動画の場面（題名に作品名と役名。"
                 "インタビュー・試写会などは除く）。出演者の写真は本人確認の基準にだけ使う。足りなければ作品の主な画像（ポスター）"},
        {"stage": STAGES[1], "title": "代表作の記事", "by": "rule", "code": "emblem_fill.add_example",
         "rule": "記事名を言語つきで指定。別の言語版は言語間リンクでたどる（検索すると別の記事に当たる）"},
        {"stage": STAGES[1], "title": "YouTube は動画の場面", "by": "rule", "code": "emblem_fill.youtube_images / emblem.video_frame",
         "rule": f"投稿者のサムネイル（題名の字）ではなく自動の場面 hq{'・'.join(map(str, sorted(ef.YT_FRAMES)))}。上下の黒帯と下 {pct(emblem.SUBTITLE)}（字幕）を切る"},
        # ③ 使える画像か
        {"stage": STAGES[2], "title": "開ける・大きさ", "by": "rule", "code": "emblem.inspect", "reason": "使えない",
         "rule": f"{emblem.MAX_BYTES // 1_000_000}MB まで・短辺 {emblem.MIN_SIDE}px 以上"},
        {"stage": STAGES[2], "title": "白紙", "by": "rule", "code": "emblem_fill.check", "reason": "白紙",
         "rule": f"明るさの標準偏差 < {ef.BLANK_STD}（ほぼ一色）"},
        {"stage": STAGES[2], "title": "同じ画像", "by": "rule", "code": "emblem_fill.check", "reason": "同じ画像",
         "rule": f"差分ハッシュの違い ≤ {ef.SAME_BITS} ビット"},
        # ④ 人物の写真（本人・グループ・出演者）
        {"stage": STAGES[3], "title": "顔がない", "by": "model", "code": "face_id.photo_problem（YuNet）", "reason": "顔なし",
         "rule": "顔が見つからない（観客席・物・絵画）"},
        {"stage": STAGES[3], "title": "遠景", "by": "model", "code": "face_id.photo_problem", "reason": "遠景",
         "rule": f"顔の高さ < 画像の {pct(face_id.FACE_MIN_RATIO)}"},
        {"stage": STAGES[3], "title": "何人も写っている", "by": "model", "code": "face_id.photo_problem", "reason": "何人も写っている",
         "rule": f"2 番目の顔 ≥ いちばん大きい顔の {pct(face_id.CROWD_RATIO)}（面積）"},
        {"stage": STAGES[3], "title": "役の記事の代表画像は顔がなくてもよい", "by": "rule", "code": "emblem_fill.check（trust_noface）",
         "rule": "兜・仮面の役（Din Djarin・アイアンマン）は顔が見つからない。役の記事の代表画像に限って「顔なし」でも残す（顔が見えて別人なら外す）"},
        {"stage": STAGES[3], "title": "別人", "by": "model", "code": "face_id.same_person（SFace）", "reason": "別人",
         "rule": f"記事の代表画像との類似度 < {face_id.THRESHOLD}。代表画像が合わなければ、いちばん多い同じ顔を本人に"},
        # ⑤ どれを選ぶか
        {"stage": STAGES[4], "title": "確かな取り方だけ", "by": "rule", "code": "emblem_fill.AUTO_SOURCES", "reason": "確かでない取り方",
         "rule": "絵のキャラは直接指定・Fandom だけ（普通の言葉の名前は Wikipedia で別物に当たる）。Web 画像検索は自動では選ばない"},
        {"stage": STAGES[4], "title": "1 要素 1 枚", "by": "rule", "code": "emblem_fill.auto_pick", "reason": "重複（その人はもういる）",
         "rule": "同じ人・同じ代表作は 1 枚（本人だけは別の写真を何枚でも）"},
        {"stage": STAGES[4], "title": "使っている・外した画像は選ばない", "by": "rule", "code": "emblem_fill.auto_pick", "reason": "もう使っている・外した画像",
         "rule": "今ある小元素の画像と emblem_reject（目で見て外した画像）は二度と選ばない"},
        {"stage": STAGES[4], "title": "目標まで", "by": "rule", "code": "emblem_fill.auto_pick", "reason": "目標を超える",
         "rule": "目標の枚数に届いたら、残りの候補は選ばない"},
        # ⑥ 切り抜き（rembg birefnet-general-lite のあと）
        {"stage": STAGES[5], "title": "人物が見つからない", "by": "model", "code": "emblem.check_whole（rembg）", "reason": "人物が見つからない",
         "rule": f"切り抜いた結果が空。離れた部分は、いちばん大きいまとまりの {pct(emblem.PART_KEEP)} 以上だけ残す"},
        {"stage": STAGES[5], "title": "コマ・アップの切り抜き", "by": "rule", "code": "emblem.check_whole", "reason": "頭が上の端で大きく切れている",
         "rule": f"上の端の {pct(emblem.TOP_MAX)} を超えて人物（吹き出しなどを消した跡がえぐれる）"},
        {"stage": STAGES[5], "title": "顔が上の端で切れている", "by": "rule", "code": "emblem.check_whole", "reason": "顔が上の端で切れている",
         "rule": f"上の端に {pct(emblem.TOP_TOUCH)} 以上当たり、顔の上端が高さの {pct(emblem.FACE_TOP)} より上（髪だけなら可）"},
        {"stage": STAGES[5], "title": "体が左右の端で切れている", "by": "rule", "code": "emblem.check_whole", "reason": "体が左右の端で切れている",
         "rule": f"左右の端（上 {pct(emblem.SIDE_ZONE)}）に {pct(emblem.SIDE_MAX)} を超えて当たる"},
        {"stage": STAGES[5], "title": "小さすぎる", "by": "rule", "code": "emblem.check_whole", "reason": "人物が小さすぎる",
         "rule": f"人物の面積 < {pct(emblem.AREA_MIN)}"},
        {"stage": STAGES[5], "title": "輪郭がにじんでいる", "by": "rule", "code": "emblem.check_whole", "reason": "輪郭がにじんでいる",
         "rule": f"半透明 > {pct(emblem.SOFT_MAX)}"},
        {"stage": STAGES[5], "title": "暗すぎる（写真・場面）", "by": "rule", "code": "emblem.check_whole（DARK_MAX）", "reason": "暗すぎて見えない",
         "rule": f"人物部分の平均の明るさ < {pct(emblem.DARK_MAX)}（黒くつぶれて何かわからない暗い場面）。役の記事の画像は、ポスター・宣伝用の絵（名前に poster・promo・render など）を場面のスクリーンショットより先に使う"},
        {"stage": STAGES[5], "title": "横長・縦長の写真は余白なしで", "by": "rule", "code": "render.CARD_AR（badge.whole）",
         "rule": "カード（4:5）と縦横比が離れた写真（コート全景・スキーヤー）は、白い余白つきのカードにせず、写真そのままに斜めの枠だけ"},
        {"stage": STAGES[5], "title": "ほかの人が残っている（写真）", "by": "model", "code": "emblem.other_faces（YuNet）", "reason": "ほかの人が残っている",
         "rule": f"切り抜きの中に、いちばん大きい顔の高さの {pct(emblem.OTHER_FACE)} 以上の顔がほかにある"},
        {"stage": STAGES[5], "title": "顔が切り抜きに残っていない（写真）", "by": "model", "code": "emblem.lost_face（YuNet）", "reason": "顔が切り抜きに残っていない",
         "rule": "元の写真・場面には顔があるのに、切り抜いた結果に顔がない = 手・持ち物・暗い背景を切り抜いた。同じページの別の画像で取り直す"},
        {"stage": STAGES[5], "title": "穴（写真）", "by": "rule", "code": "emblem.hole_share", "reason": "切り抜きに穴",
         "rule": f"体の中の透明な穴 > {emblem.HOLE_MAX:.0%}（服が背景と同じ色で抜けた）"},
        {"stage": STAGES[5], "title": "代表画像がだめなら同じページで", "by": "rule", "code": "emblem.cut_all / find_bust",
         "rule": "同じページの公式イラストを大きい順に切り抜いて、顔が合う胸像を探す。顔が見つからない（前髪で目が隠れる）キャラは、検査を通った最大の 1 枚"},
        # ⑦ 整える
        {"stage": STAGES[6], "title": "顔の大きさをそろえる", "by": "model", "code": "emblem.face_fit（Haar・LBP）",
         "rule": f"顔 = 高さの {pct(emblem.FACE_SHARE)}。顔が {pct(emblem.CLOSEUP)} を超えるアップは同じページの胸像に替える"},
        {"stage": STAGES[6], "title": "全身か胸像か", "by": "rule", "code": "emblem.want_full",
         "rule": "1 枚ごとの framing → 版面の emblem_framing → 絵のキャラで元が透明背景の公式の立ち絵なら「全身で測ってから上半身」→ それ以外（写真・コマ・場面）は顔で胸像"},
        {"stage": STAGES[6], "title": "縦に立った人の形だけ測る", "by": "rule", "code": "emblem.STAND_RATIO",
         "rule": f"輪郭の高さが幅の {emblem.STAND_RATIO} 倍未満（寝そべり・横長のマスコット・場面：ぐでたま）は測らず切らず、全体をふつうの高さで。"
                 "網页でも全身の高さは上限（200px・スマホ 130px）まで"},
        {"stage": STAGES[6], "title": "全身で測ってから上半身に切る", "by": "rule", "code": "emblem.bust_from_body（BUST_CUT）",
         "rule": f"全身のままだと小さく貼ったとき顔が見えない。目・足の裏（全身で測った目印）で、目から足の裏の {emblem.BUST_CUT:.0%} の高さ（腰のあたり）で切る。"
                 "網页は目から足の裏（画像の外）を同じ長さにそろえるので、どのキャラも体の同じところで切れて同じ大きさ、ほかの胸像とも顔の大きさが合う"},
        {"stage": STAGES[6], "title": "タイトルロゴはカードにしない", "by": "rule", "code": "emblem.wordmark_local（WORDMARK_EDGE）/ render.WIDE_LOGO",
         "rule": f"作品の主な画像の縁が透明か一色の地（文字だけのタイトルロゴ：The Mandalorian）なら、地を抜いてロゴとして貼る（カードの白い板に小さな字が浮かない）。"
                 f"高さ÷幅が {0.5} 未満の横長は、高さでなく幅で大きく（220px・スマホ 130px）。縁まで絵がある写真・ポスターは今まで通りカード"},
        {"stage": STAGES[6], "title": "上半身に切るのはふつうの体つきだけ", "by": "model", "code": "emblem.real_body（YOLOv8m-pose・HIP_MAX）",
         "rule": f"姿勢モデルで腰の高さを測り、頭のてっぺん〜足の裏の {emblem.HIP_MAX:.0%} より上ならふつうの人の体つき（実測 43〜52%）→ 上半身に切る。"
                 f"下なら頭の大きい体つき（3D のデフォルメ・ちびキャラ）、目印の確かさが {emblem.BODY_CONF} 未満なら人の体でない（動物・マスコット：あつ森の住民、ポチタ）→ 全身のまま。"
                 f"人が見つからないときは顔の高さが全体の {emblem.FACE_REAL:.0%} 以下ならふつうの体つき。モデルがないとき（Actions）は版面のほかの小元素の多いほうに合わせる"},
        {"stage": STAGES[6], "title": "全身の背の高さをそろえる", "by": "model", "code": "emblem.body_marks（YOLOv8m-pose）/ render._body_len",
         "rule": "目から足の裏までの長さをどのキャラも同じに（網页 116px・スマホ 74px）、足の裏を帯の線に、重心を同じ位置に。"
                 "足の裏は足首から真下にたどる（尻尾・武器・服の裾・影はいちばん下でも足ではない。細いヒールのすき間 3% は越える）。"
                 f"台座（下の段の幅 > 体の {emblem.PEDESTAL} 倍）は除く。しゃがんだ・前かがみ（体の大きさ ÷ 目から足が版面の中央値の 1.15 倍超）は大きさで測る。"
                 "姿勢モデルがない・見つからないときは輪郭から推定"},
        {"stage": STAGES[6], "title": "取景をそろえる", "by": "rule", "code": "emblem.keep_framing",
         "rule": "胸像と全身が混ざったら多いほうに合わせる：全身は捨てずに上半身に切る（公式の立ち絵は切らない）。前からの小元素は外さない・切り直さない"},
        {"stage": STAGES[6], "title": "ロゴは切らない", "by": "rule", "code": "emblem.is_logo / clear_flat_bg",
         "rule": f"ブランド・名前に「ロゴ」のものは、縁からつながった一色の地（差 {emblem.FLAT_TOL} まで）を透明にして倉庫に置き、全体を見せる"},
        {"stage": STAGES[6], "title": "カードは比率が近いときだけ切る", "by": "rule", "code": "render.CARD_AR",
         "rule": f"背景つきの画像を 4:5 の窓で切るのは、縦横比（高さ ÷ 幅）が {emblem.CARD_AR[0]}〜{emblem.CARD_AR[1]} のときだけ。外れたら切らずに全体"},
        # ⑧ 届かなかったら
        {"stage": STAGES[7], "title": "検査で外れた画像は二度と選ばない", "by": "rule", "code": "emblem_fill.commit",
         "rule": "選んだのに切り抜きの検査で外れた画像は emblem_reject に書く。次は同じ人の次の候補を選ぶ（同じ画像で何度も失敗しない）"},
        {"stage": STAGES[7], "title": "段を上がる・待つ", "by": "rule", "code": "emblem_fill.fill_one / RETRY_HOURS",
         "rule": f"① 標準 → ② 名前を広げる → ③ 公式・記事のページ。全部だめなら失敗：新しい記事・手がかりが来たらすぐ、来なくても {ef.RETRY_HOURS} 時間後"},
        {"stage": STAGES[7], "title": "目で見て選ぶ（手で頼んだときだけ）", "by": "ai", "code": "emblem_fill.py \"名前\" → --commit",
         "rule": "番号つきの一覧を AI が見て選ぶ。後台（自動）では使わない。外した画像は emblem_reject に書けば二度と選ばれない"},
    ]


def reasons():
    """コードが落とすときに使う理由の言葉の一覧（テスト用）。"""
    return {r["reason"] for r in rules() if r.get("reason")}


# 判断の例（前 → 後）：管理ページ「小元素の判断の例」に出す。画像は docs/emblems/examples/（本物の判断の結果を残したもの）。
# rule は rules() の title と同じ言葉（テストが確かめる）。after が空 = その画像は使わなかった（verdict に理由）
EX = "emblems/examples/"
EXAMPLES = [
    {"rule": "コマ・アップの切り抜き", "item": "BLEACH Mirrors High · チャド",
     "before": [("chad-panel", "Fandom の代表画像 = 漫画のコマ"), ("chad-before", "切り抜くと吹き出しの跡がえぐれる（上の端 82%）")],
     "after": [("chad-after", "同じページの公式イラスト（Brave Souls）に替えた")],
     "verdict": "代表画像は外し、同じページの公式イラストで取り直す"},
    {"rule": "ほかの人が残っている（写真）", "item": "The Mandalorian · Pedro Pascal",
     "before": [("the-mandalorian-pedro-pascal-before", "後ろの人と番組ロゴも一緒に切れた")],
     "after": [("the-mandalorian-pedro-pascal-after", "顔が 1 つだけの場面で取り直し")],
     "verdict": "切り抜きに 2 つ目の顔（いちばん大きい顔の高さの 20% 以上）があれば外す"},
    {"rule": "YouTube は動画の場面", "item": "ILLIT · Minju",
     "before": [("illit-minju-before", "投稿者のサムネイル：題名の字が切り抜きに残った")], "after": [],
     "verdict": "外した。字の載っていない自動の場面（hq1〜3）で取り直す"},
    {"rule": "YouTube は動画の場面", "item": "FROM · Harold Perrineau",
     "before": [("from-harold-perrineau-before", "投稿者のサムネイル（hq720）")],
     "after": [("from-harold-perrineau-after", "動画の場面から。下 18%（字幕の帯）を切ってから切り抜く")],
     "verdict": "動画の場面に替えた"},
    {"rule": "顔がない", "item": "周杰伦 · 候補の写真",
     "before": [("face-none", "応援のペンライト（記事の画像）")], "after": [], "verdict": "顔なし → 外す"},
    {"rule": "遠景", "item": "周杰伦 · 候補の写真",
     "before": [("face-far", "舞台の遠景")], "after": [], "verdict": "顔の高さ < 画像の 10% → 外す"},
    {"rule": "何人も写っている", "item": "周杰伦 · 候補の写真",
     "before": [("face-crowd", "2 人で写った写真")], "after": [], "verdict": "2 番目の顔 ≥ 60% → 外す"},
    {"rule": "別人", "item": "周杰伦 · 候補の写真",
     "before": [("face-anchor", "基準：記事の代表画像（本人）"), ("face-other", "同じ記事に載っていたショパンの肖像")], "after": [],
     "verdict": "顔の特徴（SFace）が基準と似ていない（< 0.363）→ 外す"},
    {"rule": "顔の大きさをそろえる", "item": "绝区零 · Belle",
     "before": [("belle-src", "公式の立ち絵（全身）")], "after": [("belle-after", "顔が高さの 32% になるように下を切る")],
     "verdict": "どの版面でも顔が同じ大きさに見える"},
    {"rule": "全身で測ってから上半身に切る", "item": "绝区零 · Astra Yao",
     "before": [("astra-bust", "前：顔で切っていたので、キャラごとに体の切れる場所がばらばら")],
     "after": [("astra-full", "後：全身で目と足の裏を測り、腰のあたり（目から足の 40%）で切る。20 人とも同じところで切れる")],
     "verdict": "全身で測ってから上半身に切る（全身のままだと小さすぎる）"},
    {"rule": "実写の作品は役の姿", "item": "漫威电影 · Chris Evans",
     "before": [("actor-before", "前：出演者の写真（映画祭で撮った私服）")],
     "after": [("role-after", "後：Fandom の役の記事（Steve Rogers）の剧照。出演者の写真は本人確認の基準にだけ使う")],
     "verdict": "剧・映画は役の姿。生活の写真は使わない"},
    {"rule": "上半身に切るのはふつうの体つきだけ", "item": "あつ森 · チェーンソーマン（ポチタ）",
     "before": [("chibi-before", "前：公式の立ち絵はどれも腰で切っていた → 頭の大きいキャラ・動物は顔だけになって何かわからない")],
     "after": [("chibi-after", "後：腰の高さが体の 60% より下（頭が大きい）・人の体が見つからない（動物・マスコット）ものは全身のまま")],
     "verdict": "人の体つきだけ上半身に。デフォルメ・マスコットは全身"},
    {"rule": "縦に立った人の形だけ測る", "item": "ぐでたま",
     "before": [("lying-before", "前：寝そべった横長の絵まで「立った人」として測って切った → 巨大で欠けた")],
     "after": [("lying-after", "後：高さが幅の 1.3 倍未満なので測らず切らず、全体をふつうの高さで")],
     "verdict": "人の形でないものは測らない。高さには上限"},
    {"rule": "全身の背の高さをそろえる", "item": "dota2 · ヒーロー 9 人",
     "before": [("height-before", "前：画像の高さでそろえると、武器・羽・しゃがみで背がばらばら")],
     "after": [("height-after", "後：目から足の裏をそろえ、足の裏を線（赤）に。しゃがんだ Slark は大きさで測る")],
     "verdict": "どのキャラも同じ背の高さ・同じ地面に立つ"},
    {"rule": "ロゴは切らない", "item": "gelato pique",
     "before": [("logo-before", "前：白い地つきの横長ロゴを 4:5 の窓で切って字が欠けた")], "after": [("logo-after", "後：地を抜いて全体")],
     "verdict": "ロゴは切らない。一色の地は透明に"},
    {"rule": "代表作の記事", "item": "MMORPG 新作",
     "before": [("mmorpg-before", "前：主題の記号（Twemoji）だけ")], "after": [("mmorpg-after", "後：代表作（剣霊など 5 作）のキービジュアル・ロゴ")],
     "verdict": "ジャンルの版面は「下の一段」を貼る。記号は最後の手段"},
]
