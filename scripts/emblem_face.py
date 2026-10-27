"""小元素の顔の大きさを、表示でそろえる（2026-10-27，用户 3 回目の指摘：「顔の大きさが違うのは分かるでしょ。治るのはロジックから」）。

前は、顔の大きさ fs を測ってあった小元素（94 枚中 9 枚）にだけ、しかも「大きすぎる顔を縮める」だけだった。
今は、今ある全部の人物の小元素の顔を測り（measure）、表示は「顔の高さを枠の TARGET にする」ように拡大も縮小もして切る（fit・view）。
店長の版面・お客さまの版面・管理ページの一覧・テーマ見本が、全部この 1 組の関数を使う（render.py は計算せず、ここの結果を使う）。

items.yaml の emblem の 1 枚に `face: [fs, top, fx, mx, w, h]`：
  fs = 顔の高さ ÷ 画像の高さ（0 = 顔が測れない＝「顔なし」：物・生き物・覆面）、top = 顔の上端 ÷ 高さ、
  fx = 顔の中心の x ÷ 幅、mx = 絵の重心の x ÷ 幅（不透明な所の重さの中心）、w・h = 測ったときの画像の大きさ（画像が替わったら測り直す印）。
"""

import pathlib

TARGET = 0.32     # 顔の高さ ÷ 枠の高さ。どの版面・どの欄でも、顔がこの大きさに見える（emblem.FACE_SHARE と同じ）
EYE = 0.30        # 目の線は枠の上から 30%（一覧の並びで目の高さがそろう）
EYE_IN_FACE = 0.4  # 顔の箱の上端から目の線までの割合（顔の高さに対して）
HEAD_MAX = 0.14       # 絵の上の端を枠の上から下げてよい上限（これより下げると頭の上が空きすぎて浮く）
HAIR = 0.3            # 顔の箱の上に残す髪の厚み（顔の高さに対して）。これより上の空きだけを枠の上で切る（髪・角・帽子は切らない）
FLOAT_MAX = 0.12      # 絵の下が枠の下に届かなくてよい上限（枠の高さに対して）。目の線を優先して浮かせるのはここまで
EYE_TOL = 0.05        # 目の線のずれの許し（枠の高さに対して）。超えるものは札 "short"
ZOOM = (0.5, 1.6)     # 「枠の高さに絵の高さを合わせた大きさ」に対する拡大・縮小の幅。画質が落ちる拡大はしない・縮小は前（--k）が下限なしだったので 0.5 まで
TOL = 0.11            # 顔の大きさが基準から ±11% までは「そろっている」（ぴったり同じにはしない）
FRAME_AR = 0.8        # 管理ページの一覧の枠（4:5）の 幅 ÷ 高さ
PAD = 0.3             # 検出のとき、絵の周りに足す白い余白（アップの絵は顔が端に触れていて、検出器が見落とす）


ANIME_URL = "https://huggingface.co/deepghs/anime_face_detection/resolve/main/face_detect_v1.4_s/model.onnx"
_anime = {}


def _anime_session():
    """アニメ・ゲームの絵の顔検出（YOLOv8、onnxruntime、44MB を初回だけ ~/.cache/wishlist-faces へ）。使えなければ None（ほかの検出器だけで測る）。"""
    if "s" not in _anime:
        _anime["s"] = None
        try:
            import onnxruntime
            import face_id
            p = face_id.CACHE / "anime_face.onnx"
            if not p.exists() or p.stat().st_size < 10_000_000:
                import urllib.request
                face_id.CACHE.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(urllib.request.Request(ANIME_URL, headers={"User-Agent": "wishlist-emblem"}), timeout=180) as r:
                    p.write_bytes(r.read())
            _anime["s"] = onnxruntime.InferenceSession(str(p), providers=["CPUExecutionProvider"])
        except Exception:
            pass
    return _anime["s"]


