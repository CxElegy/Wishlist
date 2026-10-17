"""版面の「更新中」の帯：収集が版面ごとに、抓完したその場で状態を書くこと（digest.ingest → live_mark）。ネットワークには出ない。"""

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
        with mock.patch.object(digest, "LIVE_EDIT_FILE", tmp), mock.patch.object(digest, "unedited", lambda: ["A", "B"]), \
                mock.patch.object(digest, "_run_min", lambda proc, d: 20), \
                mock.patch.object(livestatus, "report", lambda b, p, s, note=None, eta=None: calls.append((b, p, s, note, round(eta)))):
            digest.live_edit()
            digest._live_edit_step("AI が配図を選んでいます")
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


if __name__ == "__main__":
    unittest.main()
