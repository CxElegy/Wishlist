"""scripts/images.py 的测试：用本地 HTTP 服务器模拟各种网站，不访问外网。

    python -m unittest discover tests
"""

import datetime as dt
import io
import json
import os
import pathlib
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

from PIL import Image  # noqa: E402

import digest  # noqa: E402
import images  # noqa: E402

images.SCRAPLING = False   # 単体テストは外のネットに出ない（scrapling の取り直しは tests/test_scrape.py でにせの返事で確かめる）
import sources  # noqa: E402


def jpeg(w, h):
    """带图案的假照片（纯色块会被当成空白图，见 images.blank）。"""
    from PIL import ImageDraw
    im = Image.new("RGB", (w, h), (200, 80, 40))
    ImageDraw.Draw(im).rectangle([w // 4, h // 4, w * 3 // 4, h * 3 // 4], fill=(30, 60, 160))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def blank_jpeg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 255, 255)).save(buf, "JPEG")
    return buf.getvalue()


BIG = jpeg(640, 400)
SMALL = jpeg(120, 80)
_real_sleep = time.sleep  # 测试里把 time.sleep 换成空操作（跳过重试等待），服务器的“慢响应”要用真的
HITS = {}       # 路径 → 被请求的次数
REFERERS = []   # 收到的 Referer 头（应该一直是空的）


def png(side):
    buf = io.BytesIO()
    Image.new("RGB", (side, side), (40, 80, 200)).save(buf, "PNG")
    return buf.getvalue()


def html_page(head="", body=""):
    return f"<html><head>{head}</head><body>{body}</body></html>".encode()


ROUTES = {
    # 图片
    "/big.jpg": (200, "image/jpeg", BIG),
    "/big2.jpg": (200, "image/jpeg", jpeg(800, 450)),
    "/mislabeled.jpg": (200, "application/octet-stream", BIG),
    "/small.jpg": (200, "image/jpeg", SMALL),
    "/fake.jpg": (200, "image/jpeg", html_page(body="not an image")),
    "/forbidden.jpg": (403, "text/html", b"Forbidden"),
    "/huge.jpg": (200, "image/jpeg", jpeg(2000, 2000)),
    "/blank.jpg": (200, "image/jpeg", blank_jpeg(800, 450)),
    # 网页
    "/og.html": (200, "text/html", html_page('<meta property="og:image" content="/big.jpg">')),
    "/og-reversed.html": (200, "text/html", html_page('<meta content="/big2.jpg" name="twitter:image">')),
    "/jsonld.html": (200, "text/html", html_page(
        '<script type="application/ld+json">' + json.dumps(
            {"@type": "NewsArticle", "publisher": {"logo": {"url": "/logo.png"}},
             "image": [{"@type": "ImageObject", "url": "/big2.jpg"}]}) + "</script>")),
    "/broken-og.html": (200, "text/html", html_page(
        '<meta property="og:image" content="/forbidden.jpg">',
        '<article><img src="/icon.png"><img src="/small.jpg"><img data-src="/big.jpg"></article>')),
    "/nothing.html": (200, "text/html", html_page(body="<p>text only</p>")),
    # 虎扑の視頻帖：og:image も本文の図もなく、<video poster> だけ（小さい既定アバターは除く）
    "/video.html": (200, "text/html", html_page(body='<img src="/small.png"><video src="/v.mp4" poster="/big.jpg"></video>')),
    "/icons.html": (200, "text/html", html_page(
        '<link rel="icon" href="/fav/tiny-site"><link rel="mask-icon" href="/mask.svg">'
        '<link rel="apple-touch-icon" href="/fav/site-180">')),
    "/blocked.html": (403, "text/html", b"<title>Attention Required! | Cloudflare</title>"),
    "/copy.html": (200, "text/html", html_page('<meta property="og:image" content="/big2.jpg">')),
    "/yt-article.html": (200, "text/html", html_page('<meta property="og:image" content="/big.jpg">')),
    "/gone.html": (410, "text/html", b"Gone"),
    "/small-og.html": (200, "text/html", html_page(
        '<meta property="og:image" content="/big.jpg">'
        '<script type="application/ld+json">{"image": ["/huge.jpg"]}</script>', '<article><img src="/big2.jpg"></article>')),
    "/hotlink.html": (200, "text/html", html_page('<meta property="og:image" content="/referer-only.jpg">')),
    "/edgeone.jpg": (567, "text/html", b"Access Restricted. Protected by Tencent Cloud EdgeOne"),
    "/msn-api/en-us/AA1": (200, "application/json", json.dumps(
        {"title": "t", "imageResources": [{"url": "/big2.jpg", "width": 800, "height": 450}]}).encode()),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        HITS[path] = HITS.get(path, 0) + 1
        if self.headers.get("Referer"):
            REFERERS.append(self.headers["Referer"])
        if path == "/referer-only.jpg":  # 防盗链：只给带本站 Referer 的请求
            ok = (self.headers.get("Referer") or "").startswith("http://127.0.0.1")
            status, ctype, body = (200, "image/jpeg", BIG) if ok else (403, "text/plain", b"hotlink")
        elif path in ("/slow.jpg", "/slow.html"):
            _real_sleep(1.5)
            status, ctype, body = (200, "image/jpeg", BIG) if path.endswith(".jpg") else ROUTES["/og.html"]
        elif path.startswith("/fav/"):  # 假的网站图标服务：tiny- 开头的域名只给 16px 地球图标
            status, ctype, body = 200, "image/png", png(16 if "tiny" in path else 64)
        elif path == "/flaky.jpg":  # 第一次 503，第二次成功
            status, ctype, body = (503, "text/plain", b"busy") if HITS[path] == 1 else (200, "image/jpeg", BIG)
        else:
            status, ctype, body = ROUTES.get(path, (404, "text/plain", b"not found"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # 超时 / 超大的测试里客户端会提前断开
            pass

    def log_message(self, *args):
        pass


def entry(title="Some news title about the event", url="", image="", source="Example News"):
    return sources.Entry(title=title, url=url, published=dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc),
                         source=source, image=image)


class ImagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        images.clear_cache()
        HITS.clear()
        REFERERS.clear()
        self.real_bing, self.real_resolve = sources.bing_news, sources.resolve_url
        # 测试里不访问外网：Google 跳转还原 / Bing / Reddit 都替换掉
        self.patches = [mock.patch.object(sources, "resolve_url", lambda u: u),
                        mock.patch.object(sources, "bing_news", lambda q: []),
                        mock.patch.object(sources, "google_news", lambda q, days, lang: []),
                        mock.patch.object(images, "TIMEOUT", 1),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def u(self, path):
        return self.base + path

    # ---------- check() ----------

    def test_valid_jpeg(self):
        self.assertEqual(images.check(self.u("/big.jpg")), (True, "640×400"))

    def test_mislabeled_content_type_is_judged_by_content(self):
        ok, _ = images.check(self.u("/mislabeled.jpg"))
        self.assertTrue(ok)

    def test_rejects_small(self):
        self.assertEqual(images.check(self.u("/small.jpg")), (False, "图片太小 120×80"))

    def test_rejects_html_disguised_as_image(self):
        ok, why = images.check(self.u("/fake.jpg"))
        self.assertFalse(ok)
        self.assertIn("不是图片", why)

    def test_site_default_images_are_generic(self):
        """網站自己的占位图（Samsung 官网的 default_image.png 等）不是这篇报道的图。"""
        import urllib.parse
        for u in ("https://news.samsung.com/global/wp-content/themes/newsroom/images/default_image.png",
                  "https://x.example/img/no_photo.jpg", "https://x.example/NowPrinting.png", "https://x.example/a/blank.gif"):
            self.assertTrue(images.GENERIC.search(urllib.parse.urlparse(u).path), u)
        self.assertFalse(images.GENERIC.search(urllib.parse.urlparse("https://x.example/photos/image_01.jpg").path))

    def test_rejects_blank_placeholder(self):
        """期限切れの図の代わりに返ってくる空白（白一色）は使わない。"""
        self.assertEqual(images.check(self.u("/blank.jpg")), (False, "空白图 800×450"))

    def test_expiring_urls(self):
        self.assertTrue(images.expiring("https://newsatcl-pctr.c.yimg.jp/t/amd-img/x-view.jpg?exp=10800"))
        self.assertTrue(images.expiring("https://s3.example/a.jpg?X-Amz-Expires=600&x=1"))
        self.assertFalse(images.expiring("https://a.example/export=1/a.jpg"))

    def test_rejects_403(self):
        self.assertEqual(images.check(self.u("/forbidden.jpg")), (False, "图片 HTTP 403"))

    def test_rejects_too_big(self):
        with mock.patch.object(images, "IMAGE_LIMIT", 10_000):
            ok, why = images.check(self.u("/huge.jpg"))
        self.assertFalse(ok)
        self.assertIn("超过", why)

    def test_timeout(self):
        with mock.patch.object(images, "TIMEOUT", 0.3):
            self.assertEqual(images.check(self.u("/slow.jpg")), (False, "图片 超时"))

    def test_retries_server_error_once(self):
        self.assertTrue(images.check(self.u("/flaky.jpg"))[0])
        self.assertEqual(HITS["/flaky.jpg"], 2)

    def test_hotlink_protected_image_is_rejected_without_sending_referer(self):
        ok, why = images.check(self.u("/referer-only.jpg"))
        self.assertFalse(ok)
        self.assertEqual(why, "图片 HTTP 403")
        self.assertEqual(REFERERS, [], "不应该发送 Referer")

    def test_cache_avoids_second_download(self):
        images.check(self.u("/big.jpg"))
        images.check(self.u("/big.jpg"))
        self.assertEqual(HITS["/big.jpg"], 1)

    def test_invalid_url(self):
        self.assertEqual(images.check("data:image/png;base64,xx"), (False, "地址无效"))

    # ---------- 网页解析 ----------

    def test_og_both_attribute_orders(self):
        self.assertEqual(images.page(self.u("/og.html")).og, [self.u("/big.jpg")])
        self.assertEqual(images.page(self.u("/og-reversed.html")).og, [self.u("/big2.jpg")])

    def test_jsonld_image(self):
        p = images.page(self.u("/jsonld.html"))
        self.assertEqual(p.og, [])
        self.assertIn(self.u("/big2.jpg"), p.jsonld)

    def test_blocked_page_reason(self):
        p = images.page(self.u("/blocked.html"))
        self.assertFalse(p.ok)
        self.assertIn("防机器人", p.reason)
        self.assertIn("403", p.reason)

    # ---------- pick() ----------

    def test_ai_choice_kept_when_valid(self):
        res = images.pick(self.u("/big2.jpg"), [entry(url=self.u("/og.html"))], self.u("/og.html"))
        self.assertEqual((res.image, res.source), (self.u("/big2.jpg"), "AI 挑选"))

    def test_invalid_ai_choice_falls_back_to_og(self):
        res = images.pick(self.u("/forbidden.jpg"), [entry(url=self.u("/og.html"))], self.u("/og.html"))
        self.assertEqual((res.image, res.source), (self.u("/big.jpg"), "og:image"))
        self.assertEqual(res.trace[0], ("AI 挑选", self.u("/forbidden.jpg"), "图片 HTTP 403"))

    def test_entry_image_before_page(self):
        res = images.pick(None, [entry(url=self.u("/og.html"), image=self.u("/mislabeled.jpg"))], self.u("/og.html"))
        self.assertEqual(res.source, "条目自带")
        self.assertNotIn("/og.html", HITS)  # 条目自带图可用就不再读原文

    def test_jsonld_when_no_og(self):
        res = images.pick(None, [entry(url=self.u("/jsonld.html"))], self.u("/jsonld.html"))
        self.assertEqual((res.image, res.source), (self.u("/big2.jpg"), "JSON-LD"))

    def test_broken_og_falls_back_to_body_image(self):
        res = images.pick(None, [entry(url=self.u("/broken-og.html"))], self.u("/broken-og.html"))
        self.assertEqual((res.image, res.source), (self.u("/big.jpg"), "正文图"))
        self.assertEqual([r for _, _, r in res.trace], ["图片 HTTP 403", "图片太小 120×80", "OK"])
        self.assertNotIn(self.u("/icon.png"), [u for _, u, _ in res.trace])  # 图标被跳过

    def test_video_poster_when_no_og(self):
        self.assertEqual(images.page(self.u("/video.html")).poster, [self.u("/big.jpg")])
        res = images.pick(None, [entry(url=self.u("/video.html"))], self.u("/video.html"))
        self.assertEqual((res.image, res.source), (self.u("/big.jpg"), "视频封面"))

    def test_second_ref_page_used(self):
        refs = [entry(url=self.u("/nothing.html")), entry(url=self.u("/og.html"))]
        res = images.pick(None, refs, self.u("/nothing.html"))
        self.assertEqual(res.source, "og:image（其它来源）")

    def test_syndicated_copy_with_source(self):
        title = "八千穂高原スキー場 シーズン前に購入する事で大変お得な早割チケット10月より販売開始"
        copy = entry(title=title + "！", url=self.u("/copy.html"))
        other = entry(title="全く別の記事のタイトルです、スキー場とは関係ない", url=self.u("/og.html"))
        with mock.patch.object(sources, "bing_news", lambda q: [other, copy]):
            res = images.pick(None, [entry(title=title, url=self.u("/blocked.html"))], self.u("/blocked.html"))
        self.assertEqual(res.image, self.u("/big2.jpg"))
        self.assertEqual(res.source, "转载 127.0.0.1:%d" % self.server.server_port)
        self.assertNotIn("/og.html", HITS)  # 标题不像的不算转载
        self.assertIn("原文 HTTP 403（防机器人：Attention Required）", res.notes)

    def test_same_article_needs_whole_title_similar(self):
        """转载要两个标题整体相近：短标题刚好落在长标题里的不算（FROM 配上了《黑袍纠察队》的图）。"""
        self.assertFalse(images.same_article(
            "From Season 5 ending…", "'The Boys' season 5 ending explained: what happens to Homelander and Butcher"))
        self.assertFalse(images.same_article(
            "that damn apollo", "Margaret Hamilton, who led a software team for NASA's Apollo program, dies at 90"))
        self.assertTrue(images.same_article(  # 全角半角不同、末尾带媒体名的，照样算同一篇
            "【信州 北八ヶ岳標高 1830ｍ：八千穂高原スキー場】シーズン前に購入する事で大変お得な「早割チケット」10月より販売開始！",
            "【信州 北八ヶ岳標高 1830m：八千穂高原スキー場】シーズン前に購入する事で大変お得な「早割チケット」10月より販売開始 - 時事ドットコム"))

    def test_reddit_search_post_never_uses_syndication(self):
        """全站搜索来的 Reddit 帖子（来源名是 Reddit，不是 r/xxx）也不找转载。"""
        title = "From Season 5 ending explained by fans of the series"
        called = []
        with mock.patch.object(sources, "bing_news", lambda q: called.append(q) or [entry(title=title, url=self.u("/copy.html"))]), \
                mock.patch.object(sources, "_reddit_get", lambda path, params: (False, b"<feed/>")):
            res = images.pick(None, [entry(title=title, url="https://www.reddit.com/r/FromSeries/comments/x/y/", source="Reddit")],
                              "https://www.reddit.com/r/FromSeries/comments/x/y/")
        self.assertIsNone(res.image)
        self.assertEqual(called, [])

    def test_old_syndicated_image_on_reddit_post_dropped(self):
        """以前给 Reddit 帖子找来的「转载图」写回了 inbox：不再当条目自带图用。"""
        e = entry(url="https://www.reddit.com/r/FromSeries/comments/x/y/", source="Reddit", image=self.u("/big.jpg"))
        e.image_via = "转载 www.yahoo.com"
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, b"<feed/>")):
            res = images.pick(None, [e], e.url)
        self.assertIsNone(res.image)
        e.image_via = ""  # 收集时 Reddit 自带的预览图照常用
        images.clear_cache()
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, b"<feed/>")):
            self.assertEqual(images.pick(None, [e], e.url).source, "条目自带")

    def test_reddit_search_post_must_name_item_in_title(self):
        """Reddit 全站搜索的帖子：匹配词要在标题里，正文里随口一句「from Season 5」不算。"""
        now = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
        item = {"name": "FROM", "match": ["From Season 5", "Fromville"]}
        noise = entry(title="that damn apollo", url="https://www.reddit.com/r/RHOA/comments/1/a/", source="Reddit")
        noise.summary, noise.published = "I am watching a clip from Season 5 reunion", now
        real = entry(title="From Season 5 ending…", url="https://www.reddit.com/r/FromSeries/comments/2/b/", source="Reddit")
        real.published = now
        news = entry(title="MGM+ renews the horror series", url="https://news.example/a", source="Variety")
        news.summary, news.published = "From Season 5 will be the last", now
        got = digest.filter_entries([noise, real, news], item, {}, set(), now)
        self.assertEqual([e.title for e in got], ["MGM+ renews the horror series", "From Season 5 ending…"])

    def test_fallback_treats_reddit_search_posts_as_reddit(self):
        """关键词编排：全站搜索来的 Reddit 帖子和版块帖子一样，要命中重点词才上版面，也不排在媒体报道前面。"""
        item = {"name": "FROM", "priority_keywords": ["Season 5"]}
        chat = entry(title="Season 11 is going to be the one", url="https://www.reddit.com/r/marvelrivals/comments/1/a/", source="Reddit")
        post = entry(title="From Season 5 ending", url="https://www.reddit.com/r/FromSeries/comments/2/b/", source="Reddit")
        picked = digest.fallback_stories([chat, post], item)
        self.assertEqual([p["refs"] for p in picked], [[2]])
        self.assertTrue(sources.is_reddit(chat))
        self.assertTrue(sources.is_reddit(entry(url="https://www.reddit.com/r/x/comments/1/", source="Google")))
        self.assertFalse(sources.is_reddit(entry(url="https://news.example/a", source="Variety")))

    def test_syndicated_copy_is_checked(self):
        title = "八千穂高原スキー場 シーズン前に購入する事で大変お得な早割チケット10月より販売開始"
        bad = entry(title=title, url=self.u("/broken-og.html"))
        bad.image = self.u("/small.jpg")
        with mock.patch.object(sources, "bing_news", lambda q: [bad]), mock.patch.object(images, "BODY_IMAGES", 0):
            res = images.pick(None, [entry(title=title, url=self.u("/nothing.html"))], self.u("/nothing.html"))
        self.assertIsNone(res.image)  # 转载的图也要通过检查：一张太小、一张 403
        self.assertIn("图片太小 120×80", res.reason)
        self.assertIn("图片 HTTP 403", res.reason)

    def test_nothing_found_reason(self):
        res = images.pick(None, [entry(url=self.u("/nothing.html"))], self.u("/nothing.html"))
        self.assertIsNone(res.image)
        self.assertIn("原文没有图片元数据", res.reason)
        self.assertEqual(res.category, "无图：原文没有图")

    def test_max_checks(self):
        refs = [entry(url=self.u("/nothing.html"), image=self.u("/small.jpg")),
                entry(url=self.u("/nothing.html"), image=self.u("/forbidden.jpg")),
                entry(url=self.u("/nothing.html"), image=self.u("/fake.jpg"))]
        res = images.pick(None, refs, self.u("/nothing.html"), max_checks=2)
        self.assertEqual(len(res.trace), 2)
        self.assertIn("已检查 2 张，停止", res.notes)

    # ---------- 失败原因分类（日志和汇总要能区分） ----------

    def category_of(self, page_path, image=""):
        refs = [entry(url=self.u(page_path), image=self.u(image) if image else "")]
        return images.pick(None, refs, self.u(page_path))

    def test_categories_are_distinct(self):
        cases = {
            "/missing.html": "无图：原文 HTTP 错误",
            "/blocked.html": "无图：原文 HTTP 错误（防机器人）",
            "/nothing.html": "无图：原文没有图",
        }
        for path, want in cases.items():
            with self.subTest(path=path):
                self.assertEqual(self.category_of(path).category, want)
        image_cases = {
            "/forbidden.jpg": "无图：候选图 HTTP 错误",
            "/fake.jpg": "无图：候选图格式错误",
            "/small.jpg": "无图：候选图尺寸不合格",
            "/huge.jpg": "无图：候选图过大",
        }
        for img, want in image_cases.items():
            images.clear_cache()
            with self.subTest(image=img), mock.patch.object(images, "IMAGE_LIMIT", 10_000):
                self.assertEqual(self.category_of("/nothing.html", img).category, want)

    def test_timeout_categories(self):
        with mock.patch.object(images, "TIMEOUT", 0.3):
            self.assertEqual(self.category_of("/slow.html").category, "无图：原文超时")
            images.clear_cache()
            res = self.category_of("/nothing.html", "/slow.jpg")
        self.assertEqual(res.category, "无图：候选图超时")
        self.assertIn("图片 超时", res.reason)

    def test_network_error_category(self):
        res = images.pick(None, [entry(url="http://127.0.0.1:1/x.html")], "http://127.0.0.1:1/x.html")
        self.assertEqual(res.category, "无图：原文网络错误")

    def test_unresolved_google_link(self):
        res = images.pick(None, [entry(url="https://news.google.com/rss/articles/x")], "https://news.google.com/rss/articles/x")
        self.assertEqual(res.category, "无图：原文链接未还原")

    def test_log_line_and_summary(self):
        ok = images.pick(None, [entry(url=self.u("/broken-og.html"))], self.u("/broken-og.html"))
        images.clear_cache()
        bad = self.category_of("/nothing.html", "/small.jpg")
        self.assertEqual(images.log_line("项", "标题", ok), "  [配图] 项 | 标题 | 正文图（前 2 张不合格）")
        self.assertEqual(images.log_line("项", "标题", bad),
                         "  [配图] 项 | 标题 | 无图：原文没有图片元数据，正文也没有图；Bing / Google 新闻都没有找到带图的同一篇转载；图片太小 120×80")
        stats = images.Stats()
        stats.add(ok), stats.add(bad), stats.add(bad, fallback_cover=True)
        self.assertEqual(stats.summary(), "配图汇总：共 3 条，有图 1 条 · 有图：正文图 1 · 无图：候选图尺寸不合格 1 · 无图→作品封面 1")

    # ---------- Reddit ----------

    RSS = (b'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
           b'<content type="html">&lt;span&gt;&lt;a href=&quot;LINK&quot;&gt;[link]&lt;/a&gt;&lt;/span&gt;</content>'
           b'<link href="https://www.reddit.com/r/x/comments/abc/t/" /><title>t</title></entry></feed>')

    def test_reddit_rss_outbound_link(self):
        rss = self.RSS.replace(b"LINK", self.u("/yt-article.html").encode())
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, rss)):
            res = images.pick(None, [entry(url="https://www.reddit.com/r/x/comments/abc/t/", source="r/x")],
                              "https://www.reddit.com/r/x/comments/abc/t/")
        self.assertEqual(res.image, self.u("/big.jpg"))
        self.assertTrue(res.source.startswith("帖子外链 127.0.0.1"))

    def test_reddit_json_preview(self):
        data = json.dumps([{"data": {"children": [{"data": {
            "preview": {"images": [{"source": {"url": self.u("/big2.jpg").replace("?", "&amp;")}}]}}}]}}]).encode()
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (True, data)):
            found, note = images.reddit_candidates("https://www.reddit.com/r/x/comments/abc/t/")
        self.assertEqual(found, [("Reddit 预览图", self.u("/big2.jpg"))])

    def test_reddit_rate_limited_reason(self):
        import urllib.error

        def limited(path, params):
            raise urllib.error.HTTPError("https://www.reddit.com", 429, "Too Many Requests", {}, None)
        with mock.patch.object(sources, "_reddit_get", limited), mock.patch.object(sources, "_reddit_token", None):
            res = images.pick(None, [entry(url="https://www.reddit.com/r/x/comments/abc/t/", source="r/x")],
                              "https://www.reddit.com/r/x/comments/abc/t/")
        self.assertIsNone(res.image)
        self.assertIn("Reddit HTTP 429（未配置 REDDIT_CLIENT_ID", res.reason)
        self.assertEqual(res.category, "无图：Reddit 请求失败")

    def test_reddit_skipped_after_rate_limit(self):
        import urllib.error
        calls = []

        def limited(path, params):
            calls.append(path)
            raise urllib.error.HTTPError("https://www.reddit.com", 429, "Too Many Requests", {}, None)
        with mock.patch.object(sources, "_reddit_get", limited), mock.patch.object(sources, "_reddit_token", None):
            images.reddit_candidates("https://www.reddit.com/r/x/comments/abc/t/")
            found, note = images.reddit_candidates("https://www.reddit.com/r/x/comments/def/u/")
        self.assertEqual(len(calls), 1)
        self.assertIn("已跳过后续 Reddit 请求", note)

    def test_time_budget(self):
        res = images.pick(None, [entry(url=self.u("/og.html"))], self.u("/og.html"), budget=-1)
        self.assertIsNone(res.image)
        self.assertEqual(res.trace, [])
        self.assertIn("找图超过 -1 秒，停止", res.notes)

    def test_ingest_reddit_rss_uses_outbound_image(self):
        """收集阶段：Reddit RSS 里没缩略图的帖子（剧透帖）用外链的预览图。"""
        rss = self.RSS.replace(b"LINK", self.u("/og.html").encode())
        with mock.patch.object(sources, "_reddit_get", lambda path, params: (False, rss)):
            got = sources.reddit_sub("x")
        self.assertEqual([(e.url, e.image) for e in got], [("https://www.reddit.com/r/x/comments/abc/t/", self.u("/big.jpg"))])

    def test_reddit_links_parse(self):
        rss = self.RSS.replace(b"LINK", b"https://youtube.com/playlist?list=PL1&amp;amp;si=x")
        self.assertEqual(sources.reddit_links(rss),
                         {"https://www.reddit.com/r/x/comments/abc/t/": "https://youtube.com/playlist?list=PL1&si=x"})

    # ---------- Bing 缩略图 / MSN / 转载 / 大陆网站 / 原文已删 ----------

    def test_bing_news_image_parsed(self):
        rss = (b'<?xml version="1.0" encoding="utf-8" ?><rss version="2.0" xmlns:News="https://www.bing.com/news/search?q=x">'
               b'<channel><item><title>Galaxy S27 news</title><link>https://example.com/a</link>'
               b'<News:Source>Forbes</News:Source><News:Image>http://www.bing.com/th?id=ONUT.abc&amp;pid=News</News:Image>'
               b'<News:ImageMaxWidth>1350</News:ImageMaxWidth></item>'
               b'<item><title>Small one</title><link>https://example.com/b</link>'
               b'<News:Image>http://www.bing.com/th?id=ONUT.def&amp;pid=News</News:Image><News:ImageMaxWidth>640</News:ImageMaxWidth>'
               b'</item></channel></rss>')
        got = sources.rss_bytes(rss, "Bing 新闻")
        self.assertEqual([e.image for e in got], ["https://www.bing.com/th?id=ONUT.abc&pid=News&w=1200",
                                                   "https://www.bing.com/th?id=ONUT.def&pid=News&w=640"])
        self.assertEqual(got[0].source, "Forbes")

    def test_bing_news_retries_random_empty_result(self):
        answers = [[], [entry(url="http://www.bing.com/news/apiclick.aspx?url=https%3a%2f%2fa.example%2f1")]]
        with mock.patch.object(sources, "rss", lambda url, source=None: answers.pop(0)):
            got = self.real_bing("x")
        self.assertEqual([e.url for e in got], ["https://a.example/1"])

    def test_msn_article_uses_msn_api(self):
        api = "https://assets.msn.com/content/view/v2/Detail/en-us/AA1"
        with mock.patch.object(images, "_fetch", lambda url, limit: images.Fetched(200, {}, ROUTES["/msn-api/en-us/AA1"][2])
                               if url == api else images.Fetched(error="不该请求 " + url)):
            p = images.page("https://www.msn.com/en-us/news/other/some-title/ar-AA1")
        self.assertEqual(p.og, ["https://www.msn.com/big2.jpg"])
        self.assertEqual(p.og_label, "MSN 接口")

    def test_msn_video_uses_thumbnail(self):
        """MSN の動画（vi-）は imageResources が空で、図は thumbnail（動画の表紙）にある（2026-10-17 漫威の版面で図が出なかった）。"""
        api = "https://assets.msn.com/content/view/v2/Detail/en-us/AA2"
        body = json.dumps({"type": "video", "imageResources": [],
                           "thumbnail": {"image": {"url": "https://img-s-msn-com.akamaized.net/x/AA3.img"}}}).encode()
        with mock.patch.object(images, "_fetch", lambda url, limit: images.Fetched(200, {}, body)
                               if url == api else images.Fetched(error="不该请求 " + url)):
            p = images.page("https://www.msn.com/en-us/entertainment/general/some-title/vi-AA2")
        self.assertEqual(p.og, ["https://img-s-msn-com.akamaized.net/x/AA3.img"])

    def test_bigger_preview_on_same_page_preferred(self):
        """og:image が小さい（長辺 < SHARP_LONG）とき、同じページの JSON-LD の大きい版を使う。本文の別の図には行かない。"""
        res = images.pick(None, [entry(url=self.u("/small-og.html"))], self.u("/small-og.html"))
        self.assertEqual((res.image, res.source), (self.u("/huge.jpg"), "JSON-LD"))

    def test_small_preview_kept_when_nothing_bigger(self):
        res = images.pick(None, [entry(url=self.u("/og.html"))], self.u("/og.html"))
        self.assertEqual((res.image, res.source), (self.u("/big.jpg"), "og:image"))

    def test_hotlinked_page_image_retried_with_page_as_referer(self):
        """防盗链（新浪 sinaimg）：ほかに図がないとき、原文ページを Referer にして 1 回だけ再試行し、本站保存の印をつける。"""
        page_url = self.u("/hotlink.html")
        res = images.pick(None, [entry(url=page_url)], page_url)
        self.assertEqual((res.image, res.source), (self.u("/referer-only.jpg"), "og:image" + images.SAVED))
        self.assertEqual(REFERERS, [page_url])  # Referer は図があったページそのもの

    def test_referer_not_sent_when_plain_image_works(self):
        images.pick(None, [entry(url=self.u("/og.html"))], self.u("/og.html"))
        self.assertEqual(REFERERS, [])

    def test_bing_thumbnail_of_the_original_itself_is_used(self):
        """原文挡机器人（Forbes captcha），Bing 搜回来的就是原文本身：不再读原文，但用它的 Bing 缩略图。"""
        title = "Android Circuit: S27 Ultra Specs, Honor's New Display, Alexa Tablets"
        same = entry(title=title, url=self.u("/blocked.html"), image=self.u("/big2.jpg"))
        with mock.patch.object(sources, "bing_news", lambda q: [same]):
            res = images.pick(None, [entry(title=title, url=self.u("/blocked.html"))], self.u("/blocked.html"))
        self.assertEqual((res.image, res.source), (self.u("/big2.jpg"), "Bing 缩略图"))
        self.assertEqual(HITS["/blocked.html"], 1)

    def test_google_news_finds_press_release_original(self):
        """原文挡机器人、Bing 没有：Google 新闻用标题前半句搜到新闻稿原出处（标题后半句措辞不同也算同一篇）。"""
        title = "「西日本最大級から、西日本最高峰へ。」オリンピアン・日本のスノーリゾートを牽引するトップリーダー皆川賢太郎が、JAM福"
        orig = entry(title="「西日本最大級から、西日本最高峰へ。」オリンピアン・日本のスノーリゾートを牽引するトップリーダー 皆川賢太郎が、勝山高原開発株式会社 副社長に就任",
                     url="https://news.google.com/rss/articles/PR", source="PR TIMES")
        queries = []

        def google(q, days, lang):
            queries.append((q, lang))
            return [orig]
        with mock.patch.object(sources, "google_news", google), \
                mock.patch.object(sources, "resolve_url", lambda u: self.u("/copy.html") if u.endswith("/PR") else u):
            res = images.pick(None, [entry(title=title, url=self.u("/blocked.html"))], self.u("/blocked.html"))
        self.assertEqual(queries, [(title[:30], ("ja", "JP", "JP:ja"))])
        self.assertEqual(res.image, self.u("/big2.jpg"))
        self.assertTrue(res.source.startswith("转载 127.0.0.1"))

    def test_foreign_copy_before_domestic_copy(self):
        title = "八千穂高原スキー場 シーズン前に購入する事で大変お得な早割チケット10月より販売開始"
        cn = entry(title=title, url="https://www.sohu.com/a/1", image=self.u("/big.jpg"))
        jp = entry(title=title, url=self.u("/copy.html"))
        real_page = images.page
        with mock.patch.object(sources, "bing_news", lambda q: [cn, jp]), \
                mock.patch.object(images, "page", lambda u: real_page(u) if "sohu" not in u else images.Page(u, True)):
            found, _ = images.syndicated_candidates(title, self.u("/nothing.html"))
        self.assertEqual([label for label, _ in found], ["转载 127.0.0.1:%d" % self.server.server_port, "转载 www.sohu.com（Bing 缩略图）"])

    def test_unverifiable_domestic_image_not_used(self):
        """大陆网站把海外服务器拦掉（EdgeOne 567）的图验证不了：不用（看网页的人不在大陆就打不开）。"""
        cn_img = "https://i.17173cdn.com/x.jpg"
        with mock.patch.object(images, "check", lambda u: (False, "图片 HTTP 567") if u == cn_img else (False, "图片太小 120×80")):
            res = images.pick(None, [entry(url=self.u("/nothing.html"), image=cn_img)], self.u("/nothing.html"))
        self.assertIsNone(res.image)

    def test_is_domestic(self):
        self.assertTrue(sources.is_domestic("https://news.17173.com/content/1.shtml"))
        self.assertTrue(sources.is_domestic("https://ent.sina.cn/x"))
        self.assertTrue(sources.is_domestic("https://news.google.com/rss/articles/x", "新浪网"))
        self.assertFalse(sources.is_domestic("https://news.google.com/rss/articles/x", "Forbes"))
        self.assertFalse(sources.is_domestic("https://www.msn.com/zh-cn/x", "一点资讯 on MSN"))
        self.assertFalse(sources.is_domestic("https://tw.news.yahoo.com/x"))
        self.assertFalse(sources.is_domestic("https://www.notchina.com/x"))

    def test_attach_media_prefers_foreign_ref_and_drops_deleted(self):
        entries = [entry(url="https://www.sohu.com/a/1", source="搜狐"), entry(url=self.u("/og.html")),
                   entry(url=self.u("/gone.html")), entry(url=self.u("/missing.html")), entry(url=self.u("/jsonld.html"))]
        stories = [{"headline": "国内外都报了", "refs": [1, 2]},
                   {"headline": "原文已删", "refs": [3, 4]},
                   {"headline": "第一个来源删了，换第二个", "refs": [3, 5]}]
        stats = images.Stats()
        with mock.patch("sys.stderr", io.StringIO()) as err:
            out = digest.attach_media(stories, entries, None, "测试项", stats)
        self.assertEqual([(s["headline"], s["url"]) for s in out],
                         [("国内外都报了", self.u("/og.html")), ("第一个来源删了，换第二个", self.u("/jsonld.html"))])
        self.assertNotIn("/sohu", "".join(HITS))
        self.assertIn("[配图] 测试项 | 原文已删 | 不出刊：原文已删", err.getvalue())
        self.assertIn("另有 1 条原文已删，不出刊", stats.summary())

    def test_collect_skips_mainland_unless_zh_cn(self):
        cn = entry(url="https://www.sohu.com/a/1", source="搜狐")
        hk = entry(url="https://www.hk01.com/x", source="香港01")
        sina = entry(url="https://news.google.com/rss/articles/x", source="新浪网")  # 繁体版也偶尔混进大陆网站
        gd = entry(url="https://www.163.com/a/1", source="163.com")   # GDELT から来る大陸の網站も同じく
        with mock.patch.object(sources, "google_news", lambda q, days, lang: [sina]), \
                mock.patch.object(sources, "bing_news", lambda q: [cn, hk]), \
                mock.patch.object(sources, "gdelt", lambda q, days, langs: [gd]):
            got = digest.collect({"name": "x", "use": ["google", "bing"], "news_langs": ["zh-TW"]}, {})
            self.assertEqual([e.source for e in got], ["香港01"])
            got = digest.collect({"name": "x", "use": ["google", "bing"], "news_langs": ["zh-CN"]}, {})
            self.assertEqual([e.source for e in got], ["新浪网", "搜狐", "香港01", "163.com"])

    def test_filter_entries_prefers_foreign_copy(self):
        now = dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)
        cn = entry(title="复联5 全球预售票房突破1亿美元 距上映还有两个多月", url="https://www.sohu.com/a/1", source="搜狐")
        cn.published = now  # 大陆网站那篇更新，也不收
        hk = entry(title="复联5 全球预售票房突破1亿美元！距上映还有两个多月", url="https://www.hk01.com/x", source="香港01")
        same_title_cn = entry(title="复联5 内地定档 12 月 16 日", url="https://news.google.com/rss/articles/a", source="新浪网")
        same_title_tw = entry(title="复联5 内地定档 12 月 16 日", url="https://news.google.com/rss/articles/b", source="Yahoo奇摩新聞")
        only_cn = entry(title="复联5 内地首映礼名单公布", url="https://www.sohu.com/a/2", source="搜狐")
        got = digest.filter_entries([cn, hk, same_title_cn, same_title_tw, only_cn], {"name": "复联5"}, {}, set(), now)
        self.assertEqual({e.source for e in got}, {"香港01", "Yahoo奇摩新聞", "搜狐"})
        self.assertIn(only_cn, got)  # 只有大陆网站报道的照样收

    def test_llm_sees_domestic_mark(self):
        text = digest.format_entries([entry(url="https://www.sohu.com/a/1", source="搜狐"), entry(url="https://a.example/1")])
        self.assertIn("搜狐（大陆网站）", text)
        self.assertNotIn("Example News（大陆网站）", text)

    def test_fallback_prefers_foreign_copy(self):
        cn = entry(title="复联5 内地定档 12 月 16 日", url="https://www.sohu.com/a/1", source="搜狐")
        tw = entry(title="复联5 内地定档 12 月 16 日！", url="https://tw.news.yahoo.com/x", source="Yahoo奇摩新聞")
        picked = digest.fallback_stories([cn, tw], {"name": "复联5", "type": "show"})
        self.assertEqual([p["refs"] for p in picked], [[2]])

    def test_render_pic_fallback_chain(self):
        """网页上图打不开时按顺序换备用图；没有自己的图就直接用第一张备用图；全都没有才是名字块。"""
        import render
        html = render._pic({"image": "https://a/1.jpg", "_fbs": ["https://c/cover.jpg", "https://a/2.jpg"], "_work": "x"})
        self.assertIn('src="https://a/1.jpg" data-fb="https://c/cover.jpg https://a/2.jpg"', html)
        html = render._pic({"image": None, "_fbs": ["https://c/cover.jpg"], "_work": "x"})
        self.assertIn('src="https://c/cover.jpg"', html)
        self.assertNotIn("data-fb", html)
        self.assertIn('class="pic none"', render._pic({"image": None, "_fbs": [], "_work": "x"}))
        self.assertIn('data-fb="https://c/cover.jpg"', render._pic({"image": "https://a/1.jpg", "_cover": "https://c/cover.jpg"}))

    def test_render_cover_once_and_never_other_story_images(self):
        """没自己图的报道：作品封面每个版面只用一次，其余显示名字块；不拿别的报道的图来顶（那是另一件事的图）。"""
        import render
        issue = {"date": "2026-10-12", "items": [{"name": "网球", "cover": "https://c/cover.jpg", "stories": [
            {"headline": "a", "url": "https://a/1", "image": None, "date": "2026-10-12"},
            {"headline": "b", "url": "https://a/2", "image": "https://a/2.jpg", "date": "2026-10-11"},
            {"headline": "c", "url": "https://a/3", "image": None, "date": "2026-10-10"}]}]}
        w = render.collect([issue])[0]
        self.assertEqual([x["_fbs"] for x in w["stories"]], [["https://c/cover.jpg"], ["https://c/cover.jpg"], []])
        issue["items"][0]["stories"][1]["image"] = "https://c/cover.jpg"  # 头条已经用了封面
        w = render.collect([issue])[0]
        self.assertEqual([x["_fbs"] for x in w["stories"]], [[], [], []])
        issue["items"][0]["cover"] = None
        w = render.collect([issue])[0]
        self.assertNotIn("https://a/2.jpg", sum((x["_fbs"] for x in w["stories"]), []))

    def test_render_imageless_story_shows_source_icon(self):
        """找不到图的报道：配图位置显示来源网站的图标和网站名；连来源都看不出（没还原的 Google 新闻跳转）的
        才进「其他消息」文字列表；头版头条只挑有真正配图的（来源图标不算）。"""
        import render
        issue = {"date": "2026-10-12", "items": [{"name": "网球", "cover": "https://c/cover.jpg", "section": "运动",
                                                   "theme": dict(digest.theme.DEFAULT), "facts": [], "stories": [
            {"headline": "有图", "url": "https://a/1", "image": "https://c/cover.jpg", "image_via": "作品封面", "date": "2026-10-12", "weight": "lead"},
            {"headline": "没图的消息", "url": "https://news.nicovideo.jp/watch/nw1", "image": None, "source": "ニコニコニュース",
             "source_icon": "https://icons.example/nico.png", "date": "2026-10-12", "weight": "hero"},
            {"headline": "以前的没图消息", "url": "https://www.powder.com/news/x", "image": None, "date": "2026-10-12"},
            {"headline": "看不出来源", "url": "https://news.google.com/rss/articles/x", "image": None, "date": "2026-10-12"}]}]}
        page = render.render([issue], order=["网球"])
        self.assertIn('<img class="ico" src="https://icons.example/nico.png"', page)
        self.assertIn('<span class="src">ニコニコニュース</span>', page)
        # 以前的报道没存图标：按域名用图标服务，网站名用域名
        self.assertIn(render.FAVICON_SERVICE.format(host="www.powder.com").replace("&", "&amp;"), page)
        self.assertIn('<span class="src">powder.com</span>', page)
        self.assertIn('<div class="brief"><h4>その他のニュース</h4>', page)
        self.assertIn('看不出来源</a></li>', page)
        self.assertNotIn('没图的消息</a></li>', page)
        self.assertRegex(page, r'<article class="top"[^>]*><a class="lk" href="https://a/1"')  # 没图的 hero 不上头条大图

    def test_render_icon_fallback_order(self):
        """兜底顺序：自己的图 → 作品封面 → 来源图标（存的 → 完整域名 → 主域名）→ 作品名封面块。"""
        import render
        svc = render.FAVICON_SERVICE
        # 有图：图标先不加载，排在 data-icons 里，图全打不开才换上
        html = render._pic({"image": "https://a/1.jpg", "_fbs": ["https://c/cover.jpg"], "url": "https://news.17173.com/a"})
        self.assertIn('<div class="pic">', html)
        self.assertIn('<img class="ico" data-icons="', html)
        self.assertNotIn('class="ico" src=', html)
        self.assertIn("p.classList.add(&#x27;icon&#x27;)", html)  # 图全打不开：换成来源图标
        # 没图：直接显示图标，完整域名在前、主域名在后（news.17173.com 有 32px，17173.com 只有 16px）
        html = render._pic({"image": None, "_fbs": [], "url": "https://news.17173.com/a", "_work": "MMO"})
        self.assertIn('class="pic icon"', html)
        full, base = svc.format(host="news.17173.com"), svc.format(host="17173.com")
        self.assertIn(f'src="{full}"'.replace("&", "&amp;"), html)
        self.assertIn(f'data-icons="{base}"'.replace("&", "&amp;"), html)
        self.assertIn('<span class="ph">MMO</span>', html)  # 图标都不行时换成作品名封面块
        self.assertIn("naturalWidth&lt;32", html)  # 16px 地球图标也当作不行
        # 出刊时存的图标排第一
        icons = render._icons({"url": "https://news.nicovideo.jp/a", "source_icon": "https://i/nico.png"})
        self.assertEqual(icons, ["https://i/nico.png", svc.format(host="news.nicovideo.jp"), svc.format(host="nicovideo.jp")])
        self.assertTrue(render._has_pic({"image": None, "_fbs": [], "url": "https://x.example/a"}))
        self.assertFalse(render._has_photo({"image": None, "_fbs": [], "url": "https://x.example/a"}))
        self.assertFalse(render._has_pic({"image": None, "_fbs": [], "url": "https://news.google.com/rss/articles/x"}))
        self.assertIn('class="pic none"', render._pic({"image": None, "_fbs": [], "_work": "x"}))  # 没有链接：名字块

    def test_front_board_index_falls_back_to_other_images_and_icon(self):
        """トップのジャンルの棚：この作品の最近の記事の写真を順に予備に、次に作品の表紙、最後に記事の来源アイコン。"""
        import render
        issue = {"date": "2026-10-12", "items": [{"name": "MMO", "cover": "https://c/cover.jpg", "section": "游戏",
                                                   "theme": dict(digest.theme.DEFAULT), "facts": [], "stories": [
            {"headline": "a", "url": "https://news.17173.com/a", "image": "http://insecure.example/a.jpg", "date": "2026-10-12"},
            {"headline": "b", "url": "https://b.example/b", "image": "https://b.example/b.jpg", "date": "2026-10-11"}]}]}
        page = render.render([issue], order=["MMO"])
        entry_html = page[page.index('<a class="tape" href="#'):]
        entry_html = entry_html[:entry_html.index("</a>")]
        self.assertIn('src="http://insecure.example/a.jpg" data-fb="https://b.example/b.jpg https://c/cover.jpg"', entry_html)
        self.assertIn("news.17173.com", entry_html)  # 图都打不开：第一条报道的来源图标

    # ---------- 来源图标 ----------

    def test_page_icons_largest_first_without_mask(self):
        p = images.page(self.u("/icons.html"))
        self.assertEqual(p.icons, [self.u("/fav/site-180"), self.u("/fav/tiny-site")])

    def test_source_icon_prefers_site_icon(self):
        self.assertEqual(images.source_icon(self.u("/icons.html")), self.u("/fav/site-180"))

    def test_source_icon_falls_back_to_icon_service(self):
        with mock.patch.object(images, "FAVICON_SERVICE", self.base + "/fav/{host}"):
            self.assertEqual(images.source_icon(self.u("/blocked.html")), self.base + "/fav/127.0.0.1")
        images.clear_cache()
        with mock.patch.object(images, "FAVICON_SERVICE", self.base + "/fav/tiny-{host}"):
            self.assertIsNone(images.source_icon(self.u("/blocked.html")))  # 只有 16px 的不要
        self.assertIsNone(images.source_icon("https://news.google.com/rss/articles/x"))

    def test_base_domain(self):
        self.assertEqual(images.base_domain("news.nicovideo.jp"), "nicovideo.jp")
        self.assertEqual(images.base_domain("news.yahoo.co.jp"), "yahoo.co.jp")
        self.assertEqual(images.base_domain("m.dcinside.com"), "dcinside.com")
        self.assertEqual(images.base_domain("www.sina.com.cn"), "sina.com.cn")

    def test_attach_media_records_source_and_icon(self):
        entries = [entry(url=self.u("/nothing.html"), source="Example News")]
        with mock.patch.object(images, "FAVICON_SERVICE", self.base + "/fav/{host}"), \
                mock.patch("sys.stderr", io.StringIO()) as err:
            out = digest.attach_media([{"headline": "第二条", "refs": [1]}], entries, None, "测试项")
        self.assertIsNone(out[0]["image"])
        self.assertEqual((out[0]["source"], out[0]["source_icon"]), ("Example News", self.base + "/fav/127.0.0.1"))
        self.assertIn("（显示来源图标）", err.getvalue())

    def test_generic_and_duplicate_images_skipped(self):
        refs = [entry(url=self.u("/og.html"), image="https://cdn.example.com/wp-content/uploads/2026/07/Logo.jpg")]
        with mock.patch.object(images, "check", lambda u: (True, "640×400")):
            res = images.pick(None, refs, self.u("/og.html"), avoid={self.u("/big.jpg")})
        self.assertIsNone(res.image)
        self.assertEqual([r for _, _, r in res.trace], ["网站 logo / 默认图", "和别的报道重复"])

    def test_resolved_link_persisted_in_inbox(self):
        e = entry(url="https://news.google.com/rss/articles/x")
        with mock.patch.object(sources, "resolve_url", lambda u: "https://real.example/a"):
            self.assertEqual(sources.entry_link(e), "https://real.example/a")
        d = digest.entry_to_dict(1, e)
        self.assertEqual(d["link"], "https://real.example/a")
        self.assertEqual(digest.entry_from_dict(d).link, "https://real.example/a")
        self.assertEqual(sources.entry_link(digest.entry_from_dict(d)), "https://real.example/a")  # 不用再问 Google

    def test_resolve_url_retries(self):
        calls = []
        with mock.patch.object(sources, "_resolve_once", lambda u: calls.append(u) or (u if len(calls) < 2 else "https://real/a")):
            self.assertEqual(self.real_resolve("https://news.google.com/rss/articles/retry"), "https://real/a")
        self.assertEqual(len(calls), 2)

    # ---------- digest.attach_media（旧功能不回归） ----------

    def test_attach_media_writes_back_and_falls_back_to_cover(self):
        # 別の出来事（タイトルに共通の語がない）：同一件事的别家报道としては使わない
        entries = [entry(title="Release date trailer revealed", url=self.u("/jsonld.html")),
                   entry(title="Studio interview about soundtrack", url=self.u("/nothing.html"))]
        stories = [{"headline": "头条（原文没图）", "refs": [2]}, {"headline": "第二条", "refs": [1]},
                   {"headline": "第三条（AI 挑了图）", "image": self.u("/big.jpg"), "refs": [2]}]
        stats = images.Stats()
        with mock.patch("sys.stderr", io.StringIO()) as err:
            out = digest.attach_media(stories, entries, "https://cover.example/c.jpg", "测试项", stats)
        self.assertEqual((out[0]["image"], out[0]["image_via"]), ("https://cover.example/c.jpg", "作品封面"))
        self.assertEqual((out[1]["image"], out[1]["image_via"]), (self.u("/big2.jpg"), "JSON-LD"))
        self.assertEqual((out[2]["image"], out[2]["image_via"]), (self.u("/big.jpg"), "AI 挑选"))
        self.assertEqual(out[1]["url"], self.u("/jsonld.html"))
        self.assertEqual(out[1]["date"], "2026-10-11")
        self.assertNotIn("refs", out[1])
        # 补到的图写回条目，AI 挑的图不写回
        self.assertEqual((entries[0].image, entries[0].image_via), (self.u("/big2.jpg"), "JSON-LD"))
        self.assertEqual(entries[1].image, "")
        log = err.getvalue()
        self.assertIn("[配图] 测试项 | 头条（原文没图） | 无图：原文没有图片元数据", log)
        self.assertIn("（用作品封面）", log)
        self.assertEqual(stats.counts["无图→作品封面"], 1)
        self.assertIn("有图 2 条", stats.summary())

    def test_blocked_original_uses_same_event_report_from_other_site(self):
        """原文が人機検証で止められても（ナタリー 405）、同じ出来事を報じた別のサイトの記事の図を使う。"""
        blocked = entry(title="人気画像5位は「Mrs. GREEN APPLEとジェラピケが初コラボ、グリベアモチーフ」より", url=self.u("/blocked.html"))
        other = entry(title="Mrs. GREEN APPLE×ジェラート ピケ初コラボ！グリベアのルームウェア", url=self.u("/og.html"))
        unrelated = entry(title="冬の新作ルームウェアが登場", url=self.u("/copy.html"))
        sib = digest.same_event({"name": "gelato pique", "keywords": ["ジェラピケ", "ジェラート ピケ"]}, [blocked], [blocked, other, unrelated])
        self.assertEqual([e.url for e in sib], [self.u("/og.html")])
        res = images.pick(None, [blocked], self.u("/blocked.html"), siblings=sib)
        self.assertEqual(res.image, self.u("/big.jpg"))
        self.assertTrue(res.source.startswith("同一件事的别家报道"))

    def test_quoted_original_title(self):
        self.assertEqual(images.quoted_title("人気画像5位は「Mrs. GREEN APPLEとジェラピケが初コラボ」より、小物。"),
                         "Mrs. GREEN APPLEとジェラピケが初コラボ")
        self.assertEqual(images.quoted_title("「短い」"), "")
        self.assertEqual(images.quoted_title("「タイトル全体が引用になっている見出しです」"), "")

    def test_405_waf_is_bot_wall(self):
        f = images.Fetched(405, {"x-amzn-waf-action": "captcha"}, b"<title>Human Verification</title>")
        self.assertIn("防机器人", images._http_reason(f, "原文"))

    def test_find_image_shim_for_recommend(self):
        """「我会喜欢？」推荐用的 digest.find_image 走同一套检查：坏图跳过，最后没图返回 None。"""
        self.assertEqual(digest.find_image(self.u("/forbidden.jpg"), [entry(url=self.u("/og.html"))], self.u("/og.html")),
                         self.u("/big.jpg"))
        self.assertIsNone(digest.find_image(None, [entry(url=self.u("/nothing.html"))], self.u("/nothing.html")))

    def test_written_back_image_keeps_source_next_run(self):
        d = digest.entry_to_dict(1, entry(url=self.u("/nothing.html"), image=self.u("/big2.jpg")))
        self.assertNotIn("image_via", d)  # 没补过图的条目，inbox 格式不变
        e = entry(url=self.u("/nothing.html"), image=self.u("/big2.jpg"))
        e.image_via = "转载 jiji.com"
        e2 = digest.entry_from_dict(digest.entry_to_dict(1, e))
        self.assertEqual(e2.image_via, "转载 jiji.com")
        with mock.patch("sys.stderr", io.StringIO()):
            out = digest.attach_media([{"headline": "x", "refs": [1]}], [e2], None)
        self.assertEqual(out[0]["image_via"], "转载 jiji.com")


