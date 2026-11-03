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


def page(n):
    cards = "".join(f'<div class="pk{" big" if i == 0 else ""}"><a><div class="pic" style="min-height:120px"></div><div class="pkt"><b>t{i}</b></div></a></div>' for i in range(n))
    return f"<!doctype html><meta charset=utf-8><style>{render.CSS}</style><body><div style='width:1300px'><div class=pkgrid>{cards}</div></div></body>"


class PkgridFill(unittest.TestCase):
    def test_css_has_6_7_8_rules(self):
        for k in ("nth-child(6)", "nth-child(7)", "nth-child(8)"):
            self.assertIn(k, render.CSS)

    def test_no_hole_in_last_row_1400(self):
        try:
            from playwright.sync_api import sync_playwright
            sys.path.insert(0, str(ROOT / "harness"))
            from browser import launch
            pw = sync_playwright().start()
            b = launch(pw)
        except Exception as ex:  # noqa: BLE001
            self.skipTest("ブラウザなし: %s" % ex)
        try:
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            for n in range(1, 10):
                pg.set_content(page(n))
                r = pg.evaluate(JS)
                self.assertLessEqual(r["gap"], 4, "札 %d 枚：どこかの列の下が %dpx 空いている" % (n, r["gap"]))
        finally:
            b.close()
            pw.stop()


if __name__ == "__main__":
    unittest.main()
