"""公開 pages.yml：古い公開を止めて最新だけ出す・docs/ を push する回が終わったら公開する（2026-11-01）。"""
import datetime as dt
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
NOW = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)


def pushes_docs(text):
    """git add の行が docs を足す（git add docs / docs/…）か。"""
    return any(re.search(r"git add\b[^\n]*\bdocs\b", ln) for ln in text.splitlines())


def listed_names():
    """pages.yml の workflow_run.workflows に並ぶ名前。"""
    t = (WF / "pages.yml").read_text()
    m = re.search(r"workflows: \[([^\]]*)\]", t)
    return re.findall(r'"([^"]+)"', m.group(1))


def docs_pushers():
    """{ワークフローの名前: ファイル名}（git push して docs を git add する）。"""
    out = {}
    for f in WF.glob("*.yml"):
        t = f.read_text()
        if f.name != "pages.yml" and "git push" in t and pushes_docs(t):
            out[re.search(r"^name: (.+)$", t, re.M).group(1).strip()] = f.name
    return out


class PagesWorkflow(unittest.TestCase):
    def test_concurrency_cancels_old(self):
        t = (WF / "pages.yml").read_text()
        self.assertRegex(t, r"group: pages\s+cancel-in-progress: true")
        self.assertIn("actions/deploy-pages", t)

    def test_docs_pushers_are_listed(self):
        """docs/ を push する回は workflow_run にある（bot の push は push 触発を起こさない）。cleanup-branches の例外はなし（docs を足さない）。"""
        names = listed_names()
        for name, f in docs_pushers().items():
            self.assertIn(name, names, f"{f}（{name}）が pages.yml の workflow_run にない")

    def test_listed_names_really_push_docs(self):
        """逆向き：並べた名前は実在し、docs/ を足す回だけ（空振りの公開を起こさない）。"""
        pushers = docs_pushers()
        for name in listed_names():
            self.assertIn(name, pushers, f"「{name}」は docs/ を push しない（または名前が違う）：workflow_run から外す")

    def test_pushers_found(self):
        """数え漏れ防止：docs を push する回が 3 つ以上見つかる（見つからなければ上の点検が空振りしている）。"""
        self.assertGreaterEqual(len(docs_pushers()), 3)


class PagesHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("pages_health", ROOT / "harness" / "pages_health.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def run_(self, name, conc, hours_ago=1):
        at = (NOW - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"name": name, "created_at": at, "conclusion": conc}

    def test_legacy_runs_mean_not_switched(self):
        s = self.m.summarize([self.run_(self.m.LEGACY, "failure"), self.run_(self.m.OURS, "success")], NOW)
        ok, line = self.m.verdict(s)
        self.assertFalse(ok)
        self.assertIn("未切り替え", line)

    def test_switched_and_clean(self):
        s = self.m.summarize([self.run_(self.m.OURS, "success"), self.run_(self.m.OURS, "cancelled"), self.run_(self.m.LEGACY, "failure", 30)], NOW)
        ok, line = self.m.verdict(s)
        self.assertTrue(ok, line)
        self.assertEqual(s[self.m.OURS]["cancelled"], 1)

    def test_our_failure_is_red(self):
        ok, _ = self.m.verdict(self.m.summarize([self.run_(self.m.OURS, "failure")], NOW))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()


class PagesPhotos(unittest.TestCase):
    """写真・小元素を Pages から配る（2026-11-03）：公開物に docs/p/ を足す・旗が off の間は今のまま・on にしてよい条件。"""
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / "harness"))
        sys.path.insert(0, str(ROOT / "scripts"))
        import pages_health
        import pages_photos
        import photo_store
        cls.h, cls.s, cls.P = pages_health, pages_photos, photo_store

    def test_workflow_stages_photos_before_upload(self):
        t = (WF / "pages.yml").read_text()
        self.assertLess(t.index("pages_photos.py"), t.index("upload-pages-artifact"))
        self.assertIn("actions/cache/restore", t)

    def test_stage_copies_only_image_names_and_writes_manifest(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c").mkdir()
            (d / "c" / "0123456789abcdef-800.webp").write_bytes(b"x")
            (d / "c" / "notes.txt").write_bytes(b"x")
            self.assertEqual(self.s.stage(d / "c", d / "docs"), 1)
            m = json.loads((d / "docs" / "p" / "manifest.json").read_text())
            self.assertEqual(m["names"], ["0123456789abcdef-800.webp"])

    def test_manifest_has_bytes_and_size_verdict(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "c").mkdir()
            (d / "c" / "0123456789abcdef-800.webp").write_bytes(b"x" * 10)
            self.s.stage(d / "c", d / "docs")
            self.assertGreaterEqual(json.loads((d / "docs" / "p" / "manifest.json").read_text())["bytes"], 10)
        h = self.h
        self.assertIsNone(h.size_verdict({})[0])
        self.assertTrue(h.size_verdict({"bytes": 100 << 20}, 90 << 20)[0])
        self.assertFalse(h.size_verdict({"bytes": int(h.LIMIT * 0.71)})[0])

    def test_flag_default_off_and_url_switch(self):
        P = self.P
        k = "0123456789abcdef"
        P._CACHE[:] = [{"base": "https://s.example", "p": {k: {}}, "x": {}, "stat": {}}]
        old = list(P._ON)
        try:
            P._ON[:] = [False]
            P._CACHE[0]["p"] = {P.key("http://o/a.jpg"): {}}
            self.assertEqual(P.stored("http://o/a.jpg"), P.public("https://s.example", P.key("http://o/a.jpg")))
            P._ON[:] = [True]
            self.assertEqual(P.stored("http://o/a.jpg", 400), f"{P.PAGES_BASE}/{P.key('http://o/a.jpg')}-400.webp")
            seen, want = set(), {}
            P.scan_text([f'<img src="{P.PAGES_BASE}/{k}-800.webp" data-e="s">'], seen, want)
            self.assertEqual((seen, want), ({k}, {}))   # Pages の網址を「原寸」と読んで取りに行かない
        finally:
            P._ON[:] = old
            P._CACHE[:] = []

    def test_committed_flag_is_json(self):
        import json
        self.assertIn("on", json.loads((ROOT / "state" / "pages_photos.json").read_text()))

    def test_photos_verdict(self):
        want = {f"{i:016x}-800.webp" for i in range(100)}
        self.assertFalse(self.h.photos_verdict(None, want)[0])
        self.assertFalse(self.h.photos_verdict({"n": 50, "names": sorted(want)[:50]}, want)[0])
        self.assertFalse(self.h.photos_verdict({"n": 100, "names": sorted(want)}, want, sample_ok=False)[0])
        self.assertTrue(self.h.photos_verdict({"n": 100, "names": sorted(want)}, want)[0])


class PagesWantedFromStore(unittest.TestCase):
    """99% の判定の分母に、置き場（photo_store.json の p）にだけある写真も入れる（お客さまの pages 箱の写真は docs/*.html に載らない）。"""
    def test_store_names_added(self):
        import json
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "harness"))
        import pages_health
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "s.json"
            f.write_text(json.dumps({"p": {"0123456789abcdef": {}}}))
            self.assertEqual(pages_health.wanted_from_store(f), {"0123456789abcdef-400.webp", "0123456789abcdef-800.webp"})
            self.assertEqual(pages_health.wanted_from_store(Path(d) / "none.json"), set())
        ok, _ = pages_health.photos_verdict({"n": 1, "names": ["0123456789abcdef-400.webp"]}, {"0123456789abcdef-400.webp", "0123456789abcdef-800.webp"})
        self.assertFalse(ok)   # 置き場にあるのに Pages に並んでいない写真は 99% を割る
        import photo_store  # noqa: F401  幅の定義が同じ
        self.assertEqual(pages_health.WIDTHS, photo_store.WIDTHS)

