"""L8：札（たった今・更新・重大・作品名）は字に重ねない＝position:absolute で浮かせず、流れの中か枠の内側に置く。"""
import re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render

SRC = Path(render.__file__).read_text(encoding="utf-8")
CHECK = (Path(render.__file__).resolve().parent.parent / "harness" / "ux_check.py").read_text(encoding="utf-8")


def rules(sel):
    return [l for l in SRC.splitlines() if l.lstrip().startswith(sel)]


class BadgeFlow(unittest.TestCase):
    def test_fresh_tag_in_flow(self):
        rule = next(l for l in SRC.splitlines() if l.startswith(".fresh-tag{"))
        self.assertNotIn("absolute", rule)
        self.assertIn("function tag(", SRC)

    def test_wc_tag_in_flow(self):
        for l in rules(".wc .tg{"):
            self.assertNotIn("absolute", l)
            self.assertNotRegex(l, r"top:-\d")

    def test_burst_inside_frame(self):
        # 枠の外へ負の位置で出さない（外の字に重なる）
        for l in rules(".burst{") + [l for l in SRC.splitlines() if " .burst{" in l]:
            self.assertNotRegex(l, r"(top|left):-\d")

    def test_no_floating_tag_with_negative_offset(self):
        # 札の規則（.tg / .burst / .fresh-tag / .tgx）に、負の top/left で浮かせる作りが 0 件
        bad = [l[:60] for l in SRC.splitlines()
               if re.match(r"\s*\.(burst|fresh-tag|tgx|wc \.tg)\{", l) and re.search(r"position:absolute[^}]*(top|left):-\d", l)]
        self.assertEqual(bad, [])

    def test_ux_check_counts_all_absolute_badges(self):
        self.assertIn(".burst,.wc .tg", CHECK)
        self.assertIn("position==='absolute'", CHECK)


if __name__ == "__main__":
    unittest.main()
