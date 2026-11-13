"""描いた後に動かないか（審美基準 F5・E5）を数える。網なしで、手元の docs/ を本番の網址のまま開く。

usage: python harness/shift_check.py [--root docs] [--widths 390x844,412x915,1333x720,1440x900] [--json OUT]

開いて 2 秒待ったあと、上から下までゆっくりスクロール（1 歩 160px・90ms）。スマホの幅では 6 歩ごとに
URL 欄が隠れる・出る resize（高さだけ 56px 変わる）をまねる。全版面（section.sec）で歩くたびに測る：
  - cnt：帯が画面に入っている間に「今週」の位置（帯の中の上端）が 8px より動いた版面の数（題名の横 ↔ 下の行を行き来した）
  - band：見出しの帯の高さが 2px より変わった版面の数
  - sec：版面の下の縁が画面に入っている間に、版面の高さが 2px より変わった版面の数（下の版面が目の前で押される。sec_off は画面の外も含めた参考）
  - cls：スクロール中の layout shift の合計（hadRecentInput なし。URL 欄の出入りの瞬間の分は cls_rz、左の目次の中だけの動き〔読んでいる版面の段が開く〕は cls_nav に分ける）
写真は外の網に出ないので、どの網址も 16:9 の灰色の絵を返す（lazy の写真はスクロールで近づいてから届く）。
小元素（docs/home/emblems）と網页は手元の本物。字体（Google Fonts）は止める（CI と同じ代わりの字体）。
ux_check.py の「F5」もこれを呼ぶ。終わりのコード：上限（LIMITS）を超えたら 1。
"""
import argparse
import json
import mimetypes
import pathlib
import struct
import sys
import zlib

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import browser as hb  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://cxelegy.github.io/Wishlist/"
# 上限：直した後の数（2026-11-13）。どれか 1 つでも超えたら赤。「今週」は 1 枚でも行き来したら赤
LIMITS = {"cnt": 0, "band": 0, "sec": 0, "cls": 0.05}


def _png(w, h):
    raw = b"".join(b"\x00" + b"\x88\x88\x88" * w for _ in range(h))
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b"")


GRAY = _png(160, 90)
EMOJI = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><circle cx="18" cy="18" r="16" fill="#888"/></svg>'   # twemoji は 36×36

INIT = r"""
(() => { let sd = 7; Math.random = () => (sd = (sd * 16807) % 2147483647) / 2147483647; })();   // 小元素のランダムな 1 枚を前後で同じに
(() => { const M = window.__ls = {on: false, v: 0, n: 0, nav: 0, src: {}};
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) { if (!M.on || e.hadRecentInput) continue;
    const ns = (e.sources || []).map(s => s.node && (s.node.nodeType === 1 ? s.node : s.node.parentElement)).filter(Boolean);
    if (ns.length && ns.every(n => n.closest('.nav'))) { M.nav += e.value; continue; }   // 左の目次（読んでいる版面の段が開く・v6 の形）だけの動きは別に数える
    M.v += e.value; M.n++;
    (e.sources || []).forEach(s => { const n = s.node && s.node.nodeType === 1 ? s.node : s.node && s.node.parentElement;
      const k = n ? n.nodeName + '.' + String(n.className || '').split(' ')[0] + '@' + ((n.closest && n.closest('section[data-k]') || {}).dataset || {}).k : '?'; M.src[k] = (M.src[k] || 0) + e.value; }); } })
    .observe({type: 'layout-shift', buffered: false}); } catch (_) {} })();
"""
# 版面の高さは下の縁が画面に入っている間だけ数える（縦に長い版面の、画面の下の外で写真が届いて伸びるのは見えない）
MEASURE = r"""
() => [...document.querySelectorAll('section.sec')].map(s => { const b = s.querySelector(':scope > .band'); if (!b) return null;
  const c = b.querySelector('.cnt'), br = b.getBoundingClientRect(), cr = c && c.getBoundingClientRect();
  const sr = s.getBoundingClientRect(), H = innerHeight;
  return [s.dataset.k || s.id, Math.round(s.offsetHeight), Math.round(br.height), cr ? Math.round(cr.top - br.top) : null, sr.bottom > 0 && sr.bottom <= H, br.top < H && br.bottom > 0]; }).filter(Boolean)
"""


def route(root):
    def handle(r):
        u = r.request.url
        if u.startswith(BASE):
            p = u[len(BASE):].split("?")[0].split("#")[0]
            f = root / p
            if p.endswith("/") or not p:
                f = f / "index.html"
            if f.is_file():
                return r.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        if "/twemoji@" in u:
            return r.fulfill(status=200, body=EMOJI, content_type="image/svg+xml")
        if r.request.resource_type == "image":   # 遅らせない（sync の route で待つと全部の読み込みが止まる）。lazy の写真はスクロールで近づいてから届く
            return r.fulfill(status=200, body=GRAY, content_type="image/png")
        return r.abort()
    return handle


