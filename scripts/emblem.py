"""作品の小元素（版面の右上に貼るステッカー）を探して、版面の配色をそれに合わせる。

絵は自作しない。見ればその作品だと分かる既存の画像を探して、そのまま使う（中身は変えない）。
網页は画像を元の網址で直接引用し（新聞の配図と同じ、倉庫には保存しない）、白いフチ・色のフチ・硬い影・傾き・
スクロールで飛び出す効果だけを CSS で付ける。一つの版面に何枚あってもよく、網页を開くたびに 1 枚をランダムに出す。

探し方（AI 編集が新しい関注項を設計するときに使う）：
  1. 何を貼るか決める ── 枚数は「主要キャラの数」に合わせる。追っている「その作品版」の絵であること：
     ・実写のドラマ・映画のリメイクは、キャラのページ（旧作の写真が多い）ではなく、その作品の出演者のページの写真を使う
       （例：HBO の「Harry Potter」ドラマ → Dominic McLaughlin などのページ。映画版の Daniel Radcliffe は使わない）
     ・アニメ・漫画：AniList の主役（role MAIN、お気に入り順）。作品の顔になっているマスコットがいれば先頭に足す（例：ポチタ）
     ・ゲーム・ドラマなど AniList にないもの：シリーズでいちばん知られたキャラを AI が選んで --titles に並べる（理由を書く）
     ・キャラが一人だけの作品（ぐでたま）：その Wiki ページに載っている画像から、有名な別シーンを何枚か（--gallery）
  2. その作品のファン Wiki（Fandom など MediaWiki）で、キャラのページの代表画像（pageimages）を取る。
     Fandom にページがなければ別の Wiki（Sanrio 系・Nookipedia・Wikipedia）を試す。
  3. 使えるか確かめる：短い辺が 160px 以上。縁の 90% 以上が透明なら「切り抜き」（輪郭どおりのステッカー）。
     代表画像が四角い写真なら、同じページに載っている透明な立ち絵を探す（人物は輪郭どおりが基本。丸いバッジにはしない）。
     それでもなければ「カード」で取っておき、--cut で人物だけを切り抜く（rembg の birefnet-general-lite）。
     切り抜いた画像は docs/emblems/ に保存（元の網址は source に残す）。枠や丸で囲まない。使えないものは飛ばす。
  4. 版面の配色を合わせる：先頭（いちばん代表的な一枚）の代表色（不透明な部分で「面積 × 鮮やかさ²」が最大の色）を強調色に。
     地の明るさは作品の気質で決める（--tone）：熱血・暴力・ホラー・SF は墨の地（dark）、かわいい・癒やし・日常は米白の地（light）。
     一律に米白にしない。文字はどれも 4.5:1 以上（theme._readable）、網页に出したあと実際の重なりでも確かめる。
     キャラが入れ替わっても浮かないように、どの絵にも版面の強調色のフチと墨の硬い影を付ける（emblem_ring）。
     人物・製品の写真（色がばらつく）は --palette keep で今の配色のまま。強調色のフチで版面とつなぐ。
     絵として認識できる主題がない分類（「MMORPG 新作」「滑雪」のような総合カテゴリ）は無理に貼らない。
  5. items.yaml に emblem（リスト：subject / why / image / page / shape）と theme を書く。
  ※ AniList にないゲームなどは --category（Wiki の分類でリンクの多い順）で主要キャラを決める。

使い方：
  python scripts/emblem.py "チェーンソーマン" --api https://chainsaw-man.fandom.com/api.php \
      --titles Pochita --why "作品の顔のマスコット" --anilist 127230 --max 5 --tone dark [--write]
  python scripts/emblem.py "ぐでたま" --api https://hellokitty.fandom.com/api.php --gallery Gudetama --match Gudetama --max 4 --tone light
"""

import argparse
import io
import json
import pathlib
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sitedir  # noqa: E402
import theme  # noqa: E402
from cutshape import FLAT_RUN, FLAT_TOP, SOLID_MIN, flat_flaw, flat_runs, solidity  # noqa: E402,F401  切り抜きの形を測るところ（emb_check も読む）
import wikihttp  # noqa: E402
from sources import TIMEOUT, USER_AGENT  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_BYTES = 6_000_000
MIN_SIDE = 160


def write_atomic(path, text):
    """items.yaml などを一時ファイルに書いてから置き換える（書いている途中で殺されても、壊れた半分のファイルを残さない：
    後台作業の小元素の段は continue-on-error なので、壊れた items.yaml が push されると全部のワークフローの load_config が止まる）。"""
    import os
    import threading
    path = pathlib.Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _get(url, limit=MAX_BYTES):
    if wikihttp.is_wikimedia(url):   # Wikimedia は決まりどおりの UA・1 本ずつ・Retry-After・キャッシュ
        return wikihttp.get(url, limit)
    import time
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in (0, 3, 8, 20):   # Fandom などの「多すぎ」（429）は少し待って取り直す
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read(limit + 1)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait == 20:
                raise
    if len(data) > limit:
        raise ValueError("画像が大きすぎる")
    return data


def page_image(api, title, any_license=False):
    """MediaWiki の pageimages：そのページの代表画像の網址と、ページの網址。
    Wikipedia は既定で自由ライセンスの画像しか返さない。any_license=True はゲームのキービジュアル・パッケージ（非自由）も。"""
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "pageimages|info", "piprop": "original|thumbnail",
                                "pithumbsize": 500, "inprop": "url", "format": "json", "redirects": 1,
                                **({"pilicense": "any"} if any_license else {})})
    pages = json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"]
    page = next(iter(pages.values()))
    src = (page.get("original") or {}).get("source")
    # Wikimedia（Wikipedia）は原寸を引かず、決まったサイズの縮小版を使う決まり（https://w.wiki/GHai）
    if src and "wikimedia.org" in src and (page.get("thumbnail") or {}).get("source"):
        src = page["thumbnail"]["source"]
    if not src:
        raise LookupError(f"{title}：代表画像がない")
    return src, page.get("fullurl") or ""


def small_url(src, width=400):
    """縮小版の網址にする（網页で 130px ほどにしか出さないので、重い原寸は引かない）。
    Fandom は scale-to-width-down、Wikimedia は決まったサイズの thumb（https://w.wiki/GHai）。"""
    m = re.match(r"^(https://upload\.wikimedia\.org/wikipedia/[^/]+)/([0-9a-f])/([0-9a-f]{2})/([^/?]+)(?:\?.*)?$", src)
    if m and not m.group(4).lower().endswith(".svg"):
        base, a, ab, name = m.groups()
        return f"{base}/thumb/{a}/{ab}/{name}/500px-{name}"
    if "static.wikia.nocookie.net" in src and "/revision/latest" in src and "scale-to-width" not in src:
        return src.replace("/revision/latest", f"/revision/latest/scale-to-width-down/{width}", 1)
    return src


