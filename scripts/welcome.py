"""入口と新しく始める（2026-10-21，試作・テストグラウンド）。

App のように 1 ページで画面を切り替える：
  ① 入口（何のサイトか・店長のページの本物の画面・「新しく始める」「ログイン」「店長のページを見る」）
  ② メールアドレスと規約 → ③ 好きなジャンル（8 つの板块）→ ④ カードを左右に（気になる / パス）→ ⑤ 最初の版面の確認 → ⑥ 店長が集めに行く
このブラウザが覚えている人（localStorage の wl-user）は入口を飛ばして自分のページへ（いまは店長のページ。?stay で止まる）。
登録は本物（public.user_signup：メールアドレス・規約の同意・好み = 言語・ジャンル・最初の版面）。本人の版面はまだ作らない（第 2 步、LOGIN.md）。

カードの候補は規則で作る（AI なし）：AniList の話題のアニメ・マンガ、Steam の売れ筋、店長がフォローしているもの（いまのアカウント＝店長の関注項とアイコン、sitedir）。
  python scripts/welcome.py            → docs/index.html（本番の入口）と docs/testground/welcome.html（候補はその時点のものを埋め込む）
  digest.py render のたびに build_if_stale()：入口が 24 時間より古いときだけ作り直す（話題の候補を新しく）。
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
import sitedir  # noqa: E402
import taxonomy  # noqa: E402

OUT = ROOT / "docs" / "index.html"                       # 本番の入口（https://cxelegy.github.io/Wishlist/）
OUT_TG = ROOT / "docs" / "testground" / "welcome.html"     # テストグラウンドの写し（同じもの・パスだけ違う）
# ニュースの言語（2026-10-21，用户定的：世界中の人が使う前提）。地域ごとに漏れなく・重ならず（MECE：1 つの言語は生まれた地域 1 か所だけ）。
# ふだんはよく使われる言語だけ出し、残りは「ほかの言語」にたたむ（検索できる）。記号は BCP 47（中国語は簡体・繁体を分ける）。
LANG_TOP = ["ja", "en", "zh-Hans", "zh-Hant", "ko", "es"]
LANG_GROUPS = [
    ("東アジア", [("ja", "日本語"), ("zh-Hans", "中文（简体）"), ("zh-Hant", "中文（繁體）"), ("ko", "한국어"), ("mn", "Монгол")]),
    ("東南アジア", [("th", "ไทย"), ("vi", "Tiếng Việt"), ("id", "Bahasa Indonesia"), ("ms", "Bahasa Melayu"), ("fil", "Filipino"),
                 ("my", "မြန်မာ"), ("km", "ខ្មែរ"), ("lo", "ລາວ")]),
    ("南アジア", [("hi", "हिन्दी"), ("bn", "বাংলা"), ("ur", "اردو"), ("ta", "தமிழ்"), ("te", "తెలుగు"), ("mr", "मराठी"),
               ("gu", "ગુજરાતી"), ("ne", "नेपाली"), ("si", "සිංහල")]),
    ("中東・中央アジア", [("ar", "العربية"), ("fa", "فارسی"), ("he", "עברית"), ("tr", "Türkçe"), ("kk", "Қазақ"), ("uz", "Oʻzbek"), ("az", "Azərbaycan")]),
    ("ヨーロッパ", [("en", "English"), ("es", "Español"), ("fr", "Français"), ("de", "Deutsch"), ("it", "Italiano"), ("pt", "Português"),
                ("nl", "Nederlands"), ("pl", "Polski"), ("ru", "Русский"), ("uk", "Українська"), ("sv", "Svenska"), ("no", "Norsk"),
                ("da", "Dansk"), ("fi", "Suomi"), ("cs", "Čeština"), ("el", "Ελληνικά"), ("ro", "Română"), ("hu", "Magyar")]),
    ("アフリカ", [("sw", "Kiswahili"), ("am", "አማርኛ"), ("ha", "Hausa"), ("yo", "Yorùbá"), ("zu", "isiZulu"), ("af", "Afrikaans")]),
]
LANGS = [x for _, g in LANG_GROUPS for x in g]
# 検索用（英語名・日本語名でも探せるように）
LANG_ALIAS = {"ja": "japanese 日本語 にほんご", "zh-Hans": "chinese simplified 中国語 簡体字", "zh-Hant": "chinese traditional 中国語 繁体字 台湾 香港",
              "ko": "korean 韓国語", "mn": "mongolian モンゴル語", "th": "thai タイ語", "vi": "vietnamese ベトナム語", "id": "indonesian インドネシア語",
              "ms": "malay マレー語", "fil": "filipino tagalog フィリピン語 タガログ語", "my": "burmese myanmar ミャンマー語", "km": "khmer クメール語 カンボジア",
              "lo": "lao ラオ語", "hi": "hindi ヒンディー語", "bn": "bengali bangla ベンガル語", "ur": "urdu ウルドゥー語", "ta": "tamil タミル語",
              "te": "telugu テルグ語", "mr": "marathi マラーティー語", "gu": "gujarati グジャラート語", "ne": "nepali ネパール語", "si": "sinhala シンハラ語",
              "ar": "arabic アラビア語", "fa": "persian farsi ペルシア語", "he": "hebrew ヘブライ語", "tr": "turkish トルコ語", "kk": "kazakh カザフ語",
              "uz": "uzbek ウズベク語", "az": "azerbaijani アゼルバイジャン語", "en": "english 英語", "es": "spanish スペイン語", "fr": "french フランス語",
              "de": "german ドイツ語", "it": "italian イタリア語", "pt": "portuguese ポルトガル語 brazil", "nl": "dutch オランダ語", "pl": "polish ポーランド語",
              "ru": "russian ロシア語", "uk": "ukrainian ウクライナ語", "sv": "swedish スウェーデン語", "no": "norwegian ノルウェー語", "da": "danish デンマーク語",
              "fi": "finnish フィンランド語", "cs": "czech チェコ語", "el": "greek ギリシャ語", "ro": "romanian ルーマニア語", "hu": "hungarian ハンガリー語",
              "sw": "swahili スワヒリ語", "am": "amharic アムハラ語", "ha": "hausa ハウサ語", "yo": "yoruba ヨルバ語", "zu": "zulu ズールー語", "af": "afrikaans アフリカーンス語"}
LANG_NAME = dict(LANGS)
COLLECTED = {"ja", "en", "zh-Hans", "zh-Hant", "ko"}   # いまニュースを集めている言語（lang.py）。ほかは好みとして残し、集める言語を足すときに使う
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


def shop_picks(base="../"):
    """店長がフォローしているもの（店長のアカウント＝sitedir の関注項・アイコンつき）。カードに「店長も見ている」。"""
    data = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    out = []
    for it in data.get("items") or []:
        icon = (it.get("icon") or {}).get("image") if isinstance(it.get("icon"), dict) else None
        if not icon or it.get("parent"):
            continue
        sec = taxonomy.canonical(it.get("section") or taxonomy.BY_TYPE.get(it.get("type", "product"), "好物"))
        out.append({"name": it["name"], "img": base + sitedir.SLUG + "/" + icon, "sub": (it.get("subtitle") or "")[:30],
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
.how{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:18px 0 0;padding:0}
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
.langs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.lang{display:flex;align-items:center;justify-content:center;min-height:56px;border:3px solid var(--ink);background:var(--card);color:var(--ink);
 font:900 18px var(--font-sans);cursor:pointer;box-shadow:var(--shadow)}
.lang[aria-pressed=true]{background:var(--ink);color:var(--card);transform:rotate(-1deg)}
.also{display:flex;flex-wrap:wrap;gap:10px}
.also label{display:flex;align-items:center;gap:6px;padding:8px 12px;border:2px solid var(--ink);background:var(--card);font-weight:700;cursor:pointer}
.also label[hidden]{display:none}
.sub-q{margin:8px 0 0;font:900 16px var(--font-sans)}
.more{border:2px solid var(--ink);background:var(--card)}
.more>summary{cursor:pointer;padding:10px 14px;font-weight:900;list-style:none}
.more>summary::-webkit-details-marker{display:none}
.more>summary::after{content:" ＋"}.more[open]>summary::after{content:" －"}
.more .in{padding:0 14px 14px;display:flex;flex-direction:column;gap:10px;max-height:46vh;overflow:auto}
.more input[type=search]{padding:8px 10px;border:2px solid var(--ink);font:700 15px var(--font-sans);background:var(--paper);color:var(--ink);min-width:0}
.more h3{margin:6px 0 0;font:700 var(--fs-label) var(--font-sans);letter-spacing:.1em;opacity:.75}
.more .row{display:flex;flex-wrap:wrap;gap:6px}
.more .row button,.more .row label{border:2px solid var(--ink);background:var(--paper);color:var(--ink);padding:5px 10px;font:700 14px var(--font-sans);cursor:pointer;display:flex;gap:6px;align-items:center}
.more .row button[aria-pressed=true]{background:var(--ink);color:var(--card)}
.more [hidden]{display:none}
.soon{font-size:11px;opacity:.7;font-weight:500}
.err{margin:0;color:var(--alert);font-weight:700;min-height:1.4em}
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
.chips{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;padding:0;margin:0}
.chips li{list-style:none;max-width:16em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;background:var(--card);border:2px solid var(--ink);padding:3px 10px;font-weight:700;font-size:13px}
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
    headers: { apikey: C.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
    .then(r => r.text().then(t => { let j = null; try { j = t ? JSON.parse(t) : null; } catch (_) {} return r.ok ? j : Promise.reject(new Error((j && j.message) || r.status)); }));
  // このブラウザが覚えている人：入口を飛ばして自分のページへ（いまは店長のページ）。?stay なら止まる
  let me = null; try { me = JSON.parse(localStorage.getItem('wl-user') || 'null'); } catch (_) {}
  const stay = /[?&]stay\b/.test(location.search);
  if (me && me.name) {
    if (!stay) { location.replace(C.shop); return; }
    const b = $('.back-on'); b.classList.add('on'); $('b', b).textContent = me.name;
  }
  // ---- 画面の切り替え（戻るボタンでも戻れる）
  const ORDER = ['home', 'name', 'lang', 'genre', 'cards', 'check', 'done'];
  const NAMES = Object.fromEntries(C.langs);
  const guess = (() => { const l = (navigator.language || 'ja'); if (/^zh-(TW|HK|MO|Hant)/i.test(l)) return 'zh-Hant'; if (/^zh/i.test(l)) return 'zh-Hans';
    const b = l.split('-')[0]; return NAMES[l] ? l : NAMES[b] ? b : 'ja'; })();
  const st = { name: '', genres: new Set(), liked: [], seen: 0, lang: guess, also: new Set() };
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
  if (location.hash === '#name') show('name', false);   // 各ページ右上の「新しく始める」から
  $$('[data-go]').forEach(b => b.addEventListener('click', () => show(b.dataset.go)));
  $$('.bar [data-back]').forEach(b => b.addEventListener('click', () => history.back()));
  // ---- ② メールアドレスと規約（2026-10-21，用户定的：ログインはメールアドレス）
  const inp = $('#nm'), hint = $('#nm-hint'), agree = $('#agree'), next1 = $('#to-genre'); let tm = 0, okName = false;
  const v1 = () => { next1.disabled = !(okName && agree.checked); };
  inp.addEventListener('input', () => {
    clearTimeout(tm); okName = false; v1(); const n = inp.value.trim(); hint.className = 'hint';
    if (!/^[^@\s<>"'`/\\]+@[^@\s<>"'`/\\]+\.[^@\s<>"'`/\\]+$/.test(n)) { hint.textContent = n ? 'メールアドレスの形にしてください（例：name@example.com）' : ''; if (n) hint.className = 'hint ng'; return; }
    hint.textContent = '確かめています…';
    tm = setTimeout(() => rpc('name_available', { p_name: n }).then(ok => {
      if (inp.value.trim() !== n) return;
      okName = !!ok; hint.innerHTML = ok ? '✓ このメールアドレスで始められます' : 'このメールアドレスはもう登録されています。<a href="' + C.shop + '?login=1">ログインはこちら →</a>'; hint.className = 'hint ' + (ok ? 'ok' : 'ng'); v1();
    }).catch(() => { okName = true; hint.textContent = C.url ? '（確かめられませんでした。最後の登録のときにもう一度確かめます）' : '（プレビューなので確かめません）'; v1(); }), 350);
  });
  agree.addEventListener('change', v1);
  next1.addEventListener('click', () => { st.name = inp.value.trim().toLowerCase(); show('lang'); });
  // ---- 言語（ニュースの言語。いちばん読みやすい 1 つ＋ほかに見てもよい言語）
  // ブラウザの言語がよく使う言語に入っていなければ、先頭の列に足しておく
  if (!C.top.includes(guess)) { const t = $('#lang-top'); const b = document.createElement('button'); b.type = 'button'; b.className = 'lang'; b.dataset.l = guess; b.textContent = NAMES[guess]; t.prepend(b); }
  function paintLang() {
    $$('[data-l]').forEach(b => { const v = b.dataset.l;
      if (b.classList.contains('lang') || b.closest('#lang-more')) b.setAttribute('aria-pressed', String(v === st.lang));
      const cb = b.querySelector && b.querySelector('input[type=checkbox]'); if (cb) { cb.checked = st.also.has(v); b.hidden = v === st.lang; } });
    $('#lang-now').textContent = NAMES[st.lang] + (C.collected.includes(st.lang) ? '' : '（この言語のニュース集めは準備中）');
  }
  document.addEventListener('click', ev => { const b = ev.target.closest('#s-lang button[data-l]'); if (!b) return;
    st.lang = b.dataset.l; st.also.delete(st.lang); paintLang(); });
  document.addEventListener('change', ev => { const i = ev.target.closest('#s-lang label[data-l] input'); if (!i) return;
    const v = i.closest('label').dataset.l; i.checked ? st.also.add(v) : st.also.delete(v); });
  $$('#s-lang input[type=search]').forEach(q => q.addEventListener('input', () => {
    const w = q.value.trim().toLowerCase(), box = q.closest('.in');
    $$('[data-l]', box).forEach(x => { x.hidden = !!w && !(x.textContent.toLowerCase().includes(w) || (x.dataset.s || '').toLowerCase().includes(w) || x.dataset.l.toLowerCase().startsWith(w)); });
    $$('h3', box).forEach(h => { h.hidden = !!w && !$$('[data-l]:not([hidden])', h.nextElementSibling).length; });
    if (!w) paintLang();
  }));
  if (st.lang !== 'en') st.also.add('en');
  paintLang();
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
  // ---- 登録（本物）：メールアドレス・規約の同意・好みを一度に。もう登録されていたらメールの画面へ戻す
  $('#to-done').addEventListener('click', () => {
    const keep = $$('.picked li:not(.off)').map(li => st.liked[[...li.parentNode.children].indexOf(li)]);
    const prefs = { lang: { primary: st.lang, also: [...st.also].filter(l => l !== st.lang) }, genres: [...st.genres],
                    picks: keep.map(c => ({ name: c.name, sec: c.sec })), from: 'welcome' };
    const b = $('#to-done'), err = $('#signup-err'); b.disabled = true; err.textContent = '';
    const done = () => {
      try { localStorage.setItem('wl-user', JSON.stringify({ name: st.name, v: C.terms, at: Date.now() })); } catch (_) {}
      $('#done-name').textContent = st.name.split('@')[0]; $('#done-list').innerHTML = keep.map(c => '<li title="' + esc(c.name) + '">' + esc(c.name) + '</li>').join('');
      $('#done-lang').textContent = NAMES[st.lang]; show('done');
    };
    if (!C.url) { done(); return; }   // プレビュー（DB なし）
    rpc('user_signup', { p_name: st.name, p_agree_version: C.terms, p_prefs: prefs }).then(done).catch(e => {
      b.disabled = false;
      fetch(C.url.replace(/\/$/, '') + '/rest/v1/rpc/name_available', { method: 'POST', headers: { apikey: C.key, 'Content-Type': 'application/json' },
        body: JSON.stringify({ p_name: st.name }) }).then(r => r.json()).then(ok => {
        if (ok === false) { show('name'); hint.innerHTML = 'このメールアドレスはもう登録されています。<a href="' + C.shop + '?login=1">ログインはこちら →</a>'; hint.className = 'hint ng'; okName = false; v1(); }
        else err.textContent = '登録できませんでした。少し待ってからもう一度押してください';
      }).catch(() => { err.textContent = '登録できませんでした。通信を確かめてもう一度押してください'; });
    });
  });
})();
"""


