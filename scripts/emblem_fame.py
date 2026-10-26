"""小元素の「知られている点数」（2026-10-26，用户定的：名簿の並びでなく、外の人気の物差しで誰を出すか決める）。

点数 = max(AniList のお気に入り数, Wikipedia（英語）の直近 90 日の閲覧数 ÷ 30) の常用対数（0〜5 くらい）。
- AniList：キャラ検索（名前が合い、作品の名前が合うものだけ）。アニメ・漫画・ゲームのキャラはここで取れる。
- Wikipedia：実写・AniList にないもの。検索の 1 位の記事の閲覧数（Pageviews API）。
結果は state/emblem_fame.json に残す（同じ人は 30 日は引き直さない）。版面の 1 つずつ `python scripts/emblem_fame.py <版面の名前>`。
"""
import json
import math
import pathlib
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

FILE = pathlib.Path(__file__).resolve().parent.parent / "state" / "emblem_fame.json"
UA = {"User-Agent": "wishlist-bot/1.0 (https://github.com/CxElegy/Wishlist)"}
TTL = 30 * 86400


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _fold(s):
    """ローマ字のゆれ（Tōshirō = Toushirou = Toshiro）をそろえる。"""
    return re.sub(r"[ou]+", lambda m: m.group()[0], _norm(s)) if s else ""


def _get(url, data=None, headers=None, waits=(0, 4, 10)):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    for wait in waits:
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait == waits[-1]:
                raise


def anilist(name, work):
    """→ (お気に入り数, AniList の名前) か None。名前の語が合い、作品の名前にも work が入るものだけ。
    検索は 全部の名前 → 名字（最後の語）→ 最初の語 の順（ローマ字のゆれ Tōshirō / Toushirou で当たらないため）。"""
    q = ('query($s:String){Page(perPage:8){characters(search:$s,sort:FAVOURITES_DESC){name{full alternative}favourites'
         ' media(perPage:6){nodes{title{romaji english}}}}}}')
    base = _norm(re.sub(r"\s*\(.*\)", "", name))
    words = base.split()
    want = set(_fold(name).split())
    w = _norm(work)
    for s in dict.fromkeys([base] + words[::-1][:2]):
        d = _get("https://graphql.anilist.co", json.dumps({"query": q, "variables": {"s": s}}).encode(),
                 {"Content-Type": "application/json"})
        for c in d["data"]["Page"]["characters"]:
            names = [c["name"]["full"]] + list(c["name"].get("alternative") or [])
            if not want or not any((lambda g: g and (want <= g or g <= want))(set(_fold(n).split())) for n in names):
                continue
            titles = " ".join(_norm(t["title"].get("romaji")) + " " + _norm(t["title"].get("english")) for t in c["media"]["nodes"])
            if w and w.split()[0] not in titles:
                continue
            return c["favourites"], c["name"]["full"]
        time.sleep(0.5)
    return None


def wikipedia(name, work, live=False):
    """→ (直近 90 日の閲覧数, 記事の名前) か None。記事の名前は「名前」→「名前 (作品)」の順に直接引く
    （検索の API は混み合うと 429 になり、別の記事に当たることもあるので使わない）。"""
    end = time.strftime("%Y%m%d00", time.gmtime(time.time() - 86400))
    start = time.strftime("%Y%m%d00", time.gmtime(time.time() - 91 * 86400))
    base = re.sub(r"\s*[（(].*[）)]", "", name).strip()   # 「Harry Potter（Dominic McLaughlin）」→ 役の名前
    for title in ((base, f"{base} (character)", f"{base} ({work})") if live else (f"{base} ({work})",)):   # アニメ・ゲームは「名前 (作品)」だけ（Akon → 歌手、を避ける）
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
               + urllib.parse.quote(title.replace(" ", "_"), safe="") + f"/daily/{start}/{end}")
        try:
            p = _get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue   # 記事がない
            raise
        return sum(i["views"] for i in p["items"]), title
    return None


def score(name, work, cache, live=False):
    """→ {score, fav, wp, wp_title, src}。cache は state/emblem_fame.json の dict（呼ぶ側が保存）。"""
    k = _norm(work) + "|" + _norm(name)
    c = cache.get(k)
    if c and time.time() - c.get("at", 0) < TTL:
        return c
    fav = wp = None
    failed = False
    try:
        fav = anilist(name, work)
    except Exception as e:
        failed = True
        print(f"  AniList {name}: {e}", file=sys.stderr)
    time.sleep(0.8)
    try:
        wp = None if fav and fav[0] >= 1000 else wikipedia(name, work, live)   # AniList で十分知られていれば Wikipedia は引かない
    except Exception as e:
        failed = True
        print(f"  Wikipedia {name}: {e}", file=sys.stderr)
    a = math.log10(1 + fav[0]) if fav else 0.0
    b = math.log10(1 + wp[0] / 30) if wp else 0.0
    r = {"score": round(max(a, b), 3), "fav": fav[0] if fav else None, "anilist": fav[1] if fav else None,
                "wp": wp[0] if wp else None, "wp_title": wp[1] if wp else None,
                "src": "AniList" if a >= b and fav else ("Wikipedia" if wp else "なし"), "at": int(time.time())}
    if not failed:   # 混み合って取れなかった分は残さない（次に引き直す）
        cache[k] = r
    return r


ROSTER_WORDS = re.compile(r"roster|line-?up|playable|launch characters|参戦|使用キャラ|キャラクター一覧|出场角色|登场角色", re.I)


