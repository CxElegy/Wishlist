"""版面の記事の並び（2026-11-02 mason）：決まった升目で同じ段の背をそろえず、1px の行に 1 枚ずつ一番低い列へ積む。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


class MasonTest(unittest.TestCase):
    def test_mason_in_fit_js(self):
        js = render.FIT_JS
        for s in ("const mason = ", "'span ' + Math.max(1, Math.ceil(", "perms(tail)"):
            self.assertEqual(js.count(s), 1, s)
        self.assertEqual(js.count("m.className = 'mas'"), 2)   # 版面の小さいカードの束・過去のニュース（.older）の束
        self.assertIn("document.addEventListener('toggle'", js)   # 閉じていると高さ 0：開いたときに積む

    def test_css_masonry_rows_are_1px_and_mobile_unwraps(self):
        css = render.CSS
        self.assertIn(".mas{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:22px;grid-auto-rows:1px", css)
        self.assertIn(".mas{display:contents}", css)   # 760px 以下は外して 1 列のまま

    def test_lead_rules_follow_into_mas(self):
        # 大きい記事は .mas の子になるので、.grid>.lead の見た目の決まりが .mas>.lead にも要る
        for s in (".mas>.lead .pic", ".mas>.lead h2", ".mas>.lead .blurb", ".mas>.card,.side>.card{padding-bottom:16px"):
            self.assertIn(s, render.CSS, s)

    def test_ux_check_counts_mas_cards(self):
        src = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn(":scope>.mas>article.card,:scope>.mas>.side>article.card", src)


if __name__ == "__main__":
    unittest.main()


class MasonOlderTest(unittest.TestCase):
    def test_closed_older_not_wrapped(self):
        # 閉じた「もっと見る」を包むと、隠れた写真の測りが 0 のまま写真の余白の点検に数えられた（2026-11-02）
        self.assertIn("(old && !g.closest('details').open)", render.FIT_JS)

    def test_sb_card_has_no_row_gap(self):
        # 写真の枠は 9 行にまたがる。字の入らない行にも行の隙間が付いてカードが 73〜86px 高くなっていた
        self.assertIn("column-gap:12px;row-gap:0;align-content:start}", render.CSS)
        self.assertIn(":not(:last-child){margin-bottom:8px}", render.CSS)

    def test_sb_card_extra_height_goes_to_third_row(self):
        self.assertIn(".card.sb:not(.mini){grid-template-rows:auto auto minmax(0,1fr)}", render.CSS)

    def test_mini_c6_runs_get_two_columns(self):
        # お客さまの版面の 4 枚の並び（mini c6）も mason の外に出さない：2 列の束（.mas2）
        self.assertIn("article.card.mini.c6", render.FIT_JS)
        self.assertIn("'mas mas2'", render.FIT_JS)
        self.assertIn(".mas.mas2{grid-template-columns:repeat(2,minmax(0,1fr))}", render.CSS)
