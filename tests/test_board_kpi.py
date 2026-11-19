"""新規登録の通しの目標（harness/board_kpi.py）。目標を割ったら赤・終了コード 1。DB なし（RUNS・OUT を作り物に差し替える）。"""
import contextlib
import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import board_kpi  # noqa: E402

T0 = dt.datetime(2026, 11, 19, 0, 0, tzinfo=dt.timezone.utc)


def at(minutes):
    return (T0 + dt.timedelta(minutes=minutes)).isoformat(timespec="seconds")


def board(path, name="作品", **mins):
    return {"name": name, "path": path, "seen": {k: at(v) for k, v in mins.items()}}


GOOD_C = dict(picked=0, follow=2, board=2, raw=15, pending=25, emblem=4, edited=300, page=15, page_emblem=8)
GOOD_B = dict(picked=0, follow=2, raw=15, emblem=0, page=15)
GOOD_A = dict(picked=0, page=10)


class Kpi(unittest.TestCase):
    def report(self, runs, args=(), now_min=60):
        d = pathlib.Path(tempfile.mkdtemp())
        files = []
        for i, boards in enumerate(runs):
            f = d / f"run{i}.json"
            f.write_text(json.dumps({"t0": at(0), "email": "test-c@example.com", "account": "u_x", "boards": boards}), encoding="utf-8")
            files.append(str(f))
        out = d / "latest.json"
        ns = board_kpi.argparse.Namespace(runs=files, no_fail="--no-fail" in args, days=3)
        buf, code = io.StringIO(), 0
        with mock.patch.object(board_kpi, "OUT", out), mock.patch.object(board_kpi, "now", lambda: T0 + dt.timedelta(minutes=now_min)), contextlib.redirect_stdout(buf):
            try:
                board_kpi.cmd_report(ns)
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue(), json.loads(out.read_text(encoding="utf-8"))

    def test_green_when_all_under_target(self):
        code, _, j = self.report([[board("C", **GOOD_C), board("B", **GOOD_B), board("A", **GOOD_A)]])
        self.assertEqual((code, j["red"]), (0, []))
        self.assertTrue(j["boards"]["C"]["emblem"]["ok"])

    def test_emblem_five_minutes_is_red(self):
        code, out, j = self.report([[board("C", **{**GOOD_C, "emblem": 4.9})]])
        self.assertEqual(code, 0)
        code, out, j = self.report([[board("C", **{**GOOD_C, "emblem": 5})]])   # 「未満」：ちょうどは赤
        self.assertEqual(code, 1)
        self.assertEqual([(x["path"], x["stage"], x["minutes"], x["target"]) for x in j["red"]], [("C", "emblem", 5.0, 5)])
        self.assertIn("赤 経路 C", out)
        self.assertIn("目標 5 分未満", out)

    def test_no_fail_keeps_exit_zero_but_lists_red(self):
        code, out, j = self.report([[board("C", **{**GOOD_C, "emblem": 30})]], args=("--no-fail",))
        self.assertEqual(code, 0)
        self.assertEqual(len(j["red"]), 1)
        self.assertIn("赤 経路 C", out)

    def test_never_appearing_stage_is_red_after_24h(self):
        c = {k: v for k, v in GOOD_C.items() if k != "emblem"}
        code, _, j = self.report([[board("C", **c)]], now_min=24 * 60 + 1)
        self.assertEqual(code, 1)
        self.assertIn(("emblem", "出ないまま"), [(x["stage"], x["why"]) for x in j["red"]])

    def test_unseen_stage_waits_until_target_then_red(self):
        c = {k: v for k, v in GOOD_C.items() if k not in ("emblem", "page_emblem", "edited")}
        code, _, j = self.report([[board("C", **c)]], now_min=3)
        self.assertEqual((code, j["red"]), (0, []))   # まだ 3 分：5 分の目標には間がある
        code, _, j = self.report([[board("C", **c)]], now_min=6)
        self.assertEqual(code, 1)
        self.assertEqual([x["stage"] for x in j["red"]], ["emblem"])   # 6 分たって小元素が無い（page_emblem は 10 分・edited は 480 分まで待つ）

    def test_paths_a_b_do_not_wait_for_emblem(self):
        a = board("A", **GOOD_A)   # 小元素の段は無い（店長の号の写し）
        b = board("B", **{**GOOD_B, "emblem": 0})
        code, _, j = self.report([[a, b]], now_min=24 * 60 + 1)
        self.assertEqual((code, j["red"]), (0, []))
        code, _, j = self.report([[board("B", **{**GOOD_B, "emblem": 20})]])   # B で小元素がまだ無かった（足した時点で既にあるはず）
        self.assertEqual([(x["path"], x["stage"]) for x in j["red"]], [("B", "emblem")])

    def test_page_has_emblem(self):
        html = '<section class="sec" data-k="甲"><div class="emb ring-accent"></div></section><section class="sec" data-k="乙"><p>x</p></section>'
        self.assertTrue(board_kpi.page_has_emblem(html, "甲"))
        self.assertFalse(board_kpi.page_has_emblem(html, "乙"))
        self.assertFalse(board_kpi.page_has_emblem(html, "丙"))


if __name__ == "__main__":
    unittest.main()
