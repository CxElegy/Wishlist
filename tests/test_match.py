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

    def test_data_uri_redirect_link_is_spam(self):
        self.assertTrue(digest.is_spam("x", "https://www.fctokyo.co.jp/r?&xml=data:video/mp4;base64,AAAA"))
        self.assertFalse(digest.is_spam("x", "https://example.com/a?u=1&v=2"))

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


    def test_render_drops_spam_from_stale_recommendations(self):
        """recommend.json が古い内容で書き戻されても、ページ生成の側で垃圾页は出さない。"""
        import render
        html = render._picks([
            {"title": "#ぽかぽか The Mandalorian (gQvzdvbtKG)", "url": "https://media.unisba.ac.id/1bf3fd14/x", "source": "Unisba Media",
             "date": "2026-10-19", "work": "The Mandalorian", "image": None, "because": "w", "kind": "board", "hits": []}],
            [{"name": "The Mandalorian"}])
        self.assertEqual(html, "")


ROOT = pathlib.Path(__file__).resolve().parent.parent


def real_item(name):
    """items.yaml にいま書いてある関注項（match・exclude の正規表現そのものを確かめる）。"""
    import yaml
    cfg = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    return cfg["settings"], next(i for i in cfg["items"] if i["name"] == name)


def keeps(name, titles, **kw):
    settings, item = real_item(name)
    es = [sources.Entry(title=t, url=f"https://example.com/{i}", source=kw.get("source", "媒体"), summary="",
                        published=NOW) for i, t in enumerate(titles)]
    return [e.title for e in es if digest.drop_reason(e, item, settings) is None]


