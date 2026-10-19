"""edit.json が報告に取り込まれていないとき（収集の古い checkout・push 競合で）それを見つける：digest.stale_report。
ネットワークには出ない。

    python -m unittest tests.test_stale_report
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402


class StaleReport(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "inbox").mkdir()
        (self.tmp / "reports").mkdir()
        self.inbox = self.tmp / "inbox" / "2026-10-19.json"
        self.inbox.write_text(json.dumps({"date": "2026-10-19", "items": []}), encoding="utf-8")
        p = [mock.patch.object(digest, "INBOX_DIR", self.tmp / "inbox"), mock.patch.object(digest, "REPORTS_DIR", self.tmp / "reports")]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def report(self, **kw):
        (self.tmp / "reports" / "2026-10-19.json").write_text(json.dumps({"no": 1, "date": "2026-10-19", "items": [], **kw}), encoding="utf-8")

    def edit(self, text="{}"):
        (self.tmp / "inbox" / "2026-10-19.edit.json").write_text(text, encoding="utf-8")

    def test_no_edit_no_report_is_fine(self):
        self.assertIsNone(digest.stale_report())

    def test_edit_not_in_report_is_stale(self):
        self.report()   # 古い報告（edit_sig なし）
        self.edit('{"ILLIT": []}')
        self.assertEqual(digest.stale_report(), self.inbox)

    def test_report_with_current_edit_is_fresh(self):
        self.edit('{"ILLIT": []}')
        self.report(edit_sig=digest.edit_sig(self.inbox))
        self.assertIsNone(digest.stale_report())

    def test_edit_changed_after_report_is_stale(self):
        self.edit('{"ILLIT": []}')
        self.report(edit_sig=digest.edit_sig(self.inbox))
        self.edit('{"ILLIT": [], "GTA 6": []}')
        self.assertEqual(digest.stale_report(), self.inbox)

    def test_no_edit_file_matches_empty_sig(self):
        self.report()
        self.assertIsNone(digest.stale_report())


if __name__ == "__main__":
    unittest.main()
