"""scripts/pull_rebase.py：消した側（「違う」）を勝たせて rebase を続ける。"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pull_rebase.py"


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


class PullRebase(unittest.TestCase):
    def test_deleted_image_wins(self):
        with tempfile.TemporaryDirectory() as d:
            origin, a, b = (os.path.join(d, x) for x in ("origin", "a", "b"))
            sh(d, "git", "init", "-q", "--bare", "-b", "main", origin)
            sh(d, "git", "clone", "-q", origin, a)
            for r in (a,):
                sh(r, "git", "config", "user.email", "t@t")
                sh(r, "git", "config", "user.name", "t")
            os.makedirs(os.path.join(a, "docs/home/emblems"))
            Path(a, "docs/home/emblems/x.webp").write_text("1")
            Path(a, "items.yaml").write_text('  - {image: "emblems/x.webp"}\n  - {image: "emblems/y.webp"}\n')
            sh(a, "git", "add", "-A")
            sh(a, "git", "commit", "-qm", "init")
            sh(a, "git", "push", "-q", "origin", "main")
            sh(d, "git", "clone", "-q", origin, b)
            sh(b, "git", "config", "user.email", "t@t")
            sh(b, "git", "config", "user.name", "t")
            # a（後台作業）：同じ画像を書き直す
            Path(a, "docs/home/emblems/x.webp").write_text("2")
            sh(a, "git", "commit", "-qam", "bg")
            # b（違う）：画像と行を消して先に push
            sh(b, "git", "rm", "-q", "docs/home/emblems/x.webp")
            Path(b, "items.yaml").write_text('  - {image: "emblems/y.webp"}\n')
            sh(b, "git", "commit", "-qam", "reject")
            sh(b, "git", "push", "-q", "origin", "main")
            r = subprocess.run(["python", str(SCRIPT)], cwd=a, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(Path(a, "docs/home/emblems/x.webp").exists())
            self.assertNotIn("x.webp", Path(a, "items.yaml").read_text())


if __name__ == "__main__":
    unittest.main()
