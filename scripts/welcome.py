"""入口と新しく始める（2026-10-21，試作・テストグラウンド）。

App のように 1 ページで画面を切り替える：
  ① 入口（何のサイトか・店長のページの本物の画面・「新しく始める」「ログイン」「店長のページを見る」）
  ② 名前と規約 → ③ 好きなジャンル（8 つの板块）→ ④ カードを左右に（気になる / パス）→ ⑤ 最初の版面の確認 → ⑥ 店長が集めに行く
このブラウザが覚えている人（localStorage の wl-user）は入口を飛ばして自分のページへ（いまは店長のページ。?stay で止まる）。
試作なので登録はしない（名前が空いているかだけ本物のデータベースで確かめる）。

カードの候補は規則で作る（AI なし）：AniList の話題のアニメ・マンガ、Steam の売れ筋、店長がフォローしてきたもの（archive/test1 の関注項とアイコン）。
  python scripts/welcome.py            → docs/testground/welcome.html（候補はその時点のものを埋め込む）
"""
import html
import json
import pathlib
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render  # noqa: E402
import taxonomy  # noqa: E402

OUT = ROOT / "docs" / "testground" / "welcome.html"
SHOP = "../test2/"            # 店長のページ（入口からの行き先）
UA = {"User-Agent": "Mozilla/5.0 (watchlist welcome builder)", "Content-Type": "application/json"}
e = html.escape


