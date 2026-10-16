"""Tests for the design rules: things added later (new genres, new components, new CSS) must still follow them.

    python -m unittest discover tests

What is checked (see PRODUCT.md, Accessibility & Inclusion):
- Text is no smaller than 10px anywhere in the CSS (functional text is 11px; decorative English labels are 10px)
- Colours used repeatedly come from the design tokens (:root), not raw hex
- Genre colours, including those auto-assigned to new genres, reach 4.5:1 both with white text and as small text on a light background
- The future-content components (price, date, video, gallery, upcoming schedule) render, and break nothing when their fields are missing or malformed
"""

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import render  # noqa: E402
import theme  # noqa: E402

PAPER, WHITE = theme._rgb("#EDEBE6"), (255, 255, 255)


def all_css():
    return render.CSS + "".join(render.NAV_STYLES.values())


class Typography(unittest.TestCase):
    def test_no_text_below_10px(self):
        sizes = [int(x) for x in re.findall(r"font(?:-size)?:[^;}]*?\b(\d+)px", all_css())]
        self.assertTrue(sizes)
        self.assertGreaterEqual(min(sizes), 10, "CSS has text under 10px (functional text 11px, English labels 10px)")


class Tokens(unittest.TestCase):
    TOKENS = ("--ink", "--paper", "--rose", "--sheet", "--card", "--gold", "--alert",
              "--font-sans", "--font-serif", "--font-mono", "--fs-label")

    def test_tokens_defined(self):
        root = re.search(r":root\{([^}]*)\}", render.CSS).group(1)
        for t in self.TOKENS:
            self.assertIn(t + ":", root, t)

    def test_core_colors_not_hardcoded(self):
        """Main colours (ink, paper, rose …) are written with var(--…). Only the :root definitions may contain the hex values."""
        css = re.sub(r":root\{[^}]*\}", "", all_css())
        for hex_ in ("#1A1C22", "#EDEBE6", "#B8336A", "#F4EDE4", "#FBF8F1"):
            self.assertNotIn(hex_.lower(), css.lower(), f"{hex_} should be written as a var() token")


class Genres(unittest.TestCase):
    def assert_aa(self, color, what):
        rgb = theme._rgb(color)
        self.assertGreaterEqual(theme.contrast(rgb, WHITE), 4.5, f"{what} {color} white text")
        self.assertGreaterEqual(theme.contrast(rgb, PAPER), 4.5, f"{what} {color} on light background")

    def test_known_and_new_genres(self):
        for name, color in render.SECTIONS.items():
            self.assert_aa(color, name)
        for color in render.GENRE_EXTRA:
            self.assert_aa(color, "spare colour for new genres")

    def test_new_genre_gets_stable_color_and_labels(self):
        c = render._sec_color("旅行")
        self.assertIn(c, render.GENRE_EXTRA)
        self.assertEqual(c, render._sec_color("旅行"))          # same colour every time
        self.assertEqual(render._sec_name("旅行"), "旅行")       # not in the table: the name as written
        self.assertEqual(render._sec_en("Books"), "BOOKS")
        self.assertEqual(render._sec_en("旅行"), "")
        self.assertEqual(render._sec_name("游戏"), "ゲーム")


