"""ログイン（Google・招待制・访客は見るだけ・管理ページは管理者だけ）の部品の検査。"""
import inspect
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

    def test_customer_gets_own_page(self):
        """アカウントは 1 つずつ独立（2026-10-22）：お客さまには店長の中身でなく自分のページ（my_page）。
        言葉は skill（clarify・distill・onboarding）に合わせる：内部の事情・店長のページへの切り替えは出さない、空の状態は次の一手、外したら元に戻す。"""
        render.AUTH_DB.update(url="https://x.supabase.co", key="sb_publishable_x")
        tag = render._auth_tag("index")
        for s in ("rpc('my_page')", "my_keywords_set", "好きなジャンルは？", "data-gsec", "showMine", "wl-mybar", "../?add", "wl-wait", "気になるかも？", "setTimeout(refresh,0)", '<label for="'):
            self.assertIn(s, tag)
        for s in ("ほかの人には見えません", "店長のページを見る", "自分のページに戻る", "wl-view-shop", "まだ集めていません", "ニュース集めは準備中", "欲しい物リストは準備中"):   # お客さまに要らない内部の事情は出さない
            self.assertNotIn(s, tag)
        self.assertIn('html[data-mine="1"] body>*:not(.wl-auth):not(.wl-mine)', render.AUTH_CSS)
        import json
        cfg = json.loads(re.search(r"var A=(\{.*?\}), R=", tag).group(1))
        self.assertIn(["其他", "その他", ""], cfg["secs"])   # 大類の一覧（その他も）
        sql = (ROOT / "db" / "my_page.sql").read_text(encoding="utf-8")
        self.assertIn("lower((select auth.jwt()) ->> 'email')", sql)   # 本人の行だけ
        self.assertNotIn("to anon", sql)

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
        for word in ("集める情報", "使い道", "第三者", "保存する期間", "開示", "Supabase", "再発行はありません"):
            self.assertIn(word, html)

    def test_login_is_username_with_terms(self):
        js = render.AUTH_JS
        for fn in ("user_login", "user_agree"):
            self.assertIn(fn, js)
        self.assertIn("askAgree", js)
        self.assertIn("START", js)   # 新しく始めるは入口の流れに一本化
        self.assertNotIn("招待制", js)

    def test_login_is_email(self):
        # 2026-10-21，用户定的：ログインはメールアドレス（ユーザー名ではない）
        js = render.AUTH_JS
        self.assertIn('type="email"', js)
        self.assertIn("isMail(n)", js)
        self.assertNotIn("ユーザー名", js)
        self.assertNotIn("ユーザー名", render.render_terms("10.21"))

    def test_shop_uses_password_not_mail_link(self):
        # 2026-10-21，用户定的：店長はパスワード（毎回のメール確認はやめる）
        js = render.AUTH_JS
        self.assertIn("signInWithPassword", js)
        self.assertNotIn("sendAdminLink(mail", js)
        self.assertIn(".wl-login label[hidden]{display:none}", render.AUTH_CSS)

    def test_db_names_are_emails(self):
        s = (DB / "auth.sql").read_text(encoding="utf-8")
        last = s.rsplit("function private.user_name_ok", 1)[1]
        self.assertIn("メールアドレスを入れてください", last)


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


class Welcome(unittest.TestCase):
    """入口と新しく始める（scripts/welcome.py、テストグラウンド）。"""
    def test_css_tokens_only(self):
        import welcome
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", welcome.CSS))

    def test_flow_and_redirect(self):
        import welcome
        for word in ("wl-user", "location.replace(C.shop)", "stay", "name_available", "ArrowRight", "pointermove", "C.first",
                     "addMode", "my_keywords_set", "grant_type=refresh_token"):   # 左右に払うカードに戻した・ログイン中は ?add で同じ流れから足す（2026-10-22，用户定的）
            self.assertIn(word, welcome.JS)

    def test_languages_mece(self):
        import welcome
        codes = [k for _, g in welcome.LANG_GROUPS for k, _ in g]
        self.assertEqual(len(codes), len(set(codes)))            # 1 つの言語は 1 か所だけ
        self.assertTrue(set(welcome.LANG_TOP) <= set(codes))
        self.assertTrue(welcome.COLLECTED <= set(codes))
        self.assertTrue(set(welcome.LANG_ALIAS) == set(codes))   # どの言語も英語名・日本語名で探せる
        self.assertGreaterEqual(len(codes), 50)

    def test_entry_refreshes_stale_copy(self):
        import welcome
        self.assertIn("__V__", welcome.FRESH_JS)
        self.assertIn("location.replace", welcome.FRESH_JS)
        self.assertIn('cache:"no-store"', welcome.FRESH_JS)

    def test_pages_refresh_stale_copy_on_open(self):
        # 開いた直後に古い控えなら ?v= で開き直す（GitHub Pages の max-age=600 対策）
        js = render.LIVE_JS
        self.assertIn("function fresh(v)", js)
        self.assertIn("check();   //", js)
        self.assertNotIn("setTimeout(check,3000)", js)

    def test_signup_is_real(self):
        import welcome
        self.assertIn("user_signup", welcome.JS)
        self.assertIn("prefs", welcome.JS)

    def test_shop_picks_from_archive(self):
        import welcome
        picks = welcome.shop_picks()
        self.assertTrue(picks)
        self.assertTrue(all(p["img"].startswith(f"../{welcome.sitedir.SLUG}/icons/") and p["shop"] for p in picks))
        self.assertTrue({p["sec"] for p in picks} <= set(welcome.taxonomy.SECTIONS))


