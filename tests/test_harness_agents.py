"""係の型（.claude/agents/hw-*.md）と harness/install_agents.py。"""
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
AG = ROOT / ".claude" / "agents"
TOOLS = {"hw-read": "Read, Glob, Grep, Bash", "hw-edit": "Read, Edit, Write, Glob, Grep, Bash", "hw-ops": "Bash, Read",
         "hw-diag": "Read, Glob, Grep, Bash, WebSearch, WebFetch"}


def front(p):
    m = re.match(r"---\n(.*?)\n---\n", p.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    return dict(l.split(": ", 1) for l in m.group(1).split("\n"))


class Types(unittest.TestCase):
    def test_four_types_with_exact_tools(self):
        for n, tools in TOOLS.items():
            f = front(AG / f"{n}.md")
            self.assertEqual(f["name"], n)
            self.assertTrue(f["description"])
            self.assertEqual(f["tools"], tools)
            self.assertNotIn("model", f)     # モデルは台本が役ごとに決める
            for bad in ("Skill", "ToolSearch", "Agent", "mcp__"):
                self.assertNotIn(bad, f["tools"])

    def run_install(self, *a):
        return subprocess.run([sys.executable, str(ROOT / "harness" / "install_agents.py"), *a], capture_output=True, text=True, encoding="utf-8")

    def test_install_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_install("--check", "--dest", d).returncode, 1)     # まだ無い
            self.assertEqual(self.run_install("--dest", d).returncode, 0)
            self.assertEqual(sorted(p.name for p in pathlib.Path(d).iterdir()), [f"{n}.md" for n in sorted(TOOLS)])
            self.assertEqual(self.run_install("--check", "--dest", d).returncode, 0)
            (pathlib.Path(d) / "hw-ops.md").write_text("x", encoding="utf-8")
            self.assertEqual(self.run_install("--check", "--dest", d).returncode, 1)


if __name__ == "__main__":
    unittest.main()
