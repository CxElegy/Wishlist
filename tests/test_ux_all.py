import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "harness"))
import ux_all


class UxAll(unittest.TestCase):
    def test_units_cover_every_who_width_and_global(self):
        u = ux_all.units(["guest", "test-a"], [1400, 390])
        self.assertEqual([n for n, _ in u], ["guest-1400", "guest-390", "test-a-1400", "test-a-390", "global"])
        self.assertTrue(all("--part" in a for _, a in u))

    def test_each_unit_fits_limit(self):
        self.assertLessEqual(ux_all.LIMIT, 500)

    def test_budget_below_tool_limit_and_spent_budget_skips_start(self):
        self.assertLess(ux_all.BUDGET, 600)
        import time
        name, done, bad = ux_all.run("x", ["--part", "global"], [], time.time() - 1)   # 持ち時間なし：始めず「走らなかった」
        self.assertFalse(done)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
