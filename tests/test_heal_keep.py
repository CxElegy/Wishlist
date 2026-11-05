"""heal の出刊（edit.json を取り込み直すだけ）で、前の報告で選び済みの絵と cover を落とさない（2026-11-05：402 通し点検で reports が縮んだ）。

    python -m unittest tests.test_heal_keep
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import digest  # noqa: E402


class HealKeep(unittest.TestCase):
    def test_keeps_picked_image_and_cover(self):
        old = {"items": [{"name": "GTA 6", "cover": "c.jpg", "theme": {"accent": "#1"},
                          "stories": [{"url": "u1", "image": "ai.jpg", "image_via": "AI 挑选"}]}]}
        new = [{"name": "GTA 6", "cover": None, "theme": {}, "stories": [{"url": "u1", "image": "cover.jpg", "image_via": "作品封面"},
                                                                         {"url": "u2", "image": "n.jpg"}]}]
        digest.keep_from_report(new, old)
        self.assertEqual(new[0]["stories"][0]["image"], "ai.jpg")
        self.assertEqual(new[0]["stories"][0]["image_via"], "AI 挑选")
        self.assertEqual(new[0]["stories"][1]["image"], "n.jpg")     # 新しい記事はそのまま
        self.assertEqual((new[0]["cover"], new[0]["theme"]), ("c.jpg", {"accent": "#1"}))

    def test_no_old_report(self):
        new = [{"name": "x", "cover": None, "stories": [{"url": "u", "image": "a"}]}]
        digest.keep_from_report(new, None)
        self.assertEqual(new[0]["stories"][0]["image"], "a")

    def test_heal_calls_keep(self):
        src = pathlib.Path(digest.__file__).read_text(encoding="utf-8")
        self.assertIn("keep_from_report(blocks, load_json(REPORTS_DIR", src)


if __name__ == "__main__":
    unittest.main()
