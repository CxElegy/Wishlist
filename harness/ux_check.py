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
  - エンブレム（harness/emb_check.py の E1〜E12：出ない・読めない・白い四角・大きさ・はみ出し・題字に重なる・切れ・重複・別の作品の絵・目標に届かない・何人も・形の傷）。
    --emb quick（ふだん）は出ている 1 枚を網页で測り、画像は候補を全部見る。--emb full は候補を全部差し替えて測り、写真の一覧 OUT/emb/sheet-<だれ>-<幅>.png
設定ページ（settings.html）も同じ人・同じ幅で：素の箱・題字・令牌・はみ出し・JS のエラー、お客さまは本人の設定ページ（wl-own）か。
管理ページ（admin.html ＝トップ＋ admin-*.html の 6 つ。7 枚とも開ける・切り替え 7 つ・はみ出しなし・JS のエラーなし・前の 1 枚の欄 13 と小見出し 10 が全部どこかにある〔なくした欄 0〕。
⑤しくみ admin-system.html は、ログインなしで門を外して HTML の作りだけ）：「全体の構成（詳しい図）」の枠が潰れていない（PC で枠の幅 140px 以上、
2026-10-25 に枠が 24px に潰れた）・枠の下の空白 800px 以下（Actions の枠だけ 5,129px で下の枠が押し下げられた）・部品の重なり 0・枠や部品の字のはみ出し 0・横にはみ出さない。写真 OUT/admin-arch-<幅>.png。
写真は OUT/<だれ>-<幅>.png・OUT/<だれ>-set-<幅>.png。
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
        heads:[...document.querySelectorAll('section.sec')].filter(s=>{const p=s.querySelector('.grid>article .pic');return p&&p.matches('.icon,.none')}).map(s=>s.dataset.k),
        plates:document.querySelectorAll('section.sec .pic.icon,section.sec .pic.none').length,
        frames:document.querySelectorAll('section.sec .pic').length,
        empty:/新着なし/.test((document.querySelector('.poster .top')||{}).innerText||''),
        tofu:[...document.querySelectorAll('body *')].filter(x=>x.offsetParent&&![...x.childNodes].every(n=>n.nodeType!==3||!/[\u3000-\u9fff\uff00-\uffef]/.test(n.data))&&!/Noto Sans|Serif|Yusei/.test(getComputedStyle(x).fontFamily)&&!/^(SCRIPT|STYLE)$/.test(x.tagName)).map(x=>x.className||x.tagName).slice(0,3),
        hero:(p=>{if(!p)return false;const i=p.querySelector('img:not(.bg):not(.ico)');return p.matches('.icon,.none')||!i||!(i.complete&&i.naturalWidth>0)})(document.querySelector('.poster .top .pic')),
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
    if st["tofu"]:   # 2026-10-26：数字の書体（Anton）に日本語の字がなく □□□ になった（「（日）」）
        bad.append("日本語の字が日本語の書体でない（□になる）：" + "・".join(map(str, st["tofu"])))
    if st["hero"]:   # 2026-10-26：ポスターの写真が読み込めていない
        bad.append("ポスターの写真が出ていない")
    if st["arts"] and st["empty"]:   # 2026-10-24：記事が 8 本あってもポスターが「直近 7 日は新着なし」（写真のある記事がない）
        bad.append(f"記事が {st['arts']} 本あるのにポスターが「新着なし」（写真 {st['pics']} 枚）")
    if st["heads"]:   # 2026-10-25：版面の頭の枠が出典のアイコンの札（写真が出ない）
        bad.append(f"版面の頭が写真なし（札）{len(st['heads'])}：" + "・".join(st["heads"][:3]))
    if st["plates"]:
        print(f"  札 {st['plates']}／写真枠 {st['frames']}（{who} {width}px。0 が目標）")
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
 nav:document.querySelectorAll('.admnav a').length,sw:document.documentElement.scrollWidth,
 txt:document.body.innerText.length})"""


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
        pg.screenshot(path=str(out / f"{f[:-5]}-{width}.png"))
        pg.close()
        if not r or r.status != 200:
            bad.append(f"{f} が開けない（{r.status if r else '?'}）")
            continue
        ids |= set(st["ids"])
        h3 |= set(st["h3"])
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
        pg.goto(base, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_function("()=>/外す/.test(document.body.innerText)", timeout=30000)

        def settings():   # 自分のページの「外す」→ 設定ページに名前が出る
            if (w := press(pg, pg.get_by_role("link", name="外す", exact=True), "外す（設定へ）")):
                return w
            pg.wait_for_function("n=>document.body.innerText.includes(n)", arg=name, timeout=30000)
            pg.wait_for_timeout(3000)
            frame("設定ページ")
        if not step("設定に出る", settings):
            return bad

        def off():   # 札をもう一度押すと外れる（最後の 1 つは保存が「ひとつ以上えらぶ」で止まる。空に戻すのは journey_reset）
            tile = pg.locator(".tiles button", has_text=name)
            if (w := press(pg, tile, f"札「{name}」")):
                return w
            pg.wait_for_timeout(500)
            if tile.first.get_attribute("aria-pressed") == "true":
                return "札を押しても外れない"
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
