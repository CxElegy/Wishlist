"""scripts/hdimg.py（配図の OpenCV 高清化・本站保存）的测试。不访问外网。

    python -m unittest discover tests
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import hdimg  # noqa: E402
import images  # noqa: E402
import render  # noqa: E402


def photo(w, h):
    """细节多的假照片（格子＋斜线），量清晰度用。"""
    img = np.full((h, w, 3), 128, np.uint8)
    img[::8, :] = 30
    img[:, ::8] = 220
    cv2.line(img, (0, 0), (w - 1, h - 1), (0, 0, 255), 2)
    return img


def sharpness(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def story(img, date, weight="normal", via="og:image"):
    return {"headline": "h", "url": "https://news.example/" + img, "image": "https://img.example/" + img,
            "image_via": via, "date": date, "weight": weight}


class EnhanceTest(unittest.TestCase):
    def test_upscales_to_target_and_is_sharper_than_plain_resize(self):
        src = photo(400, 225)
        out = hdimg.enhance(src, 1280)
        self.assertEqual(out.shape[:2], (720, 1280))
        plain = cv2.resize(src, (1280, 720), interpolation=cv2.INTER_LINEAR)
        g = lambda x: cv2.cvtColor(x, cv2.COLOR_BGR2GRAY)
        self.assertGreater(sharpness(g(out)), sharpness(g(plain)))

    def test_flat_area_not_noisy(self):
        """平坦なところ（空・単色の背景）はシャープで粒を立てない（差 < THRESHOLD は触らない）。"""
        out = hdimg.enhance(np.full((200, 300, 3), 90, np.uint8), 900)
        self.assertLess(float(out.std()), 1.0)

    def test_never_enlarges_when_already_big(self):
        out = hdimg.enhance(photo(2000, 1000), 1280)
        self.assertEqual(out.shape[1], 1280)


class PlanTest(unittest.TestCase):
    def test_newest_two_per_work_and_headlines_are_big(self):
        rep = {"date": "2026-10-17", "items": [{"name": "GTA 6", "stories": [
            story("a.jpg", "2026-10-17"), story("b.jpg", "2026-10-16"), story("c.jpg", "2026-10-15"),
            story("d.jpg", "2026-10-14", weight="lead"), story("cover.jpg", "2026-10-17", via="作品封面")]}]}
        p = hdimg.plan([rep], "2026-10-17")
        target = {u.rsplit("/", 1)[1]: t for u, (t, _) in p.items()}
        self.assertEqual(target, {"a.jpg": hdimg.BIG_PX, "b.jpg": hdimg.BIG_PX, "c.jpg": hdimg.CARD_PX, "d.jpg": hdimg.BIG_PX})
        self.assertEqual(p["https://img.example/a.jpg"][1], "https://news.example/a.jpg")  # Referer 用の原文ページ

    def test_old_issues_ignored(self):
        rep = {"date": "2026-10-01", "items": [{"name": "x", "stories": [story("old.jpg", "2026-10-01")]}]}
        self.assertEqual(hdimg.plan([rep], "2026-10-17"), {})


class ClearTest(unittest.TestCase):
    def test_blur_score_orders_sharp_and_blurred(self):
        sharp = photo(800, 450)
        self.assertLess(hdimg.blur_score(sharp), hdimg.blur_score(cv2.GaussianBlur(sharp, (0, 0), 3)))

    def test_small_but_sharp_left_alone(self):
        """小さくてもくっきりした図（文字のバナーなど）は、看得清なので触らない。"""
        need, scale, _ = hdimg.unclear(photo(700, 393), hdimg.BIG_PX)
        self.assertGreater(scale, hdimg.ENLARGE)
        self.assertFalse(need)

    def test_small_and_blurry_is_unclear(self):
        need, _, b = hdimg.unclear(cv2.GaussianBlur(photo(600, 340), (0, 0), 1.5), hdimg.BIG_PX)
        self.assertTrue(need, b)

    def test_big_soft_photo_not_touched(self):
        """大きいのにぼやけた写真（背景ぼかし）は撮り方。拡大しないので測りもしない。"""
        need, _, b = hdimg.unclear(cv2.GaussianBlur(photo(1600, 900), (0, 0), 4), hdimg.BIG_PX)
        self.assertFalse(need)
        self.assertIsNone(b)

    def test_trim_white_padding(self):
        img = np.full((300, 500, 3), 255, np.uint8)
        img[50:250, 100:400] = photo(300, 200)
        self.assertEqual(hdimg.trim_white(img).shape[:2], (200, 300))


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        (root / "docs").mkdir()
        self.patches = [mock.patch.object(hdimg, "ROOT", root), mock.patch.object(hdimg, "PICS_DIR", root / "docs" / "pics"),
                        mock.patch.object(hdimg, "STATE_FILE", root / "state" / "hdimg.json")]
        for p in self.patches:
            p.start()
        self.root = root

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def fake_fetch(self, imgs, hotlink=()):
        def fetch(url, limit, referer=None):
            name = url.rsplit("/", 1)[1]
            if name in hotlink and not referer:
                return images.Fetched(403, {}, b"hotlink")
            return images.Fetched(200, {}, cv2.imencode(".png", imgs[name])[1].tobytes())
        return fetch

    def test_only_unclear_and_hotlinked_are_saved(self):
        rep = {"date": "2026-10-17", "items": [{"name": "w", "stories": [
            story("blurry.jpg", "2026-10-17"), story("sharp.jpg", "2026-10-16"),
            story("fine.jpg", "2026-10-15"), story("sina.jpg", "2026-10-14")]}]}
        imgs = {"blurry.jpg": cv2.GaussianBlur(photo(600, 340), (0, 0), 1.5), "sharp.jpg": photo(700, 393),
                "fine.jpg": photo(1600, 900), "sina.jpg": photo(690, 460)}
        with mock.patch.object(images, "_fetch", self.fake_fetch(imgs, hotlink={"sina.jpg"})):
            hdimg.run("2026-10-17", [rep])
        st = hdimg.load_state()
        blurry = st["https://img.example/blurry.jpg"]
        self.assertEqual((blurry["why"], blurry["out"]), ("看不清", [1280, 725]))
        self.assertTrue((self.root / "docs" / blurry["local"]).exists())
        self.assertNotIn("local", st["https://img.example/sharp.jpg"])   # 小さいけど看得清：触らない
        self.assertNotIn("local", st["https://img.example/fine.jpg"])
        self.assertEqual(st["https://img.example/sina.jpg"]["why"], "防盗链")
        self.assertEqual(set(hdimg.local_map()), {"https://img.example/blurry.jpg", "https://img.example/sina.jpg"})

    def test_tiny_bing_thumb_replaced_by_wide_one_without_padding(self):
        url = "https://www.bing.com/th?id=ONUT.abc&pid=News&w=1200"
        padded = np.full((1686, 1200, 3), 255, np.uint8)
        padded[300:1386, 200:1000] = photo(800, 1086)

        def fetch(u, limit, referer=None):
            img = padded if "&w=1200" in u else photo(100, 100)
            return images.Fetched(200, {}, cv2.imencode(".png", img)[1].tobytes())
        rep = {"date": "2026-10-17", "items": [{"name": "w", "stories": [
            {"headline": "h", "url": "https://n.example/1", "image": url, "date": "2026-10-17"}]}]}
        with mock.patch.object(images, "_fetch", fetch):
            hdimg.run("2026-10-17", [rep])
        r = hdimg.load_state()[url]
        self.assertEqual((r["why"], r["out"]), ("Bing の小さい縮小画像", [800, 1086]))

    def test_files_dropped_when_story_leaves_window(self):
        rep = {"date": "2026-10-17", "items": [{"name": "w", "stories": [story("blurry.jpg", "2026-10-17")]}]}
        imgs = {"blurry.jpg": cv2.GaussianBlur(photo(500, 300), (0, 0), 2)}
        with mock.patch.object(images, "_fetch", self.fake_fetch(imgs)):
            hdimg.run("2026-10-17", [rep])
            self.assertEqual(len(list((self.root / "docs" / "pics").glob("*.webp"))), 1)
            hdimg.run("2026-10-30", [rep])
        self.assertEqual(hdimg.load_state(), {})
        self.assertEqual(list((self.root / "docs" / "pics").glob("*.webp")), [])


class RenderTest(unittest.TestCase):
    def test_local_copy_first_then_original(self):
        with mock.patch.object(render, "_LOCAL", [{"https://img.example/a.jpg": "pics/abc.webp"}]):
            html = render._pic({"image": "https://img.example/a.jpg", "_fbs": [], "_work": "w"})
        self.assertIn('src="pics/abc.webp"', html)
        self.assertIn('data-fb="https://img.example/a.jpg"', html)


if __name__ == "__main__":
    unittest.main()
