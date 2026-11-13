"""docs/404.html（入口へ戻す）と、テストグラウンドの各ページから入口へ戻るリンク。"""
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import welcome  # noqa: E402

TG = ROOT / "docs" / "testground"


class NotFoundPage(unittest.TestCase):
    def test_built_page_links_to_entrance_with_absolute_urls(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "404.html"
            welcome.build_404(out)
            t = out.read_text(encoding="utf-8")
        self.assertIn(f'href="{welcome.ENTRANCE}"', t)
        self.assertNotRegex(t, r'(?:href|src)="(?!https?:|#)')   # どの深さの網址でも読めるよう相対パスなし

    def test_committed_404_matches_generator(self):
        t = (ROOT / "docs" / "404.html").read_text(encoding="utf-8")
        self.assertIn(f'href="{welcome.ENTRANCE}"', t)


class TestgroundBackLinks(unittest.TestCase):
    def test_every_page_links_back_to_index_and_index_to_entrance(self):
        for f in sorted(TG.glob("*.html")):
            if f.name in ("index.html", "welcome.html", "d5-new.html", "d5-now.html") or f.name.startswith("fill-"):
                continue
            t = f.read_text(encoding="utf-8")
            self.assertTrue(re.search(r'<a[^>]*href="(?:\./|index\.html)"', t), f"{f.name} に戻るリンクがない")
        self.assertIn('href="../"', (TG / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
