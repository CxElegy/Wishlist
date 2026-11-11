"""版面を足したらその場で後ろの仕組みを回す（2026-11-11 店長：新規ユーザーの KPI と改善）。db/board_added.sql・board_added.yml・harness/board_kpi.py。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "harness"))


class BoardAdded(unittest.TestCase):
    def test_sql_stamps_added_at_and_kicks_only_for_new_names(self):
        s = (ROOT / "db" / "board_added.sql").read_text(encoding="utf-8")
        self.assertIn("create or replace function public.my_keywords_set(p_picks jsonb)", s)
        self.assertIn("when o.v is null then x.v || jsonb_build_object('added_at', now())", s)   # 新しい名前は今
        self.assertIn("when o.v ? 'added_at' then x.v || jsonb_build_object('added_at', o.v -> 'added_at')", s)   # 前からの名前は前の時刻
        self.assertIn("if fresh > 0 then perform private.kick_board_added(", s)
        self.assertIn(">= 6 then return", s)   # 1 人 1 時間 6 回
        self.assertIn("interval '30 seconds'", s)   # 全体 30 秒に 1 回
        self.assertIn("board_added.yml/dispatches", s)
        self.assertIn("security definer set search_path = ''", s)

    def test_workflow_runs_library_then_feed_then_page_then_emblem(self):
        w = (ROOT / ".github" / "workflows" / "board_added.yml").read_text(encoding="utf-8")
        order = [w.index(x) for x in ("library.py --users", "userfeed.py", "user_pages.py", "gh workflow run library_emblem.yml")]
        self.assertEqual(order, sorted(order))
        self.assertIn("group: library", w)   # library.yml と同時に follows を書かない

    def test_kpi_tool_paths_and_targets(self):
        import board_kpi
        self.assertEqual(board_kpi.acct("test-c@example.com"), "u_96014d316e98b2b8")
        self.assertEqual([k for k, _, _ in board_kpi.STAGES], ["picked", "follow", "board", "raw", "pending", "emblem", "edited", "page"])
        self.assertLessEqual(board_kpi.TARGET["page"], 150)
        self.assertNotIn("harness", str(board_kpi.RUNS))   # 本人のデータが入る計測の回はリポジトリの外

    def test_architecture_has_the_flow(self):
        import processes
        p = next(x for x in processes.PROCESSES if x["id"] == "boardadded")
        self.assertEqual(p["workflow"], "board_added.yml")
        self.assertIn("db/board_added.sql", p["files"])


if __name__ == "__main__":
    unittest.main()
