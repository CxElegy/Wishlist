"""作ったものを自分の目で調べる（2026-11-07，店長「问题が出てから直すな。Playwright で自分で探せ。文字の欠け・アイコンの大きさ」）。

Playwright でページを開いて、人が見て気になる所を数えて、問題の所を切り抜いた 1 枚の絵にする。
  crop   写真が切れすぎ（主役の位置なし 30% 超・あり 55% 超。店長の印：主役が残れば切れても○）
  band   写真の上下左右の帯（店長の印：帯は✕。12% 超）
  gap    写真の下の空き・札と 👍 の間の空き（店長の印：✕）
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
KIND = {"gap": "写真の下に空き", "crop": "写真が切れすぎ", "band": "写真に帯", "clip": "文字が欠けている", "icon": "アイコンの大きさが不揃い", "over": "文字が重なっている", "wide": "横にはみ出す", "face": "小元素の顔が小さい"}
FIX = {"gap": "写真を字の高さまで伸ばす", "crop": "切らずに枠を写真の形にする", "band": "枠を写真の形にする", "clip": "枠を広げる・行を増やす", "icon": "同じ種類は同じ大きさに", "over": "間隔を取る", "wide": "はみ出す要素を縮める", "face": "顔が下限に届く大きさにして上半身に切る（render.CSS .emb img.body・審美基準 I1c）"}

MEASURE_JS = r"""
() => {
  const out = [], tag = (el, kind, note) => { const i = out.length; el.setAttribute('data-sr', i); out.push({i, kind, note, sel: '[data-sr="' + i + '"]'}); };
  const vis = e => { if (!e.checkVisibility || !e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false; const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(i => {
    if (!i.naturalWidth || i.naturalWidth < 32 || !vis(i) || i.closest('.pic.trim')) return;   // .trim：焼き込みの帯だけ外した絵
    const b = i.getBoundingClientRect(), r = i.naturalWidth / i.naturalHeight / (b.width / b.height), q = Math.min(r, 1 / r), loss = Math.round((1 - q) * 100), fit = getComputedStyle(i).objectFit, label = (i.closest('article,.pk,.wc,a') || i).innerText || '';
    const name = label.trim().split('\n').pop().slice(0, 24);
    if (fit === 'cover' && loss > (i.dataset.m ? 55 : 30)) tag(i.closest('.pic'), 'crop', loss + '% 切れ（' + name + '）');
    if (fit === 'contain' && loss > 12) tag(i.closest('.pic'), 'band', loss + '% 帯（' + name + '）');
  });
  document.querySelectorAll('.wc,.card').forEach(c => {
    const p = c.querySelector(':scope>.pic'); if (!p || !vis(c) || !vis(p) || c.matches('.hero,.lead,.wide')) return;
    const a = c.getBoundingClientRect(), b = p.getBoundingClientRect(), right = b.right < a.left + a.width * 0.7, pb = parseFloat(getComputedStyle(c).paddingBottom) || 0;
    if (right && a.bottom - pb - b.bottom > 16) tag(c, 'gap', Math.round(a.bottom - pb - b.bottom) + 'px（' + (c.innerText || '').trim().split('\n').pop().slice(0, 20) + '）');
  });
  document.querySelectorAll('.pk.big').forEach(c => {
    const t = c.querySelector('.pkt'), n = t && t.parentElement.nextElementSibling; if (!t || !n || !vis(c)) return;
    const g = n.getBoundingClientRect().top - t.getBoundingClientRect().bottom; if (g > 24) tag(c, 'gap', '札の下 ' + Math.round(g) + 'px');
  });
  let clamped = 0;
  document.querySelectorAll('h1,h2,h3,h4,p,a,span,li,button,small,b,strong,td,th,div').forEach(e => {
    if (!vis(e) || ![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const s = getComputedStyle(e);
    if (s.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1) { clamped++; return; }
    if (s.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) { clamped++; return; }
    if (e.closest('details:not([open])')) return;
    let inClamp = false; for (let a = e.parentElement, d = 0; a && d < 4; a = a.parentElement, d++) if (getComputedStyle(a).webkitLineClamp !== 'none') inClamp = true;
    if (inClamp) return;   // 見出しの「…」の中の飾り：字が欠けているのではない
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
    const k = e.tagName + '|' + (e.parentElement.getAttribute('class') || e.parentElement.tagName) + '|' + (e.parentElement.parentElement.getAttribute('class') || '');
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
  // 日付の行（NEW・日付・出典）と 👍👎 の重なり・はみ出し（2026-11-13 店長のスマホ：細い字の列で 👍 が日付に重なり 👎 が右端で切れた）
  document.querySelectorAll('.wc em, .when, .kick').forEach(m => {
    const v = m.querySelector(':scope > .vt');
    if (!v || !vis(m) || !vis(v)) return;
    const parts = [];
    m.childNodes.forEach(n => { if (n === v) return;
      if (n.nodeType === 3 && n.data.trim()) { const g = document.createRange(); g.selectNodeContents(n); [...g.getClientRects()].forEach(q => parts.push([n.data.trim(), q])); }
      else if (n.nodeType === 1 && vis(n)) parts.push([(n.innerText || '').trim().slice(0, 12), n.getBoundingClientRect()]); });
    const mr = m.getBoundingClientRect();
    let clipR = innerWidth; for (let p = m.parentElement; p && p !== document.body; p = p.parentElement) if (/hidden|clip/.test(getComputedStyle(p).overflowX)) { clipR = Math.min(clipR, p.getBoundingClientRect().right); break; }
    for (const btn of v.querySelectorAll('button')) {
      if (!vis(btn)) continue; const c = btn.getBoundingClientRect();
      const hit = parts.find(([, a]) => Math.min(a.right, c.right) - Math.max(a.left, c.left) > 1 && Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top) > 1);
      if (hit) { tag(m.parentElement, 'over', '日付の行と 👍：' + hit[0]); return; }
      if (c.right > clipR + 1) { tag(m.parentElement, 'clip', '👎 が右端で切れる（' + Math.round(c.right - clipR) + 'px）'); return; }
    }
    const out = parts.find(([, a]) => a.right > mr.right + 1);
    if (out) tag(m.parentElement, 'clip', '日付の行が列の外へ：' + out[0]);
  });
  // 小元素の顔（審美基準 I1c・2026-11-12「这还是有点小 看不清人脸」）：人物の顔の高さ = 顔の割合（alts の bf・fs）× 絵の高さ × 帯に合わせた拡大。下限は PC 44px・スマホ 32px（emblem_face.SIZES）。
  // 頭の大きいキャラ（全身のまま）・幅の上限に当たった横に広いポーズ・顔が絵の下のほうにある絵は数えない（規則どおりで届かない＝選び方で替える対象。emb_check E31 の情報の行が数える）
  document.querySelectorAll('section.sec.has-emb .emb').forEach(el => {
    const img = el.querySelector('img'); if (!img || !img.offsetHeight) return;
    let a = null; try { a = JSON.parse(el.dataset.alts || '[]').find(x => x.src === img.getAttribute('src')); } catch (_) {}
    const share = a && a.shape === 'cutout' && (a.body ? a.bf : a.fs); if (!share) return;
    const phone = innerWidth <= 600, floor = phone ? 32 : 44, ar = a.body ? a.body[3] : a.m >= 1 ? a.fa : 0, face = share * (ar ? img.offsetWidth / ar : img.offsetHeight) * (parseFloat(getComputedStyle(el).scale) || 1);   // 上半身に切った絵は枠が見える高さ：絵の高さは幅 ÷ 縦横比
    if (a.body && a.body[1] <= 1 && share >= 0.16 || img.offsetWidth >= (phone ? 138 : 228) || a.body && ((a.bt || 0) + 1.5 * share) * floor / share > (phone ? 100 : 156)) return;   // 最後：顔が絵の下のほうにある（頭の上に武器・帽子）→ 顔が枠に入る大きさまで
    if (face < floor * 0.95) tag(el.closest('.band') || el, 'face', Math.round(face) + 'px < ' + floor + 'px（' + (el.closest('section').dataset.k || '') + '）');
  });
  if (document.documentElement.scrollWidth > innerWidth + 1) tag(document.body, 'wide', document.documentElement.scrollWidth + 'px > ' + innerWidth + 'px');
  return {items: out, clamped, photos: document.querySelectorAll('.pic img:not(.bg):not(.ico)').length};
}
"""


def serve(root):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=str(root))
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


def review(url, width, pw_browser, shot=None):
    ctx = pw_browser.new_context(viewport={"width": width, "height": 900}, locale="ja-JP", has_touch=width <= 760, is_mobile=width <= 760)   # スマホの幅は指の端末として（hover:none で 👍/👎 が大きくなる。2026-11-13 PC の 390px では重ならず見逃した）
    pg = ctx.new_page()
    pg.goto(url, wait_until="load", timeout=60000)
    load_all(pg)
    res = pg.evaluate(MEASURE_JS)
    if shot:   # 自分の目で見る用：ページの上の方
        pg.screenshot(path=str(shot), clip={"x": 0, "y": 0, "width": width, "height": min(3000, pg.evaluate("document.documentElement.scrollHeight"))}, full_page=True, timeout=120000)
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
            seen[it["kind"]] -= 1   # 隠れている所は数えない
            if not seen[it["kind"]]:
                del seen[it["kind"]]
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
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import browser
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    urls = list(args.url)
    if args.dir:
        port = serve(args.dir)
        urls += [f"http://127.0.0.1:{port}/{p}" for p in args.page or ["home/index.html"]]
    with sync_playwright() as p:
        b = browser.launch(p)
        results = [review(u, w, b, out / f"page-{n}-{w}.png") for n, u in enumerate(urls) for w in WIDTHS]
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
