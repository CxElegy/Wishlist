import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import photo_store as P  # noqa: E402


class PhotoStore(unittest.TestCase):
    def test_evict_age_then_cap(self):
        p = {"a": {"at": 100, "b": 10}, "b": {"at": 120, "b": 10}, "c": {"at": 119, "b": 10}}
        self.assertEqual(P.evict(p, {"a"}, 120, keep_days=14, cap=10**9), [])        # a は載っている → 古くても残る
        self.assertEqual(P.evict(p, set(), 120, keep_days=14, cap=10**9), ["a"])      # 載っていない 14 日超え
        self.assertEqual(P.evict({"b": p["b"], "c": p["c"]}, {"b"}, 120, cap=15), ["c"])  # 上限超え：載っていないものから古い順

    def test_scan_and_stored(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            k = P.key("https://x.example/a.jpg")
            (d / "i.html").write_text(
                '<img src="https://x.example/a.jpg" alt="" data-e="s">'
                f'<img src="https://s.example/storage/v1/object/public/photos/{P.name(k)}" data-fb="y" data-e="s">', encoding="utf-8")
            seen, want, total = P.scan(d)
            self.assertEqual((seen, list(want), total), ({k}, [k], 1))
            # ぼかし・ギャラリー・欲しい物(r)もお客さまのページ(extra)も数える
            k2, k3 = P.key("https://y.example/b.jpg"), P.key("https://z.example/c.jpg")
            (d / "j.html").write_text('<img class="bg" src="https://y.example/b.jpg" alt="" data-e="r">', encoding="utf-8")
            seen, want, total = P.scan(d, ['<img src="https://z.example/c.jpg" data-e="s">'])
            self.assertEqual(set(want), {k, k2, k3})

    def test_render_pic_gives_srcset_and_small_bg(self):
        import render
        u = "https://x.example/a.jpg"
        k = P.key(u)
        P._CACHE[:] = [{"base": "https://s.example", "p": {k: {"at": 1, "b": 5}}, "x": {}, "stat": {}}]
        try:
            h = render._pic({"image": u, "title": "t"})
        finally:
            P._CACHE[:] = []
        self.assertIn(f'<img class="bg" src="https://s.example/storage/v1/object/public/photos/{k}-400.webp"', h)
        self.assertIn(f'srcset="https://s.example/storage/v1/object/public/photos/{k}-400.webp 400w, https://s.example/storage/v1/object/public/photos/{k}-800.webp 800w"', h)
        self.assertIn(f'data-fb="{u}"', h)

    def test_old_uploads_get_immutable_cache_header(self):
        """前に上げた分（cc の印なし）を、同じ中身で CACHE 付きに上げ直し、印を付ける。新しい分は最初から印つき。"""
        sent, k = [], P.key("https://x.example/a.jpg")
        P._req = lambda base, keyv, path, data=None, method="POST", ctype="image/webp", extra=None: sent.append((path, extra))
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): pass
            def read(s): return b"x"
        orig, orig_req = P.urllib.request.urlopen, P._req
        P.urllib.request.urlopen = lambda *a, **kw: R()
        try:
            with tempfile.TemporaryDirectory() as d:
                d = pathlib.Path(d)
                (d / "i.html").write_text('<img src="https://x.example/a.jpg" data-e="s">', encoding="utf-8")
                st = d / "s.json"
                st.write_text(json.dumps({"base": "https://s.example", "p": {k: {"at": 1, "b": 5}}}), encoding="utf-8")
                s = P.run(site=d, path=st, base="https://s.example", keyv="k")
                self.assertEqual((s["cc"], s["cc_wait"]), (1, 0))
                self.assertEqual(json.loads(st.read_text())["p"][k]["cc"], 1)
                self.assertEqual(len(sent), 2)      # 400 と 800
                self.assertTrue(all(e["Cache-Control"] == P.CACHE for _, e in sent))
                sent.clear()
                P.run(site=d, path=st, base="https://s.example", keyv="k")
                self.assertEqual(sent, [])          # 印があれば上げ直さない
        finally:
            P.urllib.request.urlopen, P._req = orig, orig_req

    def test_tint_is_inlined_as_color_underlay(self):
        """色だけの下絵（2026-10-31）：置いてある写真は平均色を枠の style に埋める（通信 0 で出る）。色のない分は style なし。"""
        import render
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (80, 80), (255, 0, 0)).save(b, "PNG")
        self.assertEqual(P.tint(b.getvalue()), "#ff0000")
        u = "https://x.example/a.jpg"
        k = P.key(u)
        try:
            P._CACHE[:] = [{"base": "https://s.example", "p": {k: {"at": 1, "b": 5, "c": "#ff0000"}}, "x": {}, "stat": {}}]
            self.assertIn('<div class="pic" style="background:#ff0000">', render._pic({"image": u, "title": "t"}))
            P._CACHE[:] = [{"base": "https://s.example", "p": {k: {"at": 1, "b": 5}}, "x": {}, "stat": {}}]
            self.assertIn('<div class="pic">', render._pic({"image": u, "title": "t"}))
        finally:
            P._CACHE[:] = []

    def test_shrink_never_upscales(self):
        from PIL import Image
        b = io.BytesIO()
        Image.new("RGB", (1000, 500), "red").save(b, "PNG")
        out = P.shrink(b.getvalue())
        self.assertEqual({w: Image.open(io.BytesIO(v)).width for w, v in out.items()}, {400: 400, 800: 800})
        b = io.BytesIO()
        Image.new("RGB", (300, 200), "red").save(b, "PNG")
        self.assertEqual({Image.open(io.BytesIO(v)).width for v in P.shrink(b.getvalue()).values()}, {300})

    def test_run_without_key_keeps_state_and_render_uses_store(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "i.html").write_text('<img src="https://x.example/a.jpg" data-e="s">', encoding="utf-8")
            st = d / "s.json"
            k = P.key("https://x.example/a.jpg")
            st.write_text(json.dumps({"base": "https://s.example", "p": {k: {"at": 1, "b": 5}}}), encoding="utf-8")
            s = P.run(site=d, path=st, base="https://s.example")
            self.assertEqual(s["n"], 1)            # 鍵なし：取らない・消さない（載っていれば at は今日に）
            self.assertEqual(json.loads(st.read_text())["p"][k]["at"], P.day())


if __name__ == "__main__":
    unittest.main()
