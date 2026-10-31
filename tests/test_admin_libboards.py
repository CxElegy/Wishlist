"""管理ページ②版面の「ライブラリの版面」：お客さまの版面の名前を HTML に焼かない・店長だけが読む・配色の RPC は店長だけ。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


class LibBoards(unittest.TestCase):
    def test_panel_hidden_and_empty(self):
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-boards.html"]
        self.assertIn('id="libboards" hidden', out)
        self.assertIn('id="wl-libboards"><p class="empty">読み込み中', out)   # 中身は JS が店長のログインで読む（焼かない）
        self.assertIn("店長がログインしたときだけ", out)

    def test_tokens_panel_says_all_accounts(self):   # 2026-10-31：AI 編集は 1 本だけ＝実行ログの合計が全アカウント分
        out = render._admin_edit_tokens({"runs": [], "today": {}, "week": {}})
        self.assertIn("まだ記録がありません", out)
        d = {"runs": [{"when": "10/31", "at": "x", "batches": [{"when": "01:00", "batch": 1, "boards": ["a"], "stories": 1,
              "tok": {"in": 1, "cw": 0, "cr": 0, "out": 1}, "total": 2}], "sum": {"in": 1}}], "today": {"in": 1}, "week": {"in": 1}}
        s = render._admin_edit_tokens(d)
        self.assertNotIn("同じ編集で作る", s)
        self.assertNotIn("全アカウント分の合計です", s)
        self.assertIn("店長の inbox の分だけ", s)
        self.assertIn("まだ編集されません", s)

    def test_screen_text_matches_edit_scope(self):   # 画面の文と実際の範囲：board_stories に書く処理が無い間は「お客さまの版面は編集されない」、BACKLOG の親の段は [x] にしない
        import re
        writers = [f.name for f in (ROOT / "scripts").glob("*.py") if f.name not in ("render.py", "processes.py", "library.py") and "board_stories" in f.read_text(encoding="utf-8")]
        self.assertEqual(writers, [], "board_stories に書く処理ができたら、④の文と ADMIN_WHO_NO を直す")
        self.assertIn("未対応", render.ADMIN_WHO_NO["tokens"])
        bl = (ROOT / "BACKLOG.md").read_text(encoding="utf-8")
        row = [l for l in bl.splitlines() if "管理ページ④：AI 編集のトークンを全アカウント合計に" in l]
        self.assertEqual(len(row), 1)
        self.assertNotIn("- [x]", row[0])
        # 「店長の分だけ」の区画（ADMIN_WHO_NO の理由に「店長の」）が残る間は、全部が [x] ではない
        mine = [k for k, v in render.ADMIN_WHO_NO.items() if v.startswith("店長の")]
        self.assertTrue(mine)
        # 区画ごとに、画面の注記が出ている（見出しの文だけでは「店長の分だけ」と読めなかった・2026-10-31）
        out = {}
        for h in render.render_admin({"items": [], "votes": {}}, {"url": "https://x.supabase.co", "key": "k"}, "u").values():
            out[h] = 1
        for k in mine:
            hits = [h for h in out if f'id="{k}"' in h and 'data-scope="mine"' in h.split(f'id="{k}"', 1)[1].split("</section>", 1)[0]]
            self.assertTrue(hits, f"{k}: 画面に「店長の分だけ」の注記がない")
        self.assertGreaterEqual(len(mine), 6)

    def test_page_is_in_admin_pages(self):
        ids = [i for f, _, _, _, ids in render.ADMIN_PAGES if f == "admin-boards.html" for i in ids]
        self.assertIn("libboards", ids)

    def test_rpc_admin_only(self):
        sql = (ROOT / "db" / "board_theme.sql").read_text(encoding="utf-8")
        self.assertIn("if not public.is_admin()", sql)
        self.assertIn("grant execute on function public.board_theme_set(bigint, jsonb) to authenticated", sql)
        self.assertNotIn("to anon", sql)
        self.assertIn("from anon;", sql)   # 実際の権限は ux_check（check_public_leak）が本番で anon の呼び出しを確かめる

    def test_no_anon_grant_on_admin_functions(self):
        """db/*.sql：admin_・board_ の関数を anon に grant しない（board_visible は RLS が使う公開）。revoke から anon を外し忘れも拾う。"""
        import re
        for f in (ROOT / "db").glob("*.sql"):
            for m in re.finditer(r"grant\s+execute\s+on\s+function\s+public\.((?:admin|board)_\w+)\s*\([^)]*\)\s+to\s+([^;]+);", f.read_text(encoding="utf-8")):
                if m.group(1) != "board_visible":
                    self.assertNotIn("anon", m.group(2), f"{f.name}: {m.group(1)}")
        self.assertIn("from anon;", (ROOT / "db" / "board_emblem.sql").read_text(encoding="utf-8"))

    def test_admin_functions_guarded_or_not_granted(self):
        """db/*.sql：authenticated に grant した admin_ の関数は、本体に is_admin() の守りがある（お客さまが店長の中身を引けない）。守りのないものは grant しない（admin_email_for の漏れの型）。"""
        import re
        sql = "\n".join(f.read_text(encoding="utf-8") for f in sorted((ROOT / "db").glob("*.sql")))
        granted = {m.group(1) for m in re.finditer(r"^grant\s+execute\s+on\s+function\s+public\.(admin_\w+)\s*\([^)]*\)\s+to\s+[^;]*authenticated", sql, re.M | re.I)}
        self.assertTrue(granted)
        for fn in sorted(granted):
            bodies = re.findall(r"create\s+or\s+replace\s+function\s+public\." + fn + r"\s*\(.*?\n\$\$;", sql, re.S | re.I)
            self.assertTrue(bodies, fn)
            self.assertIn("is_admin()", bodies[-1], f"{fn} に is_admin() の守りがない")

    def test_ux_check_admin_cells_by_key_not_index(self):
        """管理ページ②の値照合は列の位置でなく data-k で読む（列を足しても取り違えない）。"""
        u = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertNotIn("slice(7,11)", u)
        self.assertNotIn("g[2] != (f.get", u)
        self.assertIn("data-k=", render.AUTH_JS)

    def test_published_html_has_no_board_rows(self):
        """公開の docs/home/admin-boards.html に版面の行（名前）が焼かれていない。ライブラリの欄は空の入れ物だけ。"""
        f = ROOT / "docs" / "home" / "admin-boards.html"
        if not f.exists():
            self.skipTest("docs 未生成")
        html = f.read_text(encoding="utf-8")
        i = html.index('id="wl-libboards"')
        self.assertNotIn("<tr data-id", html[i:i + 400])
        self.assertIn("読み込み中", html[i:i + 120])

    def test_emblem_page_reads_all_library_boards(self):
        """③エンブレムの版面の札：店長の令牌でライブラリの boards 全部（②と同じ。anon の followers>0 だけ、にしない）・版面の数を点検する。"""
        js = render.EMM_JS
        self.assertIn("Authorization:'Bearer '+window.WL_TOK", js)
        self.assertNotIn("followers=gt.0", js)
        self.assertIn("wl-token", render.AUTH_JS)
        self.assertIn("dataset.lib", js)
        self.assertIn("dataset.lib", (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8"))
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-emblem.html"]
        self.assertNotIn("お客さまの名前", out)   # 焼かない：版面の札は JS が読む
        self.assertIn("board_emblem_request", js)

    def test_no_script_filters_library_boards_by_followers(self):
        """ライブラリの版面一覧を followers>0（や匿名鍵）で絞って読む所が scripts 全体に 0 件。0 人の版面も収集・表示の対象（画面の約束と同じ規則）。"""
        import re
        bad = [f"{p.name}:{i}" for p in sorted((ROOT / "scripts").glob("*.py")) if p.name != "processes.py"
               for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"boards\?[^\"']*followers=(gt|gte)\.", ln)]
        self.assertEqual(bad, [])

    def test_ux_check_has_coverage_and_leak_checks(self):
        src = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn('glob("*.html")', src)   # 公開 HTML は名指しでなく glob で全部
        self.assertIn("ANON_OK_FN", src)
        for name in ("def check_public_leak", "def check_admin_coverage", "UX_ADMIN_EMAIL"):
            self.assertIn(name, src)
        self.assertIn("def check_customer_admin_rpc", src)   # お客さまが admin_ を呼んでも中身が返らない点検

    def test_admin_menu_entry_only_for_admin_role(self):
        # お客さまのメニューに「管理ページへ」を出さない：chip6 は role==='admin' のときだけ連結される
        src = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("(role==='admin'&&page!=='admin'?L.chip6:'')"), 1)

    def test_customer_admin_page_checks_and_role_guards(self):
        # お客さまが admin*.html を直に開く点検がある・全ユーザーの行を作る部品は店長のときだけ動く（2026-10-31）
        ux = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("def check_customer_admin_gate", ux)
        src = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        self.assertIn("document.documentElement.dataset.role!=='admin'||!CFG.url", src)   # ③の loadLib
        for fn in ("libboards", "libedit", "libvotes", "libaccts", "libplace"):
            i = src.index(f"function {fn}()")
            self.assertIn("R.dataset.role!=='admin'", src[i:i + 400], fn)



class LibEdit(unittest.TestCase):
    def test_edit_state_panel(self):
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-ai.html"]
        self.assertIn('id="libedit" hidden', out)
        self.assertIn('id="wl-libedit"><p class="empty">読み込み中', out)
        self.assertIn("admin_board_edit_state", render.AUTH_JS)
        sql = (ROOT / "db" / "admin_board_edit.sql").read_text(encoding="utf-8")
        self.assertIn("if not public.is_admin()", sql)
        self.assertNotIn("to anon", sql)

    def test_edit_user_switch(self):   # ④にも「全員／ユーザーを選ぶ」（admin.md）。follows を店長の令牌で読み、メールは出さない
        i = render.AUTH_JS.index("function libedit")
        js = render.AUTH_JS[i:i + 2500]
        self.assertIn("whoMount(", js)
        w = render.AUTH_JS[render.AUTH_JS.index("function whoLoad"):render.AUTH_JS.index("window.WL_WHO")]
        self.assertIn("rest/v1/follows", w)
        self.assertNotIn("email", w)
        src = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        self.assertIn("管理ページ④に出ない版面", src)


class LibVotes(unittest.TestCase):
    def test_votes_panel(self):   # ②に「全アカウントの投票」：焼かない・店長の令牌の admin_votes() で読む・全員／ユーザーを選ぶ
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-boards.html"]
        self.assertIn('id="libvotes" hidden', out)
        self.assertIn('id="wl-libvotes"><p class="empty">読み込み中', out)
        self.assertIn("rpc('admin_votes')", render.AUTH_JS)
        self.assertIn("libvotes", [s for _, s, _ in render.ADMIN_WHO])
        i = render.AUTH_JS.index("function libvotes")
        self.assertIn("whoMount(", render.AUTH_JS[i:i + 2500])
        sql = (ROOT / "db" / "admin_votes.sql").read_text(encoding="utf-8")
        self.assertIn("if not public.is_admin()", sql)
        self.assertNotIn("to anon", sql)
        self.assertNotIn("email", sql)

    def test_account_filter_keys(self):   # アカウントごとの行は 'acc:<名前>' で follows のアカウントと結ぶ
        w = render.AUTH_JS[render.AUTH_JS.index("function whoLoad"):render.AUTH_JS.index("window.WL_WHO")]
        self.assertIn("'acc:'+f.account", w)
        self.assertIn("'acc:test1'", w)


class LibState(unittest.TestCase):
    def test_state_panel(self):   # ③に「ライブラリの版面ごとの状態」：焼かない・店長の令牌で読んだ boards.config から・全員／ユーザーを選ぶ
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-emblem.html"]
        self.assertIn('id="libstate" hidden', out)
        self.assertIn('id="wl-libstate"><p class="empty">読み込み中', out)
        self.assertIn("function libState", render.EMM_JS)
        self.assertIn("emblem_state", render.EMM_JS)
        self.assertIn("admin_board_edit_state", render.EMM_JS)   # 収集（記事）の列は③も④と同じ RPC から
        self.assertIn('data-k="stories"', render.EMM_JS)
        self.assertIn('data-k="design"', render.EMM_JS)
        self.assertIn("libstate", [s for _, s, _ in render.ADMIN_WHO])


class AdminWho(unittest.TestCase):
    def test_every_section_decided(self):   # 区画ごとに「切り替えを入れた」か「入れない理由」のどちらかが書いてある（漏れ 0）
        ids = {i for *_, ids in render.ADMIN_PAGES for i in ids}
        have = {s for _, s, _ in render.ADMIN_WHO}
        self.assertFalse(ids - have - set(render.ADMIN_WHO_NO), ids - have - set(render.ADMIN_WHO_NO))
        self.assertFalse(have & set(render.ADMIN_WHO_NO))

    def test_one_component(self):   # 切り替えは AUTH_JS の WL_WHO 1 つ。区画が自分で select を作らない
        self.assertEqual(render.AUTH_JS.count("<select data-who>"), 1)
        self.assertIn("window.WL_WHO", render.AUTH_JS)
        for fn in ("function libboards", "function libedit"):
            i = render.AUTH_JS.index(fn)
            self.assertIn("whoMount(", render.AUTH_JS[i:i + 3500])
        self.assertIn("WL_WHO.mount", render.EMM_JS)
        self.assertNotIn("data-who", render.EMM_JS)


if __name__ == "__main__":
    unittest.main()


class LibAccts(unittest.TestCase):
    def test_accts_panel(self):   # ②に「全アカウントの篇幅・写真・依頼・言語」：焼かない・admin_accounts()／admin_ui_langs()（店長だけ）で読む・全員／ユーザーを選ぶ
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-boards.html"]
        self.assertIn('id="libaccts" hidden', out)
        self.assertIn('id="wl-libaccts"><p class="empty">読み込み中', out)
        self.assertIn("rpc('admin_accounts')", render.AUTH_JS)
        self.assertIn("rpc('admin_ui_langs')", render.AUTH_JS)
        self.assertIn("libaccts", [s for _, s, _ in render.ADMIN_WHO])
        i = render.AUTH_JS.index("function libaccts")
        self.assertIn("whoMount(", render.AUTH_JS[i:i + 2500])
        sql = (ROOT / "db" / "admin_accounts.sql").read_text(encoding="utf-8")
        self.assertEqual(sql.count("if not public.is_admin()"), 2)
        self.assertNotIn("to anon", sql)
        self.assertNotIn("email", sql)
        self.assertIn("rpc('admin_follow_detail')", render.AUTH_JS)   # 置き方・関注項の中身（follows の section/subs/media/also）
        fd = (ROOT / "db" / "admin_follow_detail.sql").read_text(encoding="utf-8")
        self.assertEqual(fd.count("if not public.is_admin()"), 1)
        self.assertNotIn("to anon", fd)
        self.assertNotIn("email", fd)


class LibPlace(unittest.TestCase):
    def test_place_panel(self):   # ②置き方・関注項の中身（follows 1 行 = 1 行）と account ごとの言語
        out = render.render_admin({}, {"url": "https://x.supabase.co", "key": "k"}, "u")["admin-boards.html"]
        self.assertIn('id="libplace" hidden', out)
        self.assertIn('id="wl-libplace"><p class="empty">読み込み中', out)
        self.assertIn("rpc('admin_follow_rows')", render.AUTH_JS)
        self.assertIn("rpc('admin_account_langs')", render.AUTH_JS)
        self.assertIn("libplace", [s for _, s, _ in render.ADMIN_WHO])
        sql = (ROOT / "db" / "admin_follow_rows.sql").read_text(encoding="utf-8")
        self.assertEqual(sql.count("if not public.is_admin()"), 2)
        self.assertNotIn("to anon", sql)
        self.assertNotRegex(sql, r"returns table \([^)]*email")
        for col in ("section", "pos", "size", "subs", "media", "also", "scheme"):   # follows の置き方・中身の列を全部読む
            self.assertIn(col, sql)
        # 表の見出しの数 ＝ 行の列の数（10 と 11 のずれを二度と作らない）
        js = render.AUTH_JS if "la1:" in render.AUTH_JS else (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
        for key, rowfn, n in (("la1:", "function libaccts", 12), ("lp1:", "function libplace", 9)):
            h = js[js.index(key):]
            h = h[:h.index("</tr>")]
            self.assertEqual(h.count("<th>"), n, key)
            r = js[js.index(rowfn):]
            r = r[:r.index("}).join('')+'</tbody>")]
            self.assertEqual(r.count("<td"), n, rowfn)
