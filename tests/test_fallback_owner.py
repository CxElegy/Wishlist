"""お客さまの代わりの画面（本人のページが読めず ?own=0 で店長のページを絞った画面・AUTH_JS の showMine）に、
店長の数字・店長だけの中身を出さない（docs/rules/login.md L10「まだ使えないもの」、2026-11-19）。

小さな店長のページ（版面 A・B・C、欲しい物 2 件、話題度、予定）を render.render で作り、Supabase の呼び出しは page.route で
差し替えて（本番には 1 件も届かない）、ログイン中のお客さま（A だけ選んだ）・店長・访客で開く。ブラウザが無い環境では飛ばす。
  (1) 欲しい物の件数・今日の最高・更新の時刻・右の列（店長の欲しい物の名前・値段・予定）が見えない（display と文字の両方）
  (2) 選んでいない版面（B・C）の名前が見えている文字に無い（「気になるかも？」の候補は決まりどおり出してよいので除く）
  (3) LIVE_JS の知らせ（変わった版面の名前）が店長の版面の名前を出さない
  (4) 店長・访客では今までどおり全部出る
  (5) ?own=0 のまま開き直す（F5）と殻（me.html）をもう一度試す。自動の読み直し・跳ね返り 30 秒に 3 回では試さない"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "harness"))
import render  # noqa: E402

DB = "https://db.example.test"
WISH = [{"name": "店長の黒猫マグ", "price": 850, "currency": "NT$", "status": "想要"},
        {"name": "店長の白猫マグ", "price": 600, "currency": "NT$", "status": "纠结"}]
UPDATED = "11.19 12:34"
WORDS = ["trailer", "launch", "concert", "award", "patch", "season", "museum", "festival", "tour", "studio"]   # 記事ごとに違う語（_front_pick が同じ出来事と見て壁から外さない）
TH = {"bg": "#000", "fg": "#fff", "accent": "#f00", "alt_bg": "#fff", "alt_fg": "#000", "alt_accent": "#f00"}
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360f8cf000000030101005a4d6b7a0000000049454e44ae426082")


def build():
    def st(n, i, w="normal", ev=None):
        x = {"url": f"https://example.com/{n}/{i}", "headline": f"{n} {WORDS[i]} {WORDS[i + 5]}", "weight": w, "date": "2026-11-19",
             "_issue": "2026-11-19", "image": f"https://img.example.com/{n}{i}.jpg", "source": "example.com"}
        if ev:
            x["event"] = ev
        return x
    items = [
        {"name": "Alpha", "section": "游戏", "subtitle": "", "cover": None, "facts": [], "theme": TH,
         "stories": [st("Alpha", i, "hero" if i == 0 else "normal") for i in range(5)]},
        {"name": "Bravo", "section": "游戏", "subtitle": "", "cover": None, "facts": [], "theme": TH,
         "stories": [st("Bravo", i, ev={"date": "2099-01-01", "label": "発売日"} if i == 0 else None) for i in range(5)]},
        {"name": "Charlie", "section": "明星", "subtitle": "", "cover": None, "facts": [], "theme": TH,
         "stories": [st("Charlie", i) for i in range(5)]}]
    old = dict(render.AUTH_DB), list(render.AUTH_ITEMS)
    render.AUTH_DB.update({"url": DB, "key": "k"})
    render.AUTH_ITEMS[:] = [["Alpha", "游戏"], ["Bravo", "游戏"], ["Charlie", "明星"]]
    try:
        html = render.render([{"no": 1, "date": "2026-11-19", "items": items}], order=["Alpha", "Bravo", "Charlie"],
                             updated=UPDATED, wishes=WISH, heat={"Alpha": {"score": 70, "label": "注目"}, "Bravo": {"score": 91, "label": "大人気"}})
    finally:
        render.AUTH_DB.clear()
        render.AUTH_DB.update(old[0])
        render.AUTH_ITEMS[:] = old[1]
    return html


STUB = """window.supabase={createClient:function(){var s=%s;return {auth:{
 onAuthStateChange:function(cb){setTimeout(function(){cb('INITIAL_SESSION',s);},0);return {data:{subscription:{unsubscribe:function(){}}}};},
 signOut:function(){return Promise.resolve({});},getSession:function(){return Promise.resolve({data:{session:s}});}}};}};"""


class FallbackHidesOwner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = build()
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name) / "home"
        d.mkdir()
        (d / "index.html").write_text(cls.html, encoding="utf-8")
        cls.ids = dict(re.findall(r'<section [^>]*?id="(w-[0-9a-f]+)"[^>]*?data-k="([^"]+)"', cls.html))

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_page_has_the_owner_things(self):
        """前提：作った店長のページに、隠すべき物が本当に入っている（入っていなければ下の試験が空振りする）。"""
        for s in ("欲しい 1 件", 'class="fside"', "店長の黒猫マグ", "Bravo · 発売日", 'class="hm"', f"<b>{UPDATED}</b>", "hush()"):
            self.assertIn(s, self.html)
        self.assertIn("Bravo", self.ids.values())

    def open(self, pw, b, who, width, url="home/index.html?own=0", newver=True):
        import self_review
        port = getattr(self, "_port", None) or self_review.serve(self.dir.name)
        self._port = port
        sess = "null" if who == "guest" else json.dumps({"access_token": "t-" + who, "user": {"id": "u-" + who, "email": who + "@example.com"}})
        bravo = next(k for k, v in self.ids.items() if v == "Bravo")

        def rpc(fn):
            return {"auth_enforced": True, "my_role": {"user": "user", "admin": "admin"}.get(who, "guest"), "can_edit": who == "admin",
                    "my_page": {"name": "test-a@example.com", "prefs": {"picks": [{"name": "Alpha", "sec": "游戏"}]}},
                    "my_boards": {"boards": []}, "user_login": {"agreed_version": 99}}.get(fn, [])

        def handle(route):
            u = route.request.url
            if route.request.resource_type == "image":
                return route.fulfill(status=200, content_type="image/png", body=PNG)
            if "supabase-js" in u:
                return route.fulfill(status=200, content_type="application/javascript", body=STUB % sess)
            m = re.match(re.escape(DB) + r"/rest/v1/rpc/(\w+)", u)
            if m:
                return route.fulfill(status=200, content_type="application/json", body=json.dumps(rpc(m.group(1))))
            if u.split("?")[0].endswith("/home/version.json"):   # 新しい版：Bravo（お客さまが選んでいない版面）の中身が変わった
                return route.fulfill(status=200, content_type="application/json",
                                     body=json.dumps({"index": "ffff", "index_marks": {bravo: ["Bravo", "zz"]}} if newver else {"index": "__WL_VER__"}))
            if u.split("?")[0].endswith("/home/me.html"):
                return route.fulfill(status=200, content_type="text/html", body="<!doctype html><title>shell</title><p>shell")
            if u.startswith(f"http://127.0.0.1:{port}/"):
                return route.continue_()
            return route.abort()
        ctx = b.new_context(viewport={"width": width, "height": 900 if width > 760 else 844}, locale="ja-JP", reduced_motion="reduce")
        ctx.route("**/*", handle)
        me = {"name": "test-a@example.com" if who == "user" else "owner@example.com", "v": 99, "chk": 9e15}
        # 読み直したあとの印（LIVE の「更新しました：…」）と、新しい版をすぐ知らせる（?v= で開き直さない）印は、最初の 1 回だけ
        ctx.add_init_script("(()=>{" + (f"localStorage.setItem('wl-user',{json.dumps(json.dumps(me))});" if who != "guest" else "") +
                            "if(sessionStorage.getItem('t-once'))return;sessionStorage.setItem('t-once','1');"
                            "sessionStorage.setItem('wl-live:index:tried',JSON.stringify('ffff'));"
                            "sessionStorage.setItem('wl-live:index',JSON.stringify({to:'__WL_VER__',keys:{},marks:{}}));})();")
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{port}/{url}", wait_until="load", timeout=30000)
        pg.wait_for_function("()=>document.documentElement.dataset.auth&&document.documentElement.dataset.auth!=='wait'", timeout=20000)
        if who == "user":
            pg.wait_for_function("()=>document.documentElement.dataset.mine==='2'", timeout=10000)
        pg.wait_for_timeout(1200)
        return ctx, pg

    SNAP = """()=>{const vis=e=>!!e&&getComputedStyle(e).display!=='none'&&!!e.getClientRects().length;
      let t=document.body.innerText;document.querySelectorAll('.wl-maybe').forEach(x=>{t=t.split(x.innerText).join('')});
      const bar=document.querySelector('.wl-live');
      return {text:t,mine:document.documentElement.dataset.mine||'',side:document.querySelectorAll('.fside,.fstrip').length,
        wishN:vis(document.querySelector('.mastwish small')),navN:vis(document.querySelector('.navwish small')),
        meta:vis(document.querySelector('.mast .meta')),hm:vis(document.querySelector('.nav .logo .hm')),wish:vis(document.querySelector('.mastwish')),
        bar:bar?{text:bar.textContent,shown:vis(bar)&&!bar.hidden}:null,wall:[...document.querySelectorAll('.mgrid .wc')].filter(vis).map(c=>c.dataset.k)}}"""

    def browser(self):
        from browser import launch
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            b = launch(pw)
        except Exception as ex:  # noqa: BLE001  CI にブラウザが無いとき
            pw.stop()
            self.skipTest("ブラウザなし: %s" % str(ex)[:80])
        return pw, b

    def test_fallback_and_owner(self):
        pw, b = self.browser()
        try:
            for width in (1333, 390):
                ctx, pg = self.open(pw, b, "user", width)
                s = pg.evaluate(self.SNAP)
                tag = f"お客さまの代わりの画面 {width}px"
                self.assertEqual(s["mine"], "2", tag)
                self.assertIn("Alpha", s["text"], tag + "：選んだ版面は出る")
                self.assertTrue(s["wish"], tag + "：欲しい物への入口は残す")
                for k in ("wishN", "navN", "meta", "hm"):
                    self.assertFalse(s[k], f"{tag}：{k} が見える")
                self.assertEqual(s["side"], 0, tag + "：右の列（店長の欲しい物・予定）が残っている")
                for w in ("欲しい 1 件", "今日の最高", UPDATED, "店長の黒猫マグ", "NT$ 850", "店長の白猫マグ", "欲しいものの合計", "これからの予定",
                          "Bravo", "Charlie"):
                    self.assertNotIn(w, s["text"], f"{tag}：「{w}」が見える")
                self.assertTrue(s["bar"] is None or not s["bar"]["shown"], tag + "：LIVE の帯が見える")
                self.assertTrue(s["bar"] is None or ("Bravo" not in s["bar"]["text"] and "Charlie" not in s["bar"]["text"]), tag + "：LIVE の帯に店長の版面の名前")
                self.assertNotIn("Bravo", pg.evaluate("document.querySelector('.wl-live')?document.querySelector('.wl-live').textContent:''"))
                if width > 760:
                    self.assertIn("Alpha", s["wall"], tag + "：ほかの注目の選んだ版面の記事が組み直しで消えた")
                ctx.close()
            for who in ("admin", "guest"):
                for width in (1333, 390):
                    ctx, pg = self.open(pw, b, who, width, "home/index.html")
                    s = pg.evaluate(self.SNAP)
                    tag = f"{who} {width}px"
                    self.assertIn(s["mine"], ("", "0"), tag)
                    self.assertTrue(s["meta"], tag + "：更新の時刻")
                    self.assertTrue(s["hm"] or width <= 760, tag + "：ロゴの話題度")
                    self.assertTrue(s["navN"] or width <= 760, tag + "：目次の欲しい物の件数")
                    self.assertTrue(s["wishN"] or width <= 760, tag + "：報頭の欲しい物の件数")
                    self.assertEqual(s["side"], 1, tag + "：右の列")
                    for w in ([UPDATED, "Bravo", "Charlie"] + (["今日の最高", "店長の黒猫マグ", "欲しい 1 件", "これからの予定"] if width > 760 else [])):
                        self.assertIn(w, s["text"], f"{tag}：「{w}」が出ない")
                    self.assertTrue(s["bar"] and s["bar"]["shown"] and "Bravo" in s["bar"]["text"], f"{tag}：LIVE の知らせ {s['bar']}")
                    ctx.close()
        finally:
            b.close()
            pw.stop()

    def test_reload_retries_shell(self):
        pw, b = self.browser()
        try:
            ctx, pg = self.open(pw, b, "user", 1333, newver=False)   # 新しい版が待っていると、閉じるときに LIVE_JS が読み直しの印を残す（それは ?wlv= で殻へ。別の道）
            pg.reload(wait_until="load")   # 読む人の F5：殻をもう一度
            pg.wait_for_url(re.compile(r"/home/me\.html"), timeout=15000)
            # 自動の読み直し（LIVE_JS が wl-live:index を残して reload）：代わりの画面のまま
            pg.goto(pg.url.replace("me.html", "index.html?own=0"), wait_until="load")
            pg.wait_for_function("()=>document.documentElement.dataset.mine==='2'", timeout=20000)
            pg.evaluate("sessionStorage.setItem('wl-live:index',JSON.stringify({to:'__WL_VER__',keys:{},marks:{}}))")
            pg.reload(wait_until="load")
            pg.wait_for_function("()=>document.documentElement.dataset.mine==='2'", timeout=20000)
            self.assertIn("own=0", pg.url)
            # 跳ね返り 30 秒に 3 回：F5 でも代わりの画面のまま
            pg.evaluate("sessionStorage.setItem('wl-own-at',JSON.stringify([Date.now(),Date.now(),Date.now()]))")
            pg.reload(wait_until="load")
            pg.wait_for_function("()=>document.documentElement.dataset.mine==='2'", timeout=20000)
            pg.wait_for_timeout(500)
            self.assertIn("own=0", pg.url)
            ctx.close()
        finally:
            b.close()
            pw.stop()


if __name__ == "__main__":
    unittest.main()
