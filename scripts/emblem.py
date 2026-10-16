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
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import theme  # noqa: E402
from sources import TIMEOUT, USER_AGENT  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_BYTES = 6_000_000
MIN_SIDE = 160


def _get(url, limit=MAX_BYTES):
    import time
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for wait in (0, 3, 8, 20):   # Wikipedia などの「多すぎ」（429）は少し待って取り直す
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


def page_image(api, title):
    """MediaWiki の pageimages：そのページの代表画像の網址と、ページの網址。"""
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "pageimages|info", "piprop": "original|thumbnail",
                                "pithumbsize": 500, "inprop": "url", "format": "json", "redirects": 1})
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
    if min(w, h) < MIN_SIDE:
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


def category_top(api, category, n):
    """Wiki の分類（例：Wizards）のキャラを「ほかのページからのリンク数」→「記事の長さ」の順に多い n 人。
    物語の中心にいるキャラほど多くのページから参照される（AniList にないゲームなどで主要キャラを決める基準）。"""
    q = urllib.parse.urlencode({"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
                                "cmlimit": 200, "cmnamespace": 0, "format": "json"})
    titles = [m["title"] for m in json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["categorymembers"]]
    counts, length = {}, {}
    for t in titles:
        q = urllib.parse.urlencode({"action": "query", "titles": t, "prop": "linkshere|info", "lhlimit": 500,
                                    "lhnamespace": 0, "lhshow": "!redirect", "format": "json"})
        pg = next(iter(json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"].values()))
        counts[t], length[t] = len(pg.get("linkshere", [])), pg.get("length", 0)
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
    word = re.split(r"[\s(]", title)[0].lower()
    files.sort(key=lambda f: (word not in f.lower(), "icon" in f.lower() or "logo" in f.lower()))
    best = None
    for i in range(0, min(len(files), limit), 20):
        q = urllib.parse.urlencode({"action": "query", "titles": "|".join(files[i:i + 20]), "prop": "imageinfo",
                                    "iiprop": "url|size", "iiurlwidth": 400, "format": "json"})
        for p in json.loads(_get(f"{api}?{q}", 4_000_000))["query"]["pages"].values():
            info = (p.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if not url or word not in p["title"].lower():
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
    lines = path.read_text(encoding="utf-8").split("\n")
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
    keep = ("subject", "why", "image", "page", "shape", "crop", "ar")
    block[at:at] = (["    emblem:  # 作品の小元素（scripts/emblem.py）：網页を開くたびに 1 枚をランダムに出す。先頭が配色の基準"]
                    + [f"      - {_flow({k: x[k] for k in keep if k in x})}" for x in emblems]
                    + ([f"    theme: {_flow(th)}  # 小元素「{emblems[0]['subject']}」の色に合わせた配色（scripts/emblem.py）"] if th else []))
    lines[start + 1:end] = block
    path.write_text("\n".join(lines), encoding="utf-8")


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
    path.write_text("\n".join(lines), encoding="utf-8")


EMB_DIR = ROOT / "docs" / "emblems"   # 切り抜いた画像（網页と同じ場所に置く。倉庫は公開なので画像も公開になる）


def cut_out(url, slug, drawn=True):
    """背景のある画像から人物だけを切り抜いて docs/emblems/<slug>.webp に保存し、網页から読む相対パスを返す。
    rembg の birefnet-general-lite（絵も写真も）。輪郭の外側の余白は切り詰める。中身（人物）は変えない。
    暗い背景に暗い人物・網点の漫画コマなど、輪郭がにじむものは切り抜いた結果を目で見て、だめなら外す。"""
    from PIL import Image
    from rembg import new_session, remove

    img = Image.open(io.BytesIO(_get(url))).convert("RGB")
    out = remove(img, session=_session("birefnet-general-lite"))   # 絵も写真もいちばん輪郭がきれいだった（isnet-anime・u2net と比べた）
    out = check_whole(out)
    out, _ = upper_body(out)   # 縦長の全身は上半身に（小さく貼ると顔が見えない）
    out.thumbnail((420, 520))
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    out.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=88, method=6)
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
            found += [tuple(map(int, f)) for f in c.detectMultiScale(gray, 1.1, 4, minSize=(max(24, w // 10),) * 2)]
    return max(found, key=lambda f: f[2] * f[3]) if found else None


def check_whole(out):
    """切り抜いた結果を確かめる：人物の全体が見えていること。
    ・いちばん大きいまとまりだけ残す（横に残った小さな切れ端を消す）
    ・左右の端の上 65% に当たっている（体が枠で切れている）ものは使わない。下の端と左右の端の下 35%（胸像の肩）は可
    ・上の端に当たっていても、顔が全部入っていれば可（髪の上だけ切れている）。顔まで切れているものは使わない
    ・人物の面積が小さすぎる、または半透明が多い（背景と混ざって輪郭がにじんだ）ものは使わない"""
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
        if i != big and stats[i, cv2.CC_STAT_AREA] >= 0.15 * stats[big, cv2.CC_STAT_AREA]:
            keep |= labels == i
    a = np.where(keep, a, 0).astype("uint8")
    h, w = a.shape
    solid = a > 128
    upper = solid[:int(h * 0.65)]   # 下 35%（肩から下）は左右の端に当たってもよい（胸像）
    top, left, right = solid[0, :].mean(), upper[:, 0].mean(), upper[:, -1].mean()
    if top > 0.03:
        # 上の端で切れていても、顔が全部入っていれば（髪の上だけが切れている：恋次のような絵）よい
        f = face_box(out)
        if f and f[1] < h * 0.04:
            raise ValueError(f"顔が上の端で切れている（{top:.0%}）")
        if not f:   # 横顔・覆面などで顔が見つからない：外さずに残し、目で確かめる
            print(f"  [目で確認] 上の端に当たっていて顔が見つからない（{top:.0%}）", file=sys.stderr)
    if max(left, right) > 0.10:
        raise ValueError(f"体が左右の端で切れている（左 {left:.0%}・右 {right:.0%}）")
    if solid.mean() < 0.12:
        raise ValueError("人物が小さすぎる")
    soft = ((a > 24) & (a < 200)).sum() / max(1, (a > 24).sum())
    if soft > 0.18:
        raise ValueError(f"輪郭がにじんでいる（半透明 {soft:.0%}）")
    out = out.copy()
    out.putalpha(Image.fromarray(a))
    return out


_SESSIONS = {}


def _session(name):
    from rembg import new_session
    if name not in _SESSIONS:
        _SESSIONS[name] = new_session(name)
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
        img = img.crop((0, 0, w, min(h, int(bottom))))
        img = img.crop(img.getchannel("A").getbbox())
        h = img.size[1]
    return img, round(fh / h, 3)


def fit_all(name):
    """その関注項の人物の小元素を、顔の大きさがそろうように整えて docs/emblems/ に保存し、fs（顔の割合）を書く。
    ロゴ・物のアイコン（shape: logo / icon）はそのまま。"""
    import yaml
    from PIL import Image
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    for x in ems:
        if x.get("shape") in ("logo", "icon"):
            continue
        try:
            src = x.get("source")
            img = None
            if src:   # 元が透明な立ち絵なら、そこから整え直す（切り詰める前の全身から）
                cand = Image.open(io.BytesIO(_get(src))).convert("RGBA")
                if inspect(_get(src))[0] == "cutout":
                    img = cand
            if img is None:
                img = (Image.open(ROOT / "docs" / x["image"]) if x["image"].startswith("emblems/")
                       else Image.open(io.BytesIO(_get(x["image"])))).convert("RGBA")
            out, fs = face_fit(img)
            if out is None:
                out, _ = upper_body(img, force=x.get("upper"))
            slug = slugify(name, x["subject"])
            out.thumbnail((420, 520))
            EMB_DIR.mkdir(parents=True, exist_ok=True)
            out.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=88, method=6)
            if not x["image"].startswith("emblems/"):
                x["source"] = x["image"]
            x["image"], x["shape"] = f"emblems/{slug}.webp", "cutout"
            if fs:
                x["fs"] = fs
            else:
                x.pop("fs", None)
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
    keep = ("subject", "why", "image", "source", "page", "shape", "upper", "fs")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    path.write_text("\n".join(lines), encoding="utf-8")


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
            img = (Image.open(ROOT / "docs" / src) if src.startswith("emblems/") else Image.open(io.BytesIO(_get(src)))).convert("RGBA")
            out, cut = upper_body(img, force=x.get("upper"))
            if not cut:
                continue
            slug = slugify(name, x["subject"])
            out.thumbnail((420, 520))
            EMB_DIR.mkdir(parents=True, exist_ok=True)
            out.save(EMB_DIR / f"{slug}.webp", "WEBP", quality=88, method=6)
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
    path.write_text("\n".join(lines), encoding="utf-8")


def keep_framing(ems):
    """同じ版面の小元素は取景をそろえる：胸像が一枚でもあれば、全身のもの（比率が浮く）は外す。全部全身ならそのまま。
    透明な立ち絵（もとから切り抜き）は docs/emblems にないので、元の画像で判定する。"""
    from PIL import Image
    for x in ems:
        if "_framing" not in x:
            try:
                img = (Image.open(ROOT / "docs" / x["image"]) if x["image"].startswith("emblems/")
                       else Image.open(io.BytesIO(_get(x["image"]))).convert("RGBA"))
                x["_framing"] = framing(img)
            except Exception:
                x["_framing"] = "full"
    if any(x["_framing"] == "bust" for x in ems):
        for x in ems:
            if x["_framing"] == "full":
                print(f"  [取景をそろえる] {x['subject']} は全身なので外す（ほかは胸像）", file=sys.stderr)
                if x["image"].startswith("emblems/"):
                    (ROOT / "docs" / x["image"]).unlink(missing_ok=True)
        ems = [x for x in ems if x["_framing"] == "bust"]
    return ems


def cut_all(name, drawn):
    """items.yaml のその関注項の「カード」（badge）の小元素を全部切り抜きに替える（source に元の網址を残す）。"""
    import yaml
    path = ROOT / "items.yaml"
    item = next(i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["items"] if i["name"] == name)
    ems = item.get("emblem") or []
    for x in ems:
        if x.get("shape") != "badge":
            continue
        try:
            src = x.get("source") or x["image"]
            x["image"] = cut_out(src, slugify(name, x["subject"]), drawn)
            from PIL import Image
            x["_framing"] = framing(Image.open(ROOT / "docs" / x["image"]))
            x["source"], x["shape"] = src, "cutout"
            x.pop("crop", None); x.pop("ar", None)
            print(f"  {x['subject']} → {x['image']}", file=sys.stderr)
        except Exception as e:
            x["_drop"] = True
            print(f"  [飛ばす] {x['subject']}：{e}", file=sys.stderr)
    ems = keep_framing([x for x in ems if not x.get("_drop")])
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if re.match(rf'^  - name: "?{re.escape(name)}"?\s*$', l))
    j = next(i for i in range(start, len(lines)) if lines[i].startswith("    emblem:"))
    k = j + 1
    while k < len(lines) and lines[k].startswith("      - "):
        k += 1
    keep = ("subject", "why", "image", "source", "page", "shape", "crop", "ar", "upper")
    lines[j + 1:k] = [f"      - {_flow({kk: x[kk] for kk in keep if kk in x})}" for x in ems]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--fit":   # --fit 関注項：顔の大きさをそろえる
        return fit_all(sys.argv[2])
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
