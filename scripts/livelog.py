"""管理ページの一番上：ターミナルのような「ライブログ」。開いている間、裏の仕組みが版面ごとに何を始め・何を終えたかが自動で流れる。

行の出どころ（どれもページを開いた端末で読む。データベースの表は増やさない）：
  ・ページを作った時点の実行ログ（state/log/*.json、digest.backend_log）……最初の数十行
  ・Supabase の live_boards()（20 秒ごと）……前回との差：版面が現れた＝始めた、言葉が変わった＝次の段、消えた＝終わった
  ・GitHub Actions の実行（3 分ごと、管理ページの「いまの状況」と同じ localStorage を使い回す）……始まった・成功・失敗
  ・リポジトリの state/log/*.json（raw.githubusercontent.com、2 分ごと）……新しく書かれた実行ログ（出刊・AI 編集・ゲート…）
見た行は localStorage（wl-term、最新 300 行）に残すので、ページが自動で読み直されても流れは途切れない。
色は render.py の設計令牌だけ（地は --ink）。
"""

import html
import json

e = html.escape

PROCS = {"collect": "収集", "publish": "出刊", "edit": "AI編集", "emblem": "小元素", "photos": "写真", "gate": "ゲート",
         "render": "ページ", "background": "後台"}
LOG_FILES = ["collect", "publish", "edit", "emblem", "gate", "photos"]   # runlog.PROCS と同じ（state/log/<proc>.json）


def panel(log, repo="CxElegy/Wishlist"):
    """log = digest.backend_log の行（新しい順、at つき）。→ HTML。"""
    seed = [{"at": r.get("at") or "", "p": r.get("proc") or "", "b": "", "t": r.get("text") or "", "lv": r.get("level") or "info"}
            for r in reversed(log or [])]
    cfg = json.dumps({"seed": seed, "repo": repo, "files": LOG_FILES, "procs": PROCS}, ensure_ascii=False).replace("</", "<\\/")
    return ('<div class="term" id="term">'
            '<div class="term-bar"><i></i><i></i><i></i><span class="term-tt">watchlist@admin:~/log</span>'
            '<b class="term-st" id="term-st">接続中…</b>'
            '<button type="button" class="term-btn" id="term-pause" aria-pressed="false">一時停止</button></div>'
            '<ol class="term-body" id="term-body" role="log" aria-live="polite" aria-label="ライブログ"></ol>'
            '<div class="term-foot"><span class="term-cur" aria-hidden="true">▌</span><span id="term-foot">待機中</span></div></div>'
            f'<script type="application/json" id="term-cfg">{cfg}</script>')


CSS = """
.term{background:var(--ink);color:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);font:500 12.5px/1.65 var(--font-mono)}
.term-bar{display:flex;align-items:center;gap:6px;padding:7px 10px;border-bottom:1px solid color-mix(in srgb,var(--card) 18%,transparent)}
.term-bar>i{width:10px;height:10px;border-radius:50%;background:color-mix(in srgb,var(--card) 30%,transparent)}
.term-bar>i:first-child{background:var(--alert)}.term-bar>i:nth-child(2){background:var(--gold)}.term-bar>i:nth-child(3){background:var(--viz-3)}
.term-tt{margin-left:6px;opacity:.7;font-size:var(--fs-label);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.term-st,.term-btn{white-space:nowrap;flex:none}
.term-st{margin-left:auto;font:700 var(--fs-label) var(--font-mono);color:color-mix(in srgb,var(--card) 70%,transparent)}
.term-st.on{color:var(--viz-3)}.term-st.ng{color:color-mix(in srgb,var(--alert) 60%,var(--card))}
.term-btn{font:700 var(--fs-label) var(--font-mono);padding:3px 8px;background:transparent;color:var(--card);border:1px solid color-mix(in srgb,var(--card) 40%,transparent);cursor:pointer}
.term-btn[aria-pressed=true]{background:var(--gold);color:var(--ink);border-color:var(--gold)}
.term-btn:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.term-body{list-style:none;margin:0;padding:8px 12px;height:260px;overflow-y:auto;overscroll-behavior:contain}
.term-body li{display:grid;grid-template-columns:auto auto minmax(0,1fr);gap:0 10px;align-items:baseline;white-space:normal;overflow-wrap:anywhere}
.term-body time{color:color-mix(in srgb,var(--card) 55%,transparent)}
.term-body .tp{font-weight:700;min-width:5.5em}
.term-body .tp-collect{color:var(--gold)}.term-body .tp-edit{color:var(--viz-5)}.term-body .tp-emblem{color:var(--seq-1)}
.term-body .tp-gate,.term-body .tp-background{color:var(--viz-4)}.term-body .tp-publish,.term-body .tp-render{color:var(--viz-3)}
.term-body .tp-photos{color:var(--seq-0)}
.term-body b{font-weight:700;color:var(--card)}
.term-body .lv-ok .tx::before{content:"✔ ";color:var(--viz-3)}
.term-body .lv-error .tx,.term-body .lv-warn .tx{color:color-mix(in srgb,var(--alert) 55%,var(--card))}
.term-body .lv-error .tx::before{content:"✖ "}.term-body .lv-warn .tx::before{content:"! "}
.term-body li.new{animation:termin .6s ease-out}
@keyframes termin{from{background:color-mix(in srgb,var(--gold) 22%,transparent)}to{background:transparent}}
.term-foot{display:flex;gap:6px;align-items:center;padding:6px 12px 8px;border-top:1px solid color-mix(in srgb,var(--card) 12%,transparent);color:color-mix(in srgb,var(--card) 65%,transparent);font-size:var(--fs-label)}
.term-cur{color:var(--viz-3)}
@media (prefers-reduced-motion:no-preference){.term-cur{animation:termblink 1s steps(1) infinite}}
@keyframes termblink{50%{opacity:0}}
@media (max-width:560px){.term-tt{display:none}.term-body{height:300px;font-size:12px}.term-body li{grid-template-columns:auto minmax(0,1fr)}.term-body time{grid-column:1/-1}}
"""

