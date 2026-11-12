"""AI 編集を「記録を先に push してから」起こす（scripts/gate_fire.py）：後台作業と収集が同時に始まっても 2 本目は起きない。
本物の git（bare の origin に 2 つの clone）と偽の時計・偽の POST。本番の API・Actions は呼ばない。"""
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gate  # noqa: E402
import gate_fire  # noqa: E402
import runlog  # noqa: E402

NOW = dt.datetime(2026, 11, 12, 6, 0, tzinfo=dt.timezone.utc)   # 北京 14:00
ENV = {"ROUTINE_TOKEN_EDIT": "t", "GATE_FIRE": "edit", "EDIT_MODE": "run"}


def sh(cwd, *a):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return r.stdout


def fake_check():
    """gate.check の代わり：edit に溜まった版面がある、という判断を（最新の fired は残して）書く。"""
    data = gate.load()
    prev = (data.get("jobs") or {}).get("edit") or {}
    data["jobs"] = {"edit": {**prev, "need": True, "claude": True, "items": ["A"], "sig": "s", "prog": 0, "prog_day": "2026-11-12",
                             "ripe": ["A"], "tokens_today": 0, "token_cap": 1000}}
    gate.save(data)


class Fire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = pathlib.Path(self.tmp.name)
        sh(d, "init", "-q", "--bare", "-b", "main", "origin.git")
        seed = d / "seed"
        sh(d, "clone", "-q", "origin.git", "seed")
        (seed / "state" / "log").mkdir(parents=True)
        (seed / "state" / "gate.json").write_text("{}\n", "utf-8")
        (seed / "state" / "log" / "gate.json").write_text("[]\n", "utf-8")
        sh(seed, "add", "-A")
        sh(seed, "commit", "-q", "-m", "init")
        sh(seed, "push", "-q", "origin", "HEAD:main")
        for n in ("bg", "digest"):
            sh(d, "clone", "-q", "origin.git", n)
        self.d = d
        for p in (mock.patch.object(gate, "_now", lambda: NOW), mock.patch.dict(os.environ, {"GATE_FIRE_RESET": "1"})):
            p.start()
            self.addCleanup(p.stop)

    def run_in(self, name, post, **kw):
        repo = self.d / name
        with mock.patch.object(gate, "STATE", repo / "state" / "gate.json"), mock.patch.object(runlog, "LOG_DIR", repo / "state" / "log"):
            return gate_fire.run(repo, env=ENV, post=post, check=fake_check, sleep=lambda s: None, **kw)

    def origin_state(self):
        return json.loads(sh(self.d / "seed", "show", "origin/main:state/gate.json") if sh(self.d / "seed", "fetch", "-q") is not None else "{}")

    def test_second_runner_does_not_fire(self):
        """収集が先に起こして push 済み。手元に古い記録しかない後台作業は、最新を取り込んで 2 本目を起こさない。"""
        posts = []
        r1 = self.run_in("digest", lambda u, t: posts.append("digest") or 200)
        self.assertEqual(r1["edit"], "Claude を起こした")
        r2 = self.run_in("bg", lambda u, t: posts.append("bg") or 200)
        self.assertEqual(posts, ["digest"])
        self.assertIn("60 分以内", r2["edit"])

    def test_push_race_loses_and_does_not_fire(self):
        """後台作業が記録を push する直前に収集が先に push した。後台作業の push は負け、判断し直して起こさない。"""
        posts = []

        def digest_wins():
            digest_wins.done = True
            self.run_in("digest", lambda u, t: posts.append("digest") or 200)
        digest_wins.done = False
        res = self.run_in("bg", lambda u, t: posts.append("bg") or 200, before_push=lambda: None if digest_wins.done else digest_wins())
        self.assertEqual(posts, ["digest"])
        self.assertIn("60 分以内", res["edit"])

    def test_record_is_on_origin_before_the_post(self):
        """起こす（POST）の時点で、起こした記録はもう main にある（AI が最新の main を読む・ほかの回にも見える）。"""
        seen = []

        def post(u, t):
            sh(self.d / "seed", "fetch", "-q", "origin")
            seen.append(json.loads(sh(self.d / "seed", "show", "origin/main:state/gate.json"))["jobs"]["edit"]["fired"]["at"])
            return 200
        self.run_in("bg", post)
        self.assertEqual(len(seen), 1)

    def test_failed_post_releases_the_claim(self):
        """POST が失敗したら記録を取り消す（次の回が起こし直せる）。"""
        def boom(u, t):
            raise OSError("down")
        res = self.run_in("bg", boom)
        self.assertIn("起こせなかった", res["edit"])
        posts = []
        r2 = self.run_in("digest", lambda u, t: posts.append(1) or 200)
        self.assertEqual(r2["edit"], "Claude を起こした")
        self.assertEqual(posts, [1])

    def test_nothing_to_do_pushes_nothing(self):
        head = sh(self.d / "bg", "rev-parse", "origin/main")
        with mock.patch.object(gate_fire.gate, "fire", lambda **k: {"edit": "整理待ちはまだ溜まっていない"}):
            self.run_in("bg", lambda u, t: self.fail("起こさない"))
        sh(self.d / "bg", "fetch", "-q")
        self.assertEqual(sh(self.d / "bg", "rev-parse", "origin/main"), head)

    def test_refuses_outside_actions(self):
        with mock.patch.dict(os.environ, {"GATE_FIRE_RESET": "", "GITHUB_ACTIONS": ""}):
            with self.assertRaises(SystemExit):
                gate_fire.sync(self.d / "bg")


class Workflow(unittest.TestCase):
    def test_background_fires_after_push(self):
        """T-0005：起こす段は「提交」（push）のあと。gate.py fire を直接 POST に使う段はない。"""
        t = (ROOT / ".github" / "workflows" / "background.yml").read_text(encoding="utf-8")
        self.assertLess(t.index("id: commit"), t.index("scripts/gate_fire.py"))
        self.assertNotIn("scripts/gate.py fire", t)

    def test_digest_uses_gate_fire(self):
        t = (ROOT / ".github" / "workflows" / "digest.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/gate_fire.py", t)
        self.assertNotIn("scripts/gate.py fire", t)


if __name__ == "__main__":
    unittest.main()
