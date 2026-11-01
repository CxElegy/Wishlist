"""Wikimedia へ直接つなぐ logo / icon を倉庫に置く規則（三星手机 Samsung wordmark.svg の 403：E1・E2）。ネットワークには出ない。"""

import pathlib
import sys
import unittest
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem_fill as ef  # noqa: E402
from wikihttp import is_wikimedia  # noqa: E402

COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/Samsung%20wordmark.svg?width=500"


class LogoLocal(unittest.TestCase):
    def test_remote_wikimedia_logo_goes_local(self):
        item = {"name": "三星手机", "emblem": [{"subject": "Samsung のロゴ", "image": COMMONS, "shape": "logo"},
                                              {"subject": "ほか", "image": "emblems/x.webp", "shape": "cutout"},
                                              {"subject": "絵文字", "image": "https://cdn.jsdelivr.net/x.svg", "shape": "icon"}]}
        with mock.patch.object(ef.emblem, "wordmark_local", return_value=("emblems/s.webp", 0.154, False)), \
                mock.patch.object(ef.emblem, "write_item") as w:
            n = ef.localize_remote(item)
        self.assertEqual(n, 1)
        got = w.call_args[0][1]
        self.assertEqual((got[0]["image"], got[0]["source"], got[0]["ar"]), ("emblems/s.webp", COMMONS, 0.154))
        self.assertEqual(got[1]["image"], "emblems/x.webp")   # 人物の絵は触らない
        self.assertTrue(got[2]["image"].startswith("https://cdn.jsdelivr"))   # Wikimedia 以外は触らない

    def test_failure_leaves_it(self):
        item = {"name": "x", "emblem": [{"subject": "a", "image": COMMONS, "shape": "logo"}]}
        with mock.patch.object(ef.emblem, "wordmark_local", side_effect=OSError("403")), \
                mock.patch.object(ef.emblem, "write_item") as w:
            self.assertEqual(ef.localize_remote(item, log=lambda *a: None), 0)
        w.assert_not_called()

    def test_items_yaml_has_no_remote_wikimedia_logo(self):
        """live：items.yaml の logo / icon に Wikimedia への直リンクが 0（同じ壊れ方を数える点検）"""
        d = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / "items.yaml").read_text(encoding="utf-8"))
        bad = [(i["name"], x.get("subject")) for i in d["items"] for x in i.get("emblem") or []
               if x.get("shape") in ("logo", "icon") and str(x.get("image", "")).startswith("http") and is_wikimedia(x["image"])]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
