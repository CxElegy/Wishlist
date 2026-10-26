"""Wikimedia の取り方（scripts/wikihttp.py）：UA・1 本ずつ・maxlag・Retry-After・休み・キャッシュ。ネットワークには出ない。

    python -m unittest tests.test_wikihttp
"""

import io
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

import requests
import urllib3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem  # noqa: E402
import wikihttp  # noqa: E402


def _resp(code=200, body=b"{}", headers=None):
    r = requests.Response()
    r.status_code = code
    r._content = body
    r.headers.update(headers or {})
    r.reason = {200: "OK", 403: "Forbidden", 429: "Too Many Requests", 503: "Service Unavailable"}.get(code, "")
    return r


class FakeSession:
    """決まった順に応答を返す。User-Agent と網址を記録する（Wikimedia が 403 / 429 を返す場面の再現）。"""
    def __init__(self, replies, ua=wikihttp.BOT_UA):
        self.replies = list(replies)
        self.headers = {"User-Agent": ua}
        self.calls = []
        self.lock = threading.Lock()

    def get(self, url, timeout=None, **kw):
        with self.lock:
            self.calls.append((time.time(), url))
            self.auth = getattr(self, "auth", []) + [(kw.get("headers") or {}).get("Authorization")]
            if self.headers["User-Agent"].startswith("Mozilla/"):   # ブラウザのふりの UA は 403（実際にあった）
                return _resp(403, b"Please set a user-agent and respect our robot policy")
            r = self.replies.pop(0) if self.replies else _resp()
            return r() if callable(r) else r


