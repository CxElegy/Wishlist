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
WIDTHS = (1400, 1100, 768)   # 壁が右の列の横に並ぶ幅と、1 列になる手前の幅
NARROW = 390   # 1 列になる幅（壁は右の列の下に回る）。空きでなく、並びの崩れ（横にはみ出す・カードの間が開く）を数える
MANY = 14      # 右の列の欲しい物・予定の行を増やす数（隠しても壁の 1.6 倍に収まらない場合の、壁を伸ばしきれない形を作る）
LEAD_ALONE = ["WWW", "WVV", "WTT", "WVVV"]   # 先頭を 2 列の大きい 1 枚に固定（生成ページの先頭が .tall になっても外れない）：その列に 1 枚だけで、隣が 3 枚以上
COMBOS = ["WW", "TW", "VV", "WWW", "TWW", "SSS", "VWT", "TTT", "WWWW", "TVWS"]


def _png(w, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (w, h), (120, 140, 170)).save(b, "PNG")
    return b.getvalue()


NARROW_JS = """()=>{const w=document.querySelector('.mgrid>.wall');const cs=[...(w?w.querySelectorAll(':scope>.wc'):[])].filter(c=>c.offsetParent);
let gap=0;cs.forEach((c,i)=>{if(i)gap=Math.max(gap,c.offsetTop-(cs[i-1].offsetTop+cs[i-1].offsetHeight))});
return {over:Math.max(0,document.documentElement.scrollWidth-innerWidth),gap:Math.round(gap)}}"""


def _many(tail, k):
    """右の列（</div><aside…）の予定・欲しい物の行を k 行ずつに増やす（同じ行を写す）"""
    if not k:
        return tail
    def grow(m):
        li = re.findall(r"<li\b.*?</li>", m.group(2), re.S)
        return m.group(1) + m.group(2) + "".join(li[i % len(li)] for i in range(k)) + m.group(3) if li else m.group(0)
    return re.sub(r'(<div class="(?:agenda|sbox swish)">.*?<ol>)(.*?)(</ol>)', grow, tail, flags=re.S)


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
            runs = [(s, w, 0, False) for s, w in itertools.product(COMBOS, WIDTHS)]
            runs += [(s, w, MANY, False) for s, w in itertools.product(("WW", "TW", "WWW"), WIDTHS[:2])]   # 右の列が長い版面（欲しい物・予定が多い人）
            runs += [(s, NARROW, 0, False) for s in ("WW", "WWWW", "TVWS")]
            runs += [(s, w, 0, True) for s, w in itertools.product(LEAD_ALONE, WIDTHS[:1])]
            for shapes, vw, many, fixed in runs:
                n = len(shapes)
                pg = b.new_page(viewport={"width": vw, "height": 900})
                use = cards[:n]
                if fixed:   # 先頭だけ 2 列の大きい 1 枚（.lead・.tall なし）、あとは 1 列の普通のカード
                    use = [re.sub(r'class="wc[^"]*"', 'class="wc lead"' if i == 0 else 'class="wc"', c, count=1) for i, c in enumerate(use)]
                html = src[:a] + "".join(use) + _many(src[z:], many)
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
                tag = f"{vw}px {shapes}" + (f"・右の列 +{many} 行" if many else "") + ("・先頭は 2 列の 1 枚" if fixed else "")
                if vw == NARROW:
                    o = pg.evaluate(NARROW_JS)
                    if o["over"] or o["gap"] > 40:
                        bad.append(f"{tag}: 横にはみ出し {o['over']}px・カードの間 {o['gap']}px")
                else:
                    h = pg.evaluate(ux_check.HOLE_JS)
                    # 先頭固定の形は、2 列の 1 枚が伸びれば 0%（伸びないと 8%・閾値ぎりぎりで通ってしまう）なので 2% で切る
                    if h["wallPct"] > (2 if fixed else 8) or h["sidePct"] > 8:
                        bad.append(f"{tag}: 壁の中 {h['wallPct']}%・右の列との差 {h['sidePct']}%")
                pg.close()
            b.close()
        self.assertEqual(bad, [], "写真の形で壁に空きが出る組み合わせ（W 横長・S 正方形・T 縦長・V 細長）")


if __name__ == "__main__":
    unittest.main()
