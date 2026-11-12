"""一時の失敗（網・429・時間切れ・rembg）を「見たが合わなかった」と数えない（2026-11-12 裏の読み手の報告 2〜5）。
find_bust は環境の失敗を emblem.EnvFail で分けて返し、呼ぶ側（official_swap・stage_closeups・stage_holds・reach_swap・commit）は
回数に数えず・emblem_reject に入れず・次の回にやり直す。本当の不一致は今までどおり数える。ネットにも本番の DB にも出ない。"""
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import emblem  # noqa: E402
import emblem_fill as ef  # noqa: E402
import library_emblem as le  # noqa: E402
import runlog  # noqa: E402

from PIL import Image  # noqa: E402


def png(w=400, h=500, alpha=255):
    b = io.BytesIO()
    Image.new("RGBA", (w, h), (90, 90, 90, alpha)).save(b, "PNG")
    return b.getvalue()


def http(code):
    return urllib.error.HTTPError("https://o/x.png", code, "x", None, None)


def fake_rembg(remove=lambda img, session=None: img.convert("RGBA")):
    return mock.patch.dict(sys.modules, {"rembg": types.SimpleNamespace(remove=remove)})


OFF = ["https://o/char/ichigo/body.webp"]


class Classify(unittest.TestCase):
    def test_env_error_kinds(self):
        for e in (http(429), http(500), http(503), urllib.error.URLError("dns"), TimeoutError("t"), ConnectionResetError("r"),
                  ImportError("No module named 'rembg'"), emblem.EnvFail("x")):
            self.assertTrue(emblem.env_error(e), repr(e))
        from PIL import UnidentifiedImageError
        for e in (http(404), http(403), ValueError("顔が切り抜きに残っていない"), UnidentifiedImageError("not an image"), KeyError("query")):
            self.assertFalse(emblem.env_error(e), repr(e))   # 見たが合わない（画像でない中身も「合わない」）

    def test_requests_errors(self):
        import requests
        self.assertTrue(emblem.env_error(requests.exceptions.ConnectionError("x")))
        self.assertTrue(emblem.env_error(requests.exceptions.ReadTimeout("x")))


class FindBust(unittest.TestCase):
    """find_bust：公式の候補だけ（api なし）で、取得・rembg を偽物にする。"""

    def run_fb(self, get, remove=None, official=OFF, **kw):
        with fake_rembg(remove or (lambda img, session=None: img.convert("RGBA"))), mock.patch.object(emblem, "_session", return_value=object()), \
                mock.patch.object(emblem, "_get", side_effect=get), mock.patch.object(emblem, "check_whole", side_effect=lambda im, photo=False: im), \
                mock.patch.object(emblem, "face_fit", return_value=(None, None)):
            return emblem.find_bust(None, "Ichigo", official=official, **kw)

    def test_network_429_and_timeout_raise_envfail(self):
        for err in (http(429), urllib.error.URLError("down"), TimeoutError("slow"), http(502)):
            with self.subTest(err=err), self.assertRaises(emblem.EnvFail):
                self.run_fb(lambda u, *a: (_ for _ in ()).throw(err))

    def test_rembg_missing_or_broken_raise_envfail(self):
        with mock.patch.dict(sys.modules, {"rembg": None}), self.assertRaises(emblem.EnvFail):   # import できない
            emblem.find_bust(None, "Ichigo", official=OFF)
        with fake_rembg(), mock.patch.object(emblem, "_session", side_effect=RuntimeError("model download failed")), self.assertRaises(emblem.EnvFail):
            emblem.find_bust(None, "Ichigo", official=OFF)

        def boom(img, session=None):
            raise RuntimeError("onnxruntime error")
        with self.assertRaises(emblem.EnvFail):
            self.run_fb(lambda u, *a: png(), remove=boom)

    def test_real_mismatch_returns_none(self):
        self.assertIsNone(self.run_fb(lambda u, *a: (_ for _ in ()).throw(http(404))))   # 404 は「無い」
        self.assertIsNone(self.run_fb(lambda u, *a: b"<html>not an image</html>"))   # 画像でない中身も「合わない」
        self.assertIsNone(self.run_fb(lambda u, *a: png(alpha=255)))   # 読めたが顔が測れず透明でもない：合わない

    def test_mixed_env_and_mismatch_is_env(self):
        """1 枚が合わず、1 枚が網で見られなかった：全部を見ていないので「無い」とは言わない。"""
        two = OFF + ["https://o/char/ichigo/alt.webp"]
        with self.assertRaises(emblem.EnvFail):
            self.run_fb(lambda u, *a: png() if u == two[0] else (_ for _ in ()).throw(http(429)), official=two)

    def test_hit_wins_over_env(self):
        """見られなかった候補があっても、合うものが取れればそれを返す。"""
        two = ["https://o/char/ichigo/alt.webp"] + OFF
        got = self.run_fb(lambda u, *a: png(alpha=0) if u == OFF[0] else (_ for _ in ()).throw(http(429)), official=two)
        self.assertEqual(got[0], OFF[0])