class GenericMatchTest(unittest.TestCase):
    """数字・泛詞・部分一致の匹配词（2026-10-22 の検査 genericmatch：滑雪の 26/27・早割・CAPiTA、MMORPG 新作の MMO）。"""

    def test_ski_keeps_snow_news(self):
        titles = ["Best Ski Boots 2026/27: Our InTheSnow Verdicts",          # 26/27 ＋ ski
                  "Best Women's Ski Pants of 2026/27",
                  "八千穂高原スキー場、2026-27シーズンの早割リフト券を10月1日から販売開始",
                  "星野リゾート ネコマ マウンテンが2026-27シーズン券などを10月1日発売へ",   # シーズン券 ＋ ネコマ（スキー場の名前）
                  "【星野リゾート】福島県のスキー場ネコマ マウンテン、シーズン券＆早割リフト券の販売開始 - お得な「3日券・5日券」が新登場",
                  "POC Unveils New Winter 26/27 Ski Goggle and Apparel Collection",
                  "Capita Ultrafear Review", "The 2026 Capita DOA Review: Does the New Defenders of Awesome Still Rip?",
                  "Capita Super DOA Review: Is It Worth the Upgrade vs the Regular DOA?", "CAPiTA Mercury 2027 first look",
                  "Burton co-founder: The 'unf---able truths' that powered the global snowboarding brand 50 years"]
        self.assertEqual(keeps("滑雪", titles), titles)

    def test_ski_drops_number_and_generic_words(self):
        titles = ["What's new for winter 26/27 in Park City,",                       # 実際の標題（雪の語がないので 26/27 だけでは通らない）
                  "Portetta unveils expanded mountain experiences for winter 2026/27",
                  "鹿島アントラーズ、2026/27 J1 シーズンの日程発表",                  # 26/27 はサッカーにも
                  "COUNTDOWN JAPAN 26/27 第1弾出演者発表",
                  "England skipper confirmed for 2026/27 Ashes tour",                 # ski は単語だけ：skipper に当たらない
                  "Premier League 2026/27: new skipper named",
                  "【早割】お歳暮ギフト 2026 予約受付開始",                            # 早割はお歳暮にも
                  "マウンテンパーカー 早割セール開催",                                 # 服・化粧品・キャンプ用品の早割
                  "【早割】パウダーファンデーション福袋 予約開始",
                  "スノーピーク 早割キャンペーン",
                  "早割 skincare set 2026",
                  "Capita shares fall after NHS contract loss", "Capita plc wins £100m contract",   # 英国の Capita plc
                  "Vernal Capital、新ファンドを設立", "Asu Capital Partners invests in AI startup",   # CAPiTA の部分一致
                  "GDP per capita rises in Japan",
                  "Tim Burton's new film opens in Tokyo",                                # Burton は雪の語と一緒のときだけ
                  # 早割の相手の語に単独の「雪」「リフト」を書かない（化粧品・お菓子・雪まつりの早割）
                  "【早割】雪肌精 クリスマスコフレ2026 予約開始", "早割 リフトアップ美容液 福袋",
                  "さっぽろ雪まつり 早割ツアー 2027", "雪見だいふく 早割ギフト"]
        self.assertEqual(keeps("滑雪", titles), [])

    def test_ski_brand_words_next_to_kana(self):
        """Python の \\b はかな・漢字も単語の字：「CAPiTAの」「Burtonが」に当たるよう (?<![A-Za-z]) で区切る。"""
        titles = ["CAPiTAの2027モデルが発表", "BurtonがStep On新モデルを発表", "Burton Custom 2027 review",
                  "八千穂高原スキー場の早割リフト券", "skiシーズンの早割 リフト券"]
        self.assertEqual(keeps("滑雪", titles), titles)
        settings, item = real_item("滑雪")
        e = sources.Entry(title="Ride Benchwarmer vs Huck Knife Pro vs Burton Blossom", url="https://www.reddit.com/r/snowboarding/x",
                          source="Reddit", summary="", published=NOW)   # 実際の標題（inbox 10-12、要約は「aggressive park board…」）
        self.assertIsNone(digest.drop_reason(e, item, settings))

    def test_mmo_is_a_word(self):
        kept = ["솔: 인챈트부터 도깨비의세계까지, 모바일 MMO 대형 신작 흥행에 매출 반등",   # MMO の後に助詞・ハングルが続いても当たる
                "Discussion time: Do you think zone chats in MMOs are forces for good, or evil?",
                "「SteamはMMOなんだ」元Valve社員が語るゲイブの思想"]
        dropped = ["Lose Your Head as Hallows Wake Returns With New Surprises in Diablo Immortal",   # 実際の標題：iMMOrtal
                   "愛犬と泊まれる宿 pet-friendly accommodation in Hakone",                          # accoMMOdation
                   # Massively OP の周刊・雑談のコラム（単語の MMO があるので exclude で外す。実際の標題）
                   "MMO Week in Review: Welcome back to Atreia", "MMO Week in Review: RuneScape 4, Aion 2",
                   "The Daily Grind: Would you crowdfund an MMO now?", "The Daily Grind: How do you go about finding a guild in MMOs?",
                   "Make My MMO: Shroud of the Vibecoders"]
        self.assertEqual(keeps("MMORPG 新作", kept + dropped), kept)


