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
# 2026-11-19 新しい人のページ（店長が test-b を不合格にした 8 つ・主経由の底の決め）
ORPHAN_MIN = 3          # 見出しの最後の行はこの字数以上（1〜2 字の孤立は ✗）
LEAD_MAX = 0.70         # ほかの注目の大きい 1 枚の写真は頭条の写真の面積の 7 割まで
FEW_WALL = 3            # ほかの注目がこの本数以下なら、大きい 1 枚を作らず同じ大きさで並べる
SIDE_LINE_PX = 64       # 空の脇の箱（予定・欲しい物）は 1 行の細い帯（この高さまで）
NAV_GAP_PX = 80         # 左の目次の中身の底から箱の底・欲しい物のボタンまでの空き

KIND = {"edge": "吸着した位置で小元素・題・札が画面の端で切れている", "hid": "吸着した位置で固定のボタンの下に隠れている",
        "solo": "記事が 1 本だけの版面", "herogap": "重大の横に大きな空き", "emrel": "空きの小元素がその記事と無関係",
        "cgap": "カードの中に空き（写真の下・字の下・右）", "ell": "見出しが「…」で切れている", "strong": "脇役の部品に強い要素が 2 つ以上",
        "orphan": "見出しの最後の行が 1〜2 字", "leadbig": "ほかの注目の大きい 1 枚が頭条に近い大きさ", "sidebig": "空の脇の箱が 1 行の帯より大きい",
        "pendhid": "記事 1 本以下の版面で整理待ちをたたんだまま", "navgap": "左の目次の下が空く", "dup": "同じ記事・同じ写真が 2 回"}