def _name_hit(name, text_norm, text_fold):
    """名前が記事の文に出ているか：全部の名前、か最初の語（4 字以上。AniList の名前は 名・姓 の順）。"""
    full = _norm(re.sub(r"\s*[（(].*[）)]", "", name))
    if not full:
        return False
    if f" {full} " in text_norm:
        return True
    first = full.split()[0]
    return len(first) >= 4 and (f" {first} " in text_norm or f" {_fold(first)} " in text_fold)


def mentions(subjects, stories):
    """記事に出た回数と「使えるキャラ」。stories = [(見出し＋要約, 日付)]（その版面の直近 30 日）。
    → ({名前: 出た記事の数}, {使えるキャラの名前}) 。「roster・lineup・playable・参戦」を見出しに持つ記事に名前が出た人 = 使えるキャラ。"""
    n = {s: 0 for s in subjects}
    roster = set()
    for text, _d in stories:
        tn, tf = f" {_norm(text)} ", f" {_fold(text)} "
        for s in subjects:
            if _name_hit(s, tn, tf):
                n[s] += 1
                if ROSTER_WORDS.search(text.split("\n")[0]):
                    roster.add(s)
    return n, roster


def poll(wiki):
    """Fandom の公式人気投票のページ（Popularity polls など）の最新の回 → {正規化した名前: 順位}。なければ {}。
    各回は「1. [[名前]] = 票数」の行が並ぶ。順位の行（数字で始まる行）が 10 行以上ある最後の節を取る。"""
    if not wiki:
        return {}
    try:
        s = _get(f"https://{wiki}.fandom.com/api.php?action=query&list=search&srsearch=popularity+poll&format=json&srlimit=5")
        title = next((x["title"] for x in s["query"]["search"] if re.search(r"poll|ranking|popularity", x["title"], re.I)), None)
        if not title:
            return {}
        w = _get(f"https://{wiki}.fandom.com/api.php?action=parse&page={urllib.parse.quote(title)}&prop=wikitext&format=json")["parse"]["wikitext"]["*"]
    except Exception as e:
        print(f"  人気投票 {wiki}: {e}", file=sys.stderr)
        return {}
    best = {}
    for sec in re.split(r"\n==[^=]", w):
        rows = re.findall(r"^\s*(\d+)\.\s*\[?\[?(?:[^\]|=\n]*\|)?([^\]=\n<]+?)\]?\]?\s*=", sec, re.M)
        if len(rows) >= 10:
            best = {_norm(n): int(r) for r, n in rows}
    return best


def bonus(name, mention, roster, polls):
    """点数に足す分（2026-10-26，用户定的 案 2）：公式の人気投票 1 位 +1.2（30 位で 0）・ゲームで使える +1.5・記事に出た回数 +0.5×log10(1+回数)（上限 1.0）。"""
    r = polls.get(_norm(re.sub(r"\s*[（(].*[）)]", "", name)))
    return round((max(0.0, 1.2 * (31 - r) / 30) if r else 0.0) + (1.5 if name in roster else 0.0) + min(1.0, 0.5 * math.log10(1 + mention.get(name, 0))), 3)


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(cache):
    FILE.parent.mkdir(exist_ok=True)
    FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def _body(story):
    """名簿の記事（見出しに roster・lineup など）だけ、本文を取る（要約には名前が並ばないため）。取れなければ空。"""
    if not ROSTER_WORDS.search(story.get("headline") or "") or not story.get("url"):
        return ""
    try:
        req = urllib.request.Request(story["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            h = r.read(600000).decode("utf-8", "ignore")
        return " " + re.sub(r"\s+", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", h, flags=re.S))
    except Exception:
        return ""


def context(item, subjects, days=30):
    """版面（items.yaml の 1 件）の 記事に出た回数・使えるキャラ・公式人気投票 → rank の ctx。記事は reports/ の直近 days 日の見出し＋要約。"""
    stories = []
    cut = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    for f in sorted((FILE.parent.parent / "reports").glob("*.json")):
        if f.stem < cut:
            continue
        try:
            for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
                if it.get("name") == item["name"]:
                    stories += [((s.get("headline") or "") + "\n" + (s.get("blurb") or "") + _body(s), f.stem) for s in it.get("stories", [])]
        except Exception:
            pass
    n, roster = mentions(subjects, stories)
    return n, roster, poll(item.get("emblem_fandom"))


def rank(subjects, work, cache, live=False, ctx=None):
    """名簿 → 知られている点数の高い順の [(名前, 点数の記録)]。同点は名簿の順。
    ctx = (mention, roster, polls) があれば bonus を足す（記録の score は外の物差し、total が並べる点数）。"""
    rows = []
    for s in subjects:
        r = dict(score(s, work, cache, live))
        r["bonus"] = bonus(s, *ctx) if ctx else 0.0
        r["total"] = round(r["score"] + r["bonus"], 3)
        rows.append((s, r))
        if len(rows) % 10 == 0:
            save(cache)   # 途中で止まっても引いた分は残す
    return sorted(rows, key=lambda r: -r[1]["total"])


if __name__ == "__main__":
    import yaml
    root = pathlib.Path(__file__).resolve().parent.parent
    items = yaml.safe_load((root / "items.yaml").read_text(encoding="utf-8"))
    items = items["items"] if isinstance(items, dict) else items
    it = next(i for i in items if i["name"] == sys.argv[1])
    work = sys.argv[2] if len(sys.argv) > 2 else it["name"]
    live = len(sys.argv) > 3 and sys.argv[3] == "live"   # 実写の作品
    cache = load()
    subj = [e["subject"] for e in it.get("emblem") or []]
    for i, (s, r) in enumerate(rank(subj, work, cache, live)[:15], 1):
        print(i, s, r["score"], r["src"], r["fav"], r["wp"])
    save(cache)
