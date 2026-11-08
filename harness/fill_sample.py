"""「どの幅でも空きを残さない」版型の見本 3 案（2026-11-08，店長：他の人の方法を組み合わせた 3 案をテストグラウンドで見比べる）。

    python harness/fill_sample.py    # docs/testground/fill-a.html・fill-b.html・fill-c.html・fill.html（見比べ）

どれも今のページ docs/home/index.html の写しに、上書きの CSS を足しただけ（本番の render.py は変えない）。
  A Every Layout（Heydon Pickering・Andy Bell）の Switcher と Grid ＋ Intrinsic Web Design（Jen Simmons）の fr
    右の列の箱は横いっぱいで縦に積み、中身を段に並べる（Grid）。箱は中身の高さだけ。カードの一覧は auto-fit で空いた席を作らない
  B Masonry（David DeSandro・Pinterest 型）＋ CSS 段組みの高さ揃え（column-fill: balance）
    右の列の箱も記事のカードも 1 つの流れに入れ、列の高さを揃えて詰める。右下・下の空きが出ない
  C 新聞の組版（段で組む）＋ grid-auto-flow: dense（CSS-Tricks）＋ Intrinsic Web Design
    全部を同じ段の網に置き、空いた席は後ろの小さいカードで埋める。最後の段の端数は横に伸ばす
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/home/index.html"
OUT = ROOT / "docs/testground"

COMMON = """
/* カードの一覧：auto-fit（空いた席を作らず、ある分で幅を分け合う）・最後の段の端数は横いっぱい（Every Layout の Grid） */
.pkgrid.row{grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))!important}
.pkgrid.row>.pk:last-child:nth-child(odd){grid-column:1/-1}
"""
# 横に並べる案：2 つの箱の高さを揃える。長いほうの下の項目を隠す（「全部見る」から見られる）。3 件は残す
EVEN_JS = """<script>(()=>{const s=()=>document.querySelector('.mgrid>.fside');
const go=reset=>{const f=s();if(!f)return;const bx=[...f.children].filter(b=>b.offsetHeight);
if(reset)f.querySelectorAll('li[data-even]').forEach(l=>{l.hidden=false;l.removeAttribute('data-even');});
if(bx.length!==2||Math.abs(bx[0].offsetTop-bx[1].offsetTop)>4)return;
for(let n=0;n<40;n++){const[a,b]=bx.map(x=>x.offsetHeight);if(Math.abs(a-b)<=18)break;const tall=a>b?bx[0]:bx[1];
const li=[...tall.querySelectorAll('ol>li:not([hidden])')];if(li.length<=3)break;const l=li[li.length-1];l.hidden=true;l.setAttribute('data-even','1');}};
/* 壁の並べ直し（FIT_JS の wall）が行を表示に戻すので、箱の高さが変わるたびに揃え直す（揃っていれば何もしない） */
let q;const soon=r=>{clearTimeout(q);q=setTimeout(()=>go(r),120);};
addEventListener('load',()=>{soon(true);if(window.ResizeObserver){const f=s();if(f){const ro=new ResizeObserver(()=>soon(false));[...f.children].forEach(b=>ro.observe(b));}}});
addEventListener('resize',()=>setTimeout(()=>soon(true),400));})();</script>"""

PLANS = {
    "1": ("1：縦に積む（中身を段に）", COMMON + """
@media (max-width:1200px){
 .mgrid .fside{display:flex!important;flex-direction:column;gap:20px}
 .mgrid .fside>*{flex:none!important;min-width:0}
 .mgrid .fside .swish ol,.mgrid .fside .agenda ol{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr))!important;column-gap:28px}
}
""", ""),
    "2": ("2：横に半分ずつ（高さを揃える）", COMMON + """
@media (max-width:1200px){
 .mgrid .fside{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr))!important;gap:20px;align-items:start}
 .mgrid .fside>*{flex:none!important;min-width:0;height:auto!important}
 .mgrid .fside .agenda ol{grid-template-columns:minmax(0,1fr)!important}
 /* 揃えたあとの端数（1 行未満）は、短いほうの箱の行の間に均等に分ける（箱の下に空きを残さない） */
 .mgrid .fside{align-items:stretch!important}
 .mgrid .fside>*{display:flex!important;flex-direction:column}
 .mgrid .fside>* ol{flex:1 1 auto;display:flex!important;flex-direction:column;justify-content:space-between}
}
""", EVEN_JS),
    "3": ("3：横に 3 対 2（予定を広く・高さを揃える）", COMMON + """
