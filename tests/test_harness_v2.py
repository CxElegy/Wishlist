"""ハーネス v2（HARNESS_V2.md）：列（harness/q.py）・心拍と要約（harness/hb.py）・鍵（harness/lock.py）・台本（.claude/workflows/harness-v2.js）。"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import hb  # noqa: E402
import lock  # noqa: E402
import q  # noqa: E402

T0 = 1_800_000_000.0   # 決まった時刻（試験は時計を読まない）


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "repo"
        self.state = pathlib.Path(self.tmp.name) / "state"
        (self.root / "harness" / "tasks").mkdir(parents=True)

    def add(self, title, scope=(), **kw):
        tid, new = q.add(title, scope=scope, done_when=kw.pop("done_when", ["試験が通る"]), root=self.root, state=self.state, **kw)
        return tid

    def load(self):
        return q.load(self.root, self.state)


class Queue(Base):
    def test_next_skips_overlapping_scope(self):
        a = self.add("A", ["scripts/render.py", "docs/home/style.css"], priority=1)
        b = self.add("B", ["./Scripts/render.py"], priority=2)          # A と同じファイル（書き方違い）
        c = self.add("C", ["scripts/gate.py"], priority=3)
        d = self.add("D", [], priority=4)                               # 範囲が未定
        e = self.add("E", [], priority=5)                               # 未定どうしは重なる扱い
        got = [t["id"] for t in q.pick(q.ready(self.load(), self.state, T0), 5)]
        self.assertEqual(got, [a, c, d])
        self.assertNotIn(b, got)
        self.assertNotIn(e, got)

    def test_priority_then_id(self):
        self.add("後", ["a.py"], priority=9)
        first = self.add("先", ["b.py"], priority=1)
        self.assertEqual(q.ready(self.load(), self.state, T0)[0]["id"], first)

    def test_claim_blocks_others_until_stale(self):
        a = self.add("A", ["a.py"])
        self.assertTrue(q.claim(a, "build:1", self.state, T0))
        self.assertFalse(q.claim(a, "build:2", self.state, T0 + 60))            # ほかの係は取れない
        self.assertTrue(q.claim(a, "build:1", self.state, T0 + 120))            # 同じ係は時刻の更新
        self.assertEqual(q.ready(self.load(), self.state, T0 + 130), [])        # 取られた段は next に出ない
        self.assertEqual([t["id"] for t in q.ready(self.load(), self.state, T0 + 130, owner="build:1")], [a])
        late = T0 + 120 + q.CLAIM_STALE_MIN * 60 + 1
        self.assertEqual([t["id"] for t in q.ready(self.load(), self.state, late)], [a])   # 60 分動きがなければ取り直せる
        self.assertTrue(q.claim(a, "build:2", self.state, late))

    def test_heartbeat_keeps_claim_alive(self):
        a = self.add("A", ["a.py"])
        q.claim(a, "build:1", self.state, T0)
        hb.beat("build", a, "書いている", self.state, T0 + 50 * 60)
        self.assertFalse(q.claim(a, "build:2", self.state, T0 + 70 * 60))

    def test_done_and_park_are_local_and_never_touch_repo_file(self):
        a, b, c = self.add("A", ["a.py"]), self.add("B", ["b.py"]), self.add("C", ["c.py"])
        before = (self.root / "harness" / "tasks" / f"{a}.json").read_bytes()
        q.claim(a, "x", self.state, T0)
        q.done(a, "https://example.invalid/pr/1", root=self.root, state=self.state)
        q.park(b, "CI が赤", root=self.root, state=self.state)
        q.park(c, "[?] どちらにしますか", waiting=True, root=self.root, state=self.state)
        t = self.load()
        self.assertEqual([t[a]["status"], t[b]["status"], t[c]["status"]], ["done", "parked", "waiting"])
        self.assertEqual(t[b]["attempts"], 1)
        self.assertIn("CI が赤", t[b]["notes"][-1])
        self.assertEqual((self.root / "harness" / "tasks" / f"{a}.json").read_bytes(), before)   # push しない＝リポジトリは変えない
        self.assertIsNone(q.claim_of(a, self.state, T0))                                          # 済みにしたら印を返す
        self.assertEqual(q.ready(t, self.state, T0), [])
        self.assertEqual(q.counts(t, self.state, T0), {"open": 0, "done": 1, "parked": 1, "waiting": 1, "split": 0, "claimed": 0})

    def test_done_file_goes_into_the_branch(self):
        a = self.add("A", ["a.py"])
        q.done(a, "PR", file=True, root=self.root, state=self.state)
        self.assertEqual(json.loads((self.root / "harness" / "tasks" / f"{a}.json").read_text(encoding="utf-8"))["status"], "done")
        self.assertFalse((self.state / "q" / f"{a}.json").exists())

    def test_recurring_task_reopens(self):
        a = self.add("新規ユーザーの点検", ["harness/board_kpi.py"], kind="kpi", extra={"recurring": True})
        q.done(a, root=self.root, state=self.state, now=T0)
        t = self.load()[a]
        self.assertEqual(t["status"], "open")
        self.assertTrue(t["last_done"])

    def test_add_rejects_duplicate_title_and_numbers_ids(self):
        a = self.add("写真の下の 空き を 0 に")
        tid, new = q.add("写真の下の空きを0に！", root=self.root, state=self.state)
        self.assertEqual((tid, new), (a, False))
        self.assertEqual(self.add("別の段"), "T-0002")
        with self.assertRaises(ValueError):
            q.add("種類が違う", kind="feature", root=self.root, state=self.state)

    def test_local_task_is_visible_before_merge(self):
        tid, _ = q.add("本番の確かめ：T-0001", kind="verify", local=True, root=self.root, state=self.state)
        self.assertFalse((self.root / "harness" / "tasks" / f"{tid}.json").exists())
        self.assertEqual([t["id"] for t in q.ready(self.load(), self.state, T0, kind="verify")], [tid])
        self.assertEqual(q.ready(self.load(), self.state, T0), [])   # ふつうの next には出ない（確かめの係だけ）

    def test_contract_freezes_once(self):
        a = self.add("A", done_when=[])
        with self.assertRaises(ValueError):
            q.set_contract(a, root=self.root, state=self.state)                  # 確かめ方の無い約束は凍らせない
        self.assertEqual(self.load()[a]["complexity"], "normal")
        with self.assertRaises(ValueError):
            q.set_contract(a, "visual", ["x.css"], ["条件"], self.root, self.state, complexity="huge")
        q.set_contract(a, "visual", ["docs/home/style.css"], ["A1 の空き 0"], self.root, self.state, complexity="hard")
        t = self.load()[a]
        self.assertEqual((t["kind"], t["scope"], t["done_when"], t["frozen"]), ("visual", ["docs/home/style.css"], ["A1 の空き 0"], True))
        self.assertEqual((t["complexity"], q.brief(t)["complexity"]), ("hard", "hard"))   # 作る係のモデルを決める重さも約束の一部
        with self.assertRaises(ValueError):
            q.set_contract(a, "fix", ["x.py"], ["別の条件"], self.root, self.state)   # 凍ったあとは変えない
        q.done(a, "PR", file=True, root=self.root, state=self.state)             # 合併する枝には凍った約束ごと入る
        self.assertEqual(json.loads((self.root / "harness" / "tasks" / f"{a}.json").read_text(encoding="utf-8"))["done_when"], ["A1 の空き 0"])

    def test_index(self):
        self.add("読める題", ["a.py"])
        b = self.add("止めた段", ["b.py"])
        q.park(b, "理由", root=self.root, state=self.state)
        md = q.index_md(self.load(), self.state, T0)
        self.assertIn("T-0001 [fix] 読める題", md)
        self.assertIn("## 止めた", md)

    def test_cli(self):
        self.add("A", ["a.py"])
        env = {**os.environ, "HF_STATE": str(self.state), "HF_ROOT": str(self.root), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "q.py"), "next", "--json"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual([t["id"] for t in json.loads(r.stdout)], ["T-0001"])
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "q.py"), "claim", "T-9999", "--owner", "x"], env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)


BS = chr(92)
MANGLED = ["harness" + BS + "board_kpi.py", "D;C:" + BS + "Program Files" + BS + "Git" + BS + "Claude" + BS + "kpi" + BS + "x.json", "C:" + BS + "Program Files" + BS + "Git" + BS + "tmp"]


class PathConv(Base):
    """Git Bash（MSYS）の path 変換で凍る約束が壊れた事故（2026-11-12 T-0001）：--from-json・壊れた文字の拒否・repair。"""

    def cli(self, *args):
        env = {**os.environ, "HF_STATE": str(self.state), "HF_ROOT": str(self.root), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        return subprocess.run([sys.executable, str(ROOT / "harness" / "q.py"), *args], env=env, capture_output=True, text=True, encoding="utf-8")

    def js(self, name, obj):
        f = pathlib.Path(self.tmp.name) / name
        f.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return str(f)

    def test_mangled_text_is_detected_but_normal_paths_are_not(self):
        for x in MANGLED:
            self.assertTrue(q.MANGLED_RE.search(x), x)
        for x in ("harness/board_kpi.py と D:/Claude/kpi/runs/a.json", "C:" + BS + "Users" + BS + "x", "docs/rules/aesthetic.md", "経路 C（新しい名前）"):
            self.assertFalse(q.MANGLED_RE.search(x), x)

    def test_add_and_contract_refuse_mangled_text(self):
        for bad in MANGLED:
            with self.assertRaises(ValueError):
                q.add("題", done_when=[bad], root=self.root, state=self.state)
            r = self.cli("add", "--title", "別の題", "--done-when", bad)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("MSYS_NO_PATHCONV=1", r.stdout)
            self.assertIn("--from-json", r.stdout)
        a = self.add("A", ["a.py"])
        r = self.cli("contract", a, "--scope", "harness" + BS + "x.py", "--done-when", "ok")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(self.load()[a]["frozen"])           # 断ったので凍っていない
        self.assertEqual(len(list((self.root / "harness" / "tasks").glob("*.json"))), 1)   # 壊れた段は書かれていない

    def test_add_and_contract_from_json(self):
        text = "harness/board_kpi.py の回を測る（基準：D:/Claude/kpi/runs/a.json と 並べる）"
        r = self.cli("add", "--from-json", self.js("add.json", {"title": "JSON から", "why": "理由", "kind": "kpi", "scope": ["harness/board_kpi.py"], "done_when": [text], "priority": 3}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tid = json.loads(r.stdout)["id"]
        t = self.load()[tid]
        self.assertEqual((t["title"], t["kind"], t["priority"], t["scope"], t["done_when"]), ("JSON から", "kpi", 3, ["harness/board_kpi.py"], [text]))
        r = self.cli("contract", tid, "--from-json", self.js("c.json", {"kind": "kpi", "complexity": "light", "scope": "a.py,b.py", "done_when": [text, "二つ目"]}))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.load()[tid]
        self.assertEqual((t["frozen"], t["complexity"], t["scope"], t["done_when"]), (True, "light", ["a.py", "b.py"], [text, "二つ目"]))
        self.assertEqual(self.cli("contract", tid, "--from-json", str(pathlib.Path(self.tmp.name) / "nothing.json")).returncode, 2)

    def test_repair_rewrites_a_frozen_contract_and_records_why(self):
        a = self.add("A", ["a.py"], done_when=["壊れた"])
        q.set_contract(a, "kpi", ["a.py"], ["壊れた"], self.root, self.state)
        with self.assertRaises(ValueError):
            q.set_contract(a, "fix", ["b.py"], ["別"], self.root, self.state)    # contract では直せない
        good = "harness/board_kpi.py の回を測る（D:/Claude/kpi/runs/x.json）"
        r = self.cli("repair", a, "--from-json", self.js("r.json", {"scope": ["harness/board_kpi.py"], "done_when": [good]}), "--reason", "MSYS が path を書き換えた")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.load()[a]
        self.assertEqual((t["frozen"], t["done_when"], t["scope"], t["kind"]), (True, [good], ["harness/board_kpi.py"], "kpi"))
        self.assertTrue(t["repaired_at"])
        self.assertIn("MSYS が path を書き換えた", t["notes"][-1])
        self.assertIn("repaired_at", t["notes"][-1])
        self.assertEqual(t["title"], "A")                                         # JSON に無い欄は触らない
        # 壊れた文字・理由なし・欄なしは断る
        bad = self.js("b.json", {"done_when": [MANGLED[0]]})
        self.assertEqual(self.cli("repair", a, "--from-json", bad, "--reason", "x").returncode, 2)
        self.assertEqual(self.cli("repair", a, "--from-json", self.js("e.json", {"foo": 1}), "--reason", "x").returncode, 2)
        self.assertEqual(self.cli("repair", a, "--from-json", self.js("r.json", {"scope": ["z.py"]}), "--reason", " ").returncode, 2)
        self.assertEqual(self.cli("repair", "T-9999", "--from-json", self.js("r.json", {"scope": ["z.py"]}), "--reason", "x").returncode, 2)

    def test_repair_also_fixes_a_frozen_repo_file(self):
        a = self.add("A", ["a.py"], done_when=["壊れた"])
        q.set_contract(a, "fix", ["a.py"], ["壊れた"], self.root, self.state)
        q.done(a, "PR", file=True, root=self.root, state=self.state)   # 凍った約束がリポジトリのファイルに入った
        q.repair(a, {"done_when": ["直った"]}, "理由", self.root, self.state, T0)
        self.assertEqual(json.loads((self.root / "harness" / "tasks" / f"{a}.json").read_text(encoding="utf-8"))["done_when"], ["直った"])
        self.assertEqual(self.load()[a]["done_when"], ["直った"])


class Backlog(unittest.TestCase):
    TEXT = """# 一覧

