"""F2（2026-11-05）：配信の控えが古いまま（version.json の版 ≠ HTML の版）でも、LIVE_JS の開き直しは有限回で止まる。

前は ?v= → ?wlv=（v が消える）→ また fresh() で ?v= … を 40 秒で 140 回くり返した。
node で LIVE_JS を「同じタブで何度も開く」形に動かし、location.replace の回数を数える。
"""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402

SIM = r"""
var JS = process.argv[1], SERVED = process.argv[2], LIVE = process.argv[3];
var store = {}, replaces = 0, href = 'https://x.io/Wishlist/home/', now = 1e12;
var ss = {getItem: function(k){return k in store ? store[k] : null;}, setItem: function(k,v){store[k]=String(v);}, removeItem: function(k){delete store[k];}};
function load(){
  var nav = null, q = [];
  var loc = {get href(){return href;}, get search(){return new URL(href).search;}, get pathname(){return new URL(href).pathname;}, get hash(){return new URL(href).hash;},
    replace: function(u){nav = new URL(u, href).toString();}, reload: function(){nav = href;}};
  var meta = {getAttribute: function(k){return k === 'data-page' ? 'index' : null;}, content: SERVED};
  var doc = {querySelector: function(s){return /wl-ver/.test(s) ? meta : null;}, querySelectorAll: function(){return [];},
    documentElement: {lang: 'ja'}, title: 't', hidden: false, addEventListener: function(){}, activeElement: null, body: {appendChild: function(){}}};
  var g = {document: doc, location: loc, sessionStorage: ss, JSON: JSON, URL: URL, history: {replaceState: function(s, t, u){href = new URL(u, href).toString();}},
    addEventListener: function(){}, setInterval: function(){}, setTimeout: function(){}, clearTimeout: function(){}, scrollTo: function(){}, pageYOffset: 0,
    fetch: function(){return {then: function(f){var j = f({ok: true, json: function(){return {index: LIVE};}}); return {then: function(f2){q.push(function(){f2(j);}); return {catch: function(){}};}};}};}};
  g.window = g;
  var fn = new Function('window','document','location','sessionStorage','history','addEventListener','setInterval','setTimeout','clearTimeout','scrollTo','pageYOffset','fetch','URL','JSON', JS);
  var D = Date.now; Date.now = function(){return now;};
  fn(g, doc, loc, ss, g.history, g.addEventListener, g.setInterval, g.setTimeout, g.clearTimeout, g.scrollTo, 0, g.fetch, URL, JSON);
  q.forEach(function(f){f();});
  Date.now = D;
  return nav;
}
for (var i = 0; i < 50; i++){ var n = load(); if (!n) break; replaces++; href = n; now += 1000; }
console.log(JSON.stringify({replaces: replaces, href: href}));
"""


@unittest.skipUnless(shutil.which("node"), "node がない")
class LiveReloadTest(unittest.TestCase):
    def run_sim(self, served, live):
        r = subprocess.run(["node", "-e", SIM, render.LIVE_JS, served, live], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_stale_cdn_stops(self):
        out = self.run_sim("old", "new")   # 控えはいつまでも古い
        self.assertLessEqual(out["replaces"], 2, out)

    def test_up_to_date_no_reload(self):
        self.assertEqual(self.run_sim("same", "same")["replaces"], 0)


if __name__ == "__main__":
    unittest.main()


class FuncBGuards(unittest.TestCase):
    """機能 B（2026-11-05 の機能の確かめ F4・F6・F7）の壊れが戻らないか、作った JS の中身で数える。"""

    def test_logout_local_and_clears_own_copies(self):
        js = render.AUTH_JS[render.AUTH_JS.index("function logout()"):][:600]
        self.assertIn("scope:'local'", js)
        for k in ("wishlist-votes-own", "wl-own-path", "wl-own-set"):
            self.assertIn(k, js)

    def test_me_has_time_limit(self):
        self.assertIn("12000", render.render_me())

    def test_own_wait_counts_settings_rows(self):
        js = render.AUTH_JS[render.AUTH_JS.index("function ownWait("):][:800]
        self.assertIn(".cfg .row[data-item]", js)
        self.assertIn("confirm(L.rmAsk", render.AUTH_JS)

    def test_own_settings_remembers_saved_value(self):
        h = render.render_settings([{"name": "a", "section": "游戏", "size": "M"}], {"url": "u", "key": "k"}, "x", (), {"picks": []})
        self.assertIn("wl-own-set", h)
        self.assertNotIn("Date.now()", h.split("wl-own-set")[0][-50:])   # 指紋が毎回変わる時刻は HTML に焼かない
