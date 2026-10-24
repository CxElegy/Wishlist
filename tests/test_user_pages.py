"""お客さまのページ（scripts/user_pages.py）：店長と同じ部品で、中身は本人の版面。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402
import user_pages  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Account(unittest.TestCase):
    def test_same_as_supabase(self):
        # Supabase の private.user_account('test-a@example.com') と同じ（2026-10-24 に確かめた値）
        self.assertEqual(user_pages.account_of(" Test-A@example.com "), "u_ff28fe3daabfc919")


class Items(unittest.TestCase):
    SHOP = [{"name": "あつ森", "type": "game", "section": "游戏", "motif": "leaf", "theme": {"acc": "#123456"}, "parent": "x"}]

    def test_shop_board_keeps_design(self):
        it = user_pages.user_items([{"name": "あつ森", "sec": "游戏"}], self.SHOP)[0]
        self.assertTrue(it["_shop"])
        self.assertEqual(it["motif"], "leaf")       # 主題・配色は店長のものをそのまま
        self.assertNotIn("parent", it)              # 上下級は本人のページには持ち込まない

    def test_own_board_and_dupes(self):
        out = user_pages.user_items([{"name": "広島旅行", "sec": "出行"}, {"name": "広島 旅行", "sec": "出行"}, {"name": ""}], self.SHOP)
        self.assertEqual([i["name"] for i in out], ["広島旅行"])
        self.assertEqual(out[0]["section"], "出行")
        self.assertEqual(out[0]["match"], ["広島旅行"])


class Issue(unittest.TestCase):
    def test_stories_from_rows(self):
        items = [{"name": "広島旅行", "type": "category", "section": "出行", "keywords": ["広島旅行"], "match": ["広島旅行"], "subs": {}}]
        rows = {"広島旅行": {"stories": [{"title": "宮島の紅葉", "url": "https://example.com/a", "image": "https://example.com/a.jpg",
                                           "date": "2026-10-23", "source": "例"}]}}
        iss = user_pages.user_issue(items, None, rows, 0, {})
        b = iss["items"][0]
        self.assertEqual(b["stories"][0]["headline"], "宮島の紅葉")
        self.assertEqual(b["stories"][0]["weight"], "hero")
        self.assertEqual(b["cover"], "https://example.com/a.jpg")


    def test_zero_boards_same_frame(self):
        # 版面 0 個の人も、静かな版面（主題・配色つき）で最初の 1 つを選ぶ道（素の箱にしない）
        b = user_pages.user_issue([], None, {}, 0, {})["items"]
        self.assertEqual([x["name"] for x in b], [user_pages.FIRST_BOARD])
        self.assertTrue(b[0]["quiet"] and b[0]["theme"])
        self.assertIn(user_pages.ADD_URL, b[0]["status"])
        html_ = render._md_links(b[0]["status"])
        self.assertNotIn("_blank", html_)          # サイトの中の網址は同じタブ


class Loader(unittest.TestCase):
    def test_auth_js_reads_own_page(self):
        js = render.AUTH_JS
        self.assertNotIn("tok&&picks.length&&document", js)   # 版面の数によらず、まず本人のページ
        self.assertIn("location.replace('me.html'", js)            # お客さまは殻のページへ送るだけ（同じ窓で差し替えない）
        self.assertNotIn("document.write", js)
        me = render.render_me()
        for w in ("my_page_path", "storage.from('pages')", 'name="wl-own"', "?own=0"):
            self.assertIn(w, me)

    def test_no_reload_loop(self):
        # 本人のページでは「古い版なら開き直す」を働かせない・差し替えは 30 秒に 1 回まで（2026-10-24 のくり返し）
        live = render.LIVE_JS
        self.assertLess(live.index('meta[name="wl-own"]'), live.index("function fresh("))
        self.assertIn("wl-own-at", render.AUTH_JS)
        self.assertIn("if(!on&&OWN){if(signedOut)", render.AUTH_JS)   # 本人のページでは確かめの途中で開き直さない

    def test_bucket_is_private(self):
        sql = (ROOT / "db" / "user_pages.sql").read_text(encoding="utf-8")
        self.assertIn("false", sql.split("insert into storage.buckets")[1].split(";")[0])
        self.assertIn("public.is_admin()", sql)


if __name__ == "__main__":
    unittest.main()