def _anime_boxes(big, conf=0.35):
    """big（白地に置いた PIL 画像）の顔 [(x, y, w, h), …]（big の画素）。"""
    import cv2
    import numpy as np
    s = _anime_session()
    if s is None:
        return []
    W, H = big.size
    k = 640 / max(W, H)
    w, h = max(1, int(W * k)), max(1, int(H * k))
    canvas = np.full((640, 640, 3), 255, np.float32)
    canvas[:h, :w] = np.asarray(big.convert("RGB").resize((w, h)), np.float32)
    o = s.run(None, {"images": (canvas.transpose(2, 0, 1)[None] / 255).astype(np.float32)})[0][0]   # (5, 8400)：中心 x・y・幅・高さ・確からしさ
    keep = o[4] >= conf
    if not keep.any():
        return []
    b, sc = o[:4, keep].T, o[4, keep]
    boxes = [[float(x - bw / 2), float(y - bh / 2), float(bw), float(bh)] for x, y, bw, bh in b]
    idx = cv2.dnn.NMSBoxes(boxes, [float(c) for c in sc], conf, 0.45)
    return [tuple(v / k for v in boxes[int(i)]) for i in np.array(idx).flatten()]


WEAK_YUNET, WEAK_ANIME = 0.32, 0.08   # 3 段目の測り（weak）のしきい値：YuNet 0.5 → 0.32（0.30 は岩を顔とした）、アニメ顔 YOLO 0.35 → 0.08
WEAK_H = 0.2                          # weak・relax で顔と認める箱の高さの下限（画像の高さに対して）。小さい箱は手・服・飾りの誤検出が多い（dota2 の全身 40 枚）


def _boxes(img, weak=False):
    """顔の候補 [(x, y, w, h), …]（元の画像の画素。大きい順）。YuNet（写真・3D）→ アニメ顔の検出 → 顔のカスケード。
    weak = True は 1 回目で測れなかった絵だけ：しきい値を下げて（WEAK_*）探し直す（カスケードは使わない）。"""
    import cv2
    import numpy as np
    from PIL import Image
    W, H = img.size
    q = int(max(W, H) * PAD)
    bg = Image.new("RGBA", (W + 2 * q, H + 2 * q), "white")
    bg.alpha_composite(img.convert("RGBA"), (q, q))
    s = max(1.0, 480 / max(bg.size))
    big = bg.resize((int(bg.width * s), int(bg.height * s))) if s > 1 else bg
    s = big.width / bg.width
    out = []
    try:   # 写真・3D
        import face_id
        eng = face_id.engine()
        if eng:
            a = cv2.cvtColor(np.array(big.convert("RGB")), cv2.COLOR_RGB2BGR)
            det = eng[0]
            det.setInputSize((a.shape[1], a.shape[0]))
            det.setScoreThreshold(WEAK_YUNET if weak else 0.5)
            try:
                _, f = det.detect(a)
            finally:
                det.setScoreThreshold(face_id.SCORE)   # 戻す：共有の検出器に残すと forehead_cut・E7 の判定が前の測りしだいで変わる（2026-10-27：Gin Ichimaru ほか 7 枚）
            out += sorted(((r[0] / s - q, r[1] / s - q, r[2] / s, r[3] / s) for r in (f if f is not None else [])), key=lambda b: -b[2] * b[3])
    except Exception:
        pass
    try:   # アニメ・ゲームの絵
        out += sorted(((x - q, y - q, bw, bh) for x, y, bw, bh in (_anime_boxes(bg, WEAK_ANIME) if weak else _anime_boxes(bg))), key=lambda b: -b[2] * b[3])
    except Exception:
        pass
    try:   # YuNet が見つけない・使えない顔（アニメ絵・横向き）：顔のカスケード。YuNet の候補のあとに
        if weak:
            return out
        import emblem
        f = emblem.face_box(bg)
        if f:
            out.append((f[0] - q, f[1] - q, f[2], f[3]))
    except Exception:
        pass
    return out


