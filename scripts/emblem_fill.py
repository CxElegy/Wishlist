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
import datetime as dt
import io
import json
import os
import pathlib
import re
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emblem  # noqa: E402
import emblem_face  # noqa: E402
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
NAMES_V = 11   # 11：種族・役割・名無し（Wyverians・Hunter・Traveler・Manekin）を名簿から外す（emblem.NOT_CHAR）。 10：作品の呼び名の é などの記号を外す（Pokémon → Pokemon：ポケモンの分類 Main characters が見つからず、名簿が空で小元素の並びが直らなかった）。 9：大きな分類（60 人以上）の端、参照が中央値の 1 割未満で記事も短いページ（dota2 の Yasuo・Irelia・John Raider。新キャラ Ringmaster は残す）を名簿・数から外す（emblem.fringe）・記事の長さは続きの返事で 0 に戻らない。 8：名簿の順を見てすぐわかる人から（同じ名前の別の版 (Adventures)・(Origins)・(Masters) は後ろ、emblem.known_first。済みの版面の小元素の並びも名簿の順に、off_roster）。 7：Cast の節を Wikidata の記事（sitelink）からも・名字を足した書き方は同じ人・役の中の <!-- --> を消す・そろっていても版が上がった回は roster（_recount）。6：名前のない端役（Unnamed …）と集まりのページ（分類 Music bands・Gangs）を名簿・数から外す（GTA 6 の 39 人に 12）。 5：5：実写の wiki: の記事を同じ言語でも全部（漫威电影の Avengers: Doomsday が MCU に隠れていた）。 名簿（find_sources・roster）の規則の版。上げると、そろっているキャラの版面も 1 回ずつ名簿を数え直す（2：作品の分類・AniList より分類・実写は出演者、3：実写は wiki: の記事の P161・Cast の節も、4：分類に作品の登場人物 P674 がいるか・手で数えた人数に合う分類・名簿にいない人の小元素を外す、2026-10-25）
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
    return yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"] or []   # test2 を空から始めた直後は「items:」だけ（None）


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


LOGO_WORDS = re.compile(r"\b(?:logo(?:type)?s?|wordmark|emblem|symbol|of|the|and|official|new|old|current|icon|text|black|white|"
                        r"colou?r|horizontal|vertical|full|simple|flat|[23]d|v?\d+|ver(?:sion)?|svg|png|jpe?g|webp|file)\b", re.I)


def own_logo(title, subject):
    """Commons で「名前 logo」を探して当たったファイルが、その名前だけのロゴか。名前とロゴの言葉を除いて何か残れば別のもの
    （「Logo of the Linksys iPhone.svg」＝別の会社の iPhone）。"""
    if not re.search(r"logo|wordmark|emblem", title, re.I):
        return False
    rest = re.sub(r"^(?:File|ファイル):", "", title)
    for tok in sorted(re.split(r"[\s/・（）()]+", subject), key=len, reverse=True):
        if tok:
            rest = re.sub(re.escape(tok), " ", rest, flags=re.I)
    return not re.sub(r"[\W_]+", "", LOGO_WORDS.sub(" ", rest))


def commons_photos(subject, limit=10, logo=False):
    """Commons の検索。logo=True はロゴのファイル（名前に logo・wordmark・emblem、SVG も）だけ。ふだんはロゴ・記号を除いた写真"""
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrsearch": subject, "gsrnamespace": 6,
                                "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 500,
                                "format": "json"})
    pages = (_json(f"https://commons.wikimedia.org/w/api.php?{q}", 4_000_000).get("query") or {}).get("pages", {})
    out = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        if logo:   # ロゴ：前は SKIP_NAMES で logo の名前を落としていたので、「京都 logo」の検索に決済の案内板・電車の写真しか残らなかった
            if not info.get("url") or not re.search(r"\.(svg|png|webp)$", p["title"], re.I) or not re.search(r"logo|wordmark|emblem", p["title"], re.I):
                continue
        elif (not info.get("url") or not re.search(r"\.(jpe?g|png|webp)$", p["title"], re.I) or SKIP_NAMES.search(p["title"])
                or info.get("width", 0) < 300 or info.get("height", 0) < 300):
            continue
        lic = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "")
        out.append({"title": p["title"], "image": info.get("thumburl") or info["url"], "page": info.get("descriptionurl", ""),
                    "license": lic, "area": info["width"] * info["height"]})
    return sorted(out, key=lambda x: -x["area"])[:limit]


# Wikidata の P154・P18 でも小元素にならない画像（ファイル名で）：字だけ（京都の「Kyoto (Chinese characters).svg」）・
# 説明の図（生成AI の「Oversimplification on how AI Model … works.png」）・1950 年より前の写真や絵（大相撲の 1890s・c1860s）
NOT_EMBLEM = re.compile(r"\((?:chinese|japanese) characters\)|\bkanji\b|calligraphy|diagram|flow ?chart|infographic|schematic|"
                        r"\bhow\b.*\bworks?\b|oversimplification|(?:^|[\s(]|\bc)(?:1[0-8]\d\d|19[0-4]\d)s?\b", re.I)


def not_emblem(filename):
    """Wikidata の画像のファイル名が、版面の顔にならないもの（字だけ・図・古い写真）か。"""
    return bool(NOT_EMBLEM.search(filename))


def wikidata_images(query, props=("P154", "P18"), limit=3):
    """Wikidata の主題から、公式ロゴ（P154）と代表画像（P18）。Commons のファイルなのでライセンス付き。
    Commons の全文検索より、主題を取り違えにくく、429 にもなりにくい。"""
    out = []
    qid = re.fullmatch(r"Q\d+", str(query))   # 番号で渡されたら検索しない（「将棋」の名前の検索は別の項目に当たる・何も当たらない）
    for lang in ("en",) if qid else ("en", "ja", "zh"):
        if qid:
            hits = [{"id": query}]
        else:
            q = urllib.parse.urlencode({"action": "wbsearchentities", "search": query, "language": lang, "uselang": lang,
                                        "format": "json", "limit": 2})
            hits = _json(f"https://www.wikidata.org/w/api.php?{q}").get("search", [])
        for h in hits[:1]:
            # 項目の中身は Special:EntityData（CDN のキャッシュから返る。api.php の wbgetentities より 429 になりにくい）
            claims = _json(f"https://www.wikidata.org/wiki/Special:EntityData/{h['id']}.json", 4_000_000)["entities"][h["id"]].get("claims", {})
            for prop in props:
                for c in claims.get(prop, [])[:limit]:
                    fn = (c.get("mainsnak", {}).get("datavalue") or {}).get("value")
                    if isinstance(fn, str) and not not_emblem(fn):
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


HEAD = 5   # 名簿の上から何人は毎回先に集める（主役が後回しにならない）


def subjects(item, kind, hi):
    """収集する対象の名前。emblem_who（メンバー・キャラの名前）があればそれ、なければ種類ごとの決め方。"""
    who = [w for w in item.get("emblem_who") or [] if kind != "character" or not emblem.not_character(w)]   # もうある名簿にも（あつ森の Player・Parents）
    if who and kind in ("character", "group"):   # まだ小元素のいない人から STEP 人。足りない人が多いときは回ごとにずらす（見つからない人で止まらない）
        have = {n for x in item.get("emblem") or [] if isinstance(x, dict) for n in _who_of(x.get("subject"))}
        rest = [w for w in who[:hi] if w not in have]
        redo = {n for s in item.get("emblem_redo") or [] for n in _who_of(s)}   # 管理ページで「別の写真に替える」を押した人は先に
        rest = [w for w in rest if w in redo] + [w for w in rest if w not in redo]
        if len(rest) <= STEP:
            return rest or who[:1]
        # 名簿の上（主役：ちいかわ・ハチワレ・うさぎ）の HEAD 人はいつも先に。残りは回ごとにずらす（見つからない人で止まらない）
        head, tail = rest[:HEAD], rest[HEAD:]
        k = int(time.time() // 3600) * (STEP - len(head)) % len(tail)   # 1 回に試す幅だけ進める（STEP ずつだと 60 人の後ろ半分に届かなかった）
        return (head + tail[k:] + tail[:k])[:STEP]
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
    old = list(item.get("emblem_who") or [])
    who = []
    for x in old:   # 前に入った Player・Parents・同じ人の別の書き方（Tenoch Huerta Mejía）も名簿から外す（新しく足す名前だけでなく）
        if not emblem.not_character(x) and not any(_same_person(y, x) for y in who):
            who.append(x)
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    names, how, cast_roles = [], "", {}
    if item.get("emblem_category") and api:
        gone = set()
        names = emblem.category_top(api, item["emblem_category"], 999, gone)   # 物語の中心にいる（ほかのページから多く参照される）順
        who = [x for x in who if x not in gone]   # 前の名簿に入った集まり（バンド・ギャング）も外す
        how = f"分類「{item['emblem_category']}」の人数"
    elif live_action(item) and (item.get("wikidata") or item.get("wiki")):
        names, cast_roles = live_cast(item, log)   # 実写：名簿は出演者（emblem_who は出演者の名前、役は gather_roles が引く）
        how = "出演者（Wikidata の P161・記事の Cast の節）の人数"
    elif item.get("anilist_id"):
        names = emblem.anilist_main(item["anilist_id"], 50)
        how = "AniList の主役（role MAIN）の人数"
    who = emblem.known_first(who)
    names = emblem.known_first([x for x in names if not emblem.not_character(x)])   # まとめ・一覧・Player・別の作品の姿（Smash Bros・vs.）は人ではない
    if not names:
        return None
    n = len(names)
    add = [x for x in names if not any(_same_person(y, x) for y in who)][:max(0, min(CEIL["character"], n) - len(who))]   # 前の名簿の「Uryuu Ishida」と分類の「Uryū Ishida」は同じ人（2 枚にしない）
    with WRITE_LOCK:
        _set_field(item["name"], "emblem_pool", f"{n}   # 主要な要素の数＝小元素の上限（{how}、scripts/emblem_fill.py の roster）")
        full = emblem.known_first(who + add)   # 別の版（Red (Adventures)）は後ろ。足した名前がその前に入る
        if add or full != old:
            _set_field(item["name"], "emblem_who", json.dumps(full, ensure_ascii=False)
                       + "   # 集める対象（メンバー・キャラ・出演者）")
        roles = {**{k: v for k, v in cast_roles.items() if k in full}, **(item.get("emblem_roles") or {})}   # 記事の「X as Y」の役（手で書いた・前に引いた役が先）
        if roles != (item.get("emblem_roles") or {}):
            _set_field(item["name"], "emblem_roles", json.dumps(roles, ensure_ascii=False) + "   # 出演者 → 役（記事の Cast の節・gather_roles）")
    log(f"  [名簿] {item['name']}：{how} {n} → 上限 {min(CEIL['character'], n)}、名前を {len(add)} 人足した")
    return n


def _same_person(a, b):
    """同じ人か：_name_key が同じ、または 2 語以上の名前の後ろに名字を足しただけ（Tenoch Huerta ＝ Tenoch Huerta Mejía）。"""
    wa, wb = ([_name_key(w) for w in str(x).split()] for x in (a, b))
    s, l = sorted((wa, wb), key=len)
    return _name_key(a) == _name_key(b) or len(s) >= 2 and l[:len(s)] == s


def _name_key(s):
    """名前の比べ方：長音の書き方（ū・uu・ou）と記号の違いを同じに。"""
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.replace("ou", "o").replace("uu", "u"))


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
    emblem.write_atomic(path, "\n".join(lines))


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


