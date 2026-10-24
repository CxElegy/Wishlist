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


class SettingsPage(unittest.TestCase):
    def test_lists_items_by_section_with_current_size(self):
        page = render.render_settings(
            [{"name": "GTA 6", "section": "游戏", "size": "M"}, {"name": "FROM", "section": "影视", "subtitle": "美剧", "size": "S"}],
            {"url": "https://x.supabase.co", "key": "sb_publishable_x"}, "10.14 19:00")
        self.assertLess(page.index("影视"), page.index("游戏"))   # 8 大類：作品が先
        self.assertIn('data-item="FROM"', page)
        self.assertRegex(page, r'data-item="FROM".*?data-v="S" aria-pressed="true"')
        self.assertIn("rpc/${CFG.own ? (OWNFN[fn] || fn) : fn}", page)
        self.assertNotIn("sb_secret", page)


class OlderGrid(unittest.TestCase):
    def test_rows_split_evenly_with_existing_spans(self):
        """折叠区每张卡片的宽度都要在样式表里有对应的 cN（2 条以前会排成 9 + 3，c9 没有样式）。"""
        for n, want in ((1, [12]), (2, [6, 6]), (3, [4, 4, 4]), (4, [3] * 4), (5, [3] * 4 + [12]),
                        (6, [3] * 4 + [6, 6])):
            spans = [w for _, w in render._pack([story(i, "lead" if i == 0 else "normal") for i in range(n)],
                                                lambda s: 3)]
            self.assertEqual(spans, want, n)
            for w in spans:
                self.assertIn(f".c{w}{{grid-column:span {w}}}", render.CSS)


class Legible(unittest.TestCase):
    def test_section_colors_reach_aa(self):
        import theme
        t = render._legible({"bg": "#151515", "fg": "#F5F5F5", "accent": "#EF4348",
                             "alt_bg": "#EC1D24", "alt_fg": "#FFFFFF", "alt_accent": "#FFFFFF"})
        for a, b in (("fg", "bg"), ("accent", "bg"), ("alt_fg", "alt_bg"), ("alt_accent", "alt_bg")):
            self.assertGreaterEqual(theme.contrast(theme._rgb(t[a]), theme._rgb(t[b])), 4.5, (a, b, t))
        self.assertEqual(t["alt_fg"], "#FFFFFF")   # 白字不变，压暗的是底色
        for name, color in render.SECTIONS.items():   # 板块色：白字、浅底上都过 AA
            self.assertGreaterEqual(theme.contrast(theme._rgb(color), (255, 255, 255)), 4.5, name)
            self.assertGreaterEqual(theme.contrast(theme._rgb(color), theme._rgb("#EDEBE6")), 4.5, name)


class NavSchemes(unittest.TestCase):
    """小分類の分け方（⚙ 設定ページで板块ごとに選ぶ）。"""

    def test_sub_of(self):
        it = {"subs": {"status": "運営中", "platform": "PC"}}
        self.assertEqual(digest.sub_of(it, "platform"), "PC")
        self.assertEqual(digest.sub_of(it, "nope"), "運営中")          # 書いていない分け方：最初の値
        self.assertEqual(digest.sub_of({"sub": "旧"}, "status"), "旧")  # 旧い sub も読む

    def test_choice_falls_back_to_first(self):
        settings = {"sub_schemes": {"游戏": [{"id": "status"}, {"id": "platform"}], "影视": [{"id": "kind"}]}}
        with mock.patch.object(digest, "supabase", return_value=[{"section": "游戏", "scheme": "platform"},
                                                                 {"section": "影视", "scheme": "bogus"}]), \
             mock.patch.object(digest, "save_json"):
            self.assertEqual(digest.load_nav_schemes(settings), {"游戏": "platform", "影视": "kind"})


class SoftenLoudAlt(unittest.TestCase):
    """副色が原色の作品（漫威の赤など）は、折叠区の広い面を落ち着いた色にする。"""

    def test_loud_detection(self):
        for loud in ("#EC1D24", "#E2131A", "#FFB25B", "#DE1A33"):
            self.assertTrue(render._loud(loud), loud)
        for calm in ("#740001", "#1E3932", "#F1EEE6", "#C9CDD5", "#BFE3DA", "#14233A", "nonsense"):
            self.assertFalse(render._loud(calm), calm)

    def test_section_gets_softalt_only_when_loud(self):
        def page(alt_bg, alt_fg):
            issue = {"no": 1, "date": "2026-10-12", "items": [{
                "name": "X", "section": "影视", "subtitle": "", "cover": None, "facts": [],
                "theme": {"bg": "#151515", "fg": "#F5F5F5", "accent": "#EC1D24", "alt_bg": alt_bg, "alt_fg": alt_fg, "alt_accent": "#FFFFFF"},
                "stories": [story(i) for i in range(12)]}]}
            return render.render([issue], order=["X"])
        self.assertRegex(page("#EC1D24", "#FFFFFF"), r'<section[^>]*class="sec[^"]*\bsoftalt\b')
        self.assertNotRegex(page("#F1EEE6", "#1A1C22"), r'<section[^>]*class="sec[^"]*\bsoftalt\b')
