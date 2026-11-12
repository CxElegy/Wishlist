"""店長の審美基準（docs/rules/aesthetic.md・emblem.md）のうち、人が絵を見ないと分からなかった所を「数」にする（2026-11-12）。

self_review.py から呼ばれる（review() が MEASURE_JS のあとにこれを足す）。測る側だけ：scripts/render.py は読むだけで変えない。
  edge   吸着した位置（版面の上端を画面の上に。E4・I1b）で、小元素・題・「今週」の札が画面の端で切れている
  hid    同じ位置で、固定のボタン（はじめのページ・ログイン）の下に隠れている
  solo   記事が 1 本だけの版面（C2）
  herogap 重大（頭条）の横の大きな空き（頭条の高さの帯のうち、40px 以上の幅の空きの面積 / 帯の面積が HERO_SIDE_MAX 超。A1・A6）
  emrel  空きに置いた小元素（.wemb）が、その記事の字に名前（キャラ・役者）が出ない人（A8）。うち作品ロゴ・作品そのもので埋めた数は stats の emlogo
  cgap   カードの中の空き：写真の下（横並びの写真）・字の下・右が割合を超える（A1・A5）
  ell    見出し（h1〜h4・版面の題・目次の名前）が「…」で切れている（D3）
  strong 脇役の部品（右の列 .fside の箱）に強い要素（彩度の高い地が箱の面積の STRONG_AREA 以上）が 2 つ以上（C4）。グラデーション・影は測れない
既にある項目（self_review.py の face＝小元素の顔が小さい・I1c）は重ねない。

    python harness/aesthetic_count.py --dir docs --page home/index.html [--json OUT.json]    # 基準の数
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERO_SIDE_MAX = 0.10    # 重大の横の空き：帯の面積に対する割合
HERO_SIDE_MIN_W = 40    # これ以上の幅の空きだけ数える（カードの間のすき間 16px 前後は空きではない）
CGAP_PHOTO = 0.12       # カードの中の空き：横並びの写真の下／字の下／右（内側の寸法に対する割合）
CGAP_TEXT = 0.15
CGAP_RIGHT = 0.12
CGAP_MIN_PX = 24        # 割合を超えても、これ未満の px は数えない
STRONG_AREA = 0.15      # 強い要素：彩度 0.55 以上の地が箱の面積のこの割合以上
SNAP_MIN_W = 761        # 吸着は PC だけ（render.FIT_JS の snap が innerWidth <= 760 では動かない）

KIND = {"edge": "吸着した位置で小元素・題・札が画面の端で切れている", "hid": "吸着した位置で固定のボタンの下に隠れている",
        "solo": "記事が 1 本だけの版面", "herogap": "重大の横に大きな空き", "emrel": "空きの小元素がその記事と無関係",
        "cgap": "カードの中に空き（写真の下・字の下・右）", "ell": "見出しが「…」で切れている", "strong": "脇役の部品に強い要素が 2 つ以上"}
FIX = {"edge": "scroll-margin-top を小元素のはみ出し分だけ取る（render.CSS section.sec.has-emb）", "hid": "固定のボタンの下に入らない位置で吸着する",
       "solo": "版面の記事を増やす・隣の版面と一緒に組む", "herogap": "重大の横に記事・予定を置くか幅を広げる",
       "emrel": "関係のある小元素が無ければ空きのまま（置かない）", "cgap": "写真を字の高さまで伸ばす・カードを縮める",
       "ell": "行数を増やす・見出しを短くする", "strong": "脇役の箱は墨の地・小さい札だけにする（C4）"}


def emb_rel_js():
    """render.py の EMB_REL_JS（記事の字に小元素の名前が出るか）を読む。import せず文字だけ取り出す（render は重く、副作用もある）。"""
    t = (ROOT / "scripts" / "render.py").read_text(encoding="utf-8")
    m = re.search(r'EMB_REL_JS = r"""(.*?)"""', t, re.S)
    return m.group(1) if m else ""


JS_BODY = r"""
(start, P, EMB_OK) => {
  const out = [], stats = {};
  const tag = (el, kind, note) => { const i = start + out.length; el.setAttribute('data-sr', i); out.push({i, kind, note, sel: '[data-sr="' + i + '"]'}); };
  const bump = (k, n) => { stats[k] = (stats[k] || 0) + (n === undefined ? 1 : n); };
  const vis = e => { if (!e.checkVisibility || !e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false; const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const pad = (s, k) => parseFloat(s[k]) || 0;

  // 1. 吸着した位置（PC だけ）：版面の上端を scroll-margin-top のところへ。小元素・題・札が端で切れる／固定のボタンの下に隠れる
  stats.snapMeasured = 0; stats.snapSkipped = 0;
  if (innerWidth >= P.snapMinW) {
    const root = document.documentElement, prev = root.style.scrollBehavior; root.style.scrollBehavior = 'auto';
    const fixed = [...document.querySelectorAll('body *')].filter(e => {
      const s = getComputedStyle(e); if (s.position !== 'fixed' || s.pointerEvents === 'none' || s.visibility === 'hidden' || +s.opacity < 0.05) return false;
      const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4 && !(r.width > innerWidth * 0.9 && r.height > innerHeight * 0.9); });
    document.querySelectorAll('section.sec.has-emb').forEach(sec => {
      if (!vis(sec)) return;
      const m = parseFloat(getComputedStyle(sec).scrollMarginTop) || 16, y = sec.getBoundingClientRect().top + scrollY - m;
      scrollTo(0, y); void sec.offsetHeight;
      if (Math.abs(scrollY - y) > 2) { stats.snapSkipped++; return; }   // ページの底で、その位置まで上げられない
      stats.snapMeasured++;
      const parts = [...sec.querySelectorAll(':scope > .band .emb img, :scope > .band .title, :scope > .band .cnt')].filter(e => e.offsetWidth && e.offsetHeight && vis(e));
      let cut = 0, hid = 0;
      parts.forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.top < -1 || r.left < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1) cut++;
        else if (fixed.some(f => { const q = f.getBoundingClientRect(); return !f.contains(e) && Math.min(r.right, q.right) - Math.max(r.left, q.left) > 1 && Math.min(r.bottom, q.bottom) - Math.max(r.top, q.top) > 1; })) hid++;
      });
      if (cut) { bump('edge', cut); tag(sec.querySelector(':scope > .band'), 'edge', cut + ' 個（' + (sec.dataset.k || '') + '）'); }
      if (hid) { bump('hid', hid); tag(sec.querySelector(':scope > .band'), 'hid', hid + ' 個（' + (sec.dataset.k || '') + '）'); }
    });
    scrollTo(0, 0); root.style.scrollBehavior = prev;
  }

  // 2. 記事が 1 本だけの版面・重大の横の空き
  let heroN = 0, heroWorst = 0;
  document.querySelectorAll('section.sec').forEach(sec => {
    const g = sec.querySelector(':scope > .grid'); if (!g || !vis(g)) return;
    const cards = [...g.querySelectorAll('article.card')].filter(vis)   // PC では .mas（積み上げ）に包まれる; if (!cards.length) return;
    bump('boards');
    if (cards.length === 1) { bump('solo'); tag(sec, 'solo', (sec.dataset.k || '') + '：記事 1 本'); }
    const hero = cards.find(c => c.classList.contains('hero')); if (!hero) return;
    heroN++;
    const gr = g.getBoundingClientRect(), hr = hero.getBoundingClientRect(), rects = cards.map(c => c.getBoundingClientRect());
    let empty = 0, rows = 0;
    for (let y = hr.top + 2; y < hr.bottom - 1; y += 8) {
      rows++;
      const iv = rects.filter(r => r.top <= y && r.bottom >= y).map(r => [Math.max(r.left, gr.left), Math.min(r.right, gr.right)]).sort((a, b) => a[0] - b[0]);
      let x = gr.left;
      for (const [l, r] of iv) { if (l - x >= P.heroMinW) empty += l - x; x = Math.max(x, r); }
      if (gr.right - x >= P.heroMinW) empty += gr.right - x;
    }
    const ratio = rows ? empty / (rows * gr.width) : 0; heroWorst = Math.max(heroWorst, ratio);
    if (ratio > P.heroMax) { bump('herogap'); tag(sec, 'herogap', Math.round(ratio * 100) + '%（' + (sec.dataset.k || '') + '）'); }
  });
  stats.heroBoards = heroN; stats.heroWorstPct = Math.round(heroWorst * 100);

  // 3. 空きに置いた小元素（.wemb）：その記事の字に名前が出るか／作品そのもので埋めたか
  stats.wemb = 0; stats.emlogo = 0;
  if (!EMB_OK) stats.embUnmeasured = 1;
  else {
    const rel = (new Function('return (' + P.relFn + ')'))();
    document.querySelectorAll('.wemb').forEach(img => {
      const c = img.closest('.wc, li[data-k]'); if (!c || !vis(img)) return;
      stats.wemb++;
      const sec = [...document.querySelectorAll('section.sec.has-emb')].find(x => x.dataset.k === c.dataset.k), m = sec && sec.querySelector('.emb');
      let alts = []; try { alts = JSON.parse(m && m.dataset.alts || '[]'); } catch (_) {}
      const src = img.getAttribute('src'), a = alts.find(x => x && x.src === src);
      const text = c.dataset.t || c.innerText || '';
      const named = a && rel.named(a, text);
      if (!named) {
        bump('emrel');
        if (a && a.own) bump('emlogo');
        tag(c, 'emrel', (a ? (a.name || '?') + (a.own ? '（作品そのもの）' : '') : '(alts に無い)') + ' ← ' + text.slice(0, 24));
      }
    });
  }

  // 4. カードの中の空き
  const cardSel = 'section.sec .grid article.card, .mgrid .wall > .wc';
  document.querySelectorAll(cardSel).forEach(c => {
    if (!vis(c) || c.hidden) return;
    const s = getComputedStyle(c), r = c.getBoundingClientRect();
    const ib = r.bottom - pad(s, 'paddingBottom') - pad(s, 'borderBottomWidth'), ir = r.right - pad(s, 'paddingRight') - pad(s, 'borderRightWidth');
    const it = r.top + pad(s, 'paddingTop'), il = r.left + pad(s, 'paddingLeft'), ih = ib - it, iw = ir - il; if (ih < 60 || iw < 60) return;
    const kids = [...c.children].filter(k => vis(k) && getComputedStyle(k).position !== 'absolute');
    if (!kids.length) return;
    bump('cards');
    const pic = kids.find(k => k.classList.contains('pic')), why = [];
    if (pic) {
      const pr = pic.getBoundingClientRect();
      if (pr.right < il + iw * 0.7) { const g = ib - pr.bottom; if (g > ih * P.cPhoto && g >= P.cMin) why.push('写真の下 ' + Math.round(g) + 'px'); }
    }
    const txt = kids.filter(k => k !== pic);
    let low = -1e9;
    txt.forEach(k => k.querySelectorAll('*').forEach(l => { if (!vis(l) || getComputedStyle(l).position === 'absolute') return; if (![...l.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return; low = Math.max(low, l.getBoundingClientRect().bottom); }));
    if (txt.length && low > -1e8) { const g = ib - low; if (g > ih * P.cText && g >= P.cMin) why.push('字の下 ' + Math.round(g) + 'px'); }
    const right = Math.max(...kids.map(k => k.getBoundingClientRect().right)), gr = ir - right;
    if (gr > iw * P.cRight && gr >= P.cMin) why.push('右 ' + Math.round(gr) + 'px');
    if (why.length) { bump('cgap'); why.forEach(w => bump('cgap_' + (w[0] === '写' ? 'photo' : w[0] === '字' ? 'text' : 'right'))); tag(c, 'cgap', why.join('・') + '（' + (c.querySelector('h2,h3') ? c.querySelector('h2,h3').innerText.trim().slice(0, 16) : '') + '）'); }
  });

  // 5. 見出しの「…」
  const heads = [...document.querySelectorAll('h1,h2,h3,h4,section.sec > .band .title,.nsec span,.nsec b,.nsec i,.card .txt a')];
  heads.forEach(h => {
    if (!vis(h) || h.closest('details:not([open])')) return;
    bump('headings');
    for (let a = h, d = 0; a && d < 3; a = a.parentElement, d++) {
      const s = getComputedStyle(a);
      if ((s.webkitLineClamp !== 'none' && a.scrollHeight > a.clientHeight + 1) || (s.textOverflow === 'ellipsis' && a.scrollWidth > a.clientWidth + 1)) { bump('ell'); tag(h, 'ell', (h.innerText || '').trim().slice(0, 24)); return; }
    }
  });

  // 6. 脇役の部品（右の列）に強い要素が 2 つ以上
  const side = document.querySelector('.fside');
  if (!side) stats.strongUnmeasured = 1;
  else [...side.children].forEach(box => {
    if (!vis(box)) return;
    bump('sideBoxes');
    const br = box.getBoundingClientRect(), area = br.width * br.height, strong = [];
    [box, ...box.querySelectorAll('*')].forEach(e => {
      if (!vis(e)) return;
      const m = getComputedStyle(e).backgroundColor.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/); if (!m) return;
      const [r, g, b] = [m[1], m[2], m[3]].map(v => v / 255), al = m[4] === undefined ? 1 : +m[4]; if (al < 0.6) return;
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, sat = mx === mn ? 0 : (mx - mn) / (1 - Math.abs(2 * l - 1));
      if (sat < 0.55 || l < 0.2 || l > 0.7) return;
      const q = e.getBoundingClientRect();
      if (q.width * q.height >= area * P.strongArea) strong.push(e);
    });
    if (strong.length >= 2) { bump('strong'); tag(box, 'strong', strong.length + ' 個（' + ((box.querySelector('h4') || {}).innerText || '').trim().slice(0, 14) + '）'); }
  });
  return {items: out, stats};
}
"""

# 記事の字に名前が出る小元素か：render.EMB_REL_JS の embTerms/embHas/embNorm を使う（同じ判定。名前の無い小元素は名前が出ない扱い）
REL_FN = r"""
(() => {
%s
  return {named: (a, text) => !!(a && a.name && embTerms(a).some(w => embHas(embNorm(text), w)))};
})()
"""


def build_js():
    rel = emb_rel_js()
    return JS_BODY, rel


def measure(pg, start=0):
    """開いたページで測る。{items:[{i,kind,note,sel}], stats:{…}}（items は self_review の MEASURE_JS と同じ形）。"""
    body, rel = build_js()
    p = {"snapMinW": SNAP_MIN_W, "heroMax": HERO_SIDE_MAX, "heroMinW": HERO_SIDE_MIN_W, "cPhoto": CGAP_PHOTO, "cText": CGAP_TEXT, "cRight": CGAP_RIGHT,
         "cMin": CGAP_MIN_PX, "strongArea": STRONG_AREA, "relFn": REL_FN % rel if rel else ""}
    return pg.evaluate("(a) => (" + body.strip() + ")(a[0], a[1], a[2])", [start, p, bool(rel)])


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--dir", default="docs")
    a.add_argument("--page", action="append", default=[])
    a.add_argument("--widths", default="1400,390")
    a.add_argument("--json")
    args = a.parse_args(argv)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import browser
    import self_review
    from playwright.sync_api import sync_playwright
    port = self_review.serve(args.dir)
    res = {}
    with sync_playwright() as p:
        b = browser.launch(p)
        for page in args.page or ["home/index.html"]:
            for w in [int(x) for x in args.widths.split(",")]:
                ctx = b.new_context(viewport={"width": w, "height": 900}, locale="ja-JP")
                pg = ctx.new_page()
                pg.goto(f"http://127.0.0.1:{port}/{page}", wait_until="load", timeout=60000)
                self_review.load_all(pg)
                r = measure(pg)
                st = r["stats"]
                res[f"{page}@{w}"] = {"counts": {k: sum(1 for i in r["items"] if i["kind"] == k) for k in KIND}, "stats": st,
                                      "notes": {k: [i["note"] for i in r["items"] if i["kind"] == k][:8] for k in KIND}}
                print(f"{page} {w}px", json.dumps(res[f"{page}@{w}"], ensure_ascii=False))
                ctx.close()
        b.close()
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
