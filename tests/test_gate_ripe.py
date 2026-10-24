"""AI 編集は版面ごとに「溜まったら」（gate.edit_ripe）：3 件以上・いちばん古いものが 2 時間・初めての版面。1 日のトークンの上限。"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import gate  # noqa: E402
import runlog  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 24, 6, 0, tzinfo=UTC)   # 北京時間 14:00


def ent(n, hours_ago=None):
    e = {"n": n, "title": f"t{n}", "url": f"https://x/{n}"}
    if hours_ago is not None:
        e["seen"] = (NOW - dt.timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return e


class Ripe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.inbox = pathlib.Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, items, edit=None, prev_edit=None):
        (self.inbox / "2026-10-24.json").write_text(json.dumps({"items": [{"name": k, "entries": v} for k, v in items.items()]}), "utf-8")
        if edit is not None:
            (self.inbox / "2026-10-24.edit.json").write_text(json.dumps(edit), "utf-8")
        if prev_edit is not None:
            (self.inbox / "2026-10-23.edit.json").write_text(json.dumps(prev_edit), "utf-8")

    def ripe(self):
        return gate.edit_ripe(self.inbox, today="2026-10-24", now=NOW)

    def test_rules(self):
        known = {"A": [], "B": [], "C": [], "D": [], "E": []}
        self.write({
            "A": [ent(1, 1), ent(2, 0.5), ent(3, 0.1)],       # 3 件 → すぐ
            "B": [ent(1, 1), ent(2, 0.5)],                    # 2 件・1 時間 → 待つ
            "C": [ent(1, 2.5)],                               # 1 件でも 2 時間を超えた → すぐ
            "D": [ent(1)],                                    # seen のない前の形・持ち越し → 古いと数える
            "E": [ent(1, 5), ent(2, 0.2)],                    # 1 件目は編集済み（_covered 1）、残り 1 件は新しい → 待つ
            "F": [ent(1, 0.1)],                               # 初めての版面（どの edit.json にもない）→ すぐ
        }, edit={"_covered": {"E": 1}, "E": []}, prev_edit=known)
        self.assertEqual(self.ripe(), {"A": 3, "C": 1, "D": 1, "F": 1})
        self.assertEqual(gate.edit_work(self.inbox, today="2026-10-24"), {"A": 3, "B": 2, "C": 1, "D": 1, "E": 1, "F": 1})

    def test_tokens_today(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "edit.json").write_text(json.dumps([
                {"at": "2026-10-24T01:00:00+00:00", "tok": {"in": 100, "cw": 1000, "cr": 999999, "out": 50}},
                {"at": "2026-10-23T01:00:00+00:00", "tok": {"in": 5000, "cw": 0, "cr": 0, "out": 0}},   # 昨日は数えない
            ]), "utf-8")
            self.assertEqual(gate.edit_tokens_today(pathlib.Path(d), now=NOW), 1150)   # キャッシュ読みは数えない


class FireRipe(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.dir.name) / "gate.json"
        # 9:00 の回で 2 時間前に起こし、進んだ（前の形なら 18:00 を待つ状況）
        self.job = {"need": True, "items": ["A"], "sig": "s1", "prog": 25,
                    "fired": {"at": (NOW - dt.timedelta(hours=2)).isoformat(), "sig": "s0", "prog": 10, "attempts": 1}}

    def tearDown(self):
        self.dir.cleanup()

    def fire(self, **kw):
        gate.save({"jobs": {"edit": {**self.job, **kw}}}, self.state)
        calls = []
        with mock.patch.object(gate, "_now", lambda: NOW):
            res = gate.fire(self.state, post=lambda u, tok: calls.append(u) or 200,
                            env={"ROUTINE_TOKEN_EDIT": "t", "GATE_FIRE": "edit", "EDIT_MODE": "run"})["edit"]
        return res, calls

    def test_ripe_fires_without_waiting_for_slot(self):
        res, calls = self.fire(ripe=["A"], tokens_today=0, token_cap=1000)
        self.assertEqual(res, "Claude を起こした")
        self.assertEqual(len(calls), 1)

    def test_not_ripe_waits(self):
        res, calls = self.fire(ripe=[], tokens_today=0, token_cap=1000)
        self.assertIn("まだ溜まっていない", res)
        self.assertEqual(calls, [])

    def test_daily_cap(self):
        res, calls = self.fire(ripe=["A"], tokens_today=1000, token_cap=1000)
        self.assertIn("上限", res)
        self.assertEqual(calls, [])

    def test_still_one_at_a_time(self):
        """溜まっても、60 分以内に起こし済みなら 2 本目は起こさない。"""
        res, calls = self.fire(ripe=["A"], tokens_today=0, token_cap=1000,
                               fired={"at": (NOW - dt.timedelta(minutes=10)).isoformat(), "sig": "s0", "prog": 25, "attempts": 1})
        self.assertIn("60 分以内", res)
        self.assertEqual(calls, [])

    def test_no_slot_shown(self):
        self.assertEqual(gate.due_slot({**self.job, "ripe": []}, NOW), "")


if __name__ == "__main__":
    unittest.main()
