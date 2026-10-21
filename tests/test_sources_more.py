"""情報源を広げる（2026-10-22）：GDELT・YouTube の公式チャンネル・Bluesky・Mastodon。ネットには出ない（_get を差し替える）。

    python -m unittest tests.test_sources_more
"""

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402


def fake_get(body):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    return mock.patch.object(sources, "_get", lambda url: data)


class Gdelt(unittest.TestCase):
    def test_articles_become_entries_with_image(self):
        body = {"articles": [{"url": "https://www.example.jp/a", "title": "チェンソーマン 新作", "seendate": "20261021T093000Z",
                              "socialimage": "https://www.example.jp/a.jpg", "domain": "example.jp", "language": "Japanese"},
                             {"url": "", "title": "no url"}]}
        seen = {}
        with mock.patch.object(sources, "_get", lambda url: seen.setdefault("url", url) and json.dumps(body).encode()):
            got = sources.gdelt("Chainsaw Man", 7, ["ja-JP", "en-US"])
        self.assertEqual([(e.title, e.source, e.image) for e in got], [("チェンソーマン 新作", "example.jp", "https://www.example.jp/a.jpg")])
        self.assertEqual(got[0].published, dt.datetime(2026, 10, 21, 9, 30, tzinfo=dt.timezone.utc))
        self.assertIn("sourcelang%3Ajapanese", seen["url"])   # 読者の言語だけ
        self.assertIn("sourcelang%3Aenglish", seen["url"])
        self.assertIn("timespan=7d", seen["url"])

    def test_busy_message_is_not_a_crash(self):
        with fake_get(b"Please limit requests to one every 5 seconds"):
            self.assertEqual(sources.gdelt("x", 7, ["en-US"]), [])

    def test_retries_when_busy(self):
        import urllib.error
        calls = []

        def get(url):
            calls.append(url)
            if len(calls) < 2:
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
            return json.dumps({"articles": [{"url": "https://a.example/1", "title": "t"}]}).encode()
        with mock.patch.object(sources, "_get", get), mock.patch.object(sources, "GDELT_WAIT", 0):
            self.assertEqual(len(sources.gdelt("x", 7, ["en-US"])), 1)
        self.assertEqual(len(calls), 2)

    def test_paced_five_seconds(self):
        self.assertGreaterEqual(sources.PACE["api.gdeltproject.org"], 5)


YT = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"
 xmlns:media="http://search.yahoo.com/mrss/"><title>Official Channel</title>