def run(root, w, h, page_path="home/"):
    phone = w <= 760
    with sync_playwright() as p:
        b = hb.launch(p)   # 点検のブラウザは共通の 1 か所から（free-tier.md：Supabase の写真を取りに行かない）
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=phone, has_touch=phone, device_scale_factor=1)
        ctx.route("**/*", route(root))
        pg = ctx.new_page()
        pg.add_init_script(INIT)
        pg.goto(BASE + page_path, wait_until="load", timeout=60000)
        pg.wait_for_timeout(2000)
        seen = {}   # 版面 → [高さ, 帯, 今週, 高さ（見えていない間も）] の [最小, 最大]。見えている間（版面・帯が画面に入っている）の変化だけを「動いた」と数える
        def take():
            for k, sh, bh, ct, sv, bv in pg.evaluate(MEASURE):
                s = seen.setdefault(k, [[None, None] for _ in range(4)])
                for i, (v, vis) in enumerate(((sh, sv), (bh, bv), (ct, bv), (sh, True))):
                    if v is None or not vis:
                        continue
                    lo, hi = s[i]
                    s[i] = [v if lo is None else min(lo, v), v if hi is None else max(hi, v)]
        take()
        pg.evaluate("window.__ls.on = true")
        y, n, short, rz = 0, 0, False, 0.0
        while True:
            pg.mouse.wheel(0, 160) if not phone else pg.evaluate("scrollBy(0, 160)")
            pg.wait_for_timeout(90)
            n += 1
            if phone and n % 6 == 0:   # URL 欄が隠れる・出る：高さだけ 56px
                short = not short
                v0 = pg.evaluate("window.__ls.v")
                pg.set_viewport_size({"width": w, "height": h - 56 if short else h})
                pg.wait_for_timeout(120)
                rz += pg.evaluate("window.__ls.v") - v0   # URL 欄の出入りそのもので動いた分（下に固定した部品が画面と一緒に動く）は別に数える
            take()
            ny = pg.evaluate("scrollY")
            if ny <= y and n > 3:
                break
            y = ny
        pg.wait_for_timeout(600)
        take()
        ls = pg.evaluate("window.__ls")
        b.close()
    moved = {"cnt": [], "band": [], "sec": [], "sec_off": []}
    d = lambda r: (r[1] - r[0]) if r[0] is not None else 0
    for k, (sh, bh, ct, sa) in seen.items():
        if d(sh) > 2:
            moved["sec"].append((k, d(sh)))
        if d(bh) > 2:
            moved["band"].append((k, d(bh)))
        if d(ct) > 8:
            moved["cnt"].append((k, d(ct)))
        if d(sa) > 2:
            moved["sec_off"].append((k, d(sa)))
    top = sorted(ls["src"].items(), key=lambda x: -x[1])[:5]
    return {"size": f"{w}x{h}", "boards": len(seen), "cnt": len(moved["cnt"]), "band": len(moved["band"]), "sec": len(moved["sec"]),
            "cls": round(ls["v"] - rz, 4), "cls_rz": round(rz, 4), "cls_nav": round(ls["nav"], 4), "sec_off": len(moved["sec_off"]), "moved": moved, "cls_src": [(k, round(v, 4)) for k, v in top]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "docs"))
    ap.add_argument("--widths", default="390x844,412x915,1333x720,1440x900")
    ap.add_argument("--json")
    a = ap.parse_args()
    out, bad = [], False
    for s in a.widths.split(","):
        w, h = map(int, s.split("x"))
        r = run(pathlib.Path(a.root), w, h)
        out.append(r)
        over = [k for k, lim in LIMITS.items() if r[k] > lim]
        bad |= bool(over)
        print(f"{'✗' if over else '✓'} {r['size']}: 版面 {r['boards']}・今週が動いた {r['cnt']}・帯の高さ {r['band']}・版面の高さ {r['sec']}（画面の外も {r['sec_off']}）・shift {r['cls']}（URL 欄 {r['cls_rz']}・目次 {r['cls_nav']}）"
              + (f"  ← {','.join(over)}" if over else ""), flush=True)
        for k in ("cnt", "band", "sec"):
            if r["moved"][k]:
                print(f"    {k}: " + ", ".join(f"{n}(±{d})" for n, d in r["moved"][k][:8]))
        if r["cls_src"]:
            print("    shift の出どころ: " + ", ".join(f"{n} {v}" for n, v in r["cls_src"]))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
