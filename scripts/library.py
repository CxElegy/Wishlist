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


def _sitelinks(ids, get):
    """項目ごとの Wikipedia の言語数（向導の「情報少なめ」と同じ物差し）。"""
    if len(ids) < 2:
        return {}
    d = get({"action": "wbgetentities", "ids": "|".join(ids), "props": "sitelinks"})
    return {q: len((e or {}).get("sitelinks") or {}) for q, e in (d.get("entities") or {}).items()}


FRANCHISE = re.compile(r"media franchise|メディアミックス|媒体系列|跨媒体", re.I)
FRANCHISE_SECS = ("影视", "游戏", "好物", "演出", "出行")   # 作品・IP 型の 8 面が入る板块（docs/additem.js の MEDIA）


def find_pick_wikidata(name, get=_wd_get, sec=None):
    """お客さまの選んだ名前 → Wikidata の番号（名前がそろえて同じ項目だけ。なければ None）。断られたら WdBlocked。
    候補（名前か別名がそろえて同じ項目）の順番（2026-10-24、お客さまの版面の引き直しで決めた）：
    1. 説明が選んだ板块に入る（taxonomy.classify(説明) == sec）もの：F1 は映画「F1」ではなく自動車レース
    2. 名前（label）が同じもの。ただし Wikipedia の言語数 ×4 が別名で当たった一番の候補より少ないものは「情報少なめ」として後ろ
       （向導の thin と同じ物差し）
    3. Wikipedia の言語数が多いもの：京都 は 平安京（36）ではなく 京都市（260）
    3 字までの英数字は、別名だけで当たる候補を板块に入るときしか使わない（「Ado」が別名 ADO のアデノシンに当たった）。
    メディアミックス・media franchise の項目（作品・IP 全体）は作品・ゲーム・グッズ・音楽・おでかけのどの板块にも入るとみなす
    （ゲームの板块で選んだ「ポケットモンスター」がゲームシリーズ Q24558579〔33〕ではなく作品全体 Q864〔126〕のまま。
    1 つの名前は 1 つの版面、ゲーム・グッズは同じ版面の枝：CLAUDE.md「作品・IP 型の面」）。"""
    import taxonomy
    want = norm_name(name)
    if len(want) < 2:
        return None
    short = want.isascii() and len(want) <= 3
    cands = {}
    for lang in ("ja", "en"):
        hits = (get({"action": "wbsearchentities", "search": name, "language": lang, "uselang": lang, "limit": 7, "type": "item"}).get("search") or [])
        for h in hits:
            desc = str(h.get("description") or "")
            if any(w in desc.lower() for w in NOT_TOPIC) or not re.fullmatch(r"Q\d+", str(h.get("id") or "")):
                continue
            c = cands.setdefault(h["id"], {"label": False, "alias": False, "desc": "", "order": len(cands)})
            c["desc"] += " " + desc
            m = h.get("match") or {}
            others = {norm_name(a) for a in h.get("aliases") or []}
            if m.get("type") != "label":
                others.add(norm_name(m.get("text")))
            if norm_name(h.get("label")) == want:
                c["label"] = True
            elif want in others:
                c["alias"] = True
    use_sec = sec and sec != taxonomy.OTHER
    for c in cands.values():
        c["fits"] = bool(use_sec and (taxonomy.classify(c["desc"]) == sec
                                      or (sec in FRANCHISE_SECS and FRANCHISE.search(c["desc"]))))
    keep = {q: c for q, c in cands.items() if c["label"] or (c["alias"] and (not short or c["fits"]))}
    if not keep:
        return None
    sl = _sitelinks(list(keep), get)
    best_alias = max([sl.get(q, 0) for q, c in keep.items() if not c["label"]] or [0])
    def rank(q):
        c = keep[q]
        return (c["fits"], c["label"] and sl.get(q, 0) * 4 >= best_alias, sl.get(q, 0), -c["order"])
    return max(keep, key=rank)


RECHECK_VER = 3   # 番号の決め方（find_pick_wikidata）を変えたら上げる：お客さまの版面を 1 度ずつ引き直す