class NotNewsTest(unittest.TestCase):
    """攻略 wiki・クラファン・試合データ・賭け予想・手办・値下げの商品頁（2026-10-22 の検査 notnews）。"""

    def test_exclude_hosts_by_link_url_and_google_site(self):
        settings, item = real_item("あつ森")
        title = "【あつ森】ゴールデントラウトの値段と釣り方・出現時間【あつまれどうぶつの森】"   # 実際の標題（2020 年の攻略頁）
        google = "https://news.google.com/rss/articles/CBMiXEFVX3lx"
        cases = [dict(url=google, link="https://gamewith.jp/atsumori/article/show/192278"),   # 出刊で還元した原文
                 dict(url="https://www.gamewith.jp/atsumori/1"),                               # 下位網域
                 dict(url=google, site="https://gamewith.jp")]                                 # 収集の時点（Google の <source url>）
        for kw in cases:
            e = sources.Entry(title=title, source="GameWith", published=NOW, **kw)
            self.assertEqual(digest.drop_reason(e, item, settings), "exclude_hosts", kw)
        e = sources.Entry(title=title, url="https://notgamewith.jp/a", source="x", published=NOW)
        self.assertIsNone(digest.drop_reason(e, item, settings))

    def test_wiki_hosts_drop_only_guide_pages(self):
        """攻略 wiki の網域（GameWith）は編集部のニュースも出す：網域まるごとではなく、攻略頁の標題の形だけ落とす（2026-10-22 の検査）。
        収集の時点は Google の跳转で道（/gamedb/…/articles/）がわからないので、標題で分ける。"""
        google = "https://news.google.com/rss/articles/x"
        news = [("绝区零", "『ゼンレスゾーンゼロ』Ver.3.3が10月21日(水)にリリース。S級エージェント「フィオニー」と「セヴェリアン」が登場！"),
                ("MMORPG 新作", "【CBTプレイレビュー】懐かしいMMORPGの手触りとフェローに乗って大空を駆ける楽しさ『Icarus Online』"),
                ("MMORPG 新作", "CBTプレイレビュー】懐かしいMMORPGの手触りとフェローに乗って大空を駆ける楽しさ『Icarus Online"),
                ("Astrae Oratio", "『アストラエ・オラティオ』先行プレイレビュー！魔法使いの少女たちが「決闘裁判」で争うノスタルジックな東京を舞台にした新伝奇魔法RPG"),
                ("MMORPG 新作", "『Icarus Online』の事前キャラクター作成が開始！モンスターを手なずけて大空を飛び回るMMORPG！"),
                ("MMORPG 新作", "『リネージュ クラシック』日本でのサービス開始が決定！2000年代初期に一世を風靡した大規模MMORPGが現代に復刻"),
                ("MMORPG 新作", "MMORPG『AION2』×ARグラス『XREAL』コラボキャンペーンが10月20日開始！公式Xと家電量販店で実施")]
        guide = [("あつ森", "【あつ森】ゴールデントラウトの値段と釣り方・出現時間【あつまれどうぶつの森】"),
                 ("あつ森", "【あつ森】アップデート最新情報【あつまれどうぶつの森】"),
                 ("绝区零", "【ゼンゼロ】クラレッタガチャは引くべき？【ゼンレスゾーンゼロ】"),
                 ("绝区零", "【ゼンレスゾーンゼロ】リセマラ当たりランキング【ゼンゼロ】"),
                 ("ぐでたま", "【コトダマン】ヨサリ&ぐでたまの評価とステータス"),
                 ("MMORPG 新作", "【2026年最新】スマホMMORPGのおすすめ無料ゲームアプリまとめ！人気の名作から最新作まで紹介【オンラインゲーム】")]
        for name, title in news + guide:
            settings, item = real_item(name)
            for kw in (dict(url=google, site="https://gamewith.jp"), dict(url="https://gamewith.jp/gamedb/7776/articles/64257")):
                e = sources.Entry(title=title, source="GameWith", published=NOW, **kw)
                want = "exclude_hosts" if (name, title) in guide else None
                self.assertEqual(digest.drop_reason(e, item, settings), want, title)

    def test_esports_news_site_kept_stream_pages_dropped(self):
        """escorenews は網域で落とさない（ニュースの欄もある）。試合の配信頁は dota2 の exclude「match stream」で落ちる。"""
        settings, item = real_item("dota2")
        cases = {"Dota 2 online peak breaks million players after release of Terror Trove, beating TI15 record": None,
                 'Korb3n: "Collapse will definitely return to Dota 2, don\'t worry"': None,
                 "XctN - XE, 16 十月 2026 - match stream, live broadcast - DL S30 - Dota 2": "exclude",
                 "TRE - XG, October 17, 2026 - match stream, live broadcast - BLAST Slam #9 - Dota 2": "exclude"}
        for title, want in cases.items():
            e = sources.Entry(title=title, url="https://news.google.com/x", site="https://escorenews.com", source="escorenews.com",
                              published=NOW)
            self.assertEqual(digest.drop_reason(e, item, settings), want, title)

    def test_crowdfunding_hosts_for_every_item(self):
        """クラファンはどの関注項でもニュースではない：settings 全体の exclude_hosts（猫用品だけでなくテニスにも来ていた）。"""
        cases = [("猫用品", "生後5ヶ月でFIPを発症した猫「ごま」を救いたいです", "https://readyfor.jp/projects/goma-fip-0905",
                  "ReadyFor(クラウドファンディング)"),
                 ("日本顶级网球赛事", "東北で硬式テニスを次世代へ。豪華景品で大会を盛り上げたい！", "https://camp-fire.jp/projects/1",
                  "CAMPFIRE (キャンプファイヤー)")]
        for name, title, link, source in cases:
            settings, item = real_item(name)
            e = sources.Entry(title=title, url="https://news.google.com/x", link=link, source=source, published=NOW)
            self.assertEqual(digest.drop_reason(e, item, settings), "exclude_hosts", name)

    def test_google_rss_keeps_source_site(self):
        xml = (b'<rss><channel><item><title>\xe3\x80\x90\xe3\x81\x82\xe3\x81\xa4\xe6\xa3\xae\xe3\x80\x91x - GameWith</title>'
               b'<link>https://news.google.com/rss/articles/abc</link><source url="https://gamewith.jp">GameWith</source>'
               b'</item></channel></rss>')
        e, = sources.rss_bytes(xml, "Google 新闻")
        self.assertEqual((e.source, e.site), ("GameWith", "https://gamewith.jp"))
        d = digest.entry_to_dict(1, e)
        self.assertEqual(d["site"], "https://gamewith.jp")   # inbox にも書く：link を還元する前の記事も audit-match・あとの段で網域を見られる
        self.assertEqual(digest.entry_from_dict(d).site, "https://gamewith.jp")
        self.assertNotIn("site", digest.entry_to_dict(1, sources.Entry(title="x", url="https://e.com", source="e", published=None)))

    def test_exclude_sources_prefix(self):
        settings, item = {"exclude_sources": ["YouTube"]}, {"name": "x", "match": ["Avengers"], "exclude_sources": ["note"]}
        def why(source):
            return digest.drop_reason(sources.Entry(title="Avengers news", url="https://e.com/1", source=source, published=NOW),
                                      item, settings)
        self.assertEqual(why("YouTube on MSN"), "exclude_sources")   # 実際の出典名（漫威电影に 2 日で 4 件）
        self.assertEqual(why("YouTube"), "exclude_sources")
        self.assertIsNone(why("YouTube · ILLIT"))                     # 公式チャンネルの RSS は関注項が選んだもの
        self.assertEqual(why("note"), "exclude_sources")
        self.assertIsNone(why("Notebookcheck"))
        self.assertIsNone(why("notes.jp"))
        self.assertEqual(why("note株式会社"), "exclude_sources")      # 続くのが ASCII の英数字のときだけ別の名前（漢字・かなは同じ媒体）
        self.assertEqual(why("YouTubeチャンネル"), "exclude_sources")
        self.assertEqual(digest.source_in("胡润百富网", ["胡润百富"]), True)

    def test_item_exclude_words(self):
        cases = {
            "日本顶级网球赛事": ["テニス - 木下グループジャパンオープンテニスチャンピオンシップス - アン リー vs. エマーソン ジョーンズ- 試合対戦データ",
                          "テニス - 木下グループジャパンオープンテニスチャンピオンシップス - カイラ デー vs. ソフィア ケニン- 試合スタッツ",
                          "【テニス速報】 木下グループジャパンオープンテニスチャンピオンシップス 第2日 内島 萌夏 vs 柴原 瑛菜"],
            "dota2": ["Team Yandex vs Iron Wing Prediction & Betting Tip | Dota 2",
                      "DB - XE, 31 十月 2026 - match stream, live broadcast - EPL World SEA S19 - Dota 2",
                      "Dota 2 hero tier list: Best meta picks in every position"],
            "漫威电影": ["Hot Toys Avengers: Doomsday Beast Deluxe 1/6 Scale Figure Includes a Battle-Damaged Sentinel Display Base",
                     "Marvel Legends Avengers Doomsday Wave 2 Preorder",
                     "Kelsey Grammer's Beast Revealed in New Collectible Figure Ahead of Avengers: Doomsday Release"],
            "gelato pique": ["最終値下げgelato pique オーガニックコットンスウェット セット（グリーン）ルームウェア・パジャマ"],
            "猫用品": ["生後5ヶ月でFIPを発症した保護子猫「ごま」を救いたいです"],
        }
        for name, titles in cases.items():
            self.assertEqual(keeps(name, titles), [], name)
        # 「figure」だけでは外さない：宣伝の「hooded figures」・「Figured Out」は漫威の記事
        keep = ["New Avengers: Doomsday promo features hooded figures we're yet to meet",
                "After 8 Years, Marvel Has Finally Figured Out What To Do With The Guardians Of The Galaxy",
                "Avengers: Doomsday 4K Deluxe Edition arrives in March",                          # deluxe だけでは外さない
                "Newly announced Avengers Doomsday Action Figures may reveal new information about the film (POSSIBLE SPOILERS)",
                "New Avengers: Doomsday Steve Rogers action figure hints Marvel is taking inspiration from DC Flash"]   # 中身を伝える帖子
        self.assertEqual(keeps("漫威电影", keep), keep)
        keep = ["伊藤あおい 惜敗でジャパンOP本戦入り逃す、フルセットの激闘も予選敗退＜女子テニス＞（tennis365.net）"]
        self.assertEqual(keeps("日本顶级网球赛事", keep), keep)


