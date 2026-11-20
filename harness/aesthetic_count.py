"""店長の審美基準（docs/rules/aesthetic.md・emblem.md）のうち、人が絵を見ないと分からなかった所を「数」にする（2026-11-12）。

self_review.py から呼ばれる（review() が MEASURE_JS のあとにこれを足す）。測る側だけ：scripts/render.py は読むだけで変えない。
  edge   吸着した位置（版面の上端を画面の上に。E4・I1b）で、小元素・題・「今週」の札が画面の端で切れている
  hid    同じ位置で、固定のボタン（はじめのページ・ログイン）の下に隠れている
  solo   記事が 1 本だけの版面（C2）
  postergap 頭条のポスターの中で、写真の枠と字の列（日付・見出し・要約）の高さの差が 48px かつ頭条の高さの 12% 超（A1・A5。2026-11-20）
  herogap 重大（頭条）の横の大きな空き（頭条の高さの帯のうち、40px 以上の幅の空きの面積 / 帯の面積が HERO_SIDE_MAX 超。A1・A6）
  emrel  空きに置いた小元素（.wemb）が、その記事の字に名前（キャラ・役者）が出ない人（A8）。うち作品ロゴ・作品そのもので埋めた数は stats の emlogo
  cgap   カードの中の空き：写真の下（横並びの写真）・字の下・右が割合を超える（A1・A5）
  ell    見出し（h1〜h4・版面の題・目次の名前）が「…」で切れている（D3）
  strong 脇役の部品（右の列 .fside の箱）に強い要素（彩度の高い地が箱の面積の STRONG_AREA 以上）が 2 つ以上（C4）。グラデーション・影は測れない
既にある項目（self_review.py の face＝小元素の顔が小さい・I1c）は重ねない。

    python harness/aesthetic_count.py --dir docs --page home/index.html [--json OUT.json]    # 基準の数
    python harness/aesthetic_count.py --compare [origin/main]   # render を変えたとき：REF の render と今の render で店長のページを 3 幅数えて前 → 後
"""
import argparse
import json
import os
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
ROW_EDGE_PX = 4          # 同じ行に並んだカードの下端の差（これを超えたら ✗）
POSTER_GAP_PX = 48       # 頭条の中の空き（字の列と写真の高さの差）：この px かつ
POSTER_GAP = 0.12        # 頭条の高さのこの割合を超えたら ✗（2026-11-20）
NAV_GAP_PX = 80         # 左の目次の中身の底から箱の底・欲しい物のボタンまでの空き
# 2026-11-19 店長「図が小さい」（見本 a の版面の 1 件目が約 65px の正方形）：B9・D1 を数にする（仮の下限。店長の決め待ち）
SMALL_PC = 120          # 記事の写真の表示の短い辺の下限（幅 760 超）
SMALL_SP = 88           # 同じ（幅 760 以下）
SIZE_MIX = 1.5          # 同じ行の記事の写真：面積の大きいほうが小さいほうのこの倍を超えたら 1 大 1 小

KIND = {"edge": "吸着した位置で小元素・題・札が画面の端で切れている", "hid": "吸着した位置で固定のボタンの下に隠れている",
        "solo": "記事が 1 本だけの版面", "herogap": "重大の横に大きな空き", "postergap": "頭条の中で写真と字の列の高さが合わず空く", "emrel": "空きの小元素がその記事と無関係",
        "cgap": "カードの中に空き（写真の下・字の下・右）", "ell": "見出しが「…」で切れている", "strong": "脇役の部品に強い要素が 2 つ以上",
        "orphan": "見出しの最後の行が 1〜2 字", "leadbig": "ほかの注目の大きい 1 枚が頭条に近い大きさ", "sidebig": "空の脇の箱が 1 行の帯より大きい",
        "pendhid": "記事 1 本以下の版面で整理待ちをたたんだまま", "navgap": "左の目次の下が空く", "dup": "同じ記事・同じ写真が 2 回", "rowedge": "同じ行のカードの下端がそろわない", "imgfail": "記事の写真が読み込めなかった", "pending": "記事の写真が 30 秒で届かない", "noimg": "頭条に写真なし・記事の半分超が写真なし",
        "small": "記事の写真の短い辺が下限より小さい（B9）", "sizemix": "同じ行の記事の写真が 1 大 1 小（D1）"}
