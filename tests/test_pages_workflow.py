"""公開 pages.yml：古い公開を止めて最新だけ出す・bot の push の回が終わったら公開する（2026-11-01）。"""
import re
import unittest
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


class PagesWorkflow(unittest.TestCase):
    def test_concurrency_cancels_old(self):
        t = (WF / "pages.yml").read_text()
        self.assertRegex(t, r"group: pages\s+cancel-in-progress: true")
        self.assertIn("actions/deploy-pages", t)

    def test_every_docs_pusher_triggers_deploy(self):
        """docs/ を git push する workflow は、pages.yml の workflow_run に名前がある（bot の push は push 触発を起こさない）。"""
        pages = (WF / "pages.yml").read_text()
        for f in WF.glob("*.yml"):
            t = f.read_text()
            if f.name == "pages.yml" or "git push" not in t or "git add" not in t or "docs" not in t:
                continue
            name = re.search(r"^name: (.+)$", t, re.M).group(1).strip()
            if f.name == "cleanup-branches.yml":
                continue
            self.assertIn(name, pages, f"{f.name}（{name}）が pages.yml の workflow_run にない")


if __name__ == "__main__":
    unittest.main()
