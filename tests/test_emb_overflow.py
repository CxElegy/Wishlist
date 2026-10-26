"""スマホで横に長い立ち絵が画面の右へはみ出さない（ux_check E5：绝区零・Astrae Oratio）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402


class EmbOverflow(unittest.TestCase):
    def test_mobile_clamps_right_margin(self):
        i = render.CSS.index("@media (max-width:600px){.emb{height:100px")
        self.assertIn(".emb img.body{margin-right:max(", render.CSS[i:i + 1200])


if __name__ == "__main__":
    unittest.main()
