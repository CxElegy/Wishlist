"""Scroll-jank measurement for https://cxelegy.github.io/Wishlist/home/ (read-only, no login).
usage: python3 harness/scroll_measure.py "mobile/stepped,desktop/stepped" TAG
入口の会話が 2026-11-05 にスクロールの引っかかりを測った道具（harness/audits/2026-11-05-scroll.md）。browser.launch を通る（storage は止める）。
出力は WL_SCROLL_OUT（既定 /tmp/wl_scroll）。直した前／後を同じ道具で測る。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as hb  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

import os
OUT = Path(os.environ.get("WL_SCROLL_OUT") or "/tmp/wl_scroll"); OUT.mkdir(parents=True, exist_ok=True)
URL = os.environ.get("WL_URL") or "https://cxelegy.github.io/Wishlist/home/"   # 手元で作った写しを測るときは WL_URL=http://127.0.0.1:8765/home/
MODE = "desktop"
RUNS = sys.argv[1].split(",")
TAG = sys.argv[2] if len(sys.argv) > 2 else "s3"
LIMIT = 0   # 0 = whole page

INIT = r"""
(() => {
  const M = window.__m = {on: false, t0: 0, frames: [], lt: [], ls: [], loaf: []};
  const keep = e => M.on && e.startTime >= M.t0;
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (keep(e)) M.lt.push({s: e.startTime, d: e.duration,
    a: (e.attribution || []).map(a => [a.name, a.containerType, a.containerName, a.containerSrc].join('|'))}); }).observe({type: 'longtask'}); } catch (_) {}
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (keep(e)) M.ls.push({s: e.startTime, v: e.value, hr: e.hadRecentInput,
    src: (e.sources || []).slice(0, 3).map(s => s.node ? (s.node.nodeName + '.' + (s.node.className && s.node.className.baseVal === undefined ? String(s.node.className).slice(0, 40) : '')) : '?')}); }).observe({type: 'layout-shift'}); } catch (_) {}
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (keep(e)) M.loaf.push({s: e.startTime, d: e.duration, bd: e.blockingDuration,
    rs: e.renderStart, sl: e.styleAndLayoutStart,
    sc: e.scripts.map(x => ({inv: x.invoker, it: x.invokerType, fn: x.sourceFunctionName, pos: x.sourceCharPosition, src: (x.sourceURL || '').slice(-40), d: x.duration, fl: x.forcedStyleAndLayoutDuration}))}); }).observe({type: 'long-animation-frame'}); } catch (_) {}
  const C = window.__cnt = {io: 0, ioT: 0, ioNoOpt: 0, ro: 0, roT: 0, mo: 0};
  const IO = window.IntersectionObserver, RO = window.ResizeObserver;
  window.IntersectionObserver = function (cb, opt) { C.io++; if (!opt) C.ioNoOpt++;
    if (!opt && window.__EXP && window.__EXP.noLateIO) return {observe() {}, unobserve() {}, disconnect() {}, takeRecords() { return []; }};
    const o = new IO(cb, opt), ob = o.observe.bind(o); o.observe = el => { C.ioT++; ob(el); }; return o; };
  window.IntersectionObserver.prototype = IO.prototype;
  window.ResizeObserver = function (cb) { C.ro++; const o = new RO(cb), ob = o.observe.bind(o); o.observe = (el, x) => { C.roT++; ob(el, x); }; return o; };
  window.ResizeObserver.prototype = RO.prototype;
  if (window.__EXP && (window.__EXP.noScrollJS || window.__EXP.noAuthScroll || window.__EXP.noNavScroll)) {
    for (const T of [Window.prototype, Document.prototype]) {
      const add = T.addEventListener;
      T.addEventListener = function (t, f, o) { const src = f && f.toString ? f.toString() : '';
        const hit = (t === 'scroll' || t === 'scrollend') && (window.__EXP.noScrollJS === true || (window.__EXP.noAuthScroll && src.includes('mq.matches')) || (window.__EXP.noNavScroll && src.includes('ticking')));
        if (hit) { (window.__dropped = window.__dropped || []).push(t); return; } return add.call(this, t, f, o); };
    }
  }
})();
"""

FRAME_JS = r"""
window.__frames = () => { const M = __m; M.frames = []; let last = 0;
  const f = t => { if (!M.on) return; if (last) M.frames.push(t - last); last = t; requestAnimationFrame(f); }; requestAnimationFrame(f); };
