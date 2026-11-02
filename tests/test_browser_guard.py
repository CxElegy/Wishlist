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

    def test_storage_blocked(self):
        import sys
        sys.path.insert(0, str(ROOT / "harness"))
        import browser
        self.assertTrue(browser.PATTERN.match("https://x.supabase.co/storage/v1/object/public/photos/a-800.webp"))
        self.assertFalse(browser.PATTERN.match("https://x.supabase.co/rest/v1/rpc/f"))


if __name__ == "__main__":
    unittest.main()
