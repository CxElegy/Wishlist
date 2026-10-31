"""F-16 続き：小さいカード・気になるかもも、写真が枠より細いときは枠を写真の幅に絞り字の列を横に置く（.sb）。点検 gap が数える"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


class PhotoSide(unittest.TestCase):
    def test_fit_js_has_side_rule_for_small_cards_and_pk(self):
        js = render.FIT_JS
        self.assertIn("const side =", js)
        self.assertIn("const unside =", js)
        self.assertIn("side(sm, p, nat", js)   # c3・mini・wc・tape
        self.assertIn("side(pk, p, nat", js)   # 気になるかも
        self.assertIn("c.classList.add('sb')", js)

    def test_unside_runs_before_measuring(self):
        js = render.FIT_JS
        self.assertLess(js.index("unside(pk || sm, p)"), js.index("p.closest('article.hero"))

    def test_css_lays_out_each_kind(self):
        src = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        for sel in (".card.sb:not(.mini)", ".wc.sb", ".card.mini.sb", ".tape.sb", ".pk.sb>a"):
            self.assertIn(sel, src)

    def test_wall_keeps_side_height(self):
        self.assertIn("!c.classList.contains('sb')", render.FIT_JS)

    def test_ux_check_counts_gap_everywhere(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("gap:[...document.querySelectorAll('section.sec article.card,section.sec .wc,section.sec a.tape,.pk')]", u)
        self.assertIn("写真の余白（空いた横が情報なし）", u)


if __name__ == "__main__":
    unittest.main()