def _pick(boxes, al, w, h, relax=False):
    """候補のうち、顔と認める最初の箱 (x, y, bw, bh)。なければ None。
    relax = False：顔は上のほうにあるはず（y < 0.5h、中心 < 0.75h。下のほうの検出は手や服の誤検出）。
    relax = True ：髪・角・帽子の大きい上半身のアップは顔が下がる（BLEACH の Franceska、dota2 の Dark Willow）ので、
    y < 0.65h・中心 < 0.85h まで広げ、そのかわり箱の高さが画像の 20%（WEAK_H）以上のものだけ。"""
    for x, y, bw, bh in boxes:
        if not 0.04 <= bh / h <= 0.95 or (relax and bh / h < WEAK_H):
            continue
        cx, cy = x + bw / 2, y + bh / 2
        if not (0 <= cx < w and 0 <= cy < h * (0.85 if relax else 0.75) and y < h * (0.65 if relax else 0.5)):
            continue
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(w, int(x + bw)), min(h, int(y + bh))
        if x1 <= x0 or y1 <= y0 or al[y0:y1, x0:x1].mean() < 0.5:   # 顔の箱の中が透明 = 余白への誤検出
            continue
        return x, y, bw, bh
    return None


def measure(img):
    """PIL 画像 → [fs, top, fx, mx, w, h]（上の説明）。顔が測れなければ fs = 0。
    3 段：① 今までの測り（YuNet・アニメ顔 YOLO・カスケード、顔は上のほう）② 同じ候補で、顔が下がったアップを認める（relax）
    ③ しきい値を下げて探し直す（weak。向きを並べた図は除く）。前の段で測れた絵は、あとの段に進まない（測り済みの値は変わらない）。"""
    import numpy as np
    img = img.convert("RGBA")
    w, h = img.size
    al = np.array(img.getchannel("A")) > 128
    ys, xs = np.nonzero(al)
    mx = round(float(xs.mean()) / w, 3) if len(xs) else 0.5
    boxes = _boxes(img)
    f = _pick(boxes, al, w, h) or _pick(boxes, al, w, h, relax=True)
    if not f and not _is_sheet(al, w, h):   # 向きを並べた図は顔が小さく、しきい値を下げると体の模様を顔とする（dota2 Ursa）
        f = _pick(_boxes(img, weak=True), al, w, h, relax=True)
    if f:
        x, y, bw, bh = f
        return [round(float(bh) / h, 3), round(float(max(0.0, y)) / h, 3), round(float(x + bw / 2) / w, 3), mx, w, h]
    return [0, 0, 0.5, mx, w, h]


NONE_V = 3   # 顔なしと測ったときの測り方の版（x["nfv"]）。測り方を上げたら数を上げる：古い版で顔なしの絵だけ 1 回測り直す（測り済みの絵は触らない）


def stale(x, size):
    """この小元素は測り直すか（face がない・画像の大きさが替わった・古い版で顔なしと測った）。measure_item・measure_emblems が使う。"""
    f = x.get("face")
    if not (isinstance(f, list) and len(f) == 6 and f[4:] == list(size)):
        return True
    return f[0] == 0 and x.get("nfv") != NONE_V


def _store(x, img):
    """測って x に書く（顔なしなら測り方の版 nfv も）。"""
    x["face"] = measure(img)
    if x["face"][0]:
        x.pop("nfv", None)
    else:
        x["nfv"] = NONE_V


NONE_REASONS = {"sheet": "向きを並べた図（顔が小さい）", "small": "顔らしい箱はあるが小さい・場所が合わない（全身が小さい）", "noface": "顔らしいものがない（怪物・武器・物・覆面）"}


def _is_sheet(al, w, h):
    """向きを並べた図：横長（幅 ÷ 高さ ≥ 1.5）で、絵が 2 つ以上の塊（どれも全体の 15% 以上）に分かれる（dota2 の Fandom の 3D 図）。al = 不透明な所の真偽の配列。"""
    import cv2
    import numpy as np
    if w / h < 1.5 or not al.any():
        return False
    k = max(3, w // 40)
    _, _, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(al.astype(np.uint8), np.ones((k, k), np.uint8)))
    area = st[1:, cv2.CC_STAT_AREA]
    return sum(1 for s in area if s >= 0.15 * area.sum()) >= 2


