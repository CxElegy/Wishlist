"""版面の見出しの帯（.band）の重なりと「今週」の折り返しを数える（審美基準 I1c・E1、2026-11-13）。網なしで、手元の docs/ を本番の網址のまま開く。

usage: python harness/head_check.py [--root docs] [--widths 1440x900,1333x677,1000x800,390x844,412x915] [--shots DIR] [--only 名前,名前]

帯の場所の順は 題 → 数字（話題度＋今週、1 つのまとまり）→ 小元素（残りの幅）。全版面（section.sec）で、版面を画面の上にそろえた所と
画面の 6 割まで下げた所の 2 か所（小元素はスクロールで傾きが変わる）で測り、小元素の候補（開くたびにランダムに 1 枚）も 1 枚ずつ入れて測る：
  - overlap：小元素の絵（変形の後の四隅・object-fit の中身）が題・話題度・「今週」の箱に重なった版面の数
  - wrap：「今週」が話題度と別の行に落ちた、または題の横に入るのに数字が題の下の行に落ちた版面の数
写真は shift_check と同じ灰色の絵。字体は止める（CI と同じ代わりの字体）か、--fonts で本物（本番の店長の画面と同じ幅）。ux_check.py の「帯」（--head）もこれを呼ぶ。上限は両方 0。
"""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser as hb  # noqa: E402
import shift_check  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SIZES = ("1440x900", "1333x677", "1000x800", "390x844", "412x915")

# 小元素の絵の四隅：.emb の変形（translate → rotate → scale → transform、基点 transform-origin）を DOMMatrix で掛ける。
# object-fit:contain の絵は箱でなく中身の大きさ。題（-1° 傾き）は外接の箱。
MEASURE = r"""
(only) => {
  const R = e => { const r = e.getBoundingClientRect(); return r.width && r.height ? [r.left, r.top, r.right, r.bottom] : null; };
  const quads = emb => {
    const cs = getComputedStyle(emb), o = cs.transformOrigin.split(' ').map(parseFloat), M = new DOMMatrix();
    const er = emb.getBoundingClientRect();
    // 変形の前の .emb の左上（画面の座標）：帯の左上＋offset
    const band = emb.parentElement, br = band.getBoundingClientRect(), bx = br.left + band.clientLeft + emb.offsetLeft, by = br.top + band.clientTop + emb.offsetTop;
    M.translateSelf(bx + o[0], by + o[1]);
    if (cs.translate && cs.translate !== 'none') { const t = cs.translate.split(' ').map(parseFloat); M.translateSelf(t[0] || 0, t[1] || 0); }
    if (cs.rotate && cs.rotate !== 'none') M.rotateSelf(parseFloat(cs.rotate));
    if (cs.scale && cs.scale !== 'none') { const s = cs.scale.split(' ').map(parseFloat); M.scaleSelf(s[0], s.length > 1 ? s[1] : s[0]); }
    if (cs.transform && cs.transform !== 'none') M.multiplySelf(new DOMMatrix(cs.transform));
    M.translateSelf(-o[0], -o[1]);
    return [...emb.querySelectorAll('img')].filter(i => i.offsetWidth && i.offsetHeight && getComputedStyle(i).opacity !== '0').map(i => {
      let x = 0, y = 0, n = i; while (n && n !== emb) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent; }
      let w = i.offsetWidth, h = i.offsetHeight; const ic = getComputedStyle(i);
      if (ic.objectFit === 'contain' && i.naturalWidth && i.naturalHeight) {   // 中身だけ（下にそろえる：object-position bottom）
        const k = Math.min(w / i.naturalWidth, h / i.naturalHeight), cw = i.naturalWidth * k, ch = i.naturalHeight * k;
        const px = parseFloat(ic.objectPosition.split(' ')[0]) / 100, py = parseFloat(ic.objectPosition.split(' ')[1]) / 100;
        x += (w - cw) * (isNaN(px) ? .5 : px); y += (h - ch) * (isNaN(py) ? .5 : py); w = cw; h = ch; }
      // .crop の窓で切れた絵は窓の中だけ
      const cr = i.parentElement.classList.contains('crop') ? i.parentElement : null;
      if (cr) { let cx = 0, cy = 0, m = cr; while (m && m !== emb) { cx += m.offsetLeft; cy += m.offsetTop; m = m.offsetParent; }
        const x2 = Math.min(x + w, cx + cr.offsetWidth), y2 = Math.min(y + h, cy + cr.offsetHeight); x = Math.max(x, cx); y = Math.max(y, cy); w = x2 - x; h = y2 - y; }
      return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(([px, py]) => { const p = M.transformPoint(new DOMPoint(px, py)); return [p.x, p.y]; });
    });
  };
  // 四辺形と箱の重なり（分離軸）。箱は 1px 内側に
  const hit = (q, r) => { if (!r) return false; const b = [r[0] + 1, r[1] + 1, r[2] - 1, r[3] - 1];
    const bp = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
    const axes = [[1, 0], [0, 1]]; for (let k = 0; k < 4; k++) { const a = q[k], c = q[(k + 1) % 4]; axes.push([a[1] - c[1], c[0] - a[0]]); }
    return axes.every(([ax, ay]) => { const pr = ps => ps.map(([x, y]) => x * ax + y * ay); const A = pr(q), B = pr(bp);
      return Math.max(...A) > Math.min(...B) && Math.max(...B) > Math.min(...A); }); };
  return [...document.querySelectorAll('section.sec')].filter(s => s.offsetParent && (!only.length || only.includes(s.dataset.k))).map(s => {
    const band = s.querySelector(':scope > .band'); if (!band) return null;
    const t = band.querySelector(':scope > .title'), hs = band.querySelector(':scope .heat > summary'), c = band.querySelector(':scope .cnt'), emb = band.querySelector(':scope > .emb');
    const rt = t && R(t), rh = hs && R(hs), rc = c && R(c);
    const over = [];
    if (emb) quads(emb).forEach(q => { [['題', rt], ['話題度', rh], ['今週', rc]].forEach(([n, r]) => { if (hit(q, r) && !over.includes(n)) over.push(n); }); });
    let wrap = '';
    if (rh && rc && Math.abs(rh[1] - rc[1]) > 8 && Math.abs(rh[3] - rc[3]) > 8) wrap = '今週だけ次の行';
    const num = rh || rc;
    if (!wrap && rt && num && num[1] >= rt[3] - 4) {   // 数字が題の下の行：題の横に入るのに落ちたか
      const bs = getComputedStyle(band), inner = band.clientWidth - parseFloat(bs.paddingLeft) - 4;
      const nw = (rh ? rh[2] - rh[0] : 0) + (rc ? rc[2] - rc[0] : 0) + (rh && rc ? parseFloat(bs.columnGap) || 0 : 0);
      // 小元素の下限の幅（--embmin、EMB_JS の room と同じ）を残して題（・副題）の横に入るなら、落ちたのは誤り
      const sb = band.querySelector(':scope > .sub'), sw = sb ? sb.scrollWidth + (parseFloat(bs.columnGap) || 0) : 0, fmin = emb ? parseFloat(bs.getPropertyValue('--embmin')) || 0 : 0;
      if (rt[2] - rt[0] + sw + (parseFloat(bs.columnGap) || 0) + nw <= inner - fmin) wrap = '題の横に入るのに下の行';
    }
    return {k: s.dataset.k || s.id, over, wrap};
  }).filter(Boolean);
}
"""


