"""小元素の顔の大きさをそろえる（scripts/emblem_face.py）：置き方の式と、今ある全部の小元素が測れていること。"""
import pathlib
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import emblem_face as ef  # noqa: E402

PEOPLE = ("logo", "icon", "badge")


def board_items():
    return yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]


class Fit(unittest.TestCase):
    def test_small_face_is_enlarged_big_face_is_shrunk(self):
        self.assertEqual(ef.fit([0.2, 0.05, 0.5, 0.5, 400, 800])[0], 1.6)   # 0.32 / 0.2 = 1.6
        self.assertEqual(ef.fit([0.32, 0.05, 0.5, 0.5, 400, 800]), (1.0, ""))
        m, flag = ef.fit([0.9, 0.0, 0.5, 0.5, 400, 400])
        self.assertEqual((m, flag), (0.5, "big"))   # 縮小は 0.5 倍まで：それでも大きいものは札

    def test_too_small_is_flagged_and_capped(self):
        self.assertEqual(ef.fit([0.06, 0.02, 0.5, 0.5, 300, 900]), (1.6, "small"))

    def test_no_face_has_no_view(self):
        self.assertEqual(ef.fit([0, 0, 0.5, 0.5, 100, 100]), (None, "none"))
        self.assertIsNone(ef.view([0, 0, 0.5, 0.5, 100, 100]))

    def test_view_headroom_and_bottom(self):
        for fs, top in ((0.2, 0.03), (0.3, 0.1), (0.45, 0.08), (0.12, 0.02)):
            v = ef.view([fs, top, 0.5, 0.5, 400, 500])
            self.assertGreaterEqual(v["oy"], 0)
            self.assertGreaterEqual(v["oy"] + v["m"], 1 - 1e-6, "絵の下は枠の下に届く（浮かない）")
            self.assertLessEqual(v["oy"], max(ef.HEAD[1], 1 - v["m"]) + 1e-6)


class Everything(unittest.TestCase):
    """今ある全部の人物の小元素（店長の版面）：測れていて、同じ版面の顔の大きさが ±TOL に収まる。"""

    def test_all_measured(self):
        miss = [f"{it['name']}/{x.get('subject')}" for it in board_items() for x in it.get("emblem") or []
                if isinstance(x, dict) and str(x.get("image", "")).startswith("emblems/") and x.get("shape") not in PEOPLE
                and not (isinstance(x.get("face"), list) and len(x["face"]) == 6)]
        self.assertEqual(miss, [], f"顔を測っていない小元素 {len(miss)} 枚（emblem_face.measure_item）")

    def test_spread_per_board(self):
        for r in ef.audit(board_items()):
            self.assertLessEqual(r["spread"], 1.25, f"{r['name']}：顔の大きさのばらつき {r['spread']}")
            self.assertEqual(r["unmeasured"], 0, r["name"])

    def test_measure_matches_file(self):
        """測ったときの画像の大きさが、今の画像と同じ（画像が替わったのに測り直していない = 古い値で置いている）。"""
        from PIL import Image
        stale = []
        for it in board_items():
            for x in it.get("emblem") or []:
                f = x.get("face") if isinstance(x, dict) else None
                p = ROOT / "docs" / "home" / str(x.get("image", "")) if isinstance(x, dict) else None
                if f and p and p.exists() and list(Image.open(p).size) != f[4:]:
                    stale.append(f"{it['name']}/{x.get('subject')}")
        self.assertEqual(stale, [])


class CustomerRender(unittest.TestCase):
    def test_url_cutout_with_face_gets_m_and_fs(self):
        """お客さまの版面（網址の小元素）も、店長と同じ式で倍率 m と顔の高さ fs が alts に出る（ux_check E14 が数える材料）。"""
        import json
        import re
        import render
        html = render._emblem([{"image": "https://x.supabase.co/a.webp", "shape": "cutout", "face": [0.2, 0.05, 0.5, 0.5, 400, 800]}])
        a = json.loads(__import__("html").unescape(re.search(r'data-alts="([^"]*)"', html).group(1)))[0]
        self.assertEqual(a["m"], 1.6)
        self.assertAlmostEqual(a["fs"] * a["m"], 0.32, places=2)


if __name__ == "__main__":
    unittest.main()
