"""新しい版面の速い道（2026-11-19 店長「新しい版面を足したら小元素が出るまでの時間は 5 分未満を保つ」）。
library_emblem.py --fresh・library.claim_board・user_pages の 1 人だけの作り直しと記事 5 本まで待つ決まり。網・DB なし。
時計と sleep は差し替える（本当に待たない）。"""
import inspect
import json
import pathlib
import sys
import tempfile
import threading
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
            return [{"board_id": i, "section": "生活"} for i in (1, 4)] if path.startswith("follows?") else rows
        got = [b["id"] for b in le.fresh_boards(db, NOW, shop={2})]
        self.assertEqual(got, [1, 4])
        self.assertIn("board_id=in.(1,4)", seen[1])
        self.assertIn("config->>emblem_state=is.null", seen[0])
        self.assertIn("created_at=gte.", seen[0])
        self.assertNotIn("+", seen[0])   # 網址で + が空白にならない（Z で書く）

    def test_board_without_follows_waits(self):
        # library.py --users は boards を先に、follows を最後に書く：follows の前に取ると板块が分からず種類（kind_for）を間違える
        rows = [{"id": 1, "config": {}}, {"id": 2, "config": {}}]
        fol = [{"board_id": 2, "section": "游戏", "subs": {}}, {"board_id": 2, "section": "生活", "subs": {}}]
        got = le.fresh_boards(lambda path, *a, **k: fol if path.startswith("follows?") else rows, NOW)
        self.assertEqual([b["id"] for b in got], [2])
        self.assertEqual(got[0]["_follow"]["section"], "游戏")   # 最初の follows（created_at の順）

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
            seen["step"], seen["deadline"], seen["first"] = emblem_fill.STEP, emblem_fill._deadline[0], emblem_fill.FIRST_STOP
            if write:
                import emblem
                emblem.write_item(item["name"], write, None)
            return result
        step0, dl0 = emblem_fill.STEP, emblem_fill._deadline[0]
        add = le.fresh_fill(self.board, {"section": "生活"}, lambda n, d: None, BASE, time.time() + 600, fill=fake, now=NOW)
        self.assertEqual((emblem_fill.STEP, emblem_fill._deadline[0], emblem_fill.FIRST_STOP), (step0, dl0, False))   # 範囲は元に戻る（店長の後台は止めない）
        return add, seen

    def test_scope_is_narrow_but_rules_are_the_same_path(self):
        add, seen = self.fill({"state": "ok", "note": "1 枚"})
        self.assertEqual(seen["step"], le.FRESH_STEP)
        self.assertTrue(seen["first"])   # 1 枚目が通った段で止める（範囲だけ）
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


