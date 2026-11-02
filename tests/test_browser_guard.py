"""点検は共通の open_page（harness/browser.py の launch）だけでブラウザを開く（free-tier.md 決まり 1・2026-11-02）。
直接 chromium.launch すると本番の写真を毎回落として Supabase の枠（月 5 GB）を食う。"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = re.compile(r"\bchromium\.launch\(|\bchromium\.connect|launch_persistent_context\(")


class BrowserGuard(unittest.TestCase):
    def test_no_direct_launch(self):
        bad = []
        for d in ("harness", "tests", "scripts"):
            for f in (ROOT / d).glob("*.py"):
                if f.name in ("browser.py", "test_browser_guard.py"):
                    continue
                for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if RAW.search(line):
                        bad.append(f"{f.relative_to(ROOT)}:{n}")
        self.assertEqual(bad, [], "ブラウザは harness/browser.py の launch(pw) で開く")

    def test_no_direct_launch_js(self):
        """.mjs・.claude/skills の道具も（2026-11-02：RAW は *.py しか見ていなかった）。止め（setBlockedURLs / supabase.co/storage の route）を持つか、読み込む先がローカルだけと許可リストにあるもの。"""
        LOCAL_ONLY = {".claude/skills/diagram/shot.mjs"}   # file:// の自作 HTML だけ開く
        bad = []
        for pat in ("harness/**/*.mjs", "harness/**/*.js", ".claude/skills/**/*.mjs", ".claude/skills/**/*.js"):
            for f in ROOT.glob(pat):
                if "node_modules" in f.parts:
                    continue
                s = f.read_text(encoding="utf-8")
                rel = str(f.relative_to(ROOT))
                if re.search(r"\b(chromium|firefox|webkit)\.(launch|connect)|puppeteer", s) and rel not in LOCAL_ONLY \
                        and "setBlockedURLs" not in s and "supabase.co/storage" not in s and "supabase\\.co" not in s:
                    bad.append(rel)
        self.assertEqual(bad, [], "止めのない JS のブラウザ起動")
        # inspect.mjs・scenes.mjs は Browser.launch（lib/cdp.mjs）経由：そこに止めがあること
        self.assertIn("setBlockedURLs", (ROOT / ".claude/skills/design-taste-frontend/scripts/lib/cdp.mjs").read_text())

    def test_workflows_do_not_launch_browser(self):
        """workflow の run: に playwright を直接起動する行（python -c / heredoc / node -e）を書かない。ブラウザは harness/*.py（browser.launch 経由）だけ。"""
        bad = []
        for f in (ROOT / ".github" / "workflows").glob("*.yml"):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"sync_playwright|async_playwright|chromium\.launch|puppeteer|npx playwright (screenshot|open|codegen)", line):
                    bad.append(f"{f.name}:{n}")
        self.assertEqual(bad, [], "workflow が playwright を直接起動している")

    def test_urllib_guard(self):
        """harness の Python は urllib.request を使うなら browser を import する（= urlopen が supabase.co/storage を拒む）。requests・httpx は使わない。"""
        bad = []
        for f in (ROOT / "harness").glob("*.py"):
            s = f.read_text(encoding="utf-8")
            if re.search(r"^\s*(import|from) (requests|httpx|aiohttp)\b", s, re.M):
                bad.append(f"{f.name}: requests/httpx は使わない（止めを通らない）")
            if f.name != "browser.py" and re.search(r"^\s*import urllib\.request", s, re.M) and not re.search(r"^\s*(import browser|from browser import)", s, re.M):
                bad.append(f"{f.name}: urllib を使うのに browser を import していない")
        self.assertEqual(bad, [])

    def test_no_swallowed_guard_and_no_raw_storage_read(self):
        """止めの RuntimeError を except Exception が飲み込まない・storage の網址を直接 urlopen／requests しない（2026-11-02：ux_check.server_opens が 4 か所目だった）。"""
        import sys
        sys.path.insert(0, str(ROOT / "harness"))
        import ux_check
        import browser
        calls = []
        old = browser.storage_bytes
        try:
            ux_check.storage_bytes = lambda u, h=None, t=0: calls.append(u) or b"IMG"
            self.assertTrue(ux_check.server_opens("https://abc.supabase.co/storage/v1/object/public/photos/x.webp"))
            def boom(*a, **k): raise RuntimeError("guard")
            ux_check.storage_bytes = boom
            with self.assertRaises(RuntimeError):
                ux_check.server_opens("https://abc.supabase.co/storage/v1/object/public/photos/x.webp")
        finally:
            ux_check.storage_bytes = old
        self.assertEqual(len(calls), 1)
        # 静的に数える：harness で urlopen を使う所が PATTERN／storage_bytes を通るか、storage を読まないもの
        bad = []
        for f in (ROOT / "harness").glob("*.py"):
            if f.name == "browser.py":
                continue
            s = f.read_text(encoding="utf-8")
            for m in re.finditer(r"urlopen\(([^\n]*)", s):
                if "supabase.co/storage" in m.group(1):
                    bad.append(f"{f.name}: storage の網址を直接 urlopen")
        lay = (ROOT / "scripts" / "layout_sample.py").read_text(encoding="utf-8")
        self.assertIn("/storage/v1/", lay)   # 写真の網址が storage なら requests.get に行かない
        self.assertEqual(bad, [])

    def test_urlopen_storage_refused_and_cached(self):
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "harness"))
        import browser
        import urllib.request
        u = "https://x.supabase.co/storage/v1/object/public/photos/zz-800.webp"
        with self.assertRaises(RuntimeError):
            urllib.request.urlopen(u)
        with self.assertRaises(RuntimeError):
            urllib.request.urlopen(urllib.request.Request(u))
        old = browser.CACHE
        try:
            browser.CACHE = pathlib.Path(tempfile.mkdtemp())
            (browser.CACHE / "zz-800.webp").write_bytes(b"abc")
            self.assertEqual(browser.storage_bytes(u), b"abc")   # 写しがあれば網に出ない
        finally:
            browser.CACHE = old

    def test_fulfill_fills_cache_once(self):
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "harness"))
        import browser

        class Resp:
            ok = True
            def body(self): return b"IMG"

        class Route:
            n = 0
            out = None
            def __init__(s, u): s.request = type("R", (), {"url": u})
            def fetch(s, **k): Route.n += 1; return Resp()
            def fulfill(s, **k): s.out = k

        old, browser.CACHE = browser.CACHE, pathlib.Path(tempfile.mkdtemp())
        try:
            u = "https://x.supabase.co/storage/v1/object/public/photos/qq-800.webp?v=1"
            browser._fulfill(Route(u))
            r2 = Route(u)
            browser._fulfill(r2)
            self.assertEqual(Route.n, 1)                 # 2 回目は写しから
            self.assertEqual(r2.out["body"], b"IMG")
        finally:
            browser.CACHE = old

    def test_playwright_mcp_guarded(self):
        """係が自分で開く Playwright MCP も同じ止め（--init-page）。"""
        import json
        args = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["playwright"]["args"]
        self.assertIn("--init-page", args)
        f = ROOT / args[args.index("--init-page") + 1]
        self.assertTrue(f.is_file())
        self.assertIn("supabase", f.read_text())

    def test_storage_blocked(self):
        import sys
        sys.path.insert(0, str(ROOT / "harness"))
        import browser
        self.assertTrue(browser.PATTERN.match("https://x.supabase.co/storage/v1/object/public/photos/a-800.webp"))
        self.assertFalse(browser.PATTERN.match("https://x.supabase.co/rest/v1/rpc/f"))


if __name__ == "__main__":
    unittest.main()
