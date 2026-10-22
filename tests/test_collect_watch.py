"""収集が止まらないようにする（2026-10-22 全体の検査 M3・M4）。ネットには出ない。
  ・控えの時計：最後の収集から 150 分たったら、後台作業が digest.yml を起こす（collect_watch）
  ・締め切り：収集を始めて 18 分たったら新しい版面を始めない。残りは次の回に先に取る（digest.ingest）
  ・1 版面の取得の例外で収集全体を止めない
  ・新しい関注項の「すぐ AI 編集」はゲート経由（GATE_NOW：一時停止・GATE_FIRE を守る）
  ・ワークフローの形（締め切りの時間・continue-on-error・ゲートの記録を足す条件・定時の分）"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import time
import unittest
import zoneinfo
from types import SimpleNamespace as NS
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import collect_watch  # noqa: E402
import digest  # noqa: E402
import gate  # noqa: E402
import runlog  # noqa: E402

UTC = dt.timezone.utc


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


class Decide(unittest.TestCase):
    def test_fresh_collect_waits(self):
        due, why = collect_watch.decide(t("2026-10-22T04:54"), [], t("2026-10-22T07:17"))   # 143 分
        self.assertFalse(due)
        self.assertIn("143 分前", why)

    def test_missed_schedule_kicks(self):
        """本番 10-22：04:54 の収集のあと、06:17・08:17 の定時が来なかった。08:17 の後台作業（pg_cron）で起こす。"""
        runs = [{"status": "completed", "createdAt": "2026-10-22T04:47:03Z"}]
        due, why = collect_watch.decide(t("2026-10-22T04:54"), runs, t("2026-10-22T08:17"))
        self.assertTrue(due)
        self.assertIn("203 分", why)

    def test_running_or_queued_does_not_kick(self):
        for st in ("in_progress", "queued", "waiting", "pending"):
            due, _ = collect_watch.decide(t("2026-10-22T04:54"), [{"status": st, "createdAt": "2026-10-22T08:10:00Z"}], t("2026-10-22T08:17"))
            self.assertFalse(due, st)

    def test_recent_run_waits(self):
        """30 分以内に始まった回（失敗してすぐ終わった回も）があれば待つ：失敗が続いても 1 時間に 1 回までしか起こさない。"""
        runs = [{"status": "completed", "createdAt": "2026-10-22T08:00:00Z"}]
        self.assertFalse(collect_watch.decide(t("2026-10-22T04:54"), runs, t("2026-10-22T08:17"))[0])
        self.assertTrue(collect_watch.decide(t("2026-10-22T04:54"), runs, t("2026-10-22T08:47"))[0])

    def test_unreadable_runs_do_not_kick(self):
        self.assertFalse(collect_watch.decide(None, None, t("2026-10-22T08:17"))[0])

    def test_no_record_kicks(self):
        self.assertTrue(collect_watch.decide(None, [], t("2026-10-22T08:17"))[0])

    def test_hourly_watch_caps_the_gap(self):
        """本番の収集の時刻（state/log/collect.json、10-21〜22）で、毎時 17 分に見たら空きはどこまで縮むか。
        前は最大 274 分。控えの時計があれば、起こした回（+12 分で終わる）で 150 + 60 + 12 分以内に収まる。"""
        real = ["2026-10-21T06:44", "2026-10-21T10:50", "2026-10-21T13:54", "2026-10-21T16:00", "2026-10-21T18:44",
                "2026-10-21T21:36", "2026-10-22T00:20", "2026-10-22T04:54"]
        done, last, now = [t(x) for x in real], t(real[0]), t("2026-10-21T07:17")
        worst = dt.timedelta(0)
        while now < t("2026-10-22T09:00"):
            nxt = min((d for d in done if d > last), default=None)
            if nxt and nxt <= now:
                worst, last = max(worst, nxt - last), nxt
                continue
            if collect_watch.decide(last, [], now)[0]:
                done.append(now + dt.timedelta(minutes=12))   # 起こした回が 12 分で終わる
            now += dt.timedelta(hours=1)
        self.assertLessEqual(worst, dt.timedelta(minutes=150 + 60 + 12))


class Main(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.log = pathlib.Path(self.dir.name)
        (self.log / "collect.json").write_text(json.dumps([
            {"at": "2026-10-22T04:54:55+00:00", "text": "新着 3 件", "secs": 419},
            {"at": "2026-10-22T04:55:00+00:00", "text": "情報員 …"}]), encoding="utf-8")
        self.calls = []

    def tearDown(self):
        self.dir.cleanup()

    def run_(self, args, **kw):
        self.calls.append(args)
        return NS(returncode=0, stdout="[]", stderr="")

    def test_last_collect_reads_finished_rows(self):
        self.assertEqual(collect_watch.last_collect(self.log), t("2026-10-22T04:54:55"))

    def test_kicks_and_logs(self):
        due, kicked, why = collect_watch.main([], run=self.run_, log_dir=self.log, now=t("2026-10-22T08:17"))
        self.assertTrue(due and kicked)
        self.assertEqual(self.calls[-1], ["gh", "workflow", "run", "digest.yml"])
        rows = runlog.load("gate", self.log)
        self.assertTrue(rows[-1]["collect_kick"])
        self.assertIn("収集の控えの時計", rows[-1]["text"])

    def test_dry_and_fresh_do_not_call_gh(self):
        collect_watch.main(["--dry"], run=self.run_, log_dir=self.log, now=t("2026-10-22T08:17"))
        self.assertNotIn(["gh", "workflow", "run", "digest.yml"], self.calls)
        self.calls.clear()
        with mock.patch.object(collect_watch, "_now", lambda: t("2026-10-22T06:00")):
            due, kicked, _ = collect_watch.main([], run=self.run_, log_dir=self.log)
        self.assertEqual((due, kicked, self.calls), (False, False, []))   # 新しいうちは gh も呼ばない
        self.assertEqual(runlog.load("gate", self.log), [])


def _ingest_patches(items, collect, saved):
    return dict(live_mark=lambda *a, **k: None, collect=collect, load_config=lambda: ({"timezone": "Asia/Tokyo"}, items),
                seen_from_inbox=set, recent_titles=dict, has_history=lambda n: True, load_json=lambda p: {},
                save_json=lambda p, d: saved.__setitem__("inbox", d) if "inbox" in str(p) else None,
                merge_inbox=lambda a, b: b, status_facts=lambda i, s, f: ([], None), carry_over=lambda d, today: (d, 0),
                find_cover=lambda i, c: None, is_urgent=lambda e, i: False, entry_to_dict=lambda n, e: {"n": n, "url": e.url},
                title_key=lambda x: "k:" + x,
                filter_entries=lambda r, item, conf, seen, now, cmp: [NS(url=u, title=u) for u in r if u not in cmp and u not in seen])


class Ingest(unittest.TestCase):
    def test_one_board_error_does_not_stop_collect(self):
        """1 版面の取得で例外 → その版面は空、ほかは inbox に書く（前は ingest ごと止まり、inbox も書かれなかった）。"""
        items, saved = [{"name": n} for n in "ABC"], {}

        def collect(item, conf):
            if item["name"] == "B":
                raise RuntimeError("壊れた応答")
            return [item["name"] + "1"]
        with mock.patch.multiple(digest, **_ingest_patches(items, collect, saved), deferred_from_log=lambda: []):
            digest.ingest()
        self.assertEqual([b["name"] for b in saved["inbox"]["items"]], ["A", "C"])
        self.assertIn("RuntimeError", digest.LAST_INGEST["failed"]["B"])

    def test_deadline_defers_and_next_run_goes_first(self):
        items, saved, order = [{"name": n} for n in "ABCDE"], {}, []

        def collect(item, conf):
            order.append(item["name"])
            time.sleep(0.15)
            return [item["name"] + "1"]
        with mock.patch.multiple(digest, **_ingest_patches(items, collect, saved), deferred_from_log=lambda: ["D"],
                                 COLLECT_DEADLINE_MIN=0.2 / 60, COLLECT_WORKERS=1):
            digest.ingest()
        self.assertEqual(order, ["D", "A"])                          # 前の回に残った D を先に取る
        self.assertEqual(digest.LAST_INGEST["deferred"], ["B", "C", "E"])
        self.assertEqual([b["name"] for b in saved["inbox"]["items"]], ["A", "D"])   # 去重・inbox は元の順番

    def test_dedupe_keeps_original_order_even_when_fetched_later(self):
        """先に取った版面（前の回の残り）でも、去重は元の順番：前の関注項 A が収めた記事は後ろの B では収めない。"""
        items, saved = [{"name": "A"}, {"name": "B", "dedupe_others": True}], {}
        with mock.patch.multiple(digest, **_ingest_patches(items, lambda item, conf: ["x"], saved), deferred_from_log=lambda: ["B"]):
            digest.ingest()
        self.assertEqual([b["name"] for b in saved["inbox"]["items"]], ["A"])

    def test_deferred_from_log(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            rows = [{"at": "1", "secs": 300}, {"at": "2", "deferred": ["OLD"]},
                    {"at": "3", "secs": 1100}, {"at": "4", "text": "時間切れで 2 版面を次の回へ", "deferred": ["X", "Y"]}, {"at": "5", "text": "情報員"}]
            (d / "collect.json").write_text(json.dumps(rows), encoding="utf-8")
            self.assertEqual(digest.deferred_from_log(d), ["X", "Y"])
            (d / "collect.json").write_text(json.dumps(rows + [{"at": "6", "secs": 400}]), encoding="utf-8")
            self.assertEqual(digest.deferred_from_log(d), [])       # 次の回で取り終えた

    def test_logged_ingest_writes_deferred_and_failed(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)

            def fake_ingest():
                digest.LAST_INGEST.clear()
                digest.LAST_INGEST.update(deferred=["X", "Y"], failed={"Z": "RuntimeError: x"})
            with mock.patch.object(runlog, "LOG_DIR", d), mock.patch.object(digest, "ingest", fake_ingest), \
                    mock.patch.object(digest, "_inbox_counts", dict), mock.patch.object(digest.intel, "health", lambda: ""):
                digest.logged_ingest()
            rows = runlog.load("collect", d)
            self.assertIn("secs", rows[0])
            self.assertEqual(rows[1]["deferred"], ["X", "Y"])
            self.assertIn("時間切れで 2 版面を次の回へ", rows[1]["text"])
            self.assertIn("取得に失敗した 1 版面", rows[2]["text"])
            self.assertEqual(digest.deferred_from_log(d), ["X", "Y"])


class GateNow(unittest.TestCase):
    """digest.yml の「新関注項 → 立刻 AI 編集」：GATE_NOW=edit。間隔・定時は飛ばすが、一時停止・GATE_FIRE・仕事なしは守る。"""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.dir.name) / "gate.json"
        jst = zoneinfo.ZoneInfo("Asia/Tokyo")
        self.now = dt.datetime(2026, 10, 19, 13, 0, tzinfo=jst).astimezone(UTC)
        at = dt.datetime(2026, 10, 19, 12, 50, tzinfo=jst).astimezone(UTC).isoformat()   # 10 分前・9:00 の回のあとに起こし済み
        self.job = {"need": True, "items": ["新しい作品"], "sig": "s1", "prog": 25,
                    "fired": {"at": at, "sig": "s0", "prog": 10, "attempts": 1}}

    def tearDown(self):
        self.dir.cleanup()

    def fire(self, env, job=None):
        gate.save({"jobs": {"edit": dict(job or self.job)}}, self.state)
        calls = []
        with mock.patch.object(gate, "_now", lambda: self.now):
            res = gate.fire(self.state, post=lambda u, tok: calls.append(u) or 200, env={"ROUTINE_TOKEN_EDIT": "t", **env})["edit"]
        return res, calls

    def test_without_now_waits(self):
        res, calls = self.fire({"GATE_FIRE": "edit"})
        self.assertIn("待つ", res)
        self.assertEqual(calls, [])

    def test_now_skips_gap_and_records(self):
        res, calls = self.fire({"GATE_FIRE": "edit", "GATE_NOW": "edit"})
        self.assertEqual(res, "Claude を起こした")
        self.assertEqual(len(calls), 1)
        fired = gate.load(self.state)["jobs"]["edit"]["fired"]
        self.assertEqual(fired["at"], self.now.isoformat(timespec="seconds"))   # 記録が残る（次のゲートの判断に使う）

    def test_now_keeps_pause_switch_and_need(self):
        self.assertIn("一時停止中", self.fire({"GATE_FIRE": "edit", "GATE_NOW": "edit", "EDIT_MODE": "pause"})[0])
        self.assertIn("GATE_FIRE で止めている", self.fire({"GATE_FIRE": "0", "GATE_NOW": "edit"})[0])
        self.assertIn("仕事なし", self.fire({"GATE_FIRE": "edit", "GATE_NOW": "edit"}, {**self.job, "need": False})[0])


class Workflows(unittest.TestCase):
    @staticmethod
    def load(name):
        import yaml
        return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))

    def test_background(self):
        wf = self.load("background.yml")
        crons = [c["cron"] for c in wf[True]["schedule"]]   # YAML の on は True になる
        for c in crons:
            self.assertNotEqual(c.split()[0], "0", c)       # 0 分ちょうどは GitHub が混む
        slot = next(c for c in crons if c.split()[1] == "0,9")
        self.assertGreater(int(slot.split()[0]), 0)         # 9:00 / 18:00（gate.SLOTS）を過ぎてから：前だと「次は…」で起こさない
        self.assertEqual(wf["permissions"]["actions"], "write")
        steps = {s.get("id") or s.get("name"): s for s in wf["jobs"]["run"]["steps"]}
        self.assertIn("collect_watch.py", steps["kick"]["run"])
        self.assertTrue(steps["kick"].get("continue-on-error"))
        emblem = next(s for s in wf["jobs"]["run"]["steps"] if "emblem_fill.py" in str(s.get("run")))
        self.assertTrue(emblem.get("continue-on-error"))
        commit = steps["提交"]["run"]
        add = commit[commit.index("ゲートの記録は"):commit.index("git add state/gate.json")]
        self.assertNotIn("GATE_FIRE", add.split("\n", 2)[-1])   # 変数が開いているだけでは足さない
        self.assertIn("steps.fire.outputs.fired", add)
        self.assertIn("steps.kick.outputs.kicked", add)

    def test_background_slots_match_processes(self):
        import processes
        wf = self.load("background.yml")
        slot = next(c["cron"] for c in wf[True]["schedule"] if c["cron"].split()[1] == "0,9").split()
        sched = next(p for p in processes.PROCESSES if p["id"] == "gate")["schedule"]
        for h in (0, 9):
            self.assertIn((h, int(slot[0])), sched)

    def test_digest(self):
        wf = self.load("digest.yml")
        self.assertEqual(wf["jobs"]["run"]["timeout-minutes"], 40)
        self.assertGreater(40, digest.COLLECT_DEADLINE_MIN * 2)   # 締め切りのあとに出刊・通知・push の時間が残る
        step = next(s for s in wf["jobs"]["run"]["steps"] if "新关注项 → 立刻 AI 编辑" in s.get("name", ""))
        self.assertIn("gate.py fire", step["run"])
        self.assertNotIn("api.anthropic.com", step["run"])       # 直接起こさない（一時停止・記録を通す）
        self.assertEqual(step["env"]["GATE_NOW"], "edit")
        self.assertIn("git push", step["run"])                   # 起こした記録を push


if __name__ == "__main__":
    unittest.main()
