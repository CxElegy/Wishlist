"""防盗链の写真（SAVED）をお客さまの版面でも使う（2026-11-19 店長の決定 1A）。ネット・Supabase には出ない（取る所・置く所を差し替える）。

- 記事集め（userfeed.Media）は SAVED を捨てず、記事に img_ref（Referer に渡す記事の頁）を付ける（tests/test_userfeed.py）。
- user_pages.mask_saved：置き場に入るまでは画面に出さない・入ったら置き場の網址に替える・列（imgs.json）に [網址, Referer]。
- user_pages.main：一部の人の回（--recent）でも列に足す・ほかの人の分を消さない。
- photo_store：[網址, Referer] は Referer 付きで取って置く・上限に近いときはお客さまの分を足さない・公開のファイルに網址・題を出さない。
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import images  # noqa: E402
import library  # noqa: E402
import photo_store as P  # noqa: E402
import user_pages  # noqa: E402

IMG = "https://hard.example/pic/secret-photo.jpg"
REF = "https://hard.example/news/himitsu-kiji-777"
TITLE = "お客さまだけの版面の題"


def og_image_fill(rows, og, read):
    """og_image.fill の本物（images.page の代わりに読んだ網址を数える）。"""
    import og_image
    return og_image.fill(rows, og, page=lambda u: read.append(u) or images.Page(u, False, "x"), check=lambda u: (False, "x"), log=lambda _m: None)


class Mask(unittest.TestCase):
    def setUp(self):
        on = list(P._ON)
        cache = list(P._CACHE)
        self.addCleanup(lambda: (P._ON.__setitem__(slice(None), on), P._CACHE.__setitem__(slice(None), cache)))
        P._ON[:] = [True]
        P._CACHE[:] = [{"base": "https://s.example", "p": {}, "x": {}, "stat": {}}]

    def brows(self):
        return {"a": {"stories": [{"title": TITLE, "url": REF, "image": IMG, "img_ref": REF}, {"url": "https://ok.example/1", "image": "https://ok.example/1.jpg"}],
                      "pending": [{"url": REF + "2", "image": IMG + "2", "img_ref": REF + "2"}], "_src": ("bs", 7)}}

    def test_not_shown_until_stored_then_stored_url(self):
        b = self.brows()
        want = {}
        out = user_pages.mask_saved(b, want)
        self.assertIsNone(out["a"]["stories"][0]["image"])                       # 置き場に入るまでは出さない（403 にしない）
        self.assertEqual(out["a"]["stories"][1]["image"], "https://ok.example/1.jpg")   # ふつうの写真はそのまま
        self.assertIsNone(out["a"]["pending"][0]["image"])
        self.assertEqual(want[P.key(IMG)], [IMG, REF])                           # 置き場の列には [網址, Referer]
        self.assertEqual(b["a"]["stories"][0]["image"], IMG)                     # 共有の行・書き戻す行は書き換えない
        P._CACHE[0]["p"][P.key(IMG)] = {"at": 1, "b": 10}                        # photo_store が置いた
        out = user_pages.mask_saved(self.brows(), {})
        self.assertTrue(out["a"]["stories"][0]["_wait"])                         # 見直し 6：Pages に写るまで（manifest に無い）は待つ（404 にしない）
        out = user_pages.mask_saved(self.brows(), {}, {P.name(P.key(IMG))})
        self.assertEqual(out["a"]["stories"][0]["image"], f"{P.PAGES_BASE}/{P.key(IMG)}-800.webp")
        self.assertNotIn("img_ref", out["a"]["stories"][0])

    def test_waiting_photo_is_not_a_photoless_card(self):
        """見直し 2：置き場待ちの防盗链の写真の記事は、写真なしとして整理待ちへ回る（写真のないカードとして版面に残さない・B7）。
        og_image.fill・find_images は探し直さない。数の 1 行に「置き場待ち」。"""
        b = user_pages.mask_saved(self.brows(), {})
        read = []
        t = {}
        user_pages.photo_tally(b, {}, t, fill=lambda rows, og, **k: og_image_fill(rows, og, read))
        self.assertEqual(read, [])                                                   # og のページを読みに行かない
        self.assertEqual([s.get("url") for s in b["a"]["stories"]], ["https://ok.example/1"])   # カードには写真のある記事だけ
        self.assertIn(REF, [s.get("url") for s in b["a"]["pending"]])
        self.assertEqual(t["wait"], 1)
        self.assertIn("置き場待ち 1 本", user_pages.tally_line(t))
        # 写真が 1 枚も無い版面（demote が動かさない）でも、find_images は置き場待ちを探し直さない
        only = user_pages.mask_saved({"a": {"stories": [{"title": TITLE, "url": REF, "image": IMG, "img_ref": REF}]}}, {})
        picked = []
        with mock.patch.object(images, "pick", lambda *a, **k: picked.append(a) or images.Result()):
            issue = user_pages.user_issue([{"name": "A", "section": "其他"}], None, only, 1e12, {})
            only["a"]["edited"] = True
            user_pages.user_issue([{"name": "A", "section": "其他"}], None, only, 1e12, {})
        self.assertEqual(picked, [])
        self.assertIsNone(issue["items"][0]["stories"][0]["image"])

    def test_page_html_never_has_the_hard_url(self):
        """作ったページの HTML に、置き場に入っていない防盗链の写真の網址が出ない（src にも落ち先にも）。"""
        import digest
        settings, shop = digest.load_config()
        rows = user_pages.mask_saved(self.brows(), {})
        prefs = {"picks": [{"name": "A", "sec": "其他"}]}
        h = user_pages.build("t@example.com", prefs, rows, shop, None, settings, 0, {})
        self.assertNotIn("hard.example/pic", h)
        P._CACHE[0]["p"][P.key(IMG)] = {"at": 1, "b": 10}
        h = user_pages.build("t@example.com", prefs, user_pages.mask_saved(self.brows(), {}, {P.name(P.key(IMG))}), shop, None, settings, 0, {})
        self.assertNotIn("hard.example/pic", h)
        self.assertIn(f"{P.key(IMG)}-800.webp", h)

    def test_inherited_and_edited_keep_referer(self):
        pend = [{"title": "t", "url": REF, "image": IMG, "img_ref": REF}]
        st = library.edited_stories(pend, [{"headline": "H", "refs": [1]}], "fp", "at")
        self.assertEqual(st[0]["img_ref"], REF)
        st = library.edited_stories([{"title": "t", "url": REF}], [{"headline": "H", "refs": [1]}], "fp", "at")
        rows = user_pages.board_rows([{"boards": {"id": 7, "name": "A"}}], {7: {"stories": st, "pending": pend}}, {})
        self.assertEqual((rows["a"]["stories"][0]["image"], rows["a"]["stories"][0]["img_ref"]), (IMG, REF))

    def test_merge_keeps_others(self):
        old = ["https://o.example/1.jpg", ["https://o.example/2.jpg", "https://o.example/n2"], "junk", 3,
               {"u": "https://o.example/old.jpg", "d": 100}, {"u": "https://o.example/new.jpg", "d": 195}]
        out = user_pages.merge_imgs(old, {P.key(IMG): [IMG, REF]}, today=200, keep=14)
        self.assertEqual(sorted(x["u"] for x in out), sorted(["https://o.example/1.jpg", "https://o.example/2.jpg", "https://o.example/new.jpg", IMG]))
        self.assertIn({"u": IMG, "r": REF, "d": 200}, out)                       # 今回の分は今日の日で
        self.assertIn({"u": "https://o.example/new.jpg", "d": 195}, out)          # 前の分は最後に見た日のまま
        self.assertEqual([P.user_entry(x) for x in out if x["u"] == IMG], [(IMG, REF)])   # photo_store が読める形
        self.assertEqual(P.user_entry(["https://o.example/2.jpg", "https://o.example/n2"]), ("https://o.example/2.jpg", "https://o.example/n2"))   # 前の形も読む

    def test_list_shrinks_even_if_someone_always_fails(self):
        """見直し 5：毎回失敗する人がいて「前の列に足す」回が続いても、最後に見てから 14 日を過ぎた分は外れる。全員の回は空でも []。"""
        lst = [{"u": "https://gone.example/a.jpg", "d": 100}]
        for day in range(101, 120):
            lst = user_pages.merge_imgs(lst, {P.key("https://live.example/b.jpg"): "https://live.example/b.jpg"}, today=day, keep=14)
        self.assertEqual([x["u"] for x in lst], ["https://live.example/b.jpg"])
        self.assertEqual(user_pages.merge_imgs([], {}), [])


class MainPartial(unittest.TestCase):
    def test_recent_run_adds_to_list_without_erasing(self):
        """--recent（足した人だけ）の回でも、その人の写真を列に足す。前の列（ほかの人の分）は消さない。"""
        prev = ["https://other.example/keep.jpg"]
        written = []

        def fake(path, data=None, method="GET", ctype=""):
            if path.endswith("_fp/all.json"):
                return {} if method == "GET" else ""
            if "userfeed_users" in path:
                return [{"email": "a@example.com", "prefs": {"picks": [{"name": "A", "added_at": "2999-01-01T00:00:00+00:00"}]}}]
            if path.endswith("_fp/imgs.json"):
                if method == "GET":
                    return list(prev)
                written.append(json.loads(data))
                return ""
            if "/storage/" in path:
                return ""
            if path.startswith("/rest/v1/user_boards"):
                return [{"item": "A", "sec": "其他", "state": "ok", "checked_at": None,
                         "stories": [{"title": "t", "url": REF, "image": IMG, "img_ref": REF}, {"title": "u", "url": "https://ok.example/1", "image": "https://ok.example/1.jpg"}]}]
            return []
        with mock.patch.object(user_pages, "_supa", fake), mock.patch.object(user_pages.digest, "load_config", lambda: ({}, [])), \
                mock.patch.object(user_pages.photo_bands, "measure", lambda *a, **k: 0), mock.patch.object(user_pages.og_image, "fill", lambda *a, **k: 0), \
                mock.patch.object(user_pages, "build", lambda *a, **k: '<html><section><img src="https://ok.example/1.jpg" data-e="s"></section></html>'), \
                mock.patch.object(user_pages.render, "photo_opens", None, create=True), mock.patch.object(user_pages.photo_store, "published", lambda: set()):
            user_pages.main(["--recent", "3600"])
        self.assertEqual(len(written), 1)
        got = written[0]
        self.assertIn("https://other.example/keep.jpg", [x["u"] for x in got])    # ほかの人の分は残る
        self.assertIn((IMG, REF), [P.user_entry(x) for x in got])                # 防盗链の写真は Referer と一緒に
        self.assertIn("https://ok.example/1.jpg", [x["u"] for x in got])


class Small(unittest.TestCase):
    """見直し 6〜12 の小さい直し。"""

    def test_edited_picks_referer_from_any_ref(self):   # 8
        pend = [{"title": "t1", "url": "https://x.example/1", "image": "https://x.example/1.jpg"},
                {"title": "t2", "url": REF, "image": IMG, "img_ref": REF}]
        st = library.edited_stories(pend, [{"headline": "H", "image": IMG, "refs": [1, 2]}], "fp", "at")
        self.assertEqual((st[0]["image"], st[0]["img_ref"]), (IMG, REF))
        st = library.edited_stories(pend, [{"headline": "H", "refs": [1, 2]}], "fp", "at")
        self.assertNotIn("img_ref", st[0])   # 1 本目のふつうの写真なら付けない

    def test_sibling_page_is_the_referer(self):   # 9
        sib_url = "https://sib.example/news/2"
        pages = {"https://main.example/1": images.Page("https://main.example/1", False, "原文 HTTP 403 403", status=403),
                 sib_url: images.Page(sib_url, True, og=["https://sib.example/pic.jpg"])}
        with mock.patch.object(images, "page", lambda u: pages.get(u) or images.Page(u, False, "x")), \
                mock.patch.object(images, "check", lambda u, referer=None: (True, "800×450")), \
                mock.patch.object(images, "_hard", {"https://sib.example/pic.jpg"}), \
                mock.patch.object(images, "syndicated_candidates", lambda *a, **k: ([], "")), mock.patch.object(images, "author_seen", lambda: set()):
            e = images.sources.Entry(title="題", url="https://main.example/1", published=None, source="")
            s = images.sources.Entry(title="題", url=sib_url, published=None, source="", link=sib_url)
            res = images.pick(None, [e], e.url, siblings=[s])
        self.assertEqual((res.image, res.referer), ("https://sib.example/pic.jpg", sib_url))
        self.assertIn(images.SAVED, res.source)

    def test_shop_boards_are_left_out(self):   # 10
        brows = {"gta6": {"stories": [{"url": "https://s.example/1"}], "_src": ("bs", 1)}, "mine": {"stories": [{"url": "https://m.example/1"}], "_src": ("bs", 2)}}
        own, shop = user_pages.split_shop(brows, [{"name": "GTA 6"}])
        self.assertEqual((sorted(own), sorted(shop)), (["mine"], ["gta6"]))
        read = []
        user_pages.photo_tally(own, {}, {}, fill=lambda rows, og, **k: og_image_fill(rows, og, read))
        self.assertEqual(read, ["https://m.example/1"])   # 店長の版面に og の時間を使わない

    def test_og_deadline_inside_a_page(self):   # 12
        import og_image
        import time
        p = images.Page("https://n.example/1", True, og=["https://i.example/a.jpg", "https://i.example/b.jpg"])
        seen = []

        def check(u):
            seen.append(u)
            return False, "图片 HTTP 404"
        self.assertEqual(og_image.read_one("https://n.example/1", page=lambda u: p, check=check, hard=set(), deadline=time.monotonic() - 1), (None, "carry"))
        self.assertEqual(seen, [])

    def test_hard_referer_url_not_in_page(self):   # 試験の穴：記事の網址と別の網址を img_ref にした見本
        import digest
        ref = "https://other-site.example/gallery/secret-referer-page"
        b = {"a": {"stories": [{"title": "t", "url": "https://news.example/a", "image": IMG, "img_ref": ref},
                               {"title": "u", "url": "https://ok.example/1", "image": "https://ok.example/1.jpg"}]}}
        settings, shop = digest.load_config()
        for pub in (set(), {P.name(P.key(IMG))}):
            on, cache = list(P._ON), list(P._CACHE)
            try:
                P._ON[:] = [True]
                P._CACHE[:] = [{"base": "https://s.example", "p": {P.key(IMG): {"at": 1, "b": 1}}, "x": {}, "stat": {}}]
                h = user_pages.build("t@example.com", {"picks": [{"name": "A", "sec": "其他"}]}, user_pages.mask_saved(b, {}, pub), shop, None, settings, 0, {})
            finally:
                P._ON[:], P._CACHE[:] = on, cache
            self.assertIn("ok.example/1.jpg", h)   # 版面は描かれている（空のページで通っていない）
            self.assertNotIn("secret-referer-page", h)
            self.assertNotIn("hard.example/pic", h)


class MainWriteBack(unittest.TestCase):
    def test_main_fill_then_write_back(self):
        """試験の穴：main の中の og_image.fill → write_back を、取る層（images.page・images.check）だけ差し替えて通す。"""
        row = {"item": "A", "sec": "其他", "state": "ok", "checked_at": "2026-11-19T09:00:00+00:00",
               "stories": [{"title": "t", "url": "https://n.example/1"}, {"title": "u", "url": "https://ok.example/2", "image": "https://ok.example/2.jpg"}]}
        patches, alljson = [], []

        def fake(path, data=None, method="GET", ctype=""):
            if path.endswith("_fp/all.json"):
                if method != "GET":
                    alljson.append(json.loads(data))
                return {} if method == "GET" else ""
            if "userfeed_users" in path:
                return [{"email": "a@example.com", "prefs": {"picks": [{"name": "A"}]}}]
            if path.endswith("_fp/imgs.json"):
                return [] if method == "GET" else ""
            if "/storage/" in path:
                return ""
            if path.startswith("/rest/v1/user_boards"):
                if method == "PATCH":
                    patches.append((path, json.loads(data)))
                    return ""
                return [json.loads(json.dumps(row))]
            return []
        page = images.Page("https://n.example/1", True, og=["https://img.example/og1.jpg"])
        with mock.patch.object(user_pages, "_supa", fake), mock.patch.object(user_pages.digest, "load_config", lambda: ({}, [])), \
                mock.patch.object(user_pages.photo_bands, "measure", lambda *a, **k: 0), mock.patch.object(user_pages, "build", lambda *a, **k: "<html></html>"), \
                mock.patch.object(user_pages.render, "photo_opens", None, create=True), mock.patch.object(user_pages.photo_store, "published", lambda: set()), \
                mock.patch.object(images, "page", lambda u: page if u == page.url else images.Page(u, False, "x")), \
                mock.patch.object(images, "check", lambda u, referer=None: (True, "800×450")):
            user_pages.main([])
        self.assertEqual(len(patches), 1)
        self.assertIn("checked_at=eq.2026-11-19T09%3A00%3A00%2B00%3A00", patches[0][0])
        self.assertEqual(patches[0][1]["stories"][0]["image"], "https://img.example/og1.jpg")
        self.assertEqual(alljson[-1]["_og"]["https://n.example/1"]["img"], "https://img.example/og1.jpg")   # 覚えにも入る


class EmblemOnlySame(unittest.TestCase):
    """合わせ（#1058 の --emblem-only）：小元素だけの回が置くページは、ふつうの回と同じ中身（AI 編集の記事が整理待ちの写真を引き継ぐ・
    置き場に入った防盗链の写真だけ出す・置き場待ちは整理待ちへ）。小元素だけの回は網に出ず、記事に書き戻さず、imgs.json を書かない。"""
    EMAIL = "test-y@example.com"

    def test_same_page_and_no_writes(self):
        acct = user_pages.account_of(self.EMAIL)
        u1, u2, u3 = "https://n.example/1", REF, "https://n.example/3"
        latest = [{"board_id": 5, "day": "2026-11-19", "updated_at": "2026-11-19T10:00:00+00:00",
                   "stories": [{"headline": "H1", "url": u1, "refs": [u1], "image": None, "weight": "hero", "_fp": "f", "_at": "2999-01-01T00:00:00+00:00"},
                               {"headline": "H3", "url": u3, "refs": [u3], "image": "https://img.example/3.jpg", "weight": "normal", "_fp": "f", "_at": "x"}],
                   "pending": [{"title": "t1", "url": u1, "image": "https://img.example/1.jpg"},
                               {"title": "t2", "url": u2, "image": IMG, "img_ref": REF},
                               {"title": "t3", "url": u3, "image": "https://img.example/3.jpg"},
                               {"title": "t4", "url": "https://n.example/4"}]}]
        store, writes, counts = {user_pages.IMGS_PATH: []}, [], {"og": 0, "pick": 0}   # 一部の回は前の列を読んでから足す（読めない回は書かない）

        def supa(path, data=None, method="GET", ctype="application/json"):
            if "rpc/userfeed_users" in path:
                return [{"email": self.EMAIL, "prefs": {"picks": [{"name": "自分の版面", "sec": "生活"}]}}]
            if path.startswith("/storage/"):
                if method == "POST":
                    writes.append(path)
                    store[path] = json.loads(data) if ctype.startswith("application/json") else data
                    return {}
                if path in store:
                    return json.loads(json.dumps(store[path])) if isinstance(store[path], (dict, list)) else store[path]
                raise OSError("404")
            if method == "PATCH":
                writes.append(path)
                return ""
            if "follows?board_id=in." in path:
                return [{"account": acct}]
            if "follows?account" in path:
                return [{"pos": 0, "section": "生活", "subs": {}, "size": "M", "boards": {"id": 5, "name": "自分の版面", "config": {}}}]
            if "board_stories" in path:
                return json.loads(json.dumps(latest))
            if "boards?id=in." in path:
                return [{"id": 5, "emblem_state": None}]
            return []
        pages = []
        with tempfile.TemporaryDirectory() as d:
            ids = pathlib.Path(d) / "ids.json"
            ids.write_text("[5]")
            for args in (["--boards-file", str(ids)], ["--boards-file", str(ids), "--emblem-only", "--force"]):
                writes.clear()
                with mock.patch.object(user_pages, "_supa", supa), mock.patch.object(user_pages.photo_store, "published", lambda: set()), \
                        mock.patch.object(images, "pick", lambda *a, **k: counts.__setitem__("pick", counts["pick"] + 1) or images.Result()), \
                        mock.patch.object(images, "page", lambda u: counts.__setitem__("og", counts["og"] + 1) or images.Page(u, True)), \
                        mock.patch.object(user_pages.sources, "resolve_url", lambda u, tries=None: u), \
                        mock.patch.object(user_pages.render, "photo_opens", lambda u: True), mock.patch.object(user_pages.render, "OPENS", None), \
                        mock.patch.object(user_pages.photo_bands, "measure", lambda *a, **k: 0):
                    before = dict(counts)
                    user_pages.main(args)
                pages.append(store[f"/storage/v1/object/pages/{acct}/index.html"])
                if "--emblem-only" in args:
                    self.assertEqual(counts, before)   # 網に出ない（og の読み・写真探し 0）
                    self.assertFalse([w for w in writes if "imgs.json" in w or w.startswith("/rest/")])   # 書き戻し・imgs.json なし
                else:
                    self.assertTrue(any("imgs.json" in w for w in writes))
        self.assertEqual(pages[0], pages[1])                     # ふつうの回と同じ中身
        h = pages[0].decode("utf-8")
        self.assertIn("https://img.example/1.jpg", h)            # AI 編集の記事が整理待ちの写真を引き継ぐ
        self.assertNotIn("hard.example/pic", h)                  # 置き場に入っていない防盗链の写真は出さない


class MainFull(unittest.TestCase):
    def test_full_run_without_photos_writes_empty_list(self):
        """見直し 5(b)：全員作れた回で写真が 0 なら [] を書く（前の列を残さない）。"""
        written = []

        def fake(path, data=None, method="GET", ctype=""):
            if path.endswith("_fp/all.json"):
                return {} if method == "GET" else ""
            if "userfeed_users" in path:
                return [{"email": "a@example.com", "prefs": {}}]
            if path.endswith("_fp/imgs.json"):
                if method != "GET":
                    written.append(json.loads(data))
                return ["https://stale.example/x.jpg"]
            return "" if "/storage/" in path else []
        with mock.patch.object(user_pages, "_supa", fake), mock.patch.object(user_pages.digest, "load_config", lambda: ({}, [])), \
                mock.patch.object(user_pages.photo_bands, "measure", lambda *a, **k: 0), mock.patch.object(user_pages, "build", lambda *a, **k: "<html></html>"), \
                mock.patch.object(user_pages.render, "photo_opens", None, create=True), mock.patch.object(user_pages.photo_store, "published", lambda: set()):
            user_pages.main([])
        self.assertEqual(written, [[]])


class Store(unittest.TestCase):
    def env(self, d, imgs, p=None):
        (d / "i.html").write_text('<img src="https://x.example/a.jpg" data-e="s">', encoding="utf-8")
        st = d / "s.json"
        st.write_text(json.dumps({"base": "https://s.example", "p": p or {}}), encoding="utf-8")
        saved = (P.user_imgs, P.upload, P.remove)
        P.user_imgs = lambda b, k: imgs
        P.upload = lambda *a, **k: None
        P.remove = lambda *a, **k: None
        self.addCleanup(lambda: (setattr(P, "user_imgs", saved[0]), setattr(P, "upload", saved[1]), setattr(P, "remove", saved[2])))
        return st

    def test_saved_fetched_with_referer_and_public_file_has_no_urls(self):
        import io
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (900, 500), (200, 30, 30)).save(b, "JPEG")
        got = []

        def fake_fetch(url, limit, referer=None):
            got.append((url, referer))
            ok = referer == REF or "x.example" in url
            return images.Fetched(200 if ok else 403, {"content-type": "image/jpeg"}, b.getvalue() if ok else b"")
        with tempfile.TemporaryDirectory() as d, mock.patch.object(images, "_fetch", fake_fetch):
            d = pathlib.Path(d)
            st = self.env(d, [(IMG, REF), ("https://u.example/plain.jpg", None)])
            plain = []
            real_fetch = P.fetch

            def fetch(url, referer=None):
                if referer:
                    return real_fetch(url, referer)
                plain.append(url)
                return b.getvalue()
            with mock.patch.object(P, "fetch", fetch):
                s = P.run(site=d, path=st, base="https://s.example", keyv="k")
            self.assertEqual(got, [(IMG, REF)])                     # 防盗链の写真だけ Referer 付きで（店長と同じ images._fetch）
            self.assertIn("https://u.example/plain.jpg", plain)     # ふつうの写真の取り方は今までどおり
            self.assertIn(P.key(IMG), json.loads(st.read_text())["p"])
            self.assertEqual(s["saved"], 1)
            text = st.read_text(encoding="utf-8")                   # state/photo_store.json（公開のリポジトリ）
            for bad in (IMG, REF, "hard.example", TITLE, "himitsu"):
                self.assertNotIn(bad, text)

    def test_referer_fetch_rejects_non_image(self):
        with mock.patch.object(images, "_fetch", lambda u, l, r=None: images.Fetched(200, {"content-type": "text/html"}, b"<html>")):
            self.assertIsNone(P.fetch(IMG, REF))

    def test_shop_photo_keeps_shop_fetch(self):   # 7
        """店長の網页にも載っている写真は、お客さまの列に Referer 付きであっても店長の取り方（Referer なし）のまま。"""
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            shop_img = "https://x.example/a.jpg"
            st = self.env(d, [(shop_img, REF)])
            calls = []
            with mock.patch.object(P, "fetch", lambda *a: calls.append(a) or None):
                s = P.run(site=d, path=st, base="https://s.example", keyv="k")
            self.assertEqual(calls, [(shop_img,)])
            self.assertEqual(s["saved"], 0)

    def test_near_cap_skips_customer_photos(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            big = {P.key(f"https://f.example/{i}"): {"at": P.day(), "b": P.CAP // 4, "cc": 1, "c": "#000", "m": []} for i in range(4)}
            st = self.env(d, [(IMG, REF)], p=big)
            calls = []
            with mock.patch.object(P, "fetch", lambda *a: calls.append(a) or None):
                s = P.run(site=d, path=st, base="https://s.example", keyv="k")
            self.assertEqual(s["user_skip"], 1)
            self.assertNotIn((IMG, REF), calls)
            self.assertIn(("https://x.example/a.jpg",), calls)    # 店長の写真は足す


if __name__ == "__main__":
    unittest.main()
