"""本番の網页を、お客さまの目で自動で点検する（HARNESS.md §7・「一番大事な決まり」）。

だれで：ログインなし・test-a（版面が多い）・test-b（1 つ）・test-c（0 個）。どこで：1400 px と 390 px。
見ること（1 つでも外れたら ✗、終わりのコードは 1）：
  - 開き直しのくり返し：開いてから 40 秒のあいだのページの読み込み（?v= を含む）が 3 回を超える
  - 白い画面：見えている文字が 200 字未満、または版面（section.sec）もポスター（#front）もない
  - 素の箱：お客さまの画面に JS で描いた箱（.wl-mine・.wl-wait・.wl-today・.wl-maybe）が出ている
  - 店長と同じ枠組み：目次（.nav）・題字（.mast か h1）・令牌（--ink）がある
  - 横にはみ出す：scrollWidth > 画面の幅
  - JS のエラー（pageerror）
写真は OUT/<だれ>-<幅>.png。

    python harness/ux_check.py [--base https://cxelegy.github.io/Wishlist/home/] [--out DIR] [--who test-a,test-b]
"""
import argparse
import json
import os
import pathlib
import sys
import time
import urllib.request

import yaml
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
WHO = {"guest": None, "test-a": "test-a@example.com", "test-b": "test-b@example.com", "test-c": "test-c@example.com"}
PASSWORD = "0000"   # テスト用アカウントの決まった合言葉（CLAUDE.md「ログイン」）
WATCH_S = 40
BOXES = ".wl-mine,.wl-wait,.wl-today,.wl-maybe"


def session(email):
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    base, key = s["supabase_url"].rstrip("/"), s["supabase_key"]
    req = urllib.request.Request(base + "/auth/v1/token?grant_type=password",
                                 data=json.dumps({"email": email, "password": PASSWORD}).encode(),
                                 headers={"apikey": key, "Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=30).read())
    out["expires_at"] = int(time.time()) + int(out.get("expires_in", 3600))
    return out


def check(pw, base, who, width, out):
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)   # Actions では入っている Chrome（UX_CHANNEL=chrome）
    pg = b.new_page(viewport={"width": width, "height": 900})
    loads, errors = [], []
    pg.on("load", lambda: loads.append(pg.url))
    pg.on("pageerror", lambda e: errors.append(str(e)[:160]))
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    if WHO[who]:
        pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}",
                    session(WHO[who]))
    loads.clear()
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(WATCH_S * 1000)
    st = pg.evaluate("""b=>({text:document.body?document.body.innerText.replace(/\\s+/g,'').length:0,
        secs:document.querySelectorAll('section.sec').length,front:!!document.getElementById('front'),
        boxes:[...document.querySelectorAll(b)].filter(x=>x.offsetParent).length,
        nav:!!document.querySelector('.nav'),mast:!!document.querySelector('.mast,h1'),
        token:getComputedStyle(document.documentElement).getPropertyValue('--ink').trim()!=='',
        own:!!document.querySelector('meta[name="wl-own"]'),
        arts:document.querySelectorAll('section.sec article').length,
        pics:[...document.querySelectorAll('section.sec article img')].length,
        empty:/新着なし/.test((document.querySelector('.poster .top')||{}).innerText||''),
        sw:document.documentElement.scrollWidth})""", BOXES)
    pg.screenshot(path=str(out / f"{who}-{width}.png"))
    b.close()
    bad = []
    if len(loads) > 3:
        bad.append(f"開き直しのくり返し（{WATCH_S} 秒で {len(loads)} 回）")
    if st["text"] < 200 or not (st["secs"] or st["front"]):
        bad.append(f"白い画面（文字 {st['text']}・版面 {st['secs']}）")
    if WHO[who] and st["boxes"]:
        bad.append(f"素の箱 {st['boxes']} 個")
    if not (st["nav"] and st["mast"] and st["token"]):
        bad.append("店長と同じ枠組みがない（目次・題字・令牌）")
    if st["sw"] > width:
        bad.append(f"横にはみ出す（{st['sw']}px）")
    if st["arts"] and st["empty"]:   # 2026-10-24：記事が 8 本あってもポスターが「直近 7 日は新着なし」（写真のある記事がない）
        bad.append(f"記事が {st['arts']} 本あるのにポスターが「新着なし」（写真 {st['pics']} 枚）")
    if errors:
        bad.append("JS のエラー：" + " / ".join(errors[:2]))
    return st, bad


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://cxelegy.github.io/Wishlist/home/")
    ap.add_argument("--out", default=str(ROOT / "harness" / "shots"))
    ap.add_argument("--who", default=",".join(WHO))
    ap.add_argument("--widths", default="1400,390")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fails = 0
    with sync_playwright() as pw:
        for who in a.who.split(","):
            for w in map(int, a.widths.split(",")):
                try:
                    st, bad = check(pw, a.base, who, w, out)
                except Exception as ex:  # noqa: BLE001
                    st, bad = {}, [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + f"{who} {w}px：" + ("、".join(bad) if bad else
                      f"版面 {st.get('secs')}・記事 {st.get('arts')}・写真 {st.get('pics')}・本人のページ {'はい' if st.get('own') else 'いいえ'}"))
    print(f"点検：✗ {fails} 件")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
