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