class Components(unittest.TestCase):
    def test_price_event_gallery(self):
        out = render._extras({"price": {"now": "¥3,980", "was": "¥4,980", "off": "-20%", "until": "2026-10-20"},
                              "event": {"date": "2026-11-19", "label": "発売日", "time": "10:00"},
                              "gallery": ["https://e.com/1.jpg", "javascript:alert(1)", "https://e.com/2.jpg"]})
        self.assertIn("<b>¥3,980</b><s>¥4,980</s><i>-20%</i><span>10.20 まで</span>", out)
        self.assertIn("<b>11.19</b><span>発売日 · 10:00</span>", out)
        self.assertEqual(out.count("<img"), 2)                 # http(s) images only
        self.assertNotIn("javascript", out)

    def test_missing_or_broken_fields_render_nothing(self):
        for story in ({}, {"price": "安い"}, {"price": {}}, {"event": {"label": "日付なし"}}, {"gallery": "x"}, {"video": "ftp://x"}):
            self.assertEqual(render._extras(story) + render._play(story), "", story)

    def test_escaping(self):
        out = render._extras({"price": {"now": "<b>x</b>"}, "event": {"date": "2026-11-19", "place": "<script>"}})
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", out)

    def test_video_badge_on_cards(self):
        story = {"url": "https://e.com/a", "headline": "予告編公開", "_issue": "2026-10-15", "date": "2026-10-15",
                 "image": "https://e.com/a.jpg", "video": "https://www.youtube.com/watch?v=x", "weight": "normal"}
        for kw in ({"mini": True}, {}, {"small": True}):
            self.assertIn('class="xplay"', render._tcard(story, 4, 0, "2026-10-15", **kw), kw)

    def test_agenda_future_sorted_and_deduped(self):
        mk = lambda d, h: {"url": f"https://e.com/{h}", "headline": h, "_issue": "2026-10-10", "event": {"date": d, "label": "発売"}}
        works = [{"name": "A", "section": "游戏", "stories": [mk("2026-11-01", "b"), mk("2026-10-01", "old"), mk("2026-10-20", "a")]},
                 {"name": "B", "section": "旅行", "stories": [mk("2026-10-20", "a"), {"url": "u", "headline": "x", "_issue": "2026-10-10"}]}]
        out = render._agenda(works, "2026-10-15")
        self.assertNotIn("old", out)                           # past dates are not shown
        self.assertLess(out.index(">a<"), out.index(">b<"))    # date order
        self.assertEqual(out.count(">a<"), 1)                  # same day and same headline only once
        self.assertEqual(render._agenda([{"name": "A", "stories": []}], "2026-10-15"), "")


class Redesign(unittest.TestCase):
    """2026-10-16 の見た目：作品ごとの装飾、トップのポスターの取色。"""

    def test_motif_classes_exist_for_every_motif(self):
        for name in render.MOTIFS:
            self.assertIn(f".m-{name}", render.CSS, name)

    def test_unknown_motif_is_ignored(self):
        block = {"name": "X", "theme": dict(theme.DEFAULT), "stories": [], "_today": "2026-10-16", "_motif": "nope"}
        self.assertNotIn("m-nope", render._section(block, "w"))
        block["_motif"] = "manga"
        self.assertIn('class="sec m-manga', render._section(block, "w"))

    def test_poster_colors_from_cache_are_readable(self):
        url = "https://e.com/top.jpg"
        cache = {f"hero|{url}": {"bg": "#201226", "fg": "#F2EEE6", "accent": "#CF636F", "alt_bg": "#F0E7F3",
                                 "alt_fg": "#1A1C22", "alt_accent": "#BB3A48"}}
        style = render._poster_colors({"image": url}, cache)
        self.assertIn("--tint:#F0E7F3", style)
        deep = style.split("--deep:")[1].split(";")[0]
        self.assertGreaterEqual(theme.contrast(theme._rgb(deep), theme._rgb("#F0E7F3")), 4.5)
        self.assertEqual(render._poster_colors({"image": url}, None), "")  # キャッシュなし（テスト）：既定の色


class FrontSide(unittest.TestCase):
    def test_side_column_parts_and_empty(self):
        works = [{"name": "A", "section": "游戏", "stories": [{"url": "u", "headline": "h", "_issue": "2026-10-16"}],
                  "_heat": {"score": 72, "label": "盛り上がり", "delta": 12, "rising": True, "top": "volume",
                            "dims": [{"key": "volume", "name": "報道量", "weight": 20, "score": 80, "note": "7 日で 9 件"}]}}]
        wishes = [{"name": "マグ", "price": 850, "currency": "NT$", "image": "mug.jpg"}, {"name": "済み", "status": "已入手"}]
        out = render._side(works, "2026-10-16", wishes, [["作品:A", 3]])
        self.assertIn("欲しい物リスト", out)
        self.assertIn('src="wishlist/mug.jpg"', out)
        self.assertNotIn("済み", out)                       # 入手済みは出さない
        self.assertIn("話題度ランキング", out)
        self.assertIn("<em>急上昇</em>", out)
        self.assertIn("報道量（7 日で 9 件）", out)            # いちばん効いている指標を title に
        self.assertIn("<span>A</span><b>+3</b>", out)      # 作品: の接頭辞は外す
        self.assertNotIn("これからの予定", out)             # 日付のある記事がなければ出さない
        self.assertEqual(render._side([], "2026-10-16"), "")


