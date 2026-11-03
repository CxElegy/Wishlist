"""Supabase が 402 でも落ちない・静的に見える（2026-11-03）：Actions の書き込みは飛ばして続き、網页は 1 行の案内だけ。"""
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import digest  # noqa: E402
import render  # noqa: E402
import sbstate  # noqa: E402
import welcome  # noqa: E402


def _err(code):
    return urllib.error.HTTPError("https://x.supabase.co/rest/v1/news", code, "x", {}, io.BytesIO(b"{}"))


class ActionsSide(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()) / "s.json"
        self.p = [mock.patch.object(sbstate, "FILE", self.tmp), mock.patch.object(sbstate, "LIMITED", False), mock.patch.object(sbstate, "_OK", False),
                  mock.patch.object(digest, "load_config", return_value=({"supabase_url": "https://x.supabase.co"}, [])),
                  mock.patch.dict("os.environ", {"SUPABASE_SERVICE_KEY": "sb_secret_x"})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_402_skips_and_does_not_recall(self):
        with mock.patch("urllib.request.urlopen", side_effect=_err(402)) as m:
            self.assertIsNone(digest.supabase("news", [{"a": 1}]))
            self.assertIsNone(digest.supabase("stories", [{"a": 1}]))   # 2 回目は網に出ない
            self.assertEqual(m.call_count, 1)
        self.assertEqual(sbstate.load(self.tmp)["status"], "limited")

    def test_other_errors_still_raise(self):
        with mock.patch("urllib.request.urlopen", side_effect=_err(500)):
            with self.assertRaises(RuntimeError):
                digest.supabase("news")
        self.assertFalse(sbstate.LIMITED)

    def test_news_sync_mark_not_advanced(self):
        """書けなかった回は同期の印（db_news.json）が進まない＝次の回が送り直す。"""
        with mock.patch("urllib.request.urlopen", side_effect=_err(402)), mock.patch.object(digest, "save_json") as sv:
            digest.sync_news()
        sv.assert_not_called()

    def test_recovers_to_ok(self):
        sbstate.mark_limited("x", self.tmp)
        sbstate._OK = False
        sbstate.mark_ok(self.tmp)
        self.assertEqual(sbstate.load(self.tmp)["status"], "ok")


class PageSide(unittest.TestCase):
    def test_every_page_gets_the_degrade_script_first(self):
        tag = render._account_tag("index")
        self.assertIn("WL_SB", tag)
        self.assertLess(tag.index("WL_SB"), tag.find("wl-auth") if "wl-auth" in tag else len(tag))
        self.assertEqual(render._live_head("admin").count("window.WL_SB="), 1)

    def test_every_static_page_that_calls_supabase_has_it(self):
        """docs/ の html で Supabase を呼ぶものは全部、休止の部品を持つ（入口・本人のページの殻・見本の審査が抜けていた）。
        test2 は凍結（呼ばれても本番の account が違う・もう配らない）なので数えない。"""
        docs = pathlib.Path(render.__file__).resolve().parent.parent / "docs"
        miss = [str(f.relative_to(docs)) for f in docs.rglob("*.html") if "test2" not in f.parts
                and render.with_sb_deg(f.read_text(encoding="utf-8")) != f.read_text(encoding="utf-8")]
        self.assertEqual(miss, [])

    def test_outbox_keeps_rows_until_written(self):
        import tempfile
        p = pathlib.Path(tempfile.mkdtemp()) / "o.json"
        self.assertEqual(sbstate.outbox_take("live_log", p), [])
        self.assertFalse(p.exists())
        sbstate.outbox_put("live_log", [{"t": 1}], p)
        sbstate.outbox_put("live_log", [{"t": 2}], p)
        self.assertEqual([r["t"] for r in sbstate.outbox_take("live_log", p)], [1, 2])
        self.assertEqual(sbstate.outbox_take("live_log", p), [])

    def test_live_mark_does_not_resend_same(self):
        calls = []
        with mock.patch.object(digest, "supabase", lambda *a, **k: calls.append(a)), mock.patch.dict(digest._LIVE_SENT, clear=True):
            digest.live_mark("B", "fetch")
            digest.live_mark("B", "fetch")
            digest.live_mark("B", "found", found=2)
        self.assertEqual(len(calls), 2)

    def test_busy_polls_slower_when_idle(self):
        self.assertIn("live.length?30000:120000", render.BUSY_JS)

    def test_user_pages_skip_unchanged(self):
        import user_pages
        sent = []
        fp = {}

        def fake(path, data=None, method="GET", ctype=""):
            if path.endswith("_fp/all.json"):
                if method == "GET":
                    return dict(fp)
                fp.update(json.loads(data))
                return ""
            if "userfeed_users" in path:
                return [{"email": "a@example.com", "prefs": {}}]
            if "/storage/" in path:
                sent.append(path)
                return ""
            return []
        with mock.patch.object(user_pages, "_supa", fake), mock.patch.object(user_pages, "build", lambda *a, **k: "<html>x</html>"), \
                mock.patch.object(user_pages.digest, "load_config", lambda: ({}, [])), mock.patch.object(user_pages.render, "photo_opens", None, create=True):
            user_pages.main([])
            user_pages.main([])
            user_pages.main(["--force"])
        self.assertEqual(len(sent), 2)   # 1 回目と --force だけ

    def test_entrance_rebuilds_without_it(self):
        self.assertIn("render.SB_DEG_TAG in old", pathlib.Path(welcome.__file__).read_text(encoding="utf-8"))

    def test_entrance_has_it(self):
        self.assertIn("SB_DEG_TAG", pathlib.Path(welcome.__file__).read_text(encoding="utf-8"))

    def test_script_handles_402_and_does_not_recall(self):
        js = render.SB_DEG_JS
        for must in ("r.status===402", "status:503", "sessionStorage", "wl-sbnote"):
            self.assertIn(must, js)

    def test_admin_line(self):
        self.assertIn("制限中", render._sb_line({"status": "limited", "since": "2026-11-03T01:02:03Z"}))
        self.assertIn("正常", render._sb_line({"status": "ok", "at": "2026-11-03T01:02:03Z"}))
        self.assertIn('data-state="ok"', render._sb_line({}))



class SbDownCheckStable(unittest.TestCase):
    """harness/sb_down_check.py は固定の待ちでなく落ち着くまで待ち、呼ばないページも 1 回呼んで案内を確かめる（me.html の 1400 で ✗ が出たり出なかったりした）。"""

    def test_settles_and_probes(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "harness" / "sb_down_check.py").read_text(encoding="utf-8")
        self.assertIn("def settle(", src)
        self.assertNotIn("wait_for_timeout(3500)", src)
        self.assertIn("probe.supabase.co", src)
        # 呼ばないページの点検の呼び出しのあとも案内を確かめる（hits.clear() で条件が常に偽になっていた）
        self.assertIn("probed = True", src)
        self.assertIn("(hits or probed)", src)
        self.assertIn('probed and r["down"] != "down"', src)


if __name__ == "__main__":
    unittest.main()