FIX = {"edge": "scroll-margin-top を小元素のはみ出し分だけ取る（render.CSS section.sec.has-emb）", "hid": "固定のボタンの下に入らない位置で吸着する",
       "solo": "版面の記事を増やす・隣の版面と一緒に組む", "herogap": "重大の横に記事・予定を置くか幅を広げる", "postergap": "写真の列の幅を選び直して写真の高さを字の列にそろえる（render FIT_JS 頭条のポスター）",
       "emrel": "関係のある小元素が無ければ空きのまま（置かない）", "cgap": "写真を字の高さまで伸ばす・カードを縮める",
       "ell": "行数を増やす・見出しを短くする", "strong": "脇役の箱は墨の地・小さい札だけにする（C4）",
       "orphan": "字の大きさを列に合わせる・text-wrap: balance（render FIT_JS fitHead）", "leadbig": "記事 3 本以下は同じ大きさで並べる・大きい 1 枚は頭条の 7 割まで",
       "sidebig": "空の箱は 1 行の細い帯に畳む（render._side）", "pendhid": "整理待ちの見出しを写真付きで並べる（render._section）",
       "navgap": "目次の箱は中身の高さ（NAV_JS layout）", "pending": "写真の置き場・網址の速さ（photo_store・hdimg）", "imgfail": "写真の網址が開くか・置き場に入ったかを写真を取る段で確かめる（images.pick・photo_store）", "noimg": "写真のない記事は整理待ちへ（og_image.demote）・写真を探し直す", "rowedge": "同じ行は同じ組み・高いほうにそろえ、字の少ないほうは写真の高さで吸う（FIT_JS wall の FEW_WALL）", "dup": "頭条・ほかの注目に出した記事と写真は版面で使わない（render._without・_calm）",
       "small": "写真の列の幅・枠の下限を上げる（render FIT_JS fitBoard の Rn・Rk・mini）", "sizemix": "同じ行の写真は同じ大きさの段にそろえる（render FIT_JS fitBoard・wall）"}


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
  // 2b. 頭条のポスターの中の空き（2026-11-20 店長「空白のところは多すぎ」：縦長の写真で日付と見出しの間が空いた。herogap は版面の頭の記事だけを見ていた）。
  // PC で、字の列（日付＋見出し・要約）の高さと写真の枠（余白込み）の高さの差が POSTER_GAP_PX かつ頭条の高さの POSTER_GAP 超なら ✗（A1・A5）
  { const top = document.querySelector('#front .top'), fr = top && top.querySelector(':scope > .frame');
    if (top && fr && innerWidth > 760 && vis(top) && vis(fr)) {
      const pd = top.querySelector(':scope > .pdate'), tx = top.querySelector(':scope > .ptxt'), cs = getComputedStyle(top), fs = getComputedStyle(fr);
      if (top.classList.contains('pstk')) {   // 写真を上・字を下に積んだ形：写真の横の空き（左右の合計）が POSTER_GAP_PX かつ頭条の幅の 15% 超なら ✗
        const side = top.clientWidth - fr.offsetWidth - (parseFloat(fs.marginLeft) || 0) - (parseFloat(fs.marginRight) || 0); stats.posterGap = Math.round(side);
        if (side > P.posterGapPx && side > top.clientWidth * 0.15) { bump('postergap'); tag(top, 'postergap', Math.round(side) + 'px（積んだ写真の横）'); }
      } else {
      const left = (pd ? pd.offsetHeight + (parseFloat(cs.rowGap) || 0) : 0) + (tx ? tx.offsetHeight : 0);
      const right = fr.offsetHeight + (parseFloat(fs.marginTop) || 0) + (parseFloat(fs.marginBottom) || 0);
      const d = Math.abs(left - right), H = top.getBoundingClientRect().height;
      stats.posterGap = Math.round(d);
      if (d > P.posterGapPx && d > H * P.posterGap) { bump('postergap'); tag(top, 'postergap', Math.round(d) + 'px（' + (left > right ? '写真の下' : '字の列') + '・頭条の高さ ' + Math.round(H) + 'px）'); } } } }

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
  const lastLine = el=>{const rg=document.createRange(),bot=el.getBoundingClientRect().bottom+1,ns=[],tw=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);for(let n;(n=tw.nextNode());)if(n.data.trim())ns.push(n);const at=(n,i)=>{rg.setStart(n,i);rg.setEnd(n,i+1);const q=rg.getClientRects()[0];return q&&q.width&&q.bottom<=bot?q:null;};let f=null;for(const n of ns){for(let i=0;i<n.data.length&&!f;i++)if(n.data[i].trim())f=at(n,i);if(f)break;}if(!f)return 99;let y=null,c=0;for(let k=ns.length-1;k>=0;k--){const n=ns[k];for(let i=n.data.length-1;i>=0;i--){if(!n.data[i].trim())continue;const q=at(n,i);if(!q)continue;const m=q.top+q.height/2;if(y===null){y=m;if(Math.abs(y-(f.top+f.height/2))<f.height*0.5)return 99;}if(Math.abs(m-y)<q.height*0.5){if(++c>=3)return c;}else return c;}}return c;};   // 最後の行の字数（3 まで）。1 行なら 99。後ろから数える（render.NOORPHAN_JS と同じ式）
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
  // 14. 写真が本当に届いたか（2026-11-19 店長「点検は、本物の写真が取れるかどうかを含めること」）。作り物の写真で数えるとき（fake）は imgfail を見ない
  //   imgfail：記事の写真が落ち先まで全部開けなかった（SWAP_JS の data-imgfail）＋読み込みが終わったのに naturalWidth 0 のまま
  //   noimg：記事（頭条・壁・版面のカード）のうち写真が出ていない数（render が最初から字だけにした nophoto も）。nohead：頭条に写真なし。held：「集めています」の版面
  const arts = [...document.querySelectorAll('#front .top:not(.start), .wall > .wc, section.sec .grid article.card')].filter(a => vis(a) && !a.hidden && !a.closest('details:not([open])'));
  const shown = a => [...a.querySelectorAll('.pic img:not(.bg):not(.ico)')].some(i => i.complete && i.naturalWidth > 0 && vis(i));
  let fail = document.querySelectorAll('[data-imgfail]').length;
  document.querySelectorAll('.pic img[data-e="s"]').forEach(i => { if (i.complete && !i.naturalWidth && i.closest('#front, section.sec, .wall') && !i.closest('[data-imgfail]')) { fail++; tag(i.closest('.pic'), 'imgfail', (i.getAttribute('src') || '').slice(-40)); } });
  document.querySelectorAll('[data-imgfail]').forEach(e => tag(e, 'imgfail', '落ち先まで開けなかった：' + (e.innerText || '').trim().slice(0, 16)));
  stats.imgfail = fail; stats.arts = arts.length;
  // 写真の中身（2026-11-19 PC の実測：本物か代わりの絵かを見分ける）。render._pic の data-o（1 記事自身の写真・0 最初から備えの絵）・SWAP_JS の data-sw（落ち先へ替えた回数）
  const ph = a => a.querySelector('.pic img[data-e="s"]'), got = i => i && i.complete && i.naturalWidth > 0;
  stats.own = stats.swapped = stats.sub = stats.icon = stats.none = stats.pending = 0;
  const notOwn = [];
  arts.forEach(a => { const i = ph(a);
    if (i && !i.complete) { stats.pending++; return; }   // 読み込み待ち（写真なしとは数えない）
    if (got(i) && i.dataset.o === '1' && !(+i.dataset.sw)) stats.own++;
    else { notOwn.push(a); if (got(i) && +i.dataset.sw) stats.swapped++; else if (got(i) && i.dataset.o === '0') stats.sub++; else if (a.querySelector('.pic.icon')) stats.icon++; else stats.none++; } });
  if (stats.pending) tag(document.body, 'pending', stats.pending + ' 枚が 30 秒で届かない');
  const hasO = !!document.querySelector('.pic img[data-o]');   // 印の無い古いページは「写真が出ているか」で数える
  const none = hasO ? notOwn : arts.filter(a => !shown(a) && !(ph(a) && !ph(a).complete)); stats.noimg = none.length; stats.noimgPct = arts.length ? Math.round(none.length / arts.length * 100) : 0;
  const top = document.querySelector('#front .top:not(.start)'); stats.nohead = top && (hasO ? notOwn.includes(top) : !shown(top)) ? 1 : 0;
  stats.held = document.querySelectorAll('.calm[data-held]').length;
  if (stats.nohead || (arts.length && none.length * 2 > arts.length)) { bump('noimg'); tag(top || document.body, 'noimg', (stats.nohead ? '頭条に写真なし・' : '') + '写真なし ' + none.length + ' / ' + arts.length); }
  // 13. 同じ行に並んだカードの下端の差（主の決め 4・直し 2 回目：「ほかの注目」の 2 枚の下端が 95px ずれた）。同じ親の中で上端が 4px 以内にそろったカードの組
  const rowsOf = cs => { const g = []; cs.forEach(c => { const r = c.getBoundingClientRect(), x = g.find(q => Math.abs(q.t - r.top) <= 4); if (x) x.b.push(r.bottom); else g.push({t: r.top, b: [r.bottom], el: c}); }); return g; };
  const groups = new Map();
  document.querySelectorAll('.wall > .wc, section.sec .grid article.card').forEach(c => { if (!vis(c) || c.hidden || c.closest('details:not([open])')) return; const k = c.parentElement; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(c); });
  groups.forEach(cs => rowsOf(cs).forEach(g => { if (g.b.length < 2) return; bump('rows'); const d = Math.max(...g.b) - Math.min(...g.b); if (d > P.rowEdge) { bump('rowedge'); tag(g.el, 'rowedge', (g.el.matches('.wc') ? 'ほかの注目' : (g.el.closest('section.sec') || {dataset: {}}).dataset.k) + '：下端の差 ' + Math.round(d) + 'px（' + g.b.length + ' 枚）'); } }));
  // 15. 記事の写真（頭条・ほかの注目・版面のカード・写真付きの整理待ち・静かな版面。.pic img[data-e=s] の見えている枠＝.pic の箱）。目次のアイコン・小元素・欲しい物は入れない
  //   nom：届いた写真のうち主役の位置（data-m）も字の位置（data-k）も無い数（数だけ。2026-11-19 主：本站保存 pics/… の写真に data-m が付かない）
  //   small（B9）：表示の短い辺が下限（PC SMALL_PC・スマホ SMALL_SP）未満。short：種類ごとの短い辺の分布 [60 未満, 60〜88, 88〜120, 120〜160, 160 以上]
  const aimgs = [...document.querySelectorAll('.pic img[data-e="s"]')].filter(i => i.closest('#front .top, .wall, section.sec') && !i.closest('details:not([open])') && vis(i.closest('.pic')));
  stats.nom = aimgs.filter(i => got(i) && !i.dataset.m && !i.dataset.k).length;
  const kindOf = i => i.closest('#front .top') ? 'top' : i.closest('.wall') ? 'wall' : i.closest('.calm') ? 'calm' : i.closest('article[data-pd]') ? 'pend' : 'board';
  const headOf = el => { const a = el.closest('article, .calm'); const h = a && (a.querySelector('h2, h3') || a.querySelector(':scope > b, .last b')); return ((h || a || el).innerText || '').trim().slice(0, 16); };
  const lim = innerWidth > 760 ? P.smallPc : P.smallSp;
  stats.short = {};
  aimgs.forEach(i => { if (!got(i)) return; const r = i.closest('.pic').getBoundingClientRect(), s = Math.min(r.width, r.height), k = kindOf(i);
    (stats.short[k] = stats.short[k] || [0, 0, 0, 0, 0])[[60, 88, 120, 160].filter(x => s >= x).length]++;
    if (s < lim) { bump('small'); tag(i.closest('.pic'), 'small', '短い辺 ' + Math.round(s) + 'px（' + headOf(i) + '）'); } });
  //   sizemix（D1）：同じ行（同じ親・上端が 4px 以内）に並ぶ記事の写真で、面積の大きいほうが小さいほうの SIZE_MIX 倍を超える行の数。
  //   頭の記事だけ大きい形（壁の大きい 1 枚 .lead・版面の重大 .hero・2 列分〔W・R2・F2〕＝C1・C2 で認めている物）は除く
  const big = c => c.matches('.wc.lead, .hero') || /span\s*[2-9]/.test(c.style.gridColumn || '');
  const pg2 = new Map();
  document.querySelectorAll('.wall > .wc, section.sec .grid article.card').forEach(c => { if (!vis(c) || c.hidden || c.closest('details:not([open])') || big(c)) return;
    const p = c.querySelector(':scope > .pic'), i = p && p.querySelector('img[data-e="s"]'); if (!i || !got(i) || !vis(p)) return;
    const k = c.parentElement; if (!pg2.has(k)) pg2.set(k, []); pg2.get(k).push(c); });
  pg2.forEach(cs => rowsOf(cs).forEach(g => { const row = cs.filter(c => Math.abs(c.getBoundingClientRect().top - g.t) <= 4); if (row.length < 2) return;
    const ar = row.map(c => { const r = c.querySelector(':scope > .pic').getBoundingClientRect(); return r.width * r.height; }), mx = Math.max(...ar), mn = Math.min(...ar);
    if (mn > 0 && mx > mn * P.sizeMix) { bump('sizemix'); tag(row[ar.indexOf(mn)], 'sizemix', '面積 ' + (mx / mn).toFixed(1) + ' 倍（' + headOf(row[ar.indexOf(mx)]) + ' ／ ' + headOf(row[ar.indexOf(mn)]) + '）'); } }));
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
         "orphanMin": ORPHAN_MIN, "rowEdge": ROW_EDGE_PX, "leadMax": LEAD_MAX, "fewWall": FEW_WALL, "sideLine": SIDE_LINE_PX, "navGap": NAV_GAP_PX,
         "posterGapPx": POSTER_GAP_PX, "posterGap": POSTER_GAP, "smallPc": SMALL_PC, "smallSp": SMALL_SP, "sizeMix": SIZE_MIX}
    return pg.evaluate("(a) => (" + body.strip() + ")(a[0], a[1], a[2])", [start, p, bool(rel)])


