"""地域ごとの情報員（2026-10-22）：intel/*.yaml・担当の規則・同じフィードは 1 回・情報源ごとの様子。
読み取りの共通部分（RSS 1.0・宣言のない接頭辞・ホストごとの UA）も。ネットには出ない（_get を差し替える）。

    python -m unittest tests.test_intel
"""

import pathlib
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import intel  # noqa: E402
import sources  # noqa: E402

RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel rdf:about="https://www.4gamer.net/"><title>4Gamer.net</title></channel>
<item rdf:about="https://www.4gamer.net/games/1/"><title>「あつまれ どうぶつの森」新アップデート</title>
<link>https://www.4gamer.net/games/1/</link><description>&lt;img src="https://www.4gamer.net/a.jpg"&gt;本文</description>
<dc:date>2026-10-22T08:00:00+09:00</dc:date></item>
<item rdf:about="https://www.4gamer.net/games/2/"><title>【Amazonセール】ゲーミングモニター</title><link>https://www.4gamer.net/games/2/</link></item>
</rdf:RDF>""".encode()

UNBOUND = b"""<?xml version="1.0"?><rss version="2.0"><channel><item><title>VOGUE KOREA</title><link>https://www.vogue.co.kr/1</link>
<media:content url="https://img.vogue.co.kr/1.jpg"/></item></channel></rss>"""

JAPAN = {"id": "japan", "ja": "日本の情報員", "langs": ["ja-JP"], "sources": [
    {"id": "4gamer", "name": "4Gamer.net", "url": "https://www.4gamer.net/rss/index.xml", "cats": ["游戏"], "exclude": ["Amazonセール"]},
    {"id": "natalie-music", "name": "音楽ナタリー", "url": "https://natalie.mu/music/feed/news", "cats": ["演出"]},
    {"id": "all", "name": "全部", "url": "https://example.jp/all.xml", "cats": "*"},
]}
ON = {"intel": ["japan"], "news_langs": ["zh-TW", "en-US", "ja-JP"]}


class Reading(unittest.TestCase):
    def test_rss1_rdf(self):
        got = sources.rss_bytes(RDF, "4Gamer.net")
        self.assertEqual([e.title for e in got], ["「あつまれ どうぶつの森」新アップデート", "【Amazonセール】ゲーミングモニター"])
        self.assertEqual(got[0].published.isoformat(), "2026-10-22T08:00:00+09:00")   # dc:date
        self.assertEqual(got[0].image, "https://www.4gamer.net/a.jpg")

    def test_undeclared_media_prefix_is_fixed(self):
        with mock.patch.object(sources, "_warn") as warn:
            got = sources.rss_bytes(UNBOUND, "VOGUE KOREA")
        self.assertEqual([(e.title, e.image) for e in got], [("VOGUE KOREA", "https://img.vogue.co.kr/1.jpg")])
        warn.assert_not_called()

    def test_other_broken_xml_still_warns(self):
        with mock.patch.object(sources, "_warn") as warn:
            self.assertEqual(sources.rss_bytes(b"<rss><channel><item>", "x"), [])
        warn.assert_called_once()

    def test_host_user_agent(self):
        self.assertTrue(sources.user_agent("https://natalie.mu/comic/feed/news").startswith("Python-urllib/"))   # ナタリーは Mozilla を 405
        self.assertEqual(sources.user_agent("https://www.4gamer.net/rss/index.xml"), sources.USER_AGENT)
        self.assertEqual(sources.user_agent("https://evilnatalie.mu/x"), sources.USER_AGENT)


class Agents(unittest.TestCase):
    def setUp(self):
        intel.reset()
        self.p = mock.patch.object(intel, "regions", lambda: {"japan": JAPAN})
        self.p.start()

    def tearDown(self):
        self.p.stop()
        intel.reset()

    def test_by_own_langs(self):
        self.assertEqual(intel.agents_for({"name": "a", "news_langs": ["ja-JP"]}, ON), ["japan"])
        self.assertEqual(intel.agents_for({"name": "b", "news_langs": ["en-US"]}, ON), [])
        self.assertEqual(intel.agents_for({"name": "c"}, ON), [])   # settings の既定の言語は数えない

    def test_switch_and_explicit(self):
        self.assertEqual(intel.agents_for({"name": "a", "news_langs": ["ja-JP"]}, {}), [])         # 開關なし = 動かない
        self.assertEqual(intel.agents_for({"name": "a", "news_langs": ["ja-JP"], "intel": []}, ON), [])   # 関注項が止めた
        self.assertEqual(intel.agents_for({"name": "b", "news_langs": ["en-US"], "intel": ["japan"]}, ON), ["japan"])
        self.assertEqual(intel.agents_for({"name": "b", "intel": ["korea"]}, ON), [])               # 開關にない地域

    def test_sources_by_board(self):
        names = lambda item: [s["id"] for _, s in intel.sources_for(item, ON)]
        self.assertEqual(names({"name": "あつ森", "section": "游戏", "news_langs": ["ja-JP"]}), ["4gamer", "all"])
        self.assertEqual(names({"name": "GTA", "type": "game", "news_langs": ["ja-JP"]}), ["4gamer", "all"])   # section がなければ type から
        self.assertEqual(names({"name": "x", "section": "影视", "also": {"演出": {}}, "news_langs": ["ja-JP"]}), ["natalie-music", "all"])

    def test_fetched_once_and_copied(self):
        calls = []
        with mock.patch.object(sources, "_get", lambda url: calls.append(url) or (RDF if "4gamer" in url else b"<rss/>")):
            a = intel.entries_for({"name": "a", "section": "游戏", "news_langs": ["ja-JP"]}, ON)
            b = intel.entries_for({"name": "b", "section": "游戏", "news_langs": ["ja-JP"]}, ON)
        self.assertEqual(calls.count("https://www.4gamer.net/rss/index.xml"), 1)   # 関注項が 2 つでも取るのは 1 回
        self.assertNotIn("【Amazonセール】ゲーミングモニター", [e.title for e in a])  # 情報源の exclude
        a[0].image_via = "changed"
        self.assertEqual(b[0].image_via, "")   # 写しなので、片方への書き足しはもう片方に移らない

    def test_health_names_what_failed(self):
        def get(url):
            if "natalie" in url:
                raise urllib.error.HTTPError(url, 405, "Not Allowed", {}, None)
            return RDF if "4gamer" in url else b"<rss><channel></channel></rss>"
        with mock.patch.object(sources, "_get", get), mock.patch.object(sources, "_warn"):
            for _, src in intel.sources_for({"name": "x", "section": "游戏", "also": {"演出": {}}, "news_langs": ["ja-JP"]}, ON):
                intel.fetch("japan", src)
        h = intel.health()
        self.assertIn("日本の情報員：1/3 本", h)
        self.assertIn("音楽ナタリー（blocked）", h)
        self.assertNotIn("全部（", h)   # 記事がなかっただけ（no-results）は「取れない」に入れない


class Collect(unittest.TestCase):
    def test_collect_reads_intel(self):
        seen = []
        with mock.patch.object(sources, "google_news", lambda *a: []), mock.patch.object(sources, "bing_news", lambda *a: []), \
                mock.patch.object(sources, "reddit_search", lambda *a: []), mock.patch.object(sources, "gdelt", lambda *a: []), \
                mock.patch.object(sources, "bluesky", lambda *a: []), mock.patch.object(sources, "mastodon_tag", lambda *a: []), \
                mock.patch.object(intel, "entries_for", lambda item, s: seen.append(item["name"]) or []):
            digest.collect({"name": "あつ森", "news_langs": ["ja-JP"]}, {})
        self.assertEqual(seen, ["あつ森"])

    def test_real_files_are_valid(self):
        intel.reset()
        regs = intel.regions()
        self.assertIn("japan", regs)
        import taxonomy
        for r in regs.values():
            ids = [s["id"] for s in r["sources"]]
            self.assertEqual(len(ids), len(set(ids)), r["id"])
            for s in r["sources"]:
                self.assertTrue(s["url"].startswith("https://"), s["id"])
                self.assertTrue(s.get("terms"), s["id"])   # 規約を確かめた跡
                self.assertTrue(s["cats"] == "*" or set(s["cats"]) <= set(taxonomy.SECTIONS), s["id"])


if __name__ == "__main__":
    unittest.main()
