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
        self.assertEqual(q.counts(t, self.state, T0), {"open": 0, "done": 1, "parked": 1, "waiting": 1, "claimed": 0})

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
        self.assertEqual(s["queue"], {"open": 2, "done": 0, "parked": 0, "waiting": 1, "claimed": 1})
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
        self.assertEqual(ships, ["ship:intake1", "ship:T-0001", "ship:T-0003", "ship:T-0004"])   # 合併は 1 つずつ・受付の枝が先
        self.assertLess(labels.index("ship:T-0003"), labels.index("verify:1:b"))
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

    def test_old_loop_untouched(self):
        self.assertTrue((ROOT / ".claude" / "workflows" / "harness-forever.js").read_text(encoding="utf-8").startswith("export const meta = {\n  name: 'harness-forever'"))


if __name__ == "__main__":
    unittest.main()
