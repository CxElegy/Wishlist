"""Reddit 帖子「火不火」「删没删」的规则（sources.reddit_* / digest.prune_reddit / heat 的帖子数）。不访问外网。

    python -m unittest discover tests
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import heat  # noqa: E402
import images  # noqa: E402
import sources  # noqa: E402


def feed(*posts):
    """Reddit RSS：posts = [(id, 正文)]。"""
    rows = "".join(
        f'<entry><content type="html">{body} &amp;#32; submitted by</content><id>t3_{pid}</id>'
        f'<link href="https://www.reddit.com/r/MMORPG/comments/{pid}/title_{pid}/" />'
        f"<updated>2026-10-16T00:00:00+00:00</updated><published>2026-10-16T00:00:00+00:00</published>"
        f"<title>Post {pid}</title></entry>" for pid, body in posts)
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{rows}</feed>'.encode()


def post_url(pid):
    return f"https://www.reddit.com/r/MMORPG/comments/{pid}/title_{pid}/"


class HotTest(unittest.TestCase):
    def setUp(self):
        images.clear_cache()

    def test_sub_new_posts_not_on_weekly_top_are_cold(self):
        def get(path, params):
            if path.endswith("/top"):
                self.assertEqual(params, {"t": "week", "limit": sources.REDDIT_HOT_TOP})
                return False, feed(("aaa", "hot one"))
            return False, feed(("aaa", "hot one"), ("bbb", "nobody replied"))
        with mock.patch.object(sources, "_reddit_get", get):
            got = {sources.reddit_id(e.url): e.hot for e in sources.reddit_sub("MMORPG")}
        self.assertEqual(got, {"aaa": True, "bbb": False})

    def test_unknown_top_list_is_not_empty_list(self):
        """榜が取れない（ネットワークの失敗）ときは「わからない」。空の榜扱いで全部撤去してはいけない。"""
        def get(path, params):
            raise OSError("network down")
        with mock.patch.object(sources, "_reddit_get", get):
            self.assertIsNone(sources.reddit_hot_ids("MMORPG"))

    def test_search_only_top_few_are_hot(self):
        posts = [(f"p{k}", "x") for k in range(8)]
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, feed(*posts))):
            hot = [e.hot for e in sources.reddit_search('"Moonbound"')]
        self.assertEqual(hot, [True] * sources.REDDIT_HOT_TOP + [False] * (8 - sources.REDDIT_HOT_TOP))

    def test_api_numbers_must_pass_minimum(self):
        """官方 API で数字が取れるときは、榜の上でも 赞 < 100 かつ 评论 < 30 は火ではない。"""
        def post(pid, score, comments):
            return {"data": {"title": pid, "permalink": f"/r/MMORPG/comments/{pid}/x/", "created_utc": 1792200000,
                             "subreddit": "MMORPG", "score": score, "num_comments": comments, "selftext": ""}}
        data = json.dumps({"data": {"children": [post("big", 450, 80), post("chat", 12, 31), post("quiet", 9, 2)]}}).encode()
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (True, data)):
            got = {e.title: e.hot for e in sources.reddit_search("q")}
        self.assertEqual(got, {"big": True, "chat": True, "quiet": False})


class RemovedTest(unittest.TestCase):
    def test_removed_and_deleted_posts(self):
        for body, want in (("[removed]", True), ("[deleted]", True), ("&lt;p&gt;Hey all!&lt;/p&gt;", False)):
            with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, feed(("abc", body)))):
                self.assertIs(sources.reddit_removed(post_url("abc")), want, body)

    def test_404_is_removed_rate_limit_is_unknown(self):
        def raise_(code):
            def get(path, params):
                raise urllib.error.HTTPError(path, code, "x", None, None)
            return get
        with mock.patch.object(sources, "_reddit_get", raise_(404)):
            self.assertTrue(sources.reddit_removed(post_url("abc")))
        with mock.patch.object(sources, "_reddit_get", raise_(429)):
            self.assertIsNone(sources.reddit_removed(post_url("abc")))

    def test_gone_uses_reddit_status(self):
        images.clear_cache()
        with mock.patch.object(sources, "reddit_removed", lambda u: True):
            self.assertTrue(images.gone(post_url("abc")))
        images.clear_cache()
        with mock.patch.object(sources, "reddit_removed", lambda u: None):  # 拿不到：不当成删了
            self.assertFalse(images.gone(post_url("abc")))


class PruneTest(unittest.TestCase):
    def setUp(self):
        images.clear_cache()
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        (root / "reports").mkdir()
        (root / "state").mkdir()
        today = dt.date.today().isoformat()
        stories = [{"headline": "removed", "url": post_url("gone1")}, {"headline": "cold", "url": post_url("cold1")},
                   {"headline": "hot", "url": post_url("hot1")}, {"headline": "news", "url": "https://news.example/a"},
                   {"headline": "search cold", "url": "https://www.reddit.com/r/tiny/comments/sc1/x/"},
                   {"headline": "search hot", "url": "https://www.reddit.com/r/big/comments/sh1/x/"}]
        self.path = root / "reports" / f"{today}.json"
        self.path.write_text(json.dumps({"date": today, "items": [{"name": "MMORPG 新作", "stories": stories}]}))
        self.patches = [mock.patch.object(digest, "REPORTS_DIR", root / "reports"),
                        mock.patch.object(digest, "REDDIT_CHECK_FILE", root / "state" / "reddit_check.json"),
                        mock.patch.object(digest, "load_config", lambda: ({}, [{"name": "MMORPG 新作", "subreddits": ["MMORPG"]}])),
                        mock.patch.object(sources, "reddit_removed", lambda u: "gone1" in u),
                        mock.patch.object(sources, "reddit_hot_ids", lambda sub: {"hot1", "gone1"}),
                        mock.patch.object(sources, "reddit_search", lambda q, strict=False: [
                            sources.Entry(title="t", url="https://www.reddit.com/r/big/comments/sh1/x/", published=None, source="Reddit")])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_removed_and_cold_posts_taken_off_the_board(self):
        self.assertTrue(digest.prune_reddit())
        left = [s["headline"] for s in json.loads(self.path.read_text())["items"][0]["stories"]]
        self.assertEqual(left, ["hot", "news", "search hot"])

    def test_unknown_top_list_is_retried_next_time(self):
        with mock.patch.object(sources, "reddit_hot_ids", lambda sub: None):
            digest.prune_reddit()
        checks = json.loads(digest.REDDIT_CHECK_FILE.read_text())
        self.assertNotIn(post_url("cold1"), checks)   # 榜が取れなかった帖子は記録しない（次の出刊でもう一度）
        self.assertTrue(checks[post_url("gone1")]["removed"])

    def test_checked_once_a_day(self):
        digest.prune_reddit()
        with mock.patch.object(sources, "reddit_removed", side_effect=AssertionError("今日はもう見た")):
            self.assertFalse(digest.prune_reddit())


class HeatCountTest(unittest.TestCase):
    def test_cold_posts_still_count_for_fan_reaction(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "2026-10-16.json"
            p.write_text(json.dumps({"date": "2026-10-16", "items": [{"name": "x", "entries": [
                {"url": post_url("hot1"), "date": "2026-10-16T00:00:00+00:00", "source": "r/MMORPG"}],
                "reddit_cold": [{"url": post_url("cold1"), "date": "2026-10-16T00:00:00+00:00", "source": "r/MMORPG"}]}]}))
            entries, _, _ = heat.load_entries([p])
        self.assertEqual(sum(heat.is_reddit(e) for e in entries["x"]), 2)


class MergeTest(unittest.TestCase):
    def test_merge_keeps_cold_list_without_duplicates(self):
        old = {"items": [{"name": "x", "entries": [], "facts": [], "reddit_cold": [{"url": "u1"}]}]}
        new = {"items": [{"name": "x", "entries": [], "facts": [], "reddit_cold": [{"url": "u1"}, {"url": "u2"}]}]}
        merged = digest.merge_inbox(old, new)
        self.assertEqual([d["url"] for d in merged["items"][0]["reddit_cold"]], ["u1", "u2"])


if __name__ == "__main__":
    unittest.main()
