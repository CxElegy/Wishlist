"""画面を変えた PR の Before / After を Discord へ（2026-10-24，用户定的：「修正のときは画像の before after を」）。

progress.yml が PR の合併のたびに呼ぶ。画面に関わるファイルを変えた PR だけ：
  1. 合併の直後（本番はまだ前のまま）に撮る = Before
  2. その合併の render.yml（網页の生成＋お客さまのページの作り直し）が終わるのを待つ（12 分まで）＋ Pages の配信を 60 秒待つ
  3. 同じ画面を撮る = After → 左右に並べた画像を「合併しました」の知らせに付けて送る
撮る画面：ログインなし 1400px・test-a 1400px・test-a 390px（harness/ux_check.py の check と同じ開き方）。

    python harness/before_after.py <merge_sha> <PR の番号> <PR の題> <PR の網址>
"""
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

from PIL import Image, ImageChops, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ux_check  # noqa: E402

UI = re.compile(r"^(scripts/(render|user_pages|welcome|theme|likefx|emblem)\.py|templates/|sections\.yaml|docs/home/[^/]+\.js)")
VIEWS = [("guest", 1400), ("test-a", 1400), ("test-a", 390)]
BASE = "https://cxelegy.github.io/Wishlist/home/"
REPO = "CxElegy/Wishlist"
WAIT_RENDER_S = 12 * 60


def ui_changed(sha):
    files = subprocess.run(["git", "diff", "--name-only", f"{sha}~1", sha], capture_output=True, text=True).stdout.split()
    return [f for f in files if UI.match(f)]


def shoot(out):
    out.mkdir(parents=True, exist_ok=True)
    ux_check.WATCH_S = 8   # 写真だけなので短く（合併から本番の更新まで 2〜3 分：Before を間に合わせる。くり返しの点検は ux_check の本番の回で）
    with sync_playwright() as pw:
        for who, w in VIEWS:
            try:
                ux_check.check(pw, BASE, who, w, out)
            except Exception as ex:  # noqa: BLE001  1 枚撮れなくても残りは送る
                print(f"撮れなかった {who} {w}: {type(ex).__name__}")


def wait_render(sha):
    tok = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/render.yml/runs?head_sha={sha}&per_page=1"
    t0 = time.time()
    while time.time() - t0 < WAIT_RENDER_S:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
        try:
            runs = json.load(urllib.request.urlopen(req, timeout=30)).get("workflow_runs") or []
        except Exception:  # noqa: BLE001
            runs = []
        if runs and runs[0]["status"] == "completed":
            print("render.yml:", runs[0]["conclusion"])
            break
        time.sleep(30)
    time.sleep(60)   # Pages の配信


CELL = 24          # 変わった所を探すマスの大きさ（px）
CELL_MIN = 0.12    # マスの中で変わった点がこれ以上の割合なら「変わった」
BOX_MIN = 3        # 3 マス未満の小さな変化（時刻の数字など）は囲まない


def changed_boxes(a, b):
    """同じ大きさの 2 枚から、変わった所の四角（x0, y0, x1, y1）。マスに分けて比べ、隣どうしをまとめる。"""
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 40 else 0)
    cols, rows = a.width // CELL + 1, a.height // CELL + 1
    hot = set()
    for gy in range(rows):
        for gx in range(cols):
            box = (gx * CELL, gy * CELL, min((gx + 1) * CELL, a.width), min((gy + 1) * CELL, a.height))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            h = diff.crop(box).histogram()
            if h[255] / ((box[2] - box[0]) * (box[3] - box[1])) >= CELL_MIN:
                hot.add((gx, gy))
    boxes, seen = [], set()
    for start in sorted(hot):   # すぐ隣（上下左右・斜め）をつないだまとまりごとに 1 つの四角
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            gx, gy = stack.pop()
            group.append((gx, gy))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (gx + dx, gy + dy)
                    if n in hot and n not in seen:
                        seen.add(n)
                        stack.append(n)
        if len(group) < BOX_MIN:
            continue
        xs, ys = [g[0] for g in group], [g[1] for g in group]
        boxes.append((min(xs) * CELL, min(ys) * CELL, min((max(xs) + 1) * CELL, a.width), min((max(ys) + 1) * CELL, a.height)))
    # 大きな枠の中にすっぽり入る小さな枠は描かない（重なって見づらい）
    inside = lambda s, o: s != o and o[0] <= s[0] and o[1] <= s[1] and s[2] <= o[2] and s[3] <= o[3]   # noqa: E731
    return [s for s in boxes if not any(inside(s, o) for o in boxes)]


