"""harness/lock.py の先着順（整理券）：待つ人は lockq/<名前>/ に並び、先頭だけが取れる。死んだ待ち人・死んだ持ち主は pid で外す。"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import lock  # noqa: E402

ME = os.getpid()


class Fifo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = pathlib.Path(self.tmp.name)
        self.now = [1_800_000_000.0]
        self.alive_pids = {ME, 111, 222}

    def kw(self, **extra):
        def sleep(s):
            self.now[0] += s
            if extra.get("on_sleep"):
                extra["on_sleep"]()
        return dict(state=self.state, sleep=sleep, clock=lambda: self.now[0], alive=lambda p: p in self.alive_pids)

    def ticket(self, n, pid):
        qd = self.state / "lockq" / "ci"
        qd.mkdir(parents=True, exist_ok=True)
        f = qd / f"{n:020d}-{pid}.json"
        f.write_text(json.dumps({"pid": pid, "since": self.now[0], "who": "x"}), encoding="utf-8")
        return f

    def left(self):
        qd = self.state / "lockq" / "ci"
        return sorted(p.name for p in qd.glob("*.json")) if qd.is_dir() else []

    def test_free_lock_but_someone_ahead_does_not_cut_in(self):
        self.ticket(1, 111)
        self.assertIsNone(lock.acquire("ci", wait=20, **self.kw()))
        self.assertFalse((self.state / "locks" / "ci").exists())   # 先の人がいるので取っていない
        self.assertEqual(len(self.left()), 1)                       # 自分の整理券は返した・先の人のは残る

    def test_dead_waiter_ahead_is_dropped(self):
        self.ticket(1, 999)   # 死んだ pid
        d = lock.acquire("ci", wait=0, **self.kw())
        self.assertTrue(d and d.is_dir())
        self.assertEqual(self.left(), [])

    def test_takes_over_in_order_when_ahead_finishes(self):
        first = self.ticket(1, 111)
        self.ticket(2, 222)
        calls = []

        def leave():
            calls.append(1)
            if first.exists():
                first.unlink()   # 先頭の人が取って終わった
        # 222 は自分より先だが生きている → 自分は 3 番目。222 も出るまで取れない
        self.alive_pids.discard(222)   # 222 は死んだ
        d = lock.acquire("ci", wait=60, **self.kw(on_sleep=leave))
        self.assertTrue(d and d.is_dir())
        self.assertGreaterEqual(len(calls), 1)

    def test_dead_holder_is_taken_over_at_once(self):
        d = self.state / "locks" / "ci"
        d.mkdir(parents=True)
        (d / "owner.json").write_text(json.dumps({"pid": 999, "since": self.now[0], "who": "dead"}), encoding="utf-8")
        got = lock.acquire("ci", wait=0, **self.kw())
        self.assertTrue(got)
        self.assertEqual(json.loads((got / "owner.json").read_text(encoding="utf-8"))["pid"], ME)

    def test_live_holder_blocks_and_ticket_is_returned(self):
        d = self.state / "locks" / "ci"
        d.mkdir(parents=True)
        (d / "owner.json").write_text(json.dumps({"pid": 111, "since": self.now[0], "who": "live"}), encoding="utf-8")
        self.assertIsNone(lock.acquire("ci", wait=10, **self.kw()))
        self.assertEqual(self.left(), [])

    def test_queue_is_not_a_lock_in_status(self):
        self.ticket(1, 111)
        self.assertEqual(lock.status(self.state), {})
        self.assertEqual([w["pid"] for w in lock.waiting("ci", self.state, lambda p: True)], [111])

    def test_alive_for_self_and_garbage(self):
        self.assertTrue(lock._alive(ME))
        self.assertFalse(lock._alive(None))
        self.assertFalse(lock._alive(0))


if __name__ == "__main__":
    unittest.main()
