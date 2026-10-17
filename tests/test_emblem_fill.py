"""小元素の自動補完（scripts/emblem_fill.py）・本人確認（face_id.py）・プロセス一覧（processes.py）。ネットワークには出ない。

    python -m unittest discover tests
"""

import json
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import emblem_fill as ef  # noqa: E402
import face_id  # noqa: E402
import processes  # noqa: E402
import render  # noqa: E402
import runlog  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Rules(unittest.TestCase):
    def test_kind_inferred_from_type(self):
        self.assertEqual(ef.kind_of({"type": "anime"}), "character")
        self.assertEqual(ef.kind_of({"type": "event"}), "person")
        self.assertEqual(ef.kind_of({"type": "product"}), "brand")
        self.assertEqual(ef.kind_of({"type": "category"}), "topic")
        self.assertEqual(ef.kind_of({"type": "category", "emblem_kind": "brand"}), "brand")
        self.assertEqual(ef.kind_of({"type": "game", "emblem_kind": "???"}), "character")   # 知らない種類は type で推定

    def test_targets(self):
        self.assertEqual(ef.rule({"type": "event", "emblem_kind": "person"})[1:], (3, 6, 10))
        self.assertEqual(ef.rule({"type": "category", "emblem_kind": "brand"})[1:], (1, 1, 1))
        self.assertEqual(ef.rule({"type": "category"})[1:], (2, 3, 5))
        # グループはメンバー全員（最大 10）
        nine = {"type": "event", "emblem_kind": "group", "emblem_who": [f"m{i}" for i in range(9)]}
        self.assertEqual(ef.rule(nine)[2], 9)
        twelve = {**nine, "emblem_who": [f"m{i}" for i in range(12)]}
        self.assertEqual(ef.rule(twelve)[2], 10)
        # 名前を挙げたキャラはその全員が目標（2 人の作品は 2 枚で足りる）
        two = {"type": "game", "emblem_who": ["a", "b"]}
        self.assertEqual(ef.rule(two)[2], 2)

    def test_status(self):
        base = {"name": "x", "type": "game"}
        self.assertEqual(ef.status(base)["state"], "none")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 2})["state"], "low")
        self.assertEqual(ef.status({**base, "emblem": [{}] * 6})["state"], "ok")
        # emblem_skip は「足りている」の理由にならない
        self.assertEqual(ef.status({**base, "emblem_skip": "なし"})["state"], "none")

    def test_audit_sorts_gaps_first(self):
        rows = ef.audit([{"name": "a", "type": "game", "emblem": [{}] * 6}, {"name": "b", "type": "game"},
                         {"name": "c", "type": "game", "emblem": [{}]}])
        self.assertEqual([r["name"] for r in rows], ["b", "c", "a"])

    def test_every_item_resolves(self):
        items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["items"]
        for i in items:
            st = ef.status(i)
            self.assertIn(st["kind"], ef.RULES, i["name"])
            self.assertLessEqual(st["target"], 10, i["name"])
            self.assertGreaterEqual(st["target"], st["lo"], i["name"])
            if i.get("emblem_kind"):
                self.assertIn(i["emblem_kind"], ef.RULES, i["name"])


