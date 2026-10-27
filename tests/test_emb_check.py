"""エンブレムの点検（harness/emb_check.py）の画像の判断。ネットには出ない。"""
import pathlib
import sys
import unittest
from unittest import mock

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

    def test_faces_pins_detector_and_reports_drift(self):
        import face_id
        eng = face_id.engine()
        if eng is None:
            self.skipTest("顔のモデルが手元にない")
        emb_check.DRIFT.clear()
        eng[0].setScoreThreshold(0.5)
        try:
            emb_check._faces(Image.new("RGBA", (80, 80), (200, 120, 90, 255)))
            self.assertEqual(emb_check.DRIFT, [0.5])   # 戻し忘れを数える
            self.assertAlmostEqual(eng[0].getScoreThreshold(), face_id.SCORE, places=5)   # 測りは標準で
        finally:
            eng[0].setScoreThreshold(face_id.SCORE)
            emb_check.DRIFT.clear()

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

    def test_every_gather_asks_official_first(self):
        """名簿の取り方の全入口（gather・gather_wide・gather_pages・gather_roles）が official_cands を呼び、Fandom より前に置く。"""
        import ast
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fns = {f.name: f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name.startswith("gather")}
        want = {"gather", "gather_wide", "gather_pages", "gather_roles"}
        self.assertTrue(want <= set(fns))
        for n in want:
            seg = ast.get_source_segment(src, fns[n])
            self.assertIn("official_cands(", seg, f"{n} が公式を先に探していない")
            for fandom in ("cutout_on_page(", "page_image(api", "role_images("):
                if fandom in seg:
                    self.assertLess(seg.index("official_cands("), seg.index(fandom), f"{n}：公式が {fandom} より後")

    def test_fandom_over_official_counts(self):
        items = [{"name": "A", "emblem_kind": "character", "emblem": [{"subject": "Ichigo", "why": "Ichigo（Fandom のページ）"}, {"subject": "Rukia", "why": "Rukia（Fandom のページ）"}, {"subject": "Ai", "why": "Ai（公式サイトの立ち絵）"}]},
                 {"name": "B", "emblem_kind": "group", "emblem": [{"subject": "X", "why": "Fandom"}]}]
        got = emb_check.fandom_over_official(official=lambda it, s: ["u"] if s in ("Ichigo", "Ai") else [], items=items)
        self.assertEqual(got, {"A": ["Ichigo"]})

    def test_fandom_rows_match_e21(self):
        """取り直しの対象（fandom_rows）と点検 E21 が同じ人を数える。固定・人物（emblem_people）・公式にない人は対象外。"""
        import emblem_fill as ef
        items = {"name": "A", "emblem_kind": "character", "emblem": [
            {"subject": "Ichigo", "why": "Ichigo（Fandom のページ）", "shape": "cutout"},
            {"subject": "Rukia", "why": "Rukia（Fandom のページ）", "shape": "cutout", "lock": True},
            {"subject": "Nobody", "why": "Nobody（Fandom のページ）", "shape": "cutout"},
            {"subject": "Ai", "why": "Ai（公式サイトの立ち絵）", "shape": "cutout"}]}
        with mock.patch.object(ef.emblem, "official_for", side_effect=lambda it, x: ["u"] if x["subject"] != "Nobody" else []):
            rows = [x["subject"] for x in ef.fandom_rows(items)]
            self.assertEqual(rows, ["Ichigo"])
            self.assertEqual(emb_check.fandom_over_official(official=lambda it, s: ["u"], items=[items]), {"A": ["Ichigo", "Rukia", "Nobody"]})   # E21 は固定も数える（見張りは広め）
            self.assertEqual(ef.fandom_rows({**items, "emblem_people": True}), [])

    def test_official_swap_replaces_and_keeps_on_failure(self):
        import emblem_fill as ef
        from PIL import Image
        item = {"name": "A", "emblem_kind": "character", "emblem": [
            {"subject": "Ichigo", "why": "Ichigo（Fandom のページ）", "shape": "cutout", "image": "emblems/a-ichigo.webp", "source": "f1", "face": [1]},
            {"subject": "Rukia", "why": "Rukia（Fandom のページ）", "shape": "cutout", "image": "emblems/a-rukia.webp", "source": "f2"}]}
        saved = {}
        def fb(api, title, **kw):
            return ("https://o/char/ichigo/body.webp", Image.new("RGBA", (4, 4)), None) if title == "Ichigo" else None
        with mock.patch.object(ef.emblem, "official_for", return_value=["https://o/char/x/body.webp"]), mock.patch.object(ef.emblem, "official_site", return_value="https://o/"), \
                mock.patch.object(ef.emblem, "find_bust", side_effect=fb), mock.patch.object(ef.emblem, "save_cut", side_effect=lambda im, slug: saved.setdefault("s", slug)), \
                mock.patch.object(ef.emblem, "write_item", side_effect=lambda n, rows, r: saved.setdefault("rows", rows)), mock.patch.object(ef.emblem_face, "measure_item"), \
                mock.patch.object(ef, "load_items", return_value=[item]), mock.patch.object(ef, "closeup_of", return_value=False), mock.patch.object(ef, "broken_image", return_value=False):
            self.assertEqual(ef.official_swap(item, log=lambda *a: None), 1)
        rows = {x["subject"]: x for x in saved["rows"]}
        self.assertEqual(rows["Ichigo"]["source"], "https://o/char/ichigo/body.webp")
        self.assertNotIn("face", rows["Ichigo"])
        self.assertIn("公式サイト", rows["Ichigo"]["why"])
        self.assertEqual(rows["Rukia"]["source"], "f2")   # 取れなかった人は元のまま

    def test_official_swap_is_in_background_chain(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        self.assertIn("| official_swap(item, log)", src)


if __name__ == "__main__":
    unittest.main()
