"""お客さまの分の記事集め（2026-10-22，用户定的：お客さまも店長と同じ流れを自分の分で。AI は使わない・規則だけ）。

お客さまが選んだもの（Supabase app_users.prefs.picks = [{name, sec}]）のうち、店長の関注項（items.yaml）にないもの
（名前のゆるい一致 = 網页の AUTH_JS の hit と同じ考え方）だけを、店長と同じ収集（digest.collect → filter_entries：
match・exclude・垃圾・exclude_sources・exclude_hosts・重複）とキーワード編集（fallback_stories）・言語違いの重複（lang.dedupe）で集め、
Supabase の user_boards（db/user_boards.sql）に本人の account（'u_' + md5(メール) の先頭 16 字）で書く。
本人は網页から my_boards() で自分の行だけを読む。リポジトリ・公開の網页には入れない（LOGIN.md 第 2 步「本人のページは本人だけ」）。

店長の関注項にあるもの（ちいかわ 等）は店長の版面（公開のニュース）をそのまま見せるので、ここでは集めない。

    python scripts/userfeed.py            # Actions（SUPABASE_SERVICE_KEY があるとき）。digest.yml の収集のあと
    python scripts/userfeed.py --dry-run  # 何を集めるかだけ出す（ネットに出ない・書かない）
"""
import datetime as dt
import hashlib
import re
import sys
import time
import urllib.parse

import digest
import lang
import taxonomy

MAX_BOARDS_PER_USER = 10   # 1 人・1 回で集める版面（選んだ順の先頭から）
MAX_STORIES = 12           # 1 版面に残す記事（新しい順）
KEEP_DAYS = 14             # これより古い記事は版面から落とす
MAX_BOARDS_PER_RUN = 60    # 1 回で集める版面（同じ名前・同じ言語は 1 回にまとめた数）
DEADLINE_MIN = 8           # 1 回の時間の上限（店長の収集・出刊・push のあとに走る。digest.yml の timeout 40 分に収める）
WORKERS = 4                # 並列（同じサイトの間隔は店長の収集と同じく sources._pace でスレッド間で共有）
MIN_GAP_MIN = 90           # 前に探してからこれより短ければ今回は飛ばす（収集は 2 時間ごと。push のたびに走っても同じ版面を叩かない）
SUMMARY_CHARS = 160

# 入口の「新しく始める」で選ぶ言語（welcome.LANG_GROUPS の code）→ 収集の言語（digest.NEWS_LANGS）・lang.py の言語
NEWS_LANG = {"ja": "ja-JP", "en": "en-US", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW", "ko": "ko-KR"}
LANG_CODE = {"ja-JP": "ja", "en-US": "en", "zh-CN": "zh", "zh-TW": "zh", "ko-KR": "ko"}
DEFAULT_LANGS = ["ja-JP"]   # 集めていない言語だけを選んだ人は、サイトの主言語（日本語）で


def norm(s):
    return re.sub(r"\s+", "", str(s or "").lower())


def loose_hit(a, b):
    """名前のゆるい一致（render.AUTH_JS の hit と同じ）：空白・大小を無視して同じか、2 字以上の片方がもう片方に含まれる。"""
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or len(b) > 1 and b in a or len(a) > 1 and a in b)