class AuditMatchTest(unittest.TestCase):
    def test_audit_counts_spam_sources_and_hosts(self):
        """audit-match の ✗ は収集と同じ drop_reason：垃圾・出典名・網域も数える（前は match と exclude だけで、10-19 の垃圾頁 8 件が「通る」だった）。"""
        import contextlib
        import io
        import json
        import tempfile
        from unittest import mock
        item = {"name": "あつ森", "match": ["あつ森"]}
        rows = [("【あつ森】島の評判(評価)星5の条件と上げ方", "GameWith", "https://gamewith.jp/atsumori/article/show/1"),
                ("【あつ森アニメ】名探偵ちーにゃ～冷蔵庫のプリン事件～ Shania Twain (XFO2W4OAyM)", "Unisba Media", "https://media.unisba.ac.id/a"),
                ("あつ森の新作の発表", "YouTube on MSN", "https://www.msn.com/a"),
                ("あつ森 アップデート 3.0 配信", "ファミ通", "https://www.famitsu.com/a")]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "2026-10-22.json"
            blind = {"title": "【あつ森】ゆうたろうの出現条件と家具一覧", "source": "GameWith", "url": "https://news.google.com/y", "date": None}
            p.write_text(json.dumps({"items": [{"name": "あつ森", "entries": [
                {"title": t, "source": s, "url": "https://news.google.com/x", "link": u, "date": None} for t, s, u in rows] + [blind]}]}))
            out = io.StringIO()
            with mock.patch.object(digest, "INBOX_DIR", pathlib.Path(d)), \
                    mock.patch.object(digest, "load_config", return_value=(
                        {"exclude_sources": ["YouTube"], "exclude_hosts": ["gamewith.jp"]}, [item])), \
                    contextlib.redirect_stdout(out):
                digest.audit_match()
        text = out.getvalue()
        self.assertIn("（5 条、✗ 3）", text)
        # link も site もない Google の跳转は網域を判定できない：件数と、同じ出典名で網域がわかった媒体の分を出す
        self.assertIn("網域を判定できない（Google の跳转で link・site がない）：1 件。うち出典名が除外の網域の媒体と同じもの 1 件（GameWith 1）", text)
        self.assertIn("✗ [exclude_hosts]", text)
        self.assertIn("✗ [垃圾]", text)
        self.assertIn("✗ [exclude_sources]", text)
        self.assertIn("   あつ森 アップデート 3.0 配信", text)