def char_item():
    return {"name": "A", "emblem_kind": "character", "emblem": [
        {"subject": "Ichigo", "why": "Ichigo（Fandom のページ）", "shape": "cutout", "image": "emblems/a-ichigo.webp", "source": "f1"}]}


class OfficialSwap(unittest.TestCase):
    def swap(self, fb):
        item, saved = char_item(), {}
        with mock.patch.object(ef.emblem, "official_for", return_value=list(OFF)), mock.patch.object(ef.emblem, "official_site", return_value="https://o/"), \
                mock.patch.object(ef.emblem, "find_bust", side_effect=fb), mock.patch.object(ef.emblem, "save_cut"), \
                mock.patch.object(ef.emblem, "write_item"), mock.patch.object(ef.emblem_face, "measure_item"), \
                mock.patch.object(ef, "load_items", return_value=[item]), mock.patch.object(ef, "closeup_of", return_value=False), \
                mock.patch.object(ef, "broken_image", return_value=False), mock.patch.object(ef, "_set_field", side_effect=lambda n, k, v: saved.setdefault(k, v)):
            n = ef.official_swap(item, log=lambda *a: None)
        return n, saved

    def test_env_failure_does_not_reject_official(self):
        n, saved = self.swap(emblem.EnvFail("429"))
        self.assertEqual(n, 0)
        self.assertNotIn("emblem_reject", saved)   # 公式の絵を外した画像に入れない（次の回にやり直す）

    def test_env_failure_end_to_end_through_get(self):
        """本物の find_bust：公式の絵の取得が 429 → reject に入らない。"""
        item, saved = char_item(), {}
        with fake_rembg(), mock.patch.object(emblem, "_session", return_value=object()), mock.patch.object(emblem, "_get", side_effect=http(429)), \
                mock.patch.object(ef.emblem, "official_for", return_value=list(OFF)), mock.patch.object(ef.emblem, "official_site", return_value="https://o/"), \
                mock.patch.object(ef, "_set_field", side_effect=lambda n, k, v: saved.setdefault(k, v)):
            self.assertEqual(ef.official_swap(item, log=lambda *a: None), 0)
        self.assertNotIn("emblem_reject", saved)

    def test_real_mismatch_still_rejects(self):
        n, saved = self.swap(lambda api, title, **kw: None)
        self.assertEqual(n, 0)
        self.assertIn(OFF[0], saved["emblem_reject"])

    def test_library_board_env_failure_keeps_rows(self):
        item = char_item()
        with mock.patch.object(ef.emblem, "official_for", return_value=list(OFF)), mock.patch.object(ef.emblem, "find_bust", side_effect=emblem.EnvFail("x")):
            out, n = le.official_swap_board(item, item["emblem"], fetch=lambda u: png())
        self.assertEqual((n, out), (0, item["emblem"]))