def build(out=OUT, base="", cards=None):
    """入口を書く。base = docs/ からの相対の前置き（本番の入口は ""、テストグラウンドは "../"）。"""
    SHOP = base + sitedir.SLUG + "/"   # 店長のページ
    cards = cards if cards is not None else anilist("ANIME", 12) + anilist("MANGA", 6) + steam(12) + shop_picks("")
    cards = [{**c, "img": base + c["img"]} if c.get("shop") else c for c in cards]
    secs = {s["key"]: s for s in sections()}
    cfg = {"url": render.AUTH_DB.get("url") or "", "key": render.AUTH_DB.get("key") or "", "shop": SHOP,
           "cards": cards, "secs": secs, "max": 16, "first": 5, "terms": render.TERMS_VERSION, "langs": LANGS, "top": LANG_TOP, "collected": sorted(COLLECTED)}
    cfgs = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    counts = {k: sum(1 for c in cards if c["sec"] == k) for k in secs}
    def genre(s):
        icon = f'<img src="{e(s["icon"])}" alt="">' if s["icon"] else ""
        return (f'<button type="button" class="genre" data-k="{e(s["key"])}" aria-pressed="false" style="--sc:{e(s["color"])}">'
                f'{icon}{e(s["ja"])}<small>{e(s["en"])} · {counts[s["key"]] or "名前で追加"}</small></button>')
    genres = "".join(genre(s) for s in secs.values())
    dots = '<div class="dots" aria-hidden="true">' + "<i></i>" * 5 + "</div>"
    soon = lambda k: "" if k in COLLECTED else '<span class="soon">準備中</span>'
    langs = "".join(f'<button type="button" class="lang" data-l="{k}" aria-pressed="false">{e(LANG_NAME[k])}</button>' for k in LANG_TOP)
    def more(kind):
        rows = "".join(f'<h3>{e(g)}</h3><div class="row">' + "".join(
            (f'<button type="button" data-l="{k}" data-s="{e(LANG_ALIAS.get(k, ""))}" aria-pressed="false">{e(v)}{soon(k)}</button>' if kind == "main"
             else f'<label data-l="{k}" data-s="{e(LANG_ALIAS.get(k, ""))}"><input type="checkbox">{e(v)}{soon(k)}</label>') for k, v in items) + "</div>" for g, items in LANG_GROUPS)
        return (f'<details class="more" id="{"lang-more" if kind == "main" else "also-more"}"><summary>ほかの言語（{len(LANGS)}）</summary>'
                f'<div class="in"><input type="search" placeholder="言語の名前で探す（例：Français / fr）" aria-label="言語を探す">{rows}</div></details>')
    also = "".join(f'<label data-l="{k}"><input type="checkbox"> {e(LANG_NAME[k])}</label>' for k in LANG_TOP)
    bar = f'<div class="bar"><button type="button" data-back aria-label="戻る">←</button>{dots}<span style="width:38px"></span></div>'
    page = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ウォッチリスト通信</title>
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
<div class="shot"><img class="pc" src="{base}testground/welcome/shop-pc.webp" alt="店長のページ（パソコン）"><img class="sp" src="{base}testground/welcome/shop-sp.webp" alt="店長のページ（スマホ）"></div>
</div>
<ul class="how">
<li><span class="n">01</span><b>気になるものを選ぶ</b><p>ジャンルを選んで、出てくるカードを「気になる / パス」。パスワードは要りません。</p></li>
<li><span class="n">02</span><b>店長が集めに行く</b><p>ニュース・発売日・イベントを毎日集めて、AI が同じ話をまとめ、見出しを付けます。</p></li>
<li><span class="n">03</span><b>自分だけの版面を読む</b><p>作品ごとの版面で、新しいことだけ。👍 / 👎 で、店長のおすすめがだんだん合ってきます。</p></li>
</ul>
<p class="pop">「とりあえず店長のページをのぞいてみてね」— 店長</p>
<div class="foot"><a href="{SHOP}">店長のページ</a><a href="{SHOP}terms.html">利用規約・プライバシーポリシー</a><a href="{base}test2/">試験の版（2026-10-19〜21）</a><a href="{base}testground/">テストグラウンド</a></div>
</div></section>

