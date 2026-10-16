"""小元素の自動補完（scripts/emblem_fill.py）・本人確認（face_id.py）・プロセス一覧（processes.py）。ネットワークには出ない。

    python -m unittest discover tests
"""

import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem_fill as ef  # noqa: E402
import face_id  # noqa: E402
import processes  # noqa: E402
import render  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Rules(unittest.TestCase):
    def test_kind_inferred_from_type(self):
        self.assertEqual(ef.kind_of({"type": "anime"}), "character")
        self.assertEqual(ef.kind_of({"type": "event"}), "person")
        self.assertEqual(ef.kind_of({"type": "product"}), "brand")
        self.assertEqual(ef.kind_of({"type": "category"}), "topic")
        self.assertEqual(ef.kind_of({"type": "category", "emblem_kind": "brand"}), "brand")
        self.assertEqual(ef.kind_of({"type": "game", "emblem_kind": "???"}), "character")   # 知らない種類は type で推定

    def test_targets(self):
        self.assertEqual(ef.rule({"type": "event", "emblem_kind": "person"})[1:], (3, 6, 10))
        self.assertEqual(ef.rule({"type": "category", "emblem_kind": "brand"})[1:], (1, 1, 1))
        self.assertEqual(ef.rule({"type": "category"})[1:], (2, 3, 5))
        # グループはメンバー全員（最大 10）
        nine = {"type": "event", "emblem_kind": "group", "emblem_who": [f"m{i}" for i in range(9)]}
        self.assertEqual(ef.rule(nine)[2], 9)
        twelve = {**nine, "emblem_who": [f"m{i}" for i in range(12)]}
        self.assertEqual(ef.rule(twelve)[2], 10)
        # 名前を挙げたキャラはその全員が目標（2 人の作品は 2 枚で足りる）
        two = {"type": "game", "emblem_who": ["a", "b"]}
        self.assertEqual(ef.rule(two)[2], 2)

    def test_status(self):
        base = {"name": "x", "type": "game"}
        self.assertEqual(ef.status(base)["state"], "none")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 2})["state"], "low")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 6})["state"], "ok")
        # emblem_skip は「足りている」の理由にならない
        self.assertEqual(ef.status({**base, "emblem_skip": "なし"})["state"], "none")

    def test_audit_sorts_gaps_first(self):
        rows = ef.audit([{"name": "a", "type": "game", "emblem": [{}] * 6}, {"name": "b", "type": "game"},
                         {"name": "c", "type": "game", "emblem": [{}]}])
        self.assertEqual([r["name"] for r in rows], ["b", "c", "a"])

    def test_every_item_resolves(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        for i in items:
            st = ef.status(i)
            self.assertIn(st["kind"], ef.RULES, i["name"])
            self.assertLessEqual(st["target"], 10, i["name"])
            self.assertGreaterEqual(st["target"], st["lo"], i["name"])
            if i.get("emblem_kind"):
                self.assertIn(i["emblem_kind"], ef.RULES, i["name"])


class Sources(unittest.TestCase):
    def test_parse_bing(self):
        html = ('x murl&quot;:&quot;https://a.example/p/1.jpg&quot; y murl&quot;:&quot;https://a.example/p/1.jpg&quot; '
                'murl&quot;:&quot;https://b.example/bad name.png&quot; murl&quot;:&quot;https://c.example/2.webp?x=1&quot;')
        urls = [x["image"] for x in ef.parse_bing(html)]
        self.assertEqual(urls, ["https://a.example/p/1.jpg", "https://c.example/2.webp?x=1"])   # 重複と空白入りの網址は除く

    def test_relevant(self):
        self.assertTrue(ef.relevant("File:Starbucks Corporation Logo 2011.svg.png", "Starbucks"))
        self.assertFalse(ef.relevant("File:Chopin portrait.jpg", "Jay Chou"))
        self.assertTrue(ef.relevant("File:周杰倫 2014.jpg", "周杰倫"))

    def test_twemoji(self):
        self.assertTrue(ef.twemoji("🎾")["image"].endswith("/1f3be.svg"))
        self.assertTrue(ef.twemoji("⛷️")["image"].endswith("/26f7.svg"))   # 異体字セレクタは落とす

    def test_site_images_skip_logos(self):
        import types
        ef_get = ef._get
        ef._get = lambda url, limit=0: (b'<meta property="og:image" content="/og.png"><img src="/img/logo.png">'
                                        b'<img src="/img/member1.jpg">')
        try:
            urls = [x["image"] for x in ef.site_images("https://x.example/a/")]
        finally:
            ef._get = ef_get
        self.assertEqual(urls, ["https://x.example/og.png", "https://x.example/img/member1.jpg"])

    def test_auto_pick_prefers_reliable_sources(self):
        good = [{"subject": "A", "source": "Web 画像検索"}, {"subject": "A", "source": "Wikipedia"},
                {"subject": "B", "source": "Fandom"}, {"subject": "B", "source": "Web 画像検索"}]
        item = {"type": "game", "emblem_who": ["A", "B"]}
        self.assertEqual(sorted(ef.auto_pick(item, good)), [2, 3])   # 1 人 1 枚、Web 検索より Wiki 系を先に


class Identity(unittest.TestCase):
    """face_id.same_person の論理だけ確かめる（モデルなしで、特徴量の代わりに数を使う）。"""

    def setUp(self):
        self._eng, self._sim = face_id.engine, face_id.similarity
        face_id.engine = lambda: ("det", "rec")
        face_id.similarity = lambda a, b: 1.0 if a == b else 0.0

    def tearDown(self):
        face_id.engine, face_id.similarity = self._eng, self._sim

    def test_anchor_keeps_matching_only(self):
        # 0 が代表画像。顔なし（None）と別人（2）は落とす
        self.assertEqual(face_id.same_person([1, 1, None, 2, 1], anchor=0), {0, 1, 4})

    def test_majority_when_anchor_is_wrong(self):
        # 代表画像（0）だけ別の顔：同じ顔が多い方を本人とする
        self.assertEqual(face_id.same_person([9, 1, 1, 1], anchor=0), {1, 2, 3})

    def test_no_faces(self):
        self.assertEqual(face_id.same_person([None, None]), set())

    def test_unavailable_engine(self):
        face_id.engine = lambda: None
        self.assertIsNone(face_id.same_person([1, 1]))


class Processes(unittest.TestCase):
    def test_flows_are_well_formed(self):
        ids = [p["id"] for p in processes.PROCESSES]
        self.assertEqual(len(ids), len(set(ids)))
        for p in processes.PROCESSES:
            self.assertIn(p["lane"], processes.LANES)
            self.assertTrue(p["flow"], p["id"])
            for n in p["flow"]:
                self.assertIn(n["kind"], ("step", "decision", "fan", "store", "table"), p["id"])
                self.assertIn(n.get("lane"), processes.LANES, (p["id"], n["id"]))
                if n["kind"] == "decision":
                    self.assertTrue(n.get("yes") and n.get("no"), (p["id"], n["id"]))
                if n["kind"] == "fan":
                    self.assertTrue(all(len(x) == 3 for x in n["items"]))
                if n["kind"] == "table":
                    self.assertTrue(all(len(x) == 2 for x in n["rows"]))

    def test_render_and_escape(self):
        evil = [{"id": "x", "name": "<b>x</b>", "en": "X", "lane": "ai", "trigger": "t", "summary": "s",
                 "flow": [{"id": "n", "kind": "step", "lane": "ai", "title": "<script>", "text": "&"}]}]
        out = processes.render(evil)
        self.assertNotIn("<script>", out)
        self.assertNotIn("<b>x</b>", out)
        self.assertIn('id="proc-x"', out)

    def test_admin_page_has_processes_and_emblems(self):
        rows = [{"name": "A", "section": "游戏", "emblem": {"kind": "group", "kind_ja": "グループ", "have": 2, "target": 5, "hi": 10,
                                                          "lo": 3, "state": "low", "skip": False, "shapes": {"切り抜き": 2}}}]
        out = render.render_admin({"pipeline": {}, "items": rows, "votes": {}}, {}, "u")
        for p in processes.PROCESSES:
            self.assertIn(f'data-open="proc-{p["id"]}"', out)
        self.assertIn("足りない", out)
        self.assertIn('id="emblems"', out)


if __name__ == "__main__":
    unittest.main()
