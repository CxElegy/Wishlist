"""公開のログ（Actions のログは誰でも読める）にお客さまの版面の名前・記事の網址を出さない（2026-11-05 全体点検 本 3 ①・BACKLOG 552）。

お客さまの版面を回すスクリプトの print / log / ::warning:: の中に、名前・網址・題の値を差し込む行を数えて 0 であること。
数・種類（type(ex).__name__）・HTTP の番号・版面の id（uuid）は出してよい。"""
import ast
import logging
import pathlib
import sys
import types
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# お客さまの版面・ページを回すスクリプト（library_emblem.yml・digest.yml の user_pages・render.yml の user_pages）
FILES = ["library_emblem.py", "library.py", "library_design.py", "user_pages.py", "userfeed.py"]
SAY = {"print", "log", "_log", "warn"}
WORDS = ("name", "who", "url", "link", "href", "title", "src", "query", "q")


SAFE = {"len", "type", "sum", "bool", "int"}   # 数・種類だけになる包み
# 店長の版面だけを出す道具／手で回す道具（workflow から呼ばない・公開のログに出ない）
ALLOW = {("library.py", "r['name']"), ("library_design.py", 'b["name"]')}


def leaks(fname):
    """print(name)・"…" + url・f"{title}" のどれでも、言う関数の引数に名前・網址の値が入る所を数える。"""
    src = (ROOT / "scripts" / fname).read_text(encoding="utf-8")
    out = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in SAY):
            continue
        stack = list(node.args) + [k.value for k in node.keywords if k.arg not in ("file", "flush", "end", "sep")]
        while stack:
            n = stack.pop()
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") in SAFE or isinstance(n, ast.Attribute) and n.attr == "__name__":
                continue
            hit = (isinstance(n, ast.Name) and n.id in WORDS) or (isinstance(n, ast.Attribute) and n.attr in WORDS) or \
                (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value in WORDS)
            if hit:
                seg = ast.get_source_segment(src, n) or ""
                if (fname, seg) not in ALLOW:
                    out.append(f"{fname}:{n.lineno} {seg}")
                continue
            stack.extend(ast.iter_child_nodes(n))
    return out


class PublicLog(unittest.TestCase):
    def test_no_board_names_or_urls_in_logs(self):
        bad = [x for f in FILES for x in leaks(f)]
        self.assertEqual(bad, [], "公開のログに名前・網址を出す行")

    def test_counter_catches_a_name(self):
        """数える道具が本当に拾うこと（前の library_emblem の who[:10] の形）。"""
        src = "def f(n, who):\n    print(f\"E24 {n} 件：{'・'.join(who[:10])}\")\n"
        p = ROOT / "scripts" / "_tmp_public_log_probe.py"
        p.write_text(src, encoding="utf-8")
        try:
            self.assertEqual(len(leaks(p.name)), 1)
            p.write_text("def f(name, url):\n    print(name)\n    log('x ' + url)\n    print(len(name))\n", encoding="utf-8")
            self.assertEqual(len(leaks(p.name)), 2)   # f-string でない書き方も拾う・len() は拾わない
        finally:
            p.unlink()

    def test_user_pages_does_not_open_the_browser(self):
        """本物のブラウザ（images._browser_html）は開いた網址を stderr（公開のログ）に書く。library_emblem.yml は
        SCRAPLING_BROWSER=1 のまま user_pages を回すので、お客さまの記事の写真探しでは切れていること。"""
        import user_pages
        seen = []
        with mock.patch.dict("os.environ", {"SCRAPLING_BROWSER": "1"}), \
                mock.patch.object(user_pages.digest, "find_image", lambda *a, **k: seen.append(__import__("os").environ.get("SCRAPLING_BROWSER"))):
            user_pages.find_images([{"headline": "h", "url": "https://example.com/a"}], 1e12)
        self.assertEqual(seen, [None])

    def test_scrapling_does_not_log_urls(self):
        """scrapling の Fetcher は取った網址を INFO で出す（digest.yml の run の段に 19 行）。user_pages も通るので黙らせる。"""
        import images
        seen = []

        class H(logging.Handler):
            def emit(self, rec):
                seen.append(rec.getMessage())

        lg = logging.getLogger("scrapling")
        h = H()
        lg.addHandler(h)
        lg.setLevel(logging.INFO)   # scrapling は import のときに INFO にする

        class Fetcher:
            @staticmethod
            def get(url, **kw):
                lg.info(f"Fetched (200) <GET {url}>")
                return types.SimpleNamespace(body=b"x", headers={}, status=200)

        fake = types.ModuleType("scrapling.fetchers")
        fake.Fetcher = Fetcher
        try:
            with mock.patch.dict(sys.modules, {"scrapling": types.ModuleType("scrapling"), "scrapling.fetchers": fake}), \
                    mock.patch.object(images, "SCRAPLING", True):
                images._scrape("https://example.com/secret-article", 1000)
        finally:
            lg.removeHandler(h)
        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
