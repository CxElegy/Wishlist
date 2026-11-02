"""ux_check の 1 日通し：押す部品（press）が、向導のボタンが無い・別の部品に覆われているときに ✗ を返すか。本番には出ない（手元の HTML だけ）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import ux_check  # noqa: E402
import pathlib as _pl
import sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "harness"))
from browser import launch  # noqa: E402  点検のブラウザは共通の 1 か所から（free-tier.md）

try:
    from playwright.sync_api import sync_playwright
except Exception:  # noqa: BLE001
    sync_playwright = None

OK = '<button id="go" onclick="document.title=\'pushed\'">好きなものを選ぶ</button>'
GONE = "<p>好きなものを選ぶ はありません</p>"   # 向導のボタンを外した版
COVERED = OK + '<div style="position:fixed;left:0;top:0;width:100%;height:100%;background:#000"></div>'   # 固定の部品が上に重なる


class Pending(unittest.TestCase):
    def test_contradiction_is_counted(self):
        # 足したものが名前で出ているのに「最初の 1 つを選ぼう」とも言う画面は ✗（2026-10-27）
        self.assertEqual(ux_check.pending_contradiction("集めています 呪術廻戦 最初の 1 つを選ぼう", "呪術廻戦"), ["最初の 1 つを選ぼう"])
        self.assertEqual(ux_check.pending_contradiction("集めています 呪術廻戦", "呪術廻戦"), [])
        self.assertEqual(ux_check.pending_contradiction("最初の 1 つを選ぼう", "呪術廻戦"), [])   # 足していないなら正しい


class Press(unittest.TestCase):
    def run_press(self, html):
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001
                self.skipTest(f"ブラウザがない：{ex}")
            pg = b.new_page()
            pg.set_content(html)
            why = ux_check.press(pg, "#go", "好きなものを選ぶ", timeout=1500)
            title = pg.title()
            b.close()
            return why, title

    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_pushes_a_visible_button(self):
        why, title = self.run_press(OK)
        self.assertIsNone(why)
        self.assertEqual(title, "pushed")

    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_missing_button_is_a_failure(self):
        why, _ = self.run_press(GONE)
        self.assertIn("見つからない", why)

    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_covered_button_is_a_failure(self):
        why, title = self.run_press(COVERED)
        self.assertIn("重なって", why)
        self.assertNotEqual(title, "pushed")


class ImgFail(unittest.TestCase):
    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_removed_photo_is_recorded_even_after_document_open(self):
        # お客さまのページは me.html が document.open で書き替える。error の聞き手が消えても、外された写真の網址は残る（test-a の頭の誤判定）
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001
                self.skipTest(f"ブラウザがない：{ex}")
            pg = b.new_page()
            pg.add_init_script(ux_check.FAIL_JS)
            pg.goto("data:text/html,<p>x</p>")
            pg.evaluate("()=>{document.open();document.write('<section class=\"sec\" data-k=\"K\"><div class=\"pic\"><img src=\"http://x.invalid/a.jpg\"></div></section>');document.close()}")
            pg.evaluate("()=>document.querySelector('.pic').remove()")
            pg.wait_for_timeout(200)
            fails = pg.evaluate("window.__imgFail")
            b.close()
        self.assertIn(["K", "http://x.invalid/a.jpg"], fails)


    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_failed_photo_that_stays_in_dom_is_counted(self):
        # document.open のあと error の聞き手が消え、外されもしない（DOM に残る）開けない写真も FAILS_JS が数える
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001
                self.skipTest(f"ブラウザがない：{ex}")
            pg = b.new_page()
            pg.add_init_script(ux_check.FAIL_JS)
            pg.goto("data:text/html,<p>x</p>")
            pg.evaluate("()=>{document.open();document.write('<section class=\"sec\" data-k=\"K\"><img src=\"http://x.invalid/a.jpg\"><img class=\"bg\" src=\"http://x.invalid/bg.jpg\"></section>');document.close()}")
            pg.wait_for_timeout(1500)
            fails = pg.evaluate(ux_check.FAILS_JS)
            b.close()
        self.assertIn(["K", "http://x.invalid/a.jpg"], fails)
        self.assertNotIn("http://x.invalid/bg.jpg", [s for _, s in fails])


class Copy(unittest.TestCase):
    def test_wait_regex_knows_the_current_copy(self):
        """空の最初の画面の言い回しを user_pages が変えたら、通しが黙って壊れる前にここで落ちる。"""
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import user_pages
        import re
        h = user_pages.build("a@example.com", {"picks": []}, {}, [], None, {}, 0, {}, [])   # 入口の文言は主役のボタン（status ではない）
        txt = re.sub(r"<[^>]+>", "", h)
        self.assertTrue(ux_check.re_pick().search(txt), txt)

    def test_empty_page_shows_no_raw_markdown(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import re
        import user_pages
        h = user_pages.build("a@example.com", {"picks": []}, {}, [], None, {}, 0, {}, [])
        self.assertNotRegex(re.sub(r"<[^>]+>", "", h), r"\]\(")

    @unittest.skipUnless(sync_playwright, "playwright がない")
    def test_pick_skips_hidden_match(self):
        html = '<b hidden>追いかけるものを選ぶ</b><a href="#x" onclick="document.title=\'pushed\'">追いかけるものを選ぶ →</a>'
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001
                self.skipTest(f"ブラウザがない：{ex}")
            pg = b.new_page()
            pg.set_content(html)
            why = ux_check.press(pg, pg.locator("a:visible,button:visible").filter(has_text=ux_check.re_pick()), "選ぶ", timeout=1500)
            title = pg.title()
            b.close()
        self.assertIsNone(why)
        self.assertEqual(title, "pushed")


class CoverTest(unittest.TestCase):
    """右下の札が一番下の字を隠す点検（ux_check.COVER_JS）。スマホの CSS に札の高さの空きがある。"""

    def test_css_has_bottom_space(self):
        import render
        self.assertIn("body{padding-bottom:calc(72px + env(safe-area-inset-bottom,0px))}", render.AUTH_CSS if hasattr(render, "AUTH_CSS") else open(render.__file__, encoding="utf-8").read())

    def test_every_phone_rule_keeps_safe_area(self):
        """同じ規則の数え：≤560px で body の下の空きを決める所は全部 72px＋safe-area（render.py・札を持つ試作ページ）。plain な 72px が残らない。"""
        import pathlib, re
        root = pathlib.Path(__file__).resolve().parent.parent
        files = [root / "scripts" / "render.py"] + [f for f in (root / "docs" / "testground").glob("*.html")
                                                      if "max-width:560px){body{padding-bottom" in f.read_text(encoding="utf-8")
                                                      or ".wl-auth{top:auto;bottom:12px" in f.read_text(encoding="utf-8")]
        self.assertGreaterEqual(len(files), 3)   # render.py と d5-new・d5-now
        for f in files:
            t = f.read_text(encoding="utf-8")
            self.assertNotRegex(t, r"body\{padding-bottom:72px\}", f.name)
            self.assertIn("72px + env(safe-area-inset-bottom", t, f.name)

    def test_testground_copies_carry_current_shell_css(self):
        """焼いた写しの試作ページ（.wl-auth を持つもの）は、今の render.AUTH_CSS をそのまま含む。ずれたら harness/d5_sample.py で作り直す。"""
        import pathlib, render
        n = 0
        for f in (pathlib.Path(__file__).resolve().parent.parent / "docs" / "testground").rglob("*.html"):
            t = f.read_text(encoding="utf-8")
            if ".wl-auth" in t:
                n += 1
                self.assertIn(render.AUTH_CSS, t, f"{f.name} の殻が古い：python harness/d5_sample.py")
        self.assertGreaterEqual(n, 2)

    def test_d5_if_stale_skips_when_shell_is_current(self):
        """render.yml がつなぐ d5_sample --if-stale：写しの殻が今と同じなら作り直さない（ファイルを書かない）、違えば fresh() が偽。"""
        import pathlib, sys
        root = pathlib.Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(root / "harness"))
        import d5_sample
        self.assertTrue(d5_sample.fresh())
        wf = (root / ".github" / "workflows" / "render.yml").read_text(encoding="utf-8")
        self.assertIn("d5_sample.py --if-stale", wf)

    def test_cover_bad(self):
        self.assertEqual(ux_check.cover_bad([]), [])
        self.assertIn("隠す", ux_check.cover_bad(["p:末尾"])[0])

    def test_cover_js_finds_overlap(self):
        from playwright.sync_api import sync_playwright
        css = "body{margin:0}.wl-auth{position:fixed;bottom:12px;right:12px;width:120px;height:40px}p{margin:0;text-align:right}"
        for pad, want in (("0", 1), ("72px", 0)):
            with sync_playwright() as pw:
                try:
                    b = launch(pw)
                except Exception as ex:  # noqa: BLE001
                    self.skipTest(f"ブラウザがない：{ex}")
                pg = b.new_page(viewport={"width": 390, "height": 600})
                pg.set_content(f"<style>{css}body{{padding-bottom:{pad}}}</style><div style='height:900px'></div><p>おわり</p><div class=wl-auth>札</div>")
                pg.evaluate("window.scrollTo(0,99999)")
                n = len(pg.evaluate(ux_check.COVER_JS))
                b.close()
            self.assertEqual(n, want, pad)


class Settle(unittest.TestCase):
    """決まった待ち（--fast は 6 秒）だけでは遅い回線で字が出る前に測る（設定 1400 が文字 6 の白い画面）。測る前に字が出るまで待ち直す（2026-10-27）。"""

    def test_check_settles_before_measuring(self):
        import inspect
        src = inspect.getsource(ux_check.check)
        self.assertLess(src.index("settle(pg)"), src.index("st = pg.evaluate"))   # 測る前に待ち直す

    def test_waits_for_late_text(self):
        if sync_playwright is None:
            self.skipTest("playwright がない")
        late = "<body>x<script>setTimeout(()=>{document.body.innerText='あ'.repeat(150)},1500)</script>"
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001
                self.skipTest(f"ブラウザがない：{ex}")
            pg = b.new_page()
            pg.set_content(late)
            ux_check.settle(pg)
            n = pg.evaluate("document.body.innerText.length")
            b.close()
        self.assertGreaterEqual(n, 100)


if __name__ == "__main__":
    unittest.main()


class LoginMoreMenu(unittest.TestCase):
    def test_more_button_between_561_and_760(self):
        """561〜760px は右下の「⋯」だけ（押すと札・ログインが開く）。それ以外の幅では出さない。"""
        t = open(__import__("render").__file__, encoding="utf-8").read()
        self.assertIn("@media (min-width:561px) and (max-width:760px)", t)
        self.assertIn(".wl-auth>button.more{display:none}", t)
        self.assertEqual(t.count("addMore(box,keepOpen)"), 3)


class LoginDockCheck(unittest.TestCase):
    """札の境目（560|561・760|761）を ux_check の既定の回で見る（2026-11-01：既定の幅 1400/390 は 561〜760 を通らず、「⋯」の出る幅・開け閉めを誰も点検していなかった）。"""
    @staticmethod
    def uc():
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import ux_check
        return ux_check

    def test_widths_cover_both_sides_of_each_edge(self):
        w = self.uc().DOCK_WIDTHS
        for x in (390, 560, 561, 700, 760, 761):
            self.assertIn(x, w)

    def test_dock_rules(self):
        u = self.uc()
        one = {"vis": ["more"], "exp": "false", "away": False, "has": True}
        chips = {"vis": ["new home", "login"], "exp": "false", "away": False, "has": True}
        opened = {"vis": ["new home", "login", "more"], "exp": "true", "away": False, "has": True}
        self.assertEqual(u.dock_bad(700, one, opened, {"away": False}, {"away": True}), [])
        self.assertEqual(u.dock_bad(390, chips), [])
        self.assertEqual(u.dock_bad(1000, chips), [])
        # 壊れ方：⋯ が 390・761 に漏れる／700 に札が戻る／押しても開かない／開いたまましまう／閉じてもしまわない
        self.assertTrue(u.dock_bad(390, one))
        self.assertTrue(u.dock_bad(761, opened))
        self.assertTrue(u.dock_bad(700, opened))
        self.assertTrue(u.dock_bad(700, one, one))
        self.assertTrue(u.dock_bad(700, one, opened, {"away": True}, {"away": True}))
        self.assertTrue(u.dock_bad(700, one, opened, {"away": False}, {"away": False}))
        self.assertTrue(u.dock_bad(700, None))

    def test_main_runs_dock_for_three_kinds_by_default(self):
        s = open(self.uc().__file__, encoding="utf-8").read()
        self.assertIn('("guest", "test-a", "test-b")', s)
        self.assertIn("check_dock(pw, a.base, who, w)", s)
        i = s.index("check_dock(pw, a.base, who, w)")
        self.assertNotIn("if a.fast:\n                continue", s[i - 400:i])   # --fast でも走る

    def test_dock_check_visits_other_pages(self):
        """札の点検が開くのは 1 枚だけではない：AUTH_JS を持つ他のページも幅を変えて開く。"""
        u = self.uc()
        for f in ("settings.html", "wishlist.html", "heat.html", "themes.html", "terms.html", "admin.html"):
            self.assertIn(f, u.DOCK_PAGES)
        for x in (390, 700, 761):
            self.assertIn(x, u.DOCK_PAGE_WIDTHS)
        s = open(u.__file__, encoding="utf-8").read()
        self.assertIn("check_dock(pw, a.base, who, w, pgname)", s)

    def test_every_auth_page_carries_dock_css_and_guard(self):
        """札（.wl-auth）を持つ home/ の全ページが 561〜760 の CSS と「開いたままならしまわない」の守りを持つ（数える）。
        持たないのは殻の me.html（ログインの部品を入れない）だけ。"""
        import pathlib
        home = pathlib.Path(__file__).resolve().parent.parent / "docs" / "home"
        pages = [p for p in home.glob("*.html") if ".wl-auth{position:fixed" in p.read_text(encoding="utf-8")]
        self.assertGreaterEqual(len(pages), 13)   # トップ・設定・欲しい物・話題度・テーマ・規約・管理 8 枚
        for p in pages:
            s = p.read_text(encoding="utf-8")
            self.assertIn("@media (min-width:561px) and (max-width:760px)", s, p.name)
            self.assertIn(".wl-auth>button.more{display:none}", s, p.name)
            self.assertIn("b.classList.contains('open')&&innerWidth>560", s, p.name)
        self.assertNotIn("me.html", [p.name for p in pages])
        # 点検が開くページに漏れがない（トップ index と admin-* 6 枚〔admin.html と同じ殻〕を除く全部）
        mine = set(self.uc().DOCK_PAGES)
        self.assertEqual({p.name for p in pages if p.stem != "index" and not p.stem.startswith("admin-")} - mine, set())

    def test_open_dock_is_not_hidden_on_scroll(self):
        t = open(__import__("render").__file__, encoding="utf-8").read()
        self.assertIn("b.classList.contains('open')&&innerWidth>560", t)
