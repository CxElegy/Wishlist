"""小元素の自動補完：どの関注項も「その種類にふさわしい枚数」の小元素を持つようにする。

emblem.py は「Wiki を 1 つ指定して取る」道具で、種類ごとの枚数も、Wiki がない場合の代わりの取り方もなかった。
そのため、(1) 人が API とページ名を毎回決める (2) Wiki にない主題（ブランド・刚出道のグループ・本人の別の写真）は取れず
emblem_skip で逃げる (3) 何枚あれば足りるかの基準がなく、1 枚のまま放置される、という穴ができた。
ここでは「種類 → 目標の枚数 → 取り方の順番（フォールバック）」を決め、足りないものを自動で見つけて埋める。

種類（items.yaml の emblem_kind。なければ type から推定）と目標の枚数：
  person     本人の別の写真        目標 6（最少 3、最大 10）
  group      メンバー全員          目標 = メンバー数（最少 3、最大 10）
  character  主役級のキャラ        目標 6（最少 3、最大 10。人気のキャラが多いものは emblem_max で 10 まで）
  brand      公式ロゴ              1
  topic      主題を表す物          目標 3（最少 2、最大 5）：ロゴ・トロフィー・ボール・場所・絵文字アイコン

取り方（上から順に試す。足りるまで次へ）：
  0. emblem_urls     items.yaml に直接書いた画像（公式の立ち絵など）
  1. AniList         アニメ・漫画の主役
  2. Fandom          キャラのページの代表画像（emblem_fandom に wiki 名）
  3. Wikipedia       本人・メンバー・ロゴのページ画像（emblem_who の名前 / wiki: の記事）
  4. Wikimedia Commons  同じ名前の写真（ライセンス付き）
  5. 公式サイト      site の og:image と大きい画像
  6. Web 画像検索    Bing 画像（出所が確かでないので、必ず目で確かめる）
  7. Twemoji         どうしても取れない主題の最後の砦（絵文字アイコン。ここまで来れば 0 枚にはならない）

使い方：
  python scripts/emblem_fill.py --audit                 全関注項の状況（足りない順）
  python scripts/emblem_fill.py "名前"                  候補を集めて /tmp/wishlist-emblem/<名前>.jpg に番号付きの一覧を作る
  python scripts/emblem_fill.py "名前" --commit 1,4,7   一覧の番号を選んで items.yaml に書き、抠图・顔の大きさをそろえる（--replace で置き換え）
  python scripts/emblem_fill.py --auto                  足りない関注項を全部、決まった順で自動で埋める（Web 画像検索は最後の手段）
"""

import argparse
import io
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emblem  # noqa: E402
import face_id  # noqa: E402
from emblem import ROOT, inspect, small_url  # noqa: E402

_last = {}
_orig_get = emblem._get


def _throttled_get(url, limit=emblem.MAX_BYTES):
    """Wikipedia / Commons は続けて叩くと 429（多すぎ）になるので、同じホストには 1.3 秒あけ、取れなければ長めに待って取り直す。"""
    host = urllib.parse.urlparse(url).netloc
    if host.endswith("wikipedia.org") or host.endswith("wikimedia.org") or host.endswith("wikidata.org"):
        wait = _last.get(host, 0) + 1.3 - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            return _orig_get(url, limit)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(30)
            return _orig_get(url, limit)
        finally:
            _last[host] = time.time()
    return _orig_get(url, limit)


emblem._get = _throttled_get
_get = _throttled_get

# 種類 → (最少, 目標, 最大)。target が None のものは who（メンバーの人数など）に合わせる
RULES = {
    "person": (3, 6, 10),
    "group": (3, None, 10),
    "character": (3, 6, 10),
    "brand": (1, 1, 1),
    "topic": (2, 3, 5),
}
KIND_BY_TYPE = {"anime": "character", "game": "character", "show": "character",
                "event": "person", "product": "brand", "category": "topic"}
