"""testground/wishes.html と product-head.html：文字で聞かず、見て選ぶ審査（2026-11-02，用户定的：「多可视化，点开链接可以直观看到改了什么、该改什么」）。
欲しい物 A/B/C と、製品の版面の先頭 A/B を、本物の記事で「今 → 案」に描く。DB の形は変えない（案を見せるだけ）。答えは review_save（店長ログイン）。
データは 2026-11-02 の本番 user_boards の先頭 8 本（記事の題・出典・写真の網址）を SNAP に写したもの。写真は元の記事の網址（storage ではない）。
    python scripts/choice_sample.py"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/testground"
SUPA = ("https://bzokpnbcjscbcehdxtjq.supabase.co", "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC")
# 版面 -> (作っている会社の言い方, 先頭 8 本 [(題, 出典, 写真)])。順番は本番の board の並びのまま。
SNAP = {
    "iPhone": (["Apple", "アップル"], [
        ("Samsung、iPhone Duoの画面割れを広告で揶揄〜同社も故障で発売延期の過去", "iPhone Mania", "https://iphone-mania.jp/wp-content/uploads/2026/10/31/Samsung-Galaxy-Fold-Ad-2.heic.jpeg"),
        ("【Amazonセール】Spigen MagSafe対応iPhoneケース 対応機種3種がプライム会員限定で15%オフ", "AppBank", "https://www.appbank.net/wp-content/uploads/2026/10/amazon-deal-appbank-b0fd1x2y3d-20261030-hero.jpg"),
        ("ドコモ販売ランキング：新発売の「iPhone 18 Pro」が2位と4位に、「iPhone 17」が首位守る【2026年9月】", "Yahoo!ニュース", "https://newsatcl-pctr.c.yimg.jp/t/amd-img/20261030-00000023-zdn_m-000-1-view.jpg?exp=10800"),
        ("【Amazonセール】NIMASO アンチグレア ガラスフィルム iPhone 17/iPhone 16 Pro用が2,279円、プライム会員限定", "AppBank", "https://www.appbank.net/wp-content/uploads/2026/10/amazon-deal-appbank-b0fdg3fjlj-20261028-hero.jpg"),
        ("iPhone 20は、発売前からすでにAndroidメーカーの間で不安を引き起こしている。", "Vietnam.vn", ""),
        ("【Amazonセール】NIMASO ガラスフィルム iPhone用 対応機種3種が1,599円(20%オフ、プライム会員限定)", "AppBank", "https://www.appbank.net/wp-content/uploads/2026/10/amazon-deal-appbank-b09c31nvfy-20261027-hero.jpg"),
        ("iPhone 18 Pro、発売後3週間の世界販売はわずか3.1%増 中国が29%急増で独り支える", "BigGo ファイナンス", ""),
        ("Apple が iPhone Duo の発売初日に時価総額で一時世界首位に", "Hypebeast", "https://image-cdn.hypb.st/https%3A%2F%2Fjp.hypebeast.com%2Ffiles%2F2026%2F10%2FTWapple-reclaims-top-market-spot-as-iphone-duo-sells-out.jpg?w=1080&cbr=1&q=90&fit=max"),
    ]),
    "Nintendo Switch 2": (["任天堂"], [
        ("「プチプラネット」Nintendo Switch 2版が2027年にリリース決定！Switch 2本体などが当たるキャンペーンも開催", "Saiga NAK", ""),
        ("「Pikmin Day Direct」が公開！「ピクミン4 Nintendo Switch 2 Edition」の体験版が配信開始", "ｄメニューニュース", ""),
        ("Star Fox Nintendo Switch 2 remake just hit the $43 Amazon all-time low", "9to5Toys", ""),
        ("Games inbox: Is a Nintendo Switch 2 worth getting for Christmas?", "Metro on MSN", ""),
        ("HoYoverse新作『プチプラネット』Nintendo Switch 2版が2027年に登場！", "AppBank", ""),
        ("Petit Planet confirmed for Nintendo Switch 2, from Genshin Impact dev", "Nintendo Everything", ""),
        ("集英社ゲームズ、『都市伝説解体センター』のNintendo Switch 2版を発売", "gamebiz", ""),
        ("HoYoverse officially announces Petit Planet Nintendo Switch 2 port, launching 2027", "GosuGamers", ""),
    ]),
    "ガンプラ": (["バンダイ", "BANDAI"], [
        ("ガンプラ「HG 1/144 ガンダムヴァサーゴ」の抽選販売がプレミアムバンダイにて実施決定！", "hobby Watch", ""),
        ("最新ガンプラ情報が満載！【連載】ガンプラジャーナル11月号", "電撃ホビーウェブ", ""),
        ("【関西最大級】モデラーズフェスティバル2026！", "Howl.Link", ""),
        ("新作ガンプラ「HG 1/144 ガンダムアシュタロン」が11月28日発売！", "インサイド", ""),
    ]),
    "ユニクロ": (["ユニクロ", "UNIQLO", "ファーストリテイリング"], [
        ("京都最大の［ユニクロ 京都］が11月6日（金）オープン！", "Leaf KYOTO", ""),
        ("ユニクロの「三角スカーフ」で大判ストール卒業", "LEE", ""),
        ("ユニクロ、サンエックスユニバースのラウンジウェアコレクションを12月中旬発売", "Yahoo!ニュース", ""),
    ]),
}
BOARDS_WITH_STORIES = 41   # 2026-11-02 の本番で記事のある版面（user_boards、重複なし）
DEAL = re.compile(r"セール|オフ|ケース|フィルム|クーポン|特価|\bsale\b|\bdeal\b|all-time low|lowest price", re.I)
e = html.escape


def is_deal(t):
    return bool(DEAL.search(t))


def rule_a(name, rows):
    """A：作っている会社の名前が題にある記事を先に（元の順は保つ）。会社の名前を持たない版面は変わらない。"""
    makers = SNAP[name][0]
    hit = [r for r in rows if any(m in r[0] for m in makers)]
    return hit + [r for r in rows if r not in hit]


def rule_b(rows):
    """B：安売り・周辺機器の記事を、安売りでない記事の後ろへ（消さない）。"""
    return [r for r in rows if not is_deal(r[0])] + [r for r in rows if is_deal(r[0])]


def story(r, rank, mark=""):
    t, s, im = r
    img = f'<img loading="lazy" src="{e(im)}" alt="" onerror="this.remove()">' if im else ""
    d = ' <b class="dl">安売り</b>' if is_deal(t) else ""
    return f'<li class="{mark}"><span class="rk">{rank}</span>{img}<span class="tt">{e(t)}{d}<small>{e(s)}</small></span></li>'


def col(title, cls, rows, base, n=5):
    li = []
    for i, r in enumerate(rows[:n]):
        j = base.index(r)
        mark = "up" if j > i else "dn" if j < i else ""
        li.append(story(r, i + 1, mark))
    return f'<div class="col"><h3><b class="tg {cls}">{title}</b></h3><ol>{"".join(li)}</ol></div>'


def product_page():
    secs = []
    for name in ("iPhone", "Nintendo Switch 2"):
        base = SNAP[name][1]
        a, b = rule_a(name, base), rule_b(base)
        secs.append(f'<section class="pl"><h2>{e(name)} の版面</h2><div class="cols">{col("今", "b", base, base)}{col("案 A 会社を版面に持たせる", "a", a, base)}{col("案 B 安売りを後ろへ", "c", b, base)}</div></section>')
    rows = []
    ch_a = ch_b = 0
    for name, (mk, st) in SNAP.items():
        a, b = rule_a(name, st), rule_b(st)
        ca, cb = a[0] != st[0], b[0] != st[0]
        ch_a += ca
        ch_b += cb
        rows.append(f"<tr><td>{e(name)}</td><td>{e(' / '.join(mk))}</td><td>{'変わる' if ca else '同じ'}</td><td>{'変わる' if cb else '同じ'}</td></tr>")
    tbl = ('<section class="pl"><h2>ほかの版面ではどうか</h2><p class="bad">会社の名前を決めた4版面で、先頭が変わる数。ほかの記事のある版面（'
           f'{BOARDS_WITH_STORIES} のうち上の 4 を除く）は、案 A は会社の名前が未設定なので変わらず、案 B は先頭が安売りの版面だけ変わる＝本番の先頭を調べると大谷翔平の「1100億円」を除き 0 です（安売りの先頭は iPhone だけ）。</p>'
           f'<table><tr><th>版面</th><th>作っている会社</th><th>案 A</th><th>案 B</th></tr>{"".join(rows)}<tr><th>計</th><th></th><th>{ch_a} / {len(SNAP)}</th><th>{ch_b} / {len(SNAP)}</th></tr></table></section>')
    note = ('<section class="pl"><h2>この見本で分かること</h2><ul class="fix"><li>案 B だけだと、iPhone の先頭は安売りでなくなるが <b>Samsung が iPhone Duo を揶揄した記事</b>になる＝Apple の話ではない。</li>'
            '<li>案 A は「Apple が iPhone Duo の発売初日に…」が先頭になる。ただし Switch 2 は「任天堂」を題に持つ記事が無く、案 A では変わらない（出典が公式かどうかの判定が要る）。</li>'
            '<li>案 A は版面に「作っている会社」を持たせる設定が新しく要る（ライブラリの boards.config に 1 項目足すだけ。DB の形は変えない）。案 B は設定なしで全版面に効く。</li>'
            '<li>両方を合わせる（A→B の順）案 C は、この見本では A の列と同じ先頭になる。</li></ul></section>')
    ans = answer("product-head", [("A", "A 会社を版面に持たせる"), ("B", "B 安売りだけ後ろへ"), ("AB", "A と B の両方"), ("later", "あとで")])
    why = ('<p><b>なぜ聞くか</b>製品の版面の先頭を何で選ぶかは、あなたの好みで決まるからです。</p>'
           '<p><b>今どうなっているか</b>test-a の iPhone の版面は、先頭に Amazon セールの記事（Spigen のケース）が出ていました。本番の並びでは2番目、画面の先頭は重大の札で上がったものです。下の「今」の列がデータの並びそのままです。</p>'
           '<p><b>選ぶと何が変わるか</b>下の 3 列は同じ記事の並べ替えだけです。緑の矢印の行が上がった記事、赤が下がった記事。</p>')
    return page("製品の版面の先頭", "審査待ち（製品の版面）", why, "".join(secs) + tbl + note + ans, "product-head")


def answer(pid, opts):
    b = "".join(f'<button data-v="{k}" aria-pressed="false">{e(t)}</button>' for k, t in opts)
    return (f'<section class="pl" id="ans"><h2>どれにしますか</h2><div class="ans" role="group" aria-label="答え">{b}'
            '<input type="text" maxlength="200" placeholder="メモ（任意）" aria-label="メモ"></div></section>')


WISH = [("黑貓魔法術溫變馬克杯", "850 NT$", "想要"), ("貓眼溫變馬克杯", "600 NT$", "想要"), ("SALONIA コードレス ストレートアイロン", "4,378 ¥", "纠结")]


def wishes_page():
    items = "".join(f'<li><span class="ph">写真</span><span class="tt">{e(n)}<small>{e(p)}・{e(s)}</small></span></li>' for n, p, s in WISH)
    likes = "".join(story(r, "👍") for r in SNAP["iPhone"][1][2:4])
    now = ('<div class="phone"><div class="nav"><span>目次</span><span class="x">欲しい物</span></div><p class="ph0">欲しい物を押すと、何も出ません。見出しの「欲しい物リスト」ボタンも同じ。</p>'
           '<p class="ph0">店長のページでは同じ場所に写真つきの一覧が出ます。</p></div>')
    A = (f'<div class="phone"><div class="nav"><span>目次</span><span class="x">欲しい物 3</span></div><ol class="wl">{items}</ol><button class="add">＋ 写真を足す</button>'
         '<p class="why2">本人だけが読み書きできる新しい表（足すだけ）。写真を足すと一覧に出る。店長のページと同じ見た目。</p></div>')
    B = (f'<div class="phone"><div class="nav"><span>目次</span><span class="x">欲しい物 ＝ 👍 の一覧</span></div><ol>{likes}</ol>'
         '<p class="why2">新しい表なし。押した 👍 の記事が並ぶ。写真つきの「欲しい物」は足せない（記事だけ）。</p></div>')
    C = ('<div class="phone"><div class="nav"><span>目次</span></div><p class="ph0">目次の「欲しい物」と見出しの「欲しい物リスト」ボタンを、お客さまには出さない。</p>'
         '<p class="why2">何も作らない。押しても何も出ない状態をやめるだけ。後で A を足せる。</p></div>')
    cols = (f'<div class="cols4"><div class="col"><h3><b class="tg b">今の test-a</b></h3>{now}</div><div class="col"><h3><b class="tg a">A 置き場を作る</b></h3>{A}</div>'
            f'<div class="col"><h3><b class="tg c">B 👍 の一覧で代用</b></h3>{B}</div><div class="col"><h3><b class="tg d">C 隠す</b></h3>{C}</div></div>')
    cost = ('<section class="pl"><h2>作る物の差</h2><table><tr><th></th><th>A</th><th>B</th><th>C</th></tr><tr><th>本番のデータベース</th><td>表を 1 つ足す（本人だけが読み書き）</td><td>変えない</td><td>変えない</td></tr>'
            '<tr><th>写真を足せる</th><td>足せる</td><td>足せない</td><td>—</td></tr><tr><th>店長のページと同じ</th><td>同じ</td><td>違う</td><td>違う（機能が減る）</td></tr></table></section>')
    why = ('<p><b>なぜ聞くか</b>お客さまの「欲しい物」は、店長の分は wishlist.yaml（リポジトリ）と写真の依頼に入っていますが、お客さまの分を置く所がありません。置き場を作るのは本番のデータベースに表を足す話なので、作る前に見て選んでください。</p>'
         '<p><b>今どうなっているか</b>左端のとおり、test-a の目次の「欲しい物」と見出しのボタンは押しても何も出ません（test-a の 👍 は今 1 件）。写真は例の枠です。</p>'
         '<p><b>選ぶと何が変わるか</b>右の 3 列が、その案にしたときの見え方です。</p>')
    ans = answer("wishes", [("A", "A 置き場を作る"), ("B", "B 👍 の一覧で代用"), ("C", "C 隠す")])
    return page("お客さまの欲しい物", "審査待ち（欲しい物）", why, cols + cost + ans, "wishes")


CSS = """:root{--ink:#1A1C22;--paper:#EDEBE6;--card:#FBF8F1;--gold:#FFD23F;--rose:#B8336A;--ok:#1d7a4d;--ng:#D7261E;--mut:rgba(26,28,34,.62)}
@media(prefers-color-scheme:dark){:root{--paper:#1b1b1d;--card:#26262a;--ink:#eee;--mut:rgba(238,238,238,.62)}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.7 system-ui,"Noto Sans JP",sans-serif}
header{background:#1A1C22;color:#FBF8F1;padding:18px 16px}header small{color:var(--gold);font:700 11px monospace;letter-spacing:.15em}h1{margin:2px 0 0;font-size:20px}header a{color:var(--gold);font-size:13px}
main{max-width:1400px;margin:0 auto;padding:16px}
.why{background:var(--card);border:2px solid var(--ink);box-shadow:4px 4px 0 var(--ink);padding:12px 16px;margin-bottom:14px}.why p{margin:4px 0}.why b{display:inline-block;background:var(--rose);color:#fff;padding:0 8px;margin-right:6px;font-size:12px}
.pl{margin:24px 0;border-top:3px solid var(--ink);padding-top:6px}.pl h2{margin:0 0 8px;font-size:21px}.bad{color:var(--mut);font-size:14px}
.cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.cols4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:14px}
.col{min-width:0}.col h3{margin:0 0 6px}.tg{display:inline-block;padding:0 10px;font-size:13px;color:#fff}.tg.b{background:#6b6f78}.tg.a{background:var(--ok)}.tg.c{background:#2a6fb0}.tg.d{background:#8a5a00}
ol{list-style:none;margin:0;padding:0}li{display:flex;gap:8px;align-items:center;background:var(--card);border:2px solid var(--ink);margin-bottom:6px;padding:6px;min-height:64px}
li img{width:64px;height:48px;object-fit:cover;flex:none;border:1px solid var(--ink)}.rk{flex:none;width:22px;font:700 12px monospace;color:var(--mut)}
.tt{font-size:13px;line-height:1.45}.tt small{display:block;color:var(--mut)}.dl{background:var(--ng);color:#fff;font-size:11px;padding:0 5px}
li.up{border-color:var(--ok);box-shadow:3px 3px 0 var(--ok)}li.up .rk::after{content:"▲";color:var(--ok)}li.dn{border-color:var(--ng)}li.dn .rk::after{content:"▼";color:var(--ng)}
table{border-collapse:collapse;width:100%;background:var(--card)}th,td{border:2px solid var(--ink);padding:5px 10px;text-align:left;font-size:14px}
.fix{padding-left:20px;font-size:14px}.fix b{color:var(--rose)}
.phone{border:3px solid var(--ink);background:var(--card);padding:8px;min-height:240px}.nav{display:flex;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:4px;font-weight:700;font-size:13px}.nav .x{background:var(--gold);padding:0 6px}
.ph0{color:var(--mut);font-size:13px}.why2{font-size:12px;color:var(--ok);margin:8px 0 0}.ph{flex:none;width:48px;height:48px;background:#c9c5bb;display:grid;place-items:center;font-size:11px}
.add{margin-top:6px;border:2px solid var(--ink);background:var(--gold);font:700 13px inherit;padding:6px 12px;min-height:44px}
.ans{display:flex;gap:8px;flex-wrap:wrap}.ans button,.save button{border:2px solid var(--ink);background:var(--card);color:var(--ink);font:700 14px inherit;padding:6px 16px;min-height:44px;cursor:pointer}.ans button[aria-pressed=true]{background:var(--ok);color:#fff}
.ans input{flex:1;min-width:200px;min-height:44px;border:2px solid var(--ink);background:var(--card);color:var(--ink);padding:4px 10px;font:inherit}
.save{position:sticky;bottom:0;background:var(--paper);border-top:2px solid var(--ink);padding:10px 0;display:flex;gap:12px;flex-wrap:wrap;align-items:center}.save button{background:var(--gold);color:#1A1C22}
@media(max-width:800px){.cols,.cols4{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}"""

JS = """var U="@@U@@",KEY="@@K@@",P="@@P@@",K="rv-"+P,a={};try{a=JSON.parse(localStorage.getItem(K)||"{}")||{};}catch(x){}
function st(){try{localStorage.setItem(K,JSON.stringify(a));}catch(x){}}
var bs=document.querySelectorAll("#ans button"),inp=document.querySelector("#ans input");
function paint(){bs.forEach(function(b){b.setAttribute("aria-pressed",a.v===b.dataset.v);});}inp.value=a.note||"";paint();
bs.forEach(function(b){b.onclick=function(){a.v=a.v===b.dataset.v?"":b.dataset.v;st();paint();};});inp.oninput=function(){a.note=inp.value;st();};
document.getElementById("save").onclick=function(){var m=document.getElementById("msg"),tok="";st();m.textContent="このブラウザには保存しました（"+(a.v||"未選択")+"）。";
 try{tok=(JSON.parse(localStorage.getItem("wl-auth")||"{}")||{}).access_token||"";}catch(x){}
 if(!tok){m.textContent+="　係に届けるには本番のページで店長でログインしてから、もう一度押してください。";return;}
 fetch(U+"/rest/v1/rpc/review_save",{method:"POST",headers:{apikey:KEY,Authorization:"Bearer "+tok,"Content-Type":"application/json"},body:JSON.stringify({p_page:P,p_step:"choice",p_answer:a})})
 .then(function(r){return r.text().then(function(t){if(!r.ok)throw new Error(t.slice(0,120));m.textContent="保存しました。係に届きました（"+a.v+"）。";});})
 .catch(function(x){m.textContent+="　届けられませんでした："+x.message;});};"""


def page(title, kicker, why, body, pid):
    js = JS.replace("@@U@@", SUPA[0]).replace("@@K@@", SUPA[1]).replace("@@P@@", pid)
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>{e(title)}</title><style>{CSS}</style></head><body>'
            f'<header><small>{e(kicker)}</small><h1>{e(title)}</h1><a href="index.html">← テストグラウンド</a></header><main><div class="why">{why}</div>{body}'
            f'<div class="save"><button id="save">答えを保存する</button><span id="msg" role="status"></span></div></main><script>{js}</script></body></html>')


def main():
    (OUT / "product-head.html").write_text(product_page(), encoding="utf-8")
    (OUT / "wishes.html").write_text(wishes_page(), encoding="utf-8")
    print("written product-head.html wishes.html")


if __name__ == "__main__":
    main()