def _get(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def anilist(kind, n):
    """AniList の「いま話題」（TRENDING_DESC）。表紙は縦長。"""
    q = ("{Page(perPage:%d){media(sort:TRENDING_DESC,type:%s,isAdult:false){title{native romaji} coverImage{extraLarge large}}}}"
         % (n, kind))
    try:
        media = _get("https://graphql.anilist.co", {"query": q})["data"]["Page"]["media"]
    except Exception as ex:  # 取れなくても入口は作る
        print("anilist", kind, ex, file=sys.stderr)
        return []
    sub = "アニメ · いま話題" if kind == "ANIME" else "マンガ · いま話題"
    return [{"name": m["title"]["native"] or m["title"]["romaji"], "img": m["coverImage"]["extraLarge"] or m["coverImage"]["large"],
             "sub": sub, "sec": "影视"} for m in media if m["title"]["native"] or m["title"]["romaji"]]


def steam(n):
    """Steam の売れ筋（日本）。ゲームだけ（ソフトやセットは名前で除く）。"""
    try:
        cats = _get("https://store.steampowered.com/api/featuredcategories?cc=jp&l=japanese")
    except Exception as ex:
        print("steam", ex, file=sys.stderr)
        return []
    out, seen = [], set()
    for key in ("top_sellers", "new_releases"):
        for it in (cats.get(key) or {}).get("items") or []:
            name = it.get("name") or ""
            if not name or name in seen or "Steam Deck" in name or it.get("type") not in (0, None):
                continue
            seen.add(name)
            out.append({"name": name, "img": it.get("large_capsule_image") or it.get("header_image"),
                        "sub": "ゲーム · " + ("売れ筋" if key == "top_sellers" else "新作"), "sec": "游戏", "wide": True})
    return out[:n]


def shop_picks():
    """店長がフォローしてきたもの（test1 の関注項・アイコンつき）。カードに「店長も見ている」。"""
    data = yaml.safe_load((ROOT / "archive" / "test1" / "items.yaml").read_text(encoding="utf-8"))
    out = []
    for it in data.get("items") or []:
        icon = (it.get("icon") or {}).get("image") if isinstance(it.get("icon"), dict) else None
        if not icon or it.get("parent"):
            continue
        sec = taxonomy.canonical(it.get("section") or taxonomy.BY_TYPE.get(it.get("type", "product"), "好物"))
        out.append({"name": it["name"], "img": "../test1/" + icon, "sub": (it.get("subtitle") or "")[:30],
                    "sec": sec, "shop": True, "square": True})
    return out


def sections():
    return [{"key": k, "ja": r["ja"], "en": r.get("en") or "", "color": r["color"],
             "icon": render.TWEMOJI.format(r["icon"]) if r.get("icon") else ""} for k, r in taxonomy.SECTIONS.items()]


CSS = """
:root{--app:480px}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font-sans)}
.scr{min-height:100vh;min-height:100dvh;display:none;flex-direction:column}
.scr.on{display:flex}
.wrap{width:min(var(--app),100%);margin:0 auto;padding:20px 16px 28px;box-sizing:border-box;display:flex;flex-direction:column;gap:16px;flex:1}
/* ---- ① 入口 ---- */
#s-home .wrap{width:min(1100px,100%);gap:28px}
.hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:32px;align-items:center;padding-top:16px}
.logo{display:inline-block;align-self:flex-start;margin:0;background:var(--card);border:3px solid var(--ink);box-shadow:var(--shadow-l);
 padding:10px 18px;transform:rotate(var(--tilt));font:900 clamp(30px,5vw,52px)/1.1 var(--font-sans);letter-spacing:.02em;white-space:nowrap}
.catch{margin:18px 0 0;font:900 clamp(20px,2.6vw,26px)/1.5 var(--font-sans)}
.catch em{font-style:normal;background:linear-gradient(transparent 62%,var(--gold) 62%)}
.lede{margin:10px 0 0;font-size:15px;line-height:1.8;opacity:.85}
.cta{display:flex;flex-wrap:wrap;gap:12px;margin-top:22px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:48px;padding:0 22px;border:3px solid var(--ink);background:var(--card);
 color:var(--ink);font:900 16px var(--font-sans);text-decoration:none;cursor:pointer;box-shadow:var(--shadow);transition:transform .12s}
.btn:hover,.btn:focus-visible{transform:translate(-2px,-2px)}
.btn:active{transform:translate(2px,2px);box-shadow:none}
.btn.main{background:var(--rose);color:var(--card)}
.btn.sub{background:transparent;box-shadow:none;border-width:2px;font-size:14px;min-height:42px}
.btn[disabled]{opacity:.45;cursor:not-allowed;transform:none}
.btn[hidden]{display:none}
.shot{position:relative}
.shot .pc{width:100%;border:3px solid var(--ink);box-shadow:var(--shadow-l);display:block;transform:rotate(1.2deg);background:var(--card)}
.shot .sp{position:absolute;right:-10px;bottom:-26px;width:26%;border:3px solid var(--ink);box-shadow:var(--shadow);transform:rotate(-3deg);background:var(--card)}
.how{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:18px}
.how li{list-style:none;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:16px 18px;display:flex;flex-direction:column;gap:6px}
.how b{font:900 17px/1.4 var(--font-sans)}
.how .n{font:400 30px/1 var(--font-num);color:var(--rose)}
.how p{margin:0;font-size:14px;line-height:1.7;opacity:.85}
.how ul{padding:0;margin:0;display:contents}
.pop{align-self:flex-start;position:relative;background:var(--card);box-shadow:var(--shadow);padding:10px 16px;transform:rotate(-2deg);font:20px/1.4 var(--font-hand)}
.foot{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;opacity:.8}
.foot a{color:inherit}
.back-on{display:none;align-items:center;gap:10px;background:var(--ink);color:var(--card);padding:10px 14px;font-size:14px}
.back-on.on{display:flex}
.back-on a{color:var(--gold);font-weight:900}
/* ---- 手順の画面（スマホ 1 枚の大きさ） ---- */
.bar{display:flex;align-items:center;gap:10px}
.bar button{border:0;background:none;font:900 22px var(--font-sans);cursor:pointer;color:var(--ink);padding:4px 8px}
.dots{display:flex;gap:6px;flex:1;justify-content:center}
.dots i{width:28px;height:6px;background:var(--hair)}
.dots i.on{background:var(--rose)}
.q{margin:6px 0 0;font:900 24px/1.4 var(--font-sans)}
.qs{margin:0;font-size:14px;line-height:1.7;opacity:.8}
.field{display:flex;flex-direction:column;gap:6px;font-weight:700}
.field input{padding:12px 14px;border:3px solid var(--ink);background:var(--card);font:700 18px var(--font-sans);color:var(--ink);min-width:0}
.hint{min-height:1.5em;margin:0;font-size:13px}
.hint.ok{color:var(--good)}.hint.ng{color:var(--alert)}
.agree{display:flex;gap:10px;align-items:flex-start;background:var(--card);border:2px solid var(--ink);padding:12px 14px;font-size:14px;line-height:1.6}
.agree input{width:20px;height:20px;flex:none;margin-top:2px}
.agree a{color:var(--rose)}
.grow{flex:1}
.genres{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.genre{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:6px;padding:14px;border:3px solid var(--ink);background:var(--card);
 cursor:pointer;text-align:left;font:900 16px/1.3 var(--font-sans);color:var(--ink);box-shadow:var(--shadow)}
.genre img{width:34px;height:34px}
.genre small{font:700 var(--fs-tag)/1 var(--font-mono);letter-spacing:.12em;opacity:.7}
.genre[aria-pressed=true]{background:var(--sc);color:var(--card);transform:rotate(-1deg)}
.genre[aria-pressed=true]::after{content:"✓";position:absolute;top:8px;right:10px;font-size:20px}
/* カード */
.deck{position:relative;flex:1;min-height:clamp(250px,calc(100dvh - 380px),520px);display:grid;place-items:center}
#s-cards .wrap{gap:12px}
@media (max-height:820px){#s-cards .qs{display:none}}
.card{position:absolute;inset:0 0 0 0;display:flex;flex-direction:column;background:var(--card);border:3px solid var(--ink);box-shadow:var(--shadow-l);
 overflow:hidden;touch-action:pan-y;user-select:none;transition:transform .25s ease,opacity .25s}
.card.drag{transition:none}
.card .ph{position:relative;flex:1;min-height:0;background:var(--sheet);overflow:hidden}
.card .ph img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.card .ph .blur{object-fit:cover;filter:blur(18px) saturate(1.2);opacity:.55;transform:scale(1.15)}
.card .tx{padding:12px 16px 14px;display:flex;flex-direction:column;gap:4px;border-top:3px solid var(--ink)}
.card .tx b{font:900 20px/1.35 var(--font-sans);overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.card .tx span{font-size:13px;opacity:.8}
.card .sec{position:absolute;top:12px;left:12px;background:var(--sc);color:var(--card);padding:3px 10px;font:900 var(--fs-label)/1.6 var(--font-sans);transform:skewX(var(--skew))}
.card .mine{position:absolute;top:12px;right:12px;background:var(--card);padding:5px 10px;box-shadow:var(--shadow);transform:rotate(3deg);font:15px/1.2 var(--font-hand)}
.card .st{position:absolute;top:40%;left:50%;padding:6px 16px;border:4px solid currentColor;font:900 30px/1 var(--font-sans);opacity:0;pointer-events:none;background:var(--card)}
.card .st.y{color:var(--rose);transform:translate(-50%,-50%) rotate(-12deg)}
.card .st.n{color:var(--ink);transform:translate(-50%,-50%) rotate(12deg)}
.card.out-r{transform:translateX(130%) rotate(18deg);opacity:0}
.card.out-l{transform:translateX(-130%) rotate(-18deg);opacity:0}
.empty{text-align:center;font-size:15px;line-height:1.8}
.acts{display:flex;justify-content:center;gap:22px}
.act{width:68px;height:68px;border-radius:50%;border:3px solid var(--ink);background:var(--card);font:900 26px/1 var(--font-sans);cursor:pointer;box-shadow:var(--shadow);color:var(--ink)}
.act.y{background:var(--rose);color:var(--card)}
.act:active{transform:translate(2px,2px);box-shadow:none}
.count{text-align:center;font:700 13px var(--font-mono);opacity:.75}
/* 確認 */
.picked{display:flex;flex-direction:column;gap:10px;padding:0;margin:0}
.picked li{list-style:none;display:flex;align-items:center;gap:12px;background:var(--card);border:2px solid var(--ink);padding:8px 10px}
.picked img{width:48px;height:48px;object-fit:cover;flex:none;border:2px solid var(--ink)}
.picked b{flex:1;min-width:0;font-size:15px;overflow-wrap:anywhere}
.picked .nm{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.picked small{display:block;font-weight:500;font-size:12px;opacity:.75}
.picked button{border:2px solid var(--ink);background:transparent;font:700 13px var(--font-sans);padding:4px 10px;cursor:pointer;color:var(--ink)}
.picked li.off{opacity:.45}
.done{display:flex;flex-direction:column;align-items:center;text-align:center;gap:18px;padding-top:40px}
.done .pop{align-self:center;font-size:26px}
.done p{margin:0;line-height:1.8}
.proto{font:700 12px var(--font-mono);background:var(--gold);color:var(--ink);padding:4px 10px;align-self:center}
@media (max-width:820px){
 .hero{grid-template-columns:1fr;gap:26px}
 .shot{margin:0 6px 30px}
 .how{grid-template-columns:1fr}
}
@media (prefers-reduced-motion:reduce){.card,.btn{transition:none}}
"""

JS = r"""
(() => {
  const C = JSON.parse(document.getElementById('wl-cfg').textContent);
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => '&#' + c.charCodeAt(0) + ';');
  const rpc = (fn, body) => fetch(C.url.replace(/\/$/, '') + '/rest/v1/rpc/' + fn, { method: 'POST',
    headers: { apikey: C.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }).then(r => r.ok ? r.json() : Promise.reject(r.status));
  // このブラウザが覚えている人：入口を飛ばして自分のページへ（いまは店長のページ）。?stay なら止まる
  let me = null; try { me = JSON.parse(localStorage.getItem('wl-user') || 'null'); } catch (_) {}
  const stay = /[?&]stay\b/.test(location.search);
  if (me && me.name) {
    if (!stay) { location.replace(C.shop); return; }
    const b = $('.back-on'); b.classList.add('on'); $('b', b).textContent = me.name;
  }
  // ---- 画面の切り替え（戻るボタンでも戻れる）
  const ORDER = ['home', 'name', 'genre', 'cards', 'check', 'done'];
  const st = { name: '', genres: new Set(), liked: [], seen: 0 };
  function show(id, push = true) {
    $$('.scr').forEach(s => s.classList.toggle('on', s.id === 's-' + id));
    $$('#s-' + id + ' .dots i').forEach((d, i) => d.classList.toggle('on', i < ORDER.indexOf(id)));
    if (push) history.pushState({ id }, '', '#' + id);
    window.scrollTo(0, 0);
    const f = $('#s-' + id + ' [autofocus]'); if (f) f.focus();
    if (id === 'cards') deal();
    if (id === 'check') check();
  }
  addEventListener('popstate', ev => show((ev.state && ev.state.id) || 'home', false));
  $$('[data-go]').forEach(b => b.addEventListener('click', () => show(b.dataset.go)));
  $$('.bar [data-back]').forEach(b => b.addEventListener('click', () => history.back()));
  // ---- ② 名前と規約
  const inp = $('#nm'), hint = $('#nm-hint'), agree = $('#agree'), next1 = $('#to-genre'); let tm = 0, okName = false;
  const v1 = () => { next1.disabled = !(okName && agree.checked); };
  inp.addEventListener('input', () => {
    clearTimeout(tm); okName = false; v1(); const n = inp.value.trim(); hint.className = 'hint';
    if (n.length < 2) { hint.textContent = n ? '2 文字以上にしてください' : ''; return; }
    if (/[\s<>"'`/\\]/.test(n)) { hint.textContent = '空白や < > " \' ` / \\ は使えません'; hint.className = 'hint ng'; return; }
    hint.textContent = '確かめています…';
    tm = setTimeout(() => rpc('name_available', { p_name: n }).then(ok => {
      if (inp.value.trim() !== n) return;
      okName = !!ok; hint.textContent = ok ? '✓ この名前は使えます' : 'この名前はもう使われています'; hint.className = 'hint ' + (ok ? 'ok' : 'ng'); v1();
    }).catch(() => { okName = true; hint.textContent = '（確かめられませんでした。試作なのでこのまま進めます）'; v1(); }), 350);
  });
  agree.addEventListener('change', v1);
  next1.addEventListener('click', () => { st.name = inp.value.trim(); show('genre'); });
  // ---- ③ ジャンル
  const next2 = $('#to-cards');
  $$('.genre').forEach(g => g.addEventListener('click', () => {
    const on = g.getAttribute('aria-pressed') !== 'true'; g.setAttribute('aria-pressed', String(on));
    on ? st.genres.add(g.dataset.k) : st.genres.delete(g.dataset.k);
    next2.disabled = !st.genres.size; next2.textContent = st.genres.size ? st.genres.size + ' つで次へ' : 'ひとつ以上えらぶ';
  }));
  // ---- ④ カード（右 = 気になる、左 = パス。ボタン・キーボード ← → でも）
  let pile = [], idx = 0;
  function deal() {
    const pick = C.cards.filter(c => st.genres.has(c.sec));
    // ジャンルを順番に混ぜる・店長のものを先に少し
    const by = {}; pick.forEach(c => (by[c.sec] = by[c.sec] || []).push(c));
    // 店長のものと話題のものを交互に（店長のものだけが先に並ばないように）
    Object.keys(by).forEach(k => { const sh = by[k].filter(c => c.shop), tr = by[k].filter(c => !c.shop), mix = [];
      while (sh.length || tr.length) { if (tr.length) mix.push(tr.shift()); if (sh.length) mix.push(sh.shift()); if (tr.length) mix.push(tr.shift()); }
      by[k] = mix; });
    pile = []; const keys = Object.keys(by);
    for (let i = 0; pile.length < C.max && keys.some(k => by[k][i]); i++) keys.forEach(k => { if (by[k][i] && pile.length < C.max) pile.push(by[k][i]); });
    idx = 0; st.liked = []; render();
  }
  const deck = $('.deck'), cnt = $('.count');
  function cardHtml(c) {
    const sec = C.secs[c.sec] || {};
    return '<div class="card" style="--sc:' + esc(sec.color) + '"><div class="ph"><img class="blur" src="' + esc(c.img) + '" alt="" referrerpolicy="no-referrer">' +
      '<img src="' + esc(c.img) + '" alt="" referrerpolicy="no-referrer" draggable="false"></div>' +
      '<span class="sec">' + esc(sec.ja || '') + '</span>' + (c.shop ? '<span class="mine">店長も見ている</span>' : '') +
      '<span class="st y">気になる</span><span class="st n">パス</span>' +
      '<div class="tx"><b>' + esc(c.name) + '</b><span>' + esc(c.sub || '') + '</span></div></div>';
  }
  function render() {
    if (idx >= pile.length) {
      deck.innerHTML = '<p class="empty">' + (pile.length ? 'これで全部です。<br>気になる ' + st.liked.length + ' 件' : 'このジャンルの候補はまだありません。<br>あとで名前で追加できます') + '</p>';
      cnt.textContent = ''; $('#to-check').hidden = false; return;
    }
    deck.innerHTML = cardHtml(pile[idx]); cnt.textContent = (idx + 1) + ' / ' + pile.length + '　·　気になる ' + st.liked.length;
    $('#to-check').hidden = st.liked.length === 0;
    drag($('.card', deck));
  }
  function decide(yes) {
    const card = $('.card', deck); if (!card) return;
    if (yes) st.liked.push(pile[idx]);
    card.classList.add(yes ? 'out-r' : 'out-l'); idx++;
    setTimeout(render, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220);
  }
  function drag(card) {
    let x0 = null, dx = 0;
    const y = $('.st.y', card), n = $('.st.n', card);
    card.addEventListener('pointerdown', ev => { x0 = ev.clientX; dx = 0; card.classList.add('drag'); card.setPointerCapture(ev.pointerId); });
    card.addEventListener('pointermove', ev => { if (x0 == null) return; dx = ev.clientX - x0;
      card.style.transform = 'translateX(' + dx + 'px) rotate(' + dx / 18 + 'deg)'; y.style.opacity = Math.max(0, dx / 120); n.style.opacity = Math.max(0, -dx / 120); });
    const up = () => { if (x0 == null) return; x0 = null; card.classList.remove('drag');
      if (Math.abs(dx) > 100) { card.style.transform = ''; decide(dx > 0); } else { card.style.transform = ''; y.style.opacity = n.style.opacity = 0; } };
    card.addEventListener('pointerup', up); card.addEventListener('pointercancel', up);
  }
  $('.act.y').addEventListener('click', () => decide(true));
  $('.act.n').addEventListener('click', () => decide(false));
  addEventListener('keydown', ev => { if (!$('#s-cards').classList.contains('on')) return;
    if (ev.key === 'ArrowRight') decide(true); if (ev.key === 'ArrowLeft') decide(false); });
  // ---- ⑤ 確認（最初は C.first 件まで。多い分は外しておき、押せば戻せる）
  function check() {
    const ul = $('.picked'); ul.innerHTML = '';
    st.liked.forEach((c, i) => {
      const li = document.createElement('li'); if (i >= C.first) li.classList.add('off');
      li.innerHTML = '<img src="' + esc(c.img) + '" alt="" referrerpolicy="no-referrer"><b><span class="nm">' + esc(c.name) + '</span><small>' + esc((C.secs[c.sec] || {}).ja || '') + '</small></b>' +
        '<button type="button">' + (i >= C.first ? '入れる' : '外す') + '</button>';
      $('button', li).addEventListener('click', () => { li.classList.toggle('off'); $('button', li).textContent = li.classList.contains('off') ? '入れる' : '外す'; sum(); });
      ul.appendChild(li);
    });
    sum();
  }
  function sum() { const n = $$('.picked li:not(.off)').length; const b = $('#to-done'); b.disabled = !n;
    b.textContent = n ? 'この ' + n + ' つで始める' : 'ひとつ以上残してください';
    $('#first-note').textContent = st.liked.length > C.first ? '最初は ' + C.first + ' つまでがおすすめ（店長が集める量が多すぎないように）。あとで増やせます。' : ''; }
  $('#to-done').addEventListener('click', () => {
    const names = $$('.picked li:not(.off) .nm').map(b => b.textContent);
    $('#done-name').textContent = st.name; $('#done-list').textContent = names.join('、'); show('done');
  });
})();
"""


def build():
    cards = anilist("ANIME", 12) + anilist("MANGA", 6) + steam(12) + shop_picks()
    secs = {s["key"]: s for s in sections()}
    cfg = {"url": render.AUTH_DB.get("url") or "", "key": render.AUTH_DB.get("key") or "", "shop": SHOP,
           "cards": cards, "secs": secs, "max": 16, "first": 5}
    cfgs = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    counts = {k: sum(1 for c in cards if c["sec"] == k) for k in secs}
    def genre(s):
        icon = f'<img src="{e(s["icon"])}" alt="">' if s["icon"] else ""
        return (f'<button type="button" class="genre" data-k="{e(s["key"])}" aria-pressed="false" style="--sc:{e(s["color"])}">'
                f'{icon}{e(s["ja"])}<small>{e(s["en"])} · {counts[s["key"]] or "名前で追加"}</small></button>')
    genres = "".join(genre(s) for s in secs.values())
    dots = '<div class="dots" aria-hidden="true">' + "<i></i>" * 4 + "</div>"
    bar = f'<div class="bar"><button type="button" data-back aria-label="戻る">←</button>{dots}<span style="width:38px"></span></div>'
    page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ウォッチリスト通信 · はじめる</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{render.FONTS}">
<style>{render.CSS}{CSS}</style>
</head>
<body>
<section class="scr on" id="s-home"><div class="wrap">
<p class="back-on"><span>このブラウザは <b></b> さんを覚えています（ふだんは自動で自分のページへ）</span><a href="{SHOP}">開く →</a></p>
<div class="hero">
<div>
<h1 class="logo">ウォッチリスト通信</h1>
<p class="catch">好きな作品・グッズのニュースを、<br><em>店長が毎日集めて</em> 1 ページに。</p>
<p class="lede">アニメ・ゲーム・ライブ・グッズ…気になるものを選ぶだけ。店長が毎日あちこちを回ってニュースを集め、
作品ごとの版面に整理しておきます。見逃しも、同じ話の重複もなし。</p>
<div class="cta">
<button type="button" class="btn main" data-go="name">新しく始める</button>
<a class="btn" href="{SHOP}?login=1">ログイン</a>
<a class="btn sub" href="{SHOP}">まず店長のページを見る →</a>
</div>
</div>
<div class="shot"><img class="pc" src="welcome/shop-pc.webp" alt="店長のページ（パソコン）"><img class="sp" src="welcome/shop-sp.webp" alt="店長のページ（スマホ）"></div>
</div>
<ul class="how">
<li><span class="n">01</span><b>気になるものを選ぶ</b><p>ジャンルを選んで、出てくるカードを「気になる / パス」。パスワードは要りません。</p></li>
<li><span class="n">02</span><b>店長が集めに行く</b><p>ニュース・発売日・イベントを毎日集めて、AI が同じ話をまとめ、見出しを付けます。</p></li>
<li><span class="n">03</span><b>自分だけの版面を読む</b><p>作品ごとの版面で、新しいことだけ。👍 / 👎 で、店長のおすすめがだんだん合ってきます。</p></li>
</ul>
<p class="pop">「とりあえず店長のページをのぞいてみてね」— 店長</p>
<div class="foot"><a href="../test2/terms.html">利用規約・プライバシーポリシー</a><span>試作（テストグラウンド）</span></div>
</div></section>

<section class="scr" id="s-name"><div class="wrap">
{bar}
<h2 class="q">名前を決めましょう</h2>
<p class="qs">ほかの人と同じ名前は使えません。メールアドレスでも OK。パスワードはありません。</p>
<label class="field">ユーザー名<input id="nm" type="text" maxlength="40" autocomplete="username" autocapitalize="off" spellcheck="false" placeholder="好きな名前" autofocus></label>
<p class="hint" id="nm-hint" aria-live="polite"></p>
<label class="agree"><input type="checkbox" id="agree"><span><a href="../test2/terms.html" target="_blank" rel="noopener">利用規約・プライバシーポリシー</a>を読んで同意します。
選んだ作品などの「興味・関心の情報」は、このサービスのためだけに使います。</span></label>
<div class="grow"></div>
<button type="button" class="btn main" id="to-genre" disabled>次へ</button>
</div></section>

<section class="scr" id="s-genre"><div class="wrap">
{bar}
<h2 class="q">好きなジャンルは？</h2>
<p class="qs">いくつでも。次のカードはこの中から出します。</p>
<div class="genres">{genres}</div>
<div class="grow"></div>
<button type="button" class="btn main" id="to-cards" data-go="cards" disabled>ひとつ以上えらぶ</button>
</div></section>

<section class="scr" id="s-cards"><div class="wrap">
{bar}
<h2 class="q">気になる？</h2>
<p class="qs">右へ = 気になる、左へ = パス（ボタン・← → キーでも）。</p>
<div class="deck" aria-live="polite"></div>
<p class="count"></p>
<div class="acts"><button type="button" class="act n" aria-label="パス">✕</button><button type="button" class="act y" aria-label="気になる">♥</button></div>
<button type="button" class="btn main" id="to-check" data-go="check" hidden>この中から始める</button>
</div></section>

<section class="scr" id="s-check"><div class="wrap">
{bar}
<h2 class="q">最初の版面</h2>
<p class="qs">店長がこれから集めに行くものです。あとでいつでも足したり外したりできます。</p>
<p class="qs" id="first-note"></p>
<ul class="picked"></ul>
<div class="grow"></div>
<button type="button" class="btn main" id="to-done">始める</button>
</div></section>

<section class="scr" id="s-done"><div class="wrap"><div class="done">
<p class="pop">店長が集めに行ってきます！</p>
<p><b id="done-name"></b> さんの最初の版面：<br><span id="done-list"></span></p>
<p>最初のニュースは約 2 時間後。<br>それまで店長のページをのぞいていてください。</p>
<a class="btn main" href="{SHOP}">店長のページを見ながら待つ →</a>
<p class="proto">試作なので、まだ登録・保存はしていません</p>
</div></div></section>

<script type="application/json" id="wl-cfg">{cfgs}</script>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(OUT, len(cards), "cards", counts)


if __name__ == "__main__":
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("settings") or {}
    render.AUTH_DB.update({"url": s.get("supabase_url") or "", "key": s.get("supabase_key") or ""})
    build()
