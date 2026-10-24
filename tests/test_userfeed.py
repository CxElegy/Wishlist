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

    def test_context_words_need_word_edges(self):
        # ジャンルの語は語の途中で当てない（upcoming の PC・opened の open・switching の Switch）・普通の語は入れない
        for title in ("Markets head the wrong way as upcoming rate decision looms",
                      "Shop opened the wrong way, says owner", "Switching the wrong way: an update on the patch to city law",
                      "The wrong way to play the match this season"):
            self.assertFalse(self.hits("The Wrong Way", "游戏", title), title)
        self.assertTrue(self.hits("The Wrong Way", "游戏", "The Wrong Way: new PlayStation trailer"))
        self.assertTrue(self.hits("The Wrong Way", "游戏", "「The Wrong Way」の体験版が配信"))
        self.assertFalse(self.hits("Meat Train", "出行", "Meat train derails, hotelier says"))   # hotelier の hotel

    def test_number_only_name(self):
        self.assertFalse(self.hits("2027", "游戏", "2027 budget plan announced"))
        self.assertTrue(self.hits("2027", "游戏", "2027 gets a Steam release date"))
        self.assertFalse(self.hits("1999", None, "In 1999 the city changed"))   # 板块がなくても数字だけでは当てない
        self.assertTrue(self.hits("1999", None, "1999 the anime gets a trailer"))

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


class Recall(unittest.TestCase):
    """2026-10-22：10 月の inbox で、名前を含む記事のうち拾えたのが ILLIT 59/208・Vaundy 8/48・Astrae Oratio 0/40 だった（板块の語が要った）。
    よく使う語でない名前は名前だけで拾う。落ちていたのは本物の見出し"""
    hits = Rules.hits

    def test_proper_names_alone(self):
        for name, sec, title in [("Astrae Oratio", "游戏", "NC ANNOUNCES CLOSED BETA TEST REGISTRATION FOR ASTRAE ORATIO BEGINNING AUGUST 19"),
                                 ("Vaundy", "演出", "Vaundy、「しわあわせ」が急上昇1位 2021年配信楽曲が映画主題歌起用で再生数増"),
                                 ("ILLIT", "演出", "活動休止中のILLITモカの誕生日をメンバーが秘蔵写真＆長文メッセージで祝福！"),
                                 ("NewJeans", "演出", "「ILLITはNewJeansのコピー」発言…ミン・ヒジン氏を送検"),
                                 ("Vaundy", None, "KO1KEYZ Debuts at No. 1 on Japan Hot 100 as Vaundy Climbs Into Top 10")]:
            self.assertTrue(self.hits(name, sec, title), (name, title))
        self.assertEqual(userfeed.ascii_kind("Astrae Oratio"), "proper")
        self.assertEqual(userfeed.ascii_kind("The Wrong Way"), "phrase")
        self.assertEqual(userfeed.ascii_kind("Apex"), "word")
        self.assertEqual(userfeed.ascii_kind("IVE"), "word")   # 3 字以下はよく使う語と同じ扱い（略語に当たる）

    def test_common_words_still_need_context(self):
        self.assertFalse(self.hits("Apex", "游戏", "蒂姆·库克收到绝区零手办，这 1/7 比例细节有点东西|APEX-TOYS"))   # 1 語は日本語・中国語の記事でも語と一緒に
        self.assertFalse(self.hits("Tokyo", "出行", "シャネル 2027年春夏 コレクションのショーに出席（Numero TOKYO）"))
        self.assertTrue(self.hits("Hollow Knight", "游戏", "「Hollow Knight」の続編の発表は来年に"))   # 2 語以上の句は、かな・漢字の記事なら
        self.assertFalse(self.hits("Hollow Knight", "游戏", "The hollow knight statue in the old church"))
        self.assertFalse(self.hits("Live", None, "'GTA 6' official merch is live, and it's already selling out"))   # 板块がなくても語と一緒

    def test_symbols_only_not_collected(self):
        self.assertEqual(userfeed.match_terms("..."), [])
        self.assertFalse(userfeed.has_word("！？…"))
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "...", "sec": "其他"}, {"name": "広島旅行", "sec": "出行"}]}}]
        todo, keep, _, blanks = userfeed.plan(users, [], [], NOW)
        self.assertEqual([g["name"] for g in todo], ["広島旅行"])
        self.assertEqual([b[1] for b in blanks], ["..."])
        self.assertIn("...", keep[userfeed.account_of("a@example.com")])
        rows = [{"account": userfeed.account_of("a@example.com"), "item": "...", "checked_at": NOW.isoformat(), "state": "ok"}]
        self.assertEqual(userfeed.plan(users, [], rows, NOW)[3], [])   # 1 度書いたら書き直さない

    def test_kanji_name_with_genre_suffix(self):
        self.assertTrue(self.hits("広島旅行", "出行", "秋の広島観光、宮島の紅葉が見頃に"))
        self.assertTrue(self.hits("広島旅行", "出行", "広島への旅行で行きたい場所"))
        self.assertFalse(self.hits("広島旅行", "出行", "広島で大会が開催"))   # どこにでも出る語（開催）だけでは当てない

    def test_same_name_other_genre_not_shared(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "Apex", "sec": "游戏"}]}},
                 {"email": "b@example.com", "prefs": {"picks": [{"name": "Apex", "sec": "出行"}]}},
                 {"email": "c@example.com", "prefs": {"picks": [{"name": "Apex", "sec": "游戏"}]}}]
        todo = userfeed.plan(users, [], [], NOW)[0]
        self.assertEqual(sorted(len(g["boards"]) for g in todo), [1, 2])   # 匹配词が板块で変わる名前は、同じ板块の人とだけまとめる

    def test_fetch_failure_counts_as_failure(self):
        it = userfeed.board_item("広島旅行", "出行", ["ja-JP"])

        def refused(*_a, **_k):
            sources._tl.fails = sources.fetch_fails() + 1   # rss() が 429 を握りつぶしたときと同じ
            return []
        with mock.patch.object(digest, "collect", side_effect=refused):
            with self.assertRaises(RuntimeError):
                userfeed.stories_for(it, {})
        with mock.patch.object(digest, "collect", return_value=[]):
            self.assertEqual(userfeed.stories_for(it, {}), [])   # 取れて 0 件は失敗にしない


