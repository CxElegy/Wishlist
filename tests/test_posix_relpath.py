"""path の区切りが OS で変わる壊れ方の点検：.relative_to(...) は .as_posix() を付けて / 区切りにする（Windows では \ になり、比較や表示がずれる）。"""
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BAD = re.compile(r"\.relative_to\([^)]*\)(?!\.as_posix\(\))")


class PosixRelpath(unittest.TestCase):
    def test_relative_to_uses_as_posix(self):
        files = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout.splitlines()
        hits = []
        for rel in filter(None, files):
            if rel == "tests/test_posix_relpath.py":
                continue
            p = ROOT / rel
            if not p.exists():
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if BAD.search(line):
                    hits.append(f"{rel}:{n}")
        self.assertEqual(hits, [], "relative_to の path は .as_posix() で / 区切りにする（Windows の \\ 区切り）")


if __name__ == "__main__":
    unittest.main()