class Continue(unittest.TestCase):
    """2026-11-19 本番の実測 2 回目：先頭 3 人を 1 回試して 0 枚のまま、上限を 65 秒以上残して終わった → 上限まで名簿の続きを試す。"""
    board = {"id": 21, "name": "x", "wd": None, "config": {"keywords": ["x"], "emblem_claim": NOW}}

    def run_fill(self, passes):
        """passes = [(試す人, 候補の数, 使えた数, 小元素を書くか)]。fill は 1 回ごとに次を返す。"""
        seen = []

        def fake(item, log=None):
            i = len(seen)
            seen.append(list(item.get("_skip") or []))
            want, found, usable, write = passes[min(i, len(passes) - 1)]
            if write:
                import emblem
                emblem.write_item(item["name"], [{"subject": want[0], "image": "https://e.org/a.png", "shape": "badge"}], None)
            return {"state": "failed", "note": "x", "want": want, "funnel": {"found": found, "usable": usable}, "material": "m"}
        add = le.fresh_fill(self.board, {"section": "游戏"}, lambda n, d: None, BASE, time.time() + 600, fill=fake, now=NOW)
        return add, seen

    def test_next_people_until_one_passes(self):
        add, seen = self.run_fill([(["A", "B", "C"], 4, 2, False), (["D", "E", "F"], 3, 1, True)])
        self.assertEqual(seen, [[], ["A", "B", "C"]])   # 2 回目は試した人を飛ばして続きから
        st = add["emblem_state"]
        self.assertEqual((st["state"], st["have"], st["passes"]), ("running", 1, 2))
        self.assertNotIn("m", st)
        self.assertEqual(st.get("rounds", 0), 0)   # 回の番号は進めない
        self.assertEqual(le.fresh_why(st), "小元素あり")

    def test_keys_found_in_the_first_pass_are_written(self):
        """見直し 2：fill_board は渡した config と違う鍵だけ返す。2 回目からは 1 回目の結果を足した config と比べるので、
        積まないと 1 回目に見つけた名簿・分類・reject が DB に書かれなかった。"""
        n = [0]

        def fake(item, log=None):
            n[0] += 1
            if n[0] == 1:
                p = emblem_fill.ROOT / "items.yaml"
                p.write_text(p.read_text(encoding="utf-8") + '    emblem_who: ["A","B","C","D","E","F","G"]\n    emblem_category: "Main"\n'
                             '    emblem_reject: ["https://e.org/bad.png"]\n', encoding="utf-8")
            return {"state": "failed", "note": "x", "want": ["A", "B", "C"] if n[0] == 1 else ["D", "E", "F"], "funnel": {"found": 1, "usable": 0}}
        add = le.fresh_fill(self.board, {"section": "游戏"}, lambda n, d: None, BASE, time.time() + 600, fill=fake, now=NOW)
        self.assertGreaterEqual(n[0], 2)
        self.assertEqual(add.get("emblem_who"), ["A", "B", "C", "D", "E", "F", "G"])
        self.assertEqual(add.get("emblem_category"), "Main")
        self.assertEqual(add.get("emblem_reject"), ["https://e.org/bad.png"])
        self.assertNotIn("_skip", add)   # 見直し 7：一時の場所の印は config に書かない

    def test_whole_roster_without_a_pass_is_rejected_not_fingerprinted(self):
        add, seen = self.run_fill([(["A", "B", "C"], 2, 1, False), (["D"], 1, 0, False), (["A"], 0, 0, False)])
        st = add["emblem_state"]
        self.assertEqual(len(seen), 3)   # 名簿が尽きる（試す人が試した人だけ）まで
        self.assertEqual(st["fast_tried"], ["A", "B", "C", "D"])   # 見回りの列は続きから（同じ人を試し直さない）
        self.assertEqual(st["fast_why"], "rejected")   # 候補はあったが 1 枚も通らなかった
        self.assertEqual(st["seen"], [3, 1])
        self.assertNotIn("m", st)
        self.assertEqual(le.fresh_why(st), "候補が通らず")
        self.assertTrue(le.due([{"id": 21, "config": {**self.board["config"], **add}}], NOW))   # 列がすぐ拾う

    def test_no_candidates_is_counted_apart(self):
        add, _ = self.run_fill([(["A"], 0, 0, False)])
        self.assertEqual(add["emblem_state"]["fast_why"], "none")
        self.assertEqual(le.fresh_why(add["emblem_state"]), "候補なし")

    def test_stops_when_little_time_is_left(self):
        with mock.patch.object(le, "FRESH_PASS_MIN_S", 10 ** 6):
            add, seen = self.run_fill([(["A", "B", "C"], 1, 0, False), (["D"], 1, 1, True)])
        self.assertEqual(len(seen), 1)

    def test_skip_is_kept_until_the_roster_is_done(self):
        c = {"keywords": ["x"]}
        b = {"id": 21, "name": "x", "wd": None, "config": {**c, "emblem_state": {"state": "failed", "have": 0, "fast_tried": ["A"], "fast_key": le.fast_key(c),
                                                                                "nv": emblem_fill.NAMES_V, "bv": emblem_fill.BROKEN_V, "v": le.RULES}}}
        up = lambda n, d: None  # noqa: E731
        add = le.fill_board(b, {"section": "生活"}, up, BASE, fill=lambda item, log=None: {"state": "failed", "note": "時間切れ"}, now=NOW)
        self.assertEqual(add["emblem_state"]["fast_tried"], ["A"])   # 時間切れ（指紋なし）：まだ飛ばす
        add = le.fill_board(b, {"section": "生活"}, up, BASE, fill=lambda item, log=None: {"state": "failed", "note": "0 枚"}, now=NOW)
        self.assertNotIn("fast_tried", add["emblem_state"])   # 1 周して指紋が付いた：消して、日に 1 回の試し直しに入れる

    def test_skip_ends_when_rules_or_material_change(self):
        """見直し 3：規則の版（RULES・NAMES_V・BROKEN_V）や材料（emblem_urls・site・emblem_reject）が変わったら、速い道が試した人も試し直す。"""
        c = {"keywords": ["x"]}
        st = {"state": "running", "have": 1, "fast_tried": ["A", "B"], "fast_key": le.fast_key(c)}
        b = lambda cc: {"id": 21, "name": "x", "wd": None, "config": {**cc, "emblem_state": st}}  # noqa: E731
        self.assertIn("_skip", le.board_item(b(c), {"section": "游戏"}))
        self.assertNotIn("_skip", le.board_item(b({**c, "emblem_reject": ["https://e.org/bad.png"]}), {"section": "游戏"}))   # 材料が変わった
        self.assertNotIn("_skip", le.board_item(b({**c, "site": "https://official.example"}), {"section": "游戏"}))
        with mock.patch.object(le, "RULES", le.RULES + 1):
            self.assertNotIn("_skip", le.board_item(b(c), {"section": "游戏"}))   # 規則の版が上がった
        with mock.patch.object(emblem_fill, "NAMES_V", emblem_fill.NAMES_V + 1):
            self.assertNotIn("_skip", le.board_item(b(c), {"section": "游戏"}))

    def test_queue_does_not_skip_a_missing_lead(self):
        """見直し 3：名簿の先頭で欠けた主役は、速い道が試していても見回りの列は飛ばさない（「欠けた主役を毎回先に」E15・BLEACH Rukia）。
        速い道の中（FIRST_STOP）は飛ばして続きへ進む。"""
        it = {"name": "x", "emblem_who": ["A", "B", "C", "D", "E", "F"], "emblem_kind": "character", "_round": 0, "_skip": ["A", "B", "C"],
              "emblem": [{"subject": "B", "image": "https://e.org/b.png"}]}
        step, first = emblem_fill.STEP, emblem_fill.FIRST_STOP
        try:
            emblem_fill.STEP = 3
            emblem_fill.FIRST_STOP = False
            got = emblem_fill.subjects(dict(it), "character", 200)
            self.assertIn("A", got)          # 欠けた主役（先頭 3 人で小元素が無い）は戻る
            self.assertNotIn("B", got)       # もういる人は今までどおり外れる
            emblem_fill.FIRST_STOP = True
            self.assertNotIn("A", emblem_fill.subjects(dict(it), "character", 200))
        finally:
            emblem_fill.STEP, emblem_fill.FIRST_STOP = step, first

    def test_queue_skips_people_the_fast_path_tried(self):
        c = {"keywords": ["x"]}
        b = {"id": 21, "name": "x", "wd": None, "config": {**c, "emblem_state": {"state": "failed", "have": 0, "fast_tried": ["A", "B"], "fast_key": le.fast_key(c)}}}
        self.assertEqual(le.board_item(b, {"section": "游戏"})["_skip"], ["A", "B"])
        step = emblem_fill.STEP
        it = {"name": "x", "emblem_who": ["A", "B", "C", "D", "E", "F", "G"], "emblem_kind": "character", "_round": 0, "_skip": ["D", "E"],
              "emblem": [{"subject": w, "image": f"https://e.org/{w}.png"} for w in ("A", "B", "C")]}   # 主役はそろっている
        try:
            emblem_fill.STEP = 2
            got = emblem_fill.subjects(it, "character", 200)
        finally:
            emblem_fill.STEP = step
        self.assertEqual(got, ["F", "G"])   # 速い道が試した D・E を飛ばして続きから


