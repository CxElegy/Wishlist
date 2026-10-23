"""ライブラリ（2026-10-23，用户定的）：みんなの版面の置き場（Supabase の boards / board_stories / follows、db/library.sql）。

店長もお客さまも、ライブラリから自分の版面を選ぶ（なければ 1 つ足す）。記事集め・AI 編集・デザインは版面ごとに 1 回。
- 同じものかどうか（board_key）：Wikidata の番号があれば 'wd:Q…'、なければ名前をそろえたもの（全角半角・大小・空白・記号）'n:…'
- items.yaml の 1 項目を、みんなで共有する設定（config）と人ごとの置き方（follows：section・subs・also・size・priority）に分ける（split_item）

    python scripts/library.py --sql > x.sql    # 店長の items.yaml をライブラリへ写す SQL（boards と test1 の follows）
    python scripts/library.py --push           # 同じことを secret key（SUPABASE_SERVICE_KEY）で直接（Actions の library.yml）
    python scripts/library.py --users          # お客さまの選んだもの（app_users.prefs.picks）をライブラリの版面にして follows に書く（library.yml、1 時間ごと）
    python scripts/library.py --refresh --push # 番号のない版面の Wikidata を引き直して items.yaml に書き、写す（library.yml、週 1 回）
"""
import json
import pathlib
import re
import sys
import unicodedata
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PERSONAL = ("section", "subs", "also", "size", "priority")   # 人ごとの置き方（follows の列）。ほかは版面の共有の設定（boards.config）
SHOP = "test1"


def norm_name(name):
    """名前をそろえる（additem.js の normName と同じ考え方＋全角半角）。"""
    t = unicodedata.normalize("NFKC", str(name or "")).lower()
    return re.sub(r"[\s・:!?\-–—.,'\"「」『』()（）]", "", t)


def board_key(item):
    wd = str(item.get("wikidata") or "").strip()
    if re.fullmatch(r"Q\d+", wd):
        return "wd:" + wd
    return "n:" + norm_name(item.get("name"))


def split_item(item):
    """items.yaml の 1 項目 → (共有の設定, 人ごとの置き方)。"""
    shared = {k: v for k, v in item.items() if k not in PERSONAL and k not in ("name", "parent", "wikidata")}
    mine = {k: item[k] for k in PERSONAL if item.get(k) is not None}
    return shared, mine


WD_API = "https://www.wikidata.org/w/api.php"
WD_UA = "WishlistBot/1.0 (https://github.com/CxElegy/Wishlist)"


class WdBlocked(Exception):
    """Wikidata に断られた・届かなかった（429・5xx・時間切れ）。「項目が 0 件」とは別に数える。"""


def _wd_get(params):
    """Wikidata の API（429 は間を空けて 4 回まで）。4 回とも断られたら WdBlocked（空の返事と見分ける）。"""
    import time
    import urllib.request
    url = WD_API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    why = ""
    for n in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": WD_UA}), timeout=20) as r:
                return json.load(r)
        except Exception as ex:  # noqa: BLE001  429・時間切れは待ってやり直す
            why = getattr(ex, "code", None) or type(ex).__name__
            time.sleep(5 * (n + 1))
    raise WdBlocked(str(why))


def _names(entity):
    """項目の全言語の名前と別名（そろえたもの）。"""
    out = {norm_name(v["value"]) for v in (entity.get("labels") or {}).values()}
    out |= {norm_name(a["value"]) for vs in (entity.get("aliases") or {}).values() for a in vs}
    return {x for x in out if x}


def _words(item):
    return {w for w in (norm_name(x) for x in [item.get("name"), *(item.get("keywords") or [])]) if len(w) >= 2}


