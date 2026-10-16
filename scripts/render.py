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

import theme
from images import FAVICON_SERVICE, GENERIC, base_domain  # 网站 logo / 默认分享图的判断，和找图用同一条规则

FONTS = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900&family=Noto+Sans+SC:wght@500;700;900"
    "&family=Noto+Sans+TC:wght@500;700;900&family=Noto+Sans+KR:wght@500;700;900&family=Noto+Serif+SC:wght@500;700;900"
    "&family=Anton&family=Yusei+Magic&family=JetBrains+Mono:wght@500;700&display=swap"
)

CSS = """
:root{--ink:#1A1C22;--paper:#EDEBE6;--rose:#B8336A;--sheet:#F4EDE4;--card:#FBF8F1;--gold:#FFD23F;--alert:#D7261E;
 --font-sans:'Noto Sans JP','Noto Sans TC','Noto Sans SC','Noto Sans KR',sans-serif;--font-serif:'Noto Serif JP','Noto Serif SC',serif;
 --font-mono:'JetBrains Mono',monospace;--font-num:'Anton',Impact,sans-serif;--font-hand:'Yusei Magic','Noto Sans JP',sans-serif;
 --fs-label:11px;--fs-tag:10px;--gap:16px;--hair:color-mix(in srgb,var(--ink) 16%,transparent);
 --shadow:4px 4px 0 var(--ink);--shadow-l:8px 8px 0 var(--ink);--tilt:-1.5deg;--skew:-8deg}
/* デザインの骨格（PRODUCT.md）：文字箱の後ろに硬い影、見出しと枠だけ少し傾ける（-1〜-2.5°）、ラベルは平行四辺形。
   本文・リスト・作品の版面は傾けない。配色はトークンと版面の色だけ */
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:500 15px/1.6 var(--font-sans);-webkit-font-smoothing:antialiased}
html,body{overflow-x:clip}  /* 傾けた箱・吹き出しの矢印が端からはみ出してもページが横にずれない（sticky は効いたまま） */
::selection{background:var(--rose);color:#FFF}
a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--rose);outline-offset:2px}
a{color:inherit;text-decoration:none}
button{font-family:inherit}
.page{max-width:1200px;margin:0 auto;padding:40px 24px;display:flex;flex-direction:column;gap:28px}
.mono{font-family:var(--font-mono);font-size:13px}
/* ---------- 共通の部品：ラベル・見出し箱・行ごとの黒箱 ---------- */
.tg{display:inline-block;flex:none;white-space:nowrap;background:var(--sc,var(--ink));color:#FFF;padding:1px 10px;transform:skewX(var(--skew));
 font:700 12px/1.55 var(--font-sans);letter-spacing:.04em;font-style:normal}
.tg>span{display:inline-block;transform:skewX(8deg)}
.sh{margin:0;display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 14px}
.sh>span{display:inline-block;background:var(--ink);color:var(--card);padding:6px 18px 6px 16px;transform:rotate(var(--tilt));
 box-shadow:4px 4px 0 var(--rose);font:900 24px/1.25 var(--font-sans);letter-spacing:.06em}
.sh small{font:700 12px/1.5 var(--font-sans);letter-spacing:.06em;opacity:.7}
.hb{display:inline;background:var(--ink);color:var(--card);padding:3px 12px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
/* ---------- 画像：縦横比が枠に近い写真は枠いっぱい（.fill、FIT_JS が付ける）。違う写真はぼかしの上に全体を表示 ---------- */
.pic{position:relative;overflow:hidden;aspect-ratio:16/9;background:color-mix(in srgb,currentColor 8%,transparent)}
.pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.pic.fill img:not(.bg):not(.ico){object-fit:cover}
.pic.fill img.bg{display:none}
.pic .ph{position:absolute;inset:0;display:none;align-items:center;justify-content:center;padding:12px;text-align:center;
 font:900 clamp(15px,2.2vw,26px)/1.2 var(--font-sans);letter-spacing:.04em;color:#FFF;
 background:radial-gradient(circle,color-mix(in srgb,#000 22%,transparent) 1px,transparent 1.5px) 0 0/7px 7px,var(--ac,var(--rose))}
.pic.none{background:none}
.pic.none .ph{display:flex}
.pic.icon{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
 background:color-mix(in srgb,currentColor 6%,transparent)}
.pic.icon img.ico{position:static;width:min(64px,30%);height:auto;aspect-ratio:1;object-fit:contain;
 background:#FFFFFF;border-radius:14px;padding:6px;box-shadow:0 1px 4px rgba(0,0,0,.18)}
.pic.icon .src{max-width:90%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font:700 13px var(--font-sans);opacity:.75}
.pic:not(.icon) img.ico,.pic:not(.icon) .src{display:none}
.pic img.bg{object-fit:cover;filter:blur(18px) brightness(.85);transform:scale(1.15)}
/* ---------- 報頭 ---------- */
.mast{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px 20px}
.mast .mtitle{display:flex;align-items:flex-end;gap:14px;min-width:0}
.mast h1{margin:0;display:inline-block;background:var(--card);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink);transform:rotate(-1deg);
 padding:10px 22px 8px;font:900 clamp(26px,3.4vw,48px)/1.1 var(--font-sans);letter-spacing:.02em;white-space:nowrap}
.mast .stamp{padding-bottom:6px;font:700 11px/1.4 var(--font-sans);letter-spacing:.08em;opacity:.65}
.mast .tools{display:flex;align-items:stretch;gap:10px}
.mast .meta{display:flex;flex-direction:column;justify-content:center;padding:4px 14px;border:2px solid var(--ink);background:var(--card)}
.mast .meta small{font:700 10px/1.3 var(--font-sans);letter-spacing:.2em;opacity:.7}
.mast .meta b{font:26px/1 var(--font-num);letter-spacing:.02em;white-space:nowrap}
.mastwish{display:flex;align-items:center;gap:8px;padding:8px 14px;border:2px solid var(--rose);background:var(--rose);color:#FFF;
 box-shadow:var(--shadow);font:900 14px/1.3 var(--font-sans);white-space:nowrap;transition:transform .1s,box-shadow .1s}
.mastwish small{font:700 11px/1.3 var(--font-sans);background:var(--card);color:var(--rose);padding:1px 7px}
.mastwish:hover{transform:translate(2px,2px);box-shadow:2px 2px 0 var(--ink)}
.mastset{display:flex;align-items:center;padding:8px 14px;border:2px solid var(--ink);background:var(--card);font:700 13px var(--font-sans);white-space:nowrap}
.mastset:hover{background:var(--ink);color:var(--card)}
.navwish{display:flex;align-items:center;gap:8px;margin:10px 0 0 14px;padding:8px 12px;border:2px solid var(--rose);color:var(--rose);
 font:900 13px var(--font-sans);letter-spacing:.1em;flex:none;box-shadow:3px 3px 0 var(--rose)}
.navwish small{margin-left:auto;font:700 11px var(--font-sans);opacity:.8}
.navwish:hover{background:var(--rose);color:#FFF}
@media (max-width:1000px){.navwish{display:none}}
.issue{display:flex;flex-direction:column;gap:40px}
/* ---------- トップ：毎日刷り直すポスター。地色はその日のトップ記事の写真から（--tint / --deep / --hacc） ---------- */
.front{display:flex;flex-direction:column;gap:40px}
.poster{position:relative;background:var(--tint,var(--sheet));color:var(--ink);border:2px solid var(--ink);box-shadow:var(--shadow-l);padding:22px 28px 18px}
.poster::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.12;
 background-image:radial-gradient(var(--deep,var(--ink)) .7px,transparent .9px);background-size:6px 6px}
.poster .marks{position:absolute;inset:10px;pointer-events:none;opacity:.5;background:
 linear-gradient(var(--ink),var(--ink)) 0 0/16px 1px no-repeat,linear-gradient(var(--ink),var(--ink)) 0 0/1px 16px no-repeat,
 linear-gradient(var(--ink),var(--ink)) 100% 0/16px 1px no-repeat,linear-gradient(var(--ink),var(--ink)) 100% 0/1px 16px no-repeat,
 linear-gradient(var(--ink),var(--ink)) 0 100%/16px 1px no-repeat,linear-gradient(var(--ink),var(--ink)) 0 100%/1px 16px no-repeat,
 linear-gradient(var(--ink),var(--ink)) 100% 100%/16px 1px no-repeat,linear-gradient(var(--ink),var(--ink)) 100% 100%/1px 16px no-repeat}
.phead{position:relative;display:flex;align-items:center;flex-wrap:wrap;gap:8px 14px;font:700 12px/1.4 var(--font-sans);letter-spacing:.06em}
.phead .lab{background:var(--ink);color:var(--card);padding:3px 12px;transform:skewX(var(--skew))}
.phead .day{margin-left:auto;font:15px/1 var(--font-num);letter-spacing:.04em;color:var(--deep,var(--ink))}
.top{position:relative;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);grid-template-rows:auto 1fr;gap:10px 36px;margin-top:14px;color:var(--ink)}
.pdate{display:flex;align-items:flex-end;gap:14px;padding-top:4px}
.pdate b{font:clamp(84px,9.5vw,164px)/.86 var(--font-num);color:var(--deep,var(--ink));letter-spacing:-.01em;text-shadow:5px 5px 0 var(--hacc,var(--rose))}
.pdate span{display:flex;flex-direction:column;align-items:center;padding:8px 12px 6px;background:var(--deep,var(--ink));color:var(--card);
 transform:rotate(-3deg);box-shadow:var(--shadow);font:40px/1 var(--font-num)}
.pdate small{font:700 11px/1.4 var(--font-sans);letter-spacing:.2em}
.frame{grid-column:2;grid-row:1/3;position:relative;align-self:start;margin:12px 8px 8px 0;padding:8px;background:var(--card);
 border:2px solid var(--ink);box-shadow:var(--shadow-l);transform:rotate(-2deg);transition:transform .2s}
.top:hover .frame{transform:rotate(-1deg) translateY(-2px)}
.frame .pic{border:1.5px solid var(--ink);color:var(--ink)}
.burst{position:absolute;top:-22px;left:-26px;z-index:2;display:grid;place-items:center;width:92px;height:92px;background:var(--alert);color:#FFF;
 font:900 21px/1 var(--font-sans);letter-spacing:.12em;transform:rotate(8deg);filter:drop-shadow(3px 3px 0 var(--ink));
 clip-path:polygon(50% 0,61% 13%,77% 6%,80% 23%,97% 25%,89% 40%,100% 50%,89% 60%,97% 75%,80% 77%,77% 94%,61% 87%,50% 100%,39% 87%,23% 94%,20% 77%,3% 75%,11% 60%,0 50%,11% 40%,3% 25%,20% 23%,23% 6%,39% 13%)}
.ptxt{display:flex;flex-direction:column;gap:16px;align-self:end;padding-bottom:6px;min-width:0}
.kick{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.kick em{font:16px/1 var(--font-num);font-style:normal;letter-spacing:.04em;color:var(--deep,var(--ink))}
.top h2{margin:0;max-width:600px;font:900 clamp(21px,2.2vw,31px)/1.55 var(--font-sans);letter-spacing:.01em;transform:rotate(var(--tilt));transform-origin:left top}
.top:hover .hb{background:var(--deep,var(--ink))}
.top p{margin:0;max-width:560px;font-size:14px;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pfoot{position:relative;display:flex;align-items:center;flex-wrap:wrap;gap:8px 16px;margin-top:16px;padding-top:12px;border-top:1.5px solid var(--ink);
 font:700 11px/1.4 var(--font-sans);letter-spacing:.06em;color:var(--deep,var(--ink))}
.cbar{display:inline-block;flex:none;width:112px;height:10px;border:1px solid var(--ink);
 background:linear-gradient(90deg,var(--sc1,#00B4EE) 0 14%,var(--sc2,#FF3D8B) 14% 28%,var(--gold) 28% 42%,var(--ink) 42% 56%,var(--hacc,var(--rose)) 56% 70%,var(--deep,var(--ink)) 70% 84%,var(--card) 84%)}
/* ---------- ほかの注目ニュース：写真の壁 ＋ ジャンルの棚 ---------- */
.spot{display:flex;flex-direction:column;gap:22px}
.mgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,300px);gap:28px;align-items:stretch}
/* 左の壁と右の列の下端をそろえる：短いほうが伸びる（壁は各段が均等に伸び、右の列は最後の箱が伸びる） */
.mgrid>.wall{align-content:stretch}
.mgrid .wc{justify-content:flex-start}.mgrid .wc .pic{flex:1 0 auto}
.fside>:last-child{flex:1}
.fside{display:flex;flex-direction:column;gap:20px;min-width:0}
.sbox{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:12px 14px 12px}
.sbox h4,.fside .agenda h4{margin:0 0 6px;display:flex;align-items:baseline;gap:10px;padding-bottom:7px;border-bottom:2px solid var(--ink);font:900 16px/1.3 var(--font-sans);letter-spacing:.04em}
.sbox h4 small{margin-left:auto;font:700 11px var(--font-sans);opacity:.6}
.sbox h4 a:hover{color:var(--rose)}
.swish ol,.shot ol{list-style:none;margin:0;padding:0}
.swish li{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:10px;align-items:center;padding:7px 0;border-bottom:1px dashed var(--hair)}
.wthumb{width:48px;height:48px;background:#FFF;border:1.5px solid var(--ink);display:grid;place-items:center;overflow:hidden}
.wthumb img{width:90%;height:90%;object-fit:contain}
.wt{display:flex;flex-direction:column;min-width:0}
.wt b{font:700 13px/1.4 var(--font-sans);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.wt em{font:15px/1.2 var(--font-num);font-style:normal;color:var(--rose)}
.swish .tg{font-size:11px;padding:0 7px}
.stot{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin:8px 0 6px;font:700 11px var(--font-sans);opacity:.85}
.stot b{font:20px var(--font-num);color:var(--ink)}
.smore{display:block;text-align:center;padding:6px;background:var(--rose);color:#FFF;font:900 13px var(--font-sans);letter-spacing:.06em;box-shadow:3px 3px 0 var(--ink)}
.smore:hover{background:var(--ink)}
.shot li a{display:grid;grid-template-columns:96px minmax(0,1fr) 28px;gap:8px;align-items:center;padding:5px 0}
.shot .bn{font:700 12px/1.3 var(--font-sans);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.shot .bar{height:12px;width:calc(var(--v) * 100%);background:var(--sc);transform:skewX(var(--skew));box-shadow:2px 2px 0 var(--ink)}
.shot b{font:16px var(--font-num);text-align:right}
.shot li a:hover .bn{text-decoration:underline}
.staste ul{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.staste li{display:inline-flex;align-items:baseline;gap:5px;padding:3px 9px;border:1.5px solid var(--ink);background:#FFF;font:700 12px var(--font-sans)}
.staste li b{font:13px var(--font-num);color:var(--rose)}
.staste p{margin:8px 0 0;font-size:11px;opacity:.7}
.fside .agenda{padding:12px 14px 8px}
.fside .agenda ol{grid-template-columns:minmax(0,1fr)}
.agenda li b small{display:block;font:700 11px var(--font-sans);color:var(--ink);opacity:.7}
.wall{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-flow:dense;gap:22px;align-content:start}
.wc{position:relative;display:flex;flex-direction:column;gap:8px;min-width:0;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);
 padding:10px 12px 14px;transition:transform .12s,box-shadow .12s}
.wc:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
.wc.lead{grid-column:span 2;grid-row:span 2}
.wc .pic{border:1.5px solid var(--ink);aspect-ratio:16/10;--ac:var(--sc)}
.wc.lead .pic{aspect-ratio:auto;flex:1;min-height:280px}
.wc .tg{position:absolute;left:-8px;top:18px;z-index:2;box-shadow:2px 2px 0 var(--ink)}
.wc em{font:15px/1 var(--font-num);font-style:normal;letter-spacing:.04em}
.wc b{font:700 15px/1.5 var(--font-sans);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.wc.lead b{font-size:22px;font-weight:900;line-height:1.45;-webkit-line-clamp:2}
.wc:hover b{text-decoration:underline;text-underline-offset:3px}
/* ジャンルの棚：ジャンルごとに看板、作品ごとに最新の 1 本をテープのように並べる（版面へのリンク） */
.shelves{display:flex;flex-wrap:wrap;align-items:flex-end;gap:30px 26px;padding-top:6px}
.shelf{flex:var(--n) 1 calc(var(--n) * 150px);min-width:0;position:relative;padding-top:32px;--sc:var(--ink)}
.sign{position:absolute;left:0;top:0;margin:0;display:inline-flex;align-items:baseline;gap:10px;padding:5px 14px 4px;background:var(--sc);color:#FFF;
 transform:rotate(var(--tilt));box-shadow:3px 3px 0 var(--ink);font:900 16px/1.3 var(--font-sans);letter-spacing:.1em;white-space:nowrap}
.sign small{font:11px/1.3 var(--font-num);letter-spacing:.12em;opacity:.9}
.tapes{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:12px;padding:0 10px 0 6px}
.tape{display:grid;grid-template-columns:18px minmax(0,1fr);min-width:0;background:var(--card);border:1.5px solid var(--ink);box-shadow:3px 3px 0 var(--ink);transition:transform .12s}
.tape:hover{transform:translateY(-4px)}
.tape .spine{grid-row:1/3;writing-mode:vertical-rl;background:var(--sc);color:#FFF;padding:6px 0;text-align:center;font:900 10px/18px var(--font-sans);letter-spacing:.2em;overflow:hidden}
.tape .pic{margin:6px 6px 0 0;border:1px solid var(--ink);aspect-ratio:4/3;--ac:var(--sc)}
.tape .lbl{display:flex;flex-direction:column;gap:2px;min-width:0;padding:7px 8px 9px 2px}
.tape .lbl i{font:700 11px/1.3 var(--font-sans);font-style:normal;color:var(--sc);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tape .lbl b{font:700 13px/1.45 var(--font-sans);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tape.q .lbl b{font-weight:500;opacity:.65}
.plank{height:12px;margin-top:-2px;background:var(--ink);box-shadow:0 6px 0 color-mix(in srgb,var(--ink) 30%,transparent)}
/* ---- 将来のコンテンツ用の部品（_extras / _play / _agenda）。色はトークンと版面の --ac だけを使う ---- */
.xprice{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;margin-top:2px;font:700 var(--fs-label) var(--font-sans)}
.xprice b{font:20px var(--font-num);color:var(--ac,var(--rose))}
.xprice s{opacity:.7}.xprice i{font-style:normal;padding:1px 6px;background:var(--ac,var(--rose));color:var(--card);transform:skewX(var(--skew))}
.xprice span{opacity:.8}
.xevent{display:flex;align-items:baseline;gap:10px;margin-top:2px;padding:5px 10px;border:2px solid currentColor;box-shadow:3px 3px 0 currentColor;align-self:flex-start}
.xevent b{font:20px var(--font-num);letter-spacing:.02em}.xevent span{font:700 12px var(--font-sans)}
.xgal{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin-top:4px}
.xgal img{width:100%;aspect-ratio:1;object-fit:cover;display:block;border:1px solid currentColor}
.xplay{position:absolute;z-index:2;align-self:flex-start;display:inline-flex;align-items:center;gap:6px;padding:2px 10px;background:var(--ink);color:var(--card);font:700 var(--fs-label) var(--font-sans);letter-spacing:.08em}
.xplay::after{content:"動画"}
.agenda{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:14px 18px 8px}
.agenda h4{margin:0 0 4px;display:flex;align-items:baseline;gap:14px;font:900 18px var(--font-sans);letter-spacing:.06em}
.agenda h4 small{font:11px var(--font-num);letter-spacing:.2em;color:var(--alert)}
.agenda ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(260px,100%),1fr));gap:0 32px}
.agenda li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 12px;padding:8px 0;border-bottom:1px dashed var(--hair)}
.agenda li b{grid-row:span 2;font:22px var(--font-num);color:var(--sc)}
.agenda .nm{font:700 var(--fs-label) var(--font-sans);color:var(--sc)}
.agenda a{color:var(--ink);font-weight:700;line-height:1.4}.agenda a:hover{text-decoration:underline}
/* ---------- 作品の版面：作品の色（封面から取色）＋ 作品ごとの装飾（.m-○○、items.yaml の motif） ---------- */
.sec{position:relative;background:var(--bg);color:var(--fg);border:2px solid var(--ink);box-shadow:var(--shadow-l)}
.band{position:relative;display:flex;align-items:center;flex-wrap:wrap;gap:8px 18px;padding:20px 26px 4px;min-height:0}
.band .title{display:inline-block;background:var(--abg);color:var(--afg);padding:8px 22px 8px 18px;transform:rotate(-1deg);
 box-shadow:5px 5px 0 var(--acc);font:900 30px/1.2 var(--font-sans);letter-spacing:.03em}
.band .sub{font:700 12px/1.4 var(--font-sans);letter-spacing:.12em;opacity:.85}
.band .cnt{margin-left:auto;font:700 12px/1.3 var(--font-sans);opacity:.85;white-space:nowrap}
.band .cnt b{margin-right:6px;font:30px/1 var(--font-num);color:var(--acc)}
.band .deco{position:absolute;pointer-events:none;font-style:normal}
.facts{display:flex;flex-wrap:wrap;gap:12px;padding:16px 26px 0}
.fact{flex:1 1 280px;padding:12px 18px;background:var(--abg);color:var(--afg);box-shadow:4px 4px 0 var(--acc);display:flex;flex-direction:column;gap:4px}
.fact .label{font:700 11px var(--font-sans);letter-spacing:.14em;opacity:.8}
.fact .new{color:var(--aac);opacity:1}
.fact a{text-decoration:underline;text-underline-offset:3px}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:18px 22px;padding:20px 26px 22px}
.card{position:relative;display:flex;flex-direction:column;gap:10px;min-width:0}
.card.m{color:var(--fg);--ac:var(--acc)}
.card.a{color:var(--afg);--ac:var(--aacc)}
.card .pic{border:1.5px solid color-mix(in srgb,currentColor 45%,transparent)}
.card:hover h2,.card:hover h3{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:1px}
.hl{color:var(--ac)}
.tag{display:inline-block;align-self:flex-start;padding:2px 10px;background:var(--alert);color:#FFF;transform:skewX(var(--skew));font:900 12px/1.4 var(--font-sans);letter-spacing:.2em}
.card h2,.card h3{margin:0;font-family:var(--font-sans);font-weight:900}
.hero{grid-column:span 12;display:grid;grid-template-columns:7fr 5fr;gap:24px}
.hero .pic{align-self:center}
.hero .txt{display:flex;flex-direction:column;justify-content:center;gap:14px}
.hero h2{font-size:30px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden;text-wrap:balance}
.lead{grid-column:span 8}
.lead h2{font-size:28px;line-height:1.4}
.side{grid-column:span 4;display:flex;flex-direction:column;gap:14px}
.side h3{font-size:20px;line-height:1.4}
.s12{grid-column:span 12}.s6{grid-column:span 6}.s4{grid-column:span 4}
.blurb{margin:0;font-size:15px;line-height:1.75;opacity:.85}
.quiet .band{padding-bottom:18px}
.quiet .band .title{font-size:22px;padding:6px 16px}
.calm{display:flex;align-items:center;gap:20px;padding:4px 26px 20px;color:var(--fg)}
.calm .pic{flex:0 0 120px;height:62px;aspect-ratio:auto;border:1.5px solid color-mix(in srgb,currentColor 45%,transparent)}
.calm .txt{flex:1;display:flex;flex-direction:column;align-items:flex-start;gap:6px;min-width:0}
.calm .tag{background:var(--acc);color:var(--bg);letter-spacing:.12em}
.calm .status{font-size:15px;line-height:1.6}
.calm .last{flex:0 1 40%;display:flex;flex-direction:column;gap:2px;font-size:14px;line-height:1.5;border-left:1px solid color-mix(in srgb,currentColor 25%,transparent);padding-left:20px}
.calm .last .mono{font:13px var(--font-num);letter-spacing:.06em;opacity:.75}
.calm a.last:hover b{text-decoration:underline;text-underline-offset:4px}
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}.c3{grid-column:span 3}
.when{display:flex;align-items:center;gap:8px;font:14px/1 var(--font-num);letter-spacing:.05em;opacity:.85}
.when b{padding:2px 7px 1px;background:var(--ac);color:var(--bg);font:900 10px/1.4 var(--font-sans);letter-spacing:.14em}
.card.a .when b{color:var(--abg)}
.card.wide{display:grid;grid-template-columns:4fr 8fr;gap:24px;align-items:center}
.card.wide .txt{display:flex;flex-direction:column;gap:10px;min-width:0}
.card.wide h3{font-size:24px;line-height:1.4}
.card.c8 h3{font-size:24px;line-height:1.4}.card.c6 h3{font-size:21px;line-height:1.4}
.card.c4 h3,.card.c3 h3{font-size:17px;line-height:1.45}
.grid>.hero .pic{aspect-ratio:auto;height:280px}
.grid>.lead .pic{aspect-ratio:auto;height:260px}
.grid>.lead h2,.card.wide h3,.mini h3{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.grid>.lead .blurb,.card.wide .blurb{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card.mini{display:grid;grid-template-columns:120px minmax(0,1fr);grid-template-rows:auto 1fr;gap:6px 14px;align-content:start;
 padding-bottom:14px;border-bottom:1px solid color-mix(in srgb,currentColor 22%,transparent)}
.mini .pic{grid-row:span 2;align-self:start;aspect-ratio:4/3}
.mini .pic .ph{font-size:12px}.mini .pic.icon{gap:4px}.mini .pic.icon img.ico{width:min(40px,30%);border-radius:9px;padding:4px}
.mini .pic.icon .src{font-size:11px}
.mini h3{align-self:start;font-size:15px;font-weight:700;line-height:1.5}
.side .card.mini{grid-template-columns:110px minmax(0,1fr)}
.brief{padding:12px 26px 18px;border-top:1px solid var(--line)}
.brief h4{margin:0 0 8px;font:900 13px var(--font-sans);letter-spacing:.12em;opacity:.8}
.brief ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.brief li{display:flex;gap:14px;align-items:baseline;font-size:15px;line-height:1.5}
.brief .d{font:13px var(--font-num);opacity:.7;flex:none}
.brief a{color:inherit;font-weight:700}
.brief a:hover,.brief a:focus-visible{color:var(--acc);text-decoration:underline}
.older{background:var(--abg);color:var(--afg)}
.older summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:12px 26px;font:900 13px var(--font-sans);letter-spacing:.1em}
.older summary::-webkit-details-marker{display:none}
.older summary::before{content:"+";display:inline-grid;place-items:center;width:22px;height:22px;background:var(--aacc);color:var(--abg);transform:skewX(var(--skew));
 font:900 15px/1 var(--font-sans)}
.older[open] summary::before{content:"−"}
.older summary:hover,.older summary:focus-visible{color:var(--aacc);outline:none}  /* 折叠区是副色底：用副色的强调色 */
.older summary span{font-weight:700;opacity:.7;letter-spacing:.04em}
.older .grid{padding-top:8px}
.older .card.c3 h3{font-size:15px;line-height:1.45}
/* ---- 作品ごとの装飾（motif）。どれも作品の色（--bg/--acc…）だけで描く。足すときは EDITING.md にも書く ---- */
.m-retro{background-image:radial-gradient(circle,color-mix(in srgb,var(--acc) 35%,transparent) 1px,transparent 1.6px),
 radial-gradient(circle,color-mix(in srgb,var(--acc) 20%,transparent) 1px,transparent 1.6px);background-size:34px 34px,21px 21px;background-position:0 0,11px 7px}
.m-retro .band .title{border-radius:0 18px 0 18px;box-shadow:5px 5px 0 var(--acc),0 0 0 3px var(--bg),0 0 0 5px var(--acc);letter-spacing:.06em}
.m-retro .deco{right:34%;top:12px;font-size:34px;color:var(--acc);text-shadow:0 0 14px var(--acc)}
.m-retro .deco.d2{right:31%;top:50px;font-size:18px}
.m-retro .card .pic{border:2px solid var(--acc);box-shadow:4px 4px 0 color-mix(in srgb,var(--acc) 45%,transparent)}
.m-retro .when b{border-radius:999px}
.m-manga{background-image:radial-gradient(circle,color-mix(in srgb,var(--fg) 26%,transparent) .9px,transparent 1.3px);background-size:5px 5px}
.m-manga .band .title{transform:rotate(-2deg) skewX(-4deg);box-shadow:6px 6px 0 var(--acc)}
.m-manga .deco{right:24%;top:-2px;font:900 54px/1 var(--font-sans);color:var(--acc);opacity:.35;transform:rotate(-8deg) skewX(-10deg);letter-spacing:-.04em}
.m-manga .card .pic{border:3px solid var(--fg)}
.m-manga .grid>.lead .pic,.m-manga .grid>.hero .pic{clip-path:polygon(0 0,100% 0,100% 100%,3% 100%)}
.m-manga .card.mini{padding:8px;border:2.5px solid var(--fg);background:color-mix(in srgb,var(--bg) 82%,#FFF)}
.m-manga .card.mini:nth-child(odd){clip-path:polygon(0 0,100% 0,97% 100%,0 100%)}
.m-manga .card.mini:nth-child(even){clip-path:polygon(3% 0,100% 0,100% 100%,0 100%)}
.m-pop{background-image:radial-gradient(circle,color-mix(in srgb,var(--acc) 22%,transparent) 5px,transparent 5.5px);background-size:46px 46px}
.m-pop .band .title{border-radius:999px;padding:8px 26px;transform:rotate(-2deg)}
.m-pop .deco{right:30%;top:8px;font-size:30px;color:var(--acc);transform:rotate(12deg)}
.m-pop .card .pic{border-radius:14px;border:3px solid var(--acc);box-shadow:4px 4px 0 var(--fg)}
.m-pop .when b{border-radius:999px}
.m-film .band{padding-top:30px}
.m-film .band::before{content:"";position:absolute;left:0;right:0;top:0;height:16px;background:var(--fg);
 -webkit-mask:repeating-linear-gradient(90deg,#000 0 14px,transparent 14px 24px) 0 4px/100% 8px no-repeat,linear-gradient(#000,#000) 0 0/100% 4px no-repeat,linear-gradient(#000,#000) 0 12px/100% 4px no-repeat;
 mask:repeating-linear-gradient(90deg,#000 0 14px,transparent 14px 24px) 0 4px/100% 8px no-repeat,linear-gradient(#000,#000) 0 0/100% 4px no-repeat,linear-gradient(#000,#000) 0 12px/100% 4px no-repeat}
.m-film .band .title{letter-spacing:.12em;text-transform:uppercase}
.m-film .card .pic{border:4px solid var(--fg);border-left-width:10px;border-right-width:10px}
.m-street .band .title{transform:skewX(-10deg) rotate(-1deg);box-shadow:6px 6px 0 var(--acc)}
.m-street .band::after{content:"";position:absolute;left:0;right:0;bottom:-6px;height:6px;
 background:repeating-linear-gradient(-45deg,var(--acc) 0 10px,transparent 10px 20px);opacity:.8}
.m-street .card .pic{clip-path:polygon(0 0,100% 0,100% 88%,94% 100%,0 100%)}
/* ---------- 気になるかも？：店長のおすすめ POP ---------- */
.picks{--ac:var(--rose);background:var(--sheet);color:var(--ink);border:2px solid var(--ink);box-shadow:8px 8px 0 var(--rose);padding:22px 26px 28px}
.pkhead{display:flex;flex-wrap:wrap;align-items:center;gap:12px 18px}
.pkhead h2{margin:0;display:inline-block;background:var(--ink);color:var(--card);padding:6px 18px 6px 16px;transform:rotate(var(--tilt));box-shadow:4px 4px 0 var(--rose);
 font:900 24px/1.25 var(--font-sans);letter-spacing:.06em}
.pkhead h2 em{font-style:normal;color:var(--gold)}
.pkhead .flag{position:relative;display:inline-block;padding:8px 14px 7px;background:var(--card);box-shadow:var(--shadow);transform:rotate(-2deg);font:21px/1 var(--font-hand)}
.pkhead .flag::after{content:"";position:absolute;right:-12px;top:50%;margin-top:-8px;border:8px solid transparent;border-left:12px solid var(--card);border-right:0}
.pkhead>span:not(.flag){flex-basis:100%;order:3;font-size:13px;opacity:.8}
.pkhead a{color:var(--rose);font-weight:700;border-bottom:1px solid currentColor}
.pkgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:36px 22px;margin-top:22px;align-items:start}
.pkgrid.row{grid-template-columns:repeat(var(--n),minmax(0,1fr))}
.pksub{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 12px;margin-top:34px;font:900 15px var(--font-sans);letter-spacing:.1em}
.pksub::before{content:"";flex:none;width:18px;height:18px;background:var(--rose);transform:skewX(var(--skew));align-self:center}
.pksub span{font:500 12px var(--font-sans);letter-spacing:0;opacity:.75}
.pk{position:relative;display:flex;flex-direction:column;gap:0;min-width:0;color:var(--ink)}
.pk.big{grid-column:span 2;grid-row:span 2;align-self:stretch}
.pk.big>a{flex:1}.pk.big .pic{flex:1 1 auto;aspect-ratio:auto;min-height:280px}  /* 大きいカードは 2 段分の高さまで写真を伸ばす（下に空白を残さない） */
.pk>a{display:flex;flex-direction:column;min-width:0;flex:1}
.pk .pic{background:#FFF;color:var(--ink);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink);aspect-ratio:16/10}
.pk.big .pic{aspect-ratio:4/3}
.pk .pkt{position:relative;z-index:1;display:flex;flex-direction:column;gap:7px;min-width:0;margin:-18px 10px 0;padding:16px 15px 12px;background:var(--card);
 box-shadow:var(--shadow);transform:rotate(-1deg)}
.pk:nth-child(even) .pkt{transform:rotate(1deg)}
.pk.big .pkt{margin:-40px 24px 0;padding:22px 22px 16px;transform:rotate(-1.2deg)}
.pk .why{order:-1;font:16px/1.5 var(--font-hand);color:var(--ink)}
.pk .why mark{color:inherit;background:linear-gradient(transparent 55%,var(--gold) 55% 92%,transparent 92%);-webkit-box-decoration-break:clone;box-decoration-break:clone;padding:0 2px}
.pk .why small{display:block;margin-top:3px;font-size:13px;opacity:.75}
.pk.big .why{font-size:25px;line-height:1.45}
.pk.big .why small{font-size:15px}
.pk .src{font:500 12px/1.4 var(--font-sans);opacity:.7}
.pk b{font:700 15px/1.5 var(--font-sans);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.pk.big b{font-size:20px;font-weight:900;line-height:1.45;-webkit-line-clamp:4}
.pk .tags{display:flex;flex-wrap:wrap;gap:5px}
.pk .tags:empty{display:none}
.pk .tags i{font-style:normal;padding:2px 8px;border:1.5px solid var(--ink);background:#FFF;font:700 11px/1.3 var(--font-sans)}
.pk>a:hover b{text-decoration:underline;text-underline-offset:3px}
.pk .taste{font-size:11px;opacity:.7}
.pk .vote{position:relative;z-index:2;margin:8px 10px 0;padding:0 2px}
.pk.big .vote{margin:12px 24px 0}
.vote{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.pk:not(.big) .vote button span{display:none}
.vote button{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border:2px solid var(--ink);background:var(--card);color:var(--ink);
 box-shadow:3px 3px 0 var(--ink);font:700 13px var(--font-sans);cursor:pointer;border-radius:0;white-space:nowrap;transition:transform .1s,box-shadow .1s}
.vote button:hover{transform:translate(1px,1px);box-shadow:2px 2px 0 var(--ink)}
.vote button[aria-pressed=true]{background:var(--rose);border-color:var(--rose);color:#FFF}
.vote button:disabled{opacity:.5;cursor:wait}
.vote small{font-size:11px;opacity:.7}
.pk.down>a{opacity:.35;filter:grayscale(1)}
.card,.top,.wc{position:relative}
.vt{position:absolute;top:8px;right:8px;z-index:3;display:flex;gap:4px;opacity:.55;transition:opacity .15s}
.card:hover .vt,.top:hover .vt,.wc:hover .vt,.vt:focus-within,.vt.on{opacity:1}
.vt button{padding:2px 7px;border:1.5px solid var(--ink);background:var(--card);color:var(--ink);box-shadow:2px 2px 0 var(--ink);font-size:13px;line-height:1.4;cursor:pointer;border-radius:0}
.vt button[aria-pressed=true]{background:var(--rose);border-color:var(--rose);color:#FFF}
.top .vt{top:auto;bottom:0;right:0}
.brief li .vt{position:static;opacity:.5;margin-left:auto;flex:none}
.brief li:hover .vt{opacity:1}
.downv{opacity:.4;filter:grayscale(.8)}
.pkbatch[hidden]{display:none}
.shuffle{padding:7px 14px;border:2px solid var(--ink);background:var(--ink);color:var(--card);transform:skewX(var(--skew));box-shadow:3px 3px 0 var(--rose);
 font:900 13px var(--font-sans);letter-spacing:.06em;cursor:pointer;border-radius:0;white-space:nowrap}
.shuffle:hover{background:var(--rose);border-color:var(--rose);box-shadow:3px 3px 0 var(--ink)}
.shuffle small{margin-left:8px;padding:1px 7px;background:var(--card);color:var(--rose);font:700 11px var(--font-sans)}
.pknav{margin-left:auto;display:flex;gap:10px;white-space:nowrap}
.shuffle.back{background:var(--card);color:var(--ink);box-shadow:3px 3px 0 var(--ink)}
.shuffle[disabled]{opacity:.35;cursor:default;pointer-events:none}
@media (hover:none){.vt{opacity:.9}.vt button{padding:6px 10px;font-size:14px}}  /* 指で押せる大きさ（約 40×32） */
.vote button:active,.shuffle:active,.vt button:active,.mastwish:active{transform:translate(3px,3px);box-shadow:none}  /* 押した感触：影の分だけ沈む */
.pk .vote button{min-height:36px}
@media (hover:hover){.card:not(:hover) .vt:not(.on):not(:focus-within),.wc:not(:hover) .vt:not(.on):not(:focus-within){opacity:0}}  /* 細いカードでは見出しに重なるので、マウスを載せたときだけ */
/* ---------- 中くらいの幅 ---------- */
@media (max-width:1200px){
 .mgrid{grid-template-columns:minmax(0,1fr)}.mgrid>.wall{align-content:start}.fside>:last-child{flex:none}.fside{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px}
 .wall{grid-template-columns:repeat(2,minmax(0,1fr))}
 .pkgrid{grid-template-columns:repeat(2,minmax(0,1fr))}.pk.big{grid-column:1/-1;grid-row:auto}.pk.big .pic{flex:none;min-height:0;aspect-ratio:16/9}
 .pkgrid.row{grid-template-columns:repeat(2,minmax(0,1fr))}}
/* ---------- スマホ ---------- */
@media (max-width:760px){
 .page{padding:16px 14px 32px}.issue,.front{gap:30px}
 .mast{gap:12px}.mast .mtitle{width:100%}.mast .stamp{display:none}
 .mast h1{font-size:clamp(22px,7.2vw,30px);padding:8px 14px 6px;box-shadow:4px 4px 0 var(--ink)}
 .mast .tools{width:100%;gap:6px}.mast .meta{padding:3px 10px}.mast .meta b{font-size:18px}
 .mastwish{padding:6px 10px;font-size:12px;gap:5px;box-shadow:3px 3px 0 var(--ink)}.mastwish small{display:none}.mastset{padding:6px 10px;font-size:12px}
 .poster{padding:16px 14px 14px;box-shadow:5px 5px 0 var(--ink)}
 .top{grid-template-columns:minmax(0,1fr);grid-template-rows:auto;gap:18px}
 .pdate b{font-size:84px}.pdate span{font-size:28px;padding:6px 10px 4px}
 .frame{grid-column:1;grid-row:auto;margin:4px 6px 6px 0;padding:6px;transform:rotate(-1.5deg)}
 .burst{width:72px;height:72px;font-size:16px;top:-16px;left:-14px}
 .top h2{font-size:20px;transform:rotate(-1deg)}
  .wall{grid-template-columns:minmax(0,1fr);gap:16px}.wc.lead{grid-column:auto;grid-row:auto}.wc.lead .pic{min-height:0;aspect-ratio:16/10}
 .wc:not(.lead){display:grid;grid-template-columns:120px minmax(0,1fr);grid-template-rows:auto 1fr;gap:4px 12px;align-items:start}
 .wc:not(.lead) .pic{grid-row:1/3}.wc:not(.lead) .tg{left:-6px;top:6px;font-size:11px}
  .fside{display:none}  /* スマホは右の列を出さない（欲しい物は報頭のボタン、予定は各版面で） */
 .shelves{gap:28px 0}.shelf{flex:none;width:100%}
 .tapes{grid-template-columns:minmax(0,1fr);gap:10px;padding:0 4px 0 0}
 .tape{grid-template-columns:18px 110px minmax(0,1fr);align-items:start}.tape .spine{grid-row:auto;align-self:stretch}
 .tape .pic{margin:6px 0 6px 6px}.tape .lbl{padding:7px 10px 9px}
 .tape:nth-child(n+4){display:none}  /* スマホは各ジャンル 3 作品まで（ほかは下の各版面で） */
 .picks{padding:18px 14px 22px;box-shadow:5px 5px 0 var(--rose)}.pknav{margin-left:0;width:100%}
 .pkgrid,.pkgrid.row{grid-template-columns:minmax(0,1fr);gap:28px}.pk.big .pic{flex:none;min-height:0;aspect-ratio:16/10}
 .pk.big .pkt{margin:-26px 10px 0;padding:18px 16px 14px}.pk.big .why{font-size:20px}.pk.big b{font-size:17px}.pk.big .vote{margin:10px 10px 0}
 .sec{box-shadow:5px 5px 0 var(--ink)}.band{padding:16px 14px 2px}.band .title{font-size:22px;padding:6px 14px}.band .cnt{margin-left:0}.band .deco{display:none}
 .grid{padding:16px 14px 18px;gap:14px}.facts{padding:14px 14px 0}.brief{padding:12px 14px 16px}.older summary{padding:12px 14px}
 .c12,.c8,.c6,.c4,.c3{grid-column:span 12}.card.wide{grid-template-columns:1fr}
 .card.c8 h3,.card.wide h3{font-size:21px}
 .grid>.hero .pic,.grid>.lead .pic{height:200px}.grid>.lead h2{font-size:22px}
 .hero{grid-template-columns:1fr}.hero h2,.lead h2{font-size:22px}
 .lead,.side,.s12,.s6,.s4{grid-column:span 12}
 .card.mini{grid-template-columns:110px minmax(0,1fr)}
 .calm{flex-wrap:wrap;gap:12px;padding:4px 14px 16px}.calm .pic{display:none}
 .calm .last{flex:1 1 100%;border-left:0;padding-left:0}
}
/* いちばん小さいスマホ（320px）：報頭が横にはみ出さないように詰める */
@media (max-width:380px){.mast h1{font-size:21px;padding:7px 10px 5px;letter-spacing:0}.mastwish,.mastset{padding:6px 8px}.mast .meta small{display:none}}
@media (prefers-reduced-motion:reduce){.wc,.tape,.frame,.vote button,.mastwish{transition:none}}
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
.nav .pill .no{font:700 10px var(--font-mono);font-style:normal;font-variant-numeric:tabular-nums}
.nav .pill:focus-visible,.nav select:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.nav select{font:700 12px var(--font-mono);padding:6px 8px;border-radius:0}
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
  background:var(--ink)!important;color:var(--card)!important;border:none!important;box-shadow:none!important}
 .nav .here,.nav .grp{display:none!important}
 .nav .rail{flex:1;flex-direction:row;overflow-x:auto;gap:6px;padding:6px 4px!important;border:none!important}
 .nav .pill{flex:none;padding:7px 12px!important;margin:0!important;font:700 13px/1.3 var(--font-sans)!important;
  color:var(--card)!important;background:none!important;border:1px solid rgba(251,248,241,.3)!important;transform:none!important;width:auto!important}
 .nav .pill::before,.nav .pill::after,.nav .pill .no,.nav .pill .cnt{display:none!important}
 .nav .pill.on{background:var(--sc)!important;border-color:var(--sc)!important;transform:scale(1.12)!important;margin:0 4px!important}
 .nav select{background:transparent;color:var(--card);border:1px solid rgba(251,248,241,.3)}
 .nav .bar{display:block;position:absolute;left:0;bottom:0;height:3px;background:var(--cur,var(--alert));width:calc(var(--prog,0) * 100%)}
 [data-k]{scroll-margin-top:64px}
}
/* ---------- 愿望清单 ---------- */
.wish{--bg:var(--sheet);--fg:var(--ink);--acc:var(--rose);--abg:var(--ink);--afg:var(--sheet);--aacc:#F2A7C3;--ac:var(--rose);
 --line:color-mix(in srgb,var(--ink) 18%,var(--sheet));background:var(--bg);color:var(--fg);border:1px solid var(--line)}
.wish .band{background:linear-gradient(162deg,var(--ink) 0 42%,var(--bg) 42% 100%)}
.wish .band .title{font-family:var(--font-sans);font-weight:900;font-size:40px;color:var(--sheet);letter-spacing:.08em}
.wish .band .sub{color:var(--fg);font:700 13px var(--font-mono);letter-spacing:.25em}
.wgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
.wcard{position:relative;display:flex;flex-direction:column;background:var(--bg);box-shadow:0 0 0 .5px var(--line)}
.wcard.solo{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr)}
.wcard .wimg{position:relative;aspect-ratio:1/1;max-width:100%;background:#FFF;display:grid;place-items:center;overflow:hidden}
.wcard.solo .wimg{aspect-ratio:auto;min-height:380px}
.wcard .wimg img{position:absolute;inset:7%;width:86%;height:86%;object-fit:contain;transition:transform .4s cubic-bezier(.2,.9,.3,1)}
.wcard:hover .wimg img{transform:scale(1.04) rotate(-1.5deg)}
.wcard .heart{position:absolute;top:14px;left:14px;padding:4px 10px;background:var(--acc);color:#FFF;
 font:900 12px var(--font-sans);letter-spacing:.25em}
.wcard .heart.got{background:#1F9D6B}.wcard .heart.miss{background:#8C8678}.wcard .heart.torn{background:#B5650D}
.wcard .wtxt{display:flex;flex-direction:column;gap:14px;padding:24px 26px;min-width:0}
.wcard.solo .wtxt{justify-content:center;padding:36px 40px;border-left:1px solid var(--line)}
.wcard .shop{font:700 11px var(--font-mono);letter-spacing:.2em;color:var(--acc)}
.wcard h3{margin:0;font:900 26px/1.3 var(--font-sans);text-wrap:pretty}
.wcard.solo h3{font-size:36px}
.wcard .price{font:900 30px/1 var(--font-sans);letter-spacing:.01em;font-variant-numeric:tabular-nums}
.wcard .price small{font:700 14px var(--font-mono);margin-right:6px;opacity:.7}
.wcard dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 16px;font-size:14px}
.wcard dt{font:700 11px var(--font-mono);letter-spacing:.15em;opacity:.6;padding-top:2px}
.wcard dd{margin:0}
.wcard .note{margin:0;font-size:15px;line-height:1.7;opacity:.85}
.wcard .links{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font:700 12px var(--font-mono);letter-spacing:.08em}
.wcard .links a{border-bottom:2px solid var(--acc);padding-bottom:1px}
.wcard .links a:hover{color:var(--acc)}
.wcard .watch{display:flex;flex-direction:column;gap:4px;padding:12px 14px;background:color-mix(in srgb,var(--acc) 8%,transparent);border-left:3px solid var(--acc);font-size:14px;line-height:1.55}
.wcard .watch span{font:700 10px var(--font-mono);letter-spacing:.2em;color:var(--acc)}
.wcard .added{font:700 11px var(--font-mono);opacity:.5;letter-spacing:.1em}
@media (max-width:760px){.wcard.solo{grid-template-columns:1fr}.wcard.solo .wimg{min-height:0;aspect-ratio:1/1}
 .wcard.solo .wtxt{border-left:0;padding:22px}.wcard.solo h3{font-size:28px}.wish .band .title{font-size:30px}}
"""


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


