"""外した絵（emblem_reject_look）と見た目が近い候補を emblem_fill.check が落とす。同じ絵の別 URL・別の大きさ・JPEG は落ち、別の絵は残る。不访问网络。

    python -m unittest tests.test_emblem_reject_look
"""
import io
import pathlib
import random
import sys
import unittest
from unittest import mock

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem_fill as ef  # noqa: E402


def picture(seed, size=(400, 500)):
    """大きなブロックの模様（立ち絵のような、はっきりした濃淡）。seed が違えば別の絵。"""
    rnd = random.Random(seed)
    small = Image.new("RGB", (12, 15))
    small.putdata([tuple(rnd.randrange(256) for _ in range(3)) for _ in range(12 * 15)])
    return small.resize(size, Image.NEAREST)


def png(im, fmt="PNG"):
    b = io.BytesIO()
    im.save(b, fmt)
    return b.getvalue()


class RejectLook(unittest.TestCase):
    def run_check(self, pics, looks):
        cands = [{"subject": "X", "image": u, "source": "t", "why": ""} for u in pics]
        with mock.patch.object(ef, "_get", side_effect=lambda u, *a, **k: pics[u]):
            return [c["image"] for c in ef.check(cands, log=lambda *a: None, reject_looks=looks)]

    def test_same_picture_other_url_size_jpeg_is_dropped_other_picture_kept(self):
        a = picture(1)
        looks = ef.reject_looks({"emblem_reject_look": [ef.look_hex(a), "zz-bad"]})   # 読めない鍵は飛ばす
        self.assertEqual(len(looks), 1)
        pics = {"https://cdn/other-url.png": png(a), "https://cdn/half.png": png(a.resize((200, 250))),
                "https://cdn/big.png": png(a.resize((800, 1000))), "https://cdn/q50.jpg": png(a, "JPEG"),
                "https://cdn/different1.png": png(picture(2)), "https://cdn/different2.png": png(picture(3))}
        kept = self.run_check(pics, looks)
        self.assertEqual(sorted(kept), ["https://cdn/different1.png", "https://cdn/different2.png"])

    def test_no_looks_keeps_everything(self):
        a = picture(1)
        self.assertEqual(self.run_check({"https://cdn/a.png": png(a)}, ()), ["https://cdn/a.png"])

    def test_threshold_sits_between_resize_noise_and_other_pictures(self):
        """REJECT_BITS は、同じ絵の拡縮（0）より大きく、別の絵どうしの距離より小さい。"""
        a = ef._hash(picture(1))
        same = ef._hash(picture(1).resize((133, 166)))
        others = [ef._hash(picture(s)) for s in range(2, 30)]
        self.assertLessEqual(bin(a ^ same).count("1"), ef.REJECT_BITS)
        self.assertTrue(all(bin(a ^ h).count("1") > ef.REJECT_BITS for h in others))


if __name__ == "__main__":
    unittest.main()