window.__stats = () => { const M = __m, d = M.frames.slice().sort((a, b) => a - b), n = d.length;
  const q = p => n ? d[Math.min(n - 1, Math.floor(p * n))] : 0, sum = d.reduce((a, b) => a + b, 0);
  const agg = {};
  let scriptMs = 0, renderMs = 0, styleLayoutMs = 0, forced = 0;
  for (const L of M.loaf) {
    const end = L.s + L.d;
    if (L.rs) renderMs += end - L.rs;
    if (L.sl) styleLayoutMs += end - L.sl;
    for (const s of L.sc) { scriptMs += s.d; forced += s.fl || 0;
      const k = [s.it, s.inv, s.fn, s.pos].join(' | '); const a = agg[k] = agg[k] || {n: 0, d: 0, fl: 0}; a.n++; a.d += s.d; a.fl += s.fl || 0; }
  }
  const top = Object.entries(agg).sort((a, b) => b[1].d - a[1].d).slice(0, 25).map(([k, v]) => ({k, n: v.n, ms: Math.round(v.d), forced: Math.round(v.fl)}));
  const ltAgg = {}; for (const t of M.lt) { const k = t.a.join(','); ltAgg[k] = (ltAgg[k] || 0) + t.d; }
  return {frames: n, durS: +(sum / 1000).toFixed(2), fps: +(n / (sum / 1000)).toFixed(1), mean: +(sum / n).toFixed(1), p50: +q(.5).toFixed(1), p95: +q(.95).toFixed(1), p99: +q(.99).toFixed(1), max: +(d[n - 1] || 0).toFixed(0),
    gt33: d.filter(x => x > 33.4).length, gt50: d.filter(x => x > 50).length, gt100: d.filter(x => x > 100).length,
    jankMs: Math.round(d.reduce((a, x) => a + Math.max(0, x - 16.7), 0)),
    longtasks: M.lt.length, longtaskMs: Math.round(M.lt.reduce((a, t) => a + t.d, 0)), ltAgg,
    cls: +M.ls.filter(x => !x.hr).reduce((a, x) => a + x.v, 0).toFixed(4), lsN: M.ls.length, lsSrc: M.ls.slice(0, 8),
    loafN: M.loaf.length, loafMs: Math.round(M.loaf.reduce((a, L) => a + L.d, 0)), loafScriptMs: Math.round(scriptMs), loafRenderMs: Math.round(renderMs), loafStyleLayoutMs: Math.round(styleLayoutMs), loafForcedMs: Math.round(forced), top,
    y: scrollY, H: document.documentElement.scrollHeight};
};
window.__go = () => { __m.on = true; __m.t0 = performance.now(); __m.lt = []; __m.ls = []; __m.loaf = []; __frames(); };
window.__stop = () => { const s = __stats(); __m.on = false; return s; };
window.__stepped = (step, every, limit) => new Promise(res => { __go(); const end = limit || 1e9;
  const id = setInterval(() => { const before = scrollY; scrollBy(0, step);
    if (scrollY >= end || scrollY === before && scrollY + innerHeight >= document.documentElement.scrollHeight - 2) { clearInterval(id); setTimeout(() => res(__stop()), 500); } }, every); });
window.__smooth = (speed, limit) => new Promise(res => { __go(); const end = limit || 1e9; let last = 0, y = scrollY;
  const f = t => { if (last) { y += speed * (t - last) / 1000; scrollTo(0, y); } last = t;
    if (scrollY >= end || (last && scrollY + innerHeight >= document.documentElement.scrollHeight - 2)) return setTimeout(() => res(__stop()), 500);
    requestAnimationFrame(f); }; requestAnimationFrame(f); });
