"""本站保存の写真（src が pics/…・hdimg）の切る位置の材料（2026-11-19：店長のページの pics/ 116 枚に data-m が 0）。
render._pic は一時保管の記録を元の網址で引き、hdimg がそのファイルで測った m・c・k・p を先に使う。ほかの写真の出力は変えない。網に出ない。"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import hdimg  # noqa: E402
import photo_store as P  # noqa: E402
import render  # noqa: E402

ORIG = "https://img.example/a.jpg"
LOCAL = "pics/" + P.key(ORIG) + ".webp"
M = [[0] * 5 + [50, 50] + [0] * 5, [0] * 6 + [100] + [0] * 5]
M_CSS = "0,0,0,0,0,50,50,0,0,0,0,0;0,0,0,0,0,0,100,0,0,0,0,0"


class PicMarks(unittest.TestCase):
    def setUp(self):
        self._on = list(P._ON)
        P._ON[:] = [False]
        self.addCleanup(lambda: P._ON.__setitem__(slice(None), self._on))
        self.addCleanup(lambda: P._CACHE.__setitem__(slice(None), []))

    def pic(self, store, marks, image=ORIG):
        P._CACHE[:] = [{"base": "https://s.example", "p": store, "x": {}, "stat": {}}]
        with mock.patch.object(render, "_LOCAL", [{ORIG: LOCAL}]), mock.patch.object(render, "_MARKS", [marks]):
            return render._pic({"image": image, "_fbs": [], "_work": "w"})

    def test_local_src_uses_record_of_original_url(self):
        """src は pics/… のまま、主役の位置・色は元の網址の一時保管の記録から。"""
        h = self.pic({P.key(ORIG): {"at": 1, "b": 5, "c": "#112233", "m": M}}, {})
        self.assertIn(f'src="{LOCAL}"', h)
        self.assertIn(f'data-m="{M_CSS}"', h)
        self.assertIn('style="background:#112233"', h)

    def test_local_measure_wins_and_gives_text_and_people(self):
        """hdimg がファイルで測った物が先（字の範囲 data-k・人の範囲 data-p も：m だけだと題字を切った）。"""
        mk = {LOCAL: {"m": M, "c": "#aabbcc", "k": [0.1, 0.5, 0.9, 0.8], "p": [0.2, 0.1, 0.6, 0.4]}}
        h = self.pic({P.key(ORIG): {"at": 1, "b": 5, "c": "#112233", "m": [[100] + [0] * 11, [100] + [0] * 11]}}, mk)
        self.assertIn(f'data-m="{M_CSS}"', h)
        self.assertIn('data-k="0.1,0.5,0.9,0.8" data-p="0.2,0.1,0.6,0.4"', h)
        self.assertIn('background:#aabbcc', h)

    def test_no_record_no_mark(self):
        h = self.pic({}, {})
        self.assertIn(f'src="{LOCAL}"', h)
        self.assertNotIn("data-m=", h)
        self.assertNotIn("data-k=", h)
        self.assertNotIn("background:", h)

    def test_image_already_local_finds_original(self):
        """記事の写真の網址がもう pics/… でも、対応表から元の網址の記録を引く。"""
        h = self.pic({P.key(ORIG): {"at": 1, "b": 5, "m": M}}, {}, image=LOCAL)
        self.assertIn(f'data-m="{M_CSS}"', h)

    def test_other_photos_unchanged(self):
        """店長の道のほかの写真（http の網址・置き場の写真）は今までどおり src の網址で引き、data-k・data-p は付けない。"""
        u = "https://x.example/b.jpg"
        h = self.pic({P.key(u): {"at": 1, "b": 5, "c": "#010203", "m": M}}, {LOCAL: {"m": M, "k": [0, 0, 1, 1]}}, image=u)
        self.assertIn(f'src="https://s.example/storage/v1/object/public/photos/{P.key(u)}-800.webp"', h)
        self.assertIn(f'data-m="{M_CSS}" data-e="s"', h)
        self.assertNotIn("data-k=", h)
        self.assertIn('background:#010203', h)


class FillMarks(unittest.TestCase):
    def test_measures_local_file_once(self):
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            pics = pathlib.Path(d) / "pics"
            pics.mkdir()
            a = np.full((300, 500, 3), 200, np.uint8)
            a[100:200, 200:300] = 20   # 真ん中に濃い物
            Image.fromarray(a).save(pics / "abc.webp")
            st = {"https://img.example/a.jpg": {"local": "pics/abc.webp"}, "https://img.example/gone.jpg": {"local": "pics/gone.webp"},
                  "https://img.example/plain.jpg": {"w": 10}}
            with mock.patch.object(hdimg, "PICS_DIR", pics):
                self.assertEqual(hdimg.fill_marks(st), 1)
                self.assertEqual(hdimg.fill_marks(st), 0)   # 測った物は測り直さない
            r = st["https://img.example/a.jpg"]
            self.assertEqual(len(r["m"]), 2)
            self.assertGreater(sum(r["m"][0][4:8]), 50)   # 主役は真ん中
            self.assertRegex(r["c"], r"^#[0-9a-f]{6}$")
            self.assertIn("k", r)
            self.assertIn("p", r)
            self.assertNotIn("m", st["https://img.example/gone.jpg"])   # ファイルが無い記録は測らない


if __name__ == "__main__":
    unittest.main()