class WikiHttpTest(unittest.TestCase):
    def setUp(self):
        self.waits = []
        self._sleep = wikihttp.sleep
        wikihttp.sleep = self.waits.append
        self._sess = wikihttp._session[0]
        wikihttp._cool.clear()
        wikihttp._last.clear()
        wikihttp._all[0] = 0.0
        self._token = wikihttp._token[0]
        wikihttp._token[0] = ""

    def tearDown(self):
        wikihttp._token[0] = self._token
        wikihttp.sleep = self._sleep
        wikihttp._session[0] = self._sess
        wikihttp._cool.clear()
        wikihttp._last.clear()
        wikihttp._all[0] = 0.0

    def use(self, *replies, ua=wikihttp.BOT_UA):
        s = FakeSession(replies, ua)
        wikihttp._session[0] = s
        return s

    def test_user_agent_follows_policy(self):
        ua = wikihttp.BOT_UA
        self.assertFalse(ua.startswith("Mozilla"))
        self.assertRegex(ua, r"^\w*Bot/\d+\.\d+ \(https://github\.com/CxElegy/Wishlist; [^)]+\) python-requests/")
        self.assertNotIn("@", ua)   # 連絡先は repo の Issues（メールは出さない）

    def test_browser_like_ua_was_the_403(self):
        self.use(ua="Mozilla/5.0 (wishlist-digest; +https://github.com/CxElegy/Wishlist)")
        with self.assertRaises(urllib.error.HTTPError) as e:
            wikihttp.get("https://en.wikipedia.org/w/api.php?action=query")
        self.assertEqual(e.exception.code, 403)
        s = self.use()
        self.assertEqual(wikihttp.get("https://en.wikipedia.org/w/api.php?action=query"), b"{}")
        self.assertEqual(len(s.calls), 1)

    def test_only_wikimedia_hosts(self):
        for u in ("https://en.wikipedia.org/w/api.php", "https://www.wikidata.org/w/api.php",
                  "https://commons.wikimedia.org/wiki/Special:FilePath/A.png", "https://upload.wikimedia.org/wikipedia/commons/a/ab/A.jpg"):
            self.assertTrue(wikihttp.is_wikimedia(u), u)
        for u in ("https://genshin-impact.fandom.com/api.php", "https://notwikipedia.org/x", "https://example.com/?u=wikipedia.org"):
            self.assertFalse(wikihttp.is_wikimedia(u), u)

    def test_fandom_api_one_at_a_time_no_token_no_maxlag(self):
        wikihttp._token[0] = "SECRET"
        s = self.use(_resp(429, headers={"Retry-After": "3"}), _resp(200, b'{"f":1}'))
        u = "https://bleach.fandom.com/api.php?action=query"
        self.assertTrue(wikihttp.is_fandom(u))
        self.assertFalse(wikihttp.is_fandom("https://static.wikia.nocookie.net/x.png"))
        self.assertEqual(emblem._get(u), b'{"f":1}')
        self.assertEqual([c[1] for c in s.calls], [u, u])   # maxlag を付けない
        self.assertEqual(s.auth, [None, None])   # トークンは Wikimedia だけ
        self.assertIn(3.0, self.waits)   # Retry-After を守った

    def test_maxlag_added_to_api_only(self):
        self.assertEqual(wikihttp.with_maxlag("https://en.wikipedia.org/w/api.php?action=query"),
                         "https://en.wikipedia.org/w/api.php?action=query&maxlag=5")
        self.assertEqual(wikihttp.with_maxlag("https://en.wikipedia.org/w/api.php?maxlag=3"), "https://en.wikipedia.org/w/api.php?maxlag=3")
        u = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/A.jpg/500px-A.jpg"
        self.assertEqual(wikihttp.with_maxlag(u), u)
        w = "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=x"   # WDQS の遅れまで数えるので付けない
        self.assertEqual(wikihttp.with_maxlag(w), w)

    def test_429_waits_retry_after_then_200(self):
        s = self.use(_resp(429, headers={"Retry-After": "7"}), _resp(200, b'{"ok":1}'))
        self.assertEqual(wikihttp.get("https://en.wikipedia.org/w/api.php?action=query"), b'{"ok":1}')
        self.assertEqual(len(s.calls), 2)
        self.assertIn(7.0, self.waits)   # Retry-After のとおり待った

    def test_maxlag_error_is_retried(self):
        lag = _resp(200, b'{"error":{"code":"maxlag","info":"Waiting for 10.64.0.1: 6 seconds lagged"}}', {"Retry-After": "5"})
        s = self.use(lag, _resp(200, b'{"query":{}}'))
        self.assertEqual(wikihttp.get("https://commons.wikimedia.org/w/api.php?action=query&titles=File:A.jpg"), b'{"query":{}}')
        self.assertEqual(len(s.calls), 2)
        self.assertIn(5.0, self.waits)
        self.assertFalse(wikihttp._cacheable(lag))   # 断られた応答はキャッシュに残さない

    def test_429_persisting_cools_host(self):
        s = self.use(*[_resp(429) for _ in range(4)])
        with self.assertRaises(urllib.error.HTTPError) as e:
            wikihttp.get("https://commons.wikimedia.org/w/api.php?action=query")
        self.assertEqual(e.exception.code, 429)
        self.assertEqual(len(s.calls), 4)
        self.assertEqual([w for w in self.waits if w >= 5], list(wikihttp.WAITS))
        with self.assertRaises(urllib.error.HTTPError):   # 休み中はサイトに出ずにすぐ失敗
            wikihttp.get("https://commons.wikimedia.org/w/api.php?action=query&x=2")
        self.assertEqual(len(s.calls), 4)

    def test_long_retry_after_does_not_block(self):
        s = self.use(_resp(429, headers={"Retry-After": "900"}))
        with self.assertRaises(urllib.error.HTTPError):
            wikihttp.get("https://en.wikipedia.org/w/api.php?action=query")
        self.assertEqual(len(s.calls), 1)
        self.assertGreater(wikihttp._cool["en.wikipedia.org"], time.time() + 800)

    def test_one_request_at_a_time_per_host(self):
        wikihttp.sleep = time.sleep
        live, peak = [0], [0]

        def slow():
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            time.sleep(0.05)
            live[0] -= 1
            return _resp()
        s = self.use(*[slow] * 3)
        gap = wikihttp.GAP
        wikihttp.GAP = 0.2
        try:
            ts = [threading.Thread(target=wikihttp.get, args=(f"https://xx.wikipedia.org/w/api.php?n={i}",)) for i in range(3)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        finally:
            wikihttp.GAP = gap
        self.assertEqual(peak[0], 1)   # 6 本並列でも同じホストには 1 本ずつ
        t = sorted(c[0] for c in s.calls)
        self.assertGreaterEqual(t[2] - t[0], 0.4 + 0.05)

    def test_all_wikimedia_hosts_share_a_budget(self):
        self.use()
        wikihttp.get("https://en.wikipedia.org/w/api.php?a=1")
        wikihttp.get("https://www.wikidata.org/w/api.php?a=1")   # 別のホストでも毎分 200 の枠は共通
        self.assertTrue(any(0.3 < w <= wikihttp.ALL_GAP for w in self.waits), self.waits)

    def test_token_is_sent_to_apis_not_images(self):
        """共有 IP の 429 を避ける：WIKIMEDIA_TOKEN があれば API には Bearer を付ける（上限がアカウントごとになる）。"""
        wikihttp._token[0] = "tok123"
        s = self.use()
        wikihttp.get("https://www.wikidata.org/w/api.php?action=wbsearchentities&search=x")
        wikihttp.get("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/A.jpg/500px-A.jpg")
        self.assertEqual(s.auth, ["Bearer tok123", None])

    def test_rejected_token_is_dropped(self):
        wikihttp._token[0] = "bad"
        s = self.use(_resp(401, b'{"error":{"code":"mwoauth-invalid-authorization"}}'), _resp(200, b'{"ok":1}'))
        self.assertEqual(wikihttp.get("https://en.wikipedia.org/w/api.php?action=query"), b'{"ok":1}')
        self.assertEqual(s.auth, ["Bearer bad", None])
        self.assertEqual(wikihttp.token(), "")   # 以後は付けない

    def test_no_token_no_header(self):
        s = self.use()
        wikihttp.get("https://en.wikipedia.org/w/api.php?action=query")
        self.assertEqual(s.auth, [None])

    def test_emblem_get_routes_wikimedia(self):
        s = self.use(_resp(200, b"img"))
        self.assertEqual(emblem._get("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/A.jpg/500px-A.jpg"), b"img")
        self.assertEqual(len(s.calls), 1)

    def test_disk_cache_skips_network(self):
        try:
            import requests_cache  # noqa: F401
        except ImportError:
            self.skipTest("requests-cache なし")
        cache = wikihttp.CACHE
        with tempfile.TemporaryDirectory() as d:
            wikihttp.CACHE = pathlib.Path(d)
            wikihttp._session[0] = None
            try:
                s = wikihttp.session()
                sent = []

                adapter = s.get_adapter("https://")

                def send(req, **kw):   # urllib3 の応答を作って requests に渡す（ネットには出ない）
                    sent.append(req.headers["User-Agent"])
                    raw = urllib3.HTTPResponse(body=io.BytesIO(b'{"a":1}'), headers={"Content-Type": "application/json"},
                                               status=200, preload_content=False, request_url=req.url)
                    return adapter.build_response(req, raw)
                adapter.send = send
                u = "https://en.wikipedia.org/w/api.php?action=query&titles=A"
                self.assertEqual(wikihttp.get(u), b'{"a":1}')
                self.assertEqual(wikihttp.get(u), b'{"a":1}')
                self.assertEqual(len(sent), 1)   # 2 回目はディスクのキャッシュ
                self.assertEqual(sent[0], wikihttp.BOT_UA)
                self.assertTrue((pathlib.Path(d) / "wikimedia.sqlite").exists())
            finally:
                wikihttp.CACHE = cache
                wikihttp._session[0] = None


if __name__ == "__main__":
    unittest.main()
