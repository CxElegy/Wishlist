import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pc_watch as pw  # noqa: E402

T0 = dt.datetime(2026, 11, 7, 0, 0, tzinfo=dt.timezone.utc)


class Decide(unittest.TestCase):
    def test_first_run_up_is_silent(self):
        self.assertIsNone(pw.decide({}, True, T0)[1])

    def test_going_down_tells_once_then_reminds(self):
        s, kind = pw.decide({}, False, T0)
        self.assertEqual(kind, "down")
        s, kind = pw.decide(s, False, T0 + dt.timedelta(hours=1))
        self.assertIsNone(kind)
        s, kind = pw.decide(s, False, T0 + dt.timedelta(hours=6))
        self.assertEqual(kind, "still")
        self.assertEqual(s["down_since"], T0.isoformat(timespec="seconds"))

    def test_recovery_tells_and_clears(self):
        s, _ = pw.decide({}, False, T0)
        s2, kind = pw.decide(s, True, T0 + dt.timedelta(hours=1))
        self.assertEqual(kind, "up")
        self.assertNotIn("down_since", s2)


class Check(unittest.TestCase):
    def test_blip_is_not_down(self):
        answers = iter([(False, "HTTP 502"), (True, "HTTP 401")])
        self.assertTrue(pw.check("u", probe_fn=lambda _: next(answers), sleep=lambda _: None)[0])

    def test_all_failures_are_down(self):
        ok, why = pw.check("u", probe_fn=lambda _: (False, "HTTP 502"), sleep=lambda _: None)
        self.assertFalse(ok)
        self.assertEqual(why, "HTTP 502")


class BaseUrl(unittest.TestCase):
    def test_reads_setting(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "items.yaml")
            with open(p, "w", encoding="utf-8") as f:
                f.write('settings:\n  supabase_url: "https://x.example.net/"\n')
            self.assertEqual(pw.base_url(p), "https://x.example.net")

    def test_real_setting_is_https(self):
        self.assertTrue(pw.base_url(os.path.join(os.path.dirname(__file__), "..", "items.yaml")).startswith("https://"))


if __name__ == "__main__":
    unittest.main()