# 新しい人のページ（2026-11-19）を数える幅（主経由の店長の決め：どの幅でも同じ決め方・この 8 幅で数える）
NEW_USER_VIEWS = ((390, 844), (412, 915), (768, 1024), (1000, 800), (1024, 768), (1333, 720), (1440, 900), (1920, 1080))
# 8 つの指摘 → 数える項目（self_review の band・cgap と、上の 7〜12）。審美基準の番号は aesthetic_map.json
NEW_USER_KINDS = ("imgfail", "pending", "noimg", "rowedge", "orphan", "leadbig", "band", "cgap", "sidebig", "pendhid", "navgap", "dup",
                  "solo", "herogap", "postergap", "ell", "over", "wide", "clip", "gap", "small", "sizemix")


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
    out["cgap_wall"] = x["stats"].get("cgap_wall", 0)
    out["imgfail"] = x["stats"].get("imgfail", 0)   # tag の数ではなく写真の数
    out["pending"] = x["stats"].get("pending", 0)
    for k in ("noimgPct", "nohead", "held", "arts", "own", "swapped", "sub", "icon", "none", "nom", "short"):
        out["_" + k] = x["stats"].get(k, 0)   # cgap のうち「ほかの注目」の壁のカード（版面の小さいカードの前からの分と分けて数える）
    out["_notes"] = {k: v[:6] for k, v in notes.items()}
    out["_stats"] = x["stats"]
    return out


