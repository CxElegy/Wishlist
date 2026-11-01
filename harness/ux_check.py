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

--fast（2026-10-27）：札・枠組みだけを速く（小元素 off・待ち 6 秒・最初の画面と設定の 2 枚だけ・test-c の小さい端末なし）。4 人×2 幅で 5 分以内。小元素（出方も）・殻のページ・管理ページ 7 枚・40 秒の開き直しは見ない（全部は ふだんの点検）。

    python harness/ux_check.py --fast [--base ...]   （定時の速い回）
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
import urllib.error
import urllib.request

import yaml
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emb_check  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
WHO = {"guest": None, "test-a": "test-a@example.com", "test-b": "test-b@example.com", "test-c": "test-c@example.com"}
PASSWORD = "0000"   # テスト用アカウントの決まった合言葉（CLAUDE.md「ログイン」）
WATCH_S = 40
FAST_S = 6   # --fast の待ち
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


# 2026-11-01：「写真の余白」は、画面に入って読み込み済みの写真しか数えていなかった（本番 1400 で候補 1,394 枚のうち測れたのは約 130 枚。
# loading=lazy・横に流れるテープ・折りたたみ・pkpool〔[hidden] の予備〕は i.complete / offsetParent で飛ばされた）。
# 候補を全部 loading=eager にして読み込みを待ち（最大 8 秒・同時 60 枚）、[hidden] の祖先は測る間だけ外して数える。
# 読めなかった写真は unread で返し、候補の 25% を超えたら ✗（読めないまま「余白 0」と言わない）。
# 2026-11-01 スクロールで写真が出ない：届いたのに透明のまま（.ld が付かない）写真が 3 秒の保険まで色の枠だった（load は window まで上がらない）。
# 人の速さ（1 画面 / 0.35 秒）で下まで動き、画面に入った写真が「届いたのに opacity < 0.5」のまま 1 秒を超えたものを数える。
HIDDEN_JS = """async()=>{const S='.pic img:not(.bg):not(.ico)',first=new Map(),bad=new Set();let seen=0;
  const look=()=>document.querySelectorAll(S).forEach(i=>{const b=i.getBoundingClientRect();if(!i.offsetParent||b.width<20||b.bottom<=0||b.top>=innerHeight)return;
    if(!(i.complete&&i.naturalWidth>0))return;const now=performance.now();
    if(+getComputedStyle(i).opacity>=0.5){first.delete(i);return}
    if(!first.has(i))first.set(i,now);else if(now-first.get(i)>1000)bad.add(i)});
  const H=document.documentElement.scrollHeight,vh=innerHeight;
  for(let y=0;y<Math.min(H,24000);y+=vh){scrollTo(0,y);for(let k=0;k<7;k++){await new Promise(r=>setTimeout(r,50));look()}seen++}
  scrollTo(0,0);return {n:seen,bad:bad.size,eg:[...bad].slice(0,3).map(i=>((i.closest('section')||{dataset:{}}).dataset.k||'?')+' '+(i.currentSrc||i.src).split('/').pop().slice(0,20))}}"""

GAP_JS = """async()=>{const S='section.sec article.card,section.sec .wc,section.sec a.tape,.pk';
const cs=[...document.querySelectorAll(S)].map(c=>{const p=c.querySelector('.pic');return{c,p,i:p&&p.querySelector('img:not(.ico)')}}).filter(o=>o.i&&!o.c.classList.contains('nophoto')&&!o.p.matches('.icon,.none'));
const hid=new Set();cs.forEach(o=>{for(let e=o.c;e;e=e.parentElement)if(e.hidden)hid.add(e)});hid.forEach(e=>{e.hidden=false});
const wait=i=>new Promise(r=>{if(i.complete)return r();const t=setTimeout(r,8000);i.addEventListener('load',()=>{clearTimeout(t);r()},{once:true});i.addEventListener('error',()=>{clearTimeout(t);r()},{once:true})});
cs.forEach(o=>{o.i.loading='eager';if(o.i.dataset.src&&!o.i.src)o.i.src=o.i.dataset.src});
for(let k=0;k<cs.length;k+=60)await Promise.all(cs.slice(k,k+60).map(o=>wait(o.i)));
dispatchEvent(new Event('resize'));   // 予備を出すときと同じ（render.py の入れ替え）：FIT_JS が枠に合わせ直す
await new Promise(r=>setTimeout(r,600));
let unread=0,bad=0;const eg=[];
cs.forEach(o=>{const i=o.i,p=o.p;if(!i.complete||!i.naturalWidth){unread++;return}
 if(p.classList.contains('fill'))return;   // 枠いっぱいに切ってある（FIT_JS が合わせ直したあとで判る）
 if(!p.offsetParent&&!p.getClientRects().length){unread++;return}
 if(1-Math.min(i.clientWidth,i.clientHeight*i.naturalWidth/i.naturalHeight)/Math.max(1,p.clientWidth)>0.25){bad++;eg.length<3&&eg.push((o.c.className||o.c.tagName)+' '+i.currentSrc.slice(-40))}});
hid.forEach(e=>{e.hidden=true});
return{n:cs.length,bad,unread,eg}}"""


# 2026-11-01（連動の範囲）：loose / pkcut / pkv も同じ i.complete / offsetParent で、読み込み前・[hidden] の写真を飛ばしていた。
# st を数える前に全部の写真を読み込み・[hidden] の祖先を外し（RESTORE_JS で戻す）、数えた後に「測れた数 / 候補の数」を MEASURED_JS で出す。
LOADALL_JS = """async()=>{const L=[...document.querySelectorAll('section.sec img:not(.ico),.pk img:not(.ico)')];
const hid=new Set();L.forEach(i=>{for(let e=i;e;e=e.parentElement)if(e.hidden)hid.add(e)});hid.forEach(e=>{e.hidden=false});window.__hid=[...hid];
L.forEach(i=>{i.loading='eager';if(i.dataset.src&&!i.src)i.src=i.dataset.src});
const wait=i=>new Promise(r=>{if(i.complete)return r();const t=setTimeout(r,8000);i.addEventListener('load',()=>{clearTimeout(t);r()},{once:true});i.addEventListener('error',()=>{clearTimeout(t);r()},{once:true})});
for(let k=0;k<L.length;k+=60)await Promise.all(L.slice(k,k+60).map(wait));
dispatchEvent(new Event('resize'));await new Promise(r=>setTimeout(r,600));return L.length}"""
RESTORE_JS = "()=>{(window.__hid||[]).forEach(e=>{e.hidden=true});window.__hid=[]}"
# 候補 N・測れた M（loose は 1400 のみ）。M/N が MEASURED_MIN を下回れば ✗（取りこぼしを「0」と言わない）
MEASURED_JS = """()=>{const ok=i=>i&&i.complete&&i.naturalWidth;
const lc=innerWidth<=760?[]:[...document.querySelectorAll('article.hero,article.lead,article.wide')].filter(c=>c.querySelector('.pic img:not(.ico)')&&!c.classList.contains('nw')&&!c.classList.contains('dupd')&&!c.classList.contains('nxd')&&!c.querySelector('.pic').classList.contains('fill'));   /* 畳んだカード（L7）は候補でない */
const pc=[...document.querySelectorAll('section.sec .pic.fill img[data-e="s"]:not(.bg):not(.ico),section.sec .nx img[data-e="s"]:not(.whole)')];
const kc=[...document.querySelectorAll('.pk:not(.big):not(.nophoto)')];
return{loose:[lc.length,lc.filter(c=>{const p=c.querySelector('.pic');return ok(p.querySelector('img:not(.ico)'))&&p.offsetParent}).length],
pkcut:[pc.length,pc.filter(i=>ok(i)&&i.offsetParent).length],pkv:[kc.length,kc.filter(k=>k.offsetParent).length]}}"""
MEASURED_MIN = 0.9   # 0.75 では 4 分の 1 が測れなくても通った（2026-11-01）


def retryable(ex):
    """ライブ更新でページが入れ替わった（Execution context was destroyed）・網の切断は、やり直せば通る。"""
    s = str(ex)
    return any(k in s for k in ("Execution context was destroyed", "navigation", "ws_closed", "Target closed", "net::ERR"))


def measured_bad(m, lo=MEASURED_MIN):
    """候補のうち測れた割合が lo 未満の種類（loose / pkcut / pkv）を ✗ の文にして返す。候補 0 は問題なし。"""
    return [f"{k} を測れなかった：{n - got} / {n} 件（読み込み切れ・非表示のまま）" for k, (n, got) in m.items() if n and got < n * lo]

