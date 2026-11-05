"""お客さまの版面の小元素が Pages から出ること（2026-11-05 test-a：40 版面のうちキャラ・人物の 16 版面で小元素が 0）。
根：#883 で photo_cache_fill.board_text が (本文, Content-Range) の tuple を返し、boards の小元素が 0 件 → 写しから全部消え → /p/ が 404 → 枠ごと消えた。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import emblem_fill  # noqa: E402
import library_emblem  # noqa: E402
import pages_served  # noqa: E402
import photo_cache_fill  # noqa: E402
import photo_store  # noqa: E402
import render  # noqa: E402

ST = {"supabase_url": "https://x.supabase.co", "supabase_key": "k"}
EMB = "https://x.supabase.co/storage/v1/object/public/emblems/Q1-abc.webp"
F1 = "https://commons.wikimedia.org/wiki/Special:FilePath/F1%20logo.svg?width=500"
TW = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/26bd.svg"


class BoardText(unittest.TestCase):
    def test_text_not_tuple(self):
        body = ('[{"config":{"emblem":[{"image":"%s"},{"image":"%s"},{"image":"%s"}]}}]' % (EMB, F1, TW)).encode()
        with mock.patch.object(photo_cache_fill.sbread, "get", return_value=(body, "0-0/1")):
            self.assertIsInstance(photo_cache_fill.board_text(ST), str)
            self.assertEqual(photo_cache_fill.board_emblems(ST), {"Q1-abc.webp"})
            ext = photo_cache_fill.board_external(ST)
        self.assertEqual(sorted(ext.values()), sorted([F1, TW]))
        self.assertTrue(any(n.endswith(".svg") for n in ext) and any(n.endswith(".png") for n in ext))

    def test_unread_keeps_emblem_copies(self):
        """boards を読めない回は小元素の写しを消さない（写真の名前だけ docs から数えて消す）。"""
        with mock.patch.object(photo_cache_fill.sbread, "get", side_effect=OSError("down")):
            self.assertIsNone(photo_cache_fill.board_emblems(ST))
        with tempfile.TemporaryDirectory() as d:
            c = Path(d)
            for n in ("Q1-abc.webp", "x0123456789abcdef.svg", "0123456789abcdef-400.webp"):
                (c / n).write_bytes(b"x")
            with mock.patch.object(photo_cache_fill.browser, "CACHE", c), mock.patch.object(photo_cache_fill, "urls", return_value={}), \
                    mock.patch.object(photo_cache_fill, "board_urls", return_value=None):
                photo_cache_fill.main()
            self.assertEqual(sorted(f.name for f in c.iterdir()), ["Q1-abc.webp", "x0123456789abcdef.svg"])


class Rewrite(unittest.TestCase):
    def test_external_only_when_published(self):
        h = f'<img src="{F1}"><div data-alts="[{{&quot;src&quot;: &quot;{TW}&quot;}}]"></div><img src="{EMB}">'
        with mock.patch.object(photo_store, "pages_on", return_value=True):
            none = photo_store.emblems_to_pages(h, set())
            both = photo_store.emblems_to_pages(h, {photo_store.ext_name(F1), photo_store.ext_name(TW)})
        self.assertIn(F1, none)
        self.assertIn(TW, none)
        self.assertNotIn("supabase.co", none)
        self.assertNotIn("commons.wikimedia.org", both)
        self.assertNotIn("jsdelivr", both)
        self.assertIn(photo_store.PAGES_BASE + "/" + photo_store.ext_name(TW), both)

    def test_pages_stage_takes_svg(self):
        import pages_photos
        self.assertTrue(pages_photos.NAME.fullmatch(photo_store.ext_name(TW)))
        self.assertTrue(pages_photos.NAME.fullmatch(photo_store.ext_name(F1)))


class NextAlt(unittest.TestCase):
    def test_broken_emblem_tries_next_alt(self):
        """読めない小元素は枠ごと消さず次の候補へ。尽きたら消して数える（pages_served が 0 を確かめる）。"""
        self.assertIn("window.WLembNext(this))return", render.IMG_FALLBACK_JS)
        self.assertIn("embGone", render.IMG_FALLBACK_JS)
        self.assertIn("window.WLembNext", render.EMB_JS)

    def test_verdict_counts_gone(self):
        ok, line = pages_served.verdict({"pages": 100, "storage": 0}, [], [("test-a", 2)])
        self.assertFalse(ok)
        self.assertIn("小元素が消えた版面 2", line)
        self.assertTrue(pages_served.verdict({"pages": 100, "storage": 0}, [], [])[0])


class ForeignPhoto(unittest.TestCase):
    ADO = {"why": "Ado（Commons の写真）", "subject": "Ado", "page": "https://commons.wikimedia.org/wiki/File:Alassane_Ouattara_-_2024.jpg",
           "source": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/ca/Alassane_Ouattara_-_2024.jpg/500px-Alassane_Ouattara_-_2024.jpg"}

    def test_other_person(self):
        self.assertTrue(emblem_fill.foreign_photo({"name": "Ado"}, self.ADO))
        self.assertFalse(emblem_fill.foreign_photo({"name": "Ado"}, {**self.ADO, "lock": True}))
        for s, f in [("Satoru Iguchi", "File:Iguchi_Satoru_from_In_Her_Room.jpg"), ("Minju", "File:07072026_ILLIT_MINJU_PhotoCall_1.png"),
                     ("大谷翔平", "File:Shohei_Ohtani.jpg")]:
            self.assertFalse(emblem_fill.foreign_photo({"name": "G"}, {"why": f"{s}（Commons の写真）", "subject": s,
                                                                      "page": "https://commons.wikimedia.org/wiki/" + f}), s)
        self.assertFalse(emblem_fill.foreign_photo({"name": "Ado"}, {**self.ADO, "why": "Ado（Wikidata の代表画像）"}))

    def test_library_runs_board_once(self):
        b = {"id": 1, "name": "Ado", "config": {"emblem": [self.ADO], "emblem_state": {"state": "ok", "have": 1, "v": library_emblem.RULES,
                                                                                   "nv": emblem_fill.NAMES_V, "bv": emblem_fill.BROKEN_V}}}
        self.assertEqual([x["name"] for x in library_emblem.due([b], 0)], ["Ado"])

    def test_board_written_empty_when_only_one_dropped(self):
        """版面の唯一の 1 枚が別人：外したあと空の emblem を config に書く（前は got に emblem がなく前の 1 枚が残った）。"""
        cfg = {"emblem": [self.ADO], "emblem_reject": [self.ADO["source"]],
               "emblem_state": {"state": "ok", "have": 1, "v": library_emblem.RULES, "nv": emblem_fill.NAMES_V, "bv": emblem_fill.BROKEN_V}}

        def fill(item, log=print):
            emblem_fill.drop_foreign_group(next(i for i in emblem_fill.load_items() if i["name"] == item["name"]), log)
            return {"state": "running"}
        b = {"id": 152, "name": "Ado", "config": cfg}
        add = library_emblem.fill_board(b, {"section": "music"}, None, "", fill=fill, get=lambda *a, **k: {})
        self.assertEqual(add["emblem"], [])
        self.assertEqual(add["emblem_state"]["have"], 0)
        # reject に入った画像は fill が触らなくても emblem から外す
        add = library_emblem.fill_board(b, {"section": "music"}, None, "", fill=lambda item, log=print: {"state": "ok"}, get=lambda *a, **k: {})
        self.assertEqual(add["emblem"], [])
        keep = {**self.ADO, "lock": True}
        add = library_emblem.fill_board({**b, "config": {**cfg, "emblem": [keep]}}, {"section": "music"}, None, "",
                                        fill=lambda item, log=print: {"state": "ok"}, get=lambda *a, **k: {})
        self.assertNotEqual(add.get("emblem"), [])

    def test_shop_items_have_none(self):
        bad = [i["name"] for i in emblem_fill.load_items() for x in i.get("emblem") or [] if emblem_fill.foreign_photo(i, x)]
        self.assertEqual(bad, [])
        left = [i["name"] for i in emblem_fill.load_items() for x in i.get("emblem") or []
                if not x.get("lock") and x.get("source") in set(i.get("emblem_reject") or [])]
        self.assertEqual(left, [])   # 店長の版面：reject に入った画像が emblem に残っていない

    def test_dropped_left_counts(self):
        b = {"name": "Ado", "config": {"emblem": [self.ADO, {"source": "s2", "subject": "x"}], "emblem_reject": ["s2"]}}
        self.assertEqual(library_emblem.dropped_left(b), 2)
        self.assertEqual(library_emblem.dropped_left({"name": "Ado", "config": {"emblem": [{**self.ADO, "lock": True}]}}), 0)


if __name__ == "__main__":
    unittest.main()
