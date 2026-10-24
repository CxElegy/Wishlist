"""版面の「更新中」の帯：収集が版面ごとに、抓完したその場で状態を書くこと（digest.ingest → live_mark）。ネットワークには出ない。"""

import json
import pathlib
import sys
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402


class LiveMark(unittest.TestCase):
    def test_each_board_updates_when_its_fetch_ends(self):
        calls, t0 = [], time.time()
        items = [{"name": "A"}, {"name": "B", "dedupe_others": True}, {"name": "C"}]
        delay = {"A": 0.05, "B": 0.4, "C": 0.15}
        raw = {"A": ["x", "y"], "B": ["x", "z"], "C": []}   # B の x は A がもう収めた記事

        def collect(item, conf):
            time.sleep(delay[item["name"]])
            return raw[item["name"]]

        def mark(board, state=None, found=0, started=None, eta=None, proc="collect"):
            calls.append((time.time() - t0, board, state, found))

        patches = dict(live_mark=mark, collect=collect, load_config=lambda: ({"timezone": "Asia/Tokyo"}, items),
                       seen_from_inbox=set, recent_titles=dict, has_history=lambda n: True, load_json=lambda p: {},
                       save_json=lambda p, d: None, merge_inbox=lambda a, b: b, status_facts=lambda i, s, f: ([], None),
                       find_cover=lambda i, c: None, is_urgent=lambda e, i: False, entry_to_dict=lambda n, e: {"n": n},
                       title_key=lambda t: "k:" + t,
                       filter_entries=lambda r, item, conf, seen, now, cmp: [NS(url=u, title=u) for u in r if u not in cmp and u not in seen])
        with mock.patch.multiple(digest, **patches):
            digest.ingest()
        by = [(b, s, n) for _, b, s, n in calls]
        self.assertEqual(by[0], (None, None, 0))                    # 最初に前回の行を消す
        self.assertIn(("C", None, 0), by)                            # 新着なし → 帯が消える
        t = {(b, s, n): x for x, b, s, n in calls}
        self.assertLess(t[("A", "found", 2)], t[("B", "found", 2)])  # 早く抓け終わった A は B を待たない
        self.assertLess(t[("C", None, 0)], 0.35)
        self.assertEqual(by[-1], ("B", "found", 1))                  # 順番の去重で件数が変わったら直す
        self.assertEqual(by.count(("A", "found", 2)), 1)             # 変わらない版面は 2 回書かない

    def test_ai_edit_moves_the_bar_along(self):
        """AI 編集：live-edit で今日まだ編集していない版面に「編集中」→ pick-images の途中で「配図」→ 出刊で「反映待ち」。"""
        import tempfile
        import livestatus
        calls = []
        tmp = pathlib.Path(tempfile.mkdtemp()) / "live-edit.json"
        with mock.patch.object(digest, "LIVE_EDIT_FILE", tmp), mock.patch.object(digest, "edit_queue", lambda *a, **k: [[("A", 3), ("B", 1)]]), \
                mock.patch.object(digest, "_run_min", lambda proc, d: 20), \
                mock.patch.object(livestatus, "report", lambda b, p, s, note=None, eta=None: calls.append((b, p, s, note, round(eta)))):
            digest.live_edit()
            digest._live_edit_step("AI が配図を選んでいます")
            digest._live_edit_step("編集済み · 網页への反映を待っています", digest.LIVE_AFTER_MIN, only={"A"})   # 第 1 バッチ（A だけ終わった）
            self.assertEqual([c[0] for c in calls if c[3].startswith("編集済み")], ["A"])   # まだの B は「編集中」のまま
            run = digest._live_edit_step("編集済み · 網页への反映を待っています", digest.LIVE_AFTER_MIN)
        self.assertEqual(calls[:2], [("A", "edit", "work", "AI が編集しています", 23), ("B", "edit", "work", "AI が編集しています", 23)])
        self.assertEqual(calls[2][2:4], ("work", "AI が配図を選んでいます"))
        self.assertEqual(calls[-1][2], "wait")              # 出刊したら「反映待ち」
        self.assertEqual(run["boards"], ["A", "B"])          # 出刊の記録に、かかった時間（secs）を付けられる

    def test_typical_minutes_learn_from_runs(self):
        import tempfile
        import runlog
        d = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(runlog.typical("collect", "secs", 290, log_dir=d), 290)   # 記録がなければ既定値
        for secs in (100, 400, 300, 200, 9999):
            runlog.add("collect", "x", log_dir=d, secs=secs)
        self.assertEqual(runlog.typical("collect", "secs", 290, log_dir=d), 300)   # 中央値（外れ値に引っぱられない）
        self.assertEqual(runlog.typical("collect", "secs", 290, n=2, log_dir=d), 9999)   # 最近の n 回だけ


