"""点検のブラウザを開く共通の 1 か所（docs/rules/free-tier.md 決まり 1）。
Supabase の写真の配信が点検で 1 日 11 GB になった（枠は月 5 GB）ので、ここで開いたページは
*.supabase.co/storage/ を取りに行かない（state/photo_cache/ に写しがあればそれ、なければ灰色の画像）。
配信の時間そのものを測る点検だけ photos=True（環境変数 WL_ALLOW_PHOTOS=1 がないと開けない）。"""
import base64
import os
import re
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "state" / "photo_cache"
PATTERN = re.compile(r"https://[^/]+\.supabase\.co/storage/")
GRAY = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGNoaGgYFUQAANbVRbl3EF3BAAAAAElFTkSuQmCC")


# --- Python（urllib）からの読み込みも同じ止め（2026-11-02：ブラウザだけ止めても urlopen の点検が残っていた）---
_real_urlopen = urllib.request.urlopen
_allow = False


def _urlopen(req, *a, **k):
    u = req if isinstance(req, str) else req.full_url
    if PATTERN.match(u) and not _allow:
        raise RuntimeError("*.supabase.co/storage/ は browser.storage_bytes / storage_head で読む（写しを使う・free-tier.md）: " + u)
    return _real_urlopen(req, *a, **k)


if urllib.request.urlopen is _real_urlopen:   # import のたびに二重に包まない
    urllib.request.urlopen = _urlopen


def _name(url):
    return url.split("?")[0].rsplit("/", 1)[-1]


def storage_bytes(url, headers=None, timeout=30):
    """写真・小元素の中身。state/photo_cache/ に写しがあればそれ、なければ 1 回だけ落として写しを作る（同じ網址は 2 度と落とさない）。"""
    global _allow
    f = CACHE / _name(url)
    if f.is_file():
        return f.read_bytes()
    _allow = True
    try:
        data = _real_urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout).read()
    finally:
        _allow = False
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return data


_heads = {}


def storage_head(url, headers=None, timeout=30):
    """cache-control だけ見たいとき：Range で 1 バイトだけ。同じ網址は 1 回の点検で 1 回。"""
    global _allow
    if url not in _heads:
        _allow = True
        try:
            r = _real_urlopen(urllib.request.Request(url, headers={**(headers or {}), "Range": "bytes=0-0"}), timeout=timeout)
            r.read(1)
            _heads[url] = r.headers.get("cache-control", "")
        finally:
            _allow = False
    return _heads[url]


FILL_MAX = int(os.environ.get("WL_PHOTO_FILL_MAX", "300"))   # 写しが空のとき 1 つのプロセスが落とす上限（暴走止め）
_fills = 0


def _fulfill(route):
    """写しがあればそれ。なければ 1 回だけ落として写しを作る（同じ名前は 2 度と落とさない）。上限を超えたら灰色。
    写しを作らず灰色にすると naturalWidth・縦横比を測る点検が 8x8 の画像で狂う（pkcut・tiny・loose）。"""
    global _fills
    u = route.request.url
    f = CACHE / _name(u)
    if f.is_file():
        return route.fulfill(status=200, body=f.read_bytes(), headers={"content-type": "image/webp" if f.suffix == ".webp" else "image/png"})
    if _fills < FILL_MAX:
        try:
            r = route.fetch(timeout=30000)
            body = r.body()
            if r.ok and body:
                _fills += 1
                CACHE.mkdir(parents=True, exist_ok=True)
                tmp = f.with_name(f.name + ".part")
                tmp.write_bytes(body)
                tmp.replace(f)
                return route.fulfill(response=r, body=body)
        except Exception:  # noqa: BLE001  落とせなければ灰色
            pass
    return route.fulfill(status=200, body=GRAY, content_type="image/png")


def guard(target):
    """Page か BrowserContext に写真の配信止めを付ける"""
    target.route(PATTERN, _fulfill)
    return target


def launch(pw, photos=False, **kw):
    """pw.chromium.launch の代わり。new_page / new_context で作ったものに止めを自動で付ける"""
    if photos and os.environ.get("WL_ALLOW_PHOTOS") != "1":
        raise SystemExit("本番の写真を読み込む点検は WL_ALLOW_PHOTOS=1 のときだけ（free-tier.md）")
    kw.setdefault("channel", os.environ.get("UX_CHANNEL") or None)
    b = pw.chromium.launch(**kw)
    if photos:
        return b
    new_context, new_page = b.new_context, b.new_page

    def ctx(*a, **k):
        return guard(new_context(*a, **k))

    def page(*a, **k):
        c = ctx(*a, **k)
        p = c.new_page()
        return p

    b.new_context, b.new_page = ctx, page
    return b
