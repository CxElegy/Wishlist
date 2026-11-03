"""Supabase が 402 でも落ちない・静的に見える（2026-11-03）：Actions の書き込みは飛ばして続き、網页は 1 行の案内だけ。"""
import io
import json
import pathlib
import re
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

    def test_every_page_with_the_degrade_script_can_recover(self):
        """休止の部品を持つ docs/ の html は全部、今の版（recover あり）。古い版は 402 が終わっても戻らない（見本 6 枚が古いまま残った）。"""
        docs = pathlib.Path(render.__file__).resolve().parent.parent / "docs"
        old = [str(f.relative_to(docs)) for f in docs.rglob("*.html") if "test2" not in f.parts
               and "window.WL_SB=" in (s := f.read_text(encoding="utf-8")) and "function recover()" not in s]
        self.assertEqual(old, [])

    def test_stale_script_is_replaced_not_doubled(self):
        stale = "<html><head><script>window.WL_SB={};/*old*/</script></head><body></body></html>"
        out = render.with_sb_deg(stale)
        self.assertEqual(out.count("window.WL_SB="), 1)
        self.assertIn("function recover()", out)
        self.assertEqual(render.with_sb_deg(out), out)

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

    def test_script_recovers_when_limit_ends(self):
        """休止から 10 分後、触ったときに読むだけの呼び出し（GET・get_*・my_votes・live_boards）を 1 回試し、通れば案内を消して読み直す。
        書く呼び出し（my_vote_add など）は試しに使わない。"""
        js = render.SB_DEG_JS
        for must in ("function recover()", "function up()", "RETRY=600000", "location.reload()", "recover();"):
            self.assertIn(must, js)
        m = re.search(r"READ=/(.+?)/;", js.replace("\\/", "/"))
        self.assertTrue(m)
        rd = re.compile(m.group(1))
        for ok in ("/rest/v1/rpc/my_votes", "/rest/v1/rpc/live_boards", "/rest/v1/rpc/get_photo_inbox", "/rest/v1/rpc/my_votes_own"):
            self.assertTrue(rd.search(ok), ok)
        for ng in ("/rest/v1/rpc/my_vote_add", "/rest/v1/rpc/submit_item", "/rest/v1/rpc/run_now", "/rest/v1/rpc/my_keywords_set"):
            self.assertFalse(rd.search(ng), ng)

    def test_outbox_flushes_once_and_empties(self):
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp()) / "ob.json"
        sbstate.outbox_put("live_log", [{"a": 1}, {"a": 2}], d)
        self.assertEqual(sbstate.outbox_take("live_log", d), [{"a": 1}, {"a": 2}])
        self.assertEqual(sbstate.outbox_take("live_log", d), [])   # 二度目は空＝二重に書かない

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


class MemoAndNeedDb(unittest.TestCase):
    def tearDown(self):
        sbstate.LIMITED = False
        sbstate._MEMO.clear()

    def test_memo_reuses_only_in_actions(self):
        n = []
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_KEY": "k"}):
            for _ in range(3):
                sbstate.memo("t", 60, lambda: n.append(1) or 1)
        self.assertEqual(len(n), 1)
        with mock.patch.dict("os.environ", {}, clear=True):
            sbstate.memo("t2", 60, lambda: n.append(1))
            sbstate.memo("t2", 60, lambda: n.append(1))
        self.assertEqual(len(n), 3)

    def test_need_db_green_when_limited(self):
        sbstate.LIMITED = True
        with self.assertRaises(SystemExit) as c:
            sbstate.need_db("x")
        self.assertEqual(c.exception.code, 0)
        sbstate.LIMITED = False
        with self.assertRaises(SystemExit) as c:
            sbstate.need_db("x")
        self.assertEqual(c.exception.code, "x")


