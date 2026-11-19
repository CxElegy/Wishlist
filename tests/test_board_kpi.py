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


GOOD_C = dict(picked=0, follow=2, board=2, raw=15, pending=25, emblem=4, edited=300, page=15, page_emblem=8, photo=16)
GOOD_B = dict(picked=0, follow=2, raw=15, emblem=0, page=15, photo=16)
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
        c = {k: v for k, v in GOOD_C.items() if k not in ("emblem", "page_emblem", "edited", "photo")}
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

    def test_photo_stage_counts_real_photos_in_the_board(self):
        """本物の写真（記事自身の写真 data-o="1"）が版面に min(3, カード数) 枚。備えの絵（data-o="0"）・ほかの版面の写真は数えない。"""
        def card(o):
            return f'<article class="card a c3"><img src="x" alt="" data-e="s" data-o="{o}"></article>'
        html = ('<section class="sec" data-k="甲">' + card(1) + card(1) + card(0) + card(1) + '</section>'
                '<section class="sec" data-k="乙">' + card(1) + card(0) + card(0) + '</section>'
                '<section class="sec" data-k="丙">' + card(1) + '</section>')
        self.assertEqual(board_kpi.page_photos(html, "甲"), (4, 3))
        self.assertTrue(board_kpi.photo_ok(html, "甲"))
        self.assertFalse(board_kpi.photo_ok(html, "乙"))   # 3 枚のうち 1 枚だけ本物
        self.assertTrue(board_kpi.photo_ok(html, "丙"))    # カード 1 枚なら 1 枚で足りる
        self.assertFalse(board_kpi.photo_ok(html, "丁"))
        code, _, j = self.report([[board("C", **{k: v for k, v in GOOD_C.items() if k != "photo"})]], now_min=21)
        self.assertEqual([x["stage"] for x in j["red"]], ["photo"])   # 経路 C は 20 分未満

    def test_names_with_marks_and_red_without_names(self):
        """見直し 11：名前に & や " があっても render の data-k（html.escape）と合う。red（repo に入る latest.json）に版面の名前を出さない。"""
        nm = 'A&B "C"'
        card = '<article class="card a c3"><img src="x" alt="" data-e="s" data-o="1"></article>'
        html = f'<section class="sec" data-k="{board_kpi.htmlmod.escape(nm)}">' + card * 3 + '<div class="emb x"></div></section>'
        self.assertTrue(board_kpi.photo_ok(html, nm))
        self.assertTrue(board_kpi.page_has_emblem(html, nm))
        code, out, j = self.report([[{**board("C", name="秘密の版面", **{k: v for k, v in GOOD_C.items() if k != "photo"}), "board_id": 42}]], now_min=21)
        self.assertEqual([(x["board"], x["stage"]) for x in j["red"]], [(42, "photo")])
        self.assertNotIn("秘密の版面", json.dumps(j["red"], ensure_ascii=False))

    def test_photo_mix_in_report(self):
        b = {**board("C", **GOOD_C), "photos": {"n": 10, "img": 7, "wrapped": 2, "waiting": 3}}
        code, out, j = self.report([[b]])
        self.assertEqual(j["photos"]["C"], {"n": 10, "img_pct": 70, "wrapped_pct": 20, "waiting_pct": 30})
        self.assertIn("写真 経路 C", out)

    def test_page_has_emblem(self):
        html = '<section class="sec" data-k="甲"><div class="emb ring-accent"></div></section><section class="sec" data-k="乙"><p>x</p></section>'
        self.assertTrue(board_kpi.page_has_emblem(html, "甲"))
        self.assertFalse(board_kpi.page_has_emblem(html, "乙"))
        self.assertFalse(board_kpi.page_has_emblem(html, "丙"))


