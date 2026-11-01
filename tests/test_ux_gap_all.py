"""ux_check「写真の余白」は画面に入った写真だけでなく全候補を読み込んでから数える（2026-11-01）。"""
import pathlib
import unittest

SRC = (pathlib.Path(__file__).resolve().parents[1] / "harness" / "ux_check.py").read_text(encoding="utf-8")


class GapAll(unittest.TestCase):
    def js(self):
        return SRC[SRC.index('GAP_JS = """'):SRC.index('# 2026-10-27：手元の回線')]

    def test_loads_every_candidate(self):
        j = self.js()
        self.assertIn("loading='eager'", j)       # loading=lazy の写真も読み込む
        self.assertIn("e.hidden=false", j)         # [hidden] の予備（pkpool）・折りたたみも測る
        self.assertIn("hid.forEach(e=>{e.hidden=true})", j)   # 測ったら元に戻す
        self.assertNotIn("p.offsetParent||", j.split("cs.forEach(o=>{const i=o.i")[0])

    def test_unread_is_a_failure_not_silence(self):
        self.assertIn("写真の余白を測れなかった", SRC)
        self.assertIn('gp["unread"] > gp["n"] * 0.25', SRC)

    def test_old_sync_gap_gone(self):
        self.assertNotIn("gap:[...document.querySelectorAll('section.sec article.card", SRC)


if __name__ == "__main__":
    unittest.main()
