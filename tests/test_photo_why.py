"""写真の無い記事の理由を数える道具（harness/photo_why.py，2026-11-19）。ネットには出ない（道具を差し替える）。
画面に名前・題・網址の path を出さないこと、1 件ずつの行はリポジトリの外にだけ書くこと。"""
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import images  # noqa: E402
import photo_why  # noqa: E402

SECRET_PATH = "himitsu-no-kiji-12345"
TITLE = "お客さまだけの版面の記事の題"


class FakeTools:
    def __init__(self):
        self.browser = []

    def resolve(self, u):
        return "https://real.example/" + SECRET_PATH if u.endswith("ok") else u

    def page(self, u):
        if "blocked" in u:
            return images.Page(u, False, "原文 HTTP 403（防机器人：cloudflare）", status=403)
        if "news.google.com" in u:
            return images.Page(u, False, "原文是未还原的 Google 新闻跳转链接")
        return images.Page(u, True, og=["https://img.example/a.jpg"], final="https://www.final.example/" + SECRET_PATH)

    def pick(self, title, u):
        self.browser.append(__import__("os").environ.get("SCRAPLING_BROWSER"))
        if "blocked" in u:
            return images.Result(notes=["原文 HTTP 403（防机器人：cloudflare）"])
        if "news.google.com" in u:
            return images.Result(notes=["原文是未还原的 Google 新闻跳转链接", "Bing / Google 新闻都没有找到带图的同一篇转载"])
        if "saved" in u:
            return images.Result(image="https://img.example/h.jpg", source="og:image" + images.SAVED)
        return images.Result(image="https://img.example/a.jpg", source="og:image")

    def size(self, img):
        return "800×450"

    def saved(self, res):
        return images.SAVED in (res.source or "")

    def clear(self):
        pass


ITEMS = [{"url": "https://news.google.com/rss/articles/ok", "title": TITLE},
         {"url": "https://news.google.com/rss/articles/ng", "title": TITLE, "og": ""},
         {"url": f"https://blocked.example/{SECRET_PATH}", "title": TITLE, "og": {"why": "blocked", "at": "x", "n": 2}},
         {"url": f"https://saved.example/{SECRET_PATH}", "title": TITLE},
         {"url": f"https://fine.example/{SECRET_PATH}", "title": TITLE, "og": {"img": "https://img.example/a.jpg"}}]


class PhotoWhy(unittest.TestCase):
    def run_tool(self, argv, items=ITEMS, tools=None):
        lines = []
        stdin = io.StringIO(json.dumps(items, ensure_ascii=False))
        rows = photo_why.main(argv, tools=tools or FakeTools(), stdin=stdin, out=lines.append)
        return rows, "\n".join(lines)

    def test_reasons_and_no_private_text_on_screen(self):
        """(7) 画面には理由ごとの数と host だけ：題・網址の path・お客さまの名前は出さない。"""
        rows, screen = self.run_tool([])
        self.assertEqual(len(rows), 5)
        self.assertNotIn(SECRET_PATH, screen)
        self.assertNotIn(TITLE, screen)
        self.assertNotIn("/rss/articles", screen)
        self.assertIn("包みの網址 2 件：原文に戻せた 1・戻せない 1", screen)
        self.assertIn("SAVED", screen)
        self.assertIn("blocked.example", screen)   # host は出してよい
        by = {r["url"].split("/")[2]: r for r in rows}
        self.assertEqual(by["blocked.example"]["status"], 403)
        self.assertTrue(by["saved.example"]["saved"])
        self.assertEqual(by["fine.example"]["host"], "www.final.example")   # 転送のあとの最後の host
        self.assertEqual(by["fine.example"]["size"], "800×450")
        self.assertEqual(by["blocked.example"]["memo"], "取れなかった：blocked（2 回）")
        self.assertTrue(rows[0]["resolved"])
        self.assertFalse(rows[1]["resolved"])
        self.assertEqual(rows[1]["memo"], "前の形の空（試し直しの対象）")

    def test_rows_only_outside_repo(self):
        with self.assertRaises(SystemExit):
            self.run_tool(["--out", str(ROOT / "state" / "photo_why.jsonl")])
        out = pathlib.Path(tempfile.mkdtemp()) / "rows.jsonl"
        rows, screen = self.run_tool(["--out", str(out)])
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn(SECRET_PATH, lines[2])   # 1 件ずつの行（リポジトリの外）には網址
        self.assertNotIn(str(out), screen)

    def test_browser_compare(self):
        tools = FakeTools()
        rows, screen = self.run_tool(["--browser"], tools=tools)
        self.assertEqual(tools.browser, [None] * 5 + ["1"] * 5)
        self.assertIn("本物のブラウザ：なし", screen)
        self.assertNotIn(SECRET_PATH, screen)
        self.assertIn("browser_category", rows[0])

    def test_plain_lines_input(self):
        lines = []
        rows = photo_why.main([], tools=FakeTools(), stdin=io.StringIO(f"https://fine.example/{SECRET_PATH}\nnot a url\n"), out=lines.append)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
