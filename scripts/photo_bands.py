"""別のサイトの写真を、ページを作るときに 1 回だけ取って測り、img に書く（2026-11-08，店長：余白は枠の 4 分の 1 まで・文字を欠かさない）。

ブラウザは別のサイトの写真の中身を読めない（CORS）。お客さまのページの写真の多くは元のサイトから直接読むので、Actions が測る。
    data-t="上,右,下,左,#端の色"   写真に焼き込まれた無地の余白の割合（余白がなければ付けない）
    data-m="横の分布;縦の分布"      顔・題字の分布（photo_store.mass と同じ。店長のページの写真と同じ物差しで切る位置を選ぶ）
測った結果は網址ごとに残し（cache）、同じ写真は二度取りに行かない。
"""
import concurrent.futures as cf
import html as htmllib
import io
import re

MAX_NEW = 400          # 1 回で新しく測る数の上限（Actions の時間を守る）
IMG_RE = re.compile(r'<img src="(https?://[^"]+)"')
FLAT = 24              # 同じ色とみなす差（RGB の差の合計）
MIN_BAND = 0.04        # これより細い余白は外さない


def bands(data):
    """画像のバイト列 → [上, 右, 下, 左, '#rrggbb']（余白がなければ []）。"""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    if w < 32 or h < 32:
        return []
    W, H = 64, max(8, round(64 * h / w))
    px = im.resize((W, H)).load()

    def same(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) <= FLAT

    def flat(cells):
        s = cells[0]
        return all(same(c, s) for c in cells[1:])

    t = 0
    while t < H // 2 and flat([px[x, t] for x in range(W)]):
        t += 1
    b = 0
    while b < H // 2 and flat([px[x, H - 1 - b] for x in range(W)]):
        b += 1
    l = 0
    while l < W // 2 and flat([px[l, y] for y in range(H)]):
        l += 1
    r = 0
    while r < W // 2 and flat([px[W - 1 - r, y] for y in range(H)]):
        r += 1
    f = [t / H, r / W, b / H, l / W]
    if max(f) < MIN_BAND or f[0] + f[2] >= 0.7 or f[1] + f[3] >= 0.7:
        return []
    e = px[0, 0]
    return [round(v, 3) for v in f] + ["#%02x%02x%02x" % e]


def mass_css(data):
    """顔・題字の分布（photo_store.mass）を data-m の文字列に。測れなければ ""。"""
    try:
        import photo_store
        v = photo_store.mass(data)
    except Exception:  # noqa: BLE001  cv2 が無い・壊れた画像 → 位置なし（切らない）
        return ""
    return ";".join(",".join(map(str, a)) for a in v) if v else ""


def measure(urls, cache, fetch, log=print):
    """まだ測っていない網址を測って cache に入れる（MAX_NEW まで）。→ 新しく測った数"""
    todo = [u for u in dict.fromkeys(urls) if not isinstance(cache.get(u), dict)][:MAX_NEW]   # 前の形（余白だけのリスト）は測り直す

    def one(u):
        try:
            data = fetch(u)
            return u, ({"t": bands(data), "m": mass_css(data)} if data else {"t": [], "m": ""})
        except Exception:  # noqa: BLE001  開けない写真は「測れない」として次から取りに行かない
            return u, {"t": [], "m": ""}
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for u, v in ex.map(one, todo):
            cache[u] = v
    if todo:
        log(f"写真の余白と主役：{len(todo)} 枚を測った（余白あり {sum(1 for u in todo if cache[u]['t'])}・主役の位置 {sum(1 for u in todo if cache[u]['m'])}）")
    return len(todo)


def urls_in(text):
    return [htmllib.unescape(u) for u in IMG_RE.findall(text)]


def inject(text, cache):
    """<img src="網址" に data-t（余白）と data-m（主役の位置。まだ無いときだけ）を足す。"""
    def rep(m):
        v = cache.get(htmllib.unescape(m.group(1)))
        if isinstance(v, list):
            v = {"t": v, "m": ""}
        if not isinstance(v, dict):
            return m.group(0)
        out = m.group(0)
        if v.get("t"):
            out += f' data-t="{",".join(map(str, v["t"]))}"'
        if v.get("m"):
            out += f' data-mx="{v["m"]}"'
        return out
    text = IMG_RE.sub(rep, text)
    # data-mx は、同じ img にまだ data-m が無いときだけ data-m にする（店長のページの写真は render が付けた data-m を使う）
    return re.sub(r'<img ([^>]*?)data-mx="([^"]*)"([^>]*)>', lambda m: m.group(0).replace(f'data-mx="{m.group(2)}"', "" if "data-m=" in m.group(0) else f'data-m="{m.group(2)}"'), text)
