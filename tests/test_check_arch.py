"""改了逻辑就要改架构图（scripts/check_arch.py，CI 的一步）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import check_arch  # noqa: E402


class CheckArchTest(unittest.TestCase):
    def test_logic_without_arch_fails(self):
        ok, msg = check_arch.check(["scripts/render.py", "tests/test_dedupe.py"])
        self.assertFalse(ok)
        self.assertIn("scripts/render.py", msg)

    def test_logic_with_arch_passes(self):
        self.assertTrue(check_arch.check(["scripts/digest.py", "scripts/processes.py"])[0])

    def test_workflow_counts_as_logic(self):
        self.assertFalse(check_arch.check([".github/workflows/digest.yml"])[0])

    def test_non_logic_passes(self):
        self.assertTrue(check_arch.check(["items.yaml", "tests/test_x.py", "CLAUDE.md", "docs/index.html", "scripts/runlog.py"])[0])

    def test_skip_with_reason(self):
        ok, msg = check_arch.check(["scripts/render.py"], "修错字\n架构图：不用改（只改注释）")
        self.assertTrue(ok)
        self.assertIn("只改注释", msg)
