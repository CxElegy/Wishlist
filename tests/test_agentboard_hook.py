"""AgentBoard の集め係を起こす hook（.claude/hooks/agentboard_start.py）：agentboard が無ければ何もしない・
あれば 1 つだけ起こす（2 回呼んでも 2 つにならない）・会話は止めない（HARNESS_V2.md「AgentBoard」）。"""
import importlib.util
import os
import pathlib
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agentboard_start", ROOT / ".claude" / "hooks" / "agentboard_start.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@unittest.skipIf(os.name == "nt", "Windows はタスク スケジューラが起こす")
class Hook(unittest.TestCase):
    def test_no_board_is_noop(self):
        old = hook.CANDIDATES
        hook.CANDIDATES = [tempfile.mkdtemp()]
        try:
            self.assertIsNone(hook.find_board())
            hook.main()
        finally:
            hook.CANDIDATES = old

    def test_starts_once(self):
        board = pathlib.Path(tempfile.mkdtemp())
        (board / "collect.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        old = hook.CANDIDATES
        hook.CANDIDATES = [str(board)]
        try:
            self.assertEqual(hook.start(hook.find_board(), str(ROOT)), "started")
            pid = int((board / ".collector.pid").read_text())
            time.sleep(0.3)
            self.assertTrue(hook.alive(pid))
            self.assertEqual(hook.start(board, str(ROOT)), "running")      # 2 つ目は起こさない
            self.assertIn(b"--wishlist", pathlib.Path(f"/proc/{pid}/cmdline").read_bytes())
        finally:
            hook.CANDIDATES = old
            try:
                os.kill(pid, 9)
            except (OSError, UnboundLocalError):
                pass

    def test_registered_in_settings(self):
        s = (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertEqual(s.count("agentboard_start.py"), 2)                 # SessionStart と UserPromptSubmit


if __name__ == "__main__":
    unittest.main()
