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


class Follows(unittest.TestCase):
    """置く板块・小分類・篇幅・並びはライブラリの follows から（picks は follows にまだないものだけ）。"""
    FOL = [{"pos": 1, "section": "游戏", "subs": {"platform": "スマホ", "status": "運営中"}, "size": "L", "boards": {"name": "原神"}},
           {"pos": 0, "section": "出行", "subs": {"kind": "観光地"}, "size": None, "boards": {"name": "京都"}}]

    PICKS = [{"name": "原神", "sec": "游戏"}, {"name": "京都", "sec": "出行"}]

    def test_follows_first_then_new_picks(self):
        out = user_pages.own_picks(self.FOL, [{"name": "原神"}, {"name": "京都", "sec": "其他"}, {"name": "広島旅行", "sec": "出行"}])
        self.assertEqual([p["name"] for p in out], ["京都", "原神", "広島旅行"])   # follows の並び → まだ follows にないもの
        self.assertEqual(out[0]["sec"], "出行")                                    # 板块は follows（picks の「其他」ではない）

    def test_subs_and_size_reach_items(self):
        items = user_pages.user_items(user_pages.own_picks(self.FOL, self.PICKS), [])
        gen = next(i for i in items if i["name"] == "原神")
        self.assertEqual(gen["size"], "L")
        self.assertEqual(user_pages.own_sub(gen), "運営中")   # 游戏の 1 つ目の分け方（状態）。jsonb の鍵の順に頼らない
        self.assertNotIn("size", next(i for i in items if i["name"] == "京都"))

    def test_shop_board_takes_own_subs(self):
        it = user_pages.user_items([{"name": "あつ森", "sec": "游戏", "subs": {"status": "発売済み"}}], Items.SHOP)[0]
        self.assertEqual(it["subs"], {"status": "発売済み"})
        self.assertEqual(it["motif"], "leaf")

    def test_page_shows_subheads(self):
        html_ = user_pages.build("a@example.com", {"picks": self.PICKS}, {}, [], None, {}, 0, {}, self.FOL)
        self.assertIn("運営中", html_)
        self.assertIn("観光地", html_)

    def test_removed_pick_disappears(self):
        # 設定の「外す」は picks だけを書き換え、follows の行は残る → 外した版面は出さない
        out = user_pages.own_picks(self.FOL, [{"name": "京都", "sec": "出行"}])
        self.assertEqual([p["name"] for p in out], ["京都"])
        self.assertEqual(user_pages.own_picks(self.FOL, []), [])          # 全部外した
        self.assertEqual(user_pages.own_picks(self.FOL, None), [])
        html_ = user_pages.build("a@example.com", {"picks": [{"name": "京都", "sec": "出行"}]}, {}, [], None, {}, 0, {}, self.FOL)
        self.assertNotIn("原神", html_)
        self.assertIn("京都", html_)

    def test_readded_pick_uses_follows_again(self):
        # 外したあとカードで付け直した → follows の置き方（板块・小分類・篇幅）がまた効く
        out = user_pages.own_picks(self.FOL, [{"name": "京都", "sec": "出行"}, {"name": " 原神 ", "sec": "其他"}])
        gen = next(p for p in out if p["name"] == "原神")
        self.assertEqual((gen["sec"], gen["size"]), ("游戏", "L"))
        self.assertEqual(len(out), 2)


class Layout(unittest.TestCase):
    """本人が設定ページで変える篇幅・分け方（db/my_layout.sql）が本人のページに効く。店長と同じ render_settings。"""
    FOL = Follows.FOL
    PICKS = Follows.PICKS

    def test_size_from_prefs_when_no_follows(self):
        out = user_pages.own_picks(self.FOL, self.PICKS + [{"name": "広島旅行", "sec": "出行"}], {"広島旅行": "S", "原神": "M", "京都": "X"})
        by = {p["name"]: p.get("size") for p in out}
        self.assertEqual(by, {"京都": None, "原神": "L", "広島旅行": "S"})   # follows.size が先、ないときだけ prefs.sizes。S/M/L 以外は捨てる

    def test_chosen_scheme(self):
        gen = user_pages.user_items(user_pages.own_picks(self.FOL, self.PICKS), [])[1]
        self.assertEqual(gen["name"], "原神")
        self.assertEqual(user_pages.own_sub(gen, user_pages.own_schemes({"游戏": "platform"})), "スマホ")
        self.assertEqual(user_pages.own_sub(gen, user_pages.own_schemes({"游戏": "nope"})), "運営中")   # 候補にない値は 1 つ目
        html_ = user_pages.build("a@example.com", {"picks": self.PICKS}, {}, [], None, {}, 0, {}, self.FOL, {"游戏": "platform"})
        self.assertIn("スマホ", html_)

    def test_settings_page_same_parts_own_writes(self):
        pages = {}
        user_pages.build("a@example.com", {"picks": self.PICKS, "sizes": {}}, {}, [], None, {}, 0, {}, self.FOL, {"游戏": "platform"}, pages)
        s = pages["settings.html"]
        self.assertIn('name="wl-own"', s)
        self.assertIn('lang="ja"', s)
        self.assertIn('class="seg"', s)             # 店長と同じ S/M/L の部品
        self.assertIn('class="srow"', s)            # 分け方の部品
        self.assertIn('data-v="platform" aria-pressed="true"', s)
        self.assertIn("my_size_set", s)
        self.assertIn("my_nav_scheme_set", s)
        self.assertIn(user_pages.ADD_URL, s)
        for w in ("additem.js", "id=\"wiz\"", "class=\"secdel\"", "class=\"del\"", "admin.html", "回到简报"):   # 店長の向導・管理の道は出さない
            self.assertNotIn(w, s)

    def test_shop_settings_unchanged(self):
        s = render.render_settings([{"name": "あつ森", "section": "游戏", "size": "M"}], {"url": "u", "key": "k"}, "x")
        for w in ("additem.js", "新增关注项", 'lang="zh-CN"', "删除这个板块"):
            self.assertIn(w, s)
        self.assertNotIn('"own": true', s)

    def test_shell_and_sql(self):
        me = render.render_me()
        self.assertIn("p=settings", me)
        self.assertIn("'settings.html'", me)
        self.assertIn("?p=settings", render.AUTH_JS)
        sql = (ROOT / "db" / "my_layout.sql").read_text(encoding="utf-8")
        for w in ("public.my_account()", "update public.follows", "insert into public.nav_schemes", "to authenticated"):
            self.assertIn(w, sql)
        low = sql.lower()
        self.assertNotIn("drop ", low)
        self.assertNotIn("delete ", low)
        self.assertNotIn("public.sizes", low)    # get_sizes はだれでも読めるので、お客さまの分は書かない


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