class KickAndFastLog(unittest.TestCase):
    """2026-11-19：起こし（db/board_added.sql）が入っていなければ保険の道（毎時）だけで最大 60 分遅れ。PC が点検する。
    速い道の版面ごとの秒（library_emblem.fresh_main の行）を PC がログから読む。"""

    @staticmethod
    def fq(**over):
        rows = {"pg_proc": [["1"]], "position": [["1", "1"]], "vault": [["1"]], "pg_extension": [["1"]],
                "board_kicks": [["2", "2026-11-19 04:00:00+00"]], "_http_response": [["204", "2"]], **over}

        def q(sql):
            for k, v in rows.items():
                if k in sql:
                    if isinstance(v, Exception):
                        raise v
                    return v
            return []
        return q

    def test_all_in(self):
        st = board_kpi.kick_state(self.fq())
        self.assertTrue(st["ok"], st["why"])
        self.assertEqual(st["kicks_24h"], 2)

    def test_missing_pieces_are_red(self):
        st = board_kpi.kick_state(self.fq(pg_proc=[["0"]], position=[["0", "0"]], vault=[["0"]], _http_response=[["401", "1"]]))
        self.assertFalse(st["ok"])
        self.assertEqual(len(st["why"]), 4)
        st = board_kpi.kick_state(self.fq(board_kicks=RuntimeError("relation does not exist")))   # 表が無い
        self.assertIn("kicks_error", st)

    def test_kick_never_reads_the_secret_value(self):
        self.assertNotIn("decrypted", " ".join(board_kpi.KICK_SQL.values()))

    def test_fast_times_parse_the_library_emblem_line(self):
        src = (pathlib.Path(board_kpi.ROOT) / "scripts" / "library_emblem.py").read_text(encoding="utf-8")
        self.assertIn("速い道の時刻 版面 {bid}：取り始め {m['claim']}・1 枚目 {m.get('first', '—')}・書いた {m.get('write', '—')}・ページ {m.get('page', '—')}", src)
        got = board_kpi.fast_times("emblem (1)\t2026 速い道の時刻 版面 41：取り始め +93s・1 枚目 +171s・書いた +174s・ページ +186s（終了 1）\n"
                                   "速い道の時刻 版面 42：取り始め +95s・1 枚目 —・書いた +190s・ページ —")
        self.assertEqual(got, [{"board": 41, "claim": 93, "first": 171, "write": 174, "page": 186, "why": "小元素あり"},
                               {"board": 42, "claim": 95, "first": None, "write": 190, "page": None, "why": "失敗"}])
        got = board_kpi.fast_times("速い道の時刻 版面 43：取り始め +90s・1 枚目 —・書いた +170s・ページ —・結果 候補が通らず\n"
                                   "速い道の時刻 版面 44：取り始め +90s・1 枚目 —・書いた +100s・ページ —・結果 候補なし\n"
                                   "速い道の時刻 版面 45：取り始め +90s・1 枚目 +150s・書いた +155s（書けず）・ページ +200s（終了 1）・結果 小元素あり")
        self.assertEqual([(x["board"], x["why"], x["page"]) for x in got], [(43, "候補が通らず", None), (44, "候補なし", None), (45, "小元素あり", 200)])

    def test_report_counts_fast_results_apart(self):
        """2026-11-19 F4：速い道が上限まで試して 0 枚の版面は、小元素の段の「まだ出ない」（赤）にせず「候補が通らず／候補なし」で数える。"""
        run = {"t0": at(0), "boards": [dict(board("C", "a", **{k: v for k, v in GOOD_C.items() if k not in ("emblem", "page_emblem")}), fast="候補が通らず"),
                                       board("C", "b", **GOOD_C)]}
        red = board_kpi.judge(run, T0 + dt.timedelta(minutes=500))
        self.assertFalse([x for x in red if x["stage"] in ("emblem", "page_emblem")])
        run["boards"][0].pop("fast")
        red = board_kpi.judge(run, T0 + dt.timedelta(minutes=500))
        self.assertTrue([x for x in red if x["stage"] == "emblem"])   # 結果が分からない 0 枚は今までどおり赤


if __name__ == "__main__":
    unittest.main()