class Loop(unittest.TestCase):
    def run_loop(self, appear, wait=240, minutes=9, results=None, upstream=None, shard=0):
        """appear = {時刻（秒）: [版面]}：その時刻から DB に現れる。upstream = 時刻 → True／False／None（board の job の様子）。"""
        t = [0.0]
        done = set()
        asked = []

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

        def up():
            asked.append(t[0])
            return upstream(t[0]) if upstream else None
        r = le.fresh_loop(list_fresh, take, wait, minutes * 60, clock=lambda: t[0], sleep=sleep, upstream=up, shard=shard)
        return r, t[0], asked

    def test_waits_for_row_then_takes_then_quiet_exit(self):
        r, end, _ = self.run_loop({40: [{"id": 1}]})
        self.assertEqual(r["ids"], [1])
        self.assertLess(end, 40 + 60 + le.FRESH_QUIET_S + 10)

    def test_second_board_in_the_quiet_tail_is_taken(self):
        r, _, _ = self.run_loop({40: [{"id": 1}], 130: [{"id": 2}]})   # 30 秒の歯止めの間に足された 2 人目
        self.assertEqual(r["ids"], [1, 2])

    def test_unknown_upstream_gives_up_after_grace(self):
        r, end, _ = self.run_loop({}, wait=300)
        self.assertEqual(r["done"], [])
        self.assertLess(end, le.FRESH_GRACE_S + le.FRESH_POLL_S + 1)

    def test_unknown_upstream_waits_while_names_are_pending(self):
        # API が読めない・足したばかりの名前（added_at）がまだ版面になっていない：GRACE を過ぎても wait まで待つ
        t = [0.0]
        le.fresh_loop(lambda: [], lambda b: None, 200, 600, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s), waiting=lambda: 1)
        self.assertGreaterEqual(t[0], 200)

    def test_late_row_is_waited_for_while_board_job_runs(self):
        # 2026-11-19 run 1：行は board の job の終わりごろ（+50 秒）に現れた。前は +10 秒で 1 回見て「0」で終えていた
        r, end, _ = self.run_loop({50: [{"id": 7}]}, upstream=lambda s: s >= 55)
        self.assertEqual(r["ids"], [7])

    def test_row_written_just_before_job_end_is_not_missed(self):
        # 終わったのを見てから読む：job の最後に書かれた行（終わりと同じ時刻に現れる）も取る
        r, _, _ = self.run_loop({45: [{"id": 3}]}, upstream=lambda s: s >= 45)
        self.assertEqual(r["ids"], [3])

    def test_route_ab_ends_when_board_job_ends(self):
        # 経路 A/B：新しい版面は来ない。board の job が終わったら（+40 秒）すぐ終える（wait 300 秒も GRACE も待たない）
        r, end, _ = self.run_loop({}, wait=300, upstream=lambda s: s >= 40)
        self.assertEqual(r["done"], [])
        self.assertLess(end, 40 + le.FRESH_UP_S + le.FRESH_POLL_S + 1)

    def test_board_job_never_ends_stops_at_wait(self):
        r, end, _ = self.run_loop({}, wait=200, upstream=lambda s: False)
        self.assertGreaterEqual(end, 200)
        self.assertLess(end, 200 + le.FRESH_POLL_S + 1)

    def test_upstream_is_not_asked_every_poll(self):
        _, end, asked = self.run_loop({}, wait=120, upstream=lambda s: False)
        self.assertLessEqual(len(asked), end / le.FRESH_UP_S + 2)   # GitHub の API は FRESH_UP_S ごと（DB は FRESH_POLL_S ごと）

    def test_skipped_board_is_not_retried_in_the_same_run(self):
        calls = []
        t = [0.0]

        def take(b):
            calls.append(b["id"])
            return None   # Wikidata に断られた・印を取られた
        le.fresh_loop(lambda: [{"id": 1}], take, 30, 600, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
        self.assertEqual(calls, [1])

    def test_running_counts_as_left(self):
        r, _, _ = self.run_loop({0: [{"id": 1}]}, results={1: {"emblem_state": {"state": "running", "have": 1}}})
        self.assertEqual((r["ids"], r["left"]), ([1], 1))

    def test_shard_starts_at_its_own_board(self):
        order = []
        t = [0.0]
        bs = [{"id": 1}, {"id": 2}, {"id": 3}]

        def take(b):
            order.append(b["id"])
            return None
        le.fresh_loop(lambda: bs, take, 30, 600, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s), upstream=lambda: True, shard=1)
        self.assertEqual(order, [2, 3, 1])


