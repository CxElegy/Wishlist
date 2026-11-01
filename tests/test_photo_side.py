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
        # 壁が足した高さは足す前（fit が決めた .sb の写真枠の高さ）に戻す。空にして fit の高さを消さない
        self.assertIn("p.dataset.add === '-' ? '' : p.dataset.add", render.FIT_JS)

    def test_wall_packs_by_content_height(self):
        """2026-11-01 L1・L2：壁のカードは中身の高さで詰める（升目で背をそろえて下を空けない）。"""
        js, src = render.FIT_JS, (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        for s in ("c.style.gridRow = (y + 1)", "w.style.gridAutoRows = '1px'", "w.style.alignItems = 'start'"):
            self.assertIn(s, js)
        self.assertNotIn(".wc.lead{grid-column:span 2;grid-row:span 2}", src)   # 大きい 1 枚は行を 2 つ占めて伸ばさない
        self.assertIn("const GAP = 18", js)
        self.assertIn("HOLE_JS", (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8"))   # 点検：カードの中の空白

    def test_ux_check_counts_gap_everywhere(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("const S='section.sec article.card,section.sec .wc,section.sec a.tape,.pk'", u)   # GAP_JS（全候補を読み込んでから数える）
        self.assertIn("写真の余白（空いた横が情報なし）", u)



class LeadBottomAlign(unittest.TestCase):
    """2026-11-01 L2：縦長の主写真の大きい記事は右の記事の列と底をそろえる。測り直しで次のニュースが増えない"""

    def test_unnarrow_opens_text_column_before_removing_nx(self):
        js = render.FIT_JS
        a = js.index("const unnarrow =")
        body = js[a:js.index("const narrow =", a)]
        self.assertLess(body.index("lt.remove()"), body.index("querySelectorAll('.nx')"))   # 字の列（.ltx）の中の .nx も消す
        self.assertNotIn("':scope > .nx, :scope > .txt > .nx'", body)

    def test_css_stretches_lead_and_side(self):
        src = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        for s in (".grid>.lead.nw:not(.ls){align-self:stretch", "min-height:var(--ph,0px)", ".grid:has(>.lead.nw) .side>.card{align-self:stretch}"):
            self.assertIn(s, src)
        self.assertEqual(render.FIT_JS.count("setProperty('--ph'"), 2)   # sz と、測るときの 0 のとき

    def test_ux_check_counts_dup_and_gap(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        for s in ("nxdup:", "leadgap:", "「同じ版面の次のニュース」が 2 つ以上ある記事"):
            self.assertIn(s, u)

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


class NextNewsCrop(unittest.TestCase):
    """2026-11-01 主写真の横の「同じ版面の次のニュース」(.nx) も 3:2 に切るので、同じ cropAt を通す（取りこぼし）"""
    def test_nx_uses_cropat_or_whole(self):
        js = render.FIT_JS
        self.assertIn("im.dataset.m = x.i.dataset.m", js)
        self.assertIn("cropAt(im, r)", js)
        self.assertIn("classList.toggle('whole'", js)
        self.assertIn(".nx img.whole{object-fit:contain", render.CSS if hasattr(render, "CSS") else (ROOT / "scripts" / "render.py").read_text(encoding="utf-8"))

    def test_ux_check_counts_nx(self):
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn('section.sec .nx img[data-e="s"]:not(.whole)', u)
