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
        # 2026-11-19：全体 30 秒に 1 回の歯止めは、30 秒の中で 2 人目が足した版面を起こさず cron（8 時間）待ちにした。
        # 毎回起こして重なりは job の concurrency がまとめる。全体は 1 時間 120 回の暴走止めだけ
        self.assertNotIn("interval '30 seconds'", s)
        self.assertIn("interval '1 hour') >= 120 then return", s)
        self.assertIn("create table if not exists private.board_kicks", s)   # 何度流してもよい
        self.assertIn("create or replace function private.kick_board_added", s)
        self.assertIn("board_added.yml/dispatches", s)
        self.assertIn("security definer set search_path = ''", s)

    def jobs(self):
        import yaml
        w = yaml.safe_load((ROOT / ".github" / "workflows" / "board_added.yml").read_text(encoding="utf-8"))
        return w["jobs"]

    @staticmethod
    def runs(job):
        return [s.get("run", "") for s in job["steps"]]

    def at(self, job, text):
        return next(i for i, r in enumerate(self.runs(job)) if text in r)

    def test_board_job_is_alone_in_the_library_queue(self):
        j = self.jobs()["board"]
        self.assertEqual(j["concurrency"]["group"], "library")   # library.yml と同時に follows を書かない
        self.assertTrue(any("library.py --users" in r for r in self.runs(j)))
        self.assertFalse(any("userfeed.py" in r or "user_pages.py" in r for r in self.runs(j)))   # 10 分の記事集めで次の人の版面作りを待たせない

    def test_feed_then_page_after_board(self):
        j = self.jobs()["feed"]
        self.assertEqual(j["needs"], "board")
        self.assertNotIn(j["concurrency"]["group"], ("library", "library-emblem"))
        self.assertLess(self.at(j, "userfeed.py"), self.at(j, "user_pages.py --recent"))   # 記事が先・ページが後

    def test_emblem_job_runs_in_parallel_and_waits_for_the_row(self):
        import library_emblem
        j = self.jobs()["emblem"]
        self.assertNotIn("needs", j)   # board の job を待たない：準備を先に
        self.assertNotIn(j["concurrency"]["group"], ("library", "library-emblem"))   # cron の小元素の回（30 分）に並ばない
        # 2026-11-19 run 1：--check-fresh が board の job より先に 1 回見て「0」で終わった → 1 回見て決める step を置かない
        self.assertFalse(any("--check-fresh" in r for r in self.runs(j)))
        fill = j["steps"][self.at(j, "library_emblem.py --fresh")]["run"]
        # 重い道具は同じ step の中で後ろで（&）入れ、その間に行を待つ。印のファイルを --tools で渡す
        self.assertLess(fill.index("rembg"), fill.index("library_emblem.py --fresh"))
        self.assertLess(fill.index("scrapling install"), fill.index("library_emblem.py --fresh"))
        self.assertIn(") &", fill)
        self.assertIn("done=1", fill)
        self.assertLess(fill.index("rembg_done=1"), fill.index("scrapling install"))   # 速い道は rembg だけ待つ
        for arg in ("--wait", "--shard ${{ matrix.shard }}", "--tools", "--pages-dir"):
            self.assertIn(arg, fill)
        self.assertNotIn("if", j["steps"][self.at(j, "library_emblem.py --fresh")])   # 経路 A/B も同じ step（board の job の終わりを見て終える）
        self.assertFalse(any("user_pages.py" in r for r in self.runs(j)))   # ページは版面ごとに --fresh の中から（全版面の後に 1 回ではない）
        self.assertIn("more", j["steps"][self.at(j, "gh workflow run library_emblem.yml")]["if"])
        self.assertLess(self.at(j, "library_emblem.py --fresh"), self.at(j, "gh workflow run library_emblem.yml"))
        more = j["steps"][self.at(j, "gh workflow run library_emblem.yml")]["run"]
        self.assertLess(more.index("gh run list --workflow library_emblem.yml"), more.index("gh workflow run"))   # 3 本が 3 回起こさない

    def test_emblem_job_is_sharded_like_the_code(self):
        import library_emblem
        j = self.jobs()["emblem"]
        self.assertEqual(j["strategy"]["matrix"]["shard"], list(range(library_emblem.FRESH_SHARDS)))
        self.assertIs(j["strategy"]["fail-fast"], False)   # 1 つが落ちてもほかの版面を止めない
        self.assertIn("${{ matrix.shard }}", j["concurrency"]["group"])   # 列は shard ごと（同じ版面は claim で 1 回）
        self.assertEqual(j["env"]["GH_TOKEN"], "${{ github.token }}")   # board の job の様子を読む

    def test_logs_are_not_buffered(self):
        import yaml
        w = yaml.safe_load((ROOT / ".github" / "workflows" / "board_added.yml").read_text(encoding="utf-8"))
        self.assertEqual(str(w["env"]["PYTHONUNBUFFERED"]), "1")   # 各段の時刻がためずに出る
        self.assertIn("actions", w["permissions"])

    def test_library_yml_kicks_board_added_when_it_made_boards(self):
        w = (ROOT / ".github" / "workflows" / "library.yml").read_text(encoding="utf-8")
        self.assertIn("gh workflow run board_added.yml", w)   # 起こし損ね・1 人 6 回超えの控え
        self.assertIn("steps.users.outputs.new_boards", w)
        self.assertIn("actions: write", w)

    def test_kpi_tool_paths_and_targets(self):
        import board_kpi
        self.assertEqual(board_kpi.acct("test-c@example.com"), "u_96014d316e98b2b8")
        self.assertEqual([k for k, _, _ in board_kpi.STAGES], ["picked", "follow", "board", "raw", "pending", "emblem", "edited", "page", "page_emblem", "photo"])
        self.assertEqual(board_kpi.TARGET["emblem"], 5)   # 店長の決まり：小元素は 5 分未満（比べ方は「未満」）
        self.assertLessEqual(board_kpi.TARGET["page"], 20)
        self.assertEqual(set(board_kpi.TARGETS), {"A", "B", "C"})
        self.assertNotIn("harness", str(board_kpi.RUNS))   # 本人のデータが入る計測の回はリポジトリの外

    def test_architecture_has_the_flow(self):
        import processes
        p = next(x for x in processes.PROCESSES if x["id"] == "boardadded")
        self.assertEqual(p["workflow"], "board_added.yml")
        self.assertIn("db/board_added.sql", p["files"])


if __name__ == "__main__":
    unittest.main()
