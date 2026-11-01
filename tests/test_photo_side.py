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

    def test_late_and_hidden_photos_get_fitted(self):
        js = render.FIT_JS   # 隠れた版面・あとから JS で足された版面の写真も測る（390px で大きいカードの枠が絞られないままだった）
        for s in ("new ResizeObserver", "new MutationObserver", "p._ok = 1", "document.addEventListener('load'"):
            self.assertIn(s, js)

    def test_wall_keeps_side_height(self):
        self.assertIn("!c.classList.contains('sb')", render.FIT_JS)

    def test_ux_check_counts_gap_everywhere(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("gap:[...document.querySelectorAll('section.sec article.card,section.sec .wc,section.sec a.tape,.pk')]", u)
        self.assertIn("写真の余白（空いた横が情報なし）", u)


if __name__ == "__main__":
    unittest.main()


class CropEverywhere(unittest.TestCase):
    """2026-11-01 切る位置は全部の切る場所で同じ規則（cropAt）。点検 pkcut も全部を数える"""
    def test_every_cut_place_uses_cropat(self):
        js = render.FIT_JS
        self.assertGreaterEqual(js.count("cropAt(img,"), 3)   # PC の気になるかも・スマホの気になるかも・主写真と小さいカード
        self.assertIn("(r >= 0.75 && cropAt(img, r))", js)     # c3・mini・wc・tape・主写真
        self.assertIn("cropAt(img, nat / (w / h))", js)        # スマホ幅の気になるかも

    def test_mass_is_given_to_every_card_photo(self):
        self.assertNotIn("focus", render._pic.__code__.co_varnames)

    def test_ux_check_counts_cut_everywhere(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("section.sec .pic.fill img[data-e=\"s\"]", u)