<section class="scr" id="s-name"><div class="wrap">
{bar}
<h2 class="q">メールで始めます</h2>
<p class="qs">次からはこのメールアドレスでログインします。パスワードはありません。メールは送りません。</p>
<label class="field">メールアドレス<input id="nm" type="email" maxlength="120" autocomplete="email" autocapitalize="off" spellcheck="false" placeholder="name@example.com" autofocus></label>
<p class="hint" id="nm-hint" aria-live="polite"></p>
<label class="agree"><input type="checkbox" id="agree"><span><a href="{SHOP}terms.html" target="_blank" rel="noopener">利用規約・プライバシーポリシー</a>を読んで同意します。
選んだ作品などの「興味・関心の情報」は、このサービスのためだけに使います。</span></label>
<div class="grow"></div>
<button type="button" class="btn main" id="to-genre" disabled>次へ</button>
</div></section>

<section class="scr" id="s-lang"><div class="wrap">
{bar}
<h2 class="q">ニュースは何語で読みますか？</h2>
<p class="qs">同じ話が何か国語かで出ているときは、ここで選んだ言語の記事を出します。</p>
<div class="langs" id="lang-top" role="group" aria-label="いちばん読みやすい言語">{langs}</div>
{more("main")}
<p class="qs">選んでいる言語：<b id="lang-now"></b><br><small>「準備中」の言語は、集め始めるまでほかの言語の記事で代わりに出します。</small></p>
<p class="sub-q">ほかの言語の記事も見る</p>
<p class="qs">選んだ言語の記事がないときだけ、ここの言語の記事を出します。</p>
<div class="also">{also}</div>
{more("also")}
<p class="qs"><small>画面の文字（ボタンや説明）はいまは日本語だけです。あとで設定から変えられます。</small></p>
<div class="grow"></div>
<button type="button" class="btn main" data-go="genre">次へ</button>
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
<p class="err" id="signup-err" aria-live="polite"></p>
<button type="button" class="btn main" id="to-done">始める</button>
</div></section>