def compose(before, after):
    """左に Before・右に After。高さをそろえて上に札。幅は 1800px まで。"""
    a, b = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
    h = min(a.height, b.height, 1400)
    a, b = a.crop((0, 0, a.width, h)), b.crop((0, 0, b.width, h))
    if a.size == b.size:   # 変わった所を赤い枠で囲む（前と後の両方の同じ場所。2026-10-24 用户定的）
        boxes = changed_boxes(a, b)   # 描く前に 1 回だけ数える
        for im in (a, b):
            dd = ImageDraw.Draw(im)
            for x0, y0, x1, y1 in boxes:
                dd.rectangle((x0 + 2, y0 + 2, x1 - 3, y1 - 3), outline=(215, 38, 30), width=4)
    gap, top = 24, 44
    img = Image.new("RGB", (a.width + b.width + gap, h + top), (237, 235, 230))
    img.paste(a, (0, top))
    img.paste(b, (a.width + gap, top))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=26)
    except TypeError:   # 古い Pillow
        font = ImageFont.load_default()
    for x, label, color in ((0, "BEFORE", (26, 28, 34)), (a.width + gap, "AFTER", (184, 51, 106))):
        d.rectangle((x, 0, x + 170, top - 6), fill=color)
        d.text((x + 16, 6), label, fill=(251, 248, 241), font=font)
    if img.width > 1800:
        img = img.resize((1800, round(img.height * 1800 / img.width)))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def send(title, url, images):
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook:
        print("DISCORD_WEBHOOK_URL がない：送らない")
        return
    payload = {"content": f"🖼 Before / After：{title}\n{url}"[:1900], "allowed_mentions": {"parse": []},
               "attachments": [{"id": i, "filename": n} for i, (n, _) in enumerate(images)]}
    bnd = "wlba" + str(int(time.time()))
    body = io.BytesIO()
    def part(head, data):
        body.write(f"--{bnd}\r\n{head}\r\n\r\n".encode())
        body.write(data)
        body.write(b"\r\n")
    part('Content-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json', json.dumps(payload).encode())
    for i, (name, data) in enumerate(images):
        part(f'Content-Disposition: form-data; name="files[{i}]"; filename="{name}"\r\nContent-Type: image/png', data)
    body.write(f"--{bnd}--\r\n".encode())
    req = urllib.request.Request(hook, data=body.getvalue(), headers={"Content-Type": f"multipart/form-data; boundary={bnd}", "User-Agent": "wishlist-before-after"})
    with urllib.request.urlopen(req, timeout=60) as r:
        print("Discord:", r.status)


def main(argv):
    sha, num, title, url = argv[:4]
    changed = ui_changed(sha)
    if not changed:
        print("画面に関わるファイルの変更なし：撮らない")
        return 0
    root = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "ba"
    shoot(root / "before")
    wait_render(sha)
    shoot(root / "after")
    images = []
    for who, w in VIEWS:
        b, a = root / "before" / f"{who}-{w}.png", root / "after" / f"{who}-{w}.png"
        if b.exists() and a.exists():
            images.append((f"{who}-{w}.png", compose(b, a)))
    if images:
        send(f"#{num} {title}", url, images)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
