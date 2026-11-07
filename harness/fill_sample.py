"""「どの幅でも空きを残さない」版型の見本 3 案（2026-11-08，店長：他の人の方法を組み合わせた 3 案をテストグラウンドで見比べる）。

    python harness/fill_sample.py    # docs/testground/fill-a.html・fill-b.html・fill-c.html・fill.html（見比べ）

どれも今のページ docs/home/index.html の写しに、上書きの CSS を足しただけ（本番の render.py は変えない）。
  A Every Layout（Heydon Pickering・Andy Bell）の Switcher と Grid ＋ Intrinsic Web Design（Jen Simmons）の fr
    右の列の箱は「全部横に並ぶか、全部縦に積むか」の二択（Switcher）。並ぶときは残りの幅を分け合う。カードの一覧は auto-fit で空いた席を作らない
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

PLANS = {
    "a": ("A：Every Layout ＋ Intrinsic", """
/* 右の列（予定・欲しい物）：Switcher。幅が 640px あれば全部横に並び、残りを分け合う。足りなければ全部縦に積む（席を余らせない） */
@media (max-width:1100px){
 .mgrid .fside{display:flex!important;flex-wrap:wrap;gap:20px}
 .mgrid .fside>*{flex-grow:1;flex-basis:calc((640px - 100%) * 999);min-width:0}
}
/* カードの一覧：auto-fit（空いた席を作らず、ある分で幅を分け合う） */
.pkgrid.row{grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))!important}
/* 最後の段の端数は横いっぱい */
.pkgrid.row>.pk:last-child:nth-child(odd){grid-column:1/-1}
"""),
    "b": ("B：Masonry ＋ 段組みの高さ揃え", """
/* 記事のカードも右の箱も 1 つの流れに入れ、列の高さを揃えて詰める（右下の空きが出ない） */
@media (min-width:761px){
 .mgrid{display:block!important;columns:300px;column-gap:22px;column-fill:balance}
 .mgrid>.wall,.mgrid>.fside{display:contents!important}
 .mgrid .wc,.mgrid .fside>*{break-inside:avoid;margin:0 0 22px!important;width:auto!important;grid-row:auto!important;grid-column:auto!important;display:block}
 .mgrid .wc .pic{width:100%!important;height:auto!important;aspect-ratio:16/10!important}
 .mgrid .wc.lead{column-span:none}
}
.pkgrid.row{grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))!important}
"""),
    "c": ("C：新聞の段組み ＋ dense ＋ Intrinsic", """
/* 全部を同じ段の網に置く。空いた席は後ろの小さいカードで埋め（dense）、箱は段の高さまで伸ばす */
@media (min-width:761px){
 .mgrid{display:grid!important;grid-template-columns:repeat(auto-fill,minmax(250px,1fr))!important;grid-auto-flow:row dense;gap:22px;align-items:stretch!important}
 .mgrid>.wall,.mgrid>.fside{display:contents!important}
 .mgrid .wc{grid-row:auto!important;grid-column:auto!important}
 .mgrid .wc.lead{grid-column:span 2!important;grid-row:span 2!important}
 .mgrid .fside>*{grid-row:span 2}
}
.pkgrid.row{grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))!important}
.pkgrid.row>.pk:last-child:nth-child(odd){grid-column:1/-1}
"""),
}

PICK = """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>空きを残さない版型 3 案</title><style>
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
<header><h1>空きを残さない版型 3 案</h1>
<div class="seg" id="plan"><button data-p="now" aria-pressed="false">今</button><button data-p="a" aria-pressed="true">A</button><button data-p="b" aria-pressed="false">B</button><button data-p="c" aria-pressed="false">C</button></div>
<div class="seg" id="w"><button data-w="390">390</button><button data-w="600">600</button><button data-w="900" aria-pressed="true">900</button><button data-w="1200">1200</button><button data-w="1400">1400</button></div>
</header>
<p class="note" id="desc"></p>
<div class="frame"><div class="box" id="box"><iframe id="f" title="見本"></iframe></div></div>
<script>
const D={now:'今の本番の写し（比べる元）',a:'A：Every Layout（Heydon Pickering・Andy Bell）の Switcher と Grid ＋ Intrinsic Web Design（Jen Simmons）。右の箱は全部横に並ぶか全部縦に積むかの二択で、席を余らせない。',
b:'B：Masonry（David DeSandro・Pinterest 型）＋ 段組みの高さ揃え。記事も右の箱も 1 つの流れに入れて、列の高さを揃えて詰める。',
c:'C：新聞の段組み ＋ dense（CSS-Tricks）＋ Intrinsic Web Design。全部を同じ網に置き、空いた席を後ろの小さいカードで埋める。'};
let p='a',w=900;const f=document.getElementById('f'),box=document.getElementById('box');
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
    return re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)


def main():
    src = SRC.read_text(encoding="utf-8")
    (OUT / "fill-now.html").write_bytes(base(src, "版型 見本・今").encode("utf-8"))
    for k, (title, css) in PLANS.items():
        html = base(src, f"版型 見本・{title}").replace("</head>", f"<style>{css}</style></head>", 1)
        (OUT / f"fill-{k}.html").write_bytes(html.encode("utf-8"))
    (OUT / "fill.html").write_bytes(PICK.encode("utf-8"))
    print("fill-now / fill-a / fill-b / fill-c / fill.html")


if __name__ == "__main__":
    main()
