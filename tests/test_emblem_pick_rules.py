"""小元素の選び方の規則（harness/emblem_pick_rules.py）の点検：規則が動くこと・今の本番の小元素を数えること。"""
import json
import pathlib
import sys
import unittest

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import emblem_pick_rules as R  # noqa: E402

SHELF = json.loads((ROOT / "harness" / "labels" / "emblem_x_queue.json").read_text())   # × の棚（上限と理由の種類）。名前の一覧は本番の入れ替えですぐずれるので持たない


class PickRules(unittest.TestCase):
    def test_small_image_is_x(self):
        img = Image.new("RGBA", (100, 100), (200, 0, 0, 255))
        self.assertEqual(R.original_verdict(img)[0], "x")

    def test_no_face_is_back(self):
        img = Image.new("RGBA", (400, 400), (200, 0, 0, 255))
        self.assertEqual(R.original_verdict(img)[0], "-")

    def test_production_audit_counts(self):
        rows, sm = R.audit_production()
        self.assertGreater(sm["n"], 300)
        self.assertEqual(sm["n"], sm["o"] + sm["x"] + sm["-"])
        self.assertLessEqual(sm["x"], SHELF["shelf"], "× が棚を超えた（新しい壊れ方か本番の入れ替え）。名前は --audit で見て、規則で直す")
        self.assertEqual(sorted(set(sm["x_by_reason"]) - set(SHELF["reasons"])), [], "知らない理由の × が出た（新しい壊れ方）。理由を足すか規則で直す")


if __name__ == "__main__":
    unittest.main()