<entry><yt:videoId>abc123DEF45</yt:videoId><title>Teaser 2</title><published>2026-10-20T10:00:00+00:00</published>
<media:group><media:thumbnail url="https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg"/><media:description>new teaser</media:description></media:group></entry></feed>"""


class YouTube(unittest.TestCase):
    def test_channel_feed(self):
        with fake_get(YT):
            got = sources.youtube_channel("UC" + "a" * 22)
        self.assertEqual(got[0].url, "https://www.youtube.com/watch?v=abc123DEF45")
        self.assertEqual(got[0].source, "YouTube · Official Channel")
        self.assertEqual(got[0].image, "https://i.ytimg.com/vi/abc123DEF45/hqdefault.jpg")   # 必ずある版
        self.assertEqual(sources.youtube_channel("not-a-channel"), [])

    def test_channel_ids_from_items_or_wikidata_cached(self):
        tmp = pathlib.Path(tempfile.mkdtemp()) / "yt.json"
        calls = []
        with mock.patch.object(digest, "YOUTUBE_FILE", tmp), \
                mock.patch.object(sources, "youtube_channels_from_wiki", lambda w: calls.append(w) or ["UC" + "b" * 22]):
            self.assertEqual(digest.youtube_channels({"name": "A", "youtube": ["UC" + "c" * 22]}), ["UC" + "c" * 22])   # 書いてあればそれ
            self.assertEqual(digest.youtube_channels({"name": "B"}), [])                                          # wiki なし = なし
            item = {"name": "C", "wiki": ["en:C"]}
            self.assertEqual(digest.youtube_channels(item), ["UC" + "b" * 22])
            self.assertEqual(digest.youtube_channels(item), ["UC" + "b" * 22])
            self.assertEqual(len(calls), 1)   # 2 回目は覚えたものを使う（Wikidata に何度も聞かない）
            digest.youtube_channels({"name": "C", "wiki": ["en:C2"]})
            self.assertEqual(len(calls), 2)   # wiki が変わったら聞き直す


class Sns(unittest.TestCase):
    def test_bluesky_hot_line(self):
        body = {"posts": [
            {"uri": "at://did:x/app.bsky.feed.post/r1", "author": {"handle": "a.bsky.social"}, "record": {"text": "Chainsaw Man trailer!", "createdAt": "2026-10-20T00:00:00Z"},
             "likeCount": 120, "repostCount": 3, "embed": {"images": [{"fullsize": "https://cdn.bsky.app/full.jpg"}]}},
            {"uri": "at://did:x/app.bsky.feed.post/r2", "author": {"handle": "b.bsky.social"}, "record": {"text": "chainsaw man is ok"}, "likeCount": 2}]}
        with fake_get(body):
            got = sources.bluesky("Chainsaw Man", 7, ["en-US"])
        self.assertEqual([(e.url, e.hot) for e in got], [("https://bsky.app/profile/a.bsky.social/post/r1", True),
                                                         ("https://bsky.app/profile/b.bsky.social/post/r2", False)])
        self.assertEqual(got[0].image, "https://cdn.bsky.app/full.jpg")
        self.assertTrue(sources.is_sns(got[0]))

    def test_mastodon_tag_language_and_hot(self):
        body = [{"url": "https://m.example/@a/1", "content": "<p>#ChainsawMan 最高</p>", "language": "ja", "favourites_count": 30, "reblogs_count": 0},
                {"url": "https://m.example/@b/2", "content": "<p>#ChainsawMan</p>", "language": "es", "favourites_count": 99},
                {"url": "https://m.example/@bot/3", "content": "<p>https://www. wacoca.com/anime/1/ #ChainsawMan</p>", "language": "ja"}]
        seen = {}
        with mock.patch.object(sources, "_get", lambda url: seen.setdefault("url", url) and json.dumps(body).encode()):
            got = sources.mastodon_tag("Chainsaw Man", ["ja-JP"])
        self.assertTrue(seen["url"].endswith("/tag/ChainsawMan?limit=40"))
        self.assertEqual([(e.url, e.hot, e.title) for e in got], [("https://m.example/@a/1", True, "#ChainsawMan 最高")])   # 読者の言語だけ

    def test_sns_counts_as_fan_posts_in_heat(self):
        import heat
        self.assertTrue(heat.is_reddit({"source": "Bluesky"}))
        self.assertTrue(heat.is_reddit({"source": "Mastodon"}))
        self.assertFalse(heat.is_reddit({"source": "example.jp"}))

    def test_sns_needs_name_in_post_text(self):
        e = sources.Entry(title="lunch photo", url="https://bsky.app/profile/a/post/1", published=None, source="Bluesky", summary="Chainsaw Man")
        self.assertIsNone(digest.match_hit({"name": "Chainsaw Man"}, e))


class Routing(unittest.TestCase):
    """use の考え方：google → GDELT も・reddit → Bluesky・Mastodon も・YouTube は公式なので use に関係なく。"""

    def run_collect(self, item):
        hit = []
        mark = lambda name: (lambda *a, **k: hit.append(name) or [])
        with mock.patch.object(sources, "google_news", mark("google")), mock.patch.object(sources, "bing_news", mark("bing")), \
                mock.patch.object(sources, "reddit_search", mark("reddit")), mock.patch.object(sources, "gdelt", mark("gdelt")), \
                mock.patch.object(sources, "bluesky", mark("bluesky")), mock.patch.object(sources, "mastodon_tag", mark("mastodon")), \
                mock.patch.object(sources, "youtube_channel", mark("youtube")):
            digest.collect(item, {})
        return set(hit)

    def test_default_uses_everything(self):
        self.assertEqual(self.run_collect({"name": "x", "news_langs": ["ja-JP"], "youtube": ["UC" + "a" * 22]}),
                         {"google", "bing", "reddit", "gdelt", "bluesky", "mastodon", "youtube"})

    def test_common_word_titles_skip_sns(self):
        self.assertEqual(self.run_collect({"name": "FROM", "use": ["google", "bing"], "news_langs": ["en-US"]}), {"google", "bing", "gdelt"})


if __name__ == "__main__":
    unittest.main()