KIND_JA = {"person": "本人", "group": "グループ", "character": "キャラ", "brand": "ブランド", "topic": "主題"}
TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/{}.svg"
SKIP_NAMES = re.compile(r"logo|icon|signature|flag|map|symbol|commons-|question_book|edit-clear|wikiquote|wikidata|"
                        r"disambig|stub|portal|crystal_clear|ambox|nuvola|folder|sprite|button|badge|banner|\.svg$", re.I)
WIKI_LANGS = ("en", "ja", "zh", "ko")


def load_items():
    import yaml
    return yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]


def kind_of(item):
    """emblem_kind を書いていればそれ。なければ type から推定（アニメ・ゲーム・ドラマ＝キャラ、event＝本人、product＝ブランド、category＝主題）。"""
    k = item.get("emblem_kind")
    return k if k in RULES else KIND_BY_TYPE.get(item.get("type"), "topic")


def rule(item):
    """→ (種類, 最少, 目標, 最大)。"""
    kind = kind_of(item)
    lo, target, hi = RULES[kind]
    hi = min(10, int(item.get("emblem_max") or hi))
    who = item.get("emblem_who") or []
    if target is None:
        target = max(lo, min(hi, len(who) or 5))
    elif who and kind in ("character", "group"):   # 対象を名前で挙げたものは、その全員が目標
        target = min(len(who), hi)
    return kind, min(lo, hi, target), min(target, hi), hi


def status(item):
    """→ {kind, have, lo, target, hi, state}。state：ok（目標に届いている）/ low（足りない）/ none（0 枚）。
    emblem_skip は「足りている」の理由にならない（種類ごとの最後の砦まで試して初めて 0 枚が許される）。"""
    kind, lo, target, hi = rule(item)
    have = len(item.get("emblem") or []) if isinstance(item.get("emblem"), list) else 0
    state = "ok" if have >= target else ("none" if have == 0 else "low")
    return {"name": item["name"], "kind": kind, "have": have, "lo": lo, "target": target, "hi": hi, "state": state,
            "skip": bool(item.get("emblem_skip"))}


def audit(items=None):
    """全関注項の状況。足りない順（0 枚 → 足りない → 目標どおり）。"""
    rows = [status(i) for i in (items if items is not None else load_items())]
    order = {"none": 0, "low": 1, "ok": 2}
    return sorted(rows, key=lambda r: (order[r["state"]], r["have"] - r["target"]))


# ---------------------------------------------------------------- 候補の集め方
_CACHE = pathlib.Path("/tmp/wishlist-emblem/cache")


def _json(url, limit=3_000_000):
    """API の応答は /tmp にキャッシュ（Wikipedia の 429 を避ける。やり直しも速い）。"""
    import hashlib
    f = _CACHE / (hashlib.md5(url.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    data = json.loads(_get(url, limit))
    _CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def relevant(title, subject):
    """ファイル名・記事名に対象の名前が入っているか（ロゴ・主題の画像用。顔がない画像は名前で確かめるしかない）。"""
    t = re.sub(r"[\W_]+", "", title.lower())
    toks = [x for x in re.split(r"[\s/・（）()]+", subject.lower()) if len(x) >= 2]
    return any(re.sub(r"[\W_]+", "", x) in t for x in toks) if toks else True


def anilist_names(media_id, n):
    names = emblem.anilist_main(media_id, n)
    return names


def wikipedia_title(lang, query):
    """言語版 Wikipedia で query を検索して最初の記事名。なければ None。"""
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"})
    hits = _json(f"https://{lang}.wikipedia.org/w/api.php?{q}")["query"]["search"]
    return hits[0]["title"] if hits else None


def _files_info(api, titles, width=500):
    out = []
    for i in range(0, len(titles), 30):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles[i:i + 30]), "prop": "imageinfo",
                                    "iiprop": "url|size|extmetadata", "iiurlwidth": width, "format": "json"})
        for p in _json(f"{api}?{q}", 4_000_000)["query"]["pages"].values():
            info = (p.get("imageinfo") or [{}])[0]
            if info.get("url") and info.get("width", 0) >= 300 and info.get("height", 0) >= 300:
                lic = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "")
                out.append({"title": p["title"], "image": info.get("thumburl") or info["url"],
                            "page": info.get("descriptionurl", ""), "license": lic,
                            "area": info["width"] * info["height"]})
    return out