def none_reason(img):
    """顔が測れなかった（measure の fs = 0）絵の理由の札 → "sheet" / "small" / "noface"（NONE_REASONS）。点検 harness/emb_check.py E17 が数える。
    sheet = _is_sheet。small = しきい値を下げた探し直し（weak）で箱はあるが、小さい（WEAK_H 未満）か場所が合わない。noface = 箱がひとつもない。"""
    import numpy as np
    img = img.convert("RGBA")
    w, h = img.size
    if _is_sheet(np.array(img.getchannel("A")) > 128, w, h):
        return "sheet"
    return "small" if _boxes(img, weak=True) else "noface"


def fit(face):
    """face → (m, 札)。m = 枠の高さに対する絵の高さ（顔の高さが TARGET になる大きさ、ZOOM の幅まで）。
    札 = "" ならそろっている、"small" = 顔が小さすぎて拡大が足りない（全身など）、"big" = 顔が大きすぎて縮小が足りない（アップ）。
    札のついたものは、選び方の規則で同じ人の別の写真に替える対象（管理ページの一覧に出す）。顔が測れなければ None。"""
    fs = face[0] if face else 0
    if not fs:
        return None, "none"
    m = min(max(TARGET / fs, ZOOM[0]), ZOOM[1])
    share = fs * m
    return round(m, 3), ("small" if share < TARGET * (1 - TOL) else "big" if share > TARGET * (1 + TOL) else "")


def view(face, frame_ar=FRAME_AR):
    """枠（幅 ÷ 高さ = frame_ar）の中の置き方 → {m, ox, oy, w, flag}。m・w・ox・oy は枠の高さ（oy）・幅（ox・w）に対する割合。
    ① 顔の高さ = TARGET ② 目の線 = 枠の上から EYE。いちばん先に効く（2026-10-27：前は頭の上の余白 6〜14% の挟みと下そろえが先に効き、
    顔のある 192 枚のうち 104 枚が目の線を外れた）。髪を切らない（HAIR）・上に下げすぎない（HEAD_MAX）・下に浮かせすぎない（FLOAT_MAX）の範囲でだけ動かす
    ③ それでも目の線が EYE_TOL を外れるもの（絵の下が足りない近い絵）は札 "short" = 選び方の規則で、下まで写った別の写真に替える対象
    ④ 横は、絵の重心と顔の中心の真ん中を枠の真ん中に。顔が測れなければ None。"""
    m, flag = fit(face)
    if m is None:
        return None
    fs, top, fx, mx, pw, ph = face[:6]
    eye = top + EYE_IN_FACE * fs
    oy = EYE - m * eye
    oy = max(oy, min(0.0, -m * (top - HAIR * fs)), 1 - m - FLOAT_MAX)   # 髪を切らない・下に浮かせすぎない
    oy = min(oy, HEAD_MAX)
    if not flag and abs(oy + m * eye - EYE) > EYE_TOL + 1e-9:
        flag = "short"
    w = m * (pw / ph) / frame_ar
    ox = 0.5 - (0.5 * mx + 0.5 * fx) * w
    return {"m": m, "ox": round(ox, 4), "oy": round(oy, 4), "w": round(w, 4), "flag": flag, "eye": round(oy + m * eye, 3)}


import re
LOGO_NAME = re.compile(r"logo|wordmark|ロゴ", re.I)


def logo_named(x):
    """画像の名前が logo のもの（shape が cutout のまま網址で引いた Wikipedia の ArcheAge_Logo.png など）は、人物でなくロゴ：顔を測らず切り抜き扱いにしない。"""
    import urllib.parse
    return x.get("shape") in ("logo", "icon") or bool(LOGO_NAME.search(urllib.parse.unquote(str(x.get("image") or "").split("?")[0].rsplit("/", 1)[-1])))


def _files(item, root):
    for x in item.get("emblem") or []:
        im = str(x.get("image") or "") if isinstance(x, dict) else ""
        p = root / im
        if im.startswith("emblems/") and x.get("shape") not in ("logo", "icon", "badge") and p.exists():
            yield x, p


