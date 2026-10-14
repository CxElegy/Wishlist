"""设置页「新增关注项」：数据库里的请求追加进 items.yaml。不访问网络。

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
    keywords: [FROM]
"""


class TakeItemRequests(unittest.TestCase):
    def setUp(self):
        self.file = pathlib.Path(tempfile.mkdtemp()) / "items.yaml"
        self.file.write_text(ITEMS, encoding="utf-8")
        patcher = mock.patch.object(digest, "ITEMS_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def run_with(self, rows):
        def fake(path, body=None, prefer=None, method=None):
            self.calls.append((path, body, method))
            return rows if method is None else []
        with mock.patch.object(digest, "supabase", side_effect=fake):
            digest.take_item_requests()

    def test_appends_new_item_and_keeps_comments(self):
        self.run_with([{"id": 7, "name": "鬼灭之刃", "type": "anime", "keywords": ["鬼灭之刃", "鬼滅の刃", 'Demon "Slayer"'],
                        "priority": "新一季什么时候播", "section": "影视", "size": "L", "news_langs": ["zh-TW", "ja-JP"]}])
        text = self.file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 注释要留着"))
        _, items = digest.load_config()
        new = items[-1]
        self.assertEqual([i["name"] for i in items], ["FROM", "鬼灭之刃"])
        self.assertEqual(new["keywords"], ["鬼灭之刃", "鬼滅の刃", 'Demon "Slayer"'])
        self.assertEqual((new["type"], new["section"], new["size"], new["news_langs"], new["priority"]),
                         ("anime", "影视", "L", ["zh-TW", "ja-JP"], "新一季什么时候播"))
        self.assertIn(("item_requests?id=in.(7)", mock.ANY, "PATCH"), self.calls)
        self.assertEqual(self.calls[-1][1]["status"], "done")

    def test_skips_existing_and_invalid(self):
        self.run_with([{"id": 1, "name": "FROM", "type": "show", "keywords": ["FROM"], "size": "M"},
                       {"id": 2, "name": "坏语言", "type": "game", "keywords": ["x"], "size": "M", "news_langs": ["fr-FR"]}])
        self.assertEqual(self.file.read_text(encoding="utf-8"), ITEMS)
        self.assertEqual(self.calls[-1][0], "item_requests?id=in.(1,2)")
        self.assertEqual(self.calls[-1][1]["status"], "skipped")

    def test_optional_fields_left_out(self):
        self.run_with([{"id": 3, "name": "猫砂盆", "type": "category", "keywords": ["猫砂盆"], "size": "S"}])
        new = yaml.safe_load(self.file.read_text(encoding="utf-8"))["items"][-1]
        self.assertNotIn("section", new)
        self.assertNotIn("news_langs", new)
        self.assertEqual(digest.section_of(new), "好物")

    def test_database_unreachable_changes_nothing(self):
        with mock.patch.object(digest, "supabase", side_effect=RuntimeError("HTTP 500")):
            digest.take_item_requests()
        self.assertEqual(self.file.read_text(encoding="utf-8"), ITEMS)


if __name__ == "__main__":
    unittest.main()
