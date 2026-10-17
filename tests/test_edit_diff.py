"""管理ページ「AI 編集の前後」（digest.edit_diff / render._admin_edit_diff）。ネットワークには出ない。"""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import render  # noqa: E402


class EditDiff(unittest.TestCase):
    def _write(self, d, raw, edit=None):
        p = pathlib.Path(d) / "2026-10-17.json"
        p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        if edit is not None:
            (pathlib.Path(d) / "2026-10-17.edit.json").write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
        return p

    def test_counts(self):
        raw = {"items": [{"name": "A", "entries": [{"n": i} for i in range(1, 11)]},
                         {"name": "B", "entries": [{"n": 1}, {"n": 2}]}]}
        edit = {"A": [{"refs": [1, 2, 3], "weight": "lead", "image": "https://x/1.jpg"}, {"refs": [3, 4, 99], "weight": "normal"}],
                "B": [], "_covered": {"A": 9, "B": 2}}
        with tempfile.TemporaryDirectory() as d:
            out = digest.edit_diff(self._write(d, raw, edit))
        a = out["rows"][0]
        self.assertEqual((a["name"], a["total"], a["used"], a["stories"], a["lead"], a["images"], a["new"]),
                         ("A", 10, 4, 2, 1, 1, 1))   # 99 は存在しない番号なので数えない
        self.assertEqual((out["total"], out["used"], out["stories"]), (12, 4, 2))

    def test_not_edited_yet(self):
        with tempfile.TemporaryDirectory() as d:
            out = digest.edit_diff(self._write(d, {"items": []}))
        self.assertFalse(out["edited"])
        self.assertIn("まだ AI 編集していません", render._admin_edit_diff(out))

    def test_unedited_rows_are_pending(self):
        """AI 編集がまだの版面（edit.json にない）は全部「整理待ち」：版面には載らない。要紧は先に載せた件数として数える。"""
        raw = {"items": [{"name": "A", "entries": [{"n": 1}, {"n": 2, "urgent": True}]},
                         {"name": "B", "entries": [{"n": 1}, {"n": 2}, {"n": 3}]}]}
        with tempfile.TemporaryDirectory() as d:
            none = digest.edit_diff(self._write(d, raw))
            some = digest.edit_diff(self._write(d, raw, {"B": [{"refs": [1]}], "_covered": {"B": 2}}))
        self.assertFalse(none["edited"])
        self.assertEqual((none["new"], none["urgent"]), (5, 1))
        self.assertEqual({r["name"]: r["new"] for r in some["rows"]}, {"A": 2, "B": 1})
        html_ = render._admin_edit_diff(none)
        self.assertIn("5</b> 件すべて整理待ち", html_)
        self.assertIn("うち要紧 1 件は先に「重大」で掲載", html_)
        self.assertIn("整理待ち 2", render._admin_edit_diff(some))
        self.assertNotIn("未編集", render._admin_edit_diff(some))

    def test_render_escapes_and_scales(self):
        d = {"date": "2026-10-17", "edited": True, "total": 3, "used": 1, "stories": 1, "images": 0, "hero": 0,
             "rows": [{"name": "<b>x</b>", "total": 3, "used": 1, "stories": 1, "hero": 0, "lead": 1, "images": 0, "new": 0}]}
        html_ = render._admin_edit_diff(d)
        self.assertNotIn("<b>x</b>", html_)
        self.assertIn("--w:100.0%", html_)
        self.assertIn('id="editdiff"', render.render_admin({"edit_diff": d}, {}, "u"))


if __name__ == "__main__":
    unittest.main()