def wikipedia_photos(subject, langs=WIKI_LANGS, limit=10, titles=None, extra=True, query=None):
    """本人・メンバー・ロゴの記事に載っている写真（Wikipedia 各言語版）。titles は {lang: 記事名}。
    extra=False は記事の代表画像だけ（メンバー・キャラ 1 人 1 枚のとき。API の呼び出しが 1/3 で済む）。"""
    found = []
    for lang in langs:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        title = (titles or {}).get(lang) or wikipedia_title(lang, query or subject)
        if not title:
            continue
        try:
            src, page = emblem.page_image(api, title)
            found.append({"title": title, "image": small_url(src), "page": page, "license": "", "area": 10 ** 9,
                          "anchor": True})   # 記事の代表画像（本人の確認の基準）
        except Exception:
            pass
        if not extra:
            if found:
                break
            continue
        q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "images", "imlimit": 60, "format": "json", "redirects": 1})
        pg = next(iter(_json(f"{api}?{q}")["query"]["pages"].values()))
        files = [x["title"] for x in pg.get("images", []) if re.search(r"\.(jpe?g|png|webp)$", x["title"], re.I)
                 and not SKIP_NAMES.search(x["title"])]
        found += _files_info(api, files[:40])
        if len(found) >= limit:
            break
        time.sleep(0.5)
    return found[:limit]


def commons_photos(subject, limit=10):
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": subject, "gsrnamespace": 6,
                                "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 500,
                                "format": "json"})
    pages = (_json(f"https://commons.wikimedia.org/w/api.php?{q}", 4_000_000).get("query") or {}).get("pages", {})
    out = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        if (not info.get("url") or not re.search(r"\.(jpe?g|png|webp)$", p["title"], re.I) or SKIP_NAMES.search(p["title"])
                or info.get("width", 0) < 300 or info.get("height", 0) < 300):
            continue
        lic = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "")
        out.append({"title": p["title"], "image": info.get("thumburl") or info["url"], "page": info.get("descriptionurl", ""),
                    "license": lic, "area": info["width"] * info["height"]})
    return sorted(out, key=lambda x: -x["area"])[:limit]


def wikidata_images(query, props=("P154", "P18"), limit=3):
    """Wikidata の主題から、公式ロゴ（P154）と代表画像（P18）。Commons のファイルなのでライセンス付き。
    Commons の全文検索より、主題を取り違えにくく、429 にもなりにくい。"""
    out = []
    for lang in ("en", "ja", "zh"):
        q = urllib.parse.urlencode({"action": "wbsearchentities", "search": query, "language": lang, "uselang": lang,
                                    "format": "json", "limit": 2})
        hits = _json(f"https://www.wikidata.org/w/api.php?{q}").get("search", [])
        for h in hits[:1]:
            q2 = urllib.parse.urlencode({"action": "wbgetentities", "ids": h["id"], "props": "claims", "format": "json"})
            claims = _json(f"https://www.wikidata.org/w/api.php?{q2}", 4_000_000)["entities"][h["id"]].get("claims", {})
            for prop in props:
                for c in claims.get(prop, [])[:limit]:
                    fn = (c.get("mainsnak", {}).get("datavalue") or {}).get("value")
                    if isinstance(fn, str):
                        out.append({"title": fn, "image": "https://commons.wikimedia.org/wiki/Special:FilePath/"
                                    + urllib.parse.quote(fn) + "?width=500",
                                    "page": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(fn.replace(" ", "_")),
                                    "license": f"Wikidata {prop}", "area": 0, "prop": prop})
        if out:
            break
    return out


