"""機能 C（2026-11-05・F9）：お客さまの記事集めがライブラリの版面ごとに board_stories へ書き、user_pages がそこから読む。ネットに出ない。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import library  # noqa: E402
import user_pages  # noqa: E402

FOLLOWS = [{"account": "u_a", "board_id": 7, "boards": {"name": "Astrae Oratio"}},
           {"account": "u_b", "board_id": 7, "boards": {"name": "astrae oratio"}},
           {"account": "u_b", "board_id": 9, "boards": {"name": "広島旅行"}}]


def st(n):
    return [{"title": f"t{i}", "url": f"https://x.example/{i}"} for i in range(n)]


class DB:
    def __init__(self, today=()):
        self.today, self.calls = list(today), []

    def __call__(self, path, body=None, prefer=None, method=None):
        self.calls.append((path, body, prefer))
        if path.startswith("follows?"):
            return FOLLOWS
        if path.startswith("board_stories?day="):
            return [{"board_id": b} for b in self.today]
        return None

    def put(self):
        return [r for p, b, _ in self.calls if p.startswith("board_stories?on_conflict") for r in b]


class BoardStories(unittest.TestCase):
    def test_one_row_per_board_most_stories(self):
        rows = [{"account": "u_a", "item": "Astrae Oratio", "state": "ok", "stories": st(2)},
                {"account": "u_b", "item": "Astrae Oratio", "state": "ok", "stories": st(5)},
                {"account": "u_b", "item": "広島旅行", "state": "ok", "stories": st(1)},
                {"account": "u_c", "item": "だれも追っていない", "state": "ok", "stories": st(3)}]
        self.assertEqual({k: len(v) for k, v in library.board_pending(rows, FOLLOWS).items()}, {7: 5, 9: 1})

    def test_writes_new_day_and_changed_only_pending(self):
        rows = [{"account": "u_a", "item": "Astrae Oratio", "state": "ok", "stories": st(2)},
                {"account": "u_b", "item": "広島旅行", "state": "ok", "stories": st(1)}]
        old = {("u_a", "Astrae Oratio"): rows[0], ("u_b", "広島旅行"): rows[1]}
        db = DB(today=[7, 9])
        self.assertEqual(library.put_stories(db, rows, old, "2026-11-05", log=lambda m: None), 0)   # 今日の行があって変わらない → 書かない
        db = DB(today=[7])
        library.put_stories(db, rows, old, "2026-11-05", log=lambda m: None)
        self.assertEqual([r["board_id"] for r in db.put()], [9])   # 今日の行がまだ無い版面
        db = DB(today=[7, 9])
        library.put_stories(db, [{**rows[0], "stories": st(3)}, rows[1]], old, "2026-11-05", log=lambda m: None)
        put = db.put()
        self.assertEqual([r["board_id"] for r in put], [7])   # 記事が変わった版面
        self.assertNotIn("stories", put[0])   # AI 編集の結果（stories）を集め直しで消さない
        self.assertEqual(len(put[0]["pending"]), 3)

    def test_log_has_no_names(self):
        out = []
        library.put_stories(DB(), [{"account": "u_a", "item": "Astrae Oratio", "state": "ok", "stories": st(1)}], {}, "2026-11-05", log=out.append)
        self.assertTrue(out and all("Astrae" not in m for m in out))

    def test_user_pages_reads_board_first(self):
        follows = [{"boards": {"id": 7, "name": "Astrae Oratio"}}, {"boards": {"id": 9, "name": "広島旅行"}}, {"boards": {"id": 11, "name": "X"}}]
        latest = {7: {"stories": st(2), "pending": st(5)}, 9: {"stories": [], "pending": st(4)}}
        rows = user_pages.board_rows(follows, latest, {"x": {"stories": st(1)}})
        self.assertEqual(len(rows["astraeoratio"]["stories"]), 2)   # AI 編集のあとが先
        self.assertTrue(rows["astraeoratio"]["edited"])
        self.assertEqual(len(rows["広島旅行"]["stories"]), 4)   # まだ編集していなければ整理待ち
        self.assertEqual(len(rows["x"]["stories"]), 1)   # board_stories に無い版面は古い user_boards


if __name__ == "__main__":
    unittest.main()
