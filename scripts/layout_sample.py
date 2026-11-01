"""testground/layout-v2.html：記事の並べ方を 1 つの仕組みで作り直した全体見本（本物のデータ・審査待ち）。
本番の docs/home/index.html から記事を読み、①assign()＝記事の割り当て 1 か所（同じ記事は 1 回）②card()＝カード 1 種類
③board()＝並べる器 1 種類 で 7 つの場所（DESIGN_PRINCIPLES G・L1〜L11）を組む。本番は入れ替えない。"""
import html, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/home/index.html"
OUT = ROOT / "docs/testground/layout-v2.html"
PLACES = [("w-79b3c280", "滑雪"), ("w-130724c0", "猫用品"), ("w-cdea10ae", "チェーンソーマン"), ("front", "ほかの注目"),
          ("picks", "気になるかも？"), ("w-bf928230", "Astrae Oratio"), ("w-c1c3e0ed", "BLEACH Mirrors High")]
RAIL, GRID = 3, 12


def norm(t):
    return re.sub(r"\W+", "", t.lower())[:24]


def story(a):
    """記事 1 つを読む（article.card か .pk）。リンク・題・写真・日付・出典。"""
    lk = a.select_one("a[href]")
    img = a.select_one("img[data-e=s]")
    t = a.select_one("h2,h3,.pkt b") or a
    when = a.select_one(".when")
    src = a.select_one(".src,.from")
    pic = a.select_one(".pic")
    isrc = (img.get("src") if img else "") or ""
    if isrc and not isrc.startswith(("http", "data:")):
        isrc = "../home/" + isrc   # 本番の相対パスを testground から読めるように
    return dict(href=(lk or {}).get("href", "") if lk else "", title=t.get_text(" ", strip=True),
                img=isrc, ph=(a.select_one(".ph").get_text(strip=True) if a.select_one(".ph") else ""),
                bg=re.sub(r".*background:([^;]+).*", r"\1", pic.get("style", "")) if pic and "background" in pic.get("style", "") else "#d8d2c6",
                when=(when.find(string=True, recursive=False) or "").strip() if when else "",
                src=src.get_text(strip=True) if src else "", big="burst" in str(a)[:600] or "重大" in a.get_text())


def assign(stories, used):
    """記事の割り当て（ここだけ）：ページ全体で同じ記事を 2 回出さない（L7）。
    hero＝写真のある最初の 1 本、rail＝次の RAIL 本、grid＝12 の倍数（4・3・2 列のどれでも最後の段が満ちる）、残りは more。"""
    fresh = []
    for s in stories:
        k = (s["href"], norm(s["title"]))
        if not s["href"] or s["href"] in used["h"] or k[1] in used["t"]:
            continue
        used["h"].add(s["href"]); used["t"].add(k[1]); fresh.append(s)
    withp = [s for s in fresh if s["img"]]
    hero = [withp[0]] if withp else fresh[:1]
    rest = [s for s in fresh if s not in hero]
    rail, rest = rest[:RAIL], rest[RAIL:]
    n = len(rest) - len(rest) % 12 if len(rest) >= 12 else len(rest) - len(rest) % 6
    n = min(n, GRID) if n else 0
    return hero, rail, rest[:n], rest[n:]


def card(s, role):
    """カード 1 種類（見た目の違いは role と器の幅だけ）。リンクは 1 つ（L10）。写真が無ければ字だけ（L4）。"""
    e = html.escape
    pic = (f'<span class="pic" style="background:{e(s["bg"])}"><img src="{e(s["img"])}" alt="" loading="{"eager" if role != "grid" else "lazy"}" referrerpolicy="no-referrer" '
           f'onerror="this.remove()"></span>') if s["img"] else ""
    flag = '<b class="fl">重大</b>' if s["big"] and role == "hero" else ""
    return (f'<article class="cd {role}{"" if pic else " np"}"><a href="{e(s["href"])}" target="_blank" rel="noopener">{pic}'
            f'<span class="tx"><span class="mt">{flag}<time>{e(s["when"])}</time><i>{e(s["src"])}</i></span>'
            f'<h3>{e(s["title"])}</h3></span></a></article>')


