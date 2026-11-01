"""testground/face-size.html：人物の小元素の顔の大きさ（全身・胸像で基準を分ける）の見本（本物の絵・審査待ち）。
items.yaml の小元素を、型ごとに 3 案の「顔の高さ px」で並べる。本番は替えない。型は emblem_face.face_class。"""
import html
import yaml
from pathlib import Path
import emblem_face as ef

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/testground/face-size.html"
# 案ごとの「顔の高さ px」（1400px 幅）。胸像は今のまま 50px（枠 156px の 32%）
OPTIONS = {"A": {"bust": 50, "cut": 30, "full": 14, "big": 32}, "B": {"bust": 50, "cut": 36, "full": 18, "big": 36},
           "C": {"bust": 50, "cut": 26, "full": 12, "big": 28}}
HMIN, HMAX = 56, 200   # 絵の高さの下限（これより小さいと何か分からない）・上限（枠 156px を超えて飛び出す限度）
PER = 8


def people():
    d = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))
    out = {k: [] for k in ef.CLASSES}
    for it in d["items"] if isinstance(d, dict) else d:
        em = it.get("emblem") or it.get("emblems") or []
        em = em.get("items") or [] if isinstance(em, dict) else em
        for x in em:
            f, b = x.get("face"), x.get("body")
            if not (isinstance(x, dict) and f and f[0] and (x.get("image") or "").startswith("emblems/")) or x.get("shape") in ("logo", "icon", "badge"):
                continue
            b = b if b and len(b) == 5 else None
            m = ef.fit(f)[0]
            if b or m:
                out[ef.face_class(b, f[0])].append(dict(name=it["name"], img=x["image"], fs=f[0], ar=f[4] / f[5], m=m))
    return {k: sorted(v, key=lambda r: r["fs"])[::max(1, len(v) // PER)][:PER] for k, v in out.items()}


def cell(r, cls, target):
    if cls == "bust":
        h = ef.EMB_H * r["m"]
        px = ef.EMB_H * r["fs"] * r["m"]
    else:
        h = min(max(target / r["fs"], HMIN), HMAX)
        px = r["fs"] * h
    bad = abs(px - target) > target * 0.1
    return (f'<figure class="{"bad" if bad else ""}"><div class="fr"><img src="../home/{html.escape(r["img"])}" alt="" '
            f'style="height:{h:.0f}px"></div><figcaption>{html.escape(r["name"][:14])}<br>顔 {px:.0f}px{"（届かない）" if bad else ""}</figcaption></figure>')


def build():
    pe = people()
    s = ["""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人物の顔の大きさ・全身と胸像</title>
<style>:root{--bg:#f4efe6;--fg:#1a1a1a;--ok:#2a7;--no:#c33}@media(prefers-color-scheme:dark){:root{--bg:#1b1b1d;--fg:#eee}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:700 14px/1.6 system-ui,sans-serif}h1{font-size:20px}h2{font-size:17px;margin:28px 0 4px}h3{font-size:14px;margin:14px 0 4px}
.row{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;padding:8px;border-bottom:2px dashed color-mix(in srgb,var(--fg) 30%,transparent)}
figure{margin:0;text-align:center;font-size:11px}.fr{height:260px;display:flex;align-items:flex-end}.fr img{display:block;width:auto}.bad{color:var(--no)}p{max-width:60em}</style>
<h1>人物の小元素：顔の大きさのそろえ方（審査待ち）</h1>
<p>人物は表示した顔の高さ(px)を同じ型の中でそろえます（最大÷最小 1.2 以内が目標）。顔以外の体の大きさは差があってよい。型は 4 つ：胸像・上半身に切った立ち絵・全身（等身）・全身（頭の大きいキャラ）。下の 3 案は型ごとの顔の px だけが違います。赤い字は、その案では絵の高さが 56〜200px に入らず届かないもの（候補を替える対象）。</p>"""]
    for k, o in OPTIONS.items():
        s.append(f"<h2>案 {k}：" + "・".join(f"{ef.CLASSES[c]} {o[c]}px" for c in o) + "</h2>")
        for c in ef.CLASSES:
            rows = pe.get(c) or []
            bad = sum(abs(ef.EMB_H * r["fs"] * r["m"] - o[c]) > o[c] * 0.1 if c == "bust" else abs(r["fs"] * min(max(o[c] / r["fs"], HMIN), HMAX) - o[c]) > o[c] * 0.1 for r in rows)
            s.append(f"<h3>{ef.CLASSES[c]}（見本 {len(rows)} 枚・うち届かない {bad}）</h3><div class=row>" + "".join(cell(r, c, o[c]) for r in rows) + "</div>")
    OUT.write_text("\n".join(s), encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print(build())
