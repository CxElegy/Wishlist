"""お客さまの版面の AI 編集の受け渡し（scripts/lib_queue.py）：クラウドは DB の鍵なしで編める。"""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import digest  # noqa: E402
import gate  # noqa: E402
import lib_queue  # noqa: E402
import library  # noqa: E402

PENDING = [{"title": "新作の発売日", "date": "2026-11-07", "source": "S", "summary": "12 月 1 日に発売", "url": "https://a.example/1", "image": None, "account": "u_secret"},
           {"title": "別の話", "date": "2026-11-06", "source": "T", "summary": "", "url": "https://a.example/2", "image": None}]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = pathlib.Path(self.tmp.name)
        for p in (mock.patch.object(lib_queue, "QUEUE", d / "queue.json"), mock.patch.object(lib_queue, "EDITS", d / "edits"),
                  mock.patch.object(library, "LIB_ROWS", d / "rows.json"), mock.patch.object(library, "LIB_DONE", d / "done.json")):
            p.start()
            self.addCleanup(p.stop)

    def fill(self):
        with mock.patch.object(library, "lib_rows", return_value={7: {"name": "版面七", "day": "2026-11-07", "pending": PENDING}}), \
                mock.patch.object(library, "edit_todo", return_value=[(7, "版面七", 2)]):
            return lib_queue.export(lambda *a, **k: None, "2026-11-07", [], log=lambda _m: None)


class Flow(Base):
    def test_queue_has_no_account_and_is_limited(self):
        self.fill()
        text = lib_queue.QUEUE.read_text(encoding="utf-8")
        self.assertNotIn("u_secret", text)
        self.assertNotIn("account", text)
        self.assertEqual(lib_queue.todo(), [(7, "版面七", 2)])
        self.assertIn("1 2026-11-07 S｜新作の発売日｜12 月 1 日に発売", lib_queue.brief(7))

    def test_fresh_marks_never_edited(self):
        self.fill()
        self.assertIs(json.loads(lib_queue.QUEUE.read_text(encoding="utf-8"))["boards"][0]["fresh"], True)
        self.assertEqual(lib_queue.fresh_ids(), {"7"})
        with mock.patch.object(library, "lib_rows", return_value={7: {"name": "版面七", "day": "2026-11-07", "pending": PENDING, "stories": [{"headline": "x"}]}}),                 mock.patch.object(library, "edit_todo", return_value=[(7, "版面七", 2)]):
            lib_queue.export(lambda *a, **k: None, "2026-11-07", [], log=lambda _m: None)
        self.assertIs(json.loads(lib_queue.QUEUE.read_text(encoding="utf-8"))["boards"][0]["fresh"], False)
        self.assertEqual(lib_queue.fresh_ids(), set())

    def test_edit_then_apply_writes_stories_with_event(self):
        self.fill()
        lib_queue.save_edit(7, [{"headline": "新作は 12 月 1 日", "weight": "lead", "refs": [1], "event": {"date": "2026-12-01", "label": "発売日"}}])
        self.assertEqual(lib_queue.todo(), [])   # 編んだ版面は次に出ない
        self.assertEqual(lib_queue.done_today("2026-11-07"), 1)
        calls = []
        n = lib_queue.apply_edits(lambda *a, **k: calls.append((a, k)), "2026-11-07", log=lambda _m: None)
        self.assertEqual(n, 1)
        self.assertEqual(list(lib_queue.EDITS.glob("*.json")), [])
        path, body = calls[0][0][0], calls[0][0][1]
        self.assertIn("board_id=eq.7&day=eq.2026-11-07", path)
        self.assertEqual(body["stories"][0]["url"], "https://a.example/1")
        self.assertEqual(body["stories"][0]["event"]["date"], "2026-12-01")

    def test_failed_write_keeps_the_file(self):
        self.fill()
        lib_queue.save_edit(7, [])

        def boom(*a, **k):
            raise OSError("down")
        self.assertEqual(lib_queue.apply_edits(boom, "2026-11-07", log=lambda _m: None), 0)
        self.assertEqual(len(list(lib_queue.EDITS.glob("*.json"))), 1)

    def test_unknown_board_is_refused(self):
        with self.assertRaises(SystemExit):
            lib_queue.save_edit(99, [])

    def test_done_count_is_per_day(self):
        with mock.patch.object(library, "lib_rows", return_value={}), mock.patch.object(library, "edit_todo", return_value=[]):
            lib_queue.export(lambda *a, **k: None, "2026-11-07", [], applied=3, log=lambda _m: None)
            self.assertEqual(lib_queue.done_today("2026-11-07"), 3)
            self.assertEqual(lib_queue.done_today("2026-11-08"), 0)


class CloudWithoutKey(Base):
    def test_edit_next_reads_the_queue(self):
        self.fill()
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("SUPABASE_SERVICE_KEY", None)
            self.assertEqual(digest.lib_edit_todo(), [(7, "版面七", 2)])

    def test_with_key_uses_the_database(self):
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "x"}), mock.patch.object(library, "edit_todo", return_value=[(1, "a", 1)]):
            self.assertEqual(digest.lib_edit_todo(), [(1, "a", 1)])


class GateWake(Base):
    def test_due_only_after_the_gap(self):
        self.fill()
        now = gate._now()
        old = (now - gate.dt.timedelta(hours=gate.LIB_WAKE_HOURS + 1)).isoformat()
        new = (now - gate.dt.timedelta(hours=1)).isoformat()
        self.assertTrue(gate.lib_due({"jobs": {"edit": {"fired": {"at": old}}}}))
        self.assertFalse(gate.lib_due({"jobs": {"edit": {"fired": {"at": new}}}}))
        self.assertTrue(gate.lib_due({}))


if __name__ == "__main__":
    unittest.main()
