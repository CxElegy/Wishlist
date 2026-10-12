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


class SyncNews(unittest.TestCase):
    """消息写进数据库：用本地 HTTP 服务器假装是 Supabase。"""

    def setUp(self):
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        self.posts, self.fail = [], False
        test = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                code = 404 if test.fail else 201
                self.send_response(code)
                self.end_headers()
                if test.fail:
                    self.wfile.write(b'{"code":"PGRST205"}')

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self.tmp.name)
        (tmp / "inbox").mkdir()
        entry = lambda n, url, t: {"n": n, "url": url, "title": t, "source": "S", "summary": "", "date": None}
        (tmp / "inbox" / "2026-10-11.json").write_text(json.dumps({"date": "2026-10-11", "items": [
            {"name": "猫用品", "entries": [entry(1, "u1", "旧标题"), entry(2, "u2", "B")]}]}), encoding="utf-8")
        (tmp / "inbox" / "2026-10-12.json").write_text(json.dumps({"date": "2026-10-12", "items": [
            {"name": "猫用品", "backfill": True, "entries": [entry(1, "u1", "新标题")]},
            {"name": "GTA 6", "entries": [{**entry(1, "u1", "C"), "urgent": True}]}]}), encoding="utf-8")
        self.patches = [
            mock.patch.object(digest, "INBOX_DIR", tmp / "inbox"),
            mock.patch.object(digest, "NEWS_SYNC_FILE", tmp / "state" / "db_news.json"),
            mock.patch.object(digest, "load_config", return_value=(
                {"supabase_url": f"http://127.0.0.1:{self.server.server_port}"}, [])),
            mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "sb_secret_test"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.server.shutdown()
        self.tmp.cleanup()

    def test_upserts_all_once_then_only_changes(self):
        digest.sync_news()
        self.assertEqual(len(self.posts), 1)
        path, headers, rows = self.posts[0]
        self.assertEqual(path, "/rest/v1/news?on_conflict=item,url")
        self.assertIn("merge-duplicates", headers["prefer"])
        self.assertEqual(headers["apikey"], "sb_secret_test")
        self.assertNotIn("authorization", headers)
        by_key = {(r["item"], r["url"]): r for r in rows}
        self.assertEqual(len(rows), len(by_key), "一次写入里不能有重复的行")
        self.assertEqual(by_key[("猫用品", "u1")]["title"], "新标题")       # 以最新一期为准
        self.assertEqual(by_key[("猫用品", "u1")]["collected_on"], "2026-10-12")
        self.assertTrue(by_key[("猫用品", "u1")]["backfill"])
        self.assertTrue(by_key[("GTA 6", "u1")]["urgent"])
        self.assertEqual(by_key[("猫用品", "u2")]["collected_on"], "2026-10-11")

        digest.sync_news()  # 没有变化：不再写
        self.assertEqual(len(self.posts), 1)

        p = digest.INBOX_DIR / "2026-10-12.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["items"][1]["entries"].append({"n": 2, "url": "u9", "title": "D", "source": "S", "summary": "", "date": None})
        p.write_text(json.dumps(data), encoding="utf-8")
        digest.sync_news()  # 只写变了的那一期
        self.assertEqual({r["url"] for r in self.posts[-1][2]}, {"u1", "u9"})
        self.assertEqual({r["collected_on"] for r in self.posts[-1][2]}, {"2026-10-12"})

    def test_failure_retries_next_time(self):
        self.fail = True
        digest.sync_news()
        self.assertFalse(digest.NEWS_SYNC_FILE.exists())
        self.fail = False
        digest.sync_news()
        self.assertEqual(len(self.posts), 2)
