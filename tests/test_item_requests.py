"""设置页「新增 / 修改关注项」：数据库里的请求写进 items.yaml。不访问网络。

    python -m unittest discover tests
"""

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402

ITEMS = """# 注释要留着
settings:
  timezone: Asia/Shanghai

items:
  - name: FROM
    type: show
    # 字段前的注释也留着
    keywords: [FROM]
    urgent_patterns:
      # 第四季
      - 'FROM.{0,20}season 4'

      - 'FROM.{0,20}renewed'
    notes: >-
      多行的
      背景说明
    status: 第三季播完

  - name: "ILLIT"
    type: event
    keywords: [ILLIT, 아일릿]
"""


class TakeItemRequests(unittest.TestCase):
    def setUp(self):
        self.file = pathlib.Path(tempfile.mkdtemp()) / "items.yaml"
        self.file.write_text(ITEMS, encoding="utf-8")
        patcher = mock.patch.object(digest, "ITEMS_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def run_with(self, *rows):
        rows = [{"id": n, **r} for n, r in enumerate(rows, 1)]

        def fake(path, body=None, prefer=None, method=None):
            self.calls.append((path, body, method))
            return rows if method is None else []
        with mock.patch.object(digest, "supabase", side_effect=fake):
            digest.take_item_requests()
        return {p: b for p, b, m in self.calls if m == "PATCH"}

    def items(self):
        return {i["name"]: i for i in yaml.safe_load(self.file.read_text(encoding="utf-8"))["items"]}

    def test_child_follows_parent_section(self):
        """上级（parent）：板块は上級と同じに直す。上級は今ある・自分に上級のない関注項だけ（1 層）。"""
        patched = self.run_with(
            {"action": "add", "name": "FROM 映像", "config": {"type": "show", "parent": "FROM", "subs": {"kind": "ドラマ"}}},
            {"action": "add", "name": "FROM グッズ", "config": {"type": "category", "parent": "FROM", "section": "好物",   # 面ごとの下級：自分の板块
                                                              "match": ["re:(?is)(?=.*(FROM))(?=.*(" + "グッズ|" * 60 + "コラボ))"]}},
            {"action": "add", "name": "孙", "config": {"type": "show", "parent": "FROM 映像"}},
            {"action": "add", "name": "没这个上级", "config": {"type": "show", "parent": "不存在"}})
        got = self.items()
        self.assertEqual((got["FROM 映像"]["parent"], got["FROM 映像"]["section"]), ("FROM", "影视"))
        self.assertEqual(got["FROM グッズ"]["section"], "好物")
        self.assertNotIn("孙", got)
        self.assertNotIn("没这个上级", got)
        self.assertIn("上级", patched["item_requests?id=eq.3"]["note"])
        settings, items = digest.load_config()
        self.assertEqual({i["name"]: digest.section_of(i) for i in items}["FROM 映像"], "影视")

    def test_delete_removes_block_and_unparents_children(self):
        """設定ページの「删」：edit + {_delete: true}。その 1 段だけ消え、下級は parent を外して残る。"""
        self.run_with({"action": "add", "name": "FROM 映像", "config": {"type": "show", "parent": "FROM"}})
        self.calls = []
        patched = self.run_with({"action": "edit", "name": "FROM", "config": {"_delete": True}},
                                {"action": "edit", "name": "没有这个", "config": {"_delete": True}})
        got = self.items()
        self.assertEqual(set(got), {"ILLIT", "FROM 映像"})
        self.assertNotIn("parent", got["FROM 映像"])
        self.assertTrue(self.file.read_text(encoding="utf-8").startswith("# 注释要留着"))
        self.assertEqual(patched["item_requests?id=in.(1)"]["status"], "done")
        self.assertIn("没有", patched["item_requests?id=eq.2"]["note"])

    def test_deleted_item_leaves_the_page_at_once(self):
        issues = [{"date": "2026-10-18", "items": [{"name": "FROM", "section": "影视"}, {"name": "消えた", "section": "好物"}]}]
        out = digest.with_manual_themes(issues, [{"name": "FROM", "type": "show"}])
        self.assertEqual([b["name"] for b in out[0]["items"]], ["FROM"])

    def test_add_appends_and_keeps_everything_else(self):
        patched = self.run_with({"action": "add", "name": "鬼灭之刃", "config": {
            "type": "anime", "section": "影视", "size": "L", "keywords": ["鬼灭之刃", "鬼滅の刃", 'Demon "Slayer"'],
            "match": ["鬼灭", "鬼滅"], "priority": "新一季什么时候播", "news_langs": ["zh-TW", "ja-JP"],
            "urgent_patterns": [r"(鬼滅の刃|鬼灭之刃).{0,30}(第\s?\d+\s?期|劇場版)"], "anilist_id": "101922", "evil": 1}})
        text = self.file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(ITEMS.rstrip("\n")))
        new = self.items()["鬼灭之刃"]
        self.assertEqual(new["keywords"], ["鬼灭之刃", "鬼滅の刃", 'Demon "Slayer"'])
        self.assertEqual(new["urgent_patterns"], [r"(鬼滅の刃|鬼灭之刃).{0,30}(第\s?\d+\s?期|劇場版)"])
        self.assertEqual((new["type"], new["section"], new["size"], new["anilist_id"]), ("anime", "影视", "L", 101922))
        self.assertIn(digest.WEB_ITEM_MARK, new["notes"])
        self.assertNotIn("evil", new)
        digest.load_config()  # 整份还能正常读
        self.assertEqual(patched["item_requests?id=in.(1)"]["status"], "done")

    def test_add_defaults(self):
        self.run_with({"action": "add", "name": "猫砂盆", "config": {}})
        new = self.items()["猫砂盆"]
        self.assertEqual((new["type"], new["keywords"]), ("product", ["猫砂盆"]))
        self.assertEqual(digest.section_of(new), "好物")

    def test_edit_changes_only_given_fields(self):
        self.run_with({"action": "edit", "name": "FROM", "config": {
            "priority": "第四季什么时候播", "urgent_patterns": ["FROM.{0,20}(season 4|第四季)"], "status": "不允许改的字段",
            "keywords": ["FROM", "从"], "subtitle": None}})
        text = self.file.read_text(encoding="utf-8")
        self.assertIn("# 字段前的注释也留着", text)
        got = self.items()
        self.assertEqual(got["FROM"]["urgent_patterns"], ["FROM.{0,20}(season 4|第四季)"])
        self.assertEqual(got["FROM"]["keywords"], ["FROM", "从"])
        self.assertEqual(got["FROM"]["priority"], "第四季什么时候播")
        self.assertEqual(got["FROM"]["notes"], "多行的 背景说明")
        self.assertEqual(got["FROM"]["status"], "第三季播完")
        self.assertEqual(got["ILLIT"], {"name": "ILLIT", "type": "event", "keywords": ["ILLIT", "아일릿"]})

    def test_edit_can_delete_field(self):
        self.run_with({"action": "edit", "name": "FROM", "config": {"notes": "", "urgent_patterns": []}})
        got = self.items()["FROM"]
        self.assertNotIn("notes", got)
        self.assertNotIn("urgent_patterns", got)
        self.assertEqual(got["status"], "第三季播完")

    def test_edit_last_item(self):
        self.run_with({"action": "edit", "name": "ILLIT", "config": {"size": "L", "news_langs": ["ko-KR", "ja-JP"]}})
        self.assertEqual(self.items()["ILLIT"]["news_langs"], ["ko-KR", "ja-JP"])
        self.assertEqual(self.items()["ILLIT"]["size"], "L")

    def test_bad_requests_skipped_with_reason(self):
        patched = self.run_with(
            {"action": "add", "name": "FROM", "config": {}},
            {"action": "edit", "name": "不存在", "config": {"priority": "x"}},
            {"action": "add", "name": "坏规则", "config": {"urgent_patterns": ["(没关上"]}},
            {"action": "add", "name": "坏语言", "config": {"news_langs": ["fr-FR"]}})
        self.assertEqual(self.file.read_text(encoding="utf-8"), ITEMS)
        notes = [b["note"] for p, b in patched.items()]
        self.assertEqual(len(notes), 4)
        self.assertIn("已经有", notes[0])
        self.assertIn("没有", notes[1])
        self.assertIn("要紧消息规则", notes[2])

    def test_add_then_edit_same_run(self):
        self.run_with({"action": "add", "name": "新游戏", "config": {"type": "game"}},
                      {"action": "edit", "name": "新游戏", "config": {"priority": "什么时候能玩"}})
        self.assertEqual(self.items()["新游戏"]["priority"], "什么时候能玩")

    def test_database_unreachable_changes_nothing(self):
        with mock.patch.object(digest, "supabase", side_effect=RuntimeError("HTTP 500")):
            digest.take_item_requests()
        self.assertEqual(self.file.read_text(encoding="utf-8"), ITEMS)


