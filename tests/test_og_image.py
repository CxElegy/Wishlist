"""写真のない記事に記事のページの代表の写真を付ける（scripts/og_image.py，2026-11-08・2026-11-19 作り直し）。
ネットには出ない（images.page・images.check の代わりを渡す）。時計は now で渡す。"""
import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import images  # noqa: E402
import og_image  # noqa: E402

NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)
QUIET = dict(log=lambda _m: None)


class FakeWeb:
    """images.page・images.check の代わり（網址 → og の写真・読めない理由）。読んだ網址を数える。"""

    def __init__(self, og=None, fail=None, bad_img=None, hard=()):
        self.og, self.fail, self.bad_img, self.hard, self.read = og or {}, fail or {}, bad_img or {}, set(hard), []

    def page(self, u):
        self.read.append(u)
        if u in self.fail:
            st = int(self.fail[u].split()[-1]) if self.fail[u].split()[-1].isdigit() else None
            return images.Page(u, False, self.fail[u], status=st)
        return images.Page(u, True, og=[self.og[u]] if u in self.og else [])

    def check(self, img):
        return (False, self.bad_img[img]) if img in self.bad_img else (True, "800×450")

    def fill(self, rows, cache, now=NOW):
        return og_image.fill(rows, cache, page=self.page, check=self.check, now=now, hard=self.hard, **QUIET)


