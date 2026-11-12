"""test_wall_shapes の 43 通りの後ろ半分（shard(1)）と、壊したら落ちることの確かめ。
別のファイルにして run_tests.py が test_wall_shapes と並べて流す（2026-11-12：1 本で 506〜710 秒かかり、負荷で Page.goto が時間切れ）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import test_wall_shapes as ws  # noqa: E402

# 壁を並べる FIT_JS を空にしたとき、空きが出て赤になる通り（2026-11-13 Linux のコンテナで測った：空のとき直す前の作りも今の作りも
# 壁の中 6%・右の列との差 47%＝閾値 8% を大きく超える。並べたときは 0%・0%）
BROKEN_RUN = ("TVWS", 1400, 0, False)


class WallShapesB(unittest.TestCase):
    def test_wall_has_no_hole_for_any_photo_shape_b(self):
        ws.check_shard(self, 1)

    def test_empty_fit_js_goes_red(self):
        """壁の並べ方（FIT_JS）を空の関数にしたページでは赤になる：この試験が空きを見ていることの確かめ"""
        got, _ = ws.measure([BROKEN_RUN], fit_js="(() => {})();")
        self.assertIsNotNone(ws.judge(BROKEN_RUN, got[ws.tag(BROKEN_RUN)]), f"FIT_JS が空でも緑：{got}")


if __name__ == "__main__":
    unittest.main()