def official_cands(item, subj, cands, tried):
    """名簿の取り方の全部の入口（gather・gather_wide・gather_pages・gather_roles）が、Fandom より先に呼ぶ 1 つの口。
    公式サイトの立ち絵を cands に足し、足した枚数を返す（0 でなければ Fandom に行かない）。"""
    n = 0
    for u in emblem.official_for(item, {"subject": subj})[:2]:
        tried["公式サイト"] = tried.get("公式サイト", 0) + 1
        cands.append({"subject": subj, "image": u, "page": emblem.official_site(item), "source": "公式サイト",
                      "why": f"{subj}（公式サイトの立ち絵）", "license": ""})
        n += 1
    return n


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
        wd = item.get("wikidata") if not item.get("emblem_subject") and re.fullmatch(r"Q\d+", str(item.get("wikidata") or "")) else subj
        try:
            logos = wikidata_images(wd, ("P154",))
            add(f"{subj} のロゴ", logos, "Wikidata", "ブランドの顔（公式ロゴ）", 2)
            if not logos and kind == "brand":   # ロゴのない製品（iPhone：P154 なし）は Wikidata の代表画像（P18、製品の絵）
                add(subj, wikidata_images(wd, ("P18",), 2), "Wikidata", "主題を表す画像", 2)
        except Exception as e:
            log(f"  [Wikidata] {e}")
        try:
            add(f"{subj} のロゴ", [r for r in commons_photos(f"{subj} logo", 12, logo=True) if own_logo(r["title"], subj)],
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
                add(subj, wikidata_images(wd, ("P154", "P18")), "Wikidata", "主題を表す画像", 3)
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
        if kind == "character" and not item.get("emblem_people"):
            # 公式サイトの立ち絵が先（A17：公式が先、Fandom の場面画像は最後）。取れた人は Fandom に行かない
            got += official_cands(item, subj, cands, tried)
        if kind == "character" and api and not item.get("emblem_people") and not got:
            try:   # 先に、同じページの透明背景の立ち絵（ゲームの公式イラストなど）。代表画像は漫画のコマ・アニメの場面のことが多い
                r = emblem.cutout_on_page(api, subj)
                if r and page_owner(r[2], subj, item.get("emblem_who")):
                    r = None
                if r:
                    tried["Fandom"] = tried.get("Fandom", 0) + 1
                    cands.append({"subject": subj, "image": r[1], "page": r[2], "source": "Fandom",
                                  "why": f"{subj}（Fandom の公式の立ち絵・透明背景）", "license": ""})
                    got += 1
            except Exception as e:
                log(f"  [Fandom] {subj}：{e}")
            try:
                r = emblem.page_image(api, subj)
                if (other := page_owner(r[1], subj, item.get("emblem_who"))):   # 別の人のページへの転送（Zangetsu (Quincy Powers) → 黒崎一護）
                    raise ValueError(f"{other} のページへの転送")
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


ROLE_WHY = re.compile(r"役の記事|役の写真|作品の動画の場面|作品の記事の剧照|ポスター|キービジュアル")


def is_role_image(x):
    """実写の作品の小元素が「役の姿・作品の画像」か（gather_roles が書いた理由）。出演者の生活の写真は False。"""
    return bool(x.get("work") or ROLE_WHY.search(str(x.get("why") or "")))


def fandom_api(item, strict=False):
    """作品の Fandom（emblem_fandom / emblem_api）。書いていなければ名前・副題（英語名）・記事名から推測して、あるものを使う。
    strict：推測した wiki は名前（Chiikawa Wiki の「chiikawa」）が wiki の名前に入っているときだけ使う（同じ綴りの別の wiki を拾わない）。"""
    if item.get("emblem_api"):
        return item["emblem_api"]
    names = [item.get("emblem_fandom")] if item.get("emblem_fandom") else []
    ascii_kw = [k for k in (item.get("keywords") or []) if re.fullmatch(r"[A-Za-z0-9 .:'&-]{3,40}", str(k))][:4]   # 搜索词の英語名（Chiikawa）
    for t in [item["name"], item.get("subtitle") or ""] + [t for t in wiki_titles(item).values()] + ascii_kw:
        t = re.sub(r"\(.*?\)", "", str(t).lower().replace("×", "x"))
        # 続けた形（chiikawa）・ハイフンの形（spy-x-family）、「:」のあとの副題も（Demon Slayer: Kimetsu no Yaiba → kimetsu-no-yaiba）
        for part in [t] + (t.split(":")[1:] if ":" in t else []):
            for slug in (re.sub(r"[^a-z0-9]", "", part), re.sub(r"[^a-z0-9]+", "-", part).strip("-")):
                if len(slug) >= 3 and slug not in names:
                    names.append(slug)
    for n in names:
        api = f"https://{n}.fandom.com/api.php"
        try:
            site = (_json(f"{api}?action=query&meta=siteinfo&format=json").get("query") or {}).get("general") or {}
            if strict and n != item.get("emblem_fandom") and n.replace("-", "") not in re.sub(r"[^a-z0-9]", "", str(site.get("sitename", "")).lower()):
                continue
            m = re.fullmatch(r"(?:https?:)?//([a-z0-9-]+)\.fandom\.com", str(site.get("server") or ""))
            return f"https://{m.group(1)}.fandom.com/api.php" if m else api   # 転送先の本当の名前（demonslayer → kimetsu-no-yaiba）
        except Exception:
            continue
    return None


CHAR_CATEGORIES = ("Main characters", "Main Characters", "Playable characters", "Playable Characters", "Characters")   # Fandom でよくある分類名（先のほうが主要キャラに近い）


def _sitename(api):
    """wiki の名前（Bleach Wiki）。開けなければ None（書いてあった gtawiki は 404）。"""
    try:
        return str(((_json(f"{api}?action=query&meta=siteinfo&format=json").get("query") or {}).get("general") or {}).get("sitename") or "")
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def work_names(item):
    """作品の英数字の呼び名（名前・副題・記事名・搜索词。「·」「:」で分けた前後も）。分類の名前と突き合わせる。"""
    out = []
    for t in [item["name"], item.get("subtitle") or ""] + list(wiki_titles(item).values()) + list(item.get("keywords") or []):
        t = "".join(c for c in unicodedata.normalize("NFKD", str(t)) if not unicodedata.combining(c))   # Pokémon → Pokemon（é があると英数字の呼び名にならず、own_wiki が外れて分類が見つからなかった）
        for part in re.split(r"\s*[·:：]\s*", re.sub(r"\(.*?\)", "", t)):
            part = part.strip()
            if re.fullmatch(r"[A-Za-z0-9 .'&-]{3,60}", part) and len(_norm(part)) >= 4 and part not in out:
                out.append(part)
    return out


def work_category(api, item):
    """作品の名前の付いたキャラの分類（GTA Wiki の「Characters in GTA VI」）。シリーズ全体の wiki で別の作品のキャラを数えない。"""
    names = work_names(item)
    keys = [_norm(n) for n in names]
    for n in names[:4]:
        q = urllib.parse.urlencode({"action": "query", "list": "search", "srnamespace": 14, "srlimit": 10,
                                    "srsearch": f"{n} characters", "format": "json"})
        try:
            hits = [h["title"].split(":", 1)[-1] for h in _json(f"{api}?{q}")["query"]["search"]]
        except Exception:
            continue
        for c in hits:
            if "character" in c.lower() and any(k in _norm(c) for k in keys):
                return c
    return None


def own_wiki(api, site, item):
    """その作品の wiki か（Bleach Wiki と BLEACH Mirrors High は○、Hello Kitty Wiki とぐでたまは×）。
    ×の wiki の「Characters」はほかの作品のキャラも全部なので名簿にしない。"""
    slug = _norm(re.match(r"https://([^.]+)\.", api).group(1)) if re.match(r"https://([^.]+)\.", api) else ""
    core = _norm(re.sub(r"(?i)\bwiki\b|pedia$", "", site or ""))
    titles = [_norm(n) for n in work_names(item)]
    return any(k and len(k) >= 4 and any(k in w for w in titles) for k in (slug, core))


def wd_cast(qid, get=None, title=None):
    """Wikidata の出演者（P161）の名前（英語、Wikidata の順）。実写の作品の名簿。title=(言語, 記事名) ならその記事の作品の P161。"""
    get = get or _wd_get   # library._wd_get の素の urlopen は emblem を読み込んだあと 403（手元で漫威电影の P161 が引けなかった）
    q = {"sites": f"{title[0]}wiki", "titles": title[1]} if title else {"ids": qid}
    ents = get({"action": "wbgetentities", "props": "claims", **q}).get("entities") or {}
    ent = next((v for k, v in ents.items() if k.startswith("Q")), {})
    ids = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id") for c in (ent.get("claims") or {}).get("P161") or []]
    ids = [i for i in ids if i]
    out = []
    for i in range(0, len(ids), 50):
        ents = get({"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": "labels", "languages": "en"}).get("entities") or {}
        out += [((ents.get(q) or {}).get("labels") or {}).get("en", {}).get("value") for q in ids[i:i + 50]]
    return [n for n in out if n]


HAND_CATEGORIES = ("Heroes",)   # 手で数えた人数があるときだけ見る分類名（dota2 のヒーロー 126 人＝Dota 2 Wiki の Heroes）


def cat_titles(api, cat, limit=500):
    """分類の記事（名前空間 0）の名前。limit 人まで。"""
    q = urllib.parse.urlencode({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{cat}",
                                "cmlimit": limit, "cmnamespace": 0, "format": "json"})
    return [m["title"] for m in _json(f"{api}?{q}")["query"]["categorymembers"]]


def cat_fits(api, cat, leads=(), hand=0):
    """分類が作品のキャラの名簿に使えるか：3 人以上・作品の登場人物（Wikidata P674）がわかればそのうち 1 人は入っている
    （GTA 6 の wiki の「Playable characters」は GTA IV・V の主役だけで Jason・Lucia がいない）・
    手で数えた人数があればその ±10%（dota2 のヒーロー 126：Characters 196 は×、Heroes 127 は○）。"""
    try:
        n = len(cat_titles(api, cat))
        if n < 3 or hand and abs(n - hand) > max(2, hand // 10):
            return False
        if not leads:
            return True
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(leads[:40]), "prop": "categories",
                                    "clcategories": f"Category:{cat}", "redirects": 1, "format": "json"})
        return any(p.get("categories") for p in ((_json(f"{api}?{q}").get("query") or {}).get("pages") or {}).values())
    except Exception:
        return False


def pick_category(api, item, leads=(), hand=0):
    """その wiki で名簿に使う分類：作品の名前の付いた分類 → その作品の wiki ならよくある分類名（手で数えた人数があれば HAND_CATEGORIES も）。
    どれも cat_fits を通ったものだけ。"""
    cands = [c for c in [work_category(api, item)] if c]
    if own_wiki(api, _sitename(api), item):
        cands += list(CHAR_CATEGORIES) + (list(HAND_CATEGORIES) if hand else [])
    return next((c for c in cands if cat_fits(api, c, leads, hand)), None)

CAST_LINE = re.compile(r"^\*+\s*(?:'+)?(?:\[\[([^\]|]+)(?:\|([^\]]+))?\]\]|([A-Z][^\[\]{}\n*]+?))(?:'+)?\s+as\s+(?:'+)?(?:\[\[(?:[^\]|]+\|)?([^\]]+)\]\]|([^,;(\[{\n]+))", re.M)


