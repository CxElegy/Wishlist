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
        self.assertIn("あなたの投票：猫 +2", out)
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
        self.assertIn("入れ替え", out)
        self.assertIn("全 18 件", out)

    def test_explore_marked(self):
        out = render._picks([{**self.pick(1, 0), "explore": True}, self.pick(2, 1)], [])
        self.assertIn("気分転換 · 「b」が欲しいから", out)
        self.assertIn("data-new=1", out)

    def test_single_batch_has_no_button(self):
        out = render._picks([self.pick(i, 0) for i in range(3)], [])
        self.assertNotIn("入れ替え", out)
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


class StoryDedupe(unittest.TestCase):
    """「我会喜欢？」去重：同一件事（不同媒体、不同语言）只留一条。例子取自真实的推荐池。"""

    TITLES = [
        "《GTA 6》全新遊戲畫面曝光！六大廣播電台、Bad Bunny 等巨星加盟，首度加入 Podcast 功能",
        "Why GTA 6's Radio Stations Could Be More Than Just Background Music",
        "GTA 6 radio stations to be hosted by Robyn, Palms Trax, Bad Bunny, more",
        "星巴克「小熊維尼聯名周邊」10/19開賣，12款限定新品維尼馬克杯、冷水杯、收納袋、手機掛繩一次看！",
        "星巴克x小熊維尼100週年「蜂蜜罐馬克杯」12款聯名周邊超萌登場！ 星禮程密技「搶先購+無痛補奶現折20元」",
        "蜂巢馬克杯太可愛！星巴克小熊維尼聯名登場 蜂蜜罐娃包療癒感直接加倍",
        "Care BearsＸ星巴克聯名登場！馬克杯、冷水杯、不鏽鋼杯、托特包、吊飾到生活配件都有",
        "画像6 / 15＞ジェラート ピケ カフェに「スヌーピー」のクレープが登場！ジェラピケのルームウェア着た限定アート雑貨も",
        "ジェラート ピケ カフェにスヌーピーの“ひんやりクレープ”が登場！マシュマロのスヌーピーが眠るビジュアルがかわいすぎる",
        "美少女×武装艦の新作RPG『深鳶』が中国で配信開始！人気アニメ原作『鎮魂街』新作アクションもテスト間近―日本未上陸の注目ゲーム3選【2026年10月11日】｜Infoseekニュース",
        "『Farsight』眼科検診で見る“あの風景”に迷い込むサイコロジカルホラー。子供の視点ならではの不安や恐怖を描く。クローズドβテストが11月13日より開催",
    ]
    ITEMS = [{"name": "GTA 6", "keywords": ["GTA 6", "Grand Theft Auto VI"]}, {"name": "星巴克马克杯", "keywords": ["星巴克", "スタバ"]},
             {"name": "gelato pique", "keywords": ["gelato pique", "ジェラート ピケ"]}]

    def kept(self, titles):
        dd = digest.StoryDeduper(digest.generic_tokens(titles, [], self.ITEMS), titles)
        return [i for i, t in enumerate(titles) if not dd.same(t)]

    def test_same_story_kept_once_across_languages(self):
        # GTA 电台：中文 1 条 + 英文 2 条（中文那条和第 2 条英文只通过第 3 条相连）→ 留 1 条
        # 维尼联名 3 条 → 1 条；Care Bears 是另一件事；可丽饼 2 条 → 1 条；两款不同的游戏测试各留一条
        self.assertEqual(self.kept(self.TITLES), [0, 3, 6, 7, 9, 10])

    def test_order_does_not_matter_for_chains(self):
        titles = [self.TITLES[1], self.TITLES[0], self.TITLES[2]]   # 中文的排在中间也一样
        self.assertEqual(len(self.kept(titles)), 1)

    def test_numbers_and_gallery_prefix_ignored(self):
        self.assertNotIn("11", digest.story_tokens("クローズドβテストが11月13日より開催"))
        self.assertNotIn("画像", digest.story_tokens("画像6 / 15＞スヌーピーのクレープ"))
        self.assertIn("s27", digest.story_tokens("Galaxy S27 Ultra"))


