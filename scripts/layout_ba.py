"""testground/layout-v2.html：並べ方の「今の本番」と「新しい並べ方」を場所ごとに左右に並べる審査（2026-11-02，用户定的：
A 新聞／B 雑誌／C P5 は「都不太行」「交代一下让我判断的背景」。頼まれたのは見た目の方向ではなくロジック）。
見た目は今の P5 のまま。同じ場所を、本番（docs/home/index.html）と新しい並べ方（layout_sample が作る _after.html）で
同じ幅（1400／390）で撮り、空白の割合・出る記事数・重なって外した記事数を数字で並べる。聞くのは ○ 直った／× まだ だけ。
写真は harness/browser.py の止め経由（storage は写しがあればそれ、なければ灰色。free-tier.md）。画像はここに置く＝storage の網址を書かない。
    python scripts/layout_ba.py     （手元で作る。本番のデータベースは変えない）"""
import html
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import layout_sample as ls  # noqa: E402

OUT = ROOT / "docs/testground/layout-v2.html"
IMG = ROOT / "docs/testground/layout-v2"
SUPA = ("https://bzokpnbcjscbcehdxtjq.supabase.co", "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC")
WIDTHS = (1400, 390)
# 場所ごとの「今の本番で困っていること」（ユーザーの指摘・測った事実）。直った所は数字から作る。
NOTE = "指摘のあった場所（空白・重複・写真の大きさ）。数字は 2 つの画面を同じ幅で同じ方法で数えたもの"

MEASURE = """([sel,cardSel])=>{const s=document.querySelector(sel);if(!s)return null;const sr=s.getBoundingClientRect();
 const cs=[...s.querySelectorAll(cardSel)].filter(c=>{const r=c.getBoundingClientRect();return r.width>8&&r.height>8&&c.offsetParent!==null&&!c.closest('details:not([open])')});
 let top=1e9,bot=0,np=0,inner=0;const rs=cs.map(c=>{const r=c.getBoundingClientRect();top=Math.min(top,r.top);bot=Math.max(bot,r.bottom);
  const i=c.querySelector('img');if(!(i&&i.getAttribute('src')))np++;
  let b=0;c.querySelectorAll('a>*,.tx,.pic,img,h3,h2').forEach(k=>{b=Math.max(b,k.getBoundingClientRect().bottom)});
  if(b&&r.bottom-b>70&&r.bottom-b>0.3*r.height)inner++;return r});
 const C=8,D=20,W=Math.ceil(sr.width/C),H=Math.ceil(Math.max(1,bot-top)/C),g=new Uint8Array(W*H);
 rs.forEach(r=>{const x0=Math.max(0,Math.floor((r.left-sr.left-D)/C)),x1=Math.min(W-1,Math.ceil((r.right-sr.left+D)/C)),y0=Math.max(0,Math.floor((r.top-top-D)/C)),y1=Math.min(H-1,Math.ceil((r.bottom-top+D)/C));
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)g[y*W+x]=1});
 let z=0;for(const v of g)if(!v)z++;
 return {cards:cs.length,blank:z/(W*H),h:Math.round(sr.height),noimg:np,inner:inner}}"""


def shoot(pw_launch):
    """本番と新しい並べ方を撮り、数字を返す。{(sid,w): {before:{…}, after:{…}}}。画像は IMG に webp で置く。"""
    from PIL import Image
    from playwright.sync_api import sync_playwright
    IMG.mkdir(parents=True, exist_ok=True)
    res = {}
    with sync_playwright() as pw:
        b = pw_launch(pw)
        for w in WIDTHS:
            for side, url, selfn in (
                ("before", (ROOT / "docs/home/index.html").as_uri(), lambda sid: "section.front" if sid == "front" else "#" + sid),
                ("after", (ROOT / "docs/testground/_after.html").as_uri() + "?shot", lambda sid: "#p-" + sid),
            ):
                pg = b.new_page(viewport={"width": w, "height": 900})
                pg.goto(url, wait_until="load", timeout=60000)
                pg.wait_for_timeout(2500)
                for sid, _name in ls.PLACES:
                    sel = selfn(sid)
                    el = pg.query_selector(sel)
                    if el is None:
                        continue
                    el.scroll_into_view_if_needed()
                    pg.wait_for_timeout(500)
                    card = (".pk" if sid == "picks" else "article.card") if side == "before" else ".cd"
                    if side == "before" and sid == "front":
                        card = "article.top,article.wc"
                    m = pg.evaluate(MEASURE, [sel, card])
                    png = el.screenshot()
                    im = Image.open(io.BytesIO(png)).convert("RGB")
                    f = IMG / f"{sid}-{w}-{side}.webp"
                    im.save(f, "WEBP", quality=72, method=6)
                    res.setdefault((sid, w), {})[side] = dict(m, w=im.width, ih=im.height, f=f.name)
                pg.close()
        b.close()
    return res


def pct(x):
    return f"{round(x * 100)}%"


