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

    def test_story_votes_learn_from_title_and_work(self):
        wishes = [{"name": "黑猫杯", "likes": {"猫": ["猫|black cat"], "马克杯": ["マグ|mug"]}, "basics": ["马克杯"]}]
        common = {"マグ"}
        taste = digest.learn_taste([
            {"url": "a", "vote": 1, "kind": "story", "title": "黒猫ではなく猫のマグ", "work": "星巴克马克杯"},
            {"url": "b", "vote": -1, "kind": "story", "title": "GTA 6 新预告", "work": "GTA 6"},
            {"url": "c", "vote": -1, "kind": "follow", "title": "x", "work": "GTA 6", "hits": ["开放世界大作"]},
        ], wishes, common)
        # 标题命中「猫」（具体喜好）；「马克杯」是基本属性不学；作品各记一笔；同类新发现不记作品（它不是那个作品本身）
        # （标签「猫」和关键词「猫」恰好同名，算一笔）
        self.assertEqual(taste, {"猫": 1, "作品:星巴克马克杯": 1, "作品:GTA 6": -1, "开放世界大作": -1})

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
        # 投票脚本挂在整页最后（所有消息卡片都要用），不在推荐区里
        self.assertIn('"https://x.supabase.co"', render.VOTE_JS % json.dumps({"url": "https://x.supabase.co", "key": "k"}))
        # data-v 属性里的 JSON 要转义，还原后和推荐一致
        import html, re
        data = json.loads(html.unescape(re.search(r'data-v="([^"]*)"', out).group(1)))
        self.assertEqual(data["url"], self.PICK["url"])
        self.assertEqual(data["words"], ["black cat"])


if __name__ == "__main__":
    unittest.main()


class Shuffle(unittest.TestCase):
    def pick(self, i, batch, kind="wish"):
        return {"title": f"t{i}", "url": f"https://e/{i}", "source": "S", "date": "2026-10-12", "work": "w",
                "image": None, "because": "b", "hits": [], "kind": kind, "batch": batch}

    def test_first_batch_visible_rest_in_pool(self):
        picks = [self.pick(i, i // 5) for i in range(12)] + [self.pick(20 + i, i // 4, "follow") for i in range(6)]
        out = render._picks(picks, [])
        visible, pool = out.split('<div class="pkpool" hidden>')
        self.assertEqual(visible.count('data-u='), 5 + 4)       # 没有脚本时显示第一批
        self.assertEqual(pool.count('data-u='), 7 + 2)          # 其余都在隐藏的池子里，脚本随机抽
        self.assertEqual(out.count("data-f=1"), 6)                # 同类新发现做了标记
        self.assertIn("换一批", out)
        self.assertIn("共 18 条", out)

    def test_explore_marked(self):
        out = render._picks([{**self.pick(1, 0), "explore": True}, self.pick(2, 1)], [])
        self.assertIn("换换口味 · 因为你想要", out)
        self.assertIn("data-new=1", out)

    def test_single_batch_has_no_button(self):
        out = render._picks([self.pick(i, 0) for i in range(3)], [])
        self.assertNotIn("换一批", out)
        self.assertNotIn("pkpool", out)


class SyncNews(unittest.TestCase):
    """消息写进数据库：用本地 HTTP 服务器假装是 Supabase。"""

    def setUp(self):
        import os
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        self.posts, self.broken = [], False
        test = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                code = 404 if test.broken else 201
                self.send_response(code)
                self.end_headers()
                if test.broken:
                    self.wfile.write(b'{"code":"PGRST205"}')

            def do_GET(self):
                test.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, None))
                body = json.dumps(getattr(test, "get_rows", [])).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def do_PATCH(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                self.send_response(204)
                self.end_headers()

            def do_DELETE(self):
                test.posts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, None))
                self.send_response(404 if test.broken else 204)
                self.end_headers()

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
        (tmp / "reports").mkdir()
        (tmp / "reports" / "2026-10-12.json").write_text(json.dumps({"date": "2026-10-12", "items": [
            {"name": "猫用品", "stories": [
                {"headline": "黑猫杯开卖", "highlight": "开卖", "blurb": "", "weight": "lead", "url": "u1",
                 "image": "", "date": "2026-10-11"},
                {"headline": "第二条", "highlight": "", "blurb": "", "weight": "normal", "url": "u2", "image": "i"}]}]}),
            encoding="utf-8")
        (tmp / "facts.json").write_text(json.dumps({
            "steam:1": {"text": "¥ 98（-50%）", "stable": "98", "item": "游戏A", "label": "Steam 价格"},
            "tmdb:tv/1": {"text": "旧格式", "stable": "x"}}), encoding="utf-8")
        self.wishes = [{"name": "黑猫杯", "price": 850, "currency": "NT$"}, {"name": "没价格"}]
        self.patches = [
            mock.patch.object(digest, "REPORTS_DIR", tmp / "reports"),
            mock.patch.object(digest, "STORIES_SYNC_FILE", tmp / "state" / "db_stories.json"),
            mock.patch.object(digest, "PRICES_SYNC_FILE", tmp / "state" / "db_prices.json"),
            mock.patch.object(digest, "FACTS_FILE", tmp / "facts.json"),
            mock.patch.object(digest, "load_wishlist", side_effect=lambda: self.wishes),
            mock.patch.object(digest, "INBOX_DIR", tmp / "inbox"),
            mock.patch.object(digest, "NEWS_SYNC_FILE", tmp / "state" / "db_news.json"),
            mock.patch.object(digest, "load_config", return_value=(
                {"supabase_url": f"http://127.0.0.1:{self.server.server_port}"}, [])),
            mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "sb_secret_test"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):  # 倒着停：同一个函数被打了两层补丁时才能还原
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
        self.broken = True
        digest.sync_news()
        self.assertFalse(digest.NEWS_SYNC_FILE.exists())
        self.broken = False
        digest.sync_news()
        self.assertEqual(len(self.posts), 2)


