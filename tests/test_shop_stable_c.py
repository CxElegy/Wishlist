"""店長のページの数え方の 1920 幅（tests/test_shop_stable.py と同じ。並列で流すため別のファイル）。"""
import unittest

from tests.test_shop_stable import ShopStable


class ShopStableC(ShopStable):
    WIDTHS = (1920,)


del ShopStable

if __name__ == "__main__":
    unittest.main()
