"""店長のページとお客さまのページの違いの点検（harness/diff_admin.py）と、その根の直し。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import diff_admin  # noqa: E402


class Diff(unittest.TestCase):
    def test_only_missing_parts_count(self):
        admin = {"a": 3, "b": 1, "c": 0, "__admin_link": 1}
        self.assertEqual(diff_admin.diff(admin, {"a": 1, "b": 0, "c": 0}), ["b"])   # 店長に見えてお客さまにない部品だけ

    def test_admin_only_is_not_counted(self):
        k = next(iter(diff_admin.ADMIN_ONLY))
        self.assertEqual(diff_admin.diff({k: 1}, {k: 0}), [])

    def test_admin_only_has_reason(self):
        self.assertTrue(all(v for v in diff_admin.ADMIN_ONLY.values()))   # 「管理なので無し」は理由を名前で書く


class Roots(unittest.TestCase):
    SRC = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")

    def test_heat_number_not_hidden_for_customers(self):
        line = self.SRC.split('html[data-mine="2"] .mastwish', 1)[1].split("\n", 1)[0]
        self.assertNotIn(".hm", line)   # 今日の最高（話題度）は店長と同じに出す

    def test_nav_one_per_section_level(self):
        self.assertIn("①b", self.SRC)   # 板块が多くても各板块の駅が 1 つは見える


if __name__ == "__main__":
    unittest.main()
