"""push する workflow の checkout には `ref: ${{ github.ref }}` が要る（2026-10-26：requests.yml が触発時の提交を取り、
待っている間に前の回が足した emblem_redo を pull --rebase -X theirs で上書きした）。足し忘れを CI で拦める。

    python -m unittest tests.test_workflow_ref
"""
import pathlib
import re
import unittest

WF = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"

# ref を足さない workflow（理由つき）
EXEMPT = {
    "cleanup-branches.yml": "リモートの分支を消すだけ。checkout した中身は使わない",
    "ci.yml": "pull_request で動く（PR の合併候補を試すので github.ref は PR の ref。main の先頭ではない）",
    "progress.yml": "pull_request / workflow_run で動き、ref を自分で選んでいる（merge_commit_sha など）",
    "ask_remind.yml": "ref: main を明示している",
    "live_clear.yml": "push しない（page_build で動く。ref の指定は不要）",
}


def checkouts(text):
    """checkout の各段の `with:` の中身（次の `- ` の段まで）。"""
    parts = re.split(r"(?m)^(?=\s*- (?:name|uses|run|id|if):)", text)
    return [p for p in parts if "actions/checkout" in p]


class WorkflowRef(unittest.TestCase):
    def test_pushing_workflows_check_out_latest_main(self):
        bad = []
        for f in sorted(WF.glob("*.yml")):
            if f.name in EXEMPT:
                continue
            for c in checkouts(f.read_text(encoding="utf-8")):
                if not re.search(r"^\s*ref:\s*(\$\{\{\s*github\.ref\s*\}\}|main)(?!\w)", c, re.M):
                    bad.append(f.name)
        self.assertEqual(bad, [], "checkout に `ref: ${{ github.ref }}` がない（push する workflow は いまの main の先頭を取る）。push しないなら EXEMPT に理由つきで足す")

    def test_exempt_files_exist(self):
        for name in EXEMPT:
            self.assertTrue((WF / name).exists(), name)

    def test_the_fixed_ones(self):
        for name in ("requests.yml", "background.yml", "render.yml", "library_emblem.yml", "digest.yml", "library.yml"):
            self.assertIn("ref: ${{ github.ref }}", (WF / name).read_text(encoding="utf-8"), name)
