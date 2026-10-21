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


if __name__ == "__main__":
    unittest.main()
