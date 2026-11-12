"""harness/affected.py：変わったファイルから当たる試験を機械で決める（分からない時は全部）。

git を動かすのは一時の repo だけ（GIT_* の環境変数を全部外す。2026-11-12：hook から受け継いだ GIT_DIR で本物の repo が書き換わった）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import affected  # noqa: E402


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class RealTree(unittest.TestCase):
    """いまの倉庫のソースで。"""

    @classmethod
    def setUpClass(cls):
        cls.g = affected.Graph(ROOT)

    def run_on(self, *files):
        return affected.affected(list(files), ROOT, graph=self.g)

    def names(self, r):
        return set(r["fast"]) | set(r["browser"])

    def test_render_picks_every_importer(self):   # ① render を（間接でも）import する試験は全部・test_wall_shapes を含む
        r = self.run_on("scripts/render.py")
        self.assertFalse(r["all"])
        importers = {affected._n(t) for t, cl in self.g.closure.items() if "scripts/render.py" in cl}
        self.assertIn("test_wall_shapes", importers)
        self.assertLessEqual(importers, self.names(r))
        self.assertIn("test_wall_shapes", r["browser"])

    def test_one_test_file_only_itself(self):   # ② 試験のファイルだけ → その試験（とそれを読む試験）。test_gate_ripe は入り、無関係な試験は入らない
        r = self.run_on("tests/test_gate_ripe.py")
        self.assertFalse(r["all"])
        self.assertIn("test_gate_ripe", r["fast"])
        self.assertNotIn("test_match", self.names(r))
        self.assertLess(len(self.names(r)), 5)

    def test_workflow_picks_readers(self):   # ③ workflow の yml → workflow を読む試験・test_fake402 を含む
        r = self.run_on(".github/workflows/fake402.yml")
        self.assertFalse(r["all"])
        self.assertIn("test_fake402", r["fast"])

    def test_docs_md_nothing(self):   # ④ 誰も読まない md → 空（docs/rules/ は harness/emb_check.py が *.md を読むので、読む試験だけ）
        r = self.run_on("no" + "tes/zz_nobody_reads.md")
        self.assertEqual((r["all"], r["fast"], r["browser"]), (False, [], []))
        r = self.run_on("docs/rules/aesthetic.md")
        self.assertFalse(r["all"])
        self.assertNotIn("test_match", self.names(r))

    def test_unknown_script_is_all(self):   # ⑤ 表にも決まりにも当たらない新しい scripts → 全部（安全側）
        r = self.run_on("scripts/zz_brand_new.py")
        self.assertTrue(r["all"])
        self.assertIn("scripts/zz_brand_new.py", r["unknown"])
        self.assertEqual(len(self.names(r)), len(self.g.tests))

    def test_runner_changes_are_all(self):   # 試験の流し方・入れ物が変わったら全部
        for f in ("harness/lock.py", ".githooks/pre-push", "requirements.txt", "harness/ci.Dockerfile", ".github/workflows/ci.yml"):
            self.assertTrue(self.run_on(f)["all"], f)

    def test_unmatched_data_file_is_all(self):
        self.assertTrue(self.run_on("st" + "ate/zz_" + "nobody.json")["all"])   # 名前を分けて書く（この試験自身が「読む」に数えられないよう）

    def test_deleted_test_is_dropped(self):
        r = self.run_on("tests/test_zz_gone.py")
        self.assertEqual((r["all"], r["fast"], r["browser"]), (False, [], []))

    def test_same_name_rule_of_prepush(self):   # pre-push ② と同じ：scripts/x.py → tests/test_x*.py は必ず入る
        r = self.run_on("scripts/gate.py")
        self.assertIn("test_gate_ripe", self.names(r))

    def test_browser_split(self):   # browser＝playwright か harness/browser.py を直に import する試験
        r = self.run_on("scripts/render.py")
        self.assertEqual(set(r["fast"]) & set(r["browser"]), set())
        for n in r["browser"]:
            self.assertTrue(self.g.is_browser(f"tests/{n}.py"), n)
        self.assertNotIn("test_match", r["browser"])

    def test_every_listed_test_exists(self):
        r = self.run_on("scripts/render.py", "tests/test_zz_gone.py")
        for n in self.names(r):
            self.assertTrue((ROOT / "tests" / f"{n}.py").exists(), n)


class Synthetic(unittest.TestCase):
    """小さな作りものの倉庫で（読めない .py・git の道）。"""

    def make(self, d, files):
        for rel, body in files.items():
            p = Path(d) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")

    def test_broken_python_is_all(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, {"scripts/a.py": "x = 1\n", "scripts/bad.py": "def (:\n", "tests/test_a.py": "import a\n"})
            r = affected.affected(["scripts/a.py"], Path(d))
            self.assertTrue(r["all"])

    def test_small_graph(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, {"scripts/a.py": "import b\n", "scripts/b.py": "X = open('conf.yaml')\n",
                          "tests/test_a.py": "import a\n", "tests/test_c.py": "x = 1\n",
                          "tests/test_w.py": "from pathlib import Path\nfor f in (Path('.') / '.github' / 'workflows').glob('*.yml'): pass\n",
                          "tests/test_p.py": "from playwright.sync_api import sync_playwright\nimport b\n"})
            g = affected.Graph(Path(d))
            r = affected.affected(["scripts/b.py"], Path(d), graph=g)
            self.assertEqual((r["fast"], r["browser"]), (["test_a"], ["test_p"]))
            r = affected.affected(["conf.yaml"], Path(d), graph=g)   # b.py が読む → b を import する試験
            self.assertEqual(r["fast"] + r["browser"], ["test_a", "test_p"])
            r = affected.affected([".github/workflows/x.yml"], Path(d), graph=g)
            self.assertEqual(r["fast"], ["test_w"])

    def test_cli_git_range_in_temp_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, {"scripts/a.py": "x = 1\n", "tests/test_a.py": "import a\n", "tests/test_b.py": "y = 2\n"})
            env = clean_env()
            git = lambda *a: subprocess.run(["git", *a], cwd=d, env=env, check=True, capture_output=True)
            git("init", "-q", "-b", "main")
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "base")
            self.make(d, {"scripts/a.py": "x = 2\n"})
            git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam", "change")
            out = subprocess.run([sys.executable, str(ROOT / "harness/affected.py"), "--root", d, "main~1..HEAD", "--json"],
                                 cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(out.returncode, 0, out.stderr)
            r = json.loads(out.stdout)
            self.assertEqual((r["all"], r["fast"]), (False, ["test_a"]))
            out = subprocess.run([sys.executable, str(ROOT / "harness/affected.py"), "--root", d, "--base", "nope", "--names"],
                                 cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual((out.returncode, out.stdout.strip()), (0, "ALL"))   # base が無い → 全部


if __name__ == "__main__":
    unittest.main()
