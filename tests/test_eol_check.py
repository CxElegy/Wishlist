"""改行の向きの反転を止める検査（harness/eol_check.py）。一時の git 倉庫で試す。"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))

import eol_check  # noqa: E402


class EolCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.tmp.name)
        self.old = os.getcwd()
        os.chdir(self.d)
        # hook から流されても本物の repo を触らない（2026-11-12 の事故）
        self.saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GIT_")}
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("config", "core.autocrlf", "false")
        (self.d / "crlf.txt").write_bytes(b"a\r\nb\r\nc\r\n")
        (self.d / "lf.txt").write_bytes(b"a\nb\nc\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.git("branch", "base")
        self.git("checkout", "-q", "-b", "work")

    def tearDown(self):
        os.chdir(self.old)
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def git(self, *a):
        subprocess.run(["git", *a], check=True, capture_output=True)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-q", "-m", "work")

    def test_flip_crlf_to_lf_detected(self):
        (self.d / "crlf.txt").write_bytes(b"a\nb\nc\nd\n")
        self.commit()
        self.assertEqual(eol_check.flipped("base"), [("crlf.txt", "CRLF", "LF")])
        self.assertEqual(eol_check.main(["base"]), 1)

    def test_flip_lf_to_crlf_detected(self):
        (self.d / "lf.txt").write_bytes(b"a\r\nb\r\nc\r\n")
        self.commit()
        self.assertEqual(eol_check.flipped("base"), [("lf.txt", "LF", "CRLF")])

    def test_same_ending_passes(self):
        (self.d / "crlf.txt").write_bytes(b"a\r\nb\r\nc\r\nd\r\n")
        (self.d / "lf.txt").write_bytes(b"a\nb\nc\nd\n")
        self.commit()
        self.assertEqual(eol_check.flipped("base"), [])
        self.assertEqual(eol_check.main(["base"]), 0)

    def test_one_stray_line_is_not_a_flip(self):
        (self.d / "crlf.txt").write_bytes(b"a\r\nb\r\nc\r\nd\n")
        self.commit()
        self.assertEqual(eol_check.flipped("base"), [])

    def test_new_and_deleted_files_pass(self):
        (self.d / "new.txt").write_bytes(b"x\ny\n")
        (self.d / "new2.txt").write_bytes(b"x\r\ny\r\n")
        (self.d / "lf.txt").unlink()
        self.commit()
        self.assertEqual(eol_check.flipped("base"), [])

    def test_worktree_flip_before_commit(self):
        (self.d / "crlf.txt").write_bytes(b"a\nb\nc\n")
        self.assertEqual(eol_check.flipped("base"), [])
        self.assertEqual(eol_check.flipped("base", worktree=True), [("crlf.txt", "CRLF", "LF")])

    def test_missing_base_is_quiet(self):
        self.assertEqual(eol_check.flipped("no-such-ref"), [])


if __name__ == "__main__":
    unittest.main()
