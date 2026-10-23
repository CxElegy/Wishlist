"""ライブラリ（db/library.sql・scripts/library.py）：同じものかどうかの印・共有の設定と人ごとの置き方の分け方。ネットには出ない。"""
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import library  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Key(unittest.TestCase):
    def test_same_name_in_other_writing_is_one_board(self):
        self.assertEqual(library.board_key({"name": "ＧＴＡ ６"}), library.board_key({"name": "gta6"}))
        self.assertEqual(library.board_key({"name": "あつ森"}), "n:あつ森")
        self.assertEqual(library.board_key({"name": "x", "wikidata": "Q123"}), "wd:Q123")

    def test_shop_items_split(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        boards, parents, follows = library.shop_rows(items)
        self.assertEqual(len({b["key"] for b in boards}), len(items))   # 店長の版面は 1 つずつ別の版面
        for b in boards:
            for k in library.PERSONAL:
                self.assertNotIn(k, b["config"])   # 置き方は人ごと（follows）
        self.assertEqual([f["pos"] for f in follows], list(range(len(items))))
        self.assertTrue(all(f["account"] == "test1" for f in follows))



class Wikidata(unittest.TestCase):
    """番号の決め方（ネットには出ない：get を差し替える）。"""
    def ent(self, labels):
        return {"labels": {k: {"value": v} for k, v in labels.items()}, "aliases": {}}

    def test_wiki_titles_pick_best_match(self):
        # 漫威电影：記事名の 1 つ目（映画 1 本）ではなく、名前・検索語が入るシリーズ全体を選ぶ
        def get(p):
            return {"entities": {"Q1": self.ent({"en": "Avengers: Doomsday"})}} if "Doomsday" in p.get("titles", "") \
                else {"entities": {"Q2": self.ent({"zh": "漫威电影宇宙", "en": "Marvel Cinematic Universe"})}}
        item = {"name": "漫威电影", "keywords": ["漫威 电影"], "wiki": ["en:Avengers: Doomsday", "en:Marvel Cinematic Universe"]}
        self.assertEqual(library.find_wikidata(item, get), "Q2")

    def test_topic_without_wiki_has_no_number(self):
        self.assertIsNone(library.find_wikidata({"name": "猫用品", "type": "category"}, lambda p: self.fail("引かない")))

    def test_find_wikidata_brand_category(self):
        def get(p):
            return {"search": [{"id": "Q37158", "label": "Starbucks", "aliases": ["スターバックス"]},
                               {"id": "Q5", "label": "gelato pique"}]}
        brand = {"type": "category", "subs": {"owner": "ブランド"}}
        self.assertEqual(library.find_wikidata({**brand, "name": "gelato pique", "keywords": ["ジェラピケ"]}, get), "Q5")
        # ブランドの品目（マグ）は検索語の「スターバックス」で本体に当たらない
        self.assertIsNone(library.find_wikidata({**brand, "name": "星巴克马克杯", "keywords": ["スターバックス"]}, get))
        # 項目がない（gelato pique は 2026-10-23 に ja/en/zh・全文検索とも 0 件）→ 名前のまま
        self.assertIsNone(library.find_wikidata({**brand, "name": "gelato pique"}, lambda p: {"search": []}))

    def test_search_needs_exact_name(self):
        def get(p):
            return {"search": [{"id": "Q9", "label": "あつまれ どうぶつの森", "aliases": ["あつ森"]}, {"id": "Q8", "label": "どうぶつの森"}]}
        self.assertEqual(library.find_wikidata({"name": "あつ森", "type": "game"}, get), "Q9")
        self.assertIsNone(library.find_wikidata({"name": "まったく別", "type": "game"}, get))

    def test_shop_items_with_number_use_it(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        keys = {i["name"]: library.board_key(i) for i in items}
        self.assertEqual(keys["あつ森"], "wd:Q64566657")
        self.assertEqual(keys["漫威电影"], "wd:Q642878")
        self.assertTrue(keys["猫用品"].startswith("n:"))


if __name__ == "__main__":
    unittest.main()


class Refresh(unittest.TestCase):
    """週 1 回の引き直し（library.refresh・write_wikidata）：断られたのと 0 件を分ける、items.yaml はコメントを残して書く。"""
    ITEMS = [{"name": "A", "wikidata": "Q1"}, {"name": "猫用品", "type": "category"},
             {"name": "gelato pique", "type": "category", "subs": {"owner": "ブランド"}}, {"name": "あつ森", "type": "game"}]

    def test_found_none_skip(self):
        def get(p):
            if p.get("search") == "あつ森":
                return {"search": [{"id": "Q9", "label": "あつ森"}]}
            return {"search": []}
        r = library.refresh(self.ITEMS, get, pause=0)
        self.assertEqual(r["found"], {"あつ森": "Q9"})
        self.assertEqual(r["none"], ["gelato pique"])   # 聞いて 0 件
        self.assertEqual(r["skip"], ["猫用品"])          # 題材は聞かない
        self.assertEqual(r["blocked"], [])

    def test_blocked_is_not_zero_and_stops(self):
        def get(p):
            raise library.WdBlocked("429")
        r = library.refresh(self.ITEMS, get, pause=0)
        self.assertEqual(r["blocked"], ["gelato pique", "あつ森"])   # 1 度断られたら残りは聞かない
        self.assertEqual(r["none"], [])
        self.assertEqual(r["found"], {})

    def test_wd_get_raises_when_refused(self):
        import urllib.error
        from unittest import mock

        def refuse(*a, **k):
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        with mock.patch("urllib.request.urlopen", refuse), mock.patch("time.sleep"):
            with self.assertRaises(library.WdBlocked):
                library._wd_get({"action": "wbsearchentities", "search": "x"})

    def test_write_keeps_comments(self):
        text = ('items:\n  - name: A\n    wikidata: Q1\n    motif: x\n\n  - name: gelato pique\n    # wikidata: なし（引いた）\n    motif: cloud\n\n'
                '  - name: "あつ森"\n    subs: {kind: ゲーム}   # 小分類\n')
        new, done = library.write_wikidata(text, {"gelato pique": "Q5", "あつ森": "Q9", "A": "Q2"})
        self.assertEqual(done, ["gelato pique", "あつ森"])   # 番号がある A は上書きしない
        data = yaml.safe_load(new)["items"]
        self.assertEqual([i.get("wikidata") for i in data], ["Q1", "Q5", "Q9"])
        self.assertNotIn("# wikidata: なし", new)
        self.assertIn("# 小分類", new)

    def test_write_shop_items_roundtrip(self):
        text = (ROOT / "items.yaml").read_text(encoding="utf-8")
        items = yaml.safe_load(text)["items"]
        missing = [i["name"] for i in items if not i.get("wikidata")]
        new, done = library.write_wikidata(text, {n: "Q42" for n in missing})
        self.assertEqual(sorted(done), sorted(missing))
        after = yaml.safe_load(new)["items"]
        self.assertEqual(len(after), len(items))
        self.assertTrue(all(i.get("wikidata") for i in after))
        self.assertEqual([{k: v for k, v in i.items() if k != "wikidata"} for i in after],
                         [{k: v for k, v in i.items() if k != "wikidata"} for i in items])   # ほかは 1 文字も変えない

    def test_refresh_main_writes_log(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "items.yaml"
            p.write_text('items:\n  - name: "あつ森"\n    type: game\n', encoding="utf-8")
            with mock.patch("runlog.LOG_DIR", pathlib.Path(d) / "log"):
                r, done = library.refresh_main(p, lambda q: {"search": [{"id": "Q9", "label": "あつ森"}]})
                rows = __import__("runlog").load("library")
            self.assertEqual(done, ["あつ森"])
            self.assertIn("wikidata: Q9", p.read_text(encoding="utf-8"))
            self.assertEqual((rows[-1]["found"], rows[-1]["blocked"]), (1, 0))
