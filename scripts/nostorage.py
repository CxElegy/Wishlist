"""Python が Supabase の公開の箱（photos・emblems・media）を落とさない止め（2026-11-04 egress 緊急）。
使う網の道（urllib・http.client・requests/urllib3・curl_cffi）の「要求を出す所」を 1 か所で包み、
*.supabase.co/storage/v1/(object|render/image)/public/ への要求は RuntimeError にする。写真の中身は写し
（WL_PHOTO_CACHE、埋めるのは photo_cache.yml の harness/photo_cache_fill.py だけ）から読む（sbstate.storage_read）。
外すのは allowed()（browser.storage_bytes(fill=True) だけが使う）。アップロード（POST /object/<箱>/）と本人のページ（/object/pages/…）は止めない。
網を使う scripts/*.py・harness/*.py は、これを（直接か、import 先を辿って）読み込む。tests/test_browser_guard が数える。"""
import contextlib
import http.client
import importlib.util
import re

PATTERN = re.compile(r"https://[^/]+\.supabase\.co/storage/v1/(?:object|render/image)/public/")
_state = {"allow": 0}


def refuse(url):
    if not _state["allow"] and PATTERN.match(url):
        raise RuntimeError("*.supabase.co/storage/ は sbstate.storage_read で読む（写しから・free-tier.md）: " + url)


@contextlib.contextmanager
def allowed():
    _state["allow"] += 1
    try:
        yield
    finally:
        _state["allow"] -= 1


def _full(host, url, scheme="https"):
    return url if url.startswith("http") else f"{scheme}://{host}{url}"


def install():
    if getattr(http.client.HTTPConnection.putrequest, "_wl_guard", False):
        return
    put = http.client.HTTPConnection.putrequest

    def putrequest(self, method, url, *a, **k):   # urllib・http.client・requests は最後にここを通る
        refuse(_full(getattr(self, "_tunnel_host", None) or self.host, url))
        return put(self, method, url, *a, **k)

    putrequest._wl_guard = True
    http.client.HTTPConnection.putrequest = putrequest
    if importlib.util.find_spec("urllib3"):   # requests は接続の前に止める（接続が先に走るため）
        from urllib3.connectionpool import HTTPConnectionPool
        up = HTTPConnectionPool.urlopen

        def urlopen(self, method, url, *a, **k):
            refuse(_full(self.host, url, self.scheme))
            return up(self, method, url, *a, **k)

        HTTPConnectionPool.urlopen = urlopen
    if importlib.util.find_spec("curl_cffi"):   # scrapling の Fetcher・images.py の取得
        from curl_cffi.requests import Session
        sr = Session.request

        def request(self, method, url, *a, **k):
            refuse(url)
            return sr(self, method, url, *a, **k)

        Session.request = request


install()
