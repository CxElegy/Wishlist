"""把所有期的数据渲染成一张报纸式简报网页（docs/index.html）。消息永远保留，不随新一期消失。

版式规则：
- 左侧目录（撑满屏幕高度）：按板块分组列出每个作品，滚动时当前所在的一项放大并换成板块色，点击直达
- 最上面一张「头版」：最近一周的实时总览（最重要的一条做头条 + 各作品最新一条 + 最新消息列表）
- 版面数量和顺序固定（板块 → items.yaml 顺序）；每天更新只是版面里的消息变化
- 每个关注项一个版面，配色取自该作品（theme.py）。所有日期的消息汇总在一起，按时间排列（新的在前）：
  - 一周内收到的直接显示（最多多高按篇幅 S / M / L，L 约一屏），卡片大小按重要度：hero 整行、lead 8 栏、普通 4 栏，每行自动补满；
    放不下时先按重要度挑出留下的，留下的再按时间排
  - 更早的收进版面底部的「更早的消息」折叠区，点开才显示
- 一周内没有新消息的关注项只留一个小栏：标题条 + 现状
"""

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse

from images import FAVICON_SERVICE, GENERIC, base_domain  # 网站 logo / 默认分享图的判断，和找图用同一条规则

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
.pic.icon{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
 background:color-mix(in srgb,currentColor 6%,transparent)}