def find_wikidata(item, get=_wd_get):
    """版面の Wikidata の番号を規則で決める（決まらなければ None）。
    - 題材（type: category）で Wikipedia の記事名（wiki）がないものは番号を付けない（MMORPG 新作・猫用品・滑雪…）
    - wiki があれば、記事名ごとの項目のうち、名前・検索語が項目の名前・別名に一番多く入るもの（漫威电影 → 映画 1 本ではなくシリーズ全体）
    - wiki がなければ名前・検索語で検索し、項目の名前・別名が名前か検索語とそろえて同じものだけ（いちばん多く当たったもの）
    - 題材でも小分類の owner がブランドのもの（gelato pique）は番号を付ける（ユーザー決定）。ただし項目の名前・別名が
      版面の名前そのものと同じときだけ（星巴克马克杯 が検索語の「スターバックス」でスターバックス本体に当たらない）
    """
    if re.fullmatch(r"Q\d+", str(item.get("wikidata") or "")):
        return item["wikidata"]
    words = _words(item)
    wiki = item.get("wiki") or []
    if isinstance(wiki, str):
        wiki = [wiki]
    brand = item.get("type") == "category" and (item.get("subs") or {}).get("owner") == "ブランド"
    if not wiki and item.get("type") == "category" and not brand:
        return None
    if brand and not wiki:
        words = {w for w in [norm_name(item.get("name"))] if len(w) >= 2}
    best, score = None, 0
    if wiki:
        for w in wiki:
            lang, _, title = str(w).partition(":")
            d = get({"action": "wbgetentities", "sites": f"{lang}wiki", "titles": title, "props": "labels|aliases"})
            for qid, ent in (d.get("entities") or {}).items():
                if not qid.startswith("Q"):
                    continue
                names = _names(ent)
                s = sum(1 for x in words if any(x == n or x in n or n in x for n in names if len(n) >= 2)) + 0.5
                if s > score:
                    best, score = qid, s
        return best
    hits = {}
    for q in [item.get("name"), *(item.get("keywords") or [])[:3]]:
        for lang in ("ja", "en", "zh"):
            for h in (get({"action": "wbsearchentities", "search": q, "language": lang, "limit": 3, "type": "item"}).get("search") or [])[:3]:
                labels = {norm_name(h.get("label")), norm_name((h.get("match") or {}).get("text"))} | {norm_name(a) for a in h.get("aliases") or []}
                if labels & words:
                    hits[h["id"]] = hits.get(h["id"], 0) + 1
    return max(hits, key=hits.get) if hits else None


def refresh(items, get=_wd_get, pause=1.0):
    """番号のない版面の Wikidata を引き直す（週 1 回、library.yml）。
    返す：{"found": {名前: Q…}, "none": [項目が見つからない], "blocked": [断られて引けなかった], "skip": [題材で引かない]}。
    1 度断られたら、その回は残りを聞かない（Actions の共有の IP は続けて断られる。sources.gdelt と同じ）。"""
    import time
    out = {"found": {}, "none": [], "blocked": [], "skip": []}
    stop = False
    for item in items:
        if re.fullmatch(r"Q\d+", str(item.get("wikidata") or "")):
            continue
        name = item.get("name")
        if stop:
            out["blocked"].append(name)
            continue
        asked = []

        def counted(p):
            asked.append(1)
            return get(p)
        try:
            qid = find_wikidata(item, counted)
        except WdBlocked:
            out["blocked"].append(name)
            stop = True
            continue
        if qid:
            out["found"][name] = qid
        elif asked:
            out["none"].append(name)
        else:
            out["skip"].append(name)
        if asked and pause:
            time.sleep(pause)
    return out


def write_wikidata(text, found):
    """items.yaml の文字のまま（コメントを残して）、見つかった版面の `- name:` の次の行に `wikidata: Q…` を入れる。
    「# wikidata: なし…」の行があればそれと入れ替える。返す：(新しい文字, 書いた名前)。"""
    lines = text.split("\n")
    done = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)- name:\s*(.+?)\s*$", lines[i])
        if m:
            try:
                name = yaml.safe_load(m.group(2))
            except yaml.YAMLError:
                name = None
            if isinstance(name, str) and name in found and name not in done:
                pad = m.group(1) + "  "
                row = f"{pad}wikidata: {found[name]}   # Wikidata の番号（ライブラリで同じものかどうかの印、library.find_wikidata）"
                j = i + 1
                if j < len(lines) and re.match(r"^\s*wikidata:", lines[j]):
                    i += 1
                    continue   # もう番号がある（読み違いを上書きしない）
                if j < len(lines) and re.match(r"^\s*#\s*wikidata:", lines[j]):
                    lines[j] = row
                else:
                    lines.insert(j, row)
                done.append(name)
        i += 1
    return "\n".join(lines), done


