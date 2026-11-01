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


if __name__ == "__main__":
    unittest.main()
