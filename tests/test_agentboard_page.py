"""AgentBoard の画面（docs/board/index.html，HARNESS_V2.md「AgentBoard」）。

前の PC の AgentBoard（端末風・参考画像「CLAUDE CODE SUBAGENT TIP」）と同じ作りで、PC とクラウドの機械ごとの 1 枚（枝 live-*）を合わせて出す。
公開の Pages に置くので、ページ自体にデータ・鍵を入れない／令牌はこの端末の localStorage だけ。
GitHub の API は Playwright で差し替え、本物と同じ形の応答で「読む・合わせる・伝言を送る・令牌が切れたら貼り直し」を確かめる。"""
import json
import pathlib
import re
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "board" / "index.html"


class Static(unittest.TestCase):
    def setUp(self):
        self.t = PAGE.read_text(encoding="utf-8")

    def test_no_secret_or_private_data(self):
        self.assertIsNone(re.search(r"(?:github_pat|ghp|gho|ghs)_\w{20,}", self.t))
        self.assertIsNone(re.search(r"[\w.+-]+@(?!users\.noreply)[\w-]+\.[a-z]{2,}", self.t))   # メールを書かない
        self.assertNotIn("elegy.tailc8cfff", self.t)          # 前の PC の網址・k= の鍵を残さない
        self.assertIn('name="robots" content="noindex', self.t)

    def test_token_only_to_github(self):
        self.assertIn("localStorage.getItem(KEY)", self.t)
        for host in re.findall(r"https://([\w.-]+)/", self.t):
            self.assertIn(host, {"api.github.com", "github.com", "claude.ai", "fonts.googleapis.com", "fonts.gstatic.com", "example.com"}, host)

    def test_live_branches_query(self):
        # refPrefix は「/」で終わる形だけ（live- を付けた形は GitHub が受け付けないことがある）。名前で絞るのは query
        self.assertIn('refs(refPrefix:"refs/heads/",query:"live-"', self.t)

    def test_same_parts_as_old_board(self):
        for s in ("OPUS 5.5", "advisor", "BRAIN · ", "HARNESS · routing", "delegate to subagents", "back to lead — review + verify",
                  "session log", "<legend>site</legend>", "owner → brain · inbox", "~/agentboard $"):
            self.assertIn(s, self.t, s)


def host(kind, name, now, agents, brain_model="Fable 5.2", **kw):
    h = {"v": 1, "host": name, "kind": kind, "at": "x", "ts": now - 20,
         "brain": {"session": "abcd1234", "model": brain_model, "fam": "fable", "action": "計画を書く", "quiet": 0.5, "active": True},
         "agents": agents, "older_done": 2, "events": [{"t": now - 60, "label": agents[0]["label"] if agents else "BRAIN", "fam": "sonnet", "text": "書き換える：scripts/render.py", "err": False}],
         "models": {"sonnet": 2, "haiku": 1}, "opus": {"calls": 0, "tokens": 0, "active": False, "recent": []}, "pending": [], "route": None, "site": None, "harness": None}
    h.update(kw)
    return h


def ag(label, model, fam, status, now, quiet=1, **kw):
    a = {"label": label, "model": model, "fam": fam, "tools": 10, "tok": 1000, "t0": now - 900, "t1": now - quiet * 60, "min": 15, "quiet": quiet,
         "action": "コマンド：テストを流す", "result": "", "pr": "", "status": status, "source": "agent", "run": ""}
    a.update(kw)
    return a


