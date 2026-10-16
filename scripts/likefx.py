"""👍 を押したときの演出（20 種）。版面のテーマ（templates/index.yaml の fx）ごとに選ぶ。

一つの演出 = 大きな 👍 の動き（MOTION）＋ 飛び散るもの（形 × 動き × 数）＋ 文字（任意）。
押した瞬間に再生し（保存は裏）、prefers-reduced-motion のときは大きな演出をしない。
新しい演出を足すとき：FX_JS の FX に一行足し、必要なら形（.fx-○○）か動き（MOVES）を足して、下の FX にも名前を書く。
見本：docs/themes.html。
"""

# id: (日本語名, 説明)。並び順が見本ページの順。FX_JS の FX と同じ id。
FX = {
    "pop":       ("ポン", "跳ねて戻る＋放射線"),
    "stars":     ("きらり星", "くるっと回って星が散る"),
    "manga":     ("ドン！", "上から叩きつけ＋集中線＋擬音"),
    "dots":      ("水玉", "ぷるんと揺れて水玉が弾ける"),
    "film":      ("フィルム", "横から流れ込む＋フィルムが走る"),
    "street":    ("ストリート", "叩きつけ＋警告テープ"),
    "pixel":     ("ドット", "カクカク動く 8 ビットの粒"),
    "glitch":    ("グリッチ", "画面がずれるノイズ"),
    "combo":     ("+1", "数字が飛び出すゲーム風"),
    "rocket":    ("ロケット", "高く飛んで戻る＋噴射"),
    "spotlight": ("スポットライト", "ゆっくり上がって光が差す"),
    "petals":    ("花びら", "ふわっと浮いて花びらが舞う"),
    "goal":      ("ナイス！", "弾むボール＋波紋"),
    "shock":     ("衝撃波", "輪が広がる"),
    "jelly":     ("ぷるぷる", "つぶれて伸びて、しずくが落ちる"),
    "notes":     ("音符", "左右に揺れて音符が上る"),
    "confetti":  ("紙吹雪", "紙吹雪が降る"),
    "hearts":    ("ハート", "ハートがふわふわ上る"),
    "sparkle":   ("きらめき", "回転＋ひし形のきらめき"),
    "stamp":     ("スタンプ", "「いいね」の判子を押す"),
}

FX_CSS = """
.boom{position:fixed;z-index:60;width:0;height:0;pointer-events:none}
.boom>svg{position:absolute;left:0;top:0;width:110px;height:110px;fill:var(--c);stroke:var(--card);stroke-width:1.8;stroke-linejoin:round;
 filter:drop-shadow(4px 4px 0 var(--ink));transform:translate(-50%,-50%) scale(.2);opacity:0}
.boom.no>svg{width:64px;height:64px;fill:var(--card)}
.boom>b{position:absolute;left:0;top:-82px}  /* 👍 がいちばん高い位置の中心。飛び散るものはここから */
.fx-p{position:absolute;left:0;top:0;display:block;opacity:0;font-style:normal}
.fx-bar{width:28px;height:6px;background:var(--c);box-shadow:2px 2px 0 var(--ink)}
.fx-line{width:70px;height:3px;background:var(--c)}
.fx-dot{width:14px;height:14px;border-radius:50%;background:var(--c);box-shadow:2px 2px 0 var(--ink)}
.fx-square{width:10px;height:10px;background:var(--c);box-shadow:3px 3px 0 var(--ink)}
.fx-star{width:22px;height:22px;background:var(--c);clip-path:polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)}
.fx-diamond{width:14px;height:14px;background:var(--c);clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%)}
.fx-petal{width:16px;height:11px;background:var(--c);border-radius:80% 0 80% 0}
.fx-paper{width:9px;height:15px;background:var(--c)}
.fx-ring{width:70px;height:70px;border-radius:50%;border:5px solid var(--c)}
.fx-beam{width:34px;height:180px;background:linear-gradient(transparent,color-mix(in srgb,var(--c) 55%,transparent));clip-path:polygon(40% 0,60% 0,100% 100%,0 100%)}
.fx-slice{width:110px;height:9px;background:linear-gradient(90deg,var(--c) 0 60%,var(--ink) 60% 75%,var(--card) 75%)}
.fx-strip{width:260px;height:44px;background:var(--ink);border-top:8px dotted var(--card);border-bottom:8px dotted var(--card);box-sizing:border-box}
.fx-stripe{width:300px;height:30px;background:repeating-linear-gradient(-45deg,var(--c) 0 16px,var(--ink) 16px 32px);box-shadow:3px 3px 0 var(--ink)}
.fx-note,.fx-heart{font:900 28px/1 var(--font-sans);color:var(--c);text-shadow:2px 2px 0 var(--ink)}
.fx-emb{width:38px;height:38px;filter:drop-shadow(2px 2px 0 var(--ink))}
.fx-emb svg{width:100%;height:100%;display:block}
.fx-txt{position:absolute;left:0;top:-150px;white-space:nowrap;font:900 34px/1 var(--font-sans);letter-spacing:.04em;color:var(--c);
 -webkit-text-stroke:1.5px var(--ink);text-shadow:4px 4px 0 var(--ink);opacity:0}
.fx-txt.stamp{top:-96px;padding:4px 14px;border:5px solid var(--alert);color:var(--alert);background:color-mix(in srgb,var(--card) 85%,transparent);
 -webkit-text-stroke:0;text-shadow:none;font-family:var(--font-serif);border-radius:6px}
"""

