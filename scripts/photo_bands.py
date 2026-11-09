"""別のサイトの写真を、ページを作るときに 1 回だけ取って測り、img に書く（2026-11-08，店長：余白は枠の 4 分の 1 まで・文字を欠かさない）。

ブラウザは別のサイトの写真の中身を読めない（CORS）。お客さまのページの写真の多くは元のサイトから直接読むので、Actions が測る。
    data-t="上,右,下,左,#端の色"   写真に焼き込まれた無地の余白の割合（余白がなければ付けない）
    data-m="横の分布;縦の分布"      顔・題字の分布（photo_store.mass と同じ。店長のページの写真と同じ物差しで切る位置を選ぶ）
測った結果は網址ごとに残し（cache）、同じ写真は二度取りに行かない。
"""
import concurrent.futures as cf
import html as htmllib
import io
import pathlib
import re
import threading

MAX_NEW = 400          # 1 回で新しく測る数の上限（Actions の時間を守る）
IMG_RE = re.compile(r'<img src="(https?://[^"]+)"')
FLAT = 24              # 同じ色とみなす差（RGB の差の合計）
MIN_BAND = 0.04        # これより細い余白は外さない
BREATH = 0.03          # 余白を外しても残す幅（物の周りの息をする余白）
VERSION = 8            # 測り方の版。変えたら前の測りは全部測り直す（7：字の範囲を PaddleOCR の文字検出に替えた・8：人の範囲 data-p を足した 2026-11-09）


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


MODEL = pathlib.Path(__file__).resolve().parent / "models" / "ppocr_det_v3.onnx"   # PaddleOCR PP-OCRv3 の文字検出（DBNet・Apache-2.0）。日本語・中国語の字の行を拾う
_DET = {}
_DET_LOCK = threading.Lock()


def _det():
    if "s" not in _DET:
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.log_severity_level = 3
        _DET["s"] = ort.InferenceSession(str(MODEL), so, providers=["CPUExecutionProvider"])
    return _DET["s"]


def text_box(data):
    """写真の中の見出しくらいの大きさの字の範囲 → (左, 上, 右, 下) の割合。無ければ None。render の cropAt はこの範囲が全部入る切り方しか許さない（2026-11-08 店長：文字を欠かさない）。
    2026-11-09：MSER（形の塊）は日本語の字が部首ごとにばらけ、髪の毛・衣装の模様も字と取り違えて写真のほぼ全体を「字」にした（イノスケ・イヤリング）→ 伸ばせず版面に空きが残った。
    PaddleOCR の文字検出（PP-OCRv3 det を onnxruntime で）に替えた。著作権表示のような小さい字（行の太さが短い辺の 5% 未満）は数えない。動かない環境では前の MSER。"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        sess = _det()
        im = Image.open(io.BytesIO(data)).convert("RGB")
        w0, h0 = im.size
        s = 960 / max(w0, h0)
        W, H = max(32, round(w0 * s / 32) * 32), max(32, round(h0 * s / 32) * 32)
        a = np.asarray(im.resize((W, H)), dtype=np.float32) / 255.0   # RGB のまま（BGR に替えると字でない所を拾った。2026-11-09 に 9 枚で比べた）
        a = (a - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        with _DET_LOCK:
            prob = sess.run(None, {sess.get_inputs()[0].name: a.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    except Exception:  # noqa: BLE001
        return _text_box_mser(data)
    mask = (prob > 0.3).astype("uint8")
    cs = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
    boxes = []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w < 3 or h < 3 or float(prob[y:y + h, x:x + w][mask[y:y + h, x:x + w] > 0].mean()) < 0.6:
            continue
        d = w * h * 1.5 / (2 * (w + h))   # DBNet の縮めた枠を広げ直す（unclip 1.5 相当）
        x0, y0, x1, y1 = max(0, x - d), max(0, y - d), min(W, x + w + d), min(H, y + h + d)
        if min(x1 - x0, y1 - y0) < 0.05 * min(W, H):   # 小さい字（著作権表示・ゼッケン・服の模様）は切っても欠けにならない
            continue
        boxes.append((x0 / W, y0 / H, x1 / W, y1 / H))
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    if (x1 - x0) * (y1 - y0) >= 0.97:
        return None
    return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]


FACE_MODEL = pathlib.Path(__file__).resolve().parent / "models" / "face_yunet_2023mar.onnx"   # OpenCV の顔検出 YuNet（MIT）。face_id.py が使うのと同じもの
_FACE = {}


def people_box(data):
    """写真の中の人（顔を肩まで広げた範囲）を全部まとめた範囲 → (左, 上, 右, 下) の割合。いなければ None。
    render の cropAt は字の範囲（data-k）と同じく、この範囲が全部入る切り方しか許さない（2026-11-09 店長：何人も並ぶ写真で端の人が切れた。
    主役の分布〔data-m〕だけでは、端に落とすのが人か観客席かを区別できなかった）。顔は小さすぎるもの（短い辺の 4% 未満＝遠くの観客）は数えない。"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        key = threading.get_ident()
        if key not in _FACE:
            _FACE[key] = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.8, 0.3, 5000)
        det = _FACE[key]
        rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
        h, w = rgb.shape[:2]
        s = min(1.0, 960 / max(h, w))
        bgr = cv2.cvtColor(cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s)))) if s < 1 else rgb, cv2.COLOR_RGB2BGR)
        H, W = bgr.shape[:2]
        det.setInputSize((W, H))
        _, faces = det.detect(bgr)
    except Exception:  # noqa: BLE001
        return None
    boxes = []
    for f in (faces if faces is not None else []):
        x, y, fw, fh = (float(v) for v in f[:4])
        if min(fw, fh) < 0.04 * min(W, H):
            continue
        boxes.append((max(0.0, x - 0.6 * fw) / W, max(0.0, y - 0.3 * fh) / H, min(W, x + 1.6 * fw) / W, min(H, y + 2.0 * fh) / H))   # 顔 → 頭と肩
    if not boxes:
        return None
    return [round(min(b[0] for b in boxes), 3), round(min(b[1] for b in boxes), 3), round(max(b[2] for b in boxes), 3), round(max(b[3] for b in boxes), 3)]


