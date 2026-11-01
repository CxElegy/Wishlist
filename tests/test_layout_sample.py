import unittest
from scripts.layout_sample import assign


def mk(n, p=0):
    return [dict(href=f"u{p}{i}", title=f"title {p}{i}", img="x") for i in range(n)]


class T(unittest.TestCase):
    def test_no_duplicate_across_boards(self):
        used = {"h": set(), "t": set()}
        a = assign(mk(30), used)
        b = assign(mk(30), used)   # 同じ記事の 2 回目は全部落ちる
        self.assertEqual(sum(map(len, b)), 0)
        self.assertEqual(sum(map(len, a)), 30)

    def test_grid_fills_last_row(self):
        for n in (5, 14, 20, 30, 50):
            hero, rail, grid, more = assign(mk(n), {"h": set(), "t": set()})
            self.assertTrue(len(grid) % 6 == 0 or len(grid) == 0 or n - 4 < 6)
