"""PC の AI の仕事（scripts/pc_ai.py）：待ちが無ければ Claude を起こさない・上限・お客さまの写真の扱い。"""
import base64
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import pc_ai  # noqa: E402


class JsonIn(unittest.TestCase):
    def test_plain_fenced_and_prose(self):
        self.assertEqual(pc_ai.json_in('[{"a": 1}]'), [{"a": 1}])
        self.assertEqual(pc_ai.json_in('はい\n```json\n{"a": 1}\n```\n以上'), {"a": 1})
        self.assertEqual(pc_ai.json_in('結果：[] です'), [])

    def test_no_json(self):
        with self.assertRaises(ValueError):
            pc_ai.json_in("わかりません")


class WishRow(unittest.TestCase):
    ROW = {"id": 7, "account": "u_a", "status": "纠结", "note": "青いの"}

    def test_keeps_only_safe_fields(self):
        w = pc_ai.wish_row(self.ROW, {"name": "ペン", "price": -5, "url": "javascript:alert(1)", "currency": "JPY"}, None)
        self.assertEqual((w["name"], w["account"], w["status"], w["photo"]), ("ペン", "u_a", "纠结", 7))
        self.assertIsNone(w["price"])
        self.assertIsNone(w["url"])

    def test_unreadable_photo_still_makes_a_row(self):
        w = pc_ai.wish_row(self.ROW, [], None)
        self.assertIn("認識できません", w["name"])
        self.assertEqual(w["note"], "青いの")


class WishImage(unittest.TestCase):
    def test_crop_and_size(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (2000, 1000), "white").save(buf, "JPEG")
        out = pc_ai.wish_image(buf.getvalue(), [0, 0, 0.5, 1])
        self.assertTrue(out.startswith("data:image/jpeg;base64,"))
        im = Image.open(io.BytesIO(base64.b64decode(out.split(",", 1)[1])))
        self.assertEqual(im.size, (800, 800))
        self.assertLessEqual(len(out), 400000)


class Limits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(pc_ai, "STATE_DIR", pathlib.Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def test_ledger_counts_without_cache_reads(self):
        led = {}
        pc_ai.add_use(led, "2026-11-07", {"in": 10, "cw": 20, "cr": 999, "out": 5}, "boards")
        self.assertEqual(pc_ai.spent(led, "2026-11-07"), 35)
        self.assertEqual(pc_ai.load_ledger()["2026-11-07"]["boards"], 1)

    def test_no_photos_means_no_claude(self):
        with mock.patch.object(pc_ai, "db", return_value=[]), mock.patch.object(pc_ai, "run_claude") as c:
            pc_ai.do_photos({}, "2026-11-07", False)
        c.assert_not_called()

    def test_cap_stops_before_claude(self):
        row = {"id": 1, "account": "u_a", "status": "想要", "image": "data:image/jpeg;base64,AA=="}
        led = {"2026-11-07": {"in": pc_ai.DAILY_TOKENS}}
        with mock.patch.object(pc_ai, "db", return_value=[row]), mock.patch.object(pc_ai, "run_claude") as c:
            pc_ai.do_photos(led, "2026-11-07", False)
        c.assert_not_called()

    def test_photos_exclude_the_shop_and_failure_keeps_the_row(self):
        row = {"id": 1, "account": "u_a", "status": "想要", "image": "data:image/jpeg;base64,AA=="}
        calls = []

        def fake(path, *a, **k):
            calls.append(path)
            return [row]
        with mock.patch.object(pc_ai, "db", side_effect=fake), mock.patch.object(pc_ai, "run_claude", side_effect=RuntimeError("x")):
            pc_ai.do_photos({}, "2026-11-07", False)
        self.assertIn(f"account=neq.{pc_ai.SHOP_ACCOUNT}", calls[0])
        self.assertEqual(len(calls), 1)   # 失敗した写真は書き換えない（次の回にもう一度）


class Rules(unittest.TestCase):
    def test_uses_the_same_editing_rules(self):
        r = pc_ai.editing_rules()
        self.assertIn("编排规则", r)
        self.assertIn("event", r)
        self.assertNotIn("## 文件格式", r)

    def test_key_is_never_printed(self):
        src = (ROOT / "scripts/pc_ai.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"print\([^)]*key")


if __name__ == "__main__":
    unittest.main()
