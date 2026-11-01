"""版面の中の記事の並び（L2・2026-11-01）：大きい記事は右の記事の数だけ段をまたぎ、右の記事は升目の 1 段ずつに置く（.side は display:contents）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402


def story(i, w="normal"):
    return {"headline": f"t{i}", "title": f"t{i}", "url": f"https://example.com/{i}", "weight": w, "date": "2026-11-01", "_issue": "2026-11-01"}


class GridRows(unittest.TestCase):
    def test_lead_spans_side_rows(self):
        for n in (1, 2, 3):
            rows = render._layout([story(0, "lead")] + [story(i) for i in range(1, n + 1)], side=3)
            html = render._render_rows(rows, "2026-11-01")
            self.assertIn(f'<article class="card rs{n} ', html)
            self.assertEqual(html.count("mini c4"), n)

    def test_css_rules(self):
        css = pathlib.Path(render.__file__).read_text(encoding="utf-8")
        self.assertIn(".side{display:contents}", css)
        self.assertIn("align-items:start", css.split(".grid{display:grid")[1].split("}")[0])
        for k in (1, 2, 3, 4):
            self.assertIn(f".rs{k}{{grid-row:span {k}}}", css)


class GridHoleRules(unittest.TestCase):
    """縦長の主写真（ILLIT 型）と点検の数え方（2026-11-01 別の目の指摘）。"""

    def test_unnarrow_removes_nested_nx(self):
        src = pathlib.Path(render.__file__).read_text(encoding="utf-8")
        self.assertIn(":scope > .ltx > .nx", src)   # 字の列の中の次のニュースも消す（残ると 2 段目に空き）
        self.assertIn("c._span", src)
        self.assertIn("--nxw", src)
        self.assertIn(".pkgrid>.pk:not(.big){align-self:stretch}", src)
        self.assertIn("let spt;", src)   # 再測定の変数名は既存の st と別（同じ名前だと JS 全体が止まった）
        self.assertEqual(src.count("let st;"), 0)

    def test_hole_check_not_loosened(self):
        ux = (pathlib.Path(render.__file__).resolve().parent.parent / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("v[0]-y>=40", ux)            # 記事のあいだ 40px 以上（100px への緩めを戻した）
        self.assertNotIn("v[0]-y>=100", ux)
        self.assertIn("cs.length<2", ux)           # 2 記事の並びも測る
        self.assertNotIn("cs.length<3", ux)
        self.assertIn("gridSkip", ux)              # 測れなかった並びを数えて出す
        self.assertIn(".pkgrid", ux)               # 気になるかも


if __name__ == "__main__":
    unittest.main()
