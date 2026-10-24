"""ライブラリの控えの時計（library_watch）：library.yml の毎時 41 分が抜けたら、後台作業が users_only で起こす。ネットには出ない。"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import library_watch  # noqa: E402
import runlog  # noqa: E402


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def run_(status="completed", conclusion="success", at="2026-10-24T01:41:00Z"):
    return {"status": status, "conclusion": conclusion, "createdAt": at, "event": "schedule"}


class Decide(unittest.TestCase):
    NOW = t("2026-10-24T03:17")

    def test_missed_hour_kicks(self):
        """01:41 の回のあと 02:41 が抜けた → 03:17 の後台作業（96 分）で起こす。"""
        due, why = library_watch.decide([run_()], self.NOW)
        self.assertTrue(due, why)

    def test_fresh_waits(self):
        due, _ = library_watch.decide([run_(at="2026-10-24T02:41:00Z")], self.NOW)
        self.assertFalse(due)

    def test_busy_waits(self):
        for s in ("queued", "in_progress"):
            self.assertFalse(library_watch.decide([run_(status=s, conclusion=None, at="2026-10-24T03:00:00Z"), run_()], self.NOW)[0])

    def test_failed_recent_run_waits(self):
        """起こした回が落ちても、30 分以内は起こし直さない（1 時間に 1 回まで）。"""
        runs = [run_(conclusion="failure", at="2026-10-24T03:00:00Z"), run_()]
        self.assertFalse(library_watch.decide(runs, self.NOW)[0])
        self.assertTrue(library_watch.decide(runs, t("2026-10-24T03:47"))[0])

    def test_only_failures_kick(self):
        self.assertTrue(library_watch.decide([run_(conclusion="failure")], self.NOW)[0])

    def test_unreadable_does_not_kick(self):
        self.assertFalse(library_watch.decide(None, self.NOW)[0])

    def test_within_two_hours(self):
        """定時が 1 回抜けても、選んだもの（直前の回の直後に足した）が 2 時間以内に拾われる：後台作業は毎時 17 分。"""
        last = t("2026-10-24T01:41")
        for m in range(0, 60):
            pick = last + dt.timedelta(minutes=1 + m)
            # 次の 17 分の後台作業のうち、起こすのは最初に 80 分を超えたもの
            first = next(last.replace(minute=17) + dt.timedelta(hours=h) for h in range(1, 4)
                         if library_watch.decide([run_(at=last.isoformat())], last.replace(minute=17) + dt.timedelta(hours=h))[0])
            self.assertLess(first - pick, dt.timedelta(hours=2))


class Main(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.dir.name)
        self.calls = []

    def tearDown(self):
        self.dir.cleanup()

    def fake(self, runs, kick_ok=True):
        def f(args, **kw):
            self.calls.append(args)
            if args[:3] == ["gh", "workflow", "run"]:
                return NS(returncode=0 if kick_ok else 1, stdout="", stderr="" if kick_ok else "HTTP 403")
            return NS(returncode=0, stdout=json.dumps(runs), stderr="")
        return f

    def test_kicks_users_only_and_logs(self):
        due, kicked, _ = library_watch.main([], run=self.fake([run_()]), log_dir=self.log, now=t("2026-10-24T03:17"))
        self.assertTrue(due and kicked)
        self.assertEqual(self.calls[0][:4], ["gh", "run", "list", "--workflow"])
        self.assertIn("library.yml", self.calls[0])
        self.assertEqual(self.calls[-1], ["gh", "workflow", "run", "library.yml", "-f", "users_only=true"])
        rows = runlog.load("gate", self.log)
        self.assertTrue(rows[-1]["library_kick"])

    def test_failed_kick_logged_once(self):
        out = self.log / "out.txt"
        with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(out)}):
            for _ in range(2):
                library_watch.main([], run=self.fake([run_()], kick_ok=False), log_dir=self.log, now=t("2026-10-24T03:17"))
        self.assertEqual(len(runlog.load("gate", self.log)), 1)
        self.assertEqual(out.read_text().splitlines()[-1], "tried=false")   # 同じ失敗の 2 回目はコミットを増やさない

    def test_dry_does_not_kick(self):
        library_watch.main(["--dry"], run=self.fake([run_()]), log_dir=self.log, now=t("2026-10-24T03:17"))
        self.assertFalse(any(c[:3] == ["gh", "workflow", "run"] for c in self.calls))
        self.assertEqual(runlog.load("gate", self.log), [])

    def test_fresh_writes_nothing(self):
        library_watch.main([], run=self.fake([run_(at="2026-10-24T02:41:00Z")]), log_dir=self.log, now=t("2026-10-24T03:17"))
        self.assertEqual(runlog.load("gate", self.log), [])


class Workflows(unittest.TestCase):
    def test_background_runs_watch_and_commits_tried(self):
        y = (ROOT / ".github/workflows/background.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/library_watch.py", y)
        self.assertIn("steps.libkick.outputs.tried", y)
        i = y.index("library_watch.py")
        self.assertLess(i, y.index("python scripts/gate.py check"))   # 判断の段より前（落ちてもここは通る）

    def test_users_only_skips_refresh(self):
        y = (ROOT / ".github/workflows/library.yml").read_text(encoding="utf-8")
        self.assertIn("users_only:", y)
        self.assertIn("!inputs.users_only", y)


if __name__ == "__main__":
    unittest.main()
