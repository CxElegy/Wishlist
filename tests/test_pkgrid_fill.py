"""気になるかもの並び（.pkgrid）：大きい 1 枚＋小さい札が 1〜9 枚のどの枚数でも、最後の行に穴が残らない（2026-11-03。6〜7 枚で右が空いた）。
実際の CSS（render.CSS）で組んだ見本をブラウザで開き、最後の行の札の幅の合計が列の幅いっぱいか数える。ブラウザが無い環境では飛ばす。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402

JS = """()=>{const g=document.querySelector('.pkgrid'),gr=g.getBoundingClientRect(),cs=[...g.children].map(c=>c.getBoundingClientRect());
 const bot=Math.max(...cs.map(r=>r.bottom));let worst=0;
 for(let x=gr.left+4;x<gr.right;x+=16){const b=Math.max(-1,...cs.filter(r=>r.left-12<=x&&r.right+12>x).map(r=>r.bottom));worst=Math.max(worst,b<0?bot-gr.top:bot-b)}
 return {gap:Math.round(worst),n:cs.length}}"""   # 列ごとに、その列の札の底と並び全体の底の差（札のない列は全体）


def page(n, row=False):
    cards = "".join(f'<div class="pk{" big" if i == 0 and not row else ""}"><a><div class="pic" style="min-height:120px"></div><div class="pkt"><b>t{i}</b></div></a></div>' for i in range(n))
    return f"<!doctype html><meta charset=utf-8><style>{render.CSS}</style><body><div style='width:1300px'><div class='pkgrid{" row" if row else ""}'>{cards}</div></div></body>"


class PkgridFill(unittest.TestCase):
    def test_css_has_6_7_8_rules(self):
        for k in ("nth-child(6)", "nth-child(7)", "nth-child(8)"):
            self.assertIn(k, render.CSS)

    def test_no_hole_in_last_row_1400(self):
        sys.path.insert(0, str(ROOT / "harness"))
        from browser import launch
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:   # with で閉じる（start() のままだと後ろの試験が「asyncio loop の中」で落ちる）
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001  CI にブラウザが無いとき
                self.skipTest("ブラウザなし: %s" % str(ex)[:80])
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            for w in (1400, 1200, 1100, 900, 761):   # 761〜1200px も 4 列のまま（2026-11-03：2/4/6/8 枚で穴）
                pg.set_viewport_size({"width": w, "height": 900})
                for n in range(1, 10):
                    for row in (False, True) if w < 1201 else (False,):   # .row（似たジャンルの新着）は 2 列の幅だけ
                        pg.set_content(page(n, row).replace("1300px", "100%"))
                        r = pg.evaluate(JS)
                        self.assertLessEqual(r["gap"], 4, "幅 %d・札 %d 枚・row=%s：どこかの列の下が %dpx 空いている" % (w, n, row, r["gap"]))
            b.close()


if __name__ == "__main__":
    unittest.main()
