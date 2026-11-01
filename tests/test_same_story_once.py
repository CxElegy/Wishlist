"""L7「同じ記事は 1 ページに 1 回」：次のニュースに出した記事は元のカードを畳み、ux_check が二重を数える（2026-11-01）。"""
import pathlib
import sys
import unittest

R = pathlib.Path(__file__).resolve().parents[1]
RENDER = (R / "scripts" / "render.py").read_text(encoding="utf-8")
UX = (R / "harness" / "ux_check.py").read_text(encoding="utf-8")


class SameStoryOnce(unittest.TestCase):
    def test_nx_sources_are_folded(self):
        self.assertIn(".nxd,.dupd{display:none!important}", RENDER)
        self.assertIn("c._nxSrc.forEach(a => a.classList.add('nxd'))", RENDER)
        self.assertIn("(c._nxSrc || []).forEach(a => a.classList.remove('nxd'))", RENDER)   # 外すとき元のカードを戻す
        self.assertIn("!a.classList.contains('nxd')", RENDER)                                # 使った記事を別の次のニュースに使わない

    def test_ux_check_counts_duplicates(self):
        self.assertIn("sameStory", UX)
        self.assertIn("同じ記事がページに 2 回以上", UX)

    def test_page_wide_pass_exists(self):
        self.assertIn("const once = () =>", RENDER)   # ポスター → 壁 → 予定 → 版面の順に、もう出した記事のカードを畳む
        self.assertIn(".nxd,.dupd{display:none!important}", RENDER)
        self.assertIn("a.lk[href],.nx a[href],.agenda li a[href],.pk a[href]", UX)   # 点検は版面の中だけでなくページ全体

    def test_front_stories_leave_the_boards(self):
        """実際に描く：トップ（ポスター・ほかの注目）に出た記事は、版面の HTML に 2 回目が出ない。"""
        sys.path.insert(0, str(R / "scripts"))
        import render
        th = {"bg": "#000", "fg": "#fff", "accent": "#f00", "alt_bg": "#fff", "alt_fg": "#000", "alt_accent": "#f00"}
        def st(i, w="normal"):
            return {"url": f"https://example.com/{i}", "headline": f"消息 {i}", "weight": w, "date": "2026-10-12",
                    "_issue": "2026-10-12", "image": f"https://example.com/{i}.jpg"}
        items = [{"name": n, "section": "影视", "subtitle": "", "cover": None, "facts": [], "theme": th,
                  "stories": [st(i + 10 * k, "hero" if i == 0 else "normal") for i in range(5)]} for k, n in enumerate("ABC")]
        page = render.render([{"no": 1, "date": "2026-10-12", "items": items}], order=["A", "B", "C"])
        import re
        hrefs = re.findall(r'<a class="(?:lk|card)[^"]*" href="([^"]+)"', page) + re.findall(r'<a href="([^"]+)" class="lk"', page)
        top = re.findall(r'<article class="top".*?</article>', page, re.S)
        self.assertTrue(top)
        used = set(re.findall(r'https://example\.com/\d+', top[0])) | set(re.findall(r'<article class="wc.*?</article>', page, re.S) and
                                                                         re.findall(r'https://example\.com/\d+', "".join(re.findall(r'<article class="wc.*?</article>', page, re.S))))
        body = page.split('class="subhead"')[-1] if 'class="subhead"' in page else page[page.index("</section>", page.index('id="front"')):]
        for u in used:
            self.assertNotIn(u + '"', body, u)

    def test_picks_are_in_the_rule(self):
        """気になるかも（.pk）も対象：once() が数え、トップに出た記事は _picks が外す。"""
        self.assertIn(".agenda li a[href], .pk a[href], section.sec a.lk[href]", RENDER)
        self.assertIn("_picks(picks, works, fb, front_used)", RENDER)
        sys.path.insert(0, str(R / "scripts"))
        import render
        pk = lambda u: {"title": f"t{u}", "url": f"https://example.com/{u}", "work": "A", "source": "s", "date": "2026-10-12", "hits": [], "because": "x"}
        h = render._picks([pk(1), pk(2)], [{"name": "A", "_thumb": None}], None, {"https://example.com/1"})
        self.assertNotIn("example.com/1\"", h)
        self.assertIn("example.com/2", h)


if __name__ == "__main__":
    unittest.main()
