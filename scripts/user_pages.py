"""お客さま一人ひとりのページを、店長のページと同じ部品（render.render）で作る（2026-10-24，用户定的：
「框架（頭条・黄色の帯・版面の設計・主題・配色・小元素）は店長と同じ、中身は本人のもの」）。

- 版面 = 本人が選んだもの（app_users.prefs.picks）。
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
FIRST_BOARD = "はじめに"   # 版面が 0 個の人のページに置く静かな版面の名前
ADD_URL = "../?add"       # 追いかけるものを足す流れ（入口と同じ、render.AUTH_JS の ADD）


def account_of(email):
    """Supabase の private.user_account と同じ式（'u_' + md5(小文字のメール) 16 字）。"""
    return "u_" + hashlib.md5(str(email or "").strip().lower().encode()).hexdigest()[:16]


def norm(s):
    return digest.re.sub(r"\s+", "", str(s or "")).lower()


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
            it["_shop"] = True
        else:
            it = {"name": name, "type": TYPE_OF_SEC.get(sec, "category"), "section": sec or taxonomy.classify(name),
                  "keywords": [name], "match": [name], "subs": {}}
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
        if it.get("_shop") and it["name"] in shop_blocks:
            blocks.append({**shop_blocks[it["name"]], "section": it.get("section") or shop_blocks[it["name"]].get("section")})
            continue
        row = rows.get(norm(it["name"])) or {}
        st = [_story(r, "hero" if i == 0 else "normal") for i, r in enumerate((row.get("stories") or [])[:STORIES_PER_BOARD])]
        st = find_images(st, deadline)
        cover = next((s["image"] for s in st if s.get("image")), None)
        blocks.append({"name": it["name"], "section": it.get("section"), "subtitle": "", "stories": st, "facts": [],
                       "pending": [], "cover": cover, "theme": theme.resolve(it, cover, themes),
                       **({} if st else {"quiet": True, "collecting": True,
                                         "status": "記事を集めています。集まりしだい、ここに並びます"})})
    if not blocks:   # 版面が 0 個の人も同じ枠組み：静かな版面（主題・配色つき）で最初の 1 つを選ぶ道を出す（素の箱にしない）
        first = {"name": FIRST_BOARD, "type": "category", "section": "其他"}
        blocks.append({"name": FIRST_BOARD, "section": "其他", "subtitle": "", "stories": [], "facts": [], "pending": [], "cover": None,
                       "theme": theme.resolve(first, None, themes), "quiet": True,
                       "status": f"まだ何も追いかけていません。[追いかけるものを選ぶ →]({ADD_URL})"})
    date = (shop_issue or {}).get("date") or dt.date.today().isoformat()
    return {"date": date, "no": (shop_issue or {}).get("no", 0), "items": blocks}


def build(email, prefs, rows, shop_items, shop_issue, settings, deadline, themes):
    """本人のページの HTML。"""
    items = user_items((prefs or {}).get("picks"), shop_items)
    issue = user_issue(items, shop_issue, rows, deadline, themes)
    order = [i["name"] for i in items] or [FIRST_BOARD]
    tz = digest.display_tz(settings)
    updated = dt.datetime.now(tz).strftime("%m.%d %H:%M")
    render.AUTH_DB = {"url": settings.get("supabase_url") or "", "key": settings.get("supabase_key") or ""}
    render.AUTH_ITEMS = [[i["name"], digest.section_of(i)] for i in shop_items if not i.get("parent")]
    html_ = render.render([issue], settings.get("nav_style", "line"), order, updated, [], [],
                          {"url": settings.get("supabase_url"), "key": settings.get("supabase_key")}, {},
                          {i["name"]: render.template_for(i) for i in items}, themes, [], {},
                          {i["name"]: (i["emblem"], i.get("emblem_ring", "accent")) for i in items if isinstance(i.get("emblem"), list)},
                          {i["name"]: i["like_fx"] for i in items if i.get("like_fx")}, {}, settings.get("nav_hide", render.NAV_HIDE),
                          {i["name"]: i["icon"].get("image") for i in items if isinstance(i.get("icon"), dict)},
                          None, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), {}, {},
                          digest.lang.order(settings), {}, {})
    # 本人のページの印（AUTH_JS が「自分のページの中」と分かるように。もう一度読み替えない）
    return html_.replace("<head>", f'<head><meta name="wl-own" content="{render.e(email)}">', 1)


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
            (out / f"{u['account']}.html").write_text(build(u["email"], u["prefs"], rows, shop_items, shop_issue, settings, deadline, themes), encoding="utf-8")
        return
    users = _supa("/rest/v1/rpc/userfeed_users", json.dumps({"p_limit": 1000}).encode(), "POST")
    made = failed = 0
    for u in users or []:
        acct = account_of(u["email"])
        try:
            rows = _supa(f"/rest/v1/user_boards?account=eq.{acct}&select=item,sec,state,stories")
            html_ = build(u["email"], u.get("prefs") or {}, {norm(r["item"]): r for r in rows or []}, shop_items, shop_issue, settings, deadline, themes)
            _supa(f"/storage/v1/object/pages/{urllib.parse.quote(acct)}/index.html", html_.encode("utf-8"), "POST", "text/html; charset=utf-8")
            made += 1
        except Exception as ex:  # noqa: BLE001  1 人の失敗でほかの人を止めない。ログは数と種類だけ（名前・メールは出さない：Actions のログは公開）
            failed += 1
            print(f"::warning::1 人分のページを作れなかった（{type(ex).__name__}）")
    print(f"お客さまのページ：{made} 人分を作って置いた・失敗 {failed}")
    if failed and not made:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