def refresh_main(path=None, get=_wd_get):
    """items.yaml の番号のない版面を引き直して書く。ログ（state/log/library.json）には数と見つかった版面の名前（店長の公開の版面）。"""
    import runlog
    path = path or ROOT / "items.yaml"
    text = path.read_text(encoding="utf-8")
    items = (yaml.safe_load(text) or {}).get("items") or []
    r = refresh(items, get)
    new, done = write_wikidata(text, r["found"])
    if done:
        path.write_text(new, encoding="utf-8")
    got = "・".join(f"{n} {r['found'][n]}" for n in done)
    msg = (f"Wikidata の引き直し：見つかった {len(done)}" + (f"（{got}）" if done else "")
           + f"・項目なし {len(r['none'])}・断られた {len(r['blocked'])}・題材で引かない {len(r['skip'])}")
    level = "warn" if r["blocked"] else ("ok" if done else "info")
    runlog.add("library", msg, level=level, found=len(done), none=len(r["none"]), blocked=len(r["blocked"]), skip=len(r["skip"]))
    print(msg)
    return r, done


def q(v):
    return "'" + str(v).replace("'", "''") + "'"


def shop_sql(items):
    """店長の items.yaml → boards（上級を先に）と test1 の follows を入れる SQL。何度流しても同じ（key で上書き）。"""
    out = []
    for item in sorted(items, key=lambda i: bool(i.get("parent"))):
        shared, _ = split_item(item)
        out.append(
            "insert into public.boards (key, name, names, wd, config, created_by) values ("
            f"{q(board_key(item))}, {q(item['name'])}, {q(json.dumps({'ja': item['name']}, ensure_ascii=False))}::jsonb, "
            f"{q(item['wikidata']) if re.fullmatch(r'Q[0-9]+', str(item.get('wikidata') or '')) else 'null'}, "
            f"{q(json.dumps(shared, ensure_ascii=False))}::jsonb, {q(SHOP)}) "
            "on conflict (key) do update set name = excluded.name, config = excluded.config, updated_at = now();")
    by_name = {i["name"]: i for i in items}
    for item in items:
        if item.get("parent") in by_name:
            out.append(f"update public.boards set parent_id = (select id from public.boards where key = {q(board_key(by_name[item['parent']]))}) "
                       f"where key = {q(board_key(item))};")
    for pos, item in enumerate(items):
        _, mine = split_item(item)
        out.append(
            "insert into public.follows (account, board_id, section, subs, also, size, pos) values ("
            f"{q(SHOP)}, (select id from public.boards where key = {q(board_key(item))}), "
            f"{q(mine['section']) if mine.get('section') else 'null'}, {q(json.dumps(mine.get('subs') or {}, ensure_ascii=False))}::jsonb, "
            f"{q(json.dumps(mine.get('also') or {}, ensure_ascii=False))}::jsonb, {q(mine['size']) if mine.get('size') else 'null'}, {pos}) "
            "on conflict (account, board_id) do update set section = excluded.section, subs = excluded.subs, also = excluded.also, size = excluded.size, pos = excluded.pos;")
    return "\n".join(out)


def shop_rows(items):
    """店長の items.yaml → (boards の行, 上級の対応 {key: 上級の key}, follows の行（board_id の代わりに key）)。"""
    by_name = {i["name"]: i for i in items}
    boards, parents, follows = [], {}, []
    for pos, item in enumerate(items):
        shared, mine = split_item(item)
        wd = str(item.get("wikidata") or "")
        boards.append({"key": board_key(item), "name": item["name"], "names": {"ja": item["name"]},
                       "wd": wd if re.fullmatch(r"Q\d+", wd) else None, "config": shared, "created_by": SHOP})
        if item.get("parent") in by_name:
            parents[board_key(item)] = board_key(by_name[item["parent"]])
        follows.append({"account": SHOP, "key": board_key(item), "section": mine.get("section"), "subs": mine.get("subs") or {},
                        "also": mine.get("also") or {}, "size": mine.get("size"), "pos": pos})
    return boards, parents, follows


