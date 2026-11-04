"""偽の 402 を相手に Actions の入口を通しで走らせ、docs/・state/ が縮まない・入口が落ちないことを見る（harness/fake402_check.py）。
2026-11-04：11/5 以降は全部の回が 402 に当たる。部品単体ではなく入口ごとに、名簿（ALLOW）に無い縮みが 0。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import fake402_check  # noqa: E402


class Fake402(unittest.TestCase):
    def test_entries_do_not_shrink_under_402(self):
        bad = fake402_check.run()
        self.assertEqual(bad, [], "\n".join(bad))

    def test_allowlist_has_reasons(self):
        for f, why in fake402_check.ALLOW.items():
            self.assertTrue(why.strip(), f)


if __name__ == "__main__":
    unittest.main()
