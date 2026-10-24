() => {
  // 記事どうしの「近さ」：写真が上の記事か下の記事か迷わないこと（ゲシュタルトの近接）
  const vis = el => { const r = el.getBoundingClientRect(); return r.height > 0 && r.width > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const parts = a => [...a.children].filter(c => !c.matches('.lk,.vt,.xplay') && getComputedStyle(c).position !== 'absolute' && vis(c));
  const out = [];
  document.querySelectorAll('section.sec .grid').forEach(g => {
    const arts = [...g.querySelectorAll(':scope > article.card, :scope > .side > article.card')].filter(vis);
    for (const a of arts) {
      const ps = parts(a); if (ps.length < 2) continue;
      const ra = a.getBoundingClientRect();
      let inner = 0;   // 同じ記事の中で縦に並ぶ部品どうしのいちばん大きい隙間
      for (let i = 1; i < ps.length; i++) {
        const p = ps[i-1].getBoundingClientRect(), q = ps[i].getBoundingClientRect();
        if (Math.min(p.right, q.right) - Math.max(p.left, q.left) > 20 && q.top >= p.bottom - 1) inner = Math.max(inner, q.top - p.bottom);
      }
      // すぐ上にある別の記事（横に半分以上重なる）
      let prev = null, best = -1e9;
      for (const b of arts) { if (b === a) continue; const rb = b.getBoundingClientRect();
        const ov = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        if (ov > 0.5 * Math.min(ra.width, rb.width) && rb.bottom <= ra.top + 1 && rb.bottom > best) { best = rb.bottom; prev = b; } }
      if (!prev) continue;
      const pp = parts(prev); const last = pp[pp.length-1].getBoundingClientRect();
      const outer = ps[0].getBoundingClientRect().top - last.bottom;   // 上の記事の最後の字 → この記事の最初の部品
      const line = parseFloat(getComputedStyle(prev).borderBottomWidth) > 0;
      if (outer < Math.max(24, 2.5 * inner) && !line) out.push({sec: (a.closest('section.sec').dataset.k||'').slice(0,20), inner: Math.round(inner), outer: Math.round(outer)});
    }
  });
  return out;
}
