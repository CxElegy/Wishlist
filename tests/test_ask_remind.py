"""質問と報告の Discord（harness/ask_remind.py）：いつ送るか。ネットには出ない。"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import ask_remind as ar  # noqa: E402

DAY = dt.datetime(2026, 10, 24, 3, 0, tzinfo=dt.timezone.utc).timestamp()     # 日本時間 12:00
NIGHT = dt.datetime(2026, 10, 24, 17, 0, tzinfo=dt.timezone.utc).timestamp()  # 日本時間 2:00


class Step(unittest.TestCase):
    def test_ask_then_remind_then_clear(self):
        msg, st = ar.step("ask", "頭条はどれ？", {}, DAY, "<@1>")
        self.assertIn("<@1>", msg)
        self.assertIsNone(ar.step("tick", "", st, DAY + 120, "<@1>")[0])         # 2 分後はまだ
        msg, st = ar.step("tick", "", st, DAY + 300, "<@1>")                      # 5 分後に再送
        self.assertIn("まだお返事待ち", msg)
        st["count"] = ar.FAST_TIMES
        self.assertIsNone(ar.step("tick", "", st, DAY + 600, "<@1>")[0])         # 1 時間のあとは 30 分おき
        self.assertIsNotNone(ar.step("tick", "", st, DAY + 300 + 1800, "<@1>")[0])
        self.assertEqual(ar.step("clear", "", st, DAY, "<@1>")[1], {})             # 答えたら止める
        self.assertIsNone(ar.step("tick", "", {}, DAY, "<@1>")[0])

    def test_night_and_say(self):
        st = {"text": "x", "first": NIGHT - 900, "last": NIGHT - 900, "count": 2}
        self.assertIsNone(ar.step("tick", "", st, NIGHT, "<@1>")[0])               # 夜は繰り返さない
        msg, st2 = ar.step("say", "収集のタイミングを直しています", st, DAY, "<@1>")
        self.assertNotIn("<@1>", msg)                                              # 報告は @ なし
        self.assertEqual(st2, st)                                                  # 待ちはそのまま


if __name__ == "__main__":
    unittest.main()