class EditBatches(unittest.TestCase):
    """AI 編集の分批（1 版面ずつ編集 → 出刊 → push）：順番・一時停止・やり直し・トークンの記録。"""

    def setUp(self):
        self.ctl = {"mode": "run", "redo": []}
        p = mock.patch.object(digest, "edit_control", lambda: self.ctl)   # 本物のデータベースには行かない
        p.start()
        self.addCleanup(p.stop)
        self.sets = []
        q = mock.patch.object(digest, "set_edit_control", lambda **k: self.sets.append(k))
        q.start()
        self.addCleanup(q.stop)

    def _inbox(self, d):
        items = [{"name": n, "entries": [{}] * k} for n, k in (("A", 3), ("B", 9), ("G", 4))]
        (d / "2026-10-19.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        (d / "2026-10-19.edit.json").write_text(json.dumps({"G": [], "_covered": {"G": 4}}), encoding="utf-8")

    def test_pause_step_and_redo(self):
        import tempfile
        import runlog
        d = pathlib.Path(tempfile.mkdtemp())
        self._inbox(d)
        run = d / "run.json"
        run.write_text(json.dumps({"start": 1, "batch": 0}), encoding="utf-8")
        with mock.patch.object(digest, "INBOX_DIR", d), mock.patch.object(digest, "LIVE_EDIT_FILE", run), \
                mock.patch.object(digest, "undesigned", lambda *a: []), \
                mock.patch.object(runlog, "add", lambda *a, **k: None):
            self.assertEqual(digest.edit_next(), ("NEXT", "B"))              # 整理待ちの多い順に 1 つずつ
            self.assertEqual(json.loads(run.read_text())["current"], "B")
            self.ctl = {"mode": "run", "redo": ["G"]}                         # 管理ページで「G をやり直す」
            self.assertEqual(digest.edit_next(ctl=self.ctl), ("NEXT", "G"))   # 編集済みでもいちばん先に
            self.assertEqual(digest.edit_next(ctl={"mode": "pause", "redo": []})[0], "STOP")
            run.write_text(json.dumps({"start": 1, "batch": 1}), encoding="utf-8")
            self.assertEqual(digest.edit_next(ctl={"mode": "step", "redo": []})[0], "STOP")   # 1 版面ずつ：1 つ終わったら止める
        self.assertEqual(self.sets, [{"mode": "pause"}])                     # 止めるときに pause に戻す

    def test_queue_most_pending_first(self):
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp())
        items = [{"name": n, "entries": [{}] * k} for n, k in (("A", 3), ("B", 9), ("C", 1), ("D", 5), ("E", 2), ("F", 7), ("G", 4))]
        (d / "2026-10-19.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        (d / "2026-10-19.edit.json").write_text(json.dumps({"G": [], "_covered": {"G": 4}}), encoding="utf-8")   # G は編集済み
        with mock.patch.object(digest, "INBOX_DIR", d):
            q = digest.edit_queue(batch=5, ctl={"mode": "run", "redo": []})
        self.assertEqual([[n for n, _ in b] for b in q], [["B", "F", "D", "A", "E"], ["C"]])

    def test_brief_is_short_and_per_batch(self):
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp())
        ent = lambda n: {"n": n, "date": "2026-10-19T01:00:00+00:00", "source": "4Gamer", "title": f"t{n}",
                         "summary": "x" * 500, "url": "https://example.com/very/long/url", "image": "https://img.example.com/a.jpg"}
        items = [{"name": "A", "entries": [ent(1), ent(2)]}, {"name": "B", "entries": [ent(1)]}]
        (d / "2026-10-19.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        with mock.patch.object(digest, "INBOX_DIR", d):
            out = digest.edit_brief(batch=1)
            b2 = digest.edit_brief(batch=3)
        self.assertIn("## A（2 件", out)                   # 1 版面ずつ：第 1 バッチは整理待ちの多い A だけ
        self.assertNotIn("## B", out)
        self.assertNotIn("https://", out)                 # 網址は読ませない
        self.assertIn("x" * 120 + "\n", out + "\n")       # 要約は 120 字まで
        self.assertNotIn("x" * 121, out)
        self.assertEqual(b2, "")                          # 2 版面なら 2 バッチまで

    def test_admin_token_panel(self):
        import render
        d = {"today": {"in": 10, "cw": 20000, "cr": 300000, "out": 5000}, "week": {"in": 10, "cw": 20000, "cr": 300000, "out": 5000},
             "runs": [{"when": "10/19 18:05", "at": "x", "sum": {"in": 10, "cw": 20000, "cr": 300000, "out": 5000},
                       "batches": [{"when": "18:12", "batch": 1, "boards": ["<GTA 6>"], "stories": 3,
                                    "tok": {"in": 10, "cw": 20000, "cr": 300000, "out": 5000}, "total": 325010}]}]}
        h = render._admin_edit_tokens(d)
        self.assertIn("第 1 バッチ", h)
        self.assertIn("&lt;GTA 6&gt;", h)
        self.assertIn("2.5万", h)                          # 新規入力＋出力
        self.assertIn("まだ記録がありません", render._admin_edit_tokens({}))
        self.assertIn('id="tokens"', "".join(render.render_admin({"edit_tokens": d}, {}, "u").values()))

    def test_session_usage_counts_each_reply_once(self):
        import tempfile
        import usage
        f = pathlib.Path(tempfile.mkdtemp()) / "s.jsonl"
        u = lambda i, o: {"input_tokens": i, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100, "output_tokens": o}
        lines = [{"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "usage": u(1, 5)}},
                 {"type": "assistant", "message": {"id": "m1", "model": "claude-sonnet-5-5", "usage": u(1, 50)}},   # 同じ返事の続き
                 {"type": "user", "message": {"content": "x"}},
                 {"type": "assistant", "message": {"id": "m2", "model": "claude-sonnet-5-5", "usage": u(2, 7)}}]
        f.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n", encoding="utf-8")
        got = usage.session_usage(f)
        self.assertEqual((got["in"], got["cw"], got["cr"], got["out"], got["calls"]), (3, 20, 200, 57, 2))
        d = usage.diff(got, {"in": 1, "cw": 10, "cr": 100, "out": 50, "calls": 1})
        self.assertEqual((d["in"], d["out"], d["calls"]), (2, 7, 1))   # 前のバッチからの差
        self.assertIn("出力 7", usage.short(d))
        self.assertIsNone(usage.session_usage(pathlib.Path(tempfile.mkdtemp()) / "none.jsonl"))


if __name__ == "__main__":
    unittest.main()
