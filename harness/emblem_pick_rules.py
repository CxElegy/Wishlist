"""小元素の「どの絵をどう切るか」の規則（見本用・本番は変えない）と、あなたの ○×− との一致率。
python harness/emblem_pick_rules.py        → 表を出す（印 harness/labels/emblem_pick_2026-10-30.json、絵は 2026-10-26 の版 COMMIT）
規則は測れる数だけ：①顔のアップ（顔の下の肩と胸が顔の高さの 0.7 倍未満・頭の上の空きが顔の高さ未満）＝× ②胸像に切ったとき頭の上が枠で切れる＝×
③短い辺 150px 未満＝× ④顔が見つからない絵は −（使えるが後ろ）。胸像がだめで元の絵が良ければ元の絵（恋次）。"""
import io
import json
import pathlib
import subprocess
import sys

import yaml
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "harness"))
from browser import PATTERN, storage_bytes  # noqa: E402  Supabase の写真は写しから（free-tier.md）
import emblem  # noqa: E402

COMMIT = "135c63b8"          # ユーザーが印を付けた見本の版（2026-10-26）。絵は今と違うので、この版の絵で数える
FACE_W, EYE_Y, RATIO = 0.42, 0.36, 1.25
BELOW_MIN, GAP_MAX = 0.7, 1.0   # 顔のアップ：顔の下の余り < 顔の高さの 0.7 倍 かつ 頭の上の余り < 顔の高さ
MIN_SIDE = 150
CUT_TOP = 0.15                  # 胸像の枠の上端 4 行に人物が横幅のこの割合以上＝頭が切れる


def trim(img):
    img = img.convert("RGBA")
    return img.crop(img.getchannel("A").getbbox())


def bust_crop(img):
    """顔の幅＝枠の 4 割・目の線＝上から 36% の胸像（emblem_pick_page.bust と同じ）。顔がなければ None。"""
    f = emblem.face_box(img)
    if not f:
        return None
    fx, fy, fw, fh = f
    w = fw / FACE_W
    h = w * RATIO
    left, top = fx + fw / 2 - w / 2, fy + 0.42 * fh - EYE_Y * h
    h = min(h, img.size[1] - top)
    canvas = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    canvas.paste(img, (int(-left), int(-top)))
    return canvas


def close_up(img):
    """顔のアップ：肩と胸が足りない（上に髪・帽子の余りが大きい人は除く）。→ (はい/いいえ, 顔の下の倍率, 頭の上の倍率) か None（顔なし）"""
    f = emblem.face_box(img)
    if not f:
        return None
    x, y, w, h = f
    below, gap = (img.size[1] - y - h) / h, y / h
    return below < BELOW_MIN and gap < GAP_MAX, below, gap


def top_cut(img):
    import numpy as np
    a = np.array(img.getchannel("A"))[:4] > 128
    return bool(a.size) and float(a.any(axis=0).mean()) >= CUT_TOP


def original_verdict(img):
    """元の絵そのものを出してよいか → ("o"|"-"|"x", 理由)。"""
    if min(img.size) < MIN_SIDE:
        return "x", f"小さすぎる（短い辺 {min(img.size)}px）"
    c = close_up(img)
    if c is None:
        return "-", "顔が見つからない＝使えるが後ろ"
    if c[0]:
        return "x", f"顔のアップ（顔の下 {c[1]:.2f} 倍）"
    if emblem.head_cut(img):
        return "x", "頭の上が切れている"
    return "o", "顔も肩も入っている"


def bust_verdict(img):
    """胸像に切ってよいか → ("o"|"-"|"x", 理由, 胸像か None)。"""
    if min(img.size) < MIN_SIDE:
        return "x", f"小さすぎる（短い辺 {min(img.size)}px）", None
    c = close_up(img)
    if c is None:
        return "-", "顔が見つからない＝胸像にせず後ろ", None
    if c[0]:
        return "x", f"顔のアップ（顔の下 {c[1]:.2f} 倍＜{BELOW_MIN}）＝縮めると上が空く", None
    cut = bust_crop(img)
    if cut is None or top_cut(cut):
        return "x", "胸像に切ると頭の上が枠で切れる", None
    return "o", "顔の下に肩と胸が足りている・頭が切れない", cut


def decide(img):
    """最終の 1 枚 → ("bust"|"orig"|"back"|"none", 理由, 絵)。胸像 → 元の絵 → 後ろ → なし。"""
    img = trim(img)
    v, why, cut = bust_verdict(img)
    if v == "o":
        return "bust", why, cut
    ov, owhy = original_verdict(img)
    if ov == "o":
        return "orig", f"胸像はだめ（{why}）→ 元の絵が良いので元の絵", img
    if v == "-":
        return "back", why, img
    return "none", why, None


def _git(path):
    return subprocess.run(["git", "show", f"{COMMIT}:{path}"], capture_output=True, cwd=ROOT).stdout