def wiki_cast(lang, title):
    """Wikipedia の記事の「Cast」の節の「X as Y」→ [(出演者, 役)]（記事の順＝主役が先）。新しい剧で Wikidata に出演者がまだ少ないとき。"""
    base = f"https://{lang}.wikipedia.org/w/api.php?format=json&action=parse&redirects=1&page=" + urllib.parse.quote(title)
    secs = _json(base + "&prop=sections").get("parse", {}).get("sections") or []
    sec = next((s for s in secs if re.match(r"(?i)(main )?cast\b|starring", s.get("line", ""))), None)
    if not sec:
        return []
    text = _json(base + f"&prop=wikitext&section={sec['index']}").get("parse", {}).get("wikitext", {}).get("*", "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)   # 編集者への注意（Steve Rogers<!-- Do NOT add Captain America -->）は役ではない
    out = []
    for m in CAST_LINE.finditer(text):
        actor = re.sub(r"\s*\(.*?\)", "", m.group(2) or m.group(1) or m.group(3) or "").strip()
        role = re.sub(r"\s*\(.*?\)|'+", "", m.group(4) or m.group(5) or "").strip()
        if actor and len(actor.split()) <= 4:
            out.append((actor, role))
    return out


def live_cast(item, log=print):
    """実写の名簿＝出演者：作品の Wikidata の P161 → wiki: の記事の作品の P161（フランチャイズ：漫威电影は Avengers: Doomsday）
    → 記事の「Cast」の節（新しい剧：哈利波特剧集）。同じ人は 1 回（_name_key）。→ (名前, {出演者: 役})"""
    names, roles = [], {}
    arts = [(lang, title) for lang, _, title in (str(w).partition(":") for w in item.get("wiki") or []) if title]   # 同じ言語の記事が 2 つでも全部（wiki_titles は 1 言語 1 つ）
    if not arts and item.get("wikidata"):   # wiki: を書いていない版面（哈利波特剧集）は Wikidata の英語の記事の Cast の節
        try:
            arts = [("en", t) for t in [wd_enwiki(item["wikidata"])] if t]
        except Exception as e:
            log(f"  [名簿] {item['name']}：{e}")
    tries = [lambda: wd_cast(item["wikidata"])] if item.get("wikidata") else []
    tries += [lambda a=a: wd_cast(None, title=a) for a in arts] + [lambda a=a: wiki_cast(*a) for a in arts]
    for f in tries:
        try:
            got = f()
        except Exception as e:
            log(f"  [名簿] {item['name']}：{e}")
            continue
        for x in got:
            a, r = x if isinstance(x, tuple) else (x, "")
            if r and a not in roles:
                roles[a] = r
            names.append(a)
    out = []
    for n in names:
        same = next((o for o in out if _same_person(o, n)), None)
        if same is None:
            out.append(n)
        elif n in roles and same not in roles:
            roles[same] = roles[n]   # 「Tenoch Huerta Mejía as Namor」の役は先に入った「Tenoch Huerta」へ
    return out, {k: v for k, v in roles.items() if k in out}


def wd_enwiki(qid, get=None):
    """Wikidata の項目の英語の Wikipedia の記事名（なければ None）。"""
    get = get or _wd_get
    ent = (get({"action": "wbgetentities", "ids": qid, "props": "sitelinks", "sitefilter": "enwiki"}).get("entities") or {}).get(qid) or {}
    return ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")


def _wd_get(params):
    """Wikidata の API を wikihttp（名乗った UA・間隔・429 の待ち）で。library._wd_get の素の urlopen は、
    emblem を読み込んだあと（sources の ALPN の opener）403 で断られ、GTA 6 の登場人物（P674）が引けず分類を確かめられなかった（#361 のあと）。"""
    import library
    return json.loads(_get(library.WD_API + "?" + urllib.parse.urlencode({**params, "format": "json"})))


def find_sources(item, log=print):
    """キャラの関注項で、小元素の取り方に要るものが書いていなければ規則で探して items.yaml に書く（AI が設計を飛ばしても埋まる、2026-10-20）：
    ① 作品の Fandom（emblem_fandom：Fandom の公式の立ち絵は「確かな取り方」）。書いてあっても開けなければ（gtawiki）探し直す。
       名前からの推測 → Wikidata の Fandom の番号（P4073、なければシリーズ P179 の P4073。ライブラリの版面と同じ）。
    ② キャラの分類（emblem_category：主要キャラの名簿と人数）。作品の名前の付いた分類（Characters in GTA VI）→ その作品の wiki なら
       よくある分類名（CHAR_CATEGORIES）。AniList の番号があっても探す（AniList は主役の数だけ：チェンソーマン 4 人、2026-10-25）。
       分類は cat_fits を通るものだけ：作品の登場人物（Wikidata P674）が 1 人は入っている・手で数えた人数（dota2 126）があればそれに合う。
       前に書いた分類も確かめ、通らなければ（GTA 6 の Playable characters）その分類から入れた名前を名簿から外して探し直す。
    実写（emblem_people）は名簿が出演者なので分類を使わない（roster が Wikidata の出演者を数える）。
    → 書いたら True。"""
    if kind_of(item) != "character" or item.get("emblem_people") or "emblem_category" in item and not item.get("emblem_category"):
        return False   # 分類が空（""）＝前に探して使える分類がなかった
    wd = {}
    if item.get("wikidata"):
        try:
            import library_emblem
            wd = library_emblem.wd_entity(item["wikidata"], _wd_get) or {}
        except Exception as e:
            log(f"  [Fandom] Wikidata：{e}")
    leads = [x for x in wd.get("leads") or [] if not emblem.not_character(x)]
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    site = _sitename(api) if api else None
    if site is None and not item.get("emblem_api"):
        api = None
    old = item.get("emblem_category")
    if old:
        if not leads or api is None or cat_fits(api, old, leads):
            return False   # 手で書いた分類・確かめられた分類はそのまま
        try:
            bad = {_name_key(x) for x in cat_titles(api, old)} - {_name_key(x) for x in leads}
        except Exception:
            bad = set()
        who = [w for w in item.get("emblem_who") or [] if _name_key(w) not in bad]
        log(f"  [分類] {item['name']}：「{old}」に作品の登場人物がいない → 外して探し直す（名簿から {len(item.get('emblem_who') or []) - len(who)} 人外した）")
        with WRITE_LOCK:
            _set_field(item["name"], "emblem_who", json.dumps(who, ensure_ascii=False) + "   # 集める対象（メンバー・キャラ・出演者）")
            _set_field(item["name"], "emblem_pool", f"{len(who)}   # 主要な要素の数（使えない分類を外したあと、scripts/emblem_fill.py の find_sources）")
        item = {**item, "emblem_who": who, "emblem_pool": len(who)}
    hand = int(item.get("emblem_pool") or 0) if not old and not item.get("anilist_id") else 0   # 手で数えた人数（dota2 のヒーロー 126）
    apis = [api] if api else []
    if not item.get("emblem_api"):
        if not apis:
            g = fandom_api({**item, "emblem_fandom": None}, strict=True)
            apis += [g] if g else []
        slug = wd.get("fandom")
        if slug and re.fullmatch(r"[a-z0-9-]+", str(slug)) and f"https://{slug}.fandom.com/api.php" not in apis:
            apis.append(f"https://{slug}.fandom.com/api.php")   # 名前から推した wiki（grand-theft-auto-vi）に使える分類がなければ Wikidata の wiki（gta）
    apis = [a for a in apis if _sitename(a) is not None]
    wrote = bool(old)
    cat, use = None, apis[0] if apis else None
    for a in apis:
        cat = pick_category(a, item, leads, hand)
        if cat:
            use = a
            break
    if use and use != api and not item.get("emblem_api"):
        slug = re.match(r"https://([^.]+)\.fandom\.com", use).group(1)
        with WRITE_LOCK:
            _set_field(item["name"], "emblem_fandom", f"{slug}   # 作品の Fandom（scripts/emblem_fill.py の find_sources が見つけた）")
        log(f"  [Fandom] {item['name']}：{slug}.fandom.com")
        wrote = True
    if cat or old:
        with WRITE_LOCK:
            _set_field(item["name"], "emblem_category", f"{json.dumps(cat or '', ensure_ascii=False)}   # キャラの分類（find_sources）")
        log(f"  [分類] {item['name']}：{cat or '使える分類なし'}")
        wrote = True
    return wrote


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
            cell = l.split("||")[-1]
            links = [m.group(1).strip() for m in link.finditer(cell)]
            if not links:   # 役の列にリンクがなく字だけ（Wookieepedia の Katee Sackhoff：Bo-Katan Kryze<ref …>）。<ref>・{{ }}・'' を除いた字を役の名前の候補に（下で役の記事が演じた人に出演者を書いているものだけ通る）
                plain = re.sub(r"<ref[^>]*/>|<ref.*?(?:</ref>|$)|\{\{.*?\}\}|<[^>]+>|'{2,}", "", cell).strip()
                links = [plain] if re.fullmatch(r"[A-Z][\w'’. -]{2,40}", plain) else []
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


def actor_role_images(api, actor, role, limit=3):
    """出演者の記事に載っている「その人の役の姿」：ファイル名に役の名前（姓か名）がある画像（「Nick Frost as Rubeus Hagrid.jpg」）。
    作り直しの剧（哈利波特剧集）は役の記事の画像が前の映画の役者ばかりなので、この作品の役者の役の写真はここにしかないことが多い。"""
    q = urllib.parse.urlencode({"action": "query", "titles": actor, "prop": "images", "imlimit": 200, "format": "json", "redirects": 1})
    pg = next(iter(_json(f"{api}?{q}")["query"]["pages"].values()))
    titles = [x["title"] for x in pg.get("images", [])]
    q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": f'"{actor}"', "srnamespace": 6, "srlimit": 30, "format": "json"})
    titles += [h["title"] for h in _json(f"{api}?{q}")["query"]["search"] if h["title"] not in titles]   # 記事に貼っていない写真（「HPTV BTS John Lithgow as Dumbledore」）
    words = [w.lower() for w in re.split(r"[\s(),/]+", role) if len(w) >= 3]
    files = [x for x in titles if re.search(r"\.(png|jpe?g|webp)$", x, re.I)
             and not re.search(r"icon|logo|symbol|signature|favicon", x, re.I) and any(w in x.lower() for w in words)]
    return sorted(_files_info(api, files[:20], width=600), key=lambda r: -r["area"])[:limit] if files else []


SINCE_YEARS = 2   # 作品の始まり（Wikidata P580・P577・P571）のこの年数より前に上がった画像 = 前の作品のもの（配役・宣伝は始まりの 2 年前から）


def tied(text, actor, work, since=None):
    """役の画像がこの作品・この出演者のものと言えるか：ファイル名・題名に出演者の名前（姓か名）か作品の略号（Harry Potter → HPTV）がある、
    または Fandom の画像の日付（cb=YYYYMMDD）が since（作品の始まりの SINCE_YEARS 年前、YYYYMMDD）より後。
    作り直しの剧の役の記事の代表画像は前の映画の役者（PadmaPatil.png?cb=20220930 は映画の Padma、剧は 2026-12 から）なので、それだけでは信じない。"""
    u = urllib.parse.unquote(str(text or "")).lower().replace("_", " ")
    tag = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", work or "")).lower() + "tv"
    cb = re.search(r"[?&]cb=(\d{8})", u)
    return (any(w.lower() in u for w in re.split(r"[\s(),/.]+", actor or "") if len(w) >= 3) or len(tag) > 3 and tag in u.replace(" ", "")
            or bool(since and cb and cb.group(1) >= since))


_SINCE = {}


def work_since(item):
    """作品の始まり（Wikidata P580・P577・P571 のいちばん早い日）の SINCE_YEARS 年前 → YYYYMMDD か None。"""
    q = item.get("wikidata")
    if not q:
        return None
    if q not in _SINCE:
        try:
            c = _wd_get({"action": "wbgetentities", "ids": q, "props": "claims"})["entities"][q]["claims"]
            ts = [s["mainsnak"]["datavalue"]["value"]["time"] for p in ("P580", "P577", "P571") for s in c.get(p, []) if s["mainsnak"].get("datavalue")]
            d = min(re.sub(r"\D", "", x[1:11]) for x in ts) if ts else None
            _SINCE[q] = f"{int(d[:4]) - SINCE_YEARS}{d[4:]}" if d else None
        except Exception:
            return None   # 読めないときは控えない（次の回）
    return _SINCE[q]


_REMAKE = {}


def is_remake(item):
    """作り直しの剧か：Wikidata で原作（P144）が同じ別の映像作品（原作の P4969）がある（哈利波特剧集＝映画 8 本と同じ原作）。
    前の映画のない剧（FROM・The Mandalorian）は作品の動画・役の記事の画像も本人なので untied で外さない。読めないときは False（外さない）。"""
    q = item.get("wikidata")
    if not q:
        return False
    if q not in _REMAKE:
        try:
            c = _wd_get({"action": "wbgetentities", "ids": q, "props": "claims"})["entities"][q]["claims"]
            src = [s["mainsnak"]["datavalue"]["value"]["id"] for s in c.get("P144", []) if s["mainsnak"].get("datavalue")]
            n = 0
            if src:
                d = _wd_get({"action": "wbgetentities", "ids": "|".join(src[:5]), "props": "claims"})["entities"]
                n = sum(1 for e in d.values() for s in e.get("claims", {}).get("P4969", [])
                        if s["mainsnak"].get("datavalue") and s["mainsnak"]["datavalue"]["value"]["id"] != q)
            _REMAKE[q] = n > 0
        except Exception:
            return False
    return _REMAKE[q]


def anchor_rows(api, actor):
    """出演者本人の写真（本人確認の基準）：Fandom の出演者の記事の代表画像、なければ Wikidata P18。→ [(画像, ページ)]"""
    if api:
        try:
            src, page = emblem.page_image(api, actor)
            return [(small_url(src), page)]
        except Exception:
            pass
    return [(r["image"], r["page"]) for r in wikidata_images(actor, ("P18",), 1)[:1]]


ASSIGN_MARGIN = 0.08   # 剧照の顔：いちばん近い出演者と 2 番目の差がこれ未満 = だれか決められない（子役どうしは 0.4 前後まで似る）
_ANCHOR_FEAT = {}


def work_stills(api, titles, limit=30):
    """作品の記事（Fandom）に載っている画像：ファイル名にだれが写っているかない剧照（「The Philosopher's Stone HBO Max Still 01」）も。"""
    for title in titles:
        q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "images", "imlimit": 200, "format": "json", "redirects": 1})
        pg = next(iter(_json(f"{api}?{q}")["query"]["pages"].values()))
        files = [x["title"] for x in pg.get("images", []) if re.search(r"\.(png|jpe?g|webp)$", x["title"], re.I)
                 and not re.search(r"icon|logo|symbol|signature|favicon|poster", x["title"], re.I)]
        if files:
            return _files_info(api, files[:limit], width=1600)   # 場面の写真は顔が小さい（600px だと顔の幅 50px 前後で FACE_PX_MIN に落ちる）
    return []