_FAKE = {}


def _fake_png(url):
    """作り物の写真：16:10（render._pic の img は width/height 属性を持たないので決まりの 16:10）・色は網址から（同じ網址 → 同じ絵）。"""
    import hashlib
    import io
    from PIL import Image, ImageDraw
    k = hashlib.md5(url.encode("utf-8")).digest()
    if k not in _FAKE:
        im = Image.new("RGB", (320, 200), (k[0], k[1], k[2]))
        ImageDraw.Draw(im).ellipse([120, 40, 200, 120], fill=(k[3], k[4], k[5]))   # 単色の帯に見えないよう真ん中に丸
        buf = io.BytesIO()
        im.save(buf, "PNG")
        _FAKE[k] = buf.getvalue()
    return _FAKE[k]


def fake_images(ctx):
    """写真の読み込みを全部、作り物の写真で返す（2026-11-19 主の指摘 5：網の都合で写真が読めず数が回ごとに揺れ、店長のページの前／後を比べられなかった）。
    同じ網址は同じ絵・大きさは一定なので、同じページは何度数えても同じ数になる。ページ（HTML・CSS・JS）はそのまま"""
    def h(route):
        if route.request.resource_type == "image":
            return route.fulfill(status=200, content_type="image/png", body=_fake_png(route.request.url))
        if route.request.url.split("?")[0].endswith("version.json"):   # 自動更新（LIVE_JS）が版の違いで開き直すと数えている途中のページが消える
            return route.abort()
        if route.request.url.startswith(("http://127.0.0.1", "http://localhost")):
            return route.continue_()
        return route.abort()   # 外（字体・supabase など）は読まない：揺れの元を断つ
    ctx.route("**/*", h)
    # 揺れの元（2026-11-19 調べ）：気になるかも？の並べ替え（SHUFFLE_JS）と小元素の選び方（A8 のランダム）が Math.random で回ごとに違い、
    # 下の版面の高さ・組みが変わって cgap が ±3 揺れた。数えるときだけ種を固定する（ページの作りはランダムのまま）
    ctx.add_init_script("(()=>{let s=20261119;Math.random=()=>{s|=0;s=s+0x6D2B79F5|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};})();")


