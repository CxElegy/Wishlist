"""管理ページの一番上：しくみの全体図を「1 ページ 1 画面」に分け、いま動いている部品に動きをつける（ライブ図）。

  ・ページ（タブ）：全体 / ニュース収集 / AI 編集 / 小元素 / ページ更新。どれも画面に収まる大きさ
  ・部品をクリックすると、詳しい流れの図（processes.detail のダイアログ）が開く
  ・「いま待っているもの」：何を・なぜ・いつまで待っているか（ここで待ちの意味を言葉にする）
  ・動き：Supabase の live_boards()（収集・AI 編集・小元素が版面ごとに書く）と GitHub Actions の実行中を 30 秒ごとに読み、
    いま動いている部品の周りに光る枠を出す。動いていないのに「待ち」の行は「止まっているかも」と出す

部品の見た目は render.py の設計令牌（--ink --card --rose --gold --alert など）だけで、新しい色は足さない。
改めるときは PAGES（図の中身）、waits()（待ちの文）、tests/test_design.py の Overview を一緒に。
"""

import html
import json

import processes

e = html.escape

# 部品の置き場（色分けではなく札で見せる）：どこで動くか
WHERE = {
    "ext": "インターネット", "actions": "GitHub Actions · 無料", "repo": "リポジトリ", "ai": "Claude · サブスク枠",
    "web": "公開ページ", "you": "あなた", "db": "Supabase",
}

# 1 部品 = (key, 名前, 説明, where, 詳しい流れの proc id か None, 種類)。key があるものは「いま動いている」判定の対象（JS が data-k で見る）。
# 種類：step（四角）/ ask（判断：ひし形ぎみの札）。列 = 同時に並ぶ部品（縦に積む）
# m = その段だけで光らせる目印（AI 編集の note に含まれる語、または小元素の段 found=1〜3）。なければ、その仕組みが動いていれば光る
N = lambda key, name, text, where, proc=None, kind="step", m="": {"key": key, "name": name, "text": text, "where": where, "proc": proc, "kind": kind, "m": m}

