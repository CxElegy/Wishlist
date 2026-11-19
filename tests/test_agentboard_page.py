"""AgentBoard の画面（docs/board/index.html，HARNESS_V2.md「クラウドの AgentBoard」）。

公開の Pages に置くので、ページ自体にデータ・鍵を入れない／令牌はこの端末の localStorage だけ／見本（?demo）で全部の区画が描けて、
1333×677 で画面 1 枚・390 で横にはみ出さない。"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "board" / "index.html"


class Static(unittest.TestCase):
    def setUp(self):
        self.t = PAGE.read_text(encoding="utf-8")

    def test_no_secret_or_private_data(self):
        self.assertIsNone(re.search(r"(?:github_pat|ghp|gho|ghs)_\w{20,}", self.t))
        self.assertIsNone(re.search(r"[\w.+-]+@(?!users\.noreply)[\w-]+\.[a-z]{2,}", self.t))   # メールを書かない
        self.assertNotIn("elegy.tailc8cfff", self.t)          # 前の PC の網址・k= の鍵を残さない
        self.assertIn('name="robots" content="noindex', self.t)

    def test_reads_private_repo_with_token_from_this_device_only(self):
        self.assertIn("api.github.com/graphql", self.t)
        self.assertIn("REPO='agentboard'", self.t)
        self.assertIn("localStorage.getItem(KEY)", self.t)
        self.assertNotIn("sessionStorage", self.t)
        for host in re.findall(r"https://([\w.-]+)/", self.t):     # 令牌を送る先は GitHub だけ
            self.assertIn(host, {"api.github.com", "github.com", "claude.ai", "fonts.googleapis.com", "fonts.gstatic.com", "cxelegy.github.io"}, host)

    def test_inbox_write_goes_to_inbox_folder(self):
        self.assertIn("/contents/inbox/", self.t)


class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("playwright なし")
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.b.close()
        cls.pw.stop()

    def open(self, w, h, q="?demo"):
        p = self.b.new_page(viewport={"width": w, "height": h})
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
        p.goto(PAGE.as_uri() + q)
        p.wait_for_timeout(300)
        return p, errs

    def test_demo_pc_one_screen(self):
        p, errs = self.open(1333, 677)
        self.assertEqual(errs, [])
        m = p.evaluate("""()=>({sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight,
          ag:document.querySelectorAll('#agents .ag').length,pc:document.querySelectorAll('.tag.pc').length,cl:document.querySelectorAll('.tag.cloud').length,
          red:document.querySelectorAll('.dot.s').length,msgs:document.querySelectorAll('#msgs .m').length,res:document.querySelectorAll('#results li').length,
          over:[...document.querySelectorAll('section')].filter(s=>s.scrollWidth>s.clientWidth+1).map(s=>s.id)})""")
        self.assertEqual((m["sw"], m["sh"]), (1333, 677))      # 画面 1 枚（F1）・横はみ出し 0
        self.assertEqual((m["ag"], m["pc"], m["cl"], m["red"]), (4, 2, 2, 1))   # PC とクラウドの係が同じ一覧に・20 分は赤
        self.assertEqual((m["msgs"], m["res"]), (3, 5))
        self.assertEqual(m["over"], [])
        p.fill("#text", "見本の書き込み")
        p.click("#talk button")
        self.assertEqual(p.locator("#msgs .m").count(), 4)
        p.close()

    def test_phone_no_overflow_and_setup_without_token(self):
        p, errs = self.open(390, 844)
        self.assertEqual(errs, [])
        self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), 390)
        p.close()
        p, errs = self.open(390, 844, "")
        self.assertEqual(errs, [])
        self.assertTrue(p.is_visible("#setup"))
        self.assertFalse(p.is_visible("#app"))
        p.fill("#tok", "abc")
        p.click("#save")
        self.assertIn("github_pat_", p.inner_text("#err"))
        p.close()


if __name__ == "__main__":
    unittest.main()
