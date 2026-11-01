"""testground/face-size.html：小元素の顔の大きさを決める審査。触って決める・下の段から 1 段ずつ（HARNESS「審査は触って決める」）。
今は 1 段目＝分類（全身／胸像／ロゴ／物・生き物）。items.yaml の小元素を自動の分類で並べ、違うものを押して直す。本番は替えない。
答えは localStorage と、店長でログインしていれば review_answers（db/review_answers.sql）に保存。"""
import html
import json
import yaml
from pathlib import Path
import emblem_face as ef

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/testground/face-size.html"
CLS = [("bust", "胸像"), ("full", "全身"), ("logo", "ロゴ"), ("thing", "物・生き物")]
SUPA = ("https://bzokpnbcjscbcehdxtjq.supabase.co", "sb_publishable_EJunmcNeSQJOm2bnzc4JWA_u48iV4NC")


def auto_class(e):
    """自動の分類（4 つ）。全身 = 体の測りがある立ち絵（上半身に切ったもの cut・頭の大きい big も含む）、胸像 = 顔だけの切り抜き。"""
    f, b = e.get("face"), e.get("body")
    if e.get("shape") in ("logo", "icon", "badge"):
        return "logo"
    if not f or not f[0]:
        return "thing"
    return "bust" if not (b and len(b) == 5) else "full"


def emblems():
    d = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    out = []
    for it in d["items"] if isinstance(d, dict) else d:
        for e in it.get("emblem") or []:
            if (e.get("image") or "").startswith("emblems/") and (ROOT / "docs/home" / e["image"]).exists():
                f, b = e.get("face"), e.get("body")
                b = b if b and len(b) == 5 else None
                px = ef.shown_face_px(f[0], b, ef.fit(f)[0]) if f and f[0] else None
                out.append(dict(i=e["image"], n=str(e.get("subject") or "")[:18], w=it["name"][:14], c=auto_class(e), px=px))
    return out


def build():
    em = emblems()
    cnt = {c: sum(x["c"] == c for x in em) for c, _ in CLS}
    rng = lambda c: [x["px"] for x in em if x["c"] == c and x["px"]]
    rows = {c: (min(rng(c)), max(rng(c))) for c in ("bust", "full") if rng(c)}
    data = json.dumps([[x["i"], x["n"], x["w"], x["c"]] for x in em], ensure_ascii=False)
    now = (f"今の本番：胸像 {cnt['bust']} 枚の顔は {rows['bust'][0]:.0f}〜{rows['bust'][1]:.0f}px、全身 {cnt['full']} 枚の顔は {rows['full'][0]:.0f}〜{rows['full'][1]:.0f}px"
           f"（最大÷最小 {rows['bust'][1] / rows['bust'][0]:.1f} 倍と {rows['full'][1] / rows['full'][0]:.1f} 倍）。ロゴ {cnt['logo']} 枚・物や生き物 {cnt['thing']} 枚は顔を測らない。")
    page = PAGE.replace("@@DATA@@", data).replace("@@NOW@@", html.escape(now)).replace("@@URL@@", SUPA[0]).replace("@@KEY@@", SUPA[1]).replace("@@N@@", str(len(em)))
    OUT.write_text(page, encoding="utf-8")
    return OUT


