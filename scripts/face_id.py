"""写真に写っているのが「その人」かどうかを確かめる（小元素の人物の取り違えを防ぐ）。

Wikipedia や Commons の記事には、本人と関係のない画像（絵画・観客席・ペンライト・同じ記事の別人）も載っている。
名前が合っていても中身が違うことがあるので、顔の特徴で確かめる：
  1. 顔を検出（YuNet）。顔が見つからない写真は人物としては使わない（物・風景・集合写真の遠景を落とす）。
  2. 顔の特徴量（SFace、128 次元）を取る。画像の中でいちばん大きい顔を「その画像の人」とする。
  3. 基準になる顔（記事の代表画像＝anchor）と近い（コサイン類似度 ≥ 0.363：SFace の推奨しきい値）ものだけ残す。
     anchor の顔が取れないときは、候補どうしでいちばん大きい「同じ顔の集まり」を本人とみなす（多数決）。
モデルは初回だけダウンロード（~/.cache/wishlist-faces、合わせて約 39MB）。取れない・OpenCV がないときは None を返し、
呼び出し側は「顔の有無だけ」の確認に下げる（その旨をログに出す）。
"""

import os
import pathlib
import urllib.request

MODELS = {
    "yunet.onnx": "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    "sface.onnx": "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
}
CACHE = pathlib.Path(os.environ.get("WISHLIST_FACE_CACHE") or pathlib.Path.home() / ".cache" / "wishlist-faces")
THRESHOLD = 0.363   # SFace の推奨しきい値（コサイン）
_engine = {}


def _models():
    CACHE.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        p = CACHE / name
        if not p.exists() or p.stat().st_size < 100_000:
            req = urllib.request.Request(url, headers={"User-Agent": "wishlist-emblem"})
            with urllib.request.urlopen(req, timeout=120) as r:
                p.write_bytes(r.read())
    return CACHE / "yunet.onnx", CACHE / "sface.onnx"


def engine():
    """→ (detector, recognizer) か None（OpenCV がない・モデルを取れない）。"""
    if "e" in _engine:
        return _engine["e"]
    try:
        import cv2
        det_p, rec_p = _models()
        det = cv2.FaceDetectorYN.create(str(det_p), "", (320, 320), 0.8, 0.3, 5000)
        rec = cv2.FaceRecognizerSF.create(str(rec_p), "")
        _engine["e"] = (det, rec)
    except Exception:
        _engine["e"] = None
    return _engine["e"]


def main_face(img):
    """PIL 画像 → いちばん大きい顔の特徴量（numpy）か None。顔がなければ None。"""
    eng = engine()
    if eng is None:
        return None
    import cv2
    import numpy as np
    det, rec = eng
    rgb = np.array(img.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = 1.0
    if max(h, w) > 1280:   # 大きすぎる写真は縮めて検出（速く、顔の大きさも十分）
        scale = 1280 / max(h, w)
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)))
        h, w = bgr.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(bgr)
    if faces is None or not len(faces):
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    if min(f[2], f[3]) < 40:   # 小さすぎる顔（遠景の人）は本人の写真として使わない
        return None
    return rec.feature(rec.alignCrop(bgr, f))


def similarity(a, b):
    import cv2
    return float(engine()[1].match(a, b, cv2.FaceRecognizerSF_FR_COSINE))


def same_person(feats, anchor=None):
    """feats：特徴量（顔がなければ None）のリスト。→ 本人と判断した添字の集合。エンジンが使えないとき None。
    anchor：基準にする添字（記事の代表画像）。顔が取れない・基準がないときは「いちばん大きい同じ顔の集まり」が本人。"""
    if engine() is None:
        return None
    idx = [i for i, f in enumerate(feats) if f is not None]
    if not idx:
        return set()
    if anchor is not None and feats[anchor] is not None:
        base = [anchor]
        keep = {i for i in idx if i == anchor or similarity(feats[anchor], feats[i]) >= THRESHOLD}
        if len(keep) >= 2:
            return keep
        # 基準の画像が他と合わない（代表画像が別人・集合写真）：多数決に切り替える
    groups = []
    for i in idx:
        for g in groups:
            if sum(similarity(feats[j], feats[i]) >= THRESHOLD for j in g) >= max(1, (len(g) + 1) // 2):
                g.append(i)
                break
        else:
            groups.append([i])
    best = max(groups, key=len)
    return set(best) if len(best) >= 2 or len(idx) == 1 else {best[0]}
