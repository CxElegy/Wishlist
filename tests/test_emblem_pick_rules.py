"""小元素の選び方の規則（harness/emblem_pick_rules.py）の点検：規則が動くこと・今の本番の小元素を数えること。"""
import pathlib
import sys
import unittest

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import emblem_pick_rules as R  # noqa: E402

X_CEILING = 40   # 2026-10-31 の数は 32（小さすぎる 14・顔のアップ 18）。規則に当たる絵を増やさない棚


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
        self.assertLessEqual(sm["x"], X_CEILING, f"規則が × にする小元素が増えた：{sm['x_by_reason']}")


if __name__ == "__main__":
    unittest.main()