# __THUMB__（👍 の SVG）を差し込んでから使う。window.likeFx(ボタン, 票, 演出 id, 作品の小元素 SVG〔なければ省略〕)
FX_JS = r"""
window.likeFx = (() => {
  const R = (a, b) => a + Math.random() * (b - a), P = (x, y) => `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
  const C = 'translate(-50%,-50%) ';
  // 大きな 👍 の動き：[y, 拡大, 回転, 不透明度, 位置(0〜1), easing, 追加の transform]
  const K = rows => rows.map(([y, s, r, o, off, ez, ex]) => {
    const f = { transform: `translate(-50%,${y}) ${typeof s === 'number' ? `scale(${s})` : s} rotate(${r}deg) ${ex || ''}`, opacity: o };
    if (off != null) f.offset = off; if (ez) f.easing = ez; return f;
  });
  const UP = 'cubic-bezier(.2,1.4,.4,1)', IO = 'ease-in-out', BACK = 'cubic-bezier(.6,0,.9,.5)';
  const MOTION = {
    pop: [760, K([['-50%', .2, -25, 0, 0, UP], ['-125%', 1.25, 10, 1, .3, IO], ['-118%', 1, -5, 1, .52, IO], ['-118%', 1.05, 0, 1, .7, BACK], ['-50%', .12, 0, 0]])],
    spin: [820, K([['-50%', .2, 0, 0, 0, UP], ['-125%', 1.2, 0, 1, .35, IO, 'rotateY(360deg)'], ['-118%', 1, 0, 1, .7, BACK, 'rotateY(720deg)'], ['-50%', .12, 0, 0, null, null, 'rotateY(720deg)']])],
    slam: [820, K([['-170%', 2.4, -12, 0, 0, 'ease-in'], ['-115%', 1, -4, 1, .16, IO], ['-112%', 1.08, 4, 1, .26, IO], ['-115%', 1, -2, 1, .36, IO], ['-115%', 1, 0, 1, .72, BACK], ['-50%', .12, 0, 0]])],
    jelly: [860, K([['-50%', .2, 0, 0, 0, UP], ['-118%', 'scale(1.45,.62)', 0, 1, .28, IO], ['-122%', 'scale(.8,1.28)', 0, 1, .42, IO], ['-118%', 'scale(1.12,.9)', 0, 1, .56, IO], ['-118%', 1, 0, 1, .72, BACK], ['-50%', .12, 0, 0]])],
    slide: [880, [
      { transform: 'translate(calc(-50% - 140px),-118%) scale(1) skewX(-18deg)', opacity: 0, easing: 'cubic-bezier(.2,.9,.3,1)' },
      { transform: 'translate(-50%,-118%) scale(1.1) skewX(0)', opacity: 1, offset: .3, easing: IO },
      { transform: 'translate(-50%,-118%) scale(1) skewX(0)', opacity: 1, offset: .7, easing: BACK },
      { transform: 'translate(-50%,-50%) scale(.12) skewX(0)', opacity: 0 }]],
    steps: [800, K([['-50%', .2, 0, 0, 0, 'steps(3)'], ['-125%', 1.2, 0, 1, .3, 'steps(2)'], ['-118%', 1, 0, 1, .7, 'steps(3)'], ['-50%', .12, 0, 0]])],
    glitch: [800, K([['-50%', .2, 0, 0, 0, UP], ['-120%', 1.15, 0, 1, .25, 'steps(1)'], ['-118%', 1.15, 0, 1, .32, 'steps(1)', 'translateX(9px) skewX(14deg)'],
      ['-118%', 1.1, 0, 1, .38, 'steps(1)', 'translateX(-8px)'], ['-118%', 1, 0, 1, .46, IO], ['-118%', 1, 0, 1, .7, BACK], ['-50%', .12, 0, 0]])],
    rocket: [980, K([['-50%', .3, 0, 0, 0, 'cubic-bezier(.3,1.3,.5,1)'], ['-140%', 1.1, 0, 1, .22, 'ease-in'], ['-330%', .85, 0, 1, .5, IO],
      ['-160%', 1, 0, 1, .72, 'ease-in'], ['-50%', .1, 0, 0]])],
    rise: [1050, K([['-40%', .5, 0, 0, 0, 'ease-out'], ['-130%', 1.15, 0, 1, .45, IO], ['-130%', 1.1, 0, 1, .75, BACK], ['-50%', .12, 0, 0]])],
    float: [1100, K([['-50%', .3, -10, 0, 0, 'ease-out'], ['-120%', 1.1, 8, 1, .3, IO], ['-135%', 1.05, -8, 1, .55, IO], ['-125%', 1, 4, 1, .75, BACK], ['-50%', .12, 0, 0]])],
    bounce: [950, K([['-260%', 1, 0, 0, 0, 'ease-in'], ['-115%', 'scale(1.2,.8)', 0, 1, .22, 'ease-out'], ['-160%', 1, 0, 1, .36, 'ease-in'],
      ['-115%', 'scale(1.1,.9)', 0, 1, .48, 'ease-out'], ['-128%', 1, 0, 1, .56, 'ease-in'], ['-115%', 1, 0, 1, .74, BACK], ['-50%', .12, 0, 0]])],
    sway: [1000, K([['-50%', .2, 0, 0, 0, UP], ['-120%', 1.15, -16, 1, .25, IO], ['-120%', 1.1, 14, 1, .42, IO], ['-120%', 1.1, -10, 1, .58, IO], ['-120%', 1, 0, 1, .74, BACK], ['-50%', .12, 0, 0]])],
    stamp: [900, K([['-130%', 2.2, -26, 0, 0, 'ease-in'], ['-112%', .9, -12, 1, .14, 'ease-out'], ['-112%', 1, -12, 1, .74, BACK], ['-50%', .12, 0, 0]])],
  };
  // 飛び散るものの動き：(i, n) → [keyframes, 長さ ms, 遅れ ms]
  const MOVES = {
    burst: (i, n) => { const a = i / n * 6.283 + .4, r0 = 34, r1 = R(72, 96), d = a * 57.3;
      return [[{ transform: C + P(Math.cos(a) * r0, Math.sin(a) * r0) + ` rotate(${d}deg) scale(0)`, opacity: 1 },
        { transform: C + P(Math.cos(a) * (r1 - 10), Math.sin(a) * (r1 - 10)) + ` rotate(${d}deg) scale(1)`, opacity: 1, offset: .55 },
        { transform: C + P(Math.cos(a) * (r1 + 16), Math.sin(a) * (r1 + 16)) + ` rotate(${d}deg) scale(0)`, opacity: 0 }], 520, 100]; },
    grid8: (i) => { const a = (i % 8) * .785, r = 40 + Math.floor(i / 8) * 34;
      return [[{ transform: C + P(0, 0), opacity: 1, easing: 'steps(4)' }, { transform: C + P(Math.cos(a) * r, Math.sin(a) * r), opacity: 1, offset: .6, easing: 'steps(2)' },
        { transform: C + P(Math.cos(a) * (r + 24), Math.sin(a) * (r + 24)), opacity: 0 }], 560, 80]; },
    twinkle: () => { const a = R(0, 6.283), r = R(30, 100), x = Math.cos(a) * r, y = Math.sin(a) * r;
      return [[{ transform: C + P(x, y) + ' rotate(0deg) scale(0)', opacity: 1 }, { transform: C + P(x, y) + ' rotate(90deg) scale(1.2)', opacity: 1, offset: .5 },
        { transform: C + P(x, y) + ' rotate(180deg) scale(0)', opacity: 0 }], 460, R(60, 380)]; },
    focus: (i, n) => { const a = i / n * 6.283 + R(-.12, .12), d = a * 57.3;
      return [[{ transform: C + P(Math.cos(a) * 190, Math.sin(a) * 190) + ` rotate(${d}deg) scaleX(1)`, opacity: 0 },
        { transform: C + P(Math.cos(a) * 120, Math.sin(a) * 120) + ` rotate(${d}deg) scaleX(1)`, opacity: 1, offset: .4 },
        { transform: C + P(Math.cos(a) * 80, Math.sin(a) * 80) + ` rotate(${d}deg) scaleX(.2)`, opacity: 0 }], 420, R(0, 90)]; },
    fall: () => { const x1 = R(-120, 120), y1 = R(-120, -40), r = R(-400, 400);
      return [[{ transform: C + P(R(-20, 20), 0) + ' rotate(0deg)', opacity: 1, easing: 'cubic-bezier(.2,.8,.4,1)' },
        { transform: C + P(x1, y1) + ` rotate(${r / 3}deg)`, opacity: 1, offset: .32, easing: 'cubic-bezier(.5,0,.9,.6)' },
        { transform: C + P(x1 * 1.25, y1 + R(170, 240)) + ` rotate(${r}deg)`, opacity: 0 }], R(950, 1300), R(40, 160)]; },
    rise: (i) => { const x = R(-50, 50);
      return [[{ transform: C + P(x, 30) + ' scale(.5)', opacity: 0 }, { transform: C + P(x + R(-24, 24), -50) + ' scale(1.1)', opacity: 1, offset: .35 },
        { transform: C + P(x + R(-36, 36), -R(130, 180)) + ' scale(.9)', opacity: 0 }], R(850, 1150), i * 70]; },
    ring: (i) => [[{ transform: C + 'scale(.2)', opacity: 1 }, { transform: C + 'scale(2.6)', opacity: 0 }], 650, 60 + i * 130],
    trail: (i) => [[{ transform: C + P(R(-12, 12), 46) + ' scale(1)', opacity: 1 }, { transform: C + P(R(-46, 46), R(90, 140)) + ' scale(0)', opacity: 0 }], 460, i * 32],
    beam: (i, n) => { const a0 = -40 + i * 80 / Math.max(1, n - 1);
      return [[{ transform: `translate(-50%,-100%) rotate(${a0 - 18}deg)`, opacity: 0 }, { transform: `translate(-50%,-100%) rotate(${a0}deg)`, opacity: 1, offset: .4 },
        { transform: `translate(-50%,-100%) rotate(${a0 + 14}deg)`, opacity: 0 }], 950, i * 60]; },
    slice: () => { const x = R(-70, 70), y = R(-60, 60);
      return [[{ transform: C + P(x, y), opacity: 1, easing: 'steps(1)' }, { transform: C + P(x + R(-30, 30), y), opacity: 1, offset: .5, easing: 'steps(1)' },
        { transform: C + P(x, y), opacity: 0 }], 260, R(150, 420)]; },
    swipe: () => [[{ transform: C + P(-240, 40) + ' rotate(-6deg)', opacity: 1, easing: 'cubic-bezier(.2,.9,.3,1)' },
      { transform: C + P(0, 40) + ' rotate(-6deg)', opacity: 1, offset: .45 }, { transform: C + P(240, 40) + ' rotate(-6deg)', opacity: 0 }], 760, 40],
  };
  // 演出の一覧：[👍 の動き, [[形, 数, 動き], …], 文字]
  const FX = {
    pop: ['pop', [['bar', 8, 'burst']]],
    stars: ['spin', [['star', 9, 'burst'], ['star', 5, 'twinkle']]],
    manga: ['slam', [['line', 18, 'focus']], 'ドン！'],
    dots: ['jelly', [['dot', 12, 'burst'], ['dot', 6, 'twinkle']]],
    film: ['slide', [['strip', 1, 'swipe'], ['bar', 6, 'burst']]],
    street: ['slam', [['stripe', 1, 'swipe'], ['bar', 6, 'burst']], 'イイネ！'],
    pixel: ['steps', [['square', 16, 'grid8']]],
    glitch: ['glitch', [['slice', 9, 'slice']]],
    combo: ['pop', [['bar', 6, 'burst']], '+1'],
    rocket: ['rocket', [['dot', 14, 'trail']]],
    spotlight: ['rise', [['beam', 4, 'beam'], ['diamond', 5, 'twinkle']]],
    petals: ['float', [['petal', 14, 'fall']]],
    goal: ['bounce', [['ring', 2, 'ring'], ['bar', 8, 'burst']], 'ナイス！'],
    shock: ['pop', [['ring', 3, 'ring']]],
    jelly: ['jelly', [['dot', 9, 'fall']]],
    notes: ['sway', [['note', 8, 'rise']]],
    confetti: ['pop', [['paper', 22, 'fall']]],
    hearts: ['pop', [['heart', 9, 'rise']]],
    sparkle: ['spin', [['diamond', 10, 'twinkle']]],
    stamp: ['stamp', [], 'いいね'],
  };
  const TEXT = { note: ['♪', '♫'], heart: ['♥'] };
  const PAPER = ['var(--c)', 'var(--gold)', 'var(--rose)', 'var(--card)'];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const play = (btn, v, name, emblem) => {
    btn.animate([{ scale: 1 }, { scale: 1.45 }, { scale: .9 }, { scale: 1 }], { duration: 320, easing: 'ease-out' });
    if (reduce || v === 0) return;
    const r = btn.getBoundingClientRect(), up = v > 0, fx = FX[name] || FX.pop;
    const el = document.createElement('div');
    el.className = 'boom' + (up ? '' : ' no');
    el.style.left = (r.left + r.width / 2) + 'px';
    el.style.top = (r.top + r.height / 2) + 'px';
    el.style.setProperty('--c', getComputedStyle(btn).getPropertyValue('--vc').trim() || 'var(--rose)');
    el.innerHTML = __THUMB__ + '<b></b>';
    document.body.appendChild(el);
    let end = 0;
    const go = (node, kf, dur, delay) => { end = Math.max(end, dur + delay); node.animate(kf, { duration: dur, delay, fill: 'both' }); };
    if (up) {
      const [mname, parts, text] = fx, [mdur, mkf] = MOTION[mname] || MOTION.pop;
      go(el.firstChild, mkf, mdur, 0);
      const layer = el.querySelector('b'), all = parts.slice();
      if (emblem) all.push(['emb', 3, 'rise']);   // 作品の小元素も一緒に飛ぶ
      all.forEach(([shape, n, move]) => { for (let i = 0; i < n; i++) {
        const p = document.createElement('i');
        p.className = 'fx-p fx-' + shape;
        if (TEXT[shape]) p.textContent = TEXT[shape][i % TEXT[shape].length];
        if (shape === 'paper') p.style.background = PAPER[i % PAPER.length];
        if (shape === 'beam') p.style.transformOrigin = '50% 100%';
        if (shape === 'emb') p.innerHTML = emblem;
        layer.appendChild(p);
        const [kf, dur, delay] = MOVES[move](i, n);
        go(p, kf, dur, delay);
      } });
      if (text) {
        const t = document.createElement('i');
        t.className = 'fx-txt' + (name === 'stamp' ? ' stamp' : '');
        t.textContent = text;
        el.appendChild(t);
        go(t, [{ transform: C + 'scale(0) rotate(-24deg)', opacity: 0, easing: UP }, { transform: C + 'scale(1.15) rotate(-8deg)', opacity: 1, offset: .25 },
          { transform: C + 'scale(1) rotate(-8deg)', opacity: 1, offset: .7 }, { transform: C + 'scale(.6) rotate(-8deg)', opacity: 0 }], mdur, 60);
      }
    } else {
      go(el.firstChild, [{ transform: 'translate(-50%,-50%) scale(.3,-.3)', opacity: 0, easing: 'ease-out' },
        { transform: 'translate(-50%,-110%) scale(.8,-.8)', opacity: 1, offset: .3, easing: 'ease-in' },
        { transform: 'translate(-50%,-30%) scale(.35,-.35) rotate(-12deg)', opacity: 0 }], 480, 0);
    }
    setTimeout(() => el.remove(), end + 80);
  };
  play.names = Object.keys(FX);
  return play;
})();
"""