def site_images(url, limit=8, logo=False):
    """公式サイトの og:image と、本文の大きそうな画像。logo=True はロゴ（名前に logo が入る画像・apple-touch-icon）を探す。"""
    html = _get(url, 1_500_000).decode("utf-8", "replace")
    found = []
    if logo:
        for m in re.finditer(r'(?:src|href|content)=["\']([^"\']*(?:logo|apple-touch-icon)[^"\']*\.(?:png|svg|webp|jpe?g)[^"\']*)', html, re.I):
            found.append(m.group(1))
        out, seen = [], set()
        for u in found:
            u = urllib.parse.urljoin(url, u.replace("&amp;", "&"))
            if u.startswith("http") and u not in seen:
                seen.add(u)
                out.append({"title": "公式サイトのロゴ", "image": u, "page": url, "license": "公式", "area": 0})
        return out[:limit]
    for m in re.finditer(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', html, re.I):
        found.append(m.group(1))
    for m in re.finditer(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', html, re.I):
        found.append(m.group(1))
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+\.(?:jpe?g|png|webp)[^"\']*)', html, re.I):
        found.append(m.group(1))
    out, seen = [], set()
    for u in found:
        u = urllib.parse.urljoin(url, u.replace("&amp;", "&"))
        if u.startswith("http") and u not in seen and not SKIP_NAMES.search(u.split("?")[0].rsplit("/", 1)[-1]):
            seen.add(u)
            out.append({"title": "公式サイト", "image": u, "page": url, "license": "公式", "area": 0})
    return out[:limit]


def parse_bing(html, n=8):
    """Bing 画像検索の結果ページから元画像の網址（murl）を取り出す。"""
    out = []
    for m in re.finditer(r"murl&quot;:&quot;(https?://[^&]+?)&quot;", html):
        u = m.group(1)
        if u not in [x["image"] for x in out] and not re.search(r"[\s\x00-\x1f]", u) and re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I):
            out.append({"title": "Web 画像検索", "image": u, "page": "", "license": "要確認", "area": 0})
        if len(out) >= n:
            break
    return out


def bing_images(query, n=8):
    html = _get("https://www.bing.com/images/search?" + urllib.parse.urlencode({"q": query, "form": "HDRSC2", "first": 1}),
                2_500_000).decode("utf-8", "replace")
    return parse_bing(html, n)


def news_images(item_name, subject, anywhere=False, limit=12, days=14):
    """集めた新聞（inbox）の配図：その関注項の記事で、題名に対象の名前が入っているもの（anywhere=True なら名前は問わない）。
    人物の別の写真・刚出道のグループの写真は、Wiki よりここのほうが新しくて多い。"""
    out, seen = [], set()
    key = subject.lower().replace(" ", "")
    for path in sorted((ROOT / "inbox").glob("????-??-??.json"), reverse=True)[:days]:
        try:
            blocks = json.loads(path.read_text(encoding="utf-8")).get("items", [])
        except Exception:
            continue
        for b in blocks:
            if b.get("name") != item_name:
                continue
            for e in b.get("entries", []):
                u = e.get("image") or ""
                if not u.startswith("http") or u in seen:
                    continue
                if re.match(r"^https://(www\.)?bing\.com/th\?", u):
                    u = re.sub(r"&(amp;)?[wh]=\d+", "", u)
                if anywhere or key in (e.get("title") or "").lower().replace(" ", ""):
                    seen.add(u)
                    out.append({"title": e.get("source", "新聞"), "image": u, "page": e.get("url", ""),
                                "license": "新聞の配図", "area": 0})
                if len(out) >= limit:
                    return out
    return out


def twemoji(emoji):
    """絵文字（🎾）か、Twemoji のコード（1f3be、複数なら 1f3c3-200d-2640 のように -）。"""
    if re.fullmatch(r"[0-9a-fA-F]{2,6}(-[0-9a-fA-F]{2,6})*", emoji):
        code, emoji = emoji.lower(), chr(int(emoji.split("-")[0], 16))
    else:
        code = "-".join(f"{ord(c):x}" for c in emoji if ord(c) != 0xFE0F)
    return {"title": f"Twemoji {emoji}", "image": TWEMOJI.format(code), "page": "https://github.com/jdecked/twemoji",
            "license": "CC-BY 4.0", "area": 0}


def subjects(item, kind, hi):
    """収集する対象の名前。emblem_who（メンバー・キャラの名前）があればそれ、なければ種類ごとの決め方。"""
    who = list(item.get("emblem_who") or [])
    if who:
        return who[:hi]
    if kind == "character" and item.get("anilist_id"):
        return anilist_names(item["anilist_id"], hi)
    return [item.get("emblem_subject") or item["name"]]


def wiki_titles(item):
    """items.yaml の wiki: ['en:Illit', 'ja:ILLIT'] → {lang: 記事名}。"""
    out = {}
    for w in item.get("wiki") or []:
        lang, _, title = str(w).partition(":")
        if title:
            out[lang] = title
    return out


def gather(item, log=print):
    """種類に合わせて、上の順で候補を集める。→ [{subject, image, page, why, source, license, kind}]。"""
    kind, lo, target, hi = rule(item)
    name = item["name"]
    cands = []

    def add(subject, rows, source, why, per=None):
        for r in rows[:per] if per else rows:
            cands.append({"subject": subject, "image": r["image"], "page": r.get("page", ""), "source": source,
                          "why": why, "license": r.get("license", ""), "anchor": bool(r.get("anchor")), "title": r.get("title", "")})

    for u in item.get("emblem_urls") or []:
        cands.append({"subject": u.get("subject", name), "image": u["image"], "page": u.get("page", ""), "source": "直接指定",
                      "why": u.get("why", "items.yaml に直接書いた画像"), "license": ""})
    if kind in ("brand", "topic"):
        subj = item.get("emblem_subject") or name
        try:
            add(f"{subj} のロゴ", wikidata_images(subj, ("P154",)), "Wikidata", "ブランドの顔（公式ロゴ）", 2)
        except Exception as e:
            log(f"  [Wikidata] {e}")
        try:
            add(f"{subj} のロゴ", [r for r in commons_photos(f"{subj} logo", 12) if relevant(r["title"], subj)],
                "Wikimedia Commons", "ブランドの顔（公式ロゴ）", 3)
        except Exception as e:
            log(f"  [Commons] {e}")
        if item.get("site"):
            try:
                add(f"{subj} のロゴ", site_images(item["site"], 4, logo=True), "公式サイト", "公式サイトのロゴ", 2)
                if kind == "topic":
                    add(subj, site_images(item["site"], 6), "公式サイト", "公式サイトの画像")
            except Exception as e:
                log(f"  [公式サイト] {e}")
        for lang, title in wiki_titles(item).items():
            try:
                add(title, wikipedia_photos(title, (lang,), 6, {lang: title}), f"Wikipedia({lang})", "主題の記事に載っている画像", 4)
            except Exception as e:
                log(f"  [Wikipedia {lang}] {e}")
        if kind == "topic":
            try:
                add(subj, wikidata_images(subj, ("P154", "P18")), "Wikidata", "主題を表す画像", 3)
            except Exception as e:
                log(f"  [Wikidata] {e}")
            try:
                add(subj, bing_images(f"{subj} 公式 画像", 6), "Web 画像検索", "主題を表す画像（要確認）", 3)
            except Exception as e:
                log(f"  [Web] {e}")
        for emoji in (item.get("emblem_icon") or "").split():
            cands.append({**twemoji(emoji), "subject": f"{emoji} アイコン", "source": "Twemoji", "why": "版面の主題を表す物"})
        return _dedupe(cands)

    who = subjects(item, kind, hi)
    log(f"  対象（{len(who)}）：{'、'.join(who)}")
    titles = wiki_titles(item)
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    for subj in who:
        got = 0
        if kind == "character" and api:
            try:
                r = emblem.page_image(api, subj)
                cands.append({"subject": subj, "image": small_url(r[0]), "page": r[1], "source": "Fandom", "why": f"{subj}（Fandom のページ）", "license": ""})
                got += 1
            except Exception as e:
                log(f"  [Fandom] {subj}：{e}")
        if kind == "person":
            try:
                rows = wikidata_images(subj, ("P18",), 2)
                for r in rows[:1]:
                    r["anchor"] = True
                add(subj, rows, "Wikidata", f"{subj}（Wikidata の代表画像）")
                got += len(rows)
            except Exception as e:
                log(f"  [Wikidata] {subj}：{e}")
        if got == 0 or kind == "person":
            try:
                one_person = len(who) == 1
                rows = wikipedia_photos(subj, WIKI_LANGS, 10 if kind == "person" else 3, titles if one_person else None,
                                        extra=(kind == "person"), query=f"{subj} {name}" if kind == "group" else None)
                add(subj, rows, "Wikipedia", f"{subj}（Wikipedia の記事の画像）", None if kind == "person" else 2)
                got += len(rows)
            except Exception as e:
                log(f"  [Wikipedia] {subj}：{e}")
        if got < (6 if kind == "person" else 1):
            try:
                rows = commons_photos(subj if len(who) > 1 else f"{subj}", 8 if kind == "person" else 3)
                add(subj, rows, "Wikimedia Commons", f"{subj}（Commons の写真）")
                got += len(rows)
            except Exception as e:
                log(f"  [Commons] {subj}：{e}")
        if got < (6 if kind == "person" else 1) or item.get("_web"):
            try:
                rows = news_images(name, subj, anywhere=(kind == "person" and len(who) == 1), limit=12 if kind == "person" else 3)
                add(subj, rows, "新聞の配図", f"{subj}（集めた新聞の写真）")
                got += len(rows)
            except Exception as e:
                log(f"  [新聞] {e}")
        if got < (4 if kind == "person" else 1) and item.get("site") and len(who) == 1:
            try:
                add(subj, site_images(item["site"], 8), "公式サイト", "公式サイトの画像")
            except Exception as e:
                log(f"  [公式サイト] {e}")
        if got < (4 if kind == "person" else 1) or item.get("_web"):
            try:
                q = item.get("_query") or (f"{subj} {name}" if subj != name else f"{subj} 公式")
                add(subj, bing_images(q, 8 if kind == "person" else 4), "Web 画像検索", f"{subj}（Web 画像検索・要確認）")
            except Exception as e:
                log(f"  [Web] {subj}：{e}")
    return _dedupe(cands)


def _hash(img):
    g = img.convert("L").resize((9, 8))
    px = list(g.get_flattened_data() if hasattr(g, "get_flattened_data") else g.getdata())
    return int("".join("1" if px[r * 9 + c] > px[r * 9 + c + 1] else "0" for r in range(8) for c in range(8)), 2)


def _dedupe(cands):
    """同じ画像（網址違い）を落とす。"""
    out, seen = [], set()
    for c in cands:
        if c["image"] in seen:
            continue
        seen.add(c["image"])
        out.append(c)
    return out


def check(cands, log=print, need_face=False):
    """ダウンロードして使えるか確かめる（短辺 160px 以上・開ける）。
    need_face（人物・グループ）：顔の特徴量で「その人」かを確かめる（face_id）。顔がない写真（観客席・絵画・物）と、
    記事の代表画像と別人の写真を落とす。モデルが使えないときは顔の有無だけ（haar）に下げる。
    最後に、似すぎた画像（平均ハッシュ）を落とす。"""
    dl = []
    for c in cands:
        try:
            data = _get(c["image"], 6_000_000)
            if c["image"].lower().split("?")[0].endswith(".svg"):
                dl.append({**c, "shape": "icon" if c["source"] == "Twemoji" else "logo", "_img": None})
                continue
            shape, key, img = inspect(data)
            from PIL import ImageStat
            if ImageStat.Stat(img.convert("L")).stddev[0] < 6:   # 真っ白・真っ黒のほぼ一色の画像
                log(f"  [白紙] {c['subject']}（{c['source']}）")
                continue
            dl.append({**c, "shape": shape, "_img": img})
        except Exception as e:
            log(f"  [使えない] {c['subject']}（{c['source']}）：{str(e)[:50]}")
    if need_face:
        by = {}
        for i, c in enumerate(dl):
            by.setdefault(c["subject"], []).append(i)
        drop = set()
        for subj, ids in by.items():
            test = [i for i in ids if dl[i]["source"] != "直接指定"]
            feats = [face_id.main_face(dl[i]["_img"]) for i in test]
            anchor = next((k for k, i in enumerate(test) if dl[i].get("anchor")), None)
            keep = face_id.same_person(feats, anchor)
            if keep is None:   # モデルなし：顔の有無だけ
                log("  [本人確認なし] 顔モデルが使えないので、顔があるかだけ確かめた")
                keep = {k for k, i in enumerate(test) if emblem.face_box(dl[i]["_img"].convert("RGB"))}
            for k, i in enumerate(test):
                if k not in keep:
                    drop.add(i)
                    log(f"  [別人・顔なし] {subj}（{dl[i]['source']}）")
        dl = [c for i, c in enumerate(dl) if i not in drop]
    good, hashes = [], []
    for c in dl:
        if c["_img"] is not None:
            h = _hash(c["_img"])
            if any(bin(h ^ x).count("1") <= 4 for x in hashes):
                continue
            hashes.append(h)
        good.append(c)
    return good


def sheet(good, path):
    """番号付きの候補一覧（AI が目で選ぶ用）。"""
    from PIL import Image, ImageDraw
    cols, cell = 6, 220
    rows = (len(good) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, max(1, rows) * (cell + 34)), "#EDEBE6")
    d = ImageDraw.Draw(im)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 13)
    except Exception:
        font = None
    for i, c in enumerate(good):
        x, y = (i % cols) * cell, (i // cols) * (cell + 34)
        if c.get("_img") is not None:
            t = c["_img"].convert("RGBA")
            t.thumbnail((cell - 8, cell - 8))
            bg = Image.new("RGBA", t.size, "#FFFFFF")
            bg.alpha_composite(t)
            im.paste(bg.convert("RGB"), (x + 4, y + 4))
        d.rectangle([x, y + cell - 18, x + 34, y + cell + 12], fill="#1A1C22")
        d.text((x + 6, y + cell - 10), str(i + 1), fill="#FFD23F")
        d.text((x + 40, y + cell - 12), f"{c['subject'][:22]}", fill="#1A1C22", font=font)
        d.text((x + 40, y + cell + 2), f"{c['source'][:14]}·{c['shape']}", fill="#4A4538")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=88)
    return path


