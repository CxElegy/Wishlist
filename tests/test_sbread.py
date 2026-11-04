"""点検の道具が本番の Supabase を読む入口は harness/sbread.py だけ（2026-11-04・egress）。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import sbread  # noqa: E402

OK = {"sbread.py", "sb_down_check.py"}   # sb_down_check は abort する先の見本の網址（要求は出ない）


class SbRead(unittest.TestCase):
    def test_no_direct_rest_reads(self):
        for f in (ROOT / "harness").glob("*.py"):
            if f.name not in OK and re.search(r"urllib\.request\.Request\(\s*[^)]{0,200}rest/v1/(?!rpc)", f.read_text(encoding="utf-8")):
                self.fail(f"{f.name}: urllib で /rest/v1/ を直接読んでいる（sbread.get を通す）")

    def test_second_read_is_cached(self):
        class R:
            headers = {"Content-Range": "0-1/2"}
            def read(self): return b'[{"id":1}]'
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sbread, "DIR", Path(d)), \
                mock.patch("urllib.request.urlopen", return_value=R()) as u:
            sbread._n.update(net=0, hit=0, bytes=0)
            a = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact")
            b = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact")
            c = sbread.get("https://x/rest/v1/boards?select=id", "k", "other")   # 別の人の鍵は別の写し
            self.assertEqual(a, b)
            self.assertEqual(json.loads(a[0]), [{"id": 1}])
            self.assertEqual(a[1], "0-1/2")
            self.assertEqual((u.call_count, sbread.stats()["hit"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
