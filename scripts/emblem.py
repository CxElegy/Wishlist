"""作品の小元素（版面の右上に貼るステッカー）を探して、版面の配色をそれに合わせる。

絵は自作しない。見ればその作品だと分かる既存の画像を探して、そのまま使う（中身は変えない）。
網页は画像を元の網址で直接引用し（新聞の配図と同じ、倉庫には保存しない）、白いフチ・色のフチ・硬い影・傾き・
スクロールで飛び出す効果だけを CSS で付ける。一つの版面に何枚あってもよく、網页を開くたびに 1 枚をランダムに出す。

探し方（AI 編集が新しい関注項を設計するときに使う）：
  1. 何を貼るか決める ── 枚数は「主要キャラの数」に合わせる：
     ・アニメ・漫画：AniList の主役（role MAIN、お気に入り順）。作品の顔になっているマスコットがいれば先頭に足す（例：ポチタ）
     ・ゲーム・ドラマなど AniList にないもの：シリーズでいちばん知られたキャラを AI が選んで --titles に並べる（理由を書く）
     ・キャラが一人だけの作品（ぐでたま）：その Wiki ページに載っている画像から、有名な別シーンを何枚か（--gallery）
  2. その作品のファン Wiki（Fandom など MediaWiki）で、キャラのページの代表画像（pageimages）を取る。
     Fandom にページがなければ別の Wiki（Sanrio 系・Nookipedia・Wikipedia）を試す。
  3. 使えるか確かめる：短い辺が 160px 以上。縁の 90% 以上が透明なら「切り抜き」（輪郭どおりのステッカー）、
     そうでなければ「バッジ」（丸く切って貼る。絵の中身はそのまま）。使えないものは飛ばす。
  4. 版面の配色を合わせる：先頭（いちばん代表的な一枚）の代表色（不透明な部分で「面積 × 鮮やかさ²」が最大の色）を
     強調色に、その色寄りの米白を地、墨色を副面にする。文字はどれも 4.5:1 以上（theme._readable）。
     キャラが入れ替わっても浮かないように、どの絵にも版面の強調色のフチと墨の硬い影を付ける（emblem_ring）。
  5. items.yaml に emblem（リスト：subject / why / image / page / shape）と theme を書く。

使い方：
  python scripts/emblem.py "チェーンソーマン" --api https://chainsaw-man.fandom.com/api.php \
      --titles Pochita --why "作品の顔のマスコット" --anilist 127230 --max 5 [--write]
  python scripts/emblem.py "ぐでたま" --api https://hellokitty.fandom.com/api.php --gallery Gudetama --match Gudetama --max 4
"""

import argparse
import io
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import theme  # noqa: E402
from sources import TIMEOUT, USER_AGENT  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_BYTES = 6_000_000
MIN_SIDE = 160


def _get(url, limit=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("画像が大きすぎる")
    return data


def page_image(api, title):
    """MediaWiki の pageimages：そのページの代表画像の網址と、ページの網址。"""
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "pageimages|info", "piprop": "original",
                                "inprop": "url", "format": "json", "redirects": 1})
    pages = json.loads(_get(f"{api}?{q}", 2_000_000))["query"]["pages"]
    page = next(iter(pages.values()))
    src = (page.get("original") or {}).get("source")
    if not src:
        raise LookupError(f"{title}：代表画像がない")
    return src, page.get("fullurl") or ""


def small_url(src, width=400):
    """Fandom の画像は縮小版の網址にする（網页で 130px ほどにしか出さないので、重い原寸は引かない）。"""
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


def palette(key):
    """代表色 → 版面の配色。地は代表色寄りの米白、強調は代表色（読める濃さに）、副面は代表色寄りの墨。"""
    bg = theme._shift(key, 0.94, max_sat=0.45)
    fg = (30, 26, 24)
    accent = theme._readable(theme._shift(key, 0.45, max_sat=0.85), bg)
    alt_bg = theme._shift(key, 0.12, max_sat=0.25)
    alt_fg = (244, 238, 228)
    alt_accent = theme._readable(theme._shift(key, 0.6, max_sat=0.85), alt_bg)
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


def one(api, title):
    src, page = page_image(api, title)
    url = small_url(src)
    shape, key, _ = inspect(_get(url))
    return {"subject": title, "image": url, "page": page, "shape": shape, "key": theme._hex(key)}


def collect(api, titles=(), anilist=None, gallery_page=None, match=None, n=6, why=""):
    """候補を集めて使えるものだけ残す。先頭がいちばん代表的な一枚（配色の基準）。"""
    found, seen = [], set()
    names = [(t, why or "AI が選んだ代表キャラ") for t in titles]
    if anilist:
        names += [(t, "AniList の主役（お気に入り順）") for t in anilist_main(anilist, n)]
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
    return found, palette(theme._rgb(found[0]["key"]))


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
        if re.match(r"^    (emblem|theme):", l):
            skip = l.startswith("    emblem:")
            continue
        if skip and l.startswith("      - "):
            continue
        skip = False
        block.append(l)
    at = next((i + 1 for i, l in enumerate(block) if l.startswith("    motif:")), 0)
    keep = ("subject", "why", "image", "page", "shape")
    block[at:at] = (["    emblem:  # 作品の小元素（scripts/emblem.py）：網页を開くたびに 1 枚をランダムに出す。先頭が配色の基準"]
                    + [f"      - {_flow({k: x[k] for k in keep})}" for x in emblems]
                    + [f"    theme: {_flow(th)}  # 小元素「{emblems[0]['subject']}」の色に合わせた配色（scripts/emblem.py）"])
    lines[start + 1:end] = block
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="作品の小元素を探して配色を合わせる")
    ap.add_argument("name", help="items.yaml の関注項の名前")
    ap.add_argument("--api", required=True, help="MediaWiki の api.php（例 https://chainsaw-man.fandom.com/api.php）")
    ap.add_argument("--titles", nargs="*", default=[], help="Wiki のページ名（先頭がいちばん代表的なもの）")
    ap.add_argument("--why", default="", help="--titles を選んだ理由（一行）")
    ap.add_argument("--anilist", help="AniList の作品 id：主役を足す")
    ap.add_argument("--gallery", help="キャラが一人の作品：このページの画像から別シーンを集める")
    ap.add_argument("--match", help="--gallery で使う画像ファイル名の正規表現")
    ap.add_argument("--max", type=int, default=6, help="最大の枚数")
    ap.add_argument("--write", action="store_true", help="items.yaml に書く")
    a = ap.parse_args()
    found, th = collect(a.api, a.titles, a.anilist, a.gallery, a.match, a.max, a.why)
    print(json.dumps({"emblem": found, "theme": th}, ensure_ascii=False, indent=2))
    if a.write:
        write_item(a.name, found, th)
        print(f"→ items.yaml の「{a.name}」に {len(found)} 枚を書きました")


if __name__ == "__main__":
    main()
