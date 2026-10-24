"""本番の網页を、お客さまの目で自動で点検する（HARNESS.md §7・「一番大事な決まり」）。

だれで：ログインなし・test-a（版面が多い）・test-b（1 つ）・test-c（0 個）。どこで：1400 px と 390 px。
見ること（1 つでも外れたら ✗、終わりのコードは 1）：
  - 開き直しのくり返し：開いてから 40 秒のあいだのページの読み込み（?v= を含む）が 3 回を超える
  - 白い画面：見えている文字が 200 字未満、または版面（section.sec）もポスター（#front）もない
  - 素の箱：お客さまの画面に JS で描いた箱（.wl-mine・.wl-wait・.wl-today・.wl-maybe）が出ている
  - 店長と同じ枠組み：目次（.nav）・題字（.mast か h1）・令牌（--ink）がある
  - 横にはみ出す：scrollWidth > 画面の幅
  - JS のエラー（pageerror）
  - 近さ（harness/near.js，2026-10-24）：写真が上の記事か下の記事か迷う所。すぐ上に別の記事がある記事で、
    上の記事の最後の字 → この記事の最初の部品 の隙間が max(24px, 記事の中のいちばん大きい隙間 × 2.5) 未満、かつ上の記事が線で閉じていない
  - エンブレム（harness/emb_check.py の E1〜E11：出ない・読めない・白い四角・大きさ・はみ出し・題字に重なる・切れ・重複・別の作品の絵・目標に届かない・何人も）。
    --emb quick（ふだん）は出ている 1 枚を網页で測り、画像は候補を全部見る。--emb full は候補を全部差し替えて測り、写真の一覧 OUT/emb/sheet-<だれ>-<幅>.png
設定ページ（settings.html）も同じ人・同じ幅で：素の箱・題字・令牌・はみ出し・JS のエラー、お客さまは本人の設定ページ（wl-own）か。
管理ページ（admin.html、ログインなしで門を外して HTML の作りだけ）：「全体の構成（詳しい図）」の枠が潰れていない（PC で枠の幅 140px 以上、
2026-10-25 に枠が 24px に潰れた）・枠の下の空白 800px 以下（Actions の枠だけ 5,129px で下の枠が押し下げられた）・部品の重なり 0・枠や部品の字のはみ出し 0・横にはみ出さない。写真 OUT/admin-arch-<幅>.png。
写真は OUT/<だれ>-<幅>.png・OUT/<だれ>-set-<幅>.png。

    python harness/ux_check.py [--base https://cxelegy.github.io/Wishlist/home/] [--out DIR] [--who test-a,test-b] [--emb quick|full|off]
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emb_check  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
WHO = {"guest": None, "test-a": "test-a@example.com", "test-b": "test-b@example.com", "test-c": "test-c@example.com"}
PASSWORD = "0000"   # テスト用アカウントの決まった合言葉（CLAUDE.md「ログイン」）
WATCH_S = 40
BOXES = ".wl-mine,.wl-wait,.wl-today,.wl-maybe"
NEAR_JS = (pathlib.Path(__file__).resolve().parent / "near.js").read_text(encoding="utf-8")


def session(email):
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    base, key = s["supabase_url"].rstrip("/"), s["supabase_key"]
    req = urllib.request.Request(base + "/auth/v1/token?grant_type=password",
                                 data=json.dumps({"email": email, "password": PASSWORD}).encode(),
                                 headers={"apikey": key, "Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=30).read())
    out["expires_at"] = int(time.time()) + int(out.get("expires_in", 3600))
    return out


def check(pw, base, who, width, out, page="", emb="off"):
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
    pg.goto(base + page, wait_until="domcontentloaded", timeout=60000)
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
    near = [] if page else pg.evaluate(NEAR_JS)
    pg.screenshot(path=str(out / f"{who}-{'set-' if page else ''}{width}.png"))
    bad = []
    if not page and emb != "off":
        bad += emb_check.check(pg, who, width, out, full=emb == "full", guest=not WHO[who])
    b.close()
    if page:   # 設定ページ：版面・目次はないので、枠組み（題字・令牌）と本人の分か
        if st["text"] < 100:
            bad.append(f"白い画面（文字 {st['text']}）")
        if WHO[who] and st["boxes"]:
            bad.append(f"素の箱 {st['boxes']} 個（本人の設定ページではない）")
        if WHO[who] and not st["own"]:
            bad.append("本人の設定ページではない")
        if not (st["mast"] and st["token"]):
            bad.append("題字・令牌がない")
        if st["sw"] > width:
            bad.append(f"横にはみ出す（{st['sw']}px）")
        if errors:
            bad.append("JS のエラー：" + " / ".join(errors[:2]))
        return st, bad
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
    if near:
        bad.append(f"近さ {len(near)}（記事どうしの隙間が記事の中と同じくらい：" + "・".join(
            f"{x['sec']} 中 {x['inner']}px／間 {x['outer']}px" for x in near[:3]) + "）")
    if errors:
        bad.append("JS のエラー：" + " / ".join(errors[:2]))
    return st, bad


ARCH_GAP = 800   # 枠の下の空白（次の枠まで）の上限 px。2026-10-25 Actions の枠だけ 5,129px で、ほかの枠の下に 3,500〜4,800px の空白
ARCH_JS = """()=>{const GAP=%d;const s=document.querySelector('#arch');if(!s)return null;const R=s.getBoundingClientRect();
 const zs=[...s.querySelectorAll(':scope>.az')],an=[...s.querySelectorAll('.an')].map(e=>[e,e.getBoundingClientRect()]);let ov=[],ob=[];
 for(let i=0;i<an.length;i++)for(let j=i+1;j<an.length;j++){const a=an[i][1],b=an[j][1];
  if(an[i][0].contains(an[j][0])||an[j][0].contains(an[i][0]))continue;
  if(a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1)ov.push(an[i][0].id+'×'+an[j][0].id)}
 for(const e of [...zs,...an.map(x=>x[0])]){const b=e.getBoundingClientRect();
  if(b.right>R.right+1||b.left<R.left-1||e.scrollWidth>e.clientWidth+2)ob.push(e.id||e.dataset.z)}
 const zb=zs.map(z=>[z.dataset.z,z.getBoundingClientRect()]),gap=[];
 for(const [n,a] of zb){let nx=null;for(const [m,c] of zb)if(m!==n&&c.top>=a.bottom-1&&c.left<a.right-1&&a.left<c.right-1)nx=nx===null?c.top:Math.min(nx,c.top);
  if(nx!==null&&nx-a.bottom>GAP)gap.push(n+' '+Math.round(nx-a.bottom)+'px')}
 return {narrow:zs.filter(z=>z.getBoundingClientRect().width<140).map(z=>z.dataset.z),ov,ob,gap,H:Math.round(R.height),sw:document.documentElement.scrollWidth}}""" % ARCH_GAP


def check_admin(pw, base, width, out):
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.goto(base + "admin.html", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)
    # 門（data-gate=1 で .page を隠す）より強い指定で中身を出す。HTML は公開なので、見えるのは作りだけ
    pg.add_style_tag(content="html body>.page.page.page.page.page.page{display:block!important}html body>.wl-gate.wl-gate.wl-gate.wl-gate.wl-gate.wl-gate{display:none!important}"
                     ".wl-auth{visibility:hidden!important}")   # 右上に固定のログインの札が写真の図の上に写り込む（図の崩れではない）
    pg.evaluate("window.dispatchEvent(new Event('resize'))")
    pg.wait_for_timeout(1500)
    st = pg.evaluate(ARCH_JS)
    if st:
        pg.locator("#procs").screenshot(path=str(out / f"admin-arch-{width}.png"))
    b.close()
    if not st:
        return ["全体の構成の図（#arch）がない"]
    bad = []
    if width >= 980 and st["narrow"]:
        bad.append("枠が潰れている：" + "・".join(st["narrow"]))
    if width >= 980 and st["gap"]:
        bad.append(f"枠の下に大きな空白（{ARCH_GAP}px 超・図の高さ {st['H']}px）：" + "・".join(st["gap"][:3]))
    if st["ov"]:
        bad.append(f"部品の重なり {len(st['ov'])}：" + "・".join(st["ov"][:3]))
    if st["ob"]:
        bad.append(f"はみ出し {len(st['ob'])}：" + "・".join(st["ob"][:3]))
    if st["sw"] > width:
        bad.append(f"横にはみ出す（{st['sw']}px）")
    return bad


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://cxelegy.github.io/Wishlist/home/")
    ap.add_argument("--out", default=str(ROOT / "harness" / "shots"))
    ap.add_argument("--who", default=",".join(WHO))
    ap.add_argument("--widths", default="1400,390")
    ap.add_argument("--emb", default="quick", choices=("quick", "full", "off"))
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fails = 0
    with sync_playwright() as pw:
        for who in a.who.split(","):
            for w, page in [(int(w), pg) for pg in ("", "settings.html") for w in a.widths.split(",")]:
                try:
                    st, bad = check(pw, a.base, who, w, out, page, a.emb)
                except Exception as ex:  # noqa: BLE001
                    st, bad = {}, [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + f"{who}{' 設定' if page else ''} {w}px：" + ("、".join(bad) if bad else
                      f"版面 {st.get('secs')}・記事 {st.get('arts')}・写真 {st.get('pics')}・本人のページ {'はい' if st.get('own') else 'いいえ'}"))
        for w in a.widths.split(","):
            try:
                bad = check_admin(pw, a.base, int(w), out)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"管理ページ 全体の構成 {w}px：" + ("、".join(bad) if bad else "崩れなし"))
    print(f"点検：✗ {fails} 件")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
