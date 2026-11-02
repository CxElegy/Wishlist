"""写真は Pages から出る（2026-11-03 Supabase egress 対策 ④）：公開の docs/ に Supabase storage の網址を残さない・/p/ が無い間の穴を埋める仕組み。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import pages_served  # noqa: E402

STORAGE = re.compile(r"https://[^/\"'\s]+\.supabase\.co/storage/")
FB = re.compile(r'\sdata-fb="[^"]*"')   # 落ち先の欄。/p/ が開けないときだけ読む（free-tier.md「落ち先の決まり」）


class NoStorageInDocs(unittest.TestCase):
    def test_docs_have_no_storage_url_outside_fallback(self):
        """docs/ の html・js・json に、落ち先（data-fb）以外で Supabase storage の網址を書かない（見本ページも）。数えて 0。"""
        bad = []
        for f in (ROOT / "docs").rglob("*"):
            if f.suffix not in (".html", ".js", ".json") or "rules" in f.parts:
                continue
            t = FB.sub("", f.read_text(encoding="utf-8", errors="ignore"))
            n = len(STORAGE.findall(t))
            if n:
                bad.append((str(f.relative_to(ROOT)), n))
        self.assertEqual(bad, [], "storage の網址が残っている（Pages の /p/ にする）")

    def test_fallback_only_for_unstored_media(self):
        """落ち先の storage は media 箱（ig-articles。インスタの網址は切れるので自前で持つ）だけ。photos 箱は落ち先にも残さない。"""
        for f in (ROOT / "docs").rglob("*.html"):
            for fb in re.findall(r'\sdata-fb="([^"]*)"', f.read_text(encoding="utf-8", errors="ignore")):
                self.assertNotRegex(fb, r"supabase\.co/storage/v1/object/public/photos/", f.name)


class Verdict(unittest.TestCase):
    def test_classify(self):
        c = pages_served.classify
        self.assertEqual(c("https://cxelegy.github.io/Wishlist/p/ab-800.webp"), "pages")
        self.assertEqual(c("https://cxelegy.github.io/Wishlist/home/emblems/x.webp"), "own")
        self.assertEqual(c("https://x.supabase.co/storage/v1/object/public/photos/a.webp"), "storage")
        self.assertEqual(c("https://img.example.com/a.jpg"), "other")

    def test_verdict(self):
        ok = pages_served.verdict
        self.assertTrue(ok({"pages": 100, "storage": 0}, [])[0])
        self.assertFalse(ok({"pages": 100, "storage": 1}, [])[0])
        self.assertFalse(ok({"pages": 100, "storage": 0}, [(404, "u")])[0])
        self.assertFalse(ok({"pages": 0, "storage": 0}, [])[0])


class FillFollowsRender(unittest.TestCase):
    def test_photo_cache_runs_after_render_and_republishes(self):
        """新しい写真は render のあとに html へ載る。毎日 1 回だと最大 1 日 /p/ が 404 になった（2026-11-03：10 枚）→ render のあとに写しを足し、変わったら Pages を出し直す。"""
        t = (ROOT / ".github" / "workflows" / "photo_cache.yml").read_text(encoding="utf-8")
        self.assertIn('workflows: ["网页立即更新"]', t)
        self.assertIn("steps.fill.outputs.changed", t)
        self.assertIn("gh workflow run pages.yml", t)
        self.assertIn("changed=", (ROOT / "harness" / "photo_cache_fill.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
