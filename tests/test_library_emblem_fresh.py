"""新しい版面の速い道（2026-11-19 店長「新しい版面を足したら小元素が出るまでの時間は 5 分未満を保つ」）。
library_emblem.py --fresh／--check-fresh・library.claim_board・user_pages の 1 人だけの作り直しと記事 5 本まで待つ決まり。網・DB なし。"""
import inspect
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem_fill  # noqa: E402
import library  # noqa: E402
import library_emblem as le  # noqa: E402
import user_pages  # noqa: E402

BASE = "https://x.supabase.co"
NOW = 1_763_500_000


class FreshBoards(unittest.TestCase):
    def test_only_untried_recent_not_shop_not_claimed(self):
        seen = []
        rows = [{"id": 1, "config": {}},
                {"id": 2, "config": {}},                                         # 店長の版面
                {"id": 3, "config": {"emblem_claim": NOW - 10}},                 # ほかの回が取っている
                {"id": 4, "config": {"emblem_claim": NOW - library.CLAIM_S - 1}},  # 期限切れの印：取ってよい
                {"id": 5, "config": {"emblem_state": {"state": "ok"}}}]          # 試した版面（DB の条件をすり抜けても）

        def db(path, *a, **k):
            seen.append(path)
            return rows
        got = [b["id"] for b in le.fresh_boards(db, NOW, shop={2})]
        self.assertEqual(got, [1, 4])
        self.assertIn("config->>emblem_state=is.null", seen[0])
        self.assertIn("created_at=gte.", seen[0])
        self.assertNotIn("+", seen[0])   # 網址で + が空白にならない（Z で書く）

    def test_due_skips_fresh_claim_only(self):
        b1 = {"id": 1, "config": {"emblem_claim": NOW - 5}}
        b2 = {"id": 2, "config": {"emblem_claim": NOW - library.CLAIM_S - 1}}
        b3 = {"id": 3, "config": {}}
        self.assertEqual([b["id"] for b in le.due([b1, b2, b3], NOW)], [2, 3])

    def test_claim_key_not_in_sandbox_item(self):
        b = {"id": 7, "name": "x", "wd": None, "config": {"emblem_claim": NOW, "keywords": ["x"]}}
        self.assertNotIn("emblem_claim", le.board_item(b, {"section": "生活"}))


class Claim(unittest.TestCase):
    def run_claim(self, cur, rows=(1,)):
        calls = []

        def db(path, body=None, prefer=None, method=None):
            calls.append((path, body, method))
            return [{"config": cur}] if method is None else list(rows)
        return library.claim_board(9, NOW, db=db), [c for c in calls if c[2] == "PATCH"]

    def test_untried_is_claimed_with_conditional_patch(self):
        ok, p = self.run_claim({"keywords": ["x"]})
        self.assertTrue(ok)
        self.assertEqual(len(p), 1)
        self.assertIn("config->>emblem_state=is.null", p[0][0])   # 1 回の UPDATE の条件：同時に取っても片方だけ
        self.assertIn("config->>emblem_claim=is.null", p[0][0])
        self.assertEqual(p[0][1]["config"], {"keywords": ["x"], "emblem_claim": NOW})

    def test_lost_race_returns_false(self):
        ok, _ = self.run_claim({}, rows=())
        self.assertFalse(ok)

    def test_tried_or_claimed_is_not_touched(self):
        for cur in ({"emblem_state": {"state": "failed"}}, {"emblem_claim": NOW - 30}):
            ok, p = self.run_claim(cur)
            self.assertFalse(ok)
            self.assertEqual(p, [])

    def test_expired_claim_is_taken_over_only_if_unchanged(self):
        old = NOW - library.CLAIM_S - 5
        ok, p = self.run_claim({"emblem_claim": old})
        self.assertTrue(ok)
        self.assertIn(f"config->>emblem_claim=eq.{old}", p[0][0])