def measure_item(item, log=print, root=None, force=False):
    """その関注項の人物の小元素のうち、face がない・画像が替わったものを測って書く。→ 測った枚数。
    小元素を足す・規則で作り直す回（emblem_fill.drop_broken）のたびに呼ぶので、新しい小元素も自動でそろう。"""
    import emblem
    from PIL import Image
    root = pathlib.Path(root) if root else emblem.sitedir.SITE_DIR
    done = []
    for x, p in _files(item, root):
        try:
            img = Image.open(p)
            img.load()
        except Exception:
            continue
        if not force and not stale(x, img.size):
            continue
        _store(x, img)
        if x.get("fs") is not None:   # 前からの fs（顔の高さの割合）は同じ測りに揃える
            if x["face"][0]:
                x["fs"] = x["face"][0]
            else:
                x.pop("fs", None)
        done.append(x)
    if done:
        emblem.write_item(item["name"], item["emblem"], None)
        log(f"  [顔を測った] {item['name']}：{len(done)} 枚（顔なし {sum(1 for x in done if not x['face'][0])}）")
    return len(done)


def measure_emblems(emblems, load):
    """小元素のリスト（店長の items.yaml でもお客さまの boards.config.emblem でも）の人物の切り抜きのうち、face がない・画像が替わったものを測って書く。
    load(image) → PIL 画像（手元のファイルでも公開の箱の網址でも。読めなければ None＝次の回）。→ 測った枚数。
    お客さまの版面は measure_item（店長の items.yaml だけ）が届かなかったので、ここを library_emblem が呼ぶ（2026-10-27：版面 17 個・135 枚が未測定だった）。"""
    n = 0
    for x in emblems or []:
        if not isinstance(x, dict) or x.get("shape") in ("logo", "icon", "badge") or logo_named(x) or not x.get("image"):
            continue
        try:
            img = load(str(x["image"]))
            if img is None:
                continue
            img.load()
        except Exception:
            continue
        if not stale(x, img.size):
            continue
        _store(x, img)
        if x.get("fs") is not None:
            if x["face"][0]:
                x["fs"] = x["face"][0]
            else:
                x.pop("fs", None)
        n += 1
    return n


def unmeasured(emblems):
    """face がない人物の切り抜き（全身 body は顔でそろえない別の物差し）の数。版面ごとの点検（ux_check・tests）と同じ数え方。"""
    return sum(1 for x in emblems or [] if isinstance(x, dict) and x.get("shape") not in ("logo", "icon", "badge") and not logo_named(x) and x.get("image")
               and not x.get("body") and not (isinstance(x.get("face"), list) and len(x["face"]) == 6))


def audit(items):
    """版面ごとの 顔の大きさのそろい具合 → [{name, n, none, small, big, spread}]（管理ページ・ux_check・tests）。
    spread = 札のない小元素の「顔の高さ ÷ 枠の高さ」の最大 ÷ 最小（1.25 以下ならそろっている）。"""
    rows = []
    for it in items:
        shares, flags = [], {"none": 0, "small": 0, "big": 0, "short": 0, "": 0}
        em = [x for x in it.get("emblem") or [] if isinstance(x, dict) and x.get("shape") not in ("logo", "icon", "badge")
              and str(x.get("image", "")).startswith("emblems/")]   # 倉庫に置いた切り抜きだけ（網址を引用するだけの画像は測らない）
        for x in em:
            f = x.get("face")
            if not f:
                flags["unmeasured"] = flags.get("unmeasured", 0) + 1
                continue
            m, flag = fit(f)
            if not flag:
                shares.append(f[0] * m)
                flag = view(f)["flag"]   # 目の線が外れるもの（short）も札。顔の大きさは足りているので shares には入れる
            flags[flag] += 1
        if em:
            rows.append({"name": it["name"], "n": len(em), "none": flags["none"], "small": flags["small"], "big": flags["big"], "short": flags["short"],
                         "unmeasured": flags.get("unmeasured", 0), "spread": round(max(shares) / min(shares), 3) if shares else 1.0})
    return rows
