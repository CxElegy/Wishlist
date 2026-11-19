"""店長のページの数え方の後ろの 4 幅（tests/test_shop_stable.py と同じ。並列で流すため別のファイル）。"""
import unittest

from tests.test_shop_stable import ShopStable


class ShopStableB(ShopStable):
    WIDTHS = (1024, 1333, 1440, 1920)


del ShopStable

if __name__ == "__main__":
    unittest.main()
