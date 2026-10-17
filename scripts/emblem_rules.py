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
        {"stage": STAGES[5], "title": "ほかの人が残っている（写真）", "by": "model", "code": "emblem.other_faces（YuNet）", "reason": "ほかの人が残っている",
         "rule": f"切り抜きの中に、いちばん大きい顔の高さの {pct(emblem.OTHER_FACE)} 以上の顔がほかにある"},
        {"stage": STAGES[5], "title": "穴（写真）", "by": "rule", "code": "emblem.hole_share", "reason": "切り抜きに穴",
         "rule": f"体の中の透明な穴 > {emblem.HOLE_MAX:.0%}（服が背景と同じ色で抜けた）"},
        {"stage": STAGES[5], "title": "代表画像がだめなら同じページで", "by": "rule", "code": "emblem.cut_all / find_bust",
         "rule": "同じページの公式イラストを大きい順に切り抜いて、顔が合う胸像を探す。顔が見つからない（前髪で目が隠れる）キャラは、検査を通った最大の 1 枚"},
        # ⑦ 整える
        {"stage": STAGES[6], "title": "顔の大きさをそろえる", "by": "model", "code": "emblem.face_fit（Haar・LBP）",
         "rule": f"顔 = 高さの {pct(emblem.FACE_SHARE)}。顔が {pct(emblem.CLOSEUP)} を超えるアップは同じページの胸像に替える"},
        {"stage": STAGES[6], "title": "取景をそろえる", "by": "rule", "code": "emblem.keep_framing",
         "rule": "胸像と全身は多いほうに合わせる：全身は捨てずに上半身に切る／全身の立ち絵は切らずに残す。前からの小元素は外さない・切り直さない"},
        # ⑧ 届かなかったら
        {"stage": STAGES[7], "title": "段を上がる・待つ", "by": "rule", "code": "emblem_fill.fill_one / RETRY_HOURS",
         "rule": f"① 標準 → ② 名前を広げる → ③ 公式・記事のページ。全部だめなら失敗：新しい記事・手がかりが来たらすぐ、来なくても {ef.RETRY_HOURS} 時間後"},
        {"stage": STAGES[7], "title": "目で見て選ぶ（手で頼んだときだけ）", "by": "ai", "code": "emblem_fill.py \"名前\" → --commit",
         "rule": "番号つきの一覧を AI が見て選ぶ。後台（自動）では使わない。外した画像は emblem_reject に書けば二度と選ばれない"},
    ]


def reasons():
    """コードが落とすときに使う理由の言葉の一覧（テスト用）。"""
    return {r["reason"] for r in rules() if r.get("reason")}