class Og(unittest.TestCase):
    def test_find_og_then_twitter_and_relative(self):
        self.assertEqual(og_image.find('<meta content="/i/a.jpg" property="og:image">', "https://n.example/x/1"), "https://n.example/i/a.jpg")
        self.assertEqual(og_image.find("<meta name='twitter:image' content='https://c.example/b.png'>"), "https://c.example/b.png")
        self.assertIsNone(og_image.find("<p>なし</p>"))

    def test_fill_only_missing_and_remembered(self):
        rows = {"版": {"stories": [{"url": "https://n.example/1", "image": None}, {"url": "https://n.example/2", "image": "https://x/y.jpg"}],
                       "pending": [{"url": "https://n.example/3"}]}}
        web = FakeWeb(og={"https://n.example/1": "https://img.example/1.jpg"})
        cache = {"https://n.example/3": {"why": "none", "at": NOW.isoformat(), "n": 2}}   # 取れなかったばかり：まだ読まない
        got = web.fill(rows, cache)
        self.assertEqual(web.read, ["https://n.example/1"])
        self.assertEqual(rows["版"]["stories"][0]["image"], "https://img.example/1.jpg")
        self.assertEqual(rows["版"]["stories"][1]["image"], "https://x/y.jpg")
        self.assertNotIn("image", rows["版"]["pending"][0])
        self.assertEqual((got["read"], got["new"], got["memo"]), (1, 1, 0))
        self.assertEqual(cache["https://n.example/1"]["img"], "https://img.example/1.jpg")
        # 次の回（別の人の同じ記事）：読まずに覚えから付ける
        web2 = FakeWeb()
        rows2 = {"b": {"stories": [{"url": "https://n.example/1"}]}}
        got2 = web2.fill(rows2, cache)
        self.assertEqual((web2.read, got2["memo"], rows2["b"]["stories"][0]["image"]), ([], 1, "https://img.example/1.jpg"))

    def test_failure_is_retried_after_a_gap_by_reason(self):
        """(4) 失敗は永久に覚えない：理由と時刻と回数を持ち、間をあけて試し直す。前の形の "" も試し直しの対象。"""
        u, v = "https://n.example/9", "https://n.example/old"
        web = FakeWeb(fail={u: "原文 HTTP 403（防机器人：cloudflare） 403"}, og={v: "https://img.example/v.jpg"})
        cache = {v: ""}   # 前の仕組みが「写真なし」として永久に覚えた形
        got = web.fill({"b": {"stories": [{"url": u}, {"url": v}]}}, cache)
        self.assertEqual(sorted(web.read), sorted([u, v]))   # 古い "" も読み直した
        self.assertEqual(cache[v]["img"], "https://img.example/v.jpg")
        self.assertEqual((cache[u]["why"], cache[u]["n"]), ("blocked", 1))
        self.assertEqual(got["why"], {"blocked": 1})
        for hours, again in ((1, False), (og_image.FIRST_RETRY_H, True)):   # 1 回目のあとは 3 時間
            w = FakeWeb(fail={u: "原文 HTTP 403 403"})
            w.fill({"b": {"stories": [{"url": u}]}}, cache, now=NOW + dt.timedelta(hours=hours))
            self.assertEqual(bool(w.read), again, hours)
        self.assertEqual(cache[u]["n"], 2)
        later = NOW + dt.timedelta(hours=og_image.FIRST_RETRY_H)
        for hours, again in ((23, False), (24, True)):   # 2 回目からは断られた＝1 日
            w = FakeWeb(fail={u: "原文 HTTP 403 403"})
            w.fill({"b": {"stories": [{"url": u}]}}, cache, now=later + dt.timedelta(hours=hours))
            self.assertEqual(bool(w.read), again, hours)

    def test_reasons_and_gaps(self):
        self.assertEqual(og_image.why_of("原文 HTTP 404", 404), "gone")
        self.assertEqual(og_image.why_of("原文 HTTP 429（限流）"), "blocked")
        self.assertEqual(og_image.why_of("原文 超时；找图超过 60 秒，停止"), "timeout")
        self.assertEqual(og_image.why_of("原文 网络错误 URLError"), "network")
        self.assertEqual(og_image.why_of("原文是未还原的 Google 新闻跳转链接；Bing / Google 新闻都没有找到带图的同一篇转载"), "wrapped")
        self.assertEqual(og_image.why_of("原文没有图片元数据，正文也没有图"), "none")
        self.assertEqual(og_image.wait_h("none", 1), og_image.FIRST_RETRY_H)
        self.assertEqual(og_image.wait_h("none", 2), 72)
        self.assertEqual(og_image.wait_h("gone", 1), 168)
        self.assertTrue(og_image.retry_due(None, "none", 5, NOW))   # 時刻の無い前の形は試す

    def test_google_wrapped_not_read_and_saved_dropped(self):
        g = "https://news.google.com/rss/articles/abc"
        s = "https://n.example/s"
        web = FakeWeb(og={s: "https://img.example/hard.jpg"}, hard={"https://img.example/hard.jpg"})
        cache = {}
        got = web.fill({"b": {"stories": [{"url": g}, {"url": s}]}}, cache)
        self.assertEqual(web.read, [s])                     # 包みのままは読まない（数だけ）
        self.assertEqual((got["wrapped"], got["saved"]), (1, 1))
        self.assertEqual(cache[s]["why"], "saved")          # 防盗链の写真は使わない
        self.assertNotIn(g, cache)

    def test_generic_logo_is_not_a_photo(self):
        u = "https://n.example/l"
        web = FakeWeb(og={u: "https://n.example/img/logo.png"})
        cache = {}
        web.fill({"b": {"stories": [{"url": u}]}}, cache)
        self.assertEqual(cache[u]["why"], "none")

    def test_prune_and_apply(self):
        cache = {"a": {"img": "https://i/a.jpg", "at": (NOW - dt.timedelta(days=30)).isoformat()},
                 "b": {"why": "none", "at": NOW.isoformat(), "n": 1}, "c": "https://i/c.jpg"}
        self.assertEqual(og_image.prune(cache, NOW), 1)
        self.assertEqual(sorted(cache), ["b", "c"])
        st = [{"url": "c"}, {"url": "b"}, {"url": "c", "image": "https://keep.jpg"}]
        self.assertEqual(og_image.apply(st, cache), [st[0]])
        self.assertEqual(st[0]["image"], "https://i/c.jpg")
        self.assertEqual(st[2]["image"], "https://keep.jpg")

    def test_log_line_has_only_counts(self):
        t = og_image.add({}, {"read": 2, "new": 1, "memo": 3, "wrapped": 1, "saved": 0, "why": {"blocked": 1}, "touched": []})
        line = og_image.log_line(t, [1, 2, 0])
        self.assertIn("読んだ 2", line)
        self.assertIn("前の覚えから 3", line)
        self.assertIn("blocked 1", line)
        self.assertNotIn("http", line)

    def test_demote_moves_photoless_to_pending(self):
        rows = {"a": {"stories": [{"url": "1", "image": "i"}, {"url": "2"}], "pending": [{"url": "3"}]}, "b": {"stories": [{"url": "4"}]}}
        self.assertEqual(og_image.demote(rows), 1)
        self.assertEqual([s["url"] for s in rows["a"]["stories"]], ["1"])
        self.assertEqual([s["url"] for s in rows["a"]["pending"]], ["2", "3"])
        self.assertEqual([s["url"] for s in rows["b"]["stories"]], ["4"])   # 写真のある記事が無い版面は動かさない

    def test_uses_the_shops_tools(self):
        """(c) 素の urllib の別の取り方はやめ、店長と同じ images.page・images.check で読む。"""
        src = (ROOT / "scripts" / "og_image.py").read_text(encoding="utf-8")
        self.assertNotIn("urllib.request", src)
        self.assertIn("images.page", src)
        self.assertIn("images.check", src)


if __name__ == "__main__":
    unittest.main()