class LibraryGreenOn402(unittest.TestCase):
    """402 で DB が読めない（supabase() が None）ときの library 系の入口は、制限中なら緑（終了 0）で終える。"""

    def setUp(self):
        sbstate.LIMITED = True
        self.p = [mock.patch.object(digest, "supabase", return_value=None),
                  mock.patch.object(digest, "load_config", return_value=({"supabase_url": "https://x.supabase.co"}, [])),
                  mock.patch.dict("os.environ", {"SUPABASE_SERVICE_KEY": "k"})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        sbstate.LIMITED = False

    def test_entries_exit_green(self):
        import library
        import library_design
        import library_emblem
        item = {"name": "テスト", "section": "x"}
        with self.assertRaises(SystemExit) as c:
            library.push_shop([item])
        self.assertEqual(c.exception.code, 0)
        with self.assertRaises(SystemExit) as c:
            library_design.main([])
        self.assertEqual(c.exception.code, 0)
        library_emblem.main([])   # 例外なしで戻る（緑）


class SupabaseNoneExitsGoThroughNeedDb(unittest.TestCase):
    """新しい道具が古い書き方（supabase() が None → 素の SystemExit）を写すと 402 で赤になる。DB 読み出しの None の直後の SystemExit は need_db を通す。"""

    # 鍵・網址がない（402 でない）ことを見る終わり方。402 は LIMITED を見る側で扱う
    KEY_MISSING = {("library_emblem.py", 656), ("photo_store.py", 400), ("user_pages.py", 283)}

    def test_no_bare_exit_after_none_check(self):
        import re
        bad = []
        for f in sorted((ROOT / "scripts").glob("*.py")):
            lines = f.read_text(encoding="utf-8").splitlines()
            for i, ln in enumerate(lines):
                if "raise SystemExit(" not in ln or f.name == "sbstate.py":
                    continue
                head = "\n".join(lines[max(0, i - 3):i])
                if re.search(r"\bis None\b|if not (got|rows|users|r)\b", head) and "supabase" in "\n".join(lines[max(0, i - 8):i]):
                    if (f.name, i + 1) not in self.KEY_MISSING:
                        bad.append(f"{f.name}:{i + 1}")
        self.assertEqual(bad, [], "supabase() の None のあとは sbstate.need_db を通す")


class IdleTabs(unittest.TestCase):
    """放置したタブの Supabase 見回りは every() 1 本（2026-11-03）：生の setInterval で live_boards・my_boards・依頼を読み直さない。"""

    def test_pollers_use_every(self):
        src = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        self.assertIn("every:every", src)
        for call in ("WL_SB.every(read,", "WL_SB.every(function(){R._wlload", "WL_SB.every(loadLive,", "WL_SB.every(loadDb,"):
            self.assertEqual(src.count(call), 1, call)
        self.assertNotIn("clearInterval(R._wlub)", src)

    def test_no_raw_setinterval_toward_supabase_in_scripts(self):
        """scripts/ 全体（管理ページの livelog.py・overview.py も）：Supabase を読む見回りは every 経由。生の setInterval に残してよいのは
        GitHub／Pages／画面の描き直しだけ（下の許可表）。WL_SB を通る行（every が無いときの代わり）は数えない。"""
        import re
        ok = {"loadRuns", "loadLogs", "paint", "check", "maybe", "tick"}
        bad = []
        for f in sorted((ROOT / "scripts").glob("*.py")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if "setInterval(" not in line or "WL_SB" in line or "EV=" in line:
                    continue
                for m in re.finditer(r"setInterval\((.*?)(?:,\s*\w+\)|\);|$)", line):
                    names = set(re.findall(r"\b(load\w+|paint|check|maybe|tick)\b", m.group(1)))
                    if names - ok:
                        bad.append(f"{f.name}:{n} {sorted(names - ok)}")
        self.assertEqual(bad, [])

    def test_no_self_rescheduling_supabase_reader_in_static_js(self):
        """scripts/ の外の静的ファイル（docs/home/*.js、設定ページの additem.js など）：Supabase（rest/v1）を読む関数が
        setTimeout(自分, n) で自分を呼び直す、または setInterval で回すのは every を通さない見回り＝放置タブで止まらない。
        WL_SB を通る行（every が無いときの代わり）は数えない。"""
        import re
        bad = []
        for f in sorted((ROOT / "docs" / "home").glob("*.js")):
            src = f.read_text(encoding="utf-8")
            lines = src.splitlines()
            for n, line in enumerate(lines, 1):
                if "WL_SB" in line:
                    continue
                for m in re.finditer(r"setTimeout\((\w+),|setInterval\((\w+)", line):
                    name = m.group(1) or m.group(2)
                    d = re.search(r"function\s+" + name + r"\b", src)
                    if not d:
                        continue
                    body = src[d.start():d.start() + 2500]
                    if "rest/v1" in body or ".rpc(" in body:
                        bad.append(f"{f.name}:{n} {name}")
        self.assertEqual(bad, [])

    def test_additem_load_queue_uses_every(self):
        src = (ROOT / "docs" / "home" / "additem.js").read_text(encoding="utf-8")
        self.assertEqual(src.count("WL_SB.every(() => { if (qNeed) loadQueue(); }"), 1)

    def test_admin_pollers_use_every(self):
        for fn, calls in (("livelog.py", ("EV(loadLines,3000)", "EV(loadBoards,20000)", "EV(loadCtl,20000)")), ("overview.py", ("EV(loadBoards,30000)",))):
            src = (ROOT / "scripts" / fn).read_text(encoding="utf-8")
            for c in calls:
                self.assertEqual(src.count(c), 1, c)