class ExportPhotos(SyncNews):
    """拍照加愿望：新照片导出到 inbox/photos/，愿望清单里已有 photo 编号的标成 done。"""

    def test_upserts_all_once_then_only_changes(self):
        pass

    def test_failure_retries_next_time(self):
        pass

    def test_export_and_mark_done(self):
        import base64
        jpg = b"\xff\xd8\xff\xe0fakejpeg"
        img = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
        self.get_rows = [{"id": 7, "created_at": "2026-10-14T12:00:00Z", "status": "纠结", "note": "想要黑色", "image": img},
                         {"id": 6, "created_at": "2026-10-14T11:00:00Z", "status": "想要", "note": None, "image": "not-a-jpeg"}]
        self.wishes[:] = [{"name": "貓眼溫變馬克杯", "photo": 6}]
        with mock.patch.object(digest, "PHOTO_DIR", digest.INBOX_DIR / "photos"):
            digest.export_photos()
            folder = digest.INBOX_DIR / "photos"
            self.assertEqual((folder / "7.jpg").read_bytes(), jpg)
            meta = json.loads((folder / "7.json").read_text(encoding="utf-8"))
            self.assertEqual((meta["status"], meta["note"]), ("纠结", "想要黑色"))
            self.assertFalse((folder / "6.jpg").exists())       # 不是 jpeg 的不导出
        patches = [(path, body) for path, _, body in self.posts if body and "state" in body]
        self.assertIn(("/rest/v1/photo_inbox?id=eq.6", {"state": "done", "wish_name": "貓眼溫變馬克杯"}), patches)
        self.assertIn(("/rest/v1/photo_inbox?id=eq.7", {"state": "exported"}), patches)


class LikeHit(unittest.TestCase):
    def test_exclusions_and_word_boundaries(self):
        hit = digest._like_hit
        self.assertFalse(hit("リス|松鼠|-リスト", "やることリストを消化"))
        self.assertTrue(hit("リス|松鼠|-リスト", "リスくん柄ボトル やることリスト"))  # 排除的词去掉后还有リス
        self.assertFalse(hit("bunny|-bad bunny", "bad bunny joins gta 6 radio"))
        self.assertTrue(hit("bunny|-bad bunny", "a bunny mug"))
        self.assertFalse(hit("tour", "tourism in tokyo"))
        self.assertTrue(hit("tour", "world tour 2027"))
        self.assertTrue(hit("mug", "two mugs"))
        self.assertTrue(hit("moisturi", "moisturizing serum"))   # 长的英文词照样当前缀
        self.assertTrue(hit("マグ|-マグロ", "スタバのマグカップ"))
        self.assertFalse(hit("マグ|-マグロ", "マグロ丼"))