PAGES = [
    {"id": "all", "title": "全体", "lead": "ニュースを集めてから、あなたが読むまでの道のり。光っている部品がいま動いているところ。",
     "edges": ["記事を集める", "inbox に書く", "仕事を数える", "整理待ちがあれば起こす", "push", "公開", "見る"],
     "cols": [
         [N(None, "インターネット", "ニュース・価格・画像", "ext")],
         [N("collect", "ニュース収集", "2 時間ごと · 6 本並列", "actions", "collect")],
         [N(None, "inbox/", "集めた記事の置き場", "repo")],
         [N("gate", "後台のゲート", "毎時 · 仕事を数える · 収集の定時が抜けたら起こす", "actions", "gate")],
         [N("edit", "AI 編集", "毎日 9:00・18:00", "ai", "edit"),
          N("emblem", "小元素の補完", "足りない版面 · AI なし", "actions", "emblem-cron")],
         [N("render", "ページ生成", "push のたび", "actions", "render")],
         [N(None, "公開ページ", "簡報・管理ページ", "web")],
         [N(None, "あなた", "読む・👍・設定", "you")],
     ],
     "side": [N(None, "Supabase", "👍・設定・写真・版面の更新状態（live_status）", "db"),
              N(None, "Discord", "要紧は当日・周報は月曜", "ext")]},
    {"id": "collect", "title": "ニュース収集", "lead": "2 時間ごとに記事を集め、AI 編集が整理するまでは「整理待ち」として置く（要紧だけ先に載せる）。"
                                                     "定時が抜けたら後台が起こし、18 分で締め切って残りは次の回へ。",
     "edges": ["", "", "", "", "", "", ""],
     "cols": [
         [N("gate", "定時が抜けた？", "最後の収集から 150 分 → 後台のゲートが起こす", "actions", "gate", "ask")],
         [N("collect", "記事を集める", "Google・Bing・Reddit・Steam・RSS · 6 本並列", "ext", "collect"),
          N("collect", "18 分の締め切り", "過ぎたら残りの版面は次の回へ · 1 版面の失敗はその版面だけ空", "actions", None, "ask")],
         [N("collect", "絞る", "重複・スパム・match（作品の記事か）", "actions", None)],
         [N("collect", "新しい記事がある？", "なければその作品は書かない", "actions", None, "ask")],
         [N(None, "inbox に書く", "inbox/日付.json", "repo")],
         [N("collect", "出刊", "AI 整理済み + 要紧だけ。残りは整理待ち", "actions", None)],
         [N(None, "要紧 → Discord", "当日すぐ", "ext"), N("render", "push → ページ生成", "公開ページへ", "actions", "render")],
     ]},
    {"id": "edit", "title": "AI 編集", "lead": "整理待ちが溜まるとゲートが Claude を起こす。起こしただけでは「動いた」とは言わず、編集済みの数が増えたかを見る。",
     "edges": ["", "", "", "", "", "", ""],
     "cols": [
         [N("gate", "整理待ちがある？", "今日の inbox で _covered より後", "actions", "gate", "ask")],
         [N("gate", "60 分たった？動いた？", "増えていなければ停滞 → 3 回まで起こし直す", "actions", None, "ask")],
         [N("edit", "Claude を起こす", "API で定時タスクを起こす", "ai", "edit")],
         [N("edit", "編排する", "edit.json（同じ件を合わせる）", "ai", m="編集しています")],
         [N("edit", "配図を選ぶ", "候補を見て 1 枚", "ai", m="配図")],
         [N("edit", "出刊 publish", "整理済みの記事だけ版面へ", "actions", m="反映を待")],
         [N("edit", "git push", "仓库の権限がないと 403 で止まる", "repo", m="反映を待")],
         [N("render", "ページ生成", "公開ページへ", "actions", "render")],
     ]},
    {"id": "emblem", "title": "小元素", "lead": "版面右上のステッカーを、AI を使わずに集める。足りない版面があれば毎時動き、失敗は時間か新しい材料を待つ。",
     "edges": ["", "", "", "", "", ""],
     "cols": [
         [N("gate", "足りない版面がある？", "目標の枚数に届いていない版面", "actions", "gate", "ask")],
         [N("emblem", "① 標準の取り方", "Wikipedia・Commons・Fandom…", "actions", "emblem-cron", m="found=1")],
         [N("emblem", "② 名前を広げる", "別名・関連語で探す", "actions", m="found=2")],
         [N("emblem", "③ 公式・記事のページ", "公式サイトや記事の写真", "actions", m="found=3")],
         [N("emblem", "規則で確かめる", "顔の大きさ・人数・本人・切り抜きの穴", "actions")],
         [N(None, "items.yaml に書く", "足りたら終わり", "repo"), N(None, "失敗 → 待つ", "新しい材料が来たらすぐ・来なくても 1 時間後（毎時の後台）", "actions")],
     ]},
    {"id": "page", "title": "ページ更新", "lead": "リポジトリが変わると公開ページを作り直す。開いているページは 1 分ごとに気づいて、静かに読み直す。",
     "edges": ["", "", "", "", ""],
     "cols": [
         [N(None, "main に push", "収集・AI 編集・設定の反映", "repo")],
         [N("render", "ページ生成", "docs/ を作り直す", "actions", "render")],
         [N(None, "GitHub Pages", "公開（約 1 分）", "web")],
         [N(None, "version.json", "内容の指紋", "web")],
         [N(None, "開いているページ", "1 分ごとに読む → 読み直し", "you", "live")],
     ]},
]


def _node(n):
    k = (f' data-k="{e(n["key"])}"' if n["key"] else "") + (f' data-m="{e(n["m"])}"' if n.get("m") else "")
    op = f' data-open="proc-{e(n["proc"])}"' if n.get("proc") else ""
    tag = "button" if op else "div"
    typ = ' type="button"' if op else ""
    return (f'<{tag}{typ} class="ov-n ov-{e(n["kind"])}{" ov-link" if op else ""}"{k}{op}>'
            f'<small class="ov-w">{e(WHERE.get(n["where"], n["where"]))}</small><b>{e(n["name"])}</b>'
            f'<span class="ov-t">{e(n["text"])}</span><em class="ov-st" aria-live="polite"></em></{tag}>')


