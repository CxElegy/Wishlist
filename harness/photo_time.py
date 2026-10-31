"""最初の画面の主写真が、ページを開いてから何 ms で届いたか（版面ごと）。2026-10-31 写真 0.5 秒の物差し。
    python harness/photo_time.py [--base https://cxelegy.github.io/Wishlist/home/] [--width 390|1400] [--runs 2] [--slow]
画面に入っている主写真（.pic img:not(.bg):not(.ico)）ごとに：版面名・loading・届いた時刻（Resource Timing の responseEnd・キャッシュなし）。
0.5 秒（500ms）を超えたものを ✗ で出す。--slow は Fast 3G・CPU 4 倍遅。"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "https://cxelegy.github.io/Wishlist/home/"
LIMIT_MS = 500
JS = """()=>new Promise(r=>setTimeout(()=>{const res={};performance.getEntriesByType('resource').forEach(e=>{res[e.name]=Math.round(e.responseEnd)});
const out=[];document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(i=>{const b=i.getBoundingClientRect(),s=i.closest('section');
 if(!i.offsetParent||b.width<20||b.top>=innerHeight||b.bottom<=0)return;
 const u=i.currentSrc||i.src;out.push({board:s&&s.dataset.k||'?',loading:i.loading,done:i.complete&&i.naturalWidth>0,ms:res[u]??null,url:u.split('/').pop().slice(0,40)})});r(out)},4000))"""


def once(pw, base, width, slow):
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": width, "height": 844 if width < 600 else 900}, is_mobile=width < 600)
    pg = ctx.new_page()
    if slow:
        c = ctx.new_cdp_session(pg)
        c.send("Network.enable")
        c.send("Network.emulateNetworkConditions", {"offline": False, "latency": 562, "downloadThroughput": 180000, "uploadThroughput": 84000})
        c.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    pg.goto(base, wait_until="commit", timeout=120000)
    out = pg.evaluate(JS)
    b.close()
    return out


def main(a):
    base = a[a.index("--base") + 1] if "--base" in a else BASE
    width = int(a[a.index("--width") + 1]) if "--width" in a else 390
    runs = int(a[a.index("--runs") + 1]) if "--runs" in a else 2
    slow = "--slow" in a
    bad = 0
    with sync_playwright() as pw:
        for n in range(runs):
            for x in once(pw, base, width, slow):
                late = x["ms"] is None or x["ms"] > LIMIT_MS
                bad += late
                print(("✗ " if late else "  ") + json.dumps(x, ensure_ascii=False))
    print(f"{width}px runs={runs} slow={slow}: 0.5 秒超え {bad} 枚")


if __name__ == "__main__":
    main(sys.argv[1:])
