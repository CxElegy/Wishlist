"""写真の一時保管（2026-10-31，用户定的：記事の写真を先にサーバーへ置き、読み込みを速くする。溜めない）。

網页の記事の主写真は、よそのサイトの原寸へ直リンクだった（重い・遅い・防盗链で落ちる）。この係が
  1. docs/home/*.html とお客さまのページ（Storage pages/）の写真（data-e="s"／"r"：主写真・ぼかし・ギャラリー・欲しい物）の網址を数え、
  2. まだ置いていないものを Referer なしで取って、幅 400／800 の webp に縮め、
  3. Supabase Storage の公開の箱 photos（db/photos.sql）へ上げる。
render.py の _pic は置いてあるものなら 800 の網址を先頭にし、原寸の網址は落ち先（data-fb）に残す。
置く数は state/photo_store.json（キーは網址の指紋）。保つのは「いまのページに載っている」か「最後に使ってから 14 日以内」まで、
全体が上限（300MB）を超えたら古い順に消す。消すのは photos の箱の中だけ。

    python scripts/photo_store.py [--minutes 10]     # photo_store.yml（SUPABASE_SERVICE_KEY）
    python scripts/photo_store.py --kick             # render のあと（digest・background・render.yml）：置いていない写真があれば photo_store.yml を起こす
"""

import hashlib
import html
import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sitedir  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "photo_store.json"
BUCKET = "photos"
WIDTHS = (400, 800)
KEEP_DAYS = 14
CAP = 300 * 1024 * 1024
RETRY_DAYS = 1       # 取れなかった網址は 1 日あけて取り直す
MAX_FETCH = 12 * 1024 * 1024
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]*)"[^>]*?data-e="[sr]"')   # 主写真(s)・ぼかし／ギャラリー／欲しい物(r)