WAIT_PHOTOS_MS = 30000   # 本物のページでは記事の写真が届くまで最大 30 秒待つ（写真 212 枚の test-c は 8 秒で読み終わらない。2026-11-19 PC の実測）


def wait_photos(pg, ms=WAIT_PHOTOS_MS):
    """記事の写真（img[data-e=s]）が全部 complete になるまで待つ。届かない分は page_counts の pending が数える。"""
    try:
        pg.wait_for_function("() => [...document.querySelectorAll('.pic img[data-e=\"s\"]')].every(i => i.complete)", timeout=ms)
    except Exception:   # noqa: BLE001  時間切れ：pending として数える
        pass


def new_user_counts(url, browser_, views=NEW_USER_VIEWS, fake=False):
    """1 つのページを 8 幅で開いて page_counts。{'390x844': {...}, …}。browser_ は harness/browser.launch の返すもの。
    fake=True：写真を作り物にして揺れなく数える（店長のページの前／後の比べ・tests/test_new_user_page.py の上限）。"""
    import self_review
    res = {}
    for w, h in views:
        ctx = browser_.new_context(viewport={"width": w, "height": h}, locale="ja-JP", has_touch=w <= 760, is_mobile=w <= 760, reduced_motion="reduce")   # 演出（Blur Text）の途中を数えない：描き終わった形を数える
        if fake:
            fake_images(ctx)
        pg = ctx.new_page()
        pg.goto(url, wait_until="load", timeout=60000)
        self_review.load_all(pg)
        if not fake:
            wait_photos(pg)
        res[f"{w}x{h}"] = page_counts(pg)
        if fake:   # 作り物の写真では「届いたか」は意味がない
            res[f"{w}x{h}"].pop("imgfail", None)
            res[f"{w}x{h}"].pop("noimg", None)
            res[f"{w}x{h}"].pop("pending", None)
        ctx.close()
    return res