class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest("playwright なし")
        import sys
        sys.path.insert(0, str(ROOT / "harness"))
        from browser import launch          # 点検は共通の launch（tests/test_browser_guard）
        cls.pw = sync_playwright().start()
        cls.b = launch(cls.pw)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()
        cls.pw.stop()

    def open(self, w, h, q="?demo", token=None, gql=None, put=None):
        ctx = self.b.new_context(viewport={"width": w, "height": h}, reduced_motion="reduce")   # 中身の試験は動きなしで（字が打ち終わるのを待たない）
        p = ctx.new_page()
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
        if gql:
            p.route("https://api.github.com/graphql", gql)
        if put:
            p.route(re.compile(r"https://api\.github\.com/repos/.*/contents/.*"), put)
        if token:
            p.add_init_script("localStorage.setItem('agentboard.token', %s)" % json.dumps(token))
        p.goto(PAGE.as_uri() + q)
        p.wait_for_timeout(400)
        return p, errs

    def test_demo_1440_same_layout_as_old(self):
        p, errs = self.open(1440, 900)
        self.assertEqual(errs, [])
        m = p.evaluate("""()=>({sw:document.documentElement.scrollWidth,ag:document.querySelectorAll('#agents .ag').length,
          stuck:document.querySelectorAll('#agents .ag.stuck').length,pc:[...document.querySelectorAll('#agents .md small')].filter(e=>/pc/.test(e.textContent)).length,
          cloud:[...document.querySelectorAll('#agents .md small')].filter(e=>/cloud/.test(e.textContent)).length,log:document.querySelectorAll('#log .r').length,
          advLeft:document.getElementById('adv').getBoundingClientRect().right<=document.getElementById('lead').getBoundingClientRect().left})""")
        self.assertEqual(m["sw"], 1440)                       # 横はみ出し 0
        self.assertEqual(m["ag"], 7)
        self.assertEqual(m["stuck"], 1)                       # 15 分 記録なし＝赤
        self.assertGreater(m["pc"], 0)
        self.assertGreater(m["cloud"], 0)                     # PC とクラウドの係が同じ並びに
        self.assertGreaterEqual(m["log"], 10)
        self.assertTrue(m["advLeft"])                         # advisor は左の縦の列
        # いまの Claude：会話ごとに状態・最後に頼んだこと・いまの道具。押すと流れが開く
        rows = p.locator("#now .card")
        self.assertEqual(rows.count(), 6)
        self.assertEqual(p.locator("#now .card.st-working").count(), 2)
        for cls in ("st-ask", "st-quiet", "st-yours", "st-idle"):
            self.assertEqual(p.locator("#now .card." + cls).count(), 1, cls)
        # 札：枠の色＝モデル・大きなモデル名・30 分の棒グラフ・動いている係のチップ
        self.assertIn("b-opus", rows.first.get_attribute("class"))
        self.assertEqual(rows.first.locator(".mdl b").inner_text(), "OPUS 5.5")
        self.assertEqual(rows.first.locator(".spark i").count(), 30)
        harness = p.locator("#now .card", has_text="ハーネス v2")
        self.assertEqual(harness.locator(".chip").count(), 2)
        self.assertEqual(harness.locator(".chip.stuck").count(), 1)               # 19 分 動かない Haiku の係は赤
        self.assertIn("Fable 1", p.inner_text("#nowmix"))
        first = rows.first
        self.assertIn("作業中", first.inner_text())
        self.assertTrue(first.locator(".tl").is_hidden())
        first.locator(".ttl").click()
        self.assertTrue(first.locator(".tl").is_visible())
        self.assertIn("道具がエラー", first.locator(".tl").inner_text())
        p.fill("#text", "見本の伝言")
        p.press("#text", "Enter")
        self.assertIn("見本の伝言", p.inner_text("#msgs"))
        p.close()

    def test_demo_390_stacks_without_overflow(self):
        p, errs = self.open(390, 844)
        self.assertEqual(errs, [])
        self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), 390)
        lead_y = p.evaluate("document.getElementById('lead').getBoundingClientRect().top")
        adv_y = p.evaluate("document.getElementById('adv').getBoundingClientRect().top")
        route_y = p.evaluate("document.getElementById('route').getBoundingClientRect().top")
        self.assertLess(lead_y, adv_y)                        # 390 では advisor を lead の下へ（前の画面と同じ）
        self.assertLess(adv_y, route_y)
        p.close()

    def test_live_reads_hosts_and_sends_owner_note(self):
        now = time.time()
        pc = host("pc", "pc", now, [ag("fix:T-0242", "Sonnet 5.5", "sonnet", "running", now), ag("check:T-0242", "Haiku 5.5", "haiku", "running", now, quiet=30)],
                  site={"main": {"sha": "abc1234", "t": now - 600, "msg": "出刊"}, "backlog": {"open": 7, "doing": 1, "ask": 2, "top": "写真の下の空き"}},
                  harness={"queue": {"open": 7, "claimed": 1, "waiting": 2}, "choices": [{"task": "T-0236", "question": "目次の色", "url": "https://example.com/c"}]})
        cl = host("cloud", "cloud-3136e785", now, [ag("写真の出どころ調べ", "Opus 5.5", "opus", "done", now, result="直すのは高さ")], brain_model="Opus 5.5",
                  sessions=[{"id": "3136e785", "project": "Wishlist", "title": "AgentBoard の会話", "model": "Opus 5.5", "fam": "opus", "state": "working",
                             "t1": now - 3, "turn_t0": now - 300, "turn_tools": 9, "action": "書き換える：docs/board/index.html", "prompt": "実時間で見えるように",
                             "said": "", "sub": 0, "link": "session_01Live", "events": [{"t": now - 3, "text": "書き換える：docs/board/index.html", "err": False}]}])
        old = host("pc", "pc", now - 3600, [], sessions=[{"id": "50b60877", "project": "Claude", "title": "古い PC の会話", "model": "Fable 5.2", "fam": "fable",
                                                         "state": "working", "t1": now - 3600, "turn_tools": 1, "action": "x", "prompt": "y", "said": "", "sub": 0, "events": []}])
        old["host"], old["ts"] = "pc-old", now - 3600              # 1 時間 届いていない機械
        cl["brain"].update(link="session_01Cloud", name="クラウドの主")          # ab.py whoami の名札
        seen = {"q": 0, "put": None}

        def gql(route):
            seen["q"] += 1
            body = json.loads(route.request.post_data or "{}").get("query", "")
            if "live:refs" not in body:      # 令牌の確かめ
                return route.fulfill(json={"data": {"ab": {"name": "agentboard"}}})
            node = lambda h: {"name": "live-" + h["host"], "target": {"committedDate": "x", "file": {"object": {"text": json.dumps(h, ensure_ascii=False)}}}}
            tree = lambda rows: {"entries": [{"name": f"{i}.json", "object": {"text": json.dumps(r, ensure_ascii=False)}} for i, r in enumerate(rows)]}
            route.fulfill(json={"data": {"ab": {"live": {"nodes": [node(pc), node(cl), node(old)]},
                                                "agents": tree([{"role": "主の会話", "task": "brain", "note": "伝言を読んだ", "where": "cloud", "status": "working", "ts": now - 60, "started": now - 600, "session": "session_01AbC"}]),
                                                "inbox": tree([{"t": 1, "text": "写真もっと大きく", "to": "both"}]), "outbox": tree([{"t": 2, "re": "1", "text": "了解", "who": "PC の BRAIN"}]), "pcsum": None},
                                         "wl": {"pullRequests": {"nodes": [{"number": 1111, "title": "直す", "state": "OPEN", "merged": False, "updatedAt": "x",
                                                                          "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "FAILURE"}}}]}}]}}}})

        def put(route):
            seen["put"] = json.loads(route.request.post_data)
            route.fulfill(status=201, json={})

        p, errs = self.open(1333, 677, q="", token="github_pat_" + "x" * 30, gql=gql, put=put)
        p.wait_for_timeout(300)
        self.assertEqual(errs, [])
        self.assertTrue(p.is_visible("#app"))
        txt = p.inner_text("#app")
        for s in ("fix:T-0242", "写真の出どころ調べ", "主の会話:brain", "#1111", "CI 赤", "abc1234", "了解", "目次の色", "pc", "cloud"):
            self.assertIn(s, txt, s)
        self.assertEqual(p.locator("#agents .ag.stuck").count(), 1)                    # 30 分 動かない Haiku
        self.assertEqual(p.locator("#agents a.open").count(), 1)                       # session_ の会話だけ「開く」
        self.assertIn("pc,cloud-3136e785", p.inner_text("#status"))
        now_rows = p.locator("#now .card")
        self.assertEqual(now_rows.count(), 2)
        self.assertIn("実時間で見えるように", now_rows.first.inner_text())                  # 最後に頼んだこと
        self.assertIn("書き換える：docs/board/index.html", now_rows.first.inner_text())     # いまの道具
        self.assertEqual(now_rows.first.locator("a.open").get_attribute("href"), "https://claude.ai/code/session_01Live")
        self.assertIn("届いていない", now_rows.nth(1).inner_text())                         # 止まった機械の会話は「作業中」と言わない
        self.assertIn("秒前に届いた", p.inner_text("#nowage"))
        conn = p.inner_text("#conn")                                                  # つながっている機械
        self.assertIn("● cloud-3136e785", conn)
        self.assertIn("○ pc-old", conn)
        self.assertIn("クラウドの主", p.inner_text("#lead"))                         # BRAIN の箱に会話の名前と「開く」
        self.assertEqual(p.locator("#lead a.open").get_attribute("href"), "https://claude.ai/code/session_01Cloud")
        p.fill("#text", "AgentBoard 見えた")
        p.press("#text", "Enter")
        p.wait_for_timeout(200)
        self.assertIsNotNone(seen["put"])
        import base64
        self.assertEqual(json.loads(base64.b64decode(seen["put"]["content"]).decode())["text"], "AgentBoard 見えた")
        p.close()

    def test_motion_effects(self):
        """React Bits の動き（DecryptedText・StarBorder・ShinyText・Micro Slats 風の棒・LetterGlitch）が動き、最後は正しい字になる"""
        ctx = self.b.new_context(viewport={"width": 1440, "height": 900})
        p = ctx.new_page()
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
        p.goto(PAGE.as_uri() + "?demo")
        p.wait_for_timeout(1600)
        self.assertEqual(errs, [])
        self.assertEqual(p.inner_text(".title b"), "AGENTBOARD")                         # 乱れた字から戻った
        card = p.locator("#now .card.st-working").first
        self.assertNotEqual(p.evaluate("e=>getComputedStyle(e,'::before').animationName", card.element_handle()), "none")   # 縁を光が走る
        self.assertEqual(card.locator(".shine").count(), 1)
        self.assertNotEqual(card.locator(".spark i").first.evaluate("e=>getComputedStyle(e).transform"), "")
        self.assertTrue(p.is_visible("#bgfx"))
        # もっと派手に：発車板（6 つの数がめくれる）・AGENTBOARD のずれ・更新の波紋・LIVE/DEMO の札・CRT の背景
        self.assertEqual(p.locator("#flaps .k").count(), 6)
        self.assertEqual(p.inner_text("#flaps [data-k=n] .v").replace("\n", ""), "06")
        self.assertEqual(p.get_attribute(".title .glitch", "data-text"), "AGENTBOARD")
        self.assertEqual(p.locator("#now .card .ring").count(), 6)
        self.assertEqual(p.inner_text("#livebadge"), "DEMO")
        bar_dots = p.locator(".bar i").first.bounding_box()
        live = p.locator("#livebadge").bounding_box()
        self.assertGreater(live["x"], bar_dots["x"] + 200)                              # LIVE の札は右（3 つの丸に重ならない）
        # 波：作業中は大きく流れる・選んでは橙・あなたの番は小さく・動きなしは赤い平らな線・休みは灰色の平らな線
        for state, mode in (("st-working", "run"), ("st-ask", "ask"), ("st-yours", "calm"), ("st-quiet", "dead"), ("st-idle", "idle")):
            w = p.locator("#now .card." + state + " .wave").first
            self.assertIn(mode, w.get_attribute("class"), state)
        self.assertNotEqual(p.locator("#now .card.st-working .wave svg").first.evaluate("e=>getComputedStyle(e).animationName"), "none")
        self.assertEqual(p.locator("#now .card.st-idle .wave svg").first.evaluate("e=>getComputedStyle(e).animationName"), "none")
        self.assertEqual(p.locator("#agents .ag.stuck .wave.dead").count(), 1)          # 止まった係は赤い平らな線
        self.assertGreaterEqual(p.locator("#agents .ag .wave.run").count(), 3)
        self.assertIn("run", p.get_attribute("#livewave", "class"))                     # データが届いている間、LIVE の波も動く
        self.assertGreater(p.locator("#livewave").bounding_box()["width"], 30)            # 小さな波に幅がある（mini を落とさない）
        ag = p.locator("#agents .ag.stuck").element_handle()
        # Magic UI：Animated Beam（動いている係・止まりの係へ線＝見本は 4 本）・Border Beam（選んでほしい札）・Animated List（記録の行）
        self.assertEqual(p.locator("#beams g").count(), 4)
        self.assertEqual(p.locator("#beams .glow.stuck").count(), 1)
        self.assertEqual(p.locator(".card.st-ask .bbeam").evaluate("e=>getComputedStyle(e).animationName"), "bspin")
        self.assertEqual(p.locator(".card.st-working .bbeam").first.evaluate("e=>getComputedStyle(e).display"), "none")
        self.assertGreaterEqual(p.locator("#log .r").count(), 10)
        # 5 秒ごとに読み直しても札は作り直さない（動きが始めからにならない）
        h = card.element_handle()
        p.evaluate("()=>{}")
        p.wait_for_timeout(5600)
        self.assertTrue(h.evaluate("e=>e.isConnected"))
        self.assertTrue(ag.evaluate("e=>e.isConnected"))                                   # 係の箱も作り直さない（波が始めに戻らない）
        ctx.close()

    def test_token_name_per_device(self):
        ctx = self.b.new_context(viewport={"width": 390, "height": 844},
                                 user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
        p = ctx.new_page()
        p.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
        p.goto(PAGE.as_uri())
        self.assertRegex(p.locator("#newtok").get_attribute("href"), r"name=agentboard-phone-\d{8}(&|$)")
        ctx.close()

    def test_setup_and_expired_token(self):
        p, errs = self.open(390, 844, q="")
        self.assertEqual(errs, [])
        self.assertTrue(p.is_visible("#setup"))
        href = p.locator("#setup a").first.get_attribute("href")                       # 令牌は 1 回で：作成ページに項目を入れて開く
        self.assertTrue(href.startswith("https://github.com/settings/personal-access-tokens/new?"))
        for kv in ("contents=write", "expires_in=366", "target_name=CxElegy"):
            self.assertIn(kv, href)
        self.assertRegex(href, r"name=agentboard-pc-\d{8}(&|$)")                       # 名前はこの端末用（同じ名前は GitHub で作れない）
        self.assertFalse(p.is_visible("#app"))
        p.fill("#tok", "abc")
        p.press("#tok", "Enter")
        self.assertIn("github_pat_", p.inner_text("#err"))
        p.close()
        p, errs = self.open(1333, 677, q="", token="github_pat_" + "y" * 30, gql=lambda r: r.fulfill(status=401, json={}))
        p.wait_for_timeout(300)
        self.assertTrue(p.is_visible("#setup"))                                         # 切れた令牌は外して貼り直し
        self.assertIn("令牌が使えません", p.inner_text("#err"))
        self.assertIsNone(p.evaluate("localStorage.getItem('agentboard.token')"))
        p.close()


if __name__ == "__main__":
    unittest.main()