class Plan(unittest.TestCase):
    def users(self):
        return [{"email": "test-b@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "ちいかわ", "sec": "影视"}, {"name": "広島旅行", "sec": "出行"}]}},
                {"email": "test-c@example.com", "prefs": {"lang": {"primary": "ja"},
                 "picks": [{"name": "広島旅行", "sec": "生活"}, {"name": "", "sec": "x"}]}},
                {"email": None, "prefs": {"picks": [{"name": "だれか"}]}}]

    def test_only_not_in_shop_and_grouped(self):
        todo, keep, limits, _ = userfeed.plan(self.users(), ["ちいかわ"], [], NOW)
        self.assertEqual([g["name"] for g in todo], ["広島旅行"])   # 店長の版面にあるものは集めない
        self.assertEqual(len(todo[0]["boards"]), 2)                  # 2 人が同じものなら 1 回で
        self.assertEqual({b[2] for b in todo[0]["boards"]}, {"出行", "生活"})   # 板块は人ごと（1 人目のもので上書きしない）
        self.assertEqual(keep[userfeed.account_of("test-b@example.com")], {"広島旅行"})
        self.assertEqual(limits, [])

    def test_trim_and_duplicates(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "  広島旅行 ", "sec": "出行"}, {"name": "広島 旅行", "sec": "出行"},
                                                                {"name": "あ" * 90, "sec": "其他"}]}}]
        todo, keep, _, _ = userfeed.plan(users, [], [], NOW)
        self.assertEqual(keep[userfeed.account_of("a@example.com")], {"広島旅行", "あ" * 80})   # SQL の my_boards と同じ：trim・80 字・同じ名前は 1 つ
        sql = (ROOT / "db" / "user_boards.sql").read_text(encoding="utf-8")
        self.assertIn("left(btrim(x.value ->> 'name', E' \\t\\n\\r\\f\\x0b\\u3000\\u00a0'), 80)", sql)
        self.assertEqual(userfeed.pick_name("\u3000広島旅行\t"), "広島旅行")   # 全角の空白も（SQL も同じ文字）
        self.assertEqual(userfeed.TRIM, " \t\n\r\f\x0b\u3000\u00a0")
        self.assertIn("distinct on (lower(regexp_replace(r.name, '\\s', '', 'g')))", sql)

    def test_recent_skipped(self):
        acct = userfeed.account_of("test-b@example.com")
        rows = [{"account": acct, "item": "広島旅行", "checked_at": (NOW - dt.timedelta(minutes=30)).isoformat()}]
        todo, _, _, _ = userfeed.plan(self.users()[:1], [], rows, NOW)
        self.assertEqual([g["name"] for g in todo], ["ちいかわ"])   # 30 分前に探したものは飛ばす

    def test_cap_marks_limit_and_new_first(self):
        cap = userfeed.MAX_BOARDS_PER_USER
        many = [{"email": "a@example.com", "prefs": {"picks": [{"name": f"もの{i}", "sec": "其他"} for i in range(cap + 5)]}}]
        todo, keep, limits, _ = userfeed.plan(many, [], [], NOW)
        acct = userfeed.account_of("a@example.com")
        self.assertEqual(len(keep[acct]), cap + 5)                                    # 上限を超えた分も消さない
        self.assertEqual([x[1] for x in limits], [f"もの{i}" for i in range(cap, cap + 5)])   # 超えた分は limit の行（「集めています」のままにしない）
        self.assertEqual(len(todo), userfeed.PER_USER_PER_RUN)
        self.assertEqual(todo[0]["name"], f"もの{cap - 1}")                              # まだ探していないものは新しく足したものから
        rows = [{"account": acct, "item": f"もの{i}", "checked_at": (NOW - dt.timedelta(hours=10 - i)).isoformat(), "state": "ok"} for i in range(5)]
        rows += [{"account": acct, "item": f"もの{i}", "checked_at": NOW.isoformat(), "state": "limit"} for i in range(cap, cap + 5)]
        todo, _, limits, _ = userfeed.plan(many, [], rows, NOW)
        self.assertEqual(limits, [])                                             # 書いてあれば書き直さない
        self.assertEqual(todo[0]["name"], f"もの{cap - 1}")

    def test_fair_between_users(self):
        users = [{"email": f"u{n}@example.com", "prefs": {"picks": [{"name": f"{n}の{i}", "sec": "其他"} for i in range(30)]}} for n in range(30)]
        rows = [{"account": userfeed.account_of(f"u{n}@example.com"), "item": f"{n}の0", "checked_at": "2026-10-01T00:00:00+00:00"} for n in range(30)]
        todo, _, _, _ = userfeed.plan(users, [], rows, NOW)
        self.assertEqual(len(todo), userfeed.MAX_BOARDS_PER_RUN)
        firsts = todo[:30]
        self.assertEqual(len({g["boards"][0][0] for g in firsts}), 30)   # 全員の 1 つ目が先（1 人で全部を使わない）

    def test_new_users_capped(self):
        users = [{"email": f"spam{n}@example.com", "prefs": {"picks": [{"name": f"s{n}", "sec": "其他"}]}} for n in range(50)]
        todo, _, _, _ = userfeed.plan(users, [], [], NOW)
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
        logs = []
        res = self.run_with(db, collect, logs)
        self.assertEqual(res["failed"], 1)
        got = {r["item"]: r for r in db.written()}
        self.assertEqual(got["よいもの"]["found"], 1)
        self.assertNotIn("fails", got["よいもの"])   # 列のそろった行はまとめて書く（失敗の行とは分ける）
        self.assertEqual((got["だめなもの"]["fails"], got["だめなもの"]["stories"]), (1, []))   # 失敗は fails +1（網页は「集めています」のまま）
        self.assertEqual(got["だめなもの"]["checked_at"], NOW.isoformat(timespec="seconds"))
        more = [{"email": "a@example.com", "prefs": {"picks": users[0]["prefs"]["picks"] + [{"name": "新しいもの"}]}}]
        todo, _, _, _ = userfeed.plan(more, [], db.written(), NOW + dt.timedelta(hours=2))
        self.assertEqual(todo[0]["name"], "新しいもの")   # 次の回、失敗したものはまだ探していないものの後ろ（毎回 1 人分の枠を取り続けない）
        self.assertFalse(any("だめなもの" in x or "よいもの" in x or "boom" in x for x in logs))   # ログに選んだものの名前・エラーの本文を出さない
        self.assertTrue(any("取れなかった（RuntimeError）" in x for x in logs))

    def test_network_error_is_failure(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "もの"}]}}]
        db = FakeDB(users)
        orig = db.__call__

        def flaky(path, body=None, prefer=None, method=None):
            if path.startswith("user_boards?on_conflict"):
                raise TimeoutError("timed out")
            return orig(path, body, prefer, method)
        res = self.run_with(flaky, lambda item, settings: [story(1, "ものの記事")])
        self.assertEqual(res["bad"], 1)   # つながらない・時間切れ（OSError）も 1 行ずつ書き直して数える（全部を落とさない）

    def test_logs_have_no_pick_names(self):
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "秘密の旅行"}]}}]
        logs = []
        self.run_with(FakeDB(users), lambda item, settings: [], logs)
        self.assertTrue(logs)
        self.assertFalse(any("秘密の旅行" in x for x in logs))

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
        with mock.patch.object(digest, "run_parallel", return_value=({}, [("おそいもの", ("ja-JP",), tuple(userfeed.board_item("おそいもの", None, ["ja-JP"])["match"]))])):
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
                  f"b.fails between 1 and {userfeed.FAIL_SHOW - 1} then 'wait'", "a.banned_until < now()",
                  "add column if not exists fails int not null default 0",
                  "grant execute on function public.userfeed_users(int, int) to service_role",
                  "revoke all on function public.userfeed_users(int, int) from public, anon, authenticated",
                  "v := v - 'picks'"):
            self.assertIn(w, sql)
        self.assertNotIn("userfeed_users(int, int) to anon", sql)

    def test_page_reads_my_boards(self):
        import render
        for w in ("rpc('my_boards')", "今日の主なニュース", "気になるかも？", "まだ記事が見つかっていません", "100 個まで", "wl-cards",
                  "'&pick='", "new Event('wl-nav')", "R._wlmb", "clearInterval(R._wlub);R._wlmb=null"):
            self.assertIn(w, render.AUTH_JS)
        self.assertIn("document.addEventListener('wl-nav'", render.NAV_JS)   # 目次は足した駅を数え直す
        for w in ("いま集めに行っています", "1〜2 時間", "👍👎 を押すと"):   # できないことを約束しない
            self.assertNotIn(w, render.AUTH_JS)
        self.assertIn('html[data-mine="2"] .mastwish', render.AUTH_CSS)   # 店長の欲しい物の件数・話題度・👍👎 はお客さまのページに出さない
        import welcome
        self.assertIn("q.get('pick')", welcome.render_js() if hasattr(welcome, "render_js") else (ROOT / "scripts" / "welcome.py").read_text(encoding="utf-8"))

    @unittest.skipUnless(__import__("shutil").which("node"), "node がない")
    def test_js_shop_hit_same_as_python(self):
        # 網页の shopHit（AUTH_JS）と userfeed.shop_hit が同じ答えを出す（1 つの規則）
        import json, re, subprocess
        import render
        js = render.AUTH_JS
        src = "\n".join(re.search(p, js, re.S).group(0) for p in (r"function norm\(s\)\{.*?\}", r"function an\(c\)\{.*?\}",
                                                                 r"function shopHit\(a,b\)\{.*?return false;\}"))
        cases = [["ちいかわ", "ちいかわ"], ["ちいかわ", "ちいかわ グッズ"], ["GTA 6", "gta6"], ["ILLIT", "ILLIT ライブ"], ["ちいかわ", "広島旅行"],
                 ["猫用品", "犬"], ["FROM", "From Software"], ["FROM", "FROM"], ["AB", "xab"], ["ab", "ab cd"], ["", "x"], ["Ｆｏｏ", "foo"],
                 ["the wrong way", "The Wrong Way"], ["GTA", "GTA6"], ["6", "GTA 6"]]
        out = subprocess.run(["node", "-e", src + f";console.log(JSON.stringify({json.dumps(cases)}.map(c=>shopHit(c[0],c[1]))))"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [userfeed.shop_hit(a, b) for a, b in cases])
        self.assertIn("/^https?:\\/\\//.test(u)", render.AUTH_JS)   # 網址は http(s) だけ


class Wiring(unittest.TestCase):
    def test_workflow_and_arch(self):
        wf = (ROOT / ".github" / "workflows" / "digest.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/userfeed.py", wf)
        import processes
        self.assertIn("userfeed", processes.COMPONENTS)
        flow = next(p for p in processes.PROCESSES if p["id"] == "collect")
        self.assertIn("userfeed", flow["uses"])

    def test_limits_match_code(self):
        import processes
        row = next(x for x in processes.LIMITS if x[0] == "お客さまの版面の記事集め")
        self.assertIn(f"1 人 1 回 {userfeed.PER_USER_PER_RUN} 版面", row[2])   # 図の数字はコードとそろえる（CLAUDE.md）
        self.assertIn(f"1 人 1 回 {userfeed.PER_USER_PER_RUN} 版面", processes.COMPONENTS["userfeed"]["spec"])

    def test_page_side_guards(self):
        # 画面側（render.AUTH_JS）の決まり：Playwright なしで、壊れやすい所だけ文字で確かめる
        import render
        js = render.AUTH_JS
        self.assertIn("if(!on&&R.dataset.mine==='2'){", js)    # お客さま → 访客：書き換えたページを開き直す（版面・駅が混ざったままにしない）
        self.assertIn("if(sig===R._wlsig&&!bad)return;", js)    # 5 分ごとの読み直しで、返事が同じなら描き直さない
        self.assertIn("s.dataset.sub=UB", js)                    # 自分の版面は自分の小分類（店長の小分類の見出しの下に入れない）
        self.assertIn("'wl-uchip'", js.replace('"', "'"))
        self.assertIn("← '+esc(sh)+' さんのページへ", js)        # 設定から自分のトップへ戻る道
        self.assertIn("SPARE_MAX", render.NAV_JS)                # 駅が少ないときに板块の間を大きく空けない
        self.assertIn(".wl-auth.away", render.AUTH_CSS)          # スマホの右下の札は、下へ読み進める間しまう（本文に重ねない）


if __name__ == "__main__":
    unittest.main()


class MediaRules(unittest.TestCase):
    """写真と原文の網址（店長と同じ sources.resolve_url・images.pick。ネットには出ない：resolve・pick を差し替える）。"""

    def media(self, resolve=None, pick=None, now=NOW):
        import time
        return userfeed.Media(time.monotonic() + 60, now, resolve=resolve or (lambda u: u.replace("https://news.google.com/rss/articles/", "https://real.example/")),
                              pick=pick or (lambda s, budget, avoid: s["url"] + ".jpg"))

    def g(self, n, title, **kw):
        return {**story(n, title), "url": f"https://news.google.com/rss/articles/{n}", **kw}

    def test_google_link_to_original_and_photo(self):
        st = [self.g(1, "一"), self.g(2, "二"), story(3, "三")]
        m = self.media()
        self.assertTrue(m.board(st))
        self.assertEqual([s["url"] for s in st], ["https://real.example/1", "https://real.example/2", "https://news.example.jp/3"])
        self.assertEqual([s["image"] for s in st], ["https://real.example/1.jpg", "https://real.example/2.jpg", "https://news.example.jp/3.jpg"])
        self.assertFalse(userfeed.needs_media(st, NOW))

    def test_only_head_stories_get_photos_and_no_retry_soon(self):
        st = [story(n, f"記事{n}") for n in range(userfeed.MEDIA_STORIES + 2)]
        calls = []
        m = self.media(pick=lambda s, b, a: calls.append(s["url"]) or None)
        m.board(st)
        self.assertEqual(len(calls), userfeed.MEDIA_STORIES)            # 頭の数本だけ
        self.assertTrue(all(s.get("img_at") for s in st[:userfeed.MEDIA_STORIES]))
        self.assertFalse(userfeed.needs_media(st, NOW + dt.timedelta(hours=1)))   # 見つからなかった記事は 24 時間あける
        self.assertTrue(userfeed.needs_media(st, NOW + dt.timedelta(hours=userfeed.RETRY_IMG_H)))

    def test_same_photo_not_twice_in_board(self):
        st = [story(1, "一"), story(2, "二")]
        self.media(pick=lambda s, b, a: "https://img.example/same.jpg").board(st)
        self.assertEqual([bool(s["image"]) for s in st], [True, False])

    def test_unresolved_google_kept_and_breaker(self):
        calls = []
        m = self.media(resolve=lambda u: calls.append(u) or u)
        st = [self.g(n, f"記事{n}") for n in range(userfeed.RESOLVE_FAILS + 3)]
        m.board(st)
        self.assertEqual(len(calls), userfeed.RESOLVE_FAILS)   # 続けて断られたらこの回はやめる
        self.assertTrue(all("news.google.com" in s["url"] for s in st))   # 記事は残す
        self.assertTrue(all(not s["image"] for s in st))                # 跳转のままの記事には写真を探さない

    def test_saved_photo_not_used(self):
        import images
        res = images.Result(image="https://img.example/a.jpg", source="og:image" + images.SAVED)
        with mock.patch.object(images, "pick", return_value=res):
            self.assertIsNone(userfeed.Media._pick(story(1, "一"), 5, set()))
        res = images.Result(image="https://img.example/a.jpg", source="og:image")
        with mock.patch.object(images, "pick", return_value=res):
            self.assertEqual(userfeed.Media._pick(story(1, "一"), 5, set()), "https://img.example/a.jpg")

    def test_run_fixes_rows_not_collected_this_time(self):
        a = userfeed.account_of("a@example.com")
        users = [{"email": "a@example.com", "prefs": {"picks": [{"name": "新しいもの", "sec": "其他"}, {"name": "前のもの", "sec": "其他"}]}}]
        rows = [{"account": a, "item": "前のもの", "sec": "其他", "state": "ok", "found": 2, "fails": 0,
                 "stories": [self.g(9, "前の記事")], "checked_at": NOW.isoformat(), "updated_at": NOW.isoformat()}]   # 90 分以内に探した
        db = FakeDB(users, rows)
        logs = []
        with mock.patch.object(digest, "load_config", return_value=({}, [])):
            userfeed.run(db=db, collect=lambda item, settings: [self.g(1, item["name"] + "の記事")], now=NOW, log=logs.append, shop=[],
                         media=lambda deadline, now: self.media())
        got = {r["item"]: r for r in db.written()}
        self.assertEqual(got["新しいもの"]["stories"][0]["url"], "https://real.example/1")
        self.assertEqual(got["前のもの"]["stories"][0]["url"], "https://real.example/9")   # 今回は探さなかった行も直して書く
        self.assertEqual((got["前のもの"]["found"], got["前のもの"]["checked_at"]), (2, NOW.isoformat()))   # ほかの列はそのまま
        self.assertTrue(any("写真" in x for x in logs))
        self.assertFalse(any("前のもの" in x or "新しいもの" in x for x in logs))   # ログに名前を出さない

    def test_resolve_url_tries(self):
        with mock.patch.object(sources, "_resolve_once", side_effect=lambda u: u) as once, mock.patch.object(sources.time, "sleep"):
            sources.resolve_url("https://news.google.com/rss/articles/zz", tries=1)
        self.assertEqual(once.call_count, 1)
