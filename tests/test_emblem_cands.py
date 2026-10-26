"""小元素の「候補から選ぶ」（scripts/emblem_cands.py）：集める → 並ぶ → 選ぶと入れ替わって固定。"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem  # noqa: E402
import emblem_cands as ec  # noqa: E402
import emblem_fill as ef  # noqa: E402
import library_emblem as le  # noqa: E402
import render  # noqa: E402


def cand(n, src="Wikipedia", subject="A"):
    return {"subject": subject, "why": src, "image": f"https://s/{n}.jpg", "page": "https://p", "source": src, "shape": "badge", "_img": object()}


class Find(unittest.TestCase):
    def test_find_excludes_taken_and_ranks(self):
        item = {"name": "X", "emblem_kind": "person", "emblem": [{"image": "emblems/x.webp", "source": "https://s/1.jpg", "subject": "A"}],
                "emblem_reject": ["https://s/2.jpg"]}
        got = [cand(1), cand(2), cand(3, "Web"), cand(4), cand(3, "Web")]
        with mock.patch.object(ef, "STRATEGIES", [("標準", "gather")]), mock.patch.object(ef, "gather", lambda it, log, got_: got), \
                mock.patch.object(ef, "check", lambda c, *a, **k: c):
            out = ec.find(item, "A", n=6)
        self.assertEqual([c["image"] for c in out], ["https://s/4.jpg", "https://s/3.jpg"])   # 今ある 1・外した 2・重なった 3 は除く。確かな取り方が先
        self.assertNotIn("_img", out[0])

    def test_find_character_only_that_person(self):
        item = {"name": "X", "emblem_kind": "character"}
        got = [cand(1, subject="Harry"), cand(2, subject="Ron"), cand(3, subject="Harry 2")]
        with mock.patch.object(ef, "STRATEGIES", [("標準", "gather")]), mock.patch.object(ef, "gather", lambda it, log, got_: got), \
                mock.patch.object(ef, "check", lambda c, *a, **k: c):
            out = ec.find(item, "Harry 2", n=6)
        self.assertEqual([c["image"] for c in out], ["https://s/1.jpg", "https://s/3.jpg"])


class Shop(unittest.TestCase):
    def test_queue_and_view(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "c.json"
            ec.queue("X", {"_emblem_cands": [{"image": "i", "subject": "A"}]}, p)
            ec.queue("X", {"_emblem_cands": [{"image": "i", "subject": "A"}]}, p)
            self.assertEqual(ec.load(p)["wants"], [{"board": "X", "subject": "A"}])   # 同じ依頼は 1 回
            with self.assertRaises(ValueError):
                ec.queue("X", {"_emblem_pick": [{"image": "old", "pick": "https://nowhere/x.jpg"}]}, p)   # 並んでいない網址は受けない
            st = ec.load(p)
            st["cands"] = {"X": {"A": [{"image": "https://s/1.jpg", "why": "Wikipedia"}, {"image": "emblems/a.webp", "why": "x"}]}}
            ec.save(st, p)
            ec.queue("X", {"_emblem_pick": [{"image": "old", "pick": "https://s/1.jpg"}]}, p)
            self.assertEqual(ec.load(p)["picks"][0]["subject"], "A")
            v = ec.view(ec.load(p), "X", [{"image": "emblems/a.webp", "subject": "A"}, {"image": "emblems/b.webp", "subject": "B"}])
            self.assertEqual([c["image"] for c in v["emblems/a.webp"]["cands"]], ["https://s/1.jpg"])   # 今の小元素にある画像は出さない
            self.assertTrue(v["emblems/a.webp"]["wait"])
            self.assertEqual(v["emblems/b.webp"], {"cands": [], "wait": False})

    def test_run_shop_collects_then_swaps(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "c.json"
            ec.queue("X", {"_emblem_cands": [{"image": "i", "subject": "A"}]}, p)
            with mock.patch.object(ec, "find", lambda item, s, log=print, n=6: [{"image": "https://s/1.jpg", "why": "W"}]):
                self.assertTrue(ec.run_shop(lambda *a: None, p, items=[{"name": "X"}]))
            st = ec.load(p)
            self.assertEqual((st["wants"], st["cands"]["X"]["A"][0]["image"]), ([], "https://s/1.jpg"))
            ec.queue("X", {"_emblem_pick": [{"image": "old", "pick": "https://s/1.jpg"}]}, p)
            seen = []
            with mock.patch.object(ec, "apply_pick", lambda n, o, c, log=print: seen.append((n, o, c["image"])) or True):
                ec.run_shop(lambda *a: None, p)
            self.assertEqual(seen, [("X", "old", "https://s/1.jpg")])
            self.assertEqual(ec.load(p)["cands"]["X"], {})                 # 選んだ人の候補は片づく
            self.assertFalse(ec.run_shop(lambda *a: None, p))               # やることなし


class Pick(unittest.TestCase):
    def test_apply_pick_swaps_and_locks(self):
        """今の写真を外して（emblem_reject へ）選んだ候補を入れ、入れた小元素を固定する。"""
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "items.yaml").write_text(
                'items:\n  - name: "X"\n    emblem_kind: "person"\n    emblem: [{"subject": "A", "image": "https://old/a.webp", "source": "https://old/a.jpg"},'
                ' {"subject": "B", "image": "https://old/b.webp"}]\n', encoding="utf-8")
            c = {"subject": "A", "why": "W", "image": "https://new/a.jpg", "page": "p", "shape": "cutout"}

            def fake_commit(item, good, picks, replace=False, log=print):
                emblem.write_item(item["name"], list(item.get("emblem") or []) + [{**good[0], "image": "emblems/a-new.webp"}], None)
            saved = emblem.ROOT, ef.ROOT
            emblem.ROOT = ef.ROOT = root
            try:
                with mock.patch.object(ef, "commit", fake_commit):
                    self.assertTrue(ec.apply_pick("X", "https://old/a.webp", c))
                    self.assertFalse(ec.apply_pick("X", "https://old/a.webp", c))   # 元がもうない：何もしない
                got = ef.load_items()[0]
            finally:
                emblem.ROOT, ef.ROOT = saved
        self.assertEqual([x["image"] for x in got["emblem"]], ["https://old/b.webp", "emblems/a-new.webp"])
        self.assertTrue(got["emblem"][1]["lock"])
        self.assertNotIn("lock", got["emblem"][0])
        self.assertIn("https://old/a.jpg", got["emblem_reject"])
        self.assertNotIn("emblem_redo", got)                                   # 同じ人を探し直さない（選んだので）


class Library(unittest.TestCase):
    def test_apply_requests_cands_and_pick(self):
        c = {"emblem": [{"image": "https://x/a.webp", "subject": "A"}], "emblem_cands": {"A": [{"image": "https://s/1.jpg", "why": "W"}]},
             "emblem_requests": [{"_emblem_cands": [{"image": "https://x/a.webp", "subject": "A"}, {"image": "i", "subject": "B"}],
                                  "_emblem_pick": [{"image": "https://x/a.webp", "pick": "https://s/1.jpg"}, {"image": "https://x/a.webp", "pick": "https://evil/x"}]}]}
        add = le.apply_requests(c)
        self.assertEqual(add["emblem_want"], ["A", "B"])
        self.assertEqual(add["emblem_picks"], [{"old": "https://x/a.webp", "subject": "A", "cand": {"image": "https://s/1.jpg", "why": "W"}}])
        self.assertEqual(add["emblem_requests"], [])
        self.assertNotIn("emblem_state", add)                                   # 外す・替えるがないので探し直さない

    def test_serve_collects_for_wanted(self):
        b = {"id": 1, "name": "X", "wd": "Q1", "config": {"emblem_want": ["A"], "emblem_cands": {"Z": [{"image": "z"}]}}}
        with mock.patch.object(ec, "find", lambda item, s, log=print, n=6: [{"image": "https://s/1.jpg", "why": "W"}]):
            add = le.serve(b, {"section": "运动", "subs": {}}, None, "https://x.supabase.co", get=lambda p: {"entities": {}})
        self.assertEqual(add["emblem_want"], [])
        self.assertEqual(add["emblem_cands"], {"Z": [{"image": "z"}], "A": [{"image": "https://s/1.jpg", "why": "W"}]})


class Page(unittest.TestCase):
    def test_tile_carries_candidates_and_sheet_has_action(self):
        rows = [{"name": "A", "emblems": [{"image": "emblems/a.webp", "subject": "X", "why": "Wiki", "lock": False,
                                           "cands": [{"image": "https://s/1.jpg", "why": "W"}], "wait": True}],
                 "bg": {}, "thumbs": []}]
        h = render._admin_emm(rows)
        self.assertIn('data-wait="1"', h)
        self.assertIn("https://s/1.jpg", h)
        self.assertIn('data-a="cands"', h)
        self.assertIn('data-go="cands"', h)
        self.assertIn("_emblem_pick", render.EMM_JS)


if __name__ == "__main__":
    unittest.main()
