"""「我会喜欢？」投票学习的测试：不访问网络。

    python -m unittest discover tests
"""

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import render  # noqa: E402


def row(url, vote, hits=(), words=()):
    return {"url": url, "vote": vote, "hits": list(hits), "words": list(words), "title": url}


class LearnTaste(unittest.TestCase):
    def test_votes_add_up_per_label_and_keyword(self):
        taste = digest.learn_taste([
            row("a", 1, ["猫"], ["black cat"]),
            row("b", 1, ["猫"]),
            row("c", -1, ["动物 / 角色造型"], ["ポケモン"]),
            row("d", 1, ["动物 / 角色造型"], ["snoopy"]),
        ])
        # 角色造型 一赞一踩抵消，不出现
        self.assertEqual(taste, {"猫": 2, "black cat": 1, "ポケモン": -1, "snoopy": 1})

    def test_bonus_is_clamped_and_explained(self):
        taste = {"猫": 5, "black cat": 3, "ポケモン": -9}
        self.assertEqual(digest.taste_bonus(taste, ["猫", "black cat"]), (4, [["猫", 5], ["black cat", 3]]))
        self.assertEqual(digest.taste_bonus(taste, ["ポケモン"])[0], -6)
        self.assertEqual(digest.taste_bonus(taste, ["没投过"]), (0, []))


class LoadFeedback(unittest.TestCase):
    def test_latest_vote_wins_and_undo_drops(self):
        rows = [row("a", 1), row("a", -1), row("b", 1), row("b", 0), row("c", -1)]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "feedback.json"
            path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
            with mock.patch.object(digest, "FEEDBACK_FILE", path), \
                 mock.patch.object(digest, "load_config", return_value=({}, [])):
                votes = digest.load_feedback()
        self.assertEqual({r["url"]: r["vote"] for r in votes}, {"a": -1, "c": -1})


class VoteButtons(unittest.TestCase):
    PICK = {"title": "黒猫マグ", "url": "https://example.com/a?x=1&y=\"2\"", "source": "S", "date": "2026-10-12",
            "work": "猫用品", "image": None, "because": "黑猫杯", "hits": ["猫"], "kind": "wish",
            "words": ["black cat"], "taste": [["猫", 2]]}

    def test_no_buttons_without_database(self):
        out = render._picks([self.PICK], [])
        self.assertNotIn('class="vote"', out)
        self.assertNotIn("<script>", out)

    def test_buttons_carry_vote_data(self):
        out = render._picks([self.PICK], [], {"url": "https://x.supabase.co", "key": "sb_publishable_k"})
        self.assertIn('data-vote="1"', out)
        self.assertIn('data-vote="-1"', out)
        self.assertIn("按你的投票：猫 +2", out)
        self.assertIn('"https://x.supabase.co"', out)
        # data-v 属性里的 JSON 要转义，还原后和推荐一致
        import html, re
        data = json.loads(html.unescape(re.search(r'data-v="([^"]*)"', out).group(1)))
        self.assertEqual(data["url"], self.PICK["url"])
        self.assertEqual(data["words"], ["black cat"])


if __name__ == "__main__":
    unittest.main()
