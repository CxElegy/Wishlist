"""放置したタブが Supabase を呼び続けないかの点検（2026-11-03，無料枠 egress）。本番には向けない：SB_DEG_JS（全ページの見回りの規則）を
空のページに入れ、時計を進めて every() の呼び出し数を数える。触らない 10 分まで 30 秒おき／30 分まで 5 分おき／その後 0／触れば即再開。
  python harness/idle_check.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import render  # noqa: E402
from browser import launch  # noqa: E402


def run(pw):
    b = launch(pw)
    p = b.new_context().new_page()
    p.clock.install(time=0)
    p.set_content("<html><head><script>" + render.SB_DEG_JS + "</script></head><body>x<script>window.n=0;WL_SB.every(function(){n++;},30000)</script></body></html>")
    out = {}

    def adv(ms):
        p.clock.run_for(ms)
        return p.evaluate("n")
    out["10分まで"] = adv(600000)
    a = out["10分まで"]
    out["10〜30分"] = adv(1200000) - a
    a = p.evaluate("n")
    out["30分〜2時間"] = adv(5400000) - a
    a = p.evaluate("n")
    p.mouse.click(5, 5)
    p.clock.run_for(1000)
    out["触った直後"] = p.evaluate("n") - a
    b.close()
    return out


def admin(pw):
    """管理ページ（livelog.py・overview.py の見回り）を放置：Supabase への呼び出しは route.fulfill(200) で数えるだけ（本番に出さない）。
    docs/home/admin-now.html を file:// で開く＝手元の生成物。30 分過ぎたら増えない。"""
    b = launch(pw)
    p = b.new_context().new_page()
    n = {"v": 0}

    def cnt(route):
        n["v"] += 1
        route.fulfill(status=200, content_type="application/json", body="[]")   # 200 を返す＝休止にならず、見回りの数だけが残る
    p.route("**/*.supabase.co/**", cnt)
    p.route("https://api.github.com/**", lambda r: r.abort())
    p.clock.install(time=0)
    p.goto("file://" + str(ROOT / "docs" / "home" / "admin-now.html"), wait_until="domcontentloaded")
    p.clock.run_for(60000)
    first = n["v"]
    p.clock.run_for(2160000)   # 30 分 + 最後の 5 分おきの 1 回ぶんの余り（30 分の手前に仕掛けた待ちが 5 分以内に 1 回出る）
    a = n["v"]
    p.clock.run_for(5400000)
    b.close()
    return {"最初の1分": first, "36分まで": a, "30分〜2時間": n["v"] - a}


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        o = run(pw)
        ad = admin(pw)
    print(o, ad)
    ok = 19 <= o["10分まで"] <= 21 and 3 <= o["10〜30分"] <= 5 and o["30分〜2時間"] == 0 and o["触った直後"] >= 1
    ok = ok and ad["30分〜2時間"] == 0
    print("✓ 放置で止まり、触れば戻る" if ok else "✗ 放置の見回りが規則どおりでない")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