def recheck_plan(boards, follows, get=_wd_get, cache=None, limit=25, pause=1.0):
    """お客さまが足した版面（created_by = user）を今の規則で引き直す（1 版面 1 度、RECHECK_VER ごと）。
    boards = [{id, key, name, wd, created_by}]、follows = [{account, board_id, section, subs}]。
    返す：([{"id", "name", "old", "new", "wd", "sec"}]（番号が変わるものだけ）, 引き直した数)。断られたらそこまで（印を付けたものは次の回に回さない）。"""
    import time
    cache = {} if cache is None else cache
    done = cache.setdefault("_recheck", {})
    sec_of = {}
    for f in follows:
        sec_of.setdefault(f.get("board_id"), f.get("section"))
    out, checked = [], 0
    for b in boards:
        if b.get("created_by") != USER_CREATED or done.get(b["key"]) == RECHECK_VER or b.get("id") not in sec_of:
            continue
        if limit <= 0:
            break
        limit -= 1
        sec = sec_of.get(b["id"])
        try:
            qid = find_pick_wikidata(b.get("name") or "", get, sec)
        except WdBlocked:
            break
        if pause:
            time.sleep(pause)
        new = "wd:" + qid if qid else "n:" + norm_name(b.get("name"))
        done[b["key"]] = done[new] = RECHECK_VER
        checked += 1
        if new != b["key"]:
            out.append({"id": b["id"], "name": b.get("name") or "", "old": b["key"], "new": new, "wd": qid, "sec": sec})
    return out, checked


def recheck_apply(plans, boards, follows, db, get=_wd_get, cache=None):
    """引き直した番号を書く（消さない：行の key・wd を書き換えるか、follows を同じ版面へ付け替える）。
    付け替えたお客さまの小分類は、前の番号から機械が決めた値のままなら新しい番号の事実で決め直す。返す：数。"""
    import taxonomy
    cache = {} if cache is None else cache
    by_key = {b["key"]: b for b in boards}
    have = {(f["account"], f["board_id"]) for f in follows}
    n = {"moved": 0, "merged": 0, "kept": 0, "subs": 0}
    for p in plans:
        target = by_key.get(p["new"])
        if target is None:
            db(f"boards?id=eq.{p['id']}", {"key": p["new"], "wd": p["wd"]}, "return=minimal", method="PATCH")
            by_key[p["new"]] = {**by_key.pop(p["old"], {}), "key": p["new"], "wd": p["wd"], "id": p["id"]}
            tid = p["id"]
            n["moved"] += 1
        else:
            tid = target["id"]
        for f in [f for f in follows if f["board_id"] == p["id"]]:
            if tid != p["id"]:
                if (f["account"], tid) in have:     # 同じ人がもう新しい版面を追いかけている：古い行はそのまま（消さない）
                    n["kept"] += 1
                    continue
                db(f"follows?account=eq.{f['account']}&board_id=eq.{p['id']}", {"board_id": tid}, "return=minimal", method="PATCH")
                have.add((f["account"], tid))
                n["merged"] += 1
            sec, subs, name = f.get("section"), f.get("subs") or {}, p["name"]
            if not sec:
                continue
            auto = [taxonomy.guess_subs(sec, ""), taxonomy.guess_subs(sec, name)]
            try:
                if p["old"].startswith("wd:"):
                    auto.append(subs_for(sec, name, facts_for(p["old"][3:], get, cache)))
                facts = facts_for(p["wd"], get, cache) if p["wd"] else None
            except WdBlocked:
                continue
            new = subs_for(sec, name, facts)
            if subs in auto and new and new != subs:
                db(f"follows?account=eq.{f['account']}&board_id=eq.{tid}", {"subs": new}, "return=minimal", method="PATCH")
                n["subs"] += 1
    return n


# 小分類は名前だけでは決まらない（2026-10-24 別の目の指摘：大谷翔平・F1・NBA が「サッカー」、BTS が「ソロ」、
# フリーレン・鬼滅が「映画」、キャンプ・広島旅行が「ペット」＝ どの分け方も 1 つ目の値に落ちていた）。
# Wikidata の項目の説明（ja・en）と、種類（P31）・上位（P279）・ジャンル（P136）・競技（P641）・機種（P400）・
# 業種（P452）・国（P495・P17・P27）の名前を足した文で taxonomy.guess_subs を引く（HARNESS §6：細かい分け方は Wikidata から）。
# ゲームは機種が 2 つ以上の種類（スマホ・家庭用・PC）にまたがれば「マルチ」、発売日（P577・P571）が過ぎていれば「発売済み」。
FACT_PROPS = ("P31", "P279", "P136", "P641", "P400", "P452", "P495", "P17", "P27")
FACTS_FILE = ROOT / "state" / "wd_facts.json"   # 番号 → 引いた結果（30 日。毎時の回で同じ項目を聞き直さない）
FACTS_DAYS = 30


