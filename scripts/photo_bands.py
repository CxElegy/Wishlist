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
BREATH = 0.03          # 余白を外しても残す幅（物の周りの息をする余白）


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
    bl = blur_bands(im)   # ぼかした余白（無地でなく、細かい模様がほとんど無い縁。2026-11-08 NBA の写真）
    if bl:
        f = [max(x, y) for x, y in zip(f, bl)]
    if max(f) < MIN_BAND or f[0] + f[2] >= 0.7 or f[1] + f[3] >= 0.85:   # 横は 85% まで（中の空きで 2 つの物の片方だけ残すとき）
        return []
    f = [max(0.0, v - BREATH) if v > 0 else 0.0 for v in f]   # 物の周りに少し余白を残す（ぎりぎりで切らない。2026-11-08 店長「裁的太多了」）
    e = px[0, 0]
    return [round(v, 3) for v in f] + ["#%02x%02x%02x" % e]


SEG = []   # 直前の blur_bands が見つけた「空きを挟んだ 2 つの物」の横の範囲（bands が読んで返す）


def segments(data):
    """空きを挟んだ 2 つ以上の大事な物の横の範囲 [[左, 右], ...]（無ければ []）。"""
    from PIL import Image
    SEG[:] = []
    blur_bands(Image.open(io.BytesIO(data)).convert("RGB"))
    return [list(s) for s in SEG]


def blur_bands(im):
    """縁の列・行のうち、輪郭の濃さが写真の濃い所（上位 1 割）の 12% 未満が続く幅 → [上, 右, 下, 左] の割合。測れなければ None。"""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return None
    w, h = im.size
    W, H = 160, max(16, round(160 * h / w))
    g = np.asarray(im.convert("L").resize((W, H)), dtype=np.float32)
    gx, gy = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
    col, row = gx.mean(axis=0), gy.mean(axis=1)
    # 1〜2 列だけの細い線（2 枚の写真のつなぎ目など）は空きを切らない：幅 5 の中央値でならす
    col = np.array([np.median(col[max(0, i - 2):i + 3]) for i in range(len(col))])
    row = np.array([np.median(row[max(0, i - 2):i + 3]) for i in range(len(row))])
    thr_c, thr_r = 0.12 * np.percentile(col, 90), 0.12 * np.percentile(row, 90)

    def run(a, thr):
        n = 0
        while n < len(a) // 2 and a[n] < thr:
            n += 1
        return n
    l, r = run(col, thr_c), run(col[::-1], thr_c)
    t, b = run(row, thr_r), run(row[::-1], thr_r)
    # 中の空き（2 つの物の間の白など。2026-11-08 ユニクロ：人と服の間）：縁でない所に 8% 以上の空きの列があれば、
    # 輪郭の 6 割以上を持つ側だけを残す（空きを挟んだ小さいほうは外す）
    seg, i, n = [], l, len(col) - r
    while i < n:
        j = i
        while j < n and (col[j] >= thr_c) == (col[i] >= thr_c):
            j += 1
        seg.append((i, j, col[i] >= thr_c))
        i = j
    gaps = [(a, z) for a, z, on in seg if not on and a > l and z < n and z - a >= 0.08 * W and float(g[:, a:z].std()) < 8]   # 間は無地の背景だけ（人物の中の模様の少ない所を空きと取り違えない。NBA・筋トレ）
    if gaps:
        parts, a0 = [], l
        for a, z in gaps:
            parts.append((a0, a))
            a0 = z
        parts.append((a0, n))
        tot = col[l:n].sum() or 1.0
        share = [col[p[0]:p[1]].sum() / tot for p in parts]
        big = [p for p, s in zip(parts, share) if s >= 0.25]
        if len(big) >= 2:   # 2 つとも大事な物：空きだけ詰めて並べる（店長 2026-11-08「这样裁一下」）。左右の端は外側の物の端まで
            SEG[:] = [[round(max(0.0, p[0] / W - BREATH), 3), round(min(1.0, p[1] / W + BREATH), 3)] for p in big]   # 物ごとに少し余白を残す
            l, r = big[0][0], len(col) - big[-1][1]
        else:
            best = max(parts, key=lambda p: col[p[0]:p[1]].sum())
            if col[best[0]:best[1]].sum() / tot >= 0.6:
                l, r = best[0], len(col) - best[1]
    return [t / H, r / W, b / H, l / W]


