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

    def test_settings_zero_picks_has_main_button(self):
        # 版面 0 個の人の設定ページ：入口は主役のボタン（トップの最初の画面と同じ .startgo）、1 つ以上なら小さいリンク
        pages = {}
        user_pages.build("a@example.com", {"picks": [], "sizes": {}}, {}, [], None, {}, 0, {}, self.FOL, {}, pages)
        self.assertEqual(pages["settings.html"].count('<a class="startgo" href="'), 1)
        self.assertIn(user_pages.ADD_URL, pages["settings.html"])
        pages = {}
        user_pages.build("a@example.com", {"picks": self.PICKS, "sizes": {}}, {}, [], None, {}, 0, {}, self.FOL, {}, pages)
        self.assertNotIn('<a class="startgo" href="', pages["settings.html"])
        self.assertIn(">＋ 追いかけるものを足す</a>", pages["settings.html"])
        me = render.render_me()   # 欲しい物ページの 0 個の人も選ぶへ直接
        self.assertIn("go big", render.AUTH_JS)

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
        k = low.split("function private.kick_render()")[1].split("end $$")[0]
        self.assertNotIn("interval '60 seconds'", k)   # 間引くと続けて押した分が出ない（render.yml は cancel-in-progress で最後の回が勝つ）
        self.assertIn("private.render_kicks", k)


class JsSyntax(unittest.TestCase):
    """ページの中の JS が構文として正しいか（2026-10-24：行の途中に // の注釈を入れて AUTH_JS の続きを消し、本番の全ページが壊れた）。"""
    @unittest.skipUnless(__import__("shutil").which("node"), "node がない")
    def test_inline_scripts_parse(self):
        import re, subprocess, tempfile
        old = dict(render.AUTH_DB)
        render.AUTH_DB.update({"url": "https://x.supabase.co", "key": "k"})
        try:
            pages = [render._auth_tag("index"), render.render_me(),
                     render.render_settings([{"name": "a", "section": "游戏", "size": "M"}], {"url": "u", "key": "k"}, "x"),
                     render.render_settings([{"name": "a", "section": "游戏", "size": "M"}], {"url": "u", "key": "k"}, "x", (), {"picks": []})]
        finally:
            render.AUTH_DB.clear(); render.AUTH_DB.update(old)
        for h in pages:
            for s in re.findall(r"<script(?![^>]*(?:src=|application/json))[^>]*>(.*?)</script>", h, re.S):
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                    f.write(s)
                r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[:500])


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
        self.assertEqual(user_pages.ADD_URL, b[0]["start"])   # 道は主役のボタン 1 つ（status にはリンクを置かない）
        self.assertNotIn(user_pages.ADD_URL, b[0]["status"])
        html_ = render._md_links(b[0]["status"])
        self.assertNotIn("_blank", html_)          # サイトの中の網址は同じタブ


    def test_size_caps_stories(self):
        # 設定ページの約束（S 3・M 5・L 8）：本人の篇幅で切る。店長と同じ版面も、本人の版面も
        rows = {"広島旅行": {"stories": [{"title": f"記事{n}", "url": f"https://example.com/{n}", "date": "2026-10-23"} for n in range(12)]}}
        shop = {"items": [{"name": "あつ森", "section": "游戏", "stories": [{"headline": f"s{n}", "url": "https://e.com"} for n in range(9)]}]}
        for size, n in (("S", 3), ("M", 5), ("L", 8), (None, 5)):
            items = [{"name": "広島旅行", "section": "出行", **({"size": size} if size else {})},
                     {"name": "あつ森", "section": "游戏", "_shop": True, **({"size": size} if size else {})}]
            b = user_pages.user_issue(items, shop, rows, 0, {})["items"]
            self.assertEqual([len(x["stories"]) for x in b], [n, n], size)
        self.assertEqual(len(shop["items"][0]["stories"]), 9)   # 店長の号は変えない

    def test_settings_for_zero_boards(self):
        # 版面 0 個の人の設定ページも店長と同じ部品（素の箱 drawMine に落とさない）
        pages = {}
        user_pages.build("c@example.com", {"picks": []}, {}, [], None, {}, 0, {}, [], {}, pages)
        self.assertIn('name="wl-own"', pages["settings.html"])
        self.assertIn(user_pages.ADD_URL, pages["settings.html"])
        self.assertIn("if(page==='settings'&&!err&&tok){", render.AUTH_JS)


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


class FirstScreenTests(unittest.TestCase):
    def test_zero_settings_and_wishlist_need_main_button(self):
        # 設定・欲しい物ページ（zero は「まだ何も追いかけていません」の字で決まる）：主役のボタンなし・固定ボタンと重なる・画面に入らない（低い端末）は ✗
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import ux_check
        base = {"go": {"t": 300, "b": 356, "l": 20, "r": 360}, "fix": {"t": 600, "b": 640, "l": 100, "r": 378}, "H": 667,
                "shelves": False, "sum": 0, "tapes": 0, "zero": True, "quiet": False, "links": 1}
        self.assertEqual(ux_check.first_screen_bad(base), [])
        self.assertEqual(len(ux_check.first_screen_bad({**base, "go": None})), 1)
        self.assertEqual(len(ux_check.first_screen_bad({**base, "go": {"t": 590, "b": 650, "l": 20, "r": 360}})), 1)
        self.assertEqual(len(ux_check.first_screen_bad({**base, "go": {"t": 640, "b": 700, "l": 20, "r": 360}})), 2)

    def test_zero_boards_start_button_and_no_shelf(self):
        # 版面 0 個：主役は「選ぶ」ボタン（新着なしの帯・ジャンル別の数は出さない）
        h = user_pages.build("c@example.com", {"picks": []}, {}, [], None, {}, 0, {}, [], {})
        self.assertIn('class="startgo"', h)
        self.assertNotIn("は新着なし</span>", h)
        self.assertNotIn("新着なし", h.replace("新着なしの帯", ""))   # 目次の札・静かな版面の tag にも出さない
        self.assertNotIn("新 着 な し", h)
        self.assertEqual(h.count("追いかけるものを選ぶ"), 1)           # 入口は主役のボタン 1 つ
        self.assertIn('class="calm start"', h)
        self.assertNotIn('class="shelfbox"', h)

    def test_first_screen_check_catches_overlap(self):
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import ux_check
        ok = {"go": {"t": 400, "b": 460, "l": 20, "r": 360}, "fix": {"t": 790, "b": 832, "l": 250, "r": 378}, "H": 844, "shelves": False, "sum": 0, "tapes": 0}
        self.assertEqual(ux_check.first_screen_bad(ok), [])
        self.assertEqual(len(ux_check.first_screen_bad({**ok, "go": {"t": 780, "b": 830, "l": 20, "r": 360}})), 1)
        self.assertEqual(len(ux_check.first_screen_bad({**ok, "sum": 1})), 1)
        z = {**ok, "zero": True, "quiet": False, "links": 1}
        self.assertEqual(ux_check.first_screen_bad(z), [])
        self.assertEqual(len(ux_check.first_screen_bad({**z, "go": None})), 1)    # 主役のボタンが消えた
        self.assertEqual(len(ux_check.first_screen_bad({**z, "quiet": True})), 1)  # 新着なし
        self.assertEqual(len(ux_check.first_screen_bad({**z, "links": 2})), 1)    # 入口が二重