class ItemFieldsLimitTest(unittest.TestCase):
    def test_every_item_passes_settings_page_limits(self):
        """設定ページで直した欄は ITEM_FIELDS で確かめる：items.yaml にいま書いてあるものが通らないと、店長が 1 語直しただけで依頼が弾かれる
        （2026-10-22：漫威电影の exclude 35 語・猫用品の match 56 語が上限 30 を超えていた）。"""
        import yaml
        cfg = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
        for i in cfg["items"]:
            for k in ("keywords", "match", "exclude", "urgent_patterns", "subtitle", "priority", "notes"):
                if i.get(k):
                    try:
                        digest._clean_field(k, i[k])
                    except ValueError as err:
                        self.fail(f"{i['name']} の {k}：{err}")


class SetItemFieldsRoundTripTest(unittest.TestCase):
    def test_every_field_round_trips(self):
        """設定ページの依頼で keywords / match / exclude を同じ値で書き直しても、items.yaml が壊れず、ほかは変わらない。
        前は複数行の [ … ] の閉じ括弧の行が残って YAML が壊れ、take_item_requests が依頼を skipped にしていた（21 欄）。"""
        import yaml
        text = (ROOT / "items.yaml").read_text(encoding="utf-8")
        cfg = yaml.safe_load(text)
        for i in cfg["items"]:
            for k in ("keywords", "match", "exclude"):
                if not i.get(k):
                    continue
                for value in (digest._clean_field(k, i[k]), [*digest._clean_field(k, i[k])[:3], "新しい語"]):
                    got = yaml.safe_load(digest.set_item_fields(text, i["name"], {k: value}))
                    self.assertEqual(got["settings"], cfg["settings"])
                    for a, b in zip(got["items"], cfg["items"]):
                        self.assertEqual(a, {**b, k: value} if b["name"] == i["name"] else b, (i["name"], k))
                    self.assertEqual(len(got["items"]), len(cfg["items"]))


