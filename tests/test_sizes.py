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
        for patcher in (mock.patch.object(digest, "SIZES_FILE", self.tmp),
                        mock.patch.object(digest, "SIZES_PUSHED_FILE", self.tmp.with_name("pushed.json")),
                        mock.patch.object(digest, "load_config", return_value=({}, []))):
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


class PushSizes(unittest.TestCase):
    """数据库里缺的、items.yaml 新改的篇幅自动写进数据库，不用手动加。"""

    def setUp(self):
        digest.load_sizes.cache_clear()
        self.addCleanup(digest.load_sizes.cache_clear)
        tmp = pathlib.Path(tempfile.mkdtemp())
        for name, path in (("SIZES_FILE", tmp / "sizes.json"), ("SIZES_PUSHED_FILE", tmp / "pushed.json")):
            patcher = mock.patch.object(digest, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.writes = []

    def run_with(self, db, items):
        def fake(path, body=None, prefer=None):
            if body is None:
                return [{"item": k, "size": v} for k, v in db.items()]
            self.writes.append({r["item"]: r["size"] for r in body})
            db.update(self.writes[-1])
            return []
        digest.load_sizes.cache_clear()
        with mock.patch.object(digest, "supabase", side_effect=fake), \
                mock.patch.object(digest, "load_config", return_value=({}, items)):
            return digest.load_sizes()

    def test_missing_items_are_added(self):
        got = self.run_with({"A": "L"}, [{"name": "A"}, {"name": "B"}, {"name": "C", "size": "s"}])
        self.assertEqual(self.writes, [{"B": "M", "C": "S"}])
        self.assertEqual(got, {"A": "L", "B": "M", "C": "S"})

    def test_yaml_change_is_pushed_but_database_edit_wins_otherwise(self):
        db = {"A": "S"}
        self.run_with(db, [{"name": "A", "size": "S"}])
        self.assertEqual(self.writes, [])
        db["A"] = "L"  # 在数据库里手动改
        self.assertEqual(self.run_with(db, [{"name": "A", "size": "S"}]), {"A": "L"})
        self.assertEqual(self.writes, [])
        self.assertEqual(self.run_with(db, [{"name": "A", "size": "M"}]), {"A": "M"})  # items.yaml 改了
        self.assertEqual(self.writes, [{"A": "M"}])

    def test_yaml_size_used_when_database_unavailable(self):
        with mock.patch.object(digest, "supabase", return_value=None), \
                mock.patch.object(digest, "load_config", return_value=({}, [{"name": "A", "size": "L"}, {"name": "B"}])):
            self.assertEqual(digest.load_sizes(), {"A": "L"})


class SizeOnPage(unittest.TestCase):
    def shown(self, size):
        stories = [story(i) for i in range(12)]
        grid, rest = render._timeline(stories, "2026-10-12", render.SIZE_HEIGHT[size], render.SIZE_COUNT[size],
                                      render.SIZE_SIDE[size])
        return len(stories) - len(rest)

    def test_each_size_fits_its_height(self):
        stories = [story(i, "lead" if i % 4 == 0 else "normal") for i in range(16)]
        for size, budget in render.SIZE_HEIGHT.items():
            grid, rest = render._timeline(stories, "2026-10-12", budget, render.SIZE_COUNT[size], render.SIZE_SIDE[size])
            kept = [x for x in stories if x not in rest]
            self.assertLessEqual(render._height(kept, render.SIZE_SIDE[size]), budget, size)
            self.assertLessEqual(len(kept), render.SIZE_COUNT[size], size)

    def test_only_newest_lead_is_big(self):
        stories = [story(1, "lead"), story(2), story(3, "lead"), story(4)]
        kinds = [k for k, _ in render._layout(stories)]
        self.assertEqual(kinds.count("lead"), 1)
        grid, _ = render._timeline(stories, "2026-10-12", render.SIZE_HEIGHT["L"], render.SIZE_COUNT["L"], render.SIZE_SIDE["L"])
        self.assertEqual(grid.count("<h2>"), 1)

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
