"""本番のページが写真・小元素をどこから取るかを数える（2026-11-03 Supabase egress 対策 ④）。
    python harness/pages_served.py [--pages home/,home/heat.html,...] [--who test-a,test-b,test-c]
--who：ログイン中のお客さまのページ（Supabase の pages 箱の HTML）も同じ条件で数える（ログインは認証だけ。storage は止まる）。
各ページを 1 回だけ開き（共通の launch：Supabase の storage は route で止まる）、画像の取得を網域別に数える。
✓ 条件：写真の 99% 以上が Pages の /Wishlist/p/ 、Supabase storage への取得 0、/p/ の失敗（200・304 以外）0。失敗は網址と状態を出す。"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser import PATTERN, launch  # noqa: E402

BASE = "https://cxelegy.github.io/Wishlist/"
DEFAULT = "home/,home/heat.html,home/wishlist.html,home/admin.html,"


def classify(url):
    if "/Wishlist/p/" in url:
        return "pages"
    if url.startswith(BASE):
        return "own"   # docs/ の中の画像（小元素 home/emblems/・アイコン）＝Pages から出る
    if PATTERN.match(url):
        return "storage"
    return "other"


def verdict(count, bad):
    """(ok, 一行)。count＝{'pages','storage'} の取得数、bad＝/p/ の失敗の一覧。"""
    n = count["pages"] + count["storage"]
    share = count["pages"] / n if n else 0
    ok = n > 0 and share >= 0.99 and not count["storage"] and not bad
    return ok, "写真・小元素 %d 件のうち Pages %.1f%%・Supabase storage %d 件・/p/ の失敗 %d 件" % (n, share * 100, count["storage"], len(bad))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=DEFAULT)
    ap.add_argument("--who", default="", help="ログインして home/ を開く人（test-a,test-b,test-c）")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    count, bad, seen, hosts = Counter(), [], set(), Counter()
    with sync_playwright() as pw:
        b = launch(pw)
        runs = [(p, None) for p in a.pages.split(",") if a.pages] + [("home/", w) for w in a.who.split(",") if w]
        for path, who in runs:
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            if who:   # 認証の呼び出しだけ本番に当たる（storage は route で止まる）。ux_check と同じ入り方
                import ux_check
                pg.goto(BASE + "home/", wait_until="domcontentloaded", timeout=a.timeout * 1000)
                pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}",
                            ux_check.session(ux_check.WHO[who]))
            pg.on("request", lambda r: (seen.add(r.url), count.update([classify(r.url)]), hosts.update([re.sub(r"^https?://([^/]+).*", r"\1", r.url)] if classify(r.url) == "other" else [])) if r.resource_type == "image" and r.url not in seen else None)
            pg.on("response", lambda r: bad.append((r.status, r.url)) if "/Wishlist/p/" in r.url and r.status not in (200, 304) else None)
            pg.goto(BASE + path, wait_until="domcontentloaded", timeout=a.timeout * 1000)
            if who:   # 殻から本人のページ（wl-own）に替わるまで待つ。替わらなければ ✗ 扱いにするため数を出す
                try:
                    pg.wait_for_function("!!document.querySelector('meta[name=\"wl-own\"]')", timeout=30000)
                except Exception:  # noqa: BLE001
                    print("  本人のページに替わらなかった", who)
                    bad.append((0, who + " の本人のページが開かない"))
            h = pg.evaluate("document.body.scrollHeight")
            for y in range(0, h, 900):
                pg.evaluate("y=>scrollTo(0,y)", y)
                pg.wait_for_timeout(120)
            pg.wait_for_timeout(2500)
            print(who or path or "(入口)", dict(count))
            pg.close()
        b.close()
    ok, line = verdict(count, bad)
    print("  Pages の外から出た画像（原寸の外部画像＝/p/ が無いときの落ち先）", sum(hosts.values()), "件・上位", hosts.most_common(4))
    for s, u in bad[:20]:
        print("  失敗", s, u)
    print(("✓ " if ok else "✗ ") + line)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