class DiscoverFilterTest(unittest.TestCase):
    def test_discover_uses_source_prefix_and_hosts(self):
        """「気になるかも？」の収集も出典名（前方一致）・exclude_hosts で外す（GameWith の攻略頁が候補に残っていた）。"""
        from unittest import mock
        NOW = dt.datetime.now(dt.timezone.utc)   # discover は「いまから lookback_days 日」で切るので、決め打ちの日付だと日が経つと落ちる
        found = [sources.Entry(title="『桃源暗鬼 Crimson Inferno』の配信日と事前登録情報！", url="https://news.google.com/a",
                               source="GameWith", site="https://gamewith.jp", published=NOW),
                 sources.Entry(title="新作アニメの映像", url="https://www.msn.com/a", source="YouTube on MSN", published=NOW),
                 sources.Entry(title="新しいボードゲームが発売", url="https://example.com/b", source="例の媒体", published=NOW)]
        settings = {"exclude_sources": ["YouTube"], "exclude_hosts": ["gamewith.jp"], "lookback_days": 7}
        item = {"name": "x", "match": ["x"], "similar": [{"query": "q", "label": "l"}]}
        import tempfile
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(digest, "DISCOVER_FILE", pathlib.Path(d) / "discover.json"), \
                mock.patch.object(digest, "load_config", return_value=(settings, [item])), \
                mock.patch.object(digest, "load_wishlist", return_value=[]), \
                mock.patch.object(digest, "probe_queries", return_value=[]), \
                mock.patch.object(digest.sources, "google_news", return_value=found):
            titles = [x["title"] for x in digest.discover(force=True)]
        self.assertEqual(titles, ["新しいボードゲームが発売"])
