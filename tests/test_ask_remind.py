"""あなた待ちの Discord（harness/ask_remind.py）：いつ送るか。ネットには出ない。"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import ask_remind as ar  # noqa: E402

DAY = dt.datetime(2026, 10, 24, 3, 0, tzinfo=dt.timezone.utc).timestamp()     # 日本時間 12:00
NIGHT = dt.datetime(2026, 10, 24, 17, 0, tzinfo=dt.timezone.utc).timestamp()  # 日本時間 2:00


class Plan(unittest.TestCase):
    ITEMS = ar.asks("- [x] 済み\n- [?] 名前 — 案を選ぶ\n- [ ] これから\n")

    def test_new_is_sent_with_mention(self):
        send, st = ar.plan(self.ITEMS, {}, DAY)
        self.assertEqual([s[0] for s in send], ["名前"])
        self.assertTrue(send[0][2])
        self.assertIn("<@1>", ar.payload(send, "<@1>")["content"])

    def test_every_5_min_then_3_hours(self):
        st = {"名前": {"first": DAY, "last": DAY, "count": 1}}
        self.assertEqual(ar.plan(self.ITEMS, st, DAY + 120)[0], [])          # 2 分後はまだ
        self.assertEqual(len(ar.plan(self.ITEMS, st, DAY + 300)[0]), 1)      # 5 分後に再送
        st["名前"]["count"] = ar.FAST_TIMES
        self.assertEqual(ar.plan(self.ITEMS, st, DAY + 600)[0], [])          # 12 回のあとは 3 時間おき
        self.assertEqual(len(ar.plan(self.ITEMS, st, DAY + 3 * 3600)[0]), 1)

    def test_night_and_answered(self):
        st = {"名前": {"first": NIGHT - 900, "last": NIGHT - 900, "count": 2}}
        self.assertEqual(ar.plan(self.ITEMS, st, NIGHT)[0], [])              # 夜は繰り返さない
        self.assertEqual(ar.plan({}, st, DAY)[1], {})                         # [?] が消えたら止める


if __name__ == "__main__":
    unittest.main()
