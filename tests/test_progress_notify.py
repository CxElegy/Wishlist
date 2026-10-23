"""進み具合の Discord 通知（scripts/progress_notify.py）：送る中身の形。ネットには出ない。"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import progress_notify as pn  # noqa: E402


class PR(unittest.TestCase):
    def test_merged_and_opened(self):
        ev = {"action": "closed", "pull_request": {"merged": True, "title": "版面に番号", "number": 7, "changed_files": 3,
              "html_url": "https://github.com/CxElegy/Wishlist/pull/7", "body": "## 何を\n- 番号を入れた\n\n🤖 Generated with x\nhttps://claude.ai/code/s"}}
        em = pn.pr_payload(ev)["embeds"][0]
        self.assertIn("合併", em["title"])
        self.assertIn("番号を入れた", em["description"])
        self.assertNotIn("Generated", em["description"])
        self.assertIn("日本時間", em["footer"]["text"])
        self.assertIn("作業を始めました", pn.pr_payload({"action": "opened", "pull_request": {"title": "x"}})["embeds"][0]["title"])
        self.assertIsNone(pn.pr_payload({"action": "closed", "pull_request": {"merged": False}}))   # 閉じただけは送らない


class Backlog(unittest.TestCase):
    def test_changes(self):
        before = "- [~] A — 条件\n- [ ] B — 条件\n- [ ] C — 条件\n"
        after = "- [x] A — 条件（PR 1）\n- [?] B — 聞きたいこと\n- [ ] C — 条件\n- [ ] D — 新しい\n"
        titles = [e["title"] for e in pn.backlog_payload(before, after)["embeds"]]
        self.assertEqual(titles, ["✅ 済み：A", "❓ あなた待ち：B", "📝 一覧に追加：D"])
        self.assertIsNone(pn.backlog_payload(after, after))

    def test_real_backlog_parses(self):
        text = (pathlib.Path(__file__).resolve().parent.parent / "BACKLOG.md").read_text(encoding="utf-8")
        self.assertGreater(len(pn.items(text)), 5)


if __name__ == "__main__":
    unittest.main()
