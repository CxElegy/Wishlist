import unittest
from unittest import mock

import digest
import library
import sbstate

import likefx
import library_design as L
import render

OK = {"motif": "magic", "theme": {"bg": "#141B2D", "fg": "#EEF3F8", "accent": "#8FB8E8", "alt_bg": "#EAF1F7", "alt_fg": "#1C2536", "alt_accent": "#4F7CB0"}}


class LibraryDesign(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(L.missing({}), ["motif", "theme"])
        self.assertEqual(L.missing(OK), [])
        self.assertEqual(L.missing({"motif": "pop"}), ["theme"])

    def test_problems(self):
        self.assertEqual(L.problems(OK, render.MOTIFS, likefx.FX), [])
        self.assertTrue(L.problems({**OK, "motif": "nope"}, render.MOTIFS, likefx.FX))
        self.assertTrue(L.problems({**OK, "theme": {**OK["theme"], "bg": "red"}}, render.MOTIFS, likefx.FX))
        self.assertTrue(L.problems({**OK, "like_fx": "nope"}, render.MOTIFS, likefx.FX))


class AutoDesign(unittest.TestCase):
    """--auto：偽の DB（人物・ゲーム・題材の版面とデザイン済みの版面）に、規則だけで足す。"""

    def setUp(self):
        self.boards = [{"id": 1, "name": "テスト人物", "config": {}}, {"id": 2, "name": "テストゲーム", "config": {"keywords": ["x"]}},
                       {"id": 3, "name": "テスト題材", "config": None}, {"id": 4, "name": "済み", "config": dict(OK)}]
        self.follows = [{"board_id": 1, "section": "演出"}, {"board_id": 2, "section": "游戏"}, {"board_id": 3, "section": "生活"}]
        self.puts = []

        def fake_sb(path, *a, **k):
            return self.boards if path.startswith("boards?") else self.follows

        def fake_put(bid, add):
            self.puts.append(bid)
            b = next(x for x in self.boards if x["id"] == bid)
            b["config"] = {**(b["config"] or {}), **add}
            return b["config"]
        self.p = [mock.patch.object(digest, "supabase", side_effect=fake_sb), mock.patch.object(library, "put_config", side_effect=fake_put)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_auto_fills_three_types(self):
        self.assertEqual(L.main(["--auto"]), 0)
        for b in self.boards:
            self.assertEqual(L.missing(b["config"]), [], b["id"])
            self.assertEqual(L.problems(b["config"], render.MOTIFS, likefx.FX), [], b["id"])
        self.assertEqual(self.boards[1]["config"]["keywords"], ["x"])   # 足すだけ
        self.assertEqual(self.boards[3]["config"], OK)
        self.assertEqual(sorted(self.puts), [1, 2, 3])   # デザイン済みの版面へは 0 回
        self.assertEqual(self.boards[1]["config"]["motif"], "retro")

    def test_dry_writes_nothing(self):
        self.assertEqual(L.main(["--auto", "--dry"]), 0)
        self.assertEqual(self.puts, [])
        self.assertEqual(L.missing(self.boards[0]["config"]), ["motif", "theme"])

    def test_deterministic_and_idempotent(self):
        self.assertEqual(L.auto_design("a", "游戏"), L.auto_design("a", "游戏"))
        L.main(["--auto"])
        self.puts.clear()
        L.main(["--auto"])
        self.assertEqual(self.puts, [])

    def test_db_unreachable_exits_zero(self):
        sbstate.LIMITED = True
        try:
            with mock.patch.object(digest, "supabase", return_value=None):
                with self.assertRaises(SystemExit) as c:
                    L.main(["--auto"])
            self.assertEqual(c.exception.code, 0)
        finally:
            sbstate.LIMITED = False


if __name__ == "__main__":
    unittest.main()
