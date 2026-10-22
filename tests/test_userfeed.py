"""お客さまの分の記事集め（scripts/userfeed.py、db/user_boards.sql）。ネットにも Supabase にも出ない（collect・supabase を差し替える）。

    python -m unittest tests.test_userfeed
"""

import datetime as dt
import hashlib
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402
import userfeed  # noqa: E402

NOW = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)


class FakeDB:
    """digest.supabase と同じ形：(path, body=None, prefer=None, method=None)。"""

    def __init__(self, users, rows=()):
        self.users, self.rows, self.calls = users, list(rows), []

    def __call__(self, path, body=None, prefer=None, method=None):
        self.calls.append((path, body, prefer, method))
        if path.startswith("app_users?"):
            return self.users
        if path.startswith("user_boards?select="):
            return self.rows
        return []

    def written(self):
        return [r for p, b, _, m in self.calls if p.startswith("user_boards?on_conflict") for r in b]

    def deleted(self):
        return [p for p, _, _, m in self.calls if m == "DELETE"]


def story(n, title, days=0):
    return {"title": title, "url": f"https://news.example.jp/{n}", "source": "例", "summary": "",
            "image": "", "date": (NOW - dt.timedelta(days=days)).isoformat()}


class Rules(unittest.TestCase):
    def test_account_same_as_sql(self):
        # db/user_boards.sql の private.user_account：'u_' || left(md5(lower(btrim(email))), 16)
        self.assertEqual(userfeed.account_of(" Test-A@Example.com"),
                         "u_" + hashlib.md5(b"test-a@example.com").hexdigest()[:16])
        sql = (ROOT / "db" / "user_boards.sql").read_text(encoding="utf-8")
        self.assertIn("'u_' || left(md5(lower(btrim(coalesce(p_email, '')))), 16)", sql)
        self.assertIn("auth.jwt()", sql)                        # 本人の行だけ
        self.assertIn("revoke all on public.user_boards from anon, authenticated", sql)

    def test_loose_hit_like_auth_js(self):
        self.assertTrue(userfeed.loose_hit("ちいかわ", "ちいかわ"))
        self.assertTrue(userfeed.loose_hit("ちいかわ", "ちいかわ グッズ"))
        self.assertTrue(userfeed.loose_hit("GTA 6", "gta6"))
        self.assertFalse(userfeed.loose_hit("ちいかわ", "広島旅行"))
        self.assertFalse(userfeed.loose_hit("猫用品", "犬"))   # 1 字は含まれても当たりにしない

    def test_langs(self):
        self.assertEqual(userfeed.news_langs({"lang": {"primary": "ko", "also": ["en", "fr", "ja"]}}), ["ko-KR", "en-US"])
        self.assertEqual(userfeed.news_langs({"lang": {"primary": "fr"}}), ["ja-JP"])   # 集めていない言語だけ → 日本語
        self.assertEqual(userfeed.news_langs({}), ["ja-JP"])

    def test_board_item(self):
        it = userfeed.board_item("広島 旅行", "出行", ["ja-JP"])
        self.assertEqual(it["section"], "出行")
        self.assertNotIn("reddit", it["use"])
        self.assertFalse(it["gdelt"])
        e = sources.Entry(title="秋の広島で 1 泊 2 日の旅行プラン", url="https://a.example/1", published=NOW, source="例")
        self.assertIsNotNone(digest.match_hit(it, e))   # 語が離れていても全部あれば
        self.assertNotIn("section", userfeed.board_item("x", "存在しない", ["ja-JP"]))


