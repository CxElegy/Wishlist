"""テストグラウンド docs/testground/emblem-pick-2.html：作り直した規則 × あなたの ○×− の一致率の表と、同じ 3 版面で規則が選ぶ絵。
python harness/emblem_pick_rules_page.py"""
import hashlib
import html
import io
import pathlib
import sys

import yaml
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emblem_pick_rules as R  # noqa: E402

ROOT = R.ROOT
OUT = ROOT / "docs" / "testground" / "emblem-pick-2"
BOARDS = ["BLEACH Mirrors High", "チェーンソーマン", "哈利波特剧集"]
MARK = {"o": "○", "x": "×", "-": "−"}


def thumb(img, name, w=120):
    img = img.copy()
    img.thumbnail((w, int(w * 1.25)))
    OUT.mkdir(exist_ok=True)
    img.save(OUT / f"{name}.webp", quality=82)
    return f"emblem-pick-2/{name}.webp"


def label_rows():
    rows, sm = R.evaluate()
    out = []
    for stage in dict.fromkeys(r[0] for r in rows):
        trs = []
        for st, board, s, k, v, why in (r for r in rows if r[0] == stage):
            key = hashlib.md5(f"{st}{board}{s}".encode()).hexdigest()[:10]
            ok = k == v
            trs.append(f'<tr class="{"" if ok else "bad"}"><td>{html.escape(board[:8])}</td><td><b>{html.escape(s)}</b></td>'
                       f'<td class="m">{MARK[k]}</td><td class="m">{MARK[v]}</td><td>{"一致" if ok else "違う"}</td><td>{html.escape(why)}</td></tr>')
        s = sm[stage]
        out.append(f'<h3>{html.escape(stage)}：{s["same"]} / {s["n"]} 一致</h3>'
                   f'<p class="sum">× を「出す」と判定：<b>{s["x_picked"]} / {s["x_n"]}</b>（目標 0）　○ を「出す」と判定：<b>{s["o_picked"]} / {s["o_n"]}</b>（目標は全部）</p>'
                   '<details><summary>1 枚ずつの表（印・規則・理由）</summary><div class="tw"><table><tr><th>版面</th><th>名前</th><th>あなたの印</th><th>規則</th><th></th><th>理由</th></tr>'
                   + "".join(trs) + "</table></div></details>")
    return "".join(out), sm


def board_picks(items):
    out = []
    for name in BOARDS:
        it = next(i for i in items if i["name"] == name)
        em = [e for e in it["emblem"] if e.get("image", "").startswith("emblems/") and e["image"] != ""]
        picks, backs, nones = [], [], []
        for e in em:
            try:
                img = Image.open(ROOT / "docs" / "home" / e["image"])
            except OSError:
                continue
            kind, why, pic = R.decide(img)
            (picks if kind in ("bust", "orig") else backs if kind == "back" else nones).append((e["subject"], kind, why, pic))
        tiles = ""
        for s, kind, why, pic in picks[:18]:
            src = thumb(pic, hashlib.md5(f"{name}{s}".encode()).hexdigest()[:10], 150)
            tiles += (f'<figure class="t{" orig" if kind == "orig" else ""}"><img src="{src}" alt="" loading="lazy"><figcaption><b>{html.escape(s)}</b>'
                      f'<small>{"元の絵" if kind == "orig" else "胸像"}</small></figcaption></figure>')
        rej = "".join(f'<li><b>{html.escape(s)}</b>：{html.escape(why)}</li>' for s, _, why, _ in nones[:8])
        out.append(f'<section><h2>{html.escape(name)}<small>いまの版面の {len(em)} 枚 → 出す {len(picks)}・後ろ {len(backs)}・出さない {len(nones)}</small></h2>'
                   f'<div class="row">{tiles}</div><details><summary>出さない {len(nones)} 枚（理由つき・先頭 8）</summary><ul>{rej}</ul></details></section>')
    return "".join(out)


def main():
    items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    items = items["items"] if isinstance(items, dict) else items
    labels_html, sm = label_rows()
    page = PAGE.replace("@@LABELS", labels_html).replace("@@BOARDS", board_picks(items))
    (ROOT / "docs" / "testground" / "emblem-pick-2.html").write_text(page, encoding="utf-8")


PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>小元素の選び方 作り直し（見本）</title><meta name="robots" content="noindex">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900&family=JetBrains+Mono:wght@500;700&display=swap">
<style>
:root{--ink:#1A1C22;--paper:#EDEBE6;--rose:#B8336A;--card:#FBF8F1;--gold:#FFD23F;--alert:#D7261E;--font-sans:'Noto Sans JP',sans-serif;--font-mono:'JetBrains Mono',monospace;--shadow:4px 4px 0 var(--ink);--skew:-8deg;--muted:rgba(26,28,34,.62)}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.7 var(--font-sans)}
header{background:var(--ink);color:var(--card);padding:24px 16px}header small{display:block;font:700 11px var(--font-mono);letter-spacing:.2em;color:var(--gold)}h1{margin:0;font:900 22px/1.3 var(--font-sans)}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px;display:flex;flex-direction:column;gap:24px}
.note,section{background:var(--card);padding:16px;box-shadow:var(--shadow)}.note ul{margin:6px 0 0;padding-left:1.2em}
h2{margin:0 0 8px;font:900 19px var(--font-sans)}h2 small{display:block;font:500 12px var(--font-mono);color:var(--muted)}
h3{margin:16px 0 4px;font:900 15px var(--font-sans)}.sum{margin:0 0 6px}
.row{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:10px}
.t{margin:0;border:2px solid var(--ink);background:#fff}.t img{display:block;width:100%;aspect-ratio:4/5;object-fit:contain;object-position:bottom;background:var(--paper)}
.t.orig{box-shadow:3px 3px 0 var(--gold)}.t figcaption{padding:4px 6px;display:flex;flex-direction:column}.t b{font:700 12px/1.3 var(--font-sans)}.t small{font:500 10.5px/1.4 var(--font-mono);color:var(--muted)}
.tw{overflow-x:auto}table{border-collapse:collapse;font-size:12.5px;min-width:640px}th,td{border-bottom:1px solid rgba(26,28,34,.15);padding:3px 8px;text-align:left}.m{font:900 15px var(--font-mono);text-align:center}tr.bad{background:#FFE9E6}
details{margin-top:8px}summary{cursor:pointer;font-weight:700}
.q{border-left:6px solid var(--alert)}code{font:700 12px var(--font-mono)}
</style></head><body>
<header><small>TESTGROUND</small><h1>小元素の選び方 作り直し（見本）</h1></header>
<main>
<div class="note"><b>これは見本です（本番は変えていません）。</b>あなたが 2026-10-30 に付けた ○×−（見本 36 枚＋BLEACH のいま 18 枚）を正解にして、「どの絵をどう切るか」の規則を作り直しました。
<ul><li>規則は測れる数だけ：①顔のアップ（顔の下の肩と胸が顔の高さの 0.7 倍未満・頭の上の余りが顔の高さ未満）＝ × ②胸像に切ると頭の上が枠で切れる＝ × ③短い辺 150px 未満＝ × ④顔が見つからない絵は −（使えるが後ろ）。</li>
<li>胸像がだめでも元の絵が良ければ元の絵を出す（恋次：いま ○・新しい ×）。人気の順位は使わない（印と関係が薄かった）。</li>
<li>数字は印に合わせて決めたので、同じ印への一致は甘く出ます。本当の確かめは下の「同じ 3 版面で規則が選ぶ絵」に ○×− を付け直してもらうこと。</li></ul></div>
<section><h2>① あなたの印との一致率<small>絵は印を付けた版（2026-10-26）のもの。今の版面とは絵が違う</small></h2>@@LABELS</section>
<div class="note q"><b>② 聞きたいこと（規則で分けられなかった所）</b>
<ul><li><b>顔が見つからない ○ が 5 枚</b>（Gun Devil・Peeves・Kon・Byakuya・Sado）は規則が − にしてしまう：人でない（悪魔・妖精・マスコット）か公式の立ち絵。測るだけでは × の Power・Mysterious Man・George と見分けがつきません。
案 A「人でない・公式の立ち絵」の印を取る（Fandom の種族・出どころから。良い点：○ が全部出る／困る点：出どころの記録が要る）／案 B そのまま − で後ろに置く（良い点：何も足さない／困る点：Gun Devil のような版面の顔が出ない）。おすすめ A。</li>
<li>× を出してしまうのは 1 枚（Ikkaku：色が薄く切り抜きの縁が欠けた絵）。これは「切り抜きの縁の欠け」を測る別の規則が要ります（次の段）。</li></ul></div>
<h2 style="margin:0">③ 同じ 3 版面で、規則が選ぶ絵（いまの版面の絵）<small>金の影＝元の絵のまま（胸像だと悪くなるので）。○×− を付け直してください</small></h2>
@@BOARDS
</main></body></html>
"""

if __name__ == "__main__":
    main()
