"""顔なしの 3 分け（emblem_face.none_kind）と体の枠でそろえる表示（render .nb）・③を替える（emblem_fill.replace_nf）。"""
import pathlib
import sys
import unittest
from unittest import mock

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem  # noqa: E402
import emblem_face  # noqa: E402
import emblem_fill  # noqa: E402
import render  # noqa: E402


def fig(w=320, h=400, box=(60, 40, 260, 380)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle(box, fill=(200, 30, 30, 255))
    return im


class NoneKind(unittest.TestCase):
    def test_constants_match_emblem(self):
        self.assertEqual(emblem_face.BUST_MIN_SIDE, emblem.BUST_MIN_SIDE)

    def test_three_kinds(self):
        with mock.patch.object(emblem_face, "none_reason", return_value="noface"):
            self.assertEqual(emblem_face.none_kind(fig(), {"image": "emblems/dota2-zeus.webp", "subject": "Zeus"}), "keep")   # ① 名前のあるキャラ
            self.assertEqual(emblem_face.none_kind(fig(), {"image": "emblems/x-item-stella.webp", "subject": "Stella"}), "symbol")   # ② 物
            self.assertEqual(emblem_face.none_kind(fig(200, 150, (0, 0, 190, 140)), {"image": "emblems/a.webp"}), "replace")   # ③ 小さすぎ
        with mock.patch.object(emblem_face, "none_reason", return_value="sheet"):
            self.assertEqual(emblem_face.none_kind(fig(), {"image": "emblems/dota2-ursa.webp"}), "replace")   # ③ 向きを並べた図

    def test_body_box(self):
        self.assertEqual(emblem_face.body_box(fig()), [0.1, 0.953, 0.188, 0.816])

    def test_store_writes_kind_and_box_only_when_no_face(self):
        x = {"image": "emblems/zeus.webp"}
        with mock.patch.object(emblem_face, "measure", return_value=[0, 0, 0.5, 0.5, 320, 400]), mock.patch.object(emblem_face, "none_reason", return_value="noface"):
            emblem_face._store(x, fig())
        self.assertEqual((x["nk"], x["bb"][0], x["nfv"]), ("keep", 0.1, emblem_face.NONE_V))
        with mock.patch.object(emblem_face, "measure", return_value=[0.3, 0.1, 0.5, 0.5, 320, 400]):
            emblem_face._store(x, fig())
        self.assertFalse({"nk", "bb", "nfv"} & set(x))

    def test_stale_when_nk_missing(self):
        x = {"face": [0, 0, 0.5, 0.5, 320, 400], "nfv": emblem_face.NONE_V}
        self.assertTrue(emblem_face.stale(x, (320, 400)))
        x.update(nk="keep", bb=[0, 1, 0, 1])
        self.assertFalse(emblem_face.stale(x, (320, 400)))

    def test_store_keys_survive_items_yaml(self):
        """_store が書くキーが全部 items.yaml へ書き戻される（nk・bb を落として「? 10」のままだった根）。"""
        import emblem
        x = {"subject": "Zeus", "image": "emblems/zeus.webp", "shape": "cutout"}
        with mock.patch.object(emblem_face, "measure", return_value=[0, 0, 0.5, 0.5, 320, 400]), mock.patch.object(emblem_face, "none_reason", return_value="noface"):
            emblem_face._store(x, fig())
        self.assertLessEqual({"face", "nfv", "nk", "bb"}, set(emblem.EMBLEM_KEEP))
        txt = "\n".join(["  - name: A", "    motif: retro"])
        self.assertIn("nk:", emblem.item_text(txt, "A", [x]))


    def test_no_own_keep_list_in_scripts(self):
        """小元素を items.yaml に書き戻す許可リストは EMBLEM_KEEP の 1 か所だけ（recrop・upper_all の狭い独自リストが face・nfv・nk・bb・body を落としていた）。"""
        import re
        root = pathlib.Path(__file__).resolve().parent.parent / "scripts"
        own = [f"{f.name}:{n}" for f in root.glob("*.py") for n, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1)
               if re.match(r'\s*keep = \(.*"subject", "why", "image"', l) and not l.lstrip().startswith("EMBLEM_KEEP")]
        self.assertEqual(own, [])

    def test_dropped_keys_check(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import emb_check
        ok = {"subject": "A", "nfv": emblem_face.NONE_V, "nk": "keep", "bb": [0, 1, 0, 1]}
        lost = {"subject": "B", "nfv": emblem_face.NONE_V, "nk": "keep"}
        waiting = {"subject": "C", "nfv": 3}
        self.assertEqual(emb_check.dropped_keys([{"name": "S", "emblem": [ok, lost, waiting]}]), ["S B"])

    def test_boards_dropped_keys_and_none_stale(self):
        """お客さまの版面（boards.config.emblem）でも nk・bb が欠けた顔なしを数え（E23）、library_emblem が測り直す対象にする。"""
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import emb_check
        lost = {"subject": "B", "nfv": emblem_face.NONE_V, "face": [0, 0, 0, 0, 9, 9]}
        ok = {"subject": "A", "nfv": emblem_face.NONE_V, "nk": "keep", "bb": [0, 1, 0, 1], "face": [0, 0, 0, 0, 9, 9]}
        self.assertEqual(emb_check.boards_dropped_keys([{"name": "G", "config": {"emblem": [ok, lost]}}, {"name": "H", "config": {}}]), ["G B"])
        self.assertEqual(emblem_face.none_stale([ok, lost]), 1)
        self.assertEqual(emblem_face.unmeasured([lost]), 0)

    def test_measured_keys_one_list(self):
        """画像を替えるとき捨てる測り値の一覧は emblem.EMBLEM_MEASURED の 1 か所（nfv・nk・bb も。二つの除外リストが食い違っていた）。"""
        import re
        root = pathlib.Path(__file__).resolve().parent.parent / "scripts"
        own = [f.name for f in root.glob("*.py") if re.search(r'not in \("face", "fs"', f.read_text(encoding="utf-8"))]
        self.assertEqual(own, [])
        self.assertTrue({"face", "fs", "nfv", "nk", "bb"} <= set(emblem.EMBLEM_MEASURED))

    def test_background_measures_every_round(self):
        """後台は版面に変化がなくても毎回、顔の測り直し（measure_item）を全版面に回す（drop_broken の中だけでは回らなかった）。"""
        src = pathlib.Path(emblem_fill.__file__).read_text(encoding="utf-8")
        body = src[src.index("def background("):]
        self.assertIn("emblem_face.measure_item(i, log) for i in load_items()", body.split("\ndef ")[0])


class Display(unittest.TestCase):
    def item(self, **kw):
        return [{"image": "emblems/zeus.webp", "shape": "cutout", "face": [0, 0, 0.5, 0.5, 320, 400], "nk": "keep", "bb": [0.1, 0.95, 0.19, 0.81], **kw}]

    def test_no_face_is_framed_by_body_box(self):
        h = render._emblem(self.item())
        self.assertIn('class="cutout nb"', h)
        self.assertIn("--nh:0.85;--ng:0.05;--na:0.8", h)
        self.assertIn('"nk": "keep"', h.replace("&quot;", '"'))

    def test_without_box_unchanged(self):
        self.assertNotIn(" nb", render._emblem(self.item(bb=None)))

    def test_js_and_css_know_nb(self):
        src = pathlib.Path(render.__file__).read_text(encoding="utf-8")
        self.assertIn("a.nb ? ' nb'", src)
        self.assertIn(".emb img.nb{", src)


class Replace(unittest.TestCase):
    def test_replace_nf(self):
        self.assertTrue(emblem_fill.replace_nf({"nk": "replace"}))
        self.assertFalse(emblem_fill.replace_nf({"nk": "replace", "lock": True}))
        self.assertFalse(emblem_fill.replace_nf({"nk": "keep"}))
        self.assertFalse(emblem_fill.replace_nf({"nk": "replace", "body": [0, 1, 1, 1, 1]}))

    def test_both_entrances_use_it(self):
        import inspect
        import library_emblem
        self.assertIn("replace_nf", inspect.getsource(emblem_fill.broken_cuts))
        self.assertIn("replace_nf", inspect.getsource(library_emblem.unbroken))


if __name__ == "__main__":
    unittest.main()