def push_shop(items):
    """店長の版面をライブラリへ（何度流しても同じ：key・(account, board_id) で上書き）。"""
    import digest
    boards, parents, follows = shop_rows(items)
    for item in items:   # 番号が付いた版面は、名前の印（n:…）の行をそのまま番号の印（wd:…）へ（行を増やさない）
        if board_key(item).startswith("wd:"):
            old = "n:" + norm_name(item["name"])
            digest.supabase(f"boards?key=eq.{urllib.parse.quote(old)}", {"key": board_key(item), "wd": item["wikidata"]}, method="PATCH")
    got = digest.supabase("boards?on_conflict=key&select=id,key", boards, prefer="resolution=merge-duplicates,return=representation")
    if got is None:
        raise SystemExit("SUPABASE_SERVICE_KEY がないので書けません")
    ids = {r["key"]: r["id"] for r in got}
    for child, parent in parents.items():
        digest.supabase(f"boards?key=eq.{urllib.parse.quote(child)}", {"parent_id": ids[parent]}, method="PATCH")
    rows = [{**{k: v for k, v in f.items() if k != "key"}, "board_id": ids[f["key"]]} for f in follows]
    digest.supabase("follows?on_conflict=account,board_id", rows, prefer="resolution=merge-duplicates")
    print(f"ライブラリ：版面 {len(boards)}・店長の follows {len(rows)}・上級 {len(parents)}")


# ── お客さまの選んだもの → ライブラリの版面（2026-10-24）─────────────────────────────
# 入口・カードで選んだもの（app_users.prefs.picks）を、ライブラリの版面に決めて follows に書く。
# 同じものの決め方は店長と同じ印（board_key）：① もうある版面と名前（そろえたもの）が同じ → その版面
# ② Wikidata を名前で検索し、項目の名前・別名・当たった文字がそろえて名前と同じもの（曖昧さ回避・一覧のページは除く）→ wd:Q…
# ③ どちらもなければ名前の印 n:…。もうある版面の設定（店長のものも）は書き換えない。人ごとの置き方は最初の 1 回だけ書く（あとで本人が変える）。
# 公開のログ・boards には、だれが選んだか（account）を書かない（boards はだれでも読める）。
MAX_FOLLOWS = 100           # 追いかけられる数（app_users.board_limit の既定と同じ）
USER_CREATED = "user"       # boards.created_by：お客さまが足した版面（だれかは書かない）
NOT_TOPIC = ("disambiguation", "曖昧さ回避", "消歧义", "wikimedia list", "一覧")


def find_pick_wikidata(name, get=_wd_get):
    """お客さまの選んだ名前 → Wikidata の番号（名前がそろえて同じ項目だけ。なければ None）。断られたら WdBlocked。"""
    want = norm_name(name)
    if len(want) < 2:
        return None
    for lang in ("ja", "en"):
        hits = (get({"action": "wbsearchentities", "search": name, "language": lang, "uselang": lang, "limit": 7, "type": "item"}).get("search") or [])
        for h in hits:
            desc = str(h.get("description") or "").lower()
            if any(w in desc for w in NOT_TOPIC):
                continue
            labels = {norm_name(h.get("label")), norm_name((h.get("match") or {}).get("text"))} | {norm_name(a) for a in h.get("aliases") or []}
            if want in labels and re.fullmatch(r"Q\d+", str(h.get("id") or "")):
                return h["id"]
    return None


def pick_board(name, sec, langs):
    """お客さまの 1 つ → 新しく足す版面の共有の設定（userfeed.board_item と同じ匹配词の規則）と置き方。"""
    import taxonomy
    import userfeed
    item = userfeed.board_item(name, sec, langs)
    shared, mine = split_item(item)
    section = mine.get("section")
    mine["subs"] = taxonomy.guess_subs(section, name) if section else {}
    return shared, mine


