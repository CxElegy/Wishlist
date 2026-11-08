"""写真に焼き込まれた余白を測ってページに書く（scripts/photo_bands.py，2026-11-08）。"""
import io
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import photo_bands  # noqa: E402
import render  # noqa: E402


def png(w, h, box=None):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (255, 255, 255))
    if box:
        d = ImageDraw.Draw(im)
        for x in range(box[0], box[2]):   # 縞の中身（無地にしない）
            d.line([(x, box[1]), (x, box[3])], fill=(200, (x * 37) % 255, 40))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


class Bands(unittest.TestCase):
    def test_white_margin_is_measured(self):
        v = photo_bands.bands(png(400, 400, (100, 60, 300, 340)))
        self.assertEqual(len(v), 5)
        self.assertAlmostEqual(v[0], 0.15, delta=0.03)   # 上
        self.assertAlmostEqual(v[3], 0.25, delta=0.03)   # 左
        self.assertEqual(v[4], "#ffffff")

    def test_no_margin_gives_nothing(self):
        self.assertEqual(photo_bands.bands(png(400, 300, (0, 0, 400, 300))), [])

    def test_measure_uses_cache_and_inject_adds_attr(self):
        calls = []
        cache = {"https://a.example/old.jpg": {"t": [], "m": "", "k": None, "v": 4}}
        page = '<img src="https://a.example/p.jpg" alt=""><img src="https://a.example/old.jpg">'

        def fetch(u):
            calls.append(u)
            return png(400, 400, (100, 60, 300, 340))
        photo_bands.measure(photo_bands.urls_in(page), cache, fetch, log=lambda _m: None)
        self.assertEqual(calls, ["https://a.example/p.jpg"])
        out = photo_bands.inject(page, cache)
        self.assertIn('<img src="https://a.example/p.jpg" data-t="', out)
        self.assertNotIn('old.jpg" data-t', out)

    def test_broken_photo_is_remembered_as_none(self):
        cache = {}

        def boom(u):
            raise OSError("down")
        photo_bands.measure(["https://a.example/x.jpg"], cache, boom, log=lambda _m: None)
        self.assertEqual(cache, {"https://a.example/x.jpg": {"t": [], "m": "", "k": None, "v": 4}})

    def test_fit_js_reads_data_t(self):
        self.assertIn("img.dataset.t", render.FIT_JS)


if __name__ == "__main__":
    unittest.main()
