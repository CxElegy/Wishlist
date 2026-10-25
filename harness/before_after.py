"""画面を変えた PR の Before / After を Discord へ（2026-10-24，用户定的：「修正のときは画像の before after を」）。

progress.yml が PR の合併のたびに呼ぶ。網页に効く PR は、本番が新しくなったのを確かめて「🟢 公開を確かめました」を送る（2026-10-25）。画面に関わるファイルを変えた PR は写真も：
  1. 合併の直後（本番はまだ前のまま）に撮る = Before
  2. その合併の render.yml（網页の生成＋お客さまのページの作り直し）が終わるのを待つ（12 分まで）＋ Pages の配信を 60 秒待つ
  3. 同じ画面を撮る = After → 左右に並べた画像を「合併しました」の知らせに付けて送る
撮る画面：ログインなし 1400px・test-a 1400px・test-a 390px（harness/ux_check.py の session と同じログイン）。

「何が変わったか一目で」（2026-10-25，用户定的：同じに見える 2 枚では何をしているのかわからない。HARNESS「報告は何が・どこで・数」）：
  - 撮る場所は PR の説明の 1 行「画面：<ページ> <CSS セレクタ> — <どこを見る>」（例：画面：index #sec-bleach .emb — BLEACH の小元素）。
    その欄までスクロールして欄だけを切り抜き、大きく撮る。数（欄の中の img の数）の前と後も書く。書いていなければページ全体を撮り、変わった所の一番大きい所を切り抜く
  - 差がなければ写真を送らない：「画面の変化なし」の 1 行
  - 画面が後で変わる PR（小元素・名簿・記事集め・AI 編集＝LATER）は Before だけ撮って Actions の artifact（ba-pending-<番号>）に置き、
    その後台の回（progress.yml の workflow_run）が終わったあとに After を撮って送る（later）
  - 写真の上の一行：何を直した → どこを見る → 数

    python harness/before_after.py <merge_sha> <PR の番号> <PR の題> <PR の網址>     （PR_BODY に PR の説明）
    python harness/before_after.py later <終わった回の workflow の名前> <回が始まった時刻> <artifact を置いたフォルダ>
"""
import datetime as dt
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
# 合併では変わらず、後台の回のあとに画面が変わるファイル → その回の workflow の名前と定時のファイル
LATER = [
    (re.compile(r"^scripts/(emblem\w*|face_id|gate)\.py$"), "后台作業", "background.yml"),
    (re.compile(r"^scripts/library_emblem\.py$"), "ライブラリの小元素", "library_emblem.yml"),
    (re.compile(r"^scripts/(digest|sources|intel|collect_watch|hdimg|images|userfeed)\.py$"), "关注清单通信", "digest.yml"),
]
# ページは index か <英数>.html、セレクタは英数の CSS（「画面：変わらない（…）」のような文は当てない）
SPOT = re.compile(r"^\s*[-*]?\s*画面[:：]\s*(index|home/?|[\w-]+\.html)\s+([#.\[a-zA-Z][\x21-\x7e ]*?)(?:\s+[—-]{1,2}\s+(.+))?\s*$", re.M)
MAX_H = 8000       # ページ全体を撮るときの高さの上限（px）
BASE = "https://cxelegy.github.io/Wishlist/home/"
REPO = "CxElegy/Wishlist"
WAIT_RENDER_S = 12 * 60


def ui_changed(sha):
    files = subprocess.run(["git", "diff", "--name-only", f"{sha}~1", sha], capture_output=True, text=True).stdout.split()
    return [f for f in files if UI.match(f)]


def later_of(files):
    """後台の回のあとに画面が変わる PR なら、その回の (workflow の名前, 定時のファイル)。なければ None。"""
    for f in files:
        for rx, name, yml in LATER:
            if rx.match(f):
                return name, yml
    return None


