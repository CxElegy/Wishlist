"""機能 C④（2026-11-05・F9）：ライブラリの版面（お客さまの版面）にも AI 編集の入口（edit-next の NEXT lib:id → edit-brief → lib-publish）。
店長の版面の記事も board_stories へ。token の上限（1 回 LIB_EDIT_MAX 版面・12 時間は編み直さない）。ネットに出ない。"""
import datetime as dt
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import library  # noqa: E402
import user_pages  # noqa: E402

TODAY = "2026-11-05"
NOW = dt.datetime(2026, 11, 5, 12, tzinfo=dt.timezone.utc)


def pend(n, k=0):
    return [{"title": f"t{i}", "url": f"https://x.example/{i}", "source": "S", "date": TODAY, "summary": "s" * 300} for i in range(k, k + n)]


class DB:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def __call__(self, path, body=None, prefer=None, method=None):
        self.calls.append((path, body, method))
        if path.startswith("board_stories?day=gte"):
            return self.rows
        return None

    def patches(self):
        return [(p, b) for p, b, m in self.calls if m == "PATCH"]


class LibEdit(unittest.TestCase):
    def setUp(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p1 = mock.patch.object(library, "LIB_ROWS", d / "rows.json")
        p2 = mock.patch.object(library, "LIB_DONE", d / "done.json")
        p1.start(), p2.start()
        self.addCleanup(p1.stop), self.addCleanup(p2.stop)

    def row(self, bid, name, pending, stories=(), day=TODAY):
        return {"board_id": bid, "day": day, "pending": pending, "stories": list(stories), "boards": {"name": name}}

    def test_todo_skips_shop_and_edited_orders_by_pending(self):
        p = pend(5)
        done = library.edited_stories(p, [{"headline": "h", "refs": [1]}], library.pending_fp(p), "2026-11-04T00:00:00+00:00")
        db = DB([self.row(1, "A", pend(3)), self.row(2, "B", pend(6)), self.row(3, "GTA 6", pend(9)), self.row(4, "C", p, done)])
        todo = library.edit_todo(db, TODAY, ["GTA 6"], now=NOW)
        self.assertEqual([t[0] for t in todo], [2, 1])   # 店長の版面（3）・同じ整理待ちを編んだ版面（4）は入らない・多い順

    def test_recent_edit_not_redone_old_edit_redone(self):
        old = library.edited_stories(pend(2), [{"refs": [1]}], "other", "2026-11-04T00:00:00+00:00")
        new = library.edited_stories(pend(2), [{"refs": [1]}], "other", "2026-11-05T08:00:00+00:00")
        db = DB([self.row(1, "A", pend(3), old), self.row(2, "B", pend(3), new)])
        self.assertEqual([t[0] for t in library.edit_todo(db, TODAY, now=NOW)], [1])

    def test_carry_over_from_yesterday(self):
        p = pend(4)
        prev = library.edited_stories(p, [{"refs": [1]}], library.pending_fp(p), "2026-11-04T00:00:00+00:00")
        db = DB([self.row(1, "A", p), self.row(1, "A", p, prev, day="2026-11-04")])
        self.assertEqual(library.edit_todo(db, TODAY, now=NOW), [])
        self.assertEqual(db.patches(), [(f"board_stories?board_id=eq.1&day=eq.{TODAY}", {"stories": prev})])

    def test_session_cap(self):
        db = DB([self.row(i, f"B{i}", pend(2)) for i in range(1, 20)])
        for i in range(library.LIB_EDIT_MAX):
            bid = library.edit_todo(db, TODAY, now=NOW)[0][0]
            library.edit_publish(db, bid, [{"refs": [1]}], TODAY, log=lambda m: None)
        self.assertEqual(library.edit_todo(db, TODAY, now=NOW), [])   # token の上限：この回はここまで

    def test_edited_stories_from_refs(self):
        p = pend(3)
        st = library.edited_stories(p, [{"headline": "新作発表", "highlight": "発表", "weight": "lead", "blurb": "b", "refs": [2, 3]},
                                        {"headline": "x", "highlight": "zz", "refs": [9]}, "bad"], "fp", "at")
        self.assertEqual(len(st), 1)   # 範囲外の refs は捨てる
        self.assertEqual((st[0]["url"], st[0]["weight"], st[0]["highlight"], st[0]["refs"]),
                         ("https://x.example/1", "lead", "発表", ["https://x.example/1", "https://x.example/2"]))
        self.assertEqual(library.edited_stories(p, [], "fp", "at"), [{"_fp": "fp", "_at": "at"}])   # 全部見送りも印

    def test_brief_is_short(self):
        db = DB([self.row(5, "A", pend(2))])
        b = library.edit_brief(db, "5", TODAY)
        self.assertIn("ライブラリの版面 5", b)
        self.assertTrue(all(len(line) < 200 for line in b.splitlines()))

    def test_user_pages_uses_edit_and_pending_rest(self):
        p = pend(4)
        st = library.edited_stories(p, [{"headline": "H", "weight": "hero", "refs": [1, 2]}], "fp", "at")
        rows = user_pages.board_rows([{"boards": {"id": 7, "name": "A"}}], {7: {"stories": st, "pending": p}}, {})
        r = rows["a"]
        self.assertTrue(r["edited"])
        self.assertEqual([s["headline"] for s in r["stories"]], ["H"])
        self.assertEqual(len(r["pending"]), 2)   # 使わなかった新着は整理待ち

    def test_latest_stories_carries_previous_edit(self):
        rows = [{"board_id": 1, "day": TODAY, "stories": [], "pending": pend(1)},
                {"board_id": 1, "day": "2026-11-04", "stories": [{"headline": "h"}], "pending": []}]
        self.assertEqual(user_pages.latest_stories(lambda path: rows)[1]["stories"], [{"headline": "h"}])

    def test_edit_next_offers_library_after_shop(self):
        with mock.patch.object(digest, "edit_queue", return_value=[]), mock.patch.object(digest, "undesigned", return_value=[]), \
                mock.patch.object(digest, "lib_edit_todo", return_value=[(42, "広島旅行", 3)]):
            self.assertEqual(digest.edit_next(ctl={"mode": "run"}), ("NEXT", "lib:42 広島旅行"))
        with mock.patch.object(digest, "edit_queue", return_value=[]), mock.patch.object(digest, "undesigned", return_value=[]), \
                mock.patch.object(digest, "lib_edit_todo", return_value=[]):
            self.assertEqual(digest.edit_next(ctl={"mode": "run"}), ("DONE", ""))

    def test_shop_board_rows(self):
        items = [{"name": "GTA 6", "wikidata": "Q1"}, {"name": "ILLIT"}]
        issue = {"items": [{"name": "GTA 6", "stories": [{"headline": "h", "url": "u", "image_via": "x"}], "pending": [{"n": 1, "title": "t", "url": "v"}] * 30},
                           {"name": "知らない", "stories": []}]}
        rows = digest.board_story_rows(issue, items)
        self.assertEqual(list(rows), ["wd:Q1"])
        self.assertEqual(rows["wd:Q1"]["stories"], [{"headline": "h", "url": "u"}])
        self.assertEqual(len(rows["wd:Q1"]["pending"]), digest.BOARD_PENDING_MAX)


if __name__ == "__main__":
    unittest.main()
