import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import free_tier_gate as g  # noqa: E402


class GateTest(unittest.TestCase):
    def test_repo_has_no_access_token(self):
        self.assertEqual(g.token_hits(), [])

    def test_token_hit_found_and_comment_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / ".github/workflows").mkdir(parents=True)
            (r / "scripts").mkdir()
            (r / ".github/workflows/a.yml").write_text("# SUPABASE_ACCESS_TOKEN は置かない\nenv:\n  X: ${{ secrets.SUPABASE_ACCESS_TOKEN }}\n", encoding="utf-8")
            (r / "scripts/b.py").write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(g.token_hits(r), [".github/workflows/a.yml:3"])

    def test_scan_covers_harness_docs_state_claude(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            for sub in g.SCAN_DIRS:
                (r / sub).mkdir(parents=True)
            (r / "harness/x.py").write_text("k = 'sbp_" + "0" * 24 + "'\n", encoding="utf-8")
            (r / "docs/a.js").write_text("// SUPABASE_ACCESS_TOKEN\nvar t = SUPABASE_ACCESS_TOKEN\n", encoding="utf-8")
            (r / "state/s.json").write_text('{"SUPABASE_ACCESS_TOKEN": 1}\n', encoding="utf-8")
            (r / ".claude/s.json").write_text('{"a": "SUPABASE_ACCESS_TOKEN"}\n', encoding="utf-8")
            (r / "docs/note.md").write_text("SUPABASE_ACCESS_TOKEN は置かない\n", encoding="utf-8")
            self.assertEqual(sorted(g.token_hits(r)), [".claude/s.json:1", "docs/a.js:1", "docs/a.js:2", "harness/x.py:1", "state/s.json:1"])   # .md は見ない・JS の // は # ではないので数える

    def test_scan_skips_nested_worktrees(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            for sub in g.SCAN_DIRS:
                (r / sub).mkdir(parents=True)
            w = r / ".claude/worktrees/agent-x/hermes"
            w.mkdir(parents=True)
            (w / "c.yaml").write_text("k: SUPABASE_ACCESS_TOKEN\n", encoding="utf-8")
            self.assertEqual(g.token_hits(r), [])

    def test_storage_url_in_static_html_counted(self):
        u = "https://abc.supabase.co/storage/v1/object/public/media/x.jpg"
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / "docs/home").mkdir(parents=True)
            (r / "docs/home/a.html").write_text('<img src="/p/a.webp" data-fb="%s">' % u, encoding="utf-8")
            (r / "docs/home/b.html").write_text('<img src="/p/b.webp">', encoding="utf-8")
            self.assertEqual(g.storage_url_hits(r), ["docs/home/a.html:1"])

    def test_fill_max_stays_zero(self):
        self.assertEqual(g.fill_max_problems(), [])
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            for sub in (".github/workflows", "scripts", "harness"):
                (r / sub).mkdir(parents=True)
            (r / "harness/browser.py").write_text('FILL_MAX = int(os.environ.get("WL_PHOTO_FILL_MAX", "5"))\n', encoding="utf-8")
            (r / ".github/workflows/w.yml").write_text("env:\n  WL_PHOTO_FILL_MAX: 9\n", encoding="utf-8")
            self.assertEqual(len(g.fill_max_problems(r)), 2)

    def test_report_exit_codes(self):
        ok = [("a", True, "x")]
        self.assertEqual(g.report(ok, False)[0], 0)
        self.assertIn("全部 ✓（入れ終わり）", g.report(ok, False)[1][-1])
        code, lines = g.report(ok, True)   # 静的だけ：✓ でも 0 にしない・「入れ終わり」と言わない
        self.assertEqual(code, 2)
        self.assertIn("入れ終わりではない", lines[-1])
        self.assertNotIn("全部 ✓", lines[-1])
        code, lines = g.report(ok + [("b", False, "y"), ("c", False, "z")], True)
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], "✗ 2 件：b / c")

    def test_steps_skip_prod_has_only_static(self):
        names = [n for n, _, _ in g.steps(skip_prod=True)]
        self.assertEqual(len(names), 4)
        self.assertFalse(any("pages_served" in n or "sb_down" in n or "pages_health" in n for n in names))
        self.assertEqual(g.main.__name__, "main")

    def test_soft_exit_is_unknown_not_fail(self):
        # --size の 測れず（終了コード 2）は ✗ ではない（2026-11-03 別の目の指摘：ラベルと動きが食い違っていた）
        n, ok, _ = g.sh("x", [sys.executable, "-c", "raise SystemExit(2)"], 30, soft=(2,))
        self.assertIsNone(ok)
        self.assertFalse(g.sh("x", [sys.executable, "-c", "raise SystemExit(2)"], 30)[1])
        self.assertFalse(g.sh("x", [sys.executable, "-c", "raise SystemExit(1)"], 30, soft=(2,))[1])
        code, lines = g.report([("a", True, "x"), ("s", None, "測れず")], False)
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].startswith("✓") and lines[1].startswith("-"))
        self.assertIn("測れず 1 件", lines[-1])
        self.assertEqual(g.report([("s", None, "測れず"), ("b", False, "y")], False)[0], 1)

    def test_size_step_is_soft_on_2(self):
        t = (Path(g.__file__)).read_text(encoding="utf-8")
        self.assertIn('"--size"], 120, soft=(2,)', t)

    def test_timeout_is_fail(self):
        n, ok, line = g.sh("x", [sys.executable, "-c", "import time;time.sleep(5)"], 1)
        self.assertFalse(ok)
        self.assertIn("時間切れ", line)


if __name__ == "__main__":
    unittest.main()
