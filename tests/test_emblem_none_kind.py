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

    def test_store_keys_survive_items_yaml(self):
        """_store が書くキーが全部 items.yaml へ書き戻される（nk・bb を落として「? 10」のままだった根）。"""
        import emblem
        x = {"subject": "Zeus", "image": "emblems/zeus.webp", "shape": "cutout"}
        with mock.patch.object(emblem_face, "measure", return_value=[0, 0, 0.5, 0.5, 320, 400]), mock.patch.object(emblem_face, "none_reason", return_value="noface"):
            emblem_face._store(x, fig())
        self.assertLessEqual({"face", "nfv", "nk", "bb"}, set(emblem.EMBLEM_KEEP))
        txt = "\n".join(["  - name: A", "    motif: retro"])
        self.assertIn("nk:", emblem.item_text(txt, "A", [x]))


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
