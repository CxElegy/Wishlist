"""小元素を取るとき短い辺 256px 未満を断る（E18 の根）。ネットワークには出ない。"""

import inspect
import pathlib
import tempfile
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem  # noqa: E402


class MinSide(unittest.TestCase):
    def test_full_url_widens_fandom_and_wikimedia(self):
        f = "https://static.wikia.nocookie.net/x/images/a/ab/Y.png/revision/latest/scale-to-width-down/400?cb=1"
        self.assertIn(f"/scale-to-width-down/{emblem.FULL_W}?cb=1", emblem.full_url(f))
        w = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Y.jpg/500px-Y.jpg"
        self.assertEqual(emblem.full_url(w), w.replace("500px-", f"{emblem.FULL_W}px-"))
        self.assertEqual(emblem.full_url("https://example.com/a.png"), "https://example.com/a.png")

    def test_save_cut_refuses_small(self):
        from PIL import Image
        with self.assertRaises(ValueError):
            emblem.save_cut(Image.new("RGBA", (247, 434)), "t-small", emblem.BUST_MIN_SIDE)

    def test_every_taking_path_has_the_floor(self):
        """cut_out・fit_all・cut_all の save_cut は下限を渡す（全身 body だけ 0）。片方の入口だけ直さない。"""
        for fn in (emblem.cut_out, emblem.fit_all, emblem.cut_all):
            src = inspect.getsource(fn)
            self.assertIn("BUST_MIN_SIDE", src, fn.__name__)

    def test_save_cut_default_is_the_floor(self):
        """下限は既定値：渡し忘れた入口があっても小さいものは書かれない。"""
        from PIL import Image
        with self.assertRaises(ValueError):
            emblem.save_cut(Image.new("RGBA", (247, 434)), "t-small")

    def test_every_save_cut_call_passes_the_floor(self):
        """scripts/ 全部の save_cut 呼び出しを数える：min_side を省く（既定の下限）か BUST_MIN_SIDE を含む式。0 は repair_flat（既存画像の整え直し）だけ。"""
        import ast
        sd = pathlib.Path(emblem.__file__).parent
        bad, n = [], 0
        for f in sorted(sd.glob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for c in ast.walk(fn):
                    if not (isinstance(c, ast.Call) and getattr(c.func, "attr", getattr(c.func, "id", "")) == "save_cut"):
                        continue
                    n += 1
                    arg = c.args[2] if len(c.args) > 2 else next((k.value for k in c.keywords if k.arg == "min_side"), None)
                    if arg is None or "BUST_MIN_SIDE" in ast.unparse(arg):
                        continue
                    if not (fn.name == "repair_flat" and ast.unparse(arg) == "0"):
                        bad.append(f"{f.name}:{c.lineno} {fn.name} {ast.unparse(arg)}")
        self.assertGreaterEqual(n, 6)
        self.assertEqual(bad, [])

    def test_too_small_drops_old_small_cuts(self):
        """前から入っている小さい切り抜きを broken_cuts が外す。全身 body は除く。"""
        import emblem_fill
        from PIL import Image
        self.assertTrue(emblem_fill.too_small(Image.new("RGBA", (255, 400))))
        self.assertFalse(emblem_fill.too_small(Image.new("RGBA", (256, 400))))
        self.assertFalse(emblem_fill.too_small(Image.new("RGBA", (100, 400)), body=True))
        # 1 回に外す上限（版面が一度に空かない）
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "emblems").mkdir()
            rows = []
            for k in range(emblem_fill.SMALL_DROP_MAX + 3):
                Image.new("RGBA", (200, 300), (9, 9, 9, 255)).save(tmp / "emblems" / f"s{k}.webp")
                rows.append({"subject": f"s{k}", "image": f"emblems/s{k}.webp", "shape": "cutout"})
            with mock.patch.object(emblem.sitedir, "SITE_DIR", tmp), mock.patch.object(emblem_fill, "broken_image", return_value=False):
                bad = emblem_fill.broken_cuts({"emblem": rows, "emblem_kind": "character"})
            self.assertEqual(len(bad), emblem_fill.SMALL_DROP_MAX)
        import inspect as i
        self.assertIn("too_small", i.getsource(emblem_fill.broken_cuts))
        import library_emblem
        self.assertIn("too_small", i.getsource(library_emblem.unbroken))

    def test_fit_all_rejects_small_old_images(self):
        """fit_all は下限で外した前からの画像を emblem_reject に書く（commit を通らない入口）。"""
        src = inspect.getsource(emblem.fit_all)
        self.assertIn("emblem_reject", src)
        self.assertIn("small.append", src)



if __name__ == "__main__":
    unittest.main()
