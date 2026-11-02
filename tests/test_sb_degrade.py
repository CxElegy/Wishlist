"""Supabase が 402 でも落ちない・静的に見える（2026-11-03）：Actions の書き込みは飛ばして続き、網页は 1 行の案内だけ。"""
import io
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


if __name__ == "__main__":
    unittest.main()
