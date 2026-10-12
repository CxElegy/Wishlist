"""篇幅 S / M / L 的测试：不访问网络。

    python -m unittest discover tests
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import render  # noqa: E402


def story(i, weight="normal"):
    return {"url": f"https://example.com/{i}", "headline": f"消息 {i}", "weight": weight,
            "date": f"2026-10-{10 + i % 9:02d}", "_issue": "2026-10-12", "image": f"https://example.com/{i}.jpg"}


class LoadSizes(unittest.TestCase):
    def setUp(self):
        digest.load_sizes.cache_clear()
        self.addCleanup(digest.load_sizes.cache_clear)
        self.tmp = pathlib.Path(tempfile.mkdtemp()) / "sizes.json"
        patcher = mock.patch.object(digest, "SIZES_FILE", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reads_database_and_caches(self):
        rows = [{"item": "FROM", "size": "S"}, {"item": "滑雪", "size": "L"}, {"item": "坏数据", "size": "XL"}]
        with mock.patch.object(digest, "supabase", return_value=rows):
            self.assertEqual(digest.load_sizes(), {"FROM": "S", "滑雪": "L"})
        self.assertEqual(digest.load_json(self.tmp), {"FROM": "S", "滑雪": "L"})

    def test_falls_back_to_cache_when_database_unreachable(self):
        digest.save_json(self.tmp, {"FROM": "S"})
        with mock.patch.object(digest, "supabase", side_effect=RuntimeError("HTTP 503")):
            self.assertEqual(digest.load_sizes(), {"FROM": "S"})
        digest.load_sizes.cache_clear()
        with mock.patch.object(digest, "supabase", return_value=None):  # 没配置数据库
            self.assertEqual(digest.load_sizes(), {"FROM": "S"})


class SizeOnPage(unittest.TestCase):
    def shown(self, size):
        stories = [story(i) for i in range(12)]
        grid, rest = render._timeline(stories, "2026-10-12", render.SIZE_HEIGHT[size])
        return len(stories) - len(rest)

    def test_bigger_size_shows_more(self):
        s, m, l = self.shown("S"), self.shown("M"), self.shown("L")
        self.assertLessEqual(s, 3)
        self.assertLess(s, m)
        self.assertLess(m, l)

    def test_size_not_written_on_page(self):
        issue = {"no": 1, "date": "2026-10-12", "items": [{
            "name": "FROM", "section": "影视", "subtitle": "", "cover": None, "facts": [],
            "theme": {"bg": "#000", "fg": "#fff", "accent": "#f00", "alt_bg": "#fff", "alt_fg": "#000", "alt_accent": "#f00"},
            "stories": [story(i) for i in range(12)]}]}
        small = render.render([issue], order=["FROM"], sizes={"FROM": "S"})
        large = render.render([issue], order=["FROM"], sizes={"FROM": "L"})
        self.assertNotEqual(small, large)
        for word in ("篇幅", "size-S", '"S"'):
            self.assertNotIn(word, small)


if __name__ == "__main__":
    unittest.main()
