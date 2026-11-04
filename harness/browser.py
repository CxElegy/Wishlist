"""点検のブラウザを開く共通の 1 か所（docs/rules/free-tier.md 決まり 1）。
Supabase の写真の配信が点検で 1 日 11 GB になった（枠は月 5 GB）ので、ここで開いたページは
*.supabase.co/storage/ を取りに行かない（state/photo_cache/ に写しがあればそれ、なければ灰色の画像）。
配信の時間そのものを測る点検だけ photos=True（環境変数 WL_ALLOW_PHOTOS=1 がないと開けない）。"""
import base64
import os
import re
import sys
import urllib.request

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import nostorage   # noqa: E402  網の道ぜんぶの止め（fill のときだけ allowed()）

# 写しは作業ツリーの外の共通の場所（係・実行同士で共有。作業ツリーは毎回まっさらで、中に置くと毎回落とし直す）。上書き：WL_PHOTO_CACHE
CACHE = Path(os.environ.get("WL_PHOTO_CACHE") or Path.home() / ".cache" / "wl_photo_cache")
# 止めるのは公開の箱（photos・emblems・media）だけ。本人のページ（pages 箱の /object/pages/…。ログインして download する）は止めない：
# 止めると test-a〜c が灰色の画像を HTML として受け取り「素の箱」になり、ログイン後の点検が全部 ✗ になった（2026-11-03）
PATTERN = re.compile(r"https://[^/]+\.supabase\.co/storage/v1/(?:object|render/image)/public/")
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


def storage_bytes(url, headers=None, timeout=30, fill=False):
    """写真・小元素の中身。写しがあればそれ。無ければ None（点検は本番から落とさない）。
    落として写しを作るのは fill=True で呼ぶ harness/photo_cache_fill.py だけ（tests/test_browser_guard.py が数える）。"""
    global _allow
    f = CACHE / _name(url)
    if f.is_file():
        return f.read_bytes()
    if not fill:
        return None
    _allow = True
    try:
        with nostorage.allowed():
            data = _real_urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout).read()
    finally:
        _allow = False
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return data


_heads = {}


def storage_head(url, headers=None, timeout=30, fill=False):
    """cache-control だけ見たいとき：Range で 1 バイトだけ。同じ網址は 1 回の点検で 1 回。
    本番へ出るので fill=True のときだけ（既定は None＝測らない）。"""
    global _allow
    if url not in _heads:
        if not fill:
            return None
        _allow = True
        try:
            r = _real_urlopen(urllib.request.Request(url, headers={**(headers or {}), "Range": "bytes=0-0"}), timeout=timeout)
            r.read(1)
            _heads[url] = r.headers.get("cache-control", "")
        finally:
            _allow = False
    return _heads[url]


# 既定 0＝点検は本番から落とさない（写しが無ければ灰色）。写しを埋めるのは毎日 1 回の photo_cache.yml（harness/photo_cache_fill.py）だけ。
# 8x8 の灰色で測りが狂う点検だけ WL_PHOTO_FILL_MAX を明示する。
FILL_MAX = int(os.environ.get("WL_PHOTO_FILL_MAX", "0"))
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


# --- ブラウザからの Supabase（rest・rpc・auth・functions）。2026-11-04 egress：読みは 10 分の写しから返す ---
SB = re.compile(r"https://[^/]+\.supabase\.co/(?:rest/v1|auth/v1|functions/v1)/")
# 読むだけの rpc（名前で決める。ここに無い rpc は書き込みかもしれないので必ず本番へ通す）
READ_RPC = {"my_page", "my_page_path", "my_votes", "my_votes_own", "my_role", "my_boards", "live_boards", "live_log_since", "edit_control_get",
            "get_sizes", "get_nav_schemes", "can_edit", "auth_enforced", "instant_enabled", "name_available", "list_item_requests", "get_photo_inbox",
            "userfeed_users", "admin_votes", "admin_users", "admin_accounts", "admin_follow_rows", "admin_follow_detail", "admin_ui_langs",
            "admin_account_langs", "admin_list_invites", "admin_board_edit_state"}
SB_CACHE = Path(os.environ.get("WL_SB_BROWSER_CACHE") or Path.home() / ".cache" / "wl_sb_browser")


def sb_mode():
    """cache（既定）＝読みは写し／abort＝全部止める（Supabase が止まった時の見え方を見る・本番に 0 件）／live＝全部本番（直した直後の比べ用）"""
    return os.environ.get("WL_SB_BROWSER", "cache")


def cacheable(req):
    if req.method in ("GET", "HEAD"):
        return "/rest/v1/" in req.url
    m = re.search(r"/rest/v1/rpc/([a-z_0-9]+)", req.url)
    return bool(m and req.method == "POST" and m.group(1) in READ_RPC)


def _sb_route(route):
    import hashlib
    import json
    import time
    sbread = __import__("sbread")
    req, mode = route.request, sb_mode()
    if mode == "abort":
        sbread.browser_hit(req.url, "abort")
        return route.abort()
    if mode == "live" or not cacheable(req):
        sbread.browser_hit(req.url)
        return route.continue_()
    h = req.headers
    k = hashlib.sha256(f"{req.method}\n{req.url}\n{req.post_data}\n{sbread.ident(h.get('authorization') or h.get('apikey') or '-')}".encode()).hexdigest()[:40]
    f = SB_CACHE / (k + ".json")
    try:
        if time.time() - f.stat().st_mtime < sbread.BR_TTL:
            d = json.loads(f.read_text(encoding="utf-8"))
            sbread.browser_hit(req.url, "cache")
            return route.fulfill(status=d["s"], body=d["b"], headers=d["h"])
    except (OSError, ValueError, KeyError):
        pass
    sbread.browser_hit(req.url)
    r = route.fetch(timeout=30000)
    body = r.body()
    if r.ok:
        keep = {a: b for a, b in r.headers.items() if a in ("content-type", "content-range")}
        try:
            SB_CACHE.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"s": r.status, "b": body.decode("utf-8"), "h": keep}), encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return route.fulfill(response=r, body=body)


def guard(target):
    """Page か BrowserContext に写真の配信止めと Supabase の読みの写しを付ける（ux_check の最後に件数が出る）"""
    target.route(PATTERN, _fulfill)
    target.route(SB, _sb_route)
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