<section class="scr" id="s-done"><div class="wrap"><div class="done">
<p class="pop">ようこそ！メモしました</p>
<p><b id="done-name"></b> さんの好み</p>
<ul class="chips" id="done-list"></ul>
<p><small>ニュースの言語：<span id="done-lang"></span></small></p>
<p>あなた専用の版面は、店長がいま仕入れの準備中です。<br>できあがるまで、店長のページで同じしくみを見てください。</p>
<a class="btn main" href="{SHOP}">店長のページへ →</a>
</div></div></section>

<script type="application/json" id="wl-cfg">{cfgs}</script>
<script>{JS}</script>
</body>
</html>
"""
    pathlib.Path(out).write_text(page, encoding="utf-8")
    print(out, len(cards), "cards", counts)
    return cards


def build_all():
    cards = build(OUT, "")
    build(OUT_TG, "../", [{**c, "img": c["img"]} for c in cards if not c.get("shop")] + shop_picks(""))


def build_if_stale(hours=24):
    """digest.py render から呼ぶ：入口が古いとき（または無いとき）だけ作り直す。ネットにつながらなくても落ちない。"""
    import time
    if OUT.exists() and "wl-cfg" in OUT.read_text(encoding="utf-8")[:200000] and time.time() - OUT.stat().st_mtime < hours * 3600:
        return
    try:
        build_all()
    except Exception as ex:  # 入口が作れなくても簡報の生成は止めない
        print("welcome", ex, file=sys.stderr)




def preview(out):
    """そのまま開ける試作の写し（Artifact で見せる用）：画像をすべて data: に埋め込み、店長のページへのリンクは公開の URL に。
    DB には届かないので、名前の確認は「確かめられませんでした」のまま進む。"""
    import base64
    import io
    import re
    from PIL import Image

    def data_uri(src, size=360):
        try:
            if src.startswith("http"):
                req = urllib.request.Request(src, headers={"User-Agent": UA["User-Agent"]})
                raw = urllib.request.urlopen(req, timeout=20).read()
            else:
                raw = (OUT.parent / src).read_bytes()   # docs/ からのパス
            if src.endswith(".svg"):
                return "data:image/svg+xml;base64," + base64.b64encode(raw).decode()
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((size, size * 2))
            buf = io.BytesIO(); im.save(buf, "WEBP", quality=72)
            return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as ex:
            print("skip", src[:80], ex, file=sys.stderr)
            return ""

    page = OUT.read_text(encoding="utf-8")   # 本番の入口（パスは docs/ から）
    cfg = json.loads(re.search(r'<script type="application/json" id="wl-cfg">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    cards = []
    for c in cfg["cards"]:
        u = data_uri(c["img"])
        if u:
            cards.append({**c, "img": u})
    for s in cfg["secs"].values():
        s["icon"] = data_uri(s["icon"]) if s.get("icon") else ""
    live = sitedir.URL
    cfg.update({"cards": cards, "shop": live, "url": "", "key": ""})
    page = re.sub(r'(<script type="application/json" id="wl-cfg">).*?(</script>)',
                  lambda m: m.group(1) + json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/") + m.group(2), page, flags=re.S)
    for k, s in cfg["secs"].items():   # ジャンルの札のアイコン
        page = re.sub(r'(data-k="%s"[^>]*>)<img src="[^"]*"' % re.escape(k), lambda m, s=s: m.group(1) + f'<img src="{s["icon"]}"', page)
    for name in ("shop-pc.webp", "shop-sp.webp"):
        page = page.replace(f'src="testground/welcome/{name}"', f'src="{data_uri("testground/welcome/" + name, 1200)}"')
    page = page.replace(f'href="{sitedir.SLUG}/', f'target="_blank" rel="noopener" href="{live}')
    page = re.sub(r'href="(home/|test2/|testground/)', r'target="_blank" rel="noopener" href="https://cxelegy.github.io/Wishlist/\1', page)
    # Artifact は <html><head><body> を自分で付けるので中身だけ
    head = re.search(r"<head>(.*?)</head>", page, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", page, re.S).group(1)
    head = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>', "", head)
    pathlib.Path(out).write_text(head + body, encoding="utf-8")
    print(out, len(cards), "cards", round(pathlib.Path(out).stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--preview":   # python scripts/welcome.py --preview <出力先>
        preview(sys.argv[2])
    else:
        s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8")).get("settings") or {}
        render.AUTH_DB.update({"url": s.get("supabase_url") or "", "key": s.get("supabase_key") or ""})
        build_all()
