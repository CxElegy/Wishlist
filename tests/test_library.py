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


if __name__ == "__main__":
    unittest.main()
