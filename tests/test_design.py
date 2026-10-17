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


    def test_css_comments_closed(self):
        # 閉じていない CSS コメントは、後ろの規則を飲み込んで消してしまう
        import re
        css = re.sub(r"/\*.*?\*/", "", render.CSS, flags=re.S)
        self.assertNotIn("/*", css)
        self.assertNotIn("*/", css)

class AdminPage(unittest.TestCase):
    DATA = {"pipeline": {"report": "2026-10-16", "inbox": "2026-10-16", "unedited": ["2026-10-15"], "items": 2, "stale": 1},
            "items": [{"name": "A<b>", "section": "游戏", "type": "game", "size": "L", "week": 5, "urgent": 1, "last_days": 0,
                       "heat": {"score": 40, "delta": 3}, "missing": ["wiki"], "web": True},
                      {"name": "B", "section": "新ジャンル", "type": "show", "size": "S", "week": 0, "last_days": None,
                       "heat": None, "missing": []}],
            "votes": {"total": 2, "up": 1, "down": 1, "week": 3, "last": "10/16 12:00", "works": [["A<b>", 1, 1]],
                      "recent": [{"url": "javascript:alert(1)", "title": "<i>t</i>", "vote": 1, "when": "10/16"}]}}

    def test_parts_and_escaping(self):
        out = render.render_admin(self.DATA, {"url": "https://x.supabase.co", "key": "k"}, "10.16 12:00")
        for part in ('id="status"', 'id="queue"', 'id="items"', 'id="votes"', "設定ページから追加", "+3", "記事なし",
                     'class="last stale"', "そろっている", "list_item_requests", "get_photo_inbox"):
            self.assertIn(part, out, part)
        self.assertNotIn("<i>t</i>", out)
        self.assertNotIn("A<b>", out)
        self.assertNotIn('href="javascript:', out)
        # データを変える操作はない：ボタンは流れを開く・閉じるものと、裏の仕組みを早く動かす「今すぐ実行」だけ
        for b in re.findall(r"<button[^>]*>", out):
            self.assertRegex(b, r"data-(open|close|run)", b)   # 流れを開く・閉じる、または「今すぐ実行」（データは変えない）
        self.assertNotIn("<form", out)

    def test_empty(self):
        out = render.render_admin({}, {}, "u")
        self.assertIn("まだ投票がありません", out)
        self.assertIn("ウォッチ項目がありません", out)

    def test_admin_css_follows_rules(self):
        sizes = [int(x) for x in re.findall(r"font(?:-size)?:[^;}]*?\b(\d+)px", render.ADMIN_PAGE_CSS)]
        self.assertGreaterEqual(min(sizes), 10)
        self.assertNotRegex(render.ADMIN_PAGE_CSS, r"#[0-9A-Fa-f]{3,6}\b")


if __name__ == "__main__":
    unittest.main()


class Nav(unittest.TestCase):
    """左の目次（v6、testground/compare.html で決めた形）：板块ごとの枠、小分類の札、アイコン、隠し始める件数。"""

    def works(self):
        st = lambda d: {"url": "https://x/" + d, "title": "t", "_issue": d}
        return [{"name": "A<b>", "section": "游戏", "stories": [st("2026-10-16")], "_thumb": "https://img/a.jpg"},
                {"name": "B", "section": "游戏", "stories": [], "_emblems": [{"image": "emblems/b-x.webp"}]},
                {"name": "C", "section": "影视", "stories": [st("2026-09-01")]}]

    def test_slots_icons_and_escaping(self):
        out = render._nav(self.works(), "2026-10-16")
        self.assertEqual(out.count('class="nslot"'), 2)               # 板块ごとに 1 枠
        self.assertIn('data-hide="24"', out)                          # 既定は 24 件まで隠さない
        self.assertIn("A&lt;b&gt;", out)
        self.assertNotIn("A<b>", out)
        self.assertIn("emblems/b-x.webp", out)                        # emblem が作品アイコン
        self.assertIn("https://img/a.jpg", out)                       # なければ記事の写真
        self.assertIn('<i class="ic">C</i>', out)                     # それもなければ頭文字
        self.assertIn('data-hot="1"', out)                            # 今週の件数（新着順に残すとき使う）
        self.assertIn("新着 <b>1</b>／2", out)
        self.assertNotIn('class="nsubs"', out)                         # 小分類がなければ札は出さない

    def test_sub_chips_and_hide_setting(self):
        out = render._nav(self.works(), "2026-10-16", subs={"A<b>": "新作", "B": "運営中"}, hide="auto")
        self.assertIn('class="nsubs"', out)                            # 小分類が 2 つ以上なら札
        self.assertEqual(out.count('class="nlab"'), 2)
        self.assertIn('data-hide="auto"', out)

    def test_nav_css_follows_rules(self):
        css = render.NAV_STYLES["line"]
        for cls in (".nav .nslot", ".nav .nsec", ".nav .nsubs", ".nav .x"):
            self.assertIn(cls, css + render.CSS, cls)

    def test_icon_comes_first(self):
        w = {"name": "M", "section": "影视", "stories": [], "_icon": "icons/marvel.webp", "_emblems": [{"image": "emblems/x-y.webp"}]}
        self.assertEqual(render._nav_icon(w), "icons/marvel.webp")        # icon（1 作品 1 枚）が emblem より先
        self.assertEqual(render._nav_icon({**w, "_icon": "javascript:x"}), "emblems/x-y.webp")   # 変な値は使わない

