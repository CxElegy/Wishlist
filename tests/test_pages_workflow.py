"""公開 pages.yml：古い公開を止めて最新だけ出す・docs/ を push する回が終わったら公開する（2026-11-01）。"""
import datetime as dt
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
NOW = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)


def pushes_docs(text):
    """git add の行が docs を足す（git add docs / docs/…）か。"""
    return any(re.search(r"git add\b[^\n]*\bdocs\b", ln) for ln in text.splitlines())


def listed_names():
    """pages.yml の workflow_run.workflows に並ぶ名前。"""
    t = (WF / "pages.yml").read_text()
    m = re.search(r"workflows: \[([^\]]*)\]", t)
    return re.findall(r'"([^"]+)"', m.group(1))


def docs_pushers():
    """{ワークフローの名前: ファイル名}（git push して docs を git add する）。"""
    out = {}
    for f in WF.glob("*.yml"):
        t = f.read_text()
        if f.name != "pages.yml" and "git push" in t and pushes_docs(t):
            out[re.search(r"^name: (.+)$", t, re.M).group(1).strip()] = f.name
    return out


class PagesWorkflow(unittest.TestCase):
    def test_concurrency_cancels_old(self):
        t = (WF / "pages.yml").read_text()
        self.assertRegex(t, r"group: pages\s+cancel-in-progress: true")
        self.assertIn("actions/deploy-pages", t)

    def test_docs_pushers_are_listed(self):
        """docs/ を push する回は workflow_run にある（bot の push は push 触発を起こさない）。cleanup-branches の例外はなし（docs を足さない）。"""
        names = listed_names()
        for name, f in docs_pushers().items():
            self.assertIn(name, names, f"{f}（{name}）が pages.yml の workflow_run にない")

    def test_listed_names_really_push_docs(self):
        """逆向き：並べた名前は実在し、docs/ を足す回だけ（空振りの公開を起こさない）。"""
        pushers = docs_pushers()
        for name in listed_names():
            self.assertIn(name, pushers, f"「{name}」は docs/ を push しない（または名前が違う）：workflow_run から外す")

    def test_pushers_found(self):
        """数え漏れ防止：docs を push する回が 3 つ以上見つかる（見つからなければ上の点検が空振りしている）。"""
        self.assertGreaterEqual(len(docs_pushers()), 3)


class PagesHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("pages_health", ROOT / "harness" / "pages_health.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def run_(self, name, conc, hours_ago=1):
        at = (NOW - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"name": name, "created_at": at, "conclusion": conc}

    def test_legacy_runs_mean_not_switched(self):
        s = self.m.summarize([self.run_(self.m.LEGACY, "failure"), self.run_(self.m.OURS, "success")], NOW)
        ok, line = self.m.verdict(s)
        self.assertFalse(ok)
        self.assertIn("未切り替え", line)

    def test_switched_and_clean(self):
        s = self.m.summarize([self.run_(self.m.OURS, "success"), self.run_(self.m.OURS, "cancelled"), self.run_(self.m.LEGACY, "failure", 30)], NOW)
        ok, line = self.m.verdict(s)
        self.assertTrue(ok, line)
        self.assertEqual(s[self.m.OURS]["cancelled"], 1)

    def test_our_failure_is_red(self):
        ok, _ = self.m.verdict(self.m.summarize([self.run_(self.m.OURS, "failure")], NOW))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