def _anchor_feat(api, actor):
    """出演者の顔の基準の特徴量と画像（取れなければ (None, None)）。同じ回の中では 1 回だけ取る。"""
    if actor not in _ANCHOR_FEAT:
        _ANCHOR_FEAT[actor] = (None, None)
        try:
            rows = anchor_rows(api, actor)
            if rows:
                img = inspect(_get(rows[0][0], 6_000_000))[2]
                with _face_lock:
                    feat, info = face_id.face_info(img)
                if feat is not None and not face_id.photo_problem(info):
                    _ANCHOR_FEAT[actor] = (feat, rows[0])
        except Exception:
            pass
    return _ANCHOR_FEAT[actor]


def assign_stills(api, item, roles, log=print):
    """作品の記事の剧照を、名簿の出演者ぜんぶの顔の基準と比べて、いちばん近い人に割り当てる（cos ≥ face_id.THRESHOLD・2 番目と ASSIGN_MARGIN 以上の差）。
    作り直しの剧（哈利波特剧集）は役の記事も動画も前の映画の役者で、この作品の役の姿は作品の記事の剧照にしかないことが多い。
    → 候補（割り当てた剧照と、その出演者の基準の写真）。"""
    if face_id.engine() is None:
        return []
    stills = work_stills(api, list(wiki_titles(item).values()))
    if not stills:
        return []
    cast = [w for w in item.get("emblem_who") or [] if not emblem.not_character(w)][:rule(item)[3]]
    base = {}
    for actor in cast:
        _check_time()
        feat, row = _anchor_feat(api, actor)
        if feat is not None:
            base[actor] = (feat, row)
    out, got = [], 0
    for r in stills:
        try:
            with _face_lock:
                feat, info = face_id.face_info(inspect(_get(r["image"], 6_000_000))[2])
        except Exception:
            continue
        if feat is None or face_id.photo_problem(info) or not base:
            continue
        sims = sorted(((face_id.similarity(feat, f), a) for a, (f, _) in base.items()), reverse=True) + [(0.0, "")]
        (s1, actor), (s2, _) = sims[0], sims[1]
        if s1 < face_id.THRESHOLD or s1 - s2 < ASSIGN_MARGIN:
            continue
        role = roles.get(actor)
        subj = f"{role}（{actor}）" if role else actor
        if not any(c["subject"] == subj and c.get("anchor") for c in out):
            out.append({"subject": subj, "image": base[actor][1][0], "page": base[actor][1][1], "source": "基準（出演者の写真）",
                        "why": f"{actor} 本人の写真（本人確認の基準。小元素には使わない）", "anchor": True, "anchor_only": True})
        out.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "作品の剧照", "license": r.get("license", ""),
                    "why": f"{subj}：作品の記事の剧照（顔で出演者を照合 cos {s1:.2f}）", "title": r.get("title", "")})
        got += 1
    log(f"  [作品の剧照] {len(stills)} 枚 → 出演者に割り当て {got} 枚（基準 {len(base)}/{len(cast)} 人）")
    return out


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
    since = work_since(item)
    remake = is_remake(item)
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
        try:   # 基準：出演者の記事の写真（選ばない）
            for src, page in anchor_rows(api, actor):
                cands.append({"subject": subj, "image": src, "page": page, "source": "基準（出演者の写真）",
                              "why": f"{actor} 本人の写真（本人確認の基準。小元素には使わない）", "anchor": True, "anchor_only": True})
        except Exception as e:
            log(f"  [基準] {actor}：{e}")
        if role:   # 公式サイトの役の絵も候補に（顔で出演者本人かは後で確かめる。Fandom を飛ばさない）
            official_cands(item, subj, cands, tried)
        if role and api:
            try:   # 出演者の記事の役の写真（この作品のこの役者の役の姿。役の記事は前の作品の役者のことがある）
                rows = actor_role_images(api, actor, role)
                tried["出演者の記事の役の写真"] = tried.get("出演者の記事の役の写真", 0) + len(rows)
                for r in rows:
                    cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "出演者の記事の役の写真",
                                  "why": f"{role}（{actor}）：Fandom の出演者の記事の役の写真", "license": "", "title": r.get("title", "")})
            except Exception as e:
                log(f"  [出演者の記事] {actor}：{e}")
            try:
                rows = role_images(api, role)
                tried["役の記事"] = tried.get("役の記事", 0) + len(rows)
                for r in rows:
                    cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "役の記事",
                                  "why": f"{role}（{actor}）：Fandom の役の記事の{'代表画像' if r.get('infobox') else '剧照'}",
                                  "license": "", "trust_noface": bool(r.get("infobox")), "title": r.get("title", ""),
                                  "untied": remake and not tied(r["image"], actor, work_en, since)})
            except Exception as e:
                log(f"  [役の記事] {role}：{e}")
        try:   # 作品の動画の場面（題名に作品名と役名）。役がわからないときは探さない（出演者名だとインタビューばかり）
            rows = youtube_images(work_en, role, limit=2, scene=True) if role else []
            tried["作品の動画の場面"] = tried.get("作品の動画の場面", 0) + len(rows)
            for r in rows:
                cands.append({"subject": subj, "image": r["image"], "page": r["page"], "source": "作品の動画の場面",
                              "why": f"{role or actor}（{actor}）：作品の動画の場面", "license": r.get("license", ""),
                              "untied": remake and not tied(f"{r['image']} {r.get('title', '')}", actor, work_en, since)})
        except Exception as e:
            log(f"  [動画] {role or actor}：{e}")
    if api:   # 作品の記事の剧照を顔で出演者に（ファイル名に役名がない：哈利波特剧集の HBO Max Still）
        try:
            rows = assign_stills(api, item, roles, log)
            tried["作品の剧照"] = tried.get("作品の剧照", 0) + sum(1 for c in rows if not c.get("anchor"))
            cands += rows
        except OutOfTime:
            raise
        except Exception as e:
            log(f"  [作品の剧照] {e}")
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
            if official_cands(item, subj, cands, tried):   # 公式が先：取れた人は Fandom に行かない
                continue
            if api:   # 絵のキャラ：Fandom のページ名の別の書き方（名だけ・(character) つき）
                for t in {subj.split()[0], f"{subj} (character)"} - {subj}:
                    try:
                        r = emblem.page_image(api, t)
                        if page_owner(r[1], subj, item.get("emblem_who")):   # 名だけで引くと別の人のページ（Zangetsu → 黒崎一護）
                            continue
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
        if kind == "character" and not item.get("emblem_people"):
            official_cands(item, subj, cands, tried)   # 公式の立ち絵は og:image より先
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
    """差分ハッシュ（64 ビット）。透明な切り抜きは灰の上に置いてから測る（透明を黒にすると、背の高い細い立ち絵どうしが同じ形に見えた：呪術廻戦）。"""
    from PIL import Image
    im = img.convert("RGBA")
    g = Image.alpha_composite(Image.new("RGBA", im.size, (128, 128, 128, 255)), im).convert("L").resize((9, 8))
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
REJECT_BITS = 8   # 店長が「違う」で外した絵（emblem_reject_look）との違いがこれ以下 = 同じ絵（網址・大きさ・JPEG の画質が違っても戻さない）。
# 実測（dota2 の Crystal Maiden の元画像）：半分・2 倍・幅 300・JPEG 画質 30〜60 は 0、周り 5% を切ると 6。別のヒーロー 13 人との最小は 24（ヒーローどうしの最小は 18）。8 はその間


def look_hex(img):
    """絵の見た目の鍵（差分ハッシュ 64 ビットを 16 桁の 16 進で）。items.yaml の emblem_reject_look に残す。"""
    return "%016x" % _hash(img)


def look_of(x):
    """外す小元素 x の絵の見た目の鍵。元の画像（source）を取り直して測る（候補は元の画像のまま測るので、切り抜きの webp とは別）。
    取れなければ image（網址でも倉庫の webp でも）。どちらもだめなら None（URL だけの reject になる）。店長（digest.reject_emblems）もお客さま（library_emblem.apply_requests）も同じ。"""
    for u in (x.get("source"), x.get("image")):
        u = str(u or "")
        try:
            if re.match(r"https?://", u):
                return look_hex(emblem.inspect(emblem._get(u, 6_000_000))[2])
            if u:
                from PIL import Image
                return look_hex(Image.open(emblem.EMB_DIR / u.split("/", 1)[1]))
        except Exception:
            continue
    return None


def reject_looks(item):
    """外した絵の鍵（emblem_reject_look）→ 整数のリスト。読めないものは飛ばす。"""
    out = []
    for s in (item or {}).get("emblem_reject_look") or []:
        try:
            out.append(int(str(s), 16))
        except ValueError:
            pass
    return out


def check(cands, log=print, need_face=False, strict=False, reasons=None, reject_looks=()):
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
        if emblem.bad_source(c.get("image") or ""):   # 別の作品・持ち物の絵（大乱闘のフィギュア・Item_）
            drop("別の作品の絵", c)
            continue
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
            if anchor is None or feats[anchor] is None:   # 出演者の顔の基準がない（記事の写真が集合写真：Anjula Murali）：作品・出演者の名前のない役の画像は数えない
                for k, i in enumerate(test):
                    if dl[i].get("untied") and i not in out:
                        drop("別人", dl[i], "役の記事・動画の画像だけ（出演者の顔の基準がなく、ファイル名に作品・出演者の名前もない）")
                        out.add(i)
                        feats[k] = None
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
            if any(bin(h ^ x).count("1") <= REJECT_BITS for x in reject_looks):
                drop("外した絵に似ている", c, "（店長が「違う」で外した絵と同じ見た目）")
                continue
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
    emblem.write_atomic(path, "\n".join(lines))


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
        drop_broken(next((i for i in load_items() if i["name"] == name), item), log)   # 作り直しで縮んだ・読めない前からの小元素も外す
        drop_closeups(next((i for i in load_items() if i["name"] == name), item), log, only={u for x in chosen for u in (x.get("image"), x.get("source")) if u})   # 今回選んだものが顔だけのアップなら外して次の候補へ
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
    good = check(cands, log, need_face=needs_face(item), strict=strict, reasons=reasons, reject_looks=reject_looks(item))
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
PICK_ORDER = ["直接指定", "出演者の記事の役の写真", "作品の剧照", "役の記事", "作品の動画の場面", "作品の主な画像", "AniList", "Fandom", "Wikidata", "Wikipedia", "Wikimedia Commons", "新聞の配図", "公式サイト", "YouTube", "Twemoji", WEB]
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


def _named_in(c):
    """候補の画像のファイル名にその人の名前の語があるか。ないものは「その人の画像」と言えない（GTA 6 の Ernesto→ゲバラの Wikipedia 写真・Phil→公式サイトの宣伝画像）ので、
    確かでない取り方の候補としても数えず、使える画像が 1 枚もない人のまま。"""
    base = re.sub(r"\s*[(（].*?[)）]", "", _base_subject(c.get("subject")))
    words = {_name_key(w) for w in re.split(r"[^\w]+", base) if len(w) >= 3}
    name = urllib.parse.unquote(str(c.get("image") or "").split("?")[0].rsplit("/", 1)[-1])
    toks = {_name_key(w) for w in re.split(r"[^A-Za-z0-9]+|(?<=[a-z])(?=[A-Z])", name) if w}
    return bool(words & toks)


def _base_subject(s):
    return re.sub(r" \d+$", "", str(s or ""))


def _who_of(s):
    """小元素の subject → 名簿（emblem_who）で当たりうる名前の組。実写は「役（出演者）」と書くので出演者も（Harry Potter（Dominic McLaughlin）→ Dominic McLaughlin）。"""
    s = _base_subject(s)
    m = re.fullmatch(r".+（(.+)）", s)
    return {s, m.group(1)} if m else {s}


def page_owner(page, subj, who):
    """Fandom のページの網址 → そのページが名簿の別の人のものなら、その人の名前（なければ None）。
    「Zangetsu (Quincy Powers)」は黒崎一護のページへの転送で、一護の代表画像を斬魄刀の小元素として先に取ってしまい、
    一護本人は「もう使っている画像」で 1 枚も取れなかった（BLEACH Mirrors High）。"""
    m = re.search(r"/wiki/([^#?]+)", str(page or ""))
    if not m:
        return None
    title = urllib.parse.unquote(m.group(1)).replace("_", " ")
    if title.lower().startswith("file:"):
        return None
    key, mine = _name_key(title), {_name_key(subj), _name_key(_base_subject(subj))}
    if not key or key in mine:
        return None
    return next((w for w in who or [] if _name_key(w) == key), None)