def board(name, parts, nstories):
    """並べる器 1 種類：.bd（hero＋rail の上段、grid、もっと見る）。"""
    hero, rail, grid, more = parts
    top = "".join(card(s, "hero") for s in hero) + (f'<div class="rail">{"".join(card(s, "rail") for s in rail)}</div>' if rail else "")
    g = f'<div class="gr" data-n="{len(grid)}">{"".join(card(s, "grid") for s in grid)}</div>' if grid else ""
    m = (f'<details class="more"><summary>もっと見る（{len(more)}）</summary><div class="gr">{"".join(card(s, "grid") for s in more)}</div></details>'
         if more else "")
    return (f'<section class="bd"><header><h2>{html.escape(name)}</h2><small>{nstories} 本 → 画面に {len(hero)+len(rail)+len(grid)}'
            f'・もっと見る {len(more)}</small></header><div class="top">{top}</div>{g}{m}</section>')


CSS = """
:root{--ink:#1A1C22;--paper:#EDEBE6;--card:#FBF8F1;--gold:#FFD23F;--rose:#B8336A;--alert:#D7261E;--muted:rgba(26,28,34,.62);
--f:'Noto Sans JP',sans-serif;--m:'JetBrains Mono',monospace;--s:'Noto Serif JP',serif;--g:24px;--gi:8px;--r:0px;--sh:none;--bw:1px}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.65 var(--f)}
a{color:inherit;text-decoration:none}
.ctl{position:sticky;top:0;z-index:9;background:var(--ink);color:var(--card);padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ctl button{font:700 13px var(--f);border:2px solid var(--gold);background:none;color:var(--gold);padding:4px 12px;cursor:pointer}
.ctl button[aria-pressed=true]{background:var(--gold);color:var(--ink)}.ctl a{color:var(--gold);font-size:13px}
main{max-width:1240px;margin:0 auto;padding:24px 16px 80px;display:flex;flex-direction:column;gap:56px}
.bd>header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;border-bottom:var(--bw) solid var(--ink);margin-bottom:var(--g);padding-bottom:6px}
.bd h2{margin:0;font:900 26px/1.3 var(--f)}.bd header small{font:700 11px var(--m);color:var(--muted)}
.top{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:var(--g);margin-bottom:var(--g);align-items:start}
.rail{display:flex;flex-direction:column;gap:var(--gi)}
.gr{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--g)}
.gr[data-n="6"]{grid-template-columns:repeat(3,minmax(0,1fr))}
.cd a{display:flex;flex-direction:column;gap:8px;height:100%}
.pic{display:block;position:relative;overflow:hidden;aspect-ratio:3/2;border:var(--bw) solid var(--ink);box-shadow:var(--sh)}
.pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 30%}
.hero .pic{aspect-ratio:16/9}
.tx{display:flex;flex-direction:column;gap:4px;min-width:0}
.mt{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;font:700 11px var(--m);color:var(--muted)}.mt i{font-style:normal;min-width:0;overflow-wrap:anywhere}.mt{max-width:100%}
.fl{background:var(--alert);color:#fff;padding:0 8px;font:900 11px var(--f);transform:skewX(-8deg)}
h3{margin:0;font:700 14px/1.5 var(--f);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.hero h3{font:900 clamp(20px,2.4vw,28px)/1.35 var(--f);-webkit-line-clamp:4}
.rail .cd a{flex-direction:row;align-items:flex-start;gap:12px}.rail .pic{flex:0 0 38%;aspect-ratio:3/2}
.np .tx{border-left:4px solid var(--ink);padding:4px 0 4px 12px}.np.grid .tx{min-height:96px;justify-content:center}
.more{margin-top:var(--g)}.more summary{cursor:pointer;font:900 14px var(--f);padding:10px 0;border-top:var(--bw) solid var(--ink)}
.more .gr{margin-top:var(--g)}
.note{background:var(--card);border:2px solid var(--ink);padding:14px 18px;max-width:1240px;margin:24px auto 0}.note p{margin:4px 0}
/* 方向 A 新聞の紙面割り：細い罫・明朝の見出し・影なし・列の間に縦罫 */
[data-dir=news]{--bw:1px}[data-dir=news] h3,[data-dir=news] .bd h2{font-family:var(--s)}
[data-dir=news] .gr .cd+.cd{border-left:0}[data-dir=news] .gr{column-gap:var(--g)}
[data-dir=news] .hero .pic{aspect-ratio:3/2}
[data-dir=news] .gr .cd{padding-top:10px;border-top:2px solid var(--ink)}
/* 方向 B 雑誌の見開き：余白を多く・写真を大きく・罫なし・見出しは大きく軽く */
[data-dir=mag]{--g:36px;--gi:20px;--bw:0px}[data-dir=mag] .pic{border:0}[data-dir=mag] .bd h2{font:300 40px/1.2 var(--s);letter-spacing:.02em}
[data-dir=mag] .hero .pic{aspect-ratio:3/2}[data-dir=mag] h3{font-weight:500}[data-dir=mag] .hero h3{font:500 clamp(22px,3vw,34px)/1.3 var(--s)}
[data-dir=mag] .bd>header{border-bottom:0}[data-dir=mag] .gr .pic{aspect-ratio:4/3}
/* 方向 C P5 強め：太い枠・硬い影・傾けた見出し・札 */
[data-dir=p5]{--bw:3px;--sh:5px 5px 0 var(--ink)}[data-dir=p5] .bd h2{display:inline-block;background:var(--ink);color:var(--gold);padding:0 14px;transform:skewX(-8deg)}
[data-dir=p5] .bd>header{border-bottom:3px solid var(--ink)}[data-dir=p5] .cd{background:var(--card);border:3px solid var(--ink);box-shadow:var(--sh);padding:10px}
[data-dir=p5] .cd:hover{transform:translate(-2px,-2px);box-shadow:7px 7px 0 var(--ink)}[data-dir=p5] .pic{box-shadow:none}
@media (max-width:900px){.top{grid-template-columns:1fr}.gr,.gr[data-n="6"]{grid-template-columns:repeat(3,minmax(0,1fr))}.gr[data-n="12"]{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:600px){.gr,.gr[data-n="6"],.gr[data-n="12"]{grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--gi) 14px}.bd h2{font-size:22px}[data-dir=mag]{--g:20px}
.rail .pic{flex-basis:34%}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""
JS = "document.querySelectorAll('.ctl button').forEach(b=>b.onclick=()=>{document.body.dataset.dir=b.dataset.d;document.querySelectorAll('.ctl button').forEach(x=>x.setAttribute('aria-pressed',x===b))})"


def main():
    from bs4 import BeautifulSoup   # 見本づくりの手元だけで要る（CI の試験は assign だけ）
    s = BeautifulSoup(SRC.read_text(encoding="utf-8"), "lxml")
    used = {"h": set(), "t": set()}
    out, dup = [], 0
    for sid, name in PLACES:
        el = s.select_one("section.front") if sid == "front" else s.select_one("#picks") if sid == "picks" else s.select_one("#" + sid)
        if el is None:
            continue
        sel = ".pk" if sid == "picks" else "article.card"
        st = [story(a) for a in el.select(sel)]
        parts = assign(st, used)
        dup += len(st) - sum(map(len, parts))
        out.append(board(name, parts, len(st)))
    note = ('<div class="note"><p><b>審査待ち：記事の並べ方の作り直し（DESIGN G・L1〜L11）</b>　本物のデータ（本番 docs/home/ から）で、'
            '記事の割り当て 1 か所・カード 1 種類・並べる器 1 種類。同じ記事の二度出しは取り除いた数：<b>%d</b>。</p>'
            '<p>上の A / B / C で方向を切り替えて見比べてください（1400 / 768 / 390）。今の本番：'
            '<a href="../home/">店長のページ</a>。本番はまだ入れ替えていません。</p></div>' % dup)
    OUT.write_text(f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>並べ方の作り直し見本</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900&family=Noto+Serif+JP:wght@300;500;700&family=JetBrains+Mono:wght@700&display=swap">
<style>{CSS}</style></head><body data-dir="news">
<div class="ctl"><a href="index.html">← テストグラウンド</a><button data-d="news" aria-pressed="true">A 新聞の紙面割り</button>
<button data-d="mag" aria-pressed="false">B 雑誌の見開き</button><button data-d="p5" aria-pressed="false">C P5 強め</button></div>
{note}<main>{"".join(out)}</main><script>{JS}</script></body></html>''', encoding="utf-8")
    print("written", OUT, "dup removed", dup)


if __name__ == "__main__":
    main()