class Recommend(unittest.TestCase):
    """推荐来源：已经在版面里的不推荐；只命中摘要的不算；关注版面的其他消息；赞过的写理由、本身不再推荐。"""

    def run_recommend(self, inbox, report_urls, votes=(), probes=()):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "inbox").mkdir()
        (tmp / "reports").mkdir()
        (tmp / "inbox" / "2026-10-14.json").write_text(json.dumps({"date": "2026-10-14", "items": inbox}), encoding="utf-8")
        report = {"date": "2026-10-14", "no": 1, "items": [{"name": "GTA 6", "stories": [
            {"url": u, "headline": "版面上的标题"} for u in report_urls]}]}
        (tmp / "reports" / "2026-10-14.json").write_text(json.dumps(report), encoding="utf-8")
        wishes = [{"name": "黑猫杯", "likes": {"猫": ["猫|black cat"], "动物 / 角色造型": ["リス|-リスト", "bunny|-bad bunny"],
                                             "马克杯": ["マグ|mug"]}, "basics": ["马克杯"]}]
        with mock.patch.object(digest, "INBOX_DIR", tmp / "inbox"), \
             mock.patch.object(digest, "REPORTS_DIR", tmp / "reports"), \
             mock.patch.object(digest, "RECOMMEND_FILE", tmp / "rec.json"), \
             mock.patch.object(digest, "load_wishlist", return_value=wishes), \
             mock.patch.object(digest, "load_feedback", return_value=list(votes)), \
             mock.patch.object(digest, "load_config", return_value=({}, [])), \
             mock.patch.object(digest, "discover", return_value=list(probes)), \
             mock.patch.object(digest, "find_image", lambda c, r, u: c), \
             mock.patch.object(digest.sources, "resolve_url", lambda u: u):
            digest.recommend()
        return {p["url"]: p for p in json.loads((tmp / "rec.json").read_text(encoding="utf-8"))["picks"]}

    @staticmethod
    def entry(i, title, summary=""):
        return {"title": title, "url": f"https://e.com/{i}", "source": "S", "summary": summary, "date": "2026-10-14",
                "image": f"https://e.com/{i}.jpg"}

    def test_sources_and_reasons(self):
        inbox = [{"name": "猫用品", "entries": [
            self.entry(1, "黒猫のマグが新登場"),                               # 两个喜好 → wish
            self.entry(2, "猫砂盆の新製品が発売"),                              # 关注版面里只命中一个 → board
            self.entry(3, "猫のリスト", "")]},
                 {"name": "GTA 6", "entries": [
            self.entry(4, "GTA 6 新预告公开"),                                  # 已经在版面里
            self.entry(5, "GTA 6 电台阵容", "Bad Bunny 加盟，bunny mug 附赠"),   # 摘要命中不算 → board
            self.entry(6, "GTA 6 新地图泄露"),                                  # 赞过的 → 不再推荐
            {**self.entry(7, "Question about GTA 6"), "source": "r/GTA6", "url": "https://www.reddit.com/r/GTA6/x"}]}]
        votes = [{"url": "https://e.com/6", "vote": 1, "kind": "story", "title": "GTA 6 新地图泄露", "work": "GTA 6"}]
        picks = self.run_recommend(inbox, ["https://e.com/4"], votes)
        self.assertEqual(picks["https://e.com/1"]["kind"], "wish")
        self.assertEqual(picks["https://e.com/2"]["kind"], "board")
        self.assertEqual(picks["https://e.com/5"]["kind"], "board")
        self.assertNotIn("https://e.com/4", picks)   # 版面里已经有了
        self.assertNotIn("https://e.com/6", picks)   # 赞过 = 看过了
        self.assertNotIn("https://www.reddit.com/r/GTA6/x", picks)  # 网友的提问帖不当推荐
        self.assertEqual(picks["https://e.com/5"]["liked"], "GTA 6 新地图泄露")  # 同一个作品赞过
        out = render._picks(list(picks.values()), [])
        # 理由は POP の手書き：本文に蛍光ペン（mark）、👍 との関連は小さく（small）
        self.assertIn("<mark>フォロー中の「GTA 6」のほかのニュース</mark><small>👍した「GTA 6 新地图泄露」と関連</small>", out)
        self.assertIn("「黑猫杯」が欲しいから", out)

    def test_probe_entries_scored_by_title(self):
        probes = [{**self.entry(8, "Black cat bunny mug collection"), "item": "黑猫杯", "label": "猫", "probe": "黑猫杯"},
                  {**self.entry(9, "Cat news today"), "item": "黑猫杯", "label": "猫", "probe": "黑猫杯"}]
        picks = self.run_recommend([], [], probes=probes)
        self.assertEqual(picks["https://e.com/8"]["kind"], "wish")
        self.assertNotIn("https://e.com/9", picks)   # 只命中一个喜好（2 分），不够分


class Discover(unittest.TestCase):
    def test_random_seed_changes_queries(self):
        wishes = [{"name": "黑猫杯", "likes": {"猫": ["猫|black cat"], "动物 / 角色造型": ["リス|-リスト", "Snoopy|スヌーピー"],
                                             "马克杯": ["マグ|mug"]}, "basics": ["马克杯"]}]
        import random
        with mock.patch.object(digest, "load_wishlist", return_value=wishes):
            runs = [[q["query"] for q in digest.probe_queries(random.Random(seed), {})] for seed in range(6)]
            again = [q["query"] for q in digest.probe_queries(random.Random(0), {})]
        self.assertEqual(again, runs[0])                       # 同一个种子可以复现
        self.assertGreater(len({tuple(r) for r in runs}), 1)   # 不同种子搜的词不一样
        for r in runs:
            self.assertFalse(any(q.startswith("-") or " -" in q for q in r))  # 排除词不拿去搜
            self.assertFalse(any(q.split()[0] in ("マグ", "mug") for q in r))  # 基本属性不单独搜
        self.assertEqual(digest._lang_of("スヌーピー"), "ja-JP")
        self.assertEqual(digest._lang_of("black cat"), "en-US")


class ShuffleButtons(unittest.TestCase):
    def test_back_and_next(self):
        picks = [{"title": f"t{i}", "url": f"https://e/{i}", "source": "S", "date": "2026-10-12", "work": "w",
                  "image": None, "because": "b", "hits": [], "kind": "wish", "batch": i // 5} for i in range(12)]
        out = render._picks(picks, [])
        self.assertIn('class="shuffle back"', out)
        self.assertIn("前へ", out)
        self.assertIn("wishlist-seen-v2", out)
