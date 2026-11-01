"""審査待ちの見本が全部、触って答えを保存できる形か数える（2026-11-02：face-size だけ作って、ほかの A/B/C は眺めるだけだった）。"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import review_pages as rp  # noqa: E402


class ReviewPages(unittest.TestCase):
    def test_every_pending_page_is_answerable(self):
        pages = rp.pending_pages((rp.TG / "index.html").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(pages), 7)
        bad = []
        for p in pages:
            bad += rp.static_bad(p, (rp.TG / p).read_text(encoding="utf-8"))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_saver_exists_and_is_guarded(self):
        js = (rp.TG / "review.js").read_text(encoding="utf-8")
        self.assertIn("review_save", js)
        self.assertIn("wl-auth", js)
        sql = (ROOT / "db" / "review_answers.sql").read_text(encoding="utf-8")
        self.assertRegex(sql, r"review_save[\s\S]*is_admin\(\)")
        self.assertIn("enable row level security", sql)


if __name__ == "__main__":
    unittest.main()
