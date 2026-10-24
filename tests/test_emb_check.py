"""エンブレムの点検（harness/emb_check.py）の画像の判断。ネットには出ない。"""
import pathlib
import sys
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import emb_check  # noqa: E402


class EmbCheck(unittest.TestCase):
    def test_white_box(self):
        im = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        ImageDraw.Draw(im).ellipse((20, 20, 80, 80), fill=(200, 0, 0, 255))
        self.assertTrue(emb_check.white_box(im))          # 白い地が抜けていないロゴ
        clear = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(clear).ellipse((20, 20, 80, 80), fill=(200, 0, 0, 255))
        self.assertFalse(emb_check.white_box(clear))      # 地を抜いたもの

    def test_cut_edge(self):
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((10, 0, 90, 99), fill=(90, 60, 40, 255))
        self.assertTrue(emb_check.cut_edge(im))           # 頭の上が平らに切れた（上の端の 8 割が不透明）
        ok = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(ok).ellipse((30, 0, 70, 99), fill=(90, 60, 40, 255))
        self.assertFalse(emb_check.cut_edge(ok))          # 頭の先が少し触れるだけ
        self.assertFalse(emb_check.cut_edge(Image.new("RGB", (50, 50), "red")))   # 写真（切り抜きでない）は見ない

    def test_same_and_bad_source(self):
        a = Image.linear_gradient("L").resize((120, 120))
        self.assertLessEqual(bin(emb_check.dhash(a) ^ emb_check.dhash(a.resize((90, 90)))).count("1"), emb_check.SAME_BITS)
        self.assertTrue(emb_check.BAD_SOURCE.search("400px-Gulliver_SSBB_Trophy.png"))
        self.assertFalse(emb_check.BAD_SOURCE.search("Gulliver_NH.png"))


if __name__ == "__main__":
    unittest.main()