class Sources(unittest.TestCase):
    def test_wide_logo_is_not_too_small(self):
        import emblem
        import io as _io
        from PIL import Image

        def png(w, h):
            b = _io.BytesIO()
            Image.new("RGB", (w, h), "white").save(b, "PNG")
            return b.getvalue()
        emblem.inspect(png(500, 133))   # 横長のロゴは長い辺 300 以上なら使える
        for w, h in ((120, 120), (280, 60), (500, 50)):
            with self.assertRaises(ValueError):
                emblem.inspect(png(w, h))

    def test_parse_bing(self):
        html = ('x murl&quot;:&quot;https://a.example/p/1.jpg&quot; y murl&quot;:&quot;https://a.example/p/1.jpg&quot; '
                'murl&quot;:&quot;https://b.example/bad name.png&quot; murl&quot;:&quot;https://c.example/2.webp?x=1&quot;')
        urls = [x["image"] for x in ef.parse_bing(html)]
        self.assertEqual(urls, ["https://a.example/p/1.jpg", "https://c.example/2.webp?x=1"])   # 重複と空白入りの網址は除く

    def test_relevant(self):
        self.assertTrue(ef.relevant("File:Starbucks Corporation Logo 2011.svg.png", "Starbucks"))
        self.assertFalse(ef.relevant("File:Chopin portrait.jpg", "Jay Chou"))
        self.assertTrue(ef.relevant("File:周杰倫 2014.jpg", "周杰倫"))

    def test_twemoji(self):
        self.assertTrue(ef.twemoji("🎾")["image"].endswith("/1f3be.svg"))
        self.assertTrue(ef.twemoji("⛷️")["image"].endswith("/26f7.svg"))   # 異体字セレクタは落とす

    def test_site_images_skip_logos(self):
        import types
        ef_get = ef._get
        ef._get = lambda url, limit=0: (b'<meta property="og:image" content="/og.png"><img src="/img/logo.png">'
                                        b'<img src="/img/member1.jpg">')
        try:
            urls = [x["image"] for x in ef.site_images("https://x.example/a/")]
        finally:
            ef._get = ef_get
        self.assertEqual(urls, ["https://x.example/og.png", "https://x.example/img/member1.jpg"])

    def test_auto_pick_prefers_reliable_sources(self):
        good = [{"subject": "A", "source": "Web 画像検索"}, {"subject": "A", "source": "Wikipedia"},
                {"subject": "B", "source": "Fandom"}, {"subject": "B", "source": "Web 画像検索"}]
        item = {"type": "game", "emblem_who": ["A", "B"]}
        self.assertEqual(sorted(ef.auto_pick(item, good)), [2, 3])   # 1 人 1 枚、Web 検索より Wiki 系を先に


    def test_auto_pick_background_skips_web_and_existing(self):
        item = {"type": "event", "emblem_kind": "group", "emblem_who": ["A", "B", "C"],
                "emblem": [{"subject": "A", "image": "emblems/a.webp", "source": "https://x.example/a.jpg"}]}
        good = [{"subject": "A", "source": "Wikipedia", "image": "https://x.example/a2.jpg"},   # A はもうある
                {"subject": "B", "source": "Web 画像検索", "image": "https://x.example/b.jpg"},
                {"subject": "C", "source": "Wikipedia", "image": "https://x.example/a.jpg"},   # 同じ画像はもうある
                {"subject": "C", "source": "新聞の配図", "image": "https://x.example/c.jpg"}]
        self.assertEqual(ef.auto_pick(item, good, web=False), [4])
        self.assertEqual(sorted(ef.auto_pick(item, good)), [2, 4])

    def test_auto_pick_skips_rejected(self):
        item = {"type": "event", "emblem_kind": "person", "emblem_reject": ["https://x.example/bad.jpg"]}
        good = [{"subject": "A", "source": "Wikipedia", "image": "https://x.example/bad.jpg"},
                {"subject": "A", "source": "Wikipedia", "image": "https://x.example/ok.jpg"}]
        self.assertEqual(ef.auto_pick(item, good, web=False, strict=True), [2])

    def test_auto_pick_brand_prefers_wikidata_logo(self):
        item = {"type": "product", "emblem_kind": "brand"}
        good = [{"subject": "X", "source": "Wikimedia Commons", "image": "c"}, {"subject": "X", "source": "公式サイト", "image": "s"},
                {"subject": "X", "source": "Wikidata", "image": "w"}]
        self.assertEqual(ef.auto_pick(item, good, web=False), [3])

    def test_auto_pick_strict_drawn_characters(self):
        # 絵のキャラは、後台ではキャラ専用の取り方だけ（Commons の「Juggernaut」はバンドの写真だった）
        item = {"type": "game", "emblem_who": ["Juggernaut", "Axe"]}
        good = [{"subject": "Juggernaut", "source": "Wikimedia Commons", "image": "c"},
                {"subject": "Axe", "source": "直接指定", "image": "d"}]
        self.assertEqual(ef.auto_pick(item, good, web=False, strict=True), [2])
        people = {"type": "show", "emblem_people": True, "emblem_who": ["A"]}
        self.assertEqual(ef.auto_pick(people, [{"subject": "A", "source": "Wikimedia Commons", "image": "c"}], web=False, strict=True), [1])

    def test_needs_face(self):
        self.assertTrue(ef.needs_face({"type": "event"}))
        self.assertTrue(ef.needs_face({"type": "show", "emblem_people": True}))
        self.assertFalse(ef.needs_face({"type": "show"}))
        self.assertFalse(ef.needs_face({"type": "product"}))


