"""審美基準を数える項目（harness/aesthetic_count.py）：わざと違反させた小さい HTML で「違反を数える・違反が無ければ 0」を確かめる（2026-11-12）。
ブラウザが無い環境では飛ばす。本番にも写しにも触れない。"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))

PX = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
CSS = """body{margin:0;font:14px sans-serif;padding-bottom:3000px}.sp{height:900px}
section.sec{position:relative;scroll-margin-top:90px;margin:0 0 40px}.band{position:relative;height:60px;background:#222;color:#fff}
.band .title{position:absolute;left:20px;top:10px}.band .cnt{position:absolute;left:300px;top:10px}
.emb{position:absolute;right:20px;top:-70px;width:100px;height:120px}.emb img{width:100px;height:120px;display:block}
.grid{display:flex;gap:16px;width:1200px}article.card{background:#eee;height:200px;flex:none;width:300px}.hero{width:300px}
.btn{position:fixed;left:10px;top:10px;width:420px;height:50px;background:#369;z-index:9}"""


def page(body, css=""):
    return f"<!doctype html><meta charset=utf-8><style>{CSS}{css}</style>{body}"


def sec(emb="", extra="", k="作品"):
    return (f'<div class="sp"></div><section class="sec has-emb" data-k="{k}"><div class="band">{emb}<span class="title">題</span>'
            f'<span class="cnt"><b>3</b>今週</span></div>{extra}</section>')


def cards(n, hero_w=None, h3=""):
    cs = "".join(f'<article class="card{" hero" if i == 0 else ""}"{f" style=width:{hero_w}px" if i == 0 and hero_w else ""}><h3>{h3 or "記事"}</h3></article>' for i in range(n))
    return f'<div class="grid">{cs}</div>'


EMB = f'<div class="emb"><img src="{PX}"></div>'
EMB_IN = f'<div class="emb" style="top:0"><img src="{PX}"></div>'


class AestheticCount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            from browser import launch
            cls.pw = sync_playwright().start()
            cls.b = launch(cls.pw)
        except Exception as ex:   # noqa: BLE001
            raise unittest.SkipTest(f"ブラウザが開けない：{ex}")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.b.close()
            cls.pw.stop()
        except Exception:   # noqa: BLE001
            pass

    def run_page(self, html, width=1400):
        import aesthetic_count as ac
        pg = self.b.new_page(viewport={"width": width, "height": 900})
        pg.set_content(html, wait_until="load")
        r = ac.measure(pg)
        pg.close()
        return r

    def n(self, r, kind):
        return sum(1 for i in r["items"] if i["kind"] == kind)

    def test_edge_cut_at_snap(self):
        # 小元素が帯から 70px 上にはみ出し、吸着の位置（scroll-margin-top 90px）に収まる → 切れない
        ok = self.run_page(page(sec(EMB, cards(2))))
        self.assertEqual(self.n(ok, "edge"), 0)
        self.assertEqual(ok["stats"]["snapMeasured"], 1)
        # 同じ版面で吸着の余白が 20px しかない → 小元素が画面の上で切れる
        bad = self.run_page(page(sec(EMB, cards(2)), "section.sec{scroll-margin-top:20px}"))
        self.assertEqual(self.n(bad, "edge"), 1)
        # スマホ幅は吸着しない（測らない）
        ph = self.run_page(page(sec(EMB, cards(2)), "section.sec{scroll-margin-top:20px}"), 390)
        self.assertEqual((self.n(ph, "edge"), ph["stats"]["snapMeasured"]), (0, 0))

    def test_hidden_under_fixed_button(self):
        ok = self.run_page(page(sec(EMB, cards(2))))
        self.assertEqual(self.n(ok, "hid"), 0)
        bad = self.run_page(page(sec(EMB, cards(2)) + '<a class="btn">はじめのページ</a>', ".btn{left:0;top:80px;width:600px;height:60px}"))
        self.assertGreaterEqual(self.n(bad, "hid"), 1)   # 吸着位置では題（top:90+10）が固定のボタンの下

    def test_solo_board(self):
        self.assertEqual(self.n(self.run_page(page(sec(EMB_IN, cards(2)))), "solo"), 0)
        r = self.run_page(page(sec(EMB_IN, cards(1))))
        self.assertEqual(self.n(r, "solo"), 1)

    def test_hero_side_gap(self):
        self.assertEqual(self.n(self.run_page(page(sec(EMB_IN, cards(4, hero_w=300)))), "herogap"), 0)   # 300 × 4 + すき間で幅 1200 を埋める
        r = self.run_page(page(sec(EMB_IN, cards(2, hero_w=300))))                                      # 600 / 1200 が空く
        self.assertEqual(self.n(r, "herogap"), 1)
        flat = self.run_page(page(sec(EMB_IN, cards(2, hero_w=300)).replace('class="card hero"', 'class="card" data-hero="1"')))   # PC の積み上げ後の形
        self.assertEqual(self.n(flat, "herogap"), 1)

    def wemb_page(self, text, name="Makima", own=False):
        alts = json.dumps([{"src": PX, "shape": "cutout", "name": name, **({"own": True} if own else {})}], ensure_ascii=False).replace('"', "&quot;")
        s = (f'<section class="sec has-emb" data-k="作品"><div class="band"><div class="emb" data-alts="{alts}" style="top:0"><img src="{PX}"></div></div></section>'
             f'<div class="wc cmp" data-k="作品" data-t="{text}" style="position:relative;height:200px">{text}'
             f'<img class="wemb" src="{PX}" style="position:absolute;left:0;top:100px;width:40px;height:40px"></div>')
        return page(s)

    def test_gap_emblem_relation(self):
        ok = self.run_page(self.wemb_page("Makima は新しい映像に登場"))
        self.assertEqual((ok["stats"]["wemb"], self.n(ok, "emrel")), (1, 0))
        bad = self.run_page(self.wemb_page("全く別の人のニュース"))
        self.assertEqual(self.n(bad, "emrel"), 1)
        self.assertEqual(bad["stats"]["emlogo"], 0)
        logo = self.run_page(self.wemb_page("全く別の人のニュース", name="作品", own=True))   # 作品そのもので埋めた
        self.assertEqual((self.n(logo, "emrel"), logo["stats"]["emlogo"]), (1, 1))

    def test_card_inner_gap(self):
        card = lambda h: (f'<article class="card" style="display:flex;width:400px;height:{h}px;padding:0"><div class="pic" style="width:100px;height:100px;background:#abc"></div>'
                          f'<div class="txt" style="flex:1"><h3 style="margin:0;height:100px">見出し</h3></div></article>')
        wrap = lambda h: page(f'<section class="sec"><div class="band"></div><div class="grid">{card(h)}</div></section>')
        self.assertEqual(self.n(self.run_page(wrap(110)), "cgap"), 0)
        r = self.run_page(wrap(300))   # 写真の下 200px・字の下も大きく空く
        self.assertEqual(self.n(r, "cgap"), 1)
        self.assertGreaterEqual(r["stats"]["cgap_photo"], 1)
        right = self.run_page(page('<section class="sec"><div class="band"></div><div class="grid"><article class="card" style="width:400px;height:100px"><div class="pic" style="width:100px;height:100px"></div></article></div></section>'))
        self.assertGreaterEqual(right["stats"]["cgap_right"], 1)

    def test_heading_ellipsis(self):
        clamp = "h3{width:120px;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;margin:0}"
        long = "とても長い見出しの文字列がここに入って枠を超える"
        r = self.run_page(page(f'<section class="sec"><div class="band"></div>{cards(1, h3=long)}</section>', clamp))
        self.assertEqual(self.n(r, "ell"), 1)
        r = self.run_page(page(f'<section class="sec"><div class="band"></div>{cards(1, h3="短い")}</section>', clamp))
        self.assertEqual(self.n(r, "ell"), 0)

    def test_side_strong_elements(self):
        red = '<div style="width:200px;height:100px;background:#d7261e"></div>'
        side = lambda inner: page(f'<aside class="fside"><div class="agenda" style="width:220px;background:#1a1c22">{inner}</div></aside>')
        self.assertEqual(self.n(self.run_page(side(red)), "strong"), 0)            # 強い要素 1 つ
        self.assertEqual(self.n(self.run_page(side(red + red)), "strong"), 1)      # 2 つ
        none = self.run_page(page("<p>右の列なし</p>"))
        self.assertEqual(none["stats"].get("strongUnmeasured"), 1)                  # 測れない（0 とは書かない）


if __name__ == "__main__":
    unittest.main()