class FreshFill(unittest.TestCase):
    board = {"id": 11, "name": "x", "wd": None, "config": {"keywords": ["x"], "emblem_claim": NOW}}

    def fill(self, result, write=None):
        seen = {}

        def fake(item, log=None):
            seen["step"], seen["deadline"] = emblem_fill.STEP, emblem_fill._deadline[0]
            if write:
                import emblem
                emblem.write_item(item["name"], write, None)
            return result
        step0, dl0 = emblem_fill.STEP, emblem_fill._deadline[0]
        add = le.fresh_fill(self.board, {"section": "生活"}, lambda n, d: None, BASE, time.time() + 600, fill=fake, now=NOW)
        self.assertEqual((emblem_fill.STEP, emblem_fill._deadline[0]), (step0, dl0))   # 範囲は元に戻る
        return add, seen

    def test_scope_is_narrow_but_rules_are_the_same_path(self):
        add, seen = self.fill({"state": "ok", "note": "1 枚"})
        self.assertEqual(seen["step"], le.FRESH_STEP)
        self.assertLessEqual(seen["deadline"], time.time() + le.FRESH_BOARD_S + 1)   # 1 版面の上限
        self.assertEqual(add["emblem_state"]["state"], "ok")
        self.assertIsNone(add["emblem_claim"])   # 印を外す
        src = inspect.getsource(le.fresh_fill)
        self.assertIn("fill_board(", src)   # 規則の入口（fill_board → emblem_fill.fill_one）を迂回しない
        for f in (le.fresh_fill, le.fresh_loop, le.fresh_main):
            self.assertNotIn("emblem_fill.fill_one", inspect.getsource(f))
            self.assertNotIn("auto_pick", inspect.getsource(f))

    def test_timeout_leaves_no_fingerprint_nor_round(self):
        add, _ = self.fill({"state": "failed", "note": "時間切れ"})
        st = add["emblem_state"]
        self.assertEqual(st["state"], "failed")
        self.assertNotIn("m", st)
        self.assertNotIn("rounds", st)

    def test_partial_roster_is_running_without_fingerprint(self):
        add, _ = self.fill({"state": "failed", "note": "1 枚足した"}, write=[{"subject": "A", "image": "https://e.org/a.png", "shape": "badge"}])
        st = add["emblem_state"]
        self.assertEqual((st["state"], st["have"]), ("running", 1))   # 1 枚出た：続きは今までの列（running）
        self.assertNotIn("m", st)                                     # 先頭 3 人だけで「届かなかった」にしない
        self.assertEqual(st.get("rounds", 0), 0)                      # 回の番号を進めない（列が先頭から STEP 人ずつ）
        self.assertTrue(le.due([{"id": 11, "config": {**self.board["config"], **add}}], NOW))   # 列がすぐ拾う

    def test_nothing_found_is_not_filled_and_queued(self):
        add, _ = self.fill({"state": "failed", "note": "0 枚足した（a）。外した理由：候補なし"})
        self.assertFalse(add.get("emblem"))   # 合うものがなければ出さない（埋めない）
        self.assertNotIn("m", add["emblem_state"])
        self.assertTrue(le.due([{"id": 11, "config": {**self.board["config"], **add}}], NOW))