def spot(body):
    """PR の説明の「画面：<ページ> <セレクタ> — <どこを見る>」→ (ページ, セレクタ, 説明)。なければ None。ページ index は店長のページ。"""
    m = SPOT.search(body or "")
    if not m:
        return None
    page, sel, where = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
    page = "" if page in ("index", "index.html", "home", "home/") else page
    return page, sel, where or sel


def _cron_next(expr, now):
    """5 つの欄の cron（分・時は数・*・*/n・a,b。日・月・曜日は * のときだけ）の次の時刻（UTC）。読めなければ None。"""
    parts = expr.split()
    if len(parts) != 5 or any(p != "*" for p in parts[2:]):
        return None
    def vals(f, n):
        out = set()
        for x in f.split(","):
            if x == "*":
                out |= set(range(n))
            elif x.startswith("*/"):
                out |= set(range(0, n, int(x[2:])))
            elif x.isdigit():
                out.add(int(x))
            else:
                return None
        return out
    mins, hours = vals(parts[0], 60), vals(parts[1], 24)
    if not mins or not hours:
        return None
    t = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    for _ in range(60 * 48):
        if t.minute in mins and t.hour in hours:
            return t
        t += dt.timedelta(minutes=1)
    return None


def next_run(yml, now=None):
    """その workflow の定時の次の回（日本時間の HH:MM）。読めなければ「次の回」。"""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        text = (pathlib.Path(__file__).resolve().parent.parent / ".github/workflows" / yml).read_text(encoding="utf-8")
    except OSError:
        return "次の回"
    ts = [t for t in (_cron_next(c, now) for c in re.findall(r'cron:\s*"([^"]+)"', text)) if t]
    return min(ts).astimezone(progress_notify.JST).strftime("%H:%M") if ts else "次の回"


SEED_JS = """(()=>{let s=20261025;Math.random=()=>((s=Math.imul(s^(s>>>15),2246822507)+0x6D2B79F5|0)>>>0)/4294967296;})();"""


def shoot(out, where=None):
    """VIEWS をそれぞれ撮る。where=(ページ, セレクタ, …) ならその欄だけ、なければページ全体（MAX_H まで）。
    乱数は決まった種に（「気になるかも？」・小元素のランダムな 1 枚が前と後で同じになる）・動きは止める。返り値：{名前: 欄の中の img の数}。"""
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    page, sel = (where[0], where[1]) if where else ("", None)
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
        for who, w in VIEWS:
            name = f"{who}-{w}"
            try:
                ctx = b.new_context(viewport={"width": w, "height": 900}, reduced_motion="reduce")
                ctx.add_init_script(SEED_JS)
                pg = ctx.new_page()
                if ux_check.WHO[who]:
                    pg.goto(BASE, wait_until="domcontentloaded", timeout=60000)
                    pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}",
                                ux_check.session(ux_check.WHO[who]))
                pg.goto(BASE + page, wait_until="domcontentloaded", timeout=60000)
                try:   # お客さまのページは JS で描く：版面かポスターが出るまで（30 秒まで）
                    pg.wait_for_function("document.querySelector('section.sec,#front')", timeout=30000)
                except Exception:  # noqa: BLE001
                    pass
                pg.wait_for_timeout(4000)
                # 遅れて読む写真（loading=lazy）を前と後で同じにするため、下まで一度たどって戻る
                pg.evaluate("async()=>{const H=Math.min(document.documentElement.scrollHeight,%d);for(let y=0;y<H;y+=700){scrollTo(0,y);await new Promise(r=>setTimeout(r,120));}scrollTo(0,0);}" % MAX_H)
                pg.wait_for_timeout(2500)
                if sel:
                    el = pg.locator(sel).first
                    if el.count():
                        el.scroll_into_view_if_needed(timeout=10000)
                        pg.wait_for_timeout(800)
                        el.screenshot(path=str(out / f"{name}.png"))
                        counts[name] = el.locator("img").count()
                    else:
                        print(f"欄がない {name}: {sel}")
                else:
                    h = min(pg.evaluate("document.documentElement.scrollHeight"), MAX_H)
                    pg.screenshot(path=str(out / f"{name}.png"), clip={"x": 0, "y": 0, "width": w, "height": h}, full_page=True)
                ctx.close()
            except Exception as ex:  # noqa: BLE001  1 枚撮れなくても残りは送る
                print(f"撮れなかった {who} {w}: {type(ex).__name__}")
        b.close()
    (out / "counts.json").write_text(json.dumps(counts), encoding="utf-8")
    return counts


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


