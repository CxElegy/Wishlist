import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import free_tier_gate as g  # noqa: E402


class GateTest(unittest.TestCase):
    def test_repo_has_no_access_token(self):
        self.assertEqual(g.token_hits(), [])

    def test_token_hit_found_and_comment_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / ".github/workflows").mkdir(parents=True)
            (r / "scripts").mkdir()
            (r / ".github/workflows/a.yml").write_text("# SUPABASE_ACCESS_TOKEN は置かない\nenv:\n  X: ${{ secrets.SUPABASE_ACCESS_TOKEN }}\n", encoding="utf-8")
            (r / "scripts/b.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(g.token_hits(r), [".github/workflows/a.yml:3"])

    def test_timeout_is_fail(self):
        n, ok, line = g.sh("x", [sys.executable, "-c", "import time;time.sleep(5)"], 1)
        self.assertFalse(ok)
        self.assertIn("時間切れ", line)


if __name__ == "__main__":
    unittest.main()
