"""小元素の顔の大きさをそろえる（scripts/emblem_face.py）：置き方の式と、今ある全部の小元素が測れていること。"""
import pathlib
import sys
import unittest
import zlib

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

    def test_eye_line_first(self):
        """目の線 30% が、頭の上の余白の挟みや下そろえより先に効く（前は 192 枚中 104 枚が外れた）。髪は切らず、浮かせすぎず、外れるものは札 short。"""
        for fs, top, h in ((0.2, 0.03, 500), (0.3, 0.1, 500), (0.2, 0.4, 900), (0.12, 0.02, 900)):
            v = ef.view([fs, top, 0.5, 0.5, 400, h])
            self.assertIn(v["flag"], ("", "small"))
            if not v["flag"]:
                self.assertAlmostEqual(v["eye"], ef.EYE, delta=ef.EYE_TOL)
            self.assertLessEqual(v["oy"], ef.HEAD_MAX + 1e-6)
            self.assertGreaterEqual(v["oy"] + v["m"], 1 - ef.FLOAT_MAX - 1e-6, "浮かせるのは FLOAT_MAX まで")
        v = ef.view([0.3, 0.02, 0.5, 0.5, 400, 500])   # 髪（顔の箱の上の HAIR 分）が画像の上の端に近い：上を切らない
        self.assertGreaterEqual(v["oy"], 0)
        self.assertEqual(ef.view([0.9, 0.0, 0.5, 0.5, 400, 400])["flag"], "big")
        self.assertEqual(ef.view([0.482, 0.486, 0.456, 0.444, 384, 233])["flag"], "short")   # 実在の例：顔が絵の下半分にあり、目の線に合わせると絵の下が半分空く

    def test_logo_named_is_not_a_person(self):
        self.assertTrue(ef.logo_named({"shape": "cutout", "image": "https://upload.wikimedia.org/x/500px-ArcheAge_Logo.png"}))
        self.assertTrue(ef.logo_named({"shape": "cutout", "image": "https://x/Project_TL_logo.png?x=1"}))
        self.assertFalse(ef.logo_named({"shape": "cutout", "image": "emblems/bleach-ichigo.webp"}))


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

    def test_eye_line_all(self):
        """今ある全部：札のない小元素の目の線は枠の上から 30% ±5%（札 short は別の写真に替える対象。数は audit で）。"""
        off = [f"{it['name']}/{x.get('subject')}" for it in board_items() for x in it.get("emblem") or []
               if isinstance(x, dict) and x.get("face") and x.get("shape") not in PEOPLE and not x.get("body")
               and (v := ef.view(x["face"])) and not v["flag"] and abs(v["eye"] - ef.EYE) > ef.EYE_TOL + 1e-9]
        self.assertEqual(off, [])

    def test_shapeless_logos_not_cutouts(self):
        """店長の items.yaml：名前が logo の網址の画像（shape cutout のまま）は render が logo にする（ux_check E13 の 3 枚）。"""
        import html
        import json
        import re
        import render
        for it in board_items():
            for x in it.get("emblem") or []:
                if isinstance(x, dict) and x.get("shape") == "cutout" and ef.logo_named(x):
                    alt = json.loads(html.unescape(re.search(r'data-alts="([^"]*)"', render._emblem([x])).group(1)))[0]
                    self.assertEqual(alt["shape"], "logo", f"{it['name']}/{x.get('subject')}")

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
    def test_no_face_gets_nf_not_m(self):
        """顔なし（face[0] = 0）は nf=1・m なし。顔ありは m で nf なし（ux_check E13 が「測ったか」をこれで見る）。"""
        import html
        import json
        import re
        import render
        def alt(face):
            return json.loads(html.unescape(re.search(r'data-alts="([^"]*)"', render._emblem([{"image": "https://x.supabase.co/a.webp", "shape": "cutout", "face": face}])).group(1)))[0]
        self.assertEqual((alt([0, 0, 0.5, 0.5, 40, 80]).get("nf"), alt([0, 0, 0.5, 0.5, 40, 80]).get("m")), (1, None))
        self.assertEqual((alt([0.2, 0.05, 0.5, 0.5, 40, 80]).get("nf"), alt([0.2, 0.05, 0.5, 0.5, 40, 80]).get("m")), (None, 1.6))

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


def _models():
    """検出のモデルが手元にあるときだけ（CI で 80MB を落とさない）。"""
    try:
        import face_id
        return (face_id.CACHE / "anime_face.onnx").exists() and (face_id.CACHE / "yunet.onnx").exists()
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_models(), "顔のモデルが手元にない")
class Anime(unittest.TestCase):
    """アニメ・ゲームの絵の顔（2 段目 relax・3 段目 weak）と、測り済みの値が変わらないこと。docs/home/emblems/ の既存の画像だけ。"""

    def img(self, name):
        from PIL import Image
        im = Image.open(ROOT / "docs" / "home" / "emblems" / name)
        im.load()
        return im

    def test_lowered_face_close_up_relax(self):
        """髪・角の大きい上半身のアップは顔が絵の下半分にある（BLEACH の Franceska 0.54、dota2 の Dark Willow 0.22）。"""
        for name, fs in (("bleach-mirrors-high-franceska-mila-rose.webp", 0.537), ("dota2-dark-willow.webp", 0.221)):
            self.assertAlmostEqual(ef.measure(self.img(name))[0], fs, delta=0.01, msg=name)

    def test_weak_threshold_finds_anime_face(self):
        for name in ("bleach-mirrors-high-yammy-llargo.webp", "timmy-and-tommy.webp", "bleach-mirrors-high-s-ken-ishida.webp"):
            self.assertGreater(ef.measure(self.img(name))[0], 0.3, name)

    def test_sheet_is_not_weak_measured(self):
        """向きを並べた図（dota2 Ursa）は、しきい値を下げると体の模様を顔とするので 3 段目に進まない。"""
        im = self.img("dota2-ursa.webp")
        self.assertEqual(ef.measure(im)[0], 0)
        self.assertEqual(ef.none_reason(im), "sheet")

    def test_no_face_reasons(self):
        self.assertEqual(ef.none_reason(self.img("gun-devil.webp")), "noface")
        self.assertEqual(ef.none_reason(self.img("dota2-queen-of-pain.webp")), "sheet")
        self.assertEqual(ef.none_reason(self.img("dota2-juggernaut.webp")), "small")
        self.assertEqual(ef.measure(self.img("gun-devil.webp"))[0], 0)

    def test_measured_values_unchanged(self):
        """測り済みの十数枚（アニメ・3D・写真）の値が items.yaml のとおり変わらない（前の段で測れたものは後の段に進まない）。"""
        n = 0
        for it in board_items():
            for x in it.get("emblem") or []:
                f = x.get("face") if isinstance(x, dict) else None
                if f and f[0] and str(x.get("image", "")).startswith("emblems/") and n < 12 and zlib.crc32(x["image"].encode()) % 25 == 0:
                    self.assertEqual(ef.measure(self.img(x["image"].split("/", 1)[1])), f, x["image"])
                    n += 1
        self.assertGreaterEqual(n, 5)
