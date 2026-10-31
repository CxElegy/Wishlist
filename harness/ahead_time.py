"""先取り（ahead）が実際に走った時間を測る。2026-10-31 写真 0.5 秒の続き（字面でなく動きの点検）。
    python harness/ahead_time.py [--base URL] [--width 1400|390] [--slow] [--wait 30] [--limit 20]
ページを開いたまま --wait 秒置き（スクロール・目次への接近なし）、各版面の先頭の写真と、版面の中のほかの写真（lazy のまま）が
いつ届いたか（Resource Timing の responseEnd）を出す。全版面の先頭が取れ終わる秒が --limit を超えたら ✗。
ほかの写真は「取りに行ったか」を数える（lazy のまま届かないものの数＝飛んだあとに取り始める写真）。"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "https://cxelegy.github.io/Wishlist/home/"
JS = """()=>{const res={};performance.getEntriesByType('resource').forEach(e=>{res[e.name]=Math.round(e.responseEnd)});
const secs=[...document.querySelectorAll('section[data-k]')];
return secs.map(s=>{const pics=[...s.querySelectorAll('.pic')];const get=p=>[...p.querySelectorAll('img:not(.ico):not(.bg)')].map(i=>{const u=i.currentSrc||i.src;return{loading:i.loading,got:u?res[u]??null:null,has:!!u}});
 return{k:s.dataset.k,lead:pics.length?get(pics[0]):[],rest:pics.slice(1).flatMap(get)}})}"""


def measure(pw, base, width, wait, slow=False):
    """先取りの実測：{版面数, 先頭が届いた数, 届かない版面, 先頭の届く秒の並び, 先頭以外の枚数と届いた数}"""
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": width, "height": 844 if width < 600 else 900}, is_mobile=width < 600)
    pg = ctx.new_page()
    if slow:
        c = ctx.new_cdp_session(pg)
        c.send("Network.enable")
        c.send("Network.emulateNetworkConditions", {"offline": False, "latency": 562, "downloadThroughput": 180000, "uploadThroughput": 84000})
        c.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    pg.goto(base, wait_until="commit", timeout=120000)
    pg.wait_for_timeout(wait * 1000)
    secs = pg.evaluate(JS)
    b.close()
    leads = [max((x["got"] for x in s["lead"] if x["got"] is not None), default=None) for s in secs]
    rest = [x for s in secs for x in s["rest"] if x["has"]]
    return {"n": len(secs), "miss": [s["k"] for s, t in zip(secs, leads) if s["lead"] and t is None],
            "secs": sorted(t / 1000 for t in leads if t is not None), "rest": len(rest), "rest_got": sum(x["got"] is not None for x in rest)}


def main(a):
    g = lambda f, d: a[a.index(f) + 1] if f in a else d
    base, width, wait, limit, slow = g("--base", BASE), int(g("--width", 1400)), int(g("--wait", 30)), float(g("--limit", 20)), "--slow" in a
    with sync_playwright() as pw:
        m = measure(pw, base, width, wait, slow)
    done = m["secs"]
    print(f"{width}px slow={slow} wait={wait}s 版面 {m['n']}：先頭が届いた {len(done)}・届かない {len(m['miss'])} {m['miss'][:8]}")
    if done:
        print(f"  先頭の届く秒：中央 {done[len(done)//2]:.1f}・90% {done[int(len(done)*.9)-1]:.1f}・最後 {done[-1]:.1f}")
    print(f"  先頭以外の写真（src あり）{m['rest']} 枚のうち届いた {m['rest_got']}（lazy のまま {m['rest']-m['rest_got']}）")
    bad = bool(m["miss"]) or not done or done[-1] > limit
    print(("✗" if bad else "✓") + f" 全版面の先頭が {limit:.0f} 秒以内に取れ終わる")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
