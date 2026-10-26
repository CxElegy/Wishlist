"""テストグラウンド docs/testground/emblem-pick.html を作る：小元素の「誰を出すか」前（名簿の順）と後（知られている点数）を並べる。
python harness/emblem_pick_page.py  （state/emblem_fame.json にあるものを使う。なければ scripts/emblem_fame.py を先に）"""
import hashlib
import html
import pathlib
import re
import sys

import yaml
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import emblem  # noqa: E402
import emblem_fame as ef  # noqa: E402

BOARDS = [("BLEACH Mirrors High", "Bleach", False), ("チェーンソーマン", "Chainsaw Man", False), ("哈利波特剧集", "Harry Potter", True)]
TOP = 12
FACE_W, EYE_Y, RATIO = 0.42, 0.36, 1.25   # 顔の幅 = 枠の 4 割ちょっと・目の線 = 枠の上から 36%・枠は 4:5（元の絵が半身までなので、顔を小さくしすぎると下が空く）
OUT = ROOT / "docs" / "testground" / "emblem-pick"


def bust(src, key):
    """顔の大きさと目の高さをそろえた胸像に切る（見本）。→ (出力のファイル名, 注意の文字)。顔が見つからなければ (None, 理由)。"""
    img = Image.open(ROOT / "docs" / "home" / src).convert("RGBA")
    img = img.crop(img.getchannel("A").getbbox())
    f = emblem.face_box(img)
    if not f:
        return None, "顔が見つからない＝人物にしない（物・記号の別枠）"
    fx, fy, fw, fh = f
    note = "顔だけのアップ（肩がほぼない）" if fh / img.size[1] > 0.6 else ""
    w = fw / FACE_W
    h = w * RATIO
    left, top = fx + fw / 2 - w / 2, fy + 0.42 * fh - EYE_Y * h
    h = min(h, img.size[1] - top)   # 元の絵に体がなければ、そこまで（足して空けない）
    canvas = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    canvas.paste(img, (int(-left), int(-top)))
    OUT.mkdir(exist_ok=True)
    canvas.resize((240, int(240 * h / w))).save(OUT / f"{key}.webp", quality=88)
    return f"emblem-pick/{key}.webp", note


def tile(e, r, ctx, mark="", norm=False):
    mention, roster, polls = ctx
    why = [f'外の点数 {r["score"]:.2f}']
    pr = polls.get(ef._norm(re.sub(r"\s*[（(].*[）)]", "", e["subject"])))
    if pr:
        why.append(f"公式人気投票 {pr} 位")
    if e["subject"] in roster:
        why.append("ゲームで使える")
    if mention.get(e["subject"]):
        why.append(f'記事に {mention[e["subject"]]} 回')
    src, warn = e["image"], ""
    if norm:
        k = hashlib.md5(e["image"].encode()).hexdigest()[:10]
        src, warn = bust(e["image"], k)
    img = f'<img src="{"../home/" + html.escape(e["image"]) if not src or not norm else html.escape(src)}" alt="" loading="lazy">'
    cap = f'<small>合計 {r["total"]:.2f}</small><small>{html.escape(" ＋ ".join(why))}</small>' if norm else f'<small>点数 {r["score"]:.2f}</small>'
    if warn:
        cap += f'<small class="w">{html.escape(warn)}</small>'
    return f'<figure class="t {mark}{" nf" if norm and not src else ""}">{img}<figcaption><b>{html.escape(e["subject"])}</b>{cap}</figcaption></figure>'


def main():
    items = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    items = items["items"] if isinstance(items, dict) else items
    cache = ef.load()
    out = []
    for name, work, live in BOARDS:
        it = next(i for i in items if i["name"] == name)
        em = [e for e in it["emblem"] if e.get("image", "").startswith("emblems/")]
        ctx = ef.context(it, [e["subject"] for e in em])
        rows = dict(ef.rank([e["subject"] for e in em], work, cache, live, ctx))
        n = max(TOP, -(-len(em) // 5))
        now = em[:n]
        new = sorted(em, key=lambda e: -rows[e["subject"]]["total"])[:TOP]
        nowset, newset = {e["subject"] for e in now}, {e["subject"] for e in new}
        out.append(f'<section><h2>{html.escape(name)}<small>{len(em)} 枚のうち</small></h2>'
                   f'<h3><span class="tg old">いま</span>名簿の順の先頭 {len(now)} 枚・元の絵のまま（赤＝新しい選び方では出ない）</h3><div class="row">'
                   + "".join(tile(e, rows[e["subject"]], ctx, "" if e["subject"] in newset else "out") for e in now)
                   + f'</div><h3><span class="tg new">新しい</span>合計点の上位 {TOP} 枚・顔の大きさと目の高さをそろえた胸像（金＝いまは出ていない）</h3><div class="row">'
                   + "".join(tile(e, rows[e["subject"]], ctx, "" if e["subject"] in nowset else "in", True) for e in new) + '</div></section>')
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
.t.nf img{opacity:.35}.t .w{color:var(--alert)}.t.out{border-color:var(--alert);box-shadow:3px 3px 0 var(--alert)}.t.in{border-color:var(--ink);box-shadow:3px 3px 0 var(--gold)}
</style></head><body>
<header><small>TESTGROUND</small><h1>小元素の選び方（見本）</h1></header>
<main>
<div class="note"><b>これは見本です（本番は変えていません）。</b>前の見本へのあなたの答え（案 2）を入れて作り直しました。「新しい」の合計点 ＝ 外の点数（AniList のお気に入り数・Wikipedia の直近 90 日の閲覧数）＋ 公式の人気投票の順位 ＋ ゲームで使えるキャラ ＋ その版面の記事に出た回数。同時に、人の大きさをそろえた形（顔の幅＝枠の 4 割・目の線＝枠の上から 36%・4:5）も見せています。
<ul><li>公式の人気投票：Fandom の「Popularity polls」ページの最新の回（BLEACH は 49 位まで）。1 位 +1.2、30 位で 0。ない版面は 0。</li><li>ゲームで使える：見出しに roster・lineup・参戦などがある記事の本文に名前が出た人 +1.5。記事に出た回数：直近 30 日の見出し・要約に名前（+0.5×log10(1+回数)、上限 1.0）。</li><li>顔が見つからない絵は「人物にしない」と書いて元の大きさのまま出しています。顔だけのアップ（顔が高さの 5 割超）は注意を付けています。まだ入れていないもの：公式サイトの胸像への差し替え・絵柄をそろえる（CLIP）・体の穴や吹き出しの残りの点検。</li></ul>
<b>見てほしいこと：</b>A 上位 12 人はこれでよいか（BLEACH なら一護・ルキア・恋次などが先に来て、脇役が消えているか）　B 胸像の切り方（顔の大きさ・目の高さ）はこの形でよいか。OK なら全部の版面を決め直します。</div>
@@
</main></body></html>
"""

if __name__ == "__main__":
    main()
