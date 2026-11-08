"""写真のない記事に記事のページの代表の写真を付ける（scripts/og_image.py，2026-11-08）。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import og_image  # noqa: E402


class Og(unittest.TestCase):
    def test_find_og_then_twitter_and_relative(self):
        self.assertEqual(og_image.find('<meta content="/i/a.jpg" property="og:image">', "https://n.example/x/1"), "https://n.example/i/a.jpg")
        self.assertEqual(og_image.find("<meta name='twitter:image' content='https://c.example/b.png'>"), "https://c.example/b.png")
        self.assertIsNone(og_image.find("<p>なし</p>"))

    def test_fill_only_missing_and_cached(self):
        rows = {"版": {"stories": [{"url": "https://n.example/1", "image": None}, {"url": "https://n.example/2", "image": "https://x/y.jpg"}],
                       "pending": [{"url": "https://n.example/3"}]}}
        cache, read = {"https://n.example/3": ""}, []

        def fetch(u):
            read.append(u)
            return '<meta property="og:image" content="https://img.example/1.jpg">'
        og_image.fill(rows, cache, fetch, log=lambda _m: None)
        self.assertEqual(read, ["https://n.example/1"])
        self.assertEqual(rows["版"]["stories"][0]["image"], "https://img.example/1.jpg")
        self.assertEqual(rows["版"]["stories"][1]["image"], "https://x/y.jpg")
        self.assertNotIn("image", rows["版"]["pending"][0])

    def test_broken_page_is_remembered(self):
        cache = {}

        def boom(u):
            raise OSError("down")
        og_image.fill({"b": {"stories": [{"url": "https://n.example/9"}]}}, cache, boom, log=lambda _m: None)
        self.assertEqual(cache, {"https://n.example/9": ""})


    def test_demote_moves_photoless_to_pending(self):
        rows = {"a": {"stories": [{"url": "1", "image": "i"}, {"url": "2"}], "pending": [{"url": "3"}]}, "b": {"stories": [{"url": "4"}]}}
        self.assertEqual(og_image.demote(rows), 1)
        self.assertEqual([s["url"] for s in rows["a"]["stories"]], ["1"])
        self.assertEqual([s["url"] for s in rows["a"]["pending"]], ["2", "3"])
        self.assertEqual([s["url"] for s in rows["b"]["stories"]], ["4"])   # 写真のある記事が無い版面は動かさない


if __name__ == "__main__":
    unittest.main()
