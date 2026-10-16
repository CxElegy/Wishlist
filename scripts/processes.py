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
"""

import html

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
                       ("2", "Fandom", "キャラのページの代表画像"), ("3", "Wikipedia", "本人・メンバー・ロゴの記事の画像"),
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
        "id": "collect", "name": "ニュース収集", "en": "COLLECT", "lane": "actions",
        "trigger": "2 時間ごと（UTC 偶数時 17 分）／ 毎週月曜に周報",
        "summary": "関注項ごとにニュース・ SNS・価格を集めて inbox に溜め、簡報を出刊する。要紧消息は当日 Discord へ。",
        "files": [".github/workflows/digest.yml", "scripts/digest.py", "scripts/sources.py"], "doc": "README.md",
        "flow": [
            {"id": "c1", "kind": "step", "lane": "actions", "title": "収集して簡報を更新", "text": "match / exclude の規則で拾い、heat 用の外部データも保存。"},
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
        "trigger": "毎日 2 回（12:43 / 23:43）／ 新しい関注項が入ったとき",
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


# ---------------------------------------------------------------- 縮図（SVG）
def thumb(p):
    """プロセスの縮図：ノードを縦に並べた小さな流れ図。step=四角、decision=ひし形、fan=重ねた四角、store=丸角。"""
    nodes = p["flow"]
    w, gap, h = 120, 6, 12
    y = 4
    parts = []
    for i, n in enumerate(nodes):
        k, cx = n["kind"], w / 2
        if i:
            parts.append(f'<line x1="{cx}" y1="{y - gap}" x2="{cx}" y2="{y}" stroke="currentColor" stroke-width="1.5"/>')
        if k == "decision":
            parts.append(f'<path d="M{cx} {y} L{cx + 34} {y + h / 2} L{cx} {y + h} L{cx - 34} {y + h / 2}Z" fill="var(--gold)" '
                         f'stroke="currentColor" stroke-width="1.5"/>')
        elif k == "fan":
            for j in range(3):
                parts.append(f'<rect x="{cx - 44 + j * 30}" y="{y}" width="26" height="{h}" fill="var(--card)" stroke="currentColor" stroke-width="1.5"/>')
        elif k == "store":
            parts.append(f'<rect x="{cx - 34}" y="{y}" width="68" height="{h}" rx="5" fill="var(--sheet)" stroke="currentColor" stroke-width="1.5"/>')
        else:
            parts.append(f'<rect x="{cx - 34}" y="{y}" width="68" height="{h}" fill="var(--card)" stroke="currentColor" stroke-width="1.5"/>')
        y += h + gap
    return (f'<svg viewBox="0 0 {w} {y}" role="img" aria-label="{e(p["name"])}の流れの縮図" preserveAspectRatio="xMidYMin meet">{"".join(parts)}</svg>')


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
    """管理ページに入れる HTML（一覧 + 各プロセスの詳細ダイアログ）。"""
    processes = processes or PROCESSES
    cards = "".join(
        f'<button type="button" class="pc" data-open="proc-{e(p["id"])}">'
        f'<span class="pc-t">{thumb(p)}</span><b>{e(p["name"])}</b><small>{e(p["en"])}</small>'
        f'<span class="pc-w">{e(p["trigger"])}</span>{_lane_tag(p["lane"])}</button>' for p in processes)
    return f'<div class="pcs">{cards}</div>' + "".join(detail(p) for p in processes)


CSS = """
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
  document.addEventListener('click', ev => {
    const open = ev.target.closest('[data-open]');
    if (open) { const d = document.getElementById(open.dataset.open); if (d && d.showModal) d.showModal(); return; }
    if (ev.target.closest('[data-close]')) { const d = ev.target.closest('dialog'); if (d) d.close(); return; }
    if (ev.target.tagName === 'DIALOG') ev.target.close();   // 外側（暗い部分）をクリックしても閉じる
  });
})();
"""
