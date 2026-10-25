"""持ち主のいない [~] を次の係が取る・動いている持ち主の新しい [~] は飛ばす（harness/claims.py）。"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import claims as c  # noqa: E402

NOW = dt.datetime(2026, 10, 26, 9, 0, tzinfo=c.JST)
BL = """- [x] 済み
- [~] 動いている係の段 （開始 2026-10-26 08:50 JST・持ち主 wf_a）
- [~] 止まった係の段 （開始 2026-10-26 08:50 JST・持ち主 wf_dead）
- [~] 60 分たった段 （開始 2026-10-26 07:40 JST・持ち主 wf_a）
- [~] 更新した段 （開始 2026-10-26 07:00 JST・最終 2026-10-26 08:55 JST・持ち主 wf_a）
- [~] 前の書き方の段 （開始 2026-10-25・依頼の係）
- [ ] まだの段
"""


class Claims(unittest.TestCase):
    def test_orphans(self):
        bad = [x["step"].split()[0] for x in c.orphans(BL, ["wf_a"], NOW)]
        self.assertEqual(bad, ["止まった係の段", "60", "前の書き方の段"])   # 動いている持ち主の新しい [~]・更新した [~] は飛ばす

    def test_no_live_list_means_only_age(self):
        # 動いている Run が分からないときは全部取り直してよい（持ち主が見えないので）
        self.assertEqual(len(c.orphans(BL, [], NOW)), 5)

    def test_real_backlog_parses(self):
        t = (pathlib.Path(__file__).resolve().parent.parent / "BACKLOG.md").read_text(encoding="utf-8")
        self.assertTrue(all(x["step"] for x in c.parse(t)))


if __name__ == "__main__":
    unittest.main()
