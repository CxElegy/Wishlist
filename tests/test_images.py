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
import sources  # noqa: E402


def jpeg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


BIG = jpeg(640, 400)
SMALL = jpeg(120, 80)
_real_sleep = time.sleep  # 测试里把 time.sleep 换成空操作（跳过重试等待），服务器的“慢响应”要用真的
HITS = {}       # 路径 → 被请求的次数
REFERERS = []   # 收到的 Referer 头（应该一直是空的）


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
    "/blocked.html": (403, "text/html", b"<title>Attention Required! | Cloudflare</title>"),
    "/copy.html": (200, "text/html", html_page('<meta property="og:image" content="/big2.jpg">')),
    "/yt-article.html": (200, "text/html", html_page('<meta property="og:image" content="/big.jpg">')),
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
        # 测试里不访问外网：Google 跳转还原 / Bing / Reddit 都替换掉
        self.patches = [mock.patch.object(sources, "resolve_url", lambda u: u),
                        mock.patch.object(sources, "bing_news", lambda q: []),
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
                         "  [配图] 项 | 标题 | 无图：原文没有图片元数据，正文也没有图；Bing 新闻没有找到带图的同一篇转载；图片太小 120×80")
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

    # ---------- digest.attach_media（旧功能不回归） ----------

    def test_attach_media_writes_back_and_falls_back_to_cover(self):
        entries = [entry(url=self.u("/jsonld.html")), entry(url=self.u("/nothing.html"))]
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
        item = digest.load_config()[1][0]["name"]
        e1 = digest.entry_to_dict(1, entry(title="第一条新闻标题", url="https://a.example/1"))
        e2 = digest.entry_to_dict(2, entry(title="第二条新闻标题", url="https://a.example/2"))
        inbox = {"date": "2026-10-11", "items": [{"name": item, "entries": [e1, e2], "facts": [], "cover": "https://c.example/cover.jpg"}]}
        (tmp / "inbox" / "2026-10-11.json").write_text(json.dumps(inbox, ensure_ascii=False))
        edits = {item: [{"headline": "头条", "weight": "lead", "refs": [1]},
                        {"headline": "AI 挑了图", "image": "https://ai.example/pick.jpg", "refs": [2]},
                        {"headline": "补到了图", "refs": [2]}], "_covered": {item: 2}}
        (tmp / "inbox" / "2026-10-11.edit.json").write_text(json.dumps(edits, ensure_ascii=False))

        def fake_pick(chosen, refs, url):
            if chosen:
                return images.Result(chosen, "AI 挑选", [("AI 挑选", chosen, "OK")])
            if url.endswith("/1"):
                return images.Result(None, "", [], ["原文 HTTP 403（防机器人：Cloudflare）"])
            return images.Result("https://copy.example/x.jpg", "转载 copy.example", [("转载 copy.example", "x", "OK")])

        patches = [mock.patch.object(digest, d.upper() + "_DIR", tmp / d) for d in ("inbox", "reports", "docs")] + [
            mock.patch.object(digest, "STATE_DIR", tmp / "state"), mock.patch.object(digest, "THEMES_FILE", tmp / "state" / "themes.json"),
            mock.patch.object(digest, "write_issue_markdown", lambda *a: None), mock.patch.object(images, "pick", fake_pick),
            mock.patch.object(digest.theme, "resolve", lambda *a: dict(digest.theme.DEFAULT)), mock.patch.object(sources, "resolve_url", lambda u: u),
            mock.patch.object(digest, "make_client", lambda: None),
            # publish 最后会重算「我会喜欢？」：它写真实的 state/recommend.json，还会联网搜同类新品，测试里跳过
            mock.patch.object(digest, "recommend", lambda *a, **k: None)]
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
        self.assertEqual(saved[0]["image"], "")  # 封面不写回
        self.assertEqual((saved[1]["image"], saved[1]["image_via"]), ("https://copy.example/x.jpg", "转载 copy.example"))
        log = err.getvalue()
        self.assertIn("无图：原文 HTTP 403（防机器人：Cloudflare）（用作品封面）", log)
        self.assertIn("配图汇总：共 3 条，有图 2 条", log)
        self.assertTrue((tmp / "docs" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