def place_html(sid, name, r, dups):
    e = html.escape
    d = {w: r.get((sid, w)) for w in WIDTHS}
    if not all(d.values()) or not all(v.get("before") and v.get("after") for v in d.values()):
        return ""
    n, shown = dups.get(sid, (0, 0))
    lines = []
    for w, lab in ((1400, "PC"), (390, "スマホ")):
        b, a = d[w]["before"], d[w]["after"]
        lines.append(f"{lab}：穴 <b>{pct(b['blank'])} → {pct(a['blank'])}</b>・中が空いたカード <b>{b['inner']} → {a['inner']}</b> 枚・写真なし {b['noimg']} → {a['noimg']} 枚・画面に出る記事（もっと見るは閉じたまま） {b['cards']} → {a['cards']} 本")
    both = "".join(
        f'<div class="vw v{w}"><div class="pair"><figure><figcaption><b class="tg b">今の本番</b></figcaption><img loading="lazy" src="layout-v2/{sid}-{w}-before.webp" alt="{e(name)}の今の本番（{w}px）"></figure>'
        f'<figure><figcaption><b class="tg a">新しい並べ方</b></figcaption><img loading="lazy" src="layout-v2/{sid}-{w}-after.webp" alt="{e(name)}の新しい並べ方（{w}px）"></figure></div></div>'
        for w in WIDTHS)
    return (f'<section class="pl" id="s-{sid}" data-sid="{sid}"><h2>{e(name)}</h2><p class="bad"><b>今の困りごと</b> {e(NOTE)}</p>{both}'
            f'<ul class="fix"><li>直した規則：同じ記事・同じ写真はページ全体で 1 回だけ（この場所で外した重なり <b>{n - shown}</b> 本）・升目の最後の段に穴を作らない・右の列は先頭の高さにそろえる・写真のない記事は字だけの札</li>'
            + "".join(f"<li>{x}</li>" for x in lines) + '</ul>'
            f'<div class="ans" role="group" aria-label="{e(name)}の答え"><button class="ok" data-v="ok" aria-pressed="false">○ 直った</button>'
            f'<button class="ng" data-v="ng" aria-pressed="false">× まだ</button><input type="text" maxlength="200" placeholder="まだのとき：どこが気になるか（任意）" aria-label="メモ"></div></section>')


PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>並べ方の前と後</title>
<style>:root{--ink:#1A1C22;--paper:#EDEBE6;--card:#FBF8F1;--gold:#FFD23F;--rose:#B8336A;--ok:#1d7a4d;--ng:#D7261E;--mut:rgba(26,28,34,.62)}
@media(prefers-color-scheme:dark){:root{--paper:#1b1b1d;--card:#26262a;--ink:#eee;--mut:rgba(238,238,238,.62)}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.7 system-ui,"Noto Sans JP",sans-serif}
header{background:#1A1C22;color:#FBF8F1;padding:18px 16px}header small{color:var(--gold);font:700 11px monospace;letter-spacing:.15em}h1{margin:2px 0 0;font-size:20px}
main{max-width:1500px;margin:0 auto;padding:16px}
.why{background:var(--card);border:2px solid var(--ink);box-shadow:4px 4px 0 var(--ink);padding:12px 16px;margin-bottom:14px}.why p{margin:4px 0}.why b{display:inline-block;background:var(--rose);color:#fff;padding:0 8px;margin-right:6px;font-size:12px}
.bar{position:sticky;top:0;z-index:5;background:var(--paper);padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:2px solid var(--ink)}
.bar button,.ans button{border:2px solid var(--ink);background:var(--card);color:var(--ink);font:700 14px inherit;padding:6px 14px;cursor:pointer;min-height:44px;transition:transform .12s ease-out,background-color .12s ease-out}
.bar button:active,.ans button:active{transform:scale(.97)}.bar button[aria-pressed=true]{background:var(--gold);color:#1A1C22}
.bar a{margin-left:auto;font-size:13px}.bar a{color:var(--rose)}
.pl{margin:28px 0;padding-top:6px;border-top:3px solid var(--ink)}.pl h2{margin:0 0 6px;font-size:22px}.bad{margin:0 0 10px;color:var(--mut);font-size:14px}.bad b{color:var(--ink);margin-right:6px}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
.vw{display:none}body[data-w="1400"] .v1400,body[data-w="390"] .v390{display:block}
body[data-w="390"] .pair{grid-template-columns:repeat(2,minmax(0,390px));justify-content:start}
figure{margin:0;min-width:0}figcaption{margin-bottom:4px}.tg{display:inline-block;padding:0 10px;font-size:13px;color:#fff}.tg.b{background:#6b6f78}.tg.a{background:var(--ok)}
figure img{display:block;width:100%;height:auto;border:2px solid var(--ink);background:var(--card)}
.fix{margin:10px 0;padding-left:20px;font-size:14px}.fix b{color:var(--rose)}
.ans{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.ans input{flex:1;min-width:200px;min-height:44px;border:2px solid var(--ink);background:var(--card);color:var(--ink);padding:4px 10px;font:inherit}
.ans .ok[aria-pressed=true]{background:var(--ok);color:#fff}.ans .ng[aria-pressed=true]{background:var(--ng);color:#fff}
.save{position:sticky;bottom:0;background:var(--paper);border-top:2px solid var(--ink);padding:10px 0;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.save button{border:2px solid var(--ink);background:var(--gold);color:#1A1C22;font:900 15px inherit;padding:8px 20px;cursor:pointer;min-height:44px}.save span{font-size:14px}
@media(max-width:700px){.pair,body[data-w="390"] .pair{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}</style></head><body data-w="1400">
<header><small>審査待ち（並べ方）</small><h1>並べ方の「今の本番」と「新しい並べ方」</h1></header>
<main>
<div class="why"><p><b>なぜ聞くか</b>頼まれたのは並べ方のロジック（空白・同じ記事の二度出し・写真の大きさ・押した所へ行く）で、見た目の方向ではありません。前の見本（新聞・雑誌・P5 の 3 案）は、見た目を聞いてしまっていたので外しました。</p>
<p><b>今の見た目</b>見た目は今の P5（太い枠・硬い影・傾けた札）のまま。下は、指摘のあった場所ごとの「今の本番」（左）と「新しい並べ方」（右）です。「穴」は、カードのすき間（約 40px）より大きい空きの面積の割合です。「新しい並べ方」は先頭に出す記事の数を増やしています。多すぎるときは × のメモに書いてください。</p>
<p><b>答えで何が変わるか</b>○ なら、本番のこの場所を新しい並べ方に入れ替えます（全部の版面・店長とお客さま共通の規則）。× なら、そこだけ直して作り直します。本番の写真は無料の枠の都合で灰色の所があります。</p></div>
<div class="bar" role="group" aria-label="幅の切り替え"><button data-w="1400" aria-pressed="true">PC（1400px）</button><button data-w="390" aria-pressed="false">スマホ（390px）</button><a href="index.html">← テストグラウンド</a></div>
@@PLACES@@
<div class="save"><button id="save">答えを保存する</button><span id="msg" role="status"></span></div>
</main>
<script>
var U="@@URL@@",KEY="@@KEY@@",K="rv-layout-ba",ans={};
try{ans=JSON.parse(localStorage.getItem(K)||"{}")||{};}catch(e){}
function store(){try{localStorage.setItem(K,JSON.stringify(ans));}catch(e){}}
document.querySelectorAll(".bar button").forEach(function(b){b.onclick=function(){document.body.dataset.w=b.dataset.w;document.querySelectorAll(".bar button").forEach(function(x){x.setAttribute("aria-pressed",x===b);});};});
document.querySelectorAll(".pl").forEach(function(p){var sid=p.dataset.sid,a=ans[sid]||{},bs=p.querySelectorAll(".ans button"),inp=p.querySelector("input");
 function paint(){bs.forEach(function(b){b.setAttribute("aria-pressed",(ans[sid]||{}).v===b.dataset.v);});}
 inp.value=a.note||"";paint();
 bs.forEach(function(b){b.onclick=function(){ans[sid]=Object.assign(ans[sid]||{},{v:(ans[sid]||{}).v===b.dataset.v?"":b.dataset.v});store();paint();};});
 inp.oninput=function(){ans[sid]=Object.assign(ans[sid]||{},{note:inp.value});store();};});
document.getElementById("save").onclick=function(){var m=document.getElementById("msg"),tok="",n=0;
 for(var k in ans)if(ans[k].v)n++;
 store();m.textContent="このブラウザには保存しました（"+n+" / @@N@@ 場所）。";
 try{tok=(JSON.parse(localStorage.getItem("wl-auth")||"{}")||{}).access_token||"";}catch(e){}
 if(!tok){m.textContent+="　係に届けるには本番のページ（右上のログイン）で店長でログインしてから、もう一度押してください。";return;}
 fetch(U+"/rest/v1/rpc/review_save",{method:"POST",headers:{apikey:KEY,Authorization:"Bearer "+tok,"Content-Type":"application/json"},
  body:JSON.stringify({p_page:"layout-v2",p_step:"before-after",p_answer:{answers:ans,total:@@N@@}})})
 .then(function(r){return r.text().then(function(t){if(!r.ok)throw new Error(t.slice(0,120));m.textContent="保存しました。係に届きました（"+n+" / @@N@@ 場所）。";});})
 .catch(function(err){m.textContent+="　届けられませんでした："+err.message;});};
</script></body></html>"""


def main():
    from browser import launch
    dups = ls.main()
    res = shoot(launch)
    parts = [place_html(sid, name, res, dups) for sid, name in ls.PLACES]
    parts = [p for p in parts if p]
    page = (PAGE.replace("@@PLACES@@", "".join(parts)).replace("@@URL@@", SUPA[0]).replace("@@KEY@@", SUPA[1]).replace("@@N@@", str(len(parts))))
    OUT.write_text(page, encoding="utf-8")
    (ROOT / "state").mkdir(exist_ok=True)
    print("written", OUT, len(parts), "places")
    print(json.dumps({f"{k[0]}-{k[1]}": {s: {x: v for x, v in m.items() if x in ("cards", "blank", "noimg")} for s, m in d.items()} for k, d in res.items()}, ensure_ascii=False, indent=0)[:3000])


if __name__ == "__main__":
    main()
