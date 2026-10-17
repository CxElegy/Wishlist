"""版面には AI 編集が整理した記事だけ：未整理の新着は「整理待ち」（digest.split_unedited / publish。部品 render._pending は test_design.py）。
要紧消息だけは例外で、すぐ「重大」として載る。ネットワークには出ない。

    python -m unittest tests.test_pending
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402

ITEM = {"name": "Astrae Oratio", "type": "game", "section": "游戏", "keywords": ["Astrae Oratio"], "match": ["Astrae"],
        "urgent_patterns": ["リリース日"]}


def entry(title, n):
    return sources.Entry(title=title, url=f"https://example.com/{n}", source=f"媒体{n}", summary="", image="", published=None)


def raw_entry(title, n):
    return {"n": n, "date": "2026-10-17T01:00:00+00:00", "source": f"媒体{n}", "title": title,
            "summary": "", "url": f"https://example.com/{n}", "image": ""}


class SplitUnedited(unittest.TestCase):
    def test_only_urgent_goes_on_board(self):
        pairs = [(4, entry("Astrae Oratio インタビュー", 4)), (5, entry("Astrae Oratio リリース日決定", 5)),
                 (6, entry("Astrae Oratio CBT 感想", 6))]
        stories, pending = digest.split_unedited(pairs, ITEM)
        self.assertEqual([(s["refs"], s["weight"]) for s in stories], [([5], "hero")])   # 編号は inbox の番号のまま
        self.assertEqual([p["n"] for p in pending], [4, 6])
        self.assertEqual(pending[0]["title"], "Astrae Oratio インタビュー")
        self.assertEqual(pending[0]["source"], "媒体4")

    def test_nothing_urgent(self):
        stories, pending = digest.split_unedited([(1, entry("Astrae Oratio CBT", 1))], ITEM)
        self.assertEqual(stories, [])
        self.assertEqual(len(pending), 1)


class Publish(unittest.TestCase):
    """publish を通して：AI 編集のあとに来た記事・AI 編集がまだの版面の記事は版面に載らない。"""

    def _publish(self, raw_items, edit=None):
        d = pathlib.Path(self.tmp.name)
        inbox = d / "2026-10-17.json"
        inbox.write_text(json.dumps({"date": "2026-10-17", "items": raw_items}, ensure_ascii=False), encoding="utf-8")
        reports = d / "reports"
        reports.mkdir()
        if edit is not None:
            (d / "2026-10-17.edit.json").write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
        items = [ITEM, {**ITEM, "name": "新作", "urgent_patterns": []}]
        with mock.patch.multiple(digest, load_config=lambda: ({}, items), load_sizes=lambda: {},
                                 attach_media=lambda stories, *a, **k: stories, recommend=lambda *a, **k: None,
                                 write_page=lambda *a, **k: None, write_issue_markdown=lambda *a, **k: None,
                                 REPORTS_DIR=reports, THEMES_FILE=d / "themes.json"), \
                mock.patch.object(digest.theme, "resolve", lambda *a, **k: {}):
            digest.publish(inbox)
        return {b["name"]: b for b in json.loads((reports / "2026-10-17.json").read_text(encoding="utf-8"))["items"]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_late_entries_wait_and_urgent_goes_first(self):
        es = [raw_entry("Astrae Oratio 開発者インタビュー", 1), raw_entry("Astrae Oratio CBT 感想まとめ", 2),
              raw_entry("Astrae Oratio リリース日は 12 月", 3)]
        edit = {"Astrae Oratio": [{"headline": "開発者インタビュー", "weight": "lead", "refs": [1]}],
                "_covered": {"Astrae Oratio": 1}}
        out = self._publish([{"name": "Astrae Oratio", "facts": [], "entries": es}], edit)["Astrae Oratio"]
        self.assertEqual([s["refs"] for s in out["stories"]], [[3], [1]])   # 要紧（3）が先頭の重大、AI の記事（1）
        self.assertEqual(out["stories"][0]["weight"], "hero")
        self.assertEqual([p["n"] for p in out["pending"]], [2])            # 2 は整理待ち（版面に載らない）

    def test_new_item_without_edit_is_pending_not_blank(self):
        es = [raw_entry("新作 発表", 1), raw_entry("新作 PV", 2)]
        out = self._publish([{"name": "新作", "facts": [], "entries": es}], {})["新作"]
        self.assertEqual(out["stories"], [])                 # 未整理の原題は記事にしない
        self.assertEqual(len(out["pending"]), 2)             # 空白ではなく「整理待ち」の版面として残る
        self.assertNotIn("quiet", out)

    def test_fully_edited_has_no_pending(self):
        es = [raw_entry("Astrae Oratio 開発者インタビュー", 1)]
        edit = {"Astrae Oratio": [{"headline": "x", "refs": [1]}], "_covered": {"Astrae Oratio": 1}}
        out = self._publish([{"name": "Astrae Oratio", "facts": [], "entries": es}], edit)["Astrae Oratio"]
        self.assertNotIn("pending", out)


if __name__ == "__main__":
    unittest.main()
