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
    """digest.supabase と同じ形：(path, body=None, prefer=None, method=None)。PostgREST と同じく 1 回 page 行まで返す。"""

    def __init__(self, users, rows=(), page=1000, fail=None):
        self.users, self.rows, self.calls, self.page, self.fail = users, list(rows), [], page, fail

    def _slice(self, data, offset, limit):
        return data[offset:offset + min(limit, self.page)]

    def __call__(self, path, body=None, prefer=None, method=None):
        if self.fail and self.fail(path, body, method):
            raise RuntimeError("HTTP 400：boom")
        self.calls.append((path, body, prefer, method))   # 通った呼び出しだけ
        if path.startswith("rpc/userfeed_users"):
            return self._slice(self.users, body.get("p_offset", 0), body.get("p_limit", 1000))
        if path.startswith("user_boards?select="):
            q = dict(x.split("=", 1) for x in path.split("?", 1)[1].split("&"))
            return self._slice(self.rows, int(q.get("offset", 0)), int(q.get("limit", 1000)))
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

    def test_shop_hit_like_auth_js(self):
        self.assertTrue(userfeed.shop_hit("ちいかわ", "ちいかわ"))
        self.assertTrue(userfeed.shop_hit("ちいかわ", "ちいかわ グッズ"))
        self.assertTrue(userfeed.shop_hit("GTA 6", "gta6"))
        self.assertTrue(userfeed.shop_hit("ILLIT", "ILLIT ライブ"))
        self.assertFalse(userfeed.shop_hit("ちいかわ", "広島旅行"))
        self.assertFalse(userfeed.shop_hit("猫用品", "犬"))          # 1 字は含まれても当たりにしない
        self.assertFalse(userfeed.shop_hit("FROM", "From Software"))  # 英数字は語の途中で当てない
        js = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        self.assertIn("function shopHit(a,b)", js)                   # 網页も同じ規則（userfeed.shop_hit）

    def test_shop_boards_from_page(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "index.html"
            f.write_text('<section class="front" data-k="front" id="front"></section>'
                         '<section data-h="1" id="w-1" data-k="ちいかわ" data-fx="x" class="sec m-a">'
                         '<section data-k="A &amp; B" class="sec">', encoding="utf-8")
            self.assertEqual(userfeed.shop_boards(f), ["ちいかわ", "A & B"])
            self.assertIsNone(userfeed.shop_boards(pathlib.Path(d) / "nothing.html"))

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

    def hits(self, name, sec, title, summary=""):
        it = userfeed.board_item(name, sec, ["en-US"])
        return digest.match_hit(it, sources.Entry(title=title, url="https://a.example/1", published=NOW, source="例", summary=summary)) is not None

    def test_english_names_from_cards(self):
        # 入口のカード（Steam の英語名）：普通の語は板块の語と一緒のときだけ・記号のゆれは許す
        self.assertFalse(self.hits("The Wrong Way", "游戏", "Why the economy is heading the wrong way"))
        self.assertTrue(self.hits("The Wrong Way", "游戏", "The Wrong Way is a creepy new Steam game"))
        self.assertFalse(self.hits("MEAT TRAIN", "游戏", "Meat prices hit the train industry"))
        self.assertTrue(self.hits("Call of Duty®: Modern Warfare® 4", "游戏", "Call of Duty: Modern Warfare 4 reveal trailer"))
        self.assertTrue(self.hits("Street Fighter 6", "游戏", "Street Fighter 6 adds a new fighter"))
        self.assertFalse(self.hits("Street Fighter 6", "游戏", "Street Fighter 60th anniversary"))
        self.assertTrue(self.hits("DON'T SWITCH", "游戏", "Don’t Switch gets a Steam release date"))
        self.assertEqual(userfeed.board_item("Call of Duty®: Modern Warfare® 4", "游戏", ["en-US"])["keywords"][0], "Call of Duty: Modern Warfare 4")

    def test_season_suffix_and_digits(self):
        it = userfeed.board_item("薬屋のひとりごと 第2期", "影视", ["ja-JP"])
        self.assertIn("薬屋のひとりごと", it["keywords"])
        self.assertTrue(self.hits("薬屋のひとりごと 第2期", "影视", "「薬屋のひとりごと」新作映画が決定"))
        self.assertFalse(self.hits("ストリートファイター 6", "游戏", "6 月の新作ゲーム一覧"))   # 数字だけでは当てない
        self.assertTrue(self.hits("ストリートファイター 6", "游戏", "ストリートファイター6 に新キャラ"))

    def test_clean_text(self):
        e = sources.Entry(title="A &amp; B\x00 の新作 - 例のニュース", url="https://news.google.com/x", link="https://a.example/1",
                          published=NOW, source="例のニュース", summary="<p>夏&nbsp;の&lt;予定&gt;</p>")
        s = userfeed.story_of(e)
        self.assertEqual(s["title"], "A & B の新作")       # 実体を戻す・制御文字を消す・末尾の媒体名を取る
        self.assertEqual(s["summary"], "夏 の<予定>")       # 網页は esc で描く（ここでは文字に戻すだけ）
        self.assertEqual(s["url"], "https://a.example/1")   # 原文の網址を先に

    def test_kanji_only_japanese_kept(self):
        self.assertEqual(userfeed.lang_order(["ja-JP"]), ["ja", "zh"])
        self.assertEqual(userfeed.lang_order(["en-US"]), ["en"])


class Plan(unittest.TestCase):
    def users(self):
        return [{"email": "test-b@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "ちいかわ", "sec": "影视"}, {"name": "広島旅行", "sec": "出行"}]}},
                {"email": "test-c@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "広島旅行", "sec": "生活"}, {"name": "", "sec": "x"}]}},
                {"email": None, "prefs": {"picks": [{"name": "だれか"}]}}]

    def test_only_not_in_shop_and_grouped(self):
        todo, keep, limits = userfeed.plan(self.users(), ["ちいかわ"], [], NOW)
        self.assertEqual([g["name"] for g in todo], ["広島旅行"])   # 店長の版面にあるものは集めない
        self.assertEqual(len(todo[0]["boards"]), 2)                  # 2 人が同じものなら 1 回で
        self.assertEqual({b[2] for b in todo[0]["boards"]}, {"出行", "生活"})   # 板块は人ごと（1 人目のもので上書きしない）
        self.assertEqual(keep[userfeed.account_of("test-b@example.com")], {"広島旅行"})
        self.assertEqual(limits, [])

    def test_trim_and_duplicates(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "  広島旅行 ", "sec": "出行"}, {"name": "広島 旅行", "sec": "出行"},
                                                                {"name": "あ" * 90, "sec": "其他"}]}}]
        todo, keep, _ = userfeed.plan(users, [], [], NOW)
        self.assertEqual(keep[userfeed.account_of("a@example.com")], {"広島旅行", "あ" * 80})   # SQL の my_boards と同じ：trim・80 字・同じ名前は 1 つ
        sql = (ROOT / "db" / "user_boards.sql").read_text(encoding="utf-8")
        self.assertIn("left(btrim(x.value ->> 'name'), 80)", sql)
        self.assertIn("distinct on (lower(regexp_replace(r.name, '\\s', '', 'g')))", sql)

    def test_recent_skipped(self):
        acct = userfeed.account_of("test-b@example.com")
        rows = [{"account": acct, "item": "広島旅行", "checked_at": (NOW - dt.timedelta(minutes=30)).isoformat()}]
        todo, _, _ = userfeed.plan(self.users()[:1], [], rows, NOW)
        self.assertEqual([g["name"] for g in todo], ["ちいかわ"])   # 30 分前に探したものは飛ばす

    def test_cap_marks_limit_and_new_first(self):
        many = [{"email": "a@example.com", "prefs": {"picks": [{"name": f"もの{i}", "sec": "其他"} for i in range(35)]}}]
        todo, keep, limits = userfeed.plan(many, [], [], NOW)
        acct = userfeed.account_of("a@example.com")
        self.assertEqual(len(keep[acct]), 35)                                    # 上限を超えた分も消さない
        self.assertEqual([x[1] for x in limits], [f"もの{i}" for i in range(30, 35)])   # 超えた分は limit の行（「集めています」のままにしない）
        self.assertEqual(len(todo), userfeed.PER_USER_PER_RUN)
        self.assertEqual(todo[0]["name"], "もの29")                              # まだ探していないものは新しく足したものから
        rows = [{"account": acct, "item": f"もの{i}", "checked_at": (NOW - dt.timedelta(hours=10 - i)).isoformat(), "state": "ok"} for i in range(5)]
        rows += [{"account": acct, "item": f"もの{i}", "checked_at": NOW.isoformat(), "state": "limit"} for i in range(30, 35)]
        todo, _, limits = userfeed.plan(many, [], rows, NOW)
        self.assertEqual(limits, [])                                             # 書いてあれば書き直さない
        self.assertEqual(todo[0]["name"], "もの29")

    def test_fair_between_users(self):
        users = [{"email": f"u{n}@example.com", "prefs": {"picks": [{"name": f"{n}の{i}", "sec": "其他"} for i in range(30)]}} for n in range(30)]
        rows = [{"account": userfeed.account_of(f"u{n}@example.com"), "item": f"{n}の0", "checked_at": "2026-10-01T00:00:00+00:00"} for n in range(30)]
        todo, _, _ = userfeed.plan(users, [], rows, NOW)
        self.assertEqual(len(todo), userfeed.MAX_BOARDS_PER_RUN)
        firsts = todo[:30]
        self.assertEqual(len({g["boards"][0][0] for g in firsts}), 30)   # 全員の 1 つ目が先（1 人で全部を使わない）

    def test_new_users_capped(self):
        users = [{"email": f"spam{n}@example.com", "prefs": {"picks": [{"name": f"s{n}", "sec": "其他"}]}} for n in range(50)]
        todo, _, _ = userfeed.plan(users, [], [], NOW)
        self.assertEqual(len(todo), userfeed.MAX_NEW_USERS_PER_RUN)   # まだ集めていない人は 1 回 15 人まで（登録の古い順）
        self.assertEqual(todo[0]["name"], "s0")


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

    def test_original_url_wins_and_undated_ages(self):
        g = {"title": "広島で紅葉まつり", "url": "https://news.google.com/rss/articles/x", "source": "例", "date": NOW.isoformat()}
        o = {"title": "広島で紅葉まつり", "url": "https://a.example/1", "source": "例", "date": NOW.isoformat()}
        out, n = userfeed.merge([g], [o], NOW)
        self.assertEqual([s["url"] for s in out], ["https://a.example/1"])   # 跳转より原文
        self.assertEqual(n, 0)
        out, _ = userfeed.merge([], [{"title": "日付のない記事", "url": "https://a.example/2"}], NOW)
        self.assertEqual(out[0]["seen"], NOW.isoformat(timespec="seconds"))   # 見つけた日を付ける
        out, _ = userfeed.merge(out, [], NOW + dt.timedelta(days=userfeed.KEEP_DAYS + 1))
        self.assertEqual(out, [])                                             # 日付がなくても 14 日で落ちる


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
    def run_with(self, db, collect, logs=None):
        with mock.patch.object(digest, "load_config", return_value=({}, [{"name": "ちいかわ"}])):
            return userfeed.run(db=db, collect=collect, now=NOW, log=(logs.append if logs is not None else lambda *_: None), shop=["ちいかわ"])

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
        self.assertEqual(got[(b, "広島旅行")]["state"], "ok")
        self.assertEqual(got[(b, "広島旅行")]["updated_at"], NOW.isoformat(timespec="seconds"))
        self.assertEqual(len(db.deleted()), 2)
        self.assertEqual(res["found"], 2)
        for p, _, prefer, m in db.calls:   # account は本人のもの（店長の test1 には書かない）
            self.assertNotIn("account=eq.test1", p)

    def test_failure_does_not_stop_or_mark(self):
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
        self.assertNotIn("だめなもの", got)   # 失敗は探した印を付けない（「まだ見つかっていません」と出さない・次の回にもう一度）

    def test_paging_reads_everyone(self):
        users = [{"email": f"u{n}@example.com", "prefs": {"picks": [{"name": f"もの{n}", "sec": "其他"}]}} for n in range(7)]
        rows = [{"account": userfeed.account_of(f"u{n}@example.com"), "item": f"もの{n}", "stories": [],
                 "checked_at": NOW.isoformat(), "state": "ok"} for n in range(7)]
        db = FakeDB(users, rows, page=3)   # 1 回 3 行しか返さない Supabase
        with mock.patch.object(userfeed, "PAGE", 3):
            self.run_with(db, lambda item, settings: [])
        self.assertEqual(db.deleted(), [])   # 4 人目からの行を消さない
        self.assertEqual(len([c for c in db.calls if c[0].startswith("rpc/userfeed_users")]), 3)

    def test_incomplete_list_keeps_rows(self):
        users = [{"email": f"u{n}@example.com", "prefs": {"picks": [{"name": f"もの{n}", "sec": "其他"}]}} for n in range(4)]
        rows = [{"account": userfeed.account_of(f"u{n}@example.com"), "item": f"もの{n}", "stories": [],
                 "checked_at": NOW.isoformat(), "state": "ok"} for n in range(4)]
        db = FakeDB(users, rows, page=2, fail=lambda p, b, m: p.startswith("rpc/") and b.get("p_offset") == 2)
        logs = []
        with mock.patch.object(userfeed, "PAGE", 2):
            self.run_with(db, lambda item, settings: [], logs)
        self.assertEqual(db.deleted(), [])   # 一覧の 2 ページ目が読めなかった：だれの行も消さない
        self.assertTrue(any("消さない" in x for x in logs))

    def test_bad_batch_retries_rows(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "よいもの"}, {"name": "わるいもの"}]}}]
        db = FakeDB(users, fail=lambda p, b, m: p.startswith("user_boards?on_conflict") and any(r["item"] == "わるいもの" for r in b))
        res = self.run_with(db, lambda item, settings: [story(1, item["name"] + "の記事")])
        self.assertEqual(res["bad"], 1)
        self.assertEqual([r["item"] for r in db.written() if r["item"] == "よいもの"], ["よいもの"])   # 1 行ずつ書き直して残りは書く

    def test_control_chars_removed(self):
        row = userfeed._clean_row({"stories": [{"title": "a\x00b"}], "item": "x\x07"})
        self.assertEqual(row, {"stories": [{"title": "ab"}], "item": "x"})

    def test_late_not_marked(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "おそいもの"}, {"name": "はやいもの"}]}}]
        db = FakeDB(users)
        with mock.patch.object(digest, "run_parallel", return_value=({}, [("おそいもの", ("ja-JP",))])):
            res = self.run_with(db, lambda item, settings: [])
        self.assertEqual(res["late"], 1)
        self.assertNotIn("おそいもの", [r["item"] for r in db.written()])   # 時間切れは探した印を付けない

    def test_budget_from_job_start(self):
        import time
        with mock.patch.dict("os.environ", {"JOB_T0": str(int(time.time()) - 36 * 60)}):
            self.assertLess(userfeed.budget_sec(), 60 + 1)   # 40 分の job の 36 分目：残りは 1 分
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "もの"}]}}]
        db = FakeDB(users)
        with mock.patch.dict("os.environ", {"JOB_T0": str(int(time.time()) - 39 * 60)}):
            res = self.run_with(db, lambda item, settings: self.fail("時間がないのに集めた"))
        self.assertEqual(res["late"], 1)
        self.assertEqual(db.written(), [])

    def test_no_key(self):
        res = self.run_with(lambda *a, **k: None, lambda *a: [])
        self.assertEqual(res["boards"], 0)


class Sql(unittest.TestCase):
    def test_my_boards_states_and_guards(self):
        sql = (ROOT / "db" / "user_boards.sql").read_text(encoding="utf-8")
        for w in ("'wait'", "'none'", "'limit'", "coalesce(p.sec, b.sec)", "last_sign_in_at is not null",
                  "grant execute on function public.userfeed_users(int, int) to service_role",
                  "revoke all on function public.userfeed_users(int, int) from public, anon, authenticated",
                  "v := v - 'picks'"):
            self.assertIn(w, sql)
        self.assertNotIn("userfeed_users(int, int) to anon", sql)

    def test_page_reads_my_boards(self):
        import render
        for w in ("rpc('my_boards')", "今日の主なニュース", "気になるかも？", "まだ記事が見つかっていません", "30 個まで", "wl-cards"):
            self.assertIn(w, render.AUTH_JS)
        self.assertIn("/^https?:\\/\\//.test(u)", render.AUTH_JS)   # 網址は http(s) だけ


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
