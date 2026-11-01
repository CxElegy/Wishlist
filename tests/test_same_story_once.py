"""L7「同じ記事は 1 ページに 1 回」：次のニュースに出した記事は元のカードを畳み、ux_check が二重を数える（2026-11-01）。"""
import pathlib
import unittest

R = pathlib.Path(__file__).resolve().parents[1]
RENDER = (R / "scripts" / "render.py").read_text(encoding="utf-8")
UX = (R / "harness" / "ux_check.py").read_text(encoding="utf-8")


class SameStoryOnce(unittest.TestCase):
    def test_nx_sources_are_folded(self):
        self.assertIn(".nxd{display:none!important}", RENDER)
        self.assertIn("c._nxSrc.forEach(a => a.classList.add('nxd'))", RENDER)
        self.assertIn("(c._nxSrc || []).forEach(a => a.classList.remove('nxd'))", RENDER)   # 外すとき元のカードを戻す
        self.assertIn("!a.classList.contains('nxd')", RENDER)                                # 使った記事を別の次のニュースに使わない

    def test_ux_check_counts_duplicates(self):
        self.assertIn("sameStory", UX)
        self.assertIn("同じ記事が版面に 2 回以上", UX)


if __name__ == "__main__":
    unittest.main()
