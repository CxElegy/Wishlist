"""ハーネス v3（HARNESS_V2.md）：失敗の台帳 lessons.py・約束の点検 q.py contract --lint・見た目の関所 visual_gate.py・git の隔離 gitsafe.py。"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import gitsafe  # noqa: E402
import lessons  # noqa: E402
import q  # noqa: E402
import visual_gate  # noqa: E402


class Lessons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = pathlib.Path(self.tmp.name) / "lessons.jsonl"

    def test_add_list_and_due_threshold(self):
        for i in range(2):
            lessons.add("ci-fake402", f"T-000{i}", "名簿に 1 行足し忘れ", "手元で全部の試験を流さなかった", p=self.p)
        self.assertEqual(lessons.due(lessons.load(self.p)), [])          # 2 回ではまだ
        lessons.add("ci-fake402", "T-0009", "また名簿", "同じ", p=self.p)
        lessons.add("visual-band", "T-0010", "帯", "", p=self.p)
        rows = lessons.load(self.p)
        self.assertEqual(len(rows), 4)
        got = lessons.due(rows)
        self.assertEqual([g["title"].split("：")[1].split("（")[0] for g in got], ["ci-fake402"])
        g = got[0]
        self.assertIn("3 回", g["title"])
        self.assertTrue(g["done_when"])
        self.assertEqual(q.lint_contract(g["scope"], g["done_when"]), [])   # 出した段が自分の点検を通る

    def test_due_json_goes_into_q_add(self):
        state = pathlib.Path(self.tmp.name) / "state"
        root = pathlib.Path(self.tmp.name) / "repo"
        (root / "harness" / "tasks").mkdir(parents=True)
        for i in range(3):
            lessons.add("k", f"T-{i}", "x", "y", p=self.p)
        g = lessons.due(lessons.load(self.p))[0]
        tid, new = q.add(g["title"], g["why"], g["quote"], g["kind"], g["scope"], g["done_when"], g["priority"], g["source"], root=root, state=state, complexity=g["complexity"])
        self.assertTrue(new)

    def test_requires_type_and_what(self):
        with self.assertRaises(ValueError):
            lessons.add("", "T-1", "x", p=self.p)
        with self.assertRaises(ValueError):
            lessons.add("k", "T-1", " ", p=self.p)

    def test_cli_uses_hf_state(self):
        env = {**gitsafe.clean_env(), "HF_STATE": self.tmp.name}
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "lessons.py"), "add", "--type", "k", "--what", "w"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((pathlib.Path(self.tmp.name) / "lessons.jsonl").exists())
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "lessons.py"), "due"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout), [])

    def test_state_not_in_repo(self):
        self.assertNotIn(str(ROOT), str(lessons.path()).replace("\\", "/") if not os.environ.get("HF_STATE") else "")


class Lint(unittest.TestCase):
    def test_good_contract_passes(self):
        self.assertEqual(q.lint_contract(["a.py", "b.py"], ["試験が通る", "1400px の絵で帯が 0"]), [])

    def test_late_conditions_rejected(self):
        for w in ("合併後に本番の数が 10 以下", "マージ後 1 時間で反映される", "本番で開ける", "デプロイ後に確かめる", "after merge the page updates", "works in production", "Post-merge CI is green"):
            bad = q.lint_contract(["a.py"], ["試験が通る", w])
            self.assertTrue(bad, w)
            self.assertIn("2 番", bad[0])

    def test_plain_words_not_flagged(self):
        self.assertEqual(q.lint_contract(["a.py"], ["本番の写真を落とさない試験が通る", "merge 関数が 2 つの辞書を合わせる"]), [])

    def test_too_large(self):
        self.assertTrue(any("scope" in b for b in q.lint_contract([f"f{i}.py" for i in range(q.LINT_MAX_SCOPE + 1)], ["x"])))
        self.assertEqual(q.lint_contract([f"f{i}.py" for i in range(q.LINT_MAX_SCOPE)], ["x"]), [])
        self.assertTrue(any("done_when" in b for b in q.lint_contract(["a"], [f"c{i}" for i in range(q.LINT_MAX_DONE_WHEN + 1)])))
        self.assertTrue(q.lint_contract(["a"], []))

    def test_cli_exit_codes_and_no_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / "repo"
            state = pathlib.Path(d) / "state"
            (root / "harness" / "tasks").mkdir(parents=True)
            tid, _ = q.add("A", scope=["a.py"], done_when=["x"], root=root, state=state)
            env = {**gitsafe.clean_env(), "HF_STATE": str(state), "HF_ROOT": str(root)}
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / "harness" / "q.py"), "contract", tid, "--lint", *a], env=env, capture_output=True, text=True, encoding="utf-8")
            r = run("--done-when", "合併後に本番で確かめる")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("✗", r.stdout)
            r = run("--done-when", "試験が通る")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertFalse(q.load(root, state)[tid].get("frozen"))   # 点検だけで凍らせない


class VisualGate(unittest.TestCase):
    MAP = {"A1": ["gap", "cgap"], "E4": ["edge"], "A3": [], "C4": ["strong"]}

    def test_collect_formats(self):
        self.assertEqual(visual_gate.collect({"p@1400": {"counts": {"edge": 1}}, "p@390": {"counts": {"edge": 2, "ell": 0}}}), {"edge": 3, "ell": 0})
        self.assertEqual(visual_gate.collect([{"width": 1400, "counts": {"gap": 1}}, {"width": 390, "counts": {"gap": 1}}]), {"gap": 2})
        self.assertEqual(visual_gate.collect({"checks": {"over": 0, "wide": False, "icon": True}}), {"over": 0, "wide": 1, "icon": 0})
        with self.assertRaises(ValueError):
            visual_gate.collect({"x": 1})

    def test_judge_fails_on_mapped_item(self):
        rows, failed = visual_gate.judge({"gap": 0, "cgap": 2, "edge": 0}, self.MAP)
        self.assertTrue(failed)
        d = {r[0]: r[1] for r in rows}
        self.assertEqual((d["A1"], d["E4"], d["A3"], d["C4"]), ("ng", "ok", "eye", "unmeasured"))

    def test_missing_checks_tolerated_unless_strict(self):
        _, failed = visual_gate.judge({"gap": 0}, self.MAP)               # aesthetic_count の検査が無い結果でも落とさない
        self.assertFalse(failed)
        _, failed = visual_gate.judge({"gap": 0}, self.MAP, strict=True)
        self.assertTrue(failed)

    def test_real_map_matches_aesthetic_md(self):
        m = visual_gate.load_map()
        md = (ROOT / "docs" / "rules" / "aesthetic.md").read_text(encoding="utf-8")
        ids = set(re.findall(r"^\| ([A-I]\d+[a-z]?) \|", md, re.M))
        self.assertTrue(set(m) <= ids, set(m) - ids)                      # 地図の番号は基準に実在する
        known = {"gap", "crop", "band", "clip", "icon", "over", "wide", "face", "edge", "hid", "solo", "herogap", "emrel", "cgap", "ell", "strong"}
        self.assertTrue({c for cs in m.values() for c in cs} <= known)
        rev = visual_gate.checks_to_items(m)
        self.assertIn("A1", rev["gap"])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "r.json"
            f.write_text(json.dumps({"checks": {"gap": 0, "over": 1}}), encoding="utf-8")
            self.assertEqual(visual_gate.main([str(f)]), 1)               # E1 over
            f.write_text(json.dumps({"checks": {"gap": 0, "over": 0}}), encoding="utf-8")
            self.assertEqual(visual_gate.main([str(f)]), 0)
            self.assertEqual(visual_gate.main([str(pathlib.Path(d) / "none.json")]), 2)


class GitSafe(unittest.TestCase):
    def test_clean_env_strips_git_vars(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/x", "GIT_WORK_TREE": "/y", "KEEP": "1"}):
            e = gitsafe.clean_env()
        self.assertNotIn("GIT_DIR", e)
        self.assertNotIn("GIT_WORK_TREE", e)
        self.assertEqual(e["KEEP"], "1")

    def test_guard_rejects_real_repo(self):
        with self.assertRaises(AssertionError):
            gitsafe.guard(ROOT)
        with self.assertRaises(AssertionError):
            gitsafe.guard(ROOT / "harness")

    def test_run_in_temp_repo_ignores_inherited_git_dir(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"GIT_DIR": str(ROOT / ".git"), "GIT_WORK_TREE": str(ROOT)}):
                gitsafe.run(d, "init", "-q", "-b", "main")
                gitsafe.run(d, "commit", "-q", "--allow-empty", "-m", "x")
                top = gitsafe.run(d, "rev-parse", "--show-toplevel").stdout.strip()
            self.assertEqual(pathlib.Path(top).resolve(), pathlib.Path(d).resolve())
            self.assertEqual(gitsafe.run(d, "log", "--format=%s").stdout.strip(), "x")

    def test_tests_that_write_with_git_are_isolated(self):
        """git を流す試験は gitsafe か GIT_* の除去を使う（本物のリポジトリを読むだけの 2 つは除く）。"""
        read_only = {"test_posix_relpath.py", "test_sbconf.py"}
        bad = []
        for f in sorted((ROOT / "tests").glob("test_*.py")):
            t = f.read_text(encoding="utf-8")
            if f.name in read_only or f.name == pathlib.Path(__file__).name:
                continue
            if re.search(r'subprocess\.\w+\(\s*\[?\s*"git"|sh\(\s*d?\s*,?\s*"git"|"git", "(init|clone|commit|push|add)"', t) and not re.search(r"gitsafe|GIT_|clean_env", t):
                bad.append(f.name)
        self.assertEqual(bad, [], "git を GIT_* の除去なしで流している試験")


if __name__ == "__main__":
    unittest.main()