def _safe_url(u):
    u = str(u or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def _md(d):
    """2026-11-19 → 11.19（年が今年と違うときは 2027.11.19）。"""
    d = str(d or "")
    return d[5:].replace("-", ".") if len(d) >= 10 else d


def _extras(story):
    """記事に付けられる追加情報（EDITING.md の「追加フィールド」）。ない記事には何も出さない。
    price: {"now": "¥3,980", "was": "¥4,980", "off": "-20%", "until": "2026-10-20"}  価格・セール
    event: {"date": "2026-11-19", "label": "発売日", "time": "10:00", "place": "全国"}  日程・イベント
    video: "https://…"（予告編など：画像に ▶ を付ける） / gallery: ["https://…", …]（最大 4 枚の小さい写真）"""
    out = ""
    pr = story.get("price") if isinstance(story.get("price"), dict) else None
    if pr and pr.get("now"):
        out += (f'<div class="xprice"><b>{e(pr["now"])}</b>'
                + (f'<s>{e(pr["was"])}</s>' if pr.get("was") else "")
                + (f'<i>{e(pr["off"])}</i>' if pr.get("off") else "")
                + (f'<span>{e(_md(pr["until"]))} まで</span>' if pr.get("until") else "") + "</div>")
    ev = story.get("event") if isinstance(story.get("event"), dict) else None
    if ev and ev.get("date"):
        meta = " · ".join(e(str(ev[k])) for k in ("label", "time", "place") if ev.get(k))
        out += f'<div class="xevent"><b>{e(_md(ev["date"]))}</b>{f"<span>{meta}</span>" if meta else ""}</div>'
    gal = [u for u in (story.get("gallery") or [])[:4] if _safe_url(u)] if isinstance(story.get("gallery"), list) else []
    if gal:
        out += '<div class="xgal">' + "".join(
            f'<img src="{e(u)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' for u in gal) + "</div>"
    return out


def _play(story):
    """動画のある記事：画像の上に ▶ を重ねる（リンク先は記事のまま）。"""
    return '<span class="xplay" aria-label="動画あり">▶</span>' if _safe_url(story.get("video")) else ""


def _tcard(story, span, i, today, small=False, mini=False):
    side = "a" if small else "m"  # 不再黑白交替：一周内统一主色底，折叠区统一副色底
    w = story.get("weight", "normal")
    url = e(story["url"])
    if mini:  # 普通消息：左边小图、右边日期和标题
        return (f'<a class="card {side} mini c{span}" href="{url}" target="_blank" rel="noopener">{_pic(story)}{_play(story)}'
                f'{_when(story, today)}<h3>{_headline(story)}</h3>{_extras(story)}</a>')
    if span == 12 and w == "hero":
        return (f'<a class="card {side} hero" href="{url}" target="_blank" rel="noopener">{_pic(story)}{_play(story)}'
                f'<div class="txt">{_when(story, today)}<span class="tag">重 大</span><h2>{_headline(story)}</h2>'
                + (f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") else "") + _extras(story) + "</div></a>")
    blurb = f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") and not small and w != "normal" else ""
    if span == 12 and not small:
        return (f'<a class="card {side} wide c12" href="{url}" target="_blank" rel="noopener">{_pic(story)}{_play(story)}'
                f'<div class="txt">{_when(story, today)}<h3>{_headline(story)}</h3>{blurb}{_extras(story)}</div></a>')
    level = "h2" if w == "lead" and span >= 8 and not small else "h3"
    cls = f"c{span}" + (" lead" if level == "h2" else "")
    return (f'<a class="card {side} {cls}" href="{url}" target="_blank" rel="noopener">{_pic(story)}{_play(story)}'
            f'{_when(story, today)}<{level}>{_headline(story)}</{level}>{blurb}{_extras(story)}</a>')


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
    return f'<div class="brief"><h4>その他のニュース</h4><ul>{rows}</ul></div>'


def _older(stories, today, more=0, texts=()):
    """折叠区：一周内放不下的（more 条）+ 一周以前的；没图的一周前消息列在最后。"""
    if not stories and not texts:
        return ""
    if not stories:
        return (f'<details class="older"><summary>過去のニュース · {len(texts)} 件<span></span></summary>'
                f'{_brief(texts)}</details>')
    packed = _pack(stories, lambda s: 3)
    first, last = stories[-1].get("date") or stories[-1]["_issue"], stories[0].get("date") or stories[0]["_issue"]
    rng = f"{first[5:].replace('-', '.')} – {last[5:].replace('-', '.')}"
    cards = "".join(_tcard(s, w, i, today, small=True) for i, (s, w) in enumerate(packed))
    label = "もっと見る" if more else "過去のニュース"
    detail = f"今週ほかに {more} 件" + (f" · それ以前 {len(stories) - more} 件" if len(stories) > more else "") if more else rng
    return (f'<details class="older"><summary>{label} · {len(stories) + len(texts)} 件<span>{detail}</span></summary>'
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
                f'<span class="mono">直近 · {e(last["date"].replace("-", "."))}</span><b>{e(last["headline"])}</b></a>')
    tag = "収 集 中" if block.get("collecting") else "新 着 な し"
    return (f'<div class="calm">{pic}<div class="txt"><span class="tag">{tag}</span>{status}</div>'
            f"{tail}</div>")


def _legible(t):
    """版面配色的文字和强调色在各自底色上至少 4.5:1（封面取色已经保证；items.yaml 手写的 theme 可能没有）。"""
    t = dict(t)
    ok = lambda a, b: theme.contrast(theme._rgb(t[a]), theme._rgb(t[b])) >= 4.5
    for fg, bg in (("fg", "bg"), ("alt_fg", "alt_bg"), ("accent", "bg"), ("alt_accent", "alt_bg")):
        try:
            if not ok(fg, bg):
                t[fg] = theme._hex(theme._readable(theme._rgb(t[fg]), theme._rgb(t[bg])))
            if not ok(fg, bg) and fg.endswith("fg"):
                # 白字已经不能再亮（漫威的红底白字）：把底色压暗一点，品牌色基本不变
                t[bg] = theme._hex(theme._readable(theme._rgb(t[bg]), theme._rgb(t[fg])))
        except (KeyError, ValueError, TypeError):
            pass
    return t


def _section(block, anchor=""):
    t = _legible(block["theme"])
    style = (f"--bg:{t['bg']};--fg:{t['fg']};--acc:{t['accent']};--abg:{t['alt_bg']};"
             f"--afg:{t['alt_fg']};--aacc:{t['alt_accent']};--aac:{t['alt_accent']};"
             f"--line:color-mix(in srgb,{t['fg']} 22%,{t['bg']})")
    sub = f'<span class="sub">{e(block["subtitle"])}</span>' if block.get("subtitle") else ""
    motif = block.get("_motif") if block.get("_motif") in MOTIFS else ""
    # 状态只在有变化时上版面，没变化就是不必要的信息
    changed = [f for f in block.get("facts") or [] if f["changed"]]
    facts = ""
    if changed:
        facts = '<div class="facts">' + "".join(
            f'<div class="fact"><span class="label{" new" if f["changed"] else ""}">'
            f'{e(f["label"])}{" · 変更あり" if f["changed"] else ""}</span><span>{_md_links(f["text"])}</span></div>'
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
    cnt = f'<span class="cnt"><b>{len(recent)}</b>今週</span>' if recent else ""
    return (f'<section id="{anchor}" data-k="{e(block["name"])}" class="sec{" m-" + motif if motif else ""}{quiet}" style="{style}">'
            f'<div class="band">{MOTIFS.get(motif, "")}<span class="title">{e(block["name"])}</span>{sub}{cnt}</div>'
            f"{facts}{grid}</section>")


# 作品ごとの装飾（items.yaml の motif）。名前 → 版面の見出しに添える飾り（なければ空）。見た目は CSS の .m-名前。
# 色は作品の色（--bg/--acc…）だけを使う。新しい装飾を足すときはここと CSS と EDITING.md に書く
MOTIFS = {
    "retro": '<i class="deco" aria-hidden="true">✦</i><i class="deco d2" aria-hidden="true">✦</i>',  # 平成アニメ：星・角丸の題字・ドット
    "manga": '<i class="deco" aria-hidden="true">ドドド</i>',  # 漫画：網点・斜めのコマ・擬音
    "pop": '<i class="deco" aria-hidden="true">♥</i>',  # ポップ：水玉・丸い題字・角丸の写真
    "film": "",  # 映画・ドラマ：フィルムの穴・太い黒枠
    "street": "",  # ストリート：斜めの題字・警告色のしま・切り欠きの写真
}


def _why_verb(x):
    if x.get("kind") == "follow":
        return "をフォローしている"
    return "で迷っている" if x.get("kind") == "hesitate" or x.get("hesitating") else "が欲しい"


def _why(x):
    """推荐理由：wish 是命中了愿望清单里那件东西的喜好；board 是关注的版面里没上版面的其他消息；
    follow 是同类新发现。和赞过的某条有关时补一句「你赞过「那条」」。"""
    if x.get("kind") == "board":
        why = f'フォロー中の「{e(x["because"])}」のほかのニュース'
    else:
        why = f'{"気分転換 · " if x.get("explore") else ""}「{e(x["because"])}」{_why_verb(x)}から'
    if x.get("liked"):
        t = x["liked"] if len(x["liked"]) <= 24 else x["liked"][:23] + "…"
        why += f' · 👍した「{e(t)}」と関連'
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
        main, sep, liked = _why(x).partition(" · 👍した")  # 理由は手書きの POP：本文に蛍光ペン、👍 との関連は小さく
        why_html = f"<mark>{main}</mark>" + (f"<small>👍した{liked}</small>" if sep else "")
        date = e(x["date"][5:].replace("-", ".")) if x.get("date") else ""
        taste = " · ".join(f"{e(k.removeprefix(WORK_KEY))} {v:+d}" for k, v in (x.get("taste") or [])[:3])
        taste = f'<span class="taste">あなたの投票：{taste}</span>' if taste else ""
        vote = ""
        if feedback:  # 投票要写进的数据：网页把它原样发给数据库
            data = {k: x.get(k) for k in ("url", "kind", "title", "work", "because", "hits", "words")}
            vote = (f'<div class="vote" data-v="{e(json.dumps(data, ensure_ascii=False))}">'
                    f'<button type="button" data-vote="1" aria-pressed="false" title="この種類を増やす">👍<span> 好き</span></button>'
                    f'<button type="button" data-vote="-1" aria-pressed="false" title="この種類を減らす">👎<span> 興味なし</span></button>'
                    + f'<small></small></div>')
        return (
            f'<div class="pk{" big" if big else ""}" data-u="{e(x["url"])}" data-s="{x.get("score") or 4}" '
            f'data-w="{e(x["work"])}" data-key="{e("|".join(x.get("words") or []))}"{" data-f=1" if follow else ""}{" data-new=1" if x.get("explore") else ""}>'
            f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{_pic(story)}'
            f'<span class="pkt"><span class="src">{e(x["source"])}{" · " + date if date else ""}</span>'
            f'<b>{e(x["title"])}</b>'
            f'<span class="why">{why_html}</span>'
            f'<span class="tags">{tags}</span>{taste}</span></a>{vote}</div>')

    def batch_of(group):
        wish = [x for x in group if x.get("kind") not in ("follow", "hesitate")]
        follow = [x for x in group if x.get("kind") in ("follow", "hesitate")]
        body = f'<div class="pkgrid">{cards_of(wish, True)}</div>' if wish else ""
        if follow:
            body += (f'<div class="pksub">似たジャンルの新着<span>フォロー中の作品や迷っているもの以外の、同じジャンルのニュース</span></div>'
                     f'<div class="pkgrid row" style="--n:{len(follow)}">{cards_of(follow, False)}</div>')
        return body

    # 网页里放下整个候选池：第一批（没有脚本时也能看）+ 其余放进隐藏的池子；
    # 脚本每次打开随机抽一批（分数高的、没看过的更容易抽到），「换一批」再抽
    first = [x for x in picks if not x.get("batch")]
    rest = [x for x in picks if x.get("batch")]
    body = f'<div class="pkbatch">{batch_of(first)}</div>'
    if rest:
        body += f'<div class="pkpool" hidden>{cards_of(rest, False)}</div>'
    shuffle = (f'<div class="pknav"><button type="button" class="shuffle back" aria-label="前のおすすめに戻る" disabled>◀◀ 前へ</button>'
               f'<button type="button" class="shuffle next" aria-label="ほかのおすすめを見る">▶▶ 入れ替え<small>全 {len(picks)} 件</small></button></div>'
               if rest else "")
    return (f'<section class="picks" id="picks" data-k="picks"><div class="pkhead"><h2>気になるかも<em>？</em></h2><span class="flag">店長のおすすめ</span>'
            f'<span>欲しい物リスト・フォロー中の版面・👍したニュースから選びました{"。👍 / 👎 で好みを教えてください" if feedback else ""}'
            f' · <a href="wishlist.html">♥ 欲しい物リスト</a></span>{shuffle}</div>'
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
    next.querySelector('small').textContent = fresh ? `未読 ${fresh} 件` : '全部見ました。古い順にもう一度';
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
    if (tip) tip.textContent = v === 1 ? 'この種類を増やします' : v === -1 ? 'この種類を減らします' : '';
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
        if (tip) tip.textContent = '保存できませんでした。後でもう一度';
        btn.title = '保存できませんでした。後でもう一度';
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
    s.innerHTML = '<button type="button" data-vote="1" aria-pressed="false" title="好き：この種類を増やす">👍</button>'
      + '<button type="button" data-vote="-1" aria-pressed="false" title="興味なし：この種類を減らす">👎</button>';
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
  document.querySelectorAll('.sec a.card, a.top, a.wc').forEach(a => story(a, a, a));
  document.querySelectorAll('.sec .brief li').forEach(li => { const a = li.querySelector('a'); if (a) story(a, li, li); });
  new Set(boxes.map(b => b[1].url)).forEach(paint);
})();
"""


def _wish_link(wishes, cls):
    """主页面上去愿望清单子页面的入口（报头右上角、左侧目录底部）。"""
    if not wishes:
        return ""
    want = sum(1 for x in wishes if (x.get("status") or "想要") == "想要")
    return (f'<a class="{cls}" href="wishlist.html"><b>♥</b><span>{"欲しい物" if cls == "navwish" else "欲しい物リスト"}</span>'
            f'<small>欲しい {want} 件</small></a>')


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
        rows.append(f'<h2 style="--sc:{_sec_color(name)}">{e(name)}<small>{_sec_en(name)}</small></h2>')
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
<header class="mast">
<div class="mtitle"><h1>愿望清单</h1></div>
<div class="tools"><div class="meta"><small>更新于</small><b>{e(updated)}</b></div></div>
</header>
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
# 板块色：白字、浅底（#EDEBE6）上的小字都要过 WCAG AA 4.5:1（绿、粉、橙原来太浅，白字只有 2.9–4.4）
SECTIONS = {"游戏": "#2F5BD3", "影视": "#9B3FB5", "运动": "#156A48", "演出": "#BB265A", "好物": "#985315"}
SECTION_EN = {"游戏": "GAMES", "影视": "SCREEN", "运动": "SPORTS", "演出": "LIVE", "好物": "GOODS"}
# 网页上显示的板块名（数据里的板块名照旧是中文，items.yaml / 设置页不变）
SECTION_JA = {"游戏": "ゲーム", "影视": "映像", "运动": "スポーツ", "演出": "ライブ", "好物": "グッズ", "其他": "その他"}


def _sec_name(name):
    """画面に出すジャンル名（日本語）。表にない新しいジャンルは書いたままの名前。"""
    return SECTION_JA.get(name or "", name or "")


def _sec_en(name):
    """英字ラベル（GAMES など）。表にない新しいジャンルは、英字の名前ならそのまま大文字、それ以外は出さない。"""
    if name in SECTION_EN:
        return SECTION_EN[name]
    return name.upper() if name and name.isascii() else ""


# 新しいジャンル（items.yaml の section に新しい名前を書いたとき）の色：名前から決まる（毎回同じ色）。
# どれも白字・薄い背景の小さい文字で 4.5:1 以上（tests/test_design.py で確認）
GENRE_EXTRA = ("#3D5A80", "#7A4E2D", "#4A6B2F", "#8A3B52", "#5B4B8A", "#2F6F73", "#8C4A1F", "#6B5B2E")


def _sec_color(name):
    if name in SECTIONS:
        return SECTIONS[name]
    if not name or name == "其他":
        return "#5B5F6B"
    return GENRE_EXTRA[int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(GENRE_EXTRA)]


def _recent(w, today):
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HOLD_DAYS - 1)).isoformat()
    return [x for x in w["stories"] if x["_issue"] >= cutoff]


WEEKDAY = ("月", "火", "水", "木", "金", "土", "日")
WEEKDAY_EN = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
SPOT_COUNT = 6  # 「ほかの注目ニュース」の写真の壁：大きい 1 枚 + 小さい 5 枚（3 列 3 段がちょうど埋まる）


def _day(story):
    return (story.get("date") or story["_issue"])[5:].replace("-", ".")


def _poster_colors(story, themes):
    """トップのポスターの色：その日のトップ記事の写真から、作品の版面と同じ方法（theme.from_image）で取る。
    themes は state/themes.json のキャッシュ（「hero|画像URL」で 1 回だけ取色）。取れないときは紙色の既定。"""
    url = story.get("image") if story else None
    t = None
    if url and themes is not None:
        key = f"hero|{url}"
        if key not in themes:
            themes[key] = theme.from_image(url)
        t = themes.get(key)
    if not t:
        return ""
    dark = theme._lum(theme._rgb(t["bg"])) < 0.35
    tint, deep = (t["alt_bg"], t["bg"]) if dark else (t["bg"], t["alt_bg"])
    acc = t["alt_accent"] if dark else t["accent"]
    # 大きい日付（deep）と見出し（墨の箱）が淡い地色の上で読めること
    if theme.contrast(theme._rgb(deep), theme._rgb(tint)) < 4.5:
        deep = theme._hex(theme._readable(theme._rgb(deep), theme._rgb(tint)))
    return f"--tint:{tint};--deep:{deep};--hacc:{acc}"


def _side(works, today, wishes=(), taste=()):
    """トップの右の列（PC だけ。スマホでは消す）。上から：
    これからの予定（日付のある記事があるときだけ）・欲しい物リスト・今週にぎやかな作品・投票から学んだあなたの好み。
    どれもデータがなければ出さない。"""
    out = []
    ag = _agenda(works, today, 4)
    if ag:
        out.append(ag)
    want = [x for x in wishes if (x.get("status") or "想要") in ("想要", "纠结")]
    if want:
        rows = []
        for x in want[:4]:
            img = x.get("image") or ""
            if img and not img.startswith("http"):
                img = "wishlist/" + img
            price = (f'{e(str(x.get("currency", "")))} {x["price"]:,.0f}' if isinstance(x.get("price"), (int, float))
                     else e(str(x.get("price") or "")))
            torn = (x.get("status") == "纠结")
            pic = (f'<img src="{e(img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
                   if _safe_url(img) or img.startswith("wishlist/") else "")
            rows.append(f'<li><span class="wthumb">{pic}</span>'
                        f'<span class="wt"><b>{e(x["name"])}</b><em>{price}</em></span>'
                        f'<i class="tg" style="--sc:{"#985315" if torn else "var(--rose)"}"><span>{"迷い中" if torn else "欲しい"}</span></i></li>')
        total = _total(wishes, "想要")
        out.append(f'<div class="sbox swish"><h4><a href="wishlist.html">欲しい物リスト</a><small>{len(want)} 件</small></h4><ol>{"".join(rows)}</ol>'
                   f'<p class="stot"><span>欲しいものの合計</span><b>{e(total)}</b></p>'
                   f'<a class="smore" href="wishlist.html">♥ 全部見る</a></div>')
    counts = sorted(((len(_recent(w, today)), w) for w in works if _recent(w, today)), key=lambda c: -c[0])[:6]
    if counts:
        top = counts[0][0]
        bars = "".join(f'<li style="--sc:{_sec_color(w.get("section"))};--v:{n / top:.3f}"><a href="#{_wid(w["name"])}">'
                       f'<span class="bn">{e(w["name"])}</span><span class="bar"></span><b>{n}</b></a></li>' for n, w in counts)
        out.append(f'<div class="sbox shot"><h4>今週にぎやかな作品<small>記事の数</small></h4><ol>{bars}</ol></div>')
    if taste:
        chips = "".join(f'<li><span>{e(k.removeprefix(WORK_KEY))}</span><b>+{v}</b></li>' for k, v in taste[:8])
        out.append(f'<div class="sbox staste"><h4>あなたの好み<small>👍 から学習</small></h4><ul>{chips}</ul>'
                   f'<p>「気になるかも？」はこの順に選んでいます</p></div>')
    return f'<aside class="fside">{"".join(out)}</aside>' if out else ""


def _front(works, today, updated, themes=None, wishes=(), taste=()):
    """トップ：直近一週間の総覧。
    - ポスター：直近一週間でいちばん重要な 1 本（同じ重要度なら新しいほう）。地色はその記事の写真から
    - ほかの注目ニュース：次に重要な写真つきの記事（SPOT_COUNT 本）の写真の壁（文字だけの一覧は出さない）
    - ジャンルの棚：作品ごとに最新の 1 本（ポスターと壁に出たものはなるべく避ける）。押すとその作品の版面へ"""
    pool = [(w, x) for w in works for x in _recent(w, today)]
    newest = sorted(pool, key=lambda p: p[1].get("date") or p[1]["_issue"], reverse=True)
    pictured = [p for p in newest if _has_photo(p[1])]  # ポスターと壁は本物の写真があるものだけ（来源アイコンは数えない）
    top_w, top = min(pictured, key=lambda p: RANK.get(p[1].get("weight"), 2)) if pictured else (None, None)
    ranked = sorted(pictured, key=lambda p: RANK.get(p[1].get("weight"), 2))
    more = [p for p in ranked if p[1] is not top][:SPOT_COUNT]

    d = dt.date.fromisoformat(today)
    head = (f'<div class="phead"><span class="lab">トップ</span><span>直近 {HOLD_DAYS} 日 · {len(pool)} 件</span>'
            f'<span class="day">{d.year}.{d.month:02d}.{d.day:02d}（{WEEKDAY[d.weekday()]}）</span></div>')
    foot = (f'<div class="pfoot"><span class="cbar" aria-hidden="true"></span>'
            f'<span>ウォッチリスト通信 · {e(updated)} 更新 · 2 時間ごとに刷り直します</span></div>')
    date_html = (f'<div class="pdate"><b>{d.month:02d}.{d.day:02d}</b>'
                 f'<span>{WEEKDAY_EN[d.weekday()]}<small>{WEEKDAY[d.weekday()]}曜日</small></span></div>')
    if top:
        sc = _sec_color(top_w.get("section"))
        badge = "重大" if top.get("weight") == "hero" else "注目"
        top_html = (f'<a class="top" href="{e(top["url"])}" target="_blank" rel="noopener" data-k="{e(top_w["name"])}">'
                    f'{date_html}<div class="frame"><span class="burst">{badge}</span>{_pic(top)}{_play(top)}</div>'
                    f'<div class="ptxt"><span class="kick"><i class="tg" style="--sc:{sc}"><span>{e(_sec_name(top_w.get("section")))}</span></i>'
                    f'<i class="tg"><span>{e(top_w["name"])}</span></i><em>{e(_day(top))}</em></span>'
                    f'<h2><span class="hb">{_headline(top)}</span></h2>'
                    + (f'<p>{e(top["blurb"])}</p>' if top.get("blurb") else "") + _extras(top) + "</div></a>")
        style = f' style="{_poster_colors(top, themes)}"'
    else:
        top_html = f'<div class="top">{date_html}<div class="ptxt"><h2><span class="hb">直近 {HOLD_DAYS} 日は新着なし</span></h2></div></div>'
        style = ""
    poster = f'<div class="poster"{style}><div class="marks" aria-hidden="true"></div>{head}{top_html}{foot}</div>'

    wall = "".join(
        f'<a class="wc{" lead" if i == 0 else ""}" href="{e(x["url"])}" target="_blank" rel="noopener" '
        f'data-k="{e(w["name"])}" style="--sc:{_sec_color(w.get("section"))}">'
        f'<i class="tg"><span>{e(w["name"])}</span></i>{_pic(x)}{_play(x)}<em>{e(_day(x))}</em><b>{_headline(x)}</b></a>'
        for i, (w, x) in enumerate(more))
    shown = {id(top)} | {id(x) for _, x in more}
    groups = {}
    for w in works:
        groups.setdefault(w.get("section") or "其他", []).append(w)
    order = [n for n in SECTIONS] + [n for n in groups if n not in SECTIONS]
    shelves = []
    for name in order:
        tapes = []
        for w in groups.get(name, []):
            rec = _recent(w, today)
            if rec:
                first = next((x for x in rec if id(x) not in shown), rec[0])
                text, cls = first["headline"], "tape"
                # この作品を代表する小さい写真：最近の記事の写真、作品の表紙の順。開けなければ次、全部だめなら来源アイコン
                imgs = [u for u in dict.fromkeys([first.get("image")] + [x.get("image") for x in rec][:3] + [w.get("_thumb")]) if u]
                pic = {"image": imgs[0] if imgs else None, "_fbs": imgs[1:], "_work": w["name"],
                       **{k: first.get(k) for k in ("url", "source", "source_icon")}}
            else:
                text, cls = w.get("status") or "新着なし", "tape q"
                pic = {"image": w.get("_thumb"), "_work": w["name"], "_fbs": []}
            tapes.append(f'<a class="{cls}" href="#{_wid(w["name"])}"><span class="spine" aria-hidden="true">{e(_sec_name(name))}</span>'
                         f'{_pic(pic)}<span class="lbl"><i>{e(w["name"])}</i><b>{e(text)}</b></span></a>')
        if not tapes:
            continue
        en = _sec_en(name)
        shelves.append(f'<div class="shelf" style="--sc:{_sec_color(name)};--n:{len(tapes)}">'
                       f'<h3 class="sign">{e(_sec_name(name))}<small>{en + " · " if en else ""}{len(tapes)} 作品</small></h3>'
                       f'<div class="tapes">{"".join(tapes)}</div><div class="plank"></div></div>')
    side = _side(works, today, wishes, taste)
    spot = ""
    if more or shelves:
        spot = (f'<div class="spot"><h2 class="sh"><span>ほかの注目ニュース</span><small>直近 {HOLD_DAYS} 日から · 下の棚は作品ごとの最新 1 本</small></h2>'
                + (f'<div class="mgrid"><div class="wall">{wall}</div>{side}</div>' if more else "")
                + (f'<div class="shelves">{"".join(shelves)}</div>' if shelves else "") + "</div>")
    return f'<section class="front" data-k="front" id="front">{poster}{spot}</section>'


AGENDA_MAX = 8


def _left(d, today):
    """あと何日（当日は「今日」）。"""
    n = (dt.date.fromisoformat(d[:10]) - dt.date.fromisoformat(today)).days
    return "今日" if n == 0 else f"あと {n} 日"


def _agenda(works, today, limit=None):
    """これからの予定：記事に event（日程）があるものを、今日以降・日付順に最大 AGENDA_MAX 件。
    同じ日・同じ見出しは 1 回だけ。予定が 1 件もなければ何も出さない。"""
    rows, seen = [], set()
    for w in works:
        for x in w["stories"]:
            ev = x.get("event") if isinstance(x.get("event"), dict) else None
            d = str((ev or {}).get("date") or "")
            if len(d) < 10 or d[:10] < today or (d[:10], x["headline"]) in seen:
                continue
            seen.add((d[:10], x["headline"]))
            rows.append((d[:10], w, x, ev))
    if not rows:
        return ""
    rows.sort(key=lambda r: r[0])
    items = "".join(
        f'<li style="--sc:{_sec_color(w.get("section"))}"><b>{e(_md(d))}<small>{_left(d, today)}</small></b>'
        f'<span class="nm">{e(w["name"])}{" · " + e(ev["label"]) if ev.get("label") else ""}</span>'
        f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["headline"])}</a></li>'
        for d, w, x, ev in rows[:limit or AGENDA_MAX])
    return f'<div class="agenda"><h4>これからの予定<small>UPCOMING</small></h4><ol>{items}</ol></div>'


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
.nav .grp b{font:900 13px var(--font-sans);letter-spacing:.3em}
.nav .grp small{font:700 10px var(--font-mono);letter-spacing:.25em;opacity:.75}
.nav .pill{padding:9px 0 9px 26px;font:700 14px/1.3 var(--font-sans);color:rgba(26,28,34,.66);
 transition:color .2s,font-size .3s cubic-bezier(.2,.9,.3,1),padding .3s cubic-bezier(.2,.9,.3,1)}
.nav .pill::before{content:"";position:absolute;left:8px;top:0;bottom:0;width:3px;
 background:linear-gradient(var(--sc) calc(var(--p,0)*100%),rgba(26,28,34,.13) 0)}
.nav .pill::after{content:"";position:absolute;left:4px;top:50%;width:11px;height:11px;margin-top:-5.5px;border-radius:50%;
 background:var(--paper);border:2px solid rgba(26,28,34,.35);
 transition:width .35s cubic-bezier(.3,1.5,.5,1),height .35s cubic-bezier(.3,1.5,.5,1),margin .35s cubic-bezier(.3,1.5,.5,1),left .35s cubic-bezier(.3,1.5,.5,1),border-color .2s}
.nav .pill .no{display:none}
.nav .pill .nm{display:flex;flex-direction:column;gap:3px}
.nav .pill .cnt{display:none;font:700 11px var(--font-mono);letter-spacing:.12em;color:var(--sc)}
.nav .pill:hover{color:var(--ink)}
.nav .pill.past{color:rgba(26,28,34,.72)}
.nav .pill.past::after{background:var(--sc);border-color:var(--sc)}
.nav .pill.on{color:var(--ink);font-size:21px;font-weight:900;letter-spacing:-.01em;padding:16px 0 16px 40px}
.nav .pill.on .cnt{display:block}
.nav .pill.on::after{width:38px;height:38px;margin-top:-19px;left:-9px;
 background:var(--img,none) center/cover no-repeat,var(--paper);border:3px solid var(--sc);
 box-shadow:0 0 0 5px color-mix(in srgb,var(--sc) 20%,transparent),0 6px 14px rgba(26,28,34,.25)}
.nav select{margin:14px 0 0 26px;align-self:flex-start;background:transparent;color:var(--ink);border:1px solid rgba(26,28,34,.35)}
""",
    # B 报纸索引栏：米色纸面、双线，条目带编号和引导点；当前条目反白成板块色色块并放大
    "index": """
.nav{background:var(--card);color:var(--ink);border:3px solid var(--ink);box-shadow:6px 6px 0 var(--ink);padding:0}
.nav .here{display:flex;flex-direction:column;gap:2px;padding:14px 16px 12px;border-bottom:3px double var(--ink);text-align:center}
.nav .here b{font:900 30px/1 var(--font-serif);letter-spacing:.4em;padding-left:.4em}
.nav .here small{font:700 10px var(--font-mono);letter-spacing:.45em;color:var(--alert)}
.nav .here span{font:700 11px var(--font-mono);letter-spacing:.1em;opacity:.7}
.nav .rail{padding:4px 0 10px}
.nav .grp{display:flex;align-items:center;gap:8px;margin:12px 12px 4px;padding:3px 8px;background:var(--sc);color:#FFF}
.nav .grp b{font:900 13px var(--font-sans);letter-spacing:.3em}
.nav .grp small{margin-left:auto;font:700 10px var(--font-mono);letter-spacing:.2em;opacity:.9}
.nav .pill{margin:0 12px;padding:7px 8px;font:700 14px/1.35 var(--font-serif);border-bottom:1px dotted rgba(26,28,34,.35);
 transition:background .2s,color .2s,font-size .2s,padding .2s}
.nav .pill .no{color:var(--sc);min-width:18px}
.nav .pill .nm{flex:1;min-width:0}
.nav .pill::after{content:"";position:absolute;left:0;bottom:-1px;height:3px;width:calc(var(--p,0)*100%);background:var(--sc)}
.nav .pill:hover .nm{text-decoration:underline;text-underline-offset:3px}
.nav .pill.past{opacity:.55}
.nav .pill.on{background:var(--sc);color:#FFF;font-size:18px;font-weight:900;padding:12px 10px;opacity:1}
.nav .pill.on .no{color:var(--gold)}
.nav .pill.on::after{background:var(--gold)}
.nav select{margin:0 12px 12px;background:var(--card);color:var(--ink);border:2px solid var(--ink)}
""",
    # C 活页夹标签：每个作品是一张贴在内容左缘的彩色索引签；当前那张向右抽出、变大
    "tabs": """
.nav{padding:0;background:none}
.page{grid-template-columns:220px minmax(0,1fr);column-gap:0}
.nav .here{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;padding:0 0 10px 4px}
.nav .here b{font:900 24px/1 var(--font-sans);letter-spacing:.2em;white-space:nowrap}
.nav .here small{font:700 10px var(--font-mono);letter-spacing:.3em;color:var(--alert)}
.nav .here span{flex-basis:100%;font:700 10px var(--font-mono);opacity:.6}
.nav .rail{gap:5px;padding:4px 0 8px;overflow-x:visible}
.nav .grp{display:flex;align-items:baseline;gap:6px;padding:10px 4px 2px;color:var(--sc)}
.nav .grp b{font:900 12px var(--font-sans);letter-spacing:.3em}
.nav .grp small{font:700 10px var(--font-mono);letter-spacing:.2em}
.nav .pill{margin-left:28px;padding:10px 12px;background:color-mix(in srgb,var(--sc) 22%,var(--card));color:var(--ink);
 border:2px solid var(--ink);border-right:none;font:900 14px/1.25 var(--font-sans);
 clip-path:polygon(10px 0,100% 0,100% 100%,10px 100%,0 calc(100% - 10px),0 10px);
 transition:margin .3s cubic-bezier(.3,1.5,.5,1),background .2s,color .2s,font-size .2s}
.nav .pill .no{color:var(--sc)}
.nav .pill::after{content:"";position:absolute;left:0;bottom:0;height:4px;width:calc(var(--p,0)*100%);background:var(--ink)}
.nav .pill:hover{margin-left:18px}
.nav .pill.past{background:color-mix(in srgb,var(--sc) 10%,var(--card));color:rgba(26,28,34,.6)}
.nav .pill.on{margin-left:0;background:var(--sc);color:#FFF;font-size:17px;padding:14px 14px}
.nav .pill.on .no{color:var(--gold)}
.nav .pill.on::after{background:var(--gold)}
.nav select{margin:6px 0 0 28px;background:var(--card);color:var(--ink);border:2px solid var(--ink)}
""",
    # D 大字滚动：没有框，只有字；当前作品放大成巨大的板块色标题，其余缩小变淡，像焦点在移动
    "type": """
.nav{padding:4px 0}
.nav .here{display:flex;flex-direction:column;gap:2px;padding-bottom:12px;border-bottom:3px solid var(--ink)}
.nav .here b{font:900 13px var(--font-mono);letter-spacing:.5em}
.nav .here small{display:none}
.nav .here span{font:700 11px var(--font-mono);opacity:.6}
.nav .rail{padding:8px 0;mask-image:linear-gradient(transparent,#000 6%,#000 94%,transparent)}
.nav .grp{display:flex;gap:6px;align-items:baseline;padding:14px 0 2px;color:var(--sc)}
.nav .grp b{font:900 11px var(--font-sans);letter-spacing:.4em}
.nav .grp small{font:700 10px var(--font-mono);letter-spacing:.2em;opacity:.8}
.nav .pill{flex-direction:column;align-items:flex-start;gap:0;padding:5px 0;color:rgba(26,28,34,.38);
 font:900 15px/1.15 var(--font-sans);letter-spacing:-.01em;transition:font-size .35s cubic-bezier(.2,.9,.3,1),color .25s,padding .35s}
.nav .pill .no{font-size:10px;color:inherit}
.nav .pill:hover{color:var(--ink)}
.nav .pill.past{color:rgba(26,28,34,.55)}
.nav .pill.on{color:var(--sc);font-size:34px;line-height:1.02;padding:10px 0 12px}
.nav .pill.on .no{color:var(--ink)}
.nav .pill.on::after{content:"";height:4px;width:calc(var(--p,0)*100%);background:var(--sc);margin-top:8px;transition:width .15s linear}
.nav select{margin-top:8px;background:transparent;color:var(--ink);border:2px solid var(--ink)}
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
            f'<i class="no">00</i><span class="nm">トップ<small class="cnt">FRONT PAGE</small></span></a>']
    if picks:
        rail.append(f'<a class="pill" style="--sc:#B8336A" data-for="picks" href="#picks">'
                    f'<i class="no">?</i><span class="nm">気になるかも？<small class="cnt">候補 {len(picks)} 件</small></span></a>')
    n = 0
    for name in order:
        sc = _sec_color(name)
        rail.append(f'<div class="grp" style="--sc:{sc}"><b>{e(_sec_name(name))}</b><small>{_sec_en(name)}</small></div>')
        for w in groups[name]:
            n += 1
            recent = [x for x in w["stories"] if x["_issue"] >= cutoff]
            img = next((x.get("image") for x in recent if x.get("image")), None) or w.get("cover") \
                or next((x.get("image") for x in w["stories"] if x.get("image")), None)
            css_img = f";--img:url({urllib.parse.quote(img, safe=':/?&=%#@+,;~')})" if img else ""
            cnt = f"今週 {len(recent)} 件" if recent else "新着なし"
            rail.append(f'<a class="pill" style="--sc:{sc}{e(css_img)}" data-for="{e(w["name"])}" '
                        f'href="#{_wid(w["name"])}"><i class="no">{n:02d}</i>'
                        f'<span class="nm">{e(w["name"])}<small class="cnt">{cnt}</small></span></a>')
    return (f'<nav class="nav" aria-label="目次">'
            f'<div class="here"><b>目次</b><small>INDEX</small><span id="nav-here"></span></div>'
            f'<div class="rail" id="nav-rail">{"".join(rail)}</div>{_wish_link(wishes, "navwish")}'
            f'<div class="bar" id="nav-bar"></div></nav>')


# 写真の収め方：縦横比が枠とだいたい同じ（±30%）なら枠いっぱいに（.fill）、違えばぼかしの上に全体を表示（既定）。
# どんな記事の写真でも同じ型に収まる。スクリプトがないときは全部「全体を表示」
FIT_JS = """
(() => {
  const fit = img => {
    const p = img.closest('.pic');
    if (!p || !img.naturalWidth || !p.clientHeight) return;
    const r = (img.naturalWidth / img.naturalHeight) / (p.clientWidth / p.clientHeight);
    p.classList.toggle('fill', Math.abs(Math.log(r)) < 0.27);
  };
  document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(img => {
    img.addEventListener('load', () => fit(img));
    if (img.complete) fit(img);
  });
  let t;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(fit), 200); });
})();
"""


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


def render(issues, nav_style="line", order=None, updated=None, wishes=(), picks=(), feedback=None, sizes=None,
           motifs=None, themes=None, taste=()):
    """issues：按时间倒序的各期数据（全部）。nav_style：左侧目录风格，见 NAV_STYLES。
    order：items.yaml 里作品的顺序；updated：网页更新时间（显示用）；sizes：{作品: S / M / L} 篇幅。
    motifs：{作品: 装饰名}（items.yaml 的 motif，见 MOTIFS）；themes：取色キャッシュ（トップのポスターの色を書き足す）。"""
    latest = issues[0]
    works = collect(issues, order)
    for w in works:
        w["_today"] = latest["date"]
        w["_size"] = (sizes or {}).get(w["name"], "M")
        w["_motif"] = (motifs or {}).get(w["name"], "")
    updated = updated or latest["date"].replace("-", ".")
    fb = feedback if feedback and feedback.get("url") and feedback.get("key") else None
    # id 保留 issue-日期：Discord 通知里的链接指向这里
    body = (f'<div class="issue" id="issue-{latest["date"]}" data-label="更新 {updated}">'
            + _front(works, latest["date"], updated, themes, wishes, taste) + _picks(picks, works, fb)
            + "".join(_section(w, _wid(w["name"])) for w in works) + "</div>")
    parts = [body]
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ウォッチリスト通信</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}@media (min-width:1001px){{{NAV_STYLES.get(nav_style, NAV_STYLES["line"])}}}</style>
</head>
<body>
<div class="page">
<header class="mast">
<div class="mtitle"><h1>ウォッチリスト通信</h1><span class="stamp">2 時間ごとに自動更新</span></div>
<div class="tools"><div class="meta"><small>更新</small><b>{e(updated)}</b></div>
{_wish_link(wishes, "mastwish")}
<a class="mastset" href="settings.html" title="設定">⚙ 設定</a></div>
</header>
{_nav(works, latest['date'], wishes, picks)}
<main class="issues">{''.join(parts)}</main>
</div>
<script>{NAV_JS}</script>
<script>{FIT_JS}</script>
{f"<script>{VOTE_JS % json.dumps(fb)}</script>" if fb else ""}
</body>
</html>
"""
