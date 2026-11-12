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


class Unreached(unittest.TestCase):
    """T-0228：規則どおりでも顔が届かない絵を数える（emblem_face.unreached）と、選ぶ段で届く候補を先にする（cand_reach）。"""
    WIDE = {"fs": 0.09, "body": [0.06, 0.99, 0.5, 1.2, 0.9, 0.93]}                      # 幅の広い構え：幅 140px の上限で顔 10px
    WEAPON = {"fs": 0.1, "body": [0.138, 2.4, 0.5, 0.9, 0.9, 2.26], "ft": 0.6}          # 頭上に武器・帽子：顔の下の半分が入る大きさまでで 13px
    BIGHEAD = {"fs": 0.2, "body": [0.06, 0.99, 0.5, 0.6, 0.9, 0.93]}                    # 頭の大きいキャラ：全身のまま枠 100px で 20px
    OK = {"fs": 0.091, "body": [0.062, 0.992, 0.5, 0.31, 0.9, 0.93]}

    def test_three_types_are_counted(self):
        rows = [("wide", self.WIDE), ("weapon", self.WEAPON), ("big", self.BIGHEAD), ("ok", self.OK)]
        got = dict(ef.unreached(rows, "phone"))
        self.assertEqual(sorted(got), ["big", "weapon", "wide"])
        self.assertTrue(all(px < 32 * 0.95 for px in got.values()))
        self.assertEqual(ef.unreached([("ok", self.OK)], "pc"), [])

    def test_shown_is_unchanged(self):
        self.assertEqual(ef.shown(0.09, self.WIDE["body"], None, "phone")[:2], (10.5, 116.7))

    def test_reaching_candidate_comes_first(self):
        wide = {"id": "wide", **self.WIDE}
        ok = {"id": "ok", **self.OK}
        unknown = {"id": "unknown"}
        self.assertEqual([ef.cand_reach(c) for c in (wide, ok, unknown)], [1, 0, 0])
        self.assertEqual([c["id"] for c in sorted([wide, ok, unknown], key=ef.cand_reach)], ["ok", "unknown", "wide"])   # 並べ替えは安定：同じ鍵なら元の順
        self.assertEqual(ef.cand_reach({"cfs": 0.09, "car": 1.2}), 1)     # 取る前の測り（全身・横に広い）
        self.assertEqual(ef.cand_reach({"cfs": 0.35, "car": 1.2}), 0)     # 顔が大きい＝胸像かもしれない：数えない


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

    def img(self, name, live=False):
        """既定は tests/fixtures/emblems/ の固定の画像（docs/home/emblems/ は後の収集で作り直され、測り値が変わる：2026-10-29 に Timmy が顔なしになり手元だけ落ちた）。live=True は今の画像。"""
        from PIL import Image
        im = Image.open(ROOT / ("docs/home" if live else "tests/fixtures") / "emblems" / name)
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
                    self.assertEqual(ef.measure(self.img(x["image"].split("/", 1)[1], live=True)), f, x["image"])
                    n += 1
        self.assertGreaterEqual(n, 5)


class Threshold(unittest.TestCase):
    """検出器のしきい値は、共有の 1 つを書き換えた人が戻す（2026-10-27：_boxes が 0.5・0.32 のまま残し、額切れ forehead_cut・点検 E7 が前の測りしだいで変わった：Gin Ichimaru ほか 7 枚）。"""

    def test_every_set_is_restored_to_the_default(self):
        import re
        sets = {p.name: len(re.findall(r"setScoreThreshold\(", p.read_text(encoding="utf-8"))) for p in (ROOT / "scripts").glob("*.py")}
        sets = {k: v for k, v in sets.items() if v}
        self.assertEqual(sets, {"emblem_face.py": 2})   # 変える所（1）と戻す所（2）だけ。増やすなら戻し方もここに足す
        self.assertIn("setScoreThreshold(face_id.SCORE)", (ROOT / "scripts" / "emblem_face.py").read_text(encoding="utf-8"))

    @unittest.skipUnless(_models(), "顔のモデルが手元にない")
    def test_weak_boxes_leave_the_detector_at_default(self):
        import face_id
        from PIL import Image
        ef._boxes(Image.new("RGBA", (120, 120), (200, 120, 90, 255)), weak=True)
        self.assertAlmostEqual(face_id.engine()[0].getScoreThreshold(), face_id.SCORE, places=5)



