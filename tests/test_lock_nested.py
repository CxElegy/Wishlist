"""harness/lock.py：別の鍵を持ったまま取ろうとしたら即エラー（64）／ci の鍵を ci_local.sh 以外で取ったら警告。"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import lock  # noqa: E402


class LockNested(unittest.TestCase):
    def run_lock(self, held, *args):
        with tempfile.TemporaryDirectory() as st:
            env = {k: v for k, v in os.environ.items() if not k.startswith("HF_LOCK_")}
            env["HF_STATE"] = st
            env["PYTHONIOENCODING"] = "utf-8"
            for h in held:
                env[f"HF_LOCK_{h.upper()}"] = "1"
            return subprocess.run([sys.executable, str(ROOT / "harness" / "lock.py"), *args], env=env,
                                  capture_output=True, text=True, encoding="utf-8")

    def test_held_other(self):
        self.assertEqual(lock.held_other("browser", {"HF_LOCK_CI": "1", "HF_LOCK_BROWSER": "1", "X": "1"}), ["ci"])
        self.assertEqual(lock.held_other("ci", {"HF_LOCK_CI": "1"}), [])
        self.assertEqual(lock.held_other("ci", {"HF_LOCK_BROWSER": ""}), [])

    def test_nested_other_lock_errors_at_once(self):
        r = self.run_lock(["ci"], "browser", "--wait", "5", "--", sys.executable, "-c", "print('ran')")
        self.assertEqual(r.returncode, lock.MISUSE, r.stdout + r.stderr)
        self.assertNotIn("ran", r.stdout)
        self.assertIn("持ったまま", r.stdout)

    def test_same_lock_inside_is_not_retaken(self):
        r = self.run_lock(["ci"], "ci", "--", sys.executable, "-c", "print('ran')")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ran", r.stdout)

    def test_ci_lock_for_other_use_warns(self):
        r = self.run_lock([], "ci", "--wait", "5", "--", sys.executable, "-c", "print('ran')")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("警告", r.stderr)

    def test_ci_lock_for_ci_local_no_warning(self):
        r = self.run_lock([], "ci", "--wait", "5", "--", sys.executable, "-c", "print('ci_local')")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("警告", r.stderr)

    def test_browser_alone_ok(self):
        r = self.run_lock([], "browser", "--wait", "5", "--", sys.executable, "-c", "print('ran')")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
