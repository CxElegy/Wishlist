"""作ったものを自分の目で調べる（2026-11-07，店長「问题が出てから直すな。Playwright で自分で探せ。文字の欠け・アイコンの大きさ」）。

Playwright でページを開いて、人が見て気になる所を数えて、問題の所を切り抜いた 1 枚の絵にする。
  crop   写真が切れすぎ（主役の位置なし 12% 超・あり 25% 超）
  band   写真の上下左右の帯（10% 超）
  clip   文字が枠で切れている（「…」なしで隠れる。枠の箱と字の箱を比べる）
  clamp  見出しの「…」（数だけ）
  icon   同じ種類のアイコンの大きさがそろっていない（1.15 倍超）
  over   字どうしが重なっている
  wide   横にはみ出す

    python harness/self_review.py --dir docs --page home/index.html --out OUT   # OUT/review.png・review.json。問題があれば終わりのコード 1
    python harness/self_review.py --url https://... --out OUT
"""
import argparse
import base64
import functools
import html
import http.server
import json
import pathlib
import sys
import threading

WIDTHS = (1400, 390)
MAX_SHOTS = 4   # 種類ごとに絵にする数
KIND = {"crop": "写真が切れすぎ", "band": "写真に帯", "clip": "文字が欠けている", "icon": "アイコンの大きさが不揃い", "over": "文字が重なっている", "wide": "横にはみ出す"}
FIX = {"crop": "切らずに枠を写真の形にする", "band": "枠を写真の形にする", "clip": "枠を広げる・行を増やす", "icon": "同じ種類は同じ大きさに", "over": "間隔を取る", "wide": "はみ出す要素を縮める"}

MEASURE_JS = r"""
() => {
  const out = [], tag = (el, kind, note) => { const i = out.length; el.setAttribute('data-sr', i); out.push({i, kind, note, sel: '[data-sr="' + i + '"]'}); };
  const vis = e => { if (!e.checkVisibility || !e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false; const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(i => {
    if (!i.naturalWidth || i.naturalWidth < 32 || !vis(i)) return;
    const b = i.getBoundingClientRect(), r = i.naturalWidth / i.naturalHeight / (b.width / b.height), q = Math.min(r, 1 / r), loss = Math.round((1 - q) * 100), fit = getComputedStyle(i).objectFit, label = (i.closest('article,.pk,.wc,a') || i).innerText || '';
    const name = label.trim().split('\n').pop().slice(0, 24);
    if (fit === 'cover' && loss > (i.dataset.m ? 25 : 12)) tag(i.closest('.pic'), 'crop', loss + '% 切れ（' + name + '）');
    if (fit === 'contain' && loss > 10) tag(i.closest('.pic'), 'band', loss + '% 帯（' + name + '）');
  });
  let clamped = 0;
  document.querySelectorAll('h1,h2,h3,h4,p,a,span,li,button,small,b,strong,td,th,div').forEach(e => {
    if (!vis(e) || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const s = getComputedStyle(e);
    if (s.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1) { clamped++; return; }
    if (s.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) { clamped++; return; }
    const r = e.getBoundingClientRect();
    for (let a = e, depth = 0; a && a !== document.body && depth < 6; a = a.parentElement, depth++) {
      const o = getComputedStyle(a);
      if (o.overflowX === 'visible' && o.overflowY === 'visible') continue;
      if (/auto|scroll/.test(o.overflowX + o.overflowY)) break;   // 動かして読める
      const b = a === e ? null : a.getBoundingClientRect();
      const cut = a === e ? (e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2) : (r.right > b.right + 2 || r.bottom > b.bottom + 2 || r.left < b.left - 2 || r.top < b.top - 2);
      if (cut) { tag(e, 'clip', (e.innerText || '').trim().slice(0, 24)); break; }
    }
  });
  // アイコン：同じ親の種類・同じ種類の小さい絵をまとめて比べる
  const groups = {};
  document.querySelectorAll('svg, img.ico, .ico, button img, a > img, .nav img').forEach(e => {
    if (e.closest('.pic:not(.icon)') || !vis(e)) return;
    const r = e.getBoundingClientRect(); if (r.width > 96 || r.height > 96) return;
    const k = e.tagName + '|' + (e.getAttribute('class') || '') + '|' + (e.parentElement.getAttribute('class') || e.parentElement.tagName);
    (groups[k] = groups[k] || []).push({e, w: r.width, h: r.height});
  });
  Object.entries(groups).forEach(([k, g]) => {
    if (g.length < 3) return;
    const by = g.map(x => Math.max(x.w, x.h)), hi = Math.max(...by), lo = Math.min(...by);
    if (hi / lo > 1.15) { const big = g[by.indexOf(hi)], small = g[by.indexOf(lo)]; tag(big.e.parentElement, 'icon', Math.round(lo) + '〜' + Math.round(hi) + 'px（' + k.split('|').slice(1).join(' ').slice(0, 30) + '）'); }
  });
  // 字の重なり：カードの中の字の葉どうし
  document.querySelectorAll('article,.pk,.wc').forEach(c => {
    if (!vis(c)) return;
    const leaf = [...c.querySelectorAll('h3,h2,time,small,.src,.date,p')].filter(vis).map(e => [e, e.getBoundingClientRect()]);
    for (let i = 0; i < leaf.length; i++) for (let j = i + 1; j < leaf.length; j++) {
      const [a, ra] = leaf[i], [b, rb] = leaf[j]; if (a.contains(b) || b.contains(a)) continue;
      const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
      if (w > 4 && h > 4) { tag(c, 'over', (a.innerText || '').trim().slice(0, 18)); return; }
    }
  });
  if (document.documentElement.scrollWidth > innerWidth + 1) tag(document.body, 'wide', document.documentElement.scrollWidth + 'px > ' + innerWidth + 'px');
  return {items: out, clamped, photos: document.querySelectorAll('.pic img:not(.bg):not(.ico)').length};
}
"""


