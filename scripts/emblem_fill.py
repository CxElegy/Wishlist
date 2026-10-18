"""小元素の自動補完：どの関注項も「その種類にふさわしい枚数」の小元素を持つようにする。

emblem.py は「Wiki を 1 つ指定して取る」道具で、種類ごとの枚数も、Wiki がない場合の代わりの取り方もなかった。
そのため、(1) 人が API とページ名を毎回決める (2) Wiki にない主題（ブランド・刚出道のグループ・本人の別の写真）は取れず
emblem_skip で逃げる (3) 何枚あれば足りるかの基準がなく、1 枚のまま放置される、という穴ができた。
ここでは「種類 → 目標の枚数 → 取り方の順番（フォールバック）」を決め、足りないものを自動で見つけて埋める。

種類（items.yaml の emblem_kind。なければ type から推定）と目標の枚数：
  上限は「その内容の主要な要素の数」で決まる（1 要素 1 枚、CEIL まで）。キャラの多いゲームは多く、メンバー 5 人のグループは 5 枚。
  要素の数は emblem_pool（roster() が AniList の主役・Wiki の分類 emblem_category から数えて書く）・emblem_who・emblem_examples の多いほう。
  person     本人の別の写真        目標 6（最少 3、最大 10）
  group      メンバー全員          目標 = メンバー数（最大 20）
  character  主要なキャラ          目標 = 主要キャラの数（最大 20。わからないときは 6）
  brand      公式ロゴ              1
  topic      主題の下の一段        目標 = 代表作の数（最大 10。ないときは 3）：代表作 → ロゴ・トロフィー・場所 → 絵文字アイコン

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
import os
import pathlib
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emblem  # noqa: E402
import face_id  # noqa: E402
import runlog  # noqa: E402
from emblem import ROOT, inspect, small_url  # noqa: E402

WRITE_LOCK = threading.RLock()   # items.yaml・docs/emblems への書き込みと抠图（rembg）は 1 本ずつ
_face_lock = threading.Lock()    # 顔の検出・特徴量（OpenCV のモデルは 1 つを共有するので順番に）
_deadline = [None]   # 後台の時間の予算の締め切り（time.time()）。過ぎたら集めるのをやめる


class OutOfTime(Exception):
    pass


def _check_time():
    if _deadline[0] is not None and time.time() > _deadline[0]:
        raise OutOfTime("時間の予算を使い切った")


_get = emblem._get   # Wikimedia の間隔・取り直し・休み・キャッシュは wikihttp.get（emblem._get から呼ぶ）

# 種類 → (最少, 目標, 最大)。target が None のものは who（メンバーの人数など）に合わせる
RULES = {
    "person": (3, 6, 10),
    "group": (3, None, 10),
    "character": (3, 6, 10),
    "brand": (1, 1, 1),
    "topic": (2, 3, 5),
}
# 主要な要素の数で決まる上限の天井。キャラ・メンバーは主要な要素を全部（绝区零 60 人なら 60 枚、用户定的）。
# 一度に全部は集めず、1 回の後台で STEP 人ずつ（まだいない人から、回ごとにずらして）足していく
CEIL = {"person": 10, "group": 50, "character": 200, "brand": 1, "topic": 10}
STEP = 10
KIND_BY_TYPE = {"anime": "character", "game": "character", "show": "character",
                "event": "person", "product": "brand", "category": "topic"}
KIND_JA = {"person": "本人", "group": "グループ", "character": "キャラ", "brand": "ブランド", "topic": "主題"}
WEB = "Web 画像検索"
EXAMPLE = "代表作"   # 主題（ジャンル・カテゴリ）の下の一段：emblem_examples に書いた作品・ブランド・選手
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


def pool(item):
    """その内容の主要な要素の数（キャラ・メンバー・代表作）。上限はこれで決まる。わからなければ None。
    emblem_pool（roster() が数えて書いた数）・emblem_who（集める名前）・emblem_examples（主題の代表作）の多いほう。
    本人（別の写真）とブランド（ロゴ 1 枚）は要素を数えるものではないので None。"""
    kind = kind_of(item)
    if kind in ("person", "brand"):
        return None
    n = max(int(item.get("emblem_pool") or 0), len(item.get("emblem_who") or []))
    if kind == "topic":
        n = max(n, len(item.get("emblem_examples") or []))
    return n or None


def rule(item):
    """→ (種類, 最少, 目標, 最大)。最大 = 主要な要素の数（CEIL まで）。要素の数がわからないときは RULES の既定。
    emblem_max を書いたものはそれが最大（ぐでたま：キャラが 1 体だけなので別の場面 3 枚）。"""
    kind = kind_of(item)
    lo, target, hi = RULES[kind]
    n = pool(item)
    if n:   # 1 要素 1 枚：キャラ 60 人のゲームは 20（天井）、2 人しかいない作品は 2
        hi = target = min(CEIL[kind], n)
    if item.get("emblem_max"):
        hi = min(CEIL[kind] if kind != "brand" else 10, int(item["emblem_max"]))
    target = hi if target is None else target
    who = item.get("emblem_who") or []
    if n and who and kind in ("character", "group"):   # 1 人 1 枚なので、名前を挙げた人数より多くは集められない（足りない名前は roster が足す）
        target = min(target, len(who))
    return kind, min(lo, hi, target), min(target, hi), hi


def status(item):
    """→ {kind, have, lo, target, hi, state}。state：ok（目標に届いている）/ low（足りない）/ none（0 枚）。
    emblem_skip は「足りている」の理由にならない（種類ごとの最後の砦まで試して初めて 0 枚が許される）。"""
    kind, lo, target, hi = rule(item)
    ems = item.get("emblem") if isinstance(item.get("emblem"), list) else []
    if live_action(item):   # 実写の作品は役の姿・作品の画像だけを数える（出演者の生活の写真は替える対象）
        ems = [x for x in ems if isinstance(x, dict) and is_role_image(x)]
    have = len(ems)
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
    tmp = f.with_suffix(f".{threading.get_ident()}.tmp")   # 並列で同じ網址を書いても壊れないように
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    return data


def relevant(title, subject):
    """ファイル名・記事名に対象の名前が入っているか（ロゴ・主題の画像用。顔がない画像は名前で確かめるしかない）。"""
    t = re.sub(r"[\W_]+", "", title.lower())
    toks = [x for x in re.split(r"[\s/・（）()]+", subject.lower()) if len(x) >= 2]
    return any(re.sub(r"[\W_]+", "", x) in t for x in toks) if toks else True


def same_name(page, name):
    """検索で当たった記事名が、その名前の記事か（記事名に名前が丸ごと入っている。「Aion 2」→「Aion 2」「Aion 2 (video game)」）。"""
    norm = lambda x: re.sub(r"[\W_]+", "", x.lower())
    return bool(norm(name)) and norm(name) in norm(page)


def langlinks(lang, title):
    """その記事のほかの言語版の記事名 {lang: 記事名}（WIKI_LANGS のうち、あるものだけ）。"""
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "langlinks", "lllimit": 500,
                                "format": "json", "redirects": 1})
    try:
        pg = next(iter(_json(f"https://{lang}.wikipedia.org/w/api.php?{q}")["query"]["pages"].values()))
    except Exception:
        return {}
    return {l["lang"]: l["*"] for l in pg.get("langlinks", []) if l["lang"] in WIKI_LANGS}


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
    for i in range(0, len(titles), 50):   # API は titles を | で 50 件まで 1 回に
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "imageinfo",
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


def parse_youtube(html):
    """YouTube の検索結果ページ（ytInitialData）→ [(videoId, 題名)]。"""
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
    if not m:
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if isinstance(v, dict) and v.get("videoId"):
                out.append((v["videoId"], "".join(r.get("text", "") for r in (v.get("title") or {}).get("runs", []))))
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(json.loads(m.group(1)))
    return out


YT_FRAMES = (2, 1, 3)
# 作品の外の動画（インタビュー・ポッドキャスト・試写会・レッドカーペット・メイキング・リアクション）：役の姿ではない
YT_OFFSCREEN = re.compile(r"interview|podcast|premiere|red ?carpet|behind the scenes|bts|making of|react|q ?& ?a|panel|comic-?con|"
                          r"talks?|explains|breakdown|press|junket|インタビュー|舞台挨拶|인터뷰|采访|专访", re.I)   # 真ん中の場面から
YT_SOLO = re.compile(r"fancam|직캠|focus|individual|teaser|profile|close.?up|個人|ソロ", re.I)


def youtube_images(group, subject, limit=4, scene=False):
    """YouTube の動画の場面（自動で取られた 3 枚）。グループのメンバー・出演者のように Commons に写真がない人用。
    検索は「グループ名 + 名前」、題名に名前とグループ名の両方があるものだけ（名前が普通の単語でも別物に当たらない）。
    1 人を映す動画（直캠・fancam・teaser）を先に。本人かどうかは check の顔の規則で確かめる。"""
    q = f"{group} {subject}".strip()
    html = _get("https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q, "hl": "en"}),
                3_000_000).decode("utf-8", "replace")
    rows = [(v, t) for v, t in parse_youtube(html) if relevant(t, subject) and (not group or relevant(t, group))]
    if scene:   # 作品の場面だけ：インタビュー・試写会などの動画は役の姿ではない
        rows = [(v, t) for v, t in rows if not YT_OFFSCREEN.search(t)]
    rows.sort(key=lambda r: 0 if YT_SOLO.search(r[1]) else 1)
    # 投稿者が作ったサムネイル（hq720）は題名の大きな字が載っていて、切り抜くと字が残る。YouTube が動画から自動で取った
    # 場面（hq1・hq2・hq3 = 動画の 25%・50%・75% のところ、480×360）を使う。字は載っていない
    return [{"title": t, "image": f"https://i.ytimg.com/vi/{v}/hq{k}.jpg", "page": f"https://www.youtube.com/watch?v={v}",
             "license": "YouTube の動画の場面"} for v, t in rows[:limit] for k in YT_FRAMES]


def news_images(item_name, subject, anywhere=False, limit=12, days=14, summary=False):
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
                text = (e.get("title") or "") + (" " + (e.get("summary") or "") if summary else "")
                if anywhere or key in text.lower().replace(" ", ""):
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
    if who and kind in ("character", "group"):   # まだ小元素のいない人から STEP 人。足りない人が多いときは回ごとにずらす（見つからない人で止まらない）
        have = {_base_subject(x.get("subject")) for x in item.get("emblem") or [] if isinstance(x, dict)}
        rest = [w for w in who[:hi] if w not in have]
        if len(rest) <= STEP:
            return rest or who[:1]
        k = int(time.time() // 3600) * STEP % len(rest)
        return (rest[k:] + rest[:k])[:STEP]
    if who:
        return who[:hi]
    if kind == "character" and item.get("anilist_id"):
        return anilist_names(item["anilist_id"], hi)
    return [item.get("emblem_subject") or item["name"]]


def roster(item, log=print):
    """主要な要素（キャラ）の名簿を数えて items.yaml に書く：emblem_pool（数）と、足りない分の emblem_who（名前、上位から）。
    数え方：emblem_category（Fandom などの分類。例：絶区零は Playable Agents、あつ森は Special characters）があればその人数、
    なければ anilist_id の主役（role MAIN）の人数。どちらもなければ何もしない（emblem_who の人数が要素の数）。
    → 数えた数か None。"""
    if kind_of(item) != "character":
        return None
    who = list(item.get("emblem_who") or [])
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    names, how = [], ""
    if item.get("emblem_category") and api:
        names = emblem.category_top(api, item["emblem_category"], 999)   # 物語の中心にいる（ほかのページから多く参照される）順
        how = f"分類「{item['emblem_category']}」の人数"
    elif item.get("anilist_id"):
        names = emblem.anilist_main(item["anilist_id"], 50)
        how = "AniList の主役（role MAIN）の人数"
    if not names:
        return None
    n = len(names)
    add = [x for x in names if x not in who][:max(0, min(CEIL["character"], n) - len(who))]
    with WRITE_LOCK:
        _set_field(item["name"], "emblem_pool", f"{n}   # 主要な要素の数＝小元素の上限（{how}、scripts/emblem_fill.py の roster）")
        if add:
            _set_field(item["name"], "emblem_who", json.dumps(who + add, ensure_ascii=False)
                       + "   # 集める対象（メンバー・キャラ・出演者）")
    log(f"  [名簿] {item['name']}：{how} {n} → 上限 {min(CEIL['character'], n)}、名前を {len(add)} 人足した")
    return n


def _set_field(name, key, value):
    """items.yaml のその関注項の「    key: …」の行を書き換える（なければ emblem_kind の下に足す）。"""
    path = ROOT / "items.yaml"
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("  - name:")), len(lines))
    row = f"    {key}: {value}"
    at = next((i for i in range(start + 1, end) if lines[i].startswith(f"    {key}:")), None)
    if at is not None:
        lines[at] = row
    else:
        k = next((i for i in range(start + 1, end) if lines[i].startswith("    emblem_kind:")), start)
        lines.insert(k + 1, row)
    path.write_text("\n".join(lines), encoding="utf-8")


def wiki_titles(item):
    """items.yaml の wiki: ['en:Illit', 'ja:ILLIT'] → {lang: 記事名}。"""
    out = {}
    for w in item.get("wiki") or []:
        lang, _, title = str(w).partition(":")
        if title:
            out[lang] = title
    return out


def _tracking(log, tried):
    """gather の log を包んで、エラーになった取り方も「試した」として tried に残す（[Wikidata] … の形のログから）。"""
    alias = {"Commons": "Wikimedia Commons", "新聞": "新聞の配図", "Web": "Web 画像検索"}

    def out(msg):
        m = re.match(r"\s*\[([^\]\s]+)", msg)
        if m and m.group(1) not in ("使えない", "白紙", "別人・顔なし", "本人確認なし"):
            tried.setdefault(alias.get(m.group(1), m.group(1)), 0)
        log(msg)
    return out


def gather(item, log=print, tried=None):
    """種類に合わせて、上の順で候補を集める。→ [{subject, image, page, why, source, license, kind}]。
    tried（dict）を渡すと、試した取り方ごとの候補数を書き込む（進捗の記録用）。"""
    kind, lo, target, hi = rule(item)
    name = item["name"]
    cands = []
    tried = {} if tried is None else tried
    log = _tracking(log, tried)

    def add(subject, rows, source, why, per=None):
        base = source.split("(")[0]
        tried[base] = tried.get(base, 0) + len(rows[:per] if per else rows)
        for r in rows[:per] if per else rows:
            cands.append({"subject": subject, "image": r["image"], "page": r.get("page", ""), "source": source,
                          "why": why, "license": r.get("license", ""), "anchor": bool(r.get("anchor")), "title": r.get("title", "")})

    for u in item.get("emblem_urls") or []:
        tried["直接指定"] = tried.get("直接指定", 0) + 1
        cands.append({"subject": u.get("subject", name), "image": u["image"], "page": u.get("page", ""), "source": "直接指定",
                      "why": u.get("why", "items.yaml に直接書いた画像"), "license": ""})
    def add_example(ex):
        """主題の下の一段（ジャンルなら代表作、競技なら有名な選手・大会）：その作品のロゴと、記事の代表画像（キービジュアル・パッケージ）。
        ex は「en:Blade & Soul」（記事名を言語つきで指定）か名前だけ。"""
        lang, _, title = ex.partition(":") if re.match(r"^[a-z]{2}:", ex) else ("", "", ex)
        try:
            add(title, [r for r in wikidata_images(title, ("P154",), 1) if relevant(r["title"], title)],
                EXAMPLE + "(Wikidata)", f"この主題の代表作「{title}」のロゴ", 1)
        except Exception as e:
            log(f"  [代表作] {title}：{e}")
        # 指定の言語版に画像がなければ、同じ記事のほかの言語版（言語間リンクでたどる。検索だと別の記事に当たる：
        # 「Odin: Valhalla Rising」で FF13、「Chrono Odyssey」で人物の記事が出た）
        pages = {lang: title, **langlinks(lang, title)} if lang else {}
        for lg in [lang] + [x for x in WIKI_LANGS if x != lang] if lang else WIKI_LANGS:
            try:
                page = pages.get(lg) if lang else wikipedia_title(lg, title)
                if not page or not (lang or same_name(page, title)):
                    continue
                src, url = emblem.page_image(f"https://{lg}.wikipedia.org/w/api.php", page, any_license=True)
                add(title, [{"image": small_url(src), "page": url, "title": page}],
                    EXAMPLE + "(Wikipedia)", f"この主題の代表作「{title}」の記事の画像（キービジュアル・パッケージ）")
                break
            except Exception as e:
                log(f"  [代表作] {title}（{lg}）：{e}")

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
                if not item.get("_no_web"):
                    add(subj, bing_images(f"{subj} 公式 画像", 6), "Web 画像検索", "主題を表す画像（要確認）", 3)
            except Exception as e:
                log(f"  [Web] {e}")
        for ex in item.get("emblem_examples") or []:
            add_example(ex)
        for emoji in (item.get("emblem_icon") or "").split():
            tried["Twemoji"] = tried.get("Twemoji", 0) + 1
            cands.append({**twemoji(emoji), "subject": f"{emoji} アイコン", "source": "Twemoji", "why": "版面の主題を表す物"})
        return _dedupe(cands)

    if live_action(item):   # 実写の作品は役の姿（剧照）だけ。演員の生活の写真は集めない
        return gather_roles(item, log, tried)
    who = subjects(item, kind, hi)
    log(f"  対象（{len(who)}）：{'、'.join(who)}")
    titles = wiki_titles(item)
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    for subj in who:
        _check_time()
        got = 0
        if kind == "character" and api and not item.get("emblem_people"):
            try:   # 先に、同じページの透明背景の立ち絵（ゲームの公式イラストなど）。代表画像は漫画のコマ・アニメの場面のことが多い
                r = emblem.cutout_on_page(api, subj)
                if r:
                    tried["Fandom"] = tried.get("Fandom", 0) + 1
                    cands.append({"subject": subj, "image": r[1], "page": r[2], "source": "Fandom",
                                  "why": f"{subj}（Fandom の公式の立ち絵・透明背景）", "license": ""})
                    got += 1
            except Exception as e:
                log(f"  [Fandom] {subj}：{e}")
            try:
                r = emblem.page_image(api, subj)
                tried["Fandom"] = tried.get("Fandom", 0) + 1
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
                if kind != "person" and needs_face(item):   # メンバー・出演者：検索で別の記事に当たったもの（題名に名前がない）は基準にしない
                    rows = [r for r in rows if relevant(r["title"], subj)]
                add(subj, rows, "Wikipedia", f"{subj}（Wikipedia の記事の画像）", None if kind == "person" else 2)
                got += len(rows)
            except Exception as e:
                log(f"  [Wikipedia] {subj}：{e}")
        if got < (6 if kind == "person" else 1):
            try:
                # メンバー・出演者は名前だけだと普通の単語（YOUNG・VORA・OA）で村・滝・飛行機に当たるので、作品名をつける
                rows = commons_photos(f"{subj} {name}" if len(who) > 1 else subj, 8 if kind == "person" else 3)
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
        if (got < (4 if kind == "person" else 1) or item.get("_web")) and not item.get("_no_web"):
            try:
                q = item.get("_query") or (f"{subj} {name}" if subj != name else f"{subj} 公式")
                add(subj, bing_images(q, 8 if kind == "person" else 4), "Web 画像検索", f"{subj}（Web 画像検索・要確認）")
            except Exception as e:
                log(f"  [Web] {subj}：{e}")
    return _dedupe(cands)


# ---------------------------------------------------------------- 実写の作品：役の姿（剧照）
ROLE_KEY = re.compile(r"character|role|portray|played|performer|cast", re.I)
ROLE_SKIP = re.compile(r"^(file|image|category|wikipedia|w|template):|disambiguation|/|season|episode|chapter|series|film|movie|award|^\d|"
                       r"^(january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)


def live_action(item):
    """実写の作品（出演者で集めるキャラ：emblem_people）。小元素は「役の姿」＝剧照にする。演員の生活の写真は使わない。"""
    return kind_of(item) == "character" and bool(item.get("emblem_people"))


ROLE_WHY = re.compile(r"役の記事|作品の動画の場面|ポスター|キービジュアル")


def is_role_image(x):
    """実写の作品の小元素が「役の姿・作品の画像」か（gather_roles が書いた理由）。出演者の生活の写真は False。"""
    return bool(x.get("work") or ROLE_WHY.search(str(x.get("why") or "")))


def fandom_api(item):
    """作品の Fandom（emblem_fandom / emblem_api）。書いていなければ名前・記事名から推測して、あるものを使う。"""
    if item.get("emblem_api"):
        return item["emblem_api"]
    names = [item.get("emblem_fandom")] if item.get("emblem_fandom") else []
    for t in [item["name"]] + [t for t in wiki_titles(item).values()]:
        slug = re.sub(r"\(.*?\)|[^a-z0-9]", "", str(t).lower())
        if slug and slug not in names:
            names.append(slug)
    for n in names:
        api = f"https://{n}.fandom.com/api.php"
        try:
            _json(f"{api}?action=query&meta=siteinfo&format=json")
            return api
        except Exception:
            continue
    return None


def _wikitext(api, titles):
    """{記事名: wikitext}（まとめて 1 回で）。"""
    q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles), "prop": "revisions", "rvprop": "content",
                                "rvslots": "main", "format": "json", "redirects": 1})
    pages = _json(f"{api}?{q}", 6_000_000)["query"]["pages"].values()
    out = {}
    for pg in pages:
        rev = (pg.get("revisions") or [{}])[0]
        out[pg.get("title", "")] = ((rev.get("slots") or {}).get("main") or {}).get("*") or rev.get("*") or ""
    return out


def role_of(api, actor, work_words=()):
    """出演者 → 役の記事名（その作品の Fandom で）。規則：
    1. 出演者の記事の「character / role」の欄と、作品名が出る出演作の表の行にあるリンクのうち、いちばん多く出てくるもの
    2. なければ検索の上位で、「役者・演じた」の欄に出演者の名前がある記事（出演者本人の記事・回・季は除く）"""
    text = _wikitext(api, [actor]).get(actor, "")
    link = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
    named_like_work = lambda t: any(w and w.lower() in t.lower() for w in work_words)   # 作品・ゲーム・回（名前に作品名を含む）
    ok = lambda t: t and actor.lower() not in t.lower() and not ROLE_SKIP.search(t)   # 出演者の名前を含む記事（本人・インタビュー）は役ではない
    # 1. 出演者の記事の「character / role」の欄：最初のリンク（いちばん主な役。作品と同じ名前の役もある：Harry Potter・Iron Man）
    for m in re.finditer(r"\|\s*([\w ]*(?:character|role|portray)[\w ]*)=((?:\[\[[^\]]*\]\]|[^|\n])*)", text, re.I):
        for lm in link.finditer(m.group(2)):
            if ok(lm.group(1).strip()):
                return lm.group(1).strip()
    # 2. 出演作の表で作品名が出る行の、いちばん右の列（役の列）の最後のリンク（「Moff Gideon」は称号より名前）。いちばん多いもの
    score = {}
    for l in text.split("\n"):
        if "||" in l and named_like_work(l):
            links = [m.group(1).strip() for m in link.finditer(l.split("||")[-1])]
            links = [t for t in links if ok(t) and not named_like_work(t)]
            if links:
                score[links[-1]] = score.get(links[-1], 0) + 1
    # 役の記事の「演じた人」の欄（actor / portrayed by / played by / performers）。欄の中のリンク・テンプレートは飛ばして読む。
    # 「cast」（出演者一覧）は回の記事にもあるので見ない
    pat = re.compile(r"\|\s*[\w ]*(?:actor|portray|played|performer)[\w ]*=(?:\[\[[^\]]*\]\]|\{\{[^}]*\}\}|<[^>]*>|[^|])*?"
                     + re.escape(actor), re.I)
    # 欄がない Wiki（Wookieepedia）は本文：同じ文の中に「[[出演者]] … portray / play / cast / perform」
    prose = re.compile(r"\[\[" + re.escape(actor) + r"(?:\|[^\]]*)?\]\][^.\n]{0,200}?\b(?:portray|play|cast|star|perform|voic)"
                       r"|\b(?:portrayed|played|performed|voiced|cast)\b[^.\n]{0,120}?\[\[" + re.escape(actor), re.I)
    # 実在の人（ほかの役者）の記事：職業が役者・声優、または国籍の欄（架空の人物にも「生まれ」の欄はあるので、それでは決めない）
    person = re.compile(r"\|\s*occupation\s*=[^|\n]*(?:actor|actress|voice)|\|\s*nationality\s*=", re.I)
    plays = lambda t: bool((pat.search(t) or prose.search(t)) and not person.search(t))
    if score:   # 表の列は回の名前のこともあるので、役の記事に「演じた人 = 出演者」と書いてあるものだけ
        top = sorted(score, key=score.get, reverse=True)[:5]
        texts = _wikitext(api, top)
        for t in top:
            if plays(texts.get(t, "")):
                return t
    # 3. 検索の上位で、「actor / portrayed by」の欄に出演者の名前がある記事（1 行の infobox も）
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": actor, "srlimit": 8, "format": "json"})
    hits = [h["title"] for h in _json(f"{api}?{q}")["query"]["search"] if ok(h["title"]) and not any(w and w.lower() == h["title"].lower() for w in work_words)]
    if not hits:
        return None
    texts = _wikitext(api, hits[:6])
    for t in hits[:6]:
        if plays(texts.get(t, "")):
            return t
    return None


POSTER_NAME = re.compile(r"poster|promo|key.?art|teaser|banner|portrait|render|cgi|concept|character.?art|official", re.I)


def role_images(api, role, limit=6):
    """役の記事の画像：代表画像（infobox）と、記事に載っている画像のうち役の名前（姓か名）がファイル名にあるもの（大きい順）。"""
    out = []
    try:
        src, page = emblem.page_image(api, role)
        out.append({"title": role, "image": small_url(src), "page": page, "license": "", "infobox": True})
    except Exception:
        pass
    q = urllib.parse.urlencode({"action": "query", "titles": role, "prop": "images", "imlimit": 200, "format": "json", "redirects": 1})
    pg = next(iter(_json(f"{api}?{q}")["query"]["pages"].values()))
    words = [w.lower() for w in re.split(r"[\s(),/]+", role) if len(w) >= 3]
    files = [x["title"] for x in pg.get("images", []) if re.search(r"\.(png|jpe?g|webp)$", x["title"], re.I)
             and not re.search(r"icon|logo|symbol|signature", x["title"], re.I) and any(w in x["title"].lower() for w in words)]
    rows = _files_info(api, files[:40], width=600) if files else []
    seen = {r["image"] for r in out}
    for r in sorted(rows, key=lambda r: (not POSTER_NAME.search(r["title"]), -r["area"])):   # ポスター風（宣伝用の絵）を先に。場面のスクリーンショットは暗くて何かわからないことが多い
        if r["image"] not in seen:
            out.append(r)
    return out[:limit]


def gather_roles(item, log=print, tried=None):
    """実写の作品：出演者ごとに「役の姿」の剧照を集める。
    基準：出演者の写真（Fandom の出演者の記事・Wikidata）— 本人確認にだけ使い、小元素には選ばない（anchor_only）。
    候補：役の記事の画像（代表画像 = 役の姿。兜・仮面で顔が見えなくても役の記事の代表画像は信じる）・役の記事の剧照・
    YouTube の「作品名 + 役名」の動画の場面。どれも顔で出演者本人か確かめる（旧作の別の役者・別の人物は落ちる）。"""
    tried = {} if tried is None else tried
    name = item["name"]
    api = fandom_api(item)
    roles = dict(item.get("emblem_roles") or {})
    words = [name] + [re.sub(r"\s*\(.*?\)", "", t) for t in wiki_titles(item).values()]
    # 動画の題名は英語のことが多いので、作品名は英語版の記事名（「Harry Potter (TV series)」→ Harry Potter）。なければ関注項の名前
    work_en = re.sub(r"\s*\(.*?\)", "", wiki_titles(item).get("en", "")) or name
    cands = []
    for actor in subjects(item, "character", rule(item)[3]):
        _check_time()
        role = roles.get(actor)
        if not role and api:
            try:
                role = role_of(api, actor, words)
            except Exception as e:
                log(f"  [役] {actor}：{e}")
        subj = f"{role}（{actor}）" if role else actor
        if role:
            roles[actor] = role
        log(f"  [役] {actor} → {role or '見つからない'}")
        if api:
            try:   # 基準：出演者の記事の写真（選ばない）
                src, page = emblem.page_image(api, actor)
                cands.append({"subject": subj, "image": small_url(src), "page": page, "source": "基準（出演者の写真）",
                              "why": f"{actor} 本人の写真（本人確認の基準。小元素には使わない）", "anchor": True, "anchor_only": True})
            except Exception:
                pass
        if not any(c["subject"] == subj and c.get("anchor") for c in cands):
            try:
                for r in wikidata_images(actor, ("P18",), 1)[:1]:
                    cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "基準（出演者の写真）",
                                  "why": f"{actor} 本人の写真（本人確認の基準）", "anchor": True, "anchor_only": True})
            except Exception as e:
                log(f"  [基準] {actor}：{e}")
        if role and api:
            try:
                rows = role_images(api, role)
                tried["役の記事"] = tried.get("役の記事", 0) + len(rows)
                for r in rows:
                    cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "役の記事",
                                  "why": f"{role}（{actor}）：Fandom の役の記事の{'代表画像' if r.get('infobox') else '剧照'}",
                                  "license": "", "trust_noface": bool(r.get("infobox")), "title": r.get("title", "")})
            except Exception as e:
                log(f"  [役の記事] {role}：{e}")
        try:   # 作品の動画の場面（題名に作品名と役名）。役がわからないときは探さない（出演者名だとインタビューばかり）
            rows = youtube_images(work_en, role, limit=2, scene=True) if role else []
            tried["作品の動画の場面"] = tried.get("作品の動画の場面", 0) + len(rows)
            for r in rows:
                cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "作品の動画の場面",
                              "why": f"{role or actor}（{actor}）：作品の動画の場面", "license": r.get("license", "")})
        except Exception as e:
            log(f"  [動画] {role or actor}：{e}")
    # 役の姿が足りないときは、作品そのものの主な画像（Wikipedia の記事の代表画像 = ポスター・キービジュアル）で埋める。
    # 出演者の生活の写真には戻らない（新しい作品は役の剧照がまだ少ない：哈利波特剧集）
    # 作品の記事：まず作品の Fandom（ポスターが代表画像のことが多い）、次に Wikipedia
    pages = ([(api, t) for t in wiki_titles(item).values()] if api else []) + \
            [(f"https://{lang}.wikipedia.org/w/api.php", t) for lang, t in wiki_titles(item).items()]
    for wapi, title in pages:
        try:
            src, page = emblem.page_image(wapi, title, any_license=True)
            cands.append({"subject": f"{name}（作品）", "image": small_url(src), "page": page, "source": "作品の主な画像",
                          "why": f"{name} のポスター・キービジュアル（Wikipedia の記事の代表画像）", "license": "", "work": True})
            tried["作品の主な画像"] = tried.get("作品の主な画像", 0) + 1
            break
        except Exception as e:
            log(f"  [作品の主な画像] {title}：{e}")
    if roles != (item.get("emblem_roles") or {}):
        with WRITE_LOCK:
            _set_field(name, "emblem_roles", json.dumps(roles, ensure_ascii=False) + "   # 出演者 → 役（gather_roles が Fandom の出演者の記事から）")
    return _dedupe(cands)


def article_pages(item_name, subject=None, days=30, limit=10):
    """集めた記事（inbox）のうち、題名か要約に対象の名前がある記事の網址（新しい順）。subject=None なら全部。"""
    out, key = [], (subject or "").lower().replace(" ", "")
    for path in sorted((ROOT / "inbox").glob("????-??-??.json"), reverse=True)[:days]:
        try:
            blocks = json.loads(path.read_text(encoding="utf-8")).get("items", [])
        except ValueError:
            continue
        for b in blocks:
            if b.get("name") != item_name:
                continue
            for e in b.get("entries", []):
                text = ((e.get("title") or "") + " " + (e.get("summary") or "")).lower().replace(" ", "")
                u = e.get("url") or ""
                if u.startswith("http") and u not in out and (not key or key in text) and "reddit.com" not in u:
                    out.append(u)
                if len(out) >= limit:
                    return out
    return out


def gather_wide(item, log=print, tried=None):
    """② 名前を広げる：①で足りなかったとき。作品名を足して検索し、言語・枚数・日数を広げる。"""
    if live_action(item):   # 実写の作品は役の姿だけ（出演者の名前で探すと生活の写真になる）
        return []
    kind, lo, target, hi = rule(item)
    name = item["name"]
    tried = {} if tried is None else tried
    log = _tracking(log, tried)
    cands = []

    def add(subject, rows, source, why):
        tried[source] = tried.get(source, 0) + len(rows)
        cands.extend({"subject": subject, "image": r["image"], "page": r.get("page", ""), "source": source, "why": why,
                      "license": r.get("license", ""), "anchor": bool(r.get("anchor")), "title": r.get("title", "")} for r in rows)
    if kind in ("brand", "topic"):
        for kw in [item.get("subtitle")] + list(item.get("keywords") or [])[:3]:
            if not kw or kw == name:
                continue
            _check_time()
            try:
                add(f"{kw} のロゴ", wikidata_images(kw, ("P154",) if kind == "brand" else ("P154", "P18"), 2), "Wikidata", f"{kw}（別名で検索）")
            except Exception as e:
                log(f"  [Wikidata] {e}")
        return _dedupe(cands)
    who = subjects(item, kind, hi)
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    for subj in who:
        _check_time()
        if kind == "character" and not item.get("emblem_people"):
            if api:   # 絵のキャラ：Fandom のページ名の別の書き方（名だけ・(character) つき）
                for t in {subj.split()[0], f"{subj} (character)"} - {subj}:
                    try:
                        r = emblem.page_image(api, t)
                        add(subj, [{"image": small_url(r[0]), "page": r[1]}], "Fandom", f"{subj}（Fandom・{t}）")
                        break
                    except Exception:
                        pass
            continue
        try:   # 実在の人：作品名をつけて全言語の Wikipedia → 記事の代表画像を基準に
            rows = [r for r in wikipedia_photos(subj, WIKI_LANGS, 4, None, extra=False, query=f"{subj} {name}") if relevant(r["title"], subj)]
            add(subj, rows, "Wikipedia", f"{subj}（作品名つきで検索）")
        except Exception as e:
            log(f"  [Wikipedia] {subj}：{e}")
        try:
            add(subj, commons_photos(f"{subj} {name}", 12), "Wikimedia Commons", f"{subj}（作品名つきの Commons）")
        except Exception as e:
            log(f"  [Commons] {subj}：{e}")
        try:
            add(subj, news_images(name, subj, limit=12, days=30, summary=True), "新聞の配図", f"{subj}（30 日分・要約にも名前）")
        except Exception as e:
            log(f"  [新聞] {e}")
    return _dedupe(cands)


def gather_pages(item, log=print, tried=None):
    """③ 公式・記事のページ：記事の本文ページと公式サイトから、og:image と大きい画像を取る（RSS の配図にない写真）。"""
    if live_action(item):   # 実写の作品は役の姿だけ（出演者の名前で探すと生活の写真になる）
        return []
    kind, lo, target, hi = rule(item)
    name = item["name"]
    tried = {} if tried is None else tried
    log = _tracking(log, tried)
    cands = []

    def add(subject, rows, source, why):
        tried[source] = tried.get(source, 0) + len(rows)
        cands.extend({"subject": subject, "image": r["image"], "page": r.get("page", ""), "source": source, "why": why,
                      "license": r.get("license", ""), "title": r.get("title", "")} for r in rows)
    if kind in ("brand", "topic"):
        if item.get("site"):
            try:
                add(f"{name} のロゴ", site_images(item["site"], 4, logo=True), "公式サイト", "公式サイトのロゴ（深く）")
            except Exception as e:
                log(f"  [公式サイト] {e}")
        return _dedupe(cands)
    who = subjects(item, kind, hi)
    site_imgs = []
    if item.get("site"):
        try:
            site_imgs = site_images(item["site"], 30)
        except Exception as e:
            log(f"  [公式サイト] {e}")
    for subj in who:
        _check_time()
        mine = [r for r in site_imgs if relevant(r["image"].rsplit("/", 1)[-1], subj)] if len(who) > 1 else site_imgs[:8]
        add(subj, mine, "公式サイト", f"{subj}（公式サイトの画像）")
        rows = []
        for url in article_pages(name, subj if len(who) > 1 or kind != "person" else None, limit=8):
            try:
                rows += site_images(url, 1)
            except Exception:
                pass
        add(subj, rows, "記事のページ", f"{subj}（記事のページの og:image）")
        if needs_face(item):
            try:
                add(subj, youtube_images("" if kind == "person" and len(who) == 1 else name, subj), "YouTube",
                    f"{subj}（YouTube の動画のサムネイル）")
            except Exception as e:
                log(f"  [YouTube] {subj}：{e}")
    return _dedupe(cands)


STRATEGIES = [("標準", "gather"), ("名前を広げる", "gather_wide"), ("公式・記事のページ", "gather_pages")]


def _hash(img):
    g = img.convert("L").resize((9, 8))
    px = list(g.get_flattened_data() if hasattr(g, "get_flattened_data") else g.getdata())
    return int("".join("1" if px[r * 9 + c] > px[r * 9 + c + 1] else "0" for r in range(8) for c in range(8)), 2)


def file_key(url):
    """画像の「同じファイル」の鍵。Wikimedia は同じファイルが thumb/…/500px-名前・元の網址・Special:FilePath/名前 のどれでも来る
    （周杰伦：同じ写真が 2 つの網址で入って 4 枚が同じに見えた）ので、ファイル名だけにする。ほかは ? から後ろを落とす。"""
    u = urllib.parse.unquote(str(url or ""))
    m = (re.search(r"wikimedia\.org/wikipedia/[^/]+/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/?#]+)", u)
         or re.search(r"Special:FilePath/([^/?#]+)", u) or re.search(r"/wiki/File:([^/?#]+)", u))
    if m:
        return "wm:" + m.group(1).replace(" ", "_").lower()
    return u.split("?")[0]


def _dedupe(cands):
    """同じ画像（網址違い・Wikimedia の同じファイル）を落とす。"""
    out, seen = [], set()
    for c in cands:
        k = file_key(c["image"])
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


BLANK_STD = 6   # 明るさの標準偏差がこれより小さい = 真っ白・真っ黒のほぼ一色（白紙）
SAME_BITS = 4   # 差分ハッシュ（64 ビット）の違いがこれ以下 = 同じ画像


def check(cands, log=print, need_face=False, strict=False, reasons=None):
    """ダウンロードして使えるか確かめる（短辺 160px 以上・開ける）。落とした理由は reasons（dict）に数える。
    need_face（人物・グループ・出演者）：顔の特徴量で「その人」かを確かめる（face_id）。目で見ていた判断を規則にしたもの：
      顔なし（観客席・絵画・物）／遠景（顔が画像の高さの 10% 未満）／何人も写っている（2 番目の顔が 60% 以上）／
      別人（記事の代表画像と cos < 0.363。strict = 基準がなければ同じ顔 2 枚以上のときだけ本人）
    モデルが使えないときは顔の有無だけ（haar）に下げる。最後に、似すぎた画像（差分ハッシュ）を落とす。"""
    reasons = {} if reasons is None else reasons

    def drop(why, c, detail=""):
        reasons[why] = reasons.get(why, 0) + 1
        log(f"  [{why}] {c['subject']}（{c['source']}）{detail}")
    dl = []
    for c in cands:
        try:
            data = _get(c["image"], 6_000_000)
            if c["image"].lower().split("?")[0].endswith(".svg"):
                dl.append({**c, "shape": "icon" if c["source"] == "Twemoji" else "logo", "_img": None})
                continue
            shape, key, img = inspect(data)
            from PIL import ImageStat
            if ImageStat.Stat(img.convert("L")).stddev[0] < BLANK_STD:   # 真っ白・真っ黒のほぼ一色の画像
                drop("白紙", c)
                continue
            dl.append({**c, "shape": shape, "_img": img})
        except Exception as e:
            drop("使えない", c, str(e)[:50])
    if need_face:
        by = {}
        for i, c in enumerate(dl):
            by.setdefault(c["subject"], []).append(i)
        out = set()
        for subj, ids in by.items():
            test = [i for i in ids if dl[i]["source"] != "直接指定" and not dl[i].get("work")]   # 作品の主な画像は人の写真ではない
            with _face_lock:
                got = [face_id.face_info(dl[i]["_img"]) for i in test]
            feats = []
            for k, (feat, info) in enumerate(got):
                why = face_id.photo_problem(info) if info else None
                if why == "顔なし" and dl[test[k]].get("trust_noface"):   # 役の記事の代表画像：兜・仮面で顔が見えなくても役の姿
                    feats.append(None)
                    continue
                if why:
                    drop(why, dl[test[k]])
                    out.add(test[k])
                    feats.append(None)
                else:
                    feats.append(feat)
            anchor = next((k for k, i in enumerate(test) if dl[i].get("anchor")), None)
            keep = face_id.same_person(feats, anchor, strict=strict)
            if keep is None:   # モデルなし：顔の有無だけ
                log("  [本人確認なし] 顔モデルが使えないので、顔があるかだけ確かめた")
                with _face_lock:
                    keep = {k for k, i in enumerate(test) if emblem.face_box(dl[i]["_img"].convert("RGB"))}
            for k, i in enumerate(test):
                if k not in keep and i not in out and not (feats[k] is None and dl[i].get("trust_noface")):
                    drop("別人", dl[i])
                    out.add(i)
        dl = [c for i, c in enumerate(dl) if i not in out]
    dl = [c for c in dl if not c.get("anchor_only")]   # 本人確認の基準（出演者の写真）は小元素には選ばない
    good, hashes = [], []
    for c in dl:
        if c["_img"] is not None:
            h = _hash(c["_img"])
            if any(bin(h ^ x).count("1") <= SAME_BITS for x in hashes):
                reasons["同じ画像"] = reasons.get("同じ画像", 0) + 1
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
    old = [] if replace else [x for x in (item.get("emblem") or []) if isinstance(x, dict)]
    if live_action(item):   # 実写の作品：前の規則で入れた出演者の生活の写真は残さない（役の姿・作品の画像だけ）
        old = [x for x in old if is_role_image(x)]
    chosen, count = [], {}
    for x in old:   # 番号は今ある分の続きから（「周杰倫 1」が 2 つできて同じファイルに上書きされない）
        b = _base_subject(x.get("subject"))
        count[b] = count.get(b, 0) + 1
    for n in picks:
        c = good[n - 1]
        count[c["subject"]] = count.get(c["subject"], 0) + 1
        if count[c["subject"]] > 1 or sum(1 for m in picks if good[m - 1]["subject"] == c["subject"]) > 1:   # 同じ人の別の写真は名前を分ける（保存ファイル名が重ならないように）
            c = {**c, "subject": f"{c['subject']} {count[c['subject']]}"}
        row = {"subject": c["subject"], "why": c["why"], "image": c["image"], "page": c["page"], "shape": c["shape"]}
        if emblem.is_logo(row, kind) and not c["image"].lower().split("?")[0].endswith(".svg"):
            try:   # ロゴは切らない：地の色を抜いて倉庫に置く（カードの窓で切ると字が欠ける）
                row.update(image=emblem.logo_local(c["image"], emblem.slugify(name, c["subject"])), source=c["image"], shape="logo")
            except Exception as e:
                log(f"  [ロゴ] {c['subject']}：{e}")
        elif row["shape"] == "badge" and c.get("_img") is not None:
            row["ar"] = round(c["_img"].size[1] / c["_img"].size[0], 3)   # 縦横比：カードの窓に近くなければ切らずに全体を見せる
        if c.get("work"):   # 作品の主な画像（ポスター）：人を切り抜かず、カードのまま。タイトルロゴ（文字だけ）はロゴとして字を大きく
            row["work"] = True
            try:
                got = emblem.wordmark_local(c["image"], emblem.slugify(name, c["subject"]))
                if got:
                    row.update(source=c["image"], image=got[0], shape="badge" if got[2] else "logo", ar=got[1])
                    if got[2]:
                        row["plate"] = True   # 濃い地の板ごとのロゴ：白いカードに入れず、板に斜めの枠だけ
            except Exception as e:
                log(f"  [ロゴ] {c['subject']}：{e}")
        chosen.append(row)
    seen = {file_key(u) for x in old for u in (x.get("image"), x.get("source")) if u}
    merged = old + [x for x in chosen if file_key(x["image"]) not in seen]   # 同じファイルは 2 回入れない
    merged = merged[:hi]
    _drop_skip(name)
    emblem.write_item(name, merged, None)
    log(f"→ 「{name}」に {len(merged)} 枚（目標 {target}、最大 {hi}）")
    if kind in ("person", "group", "character"):
        emblem.cut_all(name, not needs_face(item), [x["image"] for x in old])   # 実在の人は写真として切る。前からの小元素は取景で外さない
        emblem.fit_all(name, not needs_face(item))
        # 切り抜きの検査で外れた画像は emblem_reject に書く（次は同じ人の次の候補を選ぶ。同じ画像で何度も失敗しない）
        now = next((i for i in load_items() if i["name"] == name), {})
        kept = {u for x in now.get("emblem") or [] if isinstance(x, dict) for u in (x.get("image"), x.get("source"))}
        failed = [x["image"] for x in chosen if x["image"] not in kept and x.get("source", x["image"]) not in kept]
        if failed:
            rej = list(dict.fromkeys(list(now.get("emblem_reject") or []) + failed))
            with WRITE_LOCK:
                _set_field(name, "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
            log(f"  [外した] 切り抜きの検査で外れた {len(failed)} 枚を emblem_reject に（次は別の候補）")
    return merged


def _sheet_path(name):
    import hashlib
    slug = re.sub(r"[^0-9A-Za-z]+", "-", name).strip("-") or hashlib.md5(name.encode()).hexdigest()[:8]
    return pathlib.Path("/tmp/wishlist-emblem") / f"{slug}.jpg"


def needs_face(item):
    """顔で本人確認する関注項：本人・グループと、出演者で集めるキャラ（emblem_people: true の実写の作品）。"""
    return kind_of(item) in ("person", "group") or (kind_of(item) == "character" and bool(item.get("emblem_people")))


def run_item(item, auto=False, picks=None, log=print, tried=None, strict=False, reasons=None):
    log(f"■ {item['name']}（{KIND_JA[kind_of(item)]}）")
    cands = gather(item, log, tried)
    good = check(cands, log, need_face=needs_face(item), strict=strict, reasons=reasons)
    out = _sheet_path(item["name"])
    sheet(good, out)
    (out.with_suffix(".json")).write_text(json.dumps([{k: v for k, v in c.items() if k != "_img"} for c in good],
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  候補 {len(good)} 枚 → {out}")
    return good, out


def source_chain(item):
    """その関注項で候補を探す取り方の順（gather と同じ順）。→ [(取り方, 自動で選んでよいか)]。管理ページ「小元素の探し方」用。"""
    kind = kind_of(item)
    if kind == "brand":
        chain = ["直接指定", "Wikidata", "Wikimedia Commons", "公式サイト", "Wikipedia", "Twemoji"]
    elif kind == "topic":
        chain = ["直接指定", "Wikidata", "Wikimedia Commons", "公式サイト", "Wikipedia", WEB, "Twemoji"]
    elif kind == "character" and not item.get("emblem_people"):
        chain = ["直接指定", "Fandom", "Wikipedia", "Wikimedia Commons", "新聞の配図", "公式サイト", WEB]
    elif kind == "person":
        chain = ["直接指定", "Wikidata", "Wikipedia", "Wikimedia Commons", "新聞の配図", "公式サイト", "YouTube", WEB]
    else:   # グループ・出演者：Wikidata は使わない（gather は本人のときだけ）。公式サイトは対象が 1 人のときだけ
        chain = ["直接指定", "Wikipedia", "Wikimedia Commons", "新聞の配図", "YouTube", WEB]
    auto = (lambda s: s != WEB) if needs_face(item) else (lambda s: s in AUTO_SOURCES.get(kind, ()))
    return [(s, auto(s)) for s in chain]


# 自動で選ぶときの、取り方の優先順。ブランドは公式ロゴ（Wikidata P154・公式サイト）、主題は Wikidata・Commons・Twemoji を先に
PICK_ORDER = ["直接指定", "役の記事", "作品の動画の場面", "作品の主な画像", "AniList", "Fandom", "Wikidata", "Wikipedia", "Wikimedia Commons", "新聞の配図", "公式サイト", "YouTube", "Twemoji", WEB]
PICK_ORDER_BY_KIND = {
    "brand": ["直接指定", "Wikidata", "公式サイト", "Wikimedia Commons", "Wikipedia", "Twemoji", WEB],
    "topic": ["直接指定", EXAMPLE, "Wikidata", "Wikimedia Commons", "Twemoji", "Wikipedia", "公式サイト", "新聞の配図", WEB],
}


# 定時の後台（strict）で自動で選んでよい取り方。絵のキャラは名前が一般的な言葉（Juggernaut・Axe）だと
# Wikipedia・Commons で別物に当たるので、キャラ専用の取り方だけ。人物（本人確認するもの）は Web 画像検索以外ならよい
AUTO_SOURCES = {
    "character": {"直接指定", "Fandom"},
    "brand": {"直接指定", "Wikidata", "公式サイト", "Wikimedia Commons"},
    "topic": {"直接指定", EXAMPLE, "Wikidata", "Wikimedia Commons", "Twemoji"},
}


def _base_subject(s):
    return re.sub(r" \d+$", "", str(s or ""))


def _have_images(item):
    """今ある小元素の画像と、目で見て外した画像（emblem_reject）。自動ではどちらも選ばない。"""
    have = {u for x in item.get("emblem") or [] if isinstance(x, dict) for u in (x.get("image"), x.get("source")) if u}
    have |= set(item.get("emblem_reject") or [])
    return have | {file_key(u) for u in have}   # 網址が違っても同じファイルなら同じ画像


def auto_pick(item, good, web=True, strict=False):
    """自動で選ぶ：目標までの足りない分だけ。今ある小元素と同じ画像・同じ人（グループ・キャラは 1 人 1 枚）は選ばない。
    web=False（定時の後台）は Web 画像検索の結果を選ばない（出所が確かでないので、一覧を目で見て選ぶ）。
    strict=True（定時の後台）は、種類ごとに確かな取り方（AUTO_SOURCES）だけ。人物は本人確認を通ったものなので Web 以外はよい。"""
    kind, lo, target, hi = rule(item)
    have = [x for x in item.get("emblem") or [] if isinstance(x, dict)]
    need = target - len(have)
    if need <= 0:
        return []
    order = PICK_ORDER_BY_KIND.get(kind, PICK_ORDER)

    def rank(src):
        src = src.split("(")[0]
        return order.index(src) if src in order else len(order)

    idx = sorted(range(len(good)), key=lambda i: (rank(good[i]["source"]), i))
    # 代表作のある主題は 1 作品 1 枚（ロゴか記事の画像のどちらか）。代表作のロゴを優先、なければ記事の画像
    per = 1 if kind == "topic" and item.get("emblem_examples") else 99 if kind in ("person", "topic", "brand") else 1
    seen = {}
    for x in have:
        s = _base_subject(x.get("subject"))
        seen[s] = seen.get(s, 0) + 1
    images, picks = _have_images(item), []
    for i in idx:
        c = good[i]
        if (not web and c["source"] == WEB) or c.get("image") in images or file_key(c.get("image")) in images:
            continue
        if strict and not needs_face(item) and c["source"].split("(")[0] not in AUTO_SOURCES.get(kind, ()):
            continue
        s = c["subject"]
        if seen.get(s, 0) >= per:
            continue
        seen[s] = seen.get(s, 0) + 1
        picks.append(i + 1)
        if len(picks) >= need:
            break
    return picks


# ---------------------------------------------------------------- 定時の後台（--background）と進捗
PROGRESS = ROOT / "state" / "emblem_progress.json"
RETRY_HOURS = 6           # 全部の段で届かなかった関注項は、材料（記事・手がかり）が変わらなければこの時間は飛ばす
MARGIN = 120              # 残り時間がこれ（秒）を切ったら、次の関注項に入らない
STATE_JA = {"ok": "そろっている", "running": "進行中", "review": "要確認", "failed": "失敗"}


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _hours_since(stamp, now):
    import datetime as dt
    try:
        return (dt.datetime.fromisoformat(now) - dt.datetime.fromisoformat(stamp)).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def load_progress(path=None):
    try:
        data = json.loads(pathlib.Path(path or PROGRESS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("items", {})
    return data


def save_progress(prog, path=None):
    path = pathlib.Path(path or PROGRESS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prog, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def sync_progress(prog, items):
    """items.yaml の今の枚数を進捗に写す（ネットには出ない）。目標に届いたものは「そろっている」、
    届いていないのにまだ手を付けていないものは「進行中（順番待ち）」。items.yaml から消えた関注項は消す。"""
    names = []
    for item in items:
        st = status(item)
        names.append(st["name"])
        e = prog["items"].setdefault(st["name"], {})
        e.update(kind=st["kind"], have=st["have"], target=st["target"])
        if st["state"] == "ok":
            if e.get("state") != "ok":
                e["note"] = f"{st['have']} / {st['target']} 枚で目標に届いた"
            e["state"] = "ok"
            e.pop("failed_at", None)
            e.pop("sheet", None)
        elif e.get("state") in (None, "ok"):
            e["state"], e["note"] = "running", "順番待ち"
    for n in list(prog["items"]):
        if n not in names:
            del prog["items"][n]
    prog["summary"] = {"ok": sum(1 for n in names if prog["items"][n]["state"] == "ok"), "total": len(names)}
    return prog


def due(prog, items, now):
    """後台で処理する順：目標に届いていないものを、足りない枚数の多い順（同じなら前回の処理が古い順）。
    RETRY_HOURS（6 時間）以内に失敗して材料も変わっていないものは飛ばす。"""
    rows = []
    for item in items:
        st = status(item)
        if st["state"] == "ok":
            continue
        e = prog["items"].get(item["name"]) or {}
        h = _hours_since(e.get("failed_at"), now)
        if (e.get("state") == "failed" and h is not None and h < RETRY_HOURS and not os.environ.get("EMBLEM_RETRY_NOW")
                and e.get("material") == material(item)):   # 材料（新しい記事・手がかり）が変わったら待たない。指紋の記録がない古い失敗も待たない
            continue
        rows.append((st["have"] - st["target"], e.get("at") or "", item["name"], item))
    return [r[3] for r in sorted(rows, key=lambda r: r[:3])]


def waiting(prog, items, now):
    """失敗して再挑戦を待っている版面 → [(名前, 再挑戦の時刻 ISO)]。材料が変われば時刻を待たずに due() に入る。"""
    import datetime as dt
    out = []
    due_names = {i["name"] for i in due(prog, items, now)}
    for item in items:
        e = prog["items"].get(item["name"]) or {}
        if item["name"] in due_names or e.get("state") != "failed" or status(item)["state"] == "ok":
            continue
        try:
            at = (dt.datetime.fromisoformat(e["failed_at"]) + dt.timedelta(hours=RETRY_HOURS)).isoformat(timespec="seconds")
        except (KeyError, ValueError):
            at = ""
        out.append((item["name"], at))
    return sorted(out, key=lambda r: r[1])


def _write_sheet(item, good):
    out = _sheet_path(item["name"])
    sheet(good, out)
    out.with_suffix(".json").write_text(json.dumps([{k: v for k, v in c.items() if k != "_img"} for c in good],
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def material(item):
    """その関注項の「材料」の指紋：集めた記事の数（直近 30 日）と、小元素の手がかり（emblem_who・urls・fandom・wiki・site・reject）。
    失敗した版面は、これが変わったら（新しい記事・手がかりが増えた）6 時間を待たずにすぐやり直す。"""
    import hashlib
    n = 0
    for path in sorted((ROOT / "inbox").glob("????-??-??.json"), reverse=True)[:30]:
        try:
            for b in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                if b.get("name") == item.get("name"):
                    n += len(b.get("entries") or [])
        except ValueError:
            pass
    keys = {k: item.get(k) for k in ("emblem_who", "emblem_urls", "emblem_fandom", "wiki", "site", "emblem_reject", "emblem_kind", "emblem_icon")}
    return hashlib.sha1(json.dumps([n, keys], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def _live(board, label=None, step=0):
    """管理ページ「いま動いているもの」・簡報の帯（Supabase live_status）に、この版面でいま何をしているかを書く。label=None で消す。
    データベースに書けなくても（鍵がない・ローカル）補完は止めない。"""
    if not os.environ.get("SUPABASE_SERVICE_KEY"):
        return
    try:
        import digest
        digest.live_mark(board, f"emblem:{label}" if label else None, found=step, proc="emblem")
    except Exception:
        pass


def fill_one(item, log=print):
    """後台で 1 つの関注項を埋める。AI も人も見ない：目で見ていた判断は全部規則にしてある。
    取り方の段（STRATEGIES）を、目標に届くまで同じ回の中で順に上がる：① 標準 → ② 名前を広げる → ③ 公式・記事のページ。
    各段で 集める → 確かめる（check：顔なし・遠景・何人も・別人・同じ画像を理由つきで落とす）→ 選ぶ（auto_pick）→ 書いて切り抜く。
    → {state: ok / failed, note, tried, funnel, steps, material}。全部の段で届かなければ failed（材料が変わるか 6 時間後にもう一度）。"""
    pooln = int(item.get("emblem_pool") or 0)
    if (item.get("emblem_category") or item.get("anilist_id")) and (
            not pooln or len(item.get("emblem_who") or []) < min(CEIL.get(kind_of(item), 0), pooln)):
        try:   # 主要な要素の数がまだわからない：先に数える（上限と集める名前が決まる）
            if roster(item, log):
                item = next(i for i in load_items() if i["name"] == item["name"])
        except Exception as e:
            log(f"  [名簿] {item['name']}：{e}")
    before = status(item)["have"]
    have0 = {_base_subject(x.get("subject")) for x in item.get("emblem") or [] if isinstance(x, dict)}
    queued = len([w for w in item.get("emblem_who") or [] if w not in have0])   # まだいない人の数。STEP を超えれば今回は一部だけ
    if needs_face(item) and face_id.engine() is None:
        return {"state": "failed", "note": "顔のモデルが使えず本人確認ができないので、自動では選ばなかった", "tried": {}}
    tried, reasons, steps = {}, {}, []
    funnel = {"found": 0, "usable": 0, "auto": 0}
    fresh = item
    try:
        for n, (label, fn) in enumerate(STRATEGIES, 1):
            _check_time()
            _live(item["name"], label, n)
            log(f"  ── 段 {n}/{len(STRATEGIES)}：{label}")
            got = {}
            cands = globals()[fn]({**fresh, "_no_web": True}, log, got)
            for k, v in got.items():
                tried[k] = tried.get(k, 0) + v
            good = check(cands, log, need_face=needs_face(item), strict=True, reasons=reasons)
            picks = auto_pick(fresh, good, web=False, strict=True)
            with WRITE_LOCK:
                before_step = status(fresh)["have"]
                if picks:
                    commit(fresh, good, picks, log=log)
                fresh = next((i for i in load_items() if i["name"] == item["name"]), fresh)
            added_step = max(0, status(fresh)["have"] - before_step)
            if len(picks) > added_step:   # 書いたが切り抜きの検査（穴・端で切れた・にじみ）で落ちた
                reasons["切り抜きの検査"] = reasons.get("切り抜きの検査", 0) + len(picks) - added_step
            funnel["found"] += sum(got.values())
            funnel["usable"] += len(good)
            funnel["auto"] += len(picks)
            steps.append({"label": label, "found": sum(got.values()), "added": added_step})
            covered = {_base_subject(x.get("subject")) for x in fresh.get("emblem") or [] if isinstance(x, dict)}
            kind = kind_of(item)
            for i, c in enumerate(good, 1):   # 選ばなかった候補の理由（前は「要確認」として AI が目で見ていた）
                if i in picks:
                    continue
                if not needs_face(item) and c["source"].split("(")[0] not in AUTO_SOURCES.get(kind, ()):
                    why = "確かでない取り方"
                elif kind in ("group", "character") and c["subject"] in covered:
                    why = "重複（その人はもういる）"
                elif c["image"] in _have_images(fresh):
                    why = "もう使っている・外した画像"
                else:
                    why = "目標を超える"
                reasons[why] = reasons.get(why, 0) + 1
            if status(fresh)["state"] == "ok":
                break
    finally:
        _live(item["name"], None)
    st = status(fresh)
    added = max(0, st["have"] - before)
    funnel.update(added=added, rejected=reasons)
    path = " → ".join(f"{x['label']} +{x['added']}" for x in steps)
    top = "・".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:3])
    if st["state"] == "ok":
        return {"state": "ok", "note": f"{added} 枚足して目標に届いた（{path}）", "tried": tried, "funnel": funnel, "steps": steps}
    if added and queued > STEP and kind_of(item) in ("character", "group"):   # STEP 人ずつ足している途中：失敗ではなく進行中。次の回に続き
        return {"state": "running", "tried": tried, "funnel": funnel, "steps": steps,
                "note": f"{added} 枚足した（{path}）。あと {st['target'] - st['have']} 枚、次の回に続きの {STEP} 人"}
    return {"state": "failed", "tried": tried, "funnel": funnel, "steps": steps, "material": material(fresh),
            "note": f"{added} 枚足した（{path}）。外した理由：{top or '候補なし'}。新しい記事が来たらすぐ、来なくても {RETRY_HOURS} 時間後にもう一度"}


def fresh_have(item):
    st = status(item)
    return f"{st['have']}/{st['target']} 枚"


def record(prog, item, result, now):
    """1 つの関注項の結果を進捗に書く。"""
    st = status(item)
    e = prog["items"].setdefault(item["name"], {})
    e.update(kind=st["kind"], have=st["have"], target=st["target"], at=now, state=result["state"], note=result.get("note", ""))
    if "tried" in result:
        e["tried"] = result["tried"]
    if "funnel" in result:
        e["funnel"] = result["funnel"]
    for k in ("steps", "material"):
        if k in result:
            e[k] = result[k]
    if result.get("sheet"):
        e["sheet"] = result["sheet"]
    else:
        e.pop("sheet", None)
    if result["state"] == "failed":
        e["failed_at"] = now
    else:
        e.pop("failed_at", None)
    return e


WORKERS = 6   # 同時に処理する関注項の数（Actions は 4 コア。集めるのは待ちが多いので 6 本。抠图・書き込みは 1 本ずつ）


def background(minutes, log=print, fill=None, clock=time.time, path=None, runlog_dir=None, workers=None, live=None):
    """定時の後台：時間の予算（分）の中で、足りない関注項を workers 本並列で埋め、state/emblem_progress.json に進捗を残す。
    候補集め・本人確認は並列、items.yaml への書き込みと抠图は WRITE_LOCK で 1 本ずつ。
    1 つ終わるごとに保存するので、途中で止まっても、それまでの結果は残る。
    live：簡報の版面の「更新中」の帯に知らせる関数（livestatus.report と同じ形）。本番（path なし）では livestatus.report。"""
    fill = fill or fill_one
    if live is None:
        import livestatus
        live = livestatus.report if path is None else (lambda *a, **k: None)   # テスト（path あり）はネットに出ない
    per_board = runlog.typical("emblem", "item_secs", 240, log_dir=runlog_dir) / 60   # 1 版面にかかる時間（最近の中央値）
    started = time.time()
    workers = max(1, int(workers or WORKERS))
    deadline = clock() + minutes * 60
    if clock is time.time:
        _deadline[0] = deadline - 60   # 集めるのはここまで（残りの 1 分で書き込みと切り抜き）
    prog = load_progress(path)
    now = _now()
    prog.setdefault("started", now)
    prog["last_run"] = {"at": now, "minutes": minutes, "workers": workers, "done": []}
    items = load_items()
    sync_progress(prog, items)
    save_progress(prog, path)
    queue = due(prog, items, now)
    runlog.add("emblem", f"開始：予算 {minutes:g} 分・{workers} 本並列・待ち {len(queue)} 版面"
                         f"（{'、'.join(i['name'] for i in queue[:4])}{' …' if len(queue) > 4 else ''}）", log_dir=runlog_dir)
    lock = threading.Lock()   # 進捗・ログ・待ち行列
    stop = threading.Event()
    todo = list(queue)

    def take():
        with lock:
            if stop.is_set() or not todo:
                return None
            if clock() > deadline - MARGIN:
                stop.set()
                log(f"時間切れ：残りは次の回に（予算 {minutes:g} 分）")
                return None
            item = todo.pop(0)
            record(prog, item, {"state": "running", "note": "処理中"}, _now())
            save_progress(prog, path)
            return item

    def worker():
        while True:
            item = take()
            if item is None:
                return
            name = item["name"]
            ilog = (lambda m, n=name: log(f"[{n}] {str(m).strip()}")) if workers > 1 else log
            live(name, "emblem", "work", "小元素を集めています", per_board + 3)
            t_item, before = time.time(), fresh_have(item)
            try:
                result = fill(item, ilog)
            except OutOfTime:
                with lock:
                    stop.set()
                    ilog("時間切れ：途中で止めた。次の回にやり直す")
                    record(prog, item, {"state": "running", "note": "時間切れで途中まで（次の回に続き）"}, _now())
                    runlog.add("emblem", f"{name}：時間切れで途中まで（次の回に続き）", "warn", log_dir=runlog_dir, item=name)
                    save_progress(prog, path)
                live(name, "emblem", "clear")
                return
            except Exception as e:   # 1 つの失敗で全体を止めない
                ilog(f"[失敗] {e}")
                result = {"state": "failed", "note": f"エラー：{str(e)[:80]}", "material": material(item)}
            with WRITE_LOCK:
                fresh = next((i for i in load_items() if i["name"] == name), item)
            with lock:
                record(prog, fresh, result, _now())
                prog["last_run"]["done"].append(name)
                ilog(f"→ {STATE_JA[result['state']]}：{result.get('note', '')}")
                runlog.add("emblem", f"{name}：{STATE_JA[result['state']]}（{fresh_have(fresh)}）{result.get('note', '')}",
                           {"ok": "ok", "review": "warn", "failed": "error"}.get(result["state"], "info"), log_dir=runlog_dir, item=name,
                           item_secs=round(time.time() - t_item))
                save_progress(prog, path)
            # 小元素が増えた版面は、この回の終わり（push → 網页の生成）に反映される。増えなかった版面は帯を消す
            if fresh_have(fresh) != before:
                live(name, "emblem", "wait", "小元素を追加 · 反映を待っています", max(1, (deadline - clock()) / 60) + 3)
            else:
                live(name, "emblem", "clear")

    threads = [threading.Thread(target=worker, name=f"emblem-{n}", daemon=True) for n in range(min(workers, max(1, len(queue))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _deadline[0] = None
    prog["last_run"]["end"] = _now()
    sync_progress(prog, load_items())
    import resources
    runlog.add("emblem", f"終了：{len(prog['last_run']['done'])} 版面を処理（{workers} 本並列）・そろっている {prog['summary']['ok']} / {prog['summary']['total']}",
               "ok", log_dir=runlog_dir, secs=round(time.time() - started), workers=workers, res=resources.snapshot())
    save_progress(prog, path)
    return prog


def main():
    ap = argparse.ArgumentParser(description="小元素の自動補完")
    ap.add_argument("name", nargs="?", help="items.yaml の関注項の名前")
    ap.add_argument("--audit", action="store_true", help="全関注項の状況を表示")
    ap.add_argument("--commit", help="候補一覧の番号（カンマ区切り）を items.yaml に書く")
    ap.add_argument("--replace", action="store_true", help="今ある小元素を置き換える")
    ap.add_argument("--web", action="store_true", help="Web 画像検索も必ず使う（足りないとき）")
    ap.add_argument("--query", help="Web 画像検索の言葉（既定は「対象 作品名」）")
    ap.add_argument("--auto", action="store_true", help="足りない関注項を決まった順で全部自動で埋める")
    ap.add_argument("--background", action="store_true", help="定時の後台：時間の予算の中で足りない順に埋め、進捗を残す")
    ap.add_argument("--minutes", type=float, default=40, help="--background の時間の予算（分）")
    ap.add_argument("--workers", type=int, default=WORKERS, help="--background で同時に処理する関注項の数")
    ap.add_argument("--roster", action="store_true", help="主要な要素（キャラ）を数えて emblem_pool と emblem_who を書く（上限が決まる）")
    ap.add_argument("--progress", action="store_true", help="items.yaml の今の枚数を進捗ファイルに写すだけ（ネットに出ない）")
    a = ap.parse_args()
    items = load_items()
    if a.background:
        prog = background(a.minutes, workers=a.workers)
        print(f"そろっている {prog['summary']['ok']} / {prog['summary']['total']}")
        for n, x in sorted(prog["items"].items(), key=lambda kv: kv[1]["state"]):
            if x["state"] != "ok":
                print(f"  {STATE_JA[x['state']]:<6} {n}：{x['have']}/{x['target']} {x.get('note', '')}{'  一覧 ' + x['sheet'] if x.get('sheet') else ''}")
        return
    if a.progress:
        prog = sync_progress(load_progress(), items)
        save_progress(prog)
        print(f"そろっている {prog['summary']['ok']} / {prog['summary']['total']}")
        return
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
    if a.roster:
        print(roster(item))
        return
    if a.commit:   # 一覧を作ったときの候補（json）から選ぶ。集め直すと順番が変わるので
        jp = _sheet_path(item["name"]).with_suffix(".json")
        good = json.loads(jp.read_text(encoding="utf-8"))
        for c in good:
            c.setdefault("_img", None)
        picks = [int(x) for x in a.commit.split(",")]
        commit(item, good, picks, a.replace)
        fresh = next(i for i in load_items() if i["name"] == item["name"])
        prog = load_progress()
        st = status(fresh)
        record(prog, fresh, {"state": "ok" if st["state"] == "ok" else "review",
                             "note": f"一覧から {len(picks)} 枚を選んだ（{st['have']} / {st['target']}）"}, _now())
        runlog.add("emblem", f"{item['name']}：一覧から {len(picks)} 枚を選んだ（{st['have']}/{st['target']} 枚）", "ok", item=item["name"])
        save_progress(sync_progress(prog, load_items()))
    else:
        item = {**item, "_web": a.web or bool(a.query), "_query": a.query}
        run_item(item)


if __name__ == "__main__":
    main()