FIX = {"edge": "scroll-margin-top を小元素のはみ出し分だけ取る（render.CSS section.sec.has-emb）", "hid": "固定のボタンの下に入らない位置で吸着する",
       "solo": "版面の記事を増やす・隣の版面と一緒に組む", "herogap": "重大の横に記事・予定を置くか幅を広げる",
       "emrel": "関係のある小元素が無ければ空きのまま（置かない）", "cgap": "写真を字の高さまで伸ばす・カードを縮める",
       "ell": "行数を増やす・見出しを短くする", "strong": "脇役の箱は墨の地・小さい札だけにする（C4）",
       "orphan": "字の大きさを列に合わせる・text-wrap: balance（render FIT_JS fitHead）", "leadbig": "記事 3 本以下は同じ大きさで並べる・大きい 1 枚は頭条の 7 割まで",
       "sidebig": "空の箱は 1 行の細い帯に畳む（render._side）", "pendhid": "整理待ちの見出しを写真付きで並べる（render._section）",
       "navgap": "目次の箱は中身の高さ（NAV_JS layout）", "dup": "頭条・ほかの注目に出した記事と写真は版面で使わない（render._without・_calm）"}


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
    const cards = [...g.querySelectorAll('article.card')].filter(vis) /* PC では .mas（積み上げ）に包まれる */; if (!cards.length) return;
    bump('boards');
    if (cards.length === 1) { bump('solo'); tag(sec, 'solo', (sec.dataset.k || '') + '：記事 1 本'); }
    const hero = cards.find(c => c.classList.contains('hero') || c.dataset.hero) /* PC の積み上げ（mason）は hero を外して data-hero に写す */; if (!hero) return;
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
      // 写真の下の空き＝写真の下端から、写真の下にある次の部品（幅いっぱいの要約など）か箱の底まで（2026-11-19：下に回した要約を空きと数えていた）
      const under = kids.filter(k => k !== pic && !k.matches('.lk') && k.getBoundingClientRect().top >= pr.bottom - 2 && k.getBoundingClientRect().left < pr.right).map(k => k.getBoundingClientRect().top);
      if (pr.right < il + iw * 0.7) { const g = (under.length ? Math.min(...under) : ib) - pr.bottom; if (g > ih * P.cPhoto && g >= P.cMin) why.push('写真の下 ' + Math.round(g) + 'px'); }
    }
    const txt = kids.filter(k => k !== pic);
    let low = -1e9;
    txt.forEach(k => [k, ...k.querySelectorAll('*')].forEach(l => {   /* 2026-11-19：子の要素そのもの（壁の見出し b・要約 p）の字も数える。前は子孫だけを見て、壁のカードは札と日付までで「字の下」を測っていた */ if (!vis(l) || getComputedStyle(l).position === 'absolute') return; if (![...l.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return; low = Math.max(low, l.getBoundingClientRect().bottom); }));
    if (txt.length && low > -1e8) { const g = ib - low; if (g > ih * P.cText && g >= P.cMin) why.push('字の下 ' + Math.round(g) + 'px'); }
    const right = Math.max(...kids.map(k => k.getBoundingClientRect().right)), gr = ir - right;
    if (gr > iw * P.cRight && gr >= P.cMin) why.push('右 ' + Math.round(gr) + 'px');
    if (why.length) { bump('cgap'); if (c.matches('.wc')) bump('cgap_wall'); why.forEach(w => bump('cgap_' + (w[0] === '写' ? 'photo' : w[0] === '字' ? 'text' : 'right'))); tag(c, 'cgap', why.join('・') + '（' + (c.querySelector('h2,h3') ? c.querySelector('h2,h3').innerText.trim().slice(0, 16) : '') + '）'); }
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

  // 7〜12：新しい人のページの形（2026-11-19 店長が test-b を不合格にした 8 つ）。店長のページにも同じに当てる
  // 7. 見出しの最後の行が 1〜2 字（孤立。P.orphanMin 字未満）
  const lastLine = el => {
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), rg = document.createRange(), lines = [], bot = el.getBoundingClientRect().bottom + 1;   // 切って隠れた行は数えない
    for (let n; (n = tw.nextNode());) for (let i = 0; i < n.data.length; i++) {
      if (!n.data[i].trim()) continue;
      rg.setStart(n, i); rg.setEnd(n, i + 1); const q = rg.getClientRects()[0]; if (!q || !q.width || q.bottom > bot) continue;
      const y = Math.round(q.top + q.height / 2), L = lines.find(l => Math.abs(l.y - y) < q.height * 0.5);
      if (L) L.n++; else lines.push({y, n: 1});
    }
    lines.sort((a, b) => a.y - b.y); return lines.length >= 2 ? lines[lines.length - 1].n : 99;
  };
  [...document.querySelectorAll('.top h2 .hb, .wall > .wc > b, section.sec article.card h2, section.sec article.card h3, .top p, .wc > .wbl, section.sec article.card p.blurb')].forEach(h => {   // 要約も（11-19 主の指摘 3）
    if (!vis(h) || h.closest('details:not([open])')) return;
    bump('orphanHeads'); const n = lastLine(h);
    if (n < P.orphanMin) { bump('orphan'); tag(h, 'orphan', '最後の行 ' + n + ' 字（' + (h.innerText || '').trim().slice(-8) + '）'); }
  });
  // 8. ほかの注目の大きい 1 枚：頭条の写真の面積の P.leadMax 超／記事が P.fewWall 本以下なのに 2 列にまたがる 1 枚
  const tp = document.querySelector('#front .top .pic'), tpr = tp && vis(tp) ? tp.getBoundingClientRect() : null, TA = tpr ? tpr.width * tpr.height : 0;
  const wcs = [...document.querySelectorAll('.wall > .wc')].filter(c => vis(c) && !c.hidden);
  if (TA && wcs.length) {
    let worst = 0, who = null; wcs.forEach(c => { const p = c.querySelector(':scope > .pic'); if (!p || !vis(p)) return; const r = p.getBoundingClientRect(), a = r.width * r.height; if (a > worst) { worst = a; who = c; } });
    stats.leadPct = Math.round(worst / TA * 100);
    const span2 = wcs.length <= P.fewWall && wcs.some(c => c.classList.contains('lead') && /span\s*2|\/\s*span 2/.test(getComputedStyle(c).gridColumn + getComputedStyle(c).gridColumnEnd));
    if (who && (worst > TA * P.leadMax || span2)) { bump('leadbig'); tag(who, 'leadbig', '頭条の ' + stats.leadPct + '%' + (span2 ? '・' + wcs.length + ' 本で大きい 1 枚' : '')); }
  }
  // 9. 脇の箱（予定・欲しい物）が空なのに 1 行の帯より高い（A7・C4。F3 の「箱は出す」は細い帯で満たす）
  document.querySelectorAll('.fside > *, .fstrip > *').forEach(b => {
    if (!vis(b) || !b.querySelector('.sempty')) return;
    bump('sideEmpty'); const h = b.getBoundingClientRect().height;
    if (h > P.sideLine) { bump('sidebig'); tag(b, 'sidebig', '空の箱 ' + Math.round(h) + 'px'); }
  });
  // 10. 版面に記事が 1 本以下なのに、整理待ちを「N 件」とたたんだまま並べていない（A6・合格の見本 4）
  document.querySelectorAll('section.sec').forEach(sec => {
    const pd = sec.querySelector('details.pend'); if (!pd || !vis(pd) || pd.open || getComputedStyle(pd).display === 'none') return;
    bump('pendClosed');
    const n = [...sec.querySelectorAll('article.card')].filter(c => vis(c) && !c.closest('details:not([open])')).length;
    if (n <= 1) { bump('pendhid'); tag(sec, 'pendhid', (sec.dataset.k || '') + '：記事 ' + n + ' 本・整理待ちはたたんだまま'); }
  });
  // 11. 左の目次の箱の下の空き（PC。中身の底 → 目次の箱の底・欲しい物のボタンまで）
  const nav = document.querySelector('.nav');
  if (nav && vis(nav) && innerWidth > 1000) {
    const nr = nav.getBoundingClientRect(), wish = nav.querySelector('.navwish');
    const kids = [...nav.querySelectorAll('.nslot, .nhead, .logo')].filter(vis), low = kids.length ? Math.max(...kids.map(k => { const r = k.getBoundingClientRect(); const ins = [...k.querySelectorAll('.pill, .nsec, .nsubs, .nmore')].filter(vis); return ins.length ? Math.max(...ins.map(x => x.getBoundingClientRect().bottom)) : r.bottom; })) : nr.top;
    const wr = wish && vis(wish) ? wish.getBoundingClientRect() : null, gap = Math.round(Math.max(wr ? wr.top - low : 0, nr.bottom - (wr ? wr.bottom : low)));
    stats.navGap = gap;
    if (gap > P.navGap) { bump('navgap'); tag(nav, 'navgap', '目次の下 ' + gap + 'px'); }
  }
  // 12. 同じ記事・同じ写真が 1 ページに 2 回（F4）
  const seenU = new Map(), seenP = new Map();
  document.querySelectorAll('#front .top, .wall > .wc, section.sec article.card, section.sec .calm, .pendwall li').forEach(c => {
    if (!vis(c) || c.closest('details:not([open])')) return;
    const a = c.querySelector('a.lk[href], a[href]'), u = a && a.getAttribute('href');
    if (u && !/^#|wishlist|settings/.test(u)) { if (seenU.has(u)) { bump('dup'); tag(c, 'dup', '同じ記事：' + (c.innerText || '').trim().slice(0, 16)); } else seenU.set(u, c); }
    const im = c.querySelector('.pic img:not(.bg):not(.ico)'), s = im && vis(im) && (im.currentSrc || im.src);
    if (s && !/^data:/.test(s) && !(u && seenU.get(u) !== c)) { if (seenP.has(s)) { bump('dup'); tag(c, 'dup', '同じ写真：' + s.split('/').pop().slice(0, 24)); } else seenP.set(s, c); }
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
         "cMin": CGAP_MIN_PX, "strongArea": STRONG_AREA, "relFn": REL_FN % rel if rel else "",
         "orphanMin": ORPHAN_MIN, "leadMax": LEAD_MAX, "fewWall": FEW_WALL, "sideLine": SIDE_LINE_PX, "navGap": NAV_GAP_PX}
    return pg.evaluate("(a) => (" + body.strip() + ")(a[0], a[1], a[2])", [start, p, bool(rel)])


# 新しい人のページ（2026-11-19）を数える幅（主経由の店長の決め：どの幅でも同じ決め方・この 8 幅で数える）
NEW_USER_VIEWS = ((390, 844), (412, 915), (768, 1024), (1000, 800), (1024, 768), (1333, 720), (1440, 900), (1920, 1080))
# 8 つの指摘 → 数える項目（self_review の band・cgap と、上の 7〜12）。審美基準の番号は aesthetic_map.json
NEW_USER_KINDS = ("orphan", "leadbig", "band", "cgap", "sidebig", "pendhid", "navgap", "dup",
                  "solo", "herogap", "ell", "over", "wide", "clip", "gap")


def page_counts(pg):
    """開いて読み込み終えたページ（self_review.load_all のあと）で、self_review の数と上の数を 1 つにした {種類: 件数, '_notes': {種類: [..]}, '_stats': {}}。
    PC の会話が本物の非公開ページ（ログインして開いた本人のページ）に同じ数え方を当てる呼び口。board_kpi.py pages もここを呼べる。"""
    import self_review   # self_review が aesthetic_count を import するので、使うときに読む
    r = pg.evaluate(self_review.MEASURE_JS)
    x = measure(pg, len(r["items"]))
    items = r["items"] + x["items"]
    out = {k: 0 for k in NEW_USER_KINDS}
    notes = {}
    for i in items:
        out[i["kind"]] = out.get(i["kind"], 0) + 1
        notes.setdefault(i["kind"], []).append(i["note"])
    out["cgap_wall"] = x["stats"].get("cgap_wall", 0)   # cgap のうち「ほかの注目」の壁のカード（版面の小さいカードの前からの分と分けて数える）
    out["_notes"] = {k: v[:6] for k, v in notes.items()}
    out["_stats"] = x["stats"]
    return out


def new_user_counts(url, browser_, views=NEW_USER_VIEWS):
    """1 つのページを 8 幅で開いて page_counts。{'390x844': {...}, …}。browser_ は harness/browser.launch の返すもの。"""
    import self_review
    res = {}
    for w, h in views:
        ctx = browser_.new_context(viewport={"width": w, "height": h}, locale="ja-JP", has_touch=w <= 760, is_mobile=w <= 760, reduced_motion="reduce")   # 演出（Blur Text）の途中を数えない：描き終わった形を数える
        pg = ctx.new_page()
        pg.goto(url, wait_until="load", timeout=60000)
        self_review.load_all(pg)
        res[f"{w}x{h}"] = page_counts(pg)
        ctx.close()
    return res


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
