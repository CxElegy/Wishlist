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

QUEUE = json.loads((ROOT / "harness" / "labels" / "emblem_x_queue.json").read_text())["x"]   # 直す待ちの × の一覧（2026-10-31：32）


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
        xs = {f"{r[0]}|{r[1]}" for r in rows if r[2] == "x"}
        self.assertEqual(sorted(xs - set(QUEUE)), [], "待ちの一覧にない × が出た（新しい壊れ方）。直すか、直す待ちとして一覧に足す")
        self.assertEqual(sorted(set(QUEUE) - xs), [], "もう × でない小元素が一覧に残っている。harness/labels/emblem_x_queue.json から外す（棚を下げる）")


if __name__ == "__main__":
    unittest.main()