class LiveUpdate(unittest.TestCase):
    """開いたままのページに新しい内容を出す（render.LIVE_JS / stamp / version.json）。"""

    def test_stamp_ignores_update_time(self):
        a, va = render.stamp(f'<meta content="{render.VER_MARK}"><b>10.17 08:35</b>x', "10.17 08:35")
        b, vb = render.stamp(f'<meta content="{render.VER_MARK}"><b>10.17 10:35</b>x', "10.17 10:35")
        c, vc = render.stamp(f'<meta content="{render.VER_MARK}"><b>10.17 10:35</b>y', "10.17 10:35")
        self.assertEqual(va, vb)
        self.assertNotEqual(va, vc)
        self.assertIn(f'content="{va}"', a)
        self.assertNotIn(render.VER_MARK, a)

    def test_admin_has_live_and_panel_marks(self):
        out = render.render_admin({"pipeline": {}, "items": [], "votes": {}}, {}, "10.17 08:35")
        self.assertIn('name="wl-ver" data-page="admin"', out)
        self.assertIn("version.json", out)
        self.assertRegex(out, r'<section class="panel" id="status" data-h="[0-9a-f]{8}">')
        again = render.render_admin({"pipeline": {}, "items": [], "votes": {}}, {}, "10.17 10:35")
        mark = lambda h, i: re.search(rf'id="{i}" data-h="(\w+)"', h).group(1)
        self.assertEqual(mark(out, "backend"), mark(again, "backend"))  # 時刻だけ違うパネルは「更新」にしない

    def test_live_css_uses_tokens(self):
        self.assertNotRegex(render.LIVE_CSS, r"#[0-9A-Fa-f]{6}\b")

    def test_busy_plan(self):
        plan = render.busy_plan({"edit": {"items": ["GTA 6"]}, "emblem-cron": {"items": []}, "collect": {"items": []}},
                                ["GTA 6", "あつ森"], {"url": "https://x.supabase.co", "key": "k"})
        by = {p["id"]: p for p in plan["procs"]}
        self.assertEqual(set(by), {"edit"})   # 収集は Supabase の版面ごとの状態、ページ生成は帯なし、空の待ち行列も帯なし
        self.assertEqual(by["edit"]["boards"], [render._wid("GTA 6")])   # 待ち行列の版面だけ
        self.assertEqual(plan["ids"]["あつ森"], render._wid("あつ森"))
        self.assertTrue(by["edit"]["slots"])
        self.assertIn("rpc/live_status", render.BUSY_JS)
        self.assertNotRegex(render.BUSY_CSS, r"#[0-9A-Fa-f]{6}\b")   # 色は版面の --acc / --bg / --fg だけ
        self.assertIn("z-index:4", render.BUSY_CSS)   # 小元素（z-index 5）の下
        tag = render._busy_tag(plan, "2026-10-17T00:00:00+00:00")
        self.assertIn('id="wl-busy"', tag)
        self.assertIn('"gen": "2026-10-17T00:00:00+00:00"', tag)
        self.assertEqual(render._busy_tag(None, ""), "")



class NavParents(unittest.TestCase):
    """目次の小分類（板块ごとに必ず）と上下級（案 A：枝線、同じ大きさ、たたまない）。"""

    def works(self):
        return Nav.works(self)

    def test_one_sub_still_shows_chips(self):
        out = render._nav(self.works(), "2026-10-16", subs={"A<b>": "新作", "B": "新作", "C": "ドラマ"})
        self.assertEqual(out.count('class="nsubs"'), 2)                # 小分類が 1 つだけの板块（映像）でも札を出す

    def test_parent_kid_branch(self):
        st = lambda u: {"url": u, "title": "t", "_issue": "2026-10-16"}
        ws = [{"name": "漫威电影", "section": "影视", "stories": [st("a"), st("b")]},
              {"name": "FROM", "section": "影视", "stories": []},
              {"name": "Spider", "section": "影视", "stories": [st("b")]},
              {"name": "Daredevil", "section": "影视", "stories": []}]
        parents = {"Spider": "漫威电影", "Daredevil": "漫威电影"}
        out = render._nav(ws, "2026-10-16", subs={"漫威电影": "映画", "FROM": "ドラマ", "Spider": "映画", "Daredevil": "ドラマ"}, parents=parents)
        order = re.findall(r'data-for="([^"]+)"', out)
        self.assertEqual(order[order.index("漫威电影"):order.index("漫威电影") + 3], ["漫威电影", "Spider", "Daredevil"])   # 下級は上級のすぐ下
        self.assertEqual(out.count('class="pill kid"'), 2)
        self.assertIn('<span class="xref">ドラマ</span>', out)        # 自分の小分類が上級と違う
        self.assertNotIn("x kid", out)                                # 下級を特別にたたまない
        works = render._dedupe_parents(ws, parents)                  # 同じニュースは下級だけに
        self.assertEqual([x["url"] for x in works[0]["stories"]], ["a"])
        self.assertEqual([x["url"] for x in works[2]["stories"]], ["b"])