class RealItemsFile(unittest.TestCase):
    def test_every_item_can_be_edited_in_place(self):
        """真的 items.yaml：每一项改 priority 都只改到它自己。"""
        text = digest.ITEMS_FILE.read_text(encoding="utf-8")
        if not yaml.safe_load(text)["items"]:  # test2 が空のあいだは test1 の写し（archive/test1）で確かめる
            text = (digest.ROOT / "archive" / "test1" / "items.yaml").read_text(encoding="utf-8")
        before = yaml.safe_load(text)["items"]
        for item in before:
            after = yaml.safe_load(digest.set_item_fields(text, item["name"], {"priority": "测试", "size": "S"}))["items"]
            self.assertEqual([i["name"] for i in after], [i["name"] for i in before])
            for a, b in zip(after, before):
                if a["name"] == item["name"]:
                    self.assertEqual(a, {**b, "priority": "测试", "size": "S"})
                else:
                    self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


class NewItemPlaceholder(unittest.TestCase):
    def test_new_item_gets_collecting_block(self):
        issues = [{"date": "2026-10-14", "items": [{"name": "FROM", "stories": []}]},
                  {"date": "2026-10-13", "items": [{"name": "ILLIT", "stories": []}]}]
        items = [{"name": "FROM", "type": "show"}, {"name": "ILLIT", "type": "event"},
                 {"name": "新的", "type": "game", "subtitle": "副"}]
        got = digest.with_new_items(issues, items)
        self.assertEqual([b["name"] for b in got[0]["items"]], ["FROM", "新的"])
        new = got[0]["items"][-1]
        self.assertTrue(new["collecting"])
        self.assertEqual((new["section"], new["subtitle"], new["stories"]), ("游戏", "副", []))
        self.assertEqual([b["name"] for b in issues[0]["items"]], ["FROM"])  # 原数据没被改
        self.assertIs(digest.with_new_items(issues, items[:2]), issues)
