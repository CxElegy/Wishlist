"""把所有期的数据渲染成一张报纸式简报网页（docs/index.html）。消息永远保留，不随新一期消失。

版式规则：
- 左侧目录（撑满屏幕高度）：按板块分组列出每个作品，滚动时当前所在的一项放大并换成板块色，点击直达
- 最上面一张「头版」：最近一周的实时总览（最重要的一条做头条 + 各作品最新一条 + 最新消息列表）
- 版面数量和顺序固定（板块 → items.yaml 顺序）；每天更新只是版面里的消息变化
- 每个关注项一个版面，配色取自该作品（theme.py）。所有日期的消息汇总在一起，按时间排列（新的在前）：
  - 一周内收到的直接显示（最多约一屏），卡片大小按重要度：hero 整行、lead 8 栏、普通 4 栏，每行自动补满；
    放不下时先按重要度挑出留下的，留下的再按时间排
  - 更早的收进版面底部的「更早的消息」折叠区，点开才显示
- 一周内没有新消息的关注项只留一个小栏：标题条 + 现状
"""

import datetime as dt
import hashlib
import html
import re
import urllib.parse

FONTS = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@700;900"
    "&family=Noto+Serif+SC:wght@500;700;900&family=Cormorant+Garamond:wght@600"
    "&family=JetBrains+Mono:wght@500;700&display=swap"
)

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#EDEBE6;color:#1A1C22;font-family:'Noto Serif SC',serif}
a{color:inherit;text-decoration:none}
.page{max-width:1200px;margin:0 auto;padding:40px 24px;display:flex;flex-direction:column;gap:28px}
.mast{border:3px solid #1A1C22;padding:5px}
.mast>div{border:1px solid #1A1C22;display:flex}
.mast .logo{width:100px;background:#1A1C22;display:flex;align-items:center;justify-content:center}
.mast h1{flex:1;margin:0;padding:14px 28px;font:900 56px/1 'Noto Sans SC',sans-serif;letter-spacing:.04em}
.mast .meta{width:190px;border-left:1px solid #1A1C22;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:2px}
.mast .no{font:900 32px/1 'Noto Sans SC',sans-serif}
.mono{font-family:'JetBrains Mono',monospace;font-size:13px}
.issue{display:flex;flex-direction:column;gap:28px}
.issue-head{display:flex;align-items:center;gap:16px}
.issue-head::before,.issue-head::after{content:"";flex:1;border-top:2px solid #1A1C22}
.issue-head span{font:700 13px 'JetBrains Mono',monospace;letter-spacing:.3em}
.sec{background:var(--bg);color:var(--fg);border:1px solid var(--bg)}
.band{min-height:92px;display:flex;align-items:center;flex-wrap:wrap;gap:6px 18px;padding:16px 28px;background:var(--bg)}
.band.split{background:linear-gradient(162deg,var(--abg) 0 55%,var(--bg) 55% 100%)}
.band .title{font-size:50px;line-height:1;color:var(--fg)}
.band.split .title{color:var(--afg)}
.band .sub{margin-left:auto;font-size:15px;letter-spacing:.1em;color:var(--fg);opacity:.85}
.serif .title{font-family:'Cormorant Garamond','Noto Serif SC',serif;font-weight:600}
.sans .title{font-family:'Noto Sans SC',sans-serif;font-weight:900;font-size:40px}
.facts{display:flex;flex-wrap:wrap;gap:1px;background:var(--line)}
.fact{flex:1 1 280px;padding:14px 22px;background:var(--abg);color:var(--afg);display:flex;flex-direction:column;gap:4px}
.fact .label{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.75}
.fact .new{color:var(--aac);opacity:1}
.fact a{text-decoration:underline;text-underline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:1px;background:var(--line)}
.card{padding:20px;display:flex;flex-direction:column;gap:12px}
.card.m{background:var(--bg);color:var(--fg);--ac:var(--acc)}
.card.a{background:var(--abg);color:var(--afg);--ac:var(--aacc)}
.card:hover h2,.card:hover h3{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:1px}
.hl{color:var(--ac)}
.pic{position:relative;overflow:hidden;border:1px solid color-mix(in srgb,currentColor 35%,transparent);
 background:repeating-linear-gradient(135deg,color-mix(in srgb,currentColor 7%,transparent) 0 14px,transparent 14px 28px)}
.pic{aspect-ratio:16/9}
.pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.pic .ph{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:12px;text-align:center;
 font:600 clamp(18px,3vw,34px)/1.1 'Cormorant Garamond','Noto Serif SC',serif;letter-spacing:.04em;color:var(--ac,currentColor);
 background:radial-gradient(circle at 30% 20%,color-mix(in srgb,var(--ac,currentColor) 28%,transparent),transparent 60%),
 color-mix(in srgb,currentColor 8%,transparent)}
.pic.none{background:none}
.pic.none .ph{display:flex}
.pic img.bg{object-fit:cover;filter:blur(18px) brightness(.8);transform:scale(1.15)}
.hero{grid-column:span 12;display:grid;grid-template-columns:7fr 5fr;gap:24px;padding:24px}
.hero .pic{align-self:center}
.s12 .pic{aspect-ratio:auto;height:260px}.s12 .pic:empty{display:none}
.hero .txt{display:flex;flex-direction:column;justify-content:center;gap:16px}
.tag{font:700 12px 'JetBrains Mono',monospace;letter-spacing:.25em;color:var(--ac)}
.hero h2{margin:0;font-weight:900;font-size:34px;line-height:1.3;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;text-wrap:balance}
.lead{grid-column:span 8}
.lead h2{margin:0;font-weight:900;font-size:36px;line-height:1.25}
.side{grid-column:span 4;display:flex;flex-direction:column;gap:1px}
.side .card{flex:1}
.side h3{margin:0;font-weight:900;font-size:22px;line-height:1.35}
.row h3{margin:0;font-weight:900;font-size:21px;line-height:1.4}
.s12{grid-column:span 12}.s6{grid-column:span 6}.s4{grid-column:span 4}
.blurb{margin:0;font-size:16px;line-height:1.75;opacity:.85}
.quiet .band{min-height:64px;padding:10px 24px}
.quiet .band .title{font-size:32px}
.sans.quiet .band .title{font-size:26px}
.calm{display:flex;align-items:center;gap:20px;padding:12px 24px;background:var(--bg);color:var(--fg);border-top:3px solid var(--acc)}
.calm .pic{flex:0 0 120px;height:62px}
.calm .txt{flex:1;display:flex;flex-direction:column;gap:4px;min-width:0}
.calm .tag{color:var(--acc)}
.calm .status{font-size:15px;line-height:1.6}
.calm .last{flex:0 1 40%;display:flex;flex-direction:column;gap:2px;font-size:15px;line-height:1.5;border-left:1px solid color-mix(in srgb,currentColor 25%,transparent);padding-left:20px}
.calm .last .mono{font-size:11px;letter-spacing:.15em;opacity:.7}
.calm a.last:hover b{text-decoration:underline;text-underline-offset:4px}
/* ---------- 头版 ---------- */
.front{background:#FBF8F1;border:3px solid #1A1C22;box-shadow:6px 6px 0 #1A1C22;display:flex;flex-direction:column;
 background-image:radial-gradient(#1A1C22 .8px,transparent .9px);background-size:7px 7px;background-position:0 0}
.front>*{background:#FBF8F1}
.fbar{display:flex;align-items:center;gap:14px;padding:8px 18px;background:#1A1C22;color:#FBF8F1;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.25em}
.fbar b{font:900 15px 'Noto Sans SC',sans-serif;letter-spacing:.3em;color:#FFD23F}
.fbar span:last-child{margin-left:auto}
.fbody{display:grid;grid-template-columns:7fr 5fr;gap:0;border-bottom:3px solid #1A1C22}
.top{position:relative;padding:22px;border-right:3px solid #1A1C22;display:flex;flex-direction:column;gap:14px;color:#1A1C22}
.top .pic{border:3px solid #1A1C22;color:#1A1C22}
.top .badge{position:absolute;left:8px;top:8px;z-index:2;padding:6px 14px 6px 12px;background:#D7261E;color:#FFF;
 font:900 20px/1 'Noto Sans SC',sans-serif;letter-spacing:.08em;clip-path:polygon(0 0,100% 0,88% 100%,0 100%);border:none}
.top .kicker{display:flex;align-items:center;gap:10px;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.2em}
.top .kicker i{font-style:normal;padding:2px 10px;color:#FFF;letter-spacing:.15em}
.top h2{margin:0;font:900 34px/1.25 'Noto Sans SC',sans-serif;color:#D7261E;letter-spacing:.01em;
 display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;text-wrap:balance;
 text-shadow:2px 2px 0 #FFD23F}
.top p{margin:0;font-size:16px;line-height:1.75}
.topcol{display:flex;flex-direction:column;border-right:3px solid #1A1C22}
.topcol .top{border-right:none}
.mores{flex:1;display:flex;flex-direction:column;padding:0 22px 18px;gap:0}
.mores h5{margin:0 0 4px;padding-top:12px;border-top:3px double #1A1C22;font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.more{display:grid;grid-template-columns:120px 1fr;gap:14px;align-items:center;padding:10px 0;border-bottom:1px dashed color-mix(in srgb,#1A1C22 35%,transparent);color:#1A1C22}
.more .pic{aspect-ratio:16/10;border:2px solid #1A1C22;--ac:var(--sc)}
.more .pic .ph{font-size:13px}
.more .nm{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.1em;color:var(--sc)}
.more b{display:block;margin-top:3px;font-size:16px;line-height:1.45}
.more:hover b{text-decoration:underline;text-underline-offset:3px}
.top:hover h2{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:6px}
.boards{display:flex;flex-direction:column}
.board{border-bottom:3px solid #1A1C22;display:flex;flex-direction:column}
.board:last-child{border-bottom:none;flex:1}
.board h3{margin:0;display:flex;align-items:center;gap:10px;padding:8px 16px;background:var(--sc);color:#FFF;
 font:900 20px/1.2 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.board h3 small{margin-left:auto;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.9}
.entry{display:grid;grid-template-columns:96px 1fr;gap:12px;align-items:center;padding:10px 16px;border-top:1px dashed color-mix(in srgb,#1A1C22 35%,transparent)}
.entry:first-of-type{border-top:none}
.entry .pic{aspect-ratio:16/10;border:2px solid #1A1C22;color:#1A1C22;--ac:var(--sc)}
.entry .pic .ph{font-size:13px}
.entry .nm{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.12em;color:var(--sc)}
.entry b{display:block;font-size:15px;line-height:1.45;margin-top:2px}
.entry.q b{font-weight:500;opacity:.6}
.entry:hover b{text-decoration:underline;text-underline-offset:3px}
.board .none{padding:10px 16px;font-size:13px;opacity:.55}
.heads{display:flex;flex-direction:column}
.heads h4{margin:0;display:flex;align-items:baseline;gap:14px;padding:10px 18px;border-bottom:2px solid #1A1C22;
 font:900 26px/1 'Noto Sans SC',sans-serif;letter-spacing:.06em}
.heads h4 small{font:700 12px 'JetBrains Mono',monospace;letter-spacing:.3em;color:#D7261E}
.heads ol{list-style:none;margin:0;padding:6px 18px 14px;columns:2;column-gap:32px}
.heads li{break-inside:avoid;padding:7px 0;border-bottom:1px dotted color-mix(in srgb,#1A1C22 40%,transparent);display:flex;gap:10px;align-items:baseline}
.heads li i{flex:none;font:900 11px/1.6 'Noto Sans SC',sans-serif;font-style:normal;color:#FFF;background:var(--sc);padding:0 6px;letter-spacing:.1em}
.heads li a{flex:1;min-width:0;font-size:15px;line-height:1.5}
.heads li .d{flex:none;font:700 11px 'JetBrains Mono',monospace;opacity:.55;font-variant-numeric:tabular-nums}
.heads li a:hover{text-decoration:underline;text-underline-offset:3px}
/* ---------- 左侧目录（共用骨架；风格见 NAV_STYLES） ---------- */
html{scroll-behavior:smooth}
[data-k]{scroll-margin-top:24px}
.page{max-width:1480px;display:grid;grid-template-columns:236px minmax(0,1fr);gap:28px 32px;align-items:start}
.mast{grid-column:1/-1}
.issues{display:flex;flex-direction:column;gap:28px;min-width:0}
.nav{position:sticky;top:calc(env(safe-area-inset-top,0px) + 16px);max-height:calc(100vh - 32px);display:flex;flex-direction:column;z-index:50}
.nav .rail{display:flex;flex-direction:column;overflow-y:auto;scrollbar-width:none;min-height:0}
.nav .rail::-webkit-scrollbar{display:none}
.nav .pill{display:flex;align-items:center;gap:8px;position:relative}
.nav .pill .no{font:700 10px 'JetBrains Mono',monospace;font-style:normal;font-variant-numeric:tabular-nums}
.nav .pill:focus-visible,.nav select:focus-visible{outline:2px solid #FFD23F;outline-offset:2px}
.nav select{font:700 12px 'JetBrains Mono',monospace;padding:6px 8px;border-radius:0}
.nav .bar{display:none}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.nav *{transition:none!important}}
/* 窄屏：目录变成顶部横条 */
@media (max-width:1000px){
 .page{grid-template-columns:minmax(0,1fr)}
 .nav{top:env(safe-area-inset-top,0px);max-height:none;flex-direction:row;align-items:center;gap:8px;padding:6px 8px!important;
  background:#1A1C22!important;color:#FBF8F1!important;border:none!important;box-shadow:none!important}
 .nav .here,.nav .grp{display:none!important}
 .nav .rail{flex:1;flex-direction:row;overflow-x:auto;gap:6px;padding:6px 4px!important;border:none!important}
 .nav .pill{flex:none;padding:4px 10px!important;margin:0!important;font:700 13px/1.3 'Noto Sans SC',sans-serif!important;
  color:#FBF8F1!important;background:none!important;border:1px solid rgba(251,248,241,.3)!important;transform:none!important;width:auto!important}
 .nav .pill::before,.nav .pill::after,.nav .pill .no,.nav .pill .cnt{display:none!important}
 .nav .pill.on{background:var(--sc)!important;border-color:var(--sc)!important;transform:scale(1.12)!important;margin:0 4px!important}
 .nav select{background:transparent;color:#FBF8F1;border:1px solid rgba(251,248,241,.3)}
 .nav .bar{display:block;position:absolute;left:0;bottom:0;height:3px;background:var(--cur,#D7261E);width:calc(var(--prog,0) * 100%)}
 [data-k]{scroll-margin-top:64px}
}
/* ---------- 愿望清单 ---------- */
.wish{--bg:#F4EDE4;--fg:#1A1C22;--acc:#B8336A;--abg:#1A1C22;--afg:#F4EDE4;--aacc:#F2A7C3;--ac:#B8336A;
 --line:color-mix(in srgb,#1A1C22 18%,#F4EDE4);background:var(--bg);color:var(--fg);border:1px solid var(--line)}
.wish .band{background:linear-gradient(162deg,#1A1C22 0 42%,var(--bg) 42% 100%)}
.wish .band .title{font-family:'Noto Sans SC',sans-serif;font-weight:900;font-size:40px;color:#F4EDE4;letter-spacing:.08em}
.wish .band .sub{color:var(--fg);font:700 13px 'JetBrains Mono',monospace;letter-spacing:.25em}
.wgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1px;background:var(--line)}
.wcard{position:relative;display:flex;flex-direction:column;background:var(--bg)}
.wcard.solo{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr)}
.wcard .wimg{position:relative;aspect-ratio:1/1;max-width:100%;background:#FFF;display:grid;place-items:center;overflow:hidden}
.wcard.solo .wimg{aspect-ratio:auto;min-height:380px}
.wcard .wimg img{width:86%;height:86%;object-fit:contain;transition:transform .4s cubic-bezier(.2,.9,.3,1)}
.wcard:hover .wimg img{transform:scale(1.04) rotate(-1.5deg)}
.wcard .heart{position:absolute;top:14px;left:14px;padding:4px 10px;background:var(--acc);color:#FFF;
 font:900 12px 'Noto Sans SC',sans-serif;letter-spacing:.25em}
.wcard .heart.got{background:#1F9D6B}.wcard .heart.miss{background:#8C8678}
.wcard .wtxt{display:flex;flex-direction:column;gap:14px;padding:24px 26px;min-width:0}
.wcard.solo .wtxt{justify-content:center;padding:36px 40px;border-left:1px solid var(--line)}
.wcard .shop{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;color:var(--acc)}
.wcard h3{margin:0;font:900 26px/1.3 'Noto Sans SC',sans-serif;text-wrap:balance}
.wcard.solo h3{font-size:36px}
.wcard .price{font:900 30px/1 'Noto Sans SC',sans-serif;letter-spacing:.01em;font-variant-numeric:tabular-nums}
.wcard .price small{font:700 14px 'JetBrains Mono',monospace;margin-right:6px;opacity:.7}
.wcard dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:14px}
.wcard dt{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.15em;opacity:.6;padding-top:2px}
.wcard dd{margin:0}
.wcard .note{margin:0;font-size:15px;line-height:1.7;opacity:.85}
.wcard .links{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.08em}
.wcard .links a{border-bottom:2px solid var(--acc);padding-bottom:1px}
.wcard .links a:hover{color:var(--acc)}
.wcard .watch{display:flex;flex-direction:column;gap:4px;padding:12px 14px;background:color-mix(in srgb,var(--acc) 8%,transparent);border-left:3px solid var(--acc);font-size:14px;line-height:1.55}
.wcard .watch span{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.2em;color:var(--acc)}
.wcard .added{font:700 11px 'JetBrains Mono',monospace;opacity:.5;letter-spacing:.1em}
@media (max-width:760px){.wcard.solo{grid-template-columns:1fr}.wcard.solo .wimg{min-height:0;aspect-ratio:1/1}
 .wcard.solo .wtxt{border-left:0;padding:22px}.wcard.solo h3{font-size:28px}.wish .band .title{font-size:30px}}
.mastwish{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;padding:0 22px;
 border-left:1px solid #1A1C22;color:#B8336A;transition:background .2s,color .2s}
.mastwish b{font-size:22px;line-height:1}.mastwish span{font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.2em;color:#1A1C22}
.mastwish small{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.1em;opacity:.7;color:#1A1C22}
.mastwish:hover{background:#B8336A}.mastwish:hover b,.mastwish:hover span,.mastwish:hover small{color:#FFF}
.navwish{display:flex;align-items:center;gap:8px;margin:10px 0 0 14px;padding:8px 12px;border:2px solid #B8336A;color:#B8336A;
 font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.15em;flex:none}
.navwish small{margin-left:auto;font:700 10px 'JetBrains Mono',monospace;letter-spacing:.05em;opacity:.8}
.navwish:hover{background:#B8336A;color:#FFF}
@media (max-width:1000px){.navwish{display:none}}
@media (max-width:760px){.mastwish{padding:0 10px}.mastwish span,.mastwish small{display:none}}
/* ---------- 我会喜欢？ ---------- */
.picks{--ac:#B8336A;background:#F4EDE4;color:#1A1C22;border:3px solid #1A1C22;box-shadow:6px 6px 0 #B8336A}
.pkhead{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 18px;padding:16px 22px 14px;border-bottom:3px solid #1A1C22}
.pkhead h2{margin:0;font:900 34px/1 'Noto Sans SC',sans-serif;letter-spacing:.04em}
.pkhead h2 em{font-style:normal;color:#B8336A;display:inline-block;transform:rotate(12deg) translateY(-2px);margin-left:2px}
.pkhead span{font-size:13px;opacity:.75}
.pkhead a{color:#B8336A;font-weight:700;border-bottom:1px solid currentColor}
.pkgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:color-mix(in srgb,#1A1C22 18%,#F4EDE4)}
.pkgrid.row{grid-template-columns:repeat(var(--n),minmax(0,1fr))}
.pksub{display:flex;align-items:baseline;gap:12px;padding:12px 22px;border-top:3px solid #1A1C22;border-bottom:1px solid color-mix(in srgb,#1A1C22 18%,#F4EDE4);
 font:900 15px 'Noto Sans SC',sans-serif;letter-spacing:.2em}
.pksub span{font:500 12px 'Noto Serif SC',serif;letter-spacing:0;opacity:.7}
.pk{display:flex;flex-direction:column;gap:10px;padding:16px;background:#F4EDE4;color:#1A1C22;min-width:0}
.pk.big{grid-column:span 2;grid-row:span 2}
.pk .pic{background:#FFF;color:#1A1C22;border:none}
.pk .pkt{display:flex;flex-direction:column;gap:6px;min-width:0}
.pk .src{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.12em;opacity:.6}
.pk b{font-size:15px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.pk.big b{font:900 22px/1.35 'Noto Sans SC',sans-serif;-webkit-line-clamp:4}
.pk .why{font-size:12px;color:#B8336A;font-weight:700}
.pk .tags{display:flex;flex-wrap:wrap;gap:4px}
.pk .tags i{font-style:normal;font:700 10px 'Noto Sans SC',sans-serif;letter-spacing:.1em;padding:1px 7px;border:1px solid #B8336A;color:#B8336A}
.pk:hover b{text-decoration:underline;text-underline-offset:3px}
@media (max-width:760px){.pkgrid,.pkgrid.row{grid-template-columns:repeat(2,minmax(0,1fr))}.pkhead h2{font-size:26px}}
/* ---------- 按时间排列的卡片 ---------- */
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}.c3{grid-column:span 3}
.when{display:flex;align-items:center;gap:8px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.15em;opacity:.75;font-variant-numeric:tabular-nums}
.when b{padding:1px 6px;background:var(--ac);color:var(--bg);letter-spacing:.1em;opacity:1}
.card.a .when b{color:var(--abg)}
.card.wide{display:grid;grid-template-columns:5fr 7fr;gap:24px;align-items:center;padding:24px}
.card.wide .txt{display:flex;flex-direction:column;gap:12px;min-width:0}
.card.wide h3{margin:0;font-weight:900;font-size:28px;line-height:1.3}
.card.c8 h3{font-size:28px;line-height:1.3}.card.c6 h3{font-size:24px;line-height:1.35}
.card.c4 h3,.card.c3 h3{margin:0;font-weight:900;font-size:20px;line-height:1.4}
.older{background:var(--abg);color:var(--afg);border-top:1px solid var(--line)}
.older .grid{background:color-mix(in srgb,var(--afg) 16%,var(--abg))}
.older summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:14px 24px;
 font:700 12px 'JetBrains Mono',monospace;letter-spacing:.2em}
.older summary::-webkit-details-marker{display:none}
.older summary::before{content:"+";display:inline-grid;place-items:center;width:22px;height:22px;border:1.5px solid currentColor;
 font:700 15px/1 'JetBrains Mono',monospace;transition:transform .25s}
.older[open] summary::before{content:"−"}
.older summary:hover,.older summary:focus-visible{color:var(--acc);outline:none}
.older summary span{opacity:.6;letter-spacing:.1em}
.older .grid .card{padding:16px;gap:10px}
.older .card.c3 h3{font-size:16px;line-height:1.45}
@media (max-width:760px){
 .c12,.c8,.c6,.c4,.c3{grid-column:span 12}.card.wide{grid-template-columns:1fr;padding:20px}
 .card.c8 h3,.card.wide h3{font-size:24px}
 .fbody{grid-template-columns:1fr}.top{border-right:none;border-bottom:3px solid #1A1C22}.topcol{border-right:none}
 .more{grid-template-columns:90px 1fr}
 .top h2{font-size:30px}.heads ol{columns:1}.fbar span:nth-child(2){display:none}
 .page{padding:20px 12px}.mast h1{font-size:30px;padding:12px}.mast .logo{display:none}.mast .meta{width:110px}.mast .no{font-size:20px}
 .band .title{font-size:34px}.band .sub{margin-left:0}
 .band.split{background:var(--abg)}.band.split .sub{color:var(--afg)}
 .hero{grid-template-columns:1fr}
 .hero h2,.lead h2{font-size:28px}
 .lead,.side,.s12,.s6,.s4{grid-column:span 12}
 .quiet .band .title{font-size:26px}
 .calm{flex-wrap:wrap;gap:12px;padding:12px 16px}.calm .pic{display:none}
 .calm .last{flex:1 1 100%;border-left:0;padding-left:0}
}
"""

LOGO = (
    '<svg width="62" height="62" viewBox="0 0 92 92" aria-hidden="true" fill="none" stroke="#EDEBE6" stroke-width="2">'
    '<circle cx="46" cy="46" r="40"/><circle cx="46" cy="46" r="31" stroke-dasharray="3 4"/>'
    '<path d="M46 18 L51 41 L74 46 L51 51 L46 74 L41 51 L18 46 L41 41 Z" fill="#EDEBE6" stroke="none"/></svg>'
)

e = html.escape


def _md_links(text):
    """把状态文字里的 [文字](链接) 转成 <a>。"""
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', e(text, quote=False))


def _headline(story):
    text = e(story["headline"])
    hl = story.get("highlight")
    if hl and e(hl) in text:
        text = text.replace(e(hl), f'<span class="hl">{e(hl)}</span>', 1)
    return text


def _pic(story):
    """配图。底层模糊铺满，上层完整显示：图片不裁切，也不留空白条。
    没有图或图打不开（防盗链等）时换成作品封面；连封面也没有，就显示作品名排版的封面块。"""
    img, cover, name = story.get("image"), story.get("_cover"), story.get("_work", "")
    fb = f' data-fb="{e(cover)}"' if cover and cover != img else ""
    swap = ("if(this.dataset.fb){this.src=this.dataset.fb;this.removeAttribute('data-fb')}"
            "else{this.parentNode.classList.add('none');this.remove()}")
    src = img or cover
    tag = "".join(
        f'<img{cls} src="{e(src)}"{fb if img else ""} alt="" loading="lazy" referrerpolicy="no-referrer" onerror="{swap}">'
        for cls in (' class="bg"', "")
    ) if src else ""
    none = "" if src else " none"
    label = f'<span class="ph">{e(name)}</span>' if name else ""
    return f'<div class="pic{none}">{label}{tag}</div>'


def _card(story, cls, side, level="h3", blurb=False):
    body = f'<{level}>{_headline(story)}</{level}>'
    if blurb and story.get("blurb"):
        body += f'<p class="blurb">{e(story["blurb"])}</p>'
    return (f'<a class="card {side} {cls}" href="{e(story["url"])}" target="_blank" rel="noopener">'
            f'{_pic(story)}{body}</a>')


def _hero(story, side):
    return (f'<a class="card {side} hero" href="{e(story["url"])}" target="_blank" rel="noopener">{_pic(story)}'
            f'<div class="txt"><span class="tag">重 大</span><h2>{_headline(story)}</h2>'
            + (f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") else "")
            + "</div></a>")


HOLD_DAYS = 7  # 一周内收到的消息直接显示，更早的收进折叠区
SPAN = {"hero": 12, "lead": 8, "normal": 4}
RANK = {"hero": 0, "lead": 1, "normal": 2}


def _wid(name):
    """作品版面的锚点。"""
    return "w-" + hashlib.md5(name.encode()).hexdigest()[:8]


def _pack(stories, size_of, total=12):
    """按顺序排成行，不改变时间顺序；一行放不下就换行，剩下的空位分给这一行里最重要的卡片。"""
    rows, row, used = [], [], 0
    for s in stories:
        w = size_of(s)
        if row and used + w > total:
            rows.append(row)
            row, used = [], 0
        row.append([s, w])
        used += w
    if row:
        rows.append(row)
    for row in rows:
        left = total - sum(w for _, w in row)
        if left:
            best = min(row, key=lambda x: RANK.get(x[0].get("weight"), 2))
            best[1] += left
    return [x for row in rows for x in row]


def _when(story, today):
    d = story.get("date") or story["_issue"]
    # NEW 只给最近 24 小时左右发布的消息（按消息本身的日期，不是收集到的日期）
    new = "<b>NEW</b>" if d >= (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat() else ""
    return f'<span class="when">{new}{e(d[5:].replace("-", "."))}</span>'


def _tcard(story, span, i, today, small=False):
    side = "a" if small else "m"  # 不再黑白交替：一周内统一主色底，折叠区统一副色底
    w = story.get("weight", "normal")
    url = e(story["url"])
    if span == 12 and w == "hero":
        return (f'<a class="card {side} hero" href="{url}" target="_blank" rel="noopener">{_pic(story)}'
                f'<div class="txt">{_when(story, today)}<span class="tag">重 大</span><h2>{_headline(story)}</h2>'
                + (f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") else "") + "</div></a>")
    blurb = f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") and not small and w != "normal" else ""
    if span == 12 and not small:
        return (f'<a class="card {side} wide c12" href="{url}" target="_blank" rel="noopener">{_pic(story)}'
                f'<div class="txt">{_when(story, today)}<h3>{_headline(story)}</h3>{blurb}</div></a>')
    level = "h2" if w == "lead" and span >= 8 and not small else "h3"
    cls = f"c{span}" + (" lead" if level == "h2" else "")
    return (f'<a class="card {side} {cls}" href="{url}" target="_blank" rel="noopener">{_pic(story)}'
            f'{_when(story, today)}<{level}>{_headline(story)}</{level}>{blurb}</a>')


PAGE_HEIGHT = 1100  # 每个作品直接显示的消息最多占大约一屏高（像素，按卡片行的大致高度估算）
ROW_HEIGHT = {12: 300, 8: 560, 6: 450, 4: 350}  # 一行里最宽那张卡片的宽度 → 这一行大约多高；整行大图另算


def _row_height(row):
    widest = max(row, key=lambda x: x[1])
    if widest[1] == 12 and widest[0].get("weight") == "hero":
        return 470
    return ROW_HEIGHT.get(widest[1], 350)


def _layout(stories):
    """一周内消息的版式（保持时间顺序）：
    重大 → 整行大图；头条 → 左 8 栏，右边竖排接下来的两条普通消息（只有一条就两张各占一半）；
    普通消息三张一排，凑不满时平分整行。返回 [(行类型, 卡片列表)]。"""
    rows, normals = [], []

    def flush():
        if normals:
            rows.append(("normal", normals[:]))
            normals.clear()

    for x in stories:
        w = x.get("weight", "normal")
        if w == "hero":
            flush()
            rows.append(("hero", [x]))
        elif w == "lead":
            flush()
            rows.append(("lead", [x]))
        else:
            last = rows[-1] if rows and not normals else None
            if last and last[0] == "lead" and len(last[1]) < 3:
                last[1].append(x)
            else:
                normals.append(x)
                if len(normals) == 3:
                    flush()
    flush()
    return rows


def _row_h(kind, cards):
    if kind == "hero":
        return 470
    if kind == "lead":
        return {1: 300, 2: 450, 3: 560}[len(cards)]
    return {1: 300, 2: 450, 3: 350}[len(cards)]


def _height(stories):
    return sum(_row_h(k, c) for k, c in _layout(stories))


def _render_rows(rows, today):
    out, i = [], 0
    for kind, cards in rows:
        if kind == "hero":
            out.append(_tcard(cards[0], 12, i, today))
        elif kind == "lead" and len(cards) == 3:
            out.append(_tcard(cards[0], 8, i, today))
            out.append('<div class="side">' + "".join(_tcard(c, 4, i, today) for c in cards[1:]) + "</div>")
        else:
            span = {1: 12, 2: 6, 3: 4}[len(cards)]
            out += [_tcard(c, span, i, today) for c in cards]
        i += 1
    return "".join(out)


def _timeline(stories, today):
    """一周内的消息，最多放约一屏。放不下时按重要度挑：重要的先留（同样重要的取新的），
    能放进一屏就留下；留下的再按时间排列显示，其余返回给折叠区。"""
    def newest_first(xs):
        return sorted(xs, key=lambda x: x.get("date") or x["_issue"], reverse=True)

    keep = stories
    if _height(stories) > PAGE_HEIGHT:
        by_rank = sorted(newest_first(stories), key=lambda x: RANK.get(x.get("weight"), 2))
        keep = []
        for x in by_rank:
            trial = newest_first(keep + [x])
            if not keep or _height(trial) <= PAGE_HEIGHT:
                keep = trial
    kept = {id(x) for x in keep}
    rest = [x for x in stories if id(x) not in kept]
    return '<div class="grid">' + _render_rows(_layout(keep), today) + "</div>", rest


def _older(stories, today, more=0):
    """折叠区：一周内放不下的（more 条）+ 一周以前的。"""
    if not stories:
        return ""
    packed = _pack(stories, lambda s: 3)
    first, last = stories[-1].get("date") or stories[-1]["_issue"], stories[0].get("date") or stories[0]["_issue"]
    rng = f"{first[5:].replace('-', '.')} – {last[5:].replace('-', '.')}"
    cards = "".join(_tcard(s, w, i, today, small=True) for i, (s, w) in enumerate(packed))
    label = "更多消息" if more else "更早的消息"
    detail = f"一周内另有 {more} 条" + (f" · 更早 {len(stories) - more} 条" if len(stories) > more else "") if more else rng
    return (f'<details class="older"><summary>{label} · {len(stories)} 条<span>{detail}</span></summary>'
            f'<div class="grid">{cards}</div></details>')


def collect(issues, order=None):
    """把各期按作品汇总：外观以最新一期为准；消息按链接去重，按时间排列（新的在前）。
    作品顺序固定：先按板块（游戏 / 影视 / 运动 / 好物 / 其他），同板块内按 order（items.yaml 的顺序）。
    这样每天更新只是版面里的消息变化，版面的数量和位置不变。"""
    latest = issues[0]
    rank = {n: i for i, n in enumerate(order or [])}
    sec_rank = {n: i for i, n in enumerate(SECTIONS)}
    blocks = sorted(latest["items"], key=lambda b: (sec_rank.get(b.get("section"), len(SECTIONS)),
                                                    rank.get(b["name"], len(rank))))
    works = {}
    for b in blocks:
        works[b["name"]] = {**b, "stories": [], "_seen": set()}
    for issue in issues:  # 新到旧
        for b in issue["items"]:
            w = works.get(b["name"])
            if w is None:  # 已经从关注清单里删掉的不再显示
                continue
            for st in b.get("stories") or []:
                if st["url"] in w["_seen"]:
                    continue
                w["_seen"].add(st["url"])
                w["stories"].append({**st, "_issue": issue["date"], "_work": b["name"],
                                     "_cover": w.get("cover") or b.get("cover")})
    for w in works.values():
        w["stories"].sort(key=lambda x: x.get("date") or x["_issue"], reverse=True)  # 按消息本身的日期
    return list(works.values())


def _calm(block):
    """没有新消息时的小栏：封面小图、现状、往期最近一条。"""
    pic = _pic({"image": block.get("cover")}) if block.get("cover") else ""
    status = f'<span class="status">{_md_links(block["status"])}</span>' if block.get("status") else ""
    last = block.get("last")
    tail = ""
    if last:
        tail = (f'<a class="last" href="{e(last["url"])}" target="_blank" rel="noopener">'
                f'<span class="mono">最近 · {e(last["date"].replace("-", "."))}</span><b>{e(last["headline"])}</b></a>')
    return (f'<div class="calm">{pic}<div class="txt"><span class="tag">暂 无 新 消 息</span>{status}</div>'
            f"{tail}</div>")


def _section(block, anchor=""):
    t = block["theme"]
    style = (f"--bg:{t['bg']};--fg:{t['fg']};--acc:{t['accent']};--abg:{t['alt_bg']};"
             f"--afg:{t['alt_fg']};--aacc:{t['alt_accent']};--aac:{t['alt_accent']};"
             f"--line:color-mix(in srgb,{t['fg']} 22%,{t['bg']})")
    band_cls = "band split" if t.get("split") else "band"
    sub = f'<span class="sub">{e(block["subtitle"])}</span>' if block.get("subtitle") else ""
    # 状态只在有变化时上版面，没变化就是不必要的信息
    changed = [f for f in block.get("facts") or [] if f["changed"]]
    facts = ""
    if changed:
        facts = '<div class="facts">' + "".join(
            f'<div class="fact"><span class="label{" new" if f["changed"] else ""}">'
            f'{e(f["label"])}{" · 有变化" if f["changed"] else ""}</span><span>{_md_links(f["text"])}</span></div>'
            for f in changed
        ) + "</div>"
    today = block["_today"]
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HOLD_DAYS - 1)).isoformat()
    recent = [x for x in block["stories"] if x["_issue"] >= cutoff]
    older = [x for x in block["stories"] if x["_issue"] < cutoff]
    if recent:
        grid, more = _timeline(recent, today)
    else:
        grid, more = _calm({**block, "last": None}), []
    grid += _older(more + older, today, len(more))
    quiet = "" if recent else " quiet"
    return (f'<section id="{anchor}" data-k="{e(block["name"])}" class="sec {"serif" if t.get("font") == "serif" else "sans"}{quiet}" style="{style}">'
            f'<div class="{band_cls}"><span class="title">{e(block["name"])}</span>{sub}</div>'
            f"{facts}{grid}</section>")


def _picks(picks, works):
    """「我会喜欢？」角落：按愿望清单的喜好，从收集到的消息里挑的推荐，每条写明推荐理由。"""
    if not picks:
        return ""
    covers = {w["name"]: w.get("cover") for w in works}

    def cards_of(group, big_first):
        return "".join(card(x, big_first and i == 0) for i, x in enumerate(group))

    def card(x, big):
        follow = x.get("kind") == "follow"  # 同类新发现不是那个作品本身，没图时不能用它的封面
        story = {"image": x.get("image"), "_cover": None if follow else covers.get(x["work"]),
                 "_work": (x.get("hits") or [x["work"]])[0] if follow else x["work"]}
        tags = "".join(f"<i>{e(h)}</i>" for h in x.get("hits", []))
        date = e(x["date"][5:].replace("-", ".")) if x.get("date") else ""
        return (
            f'<a class="pk{" big" if big else ""}" href="{e(x["url"])}" target="_blank" rel="noopener">{_pic(story)}'
            f'<span class="pkt"><span class="src">{e(x["source"])}{" · " + date if date else ""}</span>'
            f'<b>{e(x["title"])}</b>'
            f'<span class="why">因为你{"关注" if x.get("kind") == "follow" else "想要"}「{e(x["because"])}」</span>'
            f'<span class="tags">{tags}</span></span></a>')

    wish = [x for x in picks if x.get("kind") != "follow"]
    follow = [x for x in picks if x.get("kind") == "follow"]
    body = f'<div class="pkgrid">{cards_of(wish, True)}</div>' if wish else ""
    if follow:
        body += (f'<div class="pksub">同类新发现<span>你关注的作品之外，同类型的新消息</span></div>'
                 f'<div class="pkgrid row" style="--n:{len(follow)}">{cards_of(follow, False)}</div>')
    return (f'<section class="picks" id="picks" data-k="picks"><div class="pkhead"><h2>我会喜欢<em>？</em></h2>'
            f'<span>根据愿望清单里的喜好和你关注的作品类型挑的 · <a href="wishlist.html">♥ 愿望清单</a></span></div>'
            f'{body}</section>')


def _wish_link(wishes, cls):
    """主页面上去愿望清单子页面的入口（报头右上角、左侧目录底部）。"""
    if not wishes:
        return ""
    want = sum(1 for x in wishes if (x.get("status") or "想要") == "想要")
    return (f'<a class="{cls}" href="wishlist.html"><b>♥</b><span>愿望清单</span>'
            f'<small>{want} 件想要</small></a>')


def render_wishlist(wishes, works, updated):
    """愿望清单子页面（docs/wishlist.html）：收藏柜式大图网格，可按状态筛选，顶部是件数和想要的总价。"""
    totals = {}
    for x in wishes:
        if (x.get("status") or "想要") == "想要" and isinstance(x.get("price"), (int, float)):
            cur = x.get("currency", "")
            totals[cur] = totals.get(cur, 0) + x["price"]
    total = " + ".join(f"{c} {v:,.0f}" for c, v in totals.items()) or "—"
    counts = {k: sum(1 for x in wishes if (x.get("status") or "想要") == k) for k in ("想要", "已入手", "没买到")}
    chips = "".join(f'<button type="button" class="chip" data-f="{k}" aria-pressed="{str(k == "全部").lower()}">'
                    f'{k}<small>{len(wishes) if k == "全部" else counts[k]}</small></button>'
                    for k in ("全部", "想要", "已入手", "没买到") if k == "全部" or counts[k])
    section = _wish_section(wishes, works)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>愿望清单</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}
.page{{grid-template-columns:minmax(0,1fr);max-width:1200px}}
.back{{display:inline-flex;align-items:center;gap:8px;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.15em}}
.back:hover{{color:#B8336A}}
.wsum{{display:flex;flex-wrap:wrap;align-items:center;gap:12px 28px}}
.wsum .stat{{display:flex;flex-direction:column;gap:2px}}
.wsum .stat span{{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.6}}
.wsum .stat b{{font:900 26px/1 'Noto Sans SC',sans-serif;font-variant-numeric:tabular-nums}}
.chips{{margin-left:auto;display:flex;flex-wrap:wrap;gap:8px}}
.chip{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border:2px solid #1A1C22;background:transparent;color:#1A1C22;
 font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.15em;cursor:pointer}}
.chip small{{font:700 11px 'JetBrains Mono',monospace;opacity:.6}}
.chip[aria-pressed="true"]{{background:#1A1C22;color:#F4EDE4}}
.chip:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.wish .band{{display:none}}
</style>
</head>
<body>
<div class="page">
<header class="mast"><div>
<div class="logo">{LOGO}</div>
<h1>愿望清单</h1>
<div class="meta"><div class="mono">更新于</div><div class="no">{updated.split(" ")[-1]}</div><div class="mono">{updated.split(" ")[0]}</div></div>
</div></header>
<a class="back" href="./">← 回到关注清单通信</a>
<div class="wsum">
<div class="stat"><span>共</span><b>{len(wishes)} 件</b></div>
<div class="stat"><span>想要的合计</span><b>{e(total)}</b></div>
<div class="chips" role="group" aria-label="按状态筛选">{chips}</div>
</div>
{section}
</div>
<script>
document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {{
  document.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', String(x === c)));
  const f = c.dataset.f;
  document.querySelectorAll('.wcard').forEach(w => {{ w.hidden = f !== '全部' && w.dataset.status !== f; }});
}}));
</script>
</body>
</html>
"""


def _wish_section(wishes, works):
    """愿望清单版面。只有一件时做成横向大卡，多件时自动排成网格。"""
    if not wishes:
        return ""
    latest = {w["name"]: (w["stories"][0] if w["stories"] else None) for w in works}
    cards = []
    for x in wishes:
        img = x.get("image") or ""
        if img and not img.startswith("http"):
            img = "wishlist/" + img
        status = x.get("status") or "想要"
        cls = {"已入手": "got", "没买到": "miss"}.get(status, "")
        price = ""
        if x.get("price") not in (None, ""):
            price = f'<div class="price"><small>{e(str(x.get("currency", "")))}</small>{e(str(x["price"]))}</div>'
        specs = "".join(f"<dt>{e(str(k))}</dt><dd>{e(str(v))}</dd>" for k, v in (x.get("specs") or {}).items())
        links = []
        if x.get("url"):
            links.append(f'<a href="{e(x["url"])}" target="_blank" rel="noopener">去看看 ↗</a>')
        watch = ""
        if x.get("watch"):
            links.append(f'<a href="./#{_wid(x["watch"])}">{e(x["watch"])} 版面 →</a>')
            st = latest.get(x["watch"])
            if st:
                watch = (f'<a class="watch" href="{e(st["url"])}" target="_blank" rel="noopener"><span>相关最新 · '
                         f'{e((st.get("date") or st["_issue"])[5:].replace("-", "."))}</span>{e(st["headline"])}</a>')
        added = f'<span class="added">加入于 {e(str(x["added"]).replace("-", "."))}</span>' if x.get("added") else ""
        cards.append(
            f'<article class="wcard{" solo" if len(wishes) == 1 else ""}" data-status="{e(status)}">'
            f'<div class="wimg">{f"""<img src="{e(img)}" alt="{e(x["name"])}" loading="lazy" referrerpolicy="no-referrer">""" if img else ""}'
            f'<span class="heart {cls}">♥ {e(status)}</span></div>'
            f'<div class="wtxt">' + (f'<span class="shop">{e(x["shop"])}</span>' if x.get("shop") else "")
            + f'<h3>{e(x["name"])}</h3>{price}'
            + (f"<dl>{specs}</dl>" if specs else "")
            + (f'<p class="note">{e(x["note"])}</p>' if x.get("note") else "")
            + watch + f'<div class="links">{"".join(links)}{added}</div></div></article>')
    want = sum(1 for x in wishes if (x.get("status") or "想要") == "想要")
    return (f'<section id="wishlist" data-k="wishlist" class="sec wish"><div class="band split">'
            f'<span class="title">愿望清单</span><span class="sub">WISHLIST · {len(wishes)} 件 · 想要 {want}</span></div>'
            f'<div class="wgrid">{"".join(cards)}</div></section>')


# 头版板块：固定的几个先排，颜色各不相同；items.yaml 里自己起的新板块用灰色
SECTIONS = {"游戏": "#2F5BD3", "影视": "#9B3FB5", "运动": "#1F9D6B", "演出": "#D6336C", "好物": "#E07A1F"}
SECTION_EN = {"游戏": "GAMES", "影视": "SCREEN", "运动": "SPORTS", "演出": "LIVE", "好物": "GOODS"}


def _sec_color(name):
    return SECTIONS.get(name, "#5B5F6B")


def _recent(w, today):
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HOLD_DAYS - 1)).isoformat()
    return [x for x in w["stories"] if x["_issue"] >= cutoff]


def _front(works, today, updated):
    """头版：最近一周的实时总览。头条 = 最近一周里最重要的一条（同样重要取最新）；
    板块索引 = 每个作品最新的一条；最新消息 = 所有作品按时间排的前 12 条。"""
    pool = [(w, x) for w in works for x in _recent(w, today)]
    newest = sorted(pool, key=lambda p: p[1].get("date") or p[1]["_issue"], reverse=True)
    top_w, top = min(newest, key=lambda p: RANK.get(p[1].get("weight"), 2)) if newest else (None, None)

    groups = {}
    for w in works:
        groups.setdefault(w.get("section") or "其他", []).append(w)
    order = [n for n in SECTIONS] + [n for n in groups if n not in SECTIONS]

    head = (f'<div class="fbar"><b>头 版</b><span>LATEST · 最近 {HOLD_DAYS} 天</span>'
            f'<span>更新于 {updated} · {len(pool)} 条</span></div>')

    # 头条下面补 3 条次重要的（按重要度，再按新旧），填满左栏
    ranked = sorted(newest, key=lambda p: RANK.get(p[1].get("weight"), 2))
    more = [p for p in ranked if p[1] is not top][:3]
    more_html = "".join(
        f'<a class="more" href="#{_wid(w["name"])}" style="--sc:{_sec_color(w.get("section"))}">{_pic(x)}'
        f'<span><span class="nm">{e(w["name"])} · {e((x.get("date") or x["_issue"])[5:].replace("-", "."))}</span>'
        f'<b>{e(x["headline"])}</b></span></a>' for w, x in more)
    if top:
        sc = _sec_color(top_w.get("section"))
        badge = "重 磅" if top.get("weight") == "hero" else "头 条"
        top_html = (f'<a class="top" href="{e(top["url"])}" target="_blank" rel="noopener">'
                    f'<span class="badge">{badge}</span>{_pic(top)}'
                    f'<span class="kicker"><i style="background:{sc}">{e(top_w.get("section") or "")}</i>'
                    f'{e(top_w["name"])} · {e((top.get("date") or top["_issue"])[5:].replace("-", "."))}</span>'
                    f'<h2>{e(top["headline"])}</h2>'
                    + (f'<p>{e(top["blurb"])}</p>' if top.get("blurb") else "") + "</a>")
        top_html = f'<div class="topcol">{top_html}<div class="mores"><h5>其他重要</h5>{more_html}</div></div>' if more else top_html
    else:
        top_html = f'<div class="top"><h2>最近 {HOLD_DAYS} 天没有新消息</h2></div>'

    boards = []
    for name in order:
        sc = _sec_color(name)
        rows = []
        for w in groups.get(name, []):
            rec = _recent(w, today)
            if rec:
                first = rec[0]
                text, img, cls = first["headline"], first.get("image") or w.get("cover"), "entry"
            else:
                text, img, cls = w.get("status") or "暂无新消息", w.get("cover"), "entry q"
            rows.append(f'<a class="{cls}" href="#{_wid(w["name"])}">{_pic({"image": img, "_work": w["name"], "_cover": w.get("cover")})}'
                        f'<span><span class="nm">{e(w["name"])}</span><b>{e(text)}</b></span></a>')
        body = "".join(rows) or '<div class="none">还没有关注项</div>'
        boards.append(f'<div class="board" style="--sc:{sc}"><h3>{e(name)}<small>{SECTION_EN.get(name, "")}</small></h3>{body}</div>')

    heads = [f'<li style="--sc:{_sec_color(w.get("section"))}"><i>{e(w.get("section") or "")}</i>'
             f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["headline"])}</a>'
             f'<span class="d">{e((x.get("date") or x["_issue"])[5:].replace("-", "."))}</span></li>'
             for w, x in newest if x is not top and all(x is not m for _, m in more)][:12]
    heads_html = ""
    if heads:
        heads_html = (f'<div class="heads"><h4>最新消息<small>LATEST HEADLINES</small></h4>'
                      f'<ol>{"".join(heads)}</ol></div>')
    return (f'<section class="front" data-k="front" id="front">{head}<div class="fbody">{top_html}'
            f'<div class="boards">{"".join(boards)}</div></div>{heads_html}</section>')


# 左侧目录的四种风格（items.yaml 的 settings.nav_style 选择）。只在宽屏生效，窄屏统一是顶部横条
NAV_STYLES = {
    # A 线路图：每个板块一段彩色线路，作品是站点；读到哪站圆点放大，线路按进度填色，读过的站变实心
    "line": """
.nav{top:0;height:100vh;max-height:none;padding:16px 0}
.nav .here{display:none}
.nav .rail{flex:1;padding-left:14px}
.nav .pill{flex:1 1 auto;min-height:44px;max-height:180px}
.nav .grp{flex:none}
.nav .grp{display:flex;align-items:baseline;gap:8px;padding:16px 0 4px 26px;color:var(--sc)}
.nav .grp b{font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.nav .grp small{font:700 9px 'JetBrains Mono',monospace;letter-spacing:.25em;opacity:.75}
.nav .pill{padding:9px 0 9px 26px;font:700 14px/1.3 'Noto Sans SC',sans-serif;color:rgba(26,28,34,.5);
 transition:color .2s,font-size .3s cubic-bezier(.2,.9,.3,1),padding .3s cubic-bezier(.2,.9,.3,1)}
.nav .pill::before{content:"";position:absolute;left:8px;top:0;bottom:0;width:3px;
 background:linear-gradient(var(--sc) calc(var(--p,0)*100%),rgba(26,28,34,.13) 0)}
.nav .pill::after{content:"";position:absolute;left:4px;top:50%;width:11px;height:11px;margin-top:-5.5px;border-radius:50%;
 background:#EDEBE6;border:2px solid rgba(26,28,34,.35);
 transition:width .35s cubic-bezier(.3,1.5,.5,1),height .35s cubic-bezier(.3,1.5,.5,1),margin .35s cubic-bezier(.3,1.5,.5,1),left .35s cubic-bezier(.3,1.5,.5,1),border-color .2s}
.nav .pill .no{display:none}
.nav .pill .nm{display:flex;flex-direction:column;gap:3px}
.nav .pill .cnt{display:none;font:700 10px 'JetBrains Mono',monospace;letter-spacing:.12em;color:var(--sc)}
.nav .pill:hover{color:#1A1C22}
.nav .pill.past{color:rgba(26,28,34,.72)}
.nav .pill.past::after{background:var(--sc);border-color:var(--sc)}
.nav .pill.on{color:#1A1C22;font-size:21px;font-weight:900;letter-spacing:-.01em;padding:16px 0 16px 40px}
.nav .pill.on .cnt{display:block}
.nav .pill.on::after{width:38px;height:38px;margin-top:-19px;left:-9px;
 background:var(--img,none) center/cover no-repeat,#EDEBE6;border:3px solid var(--sc);
 box-shadow:0 0 0 5px color-mix(in srgb,var(--sc) 20%,transparent),0 6px 14px rgba(26,28,34,.25)}
.nav select{margin:14px 0 0 26px;align-self:flex-start;background:transparent;color:#1A1C22;border:1px solid rgba(26,28,34,.35)}
""",
    # B 报纸索引栏：米色纸面、双线，条目带编号和引导点；当前条目反白成板块色色块并放大
    "index": """
.nav{background:#FBF8F1;color:#1A1C22;border:3px solid #1A1C22;box-shadow:6px 6px 0 #1A1C22;padding:0}
.nav .here{display:flex;flex-direction:column;gap:2px;padding:14px 16px 12px;border-bottom:3px double #1A1C22;text-align:center}
.nav .here b{font:900 30px/1 'Noto Serif SC',serif;letter-spacing:.4em;padding-left:.4em}
.nav .here small{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.45em;color:#D7261E}
.nav .here span{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.1em;opacity:.7}
.nav .rail{padding:4px 0 10px}
.nav .grp{display:flex;align-items:center;gap:8px;margin:12px 12px 4px;padding:3px 8px;background:var(--sc);color:#FFF}
.nav .grp b{font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.nav .grp small{margin-left:auto;font:700 9px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.9}
.nav .pill{margin:0 12px;padding:7px 8px;font:700 14px/1.35 'Noto Serif SC',serif;border-bottom:1px dotted rgba(26,28,34,.35);
 transition:background .2s,color .2s,font-size .2s,padding .2s}
.nav .pill .no{color:var(--sc);min-width:18px}
.nav .pill .nm{flex:1;min-width:0}
.nav .pill::after{content:"";position:absolute;left:0;bottom:-1px;height:3px;width:calc(var(--p,0)*100%);background:var(--sc)}
.nav .pill:hover .nm{text-decoration:underline;text-underline-offset:3px}
.nav .pill.past{opacity:.55}
.nav .pill.on{background:var(--sc);color:#FFF;font-size:18px;font-weight:900;padding:12px 10px;opacity:1}
.nav .pill.on .no{color:#FFD23F}
.nav .pill.on::after{background:#FFD23F}
.nav select{margin:0 12px 12px;background:#FBF8F1;color:#1A1C22;border:2px solid #1A1C22}
""",
    # C 活页夹标签：每个作品是一张贴在内容左缘的彩色索引签；当前那张向右抽出、变大
    "tabs": """
.nav{padding:0;background:none}
.page{grid-template-columns:220px minmax(0,1fr);column-gap:0}
.nav .here{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;padding:0 0 10px 4px}
.nav .here b{font:900 24px/1 'Noto Sans SC',sans-serif;letter-spacing:.2em;white-space:nowrap}
.nav .here small{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.3em;color:#D7261E}
.nav .here span{flex-basis:100%;font:700 10px 'JetBrains Mono',monospace;opacity:.6}
.nav .rail{gap:5px;padding:4px 0 8px;overflow-x:visible}
.nav .grp{display:flex;align-items:baseline;gap:6px;padding:10px 4px 2px;color:var(--sc)}
.nav .grp b{font:900 12px 'Noto Sans SC',sans-serif;letter-spacing:.3em}
.nav .grp small{font:700 9px 'JetBrains Mono',monospace;letter-spacing:.2em}
.nav .pill{margin-left:28px;padding:10px 12px;background:color-mix(in srgb,var(--sc) 22%,#FBF8F1);color:#1A1C22;
 border:2px solid #1A1C22;border-right:none;font:900 14px/1.25 'Noto Sans SC',sans-serif;
 clip-path:polygon(10px 0,100% 0,100% 100%,10px 100%,0 calc(100% - 10px),0 10px);
 transition:margin .3s cubic-bezier(.3,1.5,.5,1),background .2s,color .2s,font-size .2s}
.nav .pill .no{color:var(--sc)}
.nav .pill::after{content:"";position:absolute;left:0;bottom:0;height:4px;width:calc(var(--p,0)*100%);background:#1A1C22}
.nav .pill:hover{margin-left:18px}
.nav .pill.past{background:color-mix(in srgb,var(--sc) 10%,#FBF8F1);color:rgba(26,28,34,.6)}
.nav .pill.on{margin-left:0;background:var(--sc);color:#FFF;font-size:17px;padding:14px 14px}
.nav .pill.on .no{color:#FFD23F}
.nav .pill.on::after{background:#FFD23F}
.nav select{margin:6px 0 0 28px;background:#FBF8F1;color:#1A1C22;border:2px solid #1A1C22}
""",
    # D 大字滚动：没有框，只有字；当前作品放大成巨大的板块色标题，其余缩小变淡，像焦点在移动
    "type": """
.nav{padding:4px 0}
.nav .here{display:flex;flex-direction:column;gap:2px;padding-bottom:12px;border-bottom:3px solid #1A1C22}
.nav .here b{font:900 13px 'JetBrains Mono',monospace;letter-spacing:.5em}
.nav .here small{display:none}
.nav .here span{font:700 11px 'JetBrains Mono',monospace;opacity:.6}
.nav .rail{padding:8px 0;mask-image:linear-gradient(transparent,#000 6%,#000 94%,transparent)}
.nav .grp{display:flex;gap:6px;align-items:baseline;padding:14px 0 2px;color:var(--sc)}
.nav .grp b{font:900 11px 'Noto Sans SC',sans-serif;letter-spacing:.4em}
.nav .grp small{font:700 9px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.8}
.nav .pill{flex-direction:column;align-items:flex-start;gap:0;padding:5px 0;color:rgba(26,28,34,.38);
 font:900 15px/1.15 'Noto Sans SC',sans-serif;letter-spacing:-.01em;transition:font-size .35s cubic-bezier(.2,.9,.3,1),color .25s,padding .35s}
.nav .pill .no{font-size:10px;color:inherit}
.nav .pill:hover{color:#1A1C22}
.nav .pill.past{color:rgba(26,28,34,.55)}
.nav .pill.on{color:var(--sc);font-size:34px;line-height:1.02;padding:10px 0 12px}
.nav .pill.on .no{color:#1A1C22}
.nav .pill.on::after{content:"";height:4px;width:calc(var(--p,0)*100%);background:var(--sc);margin-top:8px;transition:width .15s linear}
.nav select{margin-top:8px;background:transparent;color:#1A1C22;border:2px solid #1A1C22}
""",
}


def _nav(works, date, wishes=(), picks=()):
    """左侧目录：按板块分组列出每个作品。"""
    groups = {}
    for w in works:
        groups.setdefault(w.get("section") or "其他", []).append(w)
    order = [n for n in SECTIONS if n in groups] + [n for n in groups if n not in SECTIONS]
    cutoff = (dt.date.fromisoformat(date) - dt.timedelta(days=HOLD_DAYS - 1)).isoformat()
    rail = [f'<a class="pill front-k" style="--sc:#D7261E" data-for="front" href="#front">'
            f'<i class="no">00</i><span class="nm">头版<small class="cnt">FRONT PAGE</small></span></a>']
    if picks:
        rail.append(f'<a class="pill" style="--sc:#B8336A" data-for="picks" href="#picks">'
                    f'<i class="no">?</i><span class="nm">我会喜欢？<small class="cnt">{len(picks)} 条推荐</small></span></a>')
    n = 0
    for name in order:
        sc = _sec_color(name)
        rail.append(f'<div class="grp" style="--sc:{sc}"><b>{e(name)}</b><small>{SECTION_EN.get(name, "")}</small></div>')
        for w in groups[name]:
            n += 1
            recent = [x for x in w["stories"] if x["_issue"] >= cutoff]
            img = next((x.get("image") for x in recent if x.get("image")), None) or w.get("cover") \
                or next((x.get("image") for x in w["stories"] if x.get("image")), None)
            css_img = f";--img:url({urllib.parse.quote(img, safe=':/?&=%#@+,;~')})" if img else ""
            cnt = f"一周 {len(recent)} 条" if recent else "暂无新消息"
            rail.append(f'<a class="pill" style="--sc:{sc}{e(css_img)}" data-for="{e(w["name"])}" '
                        f'href="#{_wid(w["name"])}"><i class="no">{n:02d}</i>'
                        f'<span class="nm">{e(w["name"])}<small class="cnt">{cnt}</small></span></a>')
    return (f'<nav class="nav" aria-label="目录">'
            f'<div class="here"><b>目录</b><small>INDEX</small><span id="nav-here"></span></div>'
            f'<div class="rail" id="nav-rail">{"".join(rail)}</div>{_wish_link(wishes, "navwish")}'
            f'<div class="bar" id="nav-bar"></div></nav>')


NAV_JS = """
(() => {
  const nav = document.querySelector('.nav'), rail = document.getElementById('nav-rail'),
        here = document.getElementById('nav-here');
  const marks = [...document.querySelectorAll('[data-k]')];
  const pills = [...rail.querySelectorAll('.pill')];
  const firstIssue = document.querySelector('.issue');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = null, ticking = false;
  function update() {
    ticking = false;
    const horizontal = getComputedStyle(rail).flexDirection === 'row';
    const y = (horizontal ? nav.getBoundingClientRect().bottom : 0) + 40;
    let m = marks[0];
    for (const el of marks) { if (el.getBoundingClientRect().top <= y) m = el; else break; }
    if (!m) return;
    const r = m.getBoundingClientRect();
    const prog = Math.min(1, Math.max(0, (y - r.top) / r.height));
    nav.style.setProperty('--prog', prog.toFixed(3));
    const today = m.closest('.issue') === firstIssue;
    let idx = -1;
    pills.forEach((p, i) => { if (today && p.dataset.for === m.dataset.k) idx = i; });
    pills.forEach((p, i) => {
      p.classList.toggle('on', i === idx);
      p.classList.toggle('past', idx >= 0 && i < idx);
      p.style.setProperty('--p', i === idx ? prog.toFixed(3) : (idx >= 0 && i < idx ? 1 : 0));
    });
    if (m === cur) return;
    cur = m;
    const issue = m.closest('.issue');
    here.textContent = issue ? issue.dataset.label : '';
    const on = pills[idx];
    nav.style.setProperty('--cur', on ? getComputedStyle(on).getPropertyValue('--sc') : '#8C8678');
    if (on) {
      const opt = horizontal ? { left: on.offsetLeft - rail.clientWidth / 2 + on.offsetWidth / 2 }
                             : { top: on.offsetTop - rail.clientHeight / 2 + on.offsetHeight / 2 };
      rail.scrollTo({ ...opt, behavior: reduce ? 'auto' : 'smooth' });
    }
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  addEventListener('resize', update);
  update();
})();
"""


def render(issues, nav_style="line", order=None, updated=None, wishes=(), picks=()):
    """issues：按时间倒序的各期数据（全部）。nav_style：左侧目录风格，见 NAV_STYLES。
    order：items.yaml 里作品的顺序；updated：网页更新时间（显示用）。"""
    latest = issues[0]
    works = collect(issues, order)
    for w in works:
        w["_today"] = latest["date"]
    updated = updated or latest["date"].replace("-", ".")
    # id 保留 issue-日期：Discord 通知里的链接指向这里
    body = (f'<div class="issue" id="issue-{latest["date"]}" data-label="更新于 {updated}">'
            + _front(works, latest["date"], updated) + _picks(picks, works)
            + "".join(_section(w, _wid(w["name"])) for w in works) + "</div>")
    parts = [body]
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关注清单通信</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}@media (min-width:1001px){{{NAV_STYLES.get(nav_style, NAV_STYLES["line"])}}}</style>
</head>
<body>
<div class="page">
<header class="mast"><div>
<div class="logo">{LOGO}</div>
<h1>关注清单通信</h1>
{_wish_link(wishes, "mastwish")}
<div class="meta"><div class="mono">更新于</div><div class="no">{updated.split(" ")[-1]}</div><div class="mono">{updated.split(" ")[0]}</div></div>
</div></header>
{_nav(works, latest['date'], wishes, picks)}
<main class="issues">{''.join(parts)}</main>
</div>
<script>{NAV_JS}</script>
</body>
</html>
"""
