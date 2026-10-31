"""ページの重さ（2026-10-22 全体の検査 H6）：Web フォントを増やすと全部のページの最初の表示が遅れる。

    python -m unittest tests.test_perf
"""

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import render  # noqa: E402


class Fonts(unittest.TestCase):
    def test_only_japanese_ui_font_and_few_families(self):
        fams = re.findall(r"family=([^:&]+)", render.FONTS)
        self.assertLessEqual(len(fams), 4, fams)
        for heavy in ("Noto+Sans+SC", "Noto+Sans+TC", "Noto+Sans+KR", "Noto+Serif+SC"):   # 1 つで数 MB：記事の字は端末のフォントで
            self.assertNotIn(heavy, fams)
        self.assertIn("display=swap", render.FONTS)

    def test_gstatic_preconnected_wherever_fonts_load(self):
        for f in ("render.py", "welcome.py"):
            src = (pathlib.Path(render.__file__).parent / f).read_text(encoding="utf-8")
            self.assertEqual(src.count('href="https://fonts.googleapis.com">'),
                             src.count('href="https://fonts.gstatic.com" crossorigin>'), f)


class FontsDoNotBlockPaint(unittest.TestCase):
    """Google Fonts の CSS を描画を止める <link rel=stylesheet> で読まない（Fast 3G の最初の表示 4.3→1.2 秒、2026-10-31）。
    render.py・welcome.py のどの頁でも font_link を通す（連動の範囲：本体 7 頁＋入口＋擬音の書体）"""
    def test_no_blocking_font_stylesheet_in_sources(self):
        for f in ("render.py", "welcome.py"):
            src = (pathlib.Path(render.__file__).parent / f).read_text(encoding="utf-8")
            self.assertNotRegex(src, r'<link rel="stylesheet" href="\{[^}]*FONTS[^}]*\}">', f)
            self.assertNotIn('<link rel="stylesheet" href="{e(likefx.SFX_FONT)}">', src, f)

    def test_font_link_is_swapped_in_after_load(self):
        h = render.font_link(render.FONTS)
        self.assertIn('media="print" onload="this.media=\'all\'"', h)
        self.assertIn("<noscript>", h)

    def test_generated_pages_have_no_blocking_font_link(self):
        """生成済みの docs/index.html と docs/home/*.html を数える（ソースが直っても古い出力が本番に残るのを見つける）"""
        docs = pathlib.Path(render.__file__).resolve().parent.parent / "docs"
        pages = [docs / "index.html"] + sorted((docs / "home").glob("*.html"))
        bad = {p.name: render.blocking_font_links(p.read_text(encoding="utf-8")) for p in pages}
        self.assertEqual({k: v for k, v in bad.items() if v}, {})

    def test_blocking_font_links_counts_only_blocking(self):
        u = "https://fonts.googleapis.com/css2?family=A"
        self.assertEqual(render.blocking_font_links(render.font_link(u)), 0)
        self.assertEqual(render.blocking_font_links(f'<link rel="stylesheet" href="{u}">'), 1)


if __name__ == "__main__":
    unittest.main()
