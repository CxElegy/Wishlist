"""写真は Pages から出る（2026-11-03 Supabase egress 対策 ④）：公開の docs/ に Supabase storage の網址を残さない・/p/ が無い間の穴を埋める仕組み。"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import pages_served  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))

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
                bad.append((f.relative_to(ROOT).as_posix(), n))
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
    def test_cache_covers_every_stored_photo(self):
        """photo_store.stored() が /p/ の網址を出せる写真（置き場の全部・400 と 800）は、docs/ に無くても（お客さまのページ）写しの対象。漏れると /p/ が 404 → Supabase に戻る。"""
        import json
        import photo_cache_fill
        want = photo_cache_fill.urls()
        p = json.loads((ROOT / "state" / "photo_store.json").read_text(encoding="utf-8")).get("p", {})
        miss = [f"{k}-{w}.webp" for k in p for w in (400, 800) if f"{k}-{w}.webp" not in want]
        self.assertEqual(miss[:3], [], "写しの対象に入っていない写真が %d 枚" % len(miss))

    def test_user_emblems_go_through_pages(self):
        """お客さまのページの小元素（emblems 箱）も旗 on なら /p/ に書き換わり、pages_photos が大文字の名前（Wikidata の Q…）も並べる。"""
        import photo_store
        import pages_photos
        photo_store._ON[:] = [True]
        try:
            h = 'a&quot;https://x.supabase.co/storage/v1/object/public/emblems/Q123-ab12.webp&quot; https://x.supabase.co/storage/v1/object/public/photos/aa-400.webp'
            out = photo_store.emblems_to_pages(h)
            self.assertIn(photo_store.PAGES_BASE + "/Q123-ab12.webp&quot;", out)
            self.assertIn("/object/public/photos/aa-400.webp", out)   # 写真は別の規則（stored）
        finally:
            photo_store._ON[:] = []
        self.assertTrue(pages_photos.NAME.fullmatch("Q123-ab12.webp"))

    def test_admin_emblem_js_goes_through_pages(self):
        """管理ページ③は店長の令牌で boards を読み、小元素の src を JS で作る（HTML に焼かない）。旗 off は Supabase のまま、on は /p/ 。"""
        import subprocess
        import render
        js = render.EMM_JS
        self.assertNotIn(".src=x.image", js)
        self.assertNotIn("$('emm-img').src=t.dataset.img", js)
        self.assertIn("var PGB='';", js)
        self.assertNotIn("im.src=c.image", js)   # 候補の写真も pg() を通す
        fn = js[js.index("function pg(u)"):js.index("var lib={}")]
        u = "https://x.supabase.co/storage/v1/object/public/emblems/Q1-ab.webp"
        out = subprocess.run(["node", "-e", "var PGB=process.argv[1];%s;console.log(pg(process.argv[2]),pg('https://i.example/a.jpg'))" % fn, "", u],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, [u, "https://i.example/a.jpg"])   # 旗 off
        out = subprocess.run(["node", "-e", "var PGB=process.argv[1];%s;console.log(pg(process.argv[2]),pg('https://i.example/a.jpg'))" % fn, "P", u],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["P/Q1-ab.webp", "https://i.example/a.jpg"])   # 旗 on

    def test_emblems_missing(self):
        import pages_health
        self.assertEqual(pages_health.emblems_missing({"a.webp", "b.webp"}, {"names": ["a.webp"]}), ["b.webp"])
        self.assertEqual(pages_health.emblems_missing({"a.webp"}, None), ["a.webp"])
        self.assertEqual(pages_health.emblems_missing(set(), {"names": []}), [])

    def test_storage_leaks_counts_non_emblem(self):
        import pages_health
        e = "https://x.supabase.co/storage/v1/object/public/emblems/Q1-ab.webp"
        self.assertEqual(pages_health.storage_leaks(e), 0)
        self.assertEqual(pages_health.storage_leaks(e + " https://x.supabase.co/storage/v1/object/public/photos/aa-400.webp"), 1)
        self.assertEqual(pages_health.storage_leaks(None), 0)

    def test_photo_cache_checks_emblems_with_key(self):
        """鍵のある回（photo_cache.yml）で boards の小元素 ⊆ 写し・storage 網址 0 を毎回数える（警告として見える。手で数えた 1 回で終わらせない）。"""
        t = (ROOT / ".github" / "workflows" / "photo_cache.yml").read_text(encoding="utf-8")
        self.assertIn("pages_health.py --emblems", t)

    def test_photo_cache_runs_after_render_and_republishes(self):
        """新しい写真は render のあとに html へ載る。毎日 1 回だと最大 1 日 /p/ が 404 になった（2026-11-03：10 枚）→ render のあとに写しを足し、変わったら Pages を出し直す。"""
        t = (ROOT / ".github" / "workflows" / "photo_cache.yml").read_text(encoding="utf-8")
        self.assertIn('workflows: ["网页立即更新", "Pages 公開"]', t)   # 編排・后台作業の push は render を通らない → Pages 公開の後にも（2026-11-03 ゲート 98.3% の根）
        self.assertIn("steps.fill.outputs.changed", t)
        self.assertIn("gh workflow run pages.yml", t)
        self.assertIn("changed=", (ROOT / "harness" / "photo_cache_fill.py").read_text(encoding="utf-8"))


    def test_photo_cache_save_is_verified(self):
        """cache/save は「Unable to reserve cache」を警告だけで緑のまま終える（2026-11-03：80 枚が Pages に載らなかった）→ lookup-only で探し、無ければ別の名前で再保存、それでも無ければ赤。"""
        t = (ROOT / ".github" / "workflows" / "photo_cache.yml").read_text(encoding="utf-8")
        self.assertEqual(t.count("lookup-only: true"), 2)
        self.assertIn("wl-photo-cache-${{ github.run_id }}-retry", t)
        self.assertIn("exit 1", t)

if __name__ == "__main__":
    unittest.main()