.pic.icon img.ico{position:static;width:min(64px,30%);height:auto;aspect-ratio:1;object-fit:contain;
 background:#FFFFFF;border-radius:14px;padding:6px;box-shadow:0 1px 4px rgba(0,0,0,.18)}
.pic.icon .src{max-width:90%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 font:600 13px 'JetBrains Mono','Noto Sans SC',monospace;opacity:.75}
.pic:not(.icon) img.ico,.pic:not(.icon) .src{display:none}
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
/* 宽屏：目录占左栏从页面最上面开始（报头只在右栏），上下滚动时位置都不动。
   负的上边距抵掉 .page 的上内边距（40px）和吸顶位置的差，一打开就已经在吸顶的位置；
   页面底部的留白挪进右栏，滚到底时目录也不会被顶上去 */
@media (min-width:1001px){
 .page{padding-bottom:0}.mast{grid-column:2;grid-row:1}.issues{grid-column:2;grid-row:2;padding-bottom:40px}
 .nav{grid-column:1;grid-row:1/3;margin-top:-24px}}
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
.wgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.wcard{position:relative;display:flex;flex-direction:column;background:var(--bg);box-shadow:0 0 0 .5px var(--line)}
.wcard.solo{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr)}
.wcard .wimg{position:relative;aspect-ratio:1/1;max-width:100%;background:#FFF;display:grid;place-items:center;overflow:hidden}
.wcard.solo .wimg{aspect-ratio:auto;min-height:380px}
.wcard .wimg img{position:absolute;inset:7%;width:86%;height:86%;object-fit:contain;transition:transform .4s cubic-bezier(.2,.9,.3,1)}
.wcard:hover .wimg img{transform:scale(1.04) rotate(-1.5deg)}
.wcard .heart{position:absolute;top:14px;left:14px;padding:4px 10px;background:var(--acc);color:#FFF;
 font:900 12px 'Noto Sans SC',sans-serif;letter-spacing:.25em}
.wcard .heart.got{background:#1F9D6B}.wcard .heart.miss{background:#8C8678}.wcard .heart.torn{background:#B5650D}
.wcard .wtxt{display:flex;flex-direction:column;gap:14px;padding:24px 26px;min-width:0}
.wcard.solo .wtxt{justify-content:center;padding:36px 40px;border-left:1px solid var(--line)}
.wcard .shop{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;color:var(--acc)}
.wcard h3{margin:0;font:900 26px/1.3 'Noto Sans SC',sans-serif;text-wrap:pretty}
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
.mastset{display:flex;align-items:center;justify-content:center;padding:0 16px;border-left:1px solid #1A1C22;
 font-size:20px;color:#1A1C22;opacity:.55}
.mastset:hover{opacity:1;background:#1A1C22;color:#F4EDE4}
@media (max-width:760px){.mastset{padding:0 8px}}
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
.pk>a{display:flex;flex-direction:column;gap:10px;min-width:0;flex:1}
.pk>a:hover b{text-decoration:underline;text-underline-offset:3px}
.pk .taste{font-size:11px;opacity:.7}
.vote{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.pk:not(.big) .vote button span{display:none}
.pk:not(.big) .vote button{padding:4px 12px;font-size:14px}
.pk.big>a{flex:none}
.vote button{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border:1.5px solid #1A1C22;background:transparent;
 color:#1A1C22;font:700 12px 'Noto Sans SC',sans-serif;cursor:pointer;border-radius:0;white-space:nowrap}
.vote button:hover{background:#1A1C22;color:#F4EDE4}
.vote button[aria-pressed=true]{background:#B8336A;border-color:#B8336A;color:#FFF}
.vote button:disabled{opacity:.5;cursor:wait}
.vote small{font-size:11px;opacity:.7}
.pk.down>a{opacity:.35;filter:grayscale(1)}
.card,.top{position:relative}
.vt{position:absolute;top:8px;right:8px;z-index:3;display:flex;gap:4px;opacity:.55;transition:opacity .15s}
.card:hover .vt,.top:hover .vt,.vt:focus-within,.vt.on{opacity:1}
.vt button{padding:2px 7px;border:1px solid currentColor;background:color-mix(in srgb,var(--bg,#F4EDE4) 85%,transparent);
 color:inherit;font-size:13px;line-height:1.4;cursor:pointer;border-radius:0}
.vt button[aria-pressed=true]{background:#B8336A;border-color:#B8336A;color:#FFF}
.brief li .vt{position:static;opacity:.5;margin-left:auto;flex:none}
.brief li:hover .vt{opacity:1}
.downv{opacity:.4;filter:grayscale(.8)}
.pkbatch[hidden]{display:none}
.shuffle{margin-left:auto;padding:6px 14px;border:2px solid #1A1C22;background:#1A1C22;color:#F4EDE4;
 font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.1em;cursor:pointer;border-radius:0;white-space:nowrap}
.shuffle:hover{background:#B8336A;border-color:#B8336A}
.shuffle small{font:700 11px 'JetBrains Mono',monospace;opacity:.75;margin-left:6px}
.pknav{margin-left:auto;display:flex;gap:8px;white-space:nowrap}.pknav .shuffle{margin-left:0}.shuffle.back{background:none;color:#1A1C22}
.shuffle[disabled]{opacity:.3;cursor:default;pointer-events:none}
@media (hover:none){.vt{opacity:.9}}
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
.brief{padding:14px 24px 18px;border-top:1px solid var(--line)}
.brief h4{margin:0 0 8px;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.7}
.brief ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.brief li{display:flex;gap:14px;align-items:baseline;font-size:16px;line-height:1.5}
.brief .d{font:700 12px 'JetBrains Mono',monospace;opacity:.6;flex:none}
.brief a{color:inherit;text-decoration:none;font-weight:700}
.brief a:hover,.brief a:focus-visible{color:var(--acc);text-decoration:underline}
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
/* 一周内的版面要一屏装得下：图限高（底层模糊铺满，图不裁切），标题限行数；普通消息做成左图右字的小卡片 */
.grid>.hero .pic{aspect-ratio:auto;height:260px}
.grid>.lead .pic{aspect-ratio:auto;height:240px}.grid>.lead h2{font-size:30px}
.card.wide{grid-template-columns:4fr 8fr}
.grid>.lead h2,.card.wide h3,.mini h3{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.grid>.lead .blurb,.card.wide .blurb{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card.mini{display:grid;grid-template-columns:150px minmax(0,1fr);grid-template-rows:auto 1fr;gap:6px 16px;padding:14px 18px;align-content:start}
.mini .pic{grid-row:span 2;align-self:start}
.mini .pic .ph{font-size:13px}.mini .pic.icon{gap:4px}.mini .pic.icon img.ico{width:min(40px,30%);border-radius:9px;padding:4px}
.mini .pic.icon .src{font-size:11px}
.mini h3{margin:0;align-self:start;font-weight:900;font-size:17px;line-height:1.45}
.side .card.mini{grid-template-columns:120px minmax(0,1fr);gap:6px 14px}
@media (max-width:760px){
 .grid>.hero .pic,.grid>.lead .pic{height:200px}.grid>.lead h2{font-size:24px}
 .card.mini{grid-template-columns:120px minmax(0,1fr);padding:12px 14px}.mini h3{font-size:16px}}
@media (max-width:760px){
 .c12,.c8,.c6,.c4,.c3{grid-column:span 12}.card.wide{grid-template-columns:1fr;padding:20px}
 .card.c8 h3,.card.wide h3{font-size:24px}
 .fbody{grid-template-columns:1fr}.top{border-right:none;border-bottom:3px solid #1A1C22}.topcol{border-right:none}
 .mores .more:nth-of-type(n+4){display:none}
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


# 主图打不开：换下一张备用图（同一版面已经有这张图就跳过，免得两张卡片同一张图），背景模糊图跟着换；
# 备用图也用完了：有来源图标就换成来源图标，没有才显示作品名封面块
SWAP_JS = ("var me=this,p=me.parentNode,b=p.querySelector('img.bg'),s=me.closest('section'),"
           "f=(me.dataset.fb||'').split(' ').filter(function(u){return u&&!(s&&[].some.call("
           "s.querySelectorAll('.pic img:not(.bg)'),function(i){return i!==me&&i.src===u}))});"
           "if(f.length){me.src=f.shift();me.dataset.fb=f.join(' ');if(b)b.src=me.src}"
           "else{var ic=p.querySelector('img.ico');if(b)b.remove();me.remove();"
           "if(ic){p.classList.add('icon');var l=ic.dataset.icons.split(' ');ic.src=l.shift();ic.dataset.icons=l.join(' ')}"
           "else{p.classList.add('none')}}")
# 来源图标打不开、或者只有 16px（Google 图标服务查不到时给的地球图标）：换下一个，都不行才是作品名封面块
ICON_NEXT_JS = ("var l=(this.dataset.icons||'').split(' ').filter(Boolean);"
                "if(l.length){this.src=l.shift();this.dataset.icons=l.join(' ')}"
                "else{var p=this.closest('.pic');p.classList.remove('icon');p.classList.add('none');this.remove()}")
ICON_LOAD_JS = "if(this.naturalWidth<32){" + ICON_NEXT_JS + "}"


def _icons(story):
    """来源网站图标的候选，按顺序试：出刊时找好、检查过的；然后用 Google 的公开网站图标服务，
    先完整域名再主域名（news.17173.com 有 32px 的，17173.com 只有 16px）。看不出来源的返回空。"""
    host = (urllib.parse.urlparse(story.get("url") or "").hostname or "").lower()
    if not host or host == "news.google.com":
        return []
    found = [story.get("source_icon")] + [FAVICON_SERVICE.format(host=h) for h in (host, base_domain(host))]
    return list(dict.fromkeys(u for u in found if u))


def _source_name(story):
    host = (urllib.parse.urlparse(story.get("url") or "").hostname or "").lower()
    return story.get("source") or host.removeprefix("www.")


def _pic(story):
    """配图。底层模糊铺满，上层完整显示：图片不裁切，也不留空白条。
    兜底顺序：自己的图 → _fbs 里的备用图（作品封面）→ 来源网站的图标和网站名 → 作品名排版的封面块。
    前一个打不开（防盗链、网站删图、图标太小……）网页上自动换下一个。"""
    img, name = story.get("image"), story.get("_work", "")
    fbs = story.get("_fbs") if story.get("_fbs") is not None else [story.get("_cover")]
    chain = list(dict.fromkeys(u for u in [img, *fbs] if u))  # 第一张是 src，其余按顺序备用
    fb = f' data-fb="{e(" ".join(chain[1:]))}"' if len(chain) > 1 else ""
    src = chain[0] if chain else None
    tag = (f'<img class="bg" src="{e(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
           f'<img src="{e(src)}"{fb} alt="" loading="lazy" referrerpolicy="no-referrer" onerror="{e(SWAP_JS)}">') if src else ""
    label = f'<span class="ph">{e(name)}</span>' if name else ""
    icons = _icons(story)
    icon = ""
    if icons:  # 有图时先不加载图标（data-icons 里排着），图全打不开才换上；没图就直接显示图标
        first, rest = (None, icons) if src else (icons[0], icons[1:])
        icon = (f'<img class="ico"{f" src={chr(34)}{e(first)}{chr(34)}" if first else ""} data-icons="{e(" ".join(rest))}" '
                f'alt="" loading="lazy" referrerpolicy="no-referrer" onload="{e(ICON_LOAD_JS)}" onerror="{e(ICON_NEXT_JS)}">'
                f'<span class="src">{e(_source_name(story))}</span>')
    cls = "" if src else " icon" if icons else " none"
    return f'<div class="pic{cls}">{label}{tag}{icon}</div>'


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
    """按顺序排成行，不改变时间顺序；一行放不下就换行，凑不满的行平分整行（和一周内的普通消息一样）。
    不把空位全给一张：2 条会变成 9 栏 + 3 栏，而样式表没有 c9，那张卡片会缩成一栏宽。"""
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
        if sum(w for _, w in row) < total and total % len(row) == 0:
            for x in row:
                x[1] = total // len(row)
    return [x for row in rows for x in row]


def _when(story, today):
    d = story.get("date") or story["_issue"]
    # NEW 只给最近 24 小时左右发布的消息（按消息本身的日期，不是收集到的日期）
    new = "<b>NEW</b>" if d >= (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat() else ""
    return f'<span class="when">{new}{e(d[5:].replace("-", "."))}</span>'


def _tcard(story, span, i, today, small=False, mini=False):
    side = "a" if small else "m"  # 不再黑白交替：一周内统一主色底，折叠区统一副色底
    w = story.get("weight", "normal")
    url = e(story["url"])
    if mini:  # 普通消息：左边小图、右边日期和标题
        return (f'<a class="card {side} mini c{span}" href="{url}" target="_blank" rel="noopener">{_pic(story)}'
                f'{_when(story, today)}<h3>{_headline(story)}</h3></a>')
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


# 每个作品一周内直接显示的消息最多占多高（像素，按桌面版 1200 宽的实际高度估算），按篇幅（数据库 sizes 表）：
# L 是一屏（900 高的窗口减掉作品名横条和「更多消息」那一行），M 大约半屏，S 大约一行；表里没有的按 M。
# 同时限条数：小卡片很矮，只按高度算的话没有头条的版面能塞进十几条
SIZE_HEIGHT = {"S": 300, "M": 400, "L": 760}
SIZE_COUNT = {"S": 3, "M": 4, "L": 10}
SIZE_SIDE = {"S": 0, "M": 0, "L": 3}  # 头条右边竖排几条普通消息；0 是头条单独一行（图在左、字在右，矮得多）


def _layout(stories, side=SIZE_SIDE["L"]):
    """一周内消息的版式（保持时间顺序）：
    重大 → 整行大图；头条 → 左 8 栏，右边竖排接下来的最多 side 条普通消息（没有就一张占整行）；
    一周里每期都有头条，只有最新的那条做大图，更早的头条当普通消息排；
    普通消息做成左图右字的小卡片，三张一排，凑不满时平分整行。返回 [(行类型, 卡片列表)]。"""
    rows, normals, led = [], [], False

    def flush():
        if normals:
            rows.append(("normal", normals[:]))
            normals.clear()

    for x in stories:
        w = x.get("weight", "normal")
        if w == "hero":
            flush()
            rows.append(("hero", [x]))
        elif w == "lead" and not led:
            flush()
            rows.append(("lead", [x]))
            led = True
        else:
            last = rows[-1] if rows and not normals else None
            if last and last[0] == "lead" and len(last[1]) <= side:
                last[1].append(x)
            else:
                normals.append(x)
                if len(normals) == 3:
                    flush()
    flush()
    return rows


def _row_h(kind, cards):
    """这一行在桌面版上大约多高（照实际网页量的，标题按最多行数算）。"""
    if kind == "hero":
        return 310
    if kind == "lead":
        return 260 if len(cards) == 1 else 470
    return 125


def _height(stories, side=SIZE_SIDE["L"]):
    return sum(_row_h(k, c) for k, c in _layout(stories, side))


def _render_rows(rows, today):
    out, i = [], 0
    for kind, cards in rows:
        if kind == "hero":
            out.append(_tcard(cards[0], 12, i, today))
        elif kind == "lead":
            if len(cards) == 1:
                out.append(_tcard(cards[0], 12, i, today))
            else:
                out.append(_tcard(cards[0], 8, i, today))
                out.append('<div class="side">' + "".join(_tcard(c, 4, i, today, mini=True) for c in cards[1:]) + "</div>")
        else:
            span = {1: 12, 2: 6, 3: 4}[len(cards)]
            out += [_tcard(c, span, i, today, mini=True) for c in cards]
        i += 1
    return "".join(out)


def _timeline(stories, today, budget=SIZE_HEIGHT["M"], limit=SIZE_COUNT["M"], side=SIZE_SIDE["M"]):
    """一周内的消息，最多放 budget 高、limit 条，头条右边最多 side 条（见 SIZE_HEIGHT / SIZE_COUNT / SIZE_SIDE）。放不下时按重要度挑：
    重要的先留（同样重要的取新的），放得下就留下；留下的再按时间排列显示，其余返回给折叠区。"""
    def newest_first(xs):
        return sorted(xs, key=lambda x: x.get("date") or x["_issue"], reverse=True)

    keep = stories
    if len(stories) > limit or _height(stories, side) > budget:
        by_rank = sorted(newest_first(stories), key=lambda x: RANK.get(x.get("weight"), 2))
        keep = []
        for x in by_rank:
            if len(keep) >= limit:
                break
            trial = newest_first(keep + [x])
            if not keep or _height(trial, side) <= budget:
                keep = trial
    kept = {id(x) for x in keep}
    rest = [x for x in stories if id(x) not in kept]
    return '<div class="grid">' + _render_rows(_layout(keep, side), today) + "</div>", rest


def _has_photo(x):
    """有真正的图（自己的图，或这一版面唯一一次的作品封面）。"""
    return bool(x.get("image") or x.get("_fbs"))


def _has_pic(x):
    """能做成卡片：有图，或者至少有来源网站的图标。"""
    return _has_photo(x) or bool(_icons(x))


def _brief(stories):
    """连来源图标都没有的消息：只列日期和标题（不做空图卡片，也不拿别的图顶替）。"""
    if not stories:
        return ""
    rows = "".join(f'<li><span class="d">{e((x.get("date") or x["_issue"])[5:].replace("-", "."))}</span>'
                   f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["headline"])}</a></li>' for x in stories)
    return f'<div class="brief"><h4>其他消息</h4><ul>{rows}</ul></div>'


def _older(stories, today, more=0, texts=()):
    """折叠区：一周内放不下的（more 条）+ 一周以前的；没图的一周前消息列在最后。"""
    if not stories and not texts:
        return ""
    if not stories:
        return (f'<details class="older"><summary>更早的消息 · {len(texts)} 条<span></span></summary>'
                f'{_brief(texts)}</details>')
    packed = _pack(stories, lambda s: 3)
    first, last = stories[-1].get("date") or stories[-1]["_issue"], stories[0].get("date") or stories[0]["_issue"]
    rng = f"{first[5:].replace('-', '.')} – {last[5:].replace('-', '.')}"
    cards = "".join(_tcard(s, w, i, today, small=True) for i, (s, w) in enumerate(packed))
    label = "更多消息" if more else "更早的消息"
    detail = f"一周内另有 {more} 条" + (f" · 更早 {len(stories) - more} 条" if len(stories) > more else "") if more else rng
    return (f'<details class="older"><summary>{label} · {len(stories) + len(texts)} 条<span>{detail}</span></summary>'
            f'<div class="grid">{cards}</div>{_brief(texts)}</details>')


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
        # 没有自己图的报道：作品封面每个版面只用一次（几张卡片同一张图很难看），其余显示作品名封面块。
        # 不拿同一项别的报道的图来顶：那是另一件事的图，放上去是错的
        cover = w.get("cover")
        if cover and GENERIC.search(urllib.parse.urlparse(cover).path):
            cover = None  # 封面是品牌 logo（gelato pique）：不拿来顶替报道的图
        cover_used = any(x.get("image") == cover for x in w["stories"]) if cover else True
        w["_fbs"] = [cover] if cover else []
        # 代表整个关注项的小图（目录、暂无新消息小栏）：封面，没有就用它最近一条报道的图
        w["_thumb"] = cover or next((x["image"] for x in w["stories"] if x.get("image")), None)
        for x in w["stories"]:
            if x.get("image"):
                x["_fbs"] = [cover] if cover and cover != x["image"] else []  # 自己的图打不开时才换封面
            elif not cover_used:
                x["_fbs"], cover_used = [cover], True
            else:
                x["_fbs"] = []
    return list(works.values())


def _calm(block):
    """没有新消息时的小栏：封面小图、现状、往期最近一条。"""
    pic = _pic({"image": block.get("_thumb")}) if block.get("_thumb") else ""
    status = f'<span class="status">{_md_links(block["status"])}</span>' if block.get("status") else ""
    last = block.get("last")
    tail = ""
    if last:
        tail = (f'<a class="last" href="{e(last["url"])}" target="_blank" rel="noopener">'
                f'<span class="mono">最近 · {e(last["date"].replace("-", "."))}</span><b>{e(last["headline"])}</b></a>')
    tag = "正 在 收 集" if block.get("collecting") else "暂 无 新 消 息"
    return (f'<div class="calm">{pic}<div class="txt"><span class="tag">{tag}</span>{status}</div>'
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
    # 有图（自己的图，或这一版面唯一一次的作品封面）的做图片卡片；没图的配图位置显示来源网站图标；
    # 连来源都看不出（没还原的 Google 新闻跳转）的不做空卡片，放进「其他消息」文字列表
    recent = [x for x in block["stories"] if x["_issue"] >= cutoff and _has_pic(x)]
    older = [x for x in block["stories"] if x["_issue"] < cutoff and _has_pic(x)]
    texts = [x for x in block["stories"] if x["_issue"] >= cutoff and not _has_pic(x)]
    old_texts = [x for x in block["stories"] if x["_issue"] < cutoff and not _has_pic(x)]
    if recent:
        size = block.get("_size") if block.get("_size") in SIZE_HEIGHT else "M"
        grid, more = _timeline(recent, today, SIZE_HEIGHT[size], SIZE_COUNT[size], SIZE_SIDE[size])
    elif texts:
        grid, more = "", []
    else:
        grid, more = _calm({**block, "last": None}), []
    grid += _brief(texts) + _older(more + older, today, len(more), old_texts)
    recent = recent or texts
    quiet = "" if recent else " quiet"
    return (f'<section id="{anchor}" data-k="{e(block["name"])}" class="sec {"serif" if t.get("font") == "serif" else "sans"}{quiet}" style="{style}">'
            f'<div class="{band_cls}"><span class="title">{e(block["name"])}</span>{sub}</div>'
            f"{facts}{grid}</section>")


def _why_verb(x):
    if x.get("kind") == "follow":
        return "关注"
    return "在纠结" if x.get("kind") == "hesitate" or x.get("hesitating") else "想要"


def _why(x):
    """推荐理由：wish 是命中了愿望清单里那件东西的喜好；board 是关注的版面里没上版面的其他消息；
    follow 是同类新发现。和赞过的某条有关时补一句「你赞过「那条」」。"""
    if x.get("kind") == "board":
        why = f'你关注的「{e(x["because"])}」还有这条'
    else:
        why = f'{"换换口味 · " if x.get("explore") else ""}因为你{_why_verb(x)}「{e(x["because"])}」'
    if x.get("liked"):
        t = x["liked"] if len(x["liked"]) <= 24 else x["liked"][:23] + "…"
        why += f' · 你赞过「{e(t)}」'
    return why


WORK_KEY = "作品:"  # 投票学到的口味里，按作品记的那一类（和 digest.WORK_KEY 一致）


def _picks(picks, works, feedback=None):
    """「我会喜欢？」角落：按愿望清单的喜好，从收集到的消息里挑的推荐，每条写明推荐理由。
    feedback 配好了 Supabase（url、key）时，每条下面有 👍 / 👎，投票直接写进数据库，下次出刊时学习。"""
    if not picks:
        return ""
    covers = {w["name"]: [w["_thumb"]] if w.get("_thumb") else [] for w in works}

    def cards_of(group, big_first):
        return "".join(card(x, big_first and i == 0) for i, x in enumerate(group))

    def card(x, big):
        follow = x.get("kind") in ("follow", "hesitate")  # 同类新发现不是那个作品本身，没图时不能用它的封面
        story = {"image": x.get("image"), "_fbs": [] if follow else covers.get(x["work"], []),
                 "_work": (x.get("hits") or [x["work"]])[0] if follow else x["work"]}
        tags = "".join(f"<i>{e(h)}</i>" for h in x.get("hits", []))
        date = e(x["date"][5:].replace("-", ".")) if x.get("date") else ""
        taste = " · ".join(f"{e(k.removeprefix(WORK_KEY))} {v:+d}" for k, v in (x.get("taste") or [])[:3])
        taste = f'<span class="taste">按你的投票：{taste}</span>' if taste else ""
        vote = ""
        if feedback:  # 投票要写进的数据：网页把它原样发给数据库
            data = {k: x.get(k) for k in ("url", "kind", "title", "work", "because", "hits", "words")}
            vote = (f'<div class="vote" data-v="{e(json.dumps(data, ensure_ascii=False))}">'
                    f'<button type="button" data-vote="1" aria-pressed="false" title="多推荐这类">👍<span> 喜欢</span></button>'
                    f'<button type="button" data-vote="-1" aria-pressed="false" title="少推荐这类">👎<span> 不感兴趣</span></button>'
                    + f'<small></small></div>')
        return (
            f'<div class="pk{" big" if big else ""}" data-u="{e(x["url"])}" data-s="{x.get("score") or 4}" '
            f'data-w="{e(x["work"])}" data-key="{e("|".join(x.get("words") or []))}"{" data-f=1" if follow else ""}{" data-new=1" if x.get("explore") else ""}>'
            f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{_pic(story)}'
            f'<span class="pkt"><span class="src">{e(x["source"])}{" · " + date if date else ""}</span>'
            f'<b>{e(x["title"])}</b>'
            f'<span class="why">{_why(x)}</span>'
            f'<span class="tags">{tags}</span>{taste}</span></a>{vote}</div>')

    def batch_of(group):
        wish = [x for x in group if x.get("kind") not in ("follow", "hesitate")]
        follow = [x for x in group if x.get("kind") in ("follow", "hesitate")]
        body = f'<div class="pkgrid">{cards_of(wish, True)}</div>' if wish else ""
        if follow:
            body += (f'<div class="pksub">同类新发现<span>你关注的作品和纠结的东西之外，同类型的新消息</span></div>'
                     f'<div class="pkgrid row" style="--n:{len(follow)}">{cards_of(follow, False)}</div>')
        return body

    # 网页里放下整个候选池：第一批（没有脚本时也能看）+ 其余放进隐藏的池子；
    # 脚本每次打开随机抽一批（分数高的、没看过的更容易抽到），「换一批」再抽
    first = [x for x in picks if not x.get("batch")]
    rest = [x for x in picks if x.get("batch")]
    body = f'<div class="pkbatch">{batch_of(first)}</div>'
    if rest:
        body += f'<div class="pkpool" hidden>{cards_of(rest, False)}</div>'
    shuffle = (f'<div class="pknav"><button type="button" class="shuffle back" aria-label="回到上一批推荐" disabled>上一批</button>'
               f'<button type="button" class="shuffle next" aria-label="换一批推荐">换一批<small>共 {len(picks)} 条</small></button></div>'
               if rest else "")
    return (f'<section class="picks" id="picks" data-k="picks"><div class="pkhead"><h2>我会喜欢<em>？</em></h2>'
            f'<span>根据愿望清单、你关注的版面和你赞过的消息挑的{"，点 👍 / 👎 教它你的口味" if feedback else ""}'
            f' · <a href="wishlist.html">♥ 愿望清单</a></span>{shuffle}</div>'
            f'{body}</section>' + (f"<script>{SHUFFLE_JS}</script>" if shuffle else ""))


SHUFFLE_JS = """
(() => {
  const sec = document.getElementById('picks');
  const next = sec.querySelector('.shuffle.next'), back = sec.querySelector('.shuffle.back');
  const batch = sec.querySelector('.pkbatch'), pool = sec.querySelector('.pkpool');
  const wishGrid = batch.querySelector('.pkgrid:not(.row)'), followGrid = batch.querySelector('.pkgrid.row');
  if (!wishGrid && !followGrid) return;
  const cards = [...sec.querySelectorAll('.pk')];
  const kind = new Map(cards.map(el => [el, el.dataset.f ? 'f' : 'w']));   // 同类新发现 / 为你挑的
  // 本机记住每条推荐：t 最后一次出现的时间，o 点开看过。像 B 站首页：每次打开、每次换一批都先放没出现过的，
  // 出现过的按「多久以前出现的」轮回来，点开看过的放到最后
  const KEY = 'wishlist-seen-v2';
  let seen = {};
  try { seen = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (_) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(seen)); } catch (_) {} };
  const tier = el => { const s = seen[el.dataset.u]; return !s ? 0 : s.o ? 2 : 1; };
  // 同一档里：没出现过的按分数加权随机（Efraimidis–Spirakis，每次打开都不一样）；出现过的先放最久以前的
  const order = list => list.map(el => {
    const s = seen[el.dataset.u], w = Number(el.dataset.s || 4);
    return [tier(el), s ? s.t || 0 : -Math.pow(Math.random(), 1 / w), el];
  }).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(x => x[2]);
  // 同一批里同一个关注项只 1 张、同一个关键词（如 Snoopy）只 1 张（为你挑的和同类新发现之间关键词也不重复）；
  // 刚才那批的不再抽。没看过的凑不满时先放宽关键词、再放宽关注项，还不够才用看过的
  const draw = (list, n, keys, prev) => {
    const out = [], works = new Set(), ranked = order(list.filter(el => !prev.has(el)));
    const fresh = el => !seen[el.dataset.u], any = () => true;
    // [能用哪些, 关注项不重复, 关键词不重复]
    const passes = [[fresh, true, true], [fresh, true, false], [fresh, false, false], [any, true, true], [any, false, false]];
    for (const [ok, oneWork, oneKey] of passes) {
      for (const el of ranked) {
        if (out.length >= n) return out;
        const ks = (el.dataset.key || '').split('|').filter(Boolean);
        if (out.includes(el) || !ok(el) || (oneWork && works.has(el.dataset.w))
            || (oneKey && ks.some(k => keys.has(k)))) continue;
        out.push(el); works.add(el.dataset.w); ks.forEach(k => keys.add(k));
      }
    }
    return out;
  };
  const history = [];
  let pos = -1;
  const show = ([w, f]) => {
    cards.forEach(el => { el.classList.remove('big'); pool.appendChild(el); });
    if (wishGrid) w.forEach((el, i) => { el.classList.toggle('big', i === 0); wishGrid.appendChild(el); });
    if (followGrid) { f.forEach(el => followGrid.appendChild(el)); followGrid.style.setProperty('--n', f.length); }
    back.disabled = pos <= 0;
    const fresh = cards.filter(el => !seen[el.dataset.u]).length;
    next.querySelector('small').textContent = fresh ? `还有 ${fresh} 条没看过` : '都看过了，从最早的轮回来';
  };
  const fresh = () => {
    const prev = new Set(pos >= 0 ? history[pos].flat() : []);
    const keys = new Set();
    const w = draw(cards.filter(el => kind.get(el) === 'w'), 5, keys, prev);
    const f = draw(cards.filter(el => kind.get(el) === 'f'), 4, keys, prev);
    const now = Date.now();
    [...w, ...f].forEach((el, i) => { seen[el.dataset.u] = { ...(seen[el.dataset.u] || {}), t: now + i }; });
    save();
    history.splice(pos + 1);
    history.push([w, f]);
    pos = history.length - 1;
    show(history[pos]);
  };
  fresh();
  const top = () => sec.scrollIntoView({ block: 'start', behavior: 'smooth' });
  // 换一批：退回去看过上一批后，先回到原来那批（和浏览器的前进一样），到头了再抽新的
  next.addEventListener('click', () => { if (pos < history.length - 1) show(history[++pos]); else fresh(); top(); });
  back.addEventListener('click', () => { if (pos > 0) { show(history[--pos]); top(); } });
  sec.addEventListener('click', ev => {
    const a = ev.target.closest('.pk a'), el = a && a.closest('.pk');
    if (el) { seen[el.dataset.u] = { ...(seen[el.dataset.u] || {}), o: 1 }; save(); }
  });
})();
"""


# 投票：直接写进 Supabase 的 feedback 表（只能新增，见 db/feedback.sql）。
# 每次点击新增一行，同一条消息以最后一票为准；再点一次已选中的按钮 = 撤销（写一行 vote 0）。
# 「我会喜欢？」的卡片下面有带文字的按钮（数据在 data-v 里）；其余所有消息卡片由脚本在右上角加上小按钮，
# 作品名取所在版面的 data-k，标题取卡片里的标题。同一条消息在几处出现时，按钮状态一起变。
# 本机记住投过什么，刷新后按钮状态还在；学习在下次出刊时进行（每 2 小时）
VOTE_JS = """
(() => {
  const cfg = %s, KEY = 'wishlist-votes';
  let mine = {};
  try { mine = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (_) {}
  const headers = { apikey: cfg.key, 'Content-Type': 'application/json', Prefer: 'return=minimal' };
  if (cfg.key.startsWith('eyJ')) headers.Authorization = 'Bearer ' + cfg.key;
  const boxes = [];   // [控件, 数据, 投踩后变淡的元素, 提示文字]
  const paint = url => boxes.forEach(([box, data, dim, tip]) => {
    if (data.url !== url) return;
    const v = mine[url] || 0;
    box.querySelectorAll('button[data-vote]').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.vote) === v)));
    box.classList.toggle('on', v !== 0);
    if (dim) dim.classList.toggle(dim.classList.contains('pk') ? 'down' : 'downv', v === -1);
    if (tip) tip.textContent = v === 1 ? '会多推荐这类' : v === -1 ? '以后少推荐这类' : '';
  });
  const wire = (box, data, dim, tip) => {
    boxes.push([box, data, dim, tip]);
    box.querySelectorAll('button[data-vote]').forEach(btn => btn.addEventListener('click', async ev => {
      ev.preventDefault(); ev.stopPropagation();   // 小按钮在卡片链接里面：别打开链接
      const v = (mine[data.url] || 0) === Number(btn.dataset.vote) ? 0 : Number(btn.dataset.vote);
      box.querySelectorAll('button').forEach(b => b.disabled = true);
      try {
        const r = await fetch(cfg.url.replace(/\\/$/, '') + '/rest/v1/feedback',
          { method: 'POST', headers, body: JSON.stringify({ ...data, vote: v }) });
        if (!r.ok) throw new Error(r.status + ' ' + (await r.text()).slice(0, 120));
        mine[data.url] = v;
        try { localStorage.setItem(KEY, JSON.stringify(mine)); } catch (_) {}
        paint(data.url);
      } catch (err) {
        if (tip) tip.textContent = '没存上，稍后再试';
        btn.title = '没存上，稍后再试';
        console.error('投票失败', err);
      } finally {
        box.querySelectorAll('button').forEach(b => b.disabled = false);
      }
    }));
  };
  document.querySelectorAll('.picks .vote').forEach(box =>
    wire(box, JSON.parse(box.dataset.v), box.closest('.pk'), box.querySelector('small')));
  const small = () => {
    const s = document.createElement('span');
    s.className = 'vt';
    s.innerHTML = '<button type="button" data-vote="1" aria-pressed="false" title="喜欢，多推荐这类">👍</button>'
      + '<button type="button" data-vote="-1" aria-pressed="false" title="不感兴趣，少推荐这类">👎</button>';
    return s;
  };
  const story = (link, holder, dim) => {
    if (!/^https?:/.test(link.getAttribute('href') || '')) return;
    const w = holder.closest('[data-k]');
    const t = link.querySelector('h1,h2,h3,h4') || link;   // 标题；别用 b（日期旁的 NEW 也是 b）
    const box = small();
    holder.appendChild(box);
    const title = t.textContent.trim().slice(0, 500), work = (w && w.dataset.k || '').slice(0, 200);
    wire(box, { url: link.href, kind: 'story', title, work, hits: [], words: [] }, dim, null);
  };
  document.querySelectorAll('.sec a.card, a.top').forEach(a => story(a, a, a));
  document.querySelectorAll('.sec .brief li').forEach(li => { const a = li.querySelector('a'); if (a) story(a, li, li); });
  new Set(boxes.map(b => b[1].url)).forEach(paint);
})();
"""


def _wish_link(wishes, cls):
    """主页面上去愿望清单子页面的入口（报头右上角、左侧目录底部）。"""
    if not wishes:
        return ""
    want = sum(1 for x in wishes if (x.get("status") or "想要") == "想要")
    return (f'<a class="{cls}" href="wishlist.html"><b>♥</b><span>愿望清单</span>'
            f'<small>{want} 件想要</small></a>')


def render_settings(items, db, updated):
    """设置页（docs/settings.html）：改每个关注项的篇幅 S / M / L，新增 / 修改关注项。都不用口令。
    items：[{name, section, subtitle, size, fields}]（items.yaml 的顺序；fields 是网页上能改的那些字段的现值）；
    db：{url, key} Supabase 的地址和公开的 publishable key。篇幅用 get_sizes() 读、set_size() 改；
    新增 / 修改关注项是一问一答的向导（docs/additem.js），提交到 submit_item()（db/item_requests.sql），
    下一次更新时写进 items.yaml。"""
    groups = {}
    for it in items:
        groups.setdefault(it.get("section") or "其他", []).append(it)
    order = [n for n in SECTIONS if n in groups] + [n for n in groups if n not in SECTIONS]
    rows = []
    for name in order:
        rows.append(f'<h2 style="--sc:{_sec_color(name)}">{e(name)}<small>{SECTION_EN.get(name, "")}</small></h2>')
        for it in groups[name]:
            sub = f'<small>{e(it["subtitle"])}</small>' if it.get("subtitle") else ""
            btns = "".join(f'<button type="button" data-v="{v}" aria-pressed="{str(v == (it.get("size") or "M")).lower()}">'
                           f'{v}</button>' for v in ("S", "M", "L"))
            rows.append(f'<div class="row" data-item="{e(it["name"])}"><div class="nm"><b>{e(it["name"])}</b>{sub}</div>'
                        f'<div class="seg" role="group" aria-label="{e(it["name"])} 的篇幅">{btns}</div>'
                        f'<button type="button" class="edit" aria-label="修改 {e(it["name"])}">改</button>'
                        f'<span class="st" aria-live="polite"></span></div>')
    data = {"url": (db or {}).get("url") or "", "key": (db or {}).get("key") or "",
            "langs": (db or {}).get("langs") or ["zh-TW", "en-US"], "sections": list(dict.fromkeys(list(SECTIONS) + order)),
            "items": [{"name": it["name"], **(it.get("fields") or {})} for it in items]}
    cfg = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>设置</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}
.page{{display:flex;flex-direction:column;gap:18px;max-width:760px;padding-bottom:48px}}
.back{{display:inline-flex;align-items:center;gap:8px;font:700 12px 'JetBrains Mono',monospace;letter-spacing:.15em}}
.back:hover{{color:#B8336A}}
.intro{{font-size:14px;line-height:1.7;opacity:.8;margin:0}}
.cfg{{align-self:stretch;width:100%;display:block}}
.cfg h2{{display:flex;align-items:baseline;gap:10px;margin:22px 0 4px;padding-bottom:6px;border-bottom:3px solid var(--sc);
 font:900 20px/1 'Noto Sans SC',sans-serif;letter-spacing:.08em;color:var(--sc)}}
.cfg h2 small{{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.7}}
.row{{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,#1A1C22 15%,transparent)}}
.nm{{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}}
.nm b{{font:900 16px 'Noto Sans SC',sans-serif}}
.nm small{{font-size:12px;opacity:.6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.seg{{display:flex;border:2px solid #1A1C22}}
.seg button{{width:44px;height:36px;border:0;border-left:2px solid #1A1C22;background:transparent;color:#1A1C22;
 font:900 15px 'JetBrains Mono',monospace;cursor:pointer}}
.seg button:first-child{{border-left:0}}
.seg button[aria-pressed="true"]{{background:#1A1C22;color:#F4EDE4}}
.row .edit{{height:36px;padding:0 12px;border:2px solid #1A1C22;background:transparent;color:#1A1C22;
 font:900 14px 'Noto Sans SC',sans-serif;cursor:pointer}}
.row .edit:hover{{background:#1A1C22;color:#F4EDE4}}
.seg button:focus-visible,.row .edit:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.seg button:disabled{{cursor:wait;opacity:.6}}
.st{{width:64px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.05em;text-align:right}}
.st.ok{{color:#1F9D6B}}.st.err{{color:#C0392B}}
.legend{{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px;margin:0}}
.legend dt{{font:900 13px 'JetBrains Mono',monospace}}.legend dd{{margin:0;opacity:.75}}
.wiz{{display:flex;flex-direction:column;gap:14px;margin-top:18px;padding:18px 18px 20px;border:2px solid #1A1C22;background:#F7F5F0;scroll-margin-top:16px}}
.wiz>h2{{margin:0;font:900 20px/1 'Noto Sans SC',sans-serif;letter-spacing:.08em}}
.wiz .hint{{margin:0;font-size:13px;line-height:1.7;opacity:.75}}
.trail{{margin:0;padding:0;list-style:none;display:flex;flex-wrap:wrap;align-items:stretch;gap:8px}}
.trail:empty{{display:none}}
.trail li{{display:flex;align-items:center;gap:8px}}
.trail li:not(:last-child)::after{{content:"→";font:700 14px 'JetBrains Mono',monospace;opacity:.4}}
.trail button{{display:flex;flex-direction:column;gap:3px;min-width:96px;max-width:230px;padding:8px 11px;border:2px solid #1A1C22;
 background:#FFF;color:#1A1C22;text-align:left;cursor:pointer}}
.trail button.auto{{border-style:dashed}}
.trail button:hover{{background:#1A1C22;color:#F4EDE4}}
.trail button:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.trail span{{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;opacity:.6}}
.trail b{{font:900 14px/1.4 'Noto Sans SC',sans-serif}}
.opt.auto{{border-style:dashed}}
.q{{display:flex;flex-direction:column;gap:12px;padding:16px;border:1px solid #1A1C22;background:#FFF}}
.q .no{{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.2em;opacity:.6}}
.q h3{{margin:0;font:900 19px/1.4 'Noto Sans SC',sans-serif}}
.q p{{margin:0;font-size:13px;line-height:1.7;opacity:.75}}
.opts{{display:flex;flex-direction:column;gap:8px}}
.opt{{display:flex;flex-direction:column;gap:2px;text-align:left;padding:10px 12px;border:2px solid #1A1C22;background:#FFF;color:#1A1C22;
 font:900 15px 'Noto Sans SC',sans-serif;cursor:pointer}}
.opt small{{font:500 12px/1.5 'Noto Serif SC',serif;opacity:.65}}
.opt[aria-pressed="true"]{{background:#1A1C22;color:#F4EDE4}}
.opt:focus-visible,.wiz button:focus-visible,.wiz input:focus-visible,.wiz select:focus-visible,.wiz textarea:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.wiz input[type=text],.wiz select,.wiz textarea{{width:100%;padding:8px 10px;border:1px solid #1A1C22;background:#FFF;
 font:500 15px 'Noto Serif SC',serif;color:#1A1C22}}
.wiz textarea{{min-height:70px;resize:vertical;font-size:14px}}
.wiz textarea.code{{font:500 12px/1.6 'JetBrains Mono',monospace}}
.wnav{{display:flex;flex-wrap:wrap;align-items:center;gap:10px}}
.wnav button{{flex-shrink:0;white-space:nowrap;padding:9px 18px;border:2px solid #1A1C22;background:transparent;color:#1A1C22;
 font:900 14px 'Noto Sans SC',sans-serif;letter-spacing:.08em;cursor:pointer}}
.wnav button.main{{background:#1A1C22;color:#F4EDE4}}
.wnav button:disabled{{cursor:not-allowed;opacity:.45}}
.msg{{font:700 13px/1.6 'Noto Sans SC',sans-serif}}.msg.ok{{color:#1F9D6B}}.msg.err{{color:#C0392B}}
.rv{{display:flex;flex-direction:column;gap:12px}}
.rv label,.rv .f{{display:flex;flex-direction:column;gap:5px;font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.04em}}
.rv label small,.rv .f small{{font:500 12px/1.5 'Noto Serif SC',serif;letter-spacing:0;opacity:.6}}
.rv .two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.rv .checks{{display:flex;flex-wrap:wrap;gap:6px 14px}}
.rv .checks label{{flex-direction:row;align-items:center;gap:5px;font:500 14px 'Noto Serif SC',serif}}
.rv details{{border-top:1px dashed color-mix(in srgb,#1A1C22 40%,transparent);padding-top:10px}}
.rv summary{{cursor:pointer;font:900 13px 'Noto Sans SC',sans-serif}}
.rv details[open]>summary{{margin-bottom:10px}}
.rv details .rv{{gap:12px}}
.queue{{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px;font-size:13px}}
.queue:empty{{display:none}}
.queue li{{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 6px;padding:8px 0;border-top:1px solid color-mix(in srgb,#1A1C22 15%,transparent)}}
.queue li.qh{{border-top:0;padding:0;font:900 13px 'Noto Sans SC',sans-serif;letter-spacing:.05em}}
.queue li b{{font-family:'Noto Sans SC',sans-serif}}.queue li span{{opacity:.65}}
.queue li strong{{flex-basis:100%;font:700 13px/1.6 'Noto Sans SC',sans-serif}}
.queue .st-ok{{color:#1F9D6B}}.queue .st-err{{color:#C0392B}}.queue .st-wait{{color:#B8336A}}
@media (max-width:520px){{.st{{display:none}}.seg button{{width:40px}}.rv .two{{grid-template-columns:1fr}}.row{{gap:8px}}
 .trail{{gap:6px}}.trail li:not(:last-child)::after{{display:none}}.trail button{{min-width:0;max-width:100%;padding:6px 9px}}.trail b{{font-size:13px}}}}
</style>
</head>
<body>
<div class="page">
<a class="back" href="index.html">← 回到简报</a>
<header><h1 style="margin:0;font:900 40px/1.1 'Noto Sans SC',sans-serif;letter-spacing:.04em">设置</h1></header>
<p class="intro">点 S / M / L 改篇幅，点「改」修改这一项关注什么；想关注新的东西，在最下面「新增关注项」里只写个名字，一步一步回答几个问题就行。改完立刻存进数据库，<span id="wl-eta">下次更新时（最多 2 小时）网页按新的设置更新</span>。</p>
<dl class="legend"><dt>S</dt><dd>少：每期最多 3 条，大约一行</dd><dt>M</dt><dd>中等：每期最多 5 条</dd><dt>L</dt><dd>多：每期最多 8 条，满满一整屏</dd></dl>
<div class="cfg">{''.join(rows)}</div>
<section class="wiz" id="wiz" aria-live="polite"><h2>＋ 新增关注项</h2><p class="hint">正在加载…</p></section>
<p class="intro" style="font-size:12px">更新于 {e(updated)}</p>
</div>
<script type="application/json" id="wl-cfg">{cfg}</script>
<script>
(() => {{
  const CFG = JSON.parse(document.getElementById("wl-cfg").textContent);
  const rpc = (fn, body) => fetch(`${{CFG.url}}/rest/v1/rpc/${{fn}}`, {{
    method: "POST", headers: {{apikey: CFG.key, "Content-Type": "application/json"}}, body: JSON.stringify(body || {{}}),
  }});
  const show = (row, v) => row.querySelectorAll(".seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
  const say = (row, text, cls) => {{ const st = row.querySelector(".st"); st.textContent = text; st.className = "st " + (cls || ""); }};
  if (!CFG.url || !CFG.key) {{
    document.querySelectorAll(".row").forEach(r => {{ r.querySelectorAll(".seg button").forEach(b => b.disabled = true); say(r, "未连数据库", "err"); }});
    return;
  }}
  rpc("get_sizes").then(r => r.ok ? r.json() : []).then(list => {{
    const now = Object.fromEntries((list || []).map(x => [x.item, x.size]));
    document.querySelectorAll(".row").forEach(r => {{ if (now[r.dataset.item]) show(r, now[r.dataset.item]); }});
  }}).catch(() => {{}});
  document.querySelector(".cfg").addEventListener("click", async ev => {{
    const edit = ev.target.closest(".edit");
    if (edit) {{ window.wlEditItem && window.wlEditItem(edit.closest(".row").dataset.item); return; }}
    const btn = ev.target.closest(".seg button");
    if (!btn || btn.getAttribute("aria-pressed") === "true") return;
    const row = btn.closest(".row");
    const before = row.querySelector('.seg button[aria-pressed="true"]')?.dataset.v;
    const btns = row.querySelectorAll(".seg button");
    show(row, btn.dataset.v); btns.forEach(b => b.disabled = true); say(row, "保存中…");
    try {{
      const r = await rpc("set_size", {{p_item: row.dataset.item, p_size: btn.dataset.v, p_pass: ""}});
      if (r.ok) say(row, "已保存 ✓", "ok");
      else {{ if (before) show(row, before); say(row, "没存上", "err"); }}
    }} catch (_) {{ if (before) show(row, before); say(row, "连不上", "err"); }}
    btns.forEach(b => b.disabled = false);
  }});
}})();
</script>
<script src="additem.js"></script>
</body>
</html>
"""


WISH_STATUSES = ("想要", "纠结", "已入手", "没买到", "已过期")


def _total(wishes, status):
    totals = {}
    for x in wishes:
        if (x.get("status") or "想要") == status and isinstance(x.get("price"), (int, float)):
            cur = x.get("currency", "")
            totals[cur] = totals.get(cur, 0) + x["price"]
    return " + ".join(f"{c} {v:,.0f}" for c, v in totals.items()) or "—"


def render_wishlist(wishes, works, updated, finds=(), db=None):
    """愿望清单子页面（docs/wishlist.html）：收藏柜式大图网格，可按状态筛选，顶部是件数和想要的总价。
    「纠结」的东西单独排一栏「纠结名单」，卡片上列出帮你查的同类好产品（alternatives）和每天搜到的新发现（finds）。
    db（Supabase 的 url、公开 key）配好时，顶部有「📷 拍照加愿望」：上传照片进收件箱，Claude 定时任务认出物品加进清单。"""
    total = _total(wishes, "想要")
    counts = {k: sum(1 for x in wishes if (x.get("status") or "想要") == k) for k in WISH_STATUSES}
    chips = "".join(f'<button type="button" class="chip" data-f="{k}" aria-pressed="{str(k == "全部").lower()}">'
                    f'{k}<small>{len(wishes) if k == "全部" else counts[k]}</small></button>'
                    for k in ("全部",) + WISH_STATUSES if k == "全部" or counts[k])
    live = [x for x in wishes if x.get("status") not in ("已过期", "纠结")]
    torn = [x for x in wishes if x.get("status") == "纠结"]
    gone = [x for x in wishes if x.get("status") == "已过期"]
    section = _wish_section(live, works)
    if torn:
        section += (f'<div class="gonehead torn"><h2>纠结名单</h2><span>还在犹豫买不买 · {len(torn)} 件 · 合计 {e(_total(wishes, "纠结"))}'
                    f' · 下面列出类似的好产品，每天也会帮你搜新的</span></div>'
                    + _wish_section(torn, works, finds).replace('class="sec wish"', 'class="sec wish torn"').replace('id="wishlist" ', ''))
    if gone:
        section += (f'<div class="gonehead"><h2>过期的愿望</h2><span>去不了、买不到了，但还想要 · {len(gone)} 件</span></div>'
                    + _wish_section(gone, works).replace('class="sec wish"', 'class="sec wish expired"').replace('id="wishlist" ', ''))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>愿望清单</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}
.page{{display:flex;flex-direction:column;align-items:stretch;max-width:1200px;padding-bottom:40px}}
.sec.wish{{background:none}}
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
.gonehead{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px;padding-top:12px;border-top:3px double #1A1C22}}
.gonehead h2{{margin:0;font:900 26px/1 'Noto Sans SC',sans-serif;letter-spacing:.06em;color:#6B6457}}
.gonehead span{{font-size:13px;opacity:.7}}
.wish.expired{{--bg:#E9E5DE;--acc:#6B6457}}
.gonehead.torn h2{{color:#B5650D}}
.wish.torn{{--bg:#F6EEDC;--acc:#B5650D}}
.wcard .alts{{display:flex;flex-direction:column;gap:8px;padding:12px 14px;border:1px dashed color-mix(in srgb,var(--acc) 55%,transparent)}}
.wcard .alts>span{{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.2em;color:var(--acc)}}
.wcard .alts ul{{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px}}
.wcard .alts li{{font-size:14px;line-height:1.55}}
.wcard .alts li b{{font-weight:900}}
.wcard .alts li em{{font-style:normal;font:700 12px 'JetBrains Mono',monospace;margin-left:6px;color:var(--acc)}}
.wcard .alts li p{{margin:2px 0 0;font-size:13px;opacity:.8}}
.wcard .alts li a:hover b{{color:var(--acc)}}
.wcard .alts li small{{font:700 10px 'JetBrains Mono',monospace;opacity:.6;letter-spacing:.08em}}
.wish.expired .wimg img{{filter:grayscale(.65) contrast(.95);opacity:.85}}
.wish.expired .wcard:hover .wimg img{{filter:none;opacity:1}}
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
{_snap_panel(db)}
{section}
</div>
<script>
document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {{
  document.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', String(x === c)));
  const f = c.dataset.f;
  document.querySelectorAll('.wcard').forEach(w => {{ w.hidden = f !== '全部' && w.dataset.status !== f; }});
  document.querySelectorAll('.wish').forEach(sec => {{
    const empty = [...sec.querySelectorAll('.wcard')].every(w => w.hidden);
    sec.hidden = empty;
    if (sec.previousElementSibling && sec.previousElementSibling.classList.contains('gonehead')) sec.previousElementSibling.hidden = empty;
  }});
}}));
</script>
</body>
</html>
"""


SNAP_CSS = """
.snap{background:#FBF8F1;border:3px solid #1A1C22;box-shadow:6px 6px 0 #B8336A;padding:18px 22px;display:flex;flex-direction:column;gap:14px}
.snap h2{margin:0;font:900 22px/1.2 'Noto Sans SC',sans-serif;letter-spacing:.04em}
.snap h2 small{font:500 13px 'Noto Serif SC',serif;letter-spacing:0;opacity:.7;margin-left:10px}
.snap form{display:grid;grid-template-columns:160px minmax(0,1fr);gap:14px 18px;align-items:start}
.snap .drop{grid-row:span 4;aspect-ratio:1;border:2px dashed #1A1C22;display:grid;place-items:center;text-align:center;cursor:pointer;
 font:700 13px 'Noto Sans SC',sans-serif;background:#FFF;overflow:hidden;position:relative}
.snap .drop img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#FFF}
.snap .drop input{position:absolute;inset:0;opacity:0;cursor:pointer}
.snap .seg{display:flex;gap:8px}
.snap .seg button,.snap .send{padding:7px 16px;border:2px solid #1A1C22;background:transparent;color:#1A1C22;font:900 13px 'Noto Sans SC',sans-serif;
 letter-spacing:.12em;cursor:pointer;border-radius:0}
.snap .seg button[aria-pressed=true]{background:#1A1C22;color:#F4EDE4}
.snap .seg button[data-v="纠结"][aria-pressed=true]{background:#B5650D;border-color:#B5650D}
.snap input[type=text],.snap input[type=password]{width:100%;box-sizing:border-box;padding:8px 10px;border:2px solid #1A1C22;
 font:500 14px 'Noto Sans SC',sans-serif;background:#FFF;border-radius:0}
.snap .row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.snap .send{background:#B8336A;border-color:#B8336A;color:#FFF}
.snap .send:disabled{opacity:.5;cursor:wait}
.snap .st{font-size:13px}.snap .st.err{color:#C0392B}.snap .st.ok{color:#1F9D6B}
.snapq{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:10px}
.snapq li{display:flex;gap:8px;align-items:center;padding:6px 10px 6px 6px;border:1px solid color-mix(in srgb,#1A1C22 25%,transparent);
 font-size:12px;background:#FFF;max-width:100%}
.snapq img{width:44px;height:44px;object-fit:cover;flex:none}
.snapq b{display:block;font-size:12px}
.snapq .state{font:700 10px 'JetBrains Mono',monospace;letter-spacing:.1em;opacity:.7}
@media (max-width:640px){.snap form{grid-template-columns:1fr}.snap .drop{grid-row:auto;aspect-ratio:4/3}}
"""

# 拍照加愿望：网页先把照片缩到长边 1600（再做一张 240 的缩略图），交给数据库的 add_photo()（db/photo_inbox.sql）；
# 不要口令（和设置页一样），待处理的最多 20 张
SNAP_JS = """
(() => {
  const CFG = %s, box = document.getElementById('snap');
  const $ = s => box.querySelector(s);
  const file = $('#snap-file'), drop = $('.drop'), note = $('#snap-note'), send = $('.send'), st = $('.st');
  let status = '想要', img = null;
  box.querySelectorAll('.seg button').forEach(b => b.addEventListener('click', () => {
    status = b.dataset.v;
    box.querySelectorAll('.seg button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  }));
  const say = (t, cls) => { st.textContent = t; st.className = 'st ' + (cls || ''); };
  const rpc = (fn, body) => fetch(CFG.url.replace(/\\/$/, '') + '/rest/v1/rpc/' + fn,
    { method: 'POST', headers: { apikey: CFG.key, 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const shrink = (im, side, q) => {
    const k = Math.min(1, side / Math.max(im.naturalWidth, im.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k);
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(im, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', q);
  };
  file.addEventListener('change', () => {
    const f = file.files[0]; if (!f) return;
    const url = URL.createObjectURL(f), im = new Image();
    im.onload = () => {
      img = im;
      let p = drop.querySelector('img'); if (!p) { p = document.createElement('img'); drop.appendChild(p); }
      p.src = url; drop.querySelector('span').hidden = true; say('');
    };
    im.onerror = () => say('这张图打不开，换一张试试', 'err');
    im.src = url;
  });
  const STATE = { new: '排队中', exported: 'Claude 处理中', done: '已加入' };
  const queue = async () => {
    try {
      const r = await rpc('get_photo_inbox'); if (!r.ok) return;
      const list = await r.json();
      const ul = box.querySelector('.snapq'); ul.innerHTML = '';
      list.forEach(x => {
        const li = document.createElement('li');
        const t = document.createElement('img'); if (x.thumb) t.src = x.thumb; t.alt = '';
        const d = document.createElement('div');
        const b = document.createElement('b'); b.textContent = x.state === 'done' && x.wish_name ? x.wish_name : (x.note || '照片 #' + x.id);
        const s = document.createElement('span'); s.className = 'state';
        s.textContent = (STATE[x.state] || x.state) + ' · ' + x.status + ' · ' + new Date(x.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        d.append(b, s); li.append(t, d); ul.appendChild(li);
      });
    } catch (_) {}
  };
  send.addEventListener('click', async ev => {
    ev.preventDefault();
    if (!img) { say('先选一张照片', 'err'); return; }
    let big = shrink(img, 1600, .85);
    if (big.length > 2900000) big = shrink(img, 1200, .75);
    send.disabled = true; say('上传中…');
    try {
      const r = await rpc('add_photo', { p_pass: '', p_image: big, p_thumb: shrink(img, 240, .7), p_status: status, p_note: note.value.trim() });
      if (r.ok) {
        say('收到了 ✓ Claude 定时处理后会出现在下面的清单里（一般几个小时内）', 'ok');
        img = null; file.value = ''; note.value = ''; drop.querySelector('img')?.remove(); drop.querySelector('span').hidden = false;
        queue();
      } else {
        const err = await r.json().catch(() => ({}));
        say('没传上：' + (err.message || r.status), 'err');
      }
    } catch (_) { say('连不上，稍后再试', 'err'); }
    send.disabled = false;
  });
  queue();
})();
"""


def _snap_panel(db):
    """愿望清单页顶部的「📷 拍照加愿望」。没配数据库时不显示。"""
    if not (db and db.get("url") and db.get("key")):
        return ""
    return (f'<style>{SNAP_CSS}</style><section class="snap" id="snap"><h2>📷 拍照加愿望'
            f'<small>上传一张照片，Claude 会认出是什么、整理好加进清单（定时处理，一般几个小时内）</small></h2>'
            f'<form><label class="drop"><span>点这里选照片<br>或拍一张</span><input type="file" id="snap-file" accept="image/*"></label>'
            f'<div class="seg" role="group" aria-label="加到哪一栏"><button type="button" data-v="想要" aria-pressed="true">想要</button>'
            f'<button type="button" data-v="纠结" aria-pressed="false">纠结</button></div>'
            f'<input type="text" id="snap-note" maxlength="500" placeholder="备注（可不填）：在哪看到的、想要哪个颜色、大概多少钱…">'
            f'<div class="row"><button type="button" class="send">提交</button><span class="st" role="status"></span></div></form>'
            f'<ul class="snapq" aria-label="最近上传的照片"></ul></section>'
            f'<script>{SNAP_JS % json.dumps({"url": db["url"], "key": db["key"]})}</script>')


FINDS_PER_WISH = 3  # 纠结的东西，卡片上最多列几条每天搜到的新发现


def _alts(x, finds):
    """纠结卡片上的「类似的好产品」：先列帮你查好的 alternatives，再列每天搜到的最新几条。"""
    rows = []
    for a in x.get("alternatives") or []:
        name = f'<b>{e(a["name"])}</b>' + (f'<em>{e(str(a["price"]))}</em>' if a.get("price") else "")
        if a.get("url"):
            name = f'<a href="{e(a["url"])}" target="_blank" rel="noopener">{name}</a>'
        rows.append(f'<li>{name}' + (f'<p>{e(a["why"])}</p>' if a.get("why") else "") + "</li>")
    mine = sorted((f for f in finds if f["item"] == x["name"]), key=lambda f: f.get("date") or "", reverse=True)
    for f in mine[:FINDS_PER_WISH]:
        date = (f.get("date") or "")[5:10].replace("-", ".")
        rows.append(f'<li><a href="{e(f["url"])}" target="_blank" rel="noopener"><small>新发现 · {e(f["label"])}'
                    f'{" · " + e(date) if date else ""}</small><br><b>{e(f["title"])}</b></a></li>')
    if not rows:
        return ""
    return f'<div class="alts"><span>类似的好产品</span><ul>{"".join(rows)}</ul></div>'


def _wish_section(wishes, works, finds=()):
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
        cls = {"已入手": "got", "没买到": "miss", "已过期": "miss", "纠结": "torn"}.get(status, "")
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
            + watch + (_alts(x, finds) if status == "纠结" else "")
            + f'<div class="links">{"".join(links)}{added}</div></div></article>')
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
    pictured = [p for p in newest if _has_photo(p[1])]  # 头条和「其他重要」带大图，只从有真正配图的里挑（来源图标不算）
    top_w, top = min(pictured, key=lambda p: RANK.get(p[1].get("weight"), 2)) if pictured else (None, None)

    groups = {}
    for w in works:
        groups.setdefault(w.get("section") or "其他", []).append(w)
    order = [n for n in SECTIONS] + [n for n in groups if n not in SECTIONS]

    head = (f'<div class="fbar"><b>头 版</b><span>LATEST · 最近 {HOLD_DAYS} 天</span>'
            f'<span>更新于 {updated} · {len(pool)} 条</span></div>')

    # 头条下面补几条次重要的（按重要度，再按新旧），填满左栏：右栏每个作品一行（约 100px）、每个板块一个标题（约 45px），
    # 头条约占 600px，「其他重要」每条约 85px
    ranked = sorted(pictured, key=lambda p: RANK.get(p[1].get("weight"), 2))
    right = 100 * len(works) + 45 * len({w.get("section") or "其他" for w in works})
    more = [p for p in ranked if p[1] is not top][:max(3, min(10, (right - 600) // 85))]
    more_html = "".join(
        f'<a class="more" href="#{_wid(w["name"])}" style="--sc:{_sec_color(w.get("section"))}">{_pic(x)}'
        f'<span><span class="nm">{e(w["name"])} · {e((x.get("date") or x["_issue"])[5:].replace("-", "."))}</span>'
        f'<b>{e(x["headline"])}</b></span></a>' for w, x in more)
    if top:
        sc = _sec_color(top_w.get("section"))
        badge = "重 磅" if top.get("weight") == "hero" else "头 条"
        top_html = (f'<a class="top" href="{e(top["url"])}" target="_blank" rel="noopener" data-k="{e(top_w["name"])}">'
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
                text, cls = first["headline"], "entry"
                # 代表这个版面的小图：最近几条报道的图、作品封面，一张打不开换下一张；都不行用第一条的来源图标
                imgs = list(dict.fromkeys([x["image"] for x in rec if x.get("image")][:3] + [w.get("_thumb")]))
                imgs = [u for u in imgs if u]
                pic = {"image": imgs[0] if imgs else None, "_fbs": imgs[1:], "_work": w["name"],
                       **{k: first.get(k) for k in ("url", "source", "source_icon")}}
            else:
                text, cls = w.get("status") or "暂无新消息", "entry q"
                pic = {"image": w.get("_thumb"), "_work": w["name"], "_fbs": []}
            rows.append(f'<a class="{cls}" href="#{_wid(w["name"])}">{_pic(pic)}'
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
.nav{top:0;height:100vh;max-height:none;padding:16px 0;margin-top:-40px}
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
                    f'<i class="no">?</i><span class="nm">我会喜欢？<small class="cnt">{len(picks)} 条候选</small></span></a>')
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
  // 只认版面级的区块（头版、我会喜欢？、各作品版面），卡片上的 data-k（投票用）不算
  const marks = [...document.querySelectorAll('.issue > [data-k]')];
  const pills = [...rail.querySelectorAll('.pill')];
  const byKey = new Map(pills.map((p, i) => [p.dataset.for, i]));
  const firstIssue = document.querySelector('.issue');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = null, curIdx = -2, curProg = -1, ticking = false;
  // 选中「在屏幕里占得最多」的区块；滚到最底时选最后一个（矮的末尾版面顶边永远到不了屏幕上方）。
  // 换选中要比当前的多占 6% 屏幕高度，免得两个版面差不多时来回跳
  function pick(top, bottom) {
    const h = bottom - top;
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) {
      for (let i = marks.length - 1; i >= 0; i--) if (marks[i].getBoundingClientRect().top < bottom) return marks[i];
    }
    let best = null, bestSeen = -1, curSeen = -1;
    for (const el of marks) {
      const r = el.getBoundingClientRect();
      if (r.bottom <= top) continue;
      if (r.top >= bottom) break;
      const seen = Math.min(r.bottom, bottom) - Math.max(r.top, top);
      if (el === cur) curSeen = seen;
      if (seen > bestSeen) { best = el; bestSeen = seen; }
    }
    return cur && curSeen >= 0 && bestSeen - curSeen < h * 0.06 ? cur : best;
  }
  function update() {
    ticking = false;
    const horizontal = getComputedStyle(rail).flexDirection === 'row';
    const top = horizontal ? nav.getBoundingClientRect().bottom : 0;
    const m = pick(top, innerHeight);
    if (!m) return;
    // 进度：这个区块读了多少（屏幕底边走过了它的几成）
    const r = m.getBoundingClientRect();
    const prog = Math.round(Math.min(1, Math.max(0, (innerHeight - r.top) / r.height)) * 100) / 100;
    const idx = m.closest('.issue') === firstIssue && byKey.has(m.dataset.k) ? byKey.get(m.dataset.k) : -1;
    if (idx !== curIdx) {   // 选中项变了才动所有条目的样式
      pills.forEach((p, i) => {
        p.classList.toggle('on', i === idx);
        p.classList.toggle('past', idx >= 0 && i < idx);
        p.style.setProperty('--p', idx >= 0 && i < idx ? 1 : 0);
      });
      curIdx = idx; curProg = -1;
      const on = pills[idx];
      nav.style.setProperty('--cur', on ? getComputedStyle(on).getPropertyValue('--sc') : '#8C8678');
      if (on) {
        const opt = horizontal ? { left: on.offsetLeft - rail.clientWidth / 2 + on.offsetWidth / 2 }
                               : { top: on.offsetTop - rail.clientHeight / 2 + on.offsetHeight / 2 };
        rail.scrollTo({ ...opt, behavior: reduce ? 'auto' : 'smooth' });
      }
    }
    if (prog !== curProg) {  // 平时只更新当前这一项的进度
      curProg = prog;
      nav.style.setProperty('--prog', prog);
      if (pills[idx]) pills[idx].style.setProperty('--p', prog);
    }
    if (m === cur) return;
    cur = m;
    const issue = m.closest('.issue');
    here.textContent = issue ? issue.dataset.label : '';
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  addEventListener('resize', update);
  update();
})();
"""


def render(issues, nav_style="line", order=None, updated=None, wishes=(), picks=(), feedback=None, sizes=None):
    """issues：按时间倒序的各期数据（全部）。nav_style：左侧目录风格，见 NAV_STYLES。
    order：items.yaml 里作品的顺序；updated：网页更新时间（显示用）；sizes：{作品: S / M / L} 篇幅。"""
    latest = issues[0]
    works = collect(issues, order)
    for w in works:
        w["_today"] = latest["date"]
        w["_size"] = (sizes or {}).get(w["name"], "M")
    updated = updated or latest["date"].replace("-", ".")
    fb = feedback if feedback and feedback.get("url") and feedback.get("key") else None
    # id 保留 issue-日期：Discord 通知里的链接指向这里
    body = (f'<div class="issue" id="issue-{latest["date"]}" data-label="更新于 {updated}">'
            + _front(works, latest["date"], updated) + _picks(picks, works, fb)
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
<a class="mastset" href="settings.html" title="设置" aria-label="设置">⚙</a>
<div class="meta"><div class="mono">更新于</div><div class="no">{updated.split(" ")[-1]}</div><div class="mono">{updated.split(" ")[0]}</div></div>
</div></header>
{_nav(works, latest['date'], wishes, picks)}
<main class="issues">{''.join(parts)}</main>
</div>
<script>{NAV_JS}</script>
{f"<script>{VOTE_JS % json.dumps(fb)}</script>" if fb else ""}
</body>
</html>
"""