@media (max-width:1200px){
 .mgrid .fside{display:grid!important;grid-template-columns:minmax(0,3fr) minmax(0,2fr)!important;gap:20px;align-items:start}
 .mgrid .fside>*{flex:none!important;min-width:0;height:auto!important}
 .mgrid .fside .agenda ol{grid-template-columns:minmax(0,1fr)!important}
 /* 揃えたあとの端数（1 行未満）は、短いほうの箱の行の間に均等に分ける（箱の下に空きを残さない） */
 .mgrid .fside{align-items:stretch!important}
 .mgrid .fside>*{display:flex!important;flex-direction:column}
 .mgrid .fside>* ol{flex:1 1 auto;display:flex!important;flex-direction:column;justify-content:space-between}
}
@media (max-width:900px){.mgrid .fside{grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important}}
""", EVEN_JS),
}

PICK = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>予定と欲しい物の並べ方 3 案</title><style>
:root{--ink:#1A1C22;--paper:#EDEBE6;--card:#FBF8F1;--rose:#B8336A}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,"Noto Sans JP",sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--card);border-bottom:2px solid var(--ink);padding:10px 16px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}
h1{font-size:17px;margin:0}
.seg{display:flex;flex-wrap:wrap;gap:6px}.seg button{font:inherit;padding:4px 12px;border:2px solid var(--ink);background:#fff;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--ink);color:#fff}
.note{padding:10px 16px;margin:0}
.frame{padding:0 16px 24px}.box{border:2px solid var(--ink);background:#fff;overflow:hidden;transform-origin:0 0}
iframe{border:0;display:block}
</style></head><body>
<header><h1>予定と欲しい物の並べ方 3 案</h1>
<div class="seg" id="plan"><button data-p="now" aria-pressed="false">今</button><button data-p="1" aria-pressed="true">1</button><button data-p="2" aria-pressed="false">2</button><button data-p="3" aria-pressed="false">3</button></div>
<div class="seg" id="w"><button data-w="390">390</button><button data-w="600">600</button><button data-w="900" aria-pressed="true">900</button><button data-w="1200">1200</button><button data-w="1400">1400</button></div>
</header>
<p class="note" id="desc"></p>
<div class="frame"><div class="box" id="box"><iframe id="f" title="見本"></iframe></div></div>
<script>
const D={now:'今の本番の写し（比べる元）',1:'1：予定と欲しい物を横いっぱいの箱で縦に積み、中身を 2〜3 列に並べる（Every Layout の Grid）。',
2:'2：予定と欲しい物を半分ずつ横に並べ、高さを揃える（長いほうの残りは「全部見る」）。狭い幅では縦に積む（Every Layout の Switcher）。',
3:'3：字の多い予定を広く（3）、欲しい物を狭く（2）並べ、高さを揃える（Intrinsic Web Design の fr）。'};
let p='1',w=900;const f=document.getElementById('f'),box=document.getElementById('box');
function draw(){f.src='fill-'+p+'.html';document.getElementById('desc').textContent=D[p]+'（幅 '+w+'px で表示）';
 const avail=box.parentElement.clientWidth-32,k=Math.min(1,avail/w);f.style.width=w+'px';f.style.height=Math.round((innerHeight-140)/k)+'px';
 f.style.transform='scale('+k+')';f.style.transformOrigin='0 0';box.style.width=Math.round(w*k)+'px';box.style.height=Math.round((innerHeight-140))+'px';}
document.querySelectorAll('#plan button').forEach(b=>b.onclick=()=>{p=b.dataset.p;document.querySelectorAll('#plan button').forEach(x=>x.setAttribute('aria-pressed',x===b));draw();});
document.querySelectorAll('#w button').forEach(b=>b.onclick=()=>{w=+b.dataset.w;document.querySelectorAll('#w button').forEach(x=>x.setAttribute('aria-pressed',x===b));draw();});
addEventListener('resize',draw);draw();
</script></body></html>
"""


def base(html, title):
    html = re.sub(r'<meta name="wl-ver"[^>]*>', "", html)            # 見本は自動更新しない
    html = html.replace("<head>", '<head><base href="../home/"><meta name="robots" content="noindex">', 1)
    # ログイン中でも本人のページ（me.html）へ送らない（2026-11-08：店長は test-a でログインしたまま見るので、見本が全部いまの本番に見えていた）
    html = html.replace('"page": "index"', '"page": "sample"', 1)
    return re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)


def main():
    src = SRC.read_text(encoding="utf-8")
    (OUT / "fill-now.html").write_bytes(base(src, "版型 見本・今").encode("utf-8"))
    for k, (title, css, js) in PLANS.items():
        html = base(src, f"版型 見本・{title}").replace("</head>", f"<style>{css}</style></head>", 1).replace("</body>", js + "</body>", 1)
        (OUT / f"fill-{k}.html").write_bytes(html.encode("utf-8"))
    (OUT / "fill.html").write_bytes(PICK.encode("utf-8"))
    for old in ("a", "b", "c"):   # 前の 3 案（2026-11-08 店長：だめ）
        (OUT / f"fill-{old}.html").unlink(missing_ok=True)
    print("fill-now / fill-1 / fill-2 / fill-3 / fill.html")


if __name__ == "__main__":
    main()