def _page(p, first):
    out = []
    for i, col in enumerate(p["cols"]):
        if i:
            lab = (p.get("edges") or [""] * 99)[i - 1] if i - 1 < len(p.get("edges") or []) else ""
            out.append(f'<span class="ov-ar" aria-hidden="true"><i>{e(lab)}</i></span>')
        out.append(f'<div class="ov-c">{"".join(_node(n) for n in col)}</div>')
    side = (f'<div class="ov-side"><small>いつも横で動くもの</small>{"".join(_node(n) for n in p["side"])}</div>' if p.get("side") else "")
    return (f'<div class="ov-page" id="ov-{e(p["id"])}"{"" if first else " hidden"} role="tabpanel">'
            f'<p class="ov-lead">{e(p["lead"])}</p><div class="ov-flow">{"".join(out)}</div>{side}</div>')


def waits(data):
    """「いま待っているもの」：何を・なぜ・どうすれば。→ [(名前, 何, なぜ, ボタンの job か None)]。
    digest.admin_data の todo / items（バックグラウンドの表の元データ）から、言葉にするだけ。"""
    data = data or {}
    todo, rows = data.get("todo") or {}, data.get("items") or []
    out = []
    ed = todo.get("edit") or {}
    if ed.get("n"):
        why = {"running": "AI 編集を起こして間もない（編集中のはず）。終わるまで版面には載らず、各版面の下の「整理待ち」にいる",
               "progress": "AI 編集が動いている（起こしたあと編集済みが増え、最後の出刊から 30 分以内）。終わった分から版面に載る",
               "idle": "残りは次の回でゲートが起こす（ボタンで今すぐ）。それまで「整理待ち」にいる",   # 前回の時刻・次の回の時刻は why に
               "unpublished": "AI 編集は記事を整理したが、版面への出刊が記録されていない（出刊に失敗したかも：AI 編集の定時タスクの環境を見る）。それまで「整理待ち」にいる",
               "stalled": "起こしたのに動いていない。ゲートが次の回で起こし直す（最大 3 回）",
               "gave_up": "3 回起こしても動かない。定時タスクの設定（仓库を使えるか）を見る必要がある"}.get(
            ed.get("state"), "次の 9:00 か 18:00 にゲートが AI 編集を起こす（ボタンで今すぐ）。それまで版面には載らず「整理待ち」にいる")
        extra = f"（{ed['why']}）" if ed.get("why") and ed.get("state") in ("progress", "idle", "unpublished", "stalled", "gave_up") else ""
        out.append(("AI 編集", f"整理待ち {ed['n']} 件（{ed.get('boards', 0)} 版面）", why + extra, "edit_now"))
    failed = [r["name"] for r in rows if (r.get("bg") or {}).get("emblem", {}).get("state") == "failed"]
    if failed:
        out.append(("小元素", f"失敗 {len(failed)} 版面", "候補が足りなかった版面。新しい記事・手がかりが来たらすぐ、来なくても 1 時間後に自動で再挑戦する（ボタンで今すぐ）", "background"))
    short = [r["name"] for r in rows if (r.get("bg") or {}).get("emblem", {}).get("state") == "wait"]
    if short:
        out.append(("小元素", f"足りない {len(short)} 版面", "次の回（毎時 17・47 分）に順に埋める。AI は使わない", None))
    design = [r["name"] for r in rows if (r.get("bg") or {}).get("design", {}).get("state") == "wait"]
    if design:
        out.append(("版面の設計", f"{len(design)} 版面", "テーマ・配色が未設定。AI 編集のときに一緒に決める（それまでは種類に合う既定の見た目）", None))
    return out


def _waits(data):
    items = waits(data)
    if not items:
        return '<p class="ov-none">いま待っているものはありません。</p>'
    lis = ""
    for name, what, why, job in items:
        lab = {"edit_now": "AI 編集をもう一度起こす", "background": "今すぐ再挑戦"}.get(job, "今すぐ")
        btn = (f'<span class="nx-go"><button type="button" class="nx-run" data-run="{e(job)}" data-label="{e(lab)}">{e(lab)}</button>'
               f'<small class="nx-msg" aria-live="polite"></small></span>') if job else ""
        lis += f'<li><b>{e(name)}</b><span class="ov-what">{e(what)}</span><small>{e(why)}</small>{btn}</li>'
    return f'<ul class="ov-waits">{lis}</ul>'


