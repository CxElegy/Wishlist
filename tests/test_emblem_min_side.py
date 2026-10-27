"""小元素を取るとき短い辺 256px 未満を断る（E18 の根）。ネットワークには出ない。"""

import inspect
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem  # noqa: E402


class MinSide(unittest.TestCase):
    def test_full_url_widens_fandom_and_wikimedia(self):
        f = "https://static.wikia.nocookie.net/x/images/a/ab/Y.png/revision/latest/scale-to-width-down/400?cb=1"
        self.assertIn(f"/scale-to-width-down/{emblem.FULL_W}?cb=1", emblem.full_url(f))
        w = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Y.jpg/500px-Y.jpg"
        self.assertEqual(emblem.full_url(w), w.replace("500px-", f"{emblem.FULL_W}px-"))
        self.assertEqual(emblem.full_url("https://example.com/a.png"), "https://example.com/a.png")

    def test_save_cut_refuses_small(self):
        from PIL import Image
        with self.assertRaises(ValueError):
            emblem.save_cut(Image.new("RGBA", (247, 434)), "t-small", emblem.BUST_MIN_SIDE)

    def test_every_taking_path_has_the_floor(self):
        """cut_out・fit_all・cut_all の save_cut は下限を渡す（全身 body だけ 0）。片方の入口だけ直さない。"""
        for fn in (emblem.cut_out, emblem.fit_all, emblem.cut_all):
            src = inspect.getsource(fn)
            self.assertIn("BUST_MIN_SIDE", src, fn.__name__)


if __name__ == "__main__":
    unittest.main()
