"""拒まれたときの取り直し（scrapling）と、正文図から代表の 1 枚を選ぶ規則。ネットには出ない（_fetch_plain・_scrape を差し替える）。

    python -m unittest tests.test_scrape
"""

import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import images  # noqa: E402
from images import Fetched  # noqa: E402


class Fallback(unittest.TestCase):
    def setUp(self):
        images.clear_cache()
        p = mock.patch.object(images, "SCRAPLING", True)
        p.start()
        self.addCleanup(p.stop)

    def test_blocked_page_is_fetched_again(self):
        calls = []
        with mock.patch.object(images, "_fetch_plain", lambda u, l, r=None: Fetched(403, {}, b"cloudflare")), \
                mock.patch.object(images, "_scrape", lambda u, l, r=None, page=False: calls.append(page) or Fetched(200, {}, b"<html>ok</html>", via="scrapling")):
            f = images._fetch("https://a.example/x", images.PAGE_LIMIT)
        self.assertEqual((f.status, f.via), (200, "scrapling"))
        self.assertEqual(calls, [True])   # 記事の頁はブラウザらしいヘッダー

    def test_image_gets_no_fake_headers_and_is_saved(self):
        calls = []
        with mock.patch.object(images, "_fetch_plain", lambda u, l, r=None: Fetched(403, {}, b"")), \
                mock.patch.object(images, "_scrape", lambda u, l, r=None, page=False: calls.append(page) or Fetched(200, {}, b"img", via="scrapling")), \
                mock.patch.object(images, "_inspect", lambda b, c: (True, "1200×675")):
            self.assertEqual(images.check("https://a.example/i.jpg"), (True, "1200×675"))
        self.assertEqual(calls, [False])   # 画像には付けない
        self.assertIn("https://a.example/i.jpg", images._hard)   # 本站に保存する印

    def test_not_blocked_is_not_retried(self):
        with mock.patch.object(images, "_fetch_plain", lambda u, l, r=None: Fetched(404, {}, b"")), \
                mock.patch.object(images, "_scrape", side_effect=AssertionError("404 は取り直さない")):
            self.assertEqual(images._fetch("https://a.example/x", images.PAGE_LIMIT).status, 404)

    def test_still_blocked_keeps_first_answer(self):
        with mock.patch.object(images, "_fetch_plain", lambda u, l, r=None: Fetched(403, {}, b"cloudflare")), \
                mock.patch.object(images, "_scrape", lambda u, l, r=None, page=False: Fetched(403, {}, b"cloudflare", via="scrapling")):
            f = images._fetch("https://a.example/x", images.PAGE_LIMIT)
        self.assertEqual((f.status, f.via), (403, ""))

    def test_browser_only_when_switched_on_and_capped(self):
        with mock.patch.dict(images.os.environ, {"SCRAPLING_BROWSER": ""}):
            self.assertIsNone(images._browser_html("https://a.example/x"))
        with mock.patch.dict(images.os.environ, {"SCRAPLING_BROWSER": "1"}):
            images._browser_used[:] = [images.BROWSER_MAX, 0.0]
            self.assertIsNone(images._browser_html("https://a.example/x"))   # 1 回 BROWSER_MAX 頁まで
            images._browser_used[:] = [0, images.BROWSER_BUDGET - 1]
            self.assertIsNone(images._browser_html("https://a.example/x"))   # 持ち時間の残りが 1 頁分ない
            images._browser_used[:] = [0, 0.0]

    def test_off_switch(self):
        with mock.patch.object(images, "SCRAPLING", False):
            self.assertIsNone(images._scrape("https://a.example/x", 10))


class KeyImage(unittest.TestCase):
    def test_bigger_and_card_shaped_wins(self):
        self.assertGreater(images.key_score(1600, 1000, 1), images.key_score(600, 400, 0))
        self.assertGreater(images.key_score(1200, 750, 0), images.key_score(1200, 1800, 0))   # 縦長より横長のカード形

    def test_strips_lose(self):
        self.assertLess(images.key_score(2000, 300, 0), images.key_score(800, 500, 3))   # 細長い帯（広告・区切り）

    def test_pick_chooses_best_body_image(self):
        p = images.Page("https://a.example/x", True, body=["https://a.example/1.jpg", "https://a.example/2.jpg", "https://a.example/3.jpg"])
        sizes = {"https://a.example/1.jpg": "1600×300", "https://a.example/2.jpg": "1400×875", "https://a.example/3.jpg": "500×500"}
        images.clear_cache()
        with mock.patch.object(images, "page", lambda u: p), mock.patch.object(images, "check", lambda u, referer=None: (True, sizes[u])), \
                mock.patch.object(images, "syndicated_candidates", lambda t, u: ([], "")):
            res = images.pick(None, [], "https://a.example/x")
        self.assertEqual(res.image, "https://a.example/2.jpg")
        self.assertIn("3 枚から", res.source)


if __name__ == "__main__":
    unittest.main()
