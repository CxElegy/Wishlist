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
            cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
            self.assertIn(b"--wishlist", cmd)
            self.assertIn(b"while :", cmd)                                   # 落ちても起き直す輪の中で動く
        finally:
            hook.CANDIDATES = old
            try:
                os.killpg(pid, 9)            # 見守りの輪（bash）と中の集め係をまとめて
            except (OSError, UnboundLocalError):
                pass

    def test_agent_log_keeps_board(self):
        """道具を使うたびの記録の hook（agent_log.py）からも、止まっていたら起こし直す"""
        s = (ROOT / ".claude" / "hooks" / "agent_log.py").read_text(encoding="utf-8")
        self.assertIn("keep_board()", s)

    def test_user_hook_in_cloud_only(self):
        """クラウドの容器では user の設定にも hook を入れる（作業場所が /home/user でも、worker の再起動のあと起き直す）。
        PC・手元の機械（CLAUDE_CODE_REMOTE_SESSION_ID なし）は触らない。2 回でも 1 つ。ほかの設定は残す。読めない設定は書き換えない"""
        d = pathlib.Path(tempfile.mkdtemp())
        f = d / ".claude" / "settings.json"
        old = os.environ.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        try:
            self.assertEqual(hook.ensure_user_hook(f), "skip")
            self.assertFalse(f.exists())
            os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_test"
            f.parent.mkdir(parents=True)
            f.write_text('{"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}', encoding="utf-8")
            self.assertEqual(hook.ensure_user_hook(f), "added")
            self.assertEqual(hook.ensure_user_hook(f), "present")
            s = f.read_text(encoding="utf-8")
            self.assertEqual(s.count("agentboard_start.py"), 2)              # SessionStart と UserPromptSubmit に 1 つずつ
            self.assertIn('"model": "x"', s)
            self.assertIn("echo hi", s)
            f.write_text("{broken", encoding="utf-8")
            self.assertEqual(hook.ensure_user_hook(f), "unreadable")
            self.assertEqual(f.read_text(encoding="utf-8"), "{broken")
        finally:
            os.environ.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
            if old is not None:
                os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = old

    def test_wishlist_dir_from_home(self):
        """作業場所が /home/user（harness が無い）でも、site の欄のために hook のある Wishlist を渡す"""
        old_env, old_cwd = os.environ.get("CLAUDE_PROJECT_DIR"), os.getcwd()
        try:
            os.environ["CLAUDE_PROJECT_DIR"] = tempfile.mkdtemp()
            self.assertEqual(pathlib.Path(hook.wishlist_dir()).resolve(), ROOT.resolve())
        finally:
            if old_env is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old_env
            os.chdir(old_cwd)

    def test_registered_in_settings(self):
        s = (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        self.assertEqual(s.count("agentboard_start.py"), 2)                 # SessionStart と UserPromptSubmit


if __name__ == "__main__":
    unittest.main()
