"""点検の道具が本番の Supabase を読む入口は harness/sbread.py だけ（2026-11-04・egress）。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import sbread  # noqa: E402

OK = {"sbread.py", "sb_down_check.py", "browser.py"}   # sb_down_check は abort する先の見本の網址。browser.py はブラウザの読みの写し（BrowserRoute の tests が数える）


class SbRead(unittest.TestCase):
    def test_no_direct_rest_reads(self):
        """/rest/v1/（rpc 以外）の文字を持つ行は sbread.get を呼ぶ行か、網址の定数の行だけ。定数の網址は同じファイルで sbread.get に渡す。
        urllib・requests・page.request で /rest/v1/ を組み立てて読む道（複数行・変数）も、ファイルごとに「rest/v1 を含むのに sbread を使わない」で拾う。"""
        for f in (ROOT / "harness").glob("*.py"):
            t = f.read_text(encoding="utf-8")
            if f.name in OK or not re.search(r"rest/v1/(?!rpc)", t):
                continue
            self.assertIn("sbread.get(", t, f"{f.name}: /rest/v1/ を読むのに sbread.get を通していない")
            for m in re.finditer(r"(urlopen|requests\.(get|post)|\.request\.(get|fetch))\(", t):
                self.assertNotRegex(t[max(0, m.start() - 300):m.end() + 300], r"rest/v1/(?!rpc)", f"{f.name}: /rest/v1/ の近くで {m.group(0)} を直接呼んでいる")

    def test_second_read_is_cached(self):
        class R:
            headers = {"Content-Range": "0-1/2"}
            def read(self): return b'[{"id":1}]'
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sbread, "DIR", Path(d)), \
                mock.patch("urllib.request.urlopen", return_value=R()) as u:
            sbread._n.update(net=0, hit=0, bytes=0)
            a = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact", ttl=600)
            b = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact", ttl=600)
            c = sbread.get("https://x/rest/v1/boards?select=id", "k", "other", ttl=600)   # 別の人の鍵は別の写し
            self.assertEqual(a, b)
            self.assertEqual(json.loads(a[0]), [{"id": 1}])
            self.assertEqual(a[1], "0-1/2")
            self.assertEqual((u.call_count, sbread.stats()["hit"]), (2, 1))


    def test_default_is_cached_and_ttl0_is_fresh(self):
        """ttl を渡さない読みは写し（2026-11-04 既定を逆に）。ttl=0 だけ毎回本番。ログインのたびにトークンが変わっても同じ人は同じ写し。"""
        import base64
        class R:
            headers = {}
            def read(self): return b"[]"
        def jwt(sub, n):
            b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
            return b({"alg": "x"}) + "." + b({"sub": sub, "n": n}) + ".sig"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sbread, "DIR", Path(d)), \
                mock.patch("urllib.request.urlopen", return_value=R()) as u:
            sbread.get("https://x/rest/v1/a", "k", jwt("u1", 1)); sbread.get("https://x/rest/v1/a", "k", jwt("u1", 2))
            self.assertEqual(u.call_count, 1)
            sbread.get("https://x/rest/v1/a", "k", jwt("u2", 1))
            self.assertEqual(u.call_count, 2)
            sbread.get("https://x/rest/v1/a", "k", jwt("u1", 3), ttl=0)
            self.assertEqual(u.call_count, 3)

    def test_default_ttl_not_zero(self):
        self.assertGreater(sbread.TTL, 0)

    def test_every_get_in_ux_check_uses_default_ttl(self):
        """ux_check の sbread.get は ttl=0 を渡さない（毎回本番へ出る道を作らない）。ttl=0 の名簿は photo_cache_fill だけ。"""
        for f in (ROOT / "harness").glob("*.py"):
            if f.name != "photo_cache_fill.py" and f.name != "sbread.py":
                self.assertNotRegex(f.read_text(encoding="utf-8"), r"sbread\.get\([^\n]*ttl=0", f.name)

    def test_boards_read_is_narrowed(self):
        """版面の設定丸ごと（config）を読まない。必要な箱だけ。"""
        t = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertNotRegex(t, r"select=[^\"]*\bconfig[,\"]")


class BrowserRoute(unittest.TestCase):
    def _route(self, method, url, post=None, auth="Bearer k"):
        req = mock.Mock(method=method, url=url, post_data=post, headers={"authorization": auth})
        return mock.Mock(request=req)

    def test_cache_hit_does_not_reach_network(self):
        import browser
        r = mock.Mock(ok=True, status=200, headers={"content-type": "application/json"})
        r.body.return_value = b"[1]"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(browser, "SB_CACHE", Path(d)), mock.patch.dict("os.environ", {"WL_SB_BROWSER": "cache"}):
            sbread._n.update(br=0, brc=0, bra=0)
            a = self._route("POST", "https://x.supabase.co/rest/v1/rpc/my_page", "{}")
            a.fetch.return_value = r
            browser._sb_route(a)
            b = self._route("POST", "https://x.supabase.co/rest/v1/rpc/my_page", "{}")
            browser._sb_route(b)
            b.fetch.assert_not_called()
            self.assertEqual(b.fulfill.call_args.kwargs["body"], "[1]")
            self.assertEqual((sbread.stats()["br"], sbread.stats()["brc"]), (1, 1))

    def test_writes_and_login_pass_through(self):
        import browser
        for m, u in (("POST", "https://x.supabase.co/rest/v1/rpc/my_vote_add"), ("POST", "https://x.supabase.co/auth/v1/token?grant_type=password"),
                     ("PATCH", "https://x.supabase.co/rest/v1/boards?id=eq.1")):
            r = self._route(m, u, "{}")
            with mock.patch.dict("os.environ", {"WL_SB_BROWSER": "cache"}):
                browser._sb_route(r)
            r.continue_.assert_called_once()

    def test_abort_mode_reaches_nothing(self):
        import browser
        r = self._route("GET", "https://x.supabase.co/rest/v1/boards?select=id")
        with mock.patch.dict("os.environ", {"WL_SB_BROWSER": "abort"}):
            browser._sb_route(r)
        r.abort.assert_called_once()
        r.fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
