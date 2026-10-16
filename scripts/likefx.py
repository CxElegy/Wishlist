"""👍 を押したときの演出（20 種）。版面のテーマ（templates/index.yaml の fx）ごとに選ぶ。

一つの演出 = 大きな 👍 の動き（MOTION）＋ 飛び散るもの（形 × 動き × 数）＋ 文字（任意）。
押した瞬間に再生し（保存は裏）、prefers-reduced-motion のときは大きな演出をしない。
粒（紙吹雪・星・ハート・花びら・音符・水玉・ドット）は自作せず canvas-confetti（CONFETTI_JS）に任せる。
擬音（ドン！など）は漫画の作法：極太書体 Dela Gothic One・白と黒の二重フチ・ウニフラ（トゲの吹き出し）・一文字ずつ叩きつけ・画面の揺れ。
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

# 擬音の書体（使う文字だけ読み込む）と粒のライブラリ。どちらも演出のあるページだけで読む
SFX_TEXT = "ドン！イイネナス+1いね"
SFX_FONT = ("https://fonts.googleapis.com/css2?family=Dela+Gothic+One&display=swap&text="
            + "".join(f"%{b:02X}" for b in SFX_TEXT.encode("utf-8")))
CONFETTI_JS = "https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js"

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
.fx-emb svg,.fx-emb img{width:100%;height:100%;display:block;object-fit:contain}
/* 擬音：ウニフラ（トゲの吹き出し、白＋墨のフチ＋色の影）の上に、一文字ずつ叩きつける極太の文字 */
.fx-sfx{position:absolute;left:0;top:-160px;width:0;height:0}
.fx-sfx svg{position:absolute;left:-95px;top:-62px;width:190px;height:124px;overflow:visible;opacity:0}
.fx-sfx .burst{fill:var(--card);stroke:var(--ink);stroke-width:5;stroke-linejoin:round}
.fx-sfx .burst2{fill:var(--c);stroke:var(--ink);stroke-width:5;stroke-linejoin:round}
.fx-sfx span{position:absolute;left:0;top:0;display:flex;transform:translate(-50%,-50%) rotate(-9deg);white-space:nowrap}
.fx-sfx i{display:block;font:400 48px/1 "Dela Gothic One",var(--font-sans);font-style:normal;color:var(--c);letter-spacing:-.02em;
 -webkit-text-stroke:9px var(--ink);paint-order:stroke fill;text-shadow:5px 6px 0 var(--ink);opacity:0}
.fx-sfx.game span{transform:translate(-50%,-50%)}
.fx-sfx.game i{color:var(--gold);font-size:44px}
.fx-sfx.stamp span{padding:6px 16px 4px;border:5px double var(--alert);border-radius:8px;background:color-mix(in srgb,var(--card) 88%,transparent);transform:translate(-50%,-50%) rotate(-12deg)}
.fx-sfx.stamp i{color:var(--alert);-webkit-text-stroke:0;text-shadow:none;font-size:38px;letter-spacing:.08em;opacity:1}
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
  // 粒は canvas-confetti に任せる（https://github.com/catdad/canvas-confetti の公式サンプルの設定を元に、色だけ版面に合わせる）
  const hex = (() => { const cx = document.createElement('canvas').getContext('2d'); return c => { cx.fillStyle = '#000'; cx.fillStyle = c; return cx.fillStyle; }; })();
  const tok = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const CONFETTI = {
    confetti: (o, cs) => confetti({ ...o, particleCount: 90, spread: 75, startVelocity: 38, colors: cs }),
    stars: (o, cs) => [0, 120].forEach(d => setTimeout(() => confetti({ ...o, shapes: ['star'], colors: cs, spread: 360, ticks: 60, gravity: 0, decay: .94, startVelocity: 26, particleCount: 26, scalar: 1.2 }), d)),
    sparkle: (o, cs) => confetti({ ...o, shapes: ['star'], colors: cs, spread: 360, ticks: 50, gravity: 0, decay: .92, startVelocity: 18, particleCount: 30, scalar: .8 }),
    dots: (o, cs) => confetti({ ...o, shapes: ['circle'], colors: cs, spread: 100, particleCount: 50, startVelocity: 30, scalar: 1.1 }),
    pixel: (o, cs) => confetti({ ...o, shapes: ['square'], colors: cs, spread: 90, particleCount: 50, startVelocity: 34, flat: true }),
    hearts: (o, cs) => confetti({ ...o, shapes: [confetti.shapeFromText({ text: '❤️', scalar: 2 })], scalar: 2, spread: 80, particleCount: 18, startVelocity: 26, gravity: .6, ticks: 90 }),
    petals: (o, cs) => confetti({ ...o, shapes: [confetti.shapeFromText({ text: '🌸', scalar: 2 })], scalar: 2, spread: 120, particleCount: 22, startVelocity: 22, gravity: .35, drift: .6, ticks: 160 }),
    notes: (o, cs) => confetti({ ...o, shapes: ['♪', '♫'].map(t => confetti.shapeFromText({ text: t, scalar: 2, color: cs[0] })), scalar: 2, spread: 70, particleCount: 16, startVelocity: 24, gravity: -.15, ticks: 110 }),
  };
  const burstPath = (n, r1, r2) => { let d = ''; for (let i = 0; i < n * 2; i++) { const a = i / (n * 2) * 6.283, r = (i % 2 ? r2 * R(.85, 1.1) : r1 * R(.9, 1.12));
    d += (i ? 'L' : 'M') + (95 + Math.cos(a) * r * 1.45).toFixed(1) + ' ' + (62 + Math.sin(a) * r).toFixed(1); } return d + 'Z'; };
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
      const layer = el.querySelector('b');
      const viaLib = window.confetti && CONFETTI[name];
      if (viaLib) {
        const c = hex(getComputedStyle(btn).getPropertyValue('--vc').trim() || tok('--rose'));
        CONFETTI[name]({ origin: { x: (r.left + r.width / 2) / innerWidth, y: (r.top - 70) / innerHeight }, zIndex: 70, disableForReducedMotion: true },
          [c, hex(tok('--gold')), hex(tok('--rose')), hex(tok('--card'))]);
      }
      const all = viaLib ? [] : parts.slice();
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
      if (text) {   // 擬音：ウニフラ → 一文字ずつ叩きつけ → 揺れ → ぱっと消える
        const kind = name === 'stamp' ? 'stamp' : name === 'combo' ? 'game' : 'manga';
        const t = document.createElement('div');
        t.className = 'fx-sfx ' + kind;
        if (kind === 'manga') {   // 吹き出しの幅は文字数に合わせる
          const bw = 80 + [...text].length * 46, bh = 132;
          t.innerHTML = '<svg viewBox="0 0 190 124" preserveAspectRatio="none" style="width:' + bw + 'px;height:' + bh + 'px;left:' + (-bw / 2) + 'px;top:' + (-bh / 2) + 'px">'
            + '<path class="burst2" d="' + burstPath(16, 52, 36) + '" transform="translate(6 6)"/><path class="burst" d="' + burstPath(16, 52, 36) + '"/></svg>';
        }
        const line = document.createElement('span');
        [...text].forEach(ch => { const i = document.createElement('i'); i.textContent = ch; line.appendChild(i); });
        t.appendChild(line);
        el.appendChild(t);
        const svg = t.querySelector('svg');
        if (svg) go(svg, [{ transform: 'scale(.2) rotate(-25deg)', opacity: 0, easing: 'cubic-bezier(.2,1.6,.4,1)' }, { transform: 'scale(1.08) rotate(3deg)', opacity: 1, offset: .2 },
          { transform: 'scale(1) rotate(0deg)', opacity: 1, offset: .32 }, { transform: 'scale(1) rotate(0deg)', opacity: 1, offset: .78 }, { transform: 'scale(1.25)', opacity: 0 }], mdur + 120, 40);
        if (kind === 'game') {
          go(line, [{ transform: 'translate(-50%,-10%) scale(.6)', opacity: 0, easing: 'cubic-bezier(.2,1.5,.4,1)' }, { transform: 'translate(-50%,-50%) scale(1.15)', opacity: 1, offset: .25 },
            { transform: 'translate(-50%,-90%) scale(1)', opacity: 1, offset: .75 }, { transform: 'translate(-50%,-130%) scale(1)', opacity: 0 }], mdur + 200, 60);
          line.querySelectorAll('i').forEach(i => { i.style.opacity = 1; });
        } else if (kind === 'stamp') {
          go(line, [{ transform: 'translate(-50%,-50%) rotate(-24deg) scale(2.4)', opacity: 0, easing: 'cubic-bezier(.5,0,.8,.4)' }, { transform: 'translate(-50%,-50%) rotate(-12deg) scale(.94)', opacity: 1, offset: .16 },
            { transform: 'translate(-50%,-50%) rotate(-12deg) scale(1)', opacity: 1, offset: .24 }, { transform: 'translate(-50%,-50%) rotate(-12deg) scale(1)', opacity: 1, offset: .8 },
            { transform: 'translate(-50%,-50%) rotate(-12deg) scale(1.05)', opacity: 0 }], mdur + 200, 0);
        } else {
          line.querySelectorAll('i').forEach((i, n) => go(i, [{ transform: `scale(2.8) rotate(${R(-30, 30).toFixed(0)}deg)`, opacity: 0, easing: 'cubic-bezier(.5,0,.75,0)' },
            { transform: `scale(.88) rotate(${R(-6, 6).toFixed(0)}deg)`, opacity: 1, offset: .14, easing: 'cubic-bezier(.3,1.6,.5,1)' },
            { transform: 'scale(1) rotate(0deg)', opacity: 1, offset: .22 }, { transform: 'scale(1) rotate(0deg)', opacity: 1, offset: .78 },
            { transform: 'scale(1.2) rotate(0deg)', opacity: 0 }], mdur + 160, 90 + n * 70));
        }
        // 叩きつけた瞬間に、押したカード（なければ版面）が揺れる
        const hit = btn.closest('.card,.top,.wc,.pk,li') || btn.closest('section');
        if (hit && kind !== 'game') setTimeout(() => hit.animate([{ translate: '0 0' }, { translate: '-5px 3px' }, { translate: '4px -3px' }, { translate: '-3px 1px' }, { translate: '0 0' }],
          { duration: 240, easing: 'linear' }), kind === 'stamp' ? 140 : 150);
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