class Closeups(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self.d.name)
        (self.tmp / "emblems").mkdir()
        (self.tmp / "state").mkdir()
        Image.new("RGBA", (40, 50), (9, 9, 9, 255)).save(self.tmp / "emblems" / "low.png")
        (self.tmp / "items.yaml").write_text('items:\n  - name: b\n    emblem_kind: character\n    emblem:\n'
                                             '      - {subject: "Low", image: "emblems/low.png", source: "https://x/low.png", shape: cutout}\n', encoding="utf-8")

    def tearDown(self):
        self.d.cleanup()

    def rounds(self, bust, n=3):
        import yaml
        out = []
        with mock.patch.object(ef, "ROOT", self.tmp), mock.patch.object(ef.emblem, "ROOT", self.tmp), mock.patch.object(ef.emblem.sitedir, "SITE_DIR", self.tmp), \
                mock.patch.object(ef.emblem, "EMB_DIR", self.tmp / "emblems"), mock.patch.object(ef.emblem_face, "measure_item"), \
                mock.patch.object(ef, "bust_replacement", side_effect=bust):
            for _ in range(n):
                now = yaml.safe_load((self.tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]
                now["emblem_who"] = [f"T{i}" for i in range(20)]   # Low は上位でない（3 回で外れる側）
                out.append(ef.stage_closeups(now, [x for x in now["emblem"] if x["subject"] == "Low"], log=lambda *a: None))
            return out, yaml.safe_load((self.tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0], ef.closeup_state().get("b") or {}

    def test_env_failures_are_not_counted(self):
        out, item, st = self.rounds(emblem.EnvFail("429"))
        self.assertEqual(out, [(0, 0)] * 3)
        self.assertEqual([x["subject"] for x in item["emblem"]], ["Low"])   # 外さない
        self.assertNotIn("emblem_reject", item)
        self.assertNotIn("n", st.get("Low") or {})   # 回数が増えない

    def test_real_misses_drop_after_three(self):
        out, item, _ = self.rounds(lambda *a, **k: None)
        self.assertEqual(out[-1], (0, 1))
        self.assertIn("https://x/low.png", item["emblem_reject"])

    def test_library_stage_holds_env_not_counted(self):
        who = [f"T{i}" for i in range(20)]
        hold = [{"subject": "Low", "image": "https://x/low.png"}]
        with mock.patch.object(ef, "bust_replacement", side_effect=emblem.EnvFail("rembg")):
            rows, dropped, new = le.stage_holds({"name": "b", "emblem_who": who}, list(hold), hold, {"Low": 2}, fetch=lambda u: png())
        self.assertEqual((rows, dropped, new), (hold, [], {"Low": 2}))
        with mock.patch.object(ef, "bust_replacement", return_value=None):
            rows, dropped, new = le.stage_holds({"name": "b", "emblem_who": who}, list(hold), hold, {"Low": 2}, fetch=lambda u: png())
        self.assertEqual(dropped, hold)   # 本当に無い 3 回目は外す


class BustReplacement(unittest.TestCase):
    X = {"subject": "Ichigo", "image": "emblems/a.webp"}

    def test_find_bust_errors_become_envfail(self):
        item = {"name": "A", "emblem_fandom": "bleach"}
        for err in (emblem.EnvFail("x"), KeyError("query"), http(503)):
            with self.subTest(err=err), mock.patch.object(ef.emblem, "official_for", return_value=[]), \
                    mock.patch.object(ef.emblem, "find_bust", side_effect=err), self.assertRaises(emblem.EnvFail):
                ef.bust_replacement(item, self.X, set(), log=lambda *a: None)

    def test_official_site_down_is_env_not_none(self):
        item = {"name": "A", "site": "https://o/"}
        with mock.patch.object(emblem, "_get", side_effect=http(429)), mock.patch.object(emblem, "_OFFICIAL_HTML", {}), \
                mock.patch.object(emblem, "_OFFICIAL_INDEX", {}), mock.patch.object(emblem, "OFFICIAL_DOWN", set()):
            with self.assertRaises(emblem.EnvFail):
                ef.bust_replacement(item, self.X, set(), log=lambda *a: None)
        with mock.patch.object(ef.emblem, "official_for", return_value=[]), mock.patch.object(emblem, "OFFICIAL_DOWN", set()):
            self.assertIsNone(ef.bust_replacement(item, self.X, set(), log=lambda *a: None))   # 届いて 0 枚＝本当に無い


class ReachSwap(unittest.TestCase):
    def test_env_not_counted_real_miss_counted(self):
        item = {"name": "A", "emblem_kind": "character", "emblem": [{"subject": "W", "image": "emblems/w.webp"}]}
        for bust, want in ((emblem.EnvFail("429"), None), (lambda *a, **k: None, '"emblems/w.webp": 1')):
            saved = {}
            with self.subTest(want=want), mock.patch.object(ef, "reach_rows", return_value=item["emblem"]), \
                    mock.patch.object(ef, "bust_replacement", side_effect=bust), mock.patch.object(ef, "_set_field", side_effect=lambda n, k, v: saved.setdefault(k, v)):
                self.assertEqual(ef.reach_swap(item, log=lambda *a: None), 0)
            if want:
                self.assertIn(want, saved["emblem_reach_tried"])
            else:
                self.assertNotIn("emblem_reach_tried", saved)

    def test_no_log_text_matching(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        self.assertNotIn('startswith("[胸像]")', src)   # 環境の失敗はログの文字でなく EnvFail で見分ける


class CommitCutEnv(unittest.TestCase):
    def test_cut_all_marks_env_failures(self):
        import yaml
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "items.yaml").write_text('items:\n  - name: b\n    emblem:\n      - {subject: "S", image: "https://x/s.png", shape: badge}\n'
                                            '      - {subject: "T", image: "https://x/t.png", shape: badge}\n', encoding="utf-8")
            emblem.CUT_ENV.clear()

            def cut(src, slug, drawn):
                raise emblem.EnvFail("rembg") if "s.png" in src else ValueError("顔が切り抜きに残っていない")
            with mock.patch.object(emblem, "ROOT", tmp), mock.patch.object(emblem, "cut_out", side_effect=cut):
                emblem.cut_all("b", True)
            self.assertEqual(emblem.CUT_ENV, {"https://x/s.png"})   # 網・rembg で切れなかったものだけ（commit が reject に入れない）
            self.assertEqual(yaml.safe_load((tmp / "items.yaml").read_text(encoding="utf-8"))["items"][0]["emblem"] or [], [])
        emblem.CUT_ENV.clear()

    def test_commit_filters_cut_env(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        self.assertIn('x["image"] not in emblem.CUT_ENV', src)


class BackgroundException(unittest.TestCase):
    """後台の fill_one が例外で落ちても材料の指紋を残さない（docs/rules/background.md「例外は指紋を残さない」）。"""

    def test_exception_board_stays_due(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        path = pathlib.Path(d.name) / "emblem_progress.json"
        items = [{"name": "zero", "type": "game"}]
        mat = ef.material(items[0])
        # 前の回：失敗・材料同じ・名簿を 1 周（凍る形）
        path.write_text(json.dumps({"items": {"zero": {"state": "failed", "material": mat, "exhausted": True, "at": "x"}}}), encoding="utf-8")
        self.assertTrue(ef.frozen(items[0], {"state": "failed", "material": mat, "exhausted": True}))

        def fill(item, log):
            raise urllib.error.URLError("Wikidata down")
        with mock.patch.object(ef, "load_items", return_value=items), mock.patch.object(runlog, "LOG_DIR", pathlib.Path(d.name) / "log"), \
                mock.patch.dict("os.environ", {"EMBLEM_RETRY_NOW": "1"}):
            prog = ef.background(40, log=lambda m: None, fill=fill, path=path, workers=1)
        e = prog["items"]["zero"]
        self.assertEqual(e["state"], "failed")
        self.assertIsNone(e.get("material"))   # 前の回の指紋も消える
        self.assertFalse(ef.frozen(items[0], e))
        self.assertIn("zero", [i["name"] for i in ef.due(prog, items, "2026-11-12T00:00:00+00:00")])

    def test_face_model_missing_leaves_no_round_or_material(self):
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "emblem_fill.py").read_text(encoding="utf-8")
        self.assertNotIn('"material": material(item)}', src)
        self.assertIn('顔のモデルが使えず本人確認ができないので、自動では選ばなかった", "material": None, "env": True}', src)

    def test_library_env_result_leaves_no_material(self):
        """お客さまの版面：fill が環境の失敗（env）を返したら指紋 m も回も残さない（店長と同じ）。"""
        src = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "library_emblem.py").read_text(encoding="utf-8")
        self.assertIn('env = note == "時間切れ" or bool(r.get("env"))', src)


if __name__ == "__main__":
    unittest.main()
