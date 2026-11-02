import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import choice_sample as c  # noqa: E402


class ChoiceSample(unittest.TestCase):
    def test_rules_keep_all_stories(self):
        for n, (_m, st) in c.SNAP.items():
            self.assertEqual(sorted(c.rule_a(n, st)), sorted(st))
            self.assertEqual(sorted(c.rule_b(st)), sorted(st))

    def test_iphone_head(self):
        st = c.SNAP["iPhone"][1]
        self.assertIn("Apple", c.rule_a("iPhone", st)[0][0])
        self.assertFalse(c.is_deal(c.rule_b(st)[0][0]))

    def test_no_storage_url(self):
        self.assertNotIn("supabase.co/storage", c.product_page() + c.wishes_page())


if __name__ == "__main__":
    unittest.main()
