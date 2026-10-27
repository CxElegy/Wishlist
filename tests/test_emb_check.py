"""エンブレムの点検（harness/emb_check.py）の画像の判断。ネットには出ない。"""
import pathlib
import sys
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
import emb_check  # noqa: E402


class EmbCheck(unittest.TestCase):
    def test_white_box(self):
        im = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
        ImageDraw.Draw(im).ellipse((20, 20, 80, 80), fill=(200, 0, 0, 255))
        self.assertTrue(emb_check.white_box(im))          # 白い地が抜けていないロゴ
        clear = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(clear).ellipse((20, 20, 80, 80), fill=(200, 0, 0, 255))
        self.assertFalse(emb_check.white_box(clear))      # 地を抜いたもの

    def test_cut_edge(self):
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((10, 0, 90, 99), fill=(90, 60, 40, 255))
        self.assertTrue(emb_check.cut_edge(im))           # 頭の上が平らに切れた（上の端の 8 割が不透明 > emblem.TOP_MAX）
        ok = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(ok).ellipse((30, 0, 70, 99), fill=(90, 60, 40, 255))
        self.assertFalse(emb_check.cut_edge(ok))          # 頭の先が少し触れるだけ（顔が見つからない）
        self.assertFalse(emb_check.cut_edge(Image.new("RGB", (50, 50), "red")))   # 写真（切り抜きでない）は見ない
        strip = Image.new("RGBA", (73, 23), (0, 0, 0, 0))
        ImageDraw.Draw(strip).rectangle((10, 2, 60, 22), fill=(20, 20, 30, 255))
        self.assertTrue(emb_check.cut_edge(strip))        # 人物が消えて切れ端だけ（漫威 Black Panther 73×23）

    def test_cut_edge_whole_figure(self):
        im = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((10, 0, 90, 119), fill=(40, 40, 40, 255))
        self.assertTrue(emb_check.cut_edge(im))
        self.assertEqual(emb_check.cut_edge(im, whole=True), "")   # 公式の全身の絵（body の足の裏が画像の中）：ポチタの持ち手

    def test_head_cut(self):
        # 上の 3px に絵が横幅の 20% 以上 = 頭のてっぺんが切れた（BLEACH Mirrors High：顔は全部入っていても ✗）
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((30, -40, 70, 99), fill=(90, 60, 40, 255))   # 上の端の 3 割に髪
        self.assertIn("てっぺん", emb_check.cut_edge(im))

    def test_cut_by_face(self):
        """上の端に当たっていて、目が上から「目〜口」の EYE_TOP 倍より近い = 額まで切れた（YuNet の行を作って渡す）。"""
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((35, -10, 65, 99), fill=(90, 60, 40, 255))   # 上の端に少し当たる
        row = lambda eye, mouth: [(0, 0, 40, 40, 40, eye, 60, eye, 50, 0, 42, mouth, 58, mouth, 0.9), 0, 1.0]
        self.assertTrue(emb_check.cut_edge(im, [row(20, 40)]))    # 目 20px・目〜口 20px：1.0 倍
        self.assertFalse(emb_check.cut_edge(im, [row(40, 60)]))   # 目 40px：2.0 倍（髪の上だけ切れた）

    def test_same_rules_as_emblem(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import emblem
        self.assertEqual((emb_check.TOP_MAX, emb_check.TOP_TOUCH), (emblem.TOP_MAX, emblem.TOP_TOUCH))
        self.assertEqual((emb_check.HEAD_ROWS, emb_check.HEAD_EDGE), (emblem.HEAD_ROWS, emblem.HEAD_EDGE))

    def test_crowd(self):
        big, near, small = (0, 0, 40, 40), (0, 0, 36, 36), (0, 0, 10, 10)
        self.assertTrue(emb_check.crowd([(big, 0, 1), (near, 0, 1)]))    # 2 人写り
        self.assertFalse(emb_check.crowd([(big, 0, 1), (small, 0, 1)]))  # 後ろの小さな顔
        self.assertFalse(emb_check.crowd([(big, 0, 1)]))
        self.assertFalse(emb_check.crowd(None))                          # 顔のモデルなし

    def test_same_video(self):
        self.assertEqual(emb_check.YT.search("https://i.ytimg.com/vi/NuPVr1BxqU8/hq3.jpg").group(1),
                         emb_check.YT.search("https://www.youtube.com/watch?v=NuPVr1BxqU8").group(1))   # Vaundy -1・-2

    def test_same_and_bad_source(self):
        a = Image.linear_gradient("L").resize((120, 120))
        self.assertLessEqual(bin(emb_check.dhash(a) ^ emb_check.dhash(a.resize((90, 90)))).count("1"), emb_check.SAME_BITS)
        self.assertTrue(emb_check.BAD_SOURCE.search("400px-Gulliver_SSBB_Trophy.png"))
        self.assertFalse(emb_check.BAD_SOURCE.search("Gulliver_NH.png"))

    def test_not_people(self):
        """E17：点検の NOT_CHAR は emblem.NOT_CHAR と同じ式。種族・役割・名無しは人でない。店長の版面に今いない。"""
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import emblem
        bad = emb_check.not_char()
        for n in ("Wyverians", "Hunter", "Traveler", "Wonderland Manekin", "Inklings", "Old Man", "Soldier 11", "Pochita", "Makima"):
            self.assertEqual(bad(n), emblem.not_character(n), n)
        self.assertTrue(bad("Wyverians") and bad("Wonderland Manekin") and not bad("Soldier 11"))
        self.assertEqual(emb_check.not_people(), {})


class CloseupWait(unittest.TestCase):
    def test_wait_bad_counts_missing_and_stale(self):
        import datetime as dt
        now = dt.datetime(2026, 10, 27, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
        ok = {"b": {"A": {"n": 1, "next": "2026-10-27T12:47+09:00"}}}
        self.assertEqual(emb_check.closeup_wait_bad(ok, {"b": {"waiting": 1}}, now), [])
        self.assertEqual(len(emb_check.closeup_wait_bad({"b": {"A": {"n": 1}}}, {}, now)), 2)   # next なし・版面の見込みなし
        old = {"b": {"A": {"n": 1, "next": "2026-10-27T07:47+09:00"}}}
        self.assertIn("古い", emb_check.closeup_wait_bad(old, {"b": {"waiting": 1}}, now)[0])

    def test_library_save_passes_E20(self):
        """お客さまの入口が書く config（library_emblem.closeup_fields）を E20 の読み方で数えて ✗ にならない／待ちがなくなれば消える。"""
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import library_emblem
        f = library_emblem.closeup_fields({"Ichigo": 1, "Rukia": 2}, ["Ichigo", "Rukia"])
        self.assertEqual(emb_check.boards_closeup_bad([{"name": "X", "config": f}])[0], [])
        self.assertEqual(library_emblem.closeup_fields({}, []), {"emblem_closeup": None, "emblem_closeup_next": None, "emblem_closeup_eta": None})

    def test_boards_closeup_bad(self):
        import datetime as dt
        now = dt.datetime(2026, 10, 27, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
        good = {"name": "X", "config": {"emblem_closeup": {"A": 1}, "emblem_closeup_next": {"A": "2026-10-27T12:47+09:00"}, "emblem_closeup_eta": {"waiting": 1}}}
        self.assertEqual(emb_check.boards_closeup_bad([good, {"name": "Y", "config": {}}], now), ([], 1))
        bare = {"name": "Z", "config": {"emblem_closeup": {"A": 1}}}   # 保存の抜け（入口が next・eta を書かない）
        bad, n = emb_check.boards_closeup_bad([bare], now)
        self.assertEqual((len(bad), n), (2, 1))
        self.assertIn("お客さま Z", bad[0])


class CloseupOfficial(unittest.TestCase):
    def test_closeup_left_counts_official(self):
        items = [{"name": "A", "emblem_kind": "character", "emblem": [{"subject": "Ichigo", "fs": 0.6}, {"subject": "Rukia", "fs": 0.6}, {"subject": "Body", "fs": 0.7, "body": [1]}, {"subject": "Ok", "fs": 0.3}]},
                 {"name": "B", "emblem_kind": "topic", "emblem": [{"subject": "X", "fs": 0.9}]}]
        got = emb_check.closeup_left(official=lambda it, s: ["u"] if s == "Ichigo" else [], items=items)
        self.assertEqual(got, {"A": (2, 1, ["Ichigo"])})

    def test_threshold_matches_emblem(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import emblem
        self.assertEqual(emb_check.CLOSEUP_FS, emblem.CLOSEUP)

    def test_every_find_bust_call_gets_official(self):
        """顔のアップ→胸像の入口は全部（gather・控え・入れ替え）公式を先に渡す。"""
        import ast
        root = pathlib.Path(__file__).resolve().parent.parent / "scripts"
        n = 0
        for f in ("emblem.py", "emblem_fill.py", "library_emblem.py"):
            for c in ast.walk(ast.parse((root / f).read_text(encoding="utf-8"))):
                if isinstance(c, ast.Call) and getattr(c.func, "attr", getattr(c.func, "id", "")) == "find_bust":
                    n += 1
                    self.assertIn("official", [k.arg for k in c.keywords], f"{f}:{c.lineno} find_bust に official がない")
        self.assertGreaterEqual(n, 3)

    def test_gather_asks_official_first(self):
        """名簿の取り方（gather）も公式の立ち絵を先に探す（Fandom より前）。"""
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        g = src[src.index("\ndef gather(item"):src.index("\ndef gather_roles")]
        self.assertIn("official_for", g)
        self.assertLess(g.index("official_for"), g.index("cutout_on_page"))


if __name__ == "__main__":
    unittest.main()