class SyncHistory(SyncNews):
    """编排后的报道、价格 / 状态历史写进数据库（沿用 SyncNews 的假服务器）。"""

    def test_upserts_all_once_then_only_changes(self):
        pass  # 父类的测试，这里不重复

    def test_failure_retries_next_time(self):
        pass

    def test_stories_replace_whole_issue_once(self):
        digest.sync_stories()
        self.assertEqual([x[0] for x in self.posts], ["/rest/v1/stories?issue_date=eq.2026-10-12", "/rest/v1/stories"])
        rows = self.posts[1][2]
        self.assertEqual([(r["item"], r["pos"], r["headline"]) for r in rows], [("猫用品", 0, "黑猫杯开卖"), ("猫用品", 1, "第二条")])
        self.assertEqual(rows[0]["story_date"], "2026-10-11")
        self.assertIsNone(rows[1]["story_date"])
        self.assertIsNone(rows[0]["image"])            # 空字符串存成 NULL
        self.assertEqual(len({tuple(sorted(r)) for r in rows}), 1, "批量写入的每行字段要一样")
        digest.sync_stories()                           # 没变化：不再写
        self.assertEqual(len(self.posts), 2)

    def test_prices_only_when_changed(self):
        digest.sync_prices()
        rows = self.posts[0][2]
        self.assertEqual({(r["kind"], r["item"], r["value"]) for r in rows},
                         {("steam", "游戏A", "¥ 98（-50%）"), ("wishlist", "黑猫杯", "NT$ 850")})  # 旧格式的状态先跳过
        self.assertEqual([r["amount"] for r in rows if r["kind"] == "wishlist"], [850])
        digest.sync_prices()
        self.assertEqual(len(self.posts), 1)            # 没变化：不再写
        self.wishes[0]["price"] = 790
        digest.sync_prices()
        self.assertEqual([(r["item"], r["value"]) for r in self.posts[1][2]], [("黑猫杯", "NT$ 790")])

    def test_failure_is_retried(self):
        self.broken = True
        digest.sync_stories()
        digest.sync_prices()
        self.broken = False
        digest.sync_stories()
        digest.sync_prices()
        self.assertTrue(digest.STORIES_SYNC_FILE.exists())
        self.assertTrue(digest.PRICES_SYNC_FILE.exists())
        self.assertEqual(len(self.posts[-1][2]), 2)     # 价格：失败那次没记下，重试时两条都写


class TakeWishes(SyncNews):
    """新闻里点了「♥ 加入心愿单」：从数据库读出请求，追加进 wishlist.yaml。"""

    def test_upserts_all_once_then_only_changes(self):
        pass

    def test_failure_retries_next_time(self):
        pass

    def setUp(self):
        super().setUp()
        for patch in [x for x in self.patches if getattr(x, "attribute", "") == "load_wishlist"]:
            patch.stop()  # 这里要读真的（临时的）wishlist.yaml
            self.patches.remove(patch)
        tmp = pathlib.Path(self.tmp.name)
        self.wl = tmp / "wishlist.yaml"
        self.wl.write_text("# 注释要保留\nwishlist:\n  - name: 已有的杯子\n    url: https://e/have\n    status: 想要\n",
                           encoding="utf-8")
        for patch in (mock.patch.object(digest, "WISHLIST_FILE", self.wl),
                      mock.patch.object(digest, "_save_wish_image", side_effect=lambda u: "news-x.jpg" if u else None),
                      mock.patch.object(digest, "load_config", return_value=(
                          {"supabase_url": f"http://127.0.0.1:{self.server.server_port}", "timezone": "Asia/Shanghai"},
                          [{"name": "猫用品"}]))):
            patch.start()
            self.patches.append(patch)

    def test_adds_new_and_skips_existing(self):
        self.get_rows = [
            {"id": 1, "url": "https://e/new", "title": "黒猫の\"マグ\"発売: 限定", "work": "猫用品", "image": "https://i/1.jpg",
             "source": "PR TIMES"},
            {"id": 2, "url": "https://e/have", "title": "重复的", "work": "猫用品", "image": None, "source": None},
            {"id": 3, "url": "https://e/new", "title": "同一条点了两次", "work": "其他", "image": None, "source": None},
            {"id": 4, "url": "https://example.com/__setup-test__", "title": "设置测试", "work": None, "image": None,
             "source": None},
        ]
        digest.take_wish_requests()
        text = self.wl.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 注释要保留\n"))                 # 原来的内容一字不动
        wishes = digest.load_wishlist()
        self.assertEqual([w["name"] for w in wishes], ["已有的杯子", '黒猫の"マグ"発売: 限定'])
        new = wishes[1]
        self.assertEqual((new["url"], new["image"], new["watch"], new["status"], new["shop"]),
                         ("https://e/new", "news-x.jpg", "猫用品", "想要", "PR TIMES"))
        patches = [(path, body["status"]) for path, _, body in self.posts if body and "status" in body]
        self.assertEqual(patches, [("/rest/v1/wish_requests?id=in.(1)", "done"), ("/rest/v1/wish_requests?id=in.(2,3,4)", "skipped")])

    def test_nothing_pending(self):
        self.get_rows = []
        before = self.wl.read_text(encoding="utf-8")
        digest.take_wish_requests()
        self.assertEqual(self.wl.read_text(encoding="utf-8"), before)
