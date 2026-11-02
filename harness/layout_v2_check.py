"""testground/layout-v2.html の自動点検（2026-11-02・PR #762 の指摘：確かめが手のスクショだけだった）。
    python harness/layout_v2_check.py [--url file または https://…]   終了コード 1 = ✗ あり
1400 / 768 / 390 で「もっと見る」を全部開き、数える：①横はみ出し 0 ②左の目次の項目数 = 版面の数、リンク先が実在
③同じ写真 0（URL ではなく画像の中身。scripts/layout_sample.photo_key）④絵文字の絵が写真の場所に 0
⑤格子の穴（最後の段のカードの数が列の数で割り切れる＝ux_check の「空白の割合」の升目版）0、カード内の空白（中身の底から枠の底まで）が
枠の 30% 超かつ 70px 超のカードは 1 版面 2 枚まで ⑥主写真が 16:9（±2%）⑦字だけカードに写真の穴がない（.np に .pic が無い）"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.layout_sample import photo_key, same_photo, emoji  # noqa: E402
import pathlib as _pl
import sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "harness"))
from browser import launch  # noqa: E402  点検のブラウザは共通の 1 か所から（free-tier.md）

JS = """()=>{const o={over:document.documentElement.scrollWidth-innerWidth,toc:0,boards:0,badToc:0,imgs:[],gridHole:[],blank:[],hero:[],npPic:0};
 o.toc=document.querySelectorAll('.toc a').length;o.boards=document.querySelectorAll('section.bd').length;
 document.querySelectorAll('.toc a').forEach(a=>{if(!document.querySelector(a.getAttribute('href')))o.badToc++});
 document.querySelectorAll('.cd img').forEach(i=>o.imgs.push(i.getAttribute('src')));
 o.npPic=document.querySelectorAll('.cd.np .pic').length;
 document.querySelectorAll('.cd.hero .pic').forEach(p=>{const r=p.getBoundingClientRect();if(r.width&&Math.abs(r.width/r.height-16/9)>0.02*16/9)o.hero.push(Math.round(100*r.width/r.height)/100)});
 document.querySelectorAll('.gr').forEach(g=>{const k=[...g.children].filter(c=>c.getBoundingClientRect().height>0).length,cols=getComputedStyle(g).gridTemplateColumns.split(' ').length;
  if(k>1&&k%cols)o.gridHole.push(g.closest('section').id+' '+k+' 枚 / '+cols+' 列＝'+(cols-k%cols)+' 個の穴')});
 document.querySelectorAll('section.bd').forEach(s=>{let n=0;s.querySelectorAll('.cd').forEach(c=>{const r=c.getBoundingClientRect();if(!r.height)return;let b=0;
  c.querySelectorAll('a>*').forEach(k=>{b=Math.max(b,k.getBoundingClientRect().bottom)});
  const blank=r.bottom-b;if(b&&blank>70&&blank>0.3*r.height)n++});if(n>2)o.blank.push(s.id+' '+n+' 枚')});
 return o}"""


def check(url):
    from playwright.sync_api import sync_playwright
    bad, seen = [], []
    with sync_playwright() as p:
        b = launch(p)
        for w in (1400, 768, 390):
            pg = b.new_page(viewport={"width": w, "height": 900})
            pg.goto(url, wait_until="load", timeout=60000)
            pg.click("#openall")
            pg.wait_for_timeout(1500)
            o = pg.evaluate(JS)
            if o["over"] > 0:
                bad.append(f"{w}: 横はみ出し {o['over']}px")
            if o["toc"] != o["boards"]:
                bad.append(f"{w}: 目次 {o['toc']} 項目 ≠ 版面 {o['boards']}")
            if o["badToc"]:
                bad.append(f"{w}: 目次のリンク先がない {o['badToc']}")
            if o["npPic"]:
                bad.append(f"{w}: 字だけカードに写真の穴 {o['npPic']}")
            if o["hero"]:
                bad.append(f"{w}: 主写真が 16:9 でない {o['hero'][:3]}")
            if o["gridHole"]:
                bad.append(f"{w}: 格子の穴 {o['gridHole'][:4]}")
            if o["blank"]:
                bad.append(f"{w}: カード内の空白が多い版面 {o['blank'][:4]}")
            if w == 1400:
                seen = o["imgs"]
            pg.close()
        b.close()
    emo = [u for u in seen if emoji(u)]
    if emo:
        bad.append(f"絵文字の絵が写真の場所に {len(emo)} 枚")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(16) as ex:
        keys = list(zip(seen, ex.map(photo_key, seen)))
    dup = [(a, b) for i, (a, ka) in enumerate(keys) for b, kb in keys[i + 1:] if same_photo(ka, kb)]
    if dup:
        bad.append(f"同じ写真 {len(dup)} 組：" + " / ".join(f"{a[-30:]}={b[-30:]}" for a, b in dup[:3]))
    return bad, len(seen)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=(ROOT / "docs/testground/layout-v2.html").as_uri())
    a = ap.parse_args()
    bad, n = check(a.url)
    print(f"layout-v2 点検：写真 {n} 枚")
    for x in bad:
        print("  ✗", x)
    print("OK" if not bad else f"✗ {len(bad)} 件")
    sys.exit(1 if bad else 0)
