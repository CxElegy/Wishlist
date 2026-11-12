"""日付の行（NEW・日付・出典・👍/👎）は、どの列の幅でも重ならず・切れず・右端がそろう（2026-11-13 店長のスマホ：
写真を左に大きく取ったカードの細い字の列で 👍 が日付 11.11 に重なり、👎 が右端で切れた）。
実際の CSS（render.CSS）と行の組み方（render.META_JS）で見本を開き、列の幅を 1px きざみで変えて測る。ブラウザが無い環境では飛ばす。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402

ROW = '<span class="when">{new}{date}{src}<span class="vt">' + render._vote_buttons() + '</span></span>'
CASES = [("<b>NEW</b>", "11.11", ""), ("<b>NEW</b>", "11.11", '<span class="from">にじめん</span>'),
         ("<b>たった今</b>", "10.28", '<span class="from">www.4gamer.net</span>'), ("", "9.30", ""),
         ("<b>NEW</b>", "11.11", '<span class="from">とても長い出典の名前がここに入ります.example.com</span>')]

MEASURE = """() => [...document.querySelectorAll('.when')].map(m => {
  const v = m.querySelector('.vt'), bs = [...v.querySelectorAll('button')].map(b => b.getBoundingClientRect()), box = m.parentElement.getBoundingClientRect();
  const parts = [];
  m.childNodes.forEach(n => { if (n === v) return;
    if (n.nodeType === 3 && n.data.trim()) { const g = document.createRange(); g.selectNodeContents(n); parts.push(...g.getClientRects()); }
    else if (n.nodeType === 1) parts.push(n.getBoundingClientRect()); });
  const hit = bs.some(c => parts.some(a => Math.min(a.right, c.right) - Math.max(a.left, c.left) > 0.5 && Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top) > 0.5));
  const out = parts.some(a => a.right > box.right + 0.5);
  return {hit, out, right: Math.round(bs[bs.length - 1].right - box.right), cut: bs[bs.length - 1].right > innerWidth, down: m.classList.contains('vdown'), lines: new Set(parts.map(a => Math.round(a.top))).size};
})"""


def page(width, touch):
    var = "--vth:36px;--vtw:82px" if touch else ""
    cards = "".join(f'<div class="col" style="width:{width}px;{var}">' + ROW.format(new=n, date=d, src=s) + '</div>' for n, d, s in CASES)
    return (f"<!doctype html><meta charset=utf-8><style>{render.CSS}.col{{margin:0 0 24px;border-right:1px solid red}}"
            f".when{{{var}}}</style><body style='padding:8px 40px'>{cards}<script>{render.META_JS}</script></body>")


class MetaRow(unittest.TestCase):
    def test_css_and_js_are_wired(self):
        self.assertIn(".vdown>.vt{position:static", render.CSS)
        self.assertIn("classList.toggle('vdown'", render.META_JS)
        self.assertIn(render.META_JS.strip()[:60], render.VOTE_JS)   # 本番の投票の脚本に入っている

    def test_no_overlap_or_cut_at_any_width(self):
        sys.path.insert(0, str(ROOT / "harness"))
        from browser import launch
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:
                b = launch(pw)
            except Exception as ex:  # noqa: BLE001  CI にブラウザが無いとき
                self.skipTest("ブラウザなし: %s" % str(ex)[:80])
            pg = b.new_page(viewport={"width": 600, "height": 900})
            for touch in (False, True):
                one_line_right = None
                for w in range(96, 361, 3):
                    pg.set_content(page(w, touch))
                    for i, r in enumerate(pg.evaluate(MEASURE)):
                        tag = "幅 %dpx・指=%s・見本 %d" % (w, touch, i)
                        self.assertFalse(r["hit"], tag + "：👍/👎 が NEW・日付・出典に重なる")
                        self.assertFalse(r["out"], tag + "：NEW・日付が行の外にはみ出す")
                        self.assertFalse(r["cut"], tag + "：👎 が画面の外で切れる")
                        if one_line_right is None and not r["down"]:
                            one_line_right = r["right"]
                        if one_line_right is not None:   # 1 行のときと 2 行に下ろしたときで、👎 の右端は同じ（揃え）
                            self.assertLessEqual(abs(r["right"] - one_line_right), 1, tag + "：👎 の右端がそろわない")
                        if i == 0:
                            self.assertEqual(r["lines"], 1, tag + "：NEW と日付が別の行に割れた")
                # 広い列（PC）では今までどおり 1 行（👍/👎 は日付の行の右端）
                pg.set_content(page(360, touch))
                self.assertFalse(any(r["down"] for r in pg.evaluate(MEASURE)[:4]), "広い列で 👍/👎 が下りた")
            b.close()


if __name__ == "__main__":
    unittest.main()