PAGE = r"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>顔の大きさの審査</title>
<style>:root{--bg:#EDEBE6;--card:#FBF8F1;--fg:#1A1C22;--rose:#B8336A;--gold:#FFD23F;--ok:#1d7a4d;--mut:rgba(26,28,34,.62)}
@media(prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#26262a;--fg:#eee;--mut:rgba(238,238,238,.62)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:500 15px/1.7 system-ui,"Noto Sans JP",sans-serif}
header{background:#1A1C22;color:#FBF8F1;padding:18px 16px}header small{color:var(--gold);font:700 11px monospace;letter-spacing:.15em}h1{margin:2px 0 0;font-size:20px}
main{max-width:1100px;margin:0 auto;padding:16px}
.steps{display:flex;gap:6px;flex-wrap:wrap;padding:0;margin:0 0 14px;list-style:none}.steps li{padding:2px 10px;border:2px solid var(--fg);font-size:12px;font-weight:700;opacity:.45}.steps li.on{background:var(--gold);color:#1A1C22;opacity:1}
.why{background:var(--card);border:2px solid var(--fg);box-shadow:4px 4px 0 var(--fg);padding:12px 16px;margin-bottom:14px}.why p{margin:4px 0}.why b{display:inline-block;background:var(--rose);color:#fff;padding:0 8px;margin-right:6px;font-size:12px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:2px solid var(--fg)}
.tab{border:2px solid var(--fg);background:var(--card);color:var(--fg);padding:4px 12px;font:700 13px inherit;cursor:pointer}.tab[aria-pressed=true]{background:var(--fg);color:var(--bg)}
button.save{margin-left:auto;background:var(--rose);color:#fff;border:2px solid var(--fg);padding:6px 16px;font:900 14px inherit;cursor:pointer}
#msg{font-size:13px;color:var(--mut);width:100%}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:8px;padding:12px 0}
.c{background:var(--card);border:2px solid var(--fg);padding:4px;text-align:center;font-size:11px;cursor:pointer;position:relative;color:var(--fg);font-family:inherit}.c.ch{outline:3px solid var(--rose)}
.c img{display:block;margin:0 auto;height:84px;max-width:100%;object-fit:contain;background:repeating-conic-gradient(#0001 0 25%,#0000 0 50%) 0 0/12px 12px}
.c i{display:block;font-style:normal;font-weight:900;margin-top:2px;font-size:12px}.c.ch i{color:var(--rose)}.c small{display:block;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lock{margin-top:18px;color:var(--mut);font-size:13px}</style>
<header><small>審査 · 顔の大きさ · 1 段目 / 全 8 段</small><h1>1 段目　これは何の絵？（分類）</h1></header>
<main>
<ol class="steps"><li class="on">1 分類</li><li>2 顔の枠</li><li>3 胸像</li><li>4 全身</li><li>5 釣り合い</li><li>6 ロゴ</li><li>7 物</li><li>8 本物のページ</li></ol>
<div class="why">
<p><b>なぜ聞くか</b>大きさの基準は「全身」「胸像」「ロゴ」「物」で別々に決めます。どれに入れるかを機械が間違えると、基準そのものがずれるので、いちばん下のここから確かめます。</p>
<p><b>今どうなっている</b>@@NOW@@　下に @@N@@ 枚すべてを自動の分類つきで並べました。</p>
<p><b>答えで何が変わる</b>押して直した分類は、2 段目以降の見本と、本番の大きさの規則（emblem_face.face_class）の入力になります。直さなければ今の分類のまま次へ進みます。</p>
<p>使い方：絵を押すと分類が 胸像 → 全身 → ロゴ → 物・生き物 の順に変わります（桃色の枠＝あなたが直したもの）。全部見終わったら右上の「この段を保存」。</p></div>
<div class="bar" id="bar"><span id="tabs"></span><button class="save" id="save">この段を保存</button><div id="msg"></div></div>
<div class="grid" id="grid"></div>
<p class="lock">2 段目（顔の枠）以降は、この段を保存してから開きます。</p>
</main>
<script>
var D=@@DATA@@,CL=[["bust","胸像"],["full","全身"],["logo","ロゴ"],["thing","物・生き物"]],NAME={bust:"胸像",full:"全身",logo:"ロゴ",thing:"物・生き物"};
var K="rv-face-s1",U="@@URL@@",KEY="@@KEY@@",ans={},flt="all";
try{ans=JSON.parse(localStorage.getItem(K)||"{}")||{};}catch(e){}
function cur(r){return ans[r[0]]||r[3];}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function tabs(){var h='<button class="tab" aria-pressed="'+(flt==="all")+'" data-f="all">全部 '+D.length+'</button> ';
 CL.forEach(function(c){var n=D.filter(function(r){return cur(r)===c[0];}).length;h+='<button class="tab" aria-pressed="'+(flt===c[0])+'" data-f="'+c[0]+'">'+c[1]+' '+n+'</button> ';});
 var ch=Object.keys(ans).length;h+='<button class="tab" aria-pressed="'+(flt==="ch")+'" data-f="ch">直した '+ch+'</button>';document.getElementById("tabs").innerHTML=h;}
function grid(){var h="";D.forEach(function(r,i){var c=cur(r);if(flt==="ch"?!ans[r[0]]:(flt!=="all"&&c!==flt))return;
 h+='<button class="c'+(ans[r[0]]?" ch":"")+'" data-i="'+i+'"><img loading="lazy" decoding="async" src="../home/'+esc(r[0])+'" alt=""><i>'+NAME[c]+'</i><small>'+esc(r[1])+'</small><small>'+esc(r[2])+'</small></button>';});
 document.getElementById("grid").innerHTML=h;}
function paint(){tabs();grid();}
function store(){try{localStorage.setItem(K,JSON.stringify(ans));}catch(e){}}
document.getElementById("grid").addEventListener("click",function(e){var b=e.target.closest(".c");if(!b)return;var r=D[+b.dataset.i],c=cur(r),o=CL.map(function(x){return x[0];}),n=o[(o.indexOf(c)+1)%4];
 if(n===r[3])delete ans[r[0]];else ans[r[0]]=n;store();b.querySelector("i").textContent=NAME[n];b.classList.toggle("ch",!!ans[r[0]]);tabs();
 if(flt!=="all"&&flt!=="ch"||flt==="ch")setTimeout(grid,350);});
document.getElementById("tabs").addEventListener("click",function(e){var b=e.target.closest(".tab");if(b){flt=b.dataset.f;paint();}});
document.getElementById("save").addEventListener("click",function(){var m=document.getElementById("msg"),tok="";
 try{tok=(JSON.parse(localStorage.getItem("wl-auth")||"{}")||{}).access_token||"";}catch(e){}
 var cnt={};D.forEach(function(r){cnt[cur(r)]=(cnt[cur(r)]||0)+1;});
 store();m.textContent="このブラウザには保存しました（直した "+Object.keys(ans).length+" 枚）。";
 if(!tok){m.textContent+="　係に届けるには本番のページ（右上のログイン）で店長でログインしてから、もう一度押してください。";return;}
 fetch(U+"/rest/v1/rpc/review_save",{method:"POST",headers:{apikey:KEY,Authorization:"Bearer "+tok,"Content-Type":"application/json"},
  body:JSON.stringify({p_page:"face-size",p_step:"1",p_answer:{changed:ans,counts:cnt,total:D.length}})})
 .then(function(r){return r.text().then(function(t){if(!r.ok)throw new Error(t.slice(0,120));m.textContent="保存しました。係に届きました（直した "+Object.keys(ans).length+" 枚）。次の段を作ります。";});})
 .catch(function(err){m.textContent+="　届けられませんでした："+err.message;});});
paint();
</script></html>
"""

if __name__ == "__main__":
    print(build())