def stable_main(argv):
    """python harness/aesthetic_count.py --stable DIR PAGE [OUT.json]：写真を作り物にして 8 幅で数える（店長のページの前／後を同じ条件で）。"""
    import json as _j
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import browser
    import self_review
    from playwright.sync_api import sync_playwright
    port = self_review.serve(argv[0])
    with sync_playwright() as p:
        b = browser.launch(p)
        only = [int(x) for x in os.environ.get("WL_WIDTHS", "").split(",") if x]   # 幅を分けて流す（1 回 5 分以内）
        r = new_user_counts(f"http://127.0.0.1:{port}/{argv[1]}", b, [v for v in NEW_USER_VIEWS if not only or v[0] in only], fake=True)
        b.close()
    tot = {}
    for v, c in r.items():
        for k, n in c.items():
            if not k.startswith("_") and n:
                tot[k] = tot.get(k, 0) + n
    out = {"total": tot, "views": {v: {k: n for k, n in c.items() if not k.startswith("_") and n} for v, c in r.items()}}
    print(_j.dumps(out, ensure_ascii=False))
    if len(argv) > 2:
        pathlib.Path(argv[2]).write_text(_j.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


COMPARE_WIDTHS = (390, 1333, 1920)
# 後 ≤ 前 を見る項目（orphan は減ってよい・増えても ✗）
COMPARE_KINDS = ("orphan", "gap", "cgap", "rowedge", "herogap", "postergap", "band", "crop", "edge", "solo", "pendhid", "dup", "navgap", "sidebig")


def _render_with(render_src, out):
    """out/ に今の作業場所の写し（scripts は写し・docs は写し・ほかは名前だけ繋ぐ）を作り、render.py を render_src に替えて店長のページを作る。
    作業場所の docs/ は汚さない。写真の網址が開くかは確かめない（render.OPENS を使わない＝網の都合で頭の記事が変わらない）。"""
    import shutil
    import subprocess
    out.mkdir(parents=True)
    for x in ROOT.iterdir():
        if x.name in (".git", "scripts", "docs"):
            continue
        (out / x.name).symlink_to(x)
    shutil.copytree(ROOT / "scripts", out / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "docs", out / "docs", symlinks=True)
    (out / "scripts" / "render.py").write_bytes(render_src)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run([sys.executable, "-c", "import digest; digest._write_page()"], cwd=out, check=True, capture_output=True,
                   env={**env, "PYTHONPATH": str(out / "scripts")})
    return out / "docs"


def compare_main(argv):
    """python harness/aesthetic_count.py --compare [REF]（既定 origin/main）：REF の render.py と今の render.py で店長のページを作り（一時の所）、
    作り物の写真・種固定で 390・1333・1920 を数えて「前 → 後」の表を出す。render を変える PR は、この表（後 ≤ 前）を PR 本文に書く
    （docs/rules/aesthetic.md J）。COMPARE_KINDS のどれかが増えたら終わりの値 1。1920 は 1 回 150 秒ほど（3 幅 × 2 を並べて流す）。"""
    import concurrent.futures as cf
    import subprocess
    import tempfile
    ref = argv[0] if argv else "origin/main"
    src = subprocess.run(["git", "show", f"{ref}:scripts/render.py"], cwd=ROOT, check=True, capture_output=True).stdout
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="wl_compare_"))
    dirs = {"前": _render_with(src, tmp / "before"), "後": _render_with((ROOT / "scripts" / "render.py").read_bytes(), tmp / "after")}

    def one(side, w):
        o = tmp / f"{side}_{w}.json"
        subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--stable", str(dirs[side]), "home/index.html", str(o)],
                       env={**os.environ, "WL_WIDTHS": str(w)}, check=True, capture_output=True)
        return side, w, json.loads(o.read_text(encoding="utf-8"))["total"]

    res = {}
    with cf.ThreadPoolExecutor(3) as ex:
        for side, w, tot in ex.map(lambda a: one(*a), [(s, w) for w in COMPARE_WIDTHS for s in dirs]):
            res[(side, w)] = tot
    worse = []
    print(f"店長のページ（作り物の写真・種固定）{ref} の render → 今の render")
    print("| 幅 | " + " | ".join(COMPARE_KINDS) + " |")
    print("|---" * (len(COMPARE_KINDS) + 1) + "|")
    for w in COMPARE_WIDTHS:
        b, a = res[("前", w)], res[("後", w)]
        cells = []
        for k in COMPARE_KINDS:
            x, y = b.get(k, 0), a.get(k, 0)
            cells.append(str(y) if x == y else f"{x}→{y}" + (" ✗" if y > x else ""))
            if y > x:
                worse.append(f"{w} {k} {x}→{y}")
        print(f"| {w} | " + " | ".join(cells) + " |")
    print("✗ 増えた：" + "・".join(worse) if worse else "✓ どの幅も後 ≤ 前")
    print(f"（ページと数：{tmp}）")
    return 1 if worse else 0


def main(argv=None):
    if (argv or sys.argv[1:])[:1] == ["--stable"]:
        return stable_main((argv or sys.argv[1:])[1:])
    if (argv or sys.argv[1:])[:1] == ["--compare"]:
        sys.exit(compare_main((argv or sys.argv[1:])[1:]))
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
