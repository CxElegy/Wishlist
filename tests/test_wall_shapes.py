"""写真の形ごとの「ほかの注目ニュース」の壁の空き（2026-11-03）。
ux_check の壁の空き ✓ は、写しが空だと写真が灰色の 8x8 で測るため、写真の形で決まる空きを見逃した（#725 で ✓ のあと 11/2 に test-a で空きを指摘された）。
ここは写真の形（横長・正方形・縦長・細長）を手元で作って返し、カードが 2〜4 枚の壁を 1400px で数える。本番にも写しにも触れない。
ブラウザが無い環境では飛ばす。"""
import io
import itertools
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
DOCS = ROOT / "docs"
SHAPES = {"W": (800, 450), "S": (600, 600), "T": (400, 600), "V": (300, 900)}   # 横長・正方形・縦長・細長
COMBOS = ["WW", "TW", "VV", "WWW", "TWW", "SSS", "VWT", "TTT", "WWWW", "TVWS"]


def _png(w, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 140, 170)).save(b, "PNG")
    return b.getvalue()


class WallShapes(unittest.TestCase):
    def test_wall_has_no_hole_for_any_photo_shape(self):
        try:
            from playwright.sync_api import sync_playwright
            import ux_check
            from browser import launch
            src = (DOCS / "home" / "index.html").read_text(encoding="utf-8")
            import render
            # 置いてある页面のスクリプトは古いことがある。今の FIT_JS（壁の並べ方）で測る
            m = re.search(r"<script>(?:(?!</script>).)*const wall = \(\) =>.*?</script>", src, re.S)
            src = src[:m.start()] + "<script>" + render.FIT_JS + "</script>" + src[m.end():]
            a = src.index('<div class="wall">') + len('<div class="wall">')
            z = src.index("</div><aside", a)
        except Exception as ex:   # noqa: BLE001
            self.skipTest(f"ブラウザ・ページが無い：{ex}")
        cards = re.split(r'(?=<article class="wc)', src[a:z])[1:]
        if len(cards) < 4:
            self.skipTest("壁のカードが 4 枚未満")
        bad = []
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:   # noqa: BLE001
                self.skipTest(f"ブラウザが開けない：{ex}")
            for shapes in COMBOS:
                n = len(shapes)
                pg = b.new_page(viewport={"width": 1400, "height": 900})
                html = src[:a] + "".join(cards[:n]) + src[z:]
                smap = {}
                for c, s in zip(cards[:n], shapes):
                    for u in re.findall(r'<img[^>]*src="([^"]+)"', c):
                        smap[u.replace("&amp;", "&")] = s

                def rt(r):
                    u = r.request.url
                    if u.startswith("http://wl.test/"):
                        p = DOCS / u[len("http://wl.test/"):].split("?")[0]
                        if p == DOCS / "home" / "index.html":
                            return r.fulfill(status=200, body=html, content_type="text/html")
                        return r.fulfill(path=str(p)) if p.is_file() else r.fulfill(status=404, body="")
                    return r.fulfill(status=200, body=_png(*SHAPES[smap.get(u, "S")]), content_type="image/png")
                html, smap = html, dict(smap)
                pg.route(re.compile(r".*"), rt)
                pg.goto("http://wl.test/home/index.html", wait_until="load", timeout=30000)
                pg.wait_for_timeout(1200)
                h = pg.evaluate(ux_check.HOLE_JS)
                if h["wallPct"] > 8 or h["sidePct"] > 8:
                    bad.append(f"{shapes}: 壁の中 {h['wallPct']}%・右の列との差 {h['sidePct']}%")
                pg.close()
            b.close()
        self.assertEqual(bad, [], "写真の形で壁に空きが出る組み合わせ（W 横長・S 正方形・T 縦長・V 細長）")


if __name__ == "__main__":
    unittest.main()
