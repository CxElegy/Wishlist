"""写真の一時保管（2026-10-31，用户定的：記事の写真を先にサーバーへ置き、読み込みを速くする。溜めない）。

網页の記事の主写真は、よそのサイトの原寸へ直リンクだった（重い・遅い・防盗链で落ちる）。この係が
  1. docs/home/*.html の主写真（data-e="s"）の網址を数え、
  2. まだ置いていないものを Referer なしで取って、幅 400／800 の webp に縮め、
  3. Supabase Storage の公開の箱 photos（db/photos.sql）へ上げる。
render.py の _pic は置いてあるものなら 800 の網址を先頭にし、原寸の網址は落ち先（data-fb）に残す。
置く数は state/photo_store.json（キーは網址の指紋）。保つのは「いまのページに載っている」か「最後に使ってから 14 日以内」まで、
全体が上限（300MB）を超えたら古い順に消す。消すのは photos の箱の中だけ。

    python scripts/photo_store.py [--minutes 10]     # photo_store.yml（SUPABASE_SERVICE_KEY）
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
IMG_RE = re.compile(r'<img src="([^"]*)"([^>]*?)data-e="s">')


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


def stored(url):
    """render 用：置いてある写真なら一時保管の 800 の網址、なければ None。"""
    if not _CACHE:
        _CACHE.append(load())
    st = _CACHE[0]
    k = key(url)
    return public(st["base"], k) if st["base"] and k in st["p"] else None


def pages(site=None):
    return sorted((site or sitedir.SITE_DIR).glob("*.html"))


def scan(site=None):
    """公開ページの主写真を数える。→ (載っている指紋の集合, {指紋: 原寸の網址}（まだ置いていないもの）, 主写真の枚数)。"""
    seen, want, total = set(), {}, 0
    pre = f"/storage/v1/object/public/{BUCKET}/"
    for f in pages(site):
        for src, _ in IMG_RE.findall(f.read_text(encoding="utf-8")):
            src = html.unescape(src)
            total += 1
            if pre in src:
                seen.add(src.rsplit("/", 1)[-1].split("-")[0])
            elif src.startswith("http"):
                want[key(src)] = src
    return seen, want, total


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


def upload(base, keyv, k, sizes):
    for w, b in sizes.items():
        _req(base, keyv, f"{BUCKET}/{name(k, w)}", b, extra={"x-upsert": "true", "Cache-Control": "max-age=1209600"})


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
        return k, sum(len(b) for b in sizes.values())
    except Exception:  # noqa: BLE001  取れない・壊れた画像・箱へ上げられない。次の日に取り直す
        return k, None


def run(minutes=10, base=None, keyv=None, site=None, path=None, workers=8):
    base = base or ""
    st = load(path)
    p, x = st["p"], st["x"]
    seen, want, total = scan(site)
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
                        p[k] = {"at": today, "b": n}
                        x.pop(k, None)
                        new += 1
                    else:
                        x[k] = today
                        bad += 1
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
            "wait": max(0, len(todo) - new - bad), "day": today}
    out = {"base": base or st["base"], "p": p, "x": x, "stat": stat}
    (path or STATE).parent.mkdir(parents=True, exist_ok=True)
    (path or STATE).write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return stat


def main(argv):
    import digest
    minutes = float(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else 10
    settings, _ = digest.load_config()
    base = (settings.get("supabase_url") or "").rstrip("/")
    keyv = os.environ.get("SUPABASE_SERVICE_KEY")
    if not (base and keyv):
        raise SystemExit("supabase_url か SUPABASE_SERVICE_KEY がありません")
    s = run(minutes, base, keyv)
    print(f"写真の一時保管：{s['n']} 枚・{s['bytes'] // 1024 // 1024}MB（上限 {s['cap'] // 1024 // 1024}MB）／新しく {s['new']}・取れず {s['bad']}・消した {s['gone']}・順番待ち {s['wait']}／主写真 {s['pics']} 枚のうち一時保管から {s['hit']}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if s['new'] or s['gone'] else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