class Plan(unittest.TestCase):
    def users(self):
        return [{"email": "test-b@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "ちいかわ", "sec": "影视"}, {"name": "広島旅行", "sec": "出行"}]}},
                {"email": "test-c@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "広島旅行", "sec": "出行"}, {"name": "", "sec": "x"}]}},
                {"email": None, "prefs": {"picks": [{"name": "だれか"}]}}]

    def test_only_not_in_shop_and_grouped(self):
        todo, keep = userfeed.plan(self.users(), ["ちいかわ"], [], NOW)
        self.assertEqual([g["name"] for g in todo], ["広島旅行"])   # 店長の版面にあるものは集めない
        self.assertEqual(len(todo[0]["boards"]), 2)                  # 2 人が同じものなら 1 回で
        self.assertEqual(keep[userfeed.account_of("test-b@example.com")], {"広島旅行"})

    def test_recent_skipped_and_cap(self):
        acct = userfeed.account_of("test-b@example.com")
        rows = [{"account": acct, "item": "広島旅行", "checked_at": (NOW - dt.timedelta(minutes=30)).isoformat()}]
        users = self.users()[:1]
        todo, _ = userfeed.plan(users, [], rows, NOW)
        self.assertEqual([g["name"] for g in todo], ["ちいかわ"])   # 30 分前に探したものは飛ばす
        many = [{"email": "a@example.com", "prefs": {"picks": [{"name": f"もの{i}", "sec": "其他"} for i in range(30)]}}]
        todo, keep = userfeed.plan(many, [], [], NOW)
        self.assertEqual(len(todo), userfeed.MAX_BOARDS_PER_USER)


class Merge(unittest.TestCase):
    def test_merge(self):
        old = [story(1, "古い記事", 3), story(2, "とても古い", 20)]
        new = [story(1, "古い記事", 3), story(3, "新しい記事"), {"title": "", "url": "x"}]
        out, n = userfeed.merge(old, new, NOW)
        self.assertEqual([s["title"] for s in out], ["新しい記事", "古い記事"])   # 14 日より古いもの・壊れたものは落とす
        self.assertEqual(n, 1)

    def test_cap(self):
        out, n = userfeed.merge([], [story(i, f"記事その{i}", i * 0.1) for i in range(30)], NOW)
        self.assertEqual(len(out), userfeed.MAX_STORIES)


class Collect(unittest.TestCase):
    def test_same_filters_as_shop(self):
        it = userfeed.board_item("広島旅行", "出行", ["ja-JP"])
        raw = [sources.Entry(title="広島旅行で行きたい紅葉の名所", url="https://a.example/1", published=NOW, source="旅の例",
                             summary="<b>秋</b>の広島", image="https://a.example/1.jpg"),
               sources.Entry(title="広島旅行 在线看 高清完整", url="https://b.example/2", published=NOW, source="spam"),
               sources.Entry(title="東京のカフェ特集", url="https://c.example/3", published=NOW, source="例"),
               sources.Entry(title="広島旅行の動画", url="https://youtube.com/x", published=NOW, source="YouTube")]
        with mock.patch.object(digest, "collect", return_value=raw):
            out = userfeed.stories_for(it, {"exclude_sources": ["YouTube"]})
        self.assertEqual([s["title"] for s in out], ["広島旅行で行きたい紅葉の名所"])   # 垃圾・match・exclude_sources
        self.assertEqual(out[0]["summary"], "秋 の広島")
        self.assertEqual(out[0]["image"], "https://a.example/1.jpg")


class NoGdelt(unittest.TestCase):
    def test_collect_skips_gdelt(self):
        it = userfeed.board_item("広島旅行", "出行", ["ja-JP"])
        with mock.patch.object(sources, "google_news", return_value=[]), mock.patch.object(sources, "bing_news", return_value=[]), \
                mock.patch.object(sources, "gdelt", side_effect=AssertionError("GDELT は店長の収集だけ")), \
                mock.patch.object(digest.intel, "entries_for", return_value=[]):
            self.assertEqual(digest.collect(it, {}), [])


class Run(unittest.TestCase):
    def run_with(self, db, collect):
        with mock.patch.object(digest, "load_config", return_value=({}, [{"name": "ちいかわ"}])):
            return userfeed.run(db=db, collect=collect, now=NOW, log=lambda *_: None)

    def test_writes_rows_per_account_and_deletes_stale(self):
        b, c = userfeed.account_of("test-b@example.com"), userfeed.account_of("test-c@example.com")
        users = [{"email": "test-b@example.com", "prefs": {"picks": [{"name": "広島旅行", "sec": "出行"}]}},
                 {"email": "test-c@example.com", "prefs": {"picks": [{"name": "広島旅行", "sec": "出行"}]}}]
        rows = [{"account": b, "item": "外したもの", "stories": [], "checked_at": None},
                {"account": c, "item": "ちいかわ", "stories": [], "checked_at": None}]   # 店長の版面と同じもの
        db = FakeDB(users, rows)
        calls = []
        res = self.run_with(db, lambda item, settings: calls.append(item["name"]) or [story(1, "広島旅行の記事")])
        self.assertEqual(calls, ["広島旅行"])   # 同じものは 1 回だけ集める
        got = {(r["account"], r["item"]): r for r in db.written()}
        self.assertEqual(set(got), {(b, "広島旅行"), (c, "広島旅行")})
        self.assertEqual(got[(b, "広島旅行")]["found"], 1)
        self.assertEqual(got[(b, "広島旅行")]["updated_at"], NOW.isoformat(timespec="seconds"))
        self.assertEqual(len(db.deleted()), 2)
        self.assertEqual(res["found"], 2)
        for p, _, prefer, m in db.calls:   # account は本人のもの（店長の test1 には書かない）
            self.assertNotIn("account=eq.test1", p)

    def test_failure_does_not_stop(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "だめなもの"}, {"name": "よいもの"}]}}]
        db = FakeDB(users)

        def collect(item, settings):
            if item["name"] == "だめなもの":
                raise RuntimeError("boom")
            return [story(1, "よいものの記事")]
        res = self.run_with(db, collect)
        self.assertEqual(res["failed"], 1)
        got = {r["item"]: r for r in db.written()}
        self.assertEqual(got["よいもの"]["found"], 1)
        self.assertEqual(got["だめなもの"]["stories"], [])   # 探した印は付ける（「まだ見つかっていません」が出せる）

    def test_no_key(self):
        res = self.run_with(lambda *a, **k: None, lambda *a: [])
        self.assertEqual(res["boards"], 0)


class Wiring(unittest.TestCase):
    def test_workflow_and_arch(self):
        wf = (ROOT / ".github" / "workflows" / "digest.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/userfeed.py", wf)
        import processes
        self.assertIn("userfeed", processes.COMPONENTS)
        flow = next(p for p in processes.PROCESSES if p["id"] == "collect")
        self.assertIn("userfeed", flow["uses"])


if __name__ == "__main__":
    unittest.main()
