"""新しい人のページ（2026-11-19 店長が test-b を不合格にした 8 つ）：本物の道（user_pages.build → render.render）に作り物のデータを入れた
4 形（harness/new_user_sample.py）を 8 幅で開き、審美基準の数（harness/aesthetic_count.page_counts）が 0 であること。
ブラウザが無い環境では飛ばす。本番・本物のお客さまのデータには触れない。"""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

# 0 を保つ項目（8 つ＋A1・A5・A6・C1・C2・D3・E1・E2・F3・F4 の数えられる所）
ZERO = ("imgfail", "noimg", "orphan", "leadbig", "sidebig", "pendhid", "navgap", "dup", "solo", "herogap", "ell", "over", "wide", "clip",
        "crop", "band")   # crop・band：写真は切らない・帯で埋めない（B1〜B3・B6・A3。整理待ちのカードの縦長も枠を写真の形に）
# 0 にならない項目は 4 形（a〜d）× 8 幅の合計を上限（2026-11-19 claude/new-user-check で測った数・2 回同じ）。次の段で 0 にする：
#   rowedge（同じ行の下端の差）・small（B9 写真の短い辺が下限未満）・sizemix（D1 同じ行の 1 大 1 小）は、店長に絵を見せて決めてから直す。
#   cgap は縦長の写真を切らずに置いたカードの字の下（写真が字より高い分）と版面の小さいカードの前からの空き
KNOWN = {"cgap": 21, "gap": 1, "rowedge": 46, "small": 85, "sizemix": 41, "postergap": 4, "cgap_wall": 1}
# 2026-11-20 頭条の写真と字の列の高さを合わせた（店長「空白のところは多すぎ」）：postergap（頭条の中の空き）は前の render で 18 → 4。
#   残りの 4 と cgap・gap・cgap_wall・small の +1 は形 b（見出し 2 行・要約なし・縦長の写真）だけ：写真の高さの下限（C1）を守ると字の列が届かず、
#   頭条が縮んだ分だけ、ほかの注目の横長の写真のカードが「頭条の 64% まで」に当たって写真の下が空く（取り合い）。空いた所を情報で埋める部品は店長に絵で決めてもらってから（A9 ④）


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
        self.assertIn('data-e="s" data-o="1"', a)   # 記事自身の写真の印（点検の own）
        self.assertIn("me.dataset.sw=(+me.dataset.sw||0)+1", a)   # 落ち先へ替えた回数
        self.assertEqual(a.count('href="https://example.com/news/0"'), 1)   # 頭条だけ。版面に 2 回目なし（F4）


if __name__ == "__main__":
    unittest.main()