def evaluate():
    """印と規則を並べる → (行, 集計)。行＝(段, 版面, 名前, 印, 規則, 理由)。"""
    labels = json.load(open(ROOT / "harness" / "labels" / "emblem_pick_2026-10-30.json"))
    items = yaml.safe_load(_git("items.yaml"))
    items = items["items"] if isinstance(items, dict) else items
    rows = []
    for board, v in labels["boards"].items():
        em = {e["subject"]: e for e in next(i for i in items if i["name"] == board)["emblem"]}
        for k in "ox-":
            for s in v[k]:
                img = trim(Image.open(io.BytesIO(_git("docs/home/" + em[s]["image"]))))
                verdict, why, _ = bust_verdict(img)
                rows.append(("新しい（胸像）", board, s, k, verdict, why))
    for board, v in labels["boards_now"].items():
        if board == "note":
            continue
        em = {e["subject"]: e for e in next(i for i in items if i["name"] == board)["emblem"]}
        for k in "ox-":
            for s in v.get(k, []):
                img = trim(Image.open(io.BytesIO(_git("docs/home/" + em[s]["image"]))))
                verdict, why = original_verdict(img)
                rows.append(("いま（元の絵）", board, s, k, verdict, why))
    return rows, summary(rows)


def summary(rows):
    out = {}
    for stage in dict.fromkeys(r[0] for r in rows):
        rs = [r for r in rows if r[0] == stage]
        o = [r for r in rs if r[3] == "o"]
        x = [r for r in rs if r[3] == "x"]
        out[stage] = dict(
            n=len(rs), same=sum(r[3] == r[4] for r in rs),
            o_n=len(o), o_picked=sum(r[4] == "o" for r in o),
            x_n=len(x), x_picked=sum(r[4] == "o" for r in x))
    return out


if __name__ == "__main__" and not {"--audit", "--library"} & set(sys.argv):
    rows, sm = evaluate()
    for r in rows:
        print(("  " if r[3] == r[4] else "✗ "), r[0][:3], r[1][:5], r[2][:22].ljust(22), "印", r[3], "規則", r[4], r[5])
    print(json.dumps(sm, ensure_ascii=False, indent=1))


def audit_production():
    """今ある小元素（items.yaml の全版面）に同じ規則を当てて数える → (行, 集計)。行＝(版面, 名前, 判定, 理由)。
    規則は本番に未適用。ここで数えた × は「本番に今出ていて、規則なら出さない」絵＝同じ壊れ方の範囲。"""
    items = yaml.safe_load((ROOT / "items.yaml").read_text())
    items = items["items"] if isinstance(items, dict) else items
    rows, missing = [], 0
    for it in items:
        for e in it.get("emblem") or []:
            if e.get("shape") in ("logo", "icon", "badge"):   # 人物の切り抜きの規則：ロゴ・アイコン・ポスター（倉庫に置いた Wikimedia の絵）は当てない
                continue
            p = ROOT / "docs" / "home" / (e.get("image") or "")
            if not e.get("image") or not p.is_file():
                missing += 1
                continue
            v, why = original_verdict(trim(Image.open(p)))
            rows.append((it["name"], e["subject"], v, why))
    cnt = {k: sum(r[2] == k for r in rows) for k in "ox-"}
    why = {}
    for r in rows:
        if r[2] == "x":
            key = r[3].split("（")[0]
            why[key] = why.get(key, 0) + 1
    return rows, dict(n=len(rows), missing=missing, **cnt, x_by_reason=why)

LIB_URL = "https://bzokpnbcjscbcehdxtjq.supabase.co/rest/v1/boards?select=id,config&limit=500"
LIB_KEY = "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC"   # 公開の鍵（網頁にも入っている）。見えるのは公開の版面だけ


def audit_library():
    """ライブラリの版面（お客さまの版面）の小元素にも同じ規則を当てる → (行, 集計)。行＝(版面 id, 名前, 判定, 理由)。
    網につなぐ（公開の鍵で読める版面だけ。RLS で見えない版面は数えられない＝集計の boards に見えた数）。"""
    import urllib.request
    req = urllib.request.Request(LIB_URL, headers={"apikey": LIB_KEY})
    boards = json.load(urllib.request.urlopen(req, timeout=60))
    rows, bad = [], 0
    for b in boards:
        for e in (b.get("config") or {}).get("emblem") or []:
            try:
                if e["image"].startswith("http"):
                    raw = storage_bytes(e["image"]) if PATTERN.match(e["image"]) else urllib.request.urlopen(e["image"], timeout=30).read()
                else:   # 店長の版面と同じ絵を指す相対の道（docs/home）
                    raw = (ROOT / "docs" / "home" / e["image"]).read_bytes()
                v, why = original_verdict(trim(Image.open(io.BytesIO(raw))))
            except Exception as ex:
                print("read fail:", type(ex).__name__, ex, file=sys.stderr)
                bad += 1
                continue
            rows.append((b["id"], e["subject"], v, why))
    cnt = {k: sum(r[2] == k for r in rows) for k in "ox-"}
    return rows, dict(boards=len(boards), n=len(rows), unreadable=bad, **cnt)


if __name__ == "__main__" and "--library" in sys.argv:
    rows, sm = audit_library()
    by = {}
    for r in rows:
        if r[2] == "x":
            by.setdefault(r[0], []).append(r[1])
    for b, ns in sorted(by.items(), key=lambda t: -len(t[1])):
        print(f"board {b}: x {len(ns)}  {', '.join(ns[:6])}")
    print(json.dumps(sm, ensure_ascii=False, indent=1))

if __name__ == "__main__" and "--audit" in sys.argv:
    rows, sm = audit_production()
    by = {}
    for r in rows:
        if r[2] == "x":
            by.setdefault(r[0], []).append(r[1])
    for b, ns in sorted(by.items(), key=lambda t: -len(t[1])):
        print(f"{b}: x {len(ns)}  {', '.join(ns[:6])}")
    print(json.dumps(sm, ensure_ascii=False, indent=1))
