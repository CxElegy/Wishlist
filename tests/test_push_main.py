"""scripts/push_main.py：先を越されても取り込んで通す・push 済みの提交を書き換えない・依頼は push のあとで done。"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "push_main.py"
sys.path.insert(0, str(ROOT / "scripts"))


def sh(cwd, *a):
    return subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True).stdout


def clone(d, origin, name):
    p = os.path.join(d, name)
    sh(d, "git", "clone", "-q", origin, p)
    sh(p, "git", "config", "user.email", "t@t")
    sh(p, "git", "config", "user.name", "t")
    return p


def run(cwd, *a):
    env = {**os.environ, "GH_TOKEN": ""}
    return subprocess.run([sys.executable, str(SCRIPT), *a], cwd=cwd, capture_output=True, text=True, env=env)


class PushMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = self.tmp.name
        self.origin = os.path.join(d, "origin")
        sh(d, "git", "init", "-q", "--bare", "-b", "main", self.origin)
        a = clone(d, self.origin, "seed")
        Path(a, "items.yaml").write_text("items: []\n")
        os.makedirs(os.path.join(a, "docs"))
        Path(a, "docs/i.html").write_text("0")
        sh(a, "git", "add", "-A")
        sh(a, "git", "commit", "-qm", "init")
        sh(a, "git", "push", "-q", "origin", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def test_race_rebases_and_folds_regen(self):
        a, b = clone(self.d, self.origin, "a"), clone(self.d, self.origin, "b")
        Path(a, "x.txt").write_text("a")
        sh(a, "git", "add", "-A")
        sh(a, "git", "commit", "-qm", "data")
        Path(b, "y.txt").write_text("b")
        sh(b, "git", "add", "-A")
        sh(b, "git", "commit", "-qm", "other")
        sh(b, "git", "push", "-q", "origin", "main")   # b が先に push（a は先を越された）
        r = run(a, "--regen", "echo regen > docs/i.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        log = sh(a, "git", "log", "--format=%s", "origin/main").split("\n")
        self.assertEqual(log[:3], ["data", "other", "init"])   # 作り直しは「data」に畳まれ、提交は増えない
        self.assertEqual(sh(a, "git", "show", "origin/main:docs/i.html").strip(), "regen")

    def test_no_own_commit_does_not_rewrite_pushed(self):
        a = clone(self.d, self.origin, "a")
        r = run(a, "--regen", "echo regen > docs/i.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        log = sh(a, "git", "log", "--format=%s", "origin/main").split("\n")
        self.assertEqual(log[1], "init")   # init は書き換えず、新しい提交を足す

    def test_broken_items_yaml_not_pushed(self):
        a = clone(self.d, self.origin, "a")
        Path(a, "items.yaml").write_text("items: [\n")
        sh(a, "git", "commit", "-qam", "broken")
        self.assertEqual(run(a).returncode, 1)
        self.assertEqual(run(a, "--soft").returncode, 0)
        self.assertEqual(sh(a, "git", "show", "origin/main:items.yaml"), "items: []\n")

    def test_non_race_failure_stops_at_once(self):
        import push_main
        bad = subprocess.CompletedProcess([], 128, "", "remote: Permission denied (403)")
        with mock.patch.object(push_main.pull_rebase, "main", return_value=0), \
                mock.patch.object(push_main, "git", return_value=bad) as g, \
                mock.patch.object(push_main, "yaml_ok", return_value=True):
            sleeps = []
            self.assertFalse(push_main.push(tries=6, sleep=sleeps.append))
        self.assertEqual(sleeps, [])   # 403 は待たない
        self.assertEqual(sum(1 for c in g.call_args_list if c.args[:1] == ("push",)), 1)


class WorkflowsUsePushMain(unittest.TestCase):
    """点検：main へ push する workflow は push_main.py を通す（自前の輪・`|| true` の黙った成功を残さない）。"""
    ALLOW = {"cleanup-branches.yml", "photo_store.yml"}   # 枝を消す / 状態だけを reset して置く（本 1 ② で見直す）

    def test_no_raw_push_loops(self):
        bad = []
        for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
            if f.name in self.ALLOW:
                continue
            for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                code = ln.split("#")[0]
                if re.search(r"\bgit (push|pull)\b", code) or "pull_rebase.py" in code:
                    bad.append(f"{f.name}:{n}")
        self.assertEqual(bad, [])

    def test_docs_use_push_main(self):
        for f in ("EDITING.md", "TEMPLATES.md", "PHOTOS.md"):
            self.assertNotIn("&& git push origin main", (ROOT / f).read_text(encoding="utf-8"), f)


class ItemMarksAfterPush(unittest.TestCase):
    def test_marks_wait_for_push(self):
        import json
        import digest
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "marks.json")
            calls = []
            with mock.patch.dict(os.environ, {"WL_ITEM_MARKS": str(p)}), \
                    mock.patch.object(digest, "supabase", side_effect=lambda *a, **k: calls.append(a) or []):
                p.write_text(json.dumps({"done": [7], "skipped": {"8": "x"}}))
                self.assertEqual(calls, [])
                digest.mark_items_later()
                self.assertFalse(p.exists())
            self.assertTrue(any("id=in.(7)" in c[0] for c in calls))
            self.assertTrue(any("id=eq.8" in c[0] for c in calls))


if __name__ == "__main__":
    unittest.main()