def day():
    return int(time.time() // 86400)


def key(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def name(k, w=800):
    return f"{k}-{w}.webp"


def public(base, k, w=800):
    return f"{base.rstrip('/')}/storage/v1/object/public/{BUCKET}/{name(k, w)}"


def load(path=None):
    try:
        d = json.loads((path or STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"base": d.get("base", ""), "p": d.get("p", {}), "x": d.get("x", {}), "stat": d.get("stat", {})}


_CACHE = []


def stored(url, w=800):
    """render 用：置いてある写真なら一時保管の幅 w（400／800）の網址、なければ None。"""
    if not _CACHE:
        _CACHE.append(load())
    st = _CACHE[0]
    k = key(url)
    return public(st["base"], k, w) if st["base"] and k in st["p"] else None


def tint_css(url):
    """render 用：置いてある写真の平均色（#rrggbb）、なければ None。"""
    if not _CACHE:
        _CACHE.append(load())
    v = _CACHE[0]["p"].get(key(url))
    return (v or {}).get("c") or None


def pages(site=None):
    return sorted((site or sitedir.SITE_DIR).glob("*.html"))


def user_pages(base, keyv):
    """お客さまのページ（Storage の pages/<本人>/*.html。user_pages.py が作る）の本文。店長と同じ置き場を使うため、写真を数える。取れなければ空。"""
    out = []
    try:
        req = urllib.request.Request(f"{base.rstrip('/')}/storage/v1/object/list/pages", data=json.dumps({"prefix": "", "limit": 1000}).encode(),
                                     method="POST", headers={"apikey": keyv, "Authorization": f"Bearer {keyv}", "Content-Type": "application/json"})
        folders = [d["name"] for d in json.loads(urllib.request.urlopen(req, timeout=30).read()) if d.get("name")]
    except Exception:  # noqa: BLE001
        return out
    for fo in folders:
        try:
            r = urllib.request.Request(f"{base.rstrip('/')}/storage/v1/object/pages/{fo}/index.html", headers={"apikey": keyv, "Authorization": f"Bearer {keyv}"})
            out.append(urllib.request.urlopen(r, timeout=30).read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            continue
    return out


def scan_text(texts, seen, want):
    """want は「どの版面の先頭の写真か」を先に入れる（置く順：先頭が置き場に無い版面から。Fast 3G で先頭が届かない根）。"""
    pre = f"/storage/v1/object/public/{BUCKET}/"
    lead, rest = {}, {}
    for text in texts:
        for part in text.split("<section")[1:] or [text]:
            for i, src in enumerate(IMG_RE.findall(part)):
                src = html.unescape(src)
                if pre in src:
                    seen.add(src.rsplit("/", 1)[-1].split("-")[0])
                elif src.startswith("http"):
                    (lead if i < 2 else rest)[key(src)] = src
    for k, u in {**lead, **{k: u for k, u in rest.items() if k not in lead}}.items():
        want[k] = u


def scan(site=None, extra=()):
    """公開ページ（＋お客さまのページ extra）の写真を数える。→ (載っている指紋の集合, {指紋: 原寸の網址}（まだ置いていないもの）, 写真の種類の数)。
    店長もお客さまも、主写真・ぼかし・ギャラリー・欲しい物の写真を同じ置き場で（網址ごとに 1 回）。"""
    seen, want = set(), {}
    scan_text([f.read_text(encoding="utf-8") for f in pages(site)], seen, want)
    scan_text(extra, seen, want)
    return seen, want, len(seen | set(want))


def todo_count(path=None, site=None):
    """まだ置いていなくて、取り直してよい写真の数（render のあと、1 枚でもあれば写真の一時保管を起こす印）。
    取れなかった分は RETRY_DAYS あけるので、取れない写真で起こし続けることはない。"""
    st = load(path)
    _, want, _ = scan(site)
    today = day()
    return sum(1 for k in want if k not in st["p"] and today - st["x"].get(k, -9) >= RETRY_DAYS)


def shrink(data):
    """原寸 → {幅: webp のバイト列}。縮めるだけで拡大しない。読めない・小さすぎる画像は None。"""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) > 1 or im.width < 64 or im.height < 64:
        return None
    im = im.convert("RGBA" if "A" in im.mode or "transparency" in im.info else "RGB")
    out = {}
    for w in WIDTHS:
        v = im if im.width <= w else im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        b = io.BytesIO()
        v.save(b, "WEBP", quality=80, method=4)
        out[w] = b.getvalue()
    return out


def tint(data):
    """画像の平均の色（#rrggbb）。ページの写真の枠の下絵に埋める：通信 0 で、写真が届くまでの間も色だけは出る（2026-10-31 写真 0.5 秒）。"""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB").resize((1, 1), Image.BOX)
    return "#%02x%02x%02x" % im.getpixel((0, 0))


def mass(data, bins=12):
    """切る位置を決める材料（2026-11-01 小カード案 2）：絵の「主役」の分布を横・縦それぞれ bins 区間の整数（合計 100）で返す。
    主役 = 顔（正面向きの検出）と、題字・ロゴ・人物の輪郭が多い所（輪郭の濃さ）。顔があれば半分を顔、残りを輪郭に配る。
    render の小さいカードが、枠に合わせて切るとき主役が 6 割以上残る位置を選び、残らない絵は切らずに全体を見せる。読めなければ None。"""
    import cv2
    import numpy as np
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("L")
    g = np.asarray(im, dtype=np.float32)
    if g.shape[0] < 16 or g.shape[1] < 16:
        return None
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    edge = cv2.blur(mag, (9, 9)) ** 1.5
    edge /= edge.sum() or 1.0
    m = edge
    try:
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = casc.detectMultiScale(g.astype(np.uint8), 1.15, 5, minSize=(max(24, g.shape[1] // 14),) * 2)
    except Exception:  # noqa: BLE001  顔の検出が使えなくても輪郭だけで測る
        faces = []
    if len(faces):
        f = np.zeros_like(g)
        for x, y, w, h in faces:
            f[y:y + h, x:x + w] += 1.0
        m = 0.5 * edge + 0.5 * f / f.sum()

    def prof(v):
        b = np.array_split(v, bins)
        s = np.array([x.sum() for x in b])
        s = s / (s.sum() or 1.0) * 100
        return [int(round(x)) for x in s]
    return [prof(m.sum(axis=0)), prof(m.sum(axis=1))]


def mass_of(base, k):
    """置いてある 400 の写真から mass を取る（持たない昔の分の埋め直し）。取れない写真は [] （測れない＝切らない）。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(public(base, k, 400), headers={"User-Agent": UA}), timeout=30) as r:
            return k, mass(r.read()) or []
    except Exception:  # noqa: BLE001  次の回にまた試す
        return k, None


def mass_css(url):
    """render 用：data-m に入れる文字列「横の分布;縦の分布」。測っていない・測れない写真は None。"""
    if not _CACHE:
        _CACHE.append(load())
    v = (_CACHE[0]["p"].get(key(url)) or {}).get("m")
    return ";".join(",".join(map(str, a)) for a in v) if v else None


def tint_of(base, k):
    """置いてある 400 の写真から色を取る（色のない昔の分の埋め直し）。取れなければ None。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(public(base, k, 400), headers={"User-Agent": UA}), timeout=30) as r:
            return k, tint(r.read())
    except Exception:  # noqa: BLE001  次の回にまた試す
        return k, None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if not (r.headers.get("Content-Type") or "").startswith("image/"):
            return None
        return r.read(MAX_FETCH + 1)[:MAX_FETCH]


def _req(base, keyv, path, data=None, method="POST", ctype="image/webp", extra=None):
    h = {"apikey": keyv, "Authorization": f"Bearer {keyv}", "Content-Type": ctype, **(extra or {})}
    req = urllib.request.Request(f"{base.rstrip('/')}/storage/v1/object/{path}", data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


CACHE = "public, max-age=31536000, immutable"   # ファイル名が中身の指紋なので変わらない


def upload(base, keyv, k, sizes):
    for w, b in sizes.items():
        _req(base, keyv, f"{BUCKET}/{name(k, w)}", b, extra={"x-upsert": "true", "Cache-Control": CACHE})


def rehead(base, keyv, k):
    """前に上げた分（cache-control が public, max-age=1209600 のまま）を、同じ中身で上げ直して CACHE にする。"""
    try:
        sizes = {}
        for w in WIDTHS:
            with urllib.request.urlopen(urllib.request.Request(public(base, k, w), headers={"User-Agent": UA}), timeout=30) as r:
                sizes[w] = r.read()
        upload(base, keyv, k, sizes)
        return k, True
    except Exception:  # noqa: BLE001  次の回にまた試す
        return k, False


def remove(base, keyv, ks):
    names = [name(k, w) for k in ks for w in WIDTHS]
    for i in range(0, len(names), 200):
        _req(base, keyv, BUCKET, json.dumps({"prefixes": names[i:i + 200]}).encode(), "DELETE", "application/json")


def evict(p, seen, today, keep_days=KEEP_DAYS, cap=CAP):
    """消す指紋のリスト。ページに載っていない＆最後に使ってから keep_days 超え → 先に。まだ上限超えなら古い順（載っていないものから）。"""
    gone = [k for k, v in p.items() if k not in seen and today - v["at"] > keep_days]
    left = {k: v for k, v in p.items() if k not in gone}
    over = sum(v["b"] for v in left.values()) - cap
    if over > 0:
        for k, v in sorted(left.items(), key=lambda kv: (kv[0] in seen, kv[1]["at"])):
            if over <= 0:
                break
            gone.append(k)
            over -= v["b"]
    return gone


def one(base, keyv, k, url):
    try:
        data = fetch(url)
        sizes = shrink(data) if data else None
        if not sizes:
            return k, None
        upload(base, keyv, k, sizes)
        return k, (sum(len(b) for b in sizes.values()), tint(sizes[WIDTHS[0]]), mass(sizes[WIDTHS[0]]) or [])
    except Exception:  # noqa: BLE001  取れない・壊れた画像・箱へ上げられない。次の日に取り直す
        return k, None


def run(minutes=10, base=None, keyv=None, site=None, path=None, workers=8):
    base = base or ""
    st = load(path)
    p, x = st["p"], st["x"]
    seen, want, total = scan(site, user_pages(base, keyv) if base and keyv else ())
    today = day()
    seen |= set(want) & set(p)   # 置いたが、まだ網页を作り直していない分
    for k in seen & set(p):
        p[k]["at"] = today
    todo = [(k, u) for k, u in want.items() if k not in p and today - x.get(k, -9) >= RETRY_DAYS]
    new = bad = 0
    if todo and base and keyv:
        end = time.time() + minutes * 60
        with ThreadPoolExecutor(workers) as ex:
            for i in range(0, len(todo), workers * 4):
                if time.time() > end:
                    break
                for k, n in ex.map(lambda t: one(base, keyv, *t), todo[i:i + workers * 4]):
                    if n:
                        p[k] = {"at": today, "b": n[0], "cc": 1, "c": n[1], "m": n[2]}
                        x.pop(k, None)
                        new += 1
                    else:
                        x[k] = today
                        bad += 1
    cc = 0
    old = [k for k, v in p.items() if not v.get("cc")]   # cc = 1 は CACHE 付きで上げ済み。ないものは上げ直す（時間の余りで・8 並列）
    if old and base and keyv:
        end = time.time() + minutes * 30
        with ThreadPoolExecutor(workers) as ex:
            for i in range(0, len(old), workers * 4):
                if time.time() > end:
                    break
                for k, ok in ex.map(lambda k: rehead(base, keyv, k), old[i:i + workers * 4]):
                    if ok:
                        p[k]["cc"] = 1
                        cc += 1
    nc = 0
    nocol = [k for k, v in p.items() if not v.get("c")]   # 色（下絵）のない分は置いてある 400 から取る
    if nocol and base:
        with ThreadPoolExecutor(workers) as ex:
            for k, c in ex.map(lambda k: tint_of(base, k), nocol[:2000]):
                if c:
                    p[k]["c"] = c
                    nc += 1
    nm = 0
    nomass = [k for k, v in p.items() if "m" not in v]   # 主役の分布のない分も置いてある 400 から測る（1 回 1500 枚まで）
    if nomass and base:
        with ThreadPoolExecutor(workers) as ex:
            for k, m in ex.map(lambda k: mass_of(base, k), nomass[:1500]):
                if m is not None:
                    p[k]["m"] = m
                    nm += 1
    for k in [k for k, d in x.items() if today - d > KEEP_DAYS]:
        del x[k]
    gone = evict(p, seen, today)
    if gone and base and keyv:
        remove(base, keyv, gone)
    for k in gone:
        p.pop(k, None)
    used = sum(v["b"] for v in p.values())
    hit = len(seen)
    stat = {"n": len(p), "bytes": used, "cap": CAP, "gone": len(gone), "new": new, "bad": bad, "pics": total, "hit": hit,
            "wait": max(0, len(todo) - new - bad), "day": today, "cc": cc, "cc_wait": sum(1 for v in p.values() if not v.get("cc")),
            "nc": nc, "tint": sum(1 for v in p.values() if v.get("c")), "nm": nm, "nm_wait": sum(1 for v in p.values() if "m" not in v), "mass": sum(1 for v in p.values() if v.get("m"))}
    out = {"base": base or st["base"], "p": p, "x": x, "stat": stat}
    (path or STATE).parent.mkdir(parents=True, exist_ok=True)
    (path or STATE).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return stat


def main(argv):
    if "--todo" in argv:   # 置いていない写真の数だけ出す（Supabase に触らない）
        print(todo_count())
        return
    if "--kick" in argv:   # render を発布する全部の workflow の最後の段（tests/test_photo_kick.py が数える）：1 枚でも置いていなければ一時保管を起こす
        n = todo_count()
        print(f"置いていない写真 {n} 枚")
        if n > 0:
            import subprocess
            subprocess.run(["gh", "workflow", "run", "photo_store.yml"], check=False)
        return
    import digest
    minutes = float(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else 10
    settings, _ = digest.load_config()
    base = (settings.get("supabase_url") or "").rstrip("/")
    keyv = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and keyv):
        raise SystemExit("supabase_url か SUPABASE_SERVICE_KEY がありません")
    s = run(minutes, base, keyv)
    print(f"写真の一時保管：{s['n']} 枚・{s['bytes'] // 1024 // 1024}MB（上限 {s['cap'] // 1024 // 1024}MB）／新しく {s['new']}・取れず {s['bad']}・消した {s['gone']}・順番待ち {s['wait']}・cache 付け直し {s['cc']}（残り {s['cc_wait']}）／主写真 {s['pics']} 枚のうち一時保管から {s['hit']}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if s['new'] or s['gone'] or s['cc'] or s['nc'] or s['nm'] else 'false'}\nmore={'true' if (s['wait'] and s['new']) or (s['cc_wait'] and s['cc']) or (s['nm_wait'] and s['nm']) else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
