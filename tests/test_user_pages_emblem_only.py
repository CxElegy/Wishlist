"""小元素だけの作り直し（user_pages.py --boards-file F --emblem-only、2026-11-19 店長「新しい版面を足したら小元素が出るまで 5 分未満」）。
前は 1 人分 92 秒（記事の代表の写真を読み直す・写真の余白と主役を測り直す・「気になるかも？」の跳转を 1 本ずつ戻す・頭の写真を 1 本ずつ聞く）。
重い段を呼ばず、前の回の結果（pages/_fp/all.json）で同じページを作る。網・DB なし。"""
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


class FindImages(unittest.TestCase):
    def stories(self):
        return [{"headline": "a", "url": "https://n.example/1"}, {"headline": "b", "url": "https://n.example/2"}]

    def test_cache_only_does_not_search(self):
        calls = []
        cache = {"https://n.example/1": {"img": "https://img/1.jpg", "at": 0}, "https://n.example/2": {"img": "", "at": 0}}
        with mock.patch.object(user_pages.digest, "find_image", lambda *a: calls.append(a) or "x"):
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
        with mock.patch.object(user_pages.digest, "find_image", pick):
            user_pages.find_images(self.stories(), 9e18, cache, now=1000)
        self.assertEqual(cache, {"https://n.example/1": {"img": "https://img/1.jpg", "at": 1000}})   # 読めなかったものは覚えない（次の回にまた探す）

    def test_full_run_retries_a_miss_after_a_while(self):
        # images.pick は断られた・20 秒で止まった時も None：「無い」を永久に信じると、その記事は二度と探されず整理待ちのまま
        calls = []
        cache = {"https://n.example/1": {"img": "", "at": 1000}}
        st = [{"headline": "a", "url": "https://n.example/1"}]
        with mock.patch.object(user_pages.digest, "find_image", lambda *a: calls.append(a) or "https://img/new.jpg"):
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
        n = og_image.fill(rows, {"https://n.example/1": "https://img/og1.jpg"}, fetch=lambda u: seen.append(u) or "", log=lambda *a: None, limit=0)
        self.assertEqual((n, seen), (0, []))
        self.assertEqual(rows["x"]["stories"][0]["image"], "https://img/og1.jpg")   # 前の結果は付く

    def test_bands_limit(self):
        seen = []
        with mock.patch.object(photo_bands, "bands", lambda d: []), mock.patch.object(photo_bands, "mass_css", lambda d: ""), \
                mock.patch.object(photo_bands, "text_box", lambda d: None), mock.patch.object(photo_bands, "people_box", lambda d: None), \
                mock.patch.object(photo_bands, "segments", lambda d: []):
            photo_bands.measure([f"https://p/{i}.jpg" for i in range(40)], {}, lambda u: seen.append(u) or b"x", log=lambda *a: None, limit=user_pages.ONLY_NEW_PHOTOS)
        self.assertEqual(len(seen), user_pages.ONLY_NEW_PHOTOS)


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

    def page(self):
        return (self.store.get(f"/storage/v1/object/pages/{self.acct}/index.html") or b"").decode("utf-8")

    def run_main(self, args, during_measure=None, moved=None):
        story = {"title": "t", "url": "https://n.example/1", "summary": "", "source": "s", "date": "2026-11-19"}

        def follows():
            return [{"pos": 0, "section": "生活", "subs": {}, "size": "M",
                     "boards": {"id": 5, "name": "自分の版面", "config": json.loads(json.dumps(self.db["config"]))}}]

        def supa(path, data=None, method="GET", ctype="application/json"):
            if "rpc/userfeed_users" in path:
                return [{"email": self.EMAIL, "prefs": {"picks": [{"name": "自分の版面", "sec": "生活", "added_at": "2999-01-01T00:00:00Z"}]}}]
            if path.startswith("/storage/"):
                if method == "POST":
                    self.store[path] = json.loads(data) if ctype.startswith("application/json") else data
                    return {}
                if path in self.store:
                    return json.loads(json.dumps(self.store[path])) if isinstance(self.store[path], dict) else self.store[path]
                raise OSError("404")
            if "follows?board_id=in." in path:
                return [{"account": self.acct}]
            if "follows?account" in path:
                return follows()
            if "board_stories" in path:
                return [{"board_id": 5, "day": "2026-11-19", "stories": [], "pending": [story]}]
            if "boards?id=in." in path:
                return [{"id": 5, "emblem_state": self.db["config"].get("emblem_state")}]
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
                    mock.patch.object(user_pages.photo_store, "published", lambda: set()), \
                    mock.patch.object(user_pages.digest, "find_image", lambda *a: calls.__setitem__("pick", calls["pick"] + 1)), \
                    mock.patch.object(user_pages.sources, "resolve_url", lambda u, tries=None: calls.__setitem__("resolve", calls["resolve"] + 1) or u), \
                    mock.patch.object(user_pages.render, "photo_opens", lambda u: calls.__setitem__("opens", calls["opens"] + 1) or True), \
                    mock.patch.object(user_pages.og_image, "fill", lambda rows, cache, log=print, limit=None: fill(rows, cache, fetch=lambda u: calls.__setitem__("og", calls["og"] + 1) or "", log=lambda *a: None, limit=limit)), \
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
        self.assertEqual(calls["measure_limit"], [user_pages.ONLY_NEW_PHOTOS])   # 測るのは前に無い写真を 1 束まで
        self.assertIn(self.EMB, self.page())

    def test_full_run_still_searches(self):
        calls = self.run_main(["--boards-file", "IDS"])
        self.assertEqual(calls["og"], 1)
        self.assertEqual(calls["measure_limit"], [None])
        self.assertIn("_up_pick", self.store[FP])   # 次の --emblem-only が使う前の結果を残す
        self.assertIn("_res", self.store[FP])
        self.assertIn(f"{self.acct}/_emb", self.store[FP])   # このページに入った小元素の状態

    def test_person_without_previous_results_gets_a_full_build(self):
        # 一度もページを作っていない人：前の結果が無い → 写真の少ないページを置かず、この人だけふつうに作る
        self.write_emblem()
        calls = self.run_main(["--boards-file", "IDS", "--emblem-only"])
        self.assertEqual(calls["og"], 1)
        self.assertEqual(calls["measure_limit"], [None])
        self.assertIn(self.EMB, self.page())

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