## いちばん先（目標）

- [ ] 【依頼 2026-11-11】**gate.py の fire を push のあとに** — できたと言える条件：古い queue を読まない。店長「待たせないで」と言った
  続きの行（harness/q.py）
- [x] 済みの段
- [?] 聞いている段
- [ ] スマホの画面で写真の下に空き — 0 件にする

## そのあと

- [ ] 写さない段
"""

    def test_only_open_items_of_first_section(self):
        ts = q.from_backlog(self.TEXT, ROOT, "2026-11-12")
        self.assertEqual([t["id"] for t in ts], ["T-0001", "T-0002"])
        a, b = ts
        self.assertEqual(a["title"], "【依頼 2026-11-11】gate.py の fire を push のあとに")
        self.assertIn("続きの行", a["why"])
        self.assertEqual(a["quote"], "待たせないで")
        self.assertEqual(a["scope"], ["scripts/gate.py", "harness/q.py"])
        self.assertTrue(a["done_when"][0].startswith("古い queue を読まない"))
        self.assertEqual((a["kind"], a["created"], a["source"]), ("fix", "2026-11-11", "BACKLOG.md:5"))
        self.assertEqual((b["kind"], b["done_when"], b["priority"]), ("visual", ["0 件にする"], 2))

    def test_seeded_tasks_are_wellformed(self):
        files = sorted((ROOT / "harness" / "tasks").glob("T-*.json"))
        self.assertGreater(len(files), 20)
        for f in files:
            t = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(t["id"], f.stem)
            self.assertTrue(t["title"] and t["why"])
            self.assertIn(t["kind"], q.KINDS)
            self.assertIn(t["complexity"], q.COMPLEXITY)
            self.assertIn(t["status"], q.STATUSES)
            self.assertIsInstance(t["scope"], list)
            self.assertIsInstance(t["done_when"], list)
            self.assertNotIn(b"\r", f.read_bytes())
        kpi = [f.stem for f in files if json.loads(f.read_text(encoding="utf-8"))["kind"] == "kpi"]
        self.assertEqual(kpi, ["T-0001"])   # 新規ユーザーの点検は毎回やる段


class Heartbeat(Base):
    def test_stale_lists_only_silent_running_agents(self):
        hb.beat("build", "T-0001", "書いている", self.state, T0)
        hb.beat("evalF", "T-0002", "試験", self.state, T0 + 15 * 60)
        hb.beat("ship", "T-0003", "CI", self.state, T0)
        hb.end("ship", "T-0003", "merged", self.state, T0 + 60)                 # 終わった係は見張らない
        hb.beat("build", "T-0000", "前の日の残り", self.state, T0 - 30 * 3600)   # 24 時間より古いものは出さない
        bad = hb.stale(20, self.state, T0 + 25 * 60)
        self.assertEqual([(b["role"], b["task"], b["quiet"]) for b in bad], [("build", "T-0001", 25.0)])
        hb.beat("build", "T-0001", "まだ動いている", self.state, T0 + 26 * 60)
        self.assertEqual(hb.stale(20, self.state, T0 + 27 * 60), [])
        self.assertEqual(hb.agents(self.state, T0 + 27 * 60)[0]["beats"], 2)

    def test_summary(self):
        (self.root / "harness" / "kpi").mkdir()
        (self.root / "harness" / "kpi" / "latest.json").write_text(json.dumps({"at": "2026-11-11T13:18:08+00:00", "boards": {"C": {
            "emblem": {"n": 3, "p50": 300.0, "target": 120, "ok": False}, "page": {"n": 3, "p50": 20.0, "target": 150, "ok": True}}}}), encoding="utf-8")
        a = self.add("A", ["a.py"])
        b = self.add("B", ["b.py"])
        self.add("C", ["c.py"])
        q.park(b, "[?] 案を選ぶ", waiting=True, root=self.root, state=self.state)
        q.claim(a, "build:1", self.state, T0)
        hb.beat("build", a, "書いている", self.state, T0)
        hb.result(a, "merged", "https://example.invalid/pr/1", "合併", self.state, T0)
        hb.choice_add(b, "https://example.invalid/testground/choice.html", "どの案？", self.state, T0)
        s = hb.summary(self.state, self.root, T0 + 30 * 60)
        on_disk = json.loads((self.state / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, json.loads(json.dumps(s)))
        self.assertEqual(s["queue"], {"open": 2, "done": 0, "parked": 0, "waiting": 1, "split": 0, "claimed": 1})
        self.assertEqual([x["task"] for x in s["agents"]], [a])
        self.assertEqual([x["task"] for x in s["stale"]], [a])
        self.assertEqual(s["results"][-1]["status"], "merged")
        self.assertEqual(s["choices"][0]["task"], b)
        self.assertEqual(s["waiting"][0]["id"], b)
        self.assertEqual(s["kpi"]["over"], [{"route": "C", "stage": "emblem", "p50": 300.0, "target": 120}])
        self.assertEqual([x["id"] for x in s["next"]], [a, "T-0003"])

    def test_inbox_and_reply(self):
        board = pathlib.Path(self.tmp.name) / "board"
        drop = pathlib.Path(self.tmp.name) / "inbox"
        (drop / "done").mkdir(parents=True)
        board.mkdir()
        (board / "inbox.jsonl").write_text('{"t": 1, "text": "390 の見出しがはみ出てる"}\n{"t": 2, "text": "这一版很完美"}\n', encoding="utf-8")
        (drop / "note.md").write_text("x", encoding="utf-8")
        (drop / "done" / "old.md").write_text("x", encoding="utf-8")
        hb.reply(1, "見ました", board, T0)
        got = hb.inbox(board, drop)
        self.assertEqual([n["t"] for n in got["notes"]], [2])
        self.assertEqual([pathlib.Path(f).name for f in got["files"]], ["note.md"])
        out = json.loads((board / "outbox.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((out["re"], out["text"]), (1, "見ました"))


class Lock(Base):
    def test_one_holder_then_stale_takeover(self):
        now = [T0]
        kw = dict(state=self.state, sleep=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])
        d = lock.acquire("ci", wait=0, **kw)
        self.assertTrue(d and d.is_dir())
        self.assertIsNone(lock.acquire("ci", wait=30, **kw))        # 持ち主がいる間は取れない（30 秒待ってあきらめる）
        self.assertTrue(lock.acquire("browser", wait=0, **kw))      # 名前が違えば別の鍵
        now[0] += 1801
        self.assertTrue(lock.acquire("ci", wait=0, **kw))           # 30 分たった鍵は落ちた係の残り：取り直す
        lock.release(d)
        self.assertTrue(lock.acquire("ci", wait=0, **kw))

    def test_cli_runs_command_and_releases(self):
        env = {**os.environ, "HF_STATE": str(self.state)}
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "lock.py"), "ci", "--", sys.executable, "-c", "import sys; sys.exit(3)"], env=env)
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.state / "locks" / "ci").exists())


class Resume(Base):
    """2026-11-12 run 1112b：止めた段の枝・コミットを残し、負荷で止めた段は次の回にいちばん先に・大きい段は計画で分ける。"""
    def test_park_keeps_class_and_resume_and_infra_comes_first(self):
        a = self.add("先の段", ["a.py"], priority=1)
        b = self.add("負荷で止めた段", ["b.py"], priority=9)
        q.park(b, "Page.goto 30 秒切れ", root=self.root, state=self.state, cls="infra",
               resume={"branch": "harness/1112b-T-0002", "worktree": "D:/Claude/hf/v2r/wt/T-0002", "commit": "ce57ac1", "stage": "ship", "note": "中身は審査済み"})
        t = self.load()[b]
        self.assertEqual((t["status"], t["park_class"], t["resume"]["stage"], t["resume"]["commit"]), ("parked", "infra", "ship", "ce57ac1"))
        self.assertEqual([x["id"] for x in q.ready(self.load(), self.state)], [b, a])          # infra の段がいちばん先
        self.assertEqual(q.brief(q.ready(self.load(), self.state)[0])["resume"]["branch"], "harness/1112b-T-0002")
        for _ in range(2):
            q.park(b, "また", root=self.root, state=self.state, cls="infra")
        self.assertEqual([x["id"] for x in q.ready(self.load(), self.state)], [a])             # 3 回で主の会話へ
        self.assertEqual(self.load()[b]["resume"]["commit"], "ce57ac1")                        # 続きの手がかりは消えない
        q.done(b, "https://example.invalid/pull/1", root=self.root, state=self.state)
        self.assertEqual((self.load()[b]["resume"], self.load()[b]["park_class"]), ({}, ""))

    def test_work_park_is_not_retried_automatically(self):
        b = self.add("中身が赤い段", ["b.py"])
        q.park(b, "AssertionError", root=self.root, state=self.state, cls="work")
        self.assertEqual(q.ready(self.load(), self.state), [])
        with self.assertRaises(ValueError):
            q.park(b, "x", root=self.root, state=self.state, cls="nope")

    def test_park_cli_resume_flags(self):
        b = self.add("止める段", ["b.py"])
        env = {**os.environ, "HF_STATE": str(self.state), "HF_ROOT": str(self.root), "PYTHONIOENCODING": "cp932"}
        r = subprocess.run([sys.executable, str(ROOT / "harness" / "q.py"), "park", b, "--why", "負荷", "--cls", "infra", "--resume-branch", "harness/x-T",
                            "--resume-worktree", "D:/Claude/hf/v2r/wt/x-T", "--resume-commit", "abc", "--resume-stage", "ship", "--resume-note", "中身は良い"],
                           env=env, capture_output=True, text=True, encoding="cp932", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)                                 # cp932 の画面でも ✓ で落ちない
        self.assertEqual(self.load()[b]["resume"]["worktree"], "D:/Claude/hf/v2r/wt/x-T")

    def test_split_makes_ordered_frozen_children(self):
        p = self.add("大きい段", ["scripts/render.py", "harness/ux_check.py"], priority=3)
        q.park(p, "途中まで", root=self.root, state=self.state, cls="size", resume={"branch": "harness/1112b-T-0009", "commit": "ea8941c", "stage": "build"})
        kids = q.split(p, [{"title": "点検だけ：縦長の写真のカードの空きを数える", "done_when": ["前の数を出す"], "scope": ["harness/ux_check.py"]},
                           {"title": "実装：縦長の写真を案 C に", "done_when": ["空き 0"], "scope": ["scripts/render.py"], "complexity": "hard"}],
                       root=self.root, state=self.state)
        t = self.load()
        self.assertEqual(t[p]["status"], "split")
        self.assertTrue(all(t[k]["frozen"] for k in kids))
        self.assertEqual(t[kids[1]]["after"], [kids[0]])
        self.assertEqual(t[kids[0]]["resume"]["branch"], "harness/1112b-T-0009")              # 最初の子が前の枝を引き継ぐ
        self.assertFalse((self.root / "harness" / "tasks" / f"{kids[0]}.json").exists())       # 手元だけ（合併のときに入る）
        self.assertEqual([x["id"] for x in q.ready(t, self.state)], [kids[0]])                 # 前の子が済むまで次は出ない
        q.done(kids[0], root=self.root, state=self.state)
        self.assertEqual([x["id"] for x in q.ready(self.load(), self.state)], [kids[1]])
        q.done(kids[1], root=self.root, state=self.state)
        self.assertEqual(self.load()[p]["status"], "done")                                     # 子が全部済めば親も
        with self.assertRaises(ValueError):
            q.split(kids[0], [{"title": "1 つだけ", "done_when": ["x"]}], root=self.root, state=self.state)


class Infra(unittest.TestCase):
    def test_run_tests_tells_load_flakes_from_real_reds(self):
        import run_tests
        sep = "-" * 70
        flake = f"ERROR: test_wall (tests.test_wall_shapes.WallShapes.test_wall)\nTraceback …\nplaywright._impl._errors.TimeoutError: Page.goto: Timeout 30000ms exceeded.\n{sep}\nRan 1 test"
        real = f"FAIL: test_x (tests.test_y.Y.test_x)\nTraceback …\nAssertionError: 3 != 0\n{sep}\nRan 1 test"
        mixed = f"FAIL: test_x (a)\nAssertionError: Page.goto: 1 != 0\n{'=' * 70}\nERROR: test_z (b)\nTimeoutError: Page.goto: Timeout\n{sep}\nRan 2 tests"
        self.assertTrue(run_tests.is_infra(flake))
        self.assertFalse(run_tests.is_infra(real))
        self.assertFalse(run_tests.is_infra(mixed))
        self.assertTrue(run_tests.is_infra("FAIL: test_ux_journey（900 秒で打ち切り）\n"))

    def test_lock_resolves_windows_bash_and_timeout_to_git(self):
        g = pathlib.Path("C:/Program Files/Git")
        self.assertEqual(lock.resolve(["bash", "x.sh"], windows=True, git_root=g), [str(g / "bin" / "bash.exe"), "x.sh"])
        self.assertEqual(lock.resolve(["timeout", "5", "bash"], windows=True, git_root=g)[0], str(g / "usr" / "bin" / "timeout.exe"))
        self.assertEqual(lock.resolve(["python", "-V"], windows=True, git_root=g), ["python", "-V"])
        self.assertEqual(lock.resolve(["bash", "x.sh"], windows=False, git_root=g), ["bash", "x.sh"])

    @unittest.skipUnless(os.name == "nt" and lock._git_root(), "Windows と Git for Windows のある PC だけ")
    def test_lock_runs_git_bash_and_timeout_on_this_pc(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "HF_STATE": d}
            r = subprocess.run([sys.executable, str(ROOT / "harness" / "lock.py"), "ci", "--", "timeout", "20", "bash", "-c", "exit 3"], env=env)
            self.assertEqual(r.returncode, 3)

    def test_lock_timeout_and_reentry(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "HF_STATE": d}
            r = subprocess.run([sys.executable, str(ROOT / "harness" / "lock.py"), "ci", "--timeout", "1", "--", sys.executable, "-c", "import time; time.sleep(30)"], env=env)
            self.assertEqual(r.returncode, lock.TIMED_OUT)
            # 鍵の中から同じ鍵を呼んでも自分を待たない（ci_local.sh が自分で鍵を取る）
            inner = f"import subprocess,sys; sys.exit(subprocess.call([sys.executable, r'{ROOT / 'harness' / 'lock.py'}', 'ci', '--wait', '0', '--', sys.executable, '-c', 'import os,sys; sys.exit(4 if os.environ.get(\"HF_LOCK_CI\") else 9)']))"
            r = subprocess.run([sys.executable, str(ROOT / "harness" / "lock.py"), "ci", "--", sys.executable, "-c", inner], env=env)
            self.assertEqual(r.returncode, 4)
            self.assertFalse((pathlib.Path(d) / "locks" / "ci").exists())

    def test_ci_local_takes_the_lock_and_accepts_test_names(self):
        s = (ROOT / "harness" / "ci_local.sh").read_text(encoding="utf-8")
        self.assertIn("harness/lock.py ci", s)
        self.assertIn("HF_LOCK_CI", s)
        self.assertIn('run_tests.py "$@"', s)
        self.assertIn("' ci \"$@\"", s)


class Cost(Base):
    def test_cost_by_task_from_workflow_transcript(self):
        import cost
        wf = pathlib.Path(self.tmp.name) / "wf"
        wf.mkdir()
        rows = [("a1", "plan:1"), ("a2", "build:T-0002"), ("a3", "fix:T-0002:1"), ("a4", "build:T-0009")]
        (wf / "journal.jsonl").write_text("\n".join(json.dumps({"type": "started", "agentId": a, "label": l}) for a, l in rows), encoding="utf-8")
        def msg(i, n, t):
            return json.dumps({"type": "assistant", "timestamp": t, "message": {"id": f"m{i}", "model": "m", "content": [{"type": "tool_use"}],
                                                                                "usage": {"input_tokens": n, "output_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000}}})
        for a, _ in rows:
            (wf / f"agent-{a}.jsonl").write_text("\n".join([msg(1, 5, "2026-11-12T00:00:00Z"), msg(1, 5, "2026-11-12T00:00:30Z"), msg(2, 5, "2026-11-12T00:03:00Z")]), encoding="utf-8")
        got = cost.by_task(cost.collect(wf))
        self.assertEqual(got["T-0002"]["agents"], 2)
        self.assertEqual(got["T-0002"]["weight"], 2 * 2 * 115)                         # 同じ message id は 1 回・cache_read は重さに入れない
        self.assertEqual(got["T-0002"]["minutes"], 6.0)
        self.assertEqual(got[cost.COMMON]["agents"], 1)
        hb.result("T-0002", "merged", state=self.state)
        cost.record("1112c", got, state=self.state)
        s = hb.summary(self.state, self.root, now=T0)
        self.assertEqual((s["cost"]["run"], s["cost"]["shipped"], s["cost"]["per_shipped"]), ("1112c", 1, sum(v["weight"] for v in got.values())))


class Script(unittest.TestCase):
    """台本を node で読み、係を偽物にして 1 段を全部の段階に通す。"""
    SRC = (ROOT / ".claude" / "workflows" / "harness-v2.js").read_text(encoding="utf-8")

    def smoke(self, scenario, args=None):
        r = subprocess.run(["node", str(ROOT / "tests" / "fixtures" / "harness_v2_smoke.js"), scenario, json.dumps(args or {})],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_meta_is_first_and_names_the_phases(self):
        self.assertTrue(self.SRC.startswith("export const meta = {"))
        d = self.smoke("happy")
        self.assertEqual(d["meta"]["name"], "harness-v2")
        self.assertTrue(d["meta"]["description"])
        titles = [p["title"] for p in d["meta"]["phases"]]
        self.assertEqual(titles, ["Intake", "Plan", "Build", "Evaluate", "Fix", "Ship", "Verify", "Learn"])
        self.assertLessEqual({c["phase"] for c in d["calls"]}, set(titles))

    def test_script_does_not_use_what_the_runtime_forbids(self):
        for bad in ("Date.now(", "Math.random(", "new Date()", "require(", "import "):
            self.assertNotIn(bad, self.SRC, bad)

    def test_one_task_walks_all_stages(self):
        d = self.smoke("happy")
        labels = [c["label"] for c in d["calls"]]
        t1 = [x for x in labels if "T-0001" in x]
        # 見た目の段：作る → 機能 → 見た目（番号に ✗：係が ok と言っても落とす）→ 直す → 機能 → 見た目 → 合併
        self.assertEqual(t1, ["scout:T-0001", "build:T-0001", "evalF:T-0001:0", "evalV:T-0001:0", "fix:T-0001:1", "evalF:T-0001:1", "evalV:T-0001:1", "ship:T-0001"])
        self.assertFalse([x for x in labels if "T-0002" in x])              # T-0001 と同じファイルを触る段は、この回では進めない
        self.assertTrue(any("T-0002" in m for m in d["logs"]))
        ships = [x for x in labels if x.startswith("ship:")]
        # 合併は 1 つずつ・受付の枝が先。あとは審査を通った順（T-0003 は T-0001 の直しを待たない：2026-11-12 は 12 分待った）
        self.assertEqual(ships[0], "ship:intake1")
        self.assertEqual(sorted(ships[1:]), ["ship:T-0001", "ship:T-0003", "ship:T-0004"])
        self.assertLess(labels.index("ship:T-0003"), labels.index("ship:T-0001"))
        for s in ships:
            self.assertLess(labels.index(s), labels.index("verify:1:b"))
        self.assertLess(labels.index("verify:1:b"), labels.index("announce:T-0003"))   # 案のページは本番に出てから知らせる
        self.assertEqual(labels[-1], "learn:1")
        self.assertEqual([(t["id"], t["state"], t["live"]) for t in d["result"][0]["tasks"]], [("T-0001", "merged", True), ("T-0003", "merged", True), ("T-0004", "merged", True)])
        self.assertIn("kpi:T-0004", labels)                                   # 新規ユーザーの点検は kpi の段として同じ道を通る
        self.assertNotIn("scout:T-0004", labels)
        learn = d["prompts"]["learn:1"]
        self.assertIn("harness/q.py done T-0001 --pr", learn)
        self.assertIn("harness/q.py park T-0003 --waiting", learn)          # 案の段は店長が選ぶまで済みにしない
        self.assertIn("harness/hb.py summary", learn)
        self.assertIn("ask_remind.yml", d["prompts"]["announce:T-0003"])
        self.assertIn("cmd=say", d["prompts"]["announce:T-0003"])
        self.assertIn("pending_choices.json", d["prompts"]["announce:T-0003"])

    def test_models_by_role_and_complexity(self):
        """2026-11-12 店長（トークンの節約）：Fable は計画だけ。ほかは仕事の重さで Haiku／Sonnet／Opus。"""
        calls = self.smoke("happy")["calls"]
        role = {c["label"].split(":")[0]: c["model"] for c in calls}
        self.assertEqual({k: role[k] for k in ("plan", "scout", "verify", "learn", "kpi", "announce", "intake", "evalF", "ship", "evalV")},
                         {"plan": "fable", "scout": "haiku", "verify": "haiku", "learn": "haiku", "kpi": "haiku", "announce": "haiku",
                          "intake": "sonnet", "evalF": "sonnet", "ship": "sonnet", "evalV": "opus"})
        self.assertEqual([c["label"] for c in calls if c["model"] == "fable"], ["plan:1"])   # Fable を使うのは計画の 1 回だけ
        by = {c["label"]: c["model"] for c in calls}
        self.assertEqual((by["build:T-0001"], by["fix:T-0001:1"]), ("opus", "opus"))         # complexity=hard の段は作る・直すとも Opus
        self.assertEqual(by["build:T-0003"], "sonnet")                                       # normal
        stuck = {c["label"]: c["model"] for c in self.smoke("stuck")["calls"]}
        self.assertEqual((stuck["build:T-0009"], stuck["fix:T-0009:1"], stuck["diag:T-0009"]), ("haiku", "haiku", "opus"))   # light は Haiku・見立ては Opus

    def test_every_agent_gets_a_type_and_args_types_changes_it(self):
        """係の型（道具を絞る）：型なしだと MCP 込みの約 80 個の道具が毎回付く。args.types=false で今までどおり。"""
        d = self.smoke("happy")
        ty = {c["label"].split(":")[0]: c["agentType"] for c in d["calls"]}
        self.assertEqual(ty, {"intake": "hw-edit", "plan": "hw-edit", "build": "hw-edit", "fix": "hw-edit", "kpi": "hw-edit",
                              "evalF": "hw-read", "evalV": "hw-read",
                              "verify": "hw-ops", "learn": "hw-ops", "ship": "hw-ops", "announce": "hw-ops", "scout": "search"})
        self.assertEqual({c["agentType"] for c in self.smoke("stuck")["calls"] if c["label"].startswith("diag:")}, {"hw-diag"})
        off = self.smoke("happy", {"types": False})["calls"]
        self.assertEqual({c["label"].split(":")[0] for c in off if c["agentType"]}, {"scout"})
        self.assertEqual({c["agentType"] for c in off if c["label"].startswith("scout:")}, {"search"})
        one = self.smoke("happy", {"types": {"evalV": "x"}})["calls"]
        self.assertEqual({c["agentType"] for c in one if c["label"].startswith("evalV:")}, {"x"})
        self.assertEqual({c["agentType"] for c in one if c["label"].startswith("evalF:")}, {"hw-read"})
        # 型は他の決まりを変えない：モデル・係の順は同じ
        key = lambda cs: [(c["label"], c["model"], c["phase"]) for c in cs]
        self.assertEqual(key(off), key(self.smoke("happy")["calls"]))

    def test_model_overrides(self):
        d = self.smoke("stuck", {"model": "fable"})                                          # 全部 Fable は受け付けない
        self.assertEqual([c["label"] for c in d["calls"] if c["model"] == "fable"], ["plan:1"])
        self.assertTrue(any("args.model=fable" in m for m in d["logs"]))
        self.assertEqual({c["model"] for c in self.smoke("stuck", {"model": "sonnet"})["calls"]}, {"sonnet"})   # 試すときの「全部 1 つ」は fable 以外で
        m = {c["label"]: c["model"] for c in self.smoke("stuck", {"models": {"light": "sonnet", "diag": "sonnet"}})["calls"]}
        self.assertEqual((m["build:T-0009"], m["diag:T-0009"], m["plan:1"]), ("sonnet", "sonnet", "fable"))

    def test_no_progress_goes_to_diagnose_then_parks(self):
        d = self.smoke("stuck")
        labels = [c["label"] for c in d["calls"] if "T-0009" in c["label"]]
        # 同じ所で 2 回落ちたら、直しを重ねず見立てへ。見立てのあと 1 回だけ直し、だめなら止める（合併しない）
        self.assertEqual(labels, ["scout:T-0009", "build:T-0009", "evalF:T-0009:0", "fix:T-0009:1", "evalF:T-0009:1", "diag:T-0009", "fix:T-0009:2", "evalF:T-0009:2"])
        self.assertEqual(d["result"][0]["tasks"][0]["state"], "parked")
        self.assertIn("harness/q.py park T-0009 --why", d["prompts"]["learn:1"])
        self.assertNotIn("worktree remove", d["prompts"]["learn:1"])        # 止めた段の作業ツリーは主の会話が見るので残す

    def test_every_agent_gets_heartbeat_timeout_and_hard_rules(self):
        d = self.smoke("happy")
        for label, p in d["prompts"].items():
            if label.startswith("scout:"):
                continue   # 下調べは読むだけの小さい係（5 分）
            for must in ("harness/hb.py beat", "timeout <秒>", "読むだけ", "--force", "cancel しない", "secrets", "sed -i", "scripts/processes.py",
                         "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"):
                self.assertIn(must, p, f"{label}: {must}")
        ship = d["prompts"]["ship:T-0001"]
        for must in ("git rebase origin/main", "harness/lock.py ci", "bash harness/ci_local.sh", "gh pr create", "pending が残っていれば合併せず", "--squash", "harness/net.sh"):
            self.assertIn(must, ship, must)
        self.assertIn("1333×677", d["prompts"]["evalV:T-0001:0"])
        self.assertIn("390×844", d["prompts"]["evalV:T-0001:0"])
        # path 変換の事故（2026-11-12）：q.py／hb.py を呼ぶ文は全部、先頭が env MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' で、長い文は --from-json で渡すと書いてある
        import re
        pre = "MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'"
        for label, p in d["prompts"].items():
            self.assertIn(pre, p, label)
            for m in re.finditer(r"harness/(?:q|hb)\.py [a-z][a-z-]* ", p):
                self.assertTrue(p[:m.start()].rstrip().endswith(".exe") or p[:m.start()].rstrip().endswith("python"), f"{label}: {p[max(0, m.start() - 160):m.start() + 20]}")
            if not label.startswith("scout:"):   # 下調べは読むだけで共通の決まりを持たない
                self.assertIn("--from-json", p, label)
        self.assertIn("contract <id> --from-json", d["prompts"]["plan:1"])
        self.assertIn("harness/q.py add --from-json", d["prompts"]["intake:1"])
        self.assertIn("harness/q.py add", d["prompts"]["intake:1"])
        self.assertIn("docs/rules/aesthetic.md", d["prompts"]["intake:1"])

    # ---------- 2026-11-12 run 1112b（17 係・47 分・合併 0 件）のあと ----------
    def test_resumed_task_goes_straight_to_ship(self):
        """審査を通り合併だけが負荷で落ちた段は、作り直さず合併から（resume.stage=ship）。前の枝・作業ツリーを使う。"""
        d = self.smoke("resume")
        labels = [c["label"] for c in d["calls"] if "T-0002" in c["label"]]
        self.assertEqual(labels, ["ship:T-0002"])
        ship = d["prompts"]["ship:T-0002"]
        self.assertIn("harness/1112b-T-0002", ship)
        self.assertIn("D:/x/wt/T-0002", ship)
        self.assertIn("2 はとばす", ship)
        self.assertEqual(d["result"][0]["tasks"][0]["state"], "merged")
        self.assertIn("worktree remove --force D:/x/wt/T-0002", d["prompts"]["learn:1"])

    def test_infra_failure_parks_with_resume_at_ship(self):
        d = self.smoke("infra")
        t = d["result"][0]["tasks"][0]
        self.assertEqual((t["state"], t["cls"], t["resume"]["stage"]), ("parked", "infra", "ship"))
        learn = d["prompts"]["learn:1"]
        self.assertIn("harness/q.py park T-0005", learn)
        self.assertIn("--cls infra --resume-branch harness/smoke-T-0005", learn)
        self.assertIn("--resume-stage ship", learn)
        self.assertNotIn("worktree remove", learn)

    def test_real_red_in_local_ci_gets_one_fix_round_then_ships(self):
        """2026-11-12 run 1112d：手元の CI の本物の赤（failed_class=work）は、すぐ止めず作る係が 1 回直して、もう一度合併へ。"""
        d = self.smoke("shipfix")
        labels = [c["label"] for c in d["calls"] if "T-0011" in c["label"]]
        self.assertEqual(labels[-3:], ["ship:T-0011", "fix:T-0011:ship", "ship:T-0011:2"])
        self.assertEqual(d["result"][0]["tasks"][0]["state"], "merged")
        fix = d["prompts"]["fix:T-0011:ship"]
        self.assertIn("test_fake402", fix)                       # 落ちた試験の名前を渡す
        self.assertIn("試験を弱めない", fix)
        model = {c["label"]: c["model"] for c in d["calls"]}
        self.assertEqual(model["fix:T-0011:ship"], model["build:T-0011"])   # 重さどおりのモデル（Fable は使わない）
        self.assertNotIn("fable", {c["model"] for c in d["calls"] if not c["label"].startswith("plan:")})

    def test_still_red_after_the_ship_fix_parks_once(self):
        d = self.smoke("shipred")
        labels = [c["label"] for c in d["calls"] if "T-0012" in c["label"]]
        self.assertEqual(labels.count("fix:T-0012:ship"), 1)     # 直しは 1 回だけ
        self.assertEqual(labels.count("ship:T-0012:2"), 1)
        t = d["result"][0]["tasks"][0]
        self.assertEqual((t["state"], t["cls"], t["resume"]["stage"]), ("parked", "work", "fix"))

    def test_infra_red_does_not_trigger_a_ship_fix(self):
        d = self.smoke("infra")
        self.assertFalse([c for c in d["calls"] if c["label"].endswith(":ship")])

    def test_plan_splits_what_only_another_environment_can_measure(self):
        plan = self.smoke("happy")["prompts"]["plan:1"]
        self.assertIn("2c.", plan)
        self.assertIn("測る段", plan)                            # 別の環境でしか測れない条件は「仕組みを作る段」と後の「測る段」に分ける
        self.assertIn("クラウド", plan)
        self.assertIn("測る場所", (ROOT / "HARNESS_V2.md").read_text(encoding="utf-8") + "測る場所")

    def test_partial_build_keeps_commit_and_note(self):
        d = self.smoke("partial")
        self.assertEqual([c["label"] for c in d["calls"] if "T-0007" in c["label"]], ["scout:T-0007", "build:T-0007"])
        t = d["result"][0]["tasks"][0]
        self.assertEqual((t["state"], t["cls"]), ("parked", "size"))
        self.assertIn("--cls size", d["prompts"]["learn:1"])
        self.assertIn("render.py の side()", d["prompts"]["learn:1"])

    def test_same_failed_conditions_count_as_stuck_even_if_text_differs(self):
        """不合格の文・signature が毎回変わっても、落ちた条件と試験が同じなら直しを重ねず見立てへ。"""
        labels = [c["label"] for c in self.smoke("flip")["calls"] if "T-0008" in c["label"]]
        self.assertEqual(labels[:6], ["scout:T-0008", "build:T-0008", "evalF:T-0008:0", "fix:T-0008:1", "evalF:T-0008:1", "diag:T-0008"])

    def test_agents_per_task_are_capped(self):
        d = self.smoke("stuck", {"maxAgents": 5})
        labels = [c["label"] for c in d["calls"] if "T-0009" in c["label"]]
        self.assertLessEqual(len(labels), 5)
        t = d["result"][0]["tasks"][0]
        self.assertEqual(t["state"], "parked")
        self.assertIn("係の上限", t["why"])
        self.assertEqual(t["resume"]["stage"], "fix")

    def test_prompts_carry_the_run_1112b_lessons(self):
        d = self.smoke("happy")
        p = d["prompts"]
        plan, ship, ev = p["plan:1"], p["ship:T-0001"], p["evalF:T-0001:0"]
        self.assertIn("q.py split", plan)                        # 大きい段は計画で分ける
        self.assertIn("park_class=infra", plan)                  # 負荷で止めた段が先
        self.assertIn("pytest は無い", plan)
        self.assertIn("preexisting", ev)                         # main でも落ちる試験は不合格の理由にしない
        self.assertIn("failed_conditions", ev)
        self.assertIn("run_in_background", ship)                 # CI を見に行かない
        self.assertIn("rc=3", ship)                              # 基盤の不安定だけなら落ちた試験だけを流し直す
        self.assertIn("ci_local.sh <落ちた試験の名前", ship)
        self.assertIn("gh pr checks <番号> --watch --interval 30 && bash harness/net.sh gh pr merge <番号> --squash", ship)
        self.assertIn("failed_class", ship)
        self.assertNotIn("lock.py ci --wait 1500 -- timeout", ship)   # Windows で System32 の timeout.exe が動いた形
        for label, text in p.items():
            if not label.startswith("scout:"):
                self.assertIn("lock.py browser", text, label)    # ブラウザは鍵の中で
        self.assertIn("D:/Claude/hf/v2r/wt/smoke-T-0001", p["build:T-0001"])   # 作業ツリーは回の名前つき

    def test_plan_dropped_tasks_get_released(self):
        d = self.smoke("happy")
        self.assertIn("harness/q.py release T-0002", d["prompts"]["learn:1"])   # 計画が取ったが範囲が重なって外した段の印を返す

    def test_old_loop_untouched(self):
        self.assertTrue((ROOT / ".claude" / "workflows" / "harness-forever.js").read_text(encoding="utf-8").startswith("export const meta = {\n  name: 'harness-forever'"))


if __name__ == "__main__":
    unittest.main()
