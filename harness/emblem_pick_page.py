"""テストグラウンド docs/testground/emblem-pick.html を作る：小元素の「誰を出すか」前（名簿の順）と後（知られている点数）を並べる。
python harness/emblem_pick_page.py  （state/emblem_fame.json にあるものを使う。なければ scripts/emblem_fame.py を先に）"""
import html
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import emblem_fame as ef  # noqa: E402

BOARDS = [("BLEACH Mirrors High", "Bleach", False), ("チェーンソーマン", "Chainsaw Man", False), ("哈利波特剧集", "Harry Potter", True)]
TOP = 12


def tile(e, r, mark=""):
    sc = f'{r["score"]:.2f}'
    src = {"AniList": f'AniList お気に入り {r["fav"]:,}' if r.get("fav") is not None else "", "Wikipedia": f'Wikipedia 90 日 {r["wp"]:,}' if r.get("wp") is not None else ""}.get(r["src"], "取れていない")
    return (f'<figure class="t {mark}"><img src="../home/{html.escape(e["image"])}" alt="" loading="lazy">'
            f'<figcaption><b>{html.escape(e["subject"])}</b><small>点数 {sc}</small><small>{html.escape(src)}</small></figcaption></figure>')


def main():
    items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    items = items["items"] if isinstance(items, dict) else items
    cache = ef.load()
    out = []
    for name, work, live in BOARDS:
        it = next(i for i in items if i["name"] == name)
        em = [e for e in it["emblem"] if e.get("image", "").startswith("emblems/")]
        sc = {e["subject"]: ef.score(e["subject"], work, cache, live) for e in em}
        n = max(TOP, -(-len(em) // 5))
        now = em[:n]
        new = sorted(em, key=lambda e: -sc[e["subject"]]["score"])[:TOP]
        nowset, newset = {e["subject"] for e in now}, {e["subject"] for e in new}
        out.append(f'<section><h2>{html.escape(name)}<small>{len(em)} 枚のうち</small></h2>'
                   f'<h3><span class="tg old">いま</span>名簿の順の先頭 {len(now)} 枚（赤＝新しい選び方では出ない）</h3><div class="row">'
                   + "".join(tile(e, sc[e["subject"]], "" if e["subject"] in newset else "out") for e in now)
                   + f'</div><h3><span class="tg new">新しい</span>知られている点数の上位 {TOP} 枚（金＝いまは出ていない）</h3><div class="row">'
                   + "".join(tile(e, sc[e["subject"]], "" if e["subject"] in nowset else "in") for e in new) + '</div></section>')
    ef.save(cache)
    page = PAGE.replace("@@", "\n".join(out))
    (ROOT / "docs" / "testground" / "emblem-pick.html").write_text(page, encoding="utf-8")


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>小元素の選び方（見本）</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900&family=JetBrains+Mono:wght@500;700&display=swap">
<style>
:root{--ink:#1A1C22;--paper:#EDEBE6;--rose:#B8336A;--card:#FBF8F1;--gold:#FFD23F;--alert:#D7261E;--font-sans:'Noto Sans JP',sans-serif;--font-mono:'JetBrains Mono',monospace;--shadow:4px 4px 0 var(--ink);--skew:-8deg;--muted:rgba(26,28,34,.62)}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.7 var(--font-sans)}
header{background:var(--ink);color:var(--card);padding:24px 16px}header small{display:block;font:700 11px var(--font-mono);letter-spacing:.2em;color:var(--gold)}h1{margin:0;font:900 22px/1.3 var(--font-sans)}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px;display:flex;flex-direction:column;gap:24px}
.note,section{background:var(--card);padding:16px;box-shadow:var(--shadow)}.note ul{margin:6px 0 0;padding-left:1.2em}
h2{margin:0 0 8px;font:900 19px var(--font-sans)}h2 small{margin-left:8px;font:500 12px var(--font-mono);color:var(--muted)}
h3{margin:14px 0 8px;font:700 14px var(--font-sans)}
.tg{display:inline-block;margin-right:8px;padding:0 9px;transform:skewX(var(--skew));font:900 12px/1.7 var(--font-sans);color:#fff}.tg.old{background:var(--muted)}.tg.new{background:var(--rose)}
.row{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:10px}
.t{margin:0;border:2px solid var(--ink);background:#fff}.t img{display:block;width:100%;aspect-ratio:4/5;object-fit:contain;object-position:bottom;background:var(--paper)}
.t figcaption{padding:4px 6px;display:flex;flex-direction:column}.t b{font:700 12px/1.3 var(--font-sans)}.t small{font:500 10.5px/1.4 var(--font-mono);color:var(--muted)}
.t.out{border-color:var(--alert);box-shadow:3px 3px 0 var(--alert)}.t.in{border-color:var(--ink);box-shadow:3px 3px 0 var(--gold)}
</style></head><body>
<header><small>TESTGROUND</small><h1>小元素の選び方（見本）</h1></header>
<main>
<div class="note"><b>これは見本です（本番は変えていません）。</b>「いま」＝店長の版面の小元素のうち、いま版面の顔に出る先頭の枚数。「新しい」＝外の人気（AniList のお気に入り数・Wikipedia の直近 90 日の閲覧数）の点数が高い順の上位 12 枚。同じ画像で、選ぶ人だけを比べています。
<ul><li>OK なら、この点数で全部の版面（店長＋ライブラリ）の「誰を出すか」を決め直します。</li><li>まだ入れていないもの：公式サイトの胸像への差し替え・絵柄をそろえる（CLIP）・正解の見本集での数え。見本を見て方向が合っていれば順に入れます。</li><li>点数が取れない人（AniList にも Wikipedia にも名前がない）は 0 点＝顔には出ません（管理ページの一覧には残る）。</li></ul></div>
@@
</main></body></html>
"""

if __name__ == "__main__":
    main()