class ShownFacePx(unittest.TestCase):
    def test_class_and_px(self):
        self.assertEqual(ef.face_class(None, 0.3), "bust")
        self.assertEqual(ef.face_class([0.1, 2.0, 0.5, 0.5, 0.9], 0.2), "cut")
        self.assertEqual(ef.face_class([0.1, 0.9, 0.5, 0.5, 0.8], 0.1), "full")
        self.assertEqual(ef.face_class([0.1, 0.9, 0.5, 0.5, 0.8], 0.3), "big")
        self.assertEqual(ef.shown_face_px(0.1, [0.1, 0.9, 0.5, 0.5, 0.8, 0.8]), 44.0)   # 116 / 0.8 = 145 → 顔 14.5px では見えない → 顔 44px まで大きくして上半身に切る（I1c）
        self.assertEqual(ef.shown_face_px(0.32, None, 1.0), 49.9)
        self.assertIsNone(ef.shown_face_px(0, None, 1.0))


class FaceMin(unittest.TestCase):
    """審美基準 I1c（2026-11-12 店長「这还是有点小 看不清人脸」）：人物の小元素の顔は、どの幅でも下限以上。全身で届かなければ上半身に切る。"""

    def test_full_body_is_cut_to_reach_min(self):
        makima = [0.062, 0.992, 0.5, 0.31, 0.9, 0.93]   # ふつうの体つきの立ち絵：顔は絵の高さの 9%
        for size, fmin in (("phone", 32), ("pc", 44)):
            face, h, vis, cut = ef.shown(0.091, makima, None, size)
            self.assertGreaterEqual(face, fmin)
            self.assertTrue(cut)                                     # 全身のままでは入らない → 上半身
            self.assertLessEqual(vis, ef.SIZES[size]["vmax"])        # 見せる高さは上限まで（点検 E4 の 140・215px に入る）
            self.assertGreaterEqual(vis, ef.SIZES[size]["eh"])       # 頭だけの小さい切れ端にしない

    def test_cut_and_small_bust_reach_min(self):
        self.assertGreaterEqual(ef.shown_face_px(0.21, [0.138, 2.4, 0.5, 0.75, 0.9, 2.26], None, "phone"), 32)   # 取るときに切った上半身（绝区零）：前は 17〜24px
        self.assertGreaterEqual(ef.shown_face_px(0.1, None, 1.6, "phone", 0.4), 32)   # 拡大 1.6 倍で足りなかった胸像（札 small）：前は 16px
        self.assertLessEqual(ef.shown(0.1, None, 1.6, "phone", 0.85)[1] * 0.85, 140.5)   # 横に広い絵は幅 140px まで（題字・話題度に重ねない）＝下限に届かない（選び方で替える対象）
        self.assertEqual(ef.shown_face_px(0.32, None, 1.0, "phone"), 32.0)       # そろっている胸像はそのまま（帯に合わせた拡大 1.15 倍で 36.8px）

    def test_big_head_stays_whole(self):
        face, h, vis, cut = ef.shown(0.3, [0.06, 0.99, 0.5, 0.6, 0.9, 0.93], None, "phone")   # 頭の大きいキャラ・マスコット：切らない（emblem.md「全身のまま」）
        self.assertFalse(cut)
        self.assertEqual(h, vis)
        self.assertEqual((face, h), (30.0, 100))   # 胸像の枠の高さ（100px）いっぱいまで大きく：顔 30px（前は 74 ÷ 0.93 × 0.3 = 24px）。頭が絵の 4 割あるので分かる
        face, h, vis, cut = ef.shown(0.76, [0.06, 0.998, 0.5, 0.7, 0.9, 0.938], None, "phone")   # ポチタ：顔は十分大きい → 大きさは前のまま
        self.assertEqual(h, round(74 / 0.938, 1))

    def test_mascot_and_low_face(self):
        # あつ森の住民：顔の箱が絵の 19%（CUT_BELOW 以上）＝頭の大きいキャラ → 切らず全身のまま枠いっぱい
        face, h, vis, cut = ef.shown(0.19, [0.06, 0.99, 0.5, 0.75, 0.9, 0.93], None, "phone", None, 0.2)
        self.assertFalse(cut)
        self.assertEqual((h, vis), (100, 100))
        # 頭の上に武器・上げた腕（顔が絵の上から 37% の所）：顔とその下の半分が枠に入る大きさまで。顔の途中で切らない
        face, h, vis, cut = ef.shown(0.169, [0.138, 2.4, 0.5, 0.9, 0.9, 2.26], None, "phone", None, 0.371)
        self.assertLessEqual((0.371 + 0.169) * h, vis)
        self.assertGreater(face, 0.169 * 100)

    def test_wide_pose_is_bounded(self):
        face, h, vis, cut = ef.shown(0.09, [0.06, 0.99, 0.5, 1.2, 0.9, 0.93], None, "phone")   # 横に広いポーズ：幅 140px まで（題字の場所を取らない）
        self.assertLessEqual(h * 1.2, 140.5)