def inspect(data):
    """→ (shape, 代表色, 画像)。shape は cutout（縁がほぼ透明）か badge。"""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    w, h = img.size
    wide = max(w, h) >= 2.2 * min(w, h)   # 横長・縦長のロゴ（Samsung は 500×133）：短い辺ではなく長い辺で見る
    if (min(w, h) < 64 or max(w, h) < 300) if wide else min(w, h) < MIN_SIDE:
        raise ValueError(f"小さすぎる（{w}×{h}）")
    a = img.getchannel("A")
    edge = [a.getpixel((x, y)) for x in range(0, w, max(1, w // 60)) for y in (0, h - 1)] + \
           [a.getpixel((x, y)) for y in range(0, h, max(1, h // 60)) for x in (0, w - 1)]
    shape = "cutout" if sum(v < 16 for v in edge) / len(edge) >= 0.9 else "badge"
    if shape == "badge":  # 背景つきの画像は、背景の色を拾わないよう中央（バッジに残る部分）だけで色を見る
        img_k = img.crop((w * 0.2, h * 0.2, w * 0.8, h * 0.8))
    else:
        img_k = img
    return shape, key_color(img_k), img


def key_color(img):
    """不透明な部分だけで量子化し、「面積 × 鮮やかさ²」がいちばん大きい色を代表色にする（灰色・白・黒・淡い背景色の面積だけで選ばない）。"""
    from PIL import Image

    small = img.copy()
    small.thumbnail((160, 160))
    data = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    px = [p[:3] for p in data if p[3] > 200]
    if not px:
        raise ValueError("不透明な部分がない")
    flat = Image.new("RGB", (len(px), 1))
    flat.putdata(px)
    q = flat.quantize(12, method=Image.Quantize.FASTOCTREE)
    pal = q.getpalette()
    colors = [(n, tuple(pal[i * 3:i * 3 + 3])) for n, i in sorted(q.getcolors(), reverse=True)]
    vivid = [(n, c) for n, c in colors if theme._chroma(c) >= 0.25 and 0.15 < theme._lum(c) ** 0.5 < 0.95]
    return max(vivid or colors, key=lambda nc: nc[0] * theme._chroma(nc[1]) ** 2)[1]


def palette(key, tone="light"):
    """代表色 → 版面の配色。tone は作品の気質で決める：
    light（かわいい・癒やし・日常）＝代表色寄りの米白の地に、読める濃さの代表色。
    dark（熱血・暴力・ホラー・SF）＝代表色寄りの墨の地に、明るくした代表色。
    どちらも副面は反対の明るさ。文字と強調色はどれも 4.5:1 以上（theme._readable）。"""
    cream, ink = theme._shift(key, 0.94, max_sat=0.45), theme._shift(key, 0.1, max_sat=0.3)
    on_cream, on_ink = (30, 26, 24), (244, 238, 228)
    acc_cream = theme._readable(theme._shift(key, 0.45, max_sat=0.85), cream)
    acc_ink = theme._readable(theme._shift(key, 0.6, max_sat=0.85), ink)
    if tone == "dark":
        bg, fg, accent, alt_bg, alt_fg, alt_accent = ink, on_ink, acc_ink, cream, on_cream, acc_cream
    else:
        bg, fg, accent, alt_bg, alt_fg, alt_accent = cream, on_cream, acc_cream, ink, on_ink, acc_ink
    return {"bg": theme._hex(bg), "fg": theme._hex(fg), "accent": theme._hex(accent),
            "alt_bg": theme._hex(alt_bg), "alt_fg": theme._hex(alt_fg), "alt_accent": theme._hex(alt_accent),
            "split": True}


def anilist_main(media_id, n):
    """AniList の主役（role MAIN）をお気に入りの多い順に。英語名（Fandom のページ名とほぼ同じ）。"""
    q = {"query": "query($id:Int){Media(id:$id){characters(role:MAIN,sort:FAVOURITES_DESC,perPage:%d){nodes{name{full}}}}}" % n,
         "variables": {"id": int(media_id)}}
    req = urllib.request.Request("https://graphql.anilist.co", data=json.dumps(q).encode(),
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        nodes = json.load(r)["data"]["Media"]["characters"]["nodes"]
    return [x["name"]["full"] for x in nodes]


# 名簿に入れないページ：まとめ・一覧（MHD: FV: Felyne List）・遊ぶ人そのもの（Player）・別の作品に出たときの姿（Pokémon Trainer (Super Smash Bros.)・
# Monster Hunter (Marvel vs. Capcom: Infinite)）。括弧の中に別の作品（Smash Bros・○○ vs. ○○）があれば、その作品のキャラ。分類の名前の単数（あつ森の Special character）も
NOT_CHAR = re.compile(r"\bcharacters?\b|\blist\b|^(?:the )?(?:players?|parents?|protagonists?)$|^unnamed\b|\([^)]*(?:smash bros|\bvs\.)", re.I)


def not_character(name):
    return bool(NOT_CHAR.search(str(name or "")))


CAT_PAGES = 5   # 分類の人数は 200 × 5 = 1000 人まで数える
LH_PAGES = 4    # 1 人の参照は 500 × 4 = 2000 まで数える（それより上は同じ順位）


GROUP_CAT = re.compile(r"^Category:(?:\w+ )?(?:bands|groups|gangs|organi[sz]ations|factions|companies)$", re.I)


def groups(api, titles):
    """ページの分類が「集まり」だけの名前（Category:Music bands・Gangs・Organizations）→ 人ではないページの集合。
    名前の形では分からない（Gutless Wonders）ので、そのページの分類で決める。「Gang members」のような人の分類は当たらない。"""
    out = set()
    for i in range(0, len(titles), 50):
        cont = {}
        while True:
            q = urllib.parse.urlencode({"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "categories",
                                        "cllimit": "max", "format": "json", **cont})
            d = json.loads(_get(f"{api}?{q}", 2_000_000))
            for pg in (d.get("query") or {}).get("pages", {}).values():
                if any(GROUP_CAT.search(c.get("title", "")) for c in pg.get("categories") or []):
                    out.add(pg.get("title"))
            cont = d.get("continue") or {}
            if "clcontinue" not in cont:
                break
    return out


def category_top(api, category, n, dropped=None):
    """Wiki の分類（例：Wizards）のキャラを「ほかのページからのリンク数」→「記事の長さ」の順に多い n 人。
    物語の中心にいるキャラほど多くのページから参照される（AniList にないゲームなどで主要キャラを決める基準）。"""
    titles, cont = [], {}
    for _ in range(CAT_PAGES):   # 200 人を超える分類も続き（cmcontinue）で全員。頭の 200 人だけだと字の順の A〜B だけになる（原神・ゼルダ）
        q = urllib.parse.urlencode({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
                                    "cmlimit": 200, "cmnamespace": 0, "format": "json", **cont})
        d = json.loads(_get(f"{api}?{q}", 2_000_000))
        titles += [m["title"] for m in d["query"]["categorymembers"]]
        cont = d.get("continue") or {}
        if not cont:
            break
    # 分類の説明の記事（「Character」）・下位のページ（「Aino/Storyline」）は人ではない
    titles = [t for t in titles if "/" not in t and t.lower() not in (category.lower(), category.lower().rstrip("s")) and not not_character(t)]
    gone = groups(api, titles)   # 人の分類に入った集まり（GTA 6 の Music bands：Gutless Wonders・Dolls of Destruction）
    if dropped is not None:
        dropped.update(gone)
    titles = [t for t in titles if t not in gone]
    counts, length = {}, {}
    for t in titles:
        counts[t], cont = 0, {}
        for _ in range(LH_PAGES):   # 参照 500 で頭打ちにしない（主役ほど 500 を超え、同じ数が並んで記事の長さだけで決まっていた）
            q = urllib.parse.urlencode({"action": "query", "titles": t, "prop": "linkshere|info", "lhlimit": 500,
                                        "lhnamespace": 0, "lhshow": "!redirect", "format": "json", **cont})
            d = json.loads(_get(f"{api}?{q}", 2_000_000))
            pg = next(iter(d["query"]["pages"].values()))
            counts[t], length[t] = counts[t] + len(pg.get("linkshere", [])), pg.get("length", 0)
            cont = d.get("continue") or {}
            if "lhcontinue" not in cont:
                break
    # リンク数が同じ（ナビ欄で全員つながっているだけ）のときは、記事の長さ（主要キャラほど長い）で決める
    ranked = sorted(titles, key=lambda t: (-counts[t], -length[t]))
    print("  リンク数・記事の長さ：" + "、".join(f"{t} {counts[t]}/{length[t]}" for t in ranked[:n + 3]), file=sys.stderr)
    return ranked[:n]


def gallery(api, page, match, n):
    """キャラが一人の作品：そのページに載っている画像から、名前が match に合う別シーンを n 枚（切り抜きを優先）。"""
    q = urllib.parse.urlencode({"action": "query", "titles": page, "prop": "images", "imlimit": 200, "format": "json", "redirects": 1})
    pg = next(iter(json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"].values()))
    files = [x["title"] for x in pg.get("images", []) if re.search(match, x["title"], re.I) and re.search(r"\.(png|webp|gif)$", x["title"], re.I)]
    out = []
    for i in range(0, len(files), 40):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(files[i:i + 40]), "prop": "imageinfo",
                                    "iiprop": "url|size", "iiurlwidth": 400, "format": "json"})
        for p in json.loads(_get(f"{api}?{q}", 4_000_000))["query"]["pages"].values():
            info = (p.get("imageinfo") or [{}])[0]
            if info.get("url"):
                out.append((p["title"], info.get("thumburl") or info["url"], info.get("descriptionurl", "")))
    picked = []
    for title, url, page_url in out:
        try:
            shape, key, _ = inspect(_get(url))
        except Exception as e:
            print(f"  [飛ばす] {title}：{e}", file=sys.stderr)
            continue
        picked.append({"subject": re.sub(r"^(File|ファイル):", "", title), "image": url, "page": page_url, "shape": shape, "key": theme._hex(key)})
    picked.sort(key=lambda x: x["shape"] != "cutout")  # 切り抜きを先に
    return picked[:n]


CARD = 4 / 5   # カードの縦横比（幅 / 高さ）


def face_crop(img):
    """四角い写真をカードにするときの取景：顔を見つけて、頭と肩が入るように 4:5 で切る（絵の中身は変えない、見せる範囲だけ）。
    → [左, 上, 幅]（画像に対する割合）。顔が見つからなければ上寄りの中央。
    写真は OpenCV の顔検出、アニメ・漫画の絵は lbpcascade_animeface（MIT、scripts/data/）。OpenCV がなければ上寄りの中央。"""
    w, h = img.size
    box = None
    try:
        import cv2
        import numpy as np
        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        gray = cv2.equalizeHist(gray)
        found = []
        for path in (cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
                     str(pathlib.Path(__file__).resolve().parent / "data" / "lbpcascade_animeface.xml")):
            c = cv2.CascadeClassifier(path)
            if not c.empty():
                found += [tuple(map(int, f)) for f in c.detectMultiScale(gray, 1.1, 5, minSize=(max(24, w // 12), max(24, w // 12)))]
        if found:
            # いちばん大きい顔。ただし顔はふつう上のほうにあるので、下半分の検出（服のロゴなどの誤検出）は軽く見る
            box = max(found, key=lambda f: f[2] * f[3] * (1.0 if f[1] + f[3] / 2 < h * 0.55 else 0.25))
    except ImportError:
        print("  [取景] OpenCV がないので上寄りの中央で切る（pip install opencv-python-headless<5：5 以降は顔検出が別パッケージ）", file=sys.stderr)
    if box:
        fx, fy, fw, fh = box
        ch = min(h, fh * 3.0)                  # 顔の 3 倍の高さ：頭から肩まで
        cw = min(w, ch * CARD)
        ch = cw / CARD
        x = min(max(0, fx + fw / 2 - cw / 2), w - cw)
        y = min(max(0, fy + fh / 2 - ch * 0.4), h - ch)   # 顔が上から 4 割の位置
    else:
        cw = min(w, h * CARD)
        ch = cw / CARD
        x, y = (w - cw) / 2, min(h - ch, h * 0.04)
    return [round(x / w, 4), round(max(0, y) / h, 4), round(cw / w, 4)], round(h / w, 4)


def cutout_on_page(api, title, limit=25):
    """そのページに載っている画像から、透明背景の立ち絵（切り抜き）を探す。名前に人物名を含むものを優先し、大きい順。
    代表画像が背景つき（四角い写真）のときに使う。人物は丸や四角より、輪郭どおりのほうが良いので。"""
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "images", "imlimit": 200, "format": "json", "redirects": 1})
    pg = next(iter(json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"].values()))
    files = [x["title"] for x in pg.get("images", []) if re.search(r"\.(png|webp)$", x["title"], re.I)]
    # 名前のどれか（姓でも名でも：「Yasutora Sado」のファイルは BBSSado.png）がファイル名に入っているもの
    words = [w for w in re.split(r"[\s(),]+", title.lower()) if len(w) >= 3] or [title.lower()]
    named = lambda f: any(w in f.lower().replace("_", " ") for w in words)
    files.sort(key=lambda f: (not named(f), "icon" in f.lower() or "logo" in f.lower()))
    best = None
    for i in range(0, min(len(files), limit), 20):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(files[i:i + 20]), "prop": "imageinfo",
                                    "iiprop": "url|size", "iiurlwidth": 400, "format": "json"})
        for p in json.loads(_get(f"{api}?{q}", 4_000_000))["query"]["pages"].values():
            info = (p.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if not url or not named(p["title"]) or re.search(r"icon|logo|chibi|sprite|swimsuit|halloween|christmas|valentine|summer|bunny|wedding|new ?year", p["title"], re.I):
                continue
            try:
                shape, key, img = inspect(_get(url))
            except Exception:
                continue
            if shape == "cutout" and img.size[1] >= img.size[0] * 0.8:   # 立ち絵・バストアップ（横長の集合絵は除く）
                area = info.get("width", 0) * info.get("height", 0)
                if not best or area > best[0]:
                    best = (area, url, info.get("descriptionurl", ""), key)
    return best


def one(api, title):
    src, page = page_image(api, title)
    url = small_url(src)
    shape, key, img = inspect(_get(url))
    out = {"subject": title, "image": url, "page": page, "shape": shape, "key": theme._hex(key)}
    if shape == "badge":   # 代表画像が四角い写真なら、同じページの透明な立ち絵を探す
        try:
            found = cutout_on_page(api, title)
        except Exception as e:
            found = None
            print(f"  [切り抜き探し失敗] {title}：{e}", file=sys.stderr)
        if found:
            _, out["image"], _, key = found
            out.update(shape="cutout", key=theme._hex(key))
        else:   # 立ち絵がない写真はカードに：顔が入るように取景
            out["crop"], out["ar"] = face_crop(img)
    return out


def collect(api, titles=(), anilist=None, gallery_page=None, match=None, n=6, why="", tone="light", category=None):
    """候補を集めて使えるものだけ残す。先頭がいちばん代表的な一枚（配色の基準）。"""
    found, seen = [], set()
    names = [(t, why or "AI が選んだ代表キャラ") for t in titles]
    if anilist:
        names += [(t, "AniList の主役（お気に入り順）") for t in anilist_main(anilist, n)]
    if category:
        names += [(t, f"Wiki の分類「{category}」でリンクの多いキャラ") for t in category_top(api, category, n)]
    for t, reason in names:
        if t in seen or len(found) >= n:
            continue
        seen.add(t)
        try:
            found.append({**one(api, t), "why": reason})
        except Exception as e:
            print(f"  [飛ばす] {t}：{e}", file=sys.stderr)
    if gallery_page and len(found) < n:
        found += [{**x, "why": f"{gallery_page} の別シーン（Wiki の画像）"} for x in gallery(api, gallery_page, match or gallery_page, n - len(found))]
    if not found:
        raise LookupError("使える画像が見つからない")
    return found, (palette(theme._rgb(found[0]["key"]), tone) if tone else None)


def _flow(d):
    return "{" + ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "}"


def write_item(name, emblems, th):
    """items.yaml のその関注項に emblem（リスト）と theme を書く（あれば置き換え）。motif の行のすぐ後ろに入れる。"""
    path = ROOT / "items.yaml"
    write_atomic(path, item_text(path.read_text(encoding="utf-8"), name, emblems, th))


def item_text(text, name, emblems, th=None):
    """write_item の中身（items.yaml の全文 → 新しい全文）。emblems が空なら emblem の行ごと消す。"""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("  - name:")), len(lines))
    block, skip = [], False
    for l in lines[start + 1:end]:
        if re.match(r"^    emblem:", l) or (th and re.match(r"^    theme:", l)):
            skip = True   # この行と、その下の字下げされた続き（複数行で書いた theme や emblem のリスト）を消す
            continue
        if skip and (l.startswith("      ") or not l.strip()):
            continue
        skip = False
        block.append(l)
    at = next((i + 1 for i, l in enumerate(block) if l.startswith("    motif:")), 0)
    keep = ("subject", "why", "image", "source", "page", "shape", "crop", "ar", "upper", "framing", "body", "work", "plate", "fs")
    block[at:at] = ((["    emblem:  # 作品の小元素（scripts/emblem.py）：網页を開くたびに 1 枚をランダムに出す。先頭が配色の基準"] if emblems else [])
                    + [f"      - {_flow({k: x[k] for k in keep if k in x})}" for x in emblems]
                    + ([f"    theme: {_flow(th)}  # 小元素「{emblems[0]['subject']}」の色に合わせた配色（scripts/emblem.py）"] if th else []))
    lines[start + 1:end] = block
    return "\n".join(lines)


def recrop(name):
    """items.yaml のその関注項の「カード」（badge）の小元素だけ、画像を取り直して取景（crop）を付け直す。"""
    import yaml
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    for x in ems:
        if x.get("shape") == "badge":
            try:
                _, _, img = inspect(_get(x["image"]))
                x["crop"], x["ar"] = face_crop(img)
                print(f"  {x['subject']}：crop {x['crop']}", file=sys.stderr)
            except Exception as e:
                print(f"  [飛ばす] {x['subject']}：{e}", file=sys.stderr)
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    j = next(i for i in range(start, len(lines)) if lines[i].startswith("    emblem:"))
    k = j + 1
    while k < len(lines) and lines[k].startswith("      - "):
        k += 1
    keep = ("subject", "why", "image", "page", "shape", "crop", "ar")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    write_atomic(path, "\n".join(lines))


EMB_DIR = sitedir.SITE_DIR / "emblems"   # 切り抜いた画像（網页と同じ場所に置く。倉庫は公開なので画像も公開になる）


SUBTITLE = 0.18   # 動画の場面の下のこの割合は字幕の帯として切る


def video_frame(img):
    """YouTube の動画の場面（4:3 の枠に 16:9 の動画）→ 上下の黒い帯と、下の字幕の帯を切った画像。
    字幕は人物の肩に重なると切り抜きに残る（「…했습니다」の例）。下の端で体が切れるのは胸像なのでかまわない。"""
    import numpy as np
    g = np.array(img.convert("L"), dtype="float32")
    rows = np.where(g.mean(axis=1) > 16)[0]
    if not len(rows):
        return img
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    bottom -= int((bottom - top) * SUBTITLE)
    return img.crop((0, top, img.width, bottom)) if bottom - top > 80 else img


def cut_out(url, slug, drawn=True):
    """背景のある画像から人物だけを切り抜いて docs/emblems/<slug>.webp に保存し、網页から読む相対パスを返す。
    rembg の birefnet-general-lite（絵も写真も）。輪郭の外側の余白は切り詰める。中身（人物）は変えない。
    暗い背景に暗い人物・網点の漫画コマなど、輪郭がにじむものは切り抜いた結果を目で見て、だめなら外す。"""
    from PIL import Image
    from rembg import new_session, remove

    img = Image.open(io.BytesIO(_get(url))).convert("RGB")
    if "i.ytimg.com/" in url:
        img = video_frame(img)
    out = remove(img, session=_session("birefnet-general-lite"))   # 絵も写真もいちばん輪郭がきれいだった（isnet-anime・u2net と比べた）
    out = check_whole(out, photo=not drawn)
    if not drawn and lost_face(img, out):
        raise ValueError("顔が切り抜きに残っていない（別のもの：手・物・背景を切り抜いた）")
    out, _ = upper_body(out)   # 縦長の全身は上半身に（小さく貼ると顔が見えない）
    save_cut(out, slug)
    return f"emblems/{slug}.webp"


def framing(img):
    """bust（胸像：下の端で切れている）か full（全身：足まで入っている）か。"""
    import numpy as np
    a = np.array(img.getchannel("A")) > 128
    return "bust" if a[-1, :].mean() > 0.08 else "full"


def face_box(img):
    """いちばん大きい顔 (x, y, w, h)。写真は OpenCV の顔検出、絵は lbpcascade_animeface。なければ None。"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    rgb = np.array(img.convert("RGB"))
    gray = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    w = gray.shape[1]
    found = []
    for path in (cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
                 str(pathlib.Path(__file__).resolve().parent / "data" / "lbpcascade_animeface.xml")):
        c = cv2.CascadeClassifier(path)
        if not c.empty():
            m = max(24, min(gray.shape) // 12)   # 短い辺で決める（横長の宣伝画像でも小さめの顔を拾う）
            found += [tuple(map(int, f)) for f in c.detectMultiScale(gray, 1.1, 4, minSize=(m, m))]
    return max(found, key=lambda f: f[2] * f[3]) if found else None


HOLE_MAX = 0.03   # 実在の人の写真で、体の中の透明な穴（服が背景と同じ色で抜けた）がこれより多いものは使わない（正しい写真は ≈0%）


def hole_share(solid):
    """体（solid：True の所）の中にあいた透明な穴の面積 ÷ 体の面積。上・左・右の端につながる透明は背景、
    それ以外（下の端だけにつながるものも。胸像は下で切れているので）は穴とみなす。目で見ていた「切り抜きの穴」を数で判断する。"""
    import numpy as np
    import cv2
    clear = (~solid).astype("uint8")
    n, labels = cv2.connectedComponents(clear, connectivity=4)
    if n <= 1:
        return 0.0
    edge = set(np.unique(labels[0, :])) | set(np.unique(labels[:, 0])) | set(np.unique(labels[:, -1]))
    hole = clear.astype(bool) & ~np.isin(labels, list(edge))
    return float(hole.sum()) / max(1, int(solid.sum()))


OTHER_FACE = 0.2   # 切り抜きに残った 2 番目の顔が、いちばん大きい顔の高さのこの割合以上 = ほかの人が残っている


def other_faces(out, keep=None):
    """切り抜いた画像（白の上に置いて）で顔を数え、いちばん大きい顔のほかに目立つ顔がいくつあるか。顔のモデルがなければ 0。"""
    try:
        import face_id
        eng = face_id.engine()
        if eng is None:
            return 0
        import numpy as np
        import cv2
        from PIL import Image
        im = out.convert("RGBA")
        if keep is not None:
            a = np.where(keep, np.array(im.getchannel("A")), 0).astype("uint8")
            im.putalpha(Image.fromarray(a))
        bg = Image.new("RGBA", im.size, "#FFFFFF")
        bg.alpha_composite(im)
        bgr = cv2.cvtColor(np.array(bg.convert("RGB")), cv2.COLOR_RGB2BGR)
        det = eng[0]
        det.setInputSize((bgr.shape[1], bgr.shape[0]))
        _, faces = det.detect(bgr)
        if faces is None or len(faces) < 2:
            return 0
        hs = sorted((float(f[3]) for f in faces), reverse=True)
        return sum(1 for h in hs[1:] if h >= OTHER_FACE * hs[0])
    except Exception:
        return 0


LOGO_WORD = re.compile(r"ロゴ|logo|wordmark|ワードマーク", re.I)
FLAT_TOL = 28      # ロゴの地の色：縁の色からこの差（RGB の最大差）までを地として透明にする
CARD_AR = (0.95, 1.6)   # カード（4:5 の窓）で切ってよい縦横比（高さ ÷ 幅）。外れたら切らずに全体を見せる


def is_logo(x, kind=None):
    """ロゴか（切ってはいけない）。ブランドの小元素、または名前・理由に「ロゴ」とあるもの。"""
    return kind == "brand" or bool(LOGO_WORD.search(f'{x.get("subject", "")} {x.get("why", "")}'))


def clear_flat_bg(img):
    """縁が一色（白・黒の地）の画像の、縁からつながった地の色を透明にして、余白を切り詰める。地が一色でなければそのまま。
    ロゴの PNG に白い地と余白がついている（gelato pique の 1200×628）ので、そのままだと四角い白い板になり、カードに入れると字が切れる。"""
    import numpy as np
    import cv2
    from PIL import Image
    rgba = np.array(img.convert("RGBA"))
    rgb = rgba[..., :3].astype("int16")
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(edge, axis=0)
    if (np.abs(edge - bg).max(axis=1) <= FLAT_TOL).mean() < 0.9:   # 縁が一色でない（写真）
        return img
    flat = (np.abs(rgb - bg).max(axis=2) <= FLAT_TOL).astype("uint8")
    n, labels = cv2.connectedComponents(flat, connectivity=4)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    mask = np.isin(labels, list(border)) & (flat == 1)
    rgba[..., 3] = np.where(mask, 0, rgba[..., 3])
    out = Image.fromarray(rgba)
    box = out.getchannel("A").getbbox()
    return out.crop(box) if box else img


def logo_local(url, slug):
    """ロゴを倉庫に置く：地の色を抜いて余白を切り詰め、docs/emblems/<slug>.webp に。→ 網页から読む相対パス。"""
    from PIL import Image
    img = clear_flat_bg(Image.open(io.BytesIO(_get(url))))
    img.thumbnail((520, 520))
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    img.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=90, method=6)
    return f"emblems/{slug}.webp"


def wordmark_local(url, slug):
    """作品の主な画像がタイトルロゴ（文字だけ・地が透明か一色）なら倉庫に置く → (相対パス, 高さ÷幅, 板つきか)。写真・ポスターなら None。
    カードに入れると白い板の中に小さな字が浮くだけ（The Mandalorian）なので、ロゴそのものを大きく貼る。
    ・地が透明・白っぽい：地を抜いて字だけ（板 = False）
    ・地が濃い色（HBO の紫の板に白い字：ハリー・ポッター）：抜くと白い字が白いフチに埋もれて読めないので、地の板ごと残す（板 = True。
      白いカードには入れず、板そのものに斜めの枠だけ）"""
    import numpy as np
    from PIL import Image
    src = Image.open(io.BytesIO(_get(url))).convert("RGBA")
    a = src.getchannel("A")
    w, h = src.size
    edge = [a.getpixel((x, y)) for x in range(0, w, max(1, w // 60)) for y in (0, h - 1)] + \
           [a.getpixel((x, y)) for y in range(0, h, max(1, h // 60)) for x in (0, w - 1)]
    clear = sum(v < 16 for v in edge) / len(edge) >= WORDMARK_EDGE
    img = src if clear else clear_flat_bg(src)
    if not clear and img is src:   # 縁が透明でも一色の地でもない = 写真・ポスター
        return None
    plate = False
    if not clear:   # 一色の地：地の明るさで、抜くか板ごと残すか
        rgb = np.array(src.convert("RGB")).astype("float")
        ring = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        lum = float(np.median(ring @ [0.299, 0.587, 0.114])) / 255
        if lum < PLATE_LUM:
            img, plate = src, True
    box = img.getchannel("A").getbbox() or (0, 0, w, h)
    img = img.crop(box)
    img.thumbnail((520, 520))
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    img.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=90, method=6)
    return f"emblems/{slug}.webp", round(img.size[1] / img.size[0], 3), plate


PLATE_LUM = 0.8   # ロゴの地の明るさがこれ未満（濃い色の板）なら地を抜かずに板ごと貼る
WORDMARK_EDGE = 0.6   # 縁のこの割合以上が透明（か縁が一色の地）= タイトルロゴ（文字だけ）。写真・ポスターは縁まで絵がある


# 切り抜きの検査（check_whole）の数。判断の一覧（emblem_rules.py）もここを読む
PART_KEEP = 0.15   # いちばん大きいまとまりのこの割合以上の離れた部分（手・持ち物）は残す
SIDE_ZONE = 0.65   # 左右の端は上のこの割合だけ見る（下は胸像の肩なので当たってよい）
SIDE_MAX = 0.10    # 左右の端（上 SIDE_ZONE）に人物が当たっている割合がこれを超える = 体が枠で切れている
TOP_MAX = 0.5      # 上の端の人物の割合がこれを超える = 漫画のコマ・顔のアップを枠ごと切った
TOP_TOUCH = 0.03   # 上の端にこれ以上当たっていたら、顔まで切れていないか確かめる
HEAD_ROWS = 3      # 上の端のこの行数（px）を見る
HEAD_EDGE = 0.2    # 上の HEAD_ROWS 行に人物が横幅のこの割合以上 = 頭のてっぺんが切れている（BLEACH Mirrors High：髪が上の端で切れた絵。顔が全部入っていても使わない）
FACE_PX_MIN = 80   # 写真：切り抜く前の解像度で顔の幅がこれ未満 = 小さすぎて小元素に拡大するとぼやける
SHARP_MIN = 1.0    # 写真：書き出す大きさ（420×520 以内）の顔の輪郭の鋭さ（上位 1% の明るさの傾き ÷ 明るさの幅）がこれ未満 = ぼやけている
                   # （2026-10-25 店長の実写・人物の 66 枚：哈利波特剧集 Oliver Wood 0.51・FROM のピントの甘い場面 3 枚 0.61〜0.88・Vaundy のライブの場面 0.90 の 5 枚が下、ほかは 1.09 以上）
FACE_TOP = 0.04    # 顔の上端が高さのこの割合より上 = 顔が上の端で切れている
EYE_TOP = 1.4      # 目の高さ < 目〜口の距離 × これ = 額まで切れた（YuNet の目・口。harness/emb_check.EYE_TOP と同じ：哈利波特 Dominic 197×101 は haar の顔の上端では拾えなかった）
AREA_MIN = 0.12    # 人物の面積がこれより小さい = 小さすぎる
CUT_MIN = 64       # 書き出す切り抜きの短い辺がこれ未満 = 切れ端（漫威电影 Black Panther 60×10：作り直すたびに前の切り抜きを切り詰めて縮んだ）
CUT_WIDE = 3       # 横が縦のこの倍より長い切り抜き = 帯（BLEACH Mirrors High 209×45）。人の胸像・全身は横長にならない
DARK_MAX = 0.16    # 写真・場面の切り抜きの明るさ（人物部分の平均）がこれ未満 = 暗すぎて何かわからない
FACE_DARK = 0.10   # 顔が見つかったときは顔の明るさがこれ未満 = 暗すぎる（暗い場面の剧照の Snape／Paapa Essiedu は 14% でもはっきり見える。肌の色で外さない）
SOFT_MAX = 0.18    # 半透明（輪郭がにじんだ）部分がこれより多いものは使わない


def top_share(img):
    """切り抜きの上の端（1 行目）に人物が当たっている横幅の割合（check_whole の top と同じ）。"""
    import numpy as np
    a = np.array(img.convert("RGBA").getchannel("A"))[:1] > 128
    return float(a.mean()) if a.size else 0.0


def head_cut(img):
    """切り抜きの上の HEAD_ROWS 行に人物が横幅の HEAD_EDGE 以上 = 頭のてっぺんが上の端で切れている。"""
    import numpy as np
    a = np.array(img.convert("RGBA").getchannel("A"))[:HEAD_ROWS] > 128
    return bool(a.size) and float(a.any(axis=0).mean()) >= HEAD_EDGE


def face_sharp(img):
    """写真の切り抜き → (いちばん大きい顔の幅 px, 鋭さ, 顔の明るさ 0〜1) か None（顔のモデルがない・顔がない）。
    鋭さは書き出す大きさ（save_cut と同じ 420×520 以内）で測る：拡大したぼやけた場面（輪郭が何 px にも広がる）は小さい。"""
    try:
        import cv2
        import numpy as np
        import face_id
        eng = face_id.engine()
    except Exception:
        return None
    if eng is None:
        return None
    from PIL import Image
    im = img.convert("RGBA")
    box = im.getchannel("A").getbbox()
    if box:
        im = im.crop(box)   # 書き出すのは人物の範囲だけ（rembg の結果は元の画像の大きさのまま）
    w0 = im.width
    im.thumbnail((420, 520))
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    bgr = cv2.cvtColor(np.array(bg.convert("RGB")), cv2.COLOR_RGB2BGR)
    with _YUNET:
        eng[0].setInputSize((bgr.shape[1], bgr.shape[0]))
        f = eng[0].detect(bgr)[1]
    if f is None or not len(f):
        return None
    x, y, fw, fh = [int(v) for v in max(f, key=lambda r: r[2] * r[3])[:4]]
    g = cv2.cvtColor(bgr[max(0, y):y + fh, max(0, x):x + fw], cv2.COLOR_BGR2GRAY).astype(float)
    if min(g.shape) < 8:
        return None
    mg = np.hypot(cv2.Sobel(g, cv2.CV_64F, 1, 0), cv2.Sobel(g, cv2.CV_64F, 0, 1))[2:-2, 2:-2]
    span = max(1.0, float(np.percentile(g, 99) - np.percentile(g, 1)))
    return round(fw * w0 / im.width), float(np.percentile(mg, 99)) / span, float(g.mean()) / 255


NOFACE_WIDE = 1.3   # 写真の切り抜きに顔がなく、横が縦のこの倍より長い = 髪・額だけの切れ端（哈利波特剧集 Hermione 194×92）。顔のない兜（The Mandalorian）は縦長の全身なので当たらない


def faceless_scrap(img):
    """写真の切り抜きに顔がなく（YuNet）、横長 = 額から上だけ・髪だけの切れ端。顔のモデルがなければ False。"""
    try:
        import face_id
        if face_id.engine() is None:
            return False
    except Exception:
        return False
    box = img.convert("RGBA").getchannel("A").getbbox()
    if not box:
        return False
    w, h = box[2] - box[0], box[3] - box[1]
    return w > h * NOFACE_WIDE and face_sharp(img) is None


FLAT_KEEP = 0.4    # 直線の切り口の手前（上）で下を切り落として半身にするとき、残す高さの割合の下限（それより短くなるなら使わない）
def trim_flat(img):
    """直線の切り口を直す：上の端 → 使わない。左右の端 → 切り口が始まる行で下を切り落とし半身にする（下の端だけが直線になる）。
    残りが元の高さの FLAT_KEEP 未満・顔の下まで届かない・形が凹みすぎ（SOLID_MIN）なら ValueError。人物の範囲に切り詰めた画像を返す。"""
    img = img.convert("RGBA")
    img = img.crop(img.getchannel("A").getbbox())
    h0 = img.height
    for _ in range(2):
        r = flat_runs(img)
        if r["top"] > FLAT_TOP:
            raise ValueError(f"上の端に直線の切り口（横幅の {r['top']:.0%}）")
        if max(r["left"], r["right"]) <= FLAT_RUN:
            break
        y, f = r["start"], face_box(img)
        if y < h0 * FLAT_KEEP or f and y < f[1] + f[3] * 1.05:
            raise ValueError(f"左右の端に直線の切り口（左 {r['left']:.0%}・右 {r['right']:.0%}）")
        img = img.crop((0, 0, img.width, y))
        img = img.crop(img.getchannel("A").getbbox())
    else:
        raise ValueError("左右の端に直線の切り口（切り落としても残る）")
    s = solidity(img)
    if s < SOLID_MIN:
        raise ValueError(f"形が凹みすぎている（{s:.2f}）")
    return img


def is_sliver(w, h):
    """切り抜きの大きさ（px）が切れ端・帯か。"""
    return min(w, h) < CUT_MIN or w > h * CUT_WIDE


def save_cut(out, slug):
    """切り抜きを docs/emblems/<slug>.webp に書く。切れ端（is_sliver）は書かずに外す（前の画像を上書きして壊さない）。"""
    out.thumbnail((420, 520))
    if is_sliver(*out.size):
        raise ValueError(f"切れ端（{out.size[0]}×{out.size[1]}）")
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    out.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=88, method=6)


_YUNET = threading.Lock()


def forehead_cut(img):
    """切り抜きが上の端で額まで切れている（いちばん大きい顔の目が、目〜口の距離 × EYE_TOP より上）。
    上に白い余白を足して YuNet で見る（額が切れていても顔を見つける）。顔のモデルがない・顔がない・透明な所がないものは False。"""
    im = img.convert("RGBA")
    if im.getextrema()[3][0] > 200:
        return False
    try:
        import cv2
        import numpy as np
        import face_id
        eng = face_id.engine()
    except Exception:
        return False
    if eng is None:
        return False
    from PIL import Image
    s = max(1.0, 400 / max(im.size))
    w, h = int(im.width * s), int(im.height * s)
    pad = h // 2
    bg = Image.new("RGBA", (w, h + pad), "white")
    bg.alpha_composite(im.resize((w, h)), (0, pad))
    bgr = cv2.cvtColor(np.array(bg.convert("RGB")), cv2.COLOR_RGB2BGR)
    with _YUNET:
        eng[0].setInputSize((bgr.shape[1], bgr.shape[0]))
        f = eng[0].detect(bgr)[1]
    if f is None or not len(f):
        return False
    r = max(f, key=lambda r: r[2] * r[3])
    eye, mouth = (r[5] + r[7]) / 2 - pad, (r[11] + r[13]) / 2 - pad
    return bool(mouth > eye and eye < (mouth - eye) * EYE_TOP)


def lost_face(src, out):
    """写真：元の画像には顔があるのに、切り抜いた結果に顔がない = 違うもの（手・持ち物・暗い背景）を切り抜いた。
    顔のモデル（YuNet）がなければ判断しない（False）。兜・仮面で元から顔がないものは False。"""
    try:
        import face_id
        if face_id.engine() is None:
            return False
        had = face_id.face_info(src.convert("RGB"))[1] or {}
        if not had.get("faces"):
            return False
        bg = __import__("PIL.Image", fromlist=["Image"]).new("RGBA", out.size, "#FFFFFF")
        bg.alpha_composite(out.convert("RGBA"))
        now = face_id.face_info(bg.convert("RGB"))[1] or {}
        return not now.get("faces")
    except Exception:
        return False


def check_whole(out, photo=False):
    """切り抜いた結果を確かめる：人物の全体が見えていること。
    ・いちばん大きいまとまりだけ残す（横に残った小さな切れ端を消す）
    ・左右の端の上 65% に当たっている（体が枠で切れている）ものは使わない。下の端と左右の端の下 35%（胸像の肩）は可
    ・上の端に当たっていても、顔が全部入っていれば可（髪の上だけ切れている）。顔まで切れているもの、
      上の端の半分以上が人物のもの（漫画のコマ・顔のアップを枠ごと切った：吹き出しなどを消した跡がえぐれて残る）は使わない
    ・人物の面積が小さすぎる、または半透明が多い（背景と混ざって輪郭がにじんだ）ものは使わない
    ・写真：切り抜きにほかの人の顔が残っている（いちばん大きい顔の高さの OTHER_FACE 以上）ものは使わない"""
    import numpy as np
    import cv2
    from PIL import Image
    a = np.array(out.getchannel("A"))
    mask = (a > 128).astype("uint8")
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        raise ValueError("人物が見つからない")
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = labels == big
    for i in range(1, n):   # 大きいまとまりの 15% 以上あるもの（離れた手・持ち物）は残す
        if i != big and stats[i, cv2.CC_STAT_AREA] >= PART_KEEP * stats[big, cv2.CC_STAT_AREA]:
            keep |= labels == i
    a = np.where(keep, a, 0).astype("uint8")
    h, w = a.shape
    solid = a > 128
    upper = solid[:int(h * SIDE_ZONE)]   # 下 35%（肩から下）は左右の端に当たってもよい（胸像）
    top, left, right = solid[0, :].mean(), upper[:, 0].mean(), upper[:, -1].mean()
    if top > TOP_MAX:   # 上の端の半分以上が人物：漫画のコマ・顔のアップを枠ごと切ったもの（吹き出しを消した跡がえぐれる。チャドの例）
        raise ValueError(f"頭が上の端で大きく切れている（{top:.0%}：コマ・アップの切り抜き）")
    head = float(solid[:HEAD_ROWS].any(axis=0).mean())   # head_cut と同じ（顔が全部入っていても、髪・頭のてっぺんが切れた絵は使わない）
    if head >= HEAD_EDGE:
        raise ValueError(f"頭のてっぺんが上の端で切れている（上 {HEAD_ROWS}px に {head:.0%}）")
    if top > TOP_TOUCH:
        # 上の端に少し（HEAD_EDGE 未満：髪の先・武器の先）当たっていても、顔が全部入っていればよい
        f = face_box(out)
        if f and f[1] < h * FACE_TOP or forehead_cut(out):
            raise ValueError(f"顔が上の端で切れている（{top:.0%}）")
        if not f:   # 横顔・覆面などで顔が見つからない：外さずに残し、目で確かめる
            print(f"  [目で確認] 上の端に当たっていて顔が見つからない（{top:.0%}）", file=sys.stderr)
    if max(left, right) > SIDE_MAX:
        raise ValueError(f"体が左右の端で切れている（左 {left:.0%}・右 {right:.0%}）")
    if solid.mean() < AREA_MIN:
        raise ValueError("人物が小さすぎる")
    soft = ((a > 24) & (a < 200)).sum() / max(1, (a > 24).sum())
    if soft > SOFT_MAX:
        raise ValueError(f"輪郭がにじんでいる（半透明 {soft:.0%}）")
    if photo:   # 切り抜いた結果にほかの人の顔が残っている（後ろの人・隣の人が体とつながって一緒に切れた）
        others = other_faces(out, keep)
        if others:
            raise ValueError(f"ほかの人が残っている（顔 {others} つ）")
    if photo:   # 暗い場面の切り抜き（顔も体も黒くつぶれて何かわからない）。顔が見えればその明るさで見る
        fq = face_sharp(out)   # （黒いローブ・コートの剧照は体の平均が 7〜15% でも顔ははっきり見える：哈利波特剧集の HBO Max Still）
        lum = fq[2] if fq else float(np.array(out.convert("L"))[solid].mean()) / 255
        if lum < (FACE_DARK if fq else DARK_MAX):
            raise ValueError(f"暗すぎて見えない（{'顔の' if fq else ''}明るさ {lum:.0%}）")
    if photo and faceless_scrap(out):   # 顔がなく横長：額から上だけ・髪だけ（哈利波特剧集 Hermione）
        raise ValueError("顔がなく髪・額だけの切れ端")
    if photo:   # 小さい顔・ぼやけた場面（拡大した剧照：哈利波特剧集 Oliver Wood）は小元素にしない
        if fq and fq[0] < FACE_PX_MIN:
            raise ValueError(f"顔が小さすぎる（幅 {fq[0]}px）")
        if fq and fq[1] < SHARP_MIN:
            raise ValueError(f"ぼやけている（鋭さ {fq[1]:.2f}）")
    holes = hole_share(solid) if photo else 0.0   # 絵は武器・手足のすき間も「穴」に数えてしまう（16% の正しい絵もある）ので、写真だけ
    if holes > HOLE_MAX:
        raise ValueError(f"切り抜きに穴（{holes:.1%}）")
    out = out.copy()
    out.putalpha(Image.fromarray(a))
    return trim_flat(out)   # 左右の直線の切り口は下を切り落として半身に、上の端の直線・凹みすぎは ✗（形の健康）


_SESSIONS = {}


def _session(name):
    """rembg のセッション（1 回だけ作る）。onnxruntime のメモリ池（arena）を切る：池があると、1 枚の切り抜きで
    使った数 GB を返さずに持ち続け、何枚も切るうちに 13GB（コンテナの 15GB のほぼ全部）まで溜まった。"""
    from rembg import new_session
    if name not in _SESSIONS:
        import onnxruntime as ort
        orig = ort.SessionOptions

        def opts():
            o = orig()
            o.enable_cpu_mem_arena = False
            o.enable_mem_pattern = False
            return o
        ort.SessionOptions = opts   # rembg は new_session の中で ort.SessionOptions() を作るので、そのときだけ差し替える
        try:
            _SESSIONS[name] = new_session(name)
        finally:
            ort.SessionOptions = orig
    return _SESSIONS[name]


def slugify(name, subject):
    base = re.sub(r"[^a-z0-9]+", "-", f"{name}-{subject}".lower()).strip("-")
    if len(base) < 6:   # 漢字・かなだけの名前
        import hashlib
        base = (base + "-" if base else "") + hashlib.sha1(f"{name}|{subject}".encode()).hexdigest()[:8]
    return base[:60]


def main_parts(img, share=0.15):
    """いちばん大きいまとまりと、その share 以上の大きさのまとまり（離れた手・持ち物）だけ残す。"""
    import numpy as np
    import cv2
    from PIL import Image
    a = np.array(img.getchannel("A"))
    n, labels, stats, _ = cv2.connectedComponentsWithStats((a > 128).astype("uint8"), 8)
    if n <= 2:
        return img
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    keep = np.isin(labels, [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= share * stats[big, cv2.CC_STAT_AREA]])
    out = img.copy()
    out.putalpha(Image.fromarray(np.where(keep, a, 0).astype("uint8")))
    return out


def upper_body(img, keep=0.46, force=None, ratio=1.75):
    """全身の立ち絵は、頭から腰あたりまで（上から keep の割合）だけにする。版面には小さく貼るので、全身だと顔が見えないため。
    自動の判定：足まで入っている（framing が full）で、高さが幅の ratio 倍以上（等身の高い人物）。
    頭の大きいキャラ（ポチタ・たぬきち・グローグー）や胸像はそのまま。自動で外れるもの（小道具で横に広い人物、
    縦長だけど頭の大きいキャラ）は、AI が items.yaml の小元素に upper: true / false を書いて決める（force）。"""
    img = main_parts(img)   # 周りのきらきら・小さな飾り（離れた小さなまとまり）は消してから測る
    img = img.crop(img.getchannel("A").getbbox())
    w, h = img.size
    cut = force if force is not None else (framing(img) == "full" and h >= w * ratio)
    if not cut:
        return img, False
    img = img.crop((0, 0, w, int(h * keep)))
    return img.crop(img.getchannel("A").getbbox()), True


FACE_SHARE = 0.32   # 顔の高さ ÷ 小元素の高さ。どの版面でも顔が同じくらいの大きさに見えるようにする基準
CLOSEUP = 0.5       # 顔がこれより大きい（顔だけのアップ）は使わず、同じキャラのページから胸像を探す（find_bust）


def face_fit(img, share=FACE_SHARE):
    """人物の小元素を、顔の大きさがそろうように整える。→ (画像, 顔の割合 fs〔顔が見つからなければ None〕)
    顔が小さい（全身など）ときは、頭の上から「顔の高さ ÷ share」までで下を切る。顔が大きい（アップ）ときは切らずに fs を返し、
    網页のほうで小さく表示する（render の --k）。顔が見つからないもの（横顔・覆面・マスコット）は upper_body の規則で。"""
    img = main_parts(img)
    img = img.crop(img.getchannel("A").getbbox())
    f = face_box(img)
    w, h = img.size
    if not f or f[1] + f[3] / 2 > h * 0.35:   # 顔は上 35% にあるはず（下のほうの検出は手や服の誤検出）
        return None, None
    fy, fh = f[1], f[3]
    if fh / h < share:
        bottom = max(fh / share, fy + fh * 1.6)   # 顔が share になる高さ。ただし顔の下（あご・首）は必ず入れる
        fx = f[0]
        bw = fh / share * 1.1                      # 胸像の幅：横に広がる武器・ポーズは顔を中心にこの幅で切る
        left = 0 if w <= bw else int(min(max(0, fx + f[2] / 2 - bw / 2), w - bw))
        cut = img.crop((left, 0, min(w, int(left + bw)) if w > bw else w, min(h, int(bottom))))
        cut = main_parts(cut)
        cut = cut.crop(cut.getchannel("A").getbbox())
        try:   # 横に切った所は体の途中の直線の切り口になる（Gregory Goyle）：切り口が始まる行で下を切って半身に（直せなければそのまま：形の傷は emblem_fill.drop_broken が外して次の候補へ）
            img = trim_flat(cut)
        except ValueError:
            img = cut
        h = img.size[1]
        f2 = face_box(img)
        if f2:
            fh = f2[3]
    return img, round(fh / h, 3)


def find_bust(api, title, word=None, limit=14, lo=0.2, hi=0.45, noface=False, photo=False):
    """顔のアップ（顔が高さの 5 割を超える）しかないとき：同じページに載っている画像から、切り抜いて胸像になるもの
    （顔がはっきり見えて、顔の割合 fs が lo〜hi）を探す。名前に人物名を含む画像を先に、大きい順。→ (網址, 切り抜き画像, fs) か None"""
    from PIL import Image
    from rembg import remove
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "images", "imlimit": 300, "format": "json", "redirects": 1})
    pg = next(iter(json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"].values()))
    # 名前のどれか（姓でも名でも：「Yasutora Sado」の公式イラストは BBSSado.png）がファイル名に入っているもの
    words = [w.lower() for w in ([word] if word else []) + re.split(r"[\s(),]+", title) if len(w) >= 3]
    files = [x["title"] for x in pg.get("images", []) if re.search(r"\.(png|jpe?g|webp)$", x["title"], re.I)
             and any(w in x["title"].lower() for w in words)
             # アイコン類と、季節イベントの衣装（水着・ハロウィン…：いつもの姿ではない）は除く
             and not re.search(r"icon|logo|favicon|signature|kanji|swimsuit|halloween|christmas|valentine|summer|bunny|wedding|new ?year", x["title"], re.I)]
    infos = []
    for i in range(0, len(files), 40):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(files[i:i + 40]), "prop": "imageinfo",
                                    "iiprop": "url|size", "iiurlwidth": 600, "format": "json"})
        for p in json.loads(_get(f"{api}?{q}", 4_000_000))["query"]["pages"].values():
            info = (p.get("imageinfo") or [{}])[0]
            if info.get("width", 0) >= 300 and info.get("height", 0) >= 300:
                infos.append((info["width"] * info["height"], info.get("thumburl") or info["url"], p["title"]))
    backup = None
    for _, url, t in sorted(infos, reverse=True)[:limit]:
        try:
            raw = Image.open(io.BytesIO(_get(url)))
            clear_bg = raw.mode in ("RGBA", "LA", "P") and raw.convert("RGBA").getchannel("A").getextrema()[0] < 16   # もとから透明な背景（公式の立ち絵）
            img = raw.convert("RGB")
            out = check_whole(remove(img, session=_session("birefnet-general-lite")), photo=photo)
            if photo and lost_face(img, out):   # 写真：手・物・暗い背景を切り抜いたもの
                raise ValueError("顔が切り抜きに残っていない")
            fitted, fs = face_fit(out)
            if fs and lo <= fs <= hi:
                print(f"  [胸像] {t}：顔 {fs}", file=sys.stderr)
                return url, fitted, fs
            # 前髪で目が隠れているキャラ（チャド）は顔が見つからない：きれいに切れた一番大きいものを控えに。
            # ただし控えはもとから透明な背景の絵（公式の立ち絵）だけ：漫画のコマ・場面（jpg）は枠で切れ・「©」の文字が残る（ちいかわ のあのこ、2026-10-20）
            if noface and fs is None and backup is None and clear_bg:
                backup = (url, upper_body(out)[0], None)
            print(f"  [合わない] {t}：顔 {fs}", file=sys.stderr)
        except Exception as e:
            print(f"  [合わない] {t}：{e}", file=sys.stderr)
    if backup:
        print(f"  [胸像・顔なし] {backup[0][:80]}（目で確認）", file=sys.stderr)
    return backup


def fit_all(name, drawn=False):
    """その関注項の人物の小元素を、顔の大きさがそろうように整えて docs/emblems/ に保存し、fs（顔の割合）を書く。
    ロゴ・物のアイコン（shape: logo / icon）はそのまま。全身で使うもの（want_full：公式の立ち絵など）は切らずに全身のまま。"""
    import yaml
    from PIL import Image
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    cuts = [x["body"][1] > 1 for x in ems if x.get("body")]   # 前に決めた「上半身に切る / 全身」（モデルがないときはこの多数に合わせる）
    for x in ems:
        if x.get("shape") == "badge" and not x.get("ar") and not x.get("crop"):   # カードの縦横比（窓で切るか全体を見せるかの判断に使う）
            try:
                bw, bh = Image.open(io.BytesIO(_get(x["image"]))).size
                x["ar"] = round(bh / bw, 3)
            except Exception:
                pass
        if x.get("work") and (str(x.get("image", "")).startswith("http") or x.get("source")):
            try:   # 作品の主な画像がタイトルロゴなら、白いカードでなくロゴそのものを大きく（濃い地は板ごと）
                url = x["image"] if str(x["image"]).startswith("http") else x["source"]
                got = wordmark_local(url, slugify(name, x["subject"]))
                if got:
                    x.update(source=url, image=got[0], shape="badge" if got[2] else "logo", ar=got[1])
                    if got[2]:
                        x["plate"] = True
                    else:
                        x.pop("plate", None)
                    print(f"  {x['subject']}：タイトルロゴ → {'板ごと' if got[2] else '地を抜いて'}", file=sys.stderr)
            except Exception as e:
                print(f"  [ロゴ] {x['subject']}：{e}", file=sys.stderr)
        if x.get("shape") in ("logo", "icon") or x.get("work"):
            continue
        try:
            src = x.get("source")
            img = None
            if src:   # 元が透明な立ち絵なら、そこから整え直す（切り詰める前の全身から）
                cand = Image.open(io.BytesIO(_get(src))).convert("RGBA")
                if inspect(_get(src))[0] == "cutout":
                    img = cand
            if img is None:
                img = (Image.open(sitedir.SITE_DIR / x["image"]) if x["image"].startswith("emblems/")
                       else Image.open(io.BytesIO(_get(x["image"])))).convert("RGBA")
            full = want_full(x, drawn, item.get("emblem_framing"))
            if full:
                x.pop("upper", None)   # 前に多数決で書いた「上半身に切る」は、全身と決まったら消す
            out, fs = face_fit(img)
            if full or x.get("upper") is False:   # 全身のまま使う（公式の立ち絵・ほかの小元素が全身）：顔で切らない
                out = main_parts(img)
                out = out.crop(out.getchannel("A").getbbox())
                fs = None
            x.pop("body", None)
            if (full or x.get("upper") is False) and out.size[1] < out.size[0] * STAND_RATIO:   # 縦に立った人の形でない（寝そべり・横長のマスコット・場面）
                pass   # 測らず切らず、全体をふつうの高さで（ぐでたま）
            elif full or x.get("upper") is False:   # 目から足の裏までの長さで大きさをそろえてから、上半身に切る（網页の --bl / --bf）
                mk = body_marks(out)
                if mk:
                    real, why = real_body(out, mk)
                    if real is None:
                        real = bool(cuts) and sum(cuts) * 2 > len(cuts)
                    if real:   # ふつうの人の体つきだけ上半身に。頭の大きいキャラ・動物・マスコットは全身のまま（あつ森・ポチタ）
                        out, body = bust_from_body(out, mk)
                    else:
                        body = list(mk[:5])
                    x["body"] = body
                    print(f"  {x['subject']}：目 {mk[0]} · 足の裏 {mk[1]} · 重心 {mk[2]} · 大きさ {mk[4]}（{mk[5]}）· {why} → {'上半身' if real else '全身'}", file=sys.stderr)
            if fs and fs > CLOSEUP and x.get("page"):   # 顔だけのアップは浮くので、同じキャラのページから胸像を探す
                m = re.match(r"^(https://[^/]+)/wiki/(.+)$", x["page"])
                found = m and find_bust(m.group(1) + "/api.php", urllib.parse.unquote(m.group(2)).replace("_", " "),
                                        word=re.split(r"[\s(]", x["subject"])[0])
                if found:
                    x["image"], out, fs = found[0], found[1], found[2]
                    x.pop("source", None)
            if out is None:
                out, _ = upper_body(img, force=x.get("upper"))
            slug = slugify(name, x["subject"])
            save_cut(out, slug)
            if not x["image"].startswith("emblems/"):
                x["source"] = x["image"]
            x["image"], x["shape"] = f"emblems/{slug}.webp", "cutout"
            if fs:
                x["fs"] = fs
            else:
                x.pop("fs", None)
            if not x.get("body"):
                print(f"  {x['subject']}：顔 {fs if fs else '見つからない（上半身の規則）'}", file=sys.stderr)
        except Exception as e:
            print(f"  [飛ばす] {x['subject']}：{e}", file=sys.stderr)
    _write_emblems(name, ems)


def _write_emblems(name, ems):
    path = ROOT / "items.yaml"
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    j = next(i for i in range(start, len(lines)) if lines[i].startswith("    emblem:"))
    k = j + 1
    while k < len(lines) and lines[k].startswith("      - "):
        k += 1
    keep = ("subject", "why", "image", "source", "page", "shape", "crop", "ar", "upper", "framing", "body", "work", "plate", "fs")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    write_atomic(path, "\n".join(lines))


def upper_all(name):
    """その関注項の小元素のうち、縦長の全身を上半身にして docs/emblems/ に保存する（元の網址は source）。"""
    import yaml
    from PIL import Image
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    for x in ems:
        src = x["image"]
        try:
            img = (Image.open(sitedir.SITE_DIR / src) if src.startswith("emblems/") else Image.open(io.BytesIO(_get(src)))).convert("RGBA")
            out, cut = upper_body(img, force=x.get("upper"))
            if not cut:
                continue
            slug = slugify(name, x["subject"])
            save_cut(out, slug)
            if not src.startswith("emblems/"):
                x["source"] = src
            x["image"], x["shape"] = f"emblems/{slug}.webp", "cutout"
            print(f"  {x['subject']} → 上半身 {x['image']}", file=sys.stderr)
        except Exception as e:
            print(f"  [飛ばす] {x['subject']}：{e}", file=sys.stderr)
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    j = next(i for i in range(start, len(lines)) if lines[i].startswith("    emblem:"))
    k = j + 1
    while k < len(lines) and lines[k].startswith("      - "):
        k += 1
    keep = ("subject", "why", "image", "source", "page", "shape", "upper")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    write_atomic(path, "\n".join(lines))


POSE_MODEL = "yolov8m-pose.pt"   # 体の目印（目・足首）。ultralytics があれば使い、なければ輪郭から推定（Actions には入れていない：PyTorch が重い）
POSE_MIN = 0.5                   # 目印の確かさがこれ未満なら使わない
PEDESTAL = 1.6                   # いちばん下の段の幅が体の幅のこれ倍を超える = 台座（足の裏は台の上の縁）
_POSE = []


def _pose_model():
    if not _POSE:
        try:
            from ultralytics import YOLO
            cache = pathlib.Path.home() / ".cache" / "wishlist-pose"
            cache.mkdir(parents=True, exist_ok=True)
            _POSE.append(YOLO(str(cache / POSE_MODEL)) if (cache / POSE_MODEL).exists() else YOLO(POSE_MODEL))
        except Exception:
            _POSE.append(None)
    return _POSE[0]


def body_marks(img):
    """全身の立ち絵の「目の高さ」「足の裏」「重心」「体の大きさ」→ (eye, foot, cx, ar, size, how)。eye・foot・size は高さに対する割合、
    cx は幅に対する割合、ar = 幅 ÷ 高さ。size（面積の平方根）は、しゃがんだ・前かがみのキャラを大きくしすぎないため（render._body_len）。
    網页では重心を同じ位置に置く（武器・尻尾が横に長くても、体はいつも同じところに立つ）。
    網页では、目から足の裏までの長さがどのキャラも同じになるように縮め、足の裏を帯の線にそろえる（render の --be / --bf）。
    画像のいちばん下は足とは限らない（尻尾・武器・服の裾・影）ので、足首の目印（姿勢モデル）から真下に輪郭をたどって足の裏を探す。
    頭のてっぺんでなく目で測るのは、髪・帽子・耳の高さがキャラごとに違うため。モデルが見つけられなければ輪郭から推定。"""
    import numpy as np
    from PIL import Image
    a = np.array(img.convert("RGBA").getchannel("A")) > 128
    h, w = a.shape
    ys, xs = np.nonzero(a)
    if not len(ys):
        return None
    top, bottom = int(ys.min()), int(ys.max())
    eye = foot = None
    how = "輪郭"
    m = _pose_model()
    if m is not None:
        bg = Image.new("RGBA", img.size, "white")
        bg.alpha_composite(img.convert("RGBA"))
        r = m(bg.convert("RGB"), verbose=False)[0]
        if r.keypoints is not None and len(r.keypoints.xy):
            i = int(np.argmax(r.boxes.conf.cpu().numpy()))
            kp, cf = r.keypoints.xy[i].cpu().numpy(), r.keypoints.conf[i].cpu().numpy()
            eyes = [kp[j][1] for j in (1, 2) if cf[j] >= POSE_MIN] or ([kp[0][1]] if cf[0] >= POSE_MIN else [])
            if eyes:
                eye = float(np.mean(eyes))
            soles = []
            for j in (15, 16):   # 足首から真下へ、足首のまわりの細い帯で輪郭が続くところまで = 足の裏
                if cf[j] < POSE_MIN:
                    continue
                x0, y0 = int(kp[j][0]), int(kp[j][1])
                band = max(3, int(w * 0.04))
                col = a[:, max(0, x0 - band):x0 + band + 1].any(axis=1)
                y, gap = min(max(y0, 0), h - 1), max(2, int(h * 0.03))
                while y + 1 < h and col[y + 1:y + 1 + gap].any():   # 細いヒールのすき間（3% まで）は飛び越える
                    y += 1 + int(np.argmax(col[y + 1:y + 1 + gap]))
                soles.append(y)
            if soles:
                foot = float(max(soles))
            if eye is not None or foot is not None:
                how = "姿勢モデル"
    if eye is None:   # 頭のてっぺんから、立ち絵の高さの 6% 下あたりが目
        eye = top + (bottom - top) * 0.06
    # 重心：体の部分（目の高さから下）の不透明な画素の真ん中。横に長く伸びた武器・尻尾は細いので重心をあまり動かさない
    lo = int(eye if eye is not None else top + (bottom - top) * 0.06)
    hi = int(foot if foot is not None else bottom) + 1
    by, bx = np.nonzero(a[lo:hi])
    cx = float(bx.mean()) if len(bx) else float(xs.mean())
    if foot is None:   # 重心を通る縦の帯でいちばん下 = 足の裏（横に広がった尻尾・武器は帯の外）
        cx = int(cx)
        band = max(4, int((xs.max() - xs.min()) * 0.2))
        rows = np.nonzero(a[:, max(0, cx - band):cx + band + 1].any(axis=1))[0]
        foot = float(rows.max()) if len(rows) else float(bottom)
        # 台座（大乱闘のフィギュアの金の台）：いちばん下が体よりずっと広ければ、台の上の縁を足の裏に
        span = np.array([(np.ptp(np.nonzero(r)[0]) if r.any() else 0) for r in a])
        mid = span[int(foot - (foot - eye) * 0.45):int(foot - (foot - eye) * 0.25)]   # 下半身（台座のすぐ上）の幅。大きな頭の幅は使わない
        body_w = float(np.median(mid[mid > 0])) if (mid > 0).any() else 0
        low = int(foot - (foot - eye) * 0.3)   # 下の 30% に、体よりずっと広い段があれば台座（台の底は楕円で細くなるので、上から探す）
        wide = np.nonzero(span[low:int(foot) + 1] > PEDESTAL * body_w)[0] if body_w else []
        if len(wide):
            y = low + int(wide[0]) - 1
            if foot - y > h * 0.03:
                foot, how = float(y), "輪郭（台座を除く）"
    if foot - eye < h * 0.3:   # 目印がおかしい（座っている・寝ている）：輪郭の上下で
        eye, foot, how = top + (bottom - top) * 0.06, float(bottom), "輪郭"
    size = float(np.sqrt(a[int(eye):int(foot) + 1].sum())) / h   # 体の大きさ（目から足の裏までの面積の平方根）：しゃがんだ・前かがみの体の比べ方に
    return round(eye / h, 3), round(foot / h, 3), round(float(cx) / w, 3), round(w / h, 3), round(size, 3), how


STAND_RATIO = 1.3   # 背の高さを測って上半身に切るのは、輪郭の高さが幅のこれ倍以上（縦に立った人の形）のときだけ
BUST_CUT = 0.40   # 全身の立ち絵を「目 + 目から足の裏の長さ × これ」（腰のあたり）で切って上半身にする。どのキャラも体の同じところで切れる


HIP_MAX = 0.60   # 腰（姿勢モデルの左右の腰の点）が「頭のてっぺん〜足の裏」のこれより上なら、ふつうの人の体つき（実測 0.43〜0.52）。下なら頭の大きい体つき（ちびキャラ・3D のデフォルメ）
BODY_CONF = 0.6   # 姿勢モデルの目印の確かさの平均がこれ未満なら「人の体」と見なさない（動物・マスコット：あつ森の住民、ポチタ）
FACE_REAL = 0.12   # 姿勢モデルが人を見つけられないとき：顔の高さが全体のこれ以下なら、ふつうの人の体つき（武器・髪が多い立ち絵）


def real_body(img, mk):
    """ふつうの人の体つき（頭が全体の 1/7 くらい）か → (True/False, 理由)。上半身に切るのはこのときだけ。
    頭が大きいキャラ（3D のデフォルメ、ちびキャラ）・人の形でないもの（動物、マスコット）は、上半身に切ると何かわからなくなるので全身のまま。
    姿勢モデルで腰の高さを測る（周りに余白を足すと見つけやすい）。見つからなければ顔の大きさで。"""
    import numpy as np
    from PIL import Image
    a = np.array(img.convert("RGBA").getchannel("A")) > 128
    ys = np.nonzero(a)[0]
    w, h = img.size
    top, foot = float(ys.min()), mk[1] * h
    m = _pose_model()
    if m is None:   # モデルがない（Actions）：決めない。fit_all がこの版面のほかの小元素に合わせる
        return None, "姿勢モデルなし（ほかの小元素に合わせる）"
    if m is not None:
        p = int(max(w, h) * 0.15)
        bg = Image.new("RGBA", (w + 2 * p, h + 2 * p), "white")
        bg.alpha_composite(img.convert("RGBA"), (p, p))
        r = m(bg.convert("RGB"), verbose=False)[0]
        if r.keypoints is not None and len(r.boxes):
            i = int(np.argmax(r.boxes.conf.cpu().numpy()))
            kp, cf = r.keypoints.xy[i].cpu().numpy(), r.keypoints.conf[i].cpu().numpy()
            hips = [kp[j][1] - p for j in (11, 12) if cf[j] >= POSE_MIN]
            if cf.mean() >= BODY_CONF and hips:
                hip = (float(np.mean(hips)) - top) / max(1.0, foot - top)
                if hip <= HIP_MAX:
                    return True, f"腰 {hip:.2f}（ふつうの体つき）"
                return False, f"腰 {hip:.2f}（頭が大きい体つき）"
    bg = Image.new("RGBA", img.size, "white")
    bg.alpha_composite(img.convert("RGBA"))
    f = face_box(bg)
    if f and f[3] / max(1.0, foot - top) <= FACE_REAL:
        return True, f"顔 {f[3] / (foot - top):.2f}（ふつうの体つき）"
    return False, "人の体つきが見つからない（動物・マスコット）"


def bust_from_body(img, mk, cut=BUST_CUT):
    """全身の立ち絵を、体の目印（body_marks）で上半身に切る → (画像, body)。
    全身のままだと小さく貼ったとき顔が見えない（绝区零・チェーンソーマン）。背の高さをそろえる測り方（目から足の裏）は
    そのまま使い、切った画像に対する割合に直す：body = [目, 足の裏（切った画像の外 = 1 より大きい）, 重心, 幅÷高さ, 体の大きさ]。
    網页は「目から足の裏」を同じ長さにそろえるので、どのキャラも同じ大きさの上半身になり、ほかの胸像（顔 = 高さの 32%）とも合う。"""
    w, h = img.size
    eye, foot = mk[0] * h, mk[1] * h
    y = int(eye + (foot - eye) * cut)
    if y >= h - 2:
        return img, list(mk[:5])
    part = main_parts(img.crop((0, 0, w, y)))
    box = part.getchannel("A").getbbox() or (0, 0, w, y)
    part = part.crop(box)
    nw, nh = part.size
    cx = (mk[2] * w - box[0]) / max(1, nw)
    return part, [round((eye - box[1]) / nh, 3), round((foot - box[1]) / nh, 3), round(min(1, max(0, cx)), 3),
                  round(nw / nh, 3), round(mk[4] * h / nh, 3)]


def official_render(x):
    """元の画像が透明背景の立ち絵か（ゲーム・アニメの公式の全身イラスト。背景から切り抜いたものではない）。"""
    src = x.get("source") or x.get("image") or ""
    if not src.startswith("http"):
        return False
    try:
        return inspect(_get(src))[0] == "cutout"
    except Exception:
        return False


def want_full(x, drawn, item_framing=None):
    """この小元素を全身のまま使うか（顔で胸像に切らない）。決め方の順：
    1. 小元素に framing: full / bust と書いてあればそれ（1 枚ごとの指定）
    2. 関注項に emblem_framing: full / bust と書いてあればそれ（版面ごとの指定）
    3. 絵のキャラで、元の画像が透明背景の公式の立ち絵 → 全身（もともと全身で見せる絵。切るともったいない：絶区零・dota2・あつ森）
    4. それ以外（写真・漫画のコマ・動画の場面・背景つきの絵から切り抜いたもの）→ 胸像（全身は枠で切れたり余計な物が入ったりする）"""
    if x.get("framing") in ("full", "bust"):
        return x["framing"] == "full"
    if item_framing in ("full", "bust"):
        return item_framing == "full"
    return bool(drawn) and official_render(x)


def keep_framing(ems, old=(), drawn=False, item_framing=None):
    """同じ版面の小元素は取景をそろえる（胸像と全身が混ざると、顔の大きさがばらばらに見える）。多いほうに合わせる：
    ・胸像が多い：全身のものは捨てずに上半身に切る（upper: true → fit_all で上 46%）。要素の多い版面で枚数を減らさない
    前からある小元素（old の画像）は外さないし、切り直しもしない。
    ・全身が多い（あつ森の住民・dota2 のヒーロー）：全身の立ち絵は切らずに全身のまま（upper: false）、
      もとから胸像のものは外す。ただし前からある小元素（old の画像）は外さない
    全身でも、顔が見つかる（face_fit で胸像に切れる）か縦長の立ち絵（upper_body で切れる）なら、もともと胸像に数える。
    前は「胸像が 1 枚でもあれば全身は全部外す」で、新しい 1 枚のために前からの小元素まで消えていた。
    透明な立ち絵（もとから切り抜き）は docs/emblems にないので、元の画像で判定する。
    want_full で全身と決まったもの（公式の立ち絵・framing の指定）は、胸像が多くても切らない。"""
    from PIL import Image
    old = set(old)
    for x in ems:
        if "_framing" not in x and want_full(x, drawn, item_framing):   # 全身で使うと決まったもの（公式の立ち絵）は、多数決で切らない
            x["_framing"], x["_fixed"] = "full", True
        if "_framing" not in x:
            try:
                img = (Image.open(sitedir.SITE_DIR / x["image"]) if x["image"].startswith("emblems/")
                       else Image.open(io.BytesIO(_get(x["image"]))).convert("RGBA"))
                x["_framing"] = framing(img)
                if x["_framing"] == "full" and (face_fit(img)[1] or upper_body(img, force=x.get("upper"))[1]):
                    x["_framing"], x["_can_full"] = "bust", True   # あとで胸像に切れる（切らなければ全身のまま使える）
            except Exception:
                x["_framing"] = "full"
    # どちらにもなれる（全身の立ち絵で、切れば胸像になる）ものは数えず、決まっているものの多いほうに合わせる
    busts = sum(x["_framing"] == "bust" and not x.get("_can_full") for x in ems)
    fulls = sum(x["_framing"] == "full" for x in ems)
    if not fulls:
        return ems
    if busts >= fulls:
        for x in ems:
            if x["_framing"] == "full" and x.get("upper") is not False and x["image"] not in old and not x.get("_fixed"):   # 前からの小元素・公式の立ち絵は切り直さない
                print(f"  [取景をそろえる] {x['subject']} は全身なので上半身に切る（ほかの多くは胸像）", file=sys.stderr)
                x["upper"] = True
        return ems
    keep = []
    for x in ems:
        if x["_framing"] == "bust" and x.get("_can_full") and x["image"] not in old:   # 全身の立ち絵：胸像に切らずに全身のまま（dota2 のヒーロー）
            x["upper"] = False
            keep.append(x)
            continue
        if x["_framing"] == "bust" and x["image"] not in old:
            print(f"  [取景をそろえる] {x['subject']} は胸像なので外す（ほかの多くは全身）", file=sys.stderr)
            if x["image"].startswith("emblems/"):
                (sitedir.SITE_DIR / x["image"]).unlink(missing_ok=True)
            continue
        keep.append(x)
    return keep


def cut_all(name, drawn, old=()):
    """items.yaml のその関注項の「カード」（badge）の小元素を全部切り抜きに替える（source に元の網址を残す）。"""
    import yaml
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    for x in ems:
        if x.get("shape") != "badge" or x.get("work"):   # 作品の主な画像（ポスター）は切り抜かない
            continue
        try:
            src = x.get("source") or x["image"]
            x["image"] = cut_out(src, slugify(name, x["subject"]), drawn)
            from PIL import Image
            x["_framing"] = framing(Image.open(sitedir.SITE_DIR / x["image"]))
            x["source"], x["shape"] = src, "cutout"
            x.pop("crop", None); x.pop("ar", None)
            print(f"  {x['subject']} → {x['image']}", file=sys.stderr)
        except Exception as e:
            # 代表画像がだめ（漫画のコマ・枠で切れている）でも、同じページに公式イラストがあればそちらで（チャドの例）
            m = re.match(r"^(https://[^/]+)/wiki/(.+)$", x.get("page") or "")
            found = None
            if m and "/wiki/File:" not in x["page"]:
                try:
                    found = find_bust(m.group(1) + "/api.php", urllib.parse.unquote(m.group(2)).replace("_", " "), lo=0.12,
                                      noface=drawn, photo=not drawn)   # 顔なしの控えは絵のキャラだけ（前髪で目が隠れる）。写真は顔が残っていること
                except Exception as e2:
                    print(f"  [胸像探し失敗] {x['subject']}：{e2}", file=sys.stderr)
            if found:
                try:
                    save_cut(found[1], slugify(name, x["subject"]))
                except ValueError as e3:
                    print(f"  [切れ端] {x['subject']}：{e3}", file=sys.stderr)
                    found = None
            if found:
                slug = slugify(name, x["subject"])
                img = found[1]
                x.update(image=f"emblems/{slug}.webp", source=found[0], shape="cutout", _framing=framing(img),
                         why=f"{x.get('why') or x['subject']} → 同じページの別の画像（代表画像は切り抜きの検査で外れた）")   # 元の理由（役の記事など）は残す
                if found[2]:
                    x["fs"] = found[2]
                print(f"  {x['subject']} → {x['image']}（同じページの別の画像）", file=sys.stderr)
            else:
                x["_drop"] = True
                print(f"  [飛ばす] {x['subject']}：{e}", file=sys.stderr)
    ems = keep_framing([x for x in ems if not x.get("_drop")], old, drawn, item.get("emblem_framing"))
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    j = next(i for i in range(start, len(lines)) if lines[i].startswith("    emblem:"))
    k = j + 1
    while k < len(lines) and lines[k].startswith("      - "):
        k += 1
    keep = ("subject", "why", "image", "source", "page", "shape", "crop", "ar", "upper", "framing", "body", "work", "plate", "fs")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    write_atomic(path, "\n".join(lines))


def main():
    if len(sys.argv) in (3, 4) and sys.argv[1] == "--fit":   # --fit 関注項 [drawn]：顔の大きさをそろえる（drawn = 絵のキャラ）
        return fit_all(sys.argv[2], sys.argv[3:] == ["drawn"])
    if len(sys.argv) == 3 and sys.argv[1] == "--upper":   # --upper 関注項：縦長の全身を上半身に
        return upper_all(sys.argv[2])
    if len(sys.argv) == 4 and sys.argv[1] == "--cut":   # --cut 関注項 drawn|photo
        return cut_all(sys.argv[2], sys.argv[3] == "drawn")
    if len(sys.argv) == 3 and sys.argv[1] == "--recrop":
        return recrop(sys.argv[2])
    ap = argparse.ArgumentParser(description="作品の小元素を探して配色を合わせる")
    ap.add_argument("name", help="items.yaml の関注項の名前")
    ap.add_argument("--api", required=True, help="MediaWiki の api.php（例 https://chainsaw-man.fandom.com/api.php）")
    ap.add_argument("--titles", nargs="*", default=[], help="Wiki のページ名（先頭がいちばん代表的なもの）")
    ap.add_argument("--why", default="", help="--titles を選んだ理由（一行）")
    ap.add_argument("--anilist", help="AniList の作品 id：主役を足す")
    ap.add_argument("--gallery", help="キャラが一人の作品：このページの画像から別シーンを集める")
    ap.add_argument("--match", help="--gallery で使う画像ファイル名の正規表現")
    ap.add_argument("--max", type=int, default=6, help="最大の枚数")
    ap.add_argument("--category", help="Wiki の分類：リンクの多いキャラから足す（AniList にない作品の主要キャラ）")
    ap.add_argument("--tone", choices=["light", "dark"],
                    help="作品の気質：dark＝熱血・暴力・ホラー・SF（墨の地）、light＝かわいい・癒やし・日常（米白の地）")
    ap.add_argument("--palette", choices=["emblem", "keep"], default="emblem",
                    help="emblem＝絵の代表色から配色を作る（キャラの絵）／keep＝今の配色のまま（人物・製品の写真は色がばらつくため）")
    ap.add_argument("--write", action="store_true", help="items.yaml に書く")
    a = ap.parse_args()
    if a.palette == "emblem" and not a.tone:
        ap.error("--palette emblem のときは --tone が要る")
    found, th = collect(a.api, a.titles, a.anilist, a.gallery, a.match, a.max, a.why, a.tone if a.palette == "emblem" else None, a.category)
    print(json.dumps({"emblem": found, "theme": th}, ensure_ascii=False, indent=2))
    if a.write:
        write_item(a.name, found, th)
        print(f"→ items.yaml の「{a.name}」に {len(found)} 枚を書きました")


if __name__ == "__main__":
    main()