def mass_css(data):
    """顔・題字の分布（photo_store.mass）を data-m の文字列に。測れなければ ""。"""
    try:
        import photo_store
        v = photo_store.mass(data)
    except Exception:  # noqa: BLE001  cv2 が無い・壊れた画像 → 位置なし（切らない）
        return ""
    return ";".join(",".join(map(str, a)) for a in v) if v else ""


def text_box(data):
    """写真の中の文字のかたまりの範囲（OpenCV の MSER で、同じ高さで横に 4 個以上並ぶ字を探す）→ (左, 上, 右, 下) の割合。
    無い・写真全体（観客や葉を字と取り違えた）なら None。render の cropAt はこの範囲が全部入る切り方しか許さない（2026-11-08 店長：文字を欠かさない）。"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("L")
        w0, h0 = im.size
        W = 480
        H = max(16, round(W * h0 / w0))
        g = np.asarray(im.resize((W, H)), dtype=np.uint8)
        mser = cv2.MSER_create()
        mser.setMinArea(12)
        mser.setMaxArea(int(W * H * 0.03))
        regions, _ = mser.detectRegions(g)
    except Exception:  # noqa: BLE001
        return None
    bx = []
    for r in regions:
        x, y, w, h = cv2.boundingRect(r)
        if 0.03 * H <= h <= 0.3 * H and 0.08 <= w / h <= 2.5:
            bx.append((x, y, w, h))
    rows = []
    for b in bx:
        cy = b[1] + b[3] / 2
        same = [c for c in bx if abs((c[1] + c[3] / 2) - cy) < 0.5 * b[3] and 0.6 < c[3] / b[3] < 1.6]
        if len({c[0] for c in same}) >= 4:
            rows.extend(same)
    if not rows:
        return None
    x0, y0 = min(c[0] for c in rows) / W, min(c[1] for c in rows) / H
    x1, y1 = max(c[0] + c[2] for c in rows) / W, max(c[1] + c[3] for c in rows) / H
    if (x1 - x0) * (y1 - y0) >= 0.97:
        return None
    return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]


def measure(urls, cache, fetch, log=print):
    """まだ測っていない網址を測って cache に入れる（MAX_NEW まで）。→ 新しく測った数"""
    todo = [u for u in dict.fromkeys(urls) if not (isinstance(cache.get(u), dict) and cache[u].get("v") == 6)][:MAX_NEW]   # 前の測り方（ぼかし・中の空きを見ない）は測り直す

    def one(u):
        try:
            data = fetch(u)
            return u, ({"t": bands(data), "m": mass_css(data), "k": text_box(data), "s": segments(data), "v": 6} if data else {"t": [], "m": "", "k": None, "v": 6})
        except Exception:  # noqa: BLE001  開けない写真は「測れない」として次から取りに行かない
            return u, {"t": [], "m": "", "k": None, "v": 6}
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
        if v.get("s"):
            out += f' data-s="{";".join(",".join(map(str, s)) for s in v["s"])}"'
        if v.get("k"):
            out += f' data-k="{",".join(map(str, v["k"]))}"'
        return out
    text = IMG_RE.sub(rep, text)
    # data-mx は、同じ img にまだ data-m が無いときだけ data-m にする（店長のページの写真は render が付けた data-m を使う）
    return re.sub(r'<img ([^>]*?)data-mx="([^"]*)"([^>]*)>', lambda m: m.group(0).replace(f'data-mx="{m.group(2)}"', "" if "data-m=" in m.group(0) else f'data-m="{m.group(2)}"'), text)
