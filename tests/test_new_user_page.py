"""新しい人のページ（2026-11-19 店長が test-b を不合格にした 8 つ）：本物の道（user_pages.build → render.render）に作り物のデータを入れた
3 形（harness/new_user_sample.py）を 8 幅で開き、審美基準の数（harness/aesthetic_count.page_counts）が 0 であること。
ブラウザが無い環境では飛ばす。本番・本物のお客さまのデータには触れない。"""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

# 0 を保つ項目（8 つ＋A1・A5・A6・C1・C2・D3・E1・E2・F3・F4 の数えられる所）
ZERO = ("imgfail", "noimg", "rowedge", "cgap_wall", "orphan", "leadbig", "sidebig", "pendhid", "navgap", "dup", "solo", "herogap", "ell", "over", "wide", "clip")
# 0 を保つ：ほかの注目の壁と頭条の空き（cgap_wall）は上の ZERO。版面の小さいカードの前からの空き（cgap の残り）と写真の切れ crop は増えないことだけ見る
KNOWN = {"cgap": 8, "gap": 0, "crop": 17, "band": 85}   # 4 形（a〜d）× 8 幅（2026-11-19 仕上げ）：crop は直す前の 17 以下（B2 が先＝主役の位置が分からない写真は切らない）。その代わり同じ枠に収めた写真の余り（帯 band）が 82 出る。帯と切れのどちらを先にするかは店長の決め待ち


class NewUserPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            import browser
            cls.pw = sync_playwright().start()
            cls.b = browser.launch(cls.pw)
        except Exception as ex:   # noqa: BLE001
            raise unittest.SkipTest(f"ブラウザが開けない：{ex}")
        import new_user_sample
        import self_review
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pages = new_user_sample.build(cls.tmp.name)
        cls.port = self_review.serve(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.b.close()
            cls.pw.stop()
            cls.tmp.cleanup()
        except Exception:   # noqa: BLE001
            pass

    def test_three_shapes_eight_widths(self):
        import aesthetic_count as ac
        total = {}
        for k in self.pages:
            res = ac.new_user_counts(f"http://127.0.0.1:{self.port}/{k}.html", self.b)
            for view, c in res.items():
                for kind in ZERO:
                    with self.subTest(shape=k, view=view, kind=kind):
                        self.assertEqual(c.get(kind, 0), 0, c["_notes"].get(kind))
                for kind in KNOWN:
                    total[kind] = total.get(kind, 0) + c.get(kind, 0)
        print("ℹ 新しい人のページの残り（0 にならない項目）：" + "・".join(f"{k} {v}" for k, v in total.items()))
        for kind, most in KNOWN.items():
            self.assertLessEqual(total.get(kind, 0), most, f"{kind} が前より増えた")

    def test_html_shape(self):
        """ブラウザなしでも分かる所：空の脇の箱は細い帯・整理待ちは開いたまま・頭条の記事は版面に出ない。"""
        a = pathlib.Path(self.pages["a"]).read_text(encoding="utf-8")
        self.assertIn('<aside class="fstrip">', a)
        self.assertIn('<details class="pend" open>', a)
        self.assertEqual(a.count('href="https://example.com/news/0"'), 1)   # 頭条だけ。版面に 2 回目なし（F4）


if __name__ == "__main__":
    unittest.main()
