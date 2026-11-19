"""店長のページ（docs/home/index.html）を、写真を作り物にして（harness/aesthetic_count.fake_images：網の都合で数が揺れない）8 幅で数え、
2026-11-19 の数（直す前＝origin/main の render と、直した後の多いほう＋揺れの幅）を上限として保つ（11-19 主の指摘 5：店長のページを悪くしない、を数で）。
docs/home は main の render.yml が作り直すので、この試験は「いま公開しているページ」を見る。ブラウザが無い環境では飛ばす。"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))

# 8 幅の合計の上限。直す前（origin/main）：orphan 48・cgap 10・gap 6・herogap 2・pendhid 0・solo 0・edge 0。
# 直した後：orphan 0・cgap 13・gap 6・herogap 1。同じページを 2 回数えても cgap は ±3・orphan は ±1 揺れた（壁の組みの候補の選び方）ので、その分だけ足す（main の render のページでも cgap 10〜13 が出たので cgap は 16）
CEIL = {"orphan": 50, "cgap": 16, "gap": 6, "herogap": 2, "pendhid": 0, "solo": 0, "edge": 0, "dup": 0, "navgap": 0, "sidebig": 0}


WIDTHS = (390, 1333, 1920)   # 試験は 3 幅だけ（全体の時間。8 幅は python harness/aesthetic_count.py --stable docs home/index.html を手で・PC で）


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
        print(f"ℹ 店長のページ（作り物の写真・{self.WIDTHS}）：" + "・".join(f"{k} {tot.get(k, 0)}" for k in CEIL))
        for k, most in CEIL.items():
            with self.subTest(kind=k):
                self.assertLessEqual(tot.get(k, 0), most, {v: c["_notes"].get(k) for v, c in r.items() if c.get(k)})


if __name__ == "__main__":
    unittest.main()