def wd_facts(qid, get=_wd_get, today=None):
    """Wikidata の項目 → {"text": 説明と関係する項目の名前, "platforms": [機種の名前], "released": True/False/None}。断られたら WdBlocked。"""
    import datetime
    d = get({"action": "wbgetentities", "ids": qid, "props": "descriptions|claims", "languages": "ja|en"})
    ent = (d.get("entities") or {}).get(qid) or {}
    descs = [v.get("value", "") for v in (ent.get("descriptions") or {}).values()]
    claims = ent.get("claims") or {}

    def ids(pid):
        out = []
        for c in claims.get(pid) or []:
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(v, dict) and re.fullmatch(r"Q\d+", str(v.get("id") or "")):
                out.append(v["id"])
        return out
    rel = {pid: ids(pid)[:12] for pid in FACT_PROPS}
    want = list(dict.fromkeys(q for qs in rel.values() for q in qs))[:50]
    labels = {}
    if want:
        got = get({"action": "wbgetentities", "ids": "|".join(want), "props": "labels", "languages": "ja|en"})
        for q, e in (got.get("entities") or {}).items():
            labels[q] = [v.get("value", "") for v in (e.get("labels") or {}).values()]
    dates = []
    for pid in ("P577", "P571"):
        for c in claims.get(pid) or []:
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            m = re.match(r"[+]?(\d{4})-(\d\d)-(\d\d)", str((v or {}).get("time") or "")) if isinstance(v, dict) else None
            if m:
                dates.append((int(m[1]), max(1, int(m[2])), max(1, int(m[3]))))
    today = today or datetime.date.today()
    released = (min(dates) <= (today.year, today.month, today.day)) if dates else None
    text = " ".join(descs + [x for q in want for x in labels.get(q, [])])
    return {"text": text, "platforms": [x for q in rel["P400"] for x in labels.get(q, [])], "released": released}


