"""harness/js_check.py が壊れた埋め込み JS を見つけ、JSON・src の script は見ないか（2026-11-05 #919 で本番の JS が止まった件）。

    python -m unittest tests.test_js_check
"""
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import js_check  # noqa: E402

HTML = """<html><head>
<script type="application/ld+json">{"a": 1,}</script>
<script src="x.js"></script>
<script>var ok = 1;</script>
<script type="module">export const m = 1;</script>
<script>var broken = ;</script>
</head></html>"""


class JsCheck(unittest.TestCase):
    def test_blocks_skip_json_and_src(self):
        bodies = [b for _, b, _ in js_check.blocks(HTML)]
        self.assertEqual(len(bodies), 3)
        self.assertFalse(any('"a": 1' in b for b in bodies))

    @unittest.skipUnless(shutil.which("node"), "node が無い")
    def test_finds_broken_script_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "p.html"
            p.write_text(HTML, encoding="utf-8")
            bad = js_check.check_file(p, shutil.which("node"))
        self.assertEqual([i for _, i, _ in bad], [4])

    @unittest.skipUnless(shutil.which("node"), "node が無い")
    def test_render_js_strings_parse(self):
        self.assertEqual(js_check.check_render(shutil.which("node")), [])


if __name__ == "__main__":
    unittest.main()