class Unreached(unittest.TestCase):
    """T-0228：規則どおりでも顔が届かない絵を数える（emblem_face.unreached）と、選ぶ段で届く候補を先にする（cand_reach）。"""
    WIDE = {"fs": 0.09, "body": [0.06, 0.99, 0.5, 1.2, 0.9, 0.93]}                      # 幅の広い構え：幅 140px の上限で顔 10px
    WEAPON = {"fs": 0.1, "body": [0.138, 2.4, 0.5, 0.9, 0.9, 2.26], "ft": 0.6}          # 頭上に武器・帽子：顔の下の半分が入る大きさまでで 13px
    BIGHEAD = {"fs": 0.2, "body": [0.06, 0.99, 0.5, 0.6, 0.9, 0.93]}                    # 頭の大きいキャラ：全身のまま枠 100px で 20px
    OK = {"fs": 0.091, "body": [0.062, 0.992, 0.5, 0.31, 0.9, 0.93]}

    def test_three_types_are_counted(self):
        rows = [("wide", self.WIDE), ("weapon", self.WEAPON), ("big", self.BIGHEAD), ("ok", self.OK)]
        got = dict(ef.unreached(rows, "phone"))
        self.assertEqual(sorted(got), ["big", "weapon", "wide"])
        self.assertTrue(all(px < 32 * 0.95 for px in got.values()))
        self.assertEqual(ef.unreached([("ok", self.OK)], "pc"), [])

    def test_shown_is_unchanged(self):
        self.assertEqual(ef.shown(0.09, self.WIDE["body"], None, "phone")[:2], (10.5, 116.7))

    def test_reaching_candidate_comes_first(self):
        wide = {"id": "wide", **self.WIDE}
        ok = {"id": "ok", **self.OK}
        unknown = {"id": "unknown"}
        self.assertEqual([ef.cand_reach(c) for c in (wide, ok, unknown)], [1, 0, 0])
        self.assertEqual([c["id"] for c in sorted([wide, ok, unknown], key=ef.cand_reach)], ["ok", "unknown", "wide"])   # 並べ替えは安定：同じ鍵なら元の順
        self.assertEqual(ef.cand_reach({"cfs": 0.09, "car": 1.2}), 1)     # 取る前の測り（全身・横に広い）
        self.assertEqual(ef.cand_reach({"cfs": 0.35, "car": 1.2}), 0)     # 顔が大きい＝胸像かもしれない：数えない


if __name__ == "__main__":
    unittest.main()
