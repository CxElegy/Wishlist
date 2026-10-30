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
