"""ux_check の 1 日通し：押す部品（press）が、向導のボタンが無い・別の部品に覆われているときに ✗ を返すか。本番には出ない（手元の HTML だけ）。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import ux_check  # noqa: E402

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
                b = pw.chromium.launch()
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
                b = pw.chromium.launch()
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

    def test_cover_bad(self):
        self.assertEqual(ux_check.cover_bad([]), [])
        self.assertIn("隠す", ux_check.cover_bad(["p:末尾"])[0])

    def test_cover_js_finds_overlap(self):
        from playwright.sync_api import sync_playwright
        css = "body{margin:0}.wl-auth{position:fixed;bottom:12px;right:12px;width:120px;height:40px}p{margin:0;text-align:right}"
        for pad, want in (("0", 1), ("72px", 0)):
            with sync_playwright() as pw:
                try:
                    b = pw.chromium.launch()
                except Exception as ex:  # noqa: BLE001
                    self.skipTest(f"ブラウザがない：{ex}")
                pg = b.new_page(viewport={"width": 390, "height": 600})
                pg.set_content(f"<style>{css}body{{padding-bottom:{pad}}}</style><div style='height:900px'></div><p>おわり</p><div class=wl-auth>札</div>")
                pg.evaluate("window.scrollTo(0,99999)")
                n = len(pg.evaluate(ux_check.COVER_JS))
                b.close()
            self.assertEqual(n, want, pad)


if __name__ == "__main__":
    unittest.main()
