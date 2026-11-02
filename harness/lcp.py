"""390px・Fast 3G・CPU 4 倍遅の LCP を本番の店長のページで測る（写真の一時保管の効果・HTML を分けるかの判断材料）。
    python harness/lcp.py [--base https://cxelegy.github.io/Wishlist/home/] [--runs 3]
2.5 秒以内なら HTML は分けない（BACKLOG 最初のニュース③）。"""
import json
import statistics
import sys

from playwright.sync_api import sync_playwright
import pathlib as _pl
import sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "harness"))
from browser import launch  # noqa: E402  点検のブラウザは共通の 1 か所から（free-tier.md）

BASE = "https://cxelegy.github.io/Wishlist/home/"
JS = """()=>new Promise(r=>{let v=0,u='';new PerformanceObserver(l=>{for(const e of l.getEntries()){v=e.startTime;u=e.url||e.element&&e.element.tagName||''}}).observe({type:'largest-contentful-paint',buffered:true});
setTimeout(()=>r([v,u]),6000)})"""


def once(pw, base):
    b = launch(pw, photos=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    pg = ctx.new_page()
    c = ctx.new_cdp_session(pg)
    c.send("Network.enable")
    c.send("Network.emulateNetworkConditions", {"offline": False, "latency": 562, "downloadThroughput": 180000, "uploadThroughput": 84000})
    c.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    nbytes = [0]
    pg.on("response", lambda r: nbytes.__setitem__(0, nbytes[0] + int(r.headers.get("content-length", 0) or 0)))
    pg.goto(base, wait_until="load", timeout=120000)
    v, u = pg.evaluate(JS)
    b.close()
    return v, u, nbytes[0]


def main(a):
    base = a[a.index("--base") + 1] if "--base" in a else BASE
    n = int(a[a.index("--runs") + 1]) if "--runs" in a else 3
    with sync_playwright() as pw:
        rs = [once(pw, base) for _ in range(n)]
    print(json.dumps({"lcp_ms": [round(r[0]) for r in rs], "median_ms": round(statistics.median(r[0] for r in rs)),
                      "lcp_url": rs[-1][1][:120], "bytes": [r[2] for r in rs]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