def _text_box_mser(data):
    """前の文字の範囲（OpenCV の MSER で、同じ高さで横に 4 個以上並ぶ字を探す）。文字検出が動かない環境のときだけ使う。"""
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
    todo = [u for u in dict.fromkeys(urls) if not (isinstance(cache.get(u), dict) and cache[u].get("v") == VERSION and not cache[u].get("dead"))][:MAX_NEW]   # 開けなかった写真は毎回試し直す   # 前の測り方（ぼかし・中の空きを見ない）は測り直す

    def one(u):
        try:
            data = fetch(u)
            return u, ({"t": bands(data), "m": mass_css(data), "k": text_box(data), "p": people_box(data), "s": segments(data), "v": VERSION} if data else {"t": [], "m": "", "k": None, "v": VERSION})
        except Exception as ex:  # noqa: BLE001  「無い」（404・410）と答えた写真だけ印（ページでは最初から代わりの写真か、カードを出さない）。
            # つながらない・時間切れは一時的なものとして記録しない（次の回にまた試す。PC の DNS が落ちて 39 枚に印が付き、壁が空になった）
            return u, ({"t": [], "m": "", "k": None, "v": VERSION, "dead": 1} if getattr(ex, "code", None) in (404, 410) else None)
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        got = list(pool.map(one, todo))
    if todo and sum(1 for _, v in got if v is None or v.get("dead")) > 0.2 * len(todo):   # 2 割以上開けない：通信の問題。印は付けない
        got = [(u, None if v and v.get("dead") else v) for u, v in got]
    for u, v in got:
        if v is not None:
            cache[u] = v
    if todo:
        ok = [u for u in todo if u in cache]
        log(f"写真の余白と主役：{len(todo)} 枚を測った（余白あり {sum(1 for u in ok if cache[u]['t'])}・主役の位置 {sum(1 for u in ok if cache[u]['m'])}・無い {sum(1 for u in ok if cache[u].get('dead'))}・つながらず {len(todo) - len(ok)}）")
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
        if v.get("dead"):
            return out + ' data-dead="1"'
        if v.get("t"):
            out += f' data-t="{",".join(map(str, v["t"]))}"'
        if v.get("m"):
            out += f' data-mx="{v["m"]}"'
        if v.get("s"):
            out += f' data-s="{";".join(",".join(map(str, s)) for s in v["s"])}"'
        if v.get("k"):
            out += f' data-k="{",".join(map(str, v["k"]))}"'
        if v.get("p"):
            out += f' data-p="{",".join(map(str, v["p"]))}"'
        return out
    text = IMG_RE.sub(rep, text)
    # data-mx は、同じ img にまだ data-m が無いときだけ data-m にする（店長のページの写真は render が付けた data-m を使う）
    return re.sub(r'<img ([^>]*?)data-mx="([^"]*)"([^>]*)>', lambda m: m.group(0).replace(f'data-mx="{m.group(2)}"', "" if "data-m=" in m.group(0) else f'data-m="{m.group(2)}"'), text)
