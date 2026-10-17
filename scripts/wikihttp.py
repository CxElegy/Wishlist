"""Wikimedia（Wikipedia・Wikidata・Commons・upload.wikimedia.org）を、向こうの決まりどおりに叩く。

決まり（https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy 、
https://www.mediawiki.org/wiki/API:Etiquette 、https://www.mediawiki.org/wiki/Manual:Maxlag_parameter ）：
- User-Agent は「ツール名/版 (連絡先) ライブラリ/版」。ブラウザのふり（Mozilla/…）や汎用の UA は 403 で止められる
- 同じサイトには 1 本ずつ（並列にしない）。読む API は api.php に maxlag=5 を付け、混んでいたら Retry-After だけ待つ
- 429 / 503 は Retry-After を守って取り直す。同じものは取り直さずキャッシュを使う
キャッシュは requests-cache（SQLite、~/.cache/wishlist-http、Actions では actions/cache で次の回へ持ち越す）。
"""
import os
import pathlib
import threading
import time
import urllib.error
import urllib.parse
from datetime import timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sources import TIMEOUT

BOT_UA = (f"WishlistEmblemBot/1.1 (https://github.com/CxElegy/Wishlist; https://github.com/CxElegy/Wishlist/issues) "
          f"python-requests/{requests.__version__}")
HOSTS = ("wikipedia.org", "wikimedia.org", "wikidata.org")
CACHE = pathlib.Path(os.environ.get("WISHLIST_HTTP_CACHE") or pathlib.Path.home() / ".cache" / "wishlist-http")
EXPIRE = {   # 網址の形 → キャッシュの持ち時間（記事・Wikidata は時々変わる、画像はほぼ変わらない）
    "*/w/api.php*": timedelta(days=3),
    "upload.wikimedia.org/*": timedelta(days=14),
    "*/wiki/Special:FilePath/*": timedelta(days=14),
}
MAXLAG = 5       # 秒。サーバーの複製の遅れがこれより大きいと「maxlag」で断られる（Retry-After だけ待つ）
GAP = 1.3        # 同じホストへは前の応答から 1.3 秒あける（並列のスレッドでも 1 本ずつ）
ALL_GAP = 0.4    # Wikimedia 全体でも 0.4 秒に 1 回まで（= 毎分 150。UA を守ったボットの上限は全サイト合わせて毎分 200：
                 # https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits 。守らない UA は毎分 10）
WAITS = (5, 15, 45)   # 429 / 503 / maxlag で Retry-After がないときの待ち（3 回まで取り直す）
MAX_WAIT = 120   # Retry-After がこれより長い → 待たずにそのホストを休ませる
COOL = 300       # 取り直しても 429 → そのホストは 5 分休む（その間はすぐ失敗にして次の取り方へ）

_locks = {}
_locks_lock = threading.Lock()
_last = {}       # ホスト → 前の応答が終わった時刻
_all = [0.0]     # Wikimedia 全体で次に出してよい時刻
_cool = {}       # ホスト → この時刻までは叩かない
_session = [None]
sleep = time.sleep   # テストで差し替える


def is_wikimedia(url):
    host = urllib.parse.urlparse(url).netloc
    return any(host == h or host.endswith("." + h) for h in HOSTS)


def _cacheable(resp):
    """maxlag で断られた応答（200 で返る）は残さない。"""
    return resp.status_code == 200 and "Retry-After" not in resp.headers and b'"maxlag"' not in resp.content[:300]


def session():
    if _session[0] is None:
        try:
            import requests_cache
            CACHE.mkdir(parents=True, exist_ok=True)
            s = requests_cache.CachedSession(str(CACHE / "wikimedia"), backend="sqlite", expire_after=timedelta(days=3),
                                             urls_expire_after=EXPIRE, allowable_codes=(200,), filter_fn=_cacheable,
                                             stale_if_error=True)
            s.cache.delete(expired=True)
        except ImportError:   # requests-cache が入っていない手元でも動く（キャッシュなし）
            s = requests.Session()
        s.headers.update({"User-Agent": BOT_UA, "Api-User-Agent": BOT_UA, "Accept-Encoding": "gzip"})
        # 接続が切れた・タイムアウトだけ urllib3 に取り直させる（429 / 503 は下で Retry-After を見て待つ）
        s.mount("https://", HTTPAdapter(max_retries=Retry(total=2, connect=2, read=2, status=0, backoff_factor=2,
                                                                       respect_retry_after_header=False, raise_on_status=False)))
        _session[0] = s
    return _session[0]


def with_maxlag(url):
    p = urllib.parse.urlsplit(url)
    if not p.path.endswith("/api.php") or "maxlag=" in p.query:
        return url
    return urllib.parse.urlunsplit(p._replace(query=(p.query + "&" if p.query else "") + f"maxlag={MAXLAG}"))


def _lock(host):
    with _locks_lock:
        return _locks.setdefault(host, threading.Lock())


def _retry_after(resp):
    try:
        return max(0.0, float(resp.headers.get("Retry-After", "")))
    except ValueError:
        return None


def _error(url, resp, lag=False):
    code = 503 if lag else resp.status_code   # maxlag は 200 で返るが「混んでいる」なので 503 扱い
    return urllib.error.HTTPError(url, code, "maxlag" if lag else (resp.reason or ""), resp.headers, None)


def get(url, limit=6_000_000):
    """→ 中身（bytes）。失敗は urllib.error.HTTPError（code 429 / 403 など）で、今までの _get と同じように扱える。"""
    url = with_maxlag(url)
    host = urllib.parse.urlparse(url).netloc
    s = session()
    if hasattr(s, "cache"):   # キャッシュにあれば待たない・数えない
        hit = s.get(url, only_if_cached=True, timeout=TIMEOUT)
        if hit.status_code == 200:
            return _body(url, hit, limit)
    if _cool.get(host, 0) > time.time():
        raise urllib.error.HTTPError(url, 429, "休ませ中（429 が続いた）", None, None)
    with _lock(host):   # 同じホストへは 1 本ずつ（待っている間はほかのスレッドも待つ = サイトから見て間隔が守られる）
        for n in range(len(WAITS) + 1):
            gap = _last.get(host, 0) + GAP - time.time()
            if gap > 0:
                sleep(gap)
            with _locks_lock:   # ほかのホストのスレッドとも順番を予約する
                slot = max(time.time(), _all[0])
                _all[0] = slot + ALL_GAP
            if slot > time.time():
                sleep(slot - time.time())
            try:
                resp = s.get(url, timeout=TIMEOUT)
            finally:
                _last[host] = time.time()
            lag = resp.status_code == 200 and b'"maxlag"' in resp.content[:300]
            if resp.status_code == 200 and not lag:
                return _body(url, resp, limit)
            if resp.status_code not in (429, 503) and not lag:
                raise _error(url, resp)
            wait = _retry_after(resp)
            wait = WAITS[min(n, len(WAITS) - 1)] if wait is None else wait
            if n == len(WAITS) or wait > MAX_WAIT:
                if resp.status_code == 429 or wait > MAX_WAIT:
                    _cool[host] = time.time() + max(COOL, wait)
                raise _error(url, resp, lag)
            sleep(wait)


def _body(url, resp, limit):
    data = resp.content
    if len(data) > limit:
        raise ValueError("画像が大きすぎる")
    return data
