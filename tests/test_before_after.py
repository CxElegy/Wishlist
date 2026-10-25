"""Before / After の知らせ（harness/before_after.py）：差がなければ写真なし・切り抜きが差を含む・撮る場所・後で変わる PR。ネットには出ない。"""
import datetime as dt
import io
import pathlib
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import before_after as ba  # noqa: E402


def png(path, box=None, size=(1400, 3000)):
    im = Image.new("RGB", size, (240, 238, 230))
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], 120):   # 地の模様（同じ所は同じ）
        d.rectangle((40, y + 20, 600, y + 60), fill=(30, 30, 40))
    if box:
        d.rectangle(box, fill=(200, 20, 30))
    im.save(path)


class Compose(unittest.TestCase):
    def test_same_two_send_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = pathlib.Path(t, "a.png"), pathlib.Path(t, "b.png")
            png(a), png(b)
            self.assertIsNone(ba.compose(a, b))

    def test_crop_holds_the_change_in_the_middle(self):
        box = (900, 2200, 1100, 2400)   # 1 画面目（900px）より下の変化
        with tempfile.TemporaryDirectory() as t:
            a, b = pathlib.Path(t, "a.png"), pathlib.Path(t, "b.png")
            png(a), png(b, box)
            A, B = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
            boxes = ba.changed_boxes(A, B)
            x0, y0, x1, y1 = ba.focus(A, B, boxes)
            self.assertTrue(x0 <= box[0] and y0 <= box[1] and box[2] <= x1 and box[3] <= y1)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            self.assertLess(abs(cx - 1000), (x1 - x0) * 0.2)
            self.assertLess(abs(cy - 2300), (y1 - y0) * 0.2)
            out = Image.open(io.BytesIO(ba.compose(a, b)))
            self.assertLess(out.height, 1500)   # ページ全体ではなく切り抜き

    def test_size_change_counts(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = pathlib.Path(t, "a.png"), pathlib.Path(t, "b.png")
            png(a, size=(300, 120)), png(b, size=(300, 200))
            self.assertIsNotNone(ba.compose(a, b))


class Spot(unittest.TestCase):
    def test_line(self):
        self.assertEqual(ba.spot("## 何を\n- 直した\n\n画面：index #sec-bleach .emb — BLEACH の小元素\n"),
                         ("", "#sec-bleach .emb", "BLEACH の小元素"))
        self.assertEqual(ba.spot("画面: admin-emblem.html #tbl"), ("admin-emblem.html", "#tbl", "#tbl"))
        self.assertIsNone(ba.spot("画面の変化なし"))
        self.assertIsNone(ba.spot("画面：変わらない（Discord の知らせの仕組みだけ）"))   # #376 の説明で欄を探しに行った


class Later(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(ba.later_of(["scripts/emblem_fill.py"])[0], "后台作業")
        self.assertEqual(ba.later_of(["BACKLOG.md", "scripts/library_emblem.py"])[0], "ライブラリの小元素")
        self.assertIsNone(ba.later_of(["scripts/render.py"]))

    def test_next_cron(self):
        now = dt.datetime(2026, 10, 25, 3, 50, tzinfo=dt.timezone.utc)
        self.assertEqual(ba._cron_next("47 * * * *", now).strftime("%H:%M"), "04:47")
        self.assertEqual(ba._cron_next("29 */2 * * *", now).strftime("%H:%M"), "04:29")
        self.assertEqual(ba._cron_next("7 0,9 * * *", now).strftime("%H:%M"), "09:07")
        self.assertIsNone(ba._cron_next("47 0 * * 1", now))

    def test_later_waits_for_a_run_after_merge(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t, "ba-pending-1")
            d.mkdir()
            merged = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
            d.joinpath("meta.json").write_text(json.dumps({"num": "1", "title": "t", "url": "u", "where": None,
                                                            "workflow": "后台作業", "merged_at": merged.isoformat()}))
            old, ba.last_success = ba.last_success, lambda name: merged - dt.timedelta(minutes=5)   # 合併より前の回
            try:
                ba.later("", "", t)
                self.assertEqual(pathlib.Path(t, "sent.txt").read_text(), "")
                ba.later("ライブラリの小元素", dt.datetime.now(dt.timezone.utc).isoformat(), t)   # 別の workflow の回
                self.assertEqual(pathlib.Path(t, "sent.txt").read_text(), "")
            finally:
                ba.last_success = old

    def test_headline(self):
        self.assertIn("19→32 枚", ba.headline("名簿", "BLEACH の小元素", {"test-a-1400": 19}, {"test-a-1400": 32}))


if __name__ == "__main__":
    unittest.main()