def panel(data):
    """管理ページの一番上のパネル（render.render_admin が入れる）。"""
    tabs = "".join(f'<button type="button" role="tab" class="ov-tab{" on" if i == 0 else ""}" data-p="{e(p["id"])}" aria-selected="{"true" if i == 0 else "false"}">'
                   f'{e(p["title"])}<i class="ov-dot" aria-hidden="true"></i></button>' for i, p in enumerate(PAGES))
    pages = "".join(_page(p, i == 0) for i, p in enumerate(PAGES))
    keys = sorted({n["key"] for p in PAGES for col in p["cols"] for n in col if n["key"]})
    pages_of = {k: [p["id"] for p in PAGES if any(n["key"] == k for col in p["cols"] for n in col)] for k in keys}
    cfg = json.dumps({"pages": pages_of}, ensure_ascii=False).replace("</", "<\\/")
    return (f'<div class="ov-now" id="ov-now"><b>いま</b><span id="ov-now-t">読み込み中…</span></div>'
            f'<div class="ov-tabs" role="tablist">{tabs}</div>{pages}'
            f'<h3 class="h3">いま待っているもの <small>何を・なぜ・いつまで待っているか</small></h3>{_waits(data)}'
            f'<script type="application/json" id="ov-cfg">{cfg}</script>')


CSS = """
.ov-now{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 12px;margin:0 0 12px;padding:8px 12px;background:var(--card);border:2px solid var(--ink);box-shadow:3px 3px 0 var(--ink);font:700 14px/1.5 var(--font-sans)}
.ov-now b{background:var(--ink);color:var(--card);padding:0 8px;font-size:var(--fs-label);letter-spacing:.1em}
.ov-now.busy{border-color:var(--rose);box-shadow:3px 3px 0 var(--rose)}
.ov-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.ov-tab{position:relative;font:900 13px/1 var(--font-sans);padding:9px 14px;background:var(--card);color:var(--ink);border:2px solid var(--ink);cursor:pointer}
.ov-tab.on{background:var(--ink);color:var(--card)}
.ov-tab:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.ov-dot{display:none;position:absolute;right:-5px;top:-5px;width:10px;height:10px;border-radius:50%;background:var(--rose);border:2px solid var(--card)}
.ov-tab.live .ov-dot{display:block}
.ov-lead{margin:0 0 10px;font-size:14px;line-height:1.7}
.ov-flow{display:flex;align-items:stretch;gap:0;overflow:hidden}
.ov-c{flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:8px;justify-content:center}
.ov-ar{flex:0 0 22px;display:flex;align-items:center;justify-content:center;position:relative;color:var(--ink);font:900 18px var(--font-sans)}
.ov-ar::before{content:"›"}
.ov-ar i{display:none}
.ov-n{position:relative;display:flex;flex-direction:column;gap:3px;text-align:left;padding:8px 9px 10px;background:var(--card);color:var(--ink);border:2px solid var(--ink);box-shadow:3px 3px 0 var(--hair);font:inherit;min-width:0;overflow-wrap:anywhere}
.ov-link{cursor:pointer}.ov-link:hover{box-shadow:3px 3px 0 var(--ink)}.ov-link:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.ov-n .ov-w{font:700 var(--fs-tag) var(--font-sans);letter-spacing:.06em;opacity:.7}
.ov-n b{font:900 14px/1.35 var(--font-sans)}
.ov-n .ov-t{font-size:12px;line-height:1.5;opacity:.85}
.ov-ask{border-style:dashed}
.ov-st{display:none;font:700 var(--fs-label)/1.4 var(--font-sans);font-style:normal;margin-top:2px}
.ov-n.live{border-color:var(--rose);box-shadow:0 0 0 3px color-mix(in srgb,var(--rose) 35%,transparent),3px 3px 0 var(--rose)}
.ov-n.live .ov-st,.ov-n.stale .ov-st,.ov-n.wait .ov-st{display:block}
.ov-n.live .ov-st{color:var(--rose)}
.ov-n.stale{border-color:var(--alert)}.ov-n.stale .ov-st{color:var(--alert)}
.ov-n.live::after{content:"";position:absolute;left:0;right:0;bottom:0;height:4px;background:repeating-linear-gradient(135deg,var(--rose) 0 6px,transparent 6px 12px);background-size:24px 4px}
@media (prefers-reduced-motion:no-preference){
 .ov-n.live{animation:ovglow 1.6s ease-in-out infinite alternate}
 .ov-n.live::after{animation:ovstripe 1s linear infinite}
}
@keyframes ovglow{from{box-shadow:0 0 0 2px color-mix(in srgb,var(--rose) 20%,transparent),3px 3px 0 var(--rose)}to{box-shadow:0 0 0 7px color-mix(in srgb,var(--rose) 45%,transparent),3px 3px 0 var(--rose)}}
@keyframes ovstripe{to{background-position:24px 0}}
.ov-side{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:12px 0 18px;padding-top:10px;border-top:1px dashed var(--hair)}
.ov-side>small{flex:0 0 100%;font:700 var(--fs-label) var(--font-sans);opacity:.75}
.ov-side .ov-n{flex:1 1 220px}
.ov-waits{list-style:none;margin:0 0 4px;padding:0;display:grid;gap:8px}
.ov-waits li{display:grid;grid-template-columns:96px minmax(0,1fr);gap:2px 12px;align-items:baseline;padding:8px 12px;background:var(--card);border:2px solid var(--ink)}
.ov-waits b{grid-row:1/3;font:900 13px var(--font-sans)}.ov-what{font-weight:700;font-size:14px}
.ov-waits small{grid-column:2;font-size:12px;line-height:1.6;opacity:.85}
.ov-waits .nx-go{grid-column:2;display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;margin-top:4px}
.ov-none{margin:0;font-size:14px;opacity:.8}
@media (max-width:860px){
 .ov-flow{flex-direction:column;align-items:stretch}
 .ov-ar{flex:0 0 22px;transform:rotate(90deg)}
 .ov-c{flex:none}
 .ov-waits li{grid-template-columns:minmax(0,1fr)}.ov-waits b{grid-row:auto}.ov-waits small,.ov-waits .nx-go{grid-column:1}
}
"""