def plan_users(users, boards, get=_wd_get, pause=1.0):
    """users = [{email, prefs}]、boards = いまのライブラリ [{id, key, name, names}]。
    返す：{"new": {key: boards の行}, "follows": [{account, key, section, subs, pos}], "counts": {...}}。
    1 度断られたら残りは聞かず、その回は書かない（次の回に）。"""
    import time
    import userfeed
    by_name, keys = {}, set()
    for b in boards:
        keys.add(b["key"])
        for n in [b.get("name"), *((b.get("names") or {}).values())]:
            if norm_name(n):
                by_name.setdefault(norm_name(n), b["key"])
    new, follows = {}, []
    counts = {"users": 0, "picks": 0, "same": 0, "wd": 0, "name": 0, "blocked": 0, "over": 0}
    blocked = False
    for u in users:
        prefs = u.get("prefs") or {}
        picks = prefs.get("picks") if isinstance(prefs.get("picks"), list) else []
        if not picks:
            continue
        counts["users"] += 1
        account = userfeed.account_of(u.get("email"))
        langs = userfeed.news_langs(prefs)
        seen = set()
        for pos, p in enumerate(picks):
            name = userfeed.pick_name((p or {}).get("name")) if isinstance(p, dict) else ""
            if not norm_name(name) or norm_name(name) in seen:
                continue
            seen.add(norm_name(name))
            if len(seen) > MAX_FOLLOWS:
                counts["over"] += 1
                continue
            counts["picks"] += 1
            key = by_name.get(norm_name(name))
            if key:
                counts["same"] += 1
            else:
                qid = None
                if blocked:
                    counts["blocked"] += 1
                    continue
                try:
                    qid = find_pick_wikidata(name, get)
                except WdBlocked:
                    blocked = True
                    counts["blocked"] += 1
                    continue
                if pause:
                    time.sleep(pause)
                key = "wd:" + qid if qid else "n:" + norm_name(name)
                if key in keys:
                    counts["same"] += 1
                else:
                    shared, _ = pick_board(name, p.get("sec"), langs)
                    new[key] = {"key": key, "name": name[:80], "names": {"ja": name[:80]}, "wd": qid, "config": shared,
                                "created_by": USER_CREATED}
                    keys.add(key)
                    counts["wd" if qid else "name"] += 1
                by_name.setdefault(norm_name(name), key)
            _, mine = pick_board(name, p.get("sec"), langs)
            follows.append({"account": account, "key": key, "section": mine.get("section"), "subs": mine.get("subs") or {}, "pos": pos})
    return {"new": new, "follows": follows, "counts": counts}


def push_users(db=None, get=_wd_get):
    """お客さまの選んだものをライブラリへ（library.yml、1 時間ごと）。ログ（公開）は数だけ。"""
    import digest
    import runlog
    import userfeed
    db = db or digest.supabase
    users, _ = userfeed.fetch_all(db, "rpc/userfeed_users", {})
    if users is None:
        raise SystemExit("SUPABASE_SERVICE_KEY がないので書けません")
    boards, _ = userfeed.fetch_all(db, "boards?select=id,key,name,names&order=id")
    r = plan_users(users, boards or [], get)
    if r["new"]:
        db("boards?on_conflict=key", list(r["new"].values()), prefer="resolution=ignore-duplicates")
        boards, _ = userfeed.fetch_all(db, "boards?select=id,key,name,names&order=id")
    ids = {b["key"]: b["id"] for b in boards or []}
    have, _ = userfeed.fetch_all(db, "follows?select=account,board_id&order=account,board_id")
    have = {(h["account"], h["board_id"]) for h in have or []}
    rows = [{k: v for k, v in {**f, "board_id": ids.get(f["key"])}.items() if k != "key"} for f in r["follows"]
            if ids.get(f["key"]) and (f["account"], ids[f["key"]]) not in have]
    if rows:
        db("follows?on_conflict=account,board_id", rows, prefer="resolution=ignore-duplicates")
    c = r["counts"]
    msg = (f"お客さまの版面：{c['users']} 人・{c['picks']} 個（もとからある版面 {c['same']}・Wikidata で足した {c['wd']}・名前で足した {c['name']}"
           f"・断られて次の回へ {c['blocked']}・上限を超えた {c['over']}）・follows {len(rows)}")
    if rows or r["new"] or c["blocked"]:   # 変わらなかった回はログに書かない（空回りのコミットを作らない）
        runlog.add("library", msg, level="warn" if c["blocked"] else "info", **{f"u_{k}": v for k, v in c.items()})
    print(msg)
    return r


if __name__ == "__main__":
    items = (yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")) or {}).get("items") or []
    if "--refresh" in sys.argv:
        sys.path.insert(0, str(ROOT / "scripts"))
        refresh_main()
        items = (yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")) or {}).get("items") or []
    if "--sql" in sys.argv:
        print(shop_sql(items))
    if "--push" in sys.argv:
        sys.path.insert(0, str(ROOT / "scripts"))
        push_shop(items)
    if "--users" in sys.argv:
        sys.path.insert(0, str(ROOT / "scripts"))
        push_users()
