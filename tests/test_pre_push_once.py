"""pre-push の重複をなくす（.githooks/pre-push・harness/ci_local.sh の緑の印）：docker あり→② を飛ばす／緑の印あり→④ を飛ばす／
指紋が違う・印が古い→④ を流す／docker なし→② を流す／④ が 3 なら 3 で返す。偽の docker・偽の ci_local.sh・偽の check_arch で hook を bash で流す。"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")


def sh(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")


@unittest.skipUnless(BASH, "bash が無い")
class PrePushOnce(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        self.repo = base / "repo"
        self.bin = base / "bin"
        self.green = base / "green"
        self.marks = base / "marks"
        for d in (self.bin, self.marks):
            d.mkdir()
        origin = base / "origin.git"
        sh(["git", "init", "-q", "--bare", "-b", "main", str(origin)], base)
        self.repo.mkdir()
        for d in ("scripts", "tests", "harness", ".githooks"):
            (self.repo / d).mkdir()
        shutil.copy(ROOT / ".githooks" / "pre-push", self.repo / ".githooks" / "pre-push")
        (self.repo / "scripts" / "check_arch.py").write_text("import sys; sys.exit(0)\n")
        (self.repo / "scripts" / "foo.py").write_text("x = 1\n")
        (self.repo / "tests" / "test_foo.py").write_text(
            "import unittest, os\nclass T(unittest.TestCase):\n    def test_a(self):\n"
            f"        open(r'{self.marks / 'unit'}', 'a').write('x')\n")
        (self.repo / "harness" / "ci_local.sh").write_text(
            f"#!/usr/bin/env bash\necho x >> '{self.marks / 'ci'}'\nexit ${{FAKE_CI_RC:-0}}\n")
        for c in (["init", "-q", "-b", "main"], ["config", "user.email", "a@b"], ["config", "user.name", "t"],
                  ["remote", "add", "origin", str(origin)], ["add", "-A"], ["commit", "-qm", "base"],
                  ["push", "-q", "origin", "main"], ["checkout", "-q", "-b", "work"]):
            r = sh(["git", *c], self.repo)
            self.assertEqual(r.returncode, 0, r.stderr)
        (self.repo / "scripts" / "foo.py").write_text("x = 2\n")
        sh(["git", "commit", "-qam", "change"], self.repo)
        # 偽の python3（いま動いている python）。偽の docker は make_docker で
        (self.bin / "python3").write_text(f'#!/usr/bin/env bash\nexec "{pathlib.Path(sys.executable).as_posix()}" "$@"\n')
        self.make_docker(True)

    def make_docker(self, ok):
        (self.bin / "docker").write_text(f"#!/usr/bin/env bash\nexit {0 if ok else 1}\n")

    def mark(self, name):
        p = self.marks / name
        return len(p.read_text().split()) if p.exists() else 0

    def tree(self):
        return sh(["git", "rev-parse", "HEAD^{tree}"], self.repo).stdout.strip()

    def stamp(self, tree, age=0):
        self.green.mkdir(exist_ok=True)
        (self.green / tree).write_text(f"{int(time.time()) - age}\n")

    def run_hook(self, **extra):
        env = dict(os.environ, PATH=f"{self.bin.as_posix()}{os.pathsep}{os.environ['PATH']}",
                   HF_CI_GREEN_DIR=self.green.as_posix(), **extra)
        r = sh([BASH, ".githooks/pre-push"], self.repo, env)
        return r.returncode, r.stdout + r.stderr

    def test_docker_skips_unit_and_runs_ci(self):
        rc, out = self.run_hook()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.mark("unit"), 0, out)
        self.assertEqual(self.mark("ci"), 1, out)

    def test_green_stamp_skips_ci(self):
        self.stamp(self.tree(), age=60)
        rc, out = self.run_hook()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.mark("ci"), 0, out)
        self.assertIn("さっき緑", out)

    def test_other_tree_runs_ci(self):
        self.stamp("0" * 40)
        rc, out = self.run_hook()
        self.assertEqual((rc, self.mark("ci")), (0, 1), out)

    def test_old_stamp_runs_ci(self):
        self.stamp(self.tree(), age=7300)
        rc, out = self.run_hook()
        self.assertEqual((rc, self.mark("ci")), (0, 1), out)

    def test_no_docker_runs_unit_and_no_ci(self):
        self.make_docker(False)
        rc, out = self.run_hook()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.mark("unit"), 1, out)
        self.assertEqual(self.mark("ci"), 0, out)

    def test_exit_codes_pass_through(self):
        rc, out = self.run_hook(FAKE_CI_RC="3")
        self.assertEqual(rc, 3, out)
        rc, out = self.run_hook(FAKE_CI_RC="1")
        self.assertEqual(rc, 1, out)


class CiLocalStampText(unittest.TestCase):
    def test_stamp_only_when_all_green(self):
        t = (ROOT / "harness" / "ci_local.sh").read_text(encoding="utf-8")
        tail = t[t.index("\nrc=$?"):]
        self.assertIn('"$rc" = 0 ] && [ $# = 0 ]', tail)   # 赤・3・引数付きは印なし
        self.assertIn("HF_CI_GREEN_DIR", tail)
        self.assertIn("exit $rc", tail)


if __name__ == "__main__":
    unittest.main()