class Shards(unittest.TestCase):
    """同じ 30 秒に 3 つ足された版面を 3 つ並べた回が取る：同じ版面を 2 回取らない（library.claim_board の条件つきの書き込み）。"""

    class DB:
        def __init__(self, ids):
            self.cfg = {i: {} for i in ids}
            self.lock = threading.Lock()

        def __call__(self, path, body=None, prefer=None, method=None):
            bid = int(path.split("id=eq.")[1].split("&")[0])
            if method is None:
                return [{"config": dict(self.cfg[bid])}]
            with self.lock:   # PostgREST の 1 回の UPDATE … WHERE（条件と書き込みが 1 つ）
                c = self.cfg[bid]
                old = c.get("emblem_claim")
                cond = ("config->>emblem_claim=is.null" in path) if old is None else (f"config->>emblem_claim=eq.{old}" in path)
                if c.get("emblem_state") or not cond:
                    return []
                self.cfg[bid] = dict(body["config"])
                return [self.cfg[bid]]

    def test_claim_is_won_once_under_threads(self):
        db = self.DB([5])
        wins = []
        barrier = threading.Barrier(3)

        def go():
            barrier.wait()
            wins.append(library.claim_board(5, NOW, db=db))
        ths = [threading.Thread(target=go) for _ in range(3)]
        [x.start() for x in ths]
        [x.join() for x in ths]
        self.assertEqual(sorted(wins), [False, False, True])

    def test_three_shards_take_three_boards_once_each(self):
        db = self.DB([1, 2, 3])
        took = {}
        lock = threading.Lock()

        def shard(i):
            t = [0.0]

            def list_fresh():
                return [{"id": b} for b, c in list(db.cfg.items()) if not c.get("emblem_state")]

            def take(b):
                if not library.claim_board(b["id"], NOW, db=db):
                    return None
                time.sleep(0.01)   # 取っている間にほかの回も読む
                with lock:
                    took.setdefault(b["id"], []).append(i)
                db.cfg[b["id"]] = {"emblem_state": {"state": "running", "have": 1}}
                return {"emblem_state": {"state": "running", "have": 1}}
            le.fresh_loop(list_fresh, take, 30, 600, clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s), upstream=lambda: True, shard=i)
        ths = [threading.Thread(target=shard, args=(i,)) for i in range(le.FRESH_SHARDS)]
        [x.start() for x in ths]
        [x.join() for x in ths]
        self.assertEqual(sorted(took), [1, 2, 3])
        self.assertTrue(all(len(v) == 1 for v in took.values()), took)   # どの版面も 1 回だけ


