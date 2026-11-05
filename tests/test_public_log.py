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
# 店長の版面だけを出す道具（手で回す・店長のデータは公開の Pages に出ている）
ALLOW = {("library.py", "r['name']")}


def leaks(fname):
    src = (ROOT / "scripts" / fname).read_text(encoding="utf-8")
    out = []
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in SAY):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.FormattedValue):
                continue
            seg = ast.get_source_segment(src, sub.value) or ""
            if (fname, seg) in ALLOW:
                continue
            names = {n.id for n in ast.walk(sub.value) if isinstance(n, ast.Name)}
            names |= {n.attr for n in ast.walk(sub.value) if isinstance(n, ast.Attribute)}
            names |= {n.value for n in ast.walk(sub.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            if names & set(WORDS) and "__name__" not in seg:
                out.append(f"{fname}:{sub.lineno} {seg}")
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
        finally:
            p.unlink()

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
