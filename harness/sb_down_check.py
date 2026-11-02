"""Supabase が止まった（402・通信失敗）状態でも公開のページが崩れないかの点検（2026-11-03，用户定的：11/5 以降の 402 に備える）。

  python harness/sb_down_check.py [--base http://127.0.0.1:8000/] [--mode abort|402] [--shots DIR]

*.supabase.co の /rest・/auth・/functions を page.route で止める（abort か 402 を返す）。本番の Supabase には 1 件も届かない
（負荷を足さない・free-tier.md）。ページごと・幅（1400／390）ごとに数える：
  ✗ 横スクロールが出る ／ ✗ 案内の 1 行（.wl-sbnote）が 1 つでない ／ ✗ Supabase への呼び出しが 8 回を超える（呼び直している）
  ✗ ページの本文（main か body）が空 ／ ✗ 点検のあと ボタンを押しても網に出る（休止中は網に出ない）
本番に向ける回は timeout 付きで 1 回だけ。"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser import launch  # noqa: E402

SB = re.compile(r"https://[a-z0-9]+\.supabase\.co/(rest|auth|functions)/")
PAGES = ["", "home/index.html", "home/settings.html", "home/wishlist.html", "home/admin.html", "home/heat.html", "home/themes.html",
         "home/terms.html", "home/me.html", "home/admin-members.html", "home/admin-boards.html", "home/admin-now.html",
         "testground/face-size.html", "testground/layout-v2.html", "testground/wishes.html", "testground/product-head.html"]
MAX_CALLS = 8


def check(pw, base, mode, shots):
    bad = []
    b = launch(pw)
    for page_ in PAGES:
        for w, h in ((1400, 900), (390, 844)):
            ctx = b.new_context(viewport={"width": w, "height": h})
            hits = []

            def block(route, _req=None):
                hits.append(route.request.url)
                if mode == "402":
                    return route.fulfill(status=402, content_type="application/json", body='{"message":"Fair Use"}')
                return route.abort()

            ctx.route(SB, block)
            p = ctx.new_page()
            p.goto(base + page_, wait_until="domcontentloaded", timeout=30000)
            p.wait_for_timeout(3500)
            before = len(hits)
            for sel in ("[data-vote]", ".wl-auth > button"):   # 押しても網に出ない（休止中）
                el = p.query_selector(sel)
                if el:
                    try:
                        el.click(timeout=1500)
                    except Exception:  # noqa: BLE001
                        pass
            p.wait_for_timeout(800)
            r = p.evaluate("""()=>({ov:document.documentElement.scrollWidth-innerWidth, note:document.querySelectorAll('.wl-sbnote').length,
                 down:document.documentElement.dataset.sb||'', text:((document.querySelector('main')||document.body).innerText||'').trim().length,
                 err:Array.from(document.querySelectorAll('.err,.error,[role=alert]')).filter(e=>e.offsetParent).length})""")
            tag = f"{page_ or '入口'} {w}"
            if r["ov"] > 1:
                bad.append(f"✗ {tag}: 横スクロール {r['ov']}px")
            if r["note"] != 1 and hits:
                bad.append(f"✗ {tag}: 案内の 1 行が {r['note']} 個（Supabase 呼び出し {len(hits)} 回あったのに）")
            if len(hits) > MAX_CALLS:
                bad.append(f"✗ {tag}: Supabase を {len(hits)} 回呼んだ（呼び直し。上限 {MAX_CALLS}）")
            if len(hits) > before:
                bad.append(f"✗ {tag}: 休止中なのに押したら網に出た（+{len(hits) - before}）")
            if r["err"]:
                bad.append(f"✗ {tag}: エラーの箱が {r['err']} 個（休止中は案内の 1 行だけ）")
            if r["text"] < 50 and not page_.endswith("me.html"):   # me.html は読み込み中の殻（字は「読み込み中…」だけ）
                bad.append(f"✗ {tag}: 本文が空")
            print(f"{tag:28s} 呼び出し {len(hits):2d} · 案内 {r['note']} · 休止 {r['down'] or '-'} · 余り {r['ov']}px")
            if shots:
                pathlib.Path(shots).mkdir(parents=True, exist_ok=True)
                p.screenshot(path=str(pathlib.Path(shots) / f"{(page_ or 'entry').replace('/', '_')}_{w}_{mode}.png"))
            ctx.close()
    b.close()
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://cxelegy.github.io/Wishlist/")
    ap.add_argument("--mode", default="abort", choices=["abort", "402"])
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        bad = check(pw, a.base if a.base.endswith("/") else a.base + "/", a.mode, a.shots)
    print("\n".join(bad) or "全部 OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