class Background(unittest.TestCase):
    """定時の後台（--background）と進捗ファイル。ネットには出ず、fill を差し替える。"""

    ITEMS = [{"name": "full", "type": "game", "emblem_who": ["a"], "emblem": [{"subject": "a", "image": "x"}]},
             {"name": "one", "type": "game", "emblem": [{}]},
             {"name": "zero", "type": "game"},
             {"name": "brand", "type": "product"}]

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.dir.name) / "emblem_progress.json"
        self.items = [dict(i) for i in self.ITEMS]
        self._load = ef.load_items
        ef.load_items = lambda: self.items
        self._logdir = runlog.LOG_DIR
        runlog.LOG_DIR = pathlib.Path(self.dir.name) / "log"   # 本物の state/log に書かない

    def tearDown(self):
        ef.load_items = self._load
        runlog.LOG_DIR = self._logdir
        self.dir.cleanup()

    def test_sync_progress(self):
        prog = ef.sync_progress({"items": {"gone": {"state": "ok"}}}, self.items)
        self.assertNotIn("gone", prog["items"])
        self.assertEqual(prog["items"]["full"]["state"], "ok")
        self.assertEqual(prog["items"]["zero"]["state"], "running")
        self.assertEqual(prog["summary"], {"ok": 1, "total": 4})

    def test_due_order_and_failed_skip(self):
        now = "2026-10-17T00:00:00+00:00"
        prog = ef.sync_progress({"items": {}}, self.items)
        self.assertEqual([i["name"] for i in ef.due(prog, self.items, now)], ["zero", "one", "brand"])   # 足りない枚数の多い順
        zero = next(i for i in self.items if i["name"] == "zero")
        prog["items"]["zero"].update(state="failed", failed_at="2026-10-16T22:00:00+00:00", material=ef.material(zero))
        self.assertEqual([i["name"] for i in ef.due(prog, self.items, now)], ["one", "brand"])   # 6 時間以内・材料が同じ失敗は飛ばす
        prog["items"]["zero"]["material"] = "old"   # 新しい記事・手がかりが来た
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])
        prog["items"]["zero"].update(material=ef.material(zero), failed_at="2026-10-16T17:00:00+00:00")
        self.assertIn("zero", [i["name"] for i in ef.due(prog, self.items, now)])   # 6 時間たった

    def test_background_records_each_item(self):
        seen = []

        def fill(item, log):
            seen.append(item["name"])
            if item["name"] == "zero":
                raise RuntimeError("boom")
            if item["name"] == "one":
                item["emblem"] = [{}] * 6   # 目標に届いた
                return {"state": "ok", "note": "5 枚足した", "tried": {"Fandom": 5}}
            return {"state": "review", "note": "一覧で確かめる", "tried": {"Wikidata": 0}, "sheet": "/tmp/x.jpg"}
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["zero", "one", "brand"])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"]["zero"]["state"], "failed")   # 1 つの失敗で止まらない
        self.assertIn("failed_at", saved["items"]["zero"])
        self.assertEqual(saved["items"]["one"]["state"], "ok")
        self.assertEqual(saved["items"]["brand"]["state"], "review")
        self.assertEqual(saved["items"]["brand"]["tried"], {"Wikidata": 0})
        self.assertEqual(saved["last_run"]["done"], ["zero", "one", "brand"])
        self.assertTrue(saved["started"] and saved["last_run"]["end"])
        self.assertEqual(prog["summary"], {"ok": 2, "total": 4})
        # 2 回目：失敗したものは飛ばし、開始時刻は最初のまま
        seen.clear()
        again = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["brand"])
        self.assertEqual(again["started"], saved["started"])
        log = runlog.recent(50)
        self.assertTrue(all(r["proc"] == "emblem" for r in log))
        texts = [r["text"] for r in log]
        self.assertTrue(any(t.startswith("開始：予算 40 分・1 本並列・待ち 3 版面") for t in texts))
        self.assertTrue(any(t.startswith("zero：失敗") for t in texts))
        self.assertEqual(next(r for r in log if r["text"].startswith("one：")).get("level"), "ok")

    def test_background_stops_when_out_of_time(self):
        seen = []

        def fill(item, log):
            seen.append(item["name"])
            raise ef.OutOfTime("x")
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=1)
        self.assertEqual(seen, ["zero"])   # 途中で止めたら次に入らない
        self.assertEqual(prog["items"]["zero"]["state"], "running")
        self.assertNotIn("failed_at", prog["items"]["zero"])   # 失敗ではないので次の回にすぐやり直す

    def test_background_parallel(self):
        import threading
        import time as _t
        live, peak, lock = [0], [0], threading.Lock()

        def fill(item, log):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            _t.sleep(0.2)
            with lock:
                live[0] -= 1
            return {"state": "review", "note": item["name"]}
        prog = ef.background(40, log=lambda m: None, fill=fill, path=self.path, workers=3)
        self.assertEqual(peak[0], 3)   # 3 つ同時に動いた
        self.assertEqual(sorted(prog["last_run"]["done"]), ["brand", "one", "zero"])
        self.assertEqual(prog["last_run"]["workers"], 3)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual({n: x["note"] for n, x in saved["items"].items() if n != "full"}, {"zero": "zero", "one": "one", "brand": "brand"})
        self.assertTrue(any("3 本並列" in r["text"] for r in runlog.recent(10)))

    def test_throttle_shared_between_threads(self):
        import threading
        calls = []
        orig = ef._orig_get
        ef._orig_get = lambda url, limit=0: calls.append(_now()) or b"{}"
        try:
            import time as _t
            _now = _t.time
            ts = [threading.Thread(target=ef._throttled_get, args=("https://xx.wikipedia.org/a",)) for _ in range(3)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        finally:
            ef._orig_get = orig
        calls.sort()
        self.assertGreaterEqual(calls[2] - calls[0], 2.4)   # 3 本同時でも 1.3 秒おき

    def test_background_respects_budget(self):
        t = [0.0]

        def clock():
            return t[0]

        def fill(item, log):
            t[0] += 30 * 60   # 1 つに 30 分かかる
            return {"state": "review", "note": ""}
        prog = ef.background(40, log=lambda m: None, fill=fill, clock=clock, path=self.path, workers=1)
        self.assertEqual(prog["last_run"]["done"], ["zero", "one"])   # 30 分後（残り 10 分）は 2 つ目に入り、60 分後は入らない


class Identity(unittest.TestCase):
    """face_id.same_person の論理だけ確かめる（モデルなしで、特徴量の代わりに数を使う）。"""

    def setUp(self):
        self._eng, self._sim = face_id.engine, face_id.similarity
        face_id.engine = lambda: ("det", "rec")
        face_id.similarity = lambda a, b: 1.0 if a == b else 0.0

    def tearDown(self):
        face_id.engine, face_id.similarity = self._eng, self._sim

    def test_anchor_keeps_matching_only(self):
        # 0 が代表画像。顔なし（None）と別人（2）は落とす
        self.assertEqual(face_id.same_person([1, 1, None, 2, 1], anchor=0), {0, 1, 4})

    def test_majority_when_anchor_is_wrong(self):
        # 代表画像（0）だけ別の顔：同じ顔が多い方を本人とする
        self.assertEqual(face_id.same_person([9, 1, 1, 1], anchor=0), {1, 2, 3})

    def test_no_faces(self):
        self.assertEqual(face_id.same_person([None, None]), set())

    def test_unavailable_engine(self):
        face_id.engine = lambda: None
        self.assertIsNone(face_id.same_person([1, 1]))


class Processes(unittest.TestCase):
    def test_flows_are_well_formed(self):
        ids = [p["id"] for p in processes.PROCESSES]
        self.assertEqual(len(ids), len(set(ids)))
        for p in processes.PROCESSES:
            self.assertIn(p["lane"], processes.LANES)
            self.assertTrue(p["flow"], p["id"])
            for n in p["flow"]:
                self.assertIn(n["kind"], ("step", "decision", "fan", "store", "table"), p["id"])
                self.assertIn(n.get("lane"), processes.LANES, (p["id"], n["id"]))
                if n["kind"] == "decision":
                    self.assertTrue(n.get("no"), (p["id"], n["id"]))   # はい = 下へ続く、いいえ = 右の箱
                if n["kind"] == "fan":
                    self.assertTrue(all(len(x) in (3, 4) for x in n["items"]))
                    for x in n["items"][3:4] and [it[3] for it in n["items"] if len(it) == 4]:
                        self.assertIn(x, processes.COMPONENTS, (p["id"], n["id"]))
                for c in n.get("uses", []):
                    self.assertIn(c, processes.COMPONENTS, (p["id"], n["id"]))
            for c in p.get("uses", []):
                self.assertIn(c, processes.COMPONENTS, p["id"])
                if n["kind"] == "table":
                    self.assertTrue(all(len(x) == 2 for x in n["rows"]))

    def test_architecture(self):
        out = processes.render()
        ids = set()
        for z in processes.ARCH:
            for n in z["nodes"]:
                ids.add(n["id"])
                ids |= {f"p-{x}" for x in n.get("subs", [])}
                if n.get("proc"):
                    self.assertIn(n["proc"], {p["id"] for p in processes.PROCESSES})
                for c in n.get("uses", []):
                    self.assertIn(c, processes.COMPONENTS, n["id"])
        for n, a, b, t, c in processes.EDGES:   # 矢印の両端は図の部品・色は凡例にあるもの
            self.assertIn(a, ids)
            self.assertIn(b, ids)
            self.assertIn(c, processes.EDGE_JA)
        self.assertEqual([x[0] for x in processes.EDGES], list(range(1, len(processes.EDGES) + 1)))
        shown = {p["id"] for p in processes.PROCESSES if f'data-open="proc-{p["id"]}"' in out}
        self.assertEqual(shown, {p["id"] for p in processes.PROCESSES})   # 全部のプロセスが図から開ける
        self.assertIn('id="arch-edges"', out)
        for c in processes.COMPONENTS.values():   # モデル・アルゴリズムは名前と数字つき
            self.assertTrue(c["name"] and c["kind"] in processes.KIND_LABEL)
        for name in ("rembg birefnet-general-lite", "YuNet", "SFace", "FASTOCTREE", "話題度 6 次元"):
            self.assertIn(name, out)
        d = processes.flow_diagram(next(p for p in processes.PROCESSES if p["id"] == "emblem-cron"))
        edges = json.loads(d.split('id="dge-emblem-cron">')[1].split("</script>")[0])
        self.assertTrue(any(x[3] == "いいえ" and x[5] for x in edges))   # 判断のいいえは破線の枝
        self.assertIn("dn-dec", d)
        self.assertIn("dn-fan", d)
        try:   # ARCH に置いていない新しい仕組みも「そのほか」から開ける
            processes.PROCESSES.append({"id": "zz", "name": "新しい仕組み", "en": "ZZ", "lane": "web", "trigger": "t", "summary": "s",
                                        "flow": [{"id": "a", "kind": "step", "lane": "web", "title": "x"}]})
            out2 = processes.render()
        finally:
            processes.PROCESSES.pop()
        self.assertIn('data-open="proc-zz"', out2)
        self.assertIn("そのほかの仕組み", out2)

    def test_render_and_escape(self):
        evil = [{"id": "x", "name": "<b>x</b>", "en": "X", "lane": "ai", "trigger": "t", "summary": "s",
                 "flow": [{"id": "n", "kind": "step", "lane": "ai", "title": "<script>", "text": "&"}]}]
        out = processes.render(evil)
        self.assertNotIn("<script>", out)
        self.assertNotIn("<b>x</b>", out)
        self.assertIn('id="proc-x"', out)

    def test_admin_page_has_processes_and_emblems(self):
        rows = [{"name": "A", "section": "游戏", "emblem": {"kind": "group", "kind_ja": "グループ", "have": 2, "target": 5, "hi": 10,
                                                          "lo": 3, "state": "low", "skip": False, "shapes": {"切り抜き": 2}}}]
        out = render.render_admin({"pipeline": {}, "items": rows, "votes": {}}, {}, "u")
        for p in processes.PROCESSES:
            self.assertIn(f'data-open="proc-{p["id"]}"', out)
        self.assertIn('id="emblems"', out)
        self.assertIn("順番待ち", out)   # 進捗にまだないものは「進行中（順番待ち）」

    def test_admin_emblem_progress(self):
        rows = [{"name": "A", "section": "游戏", "emblem": {"kind": "group", "kind_ja": "グループ", "have": 2, "target": 5, "hi": 10,
                                                          "lo": 3, "state": "low", "skip": False, "shapes": {}}},
                {"name": "B", "section": "游戏", "emblem": {"kind": "brand", "kind_ja": "ブランド", "have": 1, "target": 1, "hi": 1,
                                                          "lo": 1, "state": "ok", "skip": False, "shapes": {}}}]
        run = {"ok": 1, "total": 2, "started": "10/16 08:00", "last_run": "10/17 06:00", "minutes": 40, "done": 1,
               "items": {"A": {"state": "review", "note": "<残り> 3 枚", "at": "10/17 06:10"}, "B": {"state": "ok", "note": "", "at": None}}}
        out = render.render_admin({"pipeline": {}, "items": rows, "votes": {}, "emblem_run": run}, {}, "u")
        self.assertIn("<b>1</b> / 2 版面が目標に到達", out)
        self.assertIn('aria-valuenow="1"', out)
        self.assertIn("width:50%", out)
        self.assertIn('class="em-review">要確認', out)
        self.assertIn("&lt;残り&gt; 3 枚", out)   # 結果の文は転義する
        self.assertIn("10/17 06:00", out)
        em = out[out.index('id="emblems"'):]
        self.assertLess(em.index(">A<"), em.index(">B<"))   # 要確認が上



class Backend(unittest.TestCase):
    """管理ページ「バックグラウンド」：次の実行（定時）と、版面 × プロセスの表。"""

    def test_runlog_keeps_recent_per_proc(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            for i in range(runlog.KEEP + 5):
                runlog.add("collect", f"c{i}", log_dir=d)
            runlog.add("emblem", "e", "warn", log_dir=d)
            self.assertEqual(len(runlog.load("collect", d)), runlog.KEEP)
            self.assertEqual(runlog.load("collect", d)[-1]["text"], f"c{runlog.KEEP + 4}")
            rows = runlog.recent(3, d)
            self.assertEqual(len(rows), 3)
            self.assertEqual({r["proc"] for r in rows} <= {"collect", "emblem"}, True)
            self.assertEqual(next(r for r in runlog.recent(100, d) if r["proc"] == "emblem")["name"], "小元素の自動補完")

    def test_slots(self):
        by = {p["id"]: p for p in processes.PROCESSES}
        self.assertEqual(processes.slots(by["edit"]), [[4, 43], [15, 43]])
        self.assertEqual(processes.slots(by["emblem"]), processes.slots(by["edit"]))   # 選定は AI 編集の回に
        self.assertEqual(len(processes.slots(by["collect"])), 12)
        self.assertEqual(processes.slots(by["render"]), [])
        for p in processes.PROCESSES:
            for h, m in processes.slots(p):
                self.assertTrue(0 <= h < 24 and 0 <= m < 60, p["id"])

    def test_cells(self):
        import digest
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "2026-10-17.json").write_text(json.dumps({"items": [{"name": "A", "entries": [{}] * 3},
                                                                     {"name": "B", "entries": [{}] * 2}]}), encoding="utf-8")
            (d / "2026-10-17.edit.json").write_text(json.dumps({"_covered": {"A": 3, "B": 1}}), encoding="utf-8")
            old = digest.INBOX_DIR
            digest.INBOX_DIR = d
            try:
                items = [{"name": "A", "motif": "m", "theme": {"bg": "#000"}}, {"name": "B"}, {"name": "C", "motif": "m", "theme": {"bg": "#000"}}]
                rows = [{"name": n, "emblem": {"state": st, "have": h, "target": 6}} for n, st, h in
                        (("A", "ok", 6), ("B", "low", 2), ("C", "low", 1))]
                run = {"items": {"C": {"state": "review"}}, "queue": ["B"]}
                digest.backend_cells(items, rows, d / "2026-10-17.json", run)
            finally:
                digest.INBOX_DIR = old
        a, b, c = (r["bg"] for r in rows)
        self.assertEqual((a["collect"]["state"], a["edit"]["state"], a["design"]["state"], a["emblem"]["state"]), ("ok", "ok", "ok", "ok"))
        self.assertEqual(b["edit"], {"state": "wait", "text": "新しい 1 件が待ち"})
        self.assertEqual(b["design"]["state"], "wait")
        self.assertIn("順番 1 番目", b["emblem"]["text"])
        self.assertEqual((c["collect"]["state"], c["edit"]["state"], c["emblem"]["state"]), ("idle", "idle", "review"))

    def test_render(self):
        bg = {k: {"state": "wait", "text": "<x>"} for k in ("collect", "edit", "design", "emblem")}
        rows = [{"name": "A", "section": "游戏", "bg": bg}, {"name": "B", "section": "好物", "bg": {**bg, "emblem": {"state": "failed", "text": ""}}}]
        todo = {"gate": {"text": "小元素 2 版面を Python で", "items": ["<A>", "B"]}}
        log = [{"when": "10/17 08:40", "proc": "emblem", "name": "小元素の自動補完", "level": "error", "text": "<b>x</b>"}]
        out = render._admin_backend(rows, todo, log)
        self.assertIn('class="nxs"', out)
        self.assertIn('id="bgq"', out)
        self.assertIn('class="lg-error"', out)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", out)
        cfg = json.loads(out.split('id="bg-cfg">')[1].split("</script>")[0])
        self.assertEqual(next(x for x in cfg if x["id"] == "gate")["items"], ["<A>", "B"])   # JS が textContent で入れる
        self.assertTrue(all(x["slots"] for x in cfg))
        self.assertIn('class="pbar"', out)
        self.assertIn('class="lims"', out)
        self.assertIn('class="aiu"', out)
        self.assertIn('id="livenow"', out)   # いま動いているもの（live_status を 30 秒ごと）
        for job in ("background", "collect", "render"):   # 今すぐ実行（db/run_now.sql の job と同じ名前）
            self.assertIn(f'data-run="{job}"', out)
        sql = (ROOT / "db" / "run_now.sql").read_text(encoding="utf-8")
        for job in set(render.RUN_JOBS.values()):
            self.assertIn(f"when '{job}'", sql)
        for t, k, _ in processes.AI_TASKS:
            self.assertIn(k, processes.AI_STATE_JA)
        for name, _, _ in processes.LIMITS:
            self.assertIn(name, out)
        self.assertIn("まだ記録がありません", render._admin_backend(rows))
        for p in processes.PROCESSES:   # 定時か Actions で動くものは「次の実行」に出る（AI 編集と同じ回のものは出さない）
            shown = f'data-open="proc-{p["id"]}"' in out
            self.assertEqual(shown, not isinstance(p.get("schedule"), str) and bool(processes.slots(p) or p.get("workflow")), p["id"])
        self.assertIn('data-wf="digest.yml"', out)
        self.assertIn("&lt;x&gt;", out)
        self.assertNotIn("<x>", out)
        self.assertIn('class="bgc s-failed"', out)
        self.assertLess(out.index("ゲーム"), out.index("グッズ"))   # 板块の順
        page = render.render_admin({"pipeline": {}, "items": rows, "votes": {}}, {}, "u")
        self.assertIn('id="backend"', page)
        self.assertLess(page.index('id="backend"'), page.index('id="procs"'))



class Resources(unittest.TestCase):
    """リソース：サーバーの様子・容量・トークン（管理ページ「バックグラウンド → リソース」）。"""

    def test_snapshot(self):
        import resources
        x = resources.snapshot()
        self.assertGreaterEqual(x["cpu"], 1)
        self.assertEqual(x["disk_total"], x["disk_used"] + x["disk_free"])   # マシン全体ではなく、使える分
        for k in ("mem_total", "mem_free", "disk_total", "disk_free", "peak"):
            self.assertIn(k, x)
            self.assertGreater(x[k], 0)
        self.assertLessEqual(x["mem_free"], x["mem_total"])

    def test_sizes(self):
        import resources
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "docs" / "emblems").mkdir(parents=True)
            (d / ".git").mkdir()
            (d / "docs" / "a.html").write_bytes(b"x" * 100)
            (d / "docs" / "emblems" / "b.webp").write_bytes(b"x" * 50)
            (d / ".git" / "big").write_bytes(b"x" * 1000)   # .git は数えない
            sz = resources.repo_sizes(d)
        self.assertEqual((sz["repo"], sz["pages"], sz["emblems"]), (150, 150, 50))

    def test_render(self):
        G = 1024 ** 3
        res = {"sizes": {"repo": 900 * 1024 ** 2, "pages": 100 * 1024 ** 2, "emblems": 5 * 1024 ** 2, "inbox": 1, "state": 1},
               "limits": {"repo": G, "pages": G},
               "runs": {"emblem": {"name": "小元素の自動補完", "when": "10/17 09:40", "secs": 2400, "workers": 4,
                                   "res": {"cpu": 4, "load": 3.1, "mem_total": 16 * G, "mem_free": 3 * G, "peak": 13 * G,
                                           "disk_used": 11 * G, "disk_total": 40 * G, "disk_free": 29 * G}}},
               "tokens": {"edit": {"name": "AI 編集", "last": 12345, "week": 50000, "runs": 4},
                          "collect": {"name": "<収集>", "last": None, "week": 0, "runs": 0}}}
        out = render._admin_resources(res)
        self.assertIn('class="mt warn"', out)   # リポジトリ 88% は赤
        self.assertEqual(out.count('class="mt warn"'), 2)   # メモリのピーク 81% も赤・ディスク 28% は赤にしない
        self.assertIn("<b>11.00 GB</b> / 40.00 GB", out)
        self.assertIn("40 分 0 秒", out)
        self.assertIn("4 本並列", out)
        self.assertIn("12,345", out)
        self.assertIn("未記録", out)
        self.assertIn("&lt;収集&gt;", out)
        self.assertIn("claude.ai/settings/usage", out)
        self.assertEqual(render._admin_resources(None), "")

    def test_runlog_cli_attaches_snapshot(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code = ("import sys,pathlib;sys.path.insert(0,'scripts');import runlog;runlog.LOG_DIR=pathlib.Path(sys.argv[1]);"
                    "sys.argv=['runlog','emblem','テスト','--tokens','1234'];runlog.main()")
            subprocess.run([sys.executable, "-c", code, d], cwd=ROOT, check=True)
            row = runlog.load("emblem", pathlib.Path(d))[-1]
        self.assertEqual(row["tokens"], 1234)
        self.assertIn("mem_total", row["res"])


if __name__ == "__main__":
    unittest.main()


class EmblemDetail(unittest.TestCase):
    """管理ページ「小元素の探し方」：取り方の順・次の回・助言・図。"""

    def test_source_chain_matches_gather(self):
        chain = [s for s, _ in ef.source_chain({"type": "event", "emblem_kind": "group"})]
        self.assertNotIn("Wikidata", chain)   # グループは Wikidata を使わない（gather は本人だけ）
        self.assertEqual(dict(ef.source_chain({"type": "game"}))["Fandom"], True)
        self.assertEqual(dict(ef.source_chain({"type": "game"}))["Wikipedia"], False)   # 絵のキャラは目視だけ
        self.assertEqual(dict(ef.source_chain({"type": "event"}))[ef.WEB], False)

    def test_detail_retry_and_advice(self):
        import datetime as dt
        import digest
        item = {"name": "G", "type": "event", "emblem_kind": "group", "emblem_who": ["a", "b", "c"]}
        failed = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat(timespec="seconds")
        d = digest.emblem_detail(item, {"tried": {"Wikipedia": 1, "Wikimedia Commons": 22}, "failed_at": failed, "at": failed,
                                        "note": "x"}, "failed", [], "Asia/Tokyo")
        self.assertTrue(d["todo"].endswith("以降に再挑戦") or "新しい記事" in d["todo"])
        self.assertIn("emblem_urls", d["advice"])   # Wiki に記事がないグループ → 公式の写真を
        self.assertEqual(d["why"], "メンバー 3 人")
        self.assertEqual([c["n"] for c in d["chain"]][:3], [None, 1, 22])
        brand = digest.emblem_detail({"name": "B", "type": "product"}, {"tried": {"Wikidata": 0}, "at": failed}, "failed", [], "Asia/Tokyo")
        self.assertIn("P154", brand["advice"])
        ok = digest.emblem_detail({"name": "K", "type": "game", "emblem": [{}] * 6}, {}, "ok", [], "Asia/Tokyo")
        self.assertEqual(ok["advice"], "")

    def test_flow_render(self):
        d = {"kind": "グループ", "why": "<m>", "target": 9, "have": 0, "lo": 3, "hi": 10, "faces": True, "rejects": 2,
             "chain": [{"src": "直接指定", "auto": True, "n": None}, {"src": "Wikipedia", "auto": True, "n": 0},
                       {"src": "Wikimedia Commons", "auto": True, "n": 22}, {"src": "Web 画像検索", "auto": False, "n": 8}],
             "funnel": {"found": 30, "usable": 4, "auto": 0, "review": 4}, "note": "n", "at": "10/17", "todo": "次", "advice": "a"}
        out = render._emblem_flow(d, "failed")
        self.assertIn("ef-st-failed", out)
        self.assertIn('class="ef-na"', out)
        self.assertIn('class="ef-zero"', out)
        self.assertIn('class="ef-got"', out)
        self.assertIn("ef-eye", out)   # Web は目視だけ
        self.assertIn("SFace", out)
        self.assertIn("目で外した 2 枚", out)
        self.assertIn("集めた <b>30</b>", out)
        self.assertIn("&lt;m&gt;", out)
        self.assertNotIn("<m>", out)


class Ladder(unittest.TestCase):
    """取り方の段：① 標準 → ② 名前を広げる → ③ 公式・記事のページ を、届くまで同じ回の中で上がる。"""

    def setUp(self):
        self.saved = {k: getattr(ef, k) for k in ("gather", "gather_wide", "gather_pages", "check", "auto_pick", "commit", "load_items", "_live")}
        self.items = [{"name": "X", "type": "game", "emblem_who": ["a", "b"], "emblem": []}]
        ef.load_items = lambda: self.items
        ef._live = lambda *a, **k: None
        ef.check = lambda cands, log, **k: cands
        ef.auto_pick = lambda item, good, **k: list(range(1, len(good) + 1))

        def commit(item, good, picks, log=print):
            self.items[0]["emblem"] = self.items[0]["emblem"] + [{"subject": good[n - 1]["subject"], "image": good[n - 1]["image"]} for n in picks]
        ef.commit = commit
        self.calls = []

        def make(label, rows):
            def fn(item, log, tried):
                self.calls.append(label)
                tried[label] = len(rows)
                return [{"subject": s, "image": f"{label}-{s}", "source": "Fandom"} for s in rows]
            return fn
        ef.gather, ef.gather_wide, ef.gather_pages = make("1", ["a"]), make("2", ["b"]), make("3", [])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(ef, k, v)

    def test_climbs_until_ok(self):
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(self.calls, ["1", "2"])   # ②で目標（2 人）に届いたので ③ は試さない
        self.assertEqual(r["state"], "ok")
        self.assertEqual([x["added"] for x in r["steps"]], [1, 1])

    def test_all_steps_then_failed_with_material(self):
        ef.gather_wide = lambda item, log, tried: self.calls.append("2") or []
        r = ef.fill_one(self.items[0], log=lambda m: None)
        self.assertEqual(self.calls, ["1", "2", "3"])
        self.assertEqual(r["state"], "failed")
        self.assertTrue(r["material"])
        self.assertIn("新しい記事が来たらすぐ", r["note"])


class Gate(unittest.TestCase):
    """後台のゲート：仕事があるか・AI が要るかをプログラムだけで決める（scripts/gate.py）。"""

    def setUp(self):
        import tempfile
        import gate
        self.gate = gate
        self.dir = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.dir.name)
        self.state = self.d / "gate.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_edit_work(self):
        (self.d / "2026-10-17.json").write_text(json.dumps({"items": [{"name": "A", "entries": [{}] * 3},
                                                                  {"name": "B", "entries": [{}] * 2}]}), encoding="utf-8")
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-17"), {"A": 3, "B": 2})   # edit.json なし = 全部未編集
        (self.d / "2026-10-17.edit.json").write_text(json.dumps({"_covered": {"A": 3, "B": 1}}), encoding="utf-8")
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-17"), {"B": 1})
        self.assertEqual(self.gate.edit_work(self.d, today="2026-10-18"), {})   # 今日の inbox がない

    def test_photo_work(self):
        (self.d / "photos").mkdir()
        (self.d / "photos" / "7.json").write_text("{}", encoding="utf-8")
        (self.d / "photos" / "7.jpg").write_bytes(b"x")
        self.assertEqual(self.gate.photo_work(self.d), ["7"])

    def test_fire_only_with_work_token_and_new_sig(self):
        calls = []
        post = lambda url, token: calls.append((url, token)) or 200
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1"}, "photos": {"need": False, "sig": "p"}}}, self.state)
        res = self.gate.fire(self.state, post=post, env={})
        self.assertEqual(res["edit"], "トークン未設定（定時を待つ）")
        self.assertEqual(res["photos"], "仕事なし（起こさない）")
        self.assertEqual(calls, [])
        res = self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})
        self.assertEqual(res["edit"], "Claude を起こした")
        self.assertIn("trig_01Ly92RcW35cBwZ9amWZr11j", calls[0][0])
        res = self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})
        self.assertEqual(res["edit"], "同じ仕事で起こし済み")   # 同じ指紋では 2 回起こさない
        self.assertEqual(len(calls), 1)
        data = self.gate.load(self.state)
        data["jobs"]["edit"]["sig"] = "s2"   # 新しい記事が来た
        self.gate.save(data, self.state)
        self.assertEqual(self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})["edit"], "Claude を起こした")

    def test_fire_failure_is_recorded(self):
        def post(url, token):
            raise RuntimeError("403")
        self.gate.save({"jobs": {"edit": {"need": True, "sig": "s1"}}}, self.state)
        self.assertTrue(self.gate.fire(self.state, post=post, env={"ROUTINE_TOKEN_EDIT": "t"})["edit"].startswith("起こせなかった"))


