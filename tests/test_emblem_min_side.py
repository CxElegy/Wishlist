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



class WideRetry(unittest.TestCase):
    """縮めた幅（400）で小さいと測れて外した絵を emblem_reject に入れない（dota2 Crystal Maiden 390×247）。"""

    NARROW = "https://static.wikia.nocookie.net/d/images/c/c2/A.jpg/revision/latest/scale-to-width-down/400?cb=1"

    def test_narrow_source(self):
        self.assertTrue(emblem.narrow_source(self.NARROW))
        self.assertTrue(emblem.narrow_source("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Y.jpg/500px-Y.jpg"))
        self.assertFalse(emblem.narrow_source(self.NARROW.replace("/400", "/1200")))
        self.assertFalse(emblem.narrow_source("https://static.wikia.nocookie.net/b/images/b/bc/R.png/revision/latest?cb=1"))   # Rukia：元の大きさのまま小さい = 本当に小さい

    def test_wide_retry(self):
        import emblem_fill as ef
        x = {"subject": "CM", "source": self.NARROW, "face": [0.1, 0.1, 0.5, 0.5, 390, 247]}
        self.assertTrue(ef.wide_retry(x))
        self.assertFalse(ef.wide_retry({**x, "face": [0.1, 0.1, 0.5, 0.5, 390, 300]}))      # 小さくない
        self.assertFalse(ef.wide_retry({**x, "source": self.NARROW.split("/revision")[0]}))   # 縮めた網址ではない
        self.assertFalse(ef.wide_retry({**x, "lock": True}))

    def test_drop_broken_keeps_narrow_small_out_of_reject(self):
        import emblem_fill as ef
        src = inspect.getsource(ef.drop_broken)
        self.assertIn("wide_retry", src)

    def test_unbreak_frees_narrow_small_source(self):
        import json
        import yaml
        import emblem_fill as ef
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "state").mkdir()
        x = {"subject": "CM", "image": "emblems/gone.webp", "source": self.NARROW, "face": [0.1, 0.1, 0.5, 0.5, 390, 247]}
        (tmp / "state" / "emblem_broken.json").write_text(json.dumps({"M": [{"v": 10, "emblem": x}]}), encoding="utf-8")
        (tmp / "items.yaml").write_text(f'items:\n  - name: M\n    emblem_kind: character\n    emblem_reject: ["{self.NARROW}", "http://s/z"]\n    emblem: []\n', encoding="utf-8")
        item = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        with mock.patch.object(ef, "ROOT", tmp), mock.patch.object(emblem, "ROOT", tmp), mock.patch.object(emblem.sitedir, "SITE_DIR", tmp):
            ef.unbreak(item, log=lambda *_: None)
        got = yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(got["emblem_reject"], ["http://s/z"])


class WideRetryEverywhere(unittest.TestCase):
    """縮めた幅の絵が「小さいだけ」で reject に入らない壊れ方を、店長・お客さま・点検の 3 か所で数える。"""

    NARROW = WideRetry.NARROW

    def test_customer_unbroken_drops_small_without_reject(self):
        """お客さまの版面（library_emblem.unbroken）は小さい絵を外すだけ。返すのはリストだけで emblem_reject を書く道がない（店長の drop_broken と別の道）。"""
        import io
        import library_emblem as le
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (390, 247), (200, 100, 50, 255)).save(buf, "PNG")
        u = f"https://x.supabase.co/storage/v1/object/public/{le.BUCKET}/a.png"
        x = {"subject": "CM", "image": u, "source": self.NARROW, "shape": "cutout"}
        got = le.unbroken([x], False, fetch=lambda _u: buf.getvalue())
        self.assertEqual(got, [])
        self.assertNotIn("emblem_reject", inspect.getsource(le.unbroken))
        self.assertNotIn("drop_broken", inspect.getsource(le.unbroken))

    def test_e24_counts_narrow_small_reject_without_emblem(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "harness"))
        import emb_check
        face = [0.1, 0.1, 0.5, 0.5, 390, 247]
        rec = {"M": [{"v": 10, "emblem": {"subject": "CM", "source": self.NARROW, "face": face}},
                     {"v": 10, "emblem": {"subject": "Has", "source": self.NARROW + "2", "face": face}},
                     {"v": 10, "emblem": {"subject": "Big", "source": self.NARROW + "3", "face": [0, 0, 1, 1, 900, 900]}}]}
        items = [{"name": "M", "emblem_reject": [self.NARROW, self.NARROW + "2", self.NARROW + "3"], "emblem": [{"subject": "Has", "image": "emblems/h.webp"}]}]
        self.assertEqual(emb_check.narrow_small_rejects(items, rec), ["M CM"])
        items[0]["emblem_reject"] = []   # unbreak が抜いたあと
        self.assertEqual(emb_check.narrow_small_rejects(items, rec), [])


if __name__ == "__main__":
    unittest.main()
