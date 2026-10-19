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

    def test_random_code_suffix_is_spam(self):
        """Unisba Media（被黑的印尼大学网站，2026-10）：随便一条新闻的标题 + 作品名 + 10 位随机码。真实的 47 条标题的写法。"""
        mando = {"name": "The Mandalorian", "type": "drama", "match": ["The Mandalorian"]}
        titles = ["#ぽかぽか #ぽかフェス #show_wa #向山毅 #MATSURI #シュネル #渡辺真 #昭和歌謡リバイバルプロジェクト #昭和歌謡 The Mandalorian (gQvzdvbtKG)",
                  "Bloom Energy Stock 2026: $305 Fair Value? The AI Power Boom Could Change Bloom Forever The Mandalorian And Grogu (sXJbLOTRQM)",
                  "ゼンゼロのスシローコラボを見て、とある違和感に気付いた【ゼンゼロ反応集】 Eva Lys (OSvayvh2D8)",
                  "『Vaundy One Man Live ARENA Tour “FUSION”』U-NEXTで独占配信中！ états-unis (WB4E8MlFBx)",
                  "渋谷パルコのジャンプショップ 池袋でチェンソーマンの映画 おでけけDay Hyeseong Kim (xzesW8gQyt)"]
        for t in titles:
            self.assertTrue(digest.is_spam(t), t)
        es = [entry(t, i) for i, t in enumerate(titles)]
        self.assertEqual(digest.filter_entries(es, mando, {}, set(), NOW), [])

    def test_spam_host_is_dropped_even_after_ai_cleans_the_title(self):
        """AI 編集は末尾の随機コードを削って報道にする（Vaundy の報道）：標題では見抜けないので、リンクの網域でも見る。"""
        self.assertTrue(digest.is_spam("10/9 『Vaundy One Man Live ARENA Tour “FUSION”』U-NEXTで独占配信中！",
                                       "https://media.unisba.ac.id/dc7dc9a9/76fb3431Oi0DOEwYOwQgFwE"))
        self.assertTrue(digest.is_spam("x", "https://sub.unisba.ac.id/a"))
        self.assertFalse(digest.is_spam("x", "https://notunisba.ac.id.example.com/a"))
        self.assertFalse(digest.is_spam("x", "https://www.yahoo.co.jp/a"))

    def test_spam_not_listed_as_pending(self):
        pairs = [(1, entry("Mandalorian trailer", 1)), (2, entry("どこかの動画 The Mandalorian (gQvzdvbtKG)", 2))]
        _, pending = digest.split_unedited(pairs, {"name": "The Mandalorian"})
        self.assertEqual([x["title"] for x in pending], ["Mandalorian trailer"])

    def test_normal_titles_ending_in_parentheses_are_kept(self):
        """末尾が括弧の普通の見出し（媒体名・語・数字）は垃圾ではない。"""
        for t in ["The Mandalorian & Grogu trailer lands (Reuters)", "ジェラピケ新作 (10月20日発売)", "Season 3 review (spoilers)",
                  "Marvel's new film (Deadline)", "The Mandalorian cast (Newsweekly)", "映画 (2026) 公開", "Dota 2 (BLASTSLAM8)"]:
            self.assertFalse(digest.is_spam(t), t)

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


class SpamNotCountedTest(unittest.TestCase):
    def test_heat_ignores_spam_entries(self):
        """垃圾页は話題度の「報道量」にも数えない（Unisba の 26 条が The Mandalorian の話題度を灌水していた）。"""
        import json
        import pathlib
        import tempfile
        import heat
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "2026-10-18.json"
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"date": "2026-10-18", "items": [{"name": "x", "entries": [
                    {"url": "https://a/1", "title": "Mandalorian trailer", "source": "IGN", "date": "2026-10-18T00:00:00+00:00"},
                    {"url": "https://a/2", "title": "どこかの動画 The Mandalorian (gQvzdvbtKG)", "source": "Unisba Media",
                     "date": "2026-10-18T00:00:00+00:00"}]}]}, f)
            entries, _, _ = heat.load_entries([p])
        self.assertEqual([e["url"] for e in entries["x"]], ["https://a/1"])