class Loop(unittest.TestCase):
    def run_loop(self, appear, wait=240, minutes=9, results=None):
        """appear = {時刻（秒）: [版面]}：その時刻から DB に現れる。"""
        t = [0.0]
        done = set()

        def list_fresh():
            return [b for at, bs in appear.items() if t[0] >= at for b in bs if b["id"] not in done]

        def take(b):
            t[0] += 60   # 1 版面 60 秒
            r = (results or {}).get(b["id"], {"emblem_state": {"state": "ok", "have": 2}})
            if r is not None:
                done.add(b["id"])
            return r

        def sleep(s):
            t[0] += s
        r = le.fresh_loop(list_fresh, take, wait, minutes * 60, clock=lambda: t[0], sleep=sleep)
        return r, t[0]

    def test_waits_for_row_then_takes_then_quiet_exit(self):
        r, end = self.run_loop({40: [{"id": 1}]})
        self.assertEqual(r["ids"], [1])
        self.assertLess(end, 40 + 60 + le.FRESH_QUIET_S + 10)

    def test_second_board_in_the_quiet_tail_is_taken(self):
        r, _ = self.run_loop({40: [{"id": 1}], 130: [{"id": 2}]})   # 30 秒の歯止めの間に足された 2 人目
        self.assertEqual(r["ids"], [1, 2])

    def test_gives_up_after_wait_when_nothing_comes(self):
        r, end = self.run_loop({}, wait=100)
        self.assertEqual(r["done"], [])
        self.assertLess(end, 100 + le.FRESH_POLL_S + 1)

    def test_skipped_board_is_not_retried_in_the_same_run(self):
        calls = []
        t = [0.0]

        def take(b):
            calls.append(b["id"])
            return None   # Wikidata に断られた・印を取られた
        le.fresh_loop(lambda: [{"id": 1}], take, 30, 600, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
        self.assertEqual(calls, [1])

    def test_running_counts_as_left(self):
        r, _ = self.run_loop({0: [{"id": 1}]}, results={1: {"emblem_state": {"state": "running", "have": 1}}})
        self.assertEqual((r["ids"], r["left"]), ([1], 1))


class CheckFresh(unittest.TestCase):
    def test_waiting_picks(self):
        iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(NOW - s))  # noqa: E731
        users = [{"prefs": {"picks": [{"name": "新しい名前", "added_at": iso(30)},         # 来る
                                      {"name": "大谷翔平", "added_at": iso(30)},           # 経路 A/B：もうある
                                      {"name": "古い名前", "added_at": iso(3600)},          # 足したのは前
                                      {"name": "時刻なし"}]}}]
        boards = [{"name": "大谷 翔平", "names": {"en": "Shohei Ohtani"}}]
        self.assertEqual(le.waiting_picks(users, boards, NOW), 1)
        self.assertEqual(le.waiting_picks(users[:0], boards, NOW), 0)

    def test_check_fresh_output(self):
        import digest
        import userfeed
        for fresh, users, want in (([], [], "false"), ([{"id": 1, "config": {}}], [], "true")):
            with tempfile.TemporaryDirectory() as d:
                out = pathlib.Path(d) / "o"
                sup = lambda path, body=None, prefer=None, method=None, f=fresh: f if path.startswith("boards?select=id,name,wd") else []  # noqa: E731
                with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(out), "SUPABASE_SERVICE_KEY": "k"}), \
                     mock.patch.object(digest, "load_config", lambda: ({"supabase_url": BASE}, None)), \
                     mock.patch.object(digest, "supabase", sup), \
                     mock.patch.object(userfeed, "fetch_all", lambda db, p, b=None, u=users: (u, True)):
                    le.fresh_main(["--check-fresh"])
                self.assertEqual(out.read_text().strip(), f"due={want}")


