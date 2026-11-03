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
# 戻る点検の対象：Supabase を読み込みで呼ぶ本人のページ全種（一覧・設定・愿望清单・管理）。入力欄のある設定・愿望清单では入力中に読み直さないかも見る
RECOVER_PAGES = ["home/index.html", "home/settings.html", "home/wishlist.html", "home/admin.html"]
FOCUS_PAGES = ("home/settings.html", "home/wishlist.html")


def settle(p, hits, limit=12000):
    """読み込みが落ち着くまで待つ（2026-11-03：me.html は殻から ./ へ飛ぶので、固定 3.5 秒だと飛んだ先の読み込みの呼び出しが
    「押したあと」に数えられて ✗ が出たり出なかったりした）。呼び出しの数と網址が 1.5 秒変わらない間を待つ（上限 limit ms）。"""
    last, quiet, t = None, 0, 0
    while t < limit and quiet < 1500:
        p.wait_for_timeout(250)
        t += 250
        cur = (len(hits), p.url)
        quiet = quiet + 250 if cur == last else 0
        last = cur
    if hits:   # 呼び出しがあれば休止中になるまで少し待つ（先頭の呼び出しが返って印が付く）
        try:
            p.wait_for_function("()=>document.documentElement.dataset.sb==='down'", timeout=2000)
        except Exception:  # noqa: BLE001
            pass


def check(pw, base, mode, shots):
    bad = []
    b = launch(pw)
    for page_ in PAGES:
        for w, h in ((1400, 900), (390, 844)):
            ctx = b.new_context(viewport={"width": w, "height": h})
            hits = []
            probed = False

            def block(route, _req=None):
                hits.append(route.request.url)
                if mode == "402":
                    return route.fulfill(status=402, content_type="application/json", body='{"message":"Fair Use"}')
                return route.abort()

            ctx.route(SB, block)
            p = ctx.new_page()
            p.goto(base + page_, wait_until="domcontentloaded", timeout=30000)
            settle(p, hits)
            if not hits:   # 読み込みで Supabase を呼ばないページ：1 回だけ呼んで（止めてある）案内の出方を実際に見る
                p.evaluate("()=>fetch('https://probe.supabase.co/rest/v1/rpc/x').catch(()=>0)")
                probed = True
                try:
                    p.wait_for_function("()=>document.documentElement.dataset.sb==='down'", timeout=2000)
                except Exception:  # noqa: BLE001
                    pass
                hits.clear()
            elif not p.evaluate("()=>document.documentElement.dataset.sb==='down'"):
                bad.append(f"✗ {page_ or '入口'} {w}: 呼んだのに休止中にならない")
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
            if r["note"] != 1 and (hits or probed):   # 呼ばないページも 1 回呼んだので（probed）案内が 1 つ出るはず
                bad.append(f"✗ {tag}: 案内の 1 行が {r['note']} 個（Supabase 呼び出し {len(hits)} 回・点検の呼び出し {int(probed)}）")
            if probed and r["down"] != "down":
                bad.append(f"✗ {tag}: 点検の呼び出しのあと休止中（dataset.sb）にならない")
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


def recover(pw, base):
    """制限が終わったら自動で元に戻るか（2026-11-03）：402 で休止 → 応答を 200 に切り替え → 時計を 11 分進めて触る →
    案内が消え・休止の印が外れ・（読み直しのあと）呼び出しが通る。まだ 402 の間は 10 分待って同じ網に 1 回だけ。"""
    bad = []
    b = launch(pw)
    for page_ in RECOVER_PAGES:
        for w, h in ((1400, 900), (390, 844)):
            ctx = b.new_context(viewport={"width": w, "height": h})
            st = {"code": 402, "n": 0}

            def route(r, _req=None):
                st["n"] += 1
                if st["code"] == 402:
                    return r.fulfill(status=402, content_type="application/json", body='{"message":"Fair Use"}')
                return r.fulfill(status=200, content_type="application/json", body="[]")

            ctx.route(SB, route)
            p = ctx.new_page()
            p.clock.install()
            p.goto(base + page_, wait_until="domcontentloaded", timeout=30000)
            settle(p, [1] * st["n"])
            tag = f"{page_} {w}"
            if p.evaluate("()=>document.documentElement.dataset.sb") != "down":
                bad.append(f"✗ {tag}: 402 で休止にならない（この点検の前提）")
            n0 = st["n"]
            p.clock.fast_forward(5 * 60000)
            p.mouse.wheel(0, 50)
            p.wait_for_timeout(500)
            if st["n"] != n0:
                bad.append(f"✗ {tag}: 休止 5 分で網に出た（10 分は待つ）")
            p.clock.fast_forward(6 * 60000)
            p.mouse.wheel(0, 50)   # まだ 402：試すのは 1 回だけ
            p.wait_for_timeout(500)
            if st["n"] != n0 + 1 or p.evaluate("()=>document.querySelectorAll('.wl-sbnote').length") != 1:
                bad.append(f"✗ {tag}: 11 分後の試しが 1 回でない／案内が消えた（網 +{st['n'] - n0}）")
            st["code"] = 200
            p.clock.fast_forward(11 * 60000)
            focused = p.evaluate("()=>{var i=[].slice.call(document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]),textarea')).find(function(e){return e.offsetParent;});if(i){i.focus();window.__keep=1;}return !!i&&document.activeElement===i}") if page_ in FOCUS_PAGES else False
            p.mouse.wheel(0, 50)
            try:
                p.wait_for_function("()=>!document.documentElement.dataset.sb&&!document.querySelector('.wl-sbnote')", timeout=5000)
            except Exception:  # noqa: BLE001
                bad.append(f"✗ {tag}: 402 が終わっても案内が消えない")
            p.wait_for_timeout(1500)
            if focused and p.evaluate("()=>window.__keep||0") != 1:   # 入力中は読み直さない（書きかけを消さない）
                bad.append(f"✗ {tag}: 入力中なのに読み直した")
            if p.evaluate("()=>document.documentElement.dataset.sb||''") == "down":
                bad.append(f"✗ {tag}: 戻ったのに休止のまま")
            print(f"{tag:28s} 網 {st['n']} 回 · 案内 {p.evaluate('()=>document.querySelectorAll(\".wl-sbnote\").length')}")
            ctx.close()
    b.close()
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://cxelegy.github.io/Wishlist/")
    ap.add_argument("--mode", default="abort", choices=["abort", "402", "recover"])
    ap.add_argument("--shots", default="")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        base = a.base if a.base.endswith("/") else a.base + "/"
        bad = recover(pw, base) if a.mode == "recover" else check(pw, base, a.mode, a.shots)
    print("\n".join(bad) or "全部 OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