class Budget(unittest.TestCase):
    def test_budget_fits_under_five_minutes(self):
        total = sum(s for _, s in le.FRESH_BUDGET)
        self.assertLess(total, le.FRESH_TOTAL_S)                        # 300 秒「未満」
        self.assertLessEqual(total + le.FRESH_SPARE_S, le.FRESH_TOTAL_S)   # 余り 60 秒を残す（240 + 60 ≤ 300）
        self.assertEqual(le.FRESH_TOTAL_S, 300)
        self.assertEqual([k for k, _ in le.FRESH_BUDGET], ["kick", "setup", "first", "write", "page"])
        self.assertEqual(le.FRESH_BOARD_S, dict(le.FRESH_BUDGET)["first"])   # 1 版面の上限は割り当ての「1 枚目」
        self.assertLessEqual(le.FRESH_BOARD_S, 90)
        self.assertLess(le.FRESH_TOOLS_S + le.FRESH_BOARD_S, library.CLAIM_S)   # 道具を待つ間も印は切れない
        # ログの秒は run の created_at から（「起こす」の段は中に入っている）：目標は 300 − 足してから run ができるまで。もう一度「起こす 20」を引かない
        self.assertEqual(le.FRESH_LOG_LIMIT_S, le.FRESH_TOTAL_S - le.FRESH_ADD_TO_RUN_S)
        import sys as _s
        _s.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import board_kpi
        self.assertIn("library_emblem.FRESH_LOG_LIMIT_S", inspect.getsource(board_kpi.cmd_fastlog))

    def test_first_stop_is_only_a_scope(self):
        src = inspect.getsource(emblem_fill.fill_one)
        self.assertIn('if FIRST_STOP and status(fresh)["have"] > before:', src)
        self.assertFalse(emblem_fill.FIRST_STOP)   # 店長の後台・見回りの列は今までどおり
        self.assertIn("FIRST_STOP", inspect.getsource(le.fresh_limits))