class HeatBadge(unittest.TestCase):
    H = {"score": 64, "label": "盛り上がり", "delta": None, "rising": False, "top": "event", "missing": ["一般の関心"],
         "dims": [{"key": "event", "name": "出来事", "weight": 20, "score": 90, "note": "重要ニュース 2 件 <b>"}]}

    def block(self, h):
        return {"name": "X", "theme": dict(theme.DEFAULT), "_today": "2026-10-16", "stories": [], "_heat": h}

    def test_badge_with_breakdown(self):
        out = render._section(self.block(self.H), "w")
        self.assertIn('<details class="heat">', out)            # 前週比がない：矢印もクラスもなし
        self.assertIn("<b>64</b>", out)
        self.assertIn("前週比はデータ集め中", out)
        self.assertIn("データなし（計算に入れていません）：一般の関心", out)
        self.assertIn("重要ニュース 2 件 &lt;b&gt;", out)       # 文字は転義
        self.assertNotIn("急上昇", out)

    def test_trend_and_rising(self):
        out = render._section(self.block({**self.H, "delta": 15, "rising": True}), "w")
        self.assertIn('class="heat up"', out)
        self.assertIn("急上昇", out)
        self.assertEqual(render._trend(-12)[0], "down")
        self.assertEqual(render._trend(3)[0], "flat")

    def test_no_badge_without_data(self):
        self.assertNotIn('class="heat', render._section(self.block(None), "w"))
        self.assertNotIn('class="heat', render._section(self.block({**self.H, "score": 0}), "w"))


class HeatPage(unittest.TestCase):
    """話題度の分析ページ（docs/heat.html）。"""

    def analysis(self, **over):
        h = {"score": 64, "label": "盛り上がり", "delta": None, "rising": False, "top": "event", "missing": ["一般の関心"],
             "dims": [{"key": "event", "name": "出来事", "weight": 20, "score": 90, "note": "<script>x</script>"},
                      {"key": "volume", "name": "報道量", "weight": 20, "score": 38, "note": "7 日で 3 件"}],
             "trend": [("2026-10-15", 60), ("2026-10-16", 64)],
             "articles": [("2026-10-15", 2), ("2026-10-16", 1)], "wiki": [], **over}
        return {"today": "2026-10-16", "baseline_from": "2026-10-21", "items": {"X": h}}

    def test_page_parts(self):
        out = render.render_heat(self.analysis(), [{"name": "X", "section": "游戏", "subtitle": "サブ"}], "10.16 12:00")
        for part in ("話題度アナリシス", 'id="ranking"', 'id="movers"', 'id="method"', 'id="h-' + render._wid("X") + '"',
                     "準備中", "10/21 から使えます", "サブ", "数値を表で見る"):
            self.assertIn(part, out, part)
        self.assertNotIn("<script>x</script>", out)               # 根拠の文字は転義
        self.assertIn("&lt;script&gt;", out)
        self.assertIn('class="hm na"', out)                       # データなしの指標は斜線のマス
        self.assertIn("前週比は、7 日前の時点で", out)             # 前週比がまだない：説明だけ
        self.assertIn('class="hm q4"', out)                       # 90 点 → いちばん濃い
        self.assertIn('class="hm q1"', out)                       # 38 点

    def test_movers_and_rising(self):
        out = render.render_heat(self.analysis(delta=-14, rising=True), [{"name": "X", "section": "游戏"}], "u")
        self.assertIn('<i class="down"', out)
        self.assertIn('<em class="rise">急上昇</em>', out)

    def test_chart_text_is_html_and_empty_state(self):
        out = render._chart([("2026-10-15", 3), ("2026-10-16", 12)], "bar", "--viz-1", "件", partial_last=True, caption="記事")
        self.assertIn('class="cl yt"', out)                       # 目盛りは HTML（伸ばしてもつぶれない）
        self.assertNotIn("<text", out)
        self.assertIn("今日は集計途中", out)
        self.assertIn("まだデータがありません", render._chart([("2026-10-16", 0)], "bar", "--viz-1", "件", caption="記事"))

    def test_entry_links_from_front_page(self):
        works = [{"name": "A", "section": "游戏", "stories": [],
                  "_heat": {"score": 50, "label": "話題", "delta": None, "top": "", "dims": []}}]
        self.assertIn('href="heat.html"', render._side(works, "2026-10-16"))
        block = {"name": "A", "theme": dict(theme.DEFAULT), "_today": "2026-10-16", "stories": [], **works[0]}
        self.assertIn('href="heat.html#h-' + render._wid("A") + '"', render._section(block, "w"))


if __name__ == "__main__":
    unittest.main()
