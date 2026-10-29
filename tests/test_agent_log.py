import importlib.util
import pathlib
import unittest

P = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "agent_log.py"
spec = importlib.util.spec_from_file_location("agent_log", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AgentLog(unittest.TestCase):
    def test_no_secrets_or_inputs(self):
        d = {"hook_event_name": "PostToolUse", "session_id": "abc", "cwd": "/x/c.elegy@outlook.com",
             "tool_name": "Bash", "tool_input": {"command": "curl -H sb_secret_abcdefghijklmnop https://x"},
             "tool_response": {"is_error": True}, "duration_ms": 12}
        r = m.record(d)
        s = str(r)
        for bad in ("outlook", "sb_secret", "abcdefghijklmnop", "https"):
            self.assertNotIn(bad, s)
        self.assertEqual((r["tool"], r["ok"], r["dur_ms"]), ("Bash", False, 12))
        self.assertEqual(len(r["session"]), 8)

    def test_file_tool_keeps_name_only(self):
        r = m.record({"tool_name": "Edit", "tool_input": {"file_path": "/a/b/c.py", "new_string": "SECRET body"}})
        self.assertTrue(r["summary"].startswith("c.py"))
        self.assertNotIn("SECRET", r["summary"])


if __name__ == "__main__":
    unittest.main()
