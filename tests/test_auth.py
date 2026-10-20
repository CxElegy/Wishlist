"""ログイン（Google・招待制・访客は見るだけ・管理ページは管理者だけ）の部品の検査。"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402

DB = ROOT / "db"


class AuthTag(unittest.TestCase):
    def setUp(self):
        self.saved = dict(render.AUTH_DB)

    def tearDown(self):
        render.AUTH_DB.clear()
        render.AUTH_DB.update(self.saved)

    def test_nothing_without_db(self):
        render.AUTH_DB.clear()
        self.assertEqual(render._auth_tag("index"), "")

    def test_tag_has_config_and_pinned_lib(self):
        render.AUTH_DB.update({"url": "https://x.supabase.co", "key": "sb_publishable_x"})
        t = render._auth_tag("admin")
        self.assertIn('"page": "admin"', t)
        self.assertIn("https://x.supabase.co", t)
        self.assertRegex(render.SUPABASE_JS, r"@\d+\.\d+\.\d+/")   # 版は固定
        self.assertNotIn("__AUTH__", t)
        self.assertNotIn("__LOCK__", t)
        # <script> の中に </ がそのまま出ない（ページが途中で切れない）
        body = t.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        self.assertNotIn("</", body)

    def test_pages_carry_tag(self):
        render.AUTH_DB.update({"url": "https://x.supabase.co", "key": "sb_publishable_x"})
        self.assertIn("wl-auth", render._live_head("index"))
        self.assertIn("wl-auth", render._account_tag("settings"))

    def test_lock_pages(self):
        for page in ("index", "settings", "admin", "wishlist"):
            self.assertIn(page, render.AUTH_LOCK)
        self.assertIn("[data-vote]", render.AUTH_LOCK["index"])

    def test_css_uses_tokens(self):
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", render.AUTH_CSS))

    def test_roles_in_japanese(self):
        self.assertEqual(set(render.ROLE_JA), {"admin", "user", "guest"})
        self.assertEqual(render.ROLE_JA["admin"], "店長")   # 運営者 = 店長（「店長のおすすめ」と同じ設定）

    def test_terms_page(self):
        html = render.render_terms("10.21")
        self.assertIn(f"第 {render.TERMS_VERSION} 版", html)
        for word in ("集める情報", "使い道", "第三者", "保存する期間", "開示", "Supabase", "パスワードがありません"):
            self.assertIn(word, html)

    def test_login_is_username_with_terms(self):
        js = render.AUTH_JS
        for fn in ("name_available", "user_register", "user_login", "user_agree", "user_leave"):
            self.assertIn(fn, js)
        self.assertIn("askAgree", js)
        self.assertNotIn("招待制", js)


class AuthSql(unittest.TestCase):
    def test_no_destructive_statements(self):
        # Supabase 連接器では delete / drop に確認が要る：自動で流すファイルには入れない（削除は auth_delete.sql）
        for f in ("auth.sql", "auth_guard.sql", "auth_enforce.sql"):
            s = re.sub(r"--[^\n]*", "", (DB / f).read_text(encoding="utf-8"))
            s = re.sub(r"on delete (cascade|set null)", "", s)
            self.assertIsNone(re.search(r"\b(drop|delete|truncate)\b", s, re.I), f)

    def test_every_write_function_is_guarded(self):
        s = (DB / "auth_guard.sql").read_text(encoding="utf-8")
        for fn in ("set_size", "set_nav_scheme", "submit_item", "add_photo", "edit_control_set"):
            body = re.search(r"function public\.%s\(p_account.*?end \$\$;" % fn, s, re.S)
            self.assertIsNotNone(body, fn)
            self.assertIn("public.can_edit(p_account)", body.group(0), fn)
        self.assertIn("public.is_admin()", re.search(r"function public\.run_now.*?end \$\$;", s, re.S).group(0))

    def test_invite_hook_and_admin_limit(self):
        s = (DB / "auth.sql").read_text(encoding="utf-8")
        self.assertIn("hook_invite_only", s)
        self.assertIn("app_users", s)
        self.assertIn("その名前はもう使われています", s)   # 名前は重ならない
        self.assertIn(">= 5", s)                 # 管理者は 5 人まで
        self.assertIn("c.elegy@outlook.com", s)  # 最初の管理者

    def test_enforce_is_one_switch(self):
        s = (DB / "auth_enforce.sql").read_text(encoding="utf-8")
        self.assertIn("set on_ = true where key = 'enforce'", s)


if __name__ == "__main__":
    unittest.main()
