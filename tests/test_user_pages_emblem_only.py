"""小元素だけの作り直し（user_pages.py --boards-file F --emblem-only、2026-11-19 店長「新しい版面を足したら小元素が出るまで 5 分未満」）。
前は 1 人分 92 秒（記事の代表の写真を読み直す・写真の余白と主役を測り直す・「気になるかも？」の跳转を 1 本ずつ戻す・頭の写真を 1 本ずつ聞く）。
重い段を呼ばず、前の回の結果（pages/_fp/all.json）で「前のページ＋小元素」を作る（2026-11-19 本番 2 回目：前の結果が足りない人をふつうに作り 153 秒）。網・DB なし。"""
import contextlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import og_image  # noqa: E402
import photo_bands  # noqa: E402
import user_pages  # noqa: E402

FP = "/storage/v1/object/pages/_fp/all.json"


def as_pick(find):
    """digest.find_image の形（chosen, refs, url → 網址）の偽物を images.pick の形に（find_images は SAVED を見るので images.pick を呼ぶ。2026-11-19 合わせ）。"""
    import images
    return lambda chosen, refs, url, **k: images.Result(image=find(chosen, refs, url) or None)


def pick_patch(find):
    import images
    return mock.patch.object(images, "pick", as_pick(find))


def og_page(count):
    """og_image の読み（images.page の形）の偽物：読んだら count() を呼び、写真は無い。"""
    import images
    return lambda u: count() or images.Page(u, True)


class FindImages(unittest.TestCase):
    def stories(self):
        return [{"headline": "a", "url": "https://n.example/1"}, {"headline": "b", "url": "https://n.example/2"}]

    def test_cache_only_does_not_search(self):
        calls = []
        cache = {"https://n.example/1": {"img": "https://img/1.jpg", "at": 0}, "https://n.example/2": {"img": "", "at": 0}}
        with pick_patch(lambda *a: calls.append(a) or "x"):
            st = user_pages.find_images(self.stories(), 9e18, cache, new=False)
            st2 = user_pages.find_images([{"headline": "c", "url": "https://n.example/3"}], 9e18, {}, new=False)
        self.assertEqual(calls, [])
        self.assertEqual([s.get("image") for s in st], ["https://img/1.jpg", None])   # 小元素だけの回：見つからなかった記事は無いまま（探さない）
        self.assertIsNone(st2[0].get("image"))   # 前の結果に無いものは探さない

    def test_full_run_remembers_results_but_not_errors(self):
        cache = {}

        def pick(chosen, refs, url):
            if url.endswith("/2"):
                raise OSError("net")
            return "https://img/" + url[-1] + ".jpg"
        with pick_patch(pick):
            user_pages.find_images(self.stories(), 9e18, cache, now=1000)
        self.assertEqual(cache, {"https://n.example/1": {"img": "https://img/1.jpg", "at": 1000}})   # 読めなかったものは覚えない（次の回にまた探す）

    def test_full_run_retries_a_miss_after_a_while(self):
        # images.pick は断られた・20 秒で止まった時も None：「無い」を永久に信じると、その記事は二度と探されず整理待ちのまま
        calls = []
        cache = {"https://n.example/1": {"img": "", "at": 1000}}
        st = [{"headline": "a", "url": "https://n.example/1"}]
        with pick_patch(lambda *a: calls.append(a) or "https://img/new.jpg"):
            user_pages.find_images([dict(s) for s in st], 9e18, cache, now=1000 + 60)   # 見つからなかったばかり：探さない
            self.assertEqual(calls, [])
            got = user_pages.find_images([dict(s) for s in st], 9e18, cache, now=1000 + user_pages.PICK_RETRY_S)   # 間をあけたら探し直す
        self.assertEqual(len(calls), 1)
        self.assertEqual(got[0]["image"], "https://img/new.jpg")
        self.assertEqual(cache["https://n.example/1"]["img"], "https://img/new.jpg")