def load_facts():
    try:
        return json.loads(FACTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_facts(cache):
    FACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FACTS_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def facts_for(qid, get, cache, today=None):
    """キャッシュ（30 日）があればそれ、なければ聞いて入れる。"""
    import datetime
    today = today or datetime.date.today()
    hit = cache.get(qid)
    if hit and str(hit.get("at", "")) >= (today - datetime.timedelta(days=FACTS_DAYS)).isoformat():
        return hit
    f = wd_facts(qid, get, today)
    cache[qid] = {**f, "at": today.isoformat()}
    return cache[qid]


def subs_for(section, name, facts=None):
    """板块・名前・Wikidata の事実 → 小分類（分け方ごとに 1 つ）。"""
    import taxonomy
    if not section:
        return {}
    facts = facts or {}
    subs = taxonomy.guess_subs(section, " ".join([name, facts.get("text") or ""]))
    if section == "游戏":
        scheme = {x["id"]: x for x in (taxonomy.SECTIONS.get(section) or {}).get("schemes") or []}
        plat = scheme.get("platform", {}).get("values") or []
        kinds = {taxonomy.values({"values": [v]})[0] for v in plat[:3]
                 for p in facts.get("platforms") or [] if taxonomy._says(v, p)}
        if len(kinds) >= 2 and "マルチ" in taxonomy.values(scheme.get("platform", {})):
            subs["platform"] = "マルチ"
        status = taxonomy.values(scheme.get("status", {}))
        if facts.get("released") and subs.get("status") == (status or [None])[0] and "発売済み" in status:
            subs["status"] = "発売済み"
    return subs


def pick_board(name, sec, langs, facts=None):
    """お客さまの 1 つ → 新しく足す版面の共有の設定（userfeed.board_item と同じ匹配词の規則）と置き方。"""
    import userfeed
    item = userfeed.board_item(name, sec, langs)
    shared, mine = split_item(item)
    mine["subs"] = subs_for(mine.get("section"), name, facts)
    return shared, mine


def plan_users(users, boards, get=_wd_get, pause=1.0, have=(), cache=None):
    """users = [{email, prefs}]、boards = いまのライブラリ [{id, key, name, names}]、have = もうある follows の (account, key)。
    返す：{"new": {key: boards の行}, "follows": [{account, key, section, subs, pos}], "counts": {...}}。
    もうある follows は数えるだけで小分類を引き直さない（本人の置き方は書き換えない）。
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
    have = set(have)
    cache = {} if cache is None else cache
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
                    qid = find_pick_wikidata(name, get, p.get("sec"))
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
            if (account, key) in have:
                continue
            facts = None
            if key.startswith("wd:") and not blocked:
                try:
                    facts = facts_for(key[3:], get, cache)
                except WdBlocked:   # 小分類は名前だけで決めて書き、次の回の resubs が直す
                    blocked = True
            _, mine = pick_board(name, p.get("sec"), langs, facts)
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
    boards, _ = userfeed.fetch_all(db, "boards?select=id,key,name,names,wd,created_by&order=id")
    have, _ = userfeed.fetch_all(db, "follows?select=account,board_id,section,subs&account=like.u_*&order=account,board_id")
    by_id = {b["id"]: b for b in boards or []}
    cache = load_facts()
    r = plan_users(users, boards or [], get, have={(h["account"], by_id.get(h["board_id"], {}).get("key")) for h in have or []}, cache=cache)
    if r["new"]:
        db("boards?on_conflict=key", list(r["new"].values()), prefer="resolution=ignore-duplicates")
        boards, _ = userfeed.fetch_all(db, "boards?select=id,key,name,names,wd,created_by&order=id")
    ids = {b["key"]: b["id"] for b in boards or []}
    rc = {"checked": 0, "moved": 0, "merged": 0, "kept": 0, "subs": 0}
    if not r["counts"]["blocked"]:
        plans, rc["checked"] = recheck_plan(boards or [], have or [], get, cache)
        rc.update(recheck_apply(plans, boards or [], have or [], db, get, cache))
        if plans:   # 付け替えた行を読み直してから小分類を見る
            boards, _ = userfeed.fetch_all(db, "boards?select=id,key,name,names,wd,created_by&order=id")
            have, _ = userfeed.fetch_all(db, "follows?select=account,board_id,section,subs&account=like.u_*&order=account,board_id")
            by_id = {b["id"]: b for b in boards or []}
            ids = {b["key"]: b["id"] for b in boards or []}
    fixed = resubs(have or [], by_id, get, cache, db) if not r["counts"]["blocked"] else 0
    save_facts(cache)
    have = {(h["account"], h["board_id"]) for h in have or []}
    rows = [{k: v for k, v in {**f, "board_id": ids.get(f["key"])}.items() if k != "key"} for f in r["follows"]
            if ids.get(f["key"]) and (f["account"], ids[f["key"]]) not in have]
    if rows:
        db("follows?on_conflict=account,board_id", rows, prefer="resolution=ignore-duplicates")
    c = r["counts"]
    msg = (f"お客さまの版面：{c['users']} 人・{c['picks']} 個（もとからある版面 {c['same']}・Wikidata で足した {c['wd']}・名前で足した {c['name']}"
           f"・断られて次の回へ {c['blocked']}・上限を超えた {c['over']}）・follows {len(rows)}・小分類を直した {fixed}"
           f"・番号の引き直し {rc['checked']}（番号を直した {rc['moved']}・同じ版面へ付け替え {rc['merged']}・小分類 {rc['subs']}）")
    if rows or r["new"] or c["blocked"] or fixed or rc["moved"] or rc["merged"]:   # 変わらなかった回はログに書かない（空回りのコミットを作らない）
        runlog.add("library", msg, level="warn" if c["blocked"] else "info", **{f"u_{k}": v for k, v in c.items()},
                   **{f"wd_{k}": v for k, v in rc.items()})
    print(msg)
    return r


def resubs(follows, by_id, get, cache, db, limit=60):
    """前に名前だけで決めた小分類（1 つ目の値に落ちていた）を Wikidata の事実で引き直す（2026-10-24）。
    直すのは、分け方ごとの値がどれも「1 つ目の値」か「名前だけで決めた値」の行だけ（本人が選んだらしい値の行は触らない）。直した数を返す。"""
    import taxonomy
    n = 0
    for h in follows:
        b = by_id.get(h.get("board_id")) or {}
        sec, subs = h.get("section"), h.get("subs") or {}
        if not sec or not b or not subs:
            continue
        first, by_name = taxonomy.guess_subs(sec, ""), taxonomy.guess_subs(sec, b.get("name") or "")
        if set(subs) != set(first) or any(subs[k] not in (first[k], by_name.get(k)) for k in subs):
            continue
        key = b.get("key") or ""
        facts = None
        if key.startswith("wd:"):
            if limit <= 0:
                break
            if key[3:] not in cache:
                limit -= 1
            try:
                facts = facts_for(key[3:], get, cache)
            except WdBlocked:
                break
        new = subs_for(sec, b.get("name") or "", facts)
        if new and new != subs:
            db(f"follows?account=eq.{h['account']}&board_id=eq.{h['board_id']}", {"subs": new}, "return=minimal", method="PATCH")
            n += 1
    return n


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
