"""digest.retry_images：已经出刊、没有自己配图的报道，之后每次出刊自动再找（原文被挡・限流时）。不访问外网。

    python -m unittest discover tests
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import images  # noqa: E402


class RetryImagesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        for d in ("reports", "inbox", "state"):
            (root / d).mkdir()
        day = dt.date.today().isoformat()
        stories = [{"headline": "联名", "url": "https://natalie.example/1", "image": None, "source": "ナタリー"},
                   {"headline": "已有图", "url": "https://a.example/2", "image": "https://a.example/2.jpg"}]
        self.report = root / "reports" / f"{day}.json"
        self.report.write_text(json.dumps({"date": day, "items": [{"name": "gelato pique", "stories": stories}]}))
        entries = [{"n": 1, "title": "人気画像5位は「Mrs. GREEN APPLEとジェラピケが初コラボ」より", "url": "https://news.google.com/x",
                    "link": "https://natalie.example/1", "source": "ナタリー", "date": None, "image": ""},
                   {"n": 2, "title": "Mrs. GREEN APPLE×ジェラート ピケ初コラボ！", "url": "https://walker.example/3",
                    "source": "ウォーカープラス", "date": None, "image": "https://walker.example/3.jpg"}]
        (root / "inbox" / f"{day}.json").write_text(json.dumps({"date": day, "items": [{"name": "gelato pique", "entries": entries}]}))
        self.calls = []

        def fake_pick(chosen, refs, url, budget=None, avoid=(), siblings=()):
            self.calls.append((url, [e.url for e in refs], [e.url for e in siblings], budget))
            return images.Result("https://walker.example/3.jpg", "同一件事的别家报道 walker.example", [])
        self.patches = [mock.patch.object(digest, "REPORTS_DIR", root / "reports"), mock.patch.object(digest, "INBOX_DIR", root / "inbox"),
                        mock.patch.object(digest, "IMG_RETRY_FILE", root / "state" / "img_retry.json"),
                        mock.patch.object(digest, "load_config", lambda: ({}, [{"name": "gelato pique", "keywords": ["ジェラピケ"]}])),
                        mock.patch.object(images, "pick", fake_pick), mock.patch("sys.stderr")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_found_later_and_written_back(self):
        self.assertEqual(digest.retry_images(), 1)
        url, refs, sibs, budget = self.calls[0]
        self.assertEqual((url, refs, sibs, budget), ("https://natalie.example/1", ["https://news.google.com/x"],
                                                     ["https://walker.example/3"], digest.IMG_RETRY_BUDGET))
        st = json.loads(self.report.read_text())["items"][0]["stories"][0]
        self.assertEqual(st["image"], "https://walker.example/3.jpg")
        self.assertEqual(len(self.calls), 1)   # 自己の図があるほうは探さない

    def test_not_retried_again_within_hours(self):
        with mock.patch.object(images, "pick", lambda *a, **k: images.Result(None, "", [], ["原文 HTTP 405"])):
            self.assertEqual(digest.retry_images(), 0)
        with mock.patch.object(images, "pick", side_effect=AssertionError("6 時間以内はもう探さない")):
            self.assertEqual(digest.retry_images(), 0)


if __name__ == "__main__":
    unittest.main()
