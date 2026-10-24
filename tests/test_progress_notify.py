"""進み具合の Discord 通知（scripts/progress_notify.py）：送る中身の形。ネットには出ない。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import progress_notify as pn  # noqa: E402


class PageEffect(__import__("unittest").TestCase):
    """合併の知らせの「画面の更新あり／なし」（2026-10-25，用户定的）。"""

    def test_docs_only_is_none(self):
        self.assertEqual(pn.page_effect(["BACKLOG.md", "HARNESS.md", ".claude/workflows/harness-forever.js", "harness/ux_check.py", "tests/test_x.py"]), "none")

    def test_page_files_are_maybe(self):
        for f in ("scripts/render.py", "items.yaml", "docs/testground/emblem-manage.html", "templates/a.css", "db/x.sql"):
            self.assertEqual(pn.page_effect(["BACKLOG.md", f]), "maybe", f)

    def test_message_says_it(self):
        ev = {"action": "closed", "pull_request": {"merged": True, "title": "t", "number": 1, "html_url": "u", "body": "b"}}
        self.assertIn("画面の更新：**なし**", pn.pr_payload(ev, ["BACKLOG.md"])["embeds"][0]["description"])
        self.assertIn("画面の更新：**あり", pn.pr_payload(ev, ["scripts/render.py"])["embeds"][0]["description"])


class PR(unittest.TestCase):
    def test_merged_and_opened(self):
        ev = {"action": "closed", "pull_request": {"merged": True, "title": "版面に番号", "number": 7, "changed_files": 3,
              "html_url": "https://github.com/CxElegy/Wishlist/pull/7", "body": "## 何を\n- 番号を入れた\n\n🤖 Generated with x\nhttps://claude.ai/code/s"}}
        em = pn.pr_payload(ev)["embeds"][0]
        self.assertIn("合併", em["title"])
        self.assertIn("番号を入れた", em["description"])
        self.assertNotIn("Generated", em["description"])
        self.assertIn("日本時間", em["footer"]["text"])
        self.assertIsNone(pn.pr_payload({"action": "opened", "pull_request": {"title": "x"}}))   # 出しただけは送らない
        self.assertIsNone(pn.pr_payload({"action": "closed", "pull_request": {"merged": False}}))   # 閉じただけは送らない


class Backlog(unittest.TestCase):
    def test_changes(self):
        before = "- [~] A — 条件\n- [ ] B — 条件\n- [ ] C — 条件\n"
        after = "- [x] A — 条件（PR 1）\n- [?] B — 聞きたいこと\n- [ ] C — 条件\n- [ ] D — 新しい\n"
        titles = [e["title"] for e in pn.backlog_payload(before, after)["embeds"]]
        self.assertEqual(titles, ["❓ あなた待ち：B"])   # 送るのはあなた待ちだけ
        self.assertIsNone(pn.backlog_payload(after, after))

    def test_real_backlog_parses(self):
        text = (pathlib.Path(__file__).resolve().parent.parent / "BACKLOG.md").read_text(encoding="utf-8")
        self.assertGreater(len(pn.items(text)), 5)


if __name__ == "__main__":
    unittest.main()
