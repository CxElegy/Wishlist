"""切り抜きの形の健康（左右・上の端の直線の切り口、凹みすぎ）を測る。numpy・OpenCV・PIL だけ。
emblem.py と harness/emb_check.py の両方が読む（emb_check は emblem を import すると sources の opener が入り Wikimedia が 403 を返すので、測るところだけここに分けた）。"""

FLAT_RUN = 0.15    # 左・右の端にそって人物がこの割合（絵の高さ比）を超えてまっすぐ続く = 元の写真の端で体が切れた直線の切り口（半身の下の端だけは直線でよい）
FLAT_TOP = 0.25    # 上の端：人物が横幅のこの割合を超えてまっすぐ続く（髪の頂が少し平らな写真は通す：Snape 15%・Vaundy 18%。帽子・コマの上の端は 25% 以上）
SOLID_MIN = 0.30   # 人物の形の凹まなさ（面積 ÷ 凸包の面積）がこれ未満 = 凹みが多い（背景の切れ端・持ち物が出っぱりになった）形。翼・稲妻の実在の小元素 0.33〜0.44（dota2 Dark Willow・Visage・Zeus・Pyrois）を外していたので 0.45 から下げた（切れ端は 0.00）


def _run(v):
    """真偽の列の、続いて真の長さの最大と、その始まり。"""
    import numpy as np
    d = np.diff(np.concatenate([[0], v.astype("int8"), [0]]))
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    if not len(s):
        return 0, 0
    i = int(np.argmax(e - s))
    return int(e[i] - s[i]), int(s[i])


def flat_runs(img):
    """切り抜きの外側の端（左・右の 1 列：÷ 高さ、上の 1 行：÷ 横幅）にそって人物が続く長さと、左右の始まりの行。→ {left, right, top, start}"""
    import numpy as np
    a = np.array(img.convert("RGBA").getchannel("A")) > 128
    h = max(1, a.shape[0])
    z = h   # 左右は下の端まで全部見る（check_whole の SIDE_ZONE は下 35% を許すが、そこが垂直に続くと「右下が四角く切れて体が途中で終わる」：Gregory Goyle の下 37%）
    kx, ky = min(a.shape[1] - 1, max(3, int(a.shape[1] * 0.05))), min(h - 1, max(3, int(h * 0.05)))

    def edge(on, inner, k):   # 端の列（行）と、そこから k 中の列（行）がともに人物の続き。まっすぐな切り口は中の列でも同じ長さ（斜めの肩で 1.6 倍＋k×3 まで増える）、丸い輪郭は中の列ほど長い。端にそった細い杖・剣は中が人物でない
        both = _run(on & inner)
        return both if _run(inner)[0] <= both[0] * 1.6 + 3 * k else (0, 0)
    (l, ls), (r, rs), (t, _) = edge(a[:z, 0], a[:z, kx], kx), edge(a[:z, -1], a[:z, -1 - kx], kx), edge(a[0], a[ky], ky)
    return {"left": l / h, "right": r / h, "top": t / max(1, a.shape[1]),
            "start": min([s for n, s in ((l, ls), (r, rs)) if n / h > FLAT_RUN] or [h])}


def solidity(img):
    """人物の形の凹まなさ：いちばん大きいまとまりの面積 ÷ 凸包の面積（0〜1）。"""
    import cv2
    import numpy as np
    a = (np.array(img.convert("RGBA").getchannel("A")) > 128).astype("uint8")
    cs = cv2.findContours(a, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    if not cs:
        return 1.0
    c = max(cs, key=cv2.contourArea)
    return float(cv2.contourArea(c) / max(1.0, cv2.contourArea(cv2.convexHull(c))))


def flat_flaw(img):
    """前からの切り抜きに形の傷（左右・上の端の直線の切り口、凹みすぎ）があるか。半身に切り落とせば直るもの（emblem.trim_flat）も含む。"""
    img = img.convert("RGBA")
    box = img.getchannel("A").getbbox()
    if not box:
        return False
    img = img.crop(box)
    r = flat_runs(img)
    return r["top"] > FLAT_TOP or max(r["left"], r["right"]) > FLAT_RUN or solidity(img) < SOLID_MIN
