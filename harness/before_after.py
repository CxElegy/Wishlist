"""画面を変えた PR の Before / After を Discord へ（2026-10-24，用户定的：「修正のときは画像の before after を」）。

progress.yml が PR の合併のたびに呼ぶ。網页に効く PR は、本番が新しくなったのを確かめて「🟢 公開を確かめました」を送る（2026-10-25）。画面に関わるファイルを変えた PR は写真も：
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
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import progress_notify  # noqa: E402

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
    """その合併の render.yml が終わるまで（12 分まで）。3 分たっても回が見つからなければ（render.yml の paths に当たらない PR）待たない。
    返り値：結論（success・failure・cancelled）か None（回がない・時間切れ）。"""
    tok = os.environ.get("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/render.yml/runs?head_sha={sha}&per_page=1"
    t0, out = time.time(), None
    while time.time() - t0 < WAIT_RENDER_S:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"} if tok else {})
        try:
            runs = json.load(urllib.request.urlopen(req, timeout=30)).get("workflow_runs") or []
        except Exception:  # noqa: BLE001
            runs = []
        if runs and runs[0]["status"] == "completed":
            out = runs[0]["conclusion"]
            print("render.yml:", out)
            break
        if not runs and time.time() - t0 > 180:
            print("render.yml の回なし")
            break
        time.sleep(30)
    return out


LIVE = "https://cxelegy.github.io/Wishlist/"
PAGE_NAME = {"index": "トップ（店長のページ）", "admin": "管理ページ", "wishlist": "欲しい物リスト", "heat": "話題度分析"}


def _get(url):
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}t={int(time.time() * 1000)}", headers={"Cache-Control": "no-cache", "User-Agent": "wishlist-live-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def live_versions():
    """本番の docs/home/version.json（ページごとの中身の指紋）。読めなければ {}。"""
    try:
        return {k: v for k, v in json.loads(_get(BASE + "version.json")).items() if k in PAGE_NAME}
    except Exception:  # noqa: BLE001
        return {}


def docs_files(sha):
    """PR で直接変えた公開のファイル（docs/ の下、生成物でないもの）→ 本番の網址と中身。"""
    out = []
    for f in subprocess.run(["git", "diff", "--name-only", f"{sha}~1", sha], capture_output=True, text=True).stdout.split():
        if f.startswith("docs/") and not f.startswith(("docs/home/", "docs/rules/")) and pathlib.Path(f).exists():
            out.append((LIVE + f[len("docs/"):], pathlib.Path(f).read_bytes()))
    return out


def wait_live(before, files, limit=360):
    """本番が新しくなったかを確かめる（6 分まで 20 秒おき）：version.json の指紋が変わったページは、その HTML の wl-ver も同じになるまで。
    直接変えた docs/ のファイルは、本番の中身が倉庫と同じになるまで。返り値：(新しくなったページの名前, 確かめた docs/ の網址, まだのもの)。"""
    t0, pages, done_files = time.time(), [], []
    while True:
        now = live_versions()
        pages = []
        for k, v in now.items():
            if before.get(k) and v != before.get(k):
                try:
                    html = _get(BASE + ("" if k == "index" else f"{k}.html")).decode("utf-8", "replace")
                    ok = f'content="{v}"' in html
                except Exception:  # noqa: BLE001
                    ok = False
                pages.append((k, ok))
        done_files = []
        for url, body in files:
            try:
                done_files.append((url, _get(url) == body))
            except Exception:  # noqa: BLE001
                done_files.append((url, False))
        waiting = [PAGE_NAME[k] for k, ok in pages if not ok] + [u for u, ok in done_files if not ok]
        if (pages or files) and not waiting or time.time() - t0 > limit:
            return [PAGE_NAME[k] for k, ok in pages if ok], [u for u, ok in done_files if ok], waiting
        if not files and not pages and time.time() - t0 > 120:   # 2 分たっても指紋が変わらない＝中身の変わらない合併
            return [], [], []
        time.sleep(20)


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


def send(title, url, images, text=None):
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook:
        print("DISCORD_WEBHOOK_URL がない：送らない")
        return
    if not images:   # 写真なし：文だけ
        req = urllib.request.Request(hook, data=json.dumps({"content": (text or title)[:1900], "allowed_mentions": {"parse": []}}).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "wishlist-before-after"})
        with urllib.request.urlopen(req, timeout=60) as r:
            print("Discord:", r.status)
        return
    payload = {"content": (text or f"🖼 Before / After：{title}\n{url}")[:1900], "allowed_mentions": {"parse": []},
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
    """合併のたびに：網页に効く PR（progress_notify.page_effect が maybe）は、本番で新しくなったのを確かめて「🟢 公開を確かめました」を送る
    （2026-10-25，用户定的：ページが本当に更新されたら知らせる。プライベートウィンドウなどの手間をかけさせない）。画面に関わる PR は Before / After の写真も付ける。"""
    sha, num, title, url = argv[:4]
    files = subprocess.run(["git", "diff", "--name-only", f"{sha}~1", sha], capture_output=True, text=True).stdout.split()
    if progress_notify.page_effect(files) == "none":
        print("網页に効かない PR（文書・道具だけ）：確かめない")
        return 0
    changed = ui_changed(sha)
    before = live_versions()
    root = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "ba"
    if changed:
        shoot(root / "before")
    t0 = time.time()
    res = wait_render(sha)
    pages, docs, waiting = wait_live(before, docs_files(sha))
    mins = max(1, round((time.time() - t0) / 60))
    images = []
    if changed:
        shoot(root / "after")
        for who, w in VIEWS:
            b, a = root / "before" / f"{who}-{w}.png", root / "after" / f"{who}-{w}.png"
            if b.exists() and a.exists():
                images.append((f"{who}-{w}.png", compose(b, a)))
    head = f"#{num} {title}"
    if pages or docs:
        names = "・".join(pages + [u.replace(LIVE, "") for u in docs])
        text = (f"🟢 公開を確かめました（合併から約 {mins} 分）：{head}\n新しくなったページ：{names}\n"
                f"開き直すだけで見えます（開いたままのページも自分で新しくなります）。{BASE}\n{url}")
    elif waiting:
        text = f"⚠ まだ本番が新しくなっていません（{mins} 分待った）：{head}\nまだ：{'・'.join(waiting)} · render.yml：{res or '回なし'}\n{url}"
    else:
        text = f"ℹ 公開しました・見た目の変わるページはありません（裏の仕組みだけ）：{head}\n{url}"
    send(head, url, images, text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
