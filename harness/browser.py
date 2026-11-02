"""点検のブラウザを開く共通の 1 か所（docs/rules/free-tier.md 決まり 1）。
Supabase の写真の配信が点検で 1 日 11 GB になった（枠は月 5 GB）ので、ここで開いたページは
*.supabase.co/storage/ を取りに行かない（state/photo_cache/ に写しがあればそれ、なければ灰色の画像）。
配信の時間そのものを測る点検だけ photos=True（環境変数 WL_ALLOW_PHOTOS=1 がないと開けない）。"""
import base64
import os
import re
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "state" / "photo_cache"
PATTERN = re.compile(r"https://[^/]+\.supabase\.co/storage/")
GRAY = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGNoaGgYFUQAANbVRbl3EF3BAAAAAElFTkSuQmCC")


def _fulfill(route):
    u = route.request.url
    f = CACHE / u.split("?")[0].rsplit("/", 1)[-1]
    if f.is_file():
        return route.fulfill(status=200, body=f.read_bytes(), headers={"content-type": "image/webp" if f.suffix == ".webp" else "image/png"})
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
