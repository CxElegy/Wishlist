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
  - エンブレム（harness/emb_check.py の E1〜E18：短い辺 256px 未満〔E18〕・出ない・読めない・白い四角・大きさ・はみ出し・題字に重なる・切れ・重複・別の作品の絵・目標に届かない・何人も・形の傷・顔を測っていない〔E13：網址の小元素も〕・同じ版面の顔の大きさのばらつき〔E14：最大÷最小 ≤1.25〕）。
    --emb quick（ふだん）は出ている 1 枚を網页で測り、画像は候補を全部見る。--emb full は候補を全部差し替えて測り、写真の一覧 OUT/emb/sheet-<だれ>-<幅>.png
設定ページ（settings.html）も同じ人・同じ幅で：素の箱・題字・令牌・はみ出し・JS のエラー、お客さまは本人の設定ページ（wl-own）か。
管理ページ（admin.html ＝トップ＋ admin-*.html の 6 つ。7 枚とも開ける・切り替え 7 つ・はみ出しなし・JS のエラーなし・前の 1 枚の欄 13 と小見出し 10 が全部どこかにある〔なくした欄 0〕。
⑤しくみ admin-system.html は、ログインなしで門を外して HTML の作りだけ）：「全体の構成（詳しい図）」の枠が潰れていない（PC で枠の幅 140px 以上、
2026-10-25 に枠が 24px に潰れた）・枠の下の空白 800px 以下（Actions の枠だけ 5,129px で下の枠が押し下げられた）・部品の重なり 0・枠や部品の字のはみ出し 0・横にはみ出さない。写真 OUT/admin-arch-<幅>.png。
写真は OUT/<だれ>-<幅>x<高さ>.png・OUT/<だれ>-settings-<幅>x<高さ>.png。
0 個の人（test-c）は 390 幅で高さ 667・740 でも、最初の画面・設定・欲しい物（wishlist.html）を点検（主役のボタンが画面に入り固定ボタンと重ならない）。
「1 日通し」（--journey、2026-10-27）：空のアカウント test-d で、押して通す。入口 →「ログイン」→ 空の最初の画面の「好きなものを選ぶ」→ ジャンル → カード → 確認 →「足す」→
自分のページに札が出る → 設定ページに出る →札を押して外れる → 空に戻る（本人の追いかけるものを空にする）。各段で本物のクリック（ほかの部品が上に重なっていれば押せずに ✗）、前後の画面を OUT/journey-<幅>-<段>.png に残す。
✗：押せない・押しても変わらない・JS のエラー・素の箱・横にはみ出す・同じ id の重複。始めと終わりに本人の追いかけるもの（prefs.picks）を空にする（本人の行だけ、my_keywords_set）。
今のところ 👍・欲しい物は通さない（空の人には 👍 する記事も欲しい物の入口もない。BACKLOG に書いた）。

    python harness/ux_check.py --journey [--base ...]   （1 日通しだけ。ふだんの点検には混ぜない）
    python harness/ux_check.py [--base https://cxelegy.github.io/Wishlist/home/] [--out DIR] [--who test-a,test-b] [--emb quick|full|off]
"""
import argparse
import json
import os
import pathlib
import re
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


# 2026-10-27：手元の回線（点検の箱のプロキシ）だけで開けない写真を ✗ に数えない。ブラウザで開けなかった写真を、
# ブラウザと同じ頭で取り直して画像が返れば「サイトの欠陥ではない」（AOL・Yahoo の写真が guest・test-a の版面の頭で ✗ になった）
FAIL_JS = ("window.__imgFail=[];addEventListener('error',function(e){var t=e.target;if(t&&t.tagName==='IMG'&&t.src&&!t.classList.contains('bg')){"
           "var s=t.closest('section.sec');window.__imgFail.push([s?s.dataset.k:'トップ',t.src])}},true)")
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                   "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}


def server_opens(url):
    """写真の網址を、Referer なしのブラウザの頭で取り直して画像が返るか。"""
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_HEADERS), timeout=20)
        return r.status == 200 and r.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def nohead_real(nohead, fails, opens=server_opens):
    """版面の頭が写真なしの版面のうち、本当に写真が開けない（または写真がない）もの。
    ブラウザで開けなかった写真が全部、取り直せば開く版面は手元の回線の都合なので外す。"""
    out = []
    for k in nohead:
        srcs = [s for kk, s in fails if kk == k]
        if not srcs or not all(opens(s) for s in dict.fromkeys(srcs)):
            out.append(k)
    return out


def check(pw, base, who, width, out, page="", emb="off", height=900, wait=WATCH_S):
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)   # Actions では入っている Chrome（UX_CHANNEL=chrome）
    pg = b.new_page(viewport={"width": width, "height": height})
    loads, errors = [], []
    pg.on("load", lambda: loads.append(pg.url))
    pg.on("pageerror", lambda e: errors.append(str(e)[:160]))
    pg.add_init_script(FAIL_JS)
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    if WHO[who]:
        pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}",
                    session(WHO[who]))
    loads.clear()
    pg.goto(base + page, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(wait * 1000)
    if not page:   # 2026-10-27：loading=lazy の写真は下までスクロールしないと読み込まれず、開けない写真（札）を数え損ねる。下まで読んでから数える
        for y in range(0, 40000, 800):
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(80)
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(3000)
    st = pg.evaluate("""b=>({text:document.body?document.body.innerText.replace(/\\s+/g,'').length:0,
        secs:document.querySelectorAll('section.sec').length,front:!!document.getElementById('front'),
        boxes:[...document.querySelectorAll(b)].filter(x=>x.offsetParent).length,
        nav:!!document.querySelector('.nav'),mast:!!document.querySelector('.mast,h1'),
        token:getComputedStyle(document.documentElement).getPropertyValue('--ink').trim()!=='',
        own:!!document.querySelector('meta[name="wl-own"]'),
        start:!!document.querySelector('.startgo'),
        arts:document.querySelectorAll('section.sec article').length,
        pics:[...document.querySelectorAll('section.sec article img')].length,
        heads:[...document.querySelectorAll('.pic.icon,.pic.none')].filter(x=>!x.closest('.nav,.fside')).map(x=>(x.closest('section.sec')||{dataset:{k:'トップ'}}).dataset.k),
        nohead:[...document.querySelectorAll('section.sec')].filter(s=>{const h=s.querySelector('.grid article.card.hero,.grid article.card.wide');return h&&h.classList.contains('nophoto')}).map(s=>s.dataset.k),
        plates:document.querySelectorAll('.pic.icon,.pic.none').length,
        frames:document.querySelectorAll('section.sec .pic').length,
        empty:/新着なし/.test((document.querySelector('.poster .top')||{}).innerText||''),
        tofu:[...document.querySelectorAll('body *')].filter(x=>x.offsetParent&&![...x.childNodes].every(n=>n.nodeType!==3||!/[\u3000-\u9fff\uff00-\uffef]/.test(n.data))&&!/Noto Sans|Serif|Yusei/.test(getComputedStyle(x).fontFamily)&&!/^(SCRIPT|STYLE)$/.test(x.tagName)).map(x=>x.className||x.tagName).slice(0,3),
        hero:(p=>{if(!p)return false;const i=p.querySelector('img:not(.bg):not(.ico)');return p.matches('.icon,.none')||!i||!(i.complete&&i.naturalWidth>0)})(document.querySelector('.poster .top .pic')),
        dup:[...document.querySelectorAll('[id]')].map(x=>x.id).filter((v,i,a)=>a.indexOf(v)!==i).slice(0,3),
        sw:document.documentElement.scrollWidth})""", BOXES)
    near = [] if page else pg.evaluate(NEAR_JS)
    fails = pg.evaluate("window.__imgFail||[]") if (st["nohead"] or st["heads"]) else []
    nohead = nohead_real(st["nohead"], fails) if st["nohead"] else []
    heads = nohead_real(sorted(set(st["heads"])), fails) if st["heads"] else []
    first = pg.evaluate(FIRST_JS)
    pg.screenshot(path=str(out / f"{who}-{page.split('.')[0] + '-' if page else ''}{width}x{height}.png"))
    bad = []
    if not page and emb != "off":
        bad += emb_check.check(pg, who, width, out, full=emb == "full", guest=not WHO[who])
    b.close()
    if page:   # 設定ページ：版面・目次はないので、枠組み（題字・令牌）と本人の分か
        shell = page in ("wishlist.html", "heat.html") and WHO[who]   # AUTH_JS の「index・settings 以外」の枝：本人の殻（.wl-mine .empty）が出ているのが正しい。殻は字が少ない（0 個 77・1 個 72 字）ので下限 40、殻がなければ 100
        if shell and not first.get("shell"):
            bad.append("本人の殻（.wl-mine .empty）が出ていない")
        if st["text"] < (40 if shell and first.get("shell") else 100):
            bad.append(f"白い画面（文字 {st['text']}）")
        if WHO[who] and page == "settings.html" and st["boxes"]:
            bad.append(f"素の箱 {st['boxes']} 個（本人の設定ページではない）")
        if WHO[who] and page == "settings.html" and not st["own"]:
            bad.append("本人の設定ページではない")
        if st["dup"]:   # 2026-10-27：素の箱を 2 回描いて id mine・wl-addn が重なった（同じ id の部品を数える）
            bad.append("同じ id が 2 回：" + "・".join(st["dup"]))
        if not (st["mast"] and st["token"]):
            bad.append("題字・令牌がない")
        if st["sw"] > width:
            bad.append(f"横にはみ出す（{st['sw']}px）")
        if errors:
            bad.append("JS のエラー：" + " / ".join(errors[:2]))
        bad += first_screen_bad(first)   # 0 個の人の設定・欲しい物：主役のボタンがあり・最初の画面に入り・固定ボタンと重ならない
        return st, bad
    if len(loads) > 3:
        bad.append(f"開き直しのくり返し（{WATCH_S} 秒で {len(loads)} 回）")
    if st["text"] < (100 if st["start"] else 200) or not (st["secs"] or st["front"]):   # 版面 0 個の最初の画面は字が少ないのが正しい（2026-10-27）
        bad.append(f"白い画面（文字 {st['text']}・版面 {st['secs']}）")
    if WHO[who] and st["boxes"]:
        bad.append(f"素の箱 {st['boxes']} 個")
    if st["dup"]:
        bad.append("同じ id が 2 回：" + "・".join(st["dup"]))
    if not (st["nav"] and st["mast"] and st["token"]):
        bad.append("店長と同じ枠組みがない（目次・題字・令牌）")
    if st["sw"] > width:
        bad.append(f"横にはみ出す（{st['sw']}px）")
    bad += first_screen_bad(first)
    if st["tofu"]:   # 2026-10-26：数字の書体（Anton）に日本語の字がなく □□□ になった（「（日）」）
        bad.append("日本語の字が日本語の書体でない（□になる）：" + "・".join(map(str, st["tofu"])))
    if st["hero"]:   # 2026-10-26：ポスターの写真が読み込めていない
        bad.append("ポスターの写真が出ていない")
    if st["arts"] and st["empty"]:   # 2026-10-24：記事が 8 本あってもポスターが「直近 7 日は新着なし」（写真のある記事がない）
        bad.append(f"記事が {st['arts']} 本あるのにポスターが「新着なし」（写真 {st['pics']} 枚）")
    if heads:   # 2026-10-25：記事の枠が出典のアイコンの札（写真が出ない）。2026-10-27：版面の全部の記事に、さらにトップ（#front の article.wc）も。開けない写真は render.SWAP_JS が .nophoto に落とす
        bad.append(f"記事が札（写真が出ない。開けない写真は字だけの形に落とす）{len(heads)}：" + "・".join(heads[:4]))
    if nohead:   # 2026-10-27：札は字だけの形に落ちても、版面の頭（大きい枠）が写真なしのままでは「頭に写真」の規則が守られていない（開けない写真を組むときに知らない。BACKLOG の [?] 呪術廻戦の頭）
        bad.append(f"版面の頭が写真なし（字だけの形）{len(nohead)}：" + "・".join(nohead[:4]))
    if st["plates"]:
        print(f"  札 {st['plates']}／写真枠 {st['frames']}（{who} {width}px。0 が目標）")
    if near:
        bad.append(f"近さ {len(near)}（記事どうしの隙間が記事の中と同じくらい：" + "・".join(
            f"{x['sec']} 中 {x['inner']}px／間 {x['outer']}px" for x in near[:3]) + "）")
    if errors:
        bad.append("JS のエラー：" + " / ".join(errors[:2]))
    return st, bad


# 2026-10-27：版面 0 個の人の最初の画面。主役のボタンが最初の画面の中にあり、右下の固定ボタンと 8px 以上離れる。「N 作品」の数は本当の数と一致
FIRST_JS = """()=>{const g=document.querySelector('.startgo,.wl-mine .go.big'),f=document.querySelector('.wl-auth'),r=x=>x?x.getBoundingClientRect():null;
 const sum=[...document.querySelectorAll('.shelf h3 small')].reduce((s,x)=>s+(+((x.textContent.match(/(\\d+) 作品/)||[])[1])||0),0);
 const g1=r(g),f1=r(f);let hit=true;if(g1){const e=document.elementFromPoint((g1.left+g1.right)/2,Math.min((g1.top+g1.bottom)/2,innerHeight-1));hit=!!e&&g.contains(e);}return {hit,go:g1?{t:g1.top,b:g1.bottom,l:g1.left,r:g1.right}:null,fix:f1?{t:f1.top,b:f1.bottom,l:f1.left,r:f1.right}:null,
  H:innerHeight,shelves:!!document.querySelector('.shelfbox'),sum,tapes:document.querySelectorAll('.shelf .tapes>a').length,
  zero:!!document.querySelector('.calm.start,.top.start')||/まだ何も追いかけていません/.test((document.querySelector('.page,.wl-mine')||{}).innerText||''),
  quiet:[...document.querySelectorAll('.poster,.calm.start,.pill .cnt,.calm .tag')].map(x=>x.innerText||'').join(' ').replace(/\\s+/g,'').includes('新着なし'),
  links:document.querySelectorAll('.page a.startgo,.page .calm a,.wl-mine .go.big').length,shell:!!document.querySelector('.wl-mine .empty')}}"""


def first_screen_bad(f, gap=8):
    """f = FIRST_JS の結果。壊れ方を文にして返す（単体テストで足りない所を見分ける）。"""
    if not f:
        return []
    bad = []
    g, x = f["go"], f["fix"]
    if g:
        if g["b"] > f["H"]:
            bad.append(f"主役のボタンが最初の画面に入らない（下端 {round(g['b'])}px／画面 {f['H']}px）")
        if f.get("hit") is False:   # 2026-10-27：.top の中の子は pointer-events:none だったため、見えていても押せなかった
            bad.append("主役のボタンの真ん中を押すと別の部品に当たる（押せない）")
        if x and g["l"] < x["r"] + gap and x["l"] < g["r"] + gap and g["t"] < x["b"] + gap and x["t"] < g["b"] + gap:
            bad.append("主役のボタンが右下の固定ボタンと重なる・近すぎる（8px 未満）")
        if f["shelves"]:
            bad.append("版面 0 個なのにジャンル別の棚が出ている")
    if f.get("zero"):   # 版面 0 個の人：主役のボタンが必ずある・新着の話をしない（目次・ポスター・静かな版面）・道は 1 つ
        if not g:
            bad.append("版面 0 個なのに主役のボタン（.startgo）がない")
        if f.get("quiet"):
            bad.append("版面 0 個なのに「新着なし」の字が出ている（目次・ポスター・静かな版面）")
        if f.get("links", 0) > 1:
            bad.append(f"版面 0 個の画面に「選ぶ」の入口が {f['links']} 個ある（主役の 1 つだけ）")
    if f["sum"] != f["tapes"]:
        bad.append(f"「N 作品」の数 {f['sum']} が棚の本当の数 {f['tapes']} と違う")
    return bad


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
    pg.goto(base + "admin-system.html", wait_until="networkidle", timeout=60000)   # ⑤しくみ（管理ページは 6 つ）
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


# 前の 1 枚の管理ページ（2026-10-25 まで）にあった欄と小見出し：6 つに分けても全部どこかにある（なくした欄 0）
ADMIN_OLD_IDS = ["members", "term-panel", "tokens", "ov", "status", "editdiff", "backend", "emblem-ex", "procs", "queue", "items", "emblems", "votes"]
ADMIN_OLD_H3 = ["いま待っているもの", "いま動いているもの", "次の実行", "リソース", "AI を使うか", "並列と制限", "待ち行列", "ログ", "版面ごとの状態", "「違う」の理由"]
ADMIN_FILES = ["admin.html", "admin-now.html", "admin-boards.html", "admin-emblem.html", "admin-ai.html", "admin-system.html", "admin-members.html"]
ADMIN_JS = """() => ({ids:[...document.querySelectorAll('section.panel[id]')].map(s=>s.id),
 h3:[...document.querySelectorAll('h3.h3')].map(h=>(h.firstChild&&h.firstChild.textContent||'').trim()),
 nav:document.querySelectorAll('nav .admnav a').length,samples:document.querySelectorAll('#adm-samples a[href*="testground"]').length,sw:document.documentElement.scrollWidth,
 txt:document.body.innerText.length})"""


EYE_JS = """() => { const t = [...document.querySelectorAll('.emm-ph img.fv')];
 return {n: t.length, off: t.filter(i => !i.parentElement.querySelector('.emm-fl') && Math.abs(+i.dataset.eye - 0.3) > 0.05).length,
  short: t.filter(i => (i.parentElement.querySelector('.emm-fl') || {}).textContent === '下が足りない（目の線が合わない）').length} }"""


def check_admin_pages(pw, base, width, out):
    """管理ページのトップと 6 つの別ページ：開ける・切り替え（7 つのリンク）・横にはみ出さない・JS のエラーなし・前の欄が全部どこかにある。"""
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    bad, ids, h3 = [], set(), set()
    for f in ADMIN_FILES:
        pg = b.new_page(viewport={"width": width, "height": 900})
        errs = []
        pg.on("pageerror", lambda ex: errs.append(str(ex)[:80]))
        r = pg.goto(base + f, wait_until="networkidle", timeout=60000)
        pg.add_style_tag(content="html body>.page.page.page.page.page.page{display:block!important}html body>.wl-gate.wl-gate.wl-gate.wl-gate.wl-gate.wl-gate{display:none!important}"
                         "html[data-auth] body>*{visibility:visible!important}")
        pg.wait_for_timeout(1500)
        st = pg.evaluate(ADMIN_JS)
        if f == "admin-emblem.html":   # E16：札のない小元素の目の線が枠の上から 30% ±5% を外れる（emblem_face.view。札 short は別の写真に替える対象）
            ey = pg.evaluate(EYE_JS)
            if ey["off"]:
                bad.append(f"{f} E16 目の線がずれた小元素 {ey['off']} 枚（{ey['n']} 枚中。札 short {ey['short']} 枚は別）")
            print(f"  [管理ページ小元素] 顔そろえの置き方 {ey['n']} 枚・目の線ずれ {ey['off']}・札 short {ey['short']}")
        pg.screenshot(path=str(out / f"{f[:-5]}-{width}.png"))
        pg.close()
        if not r or r.status != 200:
            bad.append(f"{f} が開けない（{r.status if r else '?'}）")
            continue
        ids |= set(st["ids"])
        h3 |= set(st["h3"])
        if f == "admin.html" and st["samples"] < 3:   # 見本・試作へ網址を打たずに行ける
            bad.append(f"{f} に見本・試作へのリンクが {st['samples']} 個（3 個以上のはず）")
        if st["nav"] != 7:
            bad.append(f"{f} の切り替えが {st['nav']} 個（7 個のはず）")
        if st["sw"] > width:
            bad.append(f"{f} が横にはみ出す（{st['sw']}px）")
        if errs:
            bad.append(f"{f} の JS のエラー：{errs[0]}")
    b.close()
    lost = [i for i in ADMIN_OLD_IDS if i not in ids] + [x for x in ADMIN_OLD_H3 if x not in h3]
    if lost:
        bad.append("なくした欄：" + "・".join(lost))
    return bad


def check_emb_fade(pw, base, width):
    """小元素の「パッ」：画像を 1.5 秒遅らせ、出る前は透明で場所（高さ）が変わらず、届いたら不透明になるか。"""
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.route("**/*", lambda r: (time.sleep(1.5), r.continue_()) if r.request.resource_type == "image" else r.continue_())
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    q = "()=>{const i=document.querySelector('.emb img'),e=i&&i.closest('.emb');return i?{o:+getComputedStyle(i).opacity,h:e.offsetHeight,ld:i.classList.contains('ld')}:null}"
    qp = "()=>{const i=document.querySelector('.pic img:not(.bg):not(.ico)');return i?{o:+getComputedStyle(i).opacity,ld:i.classList.contains('ld')}:null}"
    pg.wait_for_timeout(500)
    # 画面外の lazy な小元素は近づくまで出ない（それが正しい）。最初の 1 枚は画面に入れてから、出る前・出たあとを見る
    pg.evaluate("()=>{const i=document.querySelector('.emb img');i&&i.scrollIntoView({block:'center'})}")
    pg.wait_for_timeout(300)
    before, pbefore = pg.evaluate(q), pg.evaluate(qp)
    pg.wait_for_timeout(8000)
    after, pafter = pg.evaluate(q), pg.evaluate(qp)
    # 画面外の lazy な写真：3 秒の保険で先に .ld が付くと、近づいたとき「パッ」と出る。届いていないなら .ld は付かないこと
    far = pg.evaluate("()=>{const l=[...document.querySelectorAll('.pic img:not(.bg):not(.ico)')].filter(i=>i.getBoundingClientRect().top>innerHeight*2&&!(i.complete&&i.naturalWidth));const i=l[l.length-1];return i?{ld:i.classList.contains('ld'),n:l.length}:null}")
    b.close()
    if not before or not after:
        return ["小元素がない"]
    bad = []
    if before["o"] > 0.01 and not before["ld"]:
        bad.append(f"読み込み前に見えている（透明度 {before['o']}）")
    if before["h"] != after["h"]:
        bad.append(f"出るとき高さが変わる（{before['h']}→{after['h']}px）")
    if after["o"] < 0.99:
        bad.append(f"出たあとも透明（{after['o']}）")
    if pbefore and pbefore["o"] > 0.01 and not pbefore["ld"]:
        bad.append(f"記事の写真が読み込み前に見えている（透明度 {pbefore['o']}）")
    if pafter and pafter["o"] < 0.99:
        bad.append(f"記事の写真が出たあとも透明（{pafter['o']}）")
    if far and far["ld"]:
        bad.append("画面外の未着の写真に先に .ld が付いている（近づくと「パッ」と出る）")
    return bad

JOURNEY_MAIL = "test-d@example.com"   # 空のアカウント（HARNESS.md「test-c・test-d：空」）
JOURNEY_TIMEOUT = 6000
PICK_RE = "好きなものを選ぶ|追いかけるものを選ぶ|追いかけるものを足す"   # 空の最初の画面の入口の文言（言い回しが変わったらここ 1 か所）


def press(pg, target, label, timeout=JOURNEY_TIMEOUT):
    """本物のクリック（Playwright は、上に別の部品が重なっていれば押せずに待って落ちる）。押せなければ理由を返す。"""
    try:
        loc = target.first if hasattr(target, "first") else pg.locator(target).first
        loc.click(timeout=timeout)
    except Exception as ex:  # noqa: BLE001
        why = "上に別の部品が重なって押せない" if "intercepts pointer" in str(ex) else "見つからない・押せない"
        return f"「{label}」が{why}"
    return None


def journey_rpc(base_url, key, tok, fn, body):
    req = urllib.request.Request(base_url.rstrip("/") + "/rest/v1/rpc/" + fn, data=json.dumps(body).encode(), method="POST",
                                 headers={"apikey": key, "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=30).read().decode()


PENDING_BAD = ("最初の 1 つを選ぼう", "まだ何も追いかけていません", "選ぶボタンは上のポスター")


def pending_contradiction(text, name):
    """足したものが画面に名前で出ているのに、同じ画面が「まだ何も」と言っていれば、その言い回しの一覧（空なら矛盾なし）。
    焼いた版（2 時間ごと）は足す前の姿なので、足した直後は画面の中で食い違う（2026-10-27：「集めています 呪術廻戦」の下に「最初の 1 つを選ぼう」）。"""
    return [w for w in PENDING_BAD if name in text and w in text]


def journey_reset():
    """本人（test-d）の追いかけるものを空にする。本人の行だけ（my_keywords_set は呼んだ人の prefs.picks だけ置き換える）。"""
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    tok = session(JOURNEY_MAIL)["access_token"]
    journey_rpc(s["supabase_url"], s["supabase_key"], tok, "my_keywords_set", {"p_picks": []})


BOX_JS = "b=>({boxes:[...document.querySelectorAll(b)].filter(x=>x.offsetParent).length,sw:document.documentElement.scrollWidth,\
dup:[...document.querySelectorAll('[id]')].map(x=>x.id).filter((v,i,a)=>a.indexOf(v)!==i).slice(0,3)})"


def journey(pw, base, width, out):
    """1 日通し。返り値は ✗ の一覧（空なら ✓）。"""
    bad, errors, n = [], [], [0]
    entry = base.rstrip("/").rsplit("/", 1)[0] + "/"   # 入口（/home/ の 1 つ上）
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)[:120]))

    def shot(name):
        n[0] += 1
        pg.screenshot(path=str(out / f"journey-{width}-{n[0]}-{name}.png"))

    def step(name, fn):
        """段を 1 つ：前の画面・後の画面を残し、出た理由を ✗ に足す。✗ が出たらそこで通しを止める（先は同じ原因で崩れる）。"""
        try:
            shot(name + "-前")
            why = fn()
            pg.wait_for_timeout(300)
            shot(name + "-後")
        except Exception as ex:  # noqa: BLE001
            why = f"{type(ex).__name__}: {str(ex)[:100]}"
        if why:
            bad.append(f"{name}：{why}")
        return not why

    def frame(label):
        st = pg.evaluate(BOX_JS, BOXES)
        if st["boxes"]:
            bad.append(f"{label}：素の箱 {st['boxes']} 個")
        if st["sw"] > width:
            bad.append(f"{label}：横にはみ出す（{st['sw']}px）")
        if st["dup"]:
            bad.append(f"{label}：同じ id が 2 回（{'・'.join(st['dup'])}）")

    try:
        journey_reset()
        pg.goto(entry, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector("text=新しく始める", timeout=15000)
        if not step("入口", lambda: None if pg.evaluate("()=>[...document.querySelectorAll('a,button')].filter(x=>/新しく始める|ログイン/.test(x.innerText)&&x.getBoundingClientRect().bottom<innerHeight).length>=2") else "最初の画面に「新しく始める」と「ログイン」が並んでいない"):
            return bad
        # 入口の「ログイン」→ 店長のページのログイン欄（本物の入力と送信）
        if not step("ログイン", lambda: press(pg, pg.get_by_role("link", name="ログイン", exact=True), "ログイン")):
            return bad

        def login():
            pg.wait_for_selector(".wl-login input[type=email]", timeout=15000)
            pg.fill(".wl-login input[type=email]", JOURNEY_MAIL)
            pg.fill(".wl-login .pw input", PASSWORD)
            if (w := press(pg, ".wl-login .go", "ログインのボタン")):
                return w
            pg.wait_for_function("()=>!!localStorage.getItem('wl-auth')", timeout=15000)
        if not step("ログイン入力", login):
            return bad
        if not step("空の最初の画面", lambda: pg.wait_for_function("p=>new RegExp(p).test(document.body.innerText)", arg=PICK_RE, timeout=30000) and None):
            return bad
        frame("空の最初の画面")
        pick = pg.locator("a:visible,button:visible").filter(has_text=re_pick())   # 見える押せるもの（隠れた <b> に当たらない）
        if not step("最初の 1 つを選ぶ", lambda: press(pg, pick, "好きなものを選ぶ")):
            return bad
        pg.wait_for_selector(".genre", timeout=20000)
        if not step("ジャンル", lambda: press(pg, ".genre", "ジャンル") or press(pg, "#to-cards:not([disabled])", "ジャンルの「次へ」")):
            return bad
        pg.wait_for_selector(".act.y", timeout=15000)
        if not step("カード", lambda: press(pg, ".act.y", "気になる（♥）") or press(pg, "#to-check", "「この中から始める」")):
            return bad
        name = pg.evaluate("()=>{const e=document.querySelector('.picked li .nm');return e?e.innerText:''}")
        if not name:
            bad.append("確認：選んだものが 1 つも出ていない")
            return bad
        if not step("足す", lambda: press(pg, "#to-done", "「足す」")):
            return bad
        pg.wait_for_url("**/home/**", timeout=30000)

        def mine():
            pg.wait_for_function("n=>document.body.innerText.includes(n)", arg=name, timeout=30000)
        if not step("自分のページに札", mine):
            return bad
        pg.wait_for_timeout(3000)   # 描き替えが終わるのを待つ
        frame("足したあとの自分のページ")
        for w in pending_contradiction(pg.evaluate("()=>document.body.innerText"), name):
            bad.append(f"足したあとの自分のページ：名前が出ているのに「{w}」とも言っている")

        def settings():   # 自分のページの「設定」ボタン → 設定ページにも名前が出る（ボタンで行く。網址は打たない）
            if (w := press(pg, pg.get_by_role("link", name=re.compile("設定")).first, "設定")):
                return w
            pg.wait_for_function("n=>document.body.innerText.includes(n)", arg=name, timeout=30000)
            pg.wait_for_timeout(3000)
            frame("設定ページ")
            for w in pending_contradiction(pg.evaluate("()=>document.body.innerText"), name):
                return f"名前が出ているのに「{w}」とも言っている"
        if not step("設定に出る", settings):
            return bad

        def off():   # 「<名前> を外す」（焼いた設定の行も、集めている最中の札も同じ名前）を押すと本人の追いかけるものから消える
            if (w := press(pg, pg.get_by_role("button", name=f"{name} を外す"), f"「{name} を外す」")):
                return w
            tok = session(JOURNEY_MAIL)["access_token"]
            for _ in range(10):
                pg.wait_for_timeout(500)
                if name not in journey_rpc(s["supabase_url"], s["supabase_key"], tok, "my_page", {}):
                    return None
            return "外すを押しても本人の追いかけるものから消えない"
        step("外す", off)
    except Exception as ex:  # noqa: BLE001
        bad.append(f"通せなかった（{type(ex).__name__}: {str(ex)[:120]}）")
    finally:
        b.close()
        try:
            journey_reset()   # 失敗しても空に戻す
        except Exception as ex:  # noqa: BLE001
            bad.append(f"後始末ができなかった（{type(ex).__name__}）：test-d の追いかけるものを手で空にする")
    if errors:
        bad.append("JS のエラー：" + " / ".join(errors[:2]))
    return bad


def re_pick():
    import re
    return re.compile(PICK_RE)



def shell_pages():
    """AUTH_JS（wl-auth）を持ち、index・settings・me・admin 以外のページ＝ログインした人が同じ殻（drawMine）に入るページ。
    docs/home の html から数えるので、ページを足しても点検が自動で広がる（2026-10-27：themes・terms の数え漏れ）。"""
    d = ROOT / "docs" / "home"
    return sorted(f.name for f in d.glob("*.html")
                  if f.stem not in ("index", "settings", "me") and not f.stem.startswith("admin")
                  and "wl-auth" in f.read_text(encoding="utf-8"))


def runs_for(who, widths):
    """人ごとの (幅, ページ, 高さ)。殻のページ（shell_pages＝AUTH_JS の「index・settings 以外」の枝）は guest を含む全員・全幅、
    0 個の人（test-c）は 390 幅の小さい端末（高さ 667・740）でも、最初の画面・設定・欲しい物・話題度（2026-10-27）。"""
    runs = [(int(w), pg, 900) for pg in ("", "settings.html") for w in widths]
    runs += [(int(w), pg, 900) for pg in shell_pages() for w in widths]   # guest も（殻なし・100 字の下限の枝）
    if who == "test-c" and "390" in widths:
        runs += [(390, pg, h) for h in (667, 740) for pg in ["", "settings.html"] + shell_pages()]
    return runs


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://cxelegy.github.io/Wishlist/home/")
    ap.add_argument("--out", default=str(ROOT / "harness" / "shots"))
    ap.add_argument("--who", default=",".join(WHO))
    ap.add_argument("--widths", default="1400,390")
    ap.add_argument("--emb", default="quick", choices=("quick", "full", "off"))
    ap.add_argument("--journey", action="store_true", help="1 日通し（空のアカウントで押して通す）だけを走らせる")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fails = 0
    with sync_playwright() as pw:
        if a.journey:
            for w in a.widths.split(","):
                bad = journey(pw, a.base, int(w), out)
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + f"1 日通し {w}px：" + ("、".join(bad) if bad else "入口 → ログイン → 足す → 自分のページ → 設定 → 外す"))
            print(f"1 日通し：✗ {fails} 件")
            return 1 if fails else 0
        for who in a.who.split(","):
            runs = runs_for(who, a.widths.split(","))
            for w, page, h in runs:
                try:
                    st, bad = check(pw, a.base, who, w, out, page, a.emb if h == 900 else "off", h, WATCH_S if h == 900 else 10)
                except Exception as ex:  # noqa: BLE001
                    st, bad = {}, [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + f"{who}{' ' + page.split('.')[0] if page else ''} {w}x{h}px：" + ("、".join(bad) if bad else
                      f"版面 {st.get('secs')}・記事 {st.get('arts')}・写真 {st.get('pics')}・本人のページ {'はい' if st.get('own') else 'いいえ'}"))
        for w in a.widths.split(","):
            try:
                bad = check_admin(pw, a.base, int(w), out)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"管理ページ 全体の構成 {w}px：" + ("、".join(bad) if bad else "崩れなし"))
            try:
                bad = check_admin_pages(pw, a.base, int(w), out)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"管理ページ 7 枚 {w}px：" + ("、".join(bad) if bad else f"欄 {len(ADMIN_OLD_IDS)}・小見出し {len(ADMIN_OLD_H3)} が全部ある"))
        for w in a.widths.split(","):
            try:
                bad = check_emb_fade(pw, a.base, int(w))
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"小元素の出方（遅い回線）{w}px：" + ("、".join(bad) if bad else "パッと出ない"))
    print(f"点検：✗ {fails} 件")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
