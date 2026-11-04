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
        """/rest/v1/（rpc 以外）の文字を持つ行は sbread.get を呼ぶ行か、網址の定数の行だけ。定数の網址は同じファイルで sbread.get に渡す。
        urllib・requests・page.request で /rest/v1/ を組み立てて読む道（複数行・変数）も、ファイルごとに「rest/v1 を含むのに sbread を使わない」で拾う。"""
        for f in (ROOT / "harness").glob("*.py"):
            t = f.read_text(encoding="utf-8")
            if f.name in OK or not re.search(r"rest/v1/(?!rpc)", t):
                continue
            self.assertIn("sbread.get(", t, f"{f.name}: /rest/v1/ を読むのに sbread.get を通していない")
            for m in re.finditer(r"(urlopen|requests\.(get|post)|\.request\.(get|fetch))\(", t):
                self.assertNotRegex(t[max(0, m.start() - 300):m.end() + 300], r"rest/v1/(?!rpc)", f"{f.name}: /rest/v1/ の近くで {m.group(0)} を直接呼んでいる")

    def test_second_read_is_cached(self):
        class R:
            headers = {"Content-Range": "0-1/2"}
            def read(self): return b'[{"id":1}]'
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sbread, "DIR", Path(d)), \
                mock.patch("urllib.request.urlopen", return_value=R()) as u:
            sbread._n.update(net=0, hit=0, bytes=0)
            a = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact", ttl=600)
            b = sbread.get("https://x/rest/v1/boards?select=id", "k", "tok", prefer="count=exact", ttl=600)
            c = sbread.get("https://x/rest/v1/boards?select=id", "k", "other", ttl=600)   # 別の人の鍵は別の写し
            self.assertEqual(a, b)
            self.assertEqual(json.loads(a[0]), [{"id": 1}])
            self.assertEqual(a[1], "0-1/2")
            self.assertEqual((u.call_count, sbread.stats()["hit"]), (2, 1))


    def test_default_is_fresh(self):
        """ttl を渡さない読みは毎回本番（比べる点検が古い写しで偽の緑にならない）。"""
        class R:
            headers = {}
            def read(self): return b"[]"
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sbread, "DIR", Path(d)), \
                mock.patch("urllib.request.urlopen", return_value=R()) as u:
            sbread.get("https://x/rest/v1/a", "k", "t"); sbread.get("https://x/rest/v1/a", "k", "t")
            self.assertEqual(u.call_count, 2)


if __name__ == "__main__":
    unittest.main()
