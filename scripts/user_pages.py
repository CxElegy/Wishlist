"""お客さま一人ひとりのページを、店長のページと同じ部品（render.render）で作る（2026-10-24，用户定的：
「框架（頭条・黄色の帯・版面の設計・主題・配色・小元素）は店長と同じ、中身は本人のもの」）。

- 版面 = 本人が追いかけているもの（ライブラリの follows：置く板块・小分類・篇幅・並び）。
  follows にまだないもの（足したばかりで library.py --users の回の前）は app_users.prefs.picks から（板块だけ）。
  どれを出すかは picks が決める（picks から外したものは follows に行が残っていても出さない）。
  - 店長と同じ名前の版面：店長の設定（主題・配色・小元素・アイコン）と店長の記事（AI 編集済みの最新号）をそのまま使う。
  - 店長にないもの：本人の分として集めた記事（user_boards）で、種類から主題（render.template_for）、写真から配色（theme.resolve）。
    写真は images.pick（店長と同じ規則）で記事から探す（1 版面の頭の数本だけ・全体の時間に上限）。
- 頭条・ほかの注目ニュース・目次は render がそのまま作る（本人の版面の記事から）。
- できたページは Supabase Storage の非公開の箱 pages/<account>/index.html（本人と店長だけが読める、db/user_pages.sql）。
  網页（render.AUTH_JS）は /home/ でログインした本人の分を読み込んで替える。

    python scripts/user_pages.py            # Actions（SUPABASE_SERVICE_KEY）：全員分を作って置く
    python scripts/user_pages.py --local D  # 手元：ネットの Supabase なし、D/<account>.html に書く（テスト用のデータを渡す）
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import zoneinfo

import digest
import render
import sources
import taxonomy
import theme

ROOT = pathlib.Path(__file__).resolve().parent.parent
TYPE_OF_SEC = {"游戏": "game", "影视": "anime", "演出": "event", "运动": "category", "好物": "product",
               "生活": "category", "出行": "category", "其他": "category"}
IMG_PER_BOARD = 3        # 1 版面で写真を探す記事の数（頭から）
IMG_BUDGET_S = 240       # 1 回の写真探しの合計時間（秒）
STORIES_PER_BOARD = 8
BOARD_DESIGN = ("emblem", "theme")   # ライブラリの版面の共有のデザイン（boards.config、library_emblem.py が規則で作る）
FIRST_BOARD = render.SETTINGS_JA["first_board"]   # 版面が 0 個の人のページに置く静かな版面の名前（文字は表）
ADD_URL = "../?add"       # 追いかけるものを足す流れ（入口と同じ、render.AUTH_JS の ADD）


def account_of(email):
    """Supabase の private.user_account と同じ式（'u_' + md5(小文字のメール) 16 字）。"""
    return "u_" + hashlib.md5(str(email or "").strip().lower().encode()).hexdigest()[:16]


def norm(s):
    return digest.re.sub(r"\s+", "", str(s or "")).lower()


def own_picks(follows, picks, sizes=None):
    """いま追いかけているもの = picks（本物。設定の「外す」・カードで足すはここを書き換える）。
    follows（[{pos, section, subs, size, boards: {name}}]）は置き方だけ：picks にある名前の行を並び順に、そのあとに follows にまだない picks。
    picks から外した名前の follows は残っていても使わない（follows を消す仕組みはないので、外したらすぐ消えるように）。
    返す形は picks と同じ [{name, sec, subs, size}]（subs は follows にあるときだけ）。
    size（篇幅）= follows.size、なければ設定ページで選んだ prefs.sizes（follows にまだない版面の分、db/my_layout.sql）。"""
    sizes = {norm(k): v for k, v in (sizes or {}).items() if v in ("S", "M", "L")}
    want = {norm(p.get("name")) for p in picks or [] if str(p.get("name") or "").strip()}
    out, seen = [], set()
    for f in sorted(follows or [], key=lambda f: f.get("pos") or 0):
        name = str(((f.get("boards") or {}).get("name")) or "").strip()
        if name and norm(name) in want and norm(name) not in seen:
            seen.add(norm(name))
            cfg = (f.get("boards") or {}).get("config") or {}
            out.append({"name": name, "sec": f.get("section") or "", "subs": f.get("subs") or {},
                        "size": f.get("size") or sizes.get(norm(name)),
                        "design": {k: cfg[k] for k in BOARD_DESIGN if cfg.get(k)}})
    for p in picks or []:
        if norm(p.get("name")) not in seen:
            out.append({**p, "size": sizes.get(norm(p.get("name")))} if sizes.get(norm(p.get("name"))) else p)
    return out


def own_schemes(chosen):
    """板块ごとの分け方 {板块: id}：本人が設定ページで選んだもの（nav_schemes の本人の行）、候補にない・選んでいない板块は 1 つ目。
    店長の digest.load_nav_schemes と同じ決め方。"""
    out = {}
    for sec, schemes in taxonomy.sub_schemes().items():
        ids = [x.get("id") for x in schemes or [] if isinstance(x, dict) and x.get("id")]
        if ids:
            out[sec] = (chosen or {}).get(sec) if (chosen or {}).get(sec) in ids else ids[0]
    return out


def own_sub(item, schemes=None):
    """目次の小分類：その板块で本人が選んだ分け方（選んでいなければ 1 つ目。店長の既定と同じ）。"""
    return digest.sub_of(item, (schemes or own_schemes({})).get(item.get("section")))


def settings_page(prefs, items, schemes, settings, updated):
    """本人の設定ページ（店長と同じ render.render_settings、own の形：日本語・本人の分だけ書く）。"""
    rows = [{"name": i["name"], "section": i.get("section") or "其他", "subtitle": i.get("subtitle", ""), "size": i.get("size") or "M",
             "fields": {"section": i.get("section") or "其他"}} for i in items]
    srows = []
    for sec, opts in taxonomy.sub_schemes().items():
        ins = [i for i in items if i.get("section") == sec]
        good = [x for x in opts or [] if isinstance(x, dict) and x.get("id")]
        if not ins or not good:
            continue
        o = []
        for x in good:
            groups = {}
            for i in ins:
                g = digest.sub_of(i, x["id"]) or render.SETTINGS_JA["other"]
                groups[g] = groups.get(g, 0) + 1
            o.append({"id": x["id"], "label": x.get("label") or x["id"], "groups": list(groups.items())})
        srows.append({"section": sec, "chosen": schemes.get(sec, o[0]["id"]), "options": o})
    picks = [{"name": p["name"], "sec": p.get("sec") or "其他"} for p in (prefs or {}).get("picks") or [] if p.get("name")]
    return render.render_settings(rows, {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, updated, srows,
                                  {"picks": picks, "add": ADD_URL})


def user_items(picks, shop_items):
    """本人の版面（items.yaml と同じ形）。店長と同じ名前なら店長の設定を写す（板块は本人の選んだもの）。"""
    shop = {norm(i["name"]): i for i in shop_items}
    out, seen = [], set()
    for p in picks or []:
        name = str(p.get("name") or "").strip()
        if not name or norm(name) in seen:
            continue
        seen.add(norm(name))
        sec = taxonomy.canonical(p.get("sec") or "") if p.get("sec") else ""
        if norm(name) in shop:
            it = {k: v for k, v in shop[norm(name)].items() if k not in ("parent",)}
            if sec:
                it["section"] = sec
            if p.get("subs"):   # 本人の置き方（follows）が店長の小分類より先
                it["subs"] = dict(p["subs"])
            it["_shop"] = True
        else:
            it = {"name": name, "type": TYPE_OF_SEC.get(sec, "category"), "section": sec or taxonomy.classify(name),
                  "keywords": [name], "match": [name], "subs": dict(p.get("subs") or {}), **(p.get("design") or {})}
        if p.get("size") in ("S", "M", "L"):
            it["size"] = p["size"]
        out.append(it)
    return out


def _story(row, weight):
    return {"headline": row.get("title") or "", "url": row.get("url") or "", "image": row.get("image") or None,
            "date": str(row.get("date") or "")[:10], "blurb": row.get("summary") or "", "highlight": "", "weight": weight,
            "source": row.get("source") or ""}


def find_images(stories, deadline):
    """写真のない記事に、店長と同じ規則（images.pick）で写真を探す。時間の上限を超えたらやめる。"""
    used = set()
    for s in stories[:IMG_PER_BOARD]:
        if s.get("image") or time.time() > deadline:
            continue
        e = sources.Entry(title=s["headline"], url=s["url"], published=None, source=s.get("source", ""))
        try:
            img = digest.find_image(None, [e], s["url"])
        except Exception:  # noqa: BLE001  写真がなくても版面は出す
            img = None
        if img and img not in used:
            s["image"] = img
            used.add(img)
    return stories


def user_issue(items, shop_issue, rows, deadline, themes):
    """本人の 1 号分（render が読む形）。店長と同じ版面は店長の最新号の版面をそのまま、ほかは本人の記事から。"""
    shop_blocks = {b["name"]: b for b in (shop_issue or {}).get("items", [])}
    blocks = []
    for it in items:
        cap = digest.SIZE_STORIES.get(it.get("size") or "M", STORIES_PER_BOARD)   # 本人の篇幅（S 3・M 5・L 8、設定ページの約束）
        if it.get("_shop") and it["name"] in shop_blocks:
            sb = shop_blocks[it["name"]]
            blocks.append({**sb, "stories": (sb.get("stories") or [])[:cap], "section": it.get("section") or sb.get("section")})
            continue
        row = rows.get(norm(it["name"])) or {}
        st = [_story(r, "hero" if i == 0 else "normal") for i, r in enumerate((row.get("stories") or [])[:cap])]
        st = find_images(st, deadline)
        cover = next((s["image"] for s in st if s.get("image")), None)
        blocks.append({"name": it["name"], "section": it.get("section"), "subtitle": "", "stories": st, "facts": [],
                       "pending": [], "cover": cover, "theme": theme.resolve(it, cover, themes),
                       **({} if st else {"quiet": True, "collecting": True,
                                         "status": render.SETTINGS_JA["collecting"]})})
    if not blocks:   # 版面が 0 個の人も同じ枠組み：静かな版面（主題・配色つき）で最初の 1 つを選ぶ道を出す（素の箱にしない）
        first = {"name": FIRST_BOARD, "type": "category", "section": "其他"}
        blocks.append({"name": FIRST_BOARD, "section": "其他", "subtitle": "", "stories": [], "facts": [], "pending": [], "cover": None,
                       "theme": theme.resolve(first, None, themes), "quiet": True, "start": ADD_URL,
                       "status": render.SETTINGS_JA["none_status"]})   # 道は主役のボタン 1 つだけ（ここに 2 つ目のリンクを置かない）
    date = (shop_issue or {}).get("date") or dt.date.today().isoformat()
    return {"date": date, "no": (shop_issue or {}).get("no", 0), "items": blocks}


def build(email, prefs, rows, shop_items, shop_issue, settings, deadline, themes, follows=None, chosen=None, pages=None):
    """本人のページの HTML。follows = ライブラリの本人の行（あれば置き方はこちら）、chosen = 本人の nav_schemes {板块: id}。
    pages（dict）を渡すと、設定ページ（settings.html）もそこに入れる。"""
    items = user_items(own_picks(follows, (prefs or {}).get("picks"), (prefs or {}).get("sizes")), shop_items)
    issue = user_issue(items, shop_issue, rows, deadline, themes)
    schemes = own_schemes(chosen)
    subs = {i["name"]: own_sub(i, schemes) for i in items}
    secs = list(render.SECTIONS)
    first = {}
    for n, i in enumerate(items):   # 板块 → 小分類（出てきた順）→ 本人の並び。店長の目次・本文と同じ並べ方
        first.setdefault((i.get("section"), subs[i["name"]]), n)
    items_o = sorted(enumerate(items), key=lambda x: (secs.index(x[1].get("section")) if x[1].get("section") in secs else len(secs),
                                                      first[(x[1].get("section"), subs[x[1]["name"]])], x[0]))
    order = [i["name"] for _, i in items_o] or [FIRST_BOARD]
    tz = digest.display_tz(settings)
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    render.AUTH_DB = {"url": settings.get("supabase_url") or "", "key": settings.get("supabase_key") or ""}
    render.AUTH_ITEMS = [[i["name"], digest.section_of(i)] for i in shop_items if not i.get("parent")]
    html_ = render.render([issue], settings.get("nav_style", "line"), order, updated, [], [],
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")},
                          {i["name"]: i["size"] for i in items if i.get("size")},
                          {i["name"]: render.template_for(i) for i in items}, themes, [], {},
                          {i["name"]: (i["emblem"], i.get("emblem_ring", "accent")) for i in items if isinstance(i.get("emblem"), list)},
                          {i["name"]: i["like_fx"] for i in items if i.get("like_fx")}, {n: v for n, v in subs.items() if v},
                          settings.get("nav_hide", render.NAV_HIDE),
                          {i["name"]: i["icon"].get("image") for i in items if isinstance(i.get("icon"), dict)},
                          None, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), {}, {},
                          digest.lang.order(settings), {}, {})
    # 本人のページの印（AUTH_JS が「自分のページの中」と分かるように。もう一度読み替えない）
    mark = f'<head><meta name="wl-own" content="{render.e(email)}">'
    if pages is not None:
        pages["settings.html"] = settings_page(prefs, items, schemes, settings, updated).replace("<head>", mark, 1)
    return html_.replace("<head>", mark, 1)


def _supa(path, data=None, method="GET", ctype="application/json"):
    settings, _ = digest.load_config()
    base, key = (settings.get("supabase_url") or "").rstrip("/"), os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and key):
        raise SystemExit("SUPABASE_SERVICE_KEY がありません")
    h = {"apikey": key, "Content-Type": ctype}
    if key.startswith("eyJ"):
        h["Authorization"] = f"Bearer {key}"
    if method != "GET" and "/storage/" in path:
        h["Authorization"] = f"Bearer {key}"
        h["x-upsert"] = "true"
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8")
    return json.loads(body) if body.strip().startswith(("[", "{")) else body


def main(argv):
    if argv[:1] != ["--local"]:
        render.OPENS = render.photo_opens   # 頭に選ぶ写真が開くか焼く時に見る（店長と同じ規則）
    settings, shop_items = digest.load_config()
    reports = sorted(digest.REPORTS_DIR.glob("????-??-??.json"))
    shop_issue = digest.load_json(reports[-1]) if reports else None
    themes = digest.load_json(digest.THEMES_FILE) or {}
    deadline = time.time() + IMG_BUDGET_S
    if argv[:1] == ["--local"]:
        out = pathlib.Path(argv[1])
        data = json.loads(pathlib.Path(argv[2]).read_text(encoding="utf-8"))   # [{email, account, prefs, rows: [...]}]
        out.mkdir(parents=True, exist_ok=True)
        for u in data:
            rows = {norm(r["item"]): r for r in u.get("rows", [])}
            pages = {}
            (out / f"{u['account']}.html").write_text(build(u["email"], u["prefs"], rows, shop_items, shop_issue, settings, deadline, themes,
                                                            u.get("follows"), u.get("schemes"), pages), encoding="utf-8")
            for name, h in pages.items():
                (out / f"{u['account']}.{name}").write_text(h, encoding="utf-8")
        return
    users = _supa("/rest/v1/rpc/userfeed_users", json.dumps({"p_limit": 1000}).encode(), "POST")
    made = failed = 0
    for u in users or []:
        acct = account_of(u["email"])
        try:
            rows = _supa(f"/rest/v1/user_boards?account=eq.{acct}&select=item,sec,state,stories")
            follows = _supa(f"/rest/v1/follows?account=eq.{acct}&select=pos,section,subs,size,boards(name,config)&order=pos")
            chosen = {r["section"]: r["scheme"] for r in _supa(f"/rest/v1/nav_schemes?account=eq.{acct}&select=section,scheme") or []}
            pages = {}
            html_ = build(u["email"], u.get("prefs") or {}, {norm(r["item"]): r for r in rows or []}, shop_items, shop_issue, settings, deadline,
                          themes, follows, chosen, pages)
            for name, h in {"index.html": html_, **pages}.items():
                _supa(f"/storage/v1/object/pages/{urllib.parse.quote(acct)}/{name}", h.encode("utf-8"), "POST", "text/html; charset=utf-8")
            made += 1
        except Exception as ex:  # noqa: BLE001  1 人の失敗でほかの人を止めない。ログは数と種類だけ（名前・メールは出さない：Actions のログは公開）
            failed += 1
            print(f"::warning::1 人分のページを作れなかった（{type(ex).__name__}）")
    print(f"お客さまのページ：{made} 人分を作って置いた・失敗 {failed}")
    if failed and not made:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
