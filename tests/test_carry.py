"""前の日の「整理待ち」を今日に持ち越す（2026-10-22 全体の検査 H3）：AI 編集は最新の inbox しか見ないので、
JST 18:00 の回のあと日付が変わるまでに集めた分は、持ち越さないと二度と版面に載らない。

    python -m unittest tests.test_carry
"""

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import gate  # noqa: E402


def entry(n, title, **kw):
    return {"n": n, "title": title, "url": f"https://news.example.jp/{n}-{title}", "source": "example", **kw}


class CarryOver(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.p = mock.patch.object(digest, "INBOX_DIR", self.dir)
        self.p.start()
        (self.dir / "2026-10-21.json").write_text(json.dumps({"date": "2026-10-21", "items": [
            {"name": "GTA 6", "facts": [], "entries": [entry(1, "a"), entry(2, "b"), entry(3, "c", urgent=True), entry(4, "d")]},
            {"name": "あつ森", "facts": [], "entries": [entry(1, "x")]},
            {"name": "ILLIT", "facts": [], "entries": [entry(1, "y")]},
        ]}, ensure_ascii=False), encoding="utf-8")
        # GTA 6 は 1 件目まで編集済み・あつ森は edit.json にある（全部編集済み）・ILLIT は edit.json にない（全部まだ）
        (self.dir / "2026-10-21.edit.json").write_text(json.dumps({"_covered": {"GTA 6": 1}, "GTA 6": [], "あつ森": []}), encoding="utf-8")

    def tearDown(self):
        self.p.stop()

    def test_carries_only_unedited_and_not_urgent(self):
        data, n = digest.carry_over({"date": "2026-10-22", "items": [
            {"name": "GTA 6", "facts": [], "entries": [entry(1, "new")]}]}, "2026-10-22")
        self.assertEqual(n, 3)
        got = {b["name"]: [(e["n"], e["title"], e.get("carried")) for e in b["entries"]] for b in data["items"]}
        self.assertEqual(got["GTA 6"], [(1, "new", None), (2, "b", "2026-10-21"), (3, "d", "2026-10-21")])   # 番号は今日の続き
        self.assertEqual(got["ILLIT"], [(1, "y", "2026-10-21")])
        self.assertNotIn("あつ森", got)
        self.assertEqual(data["_carried"], "2026-10-21")

    def test_only_once_a_day(self):
        data, n = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        again, m = digest.carry_over(data, "2026-10-22")
        self.assertEqual((n, m), (3, 0))
        self.assertEqual(sum(len(b["entries"]) for b in again["items"]), 3)

    def test_too_old_is_left(self):
        data, n = digest.carry_over({"date": "2026-10-25", "items": []}, "2026-10-25")
        self.assertEqual((n, data["items"]), (0, []))

    def test_gate_sees_carried_work(self):
        data, _ = digest.carry_over({"date": "2026-10-22", "items": []}, "2026-10-22")
        (self.dir / "2026-10-22.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(gate.edit_work(self.dir, today="2026-10-22"), {"GTA 6": 2, "ILLIT": 1})   # AI 編集が起こされる


class RenderKeepsGoing(unittest.TestCase):
    def test_story_without_headline_is_skipped_not_crash(self):
        import render
        issue = {"date": "2026-10-22", "items": [{"name": "GTA 6", "stories": [
            {"url": "https://a.example/1", "weight": "normal"},                     # 見出しなし（2026-10-21 KeyError で 4 回止まった形）
            {"headline": "GTA 6 trailer", "url": "https://a.example/2", "weight": "lead"}]}]}
        works = render.collect([issue])
        self.assertEqual([x["headline"] for w in works for x in w["stories"]], ["GTA 6 trailer"])

    def test_write_page_soft_in_production_only(self):
        with mock.patch.object(digest, "_write_page", side_effect=KeyError("headline")), mock.patch("runlog.add"):
            with mock.patch.dict(digest.os.environ, {"WL_RENDER_SOFT": "1"}):
                self.assertIsNone(digest.write_page())          # 本番の収集：止めずに push へ
            with mock.patch.dict(digest.os.environ, {"WL_RENDER_SOFT": ""}):
                with self.assertRaises(KeyError):                # CI：今までどおり失敗で止まる
                    digest.write_page()


if __name__ == "__main__":
    unittest.main()