class Rules(unittest.TestCase):
    """前は Claude が目で見ていた判断を、数で決める規則。"""

    def test_photo_problem(self):
        self.assertEqual(face_id.photo_problem({"faces": 0}), "顔なし")
        self.assertEqual(face_id.photo_problem({"faces": 1, "ratio": 0.05, "second": 0}), "遠景")
        self.assertEqual(face_id.photo_problem({"faces": 2, "ratio": 0.3, "second": 0.8}), "何人も写っている")
        self.assertIsNone(face_id.photo_problem({"faces": 2, "ratio": 0.3, "second": 0.2}))   # 後ろに小さく写っているのはよい

    def test_strict_identity(self):
        old = (face_id.engine, face_id.similarity)
        face_id.engine = lambda: ("det", "rec")
        face_id.similarity = lambda a, b: 1.0 if a == b else 0.0
        try:
            self.assertEqual(face_id.same_person([5], None, strict=True), set())   # 基準なしで 1 枚 = 本人と言えない
            self.assertEqual(face_id.same_person([5, 5], None, strict=True), {0, 1})
            self.assertEqual(face_id.same_person([5], None), {0})   # 手動のときは前のまま
            self.assertEqual(face_id.same_person([5], 0, strict=True), {0})   # 記事の代表画像（基準）だけ = 本人（前は「別人」にしていた）
            self.assertEqual(face_id.same_person([5, 7], 0, strict=True), {0})   # 基準と違う顔は落とす
        finally:
            face_id.engine, face_id.similarity = old

    def test_hole_share(self):
        import emblem
        import numpy as np
        solid = np.zeros((100, 100), bool)
        solid[20:100, 20:80] = True
        self.assertEqual(emblem.hole_share(solid), 0.0)
        solid[70:100, 40:60] = False   # 服の下の方が抜けた（下の端につながる穴）
        self.assertGreater(emblem.hole_share(solid), emblem.HOLE_MAX)
