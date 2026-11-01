"""L10：カードの中の別の記事（.nx＝同じ版面の次のニュース）は自分のリンクで押せる（pointer-events:none の例外に入っている）。"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render


class NxLink(unittest.TestCase):
    def test_nx_anchor_clickable(self):
        css = render.CSS
        none = next(l for l in css.splitlines() if l.startswith(":is(.card,.top,.wc) :not("))
        auto = next(l for l in css.splitlines() if l.startswith(":is(.card,.top,.wc) :is(.vt"))
        for s in (".nx a", ".nx a *"):
            self.assertIn(s, none)
            self.assertIn(s, auto)


if __name__ == "__main__":
    unittest.main()