class PublishTest(unittest.TestCase):
    """digest.publish 整体跑一遍（临时目录、不联网）：配图写回 inbox、头条封面回退、AI 挑的图、汇总日志。"""

    def test_publish_writes_back_and_logs(self):
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        for d in ("inbox", "reports", "state", "docs"):
            (tmp / d).mkdir()
        item = "テスト作品"
        e1 = digest.entry_to_dict(1, entry(title="第一条新闻标题", url="https://a.example/1"))
        e2 = digest.entry_to_dict(2, entry(title="第二条新闻标题", url="https://a.example/2"))
        inbox = {"date": "2026-10-11", "items": [{"name": item, "entries": [e1, e2], "facts": [], "cover": "https://c.example/cover.jpg"}]}
        (tmp / "inbox" / "2026-10-11.json").write_text(json.dumps(inbox, ensure_ascii=False))
        edits = {item: [{"headline": "头条", "weight": "lead", "refs": [1]},
                        {"headline": "AI 挑了图", "image": "https://ai.example/pick.jpg", "refs": [2]},
                        {"headline": "补到了图", "refs": [2]}], "_covered": {item: 2}}
        (tmp / "inbox" / "2026-10-11.edit.json").write_text(json.dumps(edits, ensure_ascii=False))

        def fake_pick(chosen, refs, url, avoid=(), siblings=(), **kw):
            if chosen:
                return images.Result(chosen, "AI 挑选", [("AI 挑选", chosen, "OK")])
            if url.endswith("/1"):
                return images.Result(None, "", [], ["原文 HTTP 403（防机器人：Cloudflare）"])
            return images.Result("https://copy.example/x.jpg", "转载 copy.example", [("转载 copy.example", "x", "OK")])

        patches = [mock.patch.object(digest, d.upper() + "_DIR", tmp / d) for d in ("inbox", "reports", "docs")] + [
            mock.patch.object(digest, "STATE_DIR", tmp / "state"), mock.patch.object(digest, "THEMES_FILE", tmp / "state" / "themes.json"),
            mock.patch.object(digest, "write_issue_markdown", lambda *a: None), mock.patch.object(images, "pick", fake_pick),
            mock.patch.object(digest.theme, "resolve", lambda *a: dict(digest.theme.DEFAULT)), mock.patch.object(sources, "resolve_url", lambda u: u),
            mock.patch.object(digest, "make_client", lambda: None), mock.patch.object(images, "gone", lambda u: False),
            # publish 最后会重算「我会喜欢？」：它写真实的 state/recommend.json，还会联网搜同类新品，测试里跳过
            mock.patch.object(digest, "recommend", lambda *a, **k: None),
            # 出刊のあとの後片付け（Reddit の再確認・配図の再探し・高清化）はそれぞれ別のテストで見る。ここでは本物の state/ を書かない
            mock.patch.object(digest, "prune_reddit", lambda *a, **k: False),
            mock.patch.object(digest, "retry_images", lambda *a, **k: 0),
            mock.patch.object(digest, "hd_images", lambda *a, **k: None),
            mock.patch.object(images, "source_icon", lambda u: "https://icons.example/a.png"),
            mock.patch.object(digest, "find_cover", lambda *a, **k: None)]  # 没新消息的项找封面会读作品官网
        for p in patches:
            p.start()
        try:
            with mock.patch("sys.stderr", io.StringIO()) as err:
                digest.publish()
        finally:
            for p in patches:
                p.stop()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        report = json.loads((tmp / "reports" / "2026-10-11.json").read_text())
        stories = next(b for b in report["items"] if b["name"] == item)["stories"]
        self.assertEqual([(s["headline"], s["image"], s["image_via"]) for s in stories], [
            ("头条", "https://c.example/cover.jpg", "作品封面"),
            ("AI 挑了图", "https://ai.example/pick.jpg", "AI 挑选"),
            ("补到了图", "https://copy.example/x.jpg", "转载 copy.example")])
        saved = json.loads((tmp / "inbox" / "2026-10-11.json").read_text())["items"][0]["entries"]
        self.assertEqual(stories[0]["source_icon"], "https://icons.example/a.png")  # 没找到图：记下来源图标
        self.assertEqual(saved[0]["image"], "")  # 封面不写回
        self.assertEqual((saved[1]["image"], saved[1]["image_via"]), ("https://copy.example/x.jpg", "转载 copy.example"))
        log = err.getvalue()
        self.assertIn("无图：原文 HTTP 403（防机器人：Cloudflare）（用作品封面）", log)
        self.assertIn("配图汇总：共 3 条，有图 2 条", log)
        self.assertTrue((tmp / "docs" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()


class RedditBreaker(unittest.TestCase):
    """Reddit 限流后，这次运行后面的 Reddit 请求直接跳过，不再每次等十几秒。"""

    def setUp(self):
        sources._reddit_limited = None
        self.addCleanup(setattr, sources, "_reddit_limited", None)

    def test_second_request_skipped_after_429(self):
        import urllib.error
        calls = []

        def fake(req, timeout=None):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", None, None)
        with mock.patch.object(sources.urllib.request, "urlopen", fake), \
             mock.patch.object(sources.time, "sleep", lambda s: None), \
             mock.patch.dict(os.environ, {"REDDIT_CLIENT_ID": "", "REDDIT_CLIENT_SECRET": ""}):
            self.assertEqual(sources.reddit_sub("A"), [])      # 第一次：请求两次（重试一次）都 429
            self.assertEqual(len(calls), 2)
            self.assertEqual(sources.reddit_search("B"), [])   # 之后：不再请求
            self.assertEqual(len(calls), 2)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                sources._reddit_get("/r/C/new", {})
            self.assertEqual(cm.exception.code, 429)            # 配图那边照样按 429 写原因
        images.clear_cache()
        self.assertIsNone(sources._reddit_limited)

    def test_other_errors_do_not_trip(self):
        import urllib.error

        def fake(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)
        with mock.patch.object(sources.urllib.request, "urlopen", fake), \
             mock.patch.object(sources.time, "sleep", lambda s: None):
            sources.reddit_sub("A")
        self.assertIsNone(sources._reddit_limited)


class NetworkReason(unittest.TestCase):
    def test_string_reason_is_written_out(self):
        import urllib.error

        def fake(req, timeout=None):
            raise urllib.error.URLError("no host given")
        with mock.patch.object(images.urllib.request, "urlopen", fake), \
             mock.patch.object(images.time, "sleep", lambda s: None):
            f = images._fetch("http://x/y.jpg", 100)
        self.assertEqual(f.error, "网络错误 no host given")


class AsciiUrl(unittest.TestCase):
    def test_non_ascii_is_encoded(self):
        self.assertEqual(images._ascii_url("https://e.com/画像/猫 1.jpg?q=猫&a=1"),
                         "https://e.com/%E7%94%BB%E5%83%8F/%E7%8C%AB%201.jpg?q=%E7%8C%AB&a=1")
        self.assertEqual(images._ascii_url("https://e.com/a%20b.jpg?x=1"), "https://e.com/a%20b.jpg?x=1")  # 已编码的不动
        self.assertEqual(images._ascii_url("https://例え.jp/a.jpg"), "https://xn--r8jz45g.jp/a.jpg")

    def test_fetch_non_ascii_path(self):
        with mock.patch.object(images.urllib.request, "urlopen") as op:
            op.side_effect = lambda req, timeout=None: (_ for _ in ()).throw(AssertionError(req.full_url))
            f = images._fetch("http://127.0.0.1:1/画像.jpg", 100)
        self.assertNotIn("ordinal", f.error)
        self.assertIn("%E7%94%BB", op.call_args[0][0].full_url)


class BingThumbOrderTest(unittest.TestCase):
    """Bing の縮小画像は Bing が切った一部分（2026-10-17 サンリオハウスの横長バナーが縦の一切れに）：原文の図を先に試す。"""

    def test_bing_thumb_after_article_images(self):
        import images
        order = []
        with mock.patch.object(images, "check", side_effect=lambda u: (order.append(u), (False, "x"))[1]), \
             mock.patch.object(images, "page", return_value=images.Page(url="https://news.example.jp/a", ok=True, og=["https://news.example.jp/og.jpg"])), \
             mock.patch.object(images, "syndicated_candidates", return_value=([], "")):
            e = sources.Entry(title="t", url="https://news.example.jp/a", source="s", summary="",
                              image="https://www.bing.com/th?id=ONUT.x&pid=News", published=None)
            images.pick(None, [e], "https://news.example.jp/a")
        self.assertEqual(order, ["https://news.example.jp/og.jpg", "https://www.bing.com/th?id=ONUT.x&pid=News"])
        self.assertTrue(images.is_bing_thumb("https://bing.com/th?id=1"))
        self.assertFalse(images.is_bing_thumb("https://news.example.jp/og.jpg"))


class SpamOnPageTest(unittest.TestCase):
    def test_render_hides_spam_left_in_old_issues(self):
        import render
        issue = {"date": "2026-10-17", "items": [{"name": "绝区零", "stories": [
            {"headline": "绝区零艾莲被爆❌挤奶歪歪在线高清完整-爱看高清网", "url": "https://hurun.net/1", "image": None},
            {"headline": "绝区零 3.3", "url": "https://a/2", "image": None}]}]}
        self.assertEqual([x["headline"] for x in render.collect([issue])[0]["stories"]], ["绝区零 3.3"])
