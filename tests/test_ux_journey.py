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


if __name__ == "__main__":
    unittest.main()