def wrong_owner(item, log=print):
    """前からの小元素のうち、ページが名簿の別の人のもの（page_owner）を外す。画像そのものは悪くない（その人の絵）ので emblem_reject には入れない：
    本人が次の回にその画像を取れる。固定（lock）は替えない。→ 外した枚数。"""
    who = item.get("emblem_who") or []
    if kind_of(item) != "character" or live_action(item) or not who:
        return 0
    ems = [x for x in item.get("emblem") or [] if isinstance(x, dict)]
    bad = [x for x in ems if not x.get("lock") and page_owner(x.get("page"), x.get("subject"), who)]
    if not bad:
        return 0
    with WRITE_LOCK:
        emblem.write_item(item["name"], [x for x in ems if not any(x is b for b in bad)], None)
    log(f"  [別の人のページ] {item['name']}：{'、'.join(str(b.get('subject')) + '→' + page_owner(b.get('page'), b.get('subject'), who) for b in bad)}（本人の画像を先に取れるよう外した）")
    return len(bad)


def head_missing(item, n=3):
    """名簿の先頭 n 人（いちばん点数が高い・リンクの多い人）のうち、小元素がいない人。主役が欠けた版面の点検（emb_check E15 と同じ式）。"""
    who = [w for w in item.get("emblem_who") or [] if not emblem.not_character(w)][:n]
    have = {_name_key(k) for x in item.get("emblem") or [] if isinstance(x, dict) for s in _who_of(x.get("subject"))
            for k in (s, re.sub(r"\s*[(（].*?[)）]", "", s))}
    return [w for w in who if _name_key(w) not in have and _name_key(re.sub(r"\s*[(（].*?[)）]", "", w)) not in have]


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
EXHAUSTED_HOURS = 24      # 残りの人が全員「画像のない人」の版面（exhausted）は、候補が増えるのを待つので 1 日おき（1 時間おきに同じ人を試さない）
RETRY_HOURS = 1           # 全部の段で届かなかった関注項は、材料（記事・手がかり）が変わらなければこの時間は飛ばす。
                          # AI を使わないので資源は気にしない（2026-10-22，用户定的：6 時間は待たせすぎ）→ 毎時の後台で毎回やり直す
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
    RETRY_HOURS（1 時間）以内に失敗して材料も変わっていないものは飛ばす。"""
    rows, broken, closing = [], _broken_log(), closeup_state()
    for item in items:
        st = status(item)
        if item["name"] in closing:   # 胸像待ち（1 回 8 人ずつ入れ替え中）：失敗の待ち・そろっている版面でも毎回（待つと 1 日 1 回も進まない）
            rows.append((st["have"] - st["target"], (prog["items"].get(item["name"]) or {}).get("at") or "", item["name"], item))
            continue
        e = prog["items"].get(item["name"]) or {}
        hint = any(item.get(k) for k in ("emblem_fandom", "emblem_api", "emblem_category", "anilist_id", "wikidata"))
        recount = item.get("emblem_category") and not item.get("emblem_pool")   # 分類はあるのに数えられなかった（429）：版を待たずに次の回も
        unbreak_due = any(x.get("v", 1) < BROKEN_V for x in broken.get(item["name"]) or [])   # 前の規則で外した小元素の見直し待ち
        if st["state"] == "ok" and not broken_cuts(item) and not unbreak_due and (st["kind"] != "character" or not hint or e.get("names_v") == NAMES_V and not recount):   # そろっていても名簿を今の規則で 1 回は数える
            continue
        h = _hours_since(e.get("failed_at"), now)
        if (e.get("state") == "failed" and h is not None and h < (EXHAUSTED_HOURS if e.get("exhausted") else RETRY_HOURS) and not os.environ.get("EMBLEM_RETRY_NOW")
                and e.get("material") == material(item) and not broken_cuts(item) and not unbreak_due):   # 材料（新しい記事・手がかり）が変わったら待たない。指紋の記録がない古い失敗も待たない。
            continue                                                            # 壊れた小元素（頭が切れた・ぼやけた）が出ている版面も待たずに外して取り直す
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
            at = (dt.datetime.fromisoformat(e["failed_at"]) + dt.timedelta(hours=EXHAUSTED_HOURS if e.get("exhausted") else RETRY_HOURS)).isoformat(timespec="seconds")
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
    失敗した版面は、これが変わったら（新しい記事・手がかりが増えた）待たずにすぐやり直す。
    規則の版（NAMES_V・BROKEN_V）も入れる：規則を直しても失敗の版面が材料同じで 1〜24 時間待たされ、直したのが本番に効くのが遅れた（#526 のあと The Mandalorian が 04:19 まで待ち）。"""
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
    return hashlib.sha1(json.dumps([n, keys, rule_versions()], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


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
    → {state: ok / failed, note, tried, funnel, steps, material}。全部の段で届かなければ failed（材料が変わるか RETRY_HOURS 後にもう一度）。"""
    found = False
    try:   # 取り方に要るもの（作品の Fandom・キャラの分類）が書いていなければ先に探す
        if find_sources(item, log):
            found = True
            item = next(i for i in load_items() if i["name"] == item["name"])
    except Exception as e:
        log(f"  [取り方] {item['name']}：{e}")
    pooln = int(item.get("emblem_pool") or 0)
    if (item.get("emblem_category") or item.get("anilist_id") or live_action(item) and item.get("wikidata")) and (
            found or item.get("_recount") or not pooln or len(item.get("emblem_who") or []) < min(CEIL.get(kind_of(item), 0), pooln)):
        try:   # 主要な要素の数がまだわからない：先に数える（上限と集める名前が決まる）
            if roster(item, log):
                item = next(i for i in load_items() if i["name"] == item["name"])
        except Exception as e:
            log(f"  [名簿] {item['name']}：{e}")
    if unbreak(item, log):
        item = next(i for i in load_items() if i["name"] == item["name"])
    if off_roster(item, log) | wrong_owner(item, log) | drop_broken(item, log) | untied_roles(item, log) | drop_closeups(item, log) | official_swap(item, log):
        item = next(i for i in load_items() if i["name"] == item["name"])
    if status(item)["state"] == "ok":   # 名簿を数え直しても足りている（名簿を確かめに来ただけ）：集めない
        st = status(item)
        return {"state": "ok", "note": f"名簿を確かめた：{st['have']} / {st['target']} 枚でそろっている", "tried": {}}
    before = status(item)["have"]
    have0 = {n for x in item.get("emblem") or [] if isinstance(x, dict) for n in _who_of(x.get("subject"))}
    queued = len([w for w in item.get("emblem_who") or [] if w not in have0])   # まだいない人の数。STEP を超えれば今回は一部だけ
    if needs_face(item) and face_id.engine() is None:
        return {"state": "failed", "note": "顔のモデルが使えず本人確認ができないので、自動では選ばなかった", "tried": {}}
    tried, reasons, steps = {}, {}, []
    funnel = {"found": 0, "usable": 0, "auto": 0}
    fresh = item
    kind0 = kind_of(item)
    want = subjects(item, kind0, rule(item)[3]) if kind0 in ("character", "group") and item.get("emblem_who") else []   # 今回試す人
    seen = set()   # 使える候補が 1 つでもあった人（外した画像・もう使っている画像だけの人は含めない）
    try:
        for n, (label, fn) in enumerate(STRATEGIES, 1):
            _check_time()
            _live(item["name"], label, n)
            log(f"  ── 段 {n}/{len(STRATEGIES)}：{label}")
            got = {}
            cands = globals()[fn]({**fresh, "_no_web": True}, log, got)
            for k, v in got.items():
                tried[k] = tried.get(k, 0) + v
            good = check(cands, log, need_face=needs_face(item), strict=True, reasons=reasons, reject_looks=reject_looks(item))
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
                    seen.add(_base_subject(c["subject"]))
                    continue
                if not needs_face(item) and c["source"].split("(")[0] not in AUTO_SOURCES.get(kind, ()):
                    why = "確かでない取り方" if kind != "character" or _named_in(c) else "名前の合わない候補"
                elif kind in ("group", "character") and c["subject"] in covered:
                    why = "重複（その人はもういる）"
                elif c["image"] in _have_images(fresh):
                    why = "もう使っている・外した画像"
                else:
                    why = "目標を超える"
                if why not in ("もう使っている・外した画像", "名前の合わない候補"):
                    seen.add(_base_subject(c["subject"]))
                reasons[why] = reasons.get(why, 0) + 1
            if status(fresh)["state"] == "ok":
                break
    finally:
        _live(item["name"], None)
    st = status(fresh)
    added = max(0, st["have"] - before)
    have1 = {n for x in fresh.get("emblem") or [] if isinstance(x, dict) for n in _who_of(x.get("subject"))}
    noimg = [w for w in want if w not in have1 and not _who_of(w) & seen]   # 試したのに使える画像が 1 枚もない人（新作の端役）
    if noimg:
        reasons["画像のない人"] = len(noimg)
    funnel.update(added=added, rejected=reasons)
    path = " → ".join(f"{x['label']} +{x['added']}" for x in steps)
    top = "・".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:3])
    if st["state"] == "ok":
        return {"state": "ok", "note": f"{added} 枚足して目標に届いた（{path}）", "tried": tried, "funnel": funnel, "steps": steps}
    if added and queued > STEP and kind_of(item) in ("character", "group"):   # STEP 人ずつ足している途中：失敗ではなく進行中。次の回に続き
        return {"state": "running", "tried": tried, "funnel": funnel, "steps": steps,
                "note": f"{added} 枚足した（{path}）。あと {st['target'] - st['have']} 枚、次の回に続きの {STEP} 人"}
    left = st["target"] - st["have"]
    only = f"。残り {left} 枚のうち試した {len(noimg)} 人は全員が画像のない人（使える画像が 1 枚もない）" if noimg and len(noimg) == len([w for w in want if w not in have1]) and queued <= len(want) else ""   # 名簿の残り全員を試したときだけ（BLEACH は残り 108 人のうち 10 人で 24 時間待ちになっていた）   # 名簿の残り全員を試したときだけ（BLEACH は残り 108 人のうち 10 人を試しただけで 24 時間待ちになっていた）
    return {"state": "failed", "tried": tried, "funnel": funnel, "steps": steps, "material": material(fresh),
            "exhausted": bool(only),   # 残りの人が全員「画像のない人」＝いまは取れる候補が尽きた（失敗と分けて数える・次は EXHAUSTED_HOURS 後）
            "note": f"{added} 枚足した（{path}）。外した理由：{top or '候補なし'}{only}。新しい記事が来たらすぐ、来なくても {EXHAUSTED_HOURS if only else RETRY_HOURS} 時間後にもう一度"}


def off_roster(item, log=print):
    """キャラの版面で、名簿（emblem_who）にいない人の小元素を外す（名簿が勝つ：dota2 は手で数えたヒーローの名簿に戻したのに、
    分類「Characters」で足した伝承のキャラ 6 枚が残っていた・GTA 6 は使えない分類を外したあとの GTA IV・V の主役）。
    実写は役の名前で書くので見ない。名簿がなければ何もしない。→ 外した枚数。"""
    who = item.get("emblem_who") or []
    if kind_of(item) != "character" or live_action(item) or not who:
        return 0
    keys = {_name_key(w) for w in who if not emblem.not_character(w)}   # 名簿にいても人でない名前（Unnamed Officer 1）は外す
    ems = [x for x in item.get("emblem") or [] if isinstance(x, dict)]
    keep = [x for x in ems if x.get("lock") or _name_key(x.get("subject")) in keys or _name_key(_base_subject(x.get("subject"))) in keys]   # 「Soldier 11」は名前のまま。固定した写真は替えない
    rank = {}
    for i, w in enumerate(who):
        rank.setdefault(_name_key(w), i)
    keep.sort(key=lambda x: rank.get(_name_key(x.get("subject")), rank.get(_name_key(_base_subject(x.get("subject"))), len(rank))))   # 小元素の並びも名簿の順（見てすぐわかる人が先）
    if keep == ems:
        return 0
    with WRITE_LOCK:
        emblem.write_item(item["name"], keep, None)
    log(f"  [名簿] {item['name']}：名簿にいない {len(ems) - len(keep)} 枚を外した・名簿の順に並べた")
    return len(ems) - len(keep) or 1   # 並べ直しだけでも「変えた」


def untied_roles(item, log=print):
    """実写の版面の前からの小元素のうち、役の記事・作品の動画から取ったもので（tied でない）、出演者の顔の基準もないもの（本人と確かめられない）を外す。
    哈利波特剧集 Padma Patil（Anjula Murali）：役の記事の代表画像＝映画の Padma（Afshan Azad）。→ 外した枚数。"""
    if not live_action(item) or face_id.engine() is None or not is_remake(item):
        return 0
    api = fandom_api(item)
    work = re.sub(r"\s*\(.*?\)", "", wiki_titles(item).get("en", "")) or item["name"]
    since = work_since(item)
    bad = []
    for x in item.get("emblem") or []:
        m = re.search(r"（([^（）]+)）\s*\d*$", str(x.get("subject") or "")) if isinstance(x, dict) else None
        if not m or x.get("lock") or not re.search(r"役の記事|作品の動画", str(x.get("why") or "")) or tied(x.get("source"), m.group(1), work, since):
            continue
        try:
            rows = anchor_rows(api, m.group(1))
            info = face_id.face_info(inspect(_get(rows[0][0], 6_000_000))[2])[1] if rows else {}
        except Exception as e:
            log(f"  [基準] {m.group(1)}：{e}")
            continue   # 読めないときは外さない（次の回）
        if info is None or not info or face_id.photo_problem(info):
            bad.append(x)
    if not bad:
        return 0
    keep = [x for x in item.get("emblem") or [] if not any(x is b for b in bad)]
    rej = list(dict.fromkeys(list(item.get("emblem_reject") or []) + [b.get("source") or b["image"] for b in bad]))
    with WRITE_LOCK:
        emblem.write_item(item["name"], keep, None)
        _set_field(item["name"], "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
    log(f"  [外した] {item['name']}：出演者の顔の基準がなく、作品・出演者の名前もない役の画像 {len(bad)} 枚（{'、'.join(b.get('subject', '') for b in bad)}）")
    return len(bad)


def broken_cuts(item):
    """読めない（0 バイト）・切れ端（短い辺 CUT_MIN 未満・横が縦の CUT_WIDE 倍より長い）・頭のてっぺんか額が上の端で切れた・
    写真がぼやけた（emblem.SHARP_MIN）切り抜きの小元素 → [小元素]。
    網页の .emb では 60×10 の紫の帯（漫威电影 Black Panther）・209×45（BLEACH Mirrors High）になる。"""
    from PIL import Image
    bad, photo, small = [], needs_face(item), 0
    for x in item.get("emblem") or []:
        im = str(x.get("image") or "") if isinstance(x, dict) else ""
        p = emblem.sitedir.SITE_DIR / im
        if not im.startswith("emblems/") or x.get("shape") in ("logo", "icon", "badge") or not p.exists():
            continue
        if emblem.bad_source(x):   # 別の作品・持ち物の絵（あつ森の大乱闘のフィギュア・原神の Item_）
            bad.append(x)
            continue
        try:
            im = Image.open(p)
        except Exception:
            bad.append(x)
            continue
        b = x.get("body")
        if (too_small(im, bool(b)) or replace_nf(x)) and small < SMALL_DROP_MAX:   # 1 回に外す小さい画像は版面ごとに SMALL_DROP_MAX 枚まで（dota2 29・BLEACH 28 を一度に外すと版面が空く。補完が追いつく数ずつ）
            small += 1
            bad.append(x)
        elif broken_image(im, photo, whole=bool(b) and len(b) > 1 and b[1] <= 1):
            bad.append(x)
    return bad


SMALL_DROP_MAX = 8   # 前から入っている小さい画像を 1 回に外す上限（版面ごと）


def replace_nf(x):
    """顔なしの 3 分け（emblem_face.none_kind）で ③「絵として成り立たない」（向きを並べた図・小さすぎ）と測られた小元素 = 同じ人の別の絵に替える対象。固定（lock）と全身は替えない。broken_cuts とお客さまの版面（library_emblem.unbroken）が同じ。"""
    return isinstance(x, dict) and x.get("nk") == "replace" and not x.get("lock") and not x.get("body")


def too_small(im, body=False):
    """前から入っている小さい切り抜き（短い辺 < BUST_MIN_SIDE：E18。全身 body は除く）。取るときの下限（save_cut）の前の分を外して emblem_reject → 次の回は大きい幅で取り直す。broken_cuts とお客さまの版面（library_emblem.unbroken）で同じ。"""
    return not body and min(im.size) < emblem.BUST_MIN_SIDE


def broken_image(im, photo, whole=False):
    """切り抜き 1 枚（PIL）が壊れているか：切れ端・上の端の半分以上が人物（TOP_MAX：コマの切り抜き）・頭のてっぺん・額が上の端で切れた・写真がぼやけた。broken_cuts とお客さまの版面（library_emblem）で同じ。"""
    if emblem.is_sliver(*im.size) or not whole and (emblem.head_cut(im) or emblem.top_share(im) > emblem.TOP_MAX or emblem.top_share(im) > emblem.TOP_TOUCH and emblem.forehead_cut(im)):   # whole：公式の全身の絵（body の足の裏が画像の中）は上の端が絵そのもの（ポチタの持ち手）で、枠で切れたのではない   # 頭のてっぺん・額まで切れた前からの切り抜き（check_whole と同じ：額は上の端に TOP_TOUCH 以上当たっているときだけ見る。The Mandalorian Gideon 1.0%・Mayfeld 0.3% は頭が全部入っている）
        return True
    if photo and emblem.faceless_scrap(im):   # 顔がなく髪・額だけの切れ端（哈利波特剧集 Hermione 194×92）
        return True
    if emblem.other_faces(im, ratio=emblem.CROWD_H):   # 2 人が並んだ切り抜き（BLEACH Mirrors High・呪術廻戦・A2O LITE：点検 E11）
        return True
    if emblem.flat_flaw(im):   # 形の傷：左右・上の端の直線の切り口、凹みすぎ（半身に切り落とせるものは drop_broken の repair_flat が先に直す）
        return True
    fq = emblem.face_sharp(im) if photo else None   # 写真のぼやけ（拡大した剧照）。顔の幅は書き出したあとは縮んでいるので見ない
    return bool(fq and fq[1] < emblem.SHARP_MIN)


BROKEN_V = 10   # 10：顔なしの ③（図・小さすぎ：nk = replace）を替える対象に（replace_nf）。 9：公式の全身の絵（body の足の裏が画像の中）は上の端の検査を外し（ポチタ・Crystal Maiden）、体の絵を作り直せるよう外した元の画像の札を解く。 8 以前： broken_cuts の規則の版。上げると前の版で外した小元素を今の規則で見直す（unbreak）。7：2 人が並んだ切り抜き（other_faces・CROWD_H）を足した。6：別の作品・持ち物の絵（BAD_SOURCE）と同じ画像（drop_same）を足した。3：顔のない髪・額だけの切れ端（faceless_scrap）を足した。2：額の判定を上の端に当たったときだけに（#389 で頭が全部入った The Mandalorian 2 枚を外した）。4：形の傷（emblem.flat_flaw）を足した。5：凹みの閾値 0.45→0.30（翼・稲妻の小元素を戻す）

RULE_VERSION_NAMES = ("NAMES_V", "BROKEN_V")   # 規則の版は 1 か所：上がると失敗の待ちを解く（店長 material・お客さま library_emblem.due）。*_V を足したらここにも（tests が拦める）


def rule_versions():
    return {n: globals()[n] for n in RULE_VERSION_NAMES}


CLOSE_W = 0.45         # 顔の幅 ÷ 画像の幅がこれを超える = 顔だけのアップ（髪から顎まで。小元素は胸像：BLEACH の黒崎一護 372×519 は顔の幅 54〜68%）
SHOULDER_MIN = 0.15    # 顔の下端から下の余白 ÷ 画像の高さがこれ未満 = 肩・胸が写っていない（一護 5%・チェーンソーマンなどの胸像は 20% 以上）
CLOSE_HOLD = 0.5       # 1 版面でこの割合以上が当たるときは、前からの小元素は外さず報告だけ（BLEACH Mirrors High 52/92：Fandom のページ画像が顔だけのアップ）


def closeup_of(im):
    """切り抜き 1 枚（PIL）が「顔だけのアップ」か → True / False / None（顔が測れない：アニメ絵で検出できない・物・覆面。落とさず数に出す）。
    顔の測りは emblem_face.measure（fs・top）と、同じ検出器の箱（emblem_face._boxes）の幅を呼ぶだけ（書き換えない）。"""
    import emblem_face
    f = emblem_face.measure(im)
    if not f[0]:
        return None
    w, h = im.size
    box = min((b for b in emblem_face._boxes(im) if h and abs(b[3] / h - f[0]) < 0.003), key=lambda b: abs(b[3] / h - f[0]), default=None)
    face_w = box[2] / w if box and w else 0
    return face_w > CLOSE_W or 1 - f[1] - f[0] < SHOULDER_MIN


def closeup_cuts(item, only=None):
    """今ある小元素（人物の切り抜き・全身 body は除く）のうち顔だけのアップ → ([小元素], 顔が測れない枚数, 調べた枚数)。only = 元の画像の組を渡すと、それだけ。"""
    from PIL import Image
    bad, nof, n = [], 0, 0
    for x in item.get("emblem") or []:
        im = str(x.get("image") or "") if isinstance(x, dict) else ""
        p = emblem.sitedir.SITE_DIR / im
        if not im.startswith("emblems/") or x.get("shape") in ("logo", "icon", "badge") or x.get("body") or x.get("lock") or not p.exists():
            continue
        if only is not None and (x.get("source") or im) not in only and im not in only:
            continue
        try:
            r = closeup_of(Image.open(p))
        except Exception:
            continue
        n += 1
        if r is None:
            nof += 1
        elif r:
            bad.append(x)
    return bad, nof, n


CLOSE_TRIES = 3        # 胸像の代わりを探して取れなかった回数がこれに届いたら、顔だけのアップを外す（段階的な入れ替え。名簿の上位 CLOSE_TOP 人は外さず探し続ける）
CLOSE_TOP = 12         # 名簿の上位（主役）：3 回で外さず、最後まで胸像を探す
CLOSE_PER_ROUND = 8    # 1 回の掃除で胸像を探す人数（rembg で切るので重い）。回数の少ない人・名簿の上の人から
CLOSE_STATE = "emblem_closeup.json"   # state/：版面 → {人: {n: 探して取れなかった回数}}。ここにいる版面は、当たる枚数が半分を割っても段階的なまま


def closeup_state(d=None):
    """state/emblem_closeup.json（版面 → {人: {n}}：顔だけのアップで胸像の代わりを探している人）。d を渡すと書く。"""
    p = ROOT / "state" / CLOSE_STATE
    if d is None:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def closeup_eta_state(d=None):
    """state/emblem_closeup_eta.json（版面 → close_eta の辞書：待ちが終わる見込み）。d を渡すと書く。"""
    p = ROOT / "state" / "emblem_closeup_eta.json"
    if d is None:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def close_order(subjects, who, tries):
    """胸像を探す順：探した回数が少ない人 → 名簿の上の人（一護が先）。→ [subject]"""
    rank = {}
    for i, w in enumerate(who or []):
        rank.setdefault(_name_key(w), i)
    r = lambda s: rank.get(_name_key(s), rank.get(_name_key(re.sub(r"\s*[(（].*?[)）]", "", _base_subject(s))), 10 ** 6))
    return sorted(subjects, key=lambda s: (tries.get(s, 0), r(s)))


def close_round(subjects, who, tries):
    """この回に胸像を探す人：名簿の上位 CLOSE_TOP 人は毎回（一護が先・巡回に入れない）＋ほかは回数の少ない順に CLOSE_PER_ROUND 人。"""
    order = close_order(subjects, who, tries)
    top = [s for s in close_order(subjects, who, {}) if close_top(s, who)]   # 名簿の順（一護が先）
    return top + [s for s in order if s not in top][:CLOSE_PER_ROUND]


CLOSE_CRON_MIN = 47   # background.yml の毎時 47 分（JST も同じ分）


def close_next_dt(now=None):
    """次の後台の回の時刻（JST）。"""
    now = (now or dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))).astimezone(dt.timezone(dt.timedelta(hours=9)))
    nxt = now.replace(minute=CLOSE_CRON_MIN, second=0, microsecond=0)
    if nxt <= now:
        nxt += dt.timedelta(hours=1)
    return nxt


def close_next_run(now=None):
    """次の後台の回の時刻（JST の 'HH:MM'）。"""
    return close_next_dt(now).strftime("%H:%M")


def close_eta(mine, who, now=None):
    """胸像待ち 1 版面の見込み。mine = {人: {n}}。→ {waiting, top, rounds, next}：
    top = 名簿の上位（毎回探して外さない）の待ち人数、rounds = 上位以外が全員外れるまであと約何回（1 回 CLOSE_PER_ROUND 人・足りない回数の合計 ÷ 8）。"""
    top = [s for s in mine if close_top(s, who)]
    rest = [s for s in mine if s not in top]
    need = sum(max(0, CLOSE_TRIES - int((mine[s] or {}).get("n") or 0)) for s in rest)
    rounds = -(-need // CLOSE_PER_ROUND)
    done = (close_next_dt(now) + dt.timedelta(hours=max(rounds - 1, 0))).isoformat(timespec="minutes") if rounds else None   # 上位以外が全員外れる見込み（上位だけ残るなら None）
    return {"waiting": len(mine), "top": len(top), "rounds": rounds, "next": close_next_run(now), "done": done}


def close_plan(tries, who, now=None):
    """胸像待ち 1 版面の見込みを保存する形に：tries = {人: 探して取れなかった回数}。→ ({人: 次に試す見込み時刻 ISO}, close_eta の辞書)。
    上位 CLOSE_TOP 人は次の回、ほかは回数の少ない順に 1 回 CLOSE_PER_ROUND 人ずつ 1 時間おき。店長（state/）もお客さま（boards.config）も同じ式。"""
    nxt = close_next_dt(now)
    top = [s for s in tries if close_top(s, who)]
    rest = [s for s in close_order(list(tries), who, tries) if s not in top]
    at = {s: nxt for s in top}
    at.update({s: nxt + dt.timedelta(hours=i // CLOSE_PER_ROUND) for i, s in enumerate(rest)})
    return {s: v.isoformat(timespec="minutes") for s, v in at.items()}, close_eta({s: {"n": n} for s, n in tries.items()}, who, now)


def close_line(name, mine, who, now=None):
    e = close_eta(mine, who, now)
    return f"{name}：胸像待ち {e['waiting']} 人（上位 {e['top']} 人は毎回探す）・次の回 {e['next']}・上位以外を外すまであと約 {e['rounds']} 回"


def close_top(subject, who):
    """名簿の上位 CLOSE_TOP 人か（3 回で外さない人）。"""
    keys = {_name_key(w) for w in (who or [])[:CLOSE_TOP]}
    return _name_key(subject) in keys or _name_key(re.sub(r"\s*[(（].*?[)）]", "", _base_subject(subject))) in keys


def bust_fields(item, x, url, slug, fs):
    """胸像に入れ替えた小元素の書き込み分（店長・お客さま共通）。fs は公式の立ち絵〔顔が測れず上半身に切った〕のとき None → 書かない（顔は測り直しで入る）。"""
    off = urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(emblem.official_site(item) or "").netloc
    y = {"image": f"emblems/{slug}.webp", "source": url, "shape": "cutout",
         "why": f"{x['subject']}（{'公式サイトの絵' if off else 'Fandom のページの胸像'}：顔だけのアップの代わり）"}
    if fs is not None:
        y["fs"] = fs
    return y


def bust_replacement(item, x, skip, log=print, orig=None):
    """顔だけのアップ x の代わりの胸像を、同じ Fandom のページの別の画像（公式イラスト・ギャラリーのアニメの立ち絵）から探す。
    外した画像・今ある画像（skip）は探さない。顔だけのアップ・壊れた切り抜きはまた外す。
    質の下限：短い辺 emblem.BUST_MIN_SIDE 未満・ぼやけたもの・元（orig：PIL）より質が上がらないものは取らない（emblem.better_cut）。→ (網址, 切り抜き画像, fs) か None。"""
    api = item.get("emblem_api") or (f"https://{item['emblem_fandom']}.fandom.com/api.php" if item.get("emblem_fandom") else None)
    official = emblem.official_for(item, x)
    if not api and not official:
        return None
    m = re.match(r"^https://[^/]+/wiki/(.+)$", str(x.get("page") or ""))
    title = urllib.parse.unquote(m.group(1)).replace("_", " ") if m and not m.group(1).lower().startswith("file:") else _base_subject(x["subject"])
    skip = set(skip)
    for _ in range(3):
        try:
            got = emblem.find_bust(api, title, word=re.split(r"[\s(]", _base_subject(x["subject"]))[0], limit=6, skip=skip, orig=orig, official=official)
        except Exception as e:
            log(f"  [胸像] {x['subject']}：{e}")
            return None
        if not got or (got[2] is None and got[0] not in official):   # fs なしは公式の立ち絵（顔が測れないアニメ絵を上半身に切った）だけ
            return None
        if closeup_of(got[1]) is not True and not broken_image(got[1], False):
            return got
        skip.add(got[0])
    return None


def stage_closeups(item, bad, log=print):
    """半分以上が顔だけのアップの版面（BLEACH Mirrors High 52/92）の段階的な入れ替え。
    ① 今ある人の胸像の代わりを探す（1 回 CLOSE_PER_ROUND 人。回数の少ない人・名簿の上の人から、一護が先） ② 取れた人から入れ替える（取れるまでは元のまま）
    ③ 取れなかった回数が CLOSE_TRIES に届いた人は顔だけのアップを外す（名簿の上位 CLOSE_TOP 人は外さず探し続ける）。→ (入れ替えた人数, 外した人数)"""
    name = item["name"]
    who = item.get("emblem_who") or []
    st = closeup_state()
    mine = st.setdefault(name, {})
    cur = {b["subject"] for b in bad}
    for s in [s for s in mine if s not in cur]:
        del mine[s]
    tries = {s: int((mine.get(s) or {}).get("n") or 0) for s in cur}
    skip = {u for u in item.get("emblem_reject") or []} | {u for x in item.get("emblem") or [] if isinstance(x, dict) for u in (x.get("image"), x.get("source")) if u}
    by = {b["subject"]: b for b in bad}
    swapped, dropped = {}, []
    for s in close_round(cur, who, tries):   # 上位 12 人は毎回・ほかは 1 回 8 人
        try:
            _check_time()
        except OutOfTime:
            break
        x = by[s]
        try:
            from PIL import Image
            orig = Image.open(emblem.sitedir.SITE_DIR / str(x["image"]))
            orig.load()
        except Exception:
            orig = None
        got = bust_replacement(item, x, skip, log, orig=orig)
        if got:
            swapped[s] = got
            mine.pop(s, None)
        else:
            mine[s] = {"n": tries[s] + 1}
            if mine[s]["n"] >= CLOSE_TRIES and not close_top(s, who):
                dropped.append(x)
                mine.pop(s, None)
    eta = closeup_eta_state()
    if mine:   # 各人の次に試す見込みと版面の見込みを保存（管理ページ・点検 E20 が読む）
        at, eta[name] = close_plan({s: int(v.get("n") or 0) for s, v in mine.items()}, who)
        for s, v in at.items():
            mine[s]["next"] = v
    else:
        st.pop(name, None)
        eta.pop(name, None)
    if swapped or dropped:
        slugs = {}
        rows = []
        for x in item.get("emblem") or []:
            if not isinstance(x, dict):
                rows.append(x)
            elif x.get("subject") in swapped:
                url, out, fs = swapped[x["subject"]]
                slug = emblem.slugify(name, x["subject"])
                emblem.save_cut(out, slug)
                slugs[x["subject"]] = x.get("source") or x["image"]
                y = {k: v for k, v in x.items() if k not in ("face", "fs", "crop", "upper", "ar")}
                y.update(bust_fields(item, x, url, slug, fs))
                rows.append(y)
            elif not any(x is d for d in dropped):
                rows.append(x)
        rej = list(dict.fromkeys(list(item.get("emblem_reject") or []) + list(slugs.values()) + [d.get("source") or d["image"] for d in dropped]))
        redo = list(dict.fromkeys(list(item.get("emblem_redo") or []) + [d["subject"] for d in dropped if d.get("subject")]))
        with WRITE_LOCK:
            emblem.write_item(name, rows, None)
            _set_field(name, "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
            if dropped:
                _set_field(name, "emblem_redo", json.dumps(redo, ensure_ascii=False) + "   # 別の写真に替える人（次の集めで先に）")
    with WRITE_LOCK:
        if swapped:   # 入れ替えた絵はすぐ顔を測る（face を外して書いたまま回が終わると、測っていない小元素が残る）
            emblem_face.measure_item(next((i for i in load_items() if i["name"] == name), item), log)
        closeup_state(st)
        closeup_eta_state(eta)
    left = len(cur) - len(swapped) - len(dropped)
    if mine:
        log("  [胸像待ち] " + close_line(name, mine, who))
    log(f"  [胸像待ち] {name}：胸像に入れ替え {len(swapped)}（{'、'.join(swapped)}）・{CLOSE_TRIES} 回で外した {len(dropped)}・まだ待ち {left}（うち探した回数が {CLOSE_TRIES} 回以上の上位 {sum(1 for s in mine if mine[s]['n'] >= CLOSE_TRIES)}）")
    return len(swapped), len(dropped)


OFFICIAL_PER_ROUND = 4   # 1 回の掃除で Fandom から公式に取り直す人数（rembg で切るので重い）


def fandom_rows(item):
    """取り直しの対象 = 点検 E21 が数える人：character の版面で、出どころが Fandom・固定でなく、公式サイトに同じ人の立ち絵がある小元素。"""
    if item.get("emblem_kind") != "character" or item.get("emblem_people"):
        return []
    return [x for x in item.get("emblem") or [] if isinstance(x, dict) and emblem.fandom_sourced(x) and not x.get("lock")
            and x.get("shape") == "cutout" and emblem.official_for(item, x)]


def official_swap(item, log=print):
    """前に Fandom から取った小元素（規則「公式が先」の前の分）を、公式サイトの立ち絵に取り直す（胸像の入れ替えと同じ入れ替え方：
    取れた人から入れ替え・取れなければ元のまま。元より質が下がるものは取らない）。1 回 OFFICIAL_PER_ROUND 人。→ 入れ替えた人数。"""
    rows = fandom_rows(item)
    if not rows:
        return 0
    name = item["name"]
    skip = {u for u in item.get("emblem_reject") or []} | {u for x in item.get("emblem") or [] if isinstance(x, dict) for u in (x.get("image"), x.get("source")) if u}
    swapped = {}
    for x in rows[:OFFICIAL_PER_ROUND]:
        try:
            _check_time()
        except OutOfTime:
            break
        try:
            from PIL import Image
            orig = Image.open(emblem.sitedir.SITE_DIR / str(x["image"]))
            orig.load()
        except Exception:
            orig = None
        try:
            got = emblem.find_bust(None, _base_subject(x["subject"]), word=re.split(r"[\s(]", _base_subject(x["subject"]))[0], skip=skip, orig=orig,
                                   official=emblem.official_for(item, x))
        except Exception as e:
            log(f"  [公式へ] {x['subject']}：{e}")
            continue
        if got and closeup_of(got[1]) is not True and not broken_image(got[1], False):
            swapped[x["subject"]] = got
    if not swapped:
        return 0
    rows_out = []
    for x in item.get("emblem") or []:
        if isinstance(x, dict) and x.get("subject") in swapped and "Fandom" in (x.get("why") or ""):
            url, out, fs = swapped[x["subject"]]
            slug = emblem.slugify(name, x["subject"])
            emblem.save_cut(out, slug)
            y = {k: v for k, v in x.items() if k not in ("face", "fs", "crop", "upper", "ar", "nfv", "nk", "bb")}
            y.update(image=f"emblems/{slug}.webp", source=url, page=emblem.official_site(item), shape="cutout", why=f"{x['subject']}（公式サイトの立ち絵：Fandom から取り直し）")
            if fs is not None:
                y["fs"] = fs
            rows_out.append(y)
        else:
            rows_out.append(x)
    with WRITE_LOCK:
        emblem.write_item(name, rows_out, None)
        emblem_face.measure_item(next((i for i in load_items() if i["name"] == name), item), log)
    log(f"  [公式へ] {name}：Fandom から公式の立ち絵に取り直し {len(swapped)}（{'、'.join(swapped)}）・まだ Fandom {len(rows) - len(swapped)}")
    return len(swapped)


def drop_closeups(item, log=print, only=None):
    """顔だけのアップの小元素を外す：元の画像は emblem_reject（二度と選ばない）、その人は emblem_redo（次の回に同じ人の別の写真を先に）。
    取るとき（commit の直後、only = 今回選んだ元の画像）は無条件。前からのもの（only なし）は、1 版面の CLOSE_HOLD 以上が当たる版面（BLEACH Mirrors High
    52/92）は段階的な入れ替え（stage_closeups：胸像が取れた人から入れ替え・取れなくて CLOSE_TRIES 回で外す）。顔が測れないものは落とさず数に出す。
    固定（lock）は替えない。→ 外した・入れ替えた枚数。"""
    if kind_of(item) not in ("person", "group", "character"):
        return 0
    bad, nof, n = closeup_cuts(item, only)
    if nof:
        log(f"  [顔だけのアップ] {item['name']}：顔が測れない {nof} 枚は落とさない（アニメ絵など）")
    if not bad:
        if only is None and item["name"] in closeup_state():
            with WRITE_LOCK:
                d = closeup_state()
                d.pop(item["name"], None)
                closeup_state(d)
        return 0
    total = len([x for x in item.get("emblem") or [] if isinstance(x, dict)])
    if only is None and total and (len(bad) / total >= CLOSE_HOLD or item["name"] in closeup_state()):
        return sum(stage_closeups(item, bad, log))
    keep = [x for x in item.get("emblem") or [] if not any(x is b for b in bad)]
    rej = list(dict.fromkeys(list(item.get("emblem_reject") or []) + [b.get("source") or b["image"] for b in bad]))
    redo = list(dict.fromkeys(list(item.get("emblem_redo") or []) + [b["subject"] for b in bad if b.get("subject")]))
    with WRITE_LOCK:
        emblem.write_item(item["name"], keep, None)
        _set_field(item["name"], "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
        _set_field(item["name"], "emblem_redo", json.dumps(redo, ensure_ascii=False) + "   # 別の写真に替える人（次の集めで先に）")
    log(f"  [外した] {item['name']}：顔だけのアップ {len(bad)} 枚（{'、'.join(str(b.get('subject')) for b in bad)}）→ 胸像を探し直す")
    return len(bad)


def _broken_log(d=None):
    """state/emblem_broken.json（版面 → [{v, emblem}]：drop_broken が外した小元素）。d を渡すと書く。"""
    p = ROOT / "state" / "emblem_broken.json"
    if d is None:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def unbreak(item, log=print):
    """前の版（v < BROKEN_V）の broken_cuts で外した小元素を今の規則で見直し、外れないもの（画像が残り、同じ人がまだいない）を戻す。
    emblem_reject からも抜く。→ 戻した枚数。"""
    name = item["name"]
    with WRITE_LOCK:
        d = _broken_log()
        ents = d.get(name) or []
        old = [e for e in ents if e.get("v", 1) < BROKEN_V]
        if not old:
            return 0
        have = {_name_key(x.get("subject")) for x in item.get("emblem") or [] if isinstance(x, dict)}
        back = []
        for e in old:
            x = e["emblem"]
            if (_name_key(x.get("subject")) not in have and (emblem.sitedir.SITE_DIR / str(x.get("image"))).exists()
                    and not broken_cuts({**item, "emblem": [x]}) and not closeup_cuts({**item, "emblem": [x]})[0]):   # 顔だけのアップ（8）は戻さない
                back.append(x)
                have.add(_name_key(x.get("subject")))
        d[name] = [e for e in ents if e not in old] + [{**e, "v": BROKEN_V} for e in old if e["emblem"] not in back]
        _broken_log(d)
        free = {(e["emblem"].get("source") or "") for e in old if e["emblem"] not in back and e["emblem"].get("body") and _name_key(e["emblem"].get("subject")) not in have and not closeup_cuts({**item, "emblem": [e["emblem"]]})[0]}   # 体の絵は元の画像（公式の全身）から今の規則で切り直す：前の規則の切り口で外れた画像の札を解く
        if not back and not free:
            return 0
        src = {b.get("source") or b["image"] for b in back} | free
        emblem.write_item(name, list(item.get("emblem") or []) + back, None)
        _set_field(name, "emblem_reject", json.dumps([u for u in item.get("emblem_reject") or [] if u not in src], ensure_ascii=False)
                   + "   # 目で見て・検査で外した画像。自動補完は選ばない")
    log(f"  [戻した] {name}：前の規則で外した小元素 {len(back)} 枚（{'、'.join(b.get('subject', '') for b in back)}）")
    return len(back)


def repair_flat(item, log=print):
    """前からの切り抜きの、左右の端の直線の切り口を、切り口が始まる行で下を切り落として半身に直す（emblem.trim_flat）。
    直せないもの・全身の目印（body）のあるもの・読めないものは触らない（broken_cuts が外す）。顔の割合 fs も測り直す。→ 直した枚数。"""
    from PIL import Image
    fixed = []
    for x in item.get("emblem") or []:
        im = str(x.get("image") or "") if isinstance(x, dict) else ""
        p = emblem.sitedir.SITE_DIR / im
        if not im.startswith("emblems/") or x.get("shape") in ("logo", "icon", "badge") or x.get("body") or not p.exists():
            continue
        try:
            img = Image.open(p).convert("RGBA")
            if not emblem.flat_flaw(img):
                continue
            out = emblem.trim_flat(img)
            if out.size == img.crop(img.getchannel("A").getbbox()).size:
                continue
            with WRITE_LOCK:
                emblem.save_cut(out, p.stem, 0)   # 既にある画像の整え直し（小さいものは broken_image が外す）
        except Exception:
            continue
        f = emblem.face_box(out)
        if x.get("fs") and f:
            x["fs"] = round(f[3] / out.height, 3)
        fixed.append(x)
    if fixed:
        with WRITE_LOCK:
            emblem.write_item(item["name"], item["emblem"], None)
        log(f"  [直した] {item['name']}：左右の直線の切り口を半身に {len(fixed)} 枚（{'、'.join(b.get('subject', '') for b in fixed)}）")
    return len(fixed)


def same_pics(emblems, load):
    """同じ画像の小元素（後のほう）→ (同じファイル, 同じ見た目で別ファイル)。同じ image・同じ元のファイル（file_key）= 前の書き込みの重複（Vaundy 3 本が同じ vaundy-vaundy.webp）、
    差分ハッシュが SAME_BITS 以下 = 別の名前で同じ絵（原神の Item_Stella_Fortuna が 3 人に）。固定（lock）は落とさない。load(x) → PIL か None。"""
    files, looks, seen, hashes = [], [], set(), []
    for x in emblems:
        if not isinstance(x, dict):
            continue
        ks = {k for k in (x.get("image"), file_key(x.get("source")) if x.get("source") else None) if k}
        if ks & seen:
            if not x.get("lock"):
                files.append(x)
            continue
        seen |= ks
        im = None if x.get("shape") in ("logo", "icon") else load(x)
        if im is None:
            continue
        h = _hash(im)
        if any(bin(h ^ y).count("1") <= SAME_BITS for y in hashes):
            if not x.get("lock"):
                looks.append(x)
            continue
        hashes.append(h)
    return files, looks


def drop_same(item, log=print):
    """同じ画像の小元素の後ろを外す（same_pics）。同じファイルは emblem_reject に入れない（残すほうと同じ網址）、見た目だけ同じものは外して次の候補へ。→ 外した枚数。"""
    from PIL import Image

    def load(x):
        p = emblem.sitedir.SITE_DIR / str(x.get("image") or "")
        try:
            return Image.open(p) if str(x.get("image")).startswith("emblems/") and p.exists() else None
        except Exception:
            return None
    files, looks = same_pics(item.get("emblem") or [], load)
    if not files and not looks:
        return 0
    gone = files + looks
    keep = [x for x in item.get("emblem") or [] if not any(x is b for b in gone)]
    rej = list(dict.fromkeys(list(item.get("emblem_reject") or []) + [b.get("source") or b["image"] for b in looks]))
    with WRITE_LOCK:
        emblem.write_item(item["name"], keep, None)
        if looks:
            _set_field(item["name"], "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
    log(f"  [外した] {item['name']}：同じ画像の小元素 {len(gone)} 枚（{'、'.join(b.get('subject', '') for b in gone)}）")
    return len(gone)


def drop_broken(item, log=print):
    """broken_cuts を外し、元の画像を emblem_reject に（次は同じ人の次の候補）。→ 外した枚数。直せる形の傷は先に repair_flat で直す。同じ画像（drop_same）も。"""
    repair_flat(item, log)
    n = drop_same(item, log)
    if n:
        item = next((i for i in load_items() if i["name"] == item["name"]), item)
    with WRITE_LOCK:   # 顔の大きさを測る（新しい小元素・画像が替わったもの）：表示で顔をそろえる材料（emblem_face）。店長もお客さまの版面も同じ道
        emblem_face.measure_item(next((i for i in load_items() if i["name"] == item["name"]), item), log)
    bad = [b for b in broken_cuts(item) if not b.get("lock")]   # 固定した写真は替えない
    if not bad:
        return n
    with WRITE_LOCK:
        d = _broken_log()
        d.setdefault(item["name"], []).extend({"v": BROKEN_V, "emblem": b} for b in bad)
        _broken_log(d)
    keep = [x for x in item.get("emblem") or [] if not any(x is b for b in bad)]
    rej = list(dict.fromkeys(list(item.get("emblem_reject") or []) + [b.get("source") or b["image"] for b in bad]))
    with WRITE_LOCK:
        emblem.write_item(item["name"], keep, None)
        _set_field(item["name"], "emblem_reject", json.dumps(rej, ensure_ascii=False) + "   # 目で見て・検査で外した画像。自動補完は選ばない")
    log(f"  [外した] {item['name']}：読めない・切れ端・頭が切れた・ぼやけた小元素 {len(bad)} 枚（{'、'.join(b.get('subject', '') for b in bad)}）")
    return len(bad) + n


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
    if result.get("exhausted"):
        e["exhausted"] = True
    else:
        e.pop("exhausted", None)
    if "tried" in result and st["kind"] == "character":
        e["names_v"] = NAMES_V
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


def background(minutes, log=print, fill=None, clock=time.time, path=None, runlog_dir=None, workers=None, live=None, lines=None):
    """定時の後台：時間の予算（分）の中で、足りない関注項を workers 本並列で埋め、state/emblem_progress.json に進捗を残す。
    候補集め・本人確認は並列、items.yaml への書き込みと抠图は WRITE_LOCK で 1 本ずつ。
    1 つ終わるごとに保存するので、途中で止まっても、それまでの結果は残る。
    live：簡報の版面の「更新中」の帯に知らせる関数（livestatus.report と同じ形）。本番（path なし）では livestatus.report。"""
    fill = fill or fill_one
    if live is None:
        import livestatus
        live = livestatus.report if path is None else (lambda *a, **k: None)   # テスト（path あり）はネットに出ない
    if lines is None:   # 管理ページ「ライブログ」に作業の 1 行 1 行を流す（Supabase live_log。AI を使わないので細かく出してよい）
        import livestatus
        lines = livestatus.Lines("emblem", send=None if path is None else False)
        lines.prune()
    per_board = runlog.typical("emblem", "item_secs", 240, log_dir=runlog_dir) / 60   # 1 版面にかかる時間（最近の中央値）
    started = time.time()
    workers = max(1, int(workers or WORKERS))
    deadline = clock() + minutes * 60
    if clock is time.time:
        _deadline[0] = deadline - 60   # 集めるのはここまで（残りの 1 分で書き込みと切り抜き）
    if path is None:   # 本番：管理ページ「候補から選ぶ」の入れ替えと候補集めを先に（テストは触らない）
        try:
            import emblem_cands
            emblem_cands.run_shop(log)
        except OutOfTime:
            pass
        except Exception as e:  # noqa: BLE001
            log(f"[候補] {e}")
    if path is None:   # 本番：待ちの有無にかかわらず毎回、顔の測り直し（face・nk・bb が欠けた分）。drop_broken は変化のある版面でしか回らず、測り直しが届かなかった
        try:
            with WRITE_LOCK:
                m = sum(emblem_face.measure_item(i, log) for i in load_items())
            if m:
                log(f"[顔を測り直し] 全版面で {m} 枚")
        except Exception as e:  # noqa: BLE001
            log(f"[顔を測り直し] {e}")
    prog = load_progress(path)
    now = _now()
    prog.setdefault("started", now)
    prog["last_run"] = {"at": now, "minutes": minutes, "workers": workers, "done": []}
    items = load_items()
    sync_progress(prog, items)
    save_progress(prog, path)
    queue = due(prog, items, now)
    head = (f"開始：予算 {minutes:g} 分・{workers} 本並列・待ち {len(queue)} 版面"
            f"（{'、'.join(i['name'] for i in queue[:4])}{' …' if len(queue) > 4 else ''}）")
    runlog.add("emblem", head, log_dir=runlog_dir)
    if os.environ.get("EMBLEM_RETRY_NOW"):
        lines.add("管理ページの「今すぐ再挑戦」から起動：失敗した版面も待たずにやり直す")
    lines.add(head)
    if not queue:
        lines.add("やることなし：どの版面も目標に届いているか、再挑戦の時刻がまだ", level="ok")
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
            def ilog(m, n=name):
                log(f"[{n}] {str(m).strip()}" if workers > 1 else m)
                lines.add(m, board=n)
            ilog(f"開始（いま {fresh_have(item)}）")
            live(name, "emblem", "work", "小元素を集めています", per_board + 3)
            t_item, before = time.time(), fresh_have(item)
            item["_recount"] = (prog["items"].get(name) or {}).get("names_v") != NAMES_V   # 名簿の規則の版が上がった：名簿がそろっていても 1 回数え直す
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
    tail = f"終了：{len(prog['last_run']['done'])} 版面を処理（{workers} 本並列）・そろっている {prog['summary']['ok']} / {prog['summary']['total']}"
    runlog.add("emblem", tail, "ok", log_dir=runlog_dir, secs=round(time.time() - started), workers=workers, res=resources.snapshot())
    lines.add(tail + f"・{round(time.time() - started)} 秒 · 増えた分は push のあと 1〜2 分で網页に", level="ok")
    lines.close()
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
