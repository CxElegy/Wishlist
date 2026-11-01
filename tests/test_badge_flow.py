"""L8：札（たった今・更新）は字に重ねない＝position:absolute で浮かせず、日付の行の流れに並べる。"""
import re, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render


class BadgeFlow(unittest.TestCase):
    def test_fresh_tag_in_flow(self):
        src = Path(render.__file__).read_text(encoding="utf-8")
        rule = next(l for l in src.splitlines() if l.startswith(".fresh-tag{"))
        self.assertNotIn("absolute", rule)
        self.assertIn("function tag(", src)


if __name__ == "__main__":
    unittest.main()