class Pages(unittest.TestCase):
    def test_new_board_waits_for_five_stories_then_time(self):
        now = time.time()
        it = {"name": "x", "_added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 60))}
        self.assertTrue(user_pages.held(it, {"stories": [{}] * 3}, now))
        self.assertTrue(user_pages.held(it, {"stories": [{}] * 2, "pending": [{}] * 2, "edited": True}, now))
        self.assertFalse(user_pages.held(it, {"stories": [{}] * 5}, now))
        self.assertFalse(user_pages.held({**it, "_shop": True}, {}, now))          # 店長と同じ版面は店長の記事
        self.assertFalse(user_pages.held({"name": "x"}, {}, now))                  # 前からの版面（時刻なし）は待たない
        self.assertFalse(user_pages.held(it, {"stories": [{}]}, now + user_pages.NEW_HOLD_S))   # 6 時間たったら今ある分で

    def test_held_board_is_collecting_not_stories(self):
        now = time.time()
        added = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 60))
        items = user_pages.user_items(user_pages.own_picks([], [{"name": "新しい版面", "sec": "生活", "added_at": added}]), [])
        rows = {user_pages.norm("新しい版面"): {"stories": [{"title": "t", "url": "https://a/1"}] * 3}}
        issue = user_pages.user_issue(items, None, rows, now + 1, {})
        blk = issue["items"][0]
        self.assertEqual(blk["stories"], [])
        self.assertTrue(blk.get("collecting"))

    def test_added_at_survives_follows(self):
        f = [{"pos": 0, "section": "生活", "boards": {"id": 1, "name": "A", "config": {"emblem": [{"image": "u"}]}}}]
        got = user_pages.own_picks(f, [{"name": "A", "added_at": "2026-11-19T00:00:00Z"}])
        self.assertEqual(got[0]["added_at"], "2026-11-19T00:00:00Z")

    def test_pick_users(self):
        users = [{"email": "a@x"}, {"email": "b@x", "prefs": {"picks": [{"name": "n", "added_at": "2999-01-01T00:00:00Z"}]}}]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "ids.json"
            p.write_text(json.dumps([5]))
            get = lambda path: [{"account": user_pages.account_of("a@x")}] if "board_id=in.(5)" in path else []  # noqa: E731
            self.assertEqual(user_pages.pick_users(users, ["--boards-file", str(p)], get), ([users[0]], True))
            p.write_text("[]")
            self.assertEqual(user_pages.pick_users(users, ["--boards-file", str(p)], get), ([], True))
        self.assertEqual(user_pages.pick_users(users, ["--recent", "3600"], None), ([users[1]], True))
        self.assertEqual(user_pages.pick_users(users, [], None), (users, False))

    def test_design_moved(self):
        f = [{"boards": {"id": 1, "config": {"emblem_state": {"state": "ok", "at": 1}}}}]
        self.assertFalse(user_pages.design_moved(f, lambda p: [{"id": 1, "emblem_state": {"state": "ok", "at": 1}}]))
        self.assertTrue(user_pages.design_moved(f, lambda p: [{"id": 1, "emblem_state": {"state": "ok", "at": 2}}]))
        self.assertFalse(user_pages.design_moved(f, lambda p: 1 / 0))   # 読めなければそのまま置く
        self.assertFalse(user_pages.design_moved([], None))

    def test_partial_run_keeps_others_photo_list(self):
        src = inspect.getsource(user_pages.main)
        # 一部の人だけの回は imgs.json（全員分の写真の一覧）を置き換えず、前の列に足すだけ（2026-11-19：tests/test_saved_photos.MainPartial が中身を確かめる）
        self.assertIn("if partial or failed:", src)
        self.assertIn("merge_imgs(old", src)


class RegularClaims(unittest.TestCase):
    def test_regular_run_skips_board_claimed_by_fast_path(self):
        import digest
        filled = []
        b = {"id": 1, "name": "x", "wd": None, "config": {}}
        sup = lambda path, body=None, prefer=None, method=None: [] if path.startswith("follows?account") else [b] if path.startswith("boards?select") else [{}]  # noqa: E731
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(pathlib.Path(d) / "o"), "SUPABASE_SERVICE_KEY": "k"}), \
                mock.patch.object(digest, "load_config", lambda: ({"supabase_url": BASE}, None)), \
                mock.patch.object(digest, "supabase", sup), \
                mock.patch.object(le, "apply_requests", lambda c: None), \
                mock.patch.object(le, "PER_BOARD_S", 0), \
                mock.patch.object(library, "claim_board", lambda bid, stamp: False), \
                mock.patch.object(le, "fill_board", lambda *a, **k: filled.append(1)):
            le.main(["--minutes", "1"])
        self.assertEqual(filled, [])


if __name__ == "__main__":
    unittest.main()