class FreshMain(unittest.TestCase):
    def run_main(self, boards, follows=None, have=1, fill_error=None, read_fail=(), put_fail=0, claim_fail=False, tools=None):
        """read_fail = 版面の読みの何回目（0 から）を 500 にするか・put_fail = 最初の何回の config の書き込みを 500 にするか。"""
        import digest
        import urllib.error
        log, rows = [], {b["id"]: b for b in boards}
        reads, puts = [0], [0]

        def err():
            return urllib.error.HTTPError("https://db/x", 500, "boom", {}, None)

        def sup(path, body=None, prefer=None, method=None):
            if path.startswith("boards?select=id,name,wd,config"):
                reads[0] += 1
                if reads[0] - 1 in read_fail:
                    raise err()
                return [b for b in rows.values() if not (b.get("config") or {}).get("emblem_state")]
            if path.startswith("follows?board_id=in."):
                return follows if follows is not None else [{"board_id": b["id"], "section": "生活"} for b in boards]
            return []

        def fake_fill(b, f, up, base, end):
            if fill_error:
                raise fill_error
            log.append(("fill", b["id"], f.get("section")))
            return {"emblem_state": {"state": "running", "have": have}, "emblem_claim": None}

        def put(bid, add):
            if puts[0] < put_fail:
                puts[0] += 1
                raise err()
            log.append(("write", bid))
            rows[bid] = {**rows[bid], "config": {**(rows[bid].get("config") or {}), **add}}
            return rows[bid]["config"]

        def claim(bid, stamp):
            if claim_fail:
                raise err()
            return True

        def runner(d):
            return (lambda bid: log.append(("page", bid))), (lambda timeout: {x[1]: (time.time(), 0) for x in log if x[0] == "page"})
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(pathlib.Path(d) / "o"), "SUPABASE_SERVICE_KEY": "k"}), \
                mock.patch.object(digest, "load_config", lambda: ({"supabase_url": BASE}, None)), \
                mock.patch.object(digest, "supabase", sup), \
                mock.patch.object(library, "claim_board", claim), \
                mock.patch.object(le.time, "sleep", lambda s: None), \
                mock.patch.object(library, "put_config", put), \
                mock.patch.object(le, "fresh_fill", fake_fill), \
                mock.patch.object(le, "pages_runner", runner), \
                mock.patch.object(le, "board_job_done", lambda: True), \
                mock.patch.object(le, "run_started", lambda: None), \
                mock.patch.object(le, "warm", lambda face=True: log.append(("warm", face))):
            le.fresh_main(["--fresh", "--wait", "0", "--minutes", "5", "--pages-dir", d] + (["--tools", tools] if tools else []))
            out = (pathlib.Path(d) / "o").read_text()
        self.rows = rows
        return log, out

    def test_each_board_is_written_then_its_page_right_away(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}, {"id": 2, "name": "b", "config": {}}])
        log = [x for x in log if x[0] != "warm"]
        self.assertEqual(log, [("fill", 1, "生活"), ("write", 1), ("page", 1), ("fill", 2, "生活"), ("write", 2), ("page", 2)])
        self.assertIn("worked=true", out)
        self.assertIn("more=true", out)   # running：続きは今までの列

    def test_models_are_warmed_once_before_the_first_fill(self):
        # 行が python の起動前にもうある（待つ間が無い）回：模型の読み込み（≈ 40 秒）を 90 秒の上限の中に入れない
        log, _ = self.run_main([{"id": 1, "name": "a", "config": {}}, {"id": 2, "name": "b", "config": {}}])
        # rembg の切り抜きは python の始めから後ろの糸で（行を待つ間に）、顔の模型（糸ごと）は取る糸で 1 回。どちらも最初の版面の前
        self.assertEqual(log[:2], [("warm", False), ("warm", True)])
        self.assertEqual(sum(1 for x in log if x[0] == "warm"), 2)
        src = inspect.getsource(le.fresh_fill)
        self.assertIn("time.time() + FRESH_BOARD_S", src)   # 上限の時計は fresh_fill の始め＝warm の後から

    def test_no_emblem_no_page(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], have=0)
        self.assertNotIn(("page", 1), log)
        self.assertIn("worked=false", out)

    def test_route_ab_ends_without_taking(self):
        log, out = self.run_main([])
        self.assertEqual(log, [])   # 経路 A/B：版面を取らない・足したばかりの名前も無いので模型も読まない（見直し 10）

    def test_models_start_early_when_new_names_are_waiting(self):
        # 足したばかりでまだ版面になっていない名前がある：行が見える前から後ろで読み始める（F3 の効きを保つ）
        with mock.patch.object(le, "_waiting", lambda db, now, unknown=0: 1):
            log, out = self.run_main([])
        self.assertEqual(log, [("warm", False)])
        self.assertIn("worked=false", out)
        self.assertIn("more=false", out)

    def test_one_failure_does_not_stop_writing(self):
        log, _ = self.run_main([{"id": 1, "name": "a", "config": {}}], fill_error=RuntimeError("x"))
        self.assertEqual([x for x in log if x[0] != "warm"], [("write", 1)])   # 失敗も書く（指紋なしの failed・印を外す）＝次の見回りですぐ

    def test_one_500_on_read_does_not_stop(self):
        # DB は店長の PC（Tailscale 経由）：一瞬の 500 で shard ごと落ちない。「無い」とも決めない（board の job が終わっていても）
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], read_fail={0})
        self.assertEqual([x for x in log if x[0] != "warm"][:2], [("fill", 1, "生活"), ("write", 1)])
        self.assertIn("worked=true", out)

    def test_reads_keep_failing_ends_with_outputs(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], read_fail=set(range(50)))
        self.assertEqual([x for x in log if x[0] != "warm"], [])
        self.assertIn("worked=false", out)
        self.assertIn("more=true", out)   # 読めないまま：続きは列へ

    def test_failed_write_is_retried_and_claim_is_cleared(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], put_fail=1)
        self.assertIn(("write", 1), log)
        self.assertIsNone(self.rows[1]["config"].get("emblem_claim"))   # 印が残らない

    def test_write_that_keeps_failing_does_not_crash(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], put_fail=10)
        self.assertNotIn(("page", 1), log)   # 書けなかった版面のページは作らない
        self.assertIn("more=true", out)       # 印は期限（CLAIM_S）で戻り、列が拾う

    def test_claim_error_does_not_crash(self):
        log, out = self.run_main([{"id": 1, "name": "a", "config": {}}], claim_fail=True)
        self.assertEqual([x for x in log if x[0] != "warm"], [])
        self.assertIn("more=true", out)

    def test_tools_wait_is_one_limit_for_the_whole_job(self):
        # rembg が入らないまま：版面ごとに 120 秒ずつ待たない。上限を過ぎたら取らずに列へ（印は外す）
        with tempfile.TemporaryDirectory() as d, mock.patch.object(le, "FRESH_TOOLS_S", 0):
            tools = pathlib.Path(d) / "t"
            log, out = self.run_main([{"id": 1, "name": "a", "config": {}}, {"id": 2, "name": "b", "config": {}}], tools=str(tools))
        self.assertFalse([x for x in log if x[0] == "fill"])
        self.assertIn("more=true", out)
        self.assertIsNone(self.rows[1]["config"].get("emblem_claim"))

    def test_outputs_even_if_the_loop_breaks(self):
        with mock.patch.object(le, "fresh_loop", lambda *a, **k: 1 / 0):
            log, out = self.run_main([{"id": 1, "name": "a", "config": {}}])
        self.assertIn("worked=false", out)
        self.assertIn("more=true", out)

    def test_log_has_ids_and_seconds_only(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.run_main([{"id": 41, "name": "秘密の名前", "config": {}}])
        s = buf.getvalue()
        self.assertIn("速い道の時刻 版面 41：取り始め +", s)
        self.assertIn("速い道の待ち 版面 41：行が見えた +", s)   # 待ちの内訳（行・rembg・模型・印）
        self.assertIn("・模型 +", s)
        self.assertIn("・ページ +", s)
        self.assertNotIn("秘密の名前", s)


class Upstream(unittest.TestCase):
    def test_board_job_done(self):
        jobs = lambda st: {"jobs": [{"name": "emblem (0)", "status": "in_progress"}, {"name": "board", "status": st}]}  # noqa: E731
        self.assertTrue(le.board_job_done(lambda p: jobs("completed"), run_id=9))
        self.assertFalse(le.board_job_done(lambda p: jobs("in_progress"), run_id=9))
        self.assertFalse(le.board_job_done(lambda p: jobs("queued"), run_id=9))   # library.yml の列で待っている
        self.assertIsNone(le.board_job_done(lambda p: None, run_id=9))   # 読めない＝分からない
        self.assertIsNone(le.board_job_done(lambda p: {"jobs": []}, run_id=9))
        self.assertIsNone(le.board_job_done(lambda p: {"jobs": [{"name": "board", "status": "completed", "conclusion": "cancelled"}]}, run_id=9))   # 置き換えられた：分からない
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(le.board_job_done(lambda p: jobs("completed")))   # 手元（run が無い）

    def test_run_started(self):
        import datetime as dt
        want = dt.datetime(2026, 11, 19, 4, 1, 53, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(le.run_started(lambda p: {"created_at": "2026-11-19T04:01:53Z"}, run_id=1), want)
        self.assertIsNone(le.run_started(lambda p: None, run_id=1))

    def test_tools_ready(self):
        import os
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {}):
            os.environ.pop("SCRAPLING_BROWSER", None)
            f = pathlib.Path(d) / "t"
            self.assertFalse(le.tools_ready(str(f)))
            f.write_text("rembg=ok\n")
            self.assertFalse(le.tools_ready(str(f)))   # 入れている途中（印の前）は import しない
            f.write_text("rembg=ok\nrembg_done=1\n")
            self.assertTrue(le.tools_ready(str(f)))    # 任意の scrapling は待たない
            self.assertIsNone(os.environ.get("SCRAPLING_BROWSER"))
            f.write_text("rembg_done=1\nscrapling=ok\n")
            self.assertTrue(le.tools_ready(str(f)))
            self.assertEqual(os.environ.get("SCRAPLING_BROWSER"), "1")
            f.write_text("done=1\n")   # rembg が入らなくても終わりの印で進む（取るときは EnvFail＝指紋なし）
            self.assertTrue(le.tools_ready(str(f)))
        self.assertTrue(le.tools_ready(None))


class WarmThread(unittest.TestCase):
    def test_main_thread_output_survives_background_warm(self):
        """見直し 4：redirect_stdout は python 全体に効く。後ろの糸が模型を読んでいる間の元の糸の print が捨てられていた。"""
        import contextlib
        import io
        import types
        started, go = threading.Event(), threading.Event()

        def slow(name):
            started.set()
            go.wait(5)
        fake = types.SimpleNamespace(_session=slow)
        buf = io.StringIO()
        with mock.patch.dict(sys.modules, {"emblem": fake}), contextlib.redirect_stdout(buf):
            th = threading.Thread(target=le.warm, kwargs={"face": False})
            th.start()
            started.wait(5)
            print("元の糸の行")
            go.set()
            th.join(5)
        self.assertIn("元の糸の行", buf.getvalue())


class WaitingPicks(unittest.TestCase):
    def test_waiting_picks(self):   # board の job の様子が分からないときだけ使う
        iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(NOW - s))  # noqa: E731
        users = [{"prefs": {"picks": [{"name": "新しい名前", "added_at": iso(30)},         # 来る
                                      {"name": "大谷翔平", "added_at": iso(30)},           # 経路 A/B：もうある
                                      {"name": "古い名前", "added_at": iso(3600)},          # 足したのは前
                                      {"name": "時刻なし"}]}}]                              # added_at が無い DB でも落ちない
        boards = [{"name": "大谷 翔平", "names": {"en": "Shohei Ohtani"}}]
        self.assertEqual(le.waiting_picks(users, boards, NOW), 1)
        self.assertEqual(le.waiting_picks(users[:0], boards, NOW), 0)


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