JS = """
(function(){
  var C=document.getElementById('ov-cfg');if(!C)return;var P=JSON.parse(C.textContent).pages;
  var A=JSON.parse(document.getElementById('adm-cfg').textContent);
  var tabs=document.querySelectorAll('.ov-tab'),pages=document.querySelectorAll('.ov-page'),now=document.getElementById('ov-now'),nowT=document.getElementById('ov-now-t');
  function show(id){Array.prototype.forEach.call(tabs,function(t){var on=t.dataset.p===id;t.classList.toggle('on',on);t.setAttribute('aria-selected',on?'true':'false');});
    Array.prototype.forEach.call(pages,function(p){p.hidden=p.id!=='ov-'+id;});try{localStorage.setItem('wl-ov',id);}catch(e){}}
  Array.prototype.forEach.call(tabs,function(t){t.addEventListener('click',function(){show(t.dataset.p);});});
  try{var s=localStorage.getItem('wl-ov');if(s&&document.getElementById('ov-'+s))show(s);}catch(e){}
  var NAME={collect:'ニュース収集',gate:'後台のゲート',edit:'AI 編集',emblem:'小元素の補完',render:'ページ生成'};
  var WF={'digest.yml':'collect','background.yml':'gate','render.yml':'render'};
  var rowsBy={},boards=[],runs=[];
  function mins(s){var d=new Date(s);return isNaN(d)?0:Math.round((Date.now()-d)/60000);}
  function hit(r,m){if(!m)return true;if(m.indexOf('found=')===0)return String(r.found)===m.slice(6);return (r.note||'').indexOf(m)>=0;}
  function paint(){
    rowsBy={};
    function add(k,r){(rowsBy[k]=rowsBy[k]||[]).push(r);}
    runs.forEach(function(w){var k=WF[(w.path||'').split('/').pop()];if(k&&w.status!=='completed')add(k,{text:'実行中（Actions）',note:'',actions:true,stale:false,board:''});});
    boards.forEach(function(x){if(!{collect:1,edit:1,emblem:1}[x.proc])return;var m=mins(x.started_at),txt;
      if(x.proc==='collect')txt=x.state==='fetch'?'記事を探している':'新着 '+x.found+' 件 · AI 整理待ち';
      else if(x.proc==='emblem')txt=(x.note||'小元素を集めています');else txt=x.note||x.state;
      add(x.proc,{text:txt,note:x.note||'',found:x.found,board:x.board,m:m,stale:x.state==='wait'&&m>30});});   // 反映待ちのまま 30 分以上：push が通っていないかも
    function sum(rs){var lv=rs.filter(function(r){return !r.stale;}),bd=rs.filter(function(r){return !r.actions;}),
        use=bd.length?bd:rs,pick=use.filter(function(r){return !r.stale;})[0]||use[0];   // 版面ごとの記録があればそれを文にする（Actions の実行中だけのときは「実行中」）
      return {live:lv.length>0,stale:!lv.length&&rs.length>0,t:pick.text+(use.length>1&&bd.length?'（ほか '+(use.length-1)+' 版面）':'')+(pick.board&&use.length===1?'（'+pick.board+'）':''),m:pick.m||0};}
    Array.prototype.forEach.call(document.querySelectorAll('.ov-n[data-k]'),function(n){var all=rowsBy[n.dataset.k]||[],
      rs=all.filter(function(r){return r.actions||hit(r,n.dataset.m);}),st=n.querySelector('.ov-st');
      if(!rs.length){n.classList.remove('live','stale');st.textContent='';return;}var o=sum(rs);
      n.classList.toggle('live',o.live);n.classList.toggle('stale',o.stale);
      st.textContent=o.stale?'止まっているかも · '+o.m+' 分前から「'+o.t.split('（')[0]+'」':o.t;});
    var any={};Object.keys(rowsBy).forEach(function(k){any[k]=sum(rowsBy[k]);});
    Array.prototype.forEach.call(tabs,function(t){var id=t.dataset.p;t.classList.toggle('live',Object.keys(any).some(function(k){return any[k].live&&(P[k]||[]).indexOf(id)>=0;}));});
    var ks=Object.keys(any).filter(function(k){return any[k].live;}),ss=Object.keys(any).filter(function(k){return any[k].stale;});
    nowT.textContent=ks.length?ks.map(function(k){return (NAME[k]||k)+'：'+any[k].t;}).join(' ／ ')+(ss.length?' ／ 止まっているかも：'+ss.map(function(k){return NAME[k];}).join('・'):'')
      :ss.length?'止まっているかも：'+ss.map(function(k){return (NAME[k]||k)+'（'+any[k].m+' 分前から「'+any[k].t.split('（')[0]+'」のまま）';}).join('・')
      :'いまは何も動いていません。待っているものは下の一覧に。';
    now.classList.toggle('busy',!!ks.length);}
  function loadBoards(){if(!A.url||!A.key){nowT.textContent='データベースに未接続です。';return;}
    fetch(A.url+'/rest/v1/rpc/live_boards',{method:'POST',headers:{apikey:A.key,'Content-Type':'application/json'},body:JSON.stringify({p_account:window.WL_ACCOUNT})})
      .then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(l){boards=l||[];paint();}).catch(function(){});}
  // Actions の実行中：管理ページの「いまの状況」と同じ localStorage の結果を使い回す（未登録 API は 1 時間 60 回まで）
  function loadRuns(){var c=null;try{c=JSON.parse(localStorage.getItem('wl-actions')||'null');}catch(e){}
    if(c&&Date.now()-c.t<170000){runs=c.j.workflow_runs||[];paint();return;}
    fetch('https://api.github.com/repos/'+A.repo+'/actions/runs?per_page=30').then(function(r){if(!r.ok)throw 0;return r.json();})
      .then(function(j){runs=j.workflow_runs||[];paint();}).catch(function(){});}
  loadBoards();loadRuns();setInterval(function(){if(!document.hidden)loadBoards();},30000);setInterval(function(){if(!document.hidden)loadRuns();},180000);
  setInterval(paint,60000);
})();
"""
