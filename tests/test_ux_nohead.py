"""ux_check：版面の頭の写真が開けないとき、写真の側の問題か点検の手元の回線の問題かを分ける（2026-10-27 guest の周杰伦・哈利波特剧集）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import ux_check  # noqa: E402


class SplitNohead(unittest.TestCase):
    def test_split(self):
        bad = {"A": ["u1"], "B": ["u2", "u3"], "C": ["u4"]}
        ok = {"u1": True, "u2": True, "u3": False, "u4": False}
        real, env = ux_check.split_nohead(["A", "B", "C", "D"], bad, ok.get)
        self.assertEqual(env, ["A"])            # 取れる写真だけ＝手元の回線
        self.assertEqual(real, ["B", "C", "D"])  # 1 枚でも取れない・写真の記録がない（最初から字だけ）は ✗

    def test_fetchable_false_on_error(self):
        self.assertFalse(ux_check.fetchable("http://127.0.0.1:1/x.jpg"))


if __name__ == "__main__":
    unittest.main()