ALT = r"""
async ([k, i]) => { const s = [...document.querySelectorAll('section.sec')].find(x => (x.dataset.k || x.id) === k), el = s && s.querySelector(':scope > .band > .emb');
  const a = JSON.parse(el.dataset.alts || '[]')[i], n = el.wlAlt(a);
  await new Promise(r => { if (n.complete) r(); else { n.addEventListener('load', r, {once: true}); n.addEventListener('error', r, {once: true}); setTimeout(r, 3000); } });
  el.wlAlt(); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }
"""


def alts_n(pg, k):
    return pg.evaluate("k => { const s = [...document.querySelectorAll('section.sec')].find(x => (x.dataset.k || x.id) === k), el = s && s.querySelector(':scope > .band > .emb');"
                       " return el && el.wlAlt ? JSON.parse(el.dataset.alts || '[]').length : 0; }", k)


def run(root, w, h, shots=None, only=(), tag="", fonts=False, all_alts=True):
    phone = w <= 760
    res = {}
    with sync_playwright() as p:
        b = hb.launch(p)
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=phone, has_touch=phone, device_scale_factor=1)
        local = shift_check.route(pathlib.Path(root))
        ctx.route("**/*", (lambda r: r.continue_() if "fonts.g" in r.request.url else local(r)) if fonts else local)   # --fonts：本物の字体（Google Fonts）で。字の幅が変わると帯の組みも変わる
        pg = ctx.new_page()
        pg.add_init_script(shift_check.INIT)
        pg.goto(shift_check.BASE + "home/", wait_until="load", timeout=60000)
        pg.evaluate("document.documentElement.classList.remove('emb-js')")   # 飛び出す動きの途中でなく、出た後の形で測る
        pg.add_style_tag(content="body::after{content:'';display:block;height:100vh}")   # 最後の版面も画面の上へ運べるように（帯の組みには触らない）
        pg.wait_for_timeout(1500)
        keys = pg.evaluate("[...document.querySelectorAll('section.sec')].filter(s => s.offsetParent && s.querySelector(':scope > .band')).map(s => s.dataset.k || s.id)")
        for k in keys:
            if only and k not in only:
                continue
            for frac in (0.0, 0.6):
                for _ in range(6):   # 写真が届いて上の版面の高さが変わると着地がずれる：着くまで何度か
                    off = pg.evaluate("([k, f]) => { const s = [...document.querySelectorAll('section.sec')].find(x => (x.dataset.k || x.id) === k);"
                                      " const b = s.querySelector(':scope > .band'), d = b.getBoundingClientRect().top - innerHeight * f - (f ? 0 : 170);"
                                      " const y0 = scrollY; scrollTo({top: scrollY + d, behavior: 'instant'}); return Math.abs(d) < 30 || scrollY === y0 ? 0 : d; }", [k, frac])
                    pg.wait_for_timeout(150)
                    if not off:
                        break
                for r in pg.evaluate(MEASURE, [k]):
                    o = res.setdefault(r["k"], {"over": set(), "wrap": ""})
                    o["over"].update(r["over"])
                    o["wrap"] = o["wrap"] or r["wrap"]
                if shots and frac == 0.0:   # 帯と、その上にはみ出す小元素（撮る直前の場所で切る：吸着でスクロールがずれても同じ所）
                    pg.wait_for_timeout(400)
                    bb = pg.evaluate("k => { const s = [...document.querySelectorAll('section.sec')].find(x => (x.dataset.k || x.id) === k);"
                                     " const r = s.querySelector(':scope > .band').getBoundingClientRect(); return [r.top, r.height]; }", k)
                    top = max(0, bb[0] - 130)
                    if top < h - 20:
                        pg.screenshot(path=str(pathlib.Path(shots) / f"{tag}{w}x{h}-{_slug(k)}.png"),
                                      clip={"x": 0, "y": top, "width": w, "height": min(h - top, bb[1] + 150)})
            # 小元素は開くたびに候補からランダムに 1 枚：候補を 1 枚ずつ入れて（EMB_JS の el.wlAlt）同じに数える。古い網页（wlAlt なし）は最初の 1 枚だけ
            for i in range(1, alts_n(pg, k) if all_alts else 0):
                pg.evaluate(ALT, [k, i])
                for r in pg.evaluate(MEASURE, [k]):
                    o = res.setdefault(r["k"], {"over": set(), "wrap": ""})
                    o["over"].update(f"{x}（候補 {i + 1}）" for x in r["over"])
                    o["wrap"] = o["wrap"] or (r["wrap"] and f"{r['wrap']}（候補 {i + 1}）")
        b.close()
    over = {k: sorted(v["over"]) for k, v in res.items() if v["over"]}
    wrap = {k: v["wrap"] for k, v in res.items() if v["wrap"]}
    return {"size": f"{w}x{h}", "boards": len(res), "overlap": len(over), "wrap": len(wrap), "over_list": over, "wrap_list": wrap}


def _slug(k):
    return "".join(ch if ch.isalnum() else "_" for ch in k)[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "docs"))
    ap.add_argument("--widths", default=",".join(SIZES))
    ap.add_argument("--shots")
    ap.add_argument("--tag", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--fonts", action="store_true", help="本物の字体（Google Fonts）を読む（網が要る）")
    a = ap.parse_args()
    if a.shots:
        pathlib.Path(a.shots).mkdir(parents=True, exist_ok=True)
    bad = False
    only = [x for x in a.only.split(",") if x]
    for s in a.widths.split(","):
        w, h = map(int, s.split("x"))
        r = run(a.root, w, h, a.shots, only, a.tag, a.fonts)
        bad |= bool(r["overlap"] or r["wrap"])
        print(f"{'✗' if r['overlap'] or r['wrap'] else '✓'} {r['size']}: 版面 {r['boards']}・重なり {r['overlap']}・今週の折り返し {r['wrap']}", flush=True)
        for k, v in r["over_list"].items():
            print(f"    重なり {k}: 小元素が {'・'.join(v)}")
        for k, v in r["wrap_list"].items():
            print(f"    折り返し {k}: {v}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