class Limits(unittest.TestCase):
    def test_og_fill_limit_zero_reads_nothing(self):
        rows = {"x": {"stories": [{"url": "https://n.example/1"}, {"url": "https://n.example/2"}]}}
        seen = []
        n = og_image.fill(rows, {"https://n.example/1": "https://img/og1.jpg"}, page=og_page(lambda: seen.append(1)), log=lambda *a: None, limit=0)
        self.assertEqual((n["read"], seen), (0, []))
        self.assertEqual(rows["x"]["stories"][0]["image"], "https://img/og1.jpg")   # 前の結果は付く

    def test_bands_limit(self):
        seen = []
        with mock.patch.object(photo_bands, "bands", lambda d: []), mock.patch.object(photo_bands, "mass_css", lambda d: ""), \
                mock.patch.object(photo_bands, "text_box", lambda d: None), mock.patch.object(photo_bands, "people_box", lambda d: None), \
                mock.patch.object(photo_bands, "segments", lambda d: []):
            photo_bands.measure([f"https://p/{i}.jpg" for i in range(40)], {}, lambda u: seen.append(u) or b"x", log=lambda *a: None, limit=16)
        self.assertEqual(len(seen), 16)


class MemoTests(unittest.TestCase):
    def test_reuse_new_keep_and_box(self):
        asked = []
        m = user_pages.Memo({"a": "A"}, lambda u: asked.append(u) or u.upper(), keep=lambda u, v: v != u)
        self.assertEqual((m("a"), m("b"), m("b")), ("A", "B", "B"))
        self.assertEqual(asked, ["b"])   # 前の答え・この回の答えは聞かない
        self.assertEqual(m.box(True), {"a": "A", "b": "B"})
        self.assertEqual(m.box(False), {"a": "A", "b": "B"})   # 使った分
        m2 = user_pages.Memo({"a": "A", "z": "Z"}, lambda u: 1 / 0, new=False)
        self.assertEqual((m2("a"), m2("q")), ("A", "q"))   # 前の答えだけ（網に出ない）
        self.assertEqual(m2.box(False), {"a": "A"})   # 全員の回は使った分だけ（増え続けない）

    def test_fails_stop_asking(self):
        asked = []
        m = user_pages.Memo({}, lambda u: asked.append(u) or u, keep=lambda u, v: v != u, fails_max=2)
        [m(str(i)) for i in range(5)]
        self.assertEqual(asked, ["0", "1"])   # 続けて 2 回戻せなかったら、この回は聞かない

    def test_reuse_false_asks_again(self):
        asked = []
        m = user_pages.Memo({"a": False}, lambda u: asked.append(u) or True, reuse=False)
        self.assertTrue(m("a"))
        self.assertEqual(asked, ["a"])   # ふつうの作り直しは「写真が開くか」を聞き直す


class Fps(unittest.TestCase):
    def test_merge_keeps_other_runs(self):
        old = {"u1/index.html": "1", "_og": {"a": "A"}}
        cur = {"u1/index.html": "1", "u2/index.html": "9", "_og": {"a": "A", "b": "B"}}   # 作っている間にほかの回が u2 と b を書いた
        mine = {"u1/index.html": "2", "_og": {"a": "A", "c": "C"}}
        got = user_pages.merge_fps(cur, old, mine)
        self.assertEqual(got["u1/index.html"], "2")
        self.assertEqual(got["u2/index.html"], "9")
        self.assertEqual(got["_og"], {"a": "A", "b": "B", "c": "C"})
        self.assertEqual(user_pages.merge_fps(None, old, mine), mine)

    def test_full_run_does_not_undo_a_page_placed_meanwhile(self):
        # 全員の回が組んでいる間に小元素だけの回がこの人のページを置いた（指紋 2）。全員の回は変わらず置かなかった（1 のまま）：
        # 上書きすると記録の指紋が 1 に戻り、次の回が「変わっていない」と見て置き直さなかった
        old = {"u1/index.html": "1", "u2/index.html": "a", "_up_pick": {"x": {"img": "", "at": 1}}, "_open": {"o": True}}
        cur = {"u1/index.html": "2", "u2/index.html": "a", "_up_pick": {"x": {"img": "", "at": 1}}, "_open": {"o": True, "p": True}}
        mine = {"u1/index.html": "1", "u2/index.html": "b", "_up_pick": {"x": {"img": "https://img/x.jpg", "at": 9}}, "_open": {"q": False}}
        got = user_pages.merge_fps(cur, old, mine, exact=("_open", "_res"))
        self.assertEqual(got["u1/index.html"], "2")   # この回が変えていない人の分はいまのまま
        self.assertEqual(got["u2/index.html"], "b")   # この回が置いた人の分だけ差し替える
        self.assertEqual(got["_up_pick"]["x"]["img"], "https://img/x.jpg")   # 探し直して見つかった写真を前の「無い」で消さない
        self.assertEqual(got["_open"], {"q": False})   # 全員の回の _open は使った分だけ（増え続けない）
        src = __import__("inspect").getsource(user_pages.main)
        self.assertIn("new_fps = merge_fps(_fresh_fps(fp_path), fps, new_fps, exact=", src)   # 全員の回も読み直して差し替える

    def test_full_run_resolves_like_before(self):
        # ふつうの回の跳转の戻しは前の試し方のまま（3 回・失敗の数を全員で持たない）。速くするのは --emblem-only だけ
        src = __import__("inspect").getsource(user_pages.main)
        self.assertIn("lambda u: sources.resolve_url(u)", src)
        self.assertNotIn("tries=1", src)
        self.assertNotIn("fails_max", src)

    def test_newer_page(self):
        with mock.patch.object(user_pages, "_supa", lambda p: {"u1/index.html": "new"}):
            self.assertTrue(user_pages.newer_page({"u1/index.html": "old"}, FP, "u1"))
            self.assertFalse(user_pages.newer_page({"u1/index.html": "new"}, FP, "u1"))
        with mock.patch.object(user_pages, "_supa", lambda p: 1 / 0):
            self.assertFalse(user_pages.newer_page({}, FP, "u1"))   # 読めなければ置く


