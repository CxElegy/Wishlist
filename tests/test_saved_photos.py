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
        self.assertEqual(out["a"]["stories"][0]["image"], f"{P.PAGES_BASE}/{P.key(IMG)}-800.webp")
        self.assertNotIn("img_ref", out["a"]["stories"][0])

    def test_page_html_never_has_the_hard_url(self):
        """作ったページの HTML に、置き場に入っていない防盗链の写真の網址が出ない（src にも落ち先にも）。"""
        import digest
        settings, shop = digest.load_config()
        rows = user_pages.mask_saved(self.brows(), {})
        prefs = {"picks": [{"name": "A", "sec": "其他"}]}
        h = user_pages.build("t@example.com", prefs, rows, shop, None, settings, 0, {})
        self.assertNotIn("hard.example/pic", h)
        P._CACHE[0]["p"][P.key(IMG)] = {"at": 1, "b": 10}
        h = user_pages.build("t@example.com", prefs, user_pages.mask_saved(self.brows(), {}), shop, None, settings, 0, {})
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
        old = ["https://o.example/1.jpg", ["https://o.example/2.jpg", "https://o.example/n2"], "junk", 3]
        out = user_pages.merge_imgs(old, {P.key(IMG): [IMG, REF]})
        self.assertEqual(len(out), 3)                                            # 前の 2 つ＋今回の 1 つ（読めない形は捨てる）
        self.assertIn([IMG, REF], out)
        self.assertIn("https://o.example/1.jpg", out)


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
        self.assertIn("https://other.example/keep.jpg", got)    # ほかの人の分は残る
        self.assertIn([IMG, REF], got)                         # 防盗链の写真は Referer と一緒に
        self.assertIn("https://ok.example/1.jpg", got)


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