def serve(root):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def load_all(pg):
    """遅延の写真も読み込んで測る。"""
    pg.evaluate("""async () => {
      document.querySelectorAll('img[loading=lazy]').forEach(i => { i.loading = 'eager'; });
      const h = document.documentElement.scrollHeight;
      for (let y = 0; y < h; y += innerHeight) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
      scrollTo(0, 0);
      await Promise.race([Promise.all([...document.images].filter(i => !i.complete).map(i => new Promise(r => { i.onload = i.onerror = r; }))), new Promise(r => setTimeout(r, 8000))]);
      dispatchEvent(new Event('resize'));
      await new Promise(r => setTimeout(r, 500));
    }""")


def review(url, width, pw_browser):
    ctx = pw_browser.new_context(viewport={"width": width, "height": 900}, locale="ja-JP")
    pg = ctx.new_page()
    pg.goto(url, wait_until="load", timeout=60000)
    load_all(pg)
    res = pg.evaluate(MEASURE_JS)
    seen, shots = {}, []
    for it in res["items"]:
        n = seen.get(it["kind"], 0)
        seen[it["kind"]] = n + 1
        if n >= MAX_SHOTS:
            continue
        try:
            png = pg.locator(it["sel"]).first.screenshot(timeout=5000)
            shots.append({**it, "width": width, "png": base64.b64encode(png).decode()})
        except Exception:   # 隠れて撮れない所は数にだけ入れる
            shots.append({**it, "width": width, "png": ""})
    ctx.close()
    return {"width": width, "counts": seen, "clamped": res["clamped"], "photos": res["photos"], "shots": shots}


def sheet(results, title):
    """問題の所を並べた 1 枚の HTML。"""
    head = []
    cards = []
    for r in results:
        for k, n in r["counts"].items():
            head.append(f"<li><b>{html.escape(KIND[k])}</b> {n} 件（{r['width']}px）→ {html.escape(FIX[k])}</li>")
        for s in r["shots"]:
            img = f'<img src="data:image/png;base64,{s["png"]}">' if s["png"] else "<i>撮れず</i>"
            cards.append(f'<figure>{img}<figcaption><b>{html.escape(KIND[s["kind"]])}</b> {s["width"]}px<br>{html.escape(s["note"])}</figcaption></figure>')
    verdict = "<h2>問題なし</h2>" if not head else f"<ul>{''.join(head)}</ul>"
    return ("<!doctype html><meta charset=utf-8><style>body{font:15px/1.5 'Noto Sans CJK JP','Yu Gothic',sans-serif;margin:16px;width:1100px;background:#fff;color:#111}"
            "h1{font-size:20px;margin:0 0 8px}ul{margin:0 0 12px;padding-left:20px}.g{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}"
            "figure{margin:0;border:3px solid #d33;padding:6px}figure img{max-width:100%;max-height:220px;display:block}figcaption{font-size:13px;margin-top:4px}</style>"
            f"<h1>{html.escape(title)}</h1>{verdict}<div class=g>{''.join(cards)}</div>")


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--dir")
    a.add_argument("--page", action="append", default=[])
    a.add_argument("--url", action="append", default=[])
    a.add_argument("--out", default="review")
    a.add_argument("--title", default="自己点検")
    args = a.parse_args(argv)
    from playwright.sync_api import sync_playwright
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    urls = list(args.url)
    if args.dir:
        port = serve(args.dir)
        urls += [f"http://127.0.0.1:{port}/{p}" for p in args.page or ["home/index.html"]]
    with sync_playwright() as p:
        b = p.chromium.launch()
        results = [review(u, w, b) for u in urls for w in WIDTHS]
        (out / "review.json").write_text(json.dumps([{k: ([{x: s[x] for x in s if x != "png"} for s in v] if k == "shots" else v) for k, v in r.items()} for r in results], ensure_ascii=False, indent=1), encoding="utf-8")
        ctx = b.new_context(viewport={"width": 1140, "height": 800})
        pg = ctx.new_page()
        pg.set_content(sheet(results, args.title), wait_until="load")
        pg.screenshot(path=str(out / "review.png"), full_page=True)
        b.close()
    bad = sum(sum(r["counts"].values()) for r in results)
    for r in results:
        print(f"{r['width']}px：写真 {r['photos']} 枚・問題 {r['counts'] or 'なし'}・「…」{r['clamped']} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