"""

PROBE_JS = r"""
() => {
  const q = s => document.querySelectorAll(s).length;
  const imgs = [...document.images];
  const loaded = imgs.filter(i => i.complete && i.naturalWidth > 8);
  const dpr = devicePixelRatio;
  const over = loaded.map(i => { const r = i.getBoundingClientRect(); return {nw: i.naturalWidth, nh: i.naturalHeight, w: r.width * dpr, h: r.height * dpr, src: (i.currentSrc || i.src).slice(-60)}; }).filter(x => x.w > 0);
  const decodedPx = over.reduce((a, x) => a + x.nw * x.nh, 0), shownPx = over.reduce((a, x) => a + Math.min(x.nw * x.nh, x.w * x.h), 0);
  const ratio = over.map(x => x.nw / x.w).sort((a, b) => a - b);
  const navN = document.querySelector('.nav') ? document.querySelector('.nav').querySelectorAll('*').length : 0;
  const anims = document.getAnimations().map(a => ({name: a.animationName || a.constructor.name, tl: a.timeline && a.timeline.constructor.name, state: a.playState, target: a.effect && a.effect.target && (a.effect.target.className || a.effect.target.nodeName)}));
  const animSum = {}; anims.forEach(a => { const k = a.name + '|' + a.tl + '|' + a.state; animSum[k] = (animSum[k] || 0) + 1; });
  const fixed = [...document.querySelectorAll('body *')].filter(el => { const p = getComputedStyle(el).position; return p === 'fixed' || p === 'sticky'; }).map(el => el.tagName + '.' + String(el.className).slice(0, 30) + ':' + getComputedStyle(el).position);
  return {H: document.documentElement.scrollHeight, W: innerWidth, dpr, nodes: q('*'), imgs: imgs.length, imgsLoaded: loaded.length, secs: q('section[data-k]'), boards: q('.issue > [data-k]'), embs: q('.emb'), cards: q('article'),
    navNodes: navN, nslots: q('.nslot'), pills: q('.nav .pill'), anims: animSum, fixed: fixed.slice(0, 20),
    decodedMPx: +(decodedPx / 1e6).toFixed(1), shownMPx: +(shownPx / 1e6).toFixed(1), ratioP50: ratio[Math.floor(ratio.length / 2)], ratioP90: ratio[Math.floor(ratio.length * .9)],
    worst: over.sort((a, b) => b.nw * b.nh / (b.w * b.h) - a.nw * a.nh / (a.w * a.h)).slice(0, 5)};
}
"""

CATS = ["devtools.timeline", "disabled-by-default-devtools.timeline", "disabled-by-default-devtools.timeline.frame", "v8.execute",
        "disabled-by-default-v8.cpu_profiler", "blink.user_timing", "benchmark", "loading", "disabled-by-default-devtools.timeline.invalidationTracking"]

EXP_CSS = {
    "noEmbAnim": ".emb{animation:none!important}",
    "noEmbFilter": ".emb-in{filter:none!important}",
    "cv": ".issue>section[data-k]:not(.front){content-visibility:auto;contain-intrinsic-size:auto 2400px}",
    "noShadow": "*{box-shadow:none!important}",
    "noBusy": ".busy .br{animation:none!important}",
    "cvGrid": ".sec>.grid,.picks>.pkbatch{content-visibility:auto;contain-intrinsic-size:auto 1500px}",
}


def ctx_opts():
    if MODE == "desktop":
        return dict(viewport={"width": int(os.environ.get("WL_W") or 1400), "height": int(os.environ.get("WL_H") or 900)}, device_scale_factor=1)
    return dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True,
                user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36")


def open_page(b, exp):
    ctx = b.new_context(**ctx_opts())
    flags = {k: True for k in exp.split("+") if k}
    ctx.add_init_script("window.__EXP=" + json.dumps(flags) + ";")
    ctx.add_init_script(INIT)
    ctx.add_init_script(FRAME_JS)
    p = ctx.new_page()
    navs = []
    p.on("framenavigated", lambda fr: fr == p.main_frame and navs.append([round(time.time() - t, 1), fr.url]))
    p.set_default_timeout(120000)
    t = time.time()
    p.goto(URL, wait_until="load", timeout=120000)
    load_s = time.time() - t
    last = len(navs); stable = time.time()
    while time.time() - stable < 6 and time.time() - t < 90:
        p.wait_for_timeout(500)
        if len(navs) != last:
            last = len(navs); stable = time.time()
            try:
                p.wait_for_load_state("load")
            except Exception:
                pass
    print("  navs", navs, flush=True)
    css = "".join(EXP_CSS[k] for k in flags if k in EXP_CSS)
    if css:
        p.add_style_tag(content=css)
    if "noHasHover" in flags:
        print("  removed :has(:hover) rules", p.evaluate("""() => { let n = 0; for (const s of document.styleSheets) { let r; try { r = s.cssRules; } catch (_) { continue; }
          for (let i = r.length - 1; i >= 0; i--) { const x = r[i].selectorText || ''; if (/:has\\([^)]*:hover/.test(x)) { s.deleteRule(i); n++; } } } return n; }"""), flush=True)
    p.evaluate("scrollTo(0,0)")
    p.wait_for_timeout(1500)
    cdp = ctx.new_cdp_session(p)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    p.wait_for_timeout(1000)
    return ctx, p, cdp, load_s


def main():
    res = {}
    out = OUT / f"result_{TAG}_{int(time.time())}.json"
    with sync_playwright() as pw:
        b = hb.launch(pw)
        print("chromium", b.version, flush=True)
        for run in RUNS:
            global MODE
            MODE, _, rest = run.partition("/")
            name, _, exp = rest.partition(":")
            try:
                one(b, run, name, exp, res, out)
            except Exception as ex:  # noqa: BLE001
                print(run, "FAILED", repr(ex)[:300], flush=True)
        b.close()
    print("saved", out)


def one(b, run, name, exp, res, out):
    if True:
        if True:
            ctx, p, cdp, load_s = open_page(b, exp)
            r = {"load_s": round(load_s, 1), "exp": exp, "url": p.url}
            if name == "shot":
                # screenshot the first board that has an emblem, at its top edge (checks clipping by content-visibility)
                y = p.evaluate("(() => { const s = [...document.querySelectorAll('section.sec.has-emb')][2]; s.scrollIntoView(); scrollBy(0, -140); return scrollY; })()")
                p.wait_for_timeout(2500)
                p.screenshot(path=str(OUT / f"shot_{MODE}_{exp or 'base'}.png"))
                r["y"] = y
                r["stats"] = {}
            elif name == "idle":
                p.evaluate("__go()")
                p.wait_for_timeout(6000)
                r["stats"] = p.evaluate("__stop()")
            elif name == "probe":
                r["probe0"] = p.evaluate(PROBE_JS)
                r["stats"] = p.evaluate(f"__stepped(600,100,{LIMIT})")
                p.wait_for_timeout(1500)
                r["probe1"] = p.evaluate(PROBE_JS)
            elif name in ("stepped", "stepped_trace"):
                if name == "stepped_trace":
                    b.start_tracing(page=p, path=str(OUT / f"trace_{MODE}_stepped_{TAG}.json"), categories=CATS)
                r["stats"] = p.evaluate(f"__stepped(600,100,{LIMIT})")
                if name == "stepped_trace":
                    b.stop_tracing()
            elif name == "smooth":
                r["stats"] = p.evaluate(f"__smooth(3000,{LIMIT})")
            elif name in ("gesture", "gesture_trace"):
                if name == "gesture_trace":
                    b.start_tracing(page=p, path=str(OUT / f"trace_{MODE}_gesture_{TAG}.json"), categories=CATS)
                H = p.evaluate("document.documentElement.scrollHeight")
                dist = 600 * 45
                p.evaluate("__go()")
                cdp.send("Input.synthesizeScrollGesture", {"x": 700 if MODE == "desktop" else 195, "y": 700 if MODE == "desktop" else 700,
                                                            "yDistance": -600, "speed": 2400, "preventFling": True, "repeatCount": 45, "repeatDelayMs": 30,
                                                            "gestureSourceType": "mouse" if MODE == "desktop" else "touch"})
                p.wait_for_timeout(500)
                r["stats"] = p.evaluate("__stop()")
                r["dist"] = dist
                if name == "gesture_trace":
                    b.stop_tracing()
            r["dropped"] = len(p.evaluate("window.__dropped||[]"))
            r["cnt"] = p.evaluate("window.__cnt")
            r["lsTop"] = p.evaluate("(() => { const c = {}; for (const x of __m.ls) { const k = x.src.join(','); c[k] = (c[k] || 0) + 1; } return Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 6); })()")
            res[run] = r
            s = r.get("stats", {})
            print(run, "cnt", r["cnt"], "ls", r["lsTop"][:3], flush=True)
            print(run, {k: s.get(k) for k in ("frames", "durS", "fps", "p50", "p95", "p99", "max", "gt50", "gt100", "jankMs", "longtasks", "longtaskMs", "cls", "loafMs", "loafScriptMs", "loafStyleLayoutMs", "loafForcedMs", "y", "H")}, flush=True)
            out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
            ctx.close()


main()