class UiWording(unittest.TestCase):
    """お客さまの画面の文字は言語表 UI に置き、AUTH_JS に日本語を直書きしない（記事の文字を照らす正規表現は /*data*/ の印で除く）。"""
    JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

    def _parts(self):
        js = render.AUTH_JS
        i = js.index("var UI={")
        j = js.index("var L=UI", i)
        return js[:i] + js[j:], js[i:j]

    def test_no_literal_japanese_in_code(self):
        code, _ = self._parts()
        bad = [l.strip()[:80] for l in code.split("\n")
               if self.JA.search(re.sub(r"//.*$", "", l)) and "/*data*/" not in l]
        self.assertEqual(bad, [])

    def test_every_key_used_is_in_the_table(self):
        code, tab = self._parts()
        used = set(re.findall(r"\bL\.(\w+)", code))
        have = set(re.findall(r"(?:^|[{,\s])(\w+):'", tab))
        self.assertEqual(sorted(used - have), [])


class PyWording(unittest.TestCase):
    """Python 側の、お客さま用の日本語も表 SETTINGS_JA に置く（0 個の人の入口・外す・その他）。"""
    JA = UiWording.JA

    KANA = re.compile(r"[\u3041-\u30fa\u30fc-\u30ff]")   # かな（漢字は中文の板块名と同じ字なので数えない。「・」は区切り）
    # 操作する人が Actions のログで読む文（お客さまの画面に出ない）
    OPERATOR = {"_supa", "main"}

    def _literal_kana(self, mod, only=None, skip=()):
        """関数の中の文字列で、かなを含むもの（docstring・コメントは数えない。JS・CSS の中のコメント行は除く）。"""
        import ast
        t = ast.parse(inspect.getsource(mod))
        doc = {id(n.body[0].value) for n in ast.walk(t)
               if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
               and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
        bad = []
        for fn in ast.walk(t):
            if not isinstance(fn, ast.FunctionDef) or fn.name in skip or (only and fn.name not in only):
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
                    s = re.sub(r"//.*$|/\*.*?\*/", "", n.value, flags=re.M | re.S)
                    if self.KANA.search(s):
                        bad.append((fn.name, n.lineno, n.value.strip()[:40]))
        return bad

    def test_own_path_has_no_literal_japanese(self):
        import user_pages
        self.assertEqual(self._literal_kana(user_pages, skip=self.OPERATOR), [])
        self.assertEqual(self._literal_kana(render, only={"_own_add", "render_settings"}), [])
        # トップの 0 個の人のポスター（elif start:）
        r = inspect.getsource(render)
        i = r.index("elif start:")
        seg = re.sub(r"  #.*$", "", r[i:r.index('style = ""', i)], flags=re.M)
        self.assertIsNone(self.KANA.search(seg))

    def test_first_board_and_also_come_from_table(self):
        import user_pages
        self.assertEqual(user_pages.FIRST_BOARD, render.SETTINGS_JA["first_board"])
        for T in (render.SETTINGS_ZH, render.SETTINGS_JA):
            self.assertIn("{}", T["also"])

    def test_table_keys_exist(self):
        for k in ("none_hint", "pick", "start_h", "start_p", "none_status", "collecting", "out", "out_aria", "other"):
            self.assertTrue(render.SETTINGS_JA.get(k), k)

    def test_empty_person_settings_entry_uses_table(self):
        h = render._own_add({"add": "../?add"}, [])
        self.assertIn(render.SETTINGS_JA["pick"], h)
        self.assertIn(render.SETTINGS_JA["none_hint"], h)


if __name__ == "__main__":
    unittest.main()