def account_of(email):
    """お客さまの account（db/user_boards.sql の private.user_account と同じ）。"""
    return "u_" + hashlib.md5(str(email or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def news_langs(prefs):
    """prefs.lang = {primary, also: [...]}（入口で選んだもの）→ 集める言語（2 つまで、集めている言語だけ）。"""
    conf = (prefs or {}).get("lang") or {}
    if isinstance(conf, str):
        conf = {"primary": conf}
    codes = [conf.get("primary"), *(conf.get("also") or [])] if isinstance(conf, dict) else []
    out = []
    for c in codes:
        n = NEWS_LANG.get(c)
        if n and n not in out:
            out.append(n)
    return out[:2] or list(DEFAULT_LANGS)


def board_item(name, sec, langs):
    """お客さまの 1 版面の、簡単な関注項（店長の items.yaml と同じ形）。
    匹配词は名前そのもの。空白で区切った名前（「広島 旅行」）は、全部の語が出てくる記事も（re: の先読み）。
    名前が普通の言葉のこともあるので SNS（Reddit・Bluesky・Mastodon）の全体検索はしない・GDELT は店長の収集に残す。"""
    name = str(name).strip()
    match = [name]
    parts = [p for p in re.split(r"\s+", name) if p]
    if len(parts) > 1:
        match.append("re:(?is)" + "".join(f"(?=.*{re.escape(p)})" for p in parts))
    sec = taxonomy.canonical(sec) if sec else None
    item = {"name": name, "keywords": [name], "match": match, "news_langs": list(langs),
            "use": ["google", "bing"], "gdelt": False, "type": "product", "max_entries": 30}
    if sec in taxonomy.SECTIONS:
        item["section"] = sec
    return item


def story_of(e):
    s = re.sub(r"<[^>]+>", " ", e.summary or "")
    s = re.sub(r"\s+", " ", s).strip()
    return {"title": e.title.strip(), "url": e.link or e.url, "source": e.source,
            "date": e.published.isoformat() if e.published else None,
            "image": e.image if str(e.image or "").startswith("https://") else "",
            "summary": s[:SUMMARY_CHARS]}


def stories_for(item, settings):
    """1 版面の記事（新しい順、MAX_STORIES 件まで）。店長の収集と同じ絞り込み・キーワード編集・言語違いの重複。"""
    now = dt.datetime.now(dt.timezone.utc)
    raw = digest.collect(item, settings)
    entries = digest.filter_entries(raw, item, settings, set(), now)
    picked = digest.fallback_stories(entries, item, limit=MAX_STORIES)
    out = [story_of(entries[p["refs"][0] - 1]) for p in picked]
    order = list(dict.fromkeys(LANG_CODE[l] for l in item["news_langs"] if l in LANG_CODE)) or ["ja"]
    out = [{**s, "headline": s["title"]} for s in out]
    out = [{k: v for k, v in s.items() if k != "headline"} for s in lang.dedupe(out, order)]
    return out


def _when(s):
    try:
        d = dt.datetime.fromisoformat(str(s.get("date") or ""))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def merge(old, new, now=None):
    """前の回の記事に今回の分を足す（同じ網址・同じ見出しは 1 本、KEEP_DAYS より古いものは落とす、新しい順に MAX_STORIES）。
    → (記事, 新しく増えた件数)"""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=KEEP_DAYS)
    seen, out, fresh = set(), [], set()
    for s, is_new in [*((s, False) for s in old or []), *((s, True) for s in new or [])]:
        if not isinstance(s, dict) or not s.get("title") or not str(s.get("url") or "").startswith(("http://", "https://")):
            continue
        keys = {s["url"], digest.title_key(s["title"])}
        if keys & seen:
            continue
        when = _when(s)
        if when and when < since or digest.is_spam(s["title"], s["url"]):
            continue
        seen |= keys
        out.append(s)
        if is_new:
            fresh.add(id(s))
    out.sort(key=lambda s: _when(s) or since, reverse=True)
    kept = out[:MAX_STORIES]
    return kept, sum(1 for s in kept if id(s) in fresh)


def plan(users, shop_names, rows, now=None):
    """集める版面を決める。→ (todo, keep)
    todo = [{key, name, sec, langs, boards: [(account, name)]}]（同じ名前・同じ言語は 1 回にまとめる。初めての版面 → 前に探したのが古い順）
    keep = {account: {name, ...}}（いま選んでいる、店長にないもの。これ以外の行は消す）"""
    now = now or dt.datetime.now(dt.timezone.utc)
    checked = {(r["account"], r["item"]): r.get("checked_at") for r in rows}
    keep, groups = {}, {}
    for u in users:
        email = u.get("email")
        prefs = u.get("prefs") or {}
        picks = prefs.get("picks") if isinstance(prefs, dict) else None
        if not email or not isinstance(picks, list):
            continue
        acct, langs = account_of(email), news_langs(prefs)
        mine = keep.setdefault(acct, set())
        for p in picks:
            if not isinstance(p, dict) or not str(p.get("name") or "").strip():
                continue
            name = str(p["name"]).strip()[:80]
            if any(loose_hit(s, name) for s in shop_names) or name in mine:
                continue   # 店長の版面をそのまま見せる
            if len(mine) >= MAX_BOARDS_PER_USER:
                break
            mine.add(name)
            at = checked.get((acct, name))
            try:
                last = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
            except ValueError:
                last = None
            if last and (now - last).total_seconds() < MIN_GAP_MIN * 60:
                continue
            key = (norm(name), tuple(langs))
            g = groups.setdefault(key, {"key": key, "name": name, "sec": p.get("sec"), "langs": langs, "boards": [], "last": last})
            g["boards"].append((acct, name))
            if last is None or g["last"] and last < g["last"]:
                g["last"] = last
    todo = sorted(groups.values(), key=lambda g: (g["last"] is not None, g["last"] or now))
    return todo[:MAX_BOARDS_PER_RUN], keep


def _q(v):
    return urllib.parse.quote(str(v), safe="")


def run(dry_run=False, db=None, collect=None, now=None, log=print):
    """1 回分。db = supabase() と同じ形の関数（テストで差し替える）、collect = stories_for と同じ形。
    → {"boards": 集めた版面の数, "found": 新しい記事, "late": 時間切れ, "failed": 失敗, "deleted": 消した行}"""
    db = db or digest.supabase
    collect = collect or stories_for
    started = time.monotonic()
    now = now or dt.datetime.now(dt.timezone.utc)
    settings, shop = digest.load_config()
    shop_names = [i["name"] for i in shop]
    users = db("app_users?select=email,prefs&left_at=is.null&email=not.is.null&limit=5000")
    if users is None:
        log("お客さまの記事集め：Supabase の鍵がないので飛ばす")
        return {"boards": 0, "found": 0, "late": 0, "failed": 0, "deleted": 0}
    rows = db("user_boards?select=account,item,stories,checked_at,updated_at&limit=20000") or []
    todo, keep = plan(users, shop_names, rows, now)
    log(f"お客さまの記事集め：{len(users)} 人・集める版面 {len(todo)}"
        + (f"（{'、'.join(g['name'] for g in todo[:12])}{' ほか' if len(todo) > 12 else ''}）" if todo else ""))
    if dry_run:
        return {"boards": len(todo), "found": 0, "late": 0, "failed": 0, "deleted": 0}

    def one(g):
        try:
            return collect(board_item(g["name"], g["sec"], g["langs"]), settings)
        except Exception as err:  # noqa: BLE001  1 版面の失敗で全体を止めない
            log(f"  {g['name']}：取れなかった（{type(err).__name__}: {str(err)[:120]}）")
            return None
    left = max(30, DEADLINE_MIN * 60 - (time.monotonic() - started))
    got, late = digest.run_parallel(one, todo, WORKERS, left, key=lambda g: g["key"])
    old = {(r["account"], r["item"]): r for r in rows}
    stamp = now.isoformat(timespec="seconds")
    out, found, failed = [], 0, 0
    for g in todo:
        new = got.get(g["key"])
        if g["key"] in late:
            continue   # 次の回に先に取る（checked_at を進めない）
        if new is None:
            failed += 1
        for acct, name in g["boards"]:
            prev = old.get((acct, name)) or {}
            stories, n = merge(prev.get("stories"), new or [], now)
            found += n
            out.append({"account": acct, "item": name, "sec": g["sec"] if g["sec"] else None, "stories": stories, "found": n,
                        "checked_at": stamp, "updated_at": stamp if n else prev.get("updated_at")})
    for i in range(0, len(out), 200):
        db("user_boards?on_conflict=account,item", out[i:i + 200], "resolution=merge-duplicates,return=minimal")
    deleted = 0
    for r in rows:   # 外したもの・店長の関注項に入ったもの・退会した人の行は消す（本人の画面には出ない行）
        if r["item"] not in keep.get(r["account"], ()):
            db(f"user_boards?account=eq.{_q(r['account'])}&item=eq.{_q(r['item'])}", method="DELETE")
            deleted += 1
    log(f"お客さまの記事集め：{len(out)} 版面を書いた・新しい記事 {found} 件"
        + (f"・時間切れ {len(late)}（次の回へ）" if late else "") + (f"・失敗 {failed}" if failed else "")
        + (f"・消した行 {deleted}" if deleted else "") + f"・{time.monotonic() - started:.0f} 秒")
    return {"boards": len(out), "found": found, "late": len(late), "failed": failed, "deleted": deleted}


def main():
    try:
        run(dry_run="--dry-run" in sys.argv)
    except Exception as err:  # noqa: BLE001  店長の収集・出刊はもう終わっている。失敗しても止めない（次の回にもう一度）
        print(f"::warning::お客さまの記事集めに失敗：{type(err).__name__}: {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