class EmblemOnlyMain(unittest.TestCase):
    """main を偽の Supabase で回し、--emblem-only が重い段（記事の写真探し・跳转の戻し・前に聞いた写真・模型の測り）を呼ばないことを数える。
    DB（版面の config）と storage（ページ・指紋）は self.db・self.store に持ち、回をまたいで同じものを使う。"""
    EMAIL = "test-x@example.com"
    EMB = "https://e.example/a.webp"

    def setUp(self):
        self.acct = user_pages.account_of(self.EMAIL)
        self.db = {"config": {"emblem_state": {"have": 0}}}   # 版面 5 の config（小元素なし）
        self.store = {}
        self.more = []   # 2 回目から足す記事（前の回の覚えに無い記事）
        self.added = "2999-01-01T00:00:00Z"   # 版面 5 を足した時刻（既定は --recent が選ぶ「足したばかり」）
        self.fps_down = False   # 指紋（all.json）の読みが失敗する回
        self.new_board = None   # 2 回目から足す版面 {"config", "pending"}（新しく足した版面：id 6）

    def page(self):
        return (self.store.get(f"/storage/v1/object/pages/{self.acct}/index.html") or b"").decode("utf-8")

    def run_main(self, args, during_measure=None, moved=None):
        story = {"title": "t", "url": "https://n.example/1", "summary": "", "source": "s", "date": "2026-11-19"}

        def follows():
            out = [{"pos": 0, "section": "生活", "subs": {}, "size": "M",
                    "boards": {"id": 5, "name": "自分の版面", "config": json.loads(json.dumps(self.db["config"]))}}]
            if self.new_board:
                out.append({"pos": 1, "section": "生活", "subs": {}, "size": "M",
                            "boards": {"id": 6, "name": "新しい版面", "config": json.loads(json.dumps(self.new_board["config"]))}})
            return out

        def supa(path, data=None, method="GET", ctype="application/json"):
            if "rpc/userfeed_users" in path:
                picks = [{"name": "自分の版面", "sec": "生活", "added_at": self.added}]
                if self.new_board:
                    picks.append({"name": "新しい版面", "sec": "生活"})
                return [{"email": self.EMAIL, "prefs": {"picks": picks}}]
            if path.startswith("/storage/"):
                if method == "POST":
                    self.store[path] = json.loads(data) if ctype.startswith("application/json") else data
                    return {}
                if path == FP and self.fps_down:
                    raise OSError("timeout")   # 一瞬読めない（Tailscale 越しの時間切れ）
                if path in self.store:
                    return json.loads(json.dumps(self.store[path])) if isinstance(self.store[path], dict) else self.store[path]
                import urllib.error
                raise urllib.error.HTTPError(path, 404, "not found", {}, None)   # まだ無い
            if "follows?board_id=in." in path:
                return [{"account": self.acct}]
            if "follows?account" in path:
                return follows()
            if "board_stories" in path:
                out = [{"board_id": 5, "day": "2026-11-19", "stories": [], "pending": [story, *self.more]}]
                if self.new_board:
                    out.append({"board_id": 6, "day": "2026-11-19", "stories": [], "pending": self.new_board["pending"]})
                return json.loads(json.dumps(out))
            if "boards?id=in." in path:
                out = [{"id": 5, "emblem_state": self.db["config"].get("emblem_state")}]
                if self.new_board:
                    out.append({"id": 6, "emblem_state": self.new_board["config"].get("emblem_state")})
                return out
            return []
        calls = {"og": 0, "pick": 0, "resolve": 0, "opens": 0, "photo": 0, "measure_limit": []}
        real_measure = photo_bands.measure

        def measure(urls, cache, fetch, log=print, limit=None):
            calls["measure_limit"].append(limit)
            if during_measure:
                during_measure()
            return real_measure(urls, cache, lambda u: calls.__setitem__("photo", calls["photo"] + 1), log=lambda *a: None, limit=limit)
        with tempfile.TemporaryDirectory() as d:
            ids = pathlib.Path(d) / "ids.json"
            ids.write_text("[5]")
            argv = [x if x != "IDS" else str(ids) for x in args]
            fill = og_image.fill
            with mock.patch.object(user_pages, "_supa", supa), \
                    mock.patch.object(user_pages.photo_store, "published", lambda *a: set()), \
                    pick_patch(lambda *a: calls.__setitem__("pick", calls["pick"] + 1)), \
                    mock.patch.object(user_pages.sources, "resolve_url", lambda u, tries=None: calls.__setitem__("resolve", calls["resolve"] + 1) or u), \
                    mock.patch.object(user_pages.render, "photo_opens", lambda u: calls.__setitem__("opens", calls["opens"] + 1) or True), \
                    mock.patch.object(user_pages.og_image, "fill", lambda rows, cache, **kw: fill(rows, cache, **{**kw, "page": og_page(lambda: calls.__setitem__("og", calls["og"] + 1)), "log": lambda *a: None})), \
                    mock.patch.object(user_pages.photo_bands, "measure", measure), \
                    mock.patch.object(user_pages.render, "OPENS", None), \
                    (mock.patch.object(user_pages, "design_moved", moved) if moved else contextlib.nullcontext()):
                user_pages.main(argv)
        return calls

    def write_emblem(self):   # 速い道が小元素を書く（library_emblem.fill_board → put_config）
        self.db["config"] = {"emblem": [{"image": self.EMB, "subject": "a"}], "emblem_state": {"have": 1, "at": 2}}

    def test_emblem_only_uses_previous_results(self):
        self.run_main(["--boards-file", "IDS"])   # 前の回（ふつう）：測った結果を残す
        self.write_emblem()
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(calls["pick"], 0)      # 記事の写真探し（1 本 20 秒）はしない
        self.assertEqual(calls["og"], 0)        # 前に読んだ記事の代表の写真は読み直さない
        self.assertEqual(calls["resolve"], 0)   # 跳转の戻しは前の答えだけ
        self.assertEqual(calls["measure_limit"], [])   # 写真の余白と主役は前の結果だけ（模型を読まない）
        self.assertEqual(calls["opens"], 0)     # 頭の写真が開くかも前の答えだけ
        self.assertIn(self.EMB, self.page())

    def test_emblem_only_does_not_retry_old_misses(self):
        """見直し 2 回目 3：前の回の「取れなかった」が 4 時間前（ふつうの回なら試し直す間を過ぎた）でも、小元素だけの回は og を読みに行かない（0 回）。"""
        import datetime as dt
        self.run_main(["--boards-file", "IDS"])
        url = "https://n.example/1"
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)).isoformat(timespec="seconds")
        self.store[FP]["_og"][url] = {"why": "none", "at": old, "n": 1}
        self.write_emblem()
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(calls["og"], 0)
        self.assertEqual(calls["measure_limit"], [])   # ふつうに作り直してもいない（小元素だけの回のまま）
        self.assertIn(self.EMB, self.page())

    def test_story_after_previous_page_waits_for_the_normal_run(self):
        """本番 2 回目：前のページの後に来た記事（前の結果に無い）は、小元素だけの回では載せない（ふつうに作らない・網に出ない）。"""
        self.added = "2026-01-01T00:00:00Z"   # 前からの版面（記事 5 本までの待ちに入らない）
        self.run_main(["--boards-file", "IDS"])
        self.assertIn("https://n.example/1", self.page())
        self.more = [{"title": "t2", "url": "https://n.example/2", "summary": "", "source": "s", "date": "2026-11-19"}]
        self.write_emblem()
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual((calls["og"], calls["measure_limit"]), (0, []))   # ふつうに作っていない
        self.assertIn("https://n.example/1", self.page())       # 前のページの記事は残る
        self.assertNotIn("https://n.example/2", self.page())    # 後に来た記事は次のふつうの回で
        self.assertIn(self.EMB, self.page())

    def test_full_run_still_searches(self):
        calls = self.run_main(["--boards-file", "IDS"])
        self.assertEqual(calls["og"], 1)
        self.assertEqual(calls["measure_limit"], [None])
        self.assertIn("_up_pick", self.store[FP])   # 次の --emblem-only が使う前の結果を残す
        self.assertIn("_res", self.store[FP])
        self.assertIn(f"{self.acct}/_emb", self.store[FP])   # このページに入った小元素の状態
        self.assertEqual(self.store[FP][f"{self.acct}/_urls"], user_pages.story_keys({"x": {"pending": [{"url": "https://n.example/1"}]}}))   # 載せた記事

    def test_first_page_is_collecting_plus_emblem(self):
        # 一度もページを作っていない人（登録した直後）：置く物が無いより「集めています」＋小元素のページを、同じ速い道で
        self.write_emblem()
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual((calls["og"], calls["measure_limit"], calls["pick"]), (0, [], 0))
        self.assertIn(self.EMB, self.page())
        self.assertIn(user_pages.render.SETTINGS_JA["collecting"], self.page())
        self.assertNotIn("https://n.example/1", self.page())

    def _prev_page(self):
        self.added = "2026-01-01T00:00:00Z"
        self.run_main(["--boards-file", "IDS"])
        self.assertIn("https://n.example/1", self.page())
        return self.page()

    def test_story_restored_to_original_url_is_kept(self):
        """見直し 6：前のページの後に記事の網址が原文に戻った（Google の網址は gurl に残る）・AI 編集の記事が別の網址になった、でも前の記事として残す。"""
        g = "https://news.google.com/rss/articles/abc"
        self.added = "2026-01-01T00:00:00Z"
        self.more = [{"title": "包みの記事", "url": g, "summary": "", "source": "s", "date": "2026-11-19"}]
        self.run_main(["--boards-file", "IDS"])
        self.assertIn("包みの記事", self.page())
        self.more = [{"title": "包みの記事", "url": "https://origin.example/a", "gurl": g, "summary": "", "source": "s", "date": "2026-11-19"}]   # 原文に戻った
        self.write_emblem()
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertIn("包みの記事", self.page())
        self.assertIn("https://n.example/1", self.page())
        got, cut = user_pages.keep_known({"x": {"stories": [{"url": "https://ai.example/x", "refs": ["https://n.example/1"]}]}},
                                         user_pages.story_keys({"x": {"pending": [{"url": "https://n.example/1"}]}}))
        self.assertEqual((len(got["x"]["stories"]), cut), (1, 0))   # AI 編集の記事は refs で当たる

    def test_unreadable_fingerprints_place_nothing(self):
        """見直し 1(a)：指紋が一瞬読めない回に作ると known が空になり、前からある記事まで全部消えたページを置いていた → 誰のページも置かない。"""
        before = self._prev_page()
        self.write_emblem()
        self.fps_down = True
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(self.page(), before)

    def test_page_without_story_record_is_left_to_the_normal_run(self):
        """見直し 1(b)(c)：前のページはあるが載せた記事の記録（_urls）が無い（記録を残す前の回が置いた・その人のふつうの回が失敗した）→ 置かない。"""
        before = self._prev_page()
        del self.store[FP][f"{self.acct}/_urls"]
        self.write_emblem()
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(self.page(), before)
        self.assertIn("https://n.example/1", self.page())

    def test_collecting_page_only_for_people_without_any_page(self):
        """「集めています」だけのページを置いてよいのは、index.html の指紋が無い人（一度もページが無い人）だけ。"""
        self.write_emblem()
        self.run_main(["--boards-file", "IDS", "--emblem-only"])   # 一度も無い：置く
        self.assertIn(user_pages.render.SETTINGS_JA["collecting"], self.page())
        self.store[FP].pop(f"{self.acct}/_urls", None)
        self.store[FP][f"{self.acct}/index.html"] = "x"            # ページはあるが記録が無い：置かない
        self.store.pop(f"/storage/v1/object/pages/{self.acct}/index.html")
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(self.page(), "")

    def test_previous_page_plus_emblem(self):
        """店長の決め（直し 2 回目 F2）：前のページを作る → 新しい版面と新しい記事を足す → 小元素だけの回 →
        前の記事と写真が全部ある＋新しい版面は「集めています」＋小元素。前のページより写真・記事が減らない。"""
        import re
        self.added = "2026-01-01T00:00:00Z"
        self.more = [{"title": "写真の記事", "url": "https://n.example/p", "summary": "", "source": "s", "date": "2026-11-19", "image": "https://img.example/p.jpg"}]
        self.run_main(["--boards-file", "IDS"])
        before = self.page()
        old = set(re.findall(r"https://(?:n|img)\.example/[\w./]+", before))
        self.assertIn("https://img.example/p.jpg", old)
        self.more.append({"title": "あとの記事", "url": "https://n.example/late", "summary": "", "source": "s", "date": "2026-11-19"})
        emb6 = "https://e.example/new.webp"
        self.new_board = {"config": {"emblem": [{"image": emb6, "subject": "b"}], "emblem_state": {"have": 1, "at": 3}},
                          "pending": [{"title": "新しい版面の記事", "url": "https://n.example/new1", "summary": "", "source": "s", "date": "2026-11-19"}]}
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        after = self.page()
        self.assertEqual((calls["og"], calls["pick"], calls["resolve"], calls["measure_limit"]), (0, 0, 0, []))   # 網に出ない
        self.assertLessEqual(old, set(re.findall(r"https://(?:n|img)\.example/[\w./]+", after)))   # 前の記事と写真は全部ある
        self.assertNotIn("https://n.example/late", after)
        self.assertNotIn("https://n.example/new1", after)
        self.assertIn(emb6, after)                                            # 新しい版面の小元素
        self.assertIn(user_pages.render.SETTINGS_JA["collecting"], after)     # 新しい版面は「集めています」
        self.assertIn("新しい版面", after)

    def test_emblem_written_while_feed_measures_reaches_the_page(self):
        # 見直しの順：feed（--recent）が先に組む → 写真の測りの間に速い道が小元素を書く → feed が置く → 小元素だけの回
        self.run_main(["--recent", "3600"], during_measure=self.write_emblem)
        self.assertIn(self.EMB, self.page())   # 置く直前に design_moved を見るので、feed のページに小元素が入る
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertIn(self.EMB, self.page())

    def test_feed_page_without_the_emblem_is_replaced(self):
        # feed が置く直前の確かめもすり抜けた（確かめのあと・置く前に書かれた）：feed のページには小元素が無い。
        # 小元素だけの回は「ほかの回が先に置いた」でも、そのページの小元素の状態（<account>/_emb）が古ければ置く
        self.run_main(["--boards-file", "IDS"])
        state = {"n": 0}

        def late_write(follows, get):
            state["n"] += 1
            if state["n"] == 1:
                self.write_emblem()
            return False
        self.run_main(["--recent", "3600"], moved=late_write)
        self.assertNotIn(self.EMB, self.page())
        self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertIn(self.EMB, self.page())

    def test_emblem_only_skips_when_newer_page_has_the_emblem(self):
        self.run_main(["--boards-file", "IDS"])
        self.write_emblem()
        orig = user_pages._fresh_fps
        put = {}

        def newer(fp_path):   # 作っている間にほかの回が、同じ小元素の入ったページを置いた
            cur = orig(fp_path)
            if cur is not None and not put:
                put["x"] = 1
                cur[f"{self.acct}/index.html"] = "other"
                cur[f"{self.acct}/_emb"] = user_pages.emblem_stamps([{"boards": {"id": 5, "config": self.db["config"]}}])
            return cur
        before = self.page()
        with mock.patch.object(user_pages, "_fresh_fps", newer):
            self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(self.page(), before)   # 置かない（そちらが新しい）


if __name__ == "__main__":
    unittest.main()