PAD = 60          # 切り抜くとき、変わった所のまわりに残す幅（px）
CROP_MAX_H = 1400  # 切り抜きの高さの上限
ZOOM_W = 900       # 切り抜きがこれより細ければ 2 倍まで大きく


def focus(a, b, boxes):
    """変わった所の一番大きい四角を真ん中に、まわり PAD を付けて切り抜く範囲（x0, y0, x1, y1）。"""
    x0, y0, x1, y1 = max(boxes, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    hw = min(max((x1 - x0) // 2 + PAD, 320), a.width // 2)
    hh = min(max((y1 - y0) // 2 + PAD, 240), CROP_MAX_H // 2)
    if y1 - y0 + 2 * PAD > 2 * hh:   # 入りきらない（行が増えて下が全部ずれた）＝変わり始めの所を上に
        cy = y0 - PAD + hh
    left = min(max(cx - hw, 0), max(a.width - 2 * hw, 0))
    top = min(max(cy - hh, 0), max(a.height - 2 * hh, 0))
    return left, top, min(left + 2 * hw, a.width), min(top + 2 * hh, a.height)


GROUND = (128, 128, 128)   # 埋める地の色（どのテーマの地とも 40 以上違う灰色：埋めた所が必ず「変わった」になる）


def _pad(im, w, h):
    out = Image.new("RGB", (w, h), GROUND)
    if im:
        out.paste(im, (0, 0))
    return out


def compose(before, after):
    """左に Before・右に After。大きさが違えば（ページの高さが変わった）大きい方に合わせて地の色で埋め、changed_boxes の一番大きい所を
    真ん中に切り抜き、赤い枠。片方が None（その欄がない＝新しい欄・消えた欄）なら地の色の 1 枚と比べる。
    差がなければ None（写真を送らない、2026-10-25 用户定的）。幅は 1800px まで。"""
    a, b = (Image.open(p).convert("RGB") if p else None for p in (before, after))
    w, h = max(im.width for im in (a, b) if im), max(im.height for im in (a, b) if im)
    common = min(im.height for im in (a, b) if im) if a and b else 0
    a, b = (_pad(im, w, h) for im in (a, b))
    boxes = changed_boxes(a, b)   # 描く前に 1 回だけ数える
    if not boxes:
        return None
    crop = focus(a, b, [r for r in boxes if r[1] < common] or boxes)   # 伸びた下の端より、両方にある所の変化を真ん中に
    a, b = a.crop(crop), b.crop(crop)
    boxes = [(x0 - crop[0], y0 - crop[1], x1 - crop[0], y1 - crop[1]) for x0, y0, x1, y1 in boxes]
    for im in (a, b):   # 変わった所を赤い枠で囲む（前と後の両方の同じ場所。2026-10-24 用户定的）
        dd = ImageDraw.Draw(im)
        for x0, y0, x1, y1 in boxes:
            dd.rectangle((x0 + 2, y0 + 2, x1 - 3, y1 - 3), outline=(215, 38, 30), width=4)
    if max(a.width, b.width) < ZOOM_W:   # 小さな欄は大きく
        k = min(2.0, ZOOM_W / max(a.width, b.width))
        a, b = (im.resize((round(im.width * k), round(im.height * k))) for im in (a, b))
    h = max(a.height, b.height)
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


def headline(title, where, counts_b, counts_a):
    """写真の上の一行：何を直した → どこを見る → 数（欄の中の img の数が変わったときだけ）。"""
    nums = ""
    for k in counts_a:
        if k in counts_b and counts_b[k] != counts_a[k]:
            nums = f" → {counts_b[k]}→{counts_a[k]} 枚（{k}）"
            break
    return f"{title} → 見る所：{where or '赤枠の所'}{nums}"


def pairs(root, where, title):
    """before/ と after/ の同じ名前の写真を並べる。差のないものは外す。片方だけ（新しい欄・消えた欄）は「ない」と比べる。
    返り値：(写真, 一行, 両方とも撮れなかった画面の名前)。"""
    cb = json.loads((root / "before" / "counts.json").read_text()) if (root / "before" / "counts.json").exists() else {}
    ca = json.loads((root / "after" / "counts.json").read_text()) if (root / "after" / "counts.json").exists() else {}
    images, missing = [], []
    for who, w in VIEWS:
        b, a = root / "before" / f"{who}-{w}.png", root / "after" / f"{who}-{w}.png"
        if not b.exists() and not a.exists():
            missing.append(f"{who}-{w}")
            continue
        png = compose(b if b.exists() else None, a if a.exists() else None)
        if png:
            images.append((f"{who}-{w}.png", png))
    return images, headline(title, where[2] if where else "", cb, ca), missing


def no_change(missing, where):
    """写真がないときの一行：撮れなかった画面があれば「変化なし」と言わない。"""
    shot = [f"{w}-{x}" for w, x in VIEWS if f"{w}-{x}" not in missing]
    if not shot:
        return "⚠ 画面を撮れませんでした（" + (f"欄 {where[1]} が前も後もない" if where else "撮影の失敗") + "）：画面の変化は見ていません"
    return ("画面の変化なし（撮った所：" + "・".join(shot) + (f"・{where[2]}" if where else "") + "）"
            + (f"・撮れなかった：{'・'.join(missing)}" if missing else ""))


def main(argv):
    """合併のたびに：網页に効く PR（progress_notify.page_effect が maybe）は、本番で新しくなったのを確かめて「🟢 公開を確かめました」を送る
    （2026-10-25，用户定的：ページが本当に更新されたら知らせる。プライベートウィンドウなどの手間をかけさせない）。画面に関わる PR は Before / After の写真も付ける。
    後台の回のあとに変わる PR（LATER）は Before だけ撮って ba-pending/ に置く（progress.yml が artifact にする）。"""
    if argv and argv[0] == "later":
        return later(*argv[1:4])
    sha, num, title, url = argv[:4]
    body = os.environ.get("PR_BODY", "")
    files = subprocess.run(["git", "diff", "--name-only", f"{sha}~1", sha], capture_output=True, text=True).stdout.split()
    if progress_notify.page_effect(files) == "none":
        print("網页に効かない PR（文書・道具だけ）：確かめない")
        return 0
    where = spot(body)
    lat = later_of(files)
    changed = ui_changed(sha) or (where and not lat) or lat
    before = live_versions()
    root = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "ba"
    if changed:
        shoot(root / "before", where)
    t0 = time.time()
    res = wait_render(sha)
    pages, docs, waiting = wait_live(before, docs_files(sha))
    mins = max(1, round((time.time() - t0) / 60))
    images, line = [], ""
    if lat:   # 写真は後台の回のあと（③）。Before と説明を置いていく
        pend = pathlib.Path(os.environ.get("BA_PENDING", "ba-pending"))   # progress.yml が artifact にする
        pend.mkdir(parents=True, exist_ok=True)
        for f in (root / "before").glob("*"):
            (pend / f.name).write_bytes(f.read_bytes())
        (pend / "meta.json").write_text(json.dumps({"num": num, "title": title, "url": url, "where": where, "workflow": lat[0],
                                                     "merged_at": dt.datetime.now(dt.timezone.utc).isoformat()}, ensure_ascii=False), encoding="utf-8")
        line = f"🕒 画面は合併では変わりません。変わるのは「{lat[0]}」の回のあと（見込み {next_run(lat[1])} 日本時間）→ そのあと Before / After を送ります。"
    elif changed:
        shoot(root / "after", where)
        images, line, missing = pairs(root, where, title)
        if not images:
            line = no_change(missing, where)
    head = f"#{num} {title}"
    if pages or docs:
        names = "・".join(pages + [u.replace(LIVE, "") for u in docs])
        text = (f"🟢 公開を確かめました（合併から約 {mins} 分）：{head}\n新しくなったページ：{names}\n"
                f"開き直すだけで見えます（開いたままのページも自分で新しくなります）。{BASE}\n{url}")
    elif waiting:
        text = f"⚠ まだ本番が新しくなっていません（{mins} 分待った）：{head}\nまだ：{'・'.join(waiting)} · render.yml：{res or '回なし'}\n{url}"
    else:
        text = f"ℹ 公開しました・見た目の変わるページはありません（裏の仕組みだけ）：{head}\n{url}"
    if line:
        text = f"🖼 {line}\n" + text
    send(head, url, images, text)
    return 0


def last_success(name):
    """その workflow の最後に成功した回が始まった時刻（UTC）。読めなければ None。
    bot（GITHUB_TOKEN）が起こした回の終わりでは workflow_run が起きないので、定時の見回りはこれで見る（2026-10-25）。"""
    yml = next((y for _, n, y in LATER if n == name), None)
    if not yml:
        return None
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/actions/workflows/{yml}/runs?status=success&per_page=1",
                                 headers={"Authorization": f"Bearer {tok}"} if tok else {})
    try:
        runs = json.load(urllib.request.urlopen(req, timeout=30)).get("workflow_runs") or []
        return dt.datetime.fromisoformat(runs[0]["run_started_at"].replace("Z", "+00:00")) if runs else None
    except Exception:  # noqa: BLE001
        return None


def later(workflow, started_at, folder):
    """後台の回（workflow）が終わったあと：artifact に置いた Before（folder/<名前>/meta.json）のうち、この workflow を待っていて
    合併より後に始まった回のものを撮り直して送る。送った（か 2 日たって諦めた）ものの名前を folder/sent.txt へ（progress.yml が artifact を消す）。
    workflow が空（定時の見回り）なら、それぞれの待っている workflow の最後に成功した回で見る。"""
    folder = pathlib.Path(folder)
    started = dt.datetime.fromisoformat(started_at.replace("Z", "+00:00")) if started_at else None
    sent, slept = [], False
    for meta_p in sorted(folder.glob("*/meta.json")):
        d = meta_p.parent
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        merged = dt.datetime.fromisoformat(m["merged_at"])
        head = f"#{m['num']} {m['title']}"
        if dt.datetime.now(dt.timezone.utc) - merged > dt.timedelta(days=2):
            send(head, m["url"], [], f"🖼 {head}：2 日たっても「{m['workflow']}」の回のあとの写真を撮れませんでした（画面の変化は見ていません）\n{m['url']}")
            sent.append(d.name)
            continue
        if workflow:
            if m["workflow"] != workflow or started < merged:
                continue
        else:
            s = last_success(m["workflow"])
            if not s or s < merged:
                continue
        wf = m["workflow"]
        root = d / "ba"
        (root / "before").mkdir(parents=True, exist_ok=True)
        for f in d.iterdir():
            if f.is_file() and f.name not in ("meta.json", ".id"):
                (root / "before" / f.name).write_bytes(f.read_bytes())
        where = tuple(m["where"]) if m.get("where") else None
        if not slept:   # 回の push から Pages の配信まで
            time.sleep(90)
            slept = True
        shoot(root / "after", where)
        images, line, missing = pairs(root, where, m["title"])
        if not images:
            line = f"「{wf}」の回のあと：{no_change(missing, where)}：{head}"
        send(head, m["url"], images, f"🖼 {line}（「{wf}」の回のあと）\n{head}\n{m['url']}")
        sent.append(d.name)
    (folder / "sent.txt").write_text("\n".join(sent), encoding="utf-8")
    print("送った:", sent)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