# 2026-11-01 並べ方の考え L1・L2（DESIGN_PRINCIPLES G）：カードの空白の割合。決まった升目で背をそろえると、中身の少ないカードの下が空く（ほかの注目ニュースで
# ハリー・ポッターの大きいカードの下が約 350px 空いた）。①壁（.wall）の列ごとに、一番低い列の底からの差が小さいか（空き面積 / 壁の面積）
# ②カードの枠の中で、中身の一番下から枠の下までの空き（枠の高さの 30% 超かつ 70px 超）のカードの数。わざと空ける休みは 1 画面に 1 か所までなので、
# ②は 1 版面あたり 2 枚まで許す（外れ値）。1400・390 とも数える（390 は 1 列なので①は 0）
HOLE_JS = """()=>{const out={wall:0,wallArea:0,wallPct:0,cards:0,wc:0,n:0,eg:[],gridHole:0,gridEg:[],gridSkip:0,noMas:0,noMasBig:0,older:0};
const vis=e=>e.offsetParent&&e.getClientRects().length&&(!e.checkVisibility||e.checkVisibility({contentVisibilityAuto:true,visibilityProperty:true}));   // 閉じた「もっと見る」（content-visibility で隠れる）は数えない
document.querySelectorAll('.wall').forEach(w=>{const cs=[...w.querySelectorAll(':scope>.wc')].filter(vis);if(cs.length<2)return;
 const wr=w.getBoundingClientRect(),lefts=[...new Set(cs.map(c=>Math.round(c.offsetLeft/20)))];
 if(lefts.length<2)return;
 const W=Math.max(...cs.map(c=>c.offsetTop+c.offsetHeight));let hole=0;
 lefts.forEach(l=>{const m=cs.filter(c=>Math.round(c.offsetLeft/20)===l||(c.offsetWidth>1.6*cs[cs.length-1].offsetWidth&&c.offsetLeft<l*20+10&&c.offsetLeft+c.offsetWidth>l*20+10));
  const b=Math.max(...m.map(c=>c.offsetTop+c.offsetHeight));hole+=(W-b)*(wr.width/lefts.length)});
 out.wall+=hole;out.wallArea+=W*wr.width});
out.wallPct=out.wallArea?Math.round(100*out.wall/out.wallArea):0;
// 記事の並びの空き（2026-11-01 L2。.grid＝版面の中の記事／.pkgrid＝気になるかも）：記事の外の空き（x を 16px ごとに縦に見て、記事と記事のあいだ・列の底が 40px 以上空いた所。ふつうのすき間は 28px）の面積が、並びの 2% を超えるものを数える。
// 数え方を緩めない（84px の空きを見逃した 100px への緩めは戻した）。2 記事の並び（大きい記事＋右 1 件）も測る。描かれていない記事がある並び（content-visibility）は測れないので gridSkip に数えて出す
const holeOf=(g,sel,label,inner)=>{if(!vis(g))return;const gr=g.getBoundingClientRect();
 const all=[...g.querySelectorAll(sel)],cs=all.filter(vis).map(c=>{const r=c.getBoundingClientRect();let b=0;(inner?[...c.querySelectorAll(inner)]:[...c.children]).forEach(k=>{if(getComputedStyle(k).position!=='absolute')b=Math.max(b,k.getBoundingClientRect().bottom)});   // 記事の中身の下（伸ばされた枠の下ではない。.pk は札〔.pkt〕の下）
  return {left:r.left,right:r.right,top:r.top,height:r.height,bottom:Math.min(r.bottom,(b||r.bottom)+(parseFloat(getComputedStyle(c).paddingBottom)||0))}});
 if(cs.length<2)return;if(cs.length<all.length||cs.some(r=>r.height<20||r.top<gr.top-4)){out.gridSkip++;return}
 const old=!!g.closest('.older');if(old)out.older++;   // 開いた「過去のニュース」の並びも測る（2026-11-02：ここが固定の行のまま 10〜20% 空いていた。閉じていた間は誰も測っていなかった）
 if(!g.querySelector(':scope>.mas')&&label!=='気になるかも'){out.noMas++;if(cs.length>=4)out.noMasBig++}   // mason が包まなかった並び。4 枚以上は積み上げに入るはずなので ✗
 const tail=g.querySelector(':scope>.mas')?(old?Math.max(...cs.map(r=>r.height)):160):80,top=Math.min(...cs.map(r=>r.top)),bot=Math.max(...cs.map(r=>r.bottom)),w=Math.max(...cs.map(r=>r.right))-Math.min(...cs.map(r=>r.left));let hole=0,mx=0;
 for(let x=Math.min(...cs.map(r=>r.left))+4;x<Math.max(...cs.map(r=>r.right));x+=16){const iv=cs.filter(r=>r.left-12<=x&&r.right+12>x).map(r=>[r.top,r.bottom]).sort((a,b)=>a[0]-b[0]);let y=top;
  iv.forEach(v=>{if(v[0]-y>=40){hole+=(v[0]-y)*16;mx=Math.max(mx,v[0]-y)}y=Math.max(y,v[1])});if(bot-y>=tail){hole+=(bot-y)*16;mx=Math.max(mx,bot-y)}}   // 最後の段の底のでこぼこは中身の高さの違い（80px 未満は数えない。積み上げ .mas は列の底が 1 枚分まで違うのがふつうなので 160px 未満。2026-11-02 mason）。記事と記事のあいだは 40px から
 const pct=100*hole/(w*(bot-top));if(pct>2){out.gridHole++;out.gridEg.length<4&&out.gridEg.push(label+' '+Math.round(pct)+'%・最大 '+Math.round(mx)+'px')}};
document.querySelectorAll('section.sec .grid').forEach(g=>holeOf(g,':scope>article.card,:scope>.side>article.card,:scope>.mas>article.card,:scope>.mas>.side>article.card',(g.closest('section.sec').dataset.k||'').slice(0,12)));
document.querySelectorAll('.picks .pkgrid').forEach(g=>holeOf(g,':scope>.pk','気になるかも','.pkt,:scope>*:not(a)'));
document.querySelectorAll('section.sec article.card,.wc').forEach(c=>{if(!vis(c)||c.classList.contains('mini'))return;out.n++;
 const r=c.getBoundingClientRect();let b=0;[...c.children].forEach(k=>{const s=getComputedStyle(k);if(s.position==='absolute'||!vis(k))return;b=Math.max(b,k.getBoundingClientRect().bottom)});
 const pb=parseFloat(getComputedStyle(c).paddingBottom)||0,blank=r.bottom-pb-b;
 if(blank>70&&blank>0.3*r.height){out.cards++;if(c.classList.contains('wc'))out.wc++;out.eg.length<3&&out.eg.push((c.dataset.k||c.className).slice(0,20)+' '+Math.round(blank)+'px')}});
return out}"""


# 2026-10-27：手元の回線（点検の箱のプロキシ）だけで開けない写真を ✗ に数えない。ブラウザで開けなかった写真を、
# ブラウザと同じ頭で取り直して画像が返れば「サイトの欠陥ではない」（AOL・Yahoo の写真が guest・test-a の版面の頭で ✗ になった）
FAIL_JS = ("window.__imgFail=[];addEventListener('error',function(e){var t=e.target;if(t&&t.tagName==='IMG'&&t.src&&!t.classList.contains('bg')){"
           "var s=t.closest('section.sec');window.__imgFail.push([s?s.dataset.k:'トップ',t.src])}},true);"
           # お客さまのページは me.html が document.open で書き替えるので、上の error の聞き手が消える（2026-10-27：test-a の頭が「写真なし」と
           # 数えられ、取り直せば開く写真まで ✗ になった）。document に付けた MutationObserver は残るので、外された写真の網址もここで拾う
           "new MutationObserver(function(ms){ms.forEach(function(m){m.removedNodes.forEach(function(n){if(n.nodeType!==1)return;"
           "var l=n.tagName==='IMG'?[n]:[].slice.call(n.querySelectorAll('img'));var s=m.target.closest&&m.target.closest('section.sec');"
           "l.forEach(function(i){if(i.src&&!i.classList.contains('bg'))window.__imgFail.push([s?s.dataset.k:'トップ',i.src])})})})}).observe(document,{childList:true,subtree:true})")
# 外れて DOM に残っている写真（document.open のあと error の聞き手が消えた分。MutationObserver は外された写真しか拾わない）も数える
FAILS_JS = ("(window.__imgFail||[]).concat([].slice.call(document.querySelectorAll('img:not(.bg)')).filter(function(i){return i.src&&i.complete&&!i.naturalWidth})"
            ".map(function(i){var s=i.closest('section.sec');return [s?s.dataset.k:'トップ',i.src]}))")
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


READY_JS = """()=>{const t=document.body?document.body.innerText.replace(/\\s+/g,'').length:0;return t>=100||!!document.querySelector('.startgo,.wl-mine .empty')}"""
SETTLE_S = 30   # 決まった待ちのあと、字が出るまで足す上限


