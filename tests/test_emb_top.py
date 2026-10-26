"""版面の顔に出す小元素は名簿の順の上位だけ（脇役が出すぎない）。"""
import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402


def _alts(n):
    items = [{"image": f"https://example.com/{i}.png", "subject": f"c{i}"} for i in range(n)]
    h = render._emblem(items)
    import html
    return [a["src"] for a in json.loads(html.unescape(re.search(r'data-alts="([^"]*)"', h).group(1)))]


class EmbTop(unittest.TestCase):
    def test_cap(self):
        self.assertEqual(len(_alts(8)), 8)
        self.assertEqual(len(_alts(40)), 12)
        a = _alts(100)
        self.assertEqual(len(a), 20)
        self.assertEqual(a[0], "https://example.com/0.png")

    def test_first_pick_top3(self):
        self.assertIn("Math.min(alts.length, 3)", render.EMB_JS)


if __name__ == "__main__":
    unittest.main()


class EmbFade(unittest.TestCase):
    def test_pic_fade(self):
        self.assertIn("'.pic img'", render.EMB_JS)
        self.assertIn(".emb-fade .pic img:not(.bg):not(.ico):not(.ld){opacity:0", open(render.__file__, encoding="utf-8").read())

    def test_fade_in_after_decode(self):
        self.assertIn("emb-fade", render.EMB_HEAD_JS)
        self.assertIn("img.decode()", render.EMB_JS)
        self.assertIn(".emb-fade .emb img:not(.ld){opacity:0", render.CSS if hasattr(render, "CSS") else open(render.__file__, encoding="utf-8").read())
