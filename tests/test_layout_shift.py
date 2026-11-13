"""描いた後に動かない（審美基準 F5・E5）のうち、ブラウザ無しで確かめられる所。全版面・全幅の実測は harness/shift_check.py。"""
import html
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402


def _emb(items):
    h = render._emblem(items)
    return h, json.loads(html.unescape(re.search(r'data-alts="([^"]*)"', h).group(1)))


class EmblemSize(unittest.TestCase):
    def test_local_emblem_has_size(self):
        """倉庫の小元素は元の大きさを <img> と候補（alts）に書く：届く前から場所を取る。"""
        f = next((render.sitedir.SITE_DIR / "emblems").glob("*.webp"), None)
        if f is None:
            self.skipTest("docs/<面>/emblems に絵が無い")
        from PIL import Image
        with Image.open(f) as im:
            w, h = im.size
        out, alts = _emb([{"image": f"emblems/{f.name}", "subject": "x"}])
        self.assertIn(f'width="{w}" height="{h}"', out)
        self.assertEqual((alts[0]["w"], alts[0]["h"]), (w, h))

    def test_twemoji_36(self):
        out, alts = _emb([{"image": render.TWEMOJI.format("1f680"), "subject": "🚀 アイコン"}])
        self.assertIn('width="36" height="36"', out)

    def test_unknown_external_no_size(self):
        out, alts = _emb([{"image": "https://example.com/a.png", "subject": "x"}])
        self.assertNotIn("width=", out)   # 分からない絵は書かない（届いたら EMB_JS が 1 回だけ取り直す）
        self.assertNotIn("w", alts[0])

    def test_built_page_emblems_all_sized(self):
        """生成した店長のページで、倉庫の小元素の <img> は全部 width/height を持つ。"""
        page = render.sitedir.SITE_DIR / "index.html"
        if not page.is_file():
            self.skipTest("網页がまだ無い")
        if render.VIEW_GATE_JS not in page.read_text(encoding="utf-8"):
            self.skipTest("網页がこの版の render より古い（CI は試験のあとに作る）")
        imgs = re.findall(r'<img class="(?:cutout|badge|logo|icon)[^"]*"[^>]*src="emblems/[^"]+"[^>]*>', page.read_text(encoding="utf-8"))
        bad = [i[:120] for i in imgs if " width=" not in i]
        self.assertFalse(bad, bad[:3])


class OnePlace(unittest.TestCase):
    def test_band_room_written_once(self):
        """帯の右の空き（paddingRight）を書くのは EMB_JS の room だけ（FIT_JS の embPad と書き合わない）。"""
        self.assertNotIn("embPad", render.FIT_JS.replace("embPad と EMB_JS が", ""))
        self.assertEqual(render.EMB_JS.count("band.style.paddingRight ="), 1)
        self.assertNotIn("paddingRight", re.sub(r"//[^\n]*", "", render.FIT_JS))

    def test_room_untransformed(self):
        """変形の後の箱（getBoundingClientRect）でなく変形の前の箱（offsetLeft）で測る。"""
        i = render.EMB_JS.index("const room = el =>")
        body = render.EMB_JS[i:render.EMB_JS.index("const settle", i)]
        self.assertNotIn("getBoundingClientRect", body)
        self.assertIn("offsetLeft", body)

    def test_scale_once(self):
        """倍率 --s は最初に決め、帯の空けのあとは持ち上げだけ合わせる。"""
        self.assertIn("const settle = el => { place(el); room(el); place(el, 1); }", render.EMB_JS)

    def test_no_clone(self):
        self.assertNotIn("cloneNode", re.sub(r"//[^\n]*", "", render.EMB_JS))

    def test_resize_only_on_width(self):
        self.assertIn("if (innerWidth === embW) return;", render.EMB_JS)


class UrlBarGate(unittest.TestCase):
    def test_gate_first_in_head(self):
        """URL 欄の出入り（幅が同じ・高さだけ）の resize を、ほかの聞き手より先に止める門が <head> にある。"""
        self.assertIn("stopImmediatePropagation", render.VIEW_GATE_JS)
        self.assertIn("window.WLvh", render.VIEW_GATE_JS)
        page = render.sitedir.SITE_DIR / "index.html"
        if page.is_file() and "WLvh" in page.read_text(encoding="utf-8"):   # 古い網页（CI は試験のあとに作る）は見ない
            t = page.read_text(encoding="utf-8")
            head = t[:t.index("</head>")]
            self.assertIn(render.VIEW_GATE_JS, head)

    def test_budgets_use_stable_height(self):
        """版面の高さの予算は門を通った高さ（WLvh）で計る。"""
        for js in (render.FIT_JS,):
            self.assertNotRegex(js, r"budget = Math\.max\(160, \(innerHeight")
            self.assertIn("(window.WLvh || innerHeight)", js)


class CountUp(unittest.TestCase):
    def test_room_in_ch(self):
        """途中の数は最後の数が取った場所の中で（場所は字の幅 ch でも取る：字体が後から来ても動かない）。"""
        js = render.RB_JS if hasattr(render, "RB_JS") else ""
        src = js or pathlib.Path(render.__file__).read_text(encoding="utf-8")
        self.assertIn("ch + ' + (c * 0.35).toFixed(2) + 'em))'", src)


if __name__ == "__main__":
    unittest.main()