JS = """
(function(){
  var C=document.getElementById('term-cfg');if(!C)return;var T=JSON.parse(C.textContent),A=JSON.parse(document.getElementById('adm-cfg').textContent);
  var body=document.getElementById('term-body'),st=document.getElementById('term-st'),foot=document.getElementById('term-foot'),pbtn=document.getElementById('term-pause');
  var K='wl-term',MAX=300,ev=[],seen={},paused=false,stick=true;
  var FMT=new Intl.DateTimeFormat('ja-JP',{timeZone:A.tz||'Asia/Tokyo',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  function ts(s){var d=new Date(s);if(isNaN(d))return '';var o={};FMT.formatToParts(d).forEach(function(p){o[p.type]=p.value;});return o.month+'/'+o.day+' '+o.hour+':'+o.minute+':'+o.second;}
  function key(x){return x.at+'|'+x.p+'|'+x.b+'|'+x.t;}
  function row(x,fresh){var li=document.createElement('li');li.className='lv-'+(x.lv||'info')+(fresh?' new':'');
    var t=document.createElement('time');t.textContent=ts(x.at);li.appendChild(t);
    var p=document.createElement('span');p.className='tp tp-'+x.p;p.textContent='['+(T.procs[x.p]||x.p)+']';li.appendChild(p);
    var s=document.createElement('span');s.className='tx';if(x.b){var b=document.createElement('b');b.textContent=x.b;s.appendChild(b);s.appendChild(document.createTextNode('  '));}
    s.appendChild(document.createTextNode(x.t));li.appendChild(s);return li;}
  function save(){try{localStorage.setItem(K,JSON.stringify(ev.slice(-MAX)));}catch(e){}}
  function add(x,fresh){x.at=x.at||new Date().toISOString();var k=key(x);if(seen[k])return;seen[k]=1;
    ev.push(x);ev.sort(function(a,b){return a.at<b.at?-1:a.at>b.at?1:0;});if(ev.length>MAX)ev=ev.slice(-MAX);
    if(!paused){var li=row(x,fresh),after=null;for(var i=body.children.length-1;i>=0;i--){if((body.children[i].dataset.at||'')<=x.at){after=body.children[i];break;}}
      li.dataset.at=x.at;if(after)after.after(li);else body.insertBefore(li,body.firstChild);
      while(body.children.length>MAX)body.removeChild(body.firstChild);if(stick)body.scrollTop=body.scrollHeight;}
    if(fresh)save();}
  function redraw(){body.textContent='';ev.forEach(function(x){var li=row(x,false);li.dataset.at=x.at;body.appendChild(li);});body.scrollTop=body.scrollHeight;}
  body.addEventListener('scroll',function(){stick=body.scrollHeight-body.scrollTop-body.clientHeight<24;});
  pbtn.addEventListener('click',function(){paused=!paused;pbtn.setAttribute('aria-pressed',paused?'true':'false');pbtn.textContent=paused?'再開':'一時停止';if(!paused)redraw();});
  var old=[];try{old=JSON.parse(localStorage.getItem(K)||'[]');}catch(e){}
  (old.concat(T.seed)).forEach(function(x){if(x&&x.at)add(x,false);});redraw();
  function tick(msg){foot.textContent=msg+' · 最終確認 '+ts(new Date().toISOString()).slice(6);}
  // ① 版面ごとの状態（live_boards）：前回との差を 1 行に
  var prev=null;
  function words(x){if(x.proc==='collect')return x.state==='fetch'?'記事を探しています':'新着 '+x.found+' 件 · AI 整理待ちへ';
    var m=/^emblem:(.*)$/.exec(x.state||'');if(m)return (x.note||'小元素を集めています')+'（'+x.found+' 段目）';return x.note||x.state;}
  function done(x){if(x.proc==='collect')return x.state==='fetch'?'探し終わり（新着なし）':'収集完了 · 新着 '+x.found+' 件を inbox へ';
    if(x.proc==='edit')return 'AI 編集 完了 · 網页に反映';if(x.proc==='emblem')return '小元素 終わり（増えた分は網页に反映）';return '終わり';}
  function loadBoards(){if(!A.url||!A.key){st.textContent='データベース未接続';st.className='term-st ng';return;}
    fetch(A.url+'/rest/v1/rpc/live_boards',{method:'POST',headers:{apikey:A.key,'Content-Type':'application/json'},body:'{}'})
      .then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(l){var cur={};st.textContent='● ライブ';st.className='term-st on';
        (l||[]).forEach(function(x){var k=x.board+'|'+x.proc;cur[k]=x;var w=words(x);
          if(!prev){add({at:x.started_at,p:x.proc,b:x.board,t:'進行中：'+w,lv:'info'},false);return;}
          var o=prev[k];if(!o)add({at:new Date().toISOString(),p:x.proc,b:x.board,t:'開始：'+w,lv:'info'},true);
          else if(words(o)!==w)add({at:new Date().toISOString(),p:x.proc,b:x.board,t:w,lv:'info'},true);});
        if(prev)Object.keys(prev).forEach(function(k){if(!cur[k]){var x=prev[k];add({at:new Date().toISOString(),p:x.proc,b:x.board,t:done(x),lv:'ok'},true);}});
        prev=cur;var n=Object.keys(cur).length;tick(n?'処理中 '+n+' 版面':'待機中（いま動いている版面なし）');})
      .catch(function(){st.textContent='再接続中…';st.className='term-st ng';});}
  // ② GitHub Actions：実行の始まり・終わり
  var WF={'digest.yml':['collect','ニュース収集'],'background.yml':['background','後台作業（ゲート・小元素）'],'render.yml':['render','ページ生成'],'requests.yml':['background','設定ページの依頼']};
  var runSeen={};try{runSeen=JSON.parse(localStorage.getItem('wl-term-runs')||'{}');}catch(e){}
  function loadRuns(){var c=null;try{c=JSON.parse(localStorage.getItem('wl-actions')||'null');}catch(e){}
    var p=(c&&Date.now()-c.t<170000)?Promise.resolve(c.j):fetch('https://api.github.com/repos/'+A.repo+'/actions/runs?per_page=30').then(function(r){if(!r.ok)throw 0;return r.json();});
    p.then(function(j){(j.workflow_runs||[]).slice().reverse().forEach(function(w){var f=WF[(w.path||'').split('/').pop()];if(!f)return;
      var id=w.html_url||w.created_at,s=w.status==='completed'?(w.conclusion||'done'):'run';if(runSeen[id]===s)return;var first=!(id in runSeen);runSeen[id]=s;
      if(s==='run')add({at:w.created_at,p:f[0],b:'',t:f[1]+' 開始（'+(w.event||'')+'）',lv:'info'},!first);
      else add({at:w.updated_at||w.created_at,p:f[0],b:'',t:f[1]+(s==='success'?' 成功':s==='cancelled'||s==='skipped'?' 取り消し':' 失敗'),lv:s==='success'?'ok':s==='failure'?'error':'info'},!first);});
      try{localStorage.setItem('wl-term-runs',JSON.stringify(runSeen));}catch(e){}}).catch(function(){});}
  // ③ 実行ログ（リポジトリの state/log）：出刊・AI 編集・ゲートの判断など、仕組みが自分で書いた行
  function loadLogs(){T.files.forEach(function(f){fetch('https://raw.githubusercontent.com/'+A.repo+'/main/state/log/'+f+'.json',{cache:'no-store'})
    .then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(rows){(rows||[]).slice(-30).forEach(function(r){
      add({at:r.at,p:f,b:'',t:r.text||'',lv:r.level||'info'},Date.now()-new Date(r.at)<600000);});}).catch(function(){});});}
  loadBoards();loadRuns();loadLogs();
  setInterval(function(){if(!document.hidden)loadBoards();},20000);
  setInterval(function(){if(!document.hidden)loadRuns();},180000);
  setInterval(function(){if(!document.hidden)loadLogs();},120000);
})();
"""
