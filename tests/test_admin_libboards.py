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

    def test_published_html_has_no_board_rows(self):
        """公開の docs/home/admin-boards.html に版面の行（名前）が焼かれていない。ライブラリの欄は空の入れ物だけ。"""
        f = ROOT / "docs" / "home" / "admin-boards.html"
        if not f.exists():
            self.skipTest("docs 未生成")
        html = f.read_text(encoding="utf-8")
        i = html.index('id="wl-libboards"')
        self.assertNotIn("<tr data-id", html[i:i + 400])
        self.assertIn("読み込み中", html[i:i + 120])

    def test_ux_check_has_coverage_and_leak_checks(self):
        src = (ROOT / "harness" / "ux_check.py").read_text(encoding="utf-8")
        for name in ("def check_public_leak", "def check_admin_coverage", "UX_ADMIN_EMAIL"):
            self.assertIn(name, src)


if __name__ == "__main__":
    unittest.main()
