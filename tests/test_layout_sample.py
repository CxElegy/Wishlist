import unittest
from scripts.layout_sample import assign


def mk(n, p=0):
    return [dict(href=f"u{p}{i}", title=f"title {p}{i}", img="x") for i in range(n)]


class T(unittest.TestCase):
    def test_no_duplicate_across_boards(self):
        used = {"h": set(), "t": set()}
        a = assign(mk(30), used)
        b = assign(mk(30), used)   # 同じ記事の 2 回目は全部落ちる
        self.assertEqual(sum(map(len, b)), 0)
        self.assertEqual(sum(map(len, a)), 30)

    def test_grid_fills_last_row(self):
        for n in (5, 14, 20, 30, 50):
            hero, rail, grid, more = assign(mk(n), {"h": set(), "t": set()})
            self.assertTrue(len(grid) % 6 == 0 or len(grid) == 0 or n - 4 < 6)


# 2026-11-02 PR #762 の指摘：確かめが手のスクショだけだった。同じ壊れ方（同じ写真の二度出し・格子の穴・目次のずれ）を数える。
# 画面を開いての点検（横はみ出し・目次・空白）は harness/layout_v2_check.py。
import re
from pathlib import Path
from scripts.layout_sample import assign, split_more, emoji, same_photo

PAGE = Path(__file__).resolve().parent.parent / "docs/testground/_after.html"


def st(i, img):
    return dict(href=f"u{i}", title=f"title {i}", img=img)


class Photos(unittest.TestCase):
    def test_same_photo_once(self):
        used = {"h": set(), "t": set(), "p": []}
        parts = assign([st(0, "a.webp"), st(1, "a.webp"), st(2, "b.webp")], used)
        shown = [s for p in parts for s in p]
        self.assertEqual(len(shown), 3)   # 記事は残す
        self.assertEqual(sorted(s["img"] for s in shown if s["img"]), ["a.webp", "b.webp"])   # 写真は 1 回

    def test_emoji_not_a_photo(self):
        hero = assign([st(0, "https://cdn/twemoji/1f408.svg"), st(1, "p.webp")], {"h": set(), "t": set()})[0]
        self.assertEqual(hero[0]["img"], "p.webp")
        self.assertTrue(emoji("x/1f408.svg"))

    def test_hash_near(self):
        a = "0" * 64
        self.assertTrue(same_photo(a, "0" * 61 + "111"))
        self.assertFalse(same_photo(a, "0" * 60 + "1111"))

    def test_more_split_fills_rows(self):
        for n in range(0, 40):
            g, rest = split_more(list(range(n)))
            self.assertEqual(len(g) % 12, 0)
            self.assertLess(len(rest), 12)
            self.assertEqual(len(g) + len(rest), n)


class Page(unittest.TestCase):
    """_after.html は .gitignore（storage の網址を含む）なので、CI ではここで本番 docs/home/ から作る。"""
    @classmethod
    def setUpClass(cls):
        from scripts import layout_sample
        layout_sample.OFFLINE = True   # 写真を網で取りに行かない（取ると 10 分。ここで確かめるのは網址の一意・目次・格子で、写真の見分けは test_hash_near が別に確かめる）
        try:
            layout_sample.main()
        finally:
            layout_sample.OFFLINE = False
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_card_img_urls_unique(self):
        u = re.findall(r'<article class="cd[^>]*><a[^>]*><span class="pic"[^>]*><img src="([^"]+)"', self.html)
        self.assertGreater(len(u), 50)
        self.assertEqual(len(u), len(set(u)))

    def test_no_emoji_card_photo(self):
        self.assertEqual([u for u in re.findall(r'<span class="pic"[^>]*><img src="([^"]+)"', self.html) if emoji(u)], [])

    def test_toc_matches_boards(self):
        ids = re.findall(r'<section class="bd" id="([^"]+)"', self.html)
        toc = re.findall(r'<nav class="toc".*?</nav>', self.html, re.S)[0]
        self.assertEqual(re.findall(r'href="#([^"]+)"', toc), ids)

    def test_grids_fill_last_row(self):
        for m in re.finditer(r'<div class="gr"[^>]*>(.*?)</div>(?=<details|</section>|<div class="rail ls"|</details>)', self.html, re.S):
            n = m.group(1).count('<article class="cd')
            self.assertTrue(n % 6 == 0, n)

    def test_text_card_has_no_pic_hole(self):
        for a in re.findall(r'<article class="cd [^"]*\bnp\b[^"]*">.*?</article>', self.html, re.S):
            self.assertNotIn('class="pic"', a)


import hashlib, json
from scripts import layout_sample


class Measured(unittest.TestCase):
    """layout_ba.py が撮って数えた数字（measure.json）を CI で数える：新しい並べ方が前より悪くない（2026-11-02 の指摘：数字が文章に印字されるだけだった）。"""
    m = json.loads((Path(__file__).resolve().parent.parent / "docs/testground/layout-v2/measure.json").read_text(encoding="utf-8"))

    def test_not_stale(self):   # CSS を変えたら layout_ba.py をやり直して数字を撮り直す
        self.assertEqual(self.m["css_sha"], hashlib.sha256((layout_sample.CSS + layout_sample.JS).encode()).hexdigest()[:16])

    def test_every_place_measured(self):
        self.assertEqual(sorted(self.m["places"]), sorted(sid for sid, _ in layout_sample.PLACES))
        for sid, d in self.m["places"].items():
            self.assertEqual(sorted(d), ["1400", "390"], sid)

    def test_after_has_no_inner_hole_and_no_more_holes(self):
        for sid, d in self.m["places"].items():
            for w, x in d.items():
                self.assertEqual(x["after"]["inner"], 0, f"{sid} {w}: 中が空いたカード")
                self.assertLessEqual(x["after"]["blank"], max(x["before"]["blank"], 0.01), f"{sid} {w}: 穴が前より増えた")

    def test_unmeasurable_photo_numbers_say_so(self):   # 写しが足りない場所は「測れず」と書く（0→0 と書かない）
        h = (Path(__file__).resolve().parent.parent / "docs/testground/layout-v2.html").read_text(encoding="utf-8")
        for sid, c in self.m["photos"].items():
            if c["storage"] > c["cached"]:
                sec = re.search(rf'<section class="pl" id="s-{sid}".*?</section>', h, re.S).group(0)
                self.assertIn("測れず", sec, sid)

    def test_notes_differ_per_place(self):
        h = (Path(__file__).resolve().parent.parent / "docs/testground/layout-v2.html").read_text(encoding="utf-8")
        notes = re.findall(r'<p class="bad">(.*?)</p>', h)
        self.assertGreater(len(notes), 8)
        self.assertEqual(len(notes), len(set(notes)))   # 全部の場所に同じ文を貼らない
