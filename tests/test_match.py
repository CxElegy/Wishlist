"""关注项的 match：普通词忽略大小写和空格；「re:」开头的是正则，区分大小写。

    python -m unittest discover tests
"""
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import digest  # noqa: E402
import sources  # noqa: E402

# 剧名是常用英文词 from 的关注项（items.yaml 的 FROM 用的就是这种写法）
FROM = {"name": "FROM", "type": "show", "keywords": ["FROM season 5"],
        "match": ["Fromville", "'From'", r"re:\bFROM\b", r"re:^From (Season|season|S)\s?\d"]}
NOW = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)


def entry(title, n, source="媒体"):
    return sources.Entry(title=title, url=f"https://example.com/{n}", source=source, summary="", image="", published=NOW)


class MatchTest(unittest.TestCase):
    def kept(self, titles, source="媒体"):
        es = [entry(t, i, source) for i, t in enumerate(titles)]
        return [e.title for e in digest.filter_entries(es, FROM, {}, set(), NOW)]

    def test_show_titles_are_kept(self):
        titles = ["From Season 5: What to Expect in the Final Outing", "FROM Season 5 trailer drops",
                  "'From' is coming to Netflix US", "Theories about Fromville's origin"]
        self.assertEqual(self.kept(titles), titles)

    def test_ordinary_from_season_is_dropped(self):
        titles = ["Top 5 prospects from season 10 of Dana White's Contender Series",
                  "Episode 5 from Season Two of Documentary Series “Knife Edge”",
                  "why did hotd go downhill from season 2 itself"]
        self.assertEqual(self.kept(titles), [])


    def test_both_words_required(self):
        # 泛词（マグ）必须和主题词（星巴克）同时出现：用 (?=…)(?=…) 写在一条 re: 里
        item = {"name": "星巴克马克杯", "match": ["re:(?is)(?=.*(スタバ|starbucks))(?=.*(マグ|mug))"]}
        es = [entry("スタバの新マグカップは八角形", 1), entry("GODIVA×marimekkoの花柄マグカップ", 2),
              entry("Starbucks Singapore unveils mugs", 3)]
        kept = [e.title for e in digest.filter_entries(es, item, {}, set(), NOW)]
        self.assertEqual(kept, ["スタバの新マグカップは八角形", "Starbucks Singapore unveils mugs"])

    def test_match_hit_names_the_word(self):
        self.assertEqual(digest.match_hit(FROM, entry("Theories about Fromville", 1)), "Fromville")
        self.assertIsNone(digest.match_hit(FROM, entry("Top 5 prospects from season 10", 2)))


if __name__ == "__main__":
    unittest.main()


class SpamTest(unittest.TestCase):
    """被黑网站批量生成的色情 / 盗版「在线看」页面：标题塞作品名会命中 match，要整条丢掉。"""
    ZZZ = {"name": "绝区零", "type": "game", "match": ["绝区零", "ゼンゼロ"]}

    def kept(self, titles):
        es = [entry(t, i) for i, t in enumerate(titles)]
        return [e.title for e in digest.filter_entries(es, self.ZZZ, {}, set(), NOW)]

    def test_spam_pages_are_dropped(self):
        titles = ["绝区零艾莲被爆❌挤奶歪歪在线高清完整-绝区零艾莲被爆❌挤奶歪歪在线2026超清在线004 免费全集-爱看高清网",
                  "绝区零艾莲涩涩被❌-绝区零艾莲涩涩被❌2026最新版vv8.3.9 iphone版-2265安卓网",
                  "2026绝区零简被爆❌挤奶歪歪在线看-绝区零简被爆❌挤奶歪歪最新超清版39.847 全集版-爱看高清网"]
        self.assertEqual(self.kept(titles), [])

    def test_ad_stuffed_url_is_spam(self):
        """正规网站（新浪）的网址参数里塞着「伴游…添加微信」：标题是真的旧文章，也要丢。"""
        bad = ("https://finance.sina.cn/consume/shxf/2026-06-05/detail-iniaiyyn2826244.d.html?oid=%E8%8B%8F%E5%B7%9E"
               "%E5%A7%91%E8%8B%8F%E5%8C%BA%E4%BC%B4%E6%B8%B8%E6%A8%A1%E7%89%B9%EF%BC%88%E9%87%91%E7%89%8C%E7%BB%8F%E7%BA%AA"
               "%EF%BC%89%E6%B7%BB%E5%8A%A0%E5%BF%AB%E4%B9%90%E5%BE%AE%E4%BF%A1(88%E2%91%A1%E2%91%A26881)&vt=4")
        self.assertTrue(digest.is_spam("周杰伦北京演唱会抢票火爆，买演出门票别踩坑", bad))
        self.assertFalse(digest.is_spam("周杰伦北京演唱会抢票火爆，买演出门票别踩坑",
                                         "https://finance.sina.cn/consume/shxf/2026-06-05/detail-iniaiyyn2826244.d.html?vt=4"))
        self.assertFalse(digest.is_spam("微信公众号发布新功能", "https://news.qq.com/a/1.html"))   # 标题里的「微信」不算

    def test_real_news_and_collabs_are_kept(self):
        titles = ["绝区零3.3版本10月21日上线 新角色登场",
                  "【ゼンゼロ】ゼンゼロ×ローソン コラボ開催",
                  "绝区零 免费领取限定角色活动开启"]
        self.assertEqual(sorted(self.kept(titles)), sorted(titles))

    def test_blocked_source(self):
        e = sources.Entry(title="绝区零 新版本", url="https://hurun.net/news/1.sHtML", source="胡润百富",
                          summary="", image="", published=NOW)
        self.assertEqual(digest.filter_entries([e], self.ZZZ, {"exclude_sources": ["胡润百富"]}, set(), NOW), [])