# ---------------------------------------------------------------- 書き込み
def _drop_skip(name):
    path = ROOT / "items.yaml"
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("  - name:")), len(lines))
    lines[start + 1:end] = [l for l in lines[start + 1:end] if not l.startswith("    emblem_skip:")]
    path.write_text("\n".join(lines), encoding="utf-8")


def commit(item, good, picks, replace=False, log=print):
    """選んだ番号を items.yaml に書く。人物・キャラは続けて抠图と顔の大きさをそろえる。"""
    kind, lo, target, hi = rule(item)
    name = item["name"]
    chosen, count = [], {}
    for n in picks:
        c = good[n - 1]
        count[c["subject"]] = count.get(c["subject"], 0) + 1
        if sum(1 for m in picks if good[m - 1]["subject"] == c["subject"]) > 1:   # 同じ人の別の写真は名前を分ける（保存ファイル名が重ならないように）
            c = {**c, "subject": f"{c['subject']} {count[c['subject']]}"}
        chosen.append({"subject": c["subject"], "why": c["why"], "image": c["image"], "page": c["page"], "shape": c["shape"]})
    old = [] if replace else [x for x in (item.get("emblem") or []) if isinstance(x, dict)]
    seen = {(x["subject"], x["image"]) for x in old}
    merged = old + [x for x in chosen if (x["subject"], x["image"]) not in seen]
    merged = merged[:hi]
    _drop_skip(name)
    emblem.write_item(name, merged, None)
    log(f"→ 「{name}」に {len(merged)} 枚（目標 {target}、最大 {hi}）")
    if kind in ("person", "group", "character"):
        emblem.cut_all(name, kind != "person")
        emblem.fit_all(name)
    return merged


