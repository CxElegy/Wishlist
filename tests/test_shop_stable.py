"""店長のページ（docs/home/index.html）を、写真を作り物にして（harness/aesthetic_count.fake_images：網の都合で数が揺れない）8 幅で数え、
2026-11-19 の数（直す前＝origin/main の render と、直した後の多いほう＋揺れの幅）を上限として保つ（11-19 主の指摘 5：店長のページを悪くしない、を数で）。
docs/home は main の render.yml が作り直すので、この試験は「いま公開しているページ」を見る。ブラウザが無い環境では飛ばす。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

# 幅ごとの上限（2026-11-19 直し 2 回目、Math.random の種を固定して数えた）。直す前（origin/main の render）の数：
#   390：orphan 5／1333：orphan 10・gap 1・rowedge 14／1920：orphan 7・cgap 6・gap 1・rowedge 16。直した後：390 なし／1333 gap 1・rowedge 14／1920 cgap 2〜5・gap 0〜3・rowedge 13〜14。
# 1920 幅の「ほかの注目」の壁だけ、同じページでも回ごとに組みが変わる（写真が届く順と壁を組む回の時間の前後。種の固定では止まらない）ので gap は 3 まで。
# orphan は直す前のページ（NOORPHAN なし）で回ごとに ±1、rowedge（店長の版面の積み上げ）は ±2 揺れたのでその分足す。
# 1 幅ずつ別のファイル（_b 1333・_c 1920）にして並列で流す（3 幅を 1 本で数えると 174 秒）
ZERO = {"herogap": 0, "pendhid": 0, "solo": 0, "edge": 0, "dup": 0, "navgap": 0, "sidebig": 0}
CEILS = {390: {"orphan": 6, "cgap": 0, "gap": 0, "rowedge": 0, **ZERO}, 1333: {"orphan": 11, "cgap": 0, "gap": 1, "rowedge": 16, **ZERO},
         1920: {"orphan": 8, "cgap": 6, "gap": 3, "rowedge": 18, **ZERO}}


WIDTHS = (390,)   # 試験は 3 幅だけ（このファイル 390・_b 1333・_c 1920）。8 幅は python harness/aesthetic_count.py --stable docs home/index.html を手で・PC で


class ShopStable(unittest.TestCase):
    WIDTHS = WIDTHS

    def test_owner_page_not_worse(self):
        try:
            from playwright.sync_api import sync_playwright
            import browser
        except Exception as ex:   # noqa: BLE001
            raise unittest.SkipTest(f"ブラウザが無い：{ex}")
        import aesthetic_count as ac
        import self_review
        port = self_review.serve(ROOT / "docs")
        with sync_playwright() as p:
            try:
                b = browser.launch(p)
            except Exception as ex:   # noqa: BLE001
                raise unittest.SkipTest(f"ブラウザが開けない：{ex}")
            r = ac.new_user_counts(f"http://127.0.0.1:{port}/home/index.html", b, [v for v in ac.NEW_USER_VIEWS if v[0] in self.WIDTHS], fake=True)
            b.close()
        tot = {}
        for c in r.values():
            for k, n in c.items():
                if not k.startswith("_"):
                    tot[k] = tot.get(k, 0) + n
        CEIL = CEILS[self.WIDTHS[0]]
        print(f"ℹ 店長のページ（作り物の写真・{self.WIDTHS}）：" + "・".join(f"{k} {tot.get(k, 0)}" for k in CEIL))
        for k, most in CEIL.items():
            with self.subTest(kind=k):
                self.assertLessEqual(tot.get(k, 0), most, {v: c["_notes"].get(k) for v, c in r.items() if c.get(k)})


if __name__ == "__main__":
    unittest.main()