def settle(pg):
    """待ちは回線しだいで足りない（--fast の 6 秒で設定 1400 が文字 6 のまま測られた）。決まった待ちのあと、字が出るまで最大 SETTLE_S 秒待ち直してから測る（出なければそのまま測って ✗）"""
    try:
        pg.wait_for_function(READY_JS, timeout=SETTLE_S * 1000)
    except Exception:  # noqa: BLE001
        pass


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
    settle(pg)
    if page == "settings.html" and WHO[who]:   # 2026-10-31：本人の設定ページに描き替わる途中の「待ち」の箱（.wl-wait）を素の箱と数えた。描き替わる（wl-own が出て箱が消える）まで最大 SETTLE_S 秒待ってから数える。それでも残れば本物の✗
        try:
            pg.wait_for_function("b=>!!document.querySelector('meta[name=\"wl-own\"]')&&![...document.querySelectorAll(b)].some(x=>x.offsetParent)", arg=BOXES, timeout=SETTLE_S * 1000)
        except Exception:  # noqa: BLE001
            pass
    hid = pg.evaluate(HIDDEN_JS) if not page else {"bad": 0, "eg": []}
    if not page:   # 2026-10-27：loading=lazy の写真は下までスクロールしないと読み込まれず、開けない写真（札）を数え損ねる。下まで読んでから数える
        for y in range(0, 40000, 800):
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(80)
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(3000)
    if not page:
        pg.evaluate(LOADALL_JS)   # 2026-11-01：loose / pkcut / pkv も全部読み込んでから数える
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
        tiny:[...document.querySelectorAll('section.sec img[data-e]')].filter(i=>i.complete&&i.naturalWidth>0&&i.naturalWidth<32&&i.naturalHeight<32).length,
        plates:document.querySelectorAll('.pic.icon,.pic.none').length,
        pkv:[...document.querySelectorAll('.pk:not(.big):not(.nophoto)')].filter(k=>k.offsetParent).map(k=>{const c=k.getBoundingClientRect(),p=k.querySelector('.pic').getBoundingClientRect(),o=parseFloat(getComputedStyle(k.querySelector('.pic')).getPropertyValue('--pko'))||0;return (p.height-o)/c.height}).filter(v=>v<0.45).length,
        pkcut:[...document.querySelectorAll('section.sec .pic.fill img[data-e="s"]:not(.bg):not(.ico),section.sec .nx img[data-e="s"]:not(.whole)')].filter(i=>{if(!i.offsetParent||!i.naturalWidth)return false;const b=i.getBoundingClientRect();return Math.abs(Math.log((i.naturalWidth/i.naturalHeight)/(b.width/b.height)))>=0.08&&!(+i.dataset.keep>=60)}).length,
        ph:[...document.querySelectorAll('img[data-e="s"],img[data-e="r"]')].map(i=>i.currentSrc||i.src).filter(u=>{try{return new URL(u).origin!==location.origin}catch(x){return false}}).reduce((a,u)=>{a[0]++;if(/[/]storage[/]v1[/]object[/]public[/]photos[/]/.test(u))a[1]++;return a},[0,0]),
        frames:document.querySelectorAll('section.sec .pic').length,
        tint:[...document.querySelectorAll('section.sec .pic')].filter(x=>x.querySelector('img[data-e="s"][src*="/object/public/photos/"]')).reduce((a,x)=>{a[0]++;if(/background/.test(x.getAttribute('style')||''))a[1]++;return a},[0,0]),
        empty:/新着なし/.test((document.querySelector('.poster .top')||{}).innerText||''),
        tofu:[...document.querySelectorAll('body *')].filter(x=>x.offsetParent&&![...x.childNodes].every(n=>n.nodeType!==3||!/[\u3000-\u9fff\uff00-\uffef]/.test(n.data))&&!/Noto Sans|Serif|Yusei/.test(getComputedStyle(x).fontFamily)&&!/^(SCRIPT|STYLE)$/.test(x.tagName)).map(x=>x.className||x.tagName).slice(0,3),
        hero:(p=>{if(!p)return false;const i=p.querySelector('img:not(.bg):not(.ico)');return p.matches('.icon,.none')||!i||!(i.complete&&i.naturalWidth>0)})(document.querySelector('.poster .top .pic')),
        sameStory:(c=>{document.querySelectorAll('a.lk[href],.nx a[href],.agenda li a[href]').forEach(a=>{if((a.offsetParent||a.closest('details'))&&!a.closest('.nxd,.dupd'))c[a.href]=(c[a.href]||0)+1});return Object.values(c).filter(v=>v>1).length})({}),   /* ページ全体（ポスター・ほかの注目・予定・各版面・次のニュース。2026-11-01 L7） */
        dup:[...document.querySelectorAll('[id]')].map(x=>x.id).filter((v,i,a)=>a.indexOf(v)!==i).slice(0,3),
        blur:document.querySelectorAll('img.bg').length,
        loose:innerWidth<=760?0:[...document.querySelectorAll('article.hero,article.lead,article.wide')].filter(c=>{const p=c.querySelector('.pic'),i=p&&p.querySelector('img:not(.ico)');return i&&i.complete&&i.naturalWidth&&p.offsetParent&&!c.classList.contains('nw')&&!p.classList.contains('fill')&&(i.naturalWidth/i.naturalHeight)<(p.clientWidth/p.clientHeight)*0.92}).length,
        sw:document.documentElement.scrollWidth})""", BOXES)
    meas = pg.evaluate(MEASURED_JS) if not page else {}
    gp = pg.evaluate(GAP_JS) if not page else {"n": 0, "bad": 0, "unread": 0, "eg": []}
    if not page:
        pg.evaluate(RESTORE_JS)
    if not page:   # 閉じた「過去のニュース」を開けて測り、測ったら閉じる（積み上げは開いたときに走る）
        pg.evaluate("document.querySelectorAll('details.older').forEach(d=>d.open=true)"); pg.wait_for_timeout(3500)
    hole = pg.evaluate(HOLE_JS) if not page else {"wallPct": 0, "cards": 0, "wc": 0, "n": 0, "eg": [], "gridHole": 0, "gridEg": []}
    if not page:
        pg.evaluate("document.querySelectorAll('details.older').forEach(d=>d.open=false)")
    near = [] if page else pg.evaluate(NEAR_JS)
    fails = pg.evaluate(FAILS_JS) if (st["nohead"] or st["heads"]) else []
    nohead = nohead_real(st["nohead"], fails) if st["nohead"] else []
    heads = nohead_real(sorted(set(st["heads"])), fails) if st["heads"] else []
    first = pg.evaluate(FIRST_JS)
    dom_lead = lead_outside_bad(pg.content()) if not page else []   # 2026-10-31：ログイン中の DOM（お客さま）にも同じ数え方
    covered = []
    if width <= 760:   # 2026-10-27：右下の札が一番下の字を隠す。下までスクロールして札の矩形と重なる字の要素を数える
        for _ in range(8):   # 写真が読み込まれて高さが伸びるので、本当の底に着くまで（伸びが止まるまで）くり返す
            pg.evaluate("window.scrollTo(0,document.documentElement.scrollHeight)")
            pg.wait_for_timeout(700)
            if pg.evaluate("innerHeight+scrollY>=document.documentElement.scrollHeight-2"):
                break
        covered = pg.evaluate(COVER_JS)
        pg.evaluate("window.scrollTo(0,0)")
    pg.screenshot(path=str(out / f"{who}-{page.split('.')[0] + '-' if page else ''}{width}x{height}.png"))
    bad = []
    bad += dom_lead
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
        if st.get("sameStory"):   # 2026-11-01 L7：同じ記事は 1 ページ（版面）に 1 回だけ（次のニュースと元のカードの二重・本番で 33 本）
            bad.append(f"同じ記事がページに 2 回以上：{st['sameStory']} 本")
        if st["dup"]:   # 2026-10-27：素の箱を 2 回描いて id mine・wl-addn が重なった（同じ id の部品を数える）
            bad.append("同じ id が 2 回：" + "・".join(st["dup"]))
        if not (st["mast"] and st["token"]):
            bad.append("題字・令牌がない")
        if st["sw"] > width:
            bad.append(f"横にはみ出す（{st['sw']}px）")
        if errors:
            bad.append("JS のエラー：" + " / ".join(errors[:2]))
        bad += cover_bad(covered)
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
    if not page and st["ph"][0] >= 20 and st["ph"][1] * 2 < st["ph"][0]:   # 2026-10-31：店長もお客さまも同じ写真の一時保管（主写真・ぼかし・ギャラリー・欲しい物）。半分も使われていない
        bad.append(f"写真 {st['ph'][0]} 枚のうち一時保管から出たのは {st['ph'][1]} 枚（半分未満）")
    bad += measured_bad(meas)   # 2026-11-01：測れた数 / 候補の数
    if st.get("pkcut"):   # 2026-11-01 小カード案 2：枠に合わせて切っている写真は、顔・題字が 6 割以上残る位置で切ったもの（data-keep）だけ
        bad.append(f"写真を主役を測らずに切っている（小さいカード・主写真・c3・mini・wc・tape すべて）{st['pkcut']} 枚")
    if st.get("pkv"):   # 2026-10-31：「気になるかも？」の小さいカードで写真の見える高さがカードの 45% 未満（帯のように細い）
        bad.append(f"小さいカードの写真が細い（見える高さ 45% 未満）{st['pkv']} 枚")
    if gp["bad"]:   # 2026-10-31 F-16 続き：全部の画像の場所（大・小のカード・壁・テープ・気になるかも）で、写真が枠の幅の 25% 超を空けたまま（空いた横を情報に使っていない）。1400 / 390 とも数える。2026-11-01：全候補を読み込んでから（GAP_JS）
        bad.append(f"写真の余白（空いた横が情報なし）：{gp['bad']} / {gp['n']} 枚 " + "・".join(gp["eg"]))
    if hole["wallPct"] > 8:   # 2026-11-01 L1・L2：壁の列の底がそろっていない（空き面積が壁の 8% 超）
        bad.append(f"ほかの注目ニュースの壁の下が空いている（空き {hole['wallPct']}%）")
    if hole.get("noMasBig"):   # 同じ壊れ方の見張り：積み上げに入らなかった 4 枚以上の並び（固定の行のまま空きが出る）
        bad.append(f"積み上げ（mason）に入らない 4 枚以上の並び：{hole['noMasBig']}")
    if hole["gridHole"]:   # 2026-11-01 L2：版面の中の記事の並びで、記事の外の空きが 3% 超の版面
        bad.append(f"記事の並びに空きがある：{hole['gridHole']} 並び（測った並び 過去のニュース {hole['older']}・mason 外 {hole['noMas']}） " + "・".join(hole["gridEg"]))
    if hole["wc"]:   # 同じく：ほかの注目ニュースの壁のカードは中身で高さが決まる（1 枚でも枠の 30% 超・70px 超が空いたら ✗）
        bad.append(f"壁のカードの下が空いている：{hole['wc']} 枚 " + "・".join(hole["eg"]))
    if hole["cards"] - hole["wc"] > 2:   # 版面の中のカード：同じく空き（枠の 30% 超・70px 超）が 3 枚以上
        bad.append(f"カードの下が空いている：{hole['cards']} / {hole['n']} 枚 " + "・".join(hole["eg"]))
    if gp["n"] and gp["unread"] > gp["n"] * 0.25:   # 読めない写真が多い（回線切れ）のに「余白 0」と言わない
        bad.append(f"写真の余白を測れなかった：{gp['unread']} / {gp['n']} 枚（読み込み切れ）")
    if st["blur"] or st["loose"]:   # 2026-10-31 F-16：ぼかしで余白を埋めない（img.bg 0）。大きいカードで写真が枠より細いのに枠を絞っていない（.nw なし）のも✗
        bad.append(f"写真の余白：ぼかし {st['blur']} 枚・枠を絞っていない大きいカード {st['loose']} 枚")
    if hid["bad"]:   # 2026-11-01：届いたのに 1 秒を超えて透明のまま（画面に入っているのに色の枠だけ）
        bad.append(f"写真が届いたのに出ない（透明のまま 1 秒超）{hid['bad']} 枚 " + "・".join(hid["eg"]))
    if st["sw"] > width:
        bad.append(f"横にはみ出す（{st['sw']}px）")
    bad += cover_bad(covered)
    bad += first_screen_bad(first)
    if st["tofu"]:   # 2026-10-26：数字の書体（Anton）に日本語の字がなく □□□ になった（「（日）」）
        bad.append("日本語の字が日本語の書体でない（□になる）：" + "・".join(map(str, st["tofu"])))
    if st["hero"]:   # 2026-10-26：ポスターの写真が読み込めていない
        bad.append("ポスターの写真が出ていない")
    if st["arts"] and st["empty"]:   # 2026-10-24：記事が 8 本あってもポスターが「直近 7 日は新着なし」（写真のある記事がない）
        bad.append(f"記事が {st['arts']} 本あるのにポスターが「新着なし」（写真 {st['pics']} 枚）")
    if heads:   # 2026-10-25：記事の枠が出典のアイコンの札（写真が出ない）。2026-10-27：版面の全部の記事に、さらにトップ（#front の article.wc）も。開けない写真は render.SWAP_JS が .nophoto に落とす
        bad.append(f"記事が札（写真が出ない。開けない写真は字だけの形に落とす）{len(heads)}：" + "・".join(heads[:4]))
    if st.get("tiny"):   # 2026-11-01：防盗链の小さい代用画像（<32px 角）が写真の枠に残っている＝FIT_JS が error を投げて次の候補へ替えるはずが動いていない（dota2 の頭）
        bad.append(f"小さい代用画像が写真の枠に残っている {st['tiny']}")
    if nohead:   # 2026-10-27：札は字だけの形に落ちても、版面の頭（大きい枠）が写真なしのままでは「頭に写真」の規則が守られていない（開けない写真を組むときに知らない。BACKLOG の [?] 呪術廻戦の頭）
        bad.append(f"版面の頭が写真なし（字だけの形）{len(nohead)}：" + "・".join(nohead[:4]))
    if st["tint"][0] and st["tint"][1] < st["tint"][0] * 0.95:   # 2026-10-31 写真 0.5 秒：置き場の写真の枠は色だけの下絵（style の background）を持つ
        bad.append(f"写真の枠に色の下絵がない {st['tint'][0] - st['tint'][1]}／{st['tint'][0]}")
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


# checkVisibility：閉じた <details> の中は箱があっても見えない
# ページの一番下で、右下の札（.wl-auth）の矩形に重なる字の要素（札・通知・固定の部品を除く）。0 が正しい
COVER_JS = """()=>{const f=document.querySelector('.wl-auth');if(!f)return [];const r=f.getBoundingClientRect();if(!r.width)return [];
 return [...document.querySelectorAll('body *')].filter(e=>!e.closest('.wl-auth,.wl-toast,.wl-live,.wl-gate,.wl-agree')&&[...e.childNodes].some(n=>n.nodeType===3&&n.data.trim())
  &&(!e.checkVisibility||e.checkVisibility({checkVisibilityCSS:true}))&&getComputedStyle(e).position!=='fixed').filter(e=>{const b=e.getBoundingClientRect();
  return b.width&&b.height&&b.left<r.right&&r.left<b.right&&b.top<r.bottom&&r.top<b.bottom}).slice(0,3).map(e=>(e.className||e.tagName)+':'+e.innerText.slice(0,12))}"""


def cover_bad(c):
    return [f"右下の札が一番下の字を隠す（{len(c)}：" + "・".join(c) + "）"] if c else []


DOCK_WIDTHS = (390, 560, 561, 700, 760, 761, 1000)   # 2026-11-01：札の境目（560|561・760|761）の両側と真ん中。既定の 1400/390 だけでは 561〜760 を見ない
DOCK_JS = """()=>{const b=document.querySelector('.wl-auth');if(!b)return null;const v=e=>e.checkVisibility?e.checkVisibility({checkVisibilityCSS:true}):!!e.offsetParent;
 const m=b.querySelector(':scope>.more');return {vis:[...b.children].filter(v).map(e=>e.classList.contains('more')?'more':(e.className||e.tagName)),
 exp:m?m.getAttribute('aria-expanded'):null,away:b.classList.contains('away'),has:!!m}}"""


def dock_bad(width, st, clicked=None, opened_scroll=None, closed_scroll=None):
    """札（.wl-auth）の子のうち見えるものが幅ごとの決まりどおりか。st/clicked は DOCK_JS の結果。
    ≤560・≥761：「⋯」は出ず、札は見える。561〜760：「⋯」だけ。押すと開き（aria-expanded=true・札が見える）、もう一度で閉じる。
    開いたまま下へ読み進めても札をしまわない（opened_scroll.away=False）・閉じていればしまう（closed_scroll.away=True）。"""
    if not st:
        return ["札（.wl-auth）がない"]
    bad, vis = [], st["vis"]
    if not 561 <= width <= 760:
        if "more" in vis:
            bad.append(f"{width}px に「⋯」が出ている（{vis}）")
        if not [x for x in vis if x != "more"]:
            bad.append(f"{width}px に札が見えない")
        return bad
    if vis != ["more"]:
        bad.append(f"{width}px の札は「⋯」だけのはず（見えるもの：{vis}）")
    if clicked is not None:
        if not [x for x in clicked["vis"] if x != "more"] or clicked["exp"] != "true":
            bad.append(f"{width}px で「⋯」を押しても開かない（{clicked['vis']}・expanded={clicked['exp']}）")
    if opened_scroll is not None and opened_scroll["away"]:
        bad.append(f"{width}px で「⋯」を開いたまま下へ読むと札ごとしまう")
    if closed_scroll is not None and not closed_scroll["away"]:
        bad.append(f"{width}px で閉じているのに下へ読んでも札をしまわない")
    return bad


DOCK_PAGES = ("settings.html", "wishlist.html", "heat.html", "themes.html", "terms.html", "admin.html")   # 2026-11-01：AUTH_JS を持つ home/ の他のページ（いままで点検が開くのはトップ／本人のページ 1 枚だけだった）
DOCK_PAGE_WIDTHS = (390, 700, 761)   # 他のページは ≤560・561〜760・≥761 の各 1 つ


def check_dock(pw, base, who, width, page=""):
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.goto(base + page, wait_until="domcontentloaded", timeout=60000)
    if WHO[who]:
        pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}", session(WHO[who]))
        pg.goto(base + page, wait_until="domcontentloaded", timeout=60000)
    st, last = None, None
    for _ in range(25):   # ログイン中は本人のページ（me.html）へ移るので、移り終えて札の見え方が 2 回続けて同じになるまで待つ
        pg.wait_for_timeout(1200)
        try:
            st = pg.evaluate(DOCK_JS)
        except Exception:  # noqa: BLE001  移動の途中
            continue
        if st and st["vis"] and st == last:
            break
        last = st
    clicked = opened = closed = None
    if st and 561 <= width <= 760 and st["has"]:
        def sc(y):
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(500)
            return pg.evaluate(DOCK_JS)
        scrolls = pg.evaluate("document.documentElement.scrollHeight>innerHeight+300")   # 門だけの短いページ（管理の訪問者）は下へ読めない＝しまう動きは見ない
        closed = sc(900) if scrolls else None   # 閉じたまま下へ → しまう
        sc(0)
        pg.click(".wl-auth > .more")
        clicked = pg.evaluate(DOCK_JS)
        opened = sc(900) if scrolls else None   # 開いたまま下へ → しまわない
        sc(0)
        pg.click(".wl-auth > .more")
        again = pg.evaluate(DOCK_JS)
        if again and again["vis"] != ["more"]:
            clicked = {**clicked, "exp": "false", "vis": again["vis"]}   # もう一度押しても閉じない
    b.close()
    return [f"{page}：{x}" if page else x for x in dock_bad(width, st, clicked, opened, closed)]


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
ADMIN_OLD_IDS = ["members", "term-panel", "tokens", "ov", "status", "editdiff", "backend", "emblem-ex", "procs", "queue", "items", "emblems", "votes", "libboards"]
ADMIN_OLD_H3 = ["いま待っているもの", "いま動いているもの", "次の実行", "リソース", "AI を使うか", "並列と制限", "待ち行列", "ログ", "版面ごとの状態", "「違う」の理由"]
ANON_OK_FN = {"board_visible"}   # 意図的な公開（boards の RLS が使う）
ADMIN_FILES = ["admin.html", "admin-now.html", "admin-boards.html", "admin-emblem.html", "admin-ai.html", "admin-system.html", "admin-members.html"]
ADMIN_JS = """() => ({ids:[...document.querySelectorAll('section.panel[id]')].map(s=>s.id),
 h3:[...document.querySelectorAll('h3.h3')].map(h=>(h.firstChild&&h.firstChild.textContent||'').trim()),
 nav:document.querySelectorAll('nav .admnav a').length,samples:document.querySelectorAll('#adm-samples a[href*="testground"]').length,sw:document.documentElement.scrollWidth,
 txt:document.body.innerText.length})"""


EYE_JS = """() => { const t = [...document.querySelectorAll('.emm-ph img.fv')];
 return {n: t.length, off: t.filter(i => !i.parentElement.querySelector('.emm-fl') && Math.abs(+i.dataset.eye - 0.3) > 0.05).length,
  short: t.filter(i => (i.parentElement.querySelector('.emm-fl') || {}).textContent === '下が足りない（目の線が合わない）').length} }"""


def rest_boards(tok=None, exact=False):
    """boards を REST で読む（tok なし＝ログインなし）。(名前の一覧, 本当の件数) を返す。"""
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    base, key = s["supabase_url"].rstrip("/"), s["supabase_key"]
    h = {"apikey": key, "Authorization": "Bearer " + (tok or key), "Prefer": "count=exact"}
    r = urllib.request.urlopen(urllib.request.Request(base + "/rest/v1/boards?select=id,name", headers=h), timeout=30)
    rows = json.loads(r.read())
    return [x["name"] for x in rows], int(r.headers.get("Content-Range", "0-0/0").split("/")[-1])


HTML_MAX_MB = 2.8   # 2026-10-31：2.6→2.8（色の下絵 1170 枚×31B＝36KB が増えた。倍に戻る検出が目的）。2026-10-30：店長のページ 4.1MB→2.1MB。画像 1 枚ごとの onerror が戻ると倍になるので、ここを超えたら ✗
IMG_MAX = 4500


def html_weight_bad(html):
    """最初に取る HTML の重さ・画像 1 枚ごとのハンドラ・最初の写真の eager を数える（2026-10-30 最初のニュースを速く）。✗ の一覧を返す。"""
    bad = []
    mb = len(html.encode("utf-8")) / 1e6
    if mb > HTML_MAX_MB:
        bad.append(f"HTML {mb:.1f}MB（上限 {HTML_MAX_MB}MB）")
    n = len(re.findall(r"<img\b[^>]*\bon(?:error|load)=", html))
    if n:
        bad.append(f"画像 1 枚ごとの onerror/onload が {n} 件（data-e に寄せる）")
    imgs = len(re.findall(r"<img\b", html))
    if imgs > IMG_MAX:
        bad.append(f"<img> {imgs} 枚（上限 {IMG_MAX}）")
    mains = re.findall(r'<img src="([^"]*)"[^>]*?data-e="s">', html)
    kept = sum("/storage/v1/object/public/photos/" in s for s in mains)
    if kept and kept * 2 < len(mains):   # 一時保管が動いているのに半分も使われていない（photo_store の取りこぼし・render の外れ）
        bad.append(f"主写真 {len(mains)} 枚のうち写真の一時保管から出たのは {kept} 枚（半分未満）")
    st = re.findall(r'<img src="[^"]*/storage/v1/object/public/photos/[^"]*"([^>]*?)data-e="s">', html)
    nosrc = sum("srcset=" not in x for x in st)
    if nosrc:   # 一時保管の幅 400 を置いても srcset で渡さなければ使われない（2026-10-31）
        bad.append(f"一時保管の主写真 {len(st)} 枚のうち srcset がないのが {nosrc} 枚")
    if 'fetchpriority="high"' not in html and 'data-e="s"' in html:
        bad.append("最初の写真に loading=eager / fetchpriority=high がない（LCP の先読み）")
    if 'rel="preload" as="image"' not in html and kept:
        bad.append("最初の主写真の <link rel=preload> が <head> にない（本文の読み取りを待たず取る）")
    return bad


SAMPLE_N = 16


def lead_photos(html):
    """版面ごとの先頭の記事の写真（本物の 800 とぼかしの 400）の網址。一時保管から出たものだけ、重複なし。"""
    out = []
    for sec in re.split(r"(?=<section\b[^>]*\bdata-k=)", html)[1:]:
        for m in re.finditer(r'<img (?:class="bg" )?src="([^"]*/storage/v1/object/public/photos/[^"]*)"', sec[:6000]):
            out.append(re.sub(r"&amp;", "&", m.group(1)))
    return list(dict.fromkeys(out))


def photo_cache_bad(html, get=None, n=SAMPLE_N):
    """一時保管の写真を GET したとき cache-control が public で max-age が 1 日以上（HEAD は private,no-cache に見えるので GET で）。
    最初の 1 枚だけでなく、全版面の先頭の写真（400 も 800 も）から n 枚を等間隔に（2026-10-31 写真 0.5 秒：The Mandalorian は最初の写真ではない）。
    max-age が 1 年未満（前に上げた分が 14 日のまま）も数える。"""
    urls = lead_photos(html)
    if not urls:
        return []
    def head(u):
        r = urllib.request.urlopen(urllib.request.Request(u, headers=BROWSER_HEADERS), timeout=30)
        return r.headers.get("cache-control", "")
    step = max(1, len(urls) // n)
    bad = []
    for u in urls[::step][:n]:
        cc = (get or head)(u)
        age = re.search(r"max-age=(\d+)", cc)
        if not ("public" in cc and age and int(age.group(1)) >= 31536000):
            bad.append(cc)
    return [f"一時保管の写真 {min(len(urls), n)} 枚のうち {len(bad)} 枚の cache-control が public・1 年でない（例「{bad[0]}」）"] if bad else []


def ahead_bad(html):
    """全版面の先頭の写真を先に取る JS（EMB_JS の ahead）があり、先頭の写真が一時保管から出ている版面の割合が半分以上か。"""
    bad = []
    if "const ahead" not in html:
        bad.append("版面の先頭の写真を先に取る JS（ahead）がない（目次から飛ぶとぼかしのまま数秒）")
    else:   # 2026-10-31 根：開始を window load に置くと Fast 3G で遅い／一度に多く取ると最初の画面の邪魔。その書き方に戻っていないか数える
        for need, why in (("slice(n, n + 3)", "3 版面ずつの 2 周（先頭→続き）"), ("timeout: 300", "暇待ちは 300ms の上限（1.5 秒ずつだと Fast 3G で 25 版面に 1 分近くかかった）"), ("hi ? 'high' : 'low'", "ahead は low・目次に近づいたときだけ high"), ("setTimeout(start, 2500)", "開始に 2.5 秒の上限")):
            if need not in html:
                bad.append(f"ahead の書き方が戻っている：{why}（{need}）がない")
        if re.search(r"addEventListener\('load',[^;]{0,120}(start|ahead)", html):
            bad.append("ahead の開始が window load 待ち（Fast 3G で目次から飛んだ先が遅れる）")
    secs = re.split(r"(?=<section\b[^>]*\bdata-k=)", html)[1:]
    secs = [s for s in secs if '<img src="' in s[:8000] and 'data-e="s"' in s[:8000]]
    kept = sum("/storage/v1/object/public/photos/" in (re.search(r'<img src="([^"]*)"[^>]*data-e="s"', s[:8000]) or [0, ""])[1] for s in secs)
    if secs and kept * 2 < len(secs):
        bad.append(f"先頭の写真が一時保管から出た版面 {kept}/{len(secs)}（半分未満）")
    return bad


def lead_outside(html):
    """(置き場の外に残る先頭の写真の版面 key, 例外で見逃した数)。先頭 = 各版面の最初の img[data-e="s"]。属性の順は問わない（描いたあとの DOM でも読める）。"""
    import hashlib
    import html as html_lib
    try:
        x = set(json.loads((ROOT / "state" / "photo_store.json").read_text(encoding="utf-8")).get("x", {}))
    except (OSError, ValueError):
        x = set()
    out, exempt = [], 0
    for s in re.split(r"(?=<section\b[^>]*\bdata-k=)", html)[1:]:
        tag = next((g for g in re.findall(r"<img\b[^>]*>", s[:12000]) if re.search(r'\bdata-e="s"', g)), None)
        m = tag and re.search(r'\bsrc="([^"]*)"', tag)
        if not m:
            continue
        u = html_lib.unescape(m.group(1))
        if "/storage/v1/object/public/photos/" in u or not u.startswith("http"):
            continue
        if re.search(r"\.(svg|gif|ico)(\?|$)", u, re.I) or hashlib.sha1(u.encode("utf-8")).hexdigest()[:16] in x:
            exempt += 1
            continue
        out.append(re.search(r'data-k="([^"]*)"', s).group(1))
    return out, exempt


def lead_outside_bad(html):
    """先頭の写真が置き場にも本站の pics/ にも無い版面を数える。0 でなければ ✗（2026-10-31 星巴克马克杯：原寸 jpg のまま Fast 3G で届かない）。
    店長の HTML だけでなくログイン中の DOM（test-a・b・c）にも同じ数え方（お客さまも同じ規則）。例外（縮められない）は SVG・GIF・ICO と photo_store.json の x。例外の数は ✓ の行に出す（隠さない）。"""
    out, _ = lead_outside(html)
    return [f"先頭の写真が置き場に無い版面 {len(out)} 件（{out[:4]}）。SVG・GIF・取れない分を除いても残る＝photo_store の置く順／取りこぼし"] if out else []


def check_public_leak(base):
    """公開の HTML（だれでも開ける管理ページなど）にお客さまだけの版面の名前が焼かれていない（HARNESS §2-5・BACKLOG：公開の場所にお客さまの中身を出さない）。
    お客さまだけの名前 ＝ test-a が読める版面 − ログインなしが読める版面。"""
    anon, _ = rest_boards()
    mine = set()
    for e in ("test-a", "test-b", "test-c", "test-d", "test-e"):   # お客さま全員（ログインできない人は数えない）
        try:
            mine |= set(rest_boards(session(e + "@example.com")["access_token"])[0])
        except urllib.error.HTTPError:
            pass
    only = sorted(n for n in mine - set(anon) if len(n) >= 3)
    # 公開の HTML 全部：docs/home/*.html（glob）と docs/ 直下の複製
    up = base.rstrip("/").rsplit("/", 1)[0] + "/"
    pages = [(base + f.name, f.name) for f in sorted((ROOT / "docs" / "home").glob("*.html"))]
    pages += [(up + f.name, "../" + f.name) for f in sorted((ROOT / "docs").glob("*.html"))]
    bad = []
    for url, f in pages:
        html = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_HEADERS), timeout=30).read().decode("utf-8", "replace")
        # 版面の名前としての出方（data-k・data-name・表の1マス）だけ数える。記事の題や BACKLOG の文に入った同じ字は版面ではない
        hit = [n for n in only if any(m in html for m in (f'data-k="{n}"', f'data-name="{n}"', f'<td>{n}</td>'))]
        if hit:
            bad.append(f"{f} にお客さまだけの版面の名前 {len(hit)} 件（{hit[:3]}）")
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    # 管理者用の RPC（admin_・board_ で始まる）は anon が実行できない。db/*.sql の関数を、ログインなしで引数ダミーで呼び、
    # 「permission denied」以外（＝関数まで届いた）を数える。board_visible は RLS の読みが使う意図的な公開
    dummy = {"text": "", "bigint": 0, "int": 0, "integer": 0, "jsonb": {}, "boolean": False}
    open_fn = []
    for f in sorted((ROOT / "db").glob("*.sql")):
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+public\.((?:admin|board)_\w+)\s*\(([^)]*)\)", f.read_text(encoding="utf-8")):
            fn = m.group(1)
            if fn in ANON_OK_FN or fn in open_fn:
                continue
            body = {}
            for arg in filter(None, (x.strip() for x in m.group(2).split(","))):
                nm, ty = arg.split()[:2]
                body[nm] = dummy.get(ty, "")
            try:
                journey_rpc(s["supabase_url"], s["supabase_key"], s["supabase_key"], fn, body)
                open_fn.append(fn)
            except urllib.error.HTTPError as ex:
                msg = ex.read().decode("utf-8", "replace")
                if "permission denied" not in msg and "PGRST202" not in msg:   # PGRST202 = 本番にまだ無い関数
                    open_fn.append(fn)
    if open_fn:
        bad.append(f"ログインなしで実行できる管理者用の関数 {len(open_fn)} 個（{open_fn}）")
    bad += check_customer_admin_rpc(s)
    return bad, len(only)


def _rpc_denied(s, tok, fn, body):
    """RPC を呼んで permission denied（実行権なし）か。True=denied・False=関数まで届いた（成功・別のエラー）。"""
    try:
        journey_rpc(s["supabase_url"], s["supabase_key"], tok, fn, body)
        return False
    except urllib.error.HTTPError as ex:
        msg = ex.read().decode("utf-8", "replace")
        return "permission denied" in msg or "42501" in msg


def check_customer_admin_rpc(s):
    """ログインしたお客さま（test-a〜e）が admin_ の関数から中身を読めない。名前が admin_ で始まる全部を db/*.sql から数える。
    ・引数なし（読む）：お客さまで呼んで空・エラーのみ
    ・引数あり（書き換え）：呼ばず、定義の is_admin() の守りを見る。守りのないものは名前で例外にせず、
      本番で anon・お客さまとも「permission denied」（実行権なし）であることを実際に呼んで確かめる（あとで grant されたら ✗）
    ・実際に試せたお客さまの数を数え、3 人に届かなければ ✗（ログインできず黙って通るのを防ぐ）。"""
    fns = {}
    for f in sorted((ROOT / "db").glob("*.sql")):
        for m in re.finditer(r"create\s+(?:or\s+replace\s+)?function\s+public\.(admin_\w+)\s*\(([^)]*)\)(.*?)\$\$\s*;", f.read_text(encoding="utf-8"), re.S | re.I):
            fns[m.group(1)] = (m.group(2).strip(), m.group(3))
    bad = []
    dummy = {"text": "", "bigint": 0, "int": 0, "integer": 0, "jsonb": {}, "boolean": False}

    def body_of(args):
        out = {}
        for arg in filter(None, (x.strip() for x in args.split(","))):
            nm, ty = arg.split()[:2]
            out[nm] = dummy.get(ty, "")
        return out
    reads = [fn for fn, (args, _) in fns.items() if not args]
    unguarded = [fn for fn, (args, body) in fns.items() if args and "is_admin()" not in body]
    leaks, tested, failed = [], [], []
    for e in ("test-a", "test-b", "test-c", "test-d", "test-e"):
        try:
            tok = session(e + "@example.com")["access_token"]
        except urllib.error.HTTPError:
            failed.append(e)
            continue
        tested.append(e)
        for fn in reads:
            try:
                r = journey_rpc(s["supabase_url"], s["supabase_key"], tok, fn, {}).strip()
            except urllib.error.HTTPError as ex:
                if ex.code in (401, 403, 404) or ex.code == 400 and "PGRST202" in ex.read().decode("utf-8", "replace"):
                    continue   # 実行権なし・本番にまだ無い関数
                leaks.append(f"{e}:{fn}:HTTP{ex.code}")   # 想定外のエラーは黙って通さない
                continue
            if r not in ("", "[]", "{}", "null"):
                leaks.append(f"{e}:{fn}")
        for fn in unguarded:
            if not _rpc_denied(s, tok, fn, body_of(fns[fn][0])):
                leaks.append(f"{e}:{fn}:守りなしで実行できる")
    for fn in unguarded:
        if not _rpc_denied(s, s["supabase_key"], fn, body_of(fns[fn][0])):
            leaks.append(f"anon:{fn}:守りなしで実行できる")
    if len(tested) < 3:
        bad.append(f"お客さまでログインできたのは {len(tested)} 人だけ（{tested}、できなかった {failed}）。3 人に届かないので点検にならない")
    if leaks:
        bad.append(f"お客さまが管理者用の関数から中身を読めた・実行できた {len(leaks)} 件（{leaks[:4]}）")
    print(f"  admin_ の関数 {len(fns)} 個（読む {len(reads)}・守りなし {unguarded}）× お客さま {len(tested)} 人を点検")
    return bad


def check_customer_admin_pages(pw, base, width):
    """お客さま（test-a）が管理ページの網址（docs/home/admin*.html 全部）を直に開いても、全ユーザーの中身が出ない：
    render.ADMIN_WHO の表の行が 0・ページの文字に他のお客さまの名前（test-b〜e）が 0・店長の入口を書いた「管理ページへ」のリンクが 0。"""
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    r_ = importlib.import_module("render")
    ses = session("test-a@example.com")
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    bad = []
    try:
        pg.goto(base, wait_until="domcontentloaded", timeout=60000)
        pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}", ses)
        pages = sorted(f.name for f in (ROOT / "docs" / "home").glob("admin*.html"))
        sels = sorted({row for _, _, row in r_.ADMIN_WHO})
        for f in pages:
            pg.goto(base + f, wait_until="networkidle", timeout=60000)
            pg.wait_for_timeout(2500)   # 読み込み後の RPC が返るのを待つ
            rows = pg.evaluate("sels=>sels.reduce((n,s)=>n+[...document.querySelectorAll('section:not([hidden]) '+s)].filter(e=>e.offsetParent).length,0)", sels)
            txt = pg.evaluate("document.body.innerText")
            names = [e for e in ("test-b", "test-c", "test-d", "test-e") if e in txt]
            if rows or names:
                bad.append(f"{f}：お客さま(test-a)に表の行 {rows}・他のお客さまの名前 {names}")
        pg.goto(base, wait_until="networkidle", timeout=60000)
        n = pg.evaluate("[...document.querySelectorAll('a[href*=\"admin\"]')].filter(a=>a.offsetParent||a.closest('[role=menu],.menu,nav')).length")
        if n:
            bad.append(f"お客さま(test-a)のページに管理ページへのリンク {n} 個")
    finally:
        b.close()
    print(f"  管理ページ {len(pages)} 枚 × お客さま test-a を点検")
    return bad


# お客さまが管理ページの網址を直に開いたとき：門が出る・全ユーザーの行が 0・メニューに管理の入口がない（BACKLOG 2026-10-31 r2）
ROWS_JS = """() => ({gate: !!document.querySelector('.wl-gate'), gateTxt: (document.querySelector('.wl-gate')||{}).innerText||'',
 gateOn: document.documentElement.dataset.gate,
 rows: document.querySelectorAll('#wl-members tr[data-mail], [id^="wl-lib"] tr, [id^="wl-lib"][data-n]').length,
 vis: [...document.querySelectorAll('body>*:not(.wl-auth):not(.wl-gate):not(.wl-toast):not(script):not(style)')].filter(e=>e.offsetParent!==null&&e.getBoundingClientRect().height>20).length,
 menu: document.querySelectorAll('.wl-auth [data-go="admin"], .wl-auth a[href*="admin"]').length,
 user: !!document.querySelector('.wl-auth .menu')})"""
CUSTOMER_PAGES = ("test-a", "test-c")


def check_customer_admin_gate(pw, base, width):
    """test-a・test-c でログインして admin*.html 7 枚を直に開く。門（.wl-gate）が出て、全ユーザーの行（#wl-members・#wl-lib*）が 0、
    見える中身が門だけ、右上のメニューに管理の入口がない。トップの最初の画面のメニューも。門が出ない（enforce が外れた）なら ✗。"""
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    bad = []
    for who in CUSTOMER_PAGES:
        try:
            ses = session(WHO[who])
        except urllib.error.HTTPError:
            bad.append(f"{who} がログインできない（点検できていない）")
            continue
        for f in ["index.html"] + ADMIN_FILES:
            pg = b.new_page(viewport={"width": width, "height": 900})
            pg.goto(base, wait_until="domcontentloaded", timeout=60000)
            pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}", ses)
            pg.goto(base + (f if f != "index.html" else ""), wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(5000)   # お客さまの最初の画面は document.open で書き替わる。落ち着いてから札を探す
            try:
                pg.wait_for_selector(".wl-auth .menu", state="attached", timeout=30000)
            except Exception:  # noqa: BLE001
                pass
            if f != "index.html":
                try:
                    pg.wait_for_selector(".wl-gate", timeout=20000)
                except Exception:  # noqa: BLE001
                    pass
            pg.wait_for_timeout(2500)   # 門の裏で RPC が走っても行が描かれないことを見る
            st = pg.evaluate(ROWS_JS)
            pg.close()
            tag = f"{who} {f} {width}px"
            if not st["user"]:
                bad.append(f"{tag} ログインの札が出ていない（点検できていない）")
            if st["menu"]:
                bad.append(f"{tag} メニューに管理の入口 {st['menu']} 個")
            if f == "index.html":
                continue
            if not st["gate"] or st["gateOn"] != "1" or "店長だけ" not in st["gateTxt"]:
                bad.append(f"{tag} 門が出ない（管理ページの中身が見える）")
            if st["rows"]:
                bad.append(f"{tag} 全ユーザーの行・件数が {st['rows']} 個 DOM にある")
            if st["vis"]:
                bad.append(f"{tag} 門のほかに見える中身 {st['vis']} 個")
    b.close()
    return bad


def check_admin_coverage(pw, base, width):
    """管理ページ②版面（店長でログイン）に出る版面の数＝ライブラリの版面の数（HARNESS §2-5）。店長の合言葉が要る：
    UX_ADMIN_EMAIL・UX_ADMIN_PASSWORD（Actions の Secrets）。なければ None（未確認。✓ とは言わない）。"""
    em, pw_ = os.environ.get("UX_ADMIN_EMAIL"), os.environ.get("UX_ADMIN_PASSWORD")
    if not (em and pw_):
        return None
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    k, u = s["supabase_key"], s["supabase_url"].rstrip("/")
    ses = json.loads(urllib.request.urlopen(urllib.request.Request(
        u + "/auth/v1/token?grant_type=password", data=json.dumps({"email": em, "password": pw_}).encode(),
        headers={"apikey": k, "Content-Type": "application/json"}), timeout=30).read())
    ses["expires_at"] = int(time.time()) + int(ses.get("expires_in", 3600))
    want = rest_boards(ses["access_token"])[1]
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.goto(base, wait_until="domcontentloaded", timeout=60000)
    pg.evaluate("s=>{localStorage.setItem('wl-auth',JSON.stringify(s));localStorage.setItem('wl-user',JSON.stringify({name:s.user.email}));}", ses)
    pg.goto(base + "admin-boards.html", wait_until="networkidle", timeout=60000)
    pg.wait_for_selector("#wl-libboards[data-n]", state="attached", timeout=30000)
    got = pg.evaluate("[+document.getElementById('wl-libboards').dataset.n, document.querySelectorAll('#wl-libboards tr[data-id]').length]")
    bad = [] if got[0] == want and got[1] == want else [f"ライブラリの版面 {want} に対して管理ページ②は {got[0]}（行 {got[1]}）"]
    # ③エンブレムも同じ数（店長の版面＋ライブラリで足した版面。店長の版面と同じ名前は札 1 つ）：札の数 ≥ ライブラリの版面の数（店長の版面の名前が重なる分だけ減る）
    pg.goto(base + "admin-emblem.html", wait_until="networkidle", timeout=60000)
    pg.wait_for_selector(".emm-boards[data-lib]", state="attached", timeout=30000)
    em = pg.evaluate("[+document.querySelector('.emm-boards').dataset.lib, document.querySelectorAll('.emm-bt').length]")
    if em[0] != want or em[1] < want:
        bad.append(f"ライブラリの版面 {want} に対して管理ページ③は読んだ {em[0]}・札 {em[1]}")
    pg.wait_for_selector("#wl-libstate[data-n]", state="attached", timeout=30000)
    ls = pg.evaluate("[+document.getElementById('wl-libstate').dataset.n, document.querySelectorAll('#wl-libstate tr[data-id]').length]")
    if ls != [want, want]:
        bad.append(f"ライブラリの版面 {want} に対して管理ページ③の版面ごとの状態は {ls[0]}（行 {ls[1]}）")
    # 中身：各行の人数・小元素の枚数・状態の札が boards.config と一致（人数 0・失敗・まだ の版面も）
    s0 = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    brs = json.loads(urllib.request.urlopen(urllib.request.Request(
        s0["supabase_url"].rstrip("/") + "/rest/v1/boards?select=id,followers,config",
        headers={"apikey": s0["supabase_key"], "Authorization": "Bearer " + ses["access_token"]}), timeout=30).read())
    cells = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#wl-libstate tr[data-id]')].map(r=>[r.dataset.id,[...r.cells].slice(1,4).map(c=>c.textContent).concat([...r.querySelectorAll('[data-k]')].map(c=>c.textContent))]))")
    lab = {"ok": "済", "running": "待ち", "failed": "失敗"}
    for b in brs:
        c = b.get("config") or {}
        n = len(c.get("emblem") or [])
        st = (c.get("emblem_state") or {}).get("state")
        w = lab.get(st, "—" if n else "まだ")
        g = cells.get(str(b["id"]))
        if not g or g[0] != str(b.get("followers") or 0) or g[1] != str(n) or not g[2].startswith(w):
            bad.append(f"③の版面ごとの状態：版面 {b['id']} は 人数・枚数・状態 {g}、本物は {b.get('followers') or 0}・{n}・{w}")
        elif len(g) < 5 or not g[3] or (g[4] == "まだ") != (not c.get("theme")):
            bad.append(f"③の版面ごとの状態：版面 {b['id']} の記事・設計の列が本物（theme {bool(c.get('theme'))}）と合わない {g[3:]}")
    pg.goto(base + "admin-ai.html", wait_until="networkidle", timeout=60000)
    pg.wait_for_selector("#wl-libedit[data-n]", state="attached", timeout=30000)
    ae = pg.evaluate("+document.getElementById('wl-libedit').dataset.n")
    if ae != want:
        bad.append(f"ライブラリの版面 {want} に対して管理ページ④は {ae}")
    # ④の行に、ライブラリの版面の名前が 1 つ残らず出る（お客さまの版面。例：test-a のフリーレン）＋「全員／ユーザーを選ぶ」の切り替えで絞れる
    names = set(pg.evaluate("[...document.querySelectorAll('#wl-libedit tr[data-id] td:first-child')].map(x=>x.textContent)"))
    miss = [n for n in rest_boards(ses["access_token"])[0] if n not in names]
    if miss:
        bad.append(f"管理ページ④に出ない版面 {len(miss)} 個（{miss[:5]}）")
    # ②全アカウントの投票：行は follows のアカウントを 1 つ残らず含み、店長（test1）の 👍👎 が 0 でない（feedback は店長の分が一番多い）
    pg.goto(base + "admin-boards.html", wait_until="networkidle", timeout=60000)
    pg.wait_for_selector("#wl-libvotes[data-n]", state="attached", timeout=30000)
    vt = pg.evaluate("[...document.querySelectorAll('#wl-libvotes tr[data-id]')].map(r=>[r.dataset.id,+r.cells[1].textContent,+r.cells[2].textContent])")
    fl0 = json.loads(urllib.request.urlopen(urllib.request.Request(
        yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]["supabase_url"].rstrip("/") + "/rest/v1/follows?select=account",
        headers={"apikey": yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]["supabase_key"], "Authorization": "Bearer " + ses["access_token"]}), timeout=30).read())
    gone = sorted({f["account"] for f in fl0} - {r[0] for r in vt})
    if gone:
        bad.append(f"管理ページ②の投票に出ないアカウント {len(gone)} 個（{gone[:5]}）")
    if not any(r[0] == "test1" and r[1] + r[2] > 0 for r in vt):
        bad.append(f"管理ページ②の投票に店長（test1）の 👍👎 が 0：{vt[:3]}")
    # ②全アカウントの篇幅・写真・依頼：行は follows のアカウントを 1 つ残らず含む（言語の人数の行もある）
    pg.wait_for_selector("#wl-libaccts[data-n]", state="attached", timeout=30000)
    ac = pg.evaluate("[...document.querySelectorAll('#wl-libaccts tr[data-id]')].map(r=>r.dataset.id)")
    gone = sorted({f["account"] for f in fl0} - set(ac))
    if gone or not pg.evaluate("/\\d/.test(document.querySelector('#wl-libaccts p').textContent)"):
        bad.append(f"管理ページ②の篇幅・写真・依頼に出ないアカウント {len(gone)} 個（{gone[:5]}）または言語の人数なし")
    nc = pg.evaluate("(()=>{const n=document.querySelectorAll('#wl-libaccts thead th').length;return [n,[...document.querySelectorAll('#wl-libaccts tr[data-id]')].filter(r=>r.cells.length!==n).length]})()")
    if not nc[0] or nc[1]:
        bad.append(f"管理ページ②の全アカウント表で、列の数（見出し {nc[0]}）と合わない行 {nc[1]}")
    # 値の照合（数があるだけで通さない）：follows の本物から account ごとの 置いた板块・小分類つき・見たい種類・乗換駅つき を数え、画面の表と合わせる。
    # ＋置き方・関注項の中身の表（#wl-libplace）は follows の行と 1 行ずつ 板块・並び・篇幅・小分類・見たい種類・乗換駅 が合う
    s1 = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    fx = json.loads(urllib.request.urlopen(urllib.request.Request(
        s1["supabase_url"].rstrip("/") + "/rest/v1/follows?select=account,board_id,section,pos,size,subs,media,also",
        headers={"apikey": s1["supabase_key"], "Authorization": "Bearer " + ses["access_token"]}), timeout=30).read())
    exp = {}
    for f in fx:
        e = exp.setdefault(f["account"], [set(), 0, 0, 0])
        e[0].add(f.get("section")); e[1] += bool(f.get("subs")); e[2] += bool(f.get("media")); e[3] += bool(f.get("also"))
    cells = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#wl-libaccts tr[data-id]')].map(r=>[r.dataset.id,['sec','subs','media','also'].map(k=>+r.querySelector('[data-k='+k+']').textContent)]))")
    for a_, e in exp.items():
        w = [len(e[0]), e[1], e[2], e[3]]
        if cells.get(a_) != w:
            bad.append(f"②全アカウント表の {a_}：置いた板块・小分類・見たい種類・乗換駅 は {cells.get(a_)}、follows の本物は {w}")
    pg.wait_for_selector("#wl-libplace[data-n]", state="attached", timeout=30000)
    pl = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#wl-libplace tr[data-id]')].map(r=>[r.dataset.id+'/'+r.dataset.b,Object.fromEntries([...r.querySelectorAll('[data-k]')].map(c=>[c.dataset.k,c.textContent]))]))")
    if len(pl) != len(fx):
        bad.append(f"②置き方・関注項の表 {len(pl)} 行、follows は {len(fx)} 行")
    for f in fx:
        g = pl.get(f"{f['account']}/{f['board_id']}")
        if not g or g.get("sec") != (f.get("section") or "—") or g.get("pos") != str(f.get("pos")) or g.get("size") != (f.get("size") or "—") \
                or (g.get("subs") == "—") == bool(f.get("subs")) or (g.get("also") == "—") == bool(f.get("also")) or (g.get("media") == "全部") == bool(f.get("media")):
            bad.append(f"②置き方・関注項の表：{f['account']}/{f['board_id']} は {g}、follows は {f.get('section')}・{f.get('pos')}・{f.get('size')}")
            break
    # 区画ごとの「全員／ユーザーを選ぶ」（render.ADMIN_WHO の全部）：切り替えがある・選ぶと行が follows の通りに絞れる・全員に戻すと元の数
    sys.path.insert(0, str(ROOT / "scripts"))
    import render as _r
    s = yaml.safe_load((ROOT / "items.yaml").read_text(encoding="utf-8"))["settings"]
    fl = json.loads(urllib.request.urlopen(urllib.request.Request(
        s["supabase_url"].rstrip("/") + "/rest/v1/follows?select=account,board_id",
        headers={"apikey": s["supabase_key"], "Authorization": "Bearer " + ses["access_token"]}), timeout=30).read())
    mine = {}
    for f in fl:
        mine.setdefault(f["account"], set()).add(f["board_id"])
    acc = next((a for a in sorted(mine) if a != "test1"), None)
    for page, sec, row in _r.ADMIN_WHO:
        pg.goto(base + page, wait_until="networkidle", timeout=60000)
        host = "#wl-" + sec if sec.startswith("lib") else ".emm-boards"
        try:
            pg.wait_for_selector(f"{host} [data-who], [data-who]", state="attached", timeout=30000)
        except Exception:
            bad.append(f"管理ページ {page} の区画 {sec} に「全員／ユーザーを選ぶ」がない")
            continue
        sel = "[data-who]" if host == ".emm-boards" else f"{host} [data-who]"
        rows = f"{host} {row}" if host != ".emm-boards" else row
        total = pg.evaluate(f"document.querySelectorAll({json.dumps(rows)}).length")
        if acc is None:
            continue
        pg.select_option(sel, acc)
        shown = pg.evaluate(f"[...document.querySelectorAll({json.dumps(rows)})].filter(x=>!x.hidden).length")
        want_n = 1 if sec in ("libvotes", "libaccts") else len(mine[acc])   # 投票はアカウントごとに 1 行
        if shown != want_n or shown >= total:
            bad.append(f"{page} の区画 {sec}：{acc} を選ぶと {shown} 行（期待 {want_n}・全体 {total}）")
        pg.select_option(sel, "")
        back = pg.evaluate(f"[...document.querySelectorAll({json.dumps(rows)})].filter(x=>!x.hidden).length")
        if back != total:
            bad.append(f"{page} の区画 {sec}：全員に戻すと {back} 行（全体 {total}）")
    b.close()
    return bad


def check_admin_pages(pw, base, width, out):
    """管理ページのトップと 6 つの別ページ：開ける・切り替え（7 つのリンク）・横にはみ出さない・JS のエラーなし・前の欄が全部どこかにある。"""
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    sys.path.insert(0, str(ROOT / "scripts"))
    import render as _r
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
        if f == "admin-ai.html":   # 画面の文と実際の範囲：お客さまの版面を編集する処理が無い間は「同じ編集で作る」と言わない
            htm = pg.content()
            if "同じ編集で作る" in htm or "全アカウント分の合計です" in htm:
                bad.append(f"{f} ④の tokens の注記が事実とずれている（お客さまの版面はまだ編集されない）")
            elif "店長の inbox の分だけ" not in htm:
                bad.append(f"{f} ④の tokens に「店長の分だけ」の注記がない")
        miss = pg.evaluate("""(ids)=>ids.filter(i=>{const s=document.getElementById(i);return s&&!s.querySelector('[data-scope=mine]')})""",
                           [k for k, v in _r.ADMIN_WHO_NO.items() if v.startswith("店長の") and k in {i for fn, _, _, _, ids in _r.ADMIN_PAGES if fn == f for i in ids}])
        if miss:   # 「店長の分だけ」の区画は、画面に範囲の注記がある
            bad.append(f"{f} 店長の分だけの区画に注記がない：{','.join(miss)}")
        if f == "admin-emblem.html":   # E16：札のない小元素の目の線が枠の上から 30% ±5% を外れる（emblem_face.view。札 short は別の写真に替える対象）
            ey = pg.evaluate(EYE_JS)
            if ey["off"]:
                bad.append(f"{f} E16 目の線がずれた小元素 {ey['off']} 枚（{ey['n']} 枚中。札 short {ey['short']} 枚は別）")
            print(f"  [管理ページ小元素] 顔そろえの置き方 {ey['n']} 枚・目の線ずれ {ey['off']}・札 short {ey['short']}")
        cov = []
        if width <= 760:   # 2026-10-27：管理ページ 7 枚も右下の札が一番下の字を隠さない（最初の画面・設定と同じ規則）
            for _ in range(6):
                pg.evaluate("window.scrollTo(0,document.documentElement.scrollHeight)")
                pg.wait_for_timeout(500)
                if pg.evaluate("innerHeight+scrollY>=document.documentElement.scrollHeight-2"):
                    break
            cov = pg.evaluate(COVER_JS)
            pg.evaluate("window.scrollTo(0,0)")
        pg.screenshot(path=str(out / f"{f[:-5]}-{width}.png"))
        pg.close()
        bad += [f"{f} {m}" for m in cover_bad(cov)]
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


FX_JS_CHECK = """async()=>{const out=[],W=document.documentElement.clientWidth,H=innerHeight,q=n=>[...n];
const pos={'左上':[2,2],'右上':[W-30,2],'真ん中':[W/2,H/2],'左下':[2,H-30]};
for(const name of window.likeFx.names){const booms=[];
 for(const [lab,[x,y]] of Object.entries(pos)){const b=document.createElement('button');b.style.cssText='position:fixed;width:28px;height:28px;left:'+x+'px;top:'+y+'px;z-index:1';document.body.appendChild(b);
  const n0=document.querySelectorAll('.boom').length;window.likeFx(b,1,name,null);const bm=[...document.querySelectorAll('.boom')].slice(n0);if(bm[0])booms.push([lab,bm[0],b]);}
 for(const t of [150,350,600,850]){await new Promise(r=>setTimeout(r,t===150?150:t===350?200:t===600?250:250));
  for(const [lab,bm,b] of booms){const parts=[bm.firstElementChild,...bm.querySelectorAll('.fx-sfx svg,.fx-sfx span,.fx-strip,.fx-stripe')];
   for(const e of parts){if(!e||!e.isConnected)continue;if(+getComputedStyle(e).opacity<.05)continue;const r=e.getBoundingClientRect();if(!r.width)continue;
    const o=Math.max(0,-r.left,r.right-W,-r.top);if(o>1)out.push(name+'／'+lab+'／'+(e.className.baseVal??e.className)+' '+Math.round(o)+'px');}}}
 booms.forEach(([l,bm,b])=>b.remove());await new Promise(r=>setTimeout(r,300));}
return [...new Set(out)];}"""


def check_fx_edge(pw, base, width):
    """👍 の演出（likefx 20 種）の札・字・👍 本体が、端の 👍（左上・右上・左下）を押しても画面の外へ切れないか。
    テーマ見本ページで likeFx を直接押し、0.15〜0.85 秒の間に見える部品の矩形を測る（粒・光・輪は除く）。2026-10-29 ユーザー指摘「イイネ！が左へ切れる」。"""
    b = pw.chromium.launch(channel=os.environ.get("UX_CHANNEL") or None)
    pg = b.new_page(viewport={"width": width, "height": 900})
    pg.goto(base + "themes.html", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_function("()=>window.likeFx", timeout=30000)
    pg.wait_for_timeout(1500)
    bad = pg.evaluate(FX_JS_CHECK)
    b.close()
    return [f"演出が画面の外へ切れる {len(bad)} 件（{'、'.join(bad[:4])}）"] if bad else []


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


def runs_for(who, widths, fast=False):
    """人ごとの (幅, ページ, 高さ)。殻のページ（shell_pages＝AUTH_JS の「index・settings 以外」の枝）は guest を含む全員・全幅、
    0 個の人（test-c）は 390 幅の小さい端末（高さ 667・740）でも、最初の画面・設定・欲しい物・話題度（2026-10-27）。"""
    runs = [(int(w), pg, 900) for pg in ("", "settings.html") for w in widths]
    if fast:
        return runs   # 札・枠組みだけ：最初の画面と設定（殻のページ・小さい端末は ふだんの点検）
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
    ap.add_argument("--fast", action="store_true", help="札・枠組みだけを速く（小元素 off・待ち 6 秒・最初の画面と設定だけ）")
    ap.add_argument("--part", default="all", choices=("all", "who", "global"),
                    help="分けて走らせる用：who＝人ごとの画面・札の境目だけ／global＝管理ページ・HTML・公開の漏れなど人に依らない点検だけ（harness/ux_all.py が使う）")
    ap.add_argument("--journey", action="store_true", help="1 日通し（空のアカウントで押して通す）だけを走らせる")
    a = ap.parse_args(argv)
    if a.fast:
        a.emb = "off"
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
        for who in (a.who.split(",") if a.part != "global" else []):
            runs = runs_for(who, a.widths.split(","), a.fast)
            for w, page, h in runs:
                for tries in range(3):   # 2026-11-01：ライブ更新の再読み込みで 'Execution context was destroyed'・回線切れは測りそこない。2 回までやり直す
                    try:
                        st, bad = check(pw, a.base, who, w, out, page, a.emb if h == 900 else "off", h, FAST_S if a.fast else WATCH_S if h == 900 else 10)
                        break
                    except Exception as ex:  # noqa: BLE001
                        st, bad = {}, [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
                        if not retryable(ex):
                            break
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + f"{who}{' ' + page.split('.')[0] if page else ''} {w}x{h}px：" + ("、".join(bad) if bad else
                      f"版面 {st.get('secs')}・記事 {st.get('arts')}・写真 {st.get('pics')}・本人のページ {'はい' if st.get('own') else 'いいえ'}"))
        for who in [x for x in a.who.split(",") if x in ("guest", "test-a", "test-b") and a.part != "global"]:   # 札の境目（既定の幅では見ない 561〜760 を含む）
            bad = []
            for w in DOCK_WIDTHS:
                try:
                    bad += check_dock(pw, a.base, who, w)
                except Exception as ex:  # noqa: BLE001
                    bad.append(f"{w}px 開けなかった（{type(ex).__name__}: {str(ex)[:100]}）")
            for pgname in (DOCK_PAGES if who == "guest" else DOCK_PAGES[:1] if who == "test-a" else ()):   # 他のページ：訪問者は 5 枚・test-a は設定（本人のページへ移る道）
                for w in DOCK_PAGE_WIDTHS:
                    try:
                        bad += check_dock(pw, a.base, who, w, pgname)
                    except Exception as ex:  # noqa: BLE001
                        bad.append(f"{pgname} {w}px 開けなかった（{type(ex).__name__}: {str(ex)[:100]}）")
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"{who} 札の境目 {'/'.join(map(str, DOCK_WIDTHS))}px（＋他のページ {len(DOCK_PAGES) if who == 'guest' else 1 if who == 'test-a' else 0} 枚 × {'/'.join(map(str, DOCK_PAGE_WIDTHS))}px）：" + ("、".join(bad) if bad else "幅ごとの札・「⋯」の開け閉め・しまう動きどおり"))
        if a.part == "who":
            print(f"点検：✗ {fails} 件")
            return 1 if fails else 0
        for w in a.widths.split(","):
            try:
                bad = check_admin(pw, a.base, int(w), out)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"管理ページ 全体の構成 {w}px：" + ("、".join(bad) if bad else "崩れなし"))
            if a.fast:
                continue   # 管理ページ 7 枚は ふだんの点検
            try:
                bad = check_admin_pages(pw, a.base, int(w), out)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"管理ページ 7 枚 {w}px：" + ("、".join(bad) if bad else f"欄 {len(ADMIN_OLD_IDS)}・小見出し {len(ADMIN_OLD_H3)} が全部ある"))
        try:   # HTML の重さ・画像 1 枚ごとのハンドラ（ログインなしで取れる店長のページ）
            html = urllib.request.urlopen(urllib.request.Request(a.base, headers=BROWSER_HEADERS), timeout=30).read().decode("utf-8", "replace")
            bad = html_weight_bad(html) + photo_cache_bad(html) + ahead_bad(html) + lead_outside_bad(html)
            n_ex = lead_outside(html)[1]
        except Exception as ex:  # noqa: BLE001
            bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
        try:   # 本番の入口・本体の頁に、描画を止める Web フォントの link が残っていない（生成が古いままだと残る）
            root = a.base.rstrip("/").rsplit("/", 1)[0] + "/"
            blk = {}
            for pg_ in (root, a.base, a.base.rstrip("/") + "/wishlist.html", a.base.rstrip("/") + "/heat.html", a.base.rstrip("/") + "/settings.html"):
                h_ = urllib.request.urlopen(urllib.request.Request(pg_, headers=BROWSER_HEADERS), timeout=30).read().decode("utf-8", "replace")
                if render.blocking_font_links(h_):
                    blk[pg_] = render.blocking_font_links(h_)
            bad = [f"止める font link：{blk}"] if blk else []
        except Exception as ex:  # noqa: BLE001
            bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
        fails += bool(bad)
        print(("✗ " if bad else "✓ ") + "Web フォントが描画を止めない（入口＋本体 4 頁）：" + ("、".join(bad) if bad else "止める link 0 件"))
        fails += bool(bad)
        print(("✗ " if bad else "✓ ") + "最初に取る HTML：" + ("、".join(bad) if bad else f"軽い・画像 1 枚ごとのハンドラ 0・最初の写真は eager・先頭の写真の例外 {n_ex} 件"))
        try:   # 先取りが実際に走ったか（字面でなく時間）：ふつうの回線で 12 秒のうちに全版面の先頭が届き、先頭以外の写真も取りに行っている
            import ahead_time
            m = ahead_time.measure(pw, a.base, 1400, 12)
            bad = ([f"先頭が届かない版面 {len(m['miss'])}（例 {m['miss'][:3]}）"] if m["miss"] else []) + ([f"先頭が取れ終わるのに {m['secs'][-1]:.1f} 秒（12 秒を超えた）"] if m["secs"] and m["secs"][-1] > 12 else []) \
                + (["先頭以外の写真を先に取りに行っていない"] if m["rest"] and m["rest_got"] < m["n"] else [])
            msg = f"版面 {m['n']}・先頭が全部届くのは {m['secs'][-1]:.1f} 秒・先頭以外 {m['rest_got']} 枚を先取り" if m["secs"] else ""
        except Exception as ex:  # noqa: BLE001
            bad, msg = [f"測れなかった（{type(ex).__name__}: {str(ex)[:120]}）"], ""
        fails += bool(bad)
        print(("✗ " if bad else "✓ ") + "写真の先取りの実測（ログインなし・1400）：" + ("、".join(bad) if bad else msg))
        if not a.fast:   # 公開の HTML にお客さまだけの版面の名前が 0 件・店長でログインした管理ページの版面の数＝ライブラリの数
            try:
                bad, n = check_public_leak(a.base)
            except Exception as ex:  # noqa: BLE001
                bad, n = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"], 0
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + "公開の HTML にお客さまだけの版面の名前：" + ("、".join(bad) if bad else f"{n} 件の名前が 0 か所"))
            try:
                bad = check_customer_admin_pages(pw, a.base, 1400)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + "お客さまが管理ページを直に開いても全ユーザーの中身が出ない：" + ("、".join(bad) if bad else "表の行 0・他の名前 0・入口 0"))
            try:
                bad = check_admin_coverage(pw, a.base, 1400)
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            if bad is None:
                print("– 管理ページの網羅：未確認（UX_ADMIN_EMAIL・UX_ADMIN_PASSWORD がない。✓ とは言わない）")
            else:
                fails += bool(bad)
                print(("✗ " if bad else "✓ ") + "管理ページの網羅：" + ("、".join(bad) if bad else "ライブラリの版面の数と同じ"))
        for w in ([] if a.fast else a.widths.split(",")):   # お客さまが管理ページを直に開く
            try:
                bad = check_customer_admin_gate(pw, a.base, int(w))
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"お客さまが管理ページを直に開く {w}px：" + ("、".join(bad[:4]) if bad else f"{'・'.join(CUSTOMER_PAGES)} × 7 枚：門が出る・全ユーザーの行 0・メニューに入口なし"))
        for w in ([] if a.fast else sorted({*a.widths.split(","), "520"}, key=int)):   # 演出のはみ出し（390・520・1400）
            try:
                bad = check_fx_edge(pw, a.base, int(w))
            except Exception as ex:  # noqa: BLE001
                bad = [f"開けなかった（{type(ex).__name__}: {str(ex)[:120]}）"]
            fails += bool(bad)
            print(("✗ " if bad else "✓ ") + f"👍 の演出のはみ出し {w}px：" + ("、".join(bad) if bad else "20 種×端・真ん中で切れない"))
        for w in ([] if a.fast else a.widths.split(",")):   # --fast は小元素を見ない
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