def _sheet_path(name):
    import hashlib
    slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-") or hashlib.md5(name.encode()).hexdigest()[:8]
    return pathlib.Path("/tmp/wishlist-emblem") / f"{slug}.jpg"


def run_item(item, auto=False, picks=None, log=print):
    log(f"■ {item['name']}（{KIND_JA[kind_of(item)]}）")
    cands = gather(item, log)
    good = check(cands, log, need_face=kind_of(item) in ("person", "group"))
    out = _sheet_path(item["name"])
    sheet(good, out)
    (out.with_suffix(".json")).write_text(json.dumps([{k: v for k, v in c.items() if k != "_img"} for c in good],
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  候補 {len(good)} 枚 → {out}")
    return good, out


def auto_pick(item, good):
    """自動で選ぶ：Web 画像検索は最後の手段。対象ごとに 1 枚（本人は別の写真を目標まで）。"""
    kind, lo, target, hi = rule(item)
    order = {"直接指定": 0, "Fandom": 1, "Wikipedia": 2, "Wikimedia Commons": 3, "新聞の配図": 4, "公式サイト": 5, "Twemoji": 6, "Web 画像検索": 7}
    idx = sorted(range(len(good)), key=lambda i: (order.get(good[i]["source"], 9), i))
    picks, seen = [], {}
    per = 99 if kind in ("person", "topic", "brand") else 1
    for i in idx:
        s = good[i]["subject"]
        if seen.get(s, 0) >= per:
            continue
        seen[s] = seen.get(s, 0) + 1
        picks.append(i + 1)
        if len(picks) >= target:
            break
    return picks


def main():
    ap = argparse.ArgumentParser(description="小元素の自動補完")
    ap.add_argument("name", nargs="?", help="items.yaml の関注項の名前")
    ap.add_argument("--audit", action="store_true", help="全関注項の状況を表示")
    ap.add_argument("--commit", help="候補一覧の番号（カンマ区切り）を items.yaml に書く")
    ap.add_argument("--replace", action="store_true", help="今ある小元素を置き換える")
    ap.add_argument("--web", action="store_true", help="Web 画像検索も必ず使う（足りないとき）")
    ap.add_argument("--query", help="Web 画像検索の言葉（既定は「対象 作品名」）")
    ap.add_argument("--auto", action="store_true", help="足りない関注項を決まった順で全部自動で埋める")
    a = ap.parse_args()
    items = load_items()
    if a.audit:
        for r in audit(items):
            mark = {"ok": "✓", "low": "△", "none": "✗"}[r["state"]]
            print(f"{mark} {r['name']:<24} {KIND_JA[r['kind']]:<6} {r['have']}/{r['target']}（最大 {r['hi']}）{' [skip]' if r['skip'] else ''}")
        return
    if a.auto:
        for r in audit(items):
            if r["state"] == "ok":
                continue
            item = next(i for i in items if i["name"] == r["name"])
            good, _ = run_item(item)
            picks = auto_pick(item, good)
            if picks:
                commit(item, good, picks)
        return
    if not a.name:
        ap.error("名前か --audit / --auto が要る")
    item = next((i for i in items if i["name"] == a.name), None)
    if not item:
        ap.error(f"items.yaml に「{a.name}」がない")
    if a.commit:   # 一覧を作ったときの候補（json）から選ぶ。集め直すと順番が変わるので
        jp = _sheet_path(item["name"]).with_suffix(".json")
        good = json.loads(jp.read_text(encoding="utf-8"))
        for c in good:
            c.setdefault("_img", None)
        commit(item, good, [int(x) for x in a.commit.split(",")], a.replace)
    else:
        item = {**item, "_web": a.web or bool(a.query), "_query": a.query}
        run_item(item)


if __name__ == "__main__":
    main()
