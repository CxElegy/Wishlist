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
import math
import pathlib
import re
import urllib.parse

import yaml

import heat
import processes
import likefx
import theme
from images import FAVICON_SERVICE, GENERIC, base_domain  # 网站 logo / 默认分享图的判断，和找图用同一条规则

FONTS = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900&family=Noto+Sans+SC:wght@500;700;900"
    "&family=Noto+Sans+TC:wght@500;700;900&family=Noto+Sans+KR:wght@500;700;900&family=Noto+Serif+SC:wght@500;700;900"
    "&family=Anton&family=Yusei+Magic&family=JetBrains+Mono:wght@500;700&display=swap"
)

CSS = """
:root{--ink:#1A1C22;--paper:#EDEBE6;--rose:#B8336A;--sheet:#F4EDE4;--card:#FBF8F1;--gold:#FFD23F;--alert:#D7261E;--good:#1F7A55;--discord:#5865F2;
 --font-sans:'Noto Sans JP','Noto Sans TC','Noto Sans SC','Noto Sans KR',sans-serif;--font-serif:'Noto Serif JP','Noto Serif SC',serif;
 --font-mono:'JetBrains Mono',monospace;--font-num:'Anton',Impact,sans-serif;--font-hand:'Yusei Magic','Noto Sans JP',sans-serif;
 --fs-label:11px;--fs-tag:10px;--gap:16px;--hair:color-mix(in srgb,var(--ink) 16%,transparent);
 --shadow:4px 4px 0 var(--ink);--shadow-l:8px 8px 0 var(--ink);--tilt:-1.5deg;--skew:-8deg;
 /* 話題度の分析ページのグラフ（dataviz の検証済みパレット）：指標 6 色・点数の濃淡 5 段・前週比の上下 */
 --viz-1:#2a78d6;--viz-2:#eb6834;--viz-3:#1baf7a;--viz-4:#eda100;--viz-5:#e87ba4;--viz-6:#008300;
 --seq-0:#cde2fb;--seq-1:#9ec5f4;--seq-2:#5598e7;--seq-3:#256abf;--seq-4:#104281;--up:#e34948;--down:#2a78d6}
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
.mgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,300px);gap:28px;align-items:start}
/* 左の壁と右の列の下端をそろえる：短いほうが伸びる（壁は各段が均等に伸び、右の列は最後の箱が伸びる） */
.mgrid>.wall{align-content:start}
.mgrid .wc{justify-content:flex-start}
.fside>:last-child{flex:1}
.fside{display:flex;flex-direction:column;gap:20px;min-width:0}
.sbox{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:12px 14px 12px}
.sbox h4,.fside .agenda h4{margin:0 0 6px;display:flex;align-items:baseline;gap:10px;padding-bottom:7px;border-bottom:2px solid var(--ink);font:900 16px/1.3 var(--font-sans);letter-spacing:.04em}
.sbox h4 small{margin-left:auto;font:500 11px var(--font-sans)}
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
.shot li a{grid-template-columns:96px minmax(0,1fr) 28px 14px}
.shot .bn em{display:block;font:900 var(--fs-tag)/1.3 var(--font-sans);font-style:normal;color:var(--alert);letter-spacing:.08em}
.shot i{font:900 13px var(--font-sans);font-style:normal;text-align:center}
.shot i.up{color:var(--alert)}.shot i.flat{opacity:.45}.shot i.down{opacity:.6}
.snote{margin:6px 0 8px;font-size:12px;line-height:1.5;opacity:.75}
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
.wall{align-items:stretch}  /* 同じ段のカードは同じ高さ（写真枠 16:10・見出し 3 行分でそろえる） */
.wc.lead .pic{flex:1;aspect-ratio:auto;min-height:200px}  /* 大きい一枚は横の 2 枚と同じ高さ：写真は端を少し切って埋める */
.wc[hidden]{display:none}.wc:not(.lead) .pic{height:auto}.wc:not(.lead) .pic[style*='height']{aspect-ratio:auto}  /* WALL_JS が右の列とそろえるため写真枠を少し高くすることがある */
.wc .tg{position:absolute;left:-8px;top:18px;z-index:2;box-shadow:2px 2px 0 var(--ink)}
.wc em{font:15px/1 var(--font-num);font-style:normal;letter-spacing:.04em}
.wc b{font:700 15px/1.5 var(--font-sans);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:4.5em}  /* 3 行分：段のカードの高さがそろう */
.wc.lead b{font-size:22px;font-weight:900;line-height:1.45;-webkit-line-clamp:2;min-height:2.9em}
.wc:hover b{text-decoration:underline;text-underline-offset:3px}
/* ジャンルの棚：ジャンルごとに看板、作品ごとに最新の 1 本をテープのように並べる（版面へのリンク） */
.shelves{display:flex;flex-wrap:wrap;align-items:flex-end;gap:30px 26px;padding-top:6px}
.shelf{flex:var(--n) 1 calc(var(--n) * 150px);min-width:0;position:relative;padding-top:32px;--sc:var(--ink)}
.sign{position:absolute;left:0;top:0;margin:0;display:inline-flex;align-items:baseline;gap:10px;padding:5px 14px 4px;background:var(--sc);color:#FFF;
 transform:rotate(var(--tilt));box-shadow:3px 3px 0 var(--ink);font:900 16px/1.3 var(--font-sans);letter-spacing:.1em;white-space:nowrap}
.sign small{font:11px/1.3 var(--font-num);letter-spacing:.12em;opacity:.9}
.tapes{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:12px;padding:0 10px 0 6px}
.tape{display:grid;grid-template-columns:6px minmax(0,1fr);min-width:0;background:var(--card);border:1.5px solid var(--ink);box-shadow:3px 3px 0 var(--ink);transition:transform .12s}
.tape:hover{transform:translateY(-4px)}
/* 背の色だけでジャンルを示す（ジャンル名は棚の看板に 1 回だけ書く） */
.tape .spine{grid-row:1/3;background:var(--sc)}
.tape .pic{margin:6px 6px 0 8px;border:1px solid var(--ink);aspect-ratio:4/3;--ac:var(--sc)}
.tape .lbl{display:flex;flex-direction:column;gap:2px;min-width:0;padding:7px 8px 9px 8px}
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
/* 話題度（_heat_badge）：見出しの右に数字、押すと内訳のカード。数字の色は版面の --acc、カードは紙とインク */
.heat{position:relative;margin-left:auto}
.heat+.cnt{margin-left:0}
.heat summary{list-style:none;cursor:pointer;display:flex;align-items:baseline;gap:6px;white-space:nowrap;font:700 12px/1.3 var(--font-sans)}
.heat summary::-webkit-details-marker{display:none}
.heat summary small{font:700 var(--fs-label) var(--font-sans);letter-spacing:.08em;opacity:.85}
.heat summary b{font:30px/1 var(--font-num);color:var(--acc);border-bottom:2px dotted color-mix(in srgb,var(--fg) 45%,transparent)}
.heat summary i{font:900 16px/1 var(--font-sans);font-style:normal}
.heat.flat summary i{opacity:.5}.heat.down summary i{opacity:.7}
.heat summary em{font:700 var(--fs-label) var(--font-sans);font-style:normal;opacity:.85}
.heat .hx-rise{display:inline-block;padding:1px 8px;background:var(--alert);color:#FFF;transform:skewX(var(--skew));font:900 var(--fs-label)/1.4 var(--font-sans);letter-spacing:.1em}
.heat summary:hover b{border-bottom-style:solid}
.hx{position:absolute;right:0;top:calc(100% + 10px);z-index:6;width:min(420px,calc(100vw - 32px));padding:14px 16px 12px;
 background:var(--card);color:var(--ink);border:2px solid var(--ink);box-shadow:var(--shadow);white-space:normal}
.hx-head{margin:0 0 8px;padding-bottom:6px;border-bottom:2px solid var(--ink);font:700 12px/1.4 var(--font-sans)}
.hx-head b{font:900 15px var(--font-sans)}
.hx ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:7px}
.hx li{display:grid;grid-template-columns:84px minmax(0,1fr) 30px;gap:2px 8px;align-items:center}
.hx-n{font:700 12px/1.3 var(--font-sans)}
.hx-bar{height:10px;background:linear-gradient(90deg,var(--rose) calc(var(--v) * 100%),color-mix(in srgb,var(--ink) 12%,transparent) 0);transform:skewX(var(--skew))}
.hx li b{font:16px var(--font-num);text-align:right}
.hx li small{grid-column:2/4;font:500 var(--fs-label)/1.45 var(--font-sans);opacity:.8}
.hx-miss,.hx-note{margin:8px 0 0;font:500 12px/1.55 var(--font-sans);opacity:.8}
.hx-more{display:block;margin-top:10px;padding:6px;text-align:center;background:var(--ink);color:var(--card);font:900 12px var(--font-sans);letter-spacing:.06em}
.hx-more:hover{background:var(--rose)}
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
.when{display:flex;align-items:center;gap:8px;min-width:0;font:14px/1 var(--font-num);letter-spacing:.05em}  /* 薄めるのは日付の文字だけ（NEW の札まで薄めると読めなくなる） */
.from{min-width:0;overflow-wrap:break-word;font:400 11px/1.3 var(--font-sans);letter-spacing:.02em}  /* 省略しない：入らなければ次の行へ */
.brief .d{display:flex;flex-direction:column;gap:2px;max-width:9em}.brief .d .from{font-size:11px;opacity:.85}
.nm .from,.mono .from,.watch span .from{margin-left:8px;letter-spacing:.02em;color:inherit;font-weight:500}
.wc em,.kick em{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;min-width:0}
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
.card.mini>:is(.xprice,.xevent,.xgal){grid-column:2}.card.mini>:is(.xprice,.xevent){justify-self:start}.xevent span{white-space:nowrap}  /* 日程・価格は字の下に（写真の下の空きに落とさない） */
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
.older summary span{font-weight:500;letter-spacing:.04em}
.older .grid{padding-top:8px}
.older .card.c3 h3{font-size:15px;line-height:1.45}
/* ---- 作品ごとの装飾（motif = 版面模版）は templates/*.css から読み込んで、ここに入れる ---- */
/* ---------- 気になるかも？：店長のおすすめ POP ---------- */
.picks{--ac:var(--rose);background:var(--sheet);color:var(--ink);border:2px solid var(--ink);box-shadow:8px 8px 0 var(--rose);padding:22px 26px 28px}
.pkhead{display:flex;flex-wrap:wrap;align-items:center;gap:12px 18px}
.pkhead h2{margin:0;display:inline-block;background:var(--ink);color:var(--card);padding:6px 18px 6px 16px;transform:rotate(var(--tilt));box-shadow:4px 4px 0 var(--rose);
 font:900 24px/1.25 var(--font-sans);letter-spacing:.06em}
.pkhead h2 em{font-style:normal;color:var(--gold)}
.pkhead .flag{position:relative;display:inline-block;padding:8px 14px 7px;background:var(--card);box-shadow:var(--shadow);transform:rotate(-2deg);font:21px/1 var(--font-hand)}
.pkhead .flag::after{content:"";position:absolute;right:-12px;top:50%;margin-top:-8px;border:8px solid transparent;border-left:12px solid var(--card);border-right:0}
.pkhead>span:not(.flag){flex-basis:100%;order:3;font-size:13px;opacity:.8}
.pkhead a{color:color-mix(in srgb,var(--rose) 72%,var(--ink));font-weight:700;border-bottom:1px solid currentColor}  /* バラ色のままだと地の上で 4.5:1 に届かない */
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
.vote{display:flex;flex-wrap:wrap;align-items:center;gap:10px;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
.vote small{font-size:11px;opacity:.7}
.pk.down>a{opacity:.35;filter:grayscale(1)}
.card,.top,.wc{position:relative}
.lk{position:absolute;inset:0;z-index:1}  /* 原文链接 = 卡片全体を覆う透明な層 */
.lk:focus-visible{outline:3px solid currentColor;outline-offset:4px}
:is(.card,.top,.wc) :not(.lk,.vt,.vt *){pointer-events:none}  /* クリックは必ず .lk か 👍/👎 に届く */
:is(.card,.top,.wc) :is(.vt,.vt *){pointer-events:auto}  /* pointer-events は継承されるので明示的に戻す */
/* 👍/👎 = 日付の行の右端に置く小さな印。普段は線の拇指だけ（枠なし）、押すと「NEW」と同じ塗りの札になる */
.vt,.vote>span{--vc:var(--ac,var(--ink));--vt:var(--bg,var(--card));--vf:var(--fg,var(--ink));display:inline-flex;align-items:center;gap:2px;flex:none}
.vt{position:absolute;right:-6px;top:0;height:var(--vth,28px);padding:0 4px 0 12px;z-index:2;font-size:0;cursor:default;-webkit-tap-highlight-color:transparent;touch-action:manipulation}  /* 周りの余白も按钮区：按偏了也不会打开原文 */
.card.a .vt{--vt:var(--abg);--vf:var(--afg)}
.wc .vt{--vc:var(--sc,var(--ink));--vt:#FFF;--vf:var(--ink)}
.top .vt{--vc:var(--deep,var(--ink));--vt:var(--card);--vf:var(--ink)}
.picks .vote>span{--vc:var(--rose);--vt:#FFF;--vf:var(--ink)}
.vt button,.vote button{display:inline-flex;align-items:center;gap:4px;min-height:26px;padding:0 6px;border:0;background:none;color:inherit;opacity:.6;
 font:900 11px/1 var(--font-sans);letter-spacing:.1em;cursor:pointer;border-radius:0;transform:skewX(var(--skew));transition:opacity .12s,background .12s}
.vt button>i,.vote button>i{display:inline-flex;align-items:center;gap:4px;font-style:normal;transform:skewX(8deg)}
.vt svg,.vote svg{width:15px;height:15px;flex:none;fill:none;stroke:currentColor;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
.vt button:hover,.vote button:hover,.vt button:focus-visible,.vote button:focus-visible{opacity:1}
.vt button:focus-visible,.vote button:focus-visible{outline:2px solid currentColor;outline-offset:1px}
.vt button[aria-pressed=true],.vote button[aria-pressed=true]{opacity:1;background:var(--vc);color:var(--vt)}
.vt button[data-vote="-1"][aria-pressed=true],.vote button[data-vote="-1"][aria-pressed=true]{background:var(--vf)}  /* 踩 = 文字色の札（アクセント色は「好き」だけ） */
.card:has(.vt:hover) :is(h2,h3),.brief li:has(.vt:hover) a{text-decoration:none}.top:has(.vt:hover) .hb{background:var(--ink)}.wc:has(.vt:hover){transform:none;box-shadow:var(--shadow)}  /* 指在按钮上时，原文链接不做悬停反应 */
.vt button span,.pk:not(.big) .vote button span{display:none}
/* 👍/👎 は日付の行の右端に固定（absolute）、その幅だけ右を空ける。出典が長ければ出典だけ次の行に回り、ボタンを押し出さない */
.when:has(.vt),.kick:has(.vt),.wc em:has(.vt){position:relative;z-index:2;flex-wrap:wrap;row-gap:4px;align-content:center;min-height:var(--vth,28px);padding-right:var(--vtw,70px);align-self:stretch}
.vt button{min-height:var(--vth,28px)}  /* 按钮的高度 = 日期行的高度：按钮区不会伸到标题上 */
/* 出典が日付の横に入らないとき（JS が .two を付ける）：出典だけ次の行に全幅で。1 行目の右はボタンの分だけ空ける */
.when.two,.wc em.two{padding-right:0;align-content:flex-start;row-gap:0}.two>.from{order:2;flex-basis:100%}.two::before{content:"";order:1;flex:0 0 var(--vtw,70px);height:var(--vth,28px);margin-left:auto}
.vote button{opacity:.75}
.brief li .vt{position:static;margin:-6px -6px -6px auto;align-self:center}
/* 作品の小元素：右上で枠からはみ出すステッカー。白いフチ → 版面の強調色のフチ（emblem_ring）→ 墨の硬い影。
   高さを決めて幅は絵なり（全身の縦長の絵も小さくならない）。スクロールで飛び出し、そのあと影が伸びて立体に */
@property --sx{syntax:"<length>";inherits:true;initial-value:8px}
@property --sy{syntax:"<length>";inherits:true;initial-value:8px}
.emb{--ring:var(--acc);position:absolute;right:clamp(12px,4%,52px);bottom:8px;z-index:5;height:156px;pointer-events:none;transform:rotate(-6deg);transform-origin:50% 100%}  /* 見出しの帯の中に置き、下端を帯にそろえる：上には版面の外へはみ出してよいが、下のニュースには重ならない */
.emb.ring-white{--ring:var(--card)}.emb.ring-none{--ring:transparent}
.emb-in{height:100%;width:max-content;transition:transform .6s cubic-bezier(.2,1.5,.4,1),opacity .2s,--sx .35s ease-out .45s,--sy .35s ease-out .45s;
 filter:drop-shadow(2.5px 0 0 var(--card)) drop-shadow(-2.5px 0 0 var(--card)) drop-shadow(0 2.5px 0 var(--card)) drop-shadow(0 -2.5px 0 var(--card))
  drop-shadow(3px 0 0 var(--ring)) drop-shadow(-3px 0 0 var(--ring)) drop-shadow(0 3px 0 var(--ring)) drop-shadow(0 -3px 0 var(--ring))
  drop-shadow(var(--sx) var(--sy) 0 var(--ink))}  /* フチと影は外側に：切り抜きの輪郭にも、カードの四辺形にも沿う */
.emb-in{display:flex;align-items:flex-end}
.emb img{display:block;height:calc(100% * var(--k,1));width:auto;max-width:190px;object-fit:contain;object-position:bottom}  /* --k：顔の大きさをそろえる（アップの絵は小さく） */
.emb img.logo{height:62%;max-width:150px}.emb img.icon{height:70%}  /* ロゴ・物のアイコン：人物より小さめ */
/* 透明な立ち絵が見つからない写真は、丸ではなく P5 風の傾いた四辺形のカードに（中身はそのまま、顔が入るよう上寄り） */
.emb img.badge{width:auto;aspect-ratio:4/5;object-fit:cover;object-position:50% 20%;clip-path:polygon(8% 0,100% 5%,92% 100%,0 94%)}
.emb .crop{display:block;height:100%;aspect-ratio:4/5;overflow:hidden;clip-path:polygon(8% 0,100% 5%,92% 100%,0 94%)}
.emb .crop img{width:calc(100% / var(--cw));max-width:none;height:auto;aspect-ratio:auto;object-fit:fill;clip-path:none;
 margin-left:calc(-100% * var(--cx) / var(--cw));margin-top:calc(-100% * var(--cy) * var(--ar) / var(--cw))}  /* 顔が入る範囲だけ（emblem.py の crop） */
.emb-js .emb:not(.in) .emb-in{opacity:0;transform:translate(56px,44px) rotate(26deg) scale(.45);--sx:0px;--sy:0px}
.emb-js .emb.out .emb-in{transition:transform .38s cubic-bezier(.6,0,.9,.4),opacity .3s ease-in .08s,--sx .15s,--sy .15s;
 transform:translate(18px,70px) rotate(-18deg) scale(.55)}  /* 上へ戻ったとき：影が縮んで、下へ沈みながら消える */
@supports (animation-timeline:view()){.emb{animation:embdrift linear both;animation-timeline:view();animation-range:cover}}
@keyframes embdrift{from{translate:0 22px}to{translate:0 -22px}}  /* スクロールに合わせてゆっくり浮く */
.has-emb .band{padding-right:260px}  /* 小元素の右からの位置（〜52px）＋幅（〜190px）＋傾きの分 */
.has-emb .deco{display:none}  /* 小元素がその版面の飾り：題字横の装飾字は出さない（右に寄せた数字と重なるため） */
@media (max-width:600px){.emb{height:100px;right:8px}.emb img{max-width:140px}.has-emb .band{padding-right:118px}}
@media (prefers-reduced-motion:reduce){.emb,.emb-in{animation:none;transition:none}}
/*LIKEFX*/.downv :is(.pic,h2,h3,.blurb,.hb,p,.tg,.d,li>a,.xprice,.wc>b,.when>b,.from){opacity:.4;filter:grayscale(.8)}  /* 踩过的消息变淡，按钮保持清楚，能撤回 */
.pkbatch[hidden]{display:none}
.shuffle{padding:7px 14px;border:2px solid var(--ink);background:var(--ink);color:var(--card);transform:skewX(var(--skew));box-shadow:3px 3px 0 var(--rose);
 font:900 13px var(--font-sans);letter-spacing:.06em;cursor:pointer;border-radius:0;white-space:nowrap}
.shuffle:hover{background:var(--rose);border-color:var(--rose);box-shadow:3px 3px 0 var(--ink)}
.shuffle small{margin-left:8px;padding:1px 7px;background:var(--card);color:var(--rose);font:700 11px var(--font-sans)}
.pknav{margin-left:auto;display:flex;gap:10px;white-space:nowrap}
.shuffle.back{background:var(--card);color:var(--ink);box-shadow:3px 3px 0 var(--ink)}
.shuffle[disabled]{opacity:.35;cursor:default;pointer-events:none}
@media (hover:none){.vt button,.vote button{padding:0 9px;opacity:.75}.vote button{min-height:34px}.when,.kick,.wc em,.brief li{--vth:36px;--vtw:82px}}  /* 指で押せる大きさ */
.shuffle:active,.mastwish:active{transform:translate(3px,3px);box-shadow:none}  /* 押した感触：影の分だけ沈む */
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
  .wall{grid-template-columns:minmax(0,1fr);gap:16px}.wall>.wc:nth-child(n+7){display:none}.wc.lead{grid-column:auto;grid-row:auto}.wc.lead .pic{min-height:0;aspect-ratio:16/10}
 .wc:not(.lead){display:grid;grid-template-columns:120px minmax(0,1fr);grid-template-rows:auto 1fr;gap:4px 12px;align-items:start}
 .wc:not(.lead) .pic{grid-row:1/3}.wc:not(.lead) .tg{left:-6px;top:6px;font-size:11px}
  .fside{display:none}  /* スマホは右の列を出さない（欲しい物は報頭のボタン、予定は各版面で） */
 .shelves{gap:28px 0}.shelf{flex:none;width:100%}
 .tapes{grid-template-columns:minmax(0,1fr);gap:10px;padding:0 4px 0 0}
 .tape{grid-template-columns:6px 110px minmax(0,1fr);align-items:start}.tape .spine{grid-row:auto;align-self:stretch}
 .tape .pic{margin:6px 0 6px 6px}.tape .lbl{padding:7px 10px 9px}
 .tape:nth-child(n+4){display:none}  /* スマホは各ジャンル 3 作品まで（ほかは下の各版面で） */
 .picks{padding:18px 14px 22px;box-shadow:5px 5px 0 var(--rose)}.pknav{margin-left:0;width:100%}
 .pkgrid,.pkgrid.row{grid-template-columns:minmax(0,1fr);gap:28px}.pk.big .pic{flex:none;min-height:0;aspect-ratio:16/10}
 .pk.big .pkt{margin:-26px 10px 0;padding:18px 16px 14px}.pk.big .why{font-size:20px}.pk.big b{font-size:17px}.pk.big .vote{margin:10px 10px 0}
 .sec{box-shadow:5px 5px 0 var(--ink)}.band{padding:16px 14px 2px}.band .title{font-size:22px;padding:6px 14px}.band .cnt,.band .heat{margin-left:0}.band .deco{display:none}
 .hx{position:static;width:auto;margin-top:10px}.heat[open]{flex-basis:100%}
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
@media (prefers-reduced-motion:reduce){.wc,.tape,.frame,.vote button,.vt button,.mastwish{transition:none}}
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


def _img_url(u):
    """配図の網址を整える。Bing ニュースの縮小画像（bing.com/th?id=…&w=1200）は、元が小さいと
    指定の幅まで白い余白を足して返すので、w / h を外して元の大きさで取る（枠の中に白い帯ができない）。"""
    if isinstance(u, str) and re.match(r"^https://(www\.)?bing\.com/th\?", u):
        u = re.sub(r"&(amp;)?[wh]=\d+", "", u)
    return u


def _pic(story):
    """配图。底层模糊铺满，上层完整显示：图片不裁切，也不留空白条。
    兜底顺序：自己的图 → _fbs 里的备用图（作品封面）→ 来源网站的图标和网站名 → 作品名排版的封面块。
    前一个打不开（防盗链、网站删图、图标太小……）网页上自动换下一个。"""
    img, name = story.get("image"), story.get("_work", "")
    fbs = story.get("_fbs") if story.get("_fbs") is not None else [story.get("_cover")]
    chain = list(dict.fromkeys(_img_url(u) for u in [img, *fbs] if u))  # 第一张是 src，其余按顺序备用
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
    return f'<span class="when">{new}{e(d[5:].replace("-", "."))}{_from(story)}</span>'


def _from(story):
    """日期后面的浅色小字：消息来源（媒体名）。"""
    name = _source_name(story).strip()
    return f'<span class="from">{e(name[:40])}</span>' if name else ""


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


def _lk(story):
    """卡片的原文链接：透明一层盖满整张卡片（卡片本身不是 <a>），👍/👎 浮在它上面、不在链接里面。"""
    return (f'<a class="lk" href="{e(story["url"])}" target="_blank" rel="noopener" '
            f'aria-label="{e(story["headline"])}"></a>')


def _play(story):
    """動画のある記事：画像の上に ▶ を重ねる（リンク先は記事のまま）。"""
    return '<span class="xplay" aria-label="動画あり">▶</span>' if _safe_url(story.get("video")) else ""


def _tcard(story, span, i, today, small=False, mini=False):
    side = "a" if small else "m"  # 不再黑白交替：一周内统一主色底，折叠区统一副色底
    w = story.get("weight", "normal")
    url = e(story["url"])
    if mini:  # 普通消息：左边小图、右边日期和标题
        return (f'<article class="card {side} mini c{span}">{_lk(story)}{_pic(story)}{_play(story)}'
                f'{_when(story, today)}<h3>{_headline(story)}</h3>{_extras(story)}</article>')
    if span == 12 and w == "hero":
        return (f'<article class="card {side} hero">{_lk(story)}{_pic(story)}{_play(story)}'
                f'<div class="txt">{_when(story, today)}<span class="tag">重 大</span><h2>{_headline(story)}</h2>'
                + (f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") else "") + _extras(story) + "</div></article>")
    blurb = f'<p class="blurb">{e(story["blurb"])}</p>' if story.get("blurb") and not small and w != "normal" else ""
    if span == 12 and not small:
        return (f'<article class="card {side} wide c12">{_lk(story)}{_pic(story)}{_play(story)}'
                f'<div class="txt">{_when(story, today)}<h3>{_headline(story)}</h3>{blurb}{_extras(story)}</div></article>')
    level = "h2" if w == "lead" and span >= 8 and not small else "h3"
    cls = f"c{span}" + (" lead" if level == "h2" else "")
    return (f'<article class="card {side} {cls}">{_lk(story)}{_pic(story)}{_play(story)}'
            f'{_when(story, today)}<{level}>{_headline(story)}</{level}>{blurb}{_extras(story)}</article>')


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
    普通消息做成左图右字的小卡片，一排最多三张，连着的几张平均分行（4 张 = 2+2）；只有一张时做成横长的大卡片。返回 [(行类型, 卡片列表)]。"""
    rows, normals, led = [], [], False

    def flush():
        # 连着的普通消息平均分行（一行最多 3 张）：4 张是 2+2、5 张是 3+2，不留下孤零零的一张占整行
        n = len(normals)
        if n:
            k = -(-n // 3)
            at = 0
            for r in range(k):
                c = n // k + (r < n % k)
                rows.append(("normal", normals[at:at + c]))
                at += c
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
    flush()
    return rows


def _row_h(kind, cards):
    """这一行在桌面版上大约多高（照实际网页量的，标题按最多行数算）。"""
    if kind == "hero":
        return 310
    if kind == "lead":
        return 260 if len(cards) == 1 else 470
    return 200 if len(cards) == 1 else 125


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
        elif len(cards) == 1:  # 只有一张：小卡片占整行会空出一大片，做成左图右字的横长卡片
            out.append(_tcard(cards[0], 12, i, today))
        else:
            span = {2: 6, 3: 4}[len(cards)]
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
    rows = "".join(f'<li><span class="d">{e((x.get("date") or x["_issue"])[5:].replace("-", "."))}{_from(x)}</span>'
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
                f'<span class="mono">直近 · {e(last["date"].replace("-", "."))}{_from(last)}</span><b>{e(last["headline"])}</b></a>')
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


FACE_SHARE = 0.32   # emblem.FACE_SHARE と同じ：顔が小元素の高さのこの割合になる大きさで表示する


def _emblem_img(a):
    """小元素 1 枚の HTML。カード（badge）で取景（crop）があれば 4:5 の窓にその範囲だけを見せる。
    顔の割合（fs）が基準より大きい（アップの）ものは小さく表示して、どの版面でも顔が同じくらいの大きさに見えるように。"""
    k = f' style="--k:{min(1, FACE_SHARE / a["fs"]):.3f}"' if a.get("fs") else ""
    img = (f'<img class="{a["shape"]}"{k} src="{e(a["src"])}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" '
           f'onerror="var s=this.closest(\'.sec\');if(s)s.classList.remove(\'has-emb\');this.closest(\'.emb\').remove()">')
    c = a.get("crop")
    if a["shape"] == "badge" and c:
        return f'<span class="crop" style="--cx:{c[0]};--cy:{c[1]};--cw:{c[2]};--ar:{a.get("ar", 1)}">{img}</span>'
    return img


def _emblem(items, ring="accent"):
    """作品の小元素（items.yaml の emblem、scripts/emblem.py が探した既存の画像）。版面の右上に、枠からはみ出して貼る。
    候補が何枚あっても、網页を開くたびに 1 枚をランダムに（JS がなければ先頭）。画像は元の網址を直接引用（倉庫に保存しない）。
    人物は透明な立ち絵（輪郭どおり）、立ち絵がない写真は P5 風の傾いたカードに顔が入るよう取景（crop）して貼る。"""
    alts = []
    for x in items:
        local = isinstance(x, dict) and re.fullmatch(r"emblems/[a-z0-9-]+\.webp", str(x.get("image") or ""))
        if not (isinstance(x, dict) and (_safe_url(x.get("image")) or local)):
            continue   # 網址（http(s)）か、切り抜いて倉庫に置いた画像（docs/emblems/）だけ
        a = {"src": x["image"], "shape": "badge" if x.get("shape") == "badge" else "cutout"}
        c = x.get("crop")
        if isinstance(c, list) and len(c) == 3 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in c) and c[2] > 0:
            a.update(crop=c, ar=float(x.get("ar") or 1))
        fs = x.get("fs")
        if isinstance(fs, (int, float)) and 0.05 < fs <= 1:
            a["fs"] = float(fs)
        if x.get("shape") in ("logo", "icon"):
            a["shape"] = x["shape"]
        alts.append(a)
    if not alts:
        return ""
    ring = ring if ring in ("accent", "white", "none") else "accent"
    return (f'<div class="emb ring-{ring}" aria-hidden="true" data-alts="{e(json.dumps(alts, ensure_ascii=False))}">'
            f'<div class="emb-in">{_emblem_img(alts[0])}</div></div>')


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
    cnt = _heat_badge(block) + cnt
    emb_html = _emblem(block.get("_emblems") or [], block.get("_ring") or "accent")
    return (f'<section id="{anchor}" data-k="{e(block["name"])}"{_fx(block["name"])} class="sec{" m-" + motif if motif else ""}{" has-emb" if emb_html else ""}{quiet}" style="{style}">'
            f'<div class="band">{emb_html}{MOTIFS.get(motif, "")}<span class="title">{e(block["name"])}</span>{sub}{cnt}</div>'
            f"{facts}{grid}</section>")


# 版面模版（items.yaml の motif）：templates/index.yaml に一覧、見た目は templates/<id>.css（.m-<id>）。
# 作品の色（--bg/--acc…）だけで描くので、同じ模版でも作品ごとに色が変わる。足し方・合わせ方は TEMPLATES.md
TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent.parent / "templates"


def load_templates():
    """[{id, name, for, deco, defaults, css}]。CSS ファイルがないものは飛ばす。"""
    index = TEMPLATE_DIR / "index.yaml"
    if not index.exists():
        return []
    out = []
    for t in (yaml.safe_load(index.read_text(encoding="utf-8")) or {}).get("templates") or []:
        path = TEMPLATE_DIR / f"{t.get('id')}.css"
        if t.get("id") and re.fullmatch(r"[a-z][a-z0-9-]*", t["id"]) and path.exists():
            out.append({**t, "deco": t.get("deco") or [], "defaults": t.get("defaults") or [],
                        "css": path.read_text(encoding="utf-8")})
    return out


TEMPLATES = load_templates()
WEB_ITEM_MARK = "从网页设置页加进来的"  # digest.WEB_ITEM_MARK と同じ
# 名前 → 版面の見出しに添える飾り（なければ空）
MOTIFS = {t["id"]: "".join(f'<i class="deco{f" d{k + 1}" if k else ""}" aria-hidden="true">{e(str(c))}</i>'
                           for k, c in enumerate(t["deco"])) for t in TEMPLATES}
_TPL_MARK = "/* ---- 作品ごとの装飾（motif = 版面模版）は templates/*.css から読み込んで、ここに入れる ---- */\n"
CSS = CSS.replace(_TPL_MARK, _TPL_MARK + "".join(t["css"] for t in TEMPLATES))
CSS = CSS.replace("/*LIKEFX*/", likefx.FX_CSS.strip() + "\n")  # 👍 の演出（20 種）
# テーマ → 👍 の演出（templates/index.yaml の fx）。作品 → 演出は render() のたびに作る
TEMPLATE_FX = {t["id"]: t.get("fx") if t.get("fx") in likefx.FX else "pop" for t in TEMPLATES}
_FX_OF = {}


def _fx(name):
    """作品名 → data-fx 属性（その版面のテーマの 👍 演出）。"""
    return f' data-fx="{_FX_OF.get(name, "pop")}"'
  # 元の位置（スマホ用の @media より前）に入れる


def template_for(item):
    """この関注項の版面模版：items.yaml の motif。まだ設計されていない（motif なし）ものは、
    type が近い既存の模版（templates/index.yaml の defaults）を仮に使う。どれも合わなければ普通の版面。"""
    if item.get("motif") in MOTIFS:
        return item["motif"]
    if WEB_ITEM_MARK not in str(item.get("notes") or ""):  # 手で書いた関注項で motif なし＝わざと普通の版面
        return ""
    return next((t["id"] for t in TEMPLATES if item.get("type", "product") in t["defaults"]), "")


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
                    + f'<span>{_vote_buttons()}</span>'
                    + f'<small></small></div>')
        return (
            f'<div class="pk{" big" if big else ""}" data-u="{e(x["url"])}" data-s="{x.get("score") or 4}" '
            f'data-w="{e(x["work"])}"{_fx(x["work"])} data-key="{e("|".join(x.get("words") or []))}"{" data-f=1" if follow else ""}{" data-new=1" if x.get("explore") else ""}>'
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
_THUMB = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56'
          'l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/></svg>')
_THUMB_DOWN = _THUMB.replace('<svg ', '<svg style="transform:scaleY(-1)" ', 1)  # 同じ形を上下反転


def _vote_buttons():
    """👍/👎 两个按钮（「気になるかも？」和各消息卡片共用同一套外观）。"""
    return ('<button type="button" data-vote="1" aria-pressed="false" aria-label="好き" title="好き：この種類を増やす">'
            f'<i>{_THUMB}<span>好き</span></i></button>'
            '<button type="button" data-vote="-1" aria-pressed="false" aria-label="興味なし" title="興味なし：この種類を減らす">'
            f'<i>{_THUMB_DOWN}<span>興味なし</span></i></button>')


VOTE_JS = """
(() => {
  const cfg = __CFG__, KEY = 'wishlist-votes';
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
  // 押した瞬間に画面を変える（楽観的更新）。保存は裏で、同じ記事の票は順番に送る。失敗したら元に戻す
  const saved = { ...mine }, queue = {}, touched = new Set();
  const send = (data, v) => fetch(cfg.url.replace(/\\/$/, '') + '/rest/v1/feedback',
    { method: 'POST', headers, body: JSON.stringify({ ...data, vote: v }), keepalive: true })
    .then(async r => { if (!r.ok) throw new Error(r.status + ' ' + (await r.text()).slice(0, 120)); });
  const fxOf = el => (el.closest('[data-fx]') || {}).dataset?.fx || 'pop';   // 版面のテーマの演出（likefx.py）
  const embOf = el => {   // いまその作品の版面に出ている小元素の画像（👍 の演出で一緒に飛ぶ）
    const k = (el.closest('[data-k]') || {}).dataset?.k;
    const img = k && document.querySelector('.sec[data-k="' + CSS.escape(k) + '"] .emb img');
    return img && img.complete && img.naturalWidth ? '<img src="' + img.src + '" alt="" referrerpolicy="no-referrer">' : null;
  };
  const wire = (box, data, dim, tip) => {
    boxes.push([box, data, dim, tip]);
    box.addEventListener('click', ev => {
      ev.preventDefault(); ev.stopPropagation();
      const btn = ev.target.closest('button[data-vote]');
      if (!btn) return;
      const url = data.url, v = (mine[url] || 0) === Number(btn.dataset.vote) ? 0 : Number(btn.dataset.vote);
      mine[url] = v; touched.add(url);
      try { localStorage.setItem(KEY, JSON.stringify(mine)); } catch (_) {}
      paint(url); window.likeFx(btn, v, fxOf(btn), embOf(btn));
      queue[url] = (queue[url] || Promise.resolve()).then(() => send(data, v)).then(() => { saved[url] = v; }, err => {
        console.error('投票失败', err);
        if (mine[url] !== v) return;   // もう次の票を押している
        mine[url] = saved[url] || 0;
        try { localStorage.setItem(KEY, JSON.stringify(mine)); } catch (_) {}
        paint(url);
        if (tip) tip.textContent = '保存できませんでした。後でもう一度';
        btn.title = '保存できませんでした。後でもう一度';
        box.animate([{ translate: '0' }, { translate: '-4px' }, { translate: '4px' }, { translate: '0' }], { duration: 240 });
      });
    });
  };
  document.querySelectorAll('.picks .vote').forEach(box =>
    wire(box, JSON.parse(box.dataset.v), box.closest('.pk'), box.querySelector('small')));
  const small = () => {
    const s = document.createElement('span');
    s.className = 'vt';
    s.innerHTML = __BTNS__;
    return s;
  };
  const story = (link, holder, dim) => {
    if (!/^https?:/.test(link.getAttribute('href') || '')) return;
    const w = holder.closest('[data-k]');
    const t = link.getAttribute('aria-label') || link.textContent;   // 标题（卡片的 .lk 带 aria-label，列表就是链接文字）
    const box = small();
    // 放在日期那一行的右端（版面卡片 .when、头条 .kick、照片墙 em）；没有日期行的放在最后
    (holder.querySelector('.when, .kick, :scope > em') || holder).appendChild(box);
    const title = t.trim().slice(0, 500), work = (w && w.dataset.k || '').slice(0, 200);
    wire(box, { url: link.href, kind: 'story', title, work, hits: [], words: [] }, dim, null);
  };
  document.querySelectorAll('.sec .card, .top, .wc').forEach(c => { const a = c.querySelector(':scope > .lk'); if (a) story(a, c, c); });
  document.querySelectorAll('.sec .brief li').forEach(li => { const a = li.querySelector('a'); if (a) story(a, li, li); });
  new Set(boxes.map(b => b[1].url)).forEach(paint);
  // 数据库里「我点过的票」为准：换浏览器、换手机、清了缓存也显示成按过的样子（db/my_votes.sql）
  fetch(cfg.url.replace(/\\/$/, '') + '/rest/v1/rpc/my_votes', { method: 'POST', headers, body: '{}' })
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(rows => {
      const old = mine;
      mine = {};
      rows.forEach(r => { mine[r.url] = r.vote; saved[r.url] = r.vote; });
      touched.forEach(u => { mine[u] = old[u]; });   // 読み込み中に押した票はそのまま
      try { localStorage.setItem(KEY, JSON.stringify(mine)); } catch (_) {}
      new Set(Object.keys(old).concat(Object.keys(mine))).forEach(paint);
    })
    .catch(err => console.warn('读不到数据库里的投票，先用本机记录', err));
  // 日付の行が 2 行になった（出典が入らない）ときは .two：出典を次の行に全幅で出す（途中で切らない）
  const fit = () => document.querySelectorAll('.when, .wc em').forEach(r => {
    const v = r.querySelector(':scope > .vt');
    if (!v || !r.querySelector(':scope > .from')) return;
    r.classList.remove('two');
    if (r.offsetHeight > v.offsetHeight + 1) r.classList.add('two');
  });
  fit();
  if (document.fonts) document.fonts.ready.then(fit);
  let t; addEventListener('resize', () => { clearTimeout(t); t = setTimeout(fit, 150); });
})();
"""
VOTE_JS = (VOTE_JS.replace("__BTNS__", json.dumps(_vote_buttons(), ensure_ascii=False))
           .replace("__THUMB__", json.dumps(_THUMB)))
LIKEFX_JS = likefx.FX_JS.replace("__THUMB__", json.dumps(_THUMB))
# 作品の小元素：アニメーションできるときだけ最初は隠し（<head> で html に emb-js）、版面がスクロールで入ってきたら .in で飛び出す
EMB_HEAD_JS = ("if('IntersectionObserver' in window&&!matchMedia('(prefers-reduced-motion: reduce)').matches)"
               "document.documentElement.classList.add('emb-js')")
EMB_JS = """
(() => {
  const els = [...document.querySelectorAll('.emb')];
  // 開くたびに候補から 1 枚をランダムに
  els.forEach(el => {
    let alts = []; try { alts = JSON.parse(el.dataset.alts || '[]'); } catch (_) {}
    const inner = el.querySelector('.emb-in'), img = el.querySelector('img');
    if (alts.length > 1 && inner && img) {
      const a = alts[Math.floor(Math.random() * alts.length)];
      const n = img.cloneNode(); n.className = a.shape; n.src = a.src; n.style.cssText = a.fs ? '--k:' + Math.min(1, 0.32 / a.fs).toFixed(3) : '';
      if (a.shape === 'badge' && a.crop) {
        const c = document.createElement('span'); c.className = 'crop';
        c.style.cssText = '--cx:' + a.crop[0] + ';--cy:' + a.crop[1] + ';--cw:' + a.crop[2] + ';--ar:' + (a.ar || 1);
        c.appendChild(n); inner.replaceChildren(c);
      } else inner.replaceChildren(n);
    }
  });
  if (!els.length || !document.documentElement.classList.contains('emb-js')) return;
  // 下へスクロールして見えたら飛び出す（.in）。上へ戻って版面が画面の下へ消えたら、引っ込んで消える（.out）→ もう一度下へ来るとまた飛び出す
  const io = new IntersectionObserver(es => es.forEach(en => {
    const el = en.target;
    if (en.isIntersecting || en.boundingClientRect.bottom < 0) { el.classList.remove('out'); el.classList.add('in'); }
    else if (en.boundingClientRect.top > 0 && el.classList.contains('in')) { el.classList.remove('in'); el.classList.add('out'); }
  }), { rootMargin: '0px 0px -15% 0px', threshold: .5 });
  els.forEach(el => io.observe(el));
})();
"""
# 擬音の書体（使う文字だけ）と粒のライブラリ canvas-confetti（読めなくても演出は自作の粒で動く）
LIKEFX_HEAD = (f'<link rel="stylesheet" href="{e(likefx.SFX_FONT)}">'
               f'<script src="{likefx.CONFETTI_JS}" defer crossorigin="anonymous"></script>')


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
<p class="hint"><a href="themes.html">版面主题（30 套）和 👍 演出（20 种）一览 →</a>　<a href="admin.html">管理页（运行状况・投票・各关注项的记事数）→</a></p>
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
                         f'{e((st.get("date") or st["_issue"])[5:].replace("-", "."))}{_from(st)}</span>{e(st["headline"])}</a>')
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



HEAT_NOTE = ("6 つの指標の加重平均。各指標は「この作品のいつも」と比べて 6 割、全作品共通の物差しで 4 割"
             "（出来事は事件の大きさ、勢いは自分との比較だけ）。データのない指標は除いて計算し、👍 / 👎 は入れていません。")


def _trend(delta):
    """前週比 → (クラス, 矢印, 説明)。比べられない（データ不足）ときは矢印なし。"""
    if delta is None:
        return "", "", "前週比はデータ集め中"
    if delta >= 10:
        return "up", "↑", f"前週比 +{delta}"
    if delta <= -10:
        return "down", "↓", f"前週比 {delta}"
    return "flat", "→", f"前週比 {delta:+d}"


def _heat_badge(w):
    """版面の見出しの話題度（heat.py が計算）。押すと 6 つの指標の内訳。データがなければ出さない。"""
    h = w.get("_heat")
    if not h or not h.get("score"):
        return ""
    cls, arrow, why = _trend(h.get("delta"))
    rows = "".join(
        f'<li style="--v:{d["score"] / 100:.2f}"><span class="hx-n">{e(d["name"])}</span>'
        f'<span class="hx-bar" aria-hidden="true"></span><b>{d["score"]}</b><small>{e(d["note"])}</small></li>'
        for d in h.get("dims") or [])
    miss = (f'<p class="hx-miss">データなし（計算に入れていません）：{e("・".join(h["missing"]))}</p>'
            if h.get("missing") else "")
    hot = '<span class="hx-rise">急上昇</span>' if h.get("rising") else ""
    tip = f'話題度 {h["score"]}（{h["label"]}）· {why} · 押すと内訳'
    return (f'<details class="heat{" " + cls if cls else ""}"><summary title="{e(tip)}">'
            f'<small>話題度</small><b>{h["score"]}</b>{f'<i aria-hidden="true">{arrow}</i>' if arrow else ""}'
            f'<em>{e(h["label"])}</em>{hot}</summary>'
            f'<div class="hx"><p class="hx-head"><b>話題度 {h["score"]}</b> / 100 · {e(h["label"])} · {e(why)}</p>'
            f'<ol>{rows}</ol>{miss}<p class="hx-note">{e(HEAT_NOTE)}</p>'
            f'<a class="hx-more" href="heat.html#h-{_wid(w["name"])}">分析ページで詳しく →</a></div></details>')


WEEKDAY = ("月", "火", "水", "木", "金", "土", "日")
WEEKDAY_EN = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
SPOT_COUNT = 15  # 「ほかの注目ニュース」の写真の壁の候補：大きい 1 枚（2×2）+ 小さい 14 枚。WALL_JS が右の列の高さに収まる段数だけ出す。スマホは 6 枚まで


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
    hot = sorted((w for w in works if (w.get("_heat") or {}).get("score")), key=lambda w: -w["_heat"]["score"])[:6]
    if hot:
        rows = []
        for w in hot:
            h = w["_heat"]
            cls, arrow, why = _trend(h.get("delta"))
            top = next((d for d in h.get("dims") or [] if d["key"] == h.get("top")), None)
            tip = f'{h["label"]} · {why}' + (f' · いちばん効いている：{top["name"]}（{top["note"]}）' if top else "")
            rows.append(f'<li style="--sc:{_sec_color(w.get("section"))};--v:{h["score"] / 100:.3f}"><a href="#{_wid(w["name"])}" title="{e(tip)}">'
                        f'<span class="bn">{e(w["name"])}{"<em>急上昇</em>" if h.get("rising") else ""}</span>'
                        f'<span class="bar"></span><b>{h["score"]}</b>'
                        f'<i class="{cls}"{f' aria-label="{e(why)}"' if arrow else ' aria-hidden="true"'}>{arrow}</i></a></li>')
        out.append(f'<div class="sbox shot"><h4><a href="heat.html">話題度ランキング</a><small>100 点満点</small></h4><ol>{"".join(rows)}</ol>'
                   f'<p class="snote">報道量・広がり・出来事・勢い・Wikipedia・ファンの反応から計算。各作品の見出しの数字を押すと内訳</p>'
                   f'<a class="smore" href="heat.html">詳しい分析 →</a></div>')
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
        top_html = (f'<article class="top" data-k="{e(top_w["name"])}"{_fx(top_w["name"])}>{_lk(top)}'
                    f'{date_html}<div class="frame"><span class="burst">{badge}</span>{_pic(top)}{_play(top)}</div>'
                    f'<div class="ptxt"><span class="kick"><i class="tg" style="--sc:{sc}"><span>{e(_sec_name(top_w.get("section")))}</span></i>'
                    f'<i class="tg"><span>{e(top_w["name"])}</span></i><em>{e(_day(top))}{_from(top)}</em></span>'
                    f'<h2><span class="hb">{_headline(top)}</span></h2>'
                    + (f'<p>{e(top["blurb"])}</p>' if top.get("blurb") else "") + _extras(top) + "</div></article>")
        style = f' style="{_poster_colors(top, themes)}"'
    else:
        top_html = f'<div class="top">{date_html}<div class="ptxt"><h2><span class="hb">直近 {HOLD_DAYS} 日は新着なし</span></h2></div></div>'
        style = ""
    poster = f'<div class="poster"{style}><div class="marks" aria-hidden="true"></div>{head}{top_html}{foot}</div>'

    wall = "".join(
        f'<article class="wc{" lead" if i == 0 else ""}" data-k="{e(w["name"])}"{_fx(w["name"])} style="--sc:{_sec_color(w.get("section"))}">{_lk(x)}'
        f'<i class="tg"><span>{e(w["name"])}</span></i>{_pic(x)}{_play(x)}<em>{e(_day(x))}{_from(x)}</em><b>{_headline(x)}</b></article>'
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
            tapes.append(f'<a class="{cls}" href="#{_wid(w["name"])}"><span class="spine" aria-hidden="true"></span>'
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
        f'<span class="nm">{e(w["name"])}{" · " + e(ev["label"]) if ev.get("label") else ""}{_from(x)}</span>'
        f'<a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["headline"])}</a></li>'
        for d, w, x, ev in rows[:limit or AGENDA_MAX])
    return f'<div class="agenda"><h4>これからの予定<small>UPCOMING</small></h4><ol>{items}</ol></div>'


# 左侧目录的四种风格（items.yaml 的 settings.nav_style 选择）。只在宽屏生效，窄屏统一是顶部横条
NAV_STYLES = {
    # A 线路图：每个板块一段彩色线路，作品是站点；读到哪站圆点放大，线路按进度填色，读过的站变实心
    "line": """
/* P5 风：底色就是页面背景，站点是编号 + 斜切标签；当前站点反白、带红色硬阴影和进度条。不滚动：站点按画面高度平分 */
.nav{top:0;height:100vh;max-height:none;margin-top:-40px;padding:18px 14px 14px 14px;background:transparent;color:var(--ink);
 border-left:6px solid var(--alert)}
.nav .here{display:none}
.nav .rail{flex:1;padding:0 6px 0 0;overflow:hidden}
.nav .grp{flex:none;display:flex;align-items:center;gap:8px;margin:clamp(3px,1.2vh,14px) 0 clamp(1px,.4vh,4px)}
.nav .grp b{display:inline-block;background:var(--sc);color:#FFF;padding:0 10px;transform:skewX(var(--skew));font:900 12px/1.5 var(--font-sans);letter-spacing:.25em}
.nav .grp small{font:700 10px var(--font-mono);letter-spacing:.25em;color:rgba(26,28,34,.6)}
.nav .pill{flex:1 1 0;min-height:0;max-height:64px;gap:8px;padding:0 6px 0 8px;isolation:isolate;color:rgba(26,28,34,.74);
 font:800 clamp(11px,1.6vh,14px)/1.3 var(--font-sans);transition:color .15s,transform .25s cubic-bezier(.3,1.4,.5,1)}
.nav .pill .no{display:inline;font:700 10px var(--font-mono);letter-spacing:.05em;color:var(--sc)}
.nav .pill .nm{display:flex;flex-direction:column;gap:2px}
.nav .pill .cnt{display:none;font:700 10px var(--font-mono);letter-spacing:.12em;color:var(--gold)}
.nav .pill::before{content:"";position:absolute;inset:1px -4px 1px -6px;z-index:-1;transform:skewX(var(--skew));transition:background .15s}
.nav .pill:hover{color:var(--ink)}
.nav .pill:hover::before{background:rgba(26,28,34,.08)}
.nav .pill.past{color:var(--ink)}
.nav .pill.on{flex:0 0 auto;max-height:none;color:var(--card);font-size:clamp(14px,2.1vh,18px);font-weight:900;
 padding:clamp(5px,1.2vh,10px) 6px clamp(5px,1.2vh,10px) 12px;transform:translateX(10px)}
.nav .pill.on::before{background:var(--ink);box-shadow:4px 4px 0 var(--alert)}
.nav .pill.on::after{content:"";position:absolute;left:-2px;bottom:1px;z-index:-1;height:3px;width:calc(var(--p,0)*100%);background:var(--alert);transform:skewX(var(--skew))}
.nav .pill.on .no{color:var(--gold)}
.nav .pill.on .cnt{display:block}
.nav select{margin:14px 0 0 10px;align-self:flex-start;background:transparent;color:var(--ink);border:1px solid rgba(26,28,34,.4)}
.nav .navwish{margin:8px 6px 0 0;border-color:var(--ink);color:var(--ink);box-shadow:3px 3px 0 var(--alert);transform:skewX(var(--skew))}
.nav .navwish:hover{background:var(--alert);border-color:var(--alert);color:#FFF}
@media (max-height:700px){.nav{padding-top:10px;padding-bottom:8px}.nav .grp{margin-top:2px;margin-bottom:0}.nav .pill.on{padding-top:3px;padding-bottom:3px}.nav .pill.on .cnt{display:none}}
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
            css_img = f";--img:url({urllib.parse.quote(_img_url(img), safe=':/?&=%#@+,;~')})" if img else ""
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
    const nat = img.naturalWidth / img.naturalHeight;
    if (p.closest('.wc') && !(p.closest('.wc.lead') && innerWidth > 760)) { p.classList.add('fill'); return; }   // 写真の壁：枠 16:10 にそろえて埋める（段の高さがそろう）
    const r = nat / (p.clientWidth / p.clientHeight);
    // そのほかの枠は、比率が近いときだけ埋める（遠いときはぼかしの上に全体を見せる）
    p.classList.toggle('fill', Math.abs(Math.log(r)) < (p.closest('.wc.lead') ? 0.6 : 0.27));   // 大きい一枚は写真の 55% 以上見えるなら埋める
  };
  document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(img => {
    img.addEventListener('load', () => fit(img));
    if (img.complete) fit(img);
  });
  let t;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { document.querySelectorAll('.pic img:not(.bg):not(.ico)').forEach(fit); wall(); }, 200); });
  // 写真の壁を右の列とそろえる：右の列の高さに収まる段数だけカードを出し、残りの数十 px は各段の写真枠に等分して足す（空白を作らない）
  const wall = () => {
    const w = document.querySelector('.mgrid > .wall'), side = document.querySelector('.mgrid > .fside');
    if (!w) return;
    const cards = [...w.querySelectorAll(':scope > .wc')];
    cards.forEach(c => { c.hidden = false; const p = c.querySelector('.pic'); if (p) p.style.height = ''; });
    if (!side || innerWidth <= 760 || getComputedStyle(w).gridTemplateColumns.split(' ').length < 3) return;
    const target = side.getBoundingClientRect().height;
    // 大きい 1 枚＋横の 2 枚で 2 段、そのあと 3 枚ずつ 1 段
    let rows = 2;
    const show = r => cards.forEach((c, i) => { c.hidden = i >= 3 + (r - 2) * 3; });
    show(rows);
    while (3 + (rows - 1) * 3 <= cards.length) {
      show(rows + 1);
      if (w.getBoundingClientRect().height > target) { show(rows); break; }
      rows++;
    }
    const gap = target - w.getBoundingClientRect().height;
    if (gap > 0) {
      const add = gap / rows;
      cards.filter(c => !c.hidden && !c.classList.contains('lead')).forEach(c => {
        const p = c.querySelector('.pic'); if (p) p.style.height = (p.getBoundingClientRect().height + add) + 'px';
      });
    }
  };
  wall();
  if (document.fonts) document.fonts.ready.then(wall);
  addEventListener('load', wall);
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
  // 选中「屏幕里露出标题的、最靠上的」区块（上一个版面只剩尾巴时就算到下一个）；
  // 屏幕里一个标题都没有（在读长版面的中间）时选盖住屏幕顶边的那个。滚到最底时选最后一个
  function pick(top, bottom) {
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) {
      for (let i = marks.length - 1; i >= 0; i--) if (marks[i].getBoundingClientRect().top < bottom) return marks[i];
    }
    let covering = null;
    for (const el of marks) {
      const r = el.getBoundingClientRect();
      if (r.top >= top - 4 && r.top < bottom - 80) return el;   // 标题露出来了
      if (r.top < top && r.bottom > top) covering = el;
      if (r.top >= bottom) break;
    }
    return covering;
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
           motifs=None, themes=None, taste=(), heat=None, emblems=None, like_fx=None):
    """issues：按时间倒序的各期数据（全部）。nav_style：左侧目录风格，见 NAV_STYLES。
    order：items.yaml 里作品的顺序；updated：网页更新时间（显示用）；sizes：{作品: S / M / L} 篇幅。
    motifs：{作品: 装饰名}（items.yaml 的 motif，见 MOTIFS）；themes：取色キャッシュ（トップのポスターの色を書き足す）。
    heat：{作品: 話題度}（heat.compute 的结果，版面的见出し和トップの右の列に出す）。"""
    latest = issues[0]
    works = collect(issues, order)
    for w in works:
        w["_today"] = latest["date"]
        w["_size"] = (sizes or {}).get(w["name"], "M")
        w["_motif"] = (motifs or {}).get(w["name"], "")
        # 👍 の演出：items.yaml の like_fx（版面ごとに AI が決める）＞ テーマの fx
        own = (like_fx or {}).get(w["name"])
        _FX_OF[w["name"]] = own if own in likefx.FX else TEMPLATE_FX.get(w["_motif"], "pop")
        w["_emblems"], w["_ring"] = (emblems or {}).get(w["name"]) or ([], "accent")
        w["_heat"] = (heat or {}).get(w["name"])  # 話題度（heat.compute）
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
{LIKEFX_HEAD if fb else ""}
<script>{EMB_HEAD_JS}</script>
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
{f"<script>{LIKEFX_JS}</script><script>{VOTE_JS.replace('__CFG__', json.dumps(fb))}</script>" if fb else ""}
<script>{EMB_JS}</script>
</body>
</html>
"""


# ---------- 話題度の分析ページ（docs/heat.html）----------
# heat.analyze の結果を、ランキング（ヒートマップ表）・前週比・作品ごとの内訳とグラフ・計算方法の順に並べる。
# グラフはサーバー側で書く SVG（ライブラリなし）。色はトークン（--viz-* = 指標、--seq-* = 点数の濃淡、--up / --down = 前週比）だけ。
# ツールチップは補助：値は表（「表で見る」）からも全部読める

HEAT_DIM_COLOR = {"volume": "--viz-1", "breadth": "--viz-2", "event": "--viz-3",
                  "momentum": "--viz-4", "public": "--viz-5", "fandom": "--viz-6"}
HEAT_DIM_ABOUT = {  # 指標 → (何を測るか, データ)
    "volume": ("直近 7 日の報道の量。新しい記事ほど重く数える", "収集したニュース記事（Google ニュース・Bing・RSS）"),
    "breadth": ("どれだけ広く報じられたか。媒体の数 × 言語圏（日・中・韓・英）が 1 つ増えるごとに +25%", "収集したニュース記事の媒体名と見出しの言語"),
    "event": ("出来事そのものの大きさ。重要ニュース（発売日決定など）・状態の変化・14 日以内の予定・大きな記事", "重要ニュースの判定（作品ごとの条件）、AniList / TMDB の状態、記事の予定日"),
    "momentum": ("上り調子か下り坂か。昨日まで 2 日の速さ ÷ その前 5 日の速さ（今日は集計途中なので除く）", "記事の数、Wikipedia の閲覧数"),
    "public": ("ファン以外の一般の人の関心", "Wikipedia の閲覧数（人間のみ、複数言語の合計）"),
    "fandom": ("ファンコミュニティの反応", "Reddit の投稿数、AniList トレンド、TMDB 人気度、Steam 同時接続"),
}
HEAT_REF_LABEL = {  # 共通の物差しの満点：(名前, 書き方)
    "volume": ("報道量", "週 {} 件"), "breadth": ("広がり", "{}（媒体数 × 言語圏係数）"), "wiki": ("Wikipedia", "1 日 {} 回"),
    "reddit": ("Reddit", "週 {} 件"), "steam": ("Steam", "同時接続 {}"), "anilist": ("AniList", "トレンド {}"), "tmdb": ("TMDB", "人気度 {}")}


def _compact(n):
    """12,345 → 1.2万（グラフの目盛り・ツールチップ）。"""
    n = float(n)
    if n >= 10000:
        return f"{n / 10000:.1f}".rstrip("0").rstrip(".") + "万"
    return f"{n:,.0f}"


def _md_day(d):
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _seq(score):
    """点数 → ヒートマップの濃さ（5 段階、0〜19 がいちばん淡い）。"""
    return f"q{min(4, max(0, int(score) // 20))}"


def _nice(v):
    """目盛りの上限：1 / 2 / 5 × 10^n に切り上げ。"""
    if v <= 0:
        return 1
    p = 10 ** math.floor(math.log10(v))
    return next(m * p for m in (1, 2, 5, 10) if m * p >= v)


def _spark(trend):
    """表の中の小さい折れ線（話題度の推移、縦軸は 0〜100 で全作品共通）。最後の点だけ強調。"""
    if len(trend) < 2:
        return '<span class="na" title="推移はデータが 2 日分そろってから">—</span>'
    w, h, p = 112, 30, 4
    xs = [p + i * (w - 2 * p) / (len(trend) - 1) for i in range(len(trend))]
    ys = [h - p - s / 100 * (h - 2 * p) for _, s in trend]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    label = f"{_md_day(trend[0][0])} {trend[0][1]} → {_md_day(trend[-1][0])} {trend[-1][1]}"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="推移 {e(label)}">'
            f'<polyline points="{pts}"/><circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4"/></svg>')


def _chart(points, kind, color, unit, ymax=None, bands=(), partial_last=False, caption=""):
    """日ごとのグラフ。kind = "bar"（記事数）/ "line"（話題度・閲覧数）。points = [(日付, 値)]。
    図形は SVG を枠いっぱいに伸ばし（preserveAspectRatio="none"）、文字と端の点は HTML を % で重ねる：
    どの幅でも文字がつぶれない。縦軸は 1 本だけ、目盛りはきりのいい数、細い実線のグリッド。
    各日に透明な当たり判定（data-tip）を重ねる。"""
    if not points or not any(v for _, v in points):
        return f'<p class="empty">{e(caption)}：まだデータがありません</p>'
    W, H, L, R, T, B = 640, 168, 40, 44, 10, 24
    pw, ph = W - L - R, H - T - B
    top = ymax or _nice(max(v for _, v in points))
    n = len(points)
    band = pw / n
    y = lambda v: T + ph - v / top * ph
    svg, labels = [], []
    lab = lambda cls, x, yy, text: labels.append(
        f'<span class="cl {cls}" style="left:{x / W * 100:.2f}%;top:{yy / H * 100:.2f}%">{e(text)}</span>')
    for v, name in bands:  # 等級の境目（話題度）
        svg.append(f'<line class="band" x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        lab("bl", L + pw + 4, y(v), name)
    for t in ([0, 50, 100] if bands else [0, top / 2, top]):
        svg.append(f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        lab("yt", L - 6, y(t), _compact(t))
    for i, (d, _) in enumerate(points):
        if i == 0 or i == n - 1 or (n - 1 - i) % 7 == 0:
            lab("xt", L + band * (i + .5), H - B + 6, _md_day(d))
    if kind == "bar":
        bw = min(24, band - 2)
        for i, (d, v) in enumerate(points):
            if not v:
                continue
            x, top_y, base = L + band * i + (band - bw) / 2, y(v), T + ph
            r = min(4, base - top_y, bw / 2)
            cls = ' class="part"' if partial_last and i == n - 1 else ""
            svg.append(f'<path{cls} style="fill:var({color})" d="M{x:.1f},{base:.1f}V{top_y + r:.1f}Q{x:.1f},{top_y:.1f} {x + r:.1f},{top_y:.1f}'
                       f'H{x + bw - r:.1f}Q{x + bw:.1f},{top_y:.1f} {x + bw:.1f},{top_y + r:.1f}V{base:.1f}Z"/>')
    else:
        xs = [L + band * (i + .5) for i in range(n)]
        pts = [(x, y(v)) for x, (_, v) in zip(xs, points)]
        line = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
        svg.append(f'<polygon class="wash" style="fill:var({color})" points="{pts[0][0]:.1f},{T + ph} {line} {pts[-1][0]:.1f},{T + ph}"/>'
                   f'<polyline class="ln" style="stroke:var({color})" points="{line}"/>')
        labels.append(f'<span class="cd" style="left:{pts[-1][0] / W * 100:.2f}%;top:{pts[-1][1] / H * 100:.2f}%;background:var({color})"></span>')
        lab("end", pts[-1][0] + 8, pts[-1][1], _compact(points[-1][1]))
    for i, (d, v) in enumerate(points):  # 当たり判定：その日の列全体
        note = "（今日は集計途中）" if partial_last and i == n - 1 else ""
        svg.append(f'<rect class="hit" x="{L + band * i:.1f}" y="{T}" width="{band:.1f}" height="{ph}" '
                   f'data-tip="{_compact(v)} {e(unit)}{note}&#10;{_md_day(d)}"/>')
    return (f'<figure class="fig"><figcaption>{e(caption)}</figcaption><div class="plot">'
            f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{e(caption)}" preserveAspectRatio="none">{"".join(svg)}</svg>'
            f'{"".join(labels)}</div></figure>')


def _contrib(h):
    """話題度の内訳：各指標の寄与（点数 × 重み ÷ 重みの合計）を横に積む。合計がそのまま話題度。凡例つき。"""
    dims = h.get("dims") or []
    total_w = sum(d["weight"] for d in dims) or 1
    parts = [(d, d["score"] * d["weight"] / total_w) for d in dims]
    segs = "".join(f'<span class="seg" style="width:{c:.2f}%;background:var({HEAT_DIM_COLOR[d["key"]]})" '
                   f'data-tip="+{c:.1f} 点&#10;{e(d["name"])}（{d["score"]} 点 × 重み {d["weight"]}）"></span>'
                   for d, c in parts if c > 0)
    legend = "".join(
        f'<li><i style="background:var({HEAT_DIM_COLOR[d["key"]]})"></i><span class="dn">{e(d["name"])}</span>'
        f'<b>{d["score"]}</b><span class="dc">+{c:.1f}</span><small>{e(d["note"])}</small></li>' for d, c in parts)
    miss = (f'<p class="miss">データなし（計算から除外）：{e("・".join(h["missing"]))}</p>' if h.get("missing") else "")
    return (f'<div class="stack" role="img" aria-label="内訳">{segs}</div>'
            f'<ol class="legend"><li class="lh"><span></span><span class="dn">指標</span><b>点数</b><span class="dc">寄与</span><small>根拠</small></li>'
            f'{legend}</ol>{miss}')


def _delta_text(d):
    if d is None:
        return "—"
    return f"+{d}" if d > 0 else str(d)


def _heat_kpis(rows, a):
    scored = [h for _, h in rows if h["score"]]
    avg = sum(h["score"] for h in scored) / len(scored) if scored else 0
    deltas = [h["delta"] for h in scored if h.get("delta") is not None]
    avg_d = (f'<span class="kd">前週比 {_delta_text(round(sum(deltas) / len(deltas)))}</span>' if deltas
             else '<span class="kd">前週比はデータ集め中</span>')
    top_w, top_h = rows[0] if rows else (None, None)
    rising = [w["name"] for w, h in rows if h.get("rising")]
    wiki = sum(1 for _, h in rows if "public" in [d["key"] for d in h.get("dims") or []])
    fan = sum(1 for _, h in rows if "fandom" in [d["key"] for d in h.get("dims") or []])
    base = a.get("baseline_from")
    base_txt = ("4 週間の平常と比較" if base and base <= a["today"] else
                f'{_md_day(base)} から使えます' if base else "—")
    tiles = [
        ("対象", f"{len(rows)}", "作品", ""),
        ("平均話題度", f"{avg:.0f}", "/ 100", avg_d),
        ("首位", f'{top_h["score"]}' if top_h else "—", e(top_w["name"]) if top_w else "", ""),
        ("急上昇", f"{len(rising)}", "作品", f'<span class="kd">{e("・".join(rising[:3]))}</span>' if rising else '<span class="kd">なし</span>'),
        ("外部データ", f"{wiki}", f"/ {len(rows)} 作品", f'<span class="kd">Wikipedia あり · ファン指標 {fan} 作品</span>'),
        ("平常との比較", "準備中" if not (base and base <= a["today"]) else "有効", "", f'<span class="kd">{e(base_txt)}</span>'),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><span class="kl">{k}</span><span class="kv"><b>{v}</b><small>{u}</small></span>{extra}</div>'
        for k, v, u, extra in tiles) + "</div>"


def _heat_table(rows):
    head = "".join(f'<th scope="col" class="hm"><button type="button" data-sort="{k}">{e(lab)}<small>×{w}</small></button></th>'
                   for k, lab, w in heat.DIMS)
    body = []
    for i, (w, h) in enumerate(rows, 1):
        dims = {d["key"]: d for d in h.get("dims") or []}
        cells = "".join(
            (f'<td class="hm {_seq(dims[k]["score"])}" data-label="{e(lab)}" data-v="{dims[k]["score"]}" '
             f'data-tip="{dims[k]["score"]}&#10;{e(lab)} · {e(dims[k]["note"])}">{dims[k]["score"]}</td>') if k in dims else
            f'<td class="hm na" data-label="{e(lab)}" data-v="-1" data-tip="—&#10;{e(lab)} · データなし（計算から除外）">—</td>'
            for k, lab, _ in heat.DIMS)
        cls, arrow, why = _trend(h.get("delta"))
        rise = '<em class="rise">急上昇</em>' if h.get("rising") else ""
        body.append(
            f'<tr data-score="{h["score"]}" data-delta="{h["delta"] if h.get("delta") is not None else -999}" data-rank="{i}">'
            f'<td class="rk">{i}</td>'
            f'<th scope="row" class="nm"><a href="#h-{_wid(w["name"])}">{e(w["name"])}</a>'
            f'<small><i style="background:{_sec_color(w.get("section"))}"></i>{e(_sec_name(w.get("section")))}</small>{rise}</th>'
            f'<td class="sc"><b>{h["score"]}</b><span class="mt" style="--v:{h["score"] / 100:.2f}" aria-hidden="true"></span>'
            f'<small>{e(h["label"] or "—")}</small></td>'
            f'<td class="dl {cls}" title="{e(why)}">{_delta_text(h.get("delta"))}</td>'
            f"{cells}<td class=\"sp\">{_spark(h.get('trend') or [])}</td></tr>")
    return (f'<div class="tw"><table class="rank"><thead><tr><th scope="col" class="rk">#</th><th scope="col" class="nm">作品</th>'
            f'<th scope="col" class="sc"><button type="button" data-sort="score" aria-pressed="true">話題度</button></th>'
            f'<th scope="col" class="dl"><button type="button" data-sort="delta">前週比</button></th>{head}'
            f'<th scope="col" class="sp">推移</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<div class="scale" aria-hidden="true"><span>指標の点数</span>'
            + "".join(f'<i class="{_seq(v)}">{v}〜</i>' for v in (0, 20, 40, 60, 80)) + '<i class="na">—</i><span>データなし</span></div>')


def _heat_movers(rows):
    """前週比のダイバージング棒（上がった＝赤、下がった＝青、真ん中が 0）。比べられないときは説明だけ。"""
    have = sorted(((w, h) for w, h in rows if h.get("delta") is not None), key=lambda r: -r[1]["delta"])
    if not have:
        return ('<p class="empty">前週比は、7 日前の時点で 1 週間分の連続した収集データがそろってから出します。'
                'それまでの比較相手は、さかのぼって集めた古い記事だけで数が少なく、実際より上がって見えるためです。</p>')
    span = max(abs(h["delta"]) for _, h in have) or 1
    items = []
    for w, h in have:
        d = h["delta"]
        pct = abs(d) / span * 50
        side = "up" if d > 0 else "down" if d < 0 else "zero"
        items.append(f'<li data-tip="{_delta_text(d)}&#10;{e(w["name"])} · {h["score"]} 点"><span class="mn">{e(w["name"])}</span>'
                     f'<span class="mbar"><i class="{side}" style="width:{pct:.1f}%"></i></span><b>{_delta_text(d)}</b></li>')
    return f'<ol class="movers">{"".join(items)}</ol>'


def _heat_card(w, h):
    cls, arrow, why = _trend(h.get("delta"))
    rise = '<em class="rise">急上昇</em>' if h.get("rising") else ""
    trend = h.get("trend") or []
    charts = _chart(trend, "line", "--ink", "点", ymax=100,
                    bands=[(low, lab) for low, lab in heat.LEVELS if low > 1], caption="話題度の推移（連続収集を始めた日から）")
    charts += _chart(h.get("articles") or [], "bar", "--viz-1", "件", partial_last=True, caption=f"1 日の記事数（直近 {heat.TREND_DAYS} 日）")
    if h.get("wiki"):
        charts += _chart(h["wiki"], "line", "--viz-5", "回", caption="Wikipedia の閲覧数（1 日・集計は 1〜2 日遅れ）")
    by_day = {}
    for col, series in ((0, trend), (1, h.get("articles") or []), (2, h.get("wiki") or [])):
        for d, v in series:
            by_day.setdefault(d, ["—", "—", "—"])[col] = _compact(v)
    table = "".join(f"<tr><th scope=\"row\">{_md_day(d)}</th><td>{a}</td><td>{b}</td><td>{c}</td></tr>"
                    for d, (a, b, c) in sorted(by_day.items(), reverse=True))
    return (f'<article class="hcard" id="h-{_wid(w["name"])}" style="--sc:{_sec_color(w.get("section"))}">'
            f'<header><div class="ht"><span class="hsec"><i></i>{e(_sec_name(w.get("section")))}</span>'
            f'<h3>{e(w["name"])}</h3>' + (f'<span class="hsub">{e(w["subtitle"])}</span>' if w.get("subtitle") else "") + '</div>'
            f'<div class="hs"><b>{h["score"]}</b><span><em>{e(h["label"] or "—")}</em><small class="{cls}">{e(why)}</small>{rise}</span></div>'
            f'<a class="jump" href="./#{_wid(w["name"])}">記事を見る →</a></header>'
            f'<div class="hbody"><div class="hl">{_contrib(h)}</div><div class="hr">{charts}'
            f'<details class="tv"><summary>数値を表で見る</summary><table><thead><tr><th scope="col">日付</th><th scope="col">話題度</th>'
            f'<th scope="col">記事数</th><th scope="col">閲覧数</th></tr></thead><tbody>{table}</tbody></table></details></div></div></article>')


def _heat_method(a):
    dims = "".join(
        f'<tr><td><i style="background:var({HEAT_DIM_COLOR[k]})"></i>{e(lab)}</td><td class="n">{w}</td>'
        f'<td>{e(HEAT_DIM_ABOUT[k][0])}</td><td>{e(HEAT_DIM_ABOUT[k][1])}</td></tr>' for k, lab, w in heat.DIMS)
    refs = "".join(f'<li><span>{e(HEAT_REF_LABEL[k][0])}</span><b>{e(HEAT_REF_LABEL[k][1].format(_compact(v)))}</b></li>'
                   for k, v in heat.REF.items() if k in HEAT_REF_LABEL)
    levels = " · ".join(f"{low} 点以上「{lab}」" for low, lab in heat.LEVELS if low > 1) + " · それ未満「静か」"
    rel = round(heat.REL_SHARE * 100)
    return f"""<div class="method">
<div class="mcol">
<h3>計算式</h3>
<p class="eq">話題度 = Σ（指標の点数 × 重み）÷ Σ（使えた指標の重み）</p>
<p>各指標（出来事・勢い以外）の点数 = <b>{rel}%</b>「この作品のいつも」との比較 + <b>{100 - rel}%</b>「全作品共通の物差し」。</p>
<ul class="fx">
<li><span>いつもとの比較</span><code>50 + 25 × log₂（(今週 + 1) ÷ (平常 + 1)）</code><small>平常並み 50 点、2 倍 75 点、4 倍で満点。今週ゼロは 0 点。平常 = 過去 4 週間の週平均</small></li>
<li><span>共通の物差し</span><code>100 × log(1 + 値) ÷ log(1 + 満点の値)</code><small>対数目盛り。作品数が増減しても変わらないので、日をまたいで比べられる</small></li>
<li><span>出来事</span><code>重要ニュース 40〜60 + 状態の変化 30 + 予定 0〜30 + 大きな記事 0〜20</code><small>上限 100。予定は近いほど高い（{heat.EVENT_SOON} 日前から）</small></li>
<li><span>勢い</span><code>50 + 25 × log₂（昨日まで 2 日の速さ ÷ その前 5 日の速さ）</code><small>記事と Wikipedia の平均。{heat.RISING} 点以上かつ話題度 30 以上で「急上昇」</small></li>
</ul>
<p>等級：{e(levels)}。データのない指標は 0 点にせず、計算から外して残りの重みで割ります（各作品の内訳に明記）。
自分の 👍 / 👎 は入れていません。話題度は世の中の盛り上がりだけを表します。</p>
</div>
<div class="mcol">
<h3>指標と重み</h3>
<table class="dims"><thead><tr><th scope="col">指標</th><th scope="col">重み</th><th scope="col">何を測るか</th><th scope="col">データ</th></tr></thead><tbody>{dims}</tbody></table>
<h3>共通の物差しの満点</h3>
<ul class="refs">{refs}</ul>
<h3>更新と限界</h3>
<ul class="notes">
<li>記事・Steam・AniList・TMDB は 2 時間ごと、Wikipedia は 1 日 1 回取得。点数はページを作るたびに計算し直します。</li>
<li>「平常」は連続して収集を始めた日から数えます（{e(_md_day(a["baseline_from"])) + " ごろから" if a.get("baseline_from") else "準備中"}使えます）。それまでは「いつもとの比較」を平常並み（50 点）として扱います。</li>
<li>収集は 1 回あたり最大 30 記事なので、非常に報道の多い作品では記事数が頭打ちになります。</li>
<li>Reddit の投稿が一度もない作品はファンの反応を計算に入れません（日本の商品などは Reddit で話題になりにくいため）。</li>
</ul>
</div>
</div>"""


THEMES_PAGE_CSS = """
.tlist{display:grid;gap:34px;margin:18px 0 40px}
.tlist .sec{scroll-margin-top:16px}
.tlist .pic{aspect-ratio:16/9}
.tlist .mini .pic{aspect-ratio:4/3}
.tuse{margin:0;padding:0 26px 20px;font-size:13px;line-height:1.7;opacity:.85}
.tuse b{font:700 var(--fs-label) var(--font-sans);letter-spacing:.1em;margin-right:6px}
.fxlist{list-style:none;margin:14px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;--ac:var(--rose);--bg:var(--card);--fg:var(--ink)}
.fxlist li{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;gap:2px 12px;align-items:center;padding:12px 14px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow)}
.fxlist .vt{position:static;grid-row:span 2;margin:0;padding:0;height:auto}
.fxlist .vt button{min-height:36px;padding:0 8px;opacity:.85}
.fxlist b{font:900 15px/1.3 var(--font-sans)}
.fxlist small{font-size:11px;line-height:1.4;opacity:.75}
@media (max-width:600px){.tuse{padding:0 14px 16px}}
"""
HEAT_PAGE_CSS = """
.page{display:flex;flex-direction:column;align-items:stretch;max-width:1240px}
.back{display:inline-flex;align-items:center;gap:8px;font:700 12px var(--font-mono);letter-spacing:.12em}.back:hover{color:var(--rose)}
.lede{margin:0;max-width:760px;font-size:15px;line-height:1.8}
.panel{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:20px 22px}
.panel>h2.sh{margin-bottom:16px}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:0;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow)}
.kpi{display:flex;flex-direction:column;gap:4px;padding:14px 16px;border-left:1px solid var(--hair);min-width:0}
.kpi:first-child{border-left:0}
.kl{font:700 var(--fs-label) var(--font-sans);letter-spacing:.08em;opacity:.8}
.kv{display:flex;align-items:baseline;gap:6px;min-width:0}
.kv b{font:700 34px/1.1 var(--font-sans);letter-spacing:-.01em}
.kv small{font:700 12px var(--font-sans);opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kd{font:500 12px/1.45 var(--font-sans);opacity:.75}
.tw{overflow:visible}
table.rank{width:100%;border-collapse:collapse;font-size:13px}
.rank th,.rank td{padding:7px 6px;border-bottom:1px solid var(--hair);text-align:left;vertical-align:middle}
.rank thead th{font:700 var(--fs-label) var(--font-sans);letter-spacing:.04em;border-bottom:2px solid var(--ink);white-space:nowrap}
.rank thead button{all:unset;cursor:pointer;display:inline-flex;align-items:baseline;gap:3px}
.rank thead button small{font:500 var(--fs-tag) var(--font-mono);opacity:.8}
.rank thead button:hover,.rank thead button[aria-pressed="true"]{text-decoration:underline;text-underline-offset:4px}
.rank thead button:focus-visible{outline:2px solid var(--rose);outline-offset:2px}
.rank td.rk{width:28px;font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;opacity:.8}
.rank .nm{min-width:150px}
.rank .nm a{font:900 14px/1.35 var(--font-sans)}.rank .nm a:hover{color:var(--rose);text-decoration:underline}
.rank .nm small{display:flex;align-items:center;gap:5px;margin-top:2px;font:500 var(--fs-label) var(--font-sans);opacity:.75}
.rank .nm small i,.hsec i,.method td i{display:inline-block;width:8px;height:8px;border-radius:2px;flex:none}
.rise{display:inline-block;margin-top:3px;padding:0 7px;background:var(--alert);color:#FFF;font:900 var(--fs-tag)/1.6 var(--font-sans);font-style:normal;letter-spacing:.08em}
.rank td.sc{width:132px;white-space:nowrap}
.rank td.sc b{display:inline-block;width:30px;font:700 18px var(--font-mono);font-variant-numeric:tabular-nums}
.rank td.sc .mt{display:inline-block;vertical-align:middle;width:56px;height:8px;border-radius:0 4px 4px 0;
 background:linear-gradient(90deg,var(--ink) calc(var(--v) * 100%),color-mix(in srgb,var(--ink) 10%,transparent) 0)}
.rank td.sc small{display:block;font:500 var(--fs-label) var(--font-sans);opacity:.8}
.rank td.dl{width:58px;font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.rank td.dl.up{color:var(--alert)}
.rank td.hm{width:62px;text-align:center;font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;border:2px solid var(--card)}
.q0{background:var(--seq-0);color:var(--ink)}.q1{background:var(--seq-1);color:var(--ink)}.q2{background:var(--seq-2);color:var(--ink)}
.q3{background:var(--seq-3);color:#FFF}.q4{background:var(--seq-4);color:#FFF}
td.na,.scale i.na{background:repeating-linear-gradient(45deg,transparent 0 4px,color-mix(in srgb,var(--ink) 9%,transparent) 4px 5px);color:color-mix(in srgb,var(--ink) 55%,transparent)}
.rank td.hm:hover{outline:2px solid var(--ink);outline-offset:-2px}
.rank td.sp{width:120px}
.spark{display:block}.spark polyline{fill:none;stroke:color-mix(in srgb,var(--ink) 55%,transparent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark circle{fill:var(--rose);stroke:var(--card);stroke-width:2}
.na{opacity:.5}
.scale{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:12px;font:500 var(--fs-label) var(--font-sans)}
.scale i{display:inline-block;min-width:40px;padding:1px 6px;text-align:center;font:700 var(--fs-label) var(--font-mono);font-style:normal}
.scale span{opacity:.75}
.movers{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px;max-width:760px}
.movers li{display:grid;grid-template-columns:150px minmax(0,1fr) 44px;gap:10px;align-items:center;font-size:13px}
.mn{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mbar{position:relative;height:14px;background:linear-gradient(90deg,transparent calc(50% - .5px),var(--ink) calc(50% - .5px) calc(50% + .5px),transparent 0)}
.mbar i{position:absolute;top:2px;height:10px}
.mbar i.up{left:50%;background:var(--up);border-radius:0 4px 4px 0}
.mbar i.down{right:50%;background:var(--down);border-radius:4px 0 0 4px}
.movers b{font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;text-align:right}
.empty{margin:0;padding:14px 16px;border:1px dashed var(--hair);font-size:13px;line-height:1.7;opacity:.85}
.cards{display:flex;flex-direction:column;gap:22px}
.hcard{background:var(--card);border:2px solid var(--ink);border-top:6px solid var(--sc);box-shadow:var(--shadow);scroll-margin-top:16px}
.hcard header{display:flex;flex-wrap:wrap;align-items:center;gap:10px 24px;padding:16px 20px 14px;border-bottom:1px solid var(--hair)}
.ht{display:flex;flex-direction:column;gap:2px;min-width:0}
.hsec{display:inline-flex;align-items:center;gap:6px;font:700 var(--fs-label) var(--font-sans);letter-spacing:.06em;opacity:.8}
.hsec i{background:var(--sc)}
.hcard h3{margin:0;font:900 22px/1.3 var(--font-sans)}
.hsub{font:700 12px/1.4 var(--font-sans);opacity:.8}
.hs{display:flex;align-items:center;gap:12px;margin-left:auto}
.hs b{font:700 48px/1 var(--font-sans);letter-spacing:-.02em}
.hs span{display:flex;flex-direction:column;align-items:flex-start;gap:2px}
.hs em{font:900 14px var(--font-sans);font-style:normal}
.hs small{font:500 12px var(--font-sans);opacity:.75}.hs small.up{color:var(--alert);opacity:1}
.jump{font:700 12px var(--font-sans);border-bottom:1.5px solid currentColor}.jump:hover{color:var(--rose)}
.hbody{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:8px 28px;padding:18px 20px 16px}
.stack{display:flex;height:16px;background:color-mix(in srgb,var(--ink) 8%,transparent);border-radius:0 4px 4px 0;overflow:hidden}
.seg{height:100%;border-right:2px solid var(--card)}
.seg:last-child{border-radius:0 4px 4px 0}
.seg:hover{filter:brightness(1.1)}
.legend{list-style:none;margin:14px 0 0;padding:0;display:flex;flex-direction:column}
.legend li{display:grid;grid-template-columns:12px 84px 32px 44px minmax(0,1fr);gap:4px 8px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--hair);font-size:13px}
.legend li i{width:10px;height:10px;border-radius:2px;align-self:center}
.legend .lh{font:700 var(--fs-label) var(--font-sans);opacity:.8;border-bottom:1.5px solid var(--ink)}
.legend .lh b,.legend .lh .dc{font:700 var(--fs-label) var(--font-sans)}
.dn{font-weight:700}
.legend b{font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;text-align:right}
.dc{font:500 12px var(--font-mono);font-variant-numeric:tabular-nums;text-align:right;opacity:.75}
.legend small{font:500 12px/1.5 var(--font-sans);opacity:.8}
.miss{margin:10px 0 0;font:500 12px/1.5 var(--font-sans);opacity:.75}
.fig{margin:0 0 12px}
.fig figcaption{font:700 12px var(--font-sans);margin-bottom:2px}
.plot{position:relative}
.chart{display:block;width:100%;height:168px;overflow:visible}
.cl{position:absolute;font:500 11px/1 var(--font-mono);color:color-mix(in srgb,var(--ink) 70%,transparent);white-space:nowrap;pointer-events:none}
.cl.yt{transform:translate(-100%,-50%)}.cl.xt{transform:translate(-50%,0)}.cl.bl{transform:translate(0,-50%);font-family:var(--font-sans)}
.cl.end{transform:translate(0,-50%);color:var(--ink);font-weight:700}
.cd{position:absolute;width:8px;height:8px;border-radius:50%;transform:translate(-50%,-50%);box-shadow:0 0 0 2px var(--card);pointer-events:none}
.chart .grid{stroke:color-mix(in srgb,var(--ink) 12%,transparent);stroke-width:1;vector-effect:non-scaling-stroke}
.chart .band{stroke:color-mix(in srgb,var(--ink) 22%,transparent);stroke-width:1;vector-effect:non-scaling-stroke}
.chart .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.chart .wash{fill-opacity:.1}
.chart .part{fill-opacity:.4}
.chart .hit{fill:transparent}.chart .hit:hover{fill:color-mix(in srgb,var(--ink) 7%,transparent)}
.tv summary{cursor:pointer;font:700 12px var(--font-sans);opacity:.8}
.tv table{margin-top:8px;border-collapse:collapse;font:500 12px var(--font-mono);font-variant-numeric:tabular-nums}
.tv th,.tv td{padding:3px 12px 3px 0;text-align:right;border-bottom:1px solid var(--hair)}
.tv thead th{font-family:var(--font-sans);font-weight:700}
.method{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px 36px;font-size:14px;line-height:1.75}
.method h3{margin:0 0 8px;font:900 15px var(--font-sans);padding-bottom:4px;border-bottom:1.5px solid var(--ink)}
.method h3:not(:first-child){margin-top:20px}
.method p{margin:0 0 10px}
.eq{font:700 14px var(--font-mono);padding:10px 12px;background:var(--sheet);border-left:4px solid var(--ink)}
.fx{list-style:none;margin:0 0 12px;padding:0;display:flex;flex-direction:column;gap:10px}
.fx li{display:flex;flex-direction:column;gap:2px}
.fx span{font:700 13px var(--font-sans)}
.fx code{font:500 13px var(--font-mono);overflow-wrap:anywhere}
.fx small{font-size:12px;opacity:.75}
table.dims{width:100%;border-collapse:collapse;font-size:12px;line-height:1.55}
.dims th,.dims td{padding:6px 6px 6px 0;border-bottom:1px solid var(--hair);text-align:left;vertical-align:top}
.dims thead th{border-bottom:1.5px solid var(--ink);white-space:nowrap}
.dims td:first-child{white-space:nowrap;font-weight:700}.dims td i{margin-right:6px}
.dims td.n{font:700 12px var(--font-mono);text-align:right;padding-right:12px}
.refs,.notes{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px;font-size:13px}
.refs li{display:flex;justify-content:space-between;gap:12px;padding:3px 0 4px;border-bottom:1px dashed var(--hair)}
.refs span{font:500 12px var(--font-mono);opacity:.75}
.notes li{padding-left:14px;position:relative}.notes li::before{content:"";position:absolute;left:0;top:.75em;width:6px;height:2px;background:var(--ink)}
.vtip{position:fixed;z-index:20;pointer-events:none;display:flex;flex-direction:column;gap:2px;max-width:280px;padding:7px 10px;
 background:var(--ink);color:var(--card);font:500 12px/1.45 var(--font-sans);box-shadow:3px 3px 0 var(--rose)}
.vtip b{font:700 16px var(--font-mono)}
@media (max-width:1100px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.kpi:nth-child(4){border-left:0}.kpi:nth-child(n+4){border-top:1px solid var(--hair)}
 .hbody,.method{grid-template-columns:minmax(0,1fr)}}
@media (max-width:860px){
 .rank thead{display:none}
 .rank,.rank tbody{display:block}
 /* スマホ：1 作品 = 3 段（名前・話題度・前週比 / 6 指標のマス / 推移）。横にスクロールさせない */
 .rank tr{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px 3px;padding:12px 0;border-bottom:1px solid var(--hair)}
 .rank th,.rank td{border:0;padding:0}
 .rank td.rk{display:none}
 .rank .nm{grid-column:1/5;min-width:0}
 .rank td.sc{grid-column:5/6;width:auto;text-align:right}.rank td.sc b{width:auto}.rank td.sc .mt{display:none}
 .rank td.dl{grid-column:6/7;width:auto;text-align:right;padding-top:3px}
 .rank td.hm{width:auto;border:0;padding:3px 0 4px;font-size:12px}
 .rank td.hm::before{content:attr(data-label);display:block;font:700 var(--fs-tag)/1.3 var(--font-sans);letter-spacing:0;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 2px}
 .rank td.sp{grid-column:1/-1;width:auto}
 .panel{padding:16px 14px}.hbody{padding:14px}.hcard header{padding:14px}
 .movers li{grid-template-columns:96px minmax(0,1fr) 40px}
 .cl.bl{display:none}  /* 狭い画面では等級の名前を省く（線は残す。等級は計算方法に書いてある） */
 .legend li{grid-template-columns:12px 76px 28px 40px minmax(0,1fr)}
}
@media (max-width:560px){.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.kpi{border-left:0!important;border-top:1px solid var(--hair)}.kpi:nth-child(-n+2){border-top:0}
 .kpi:nth-child(even){border-left:1px solid var(--hair)!important}.kv b{font-size:28px}.hs b{font-size:40px}
 .legend li{grid-template-columns:12px minmax(0,1fr) 28px 40px}.legend small{grid-column:2/5}.legend .lh small{display:none}}
"""

HEAT_PAGE_JS = """
(function(){
  var tip=document.createElement('div');tip.className='vtip';tip.hidden=true;document.body.appendChild(tip);
  function show(el,x,y){
    var lines=(el.getAttribute('data-tip')||'').split('\\n');tip.textContent='';
    var b=document.createElement('b');b.textContent=lines[0];tip.appendChild(b);
    lines.slice(1).forEach(function(s){var d=document.createElement('span');d.textContent=s;tip.appendChild(d);});
    tip.hidden=false;var r=tip.getBoundingClientRect();
    var nx=Math.max(8,Math.min(x+14,innerWidth-r.width-8)),ny=y-r.height-12;if(ny<8)ny=y+18;
    tip.style.left=nx+'px';tip.style.top=ny+'px';
  }
  document.addEventListener('pointermove',function(ev){
    var el=ev.target.closest&&ev.target.closest('[data-tip]');if(!el){tip.hidden=true;return;}show(el,ev.clientX,ev.clientY);
  });
  document.addEventListener('scroll',function(){tip.hidden=true;},{passive:true});
  // 表の並べ替え：話題度・前週比・各指標（同点は今の順位のまま）
  var tbody=document.querySelector('.rank tbody');
  document.querySelectorAll('.rank thead button[data-sort]').forEach(function(btn){
    btn.addEventListener('click',function(){
      var k=btn.dataset.sort,rows=[].slice.call(tbody.rows);
      var val=function(tr){
        if(k==='score')return +tr.dataset.score;if(k==='delta')return +tr.dataset.delta;
        var i=[].indexOf.call(btn.closest('tr').children,btn.closest('th'));return +tr.children[i].dataset.v;
      };
      rows.sort(function(a,b){return val(b)-val(a)||(+a.dataset.rank)-(+b.dataset.rank);});
      rows.forEach(function(tr,i){tr.children[0].textContent=i+1;tbody.appendChild(tr);});
      document.querySelectorAll('.rank thead button').forEach(function(x){x.setAttribute('aria-pressed',String(x===btn));});
    });
  });
})();
"""


# テーマ見本（docs/themes.html）：30 のテーマと 20 の 👍 演出を、本物の版面と同じ部品で並べる
SAMPLE_THEMES = [  # まだどの作品も使っていないテーマの見本の色
    {"bg": "#14161F", "fg": "#F1EEE6", "accent": "#F2B544", "alt_bg": "#F1EEE6", "alt_fg": "#14161F", "alt_accent": "#B5452B"},
    {"bg": "#F7F3EA", "fg": "#1F2430", "accent": "#C2402F", "alt_bg": "#1F2430", "alt_fg": "#F7F3EA", "alt_accent": "#F29E8E"},
    {"bg": "#0F2A3D", "fg": "#EEF4F7", "accent": "#5FD3C6", "alt_bg": "#EEF4F7", "alt_fg": "#0F2A3D", "alt_accent": "#1F7A72"},
    {"bg": "#FFF3F6", "fg": "#3A1F2B", "accent": "#C93C6E", "alt_bg": "#C93C6E", "alt_fg": "#FFFFFF", "alt_accent": "#FFD3E1"},
]
THEMES_PAGE_JS = """
document.querySelectorAll('.vt').forEach(box => box.addEventListener('click', ev => {
  const btn = ev.target.closest('button[data-vote]'); if (!btn) return;
  ev.preventDefault();
  const on = btn.getAttribute('aria-pressed') !== 'true';
  box.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false'));
  btn.setAttribute('aria-pressed', String(on));
  window.likeFx(btn, on ? Number(btn.dataset.vote) : 0, (btn.closest('[data-fx]') || {}).dataset.fx, null);
}));
"""


def render_themes(items, updated):
    """テーマ見本ページ。items = [{name, motif, theme}]（items.yaml）。押しても保存しない、試すだけの 👍。"""
    users = {}
    for it in items:
        if it.get("motif") in MOTIFS:
            users.setdefault(it["motif"], []).append(it)
    btns = f'<span class="vt">{_vote_buttons()}</span>'
    secs = []
    for k, t in enumerate(TEMPLATES):
        used = users.get(t["id"], [])
        pal = next((u["theme"] for u in used if isinstance(u.get("theme"), dict)), None) or SAMPLE_THEMES[k % len(SAMPLE_THEMES)]
        c = _legible({**SAMPLE_THEMES[0], **pal})
        style = (f"--bg:{c['bg']};--fg:{c['fg']};--acc:{c['accent']};--abg:{c['alt_bg']};--afg:{c['alt_fg']};--aacc:{c['alt_accent']};"
                 f"--line:color-mix(in srgb,{c['fg']} 22%,{c['bg']})")
        fx = TEMPLATE_FX.get(t["id"], "pop")
        who = "・".join(u["name"] for u in used) or "まだ使っていません"
        card = lambda cls, h: (f'<article class="card m {cls}"><div class="pic"><span class="ph">{e(t.get("ja") or t["id"])}</span></div>'
                               f'<span class="when"><b>NEW</b>10.16<span class="from">example.com</span>{btns}</span><h3>{h}</h3></article>')
        secs.append(
            f'<section class="sec m-{t["id"]}" data-fx="{fx}" style="{style}" id="t-{t["id"]}">'
            f'<div class="band">{MOTIFS.get(t["id"], "")}<span class="title">{e(t["id"])}</span>'
            f'<span class="sub">{e(t.get("ja") or t["id"])} · 👍「{e(likefx.FX[fx][0])}」</span></div>'
            f'<div class="grid">{card("c8 lead", "見出しのサンプル：ここにニュースの見出しが入ります")}'
            f'<div class="side">{card("mini c4", "小さいカードの見出し")}{card("mini c4", "もう一つの見出し")}</div></div>'
            f'<p class="tuse"><b>使っている作品</b> {e(who)}</p></section>')
    fxs = "".join(f'<li data-fx="{k}"><span class="vt">{_vote_buttons()}</span><b>{e(v[0])}</b><small>{e(k)} · {e(v[1])}</small></li>'
                  for k, v in likefx.FX.items())
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>テーマ見本</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}{THEMES_PAGE_CSS}</style>
{LIKEFX_HEAD}
</head>
<body>
<div class="page">
<header class="mast"><div class="mtitle"><h1>テーマ見本</h1><span class="stamp">ウォッチリスト通信</span></div>
<div class="tools"><div class="meta"><small>テーマ</small><b>{len(TEMPLATES)}</b></div><div class="meta"><small>👍 演出</small><b>{len(likefx.FX)}</b></div>
<div class="meta"><small>更新</small><b>{e(updated)}</b></div></div></header>
<a class="back" href="./">← ウォッチリスト通信に戻る</a>
<p class="lede">各作品の版面は、この中のテーマ（背景の柄・題字の形・写真の枠・👍 を押したときの演出）を一つ使います。
色は作品ごとに違うので、同じテーマでも作品によって雰囲気が変わります。👍 を押すと演出を試せます（ここでは保存しません）。</p>
<section class="panel" id="fx"><h2 class="sh"><span>👍 の演出</span><small>{len(likefx.FX)} 種類 · 押して試す</small></h2><ul class="fxlist">{fxs}</ul></section>
<h2 class="sh"><span>テーマ一覧</span><small>{len(TEMPLATES)} 種類</small></h2>
<div class="tlist">{"".join(secs)}</div>
</div>
<script>{LIKEFX_JS}</script><script>{THEMES_PAGE_JS}</script>
</body>
</html>
"""


def render_heat(analysis, works, updated):
    """話題度の分析ページ（docs/heat.html）。analysis = heat.analyze の結果、works = collect の結果（名前・ジャンルの順）。"""
    items = analysis.get("items") or {}
    rows = sorted(((w, items[w["name"]]) for w in works if w["name"] in items),
                  key=lambda r: (-r[1]["score"], r[0]["name"]))
    today = analysis.get("today") or ""
    cards = "".join(_heat_card(w, h) for w, h in rows)
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>話題度アナリシス</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}</style>
</head>
<body>
<div class="page">
<header class="mast">
<div class="mtitle"><h1>話題度アナリシス</h1><span class="stamp">ウォッチリスト通信</span></div>
<div class="tools"><div class="meta"><small>基準日</small><b>{e(today.replace("-", "."))}</b></div>
<div class="meta"><small>更新</small><b>{e(updated)}</b></div></div>
</header>
<a class="back" href="./">← ウォッチリスト通信に戻る</a>
<p class="lede">ウォッチリストの各作品が、いま世の中でどれだけ話題になっているかを 0〜100 で表した指数です。
報道量・広がり・出来事・勢い・一般の関心（Wikipedia）・ファンの反応の 6 つの指標から計算します。数字にカーソルを合わせると根拠が出ます。</p>
{_heat_kpis(rows, analysis)}
<section class="panel" id="ranking"><h2 class="sh"><span>ランキング</span><small>指標の列見出しで並べ替え · ×は重み</small></h2>{_heat_table(rows)}</section>
<section class="panel" id="movers"><h2 class="sh"><span>前週比</span><small>7 日前の話題度との差</small></h2>{_heat_movers(rows)}</section>
<section id="detail"><h2 class="sh"><span>作品ごとの内訳</span><small>点数の内訳・推移・記事数・閲覧数</small></h2></section>
<div class="cards">{cards}</div>
<section class="panel" id="method"><h2 class="sh"><span>計算方法</span><small>METHODOLOGY</small></h2>{_heat_method(analysis)}</section>
</div>
<script>{HEAT_PAGE_JS}</script>
</body>
</html>
"""


# ---------- 管理ページ（docs/admin.html）：見るだけ。口令なし・ボタンで何かを変えることはしない ----------
# 生成時に分かるもの（収集・編集の状況、作品ごとの記事数、投票）は HTML に書き込み、
# その場で変わるもの（GitHub Actions の実行結果、設定ページの依頼、写真の受付）はページを開いたときに読む。
ADMIN_WORKFLOWS = {"digest.yml": "収集・出刊", "render.yml": "ページの再生成", "requests.yml": "設定ページの依頼", "ci.yml": "テスト"}
ADMIN_STALE_DAYS = 3  # 最新の記事がこれより古い作品は「止まっているかも」


def _ago(days):
    if days is None:
        return "記事なし"
    return "今日" if days <= 0 else "昨日" if days == 1 else f"{days} 日前"


def _admin_pipeline(p):
    edits = p.get("unedited") or []
    tiles = [
        ("最新号", e(_md_day(p["report"])) if p.get("report") else "—", "", f'<span class="kd">更新 {e(p.get("updated") or "")}</span>'),
        ("収集", e(_md_day(p["inbox"])) if p.get("inbox") else "—", "",
         f'<span class="kd">今日 {p.get("today_entries", 0)} 件 · 7 日 {p.get("week_entries", 0)} 件</span>'),
        ("AI 編集", "済" if not edits else f"{len(edits)}", "" if not edits else "日分 未編集",
         '<span class="kd">' + (e("・".join(_md_day(d) for d in edits[:4])) if edits else "最新の収集まで編集済み") + "</span>"),
        ("止まっている作品", f'{p.get("stale", 0)}', f'/ {p.get("items", 0)} 作品',
         f'<span class="kd">{ADMIN_STALE_DAYS} 日以上 新しい記事なし</span>'),
        ("週報", e(p.get("weekly") or "—"), "", '<span class="kd">Discord に最後に送った日時</span>'),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><span class="kl">{k}</span><span class="kv"><b>{v}</b><small>{u}</small></span>{x}</div>'
        for k, v, u, x in tiles) + "</div>"


def _admin_items(rows):
    if not rows:
        return '<p class="empty">ウォッチ項目がありません。</p>'
    out = []
    for r in rows:
        sc = _sec_color(r.get("section") or "其他")
        heat_ = r.get("heat")
        heat_txt = (f'<b>{heat_["score"]}</b><small>{_delta_text(heat_["delta"])}</small>' if heat_ and heat_.get("delta") is not None
                    else f'<b>{heat_["score"]}</b>' if heat_ else '<span class="na">—</span>')
        miss = "".join(f'<i class="chip">{e(m)}</i>' for m in r.get("missing") or []) or '<span class="ok">そろっている</span>'
        web = '<i class="chip web">設定ページから追加</i>' if r.get("web") else ""
        stale = r.get("last_days") is None or r["last_days"] >= ADMIN_STALE_DAYS
        out.append(
            f'<tr><td class="nm"><a href="index.html#{_wid(r["name"])}">{e(r["name"])}</a>'
            f'<small><i style="background:{sc}"></i>{e(_sec_name(r.get("section") or "其他"))} · {e(r.get("type") or "")}</small></td>'
            f'<td class="sz" data-label="篇幅">{e(r.get("size") or "M")}</td>'
            f'<td class="n" data-label="7 日">{r.get("week", 0)}</td>'
            f'<td class="n" data-label="速報">{r.get("urgent", 0) or "—"}</td>'
            f'<td class="last{" stale" if stale else ""}" data-label="最新">{e(_ago(r.get("last_days")))}</td>'
            f'<td class="hz" data-label="話題度">{heat_txt}</td>'
            f'<td class="ms">{web}{miss}</td></tr>')
    return ('<div class="tw"><table class="adm"><thead><tr><th>作品</th><th>篇幅</th><th>7 日の記事</th><th>速報</th>'
            '<th>最新の記事</th><th>話題度</th><th>未設定の項目</th></tr></thead><tbody>' + "".join(out) + "</tbody></table></div>")


BG_STATES = {"ok": "済", "wait": "待ち", "review": "要確認", "failed": "失敗", "idle": "—"}
# 「バックグラウンド」の表の列：(セルのキー, 見出し, 時刻を出すプロセスの id)。版面の設計は AI 編集の回にやる
BG_COLS = (("collect", "収集", "collect"), ("edit", "AI 編集", "edit"), ("design", "版面の設計", "edit"),
           ("emblem", "小元素", "emblem-cron"))
BG_ON_EVENT = {"render": "main に push されたとき", "requests": "設定ページから依頼が来たとき"}


def _slots_attr(pid):
    p = next((x for x in processes.PROCESSES if x["id"] == pid), None)
    return e(json.dumps(processes.slots(p))) if p else "[]"


def _admin_backend(rows, todo=None, log=None, res=None):
    """バックグラウンド：裏で動く仕組みの「次の実行」（前回・次回・残り時間はページを開いた端末で計算）と、
    版面（行）× プロセス（列）の今の状態の表。何が待っていて、次にいつ動くかを一目で見る。"""
    cards, plan = [], []
    for p in processes.PROCESSES:
        sl = processes.slots(p)
        if isinstance(p.get("schedule"), str) or not (sl or p.get("workflow")):
            continue   # 別のプロセスと同じ回に動くもの（小元素の選定＝AI 編集）は出さない
        when = (f'<b class="nx-t">--:--</b><small class="nx-l"></small><small class="nx-p"></small>' if sl
                else f'<b class="nx-t ev">{e(BG_ON_EVENT.get(p["id"], "必要なとき"))}</b>')
        wf = f' data-wf="{e(p["workflow"])}"' if p.get("workflow") else ""
        td = (todo or {}).get(p["id"]) or {}
        cards.append(f'<li class="nx" data-slots="{e(json.dumps(sl))}"{wf}>'
                     f'<button type="button" class="nx-n" data-open="proc-{e(p["id"])}">{e(p["name"])}</button>{when}'
                     + ('<span class="pbar" aria-hidden="true"><i></i></span>' if sl
                        else '<span class="pbar ev" aria-hidden="true"><i></i></span>')   # 定時でないものは実行中だけ出す
                     + (f'<small class="nx-do">{e(td["text"])}</small>' if td.get("text") else "")
                     + f'<span class="lv">{_lane_short(p["lane"])}</span></li>')
        if sl:
            plan.append({"id": p["id"], "name": p["name"], "slots": sl, "text": td.get("text", ""), "items": td.get("items", [])[:12]})
    rows = [r for r in rows if r.get("bg")]
    if not rows:
        return f'<ol class="nxs">{"".join(cards)}</ol><p class="empty">データがありません。</p>'
    order = list(SECTIONS) + ["其他"]
    rows = sorted(rows, key=lambda r: (order.index(r.get("section")) if r.get("section") in order else len(order),
                                       r.get("section") or "", r["name"]))
    waits = {k: sum(1 for r in rows if r["bg"][k]["state"] in ("wait", "review", "failed")) for k, _, _ in BG_COLS}
    head = "".join(f'<th><span>{e(t)}</span><small class="nx-h" data-slots="{_slots_attr(pid)}"></small>'
                   f'<small class="bgw">待ち {waits[k]}</small></th>' for k, t, pid in BG_COLS)
    body, sec = [], None
    for r in rows:
        if r.get("section") != sec:
            sec = r.get("section")
            body.append(f'<tr class="bgs"><th colspan="{len(BG_COLS) + 1}"><i style="background:{_sec_color(sec or "其他")}"></i>'
                        f'{e(_sec_name(sec or "其他"))}</th></tr>')
        cells = "".join(f'<td class="bgc s-{r["bg"][k]["state"]}" data-label="{e(t)}"><b>{BG_STATES[r["bg"][k]["state"]]}</b>'
                        f'<small>{e(r["bg"][k]["text"])}</small></td>' for k, t, _ in BG_COLS)
        body.append(f'<tr><td class="nm"><a href="index.html#{_wid(r["name"])}">{e(r["name"])}</a></td>{cells}</tr>')
    logs = "".join(f'<li class="lg-{e(x.get("level") or "info")}"><time>{e(x.get("when") or "")}</time>'
                   f'<span class="lg-p">{e(x.get("name") or "")}</span><span class="lg-t">{e(x.get("text") or "")}</span></li>'
                   for x in (log or []))
    cfg = json.dumps(plan, ensure_ascii=False).replace("</", "<\\/")
    return (f'<h3 class="h3">次の実行 <small>近い順 · 時刻は日本時間 · バーは前回から次回までの経過 · 名前をクリックで流れ</small></h3>'
            f'<ol class="nxs">{"".join(cards)}</ol>'
            + '<h3 class="h3">リソース <small>サーバーの残り · 容量 · トークン</small></h3>' + _admin_resources(res) +
            '<h3 class="h3">並列と制限 <small>同時にいくつ動かすか · それ以上速くできない理由</small></h3>'
            '<ul class="lims">' + "".join(f'<li><b>{e(a)}</b><span class="lim-n">{e(b)}</span><small>{e(c)}</small></li>'
                                          for a, b, c in processes.LIMITS) + '</ul>'
            '<div class="two bgtwo"><div><h3 class="h3">待ち行列 <small>これから 24 時間の実行と、そのとき処理するもの</small></h3>'
            '<ol class="bgq" id="bgq"><li class="empty">計算中…</li></ol></div>'
            '<div><h3 class="h3">ログ <small>裏で動いた仕組みの記録 · 新しい順</small></h3>'
            f'<ol class="blog">{logs or "<li class=empty>まだ記録がありません。次の実行から残ります。</li>"}</ol></div></div>'
            f'<script type="application/json" id="bg-cfg">{cfg}</script>'
            '<h3 class="h3">版面ごとの状態 <small>済 = 終わった · 待ち = 次の回で動く · 要確認 = AI が目で選ぶ · 失敗 = 時間をおいて再挑戦</small></h3>'
            f'<div class="tw"><table class="adm bgm"><thead><tr><th>版面</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _mb(n):
    return f"{n / 1048576:.1f} MB" if n < 1024 ** 3 else f"{n / 1024 ** 3:.2f} GB"


def _meter(label, used, total, note="", warn_at=80):
    """横長のメーター（使った量 / 上限）。warn_at（%）を超えたら赤。赤にしないもの（マシン全体の値）は warn_at=None。"""
    if not total:
        return ""
    pct = max(0, min(100, round(100 * used / total)))
    warn = " warn" if warn_at is not None and pct >= warn_at else ""
    return (f'<div class="mt{warn}"><span class="mt-l">{e(label)}</span><span class="mt-v"><b>{_mb(used)}</b> / {_mb(total)}'
            f'<small>{pct}%</small></span><span class="mt-bar" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}">'
            f'<i style="width:{pct}%"></i></span>' + (f'<small class="mt-n">{e(note)}</small>' if note else "") + "</div>")


def _admin_resources(res):
    """リソース：容量（リポジトリ・公開ページ）、仕組みごとの最近の実行のサーバー（メモリ・ディスク・CPU）、トークン。"""
    if not res:
        return ""
    sz, lim = res.get("sizes") or {}, res.get("limits") or {}
    cap = (_meter("リポジトリ", sz.get("repo", 0), lim.get("repo"), "GitHub は 1GB 未満を推奨（5GB で警告）")
           + _meter("公開ページ（docs/）", sz.get("pages", 0), lim.get("pages"),
                    f'GitHub Pages は 1GB まで · うち小元素の画像 {_mb(sz.get("emblems", 0))}')
           + f'<p class="mt-x">集めた記事（inbox/） {_mb(sz.get("inbox", 0))} · 記録（state/） {_mb(sz.get("state", 0))}</p>')
    rows = []
    for proc, r in (res.get("runs") or {}).items():
        x = r.get("res") or {}
        mem = (_meter("メモリ（使用中）", x["mem_total"] - x.get("mem_free", 0), x["mem_total"],
                      f'空き {_mb(x.get("mem_free", 0))} · この処理のピーク {_mb(x.get("peak", 0))}') if x.get("mem_total") else "")
        disk = (_meter("ディスク（マシン全体）", x["disk_total"] - x.get("disk_free", 0), x["disk_total"],
                       f'残り {_mb(x.get("disk_free", 0))} · Claude のセッションは別に割り当ての上限がある', warn_at=None)
                if x.get("disk_total") else "")
        secs = r.get("secs")
        meta = " · ".join(v for v in (e(r.get("when") or ""), f'{secs // 60} 分 {secs % 60} 秒' if isinstance(secs, int) else "",
                                      f'{r["workers"]} 本並列' if r.get("workers") else "",
                                      f'CPU {x.get("cpu")} コア · 負荷 {x.get("load")}' if x.get("cpu") else "") if v)
        rows.append(f'<li><b>{e(r["name"])}</b><small>{meta}</small>{mem}{disk}</li>')
    srv = (f'<ul class="srv">{"".join(rows)}</ul>' if rows
           else '<p class="empty">まだ記録がありません。次の実行から、終わったときのサーバーの様子が残ります。</p>')
    tk = []
    for proc, t in (res.get("tokens") or {}).items():
        val = (f'<b>{t["last"]:,}</b><small>最近 · 7 日で {t["week"]:,}（{t["runs"]} 回）</small>' if t.get("last") is not None
               else '<b class="na">未記録</b>')
        tk.append(f'<li><span>{e(t["name"])}</span>{val}</li>')
    return ('<div class="two rsrc"><div><h3 class="h3">容量 <small>上限と比べて · 8 割を超えると赤</small></h3>' + cap
            + '<h3 class="h3">トークン <small>Claude の使用量</small></h3><ul class="tok">' + "".join(tk) + '</ul>'
            '<p class="mt-x">Claude API を使ったときは自動で数える。定時タスク（サブスク枠）は Claude が終わりに目安を書く。'
            'サブスク枠の残りはプログラムから読めないので <a href="https://claude.ai/settings/usage" target="_blank" rel="noopener noreferrer">Claude の設定 → 使用量</a> で。</p></div>'
            '<div><h3 class="h3">サーバー <small>仕組みごとの最近の実行 · 終わったときの様子</small></h3>' + srv + "</div></div>")


def _lane_short(lane):
    name, cost, _ = processes.LANES.get(lane, (lane, "", ""))
    return f'<small>{e(name)} · {e(cost)}</small>'


EMBLEM_STATES = {"ok": "そろっている", "running": "進行中", "review": "要確認", "failed": "失敗"}


def _admin_emblem_progress(run):
    """小元素の「進捗」：目標に届いた版面の数（進捗バー）・状態ごとの数・定時の自動補完の最近の実行。"""
    ok, total = run.get("ok", 0), run.get("total", 0)
    pct = round(100 * ok / total) if total else 0
    counts = {}
    for x in (run.get("items") or {}).values():
        counts[x["state"]] = counts.get(x["state"], 0) + 1
    chips = "".join(f'<span class="em-{k}">{EMBLEM_STATES[k]} {counts[k]}</span>' for k in EMBLEM_STATES if counts.get(k))
    last = (f'最近の実行 <b>{e(run["last_run"])}</b>（予算 {run.get("minutes") or 0:g} 分 · {run.get("done", 0)} 版面を処理）'
            if run.get("last_run") else "定時の自動補完はまだ動いていません")
    since = f' · 開始 {e(run["started"])}' if run.get("started") else ""
    return (f'<div class="emp"><div class="emp-h"><h3 class="h3">進捗</h3><span class="emp-n"><b>{ok}</b> / {total} 版面が目標に到達'
            f'<small>{pct}%</small></span></div>'
            f'<div class="emp-bar" role="progressbar" aria-valuemin="0" aria-valuemax="{total}" aria-valuenow="{ok}"><i style="width:{pct}%"></i></div>'
            f'<p class="emp-meta"><span class="emp-st">{chips}</span><span>{last}{since}</span></p></div>')


def _admin_emblems(rows, run=None):
    """小元素（版面右上のステッカー）の状況：種類・目標・いまの枚数と、定時の自動補完の進捗。止まっているものを上に。"""
    rows = [r for r in rows if r.get("emblem")]
    if not rows:
        return '<p class="empty">データがありません。</p>'
    run = run or {}
    prog = run.get("items") or {}

    def state(r):
        if r["emblem"]["state"] == "ok":
            return "ok"
        return (prog.get(r["name"]) or {}).get("state") or "running"
    order = {"failed": 0, "review": 1, "running": 2, "ok": 3}
    rows = sorted(rows, key=lambda r: (order.get(state(r), 2), r["emblem"]["have"] - r["emblem"]["target"], r["name"]))
    out = []
    for r in rows:
        m, st, p = r["emblem"], state(r), prog.get(r["name"]) or {}
        pct = min(100, round(100 * m["have"] / max(1, m["target"])))
        shapes = " ".join(f'<i class="chip">{e(k)} {v}</i>' for k, v in (m.get("shapes") or {}).items())
        note = e(p.get("note") or ("" if st == "ok" else "順番待ち"))
        when = f'<small>{e(p["at"])}</small>' if p.get("at") else ""
        out.append(
            f'<tr><td class="nm"><a href="index.html#{_wid(r["name"])}">{e(r["name"])}</a></td>'
            f'<td data-label="種類">{e(m["kind_ja"])}</td>'
            f'<td class="em-n" data-label="枚数"><span class="em-bar"><i style="width:{pct}%"></i></span>'
            f'<b>{m["have"]}</b> / {m["target"]}<small>最大 {m["hi"]}</small></td>'
            f'<td data-label="状態"><span class="em-{st}">{EMBLEM_STATES[st]}</span></td>'
            f'<td class="ms em-note" data-label="最近の結果">{note}{when}</td>'
            f'<td class="ms">{shapes}</td></tr>')
    gap = sum(1 for r in rows if r["emblem"]["state"] != "ok")
    note = (f'<p class="empty">{gap} 件が目標に届いていません。定時の自動補完（プロセス「小元素の自動補完（定時）」）が、足りない順に埋めていきます。'
            '「要確認」は AI が候補の一覧を目で見て選びます。</p>' if gap else '<p class="empty">すべての版面が目標の枚数に届いています。</p>')
    return (_admin_emblem_progress(run) + note
            + '<div class="tw"><table class="adm"><thead><tr><th>作品</th><th>種類</th><th>枚数 / 目標</th><th>状態</th><th>最近の結果</th><th>内訳</th></tr></thead><tbody>'
            + "".join(out) + "</tbody></table></div>")


def _admin_votes(v):
    if not v.get("total"):
        return '<p class="empty">まだ投票がありません。</p>'
    tiles = [("👍", f'{v["up"]}', "件", ""), ("👎", f'{v["down"]}', "件", ""),
             ("この 7 日", f'{v["week"]}', "回", '<span class="kd">取り消しも含む押した回数</span>'),
             ("最後の投票", e(v.get("last") or "—"), "", "")]
    kp = '<div class="kpis k4">' + "".join(
        f'<div class="kpi"><span class="kl">{k}</span><span class="kv"><b>{val}</b><small>{u}</small></span>{x}</div>'
        for k, val, u, x in tiles) + "</div>"
    peak = max((a + b for _, a, b in v.get("works") or []), default=1) or 1
    works = "".join(
        f'<li><span class="mn">{e(n)}</span><span class="vbar"><i class="vu" style="width:{a / peak * 100:.1f}%"></i>'
        f'<i class="vd" style="width:{b / peak * 100:.1f}%"></i></span><b>{a}<small> / {b}</small></b></li>'
        for n, a, b in v.get("works") or [])
    recent = "".join(
        f'<li><span class="vv {"up" if r["vote"] > 0 else "down"}">{"👍" if r["vote"] > 0 else "👎"}</span>'
        f'<a href="{e(_safe_url(r.get("url")) or "#")}" target="_blank" rel="noopener noreferrer">{e(r.get("title") or r.get("url") or "")}</a>'
        f'<small>{e(r.get("work") or r.get("kind") or "")} · {e(r.get("when") or "")}</small></li>'
        for r in v.get("recent") or [])
    return (kp + '<div class="two"><div><h3 class="h3">作品ごと <small>👍 / 👎（今の票）</small></h3>'
            f'<ul class="vworks">{works or "<li class=empty>—</li>"}</ul></div>'
            f'<div><h3 class="h3">最近の投票</h3><ul class="vrecent">{recent}</ul></div></div>')


ADMIN_PAGE_CSS = """
.em-n{white-space:nowrap}.em-n small{margin-left:8px;opacity:.65}
.em-bar{display:inline-block;width:70px;height:10px;margin-right:8px;background:var(--sheet);border:1px solid var(--ink);vertical-align:middle;position:relative}
.em-bar i{position:absolute;inset:0 auto 0 0;background:var(--good)}
.em-ok,.em-running,.em-review,.em-failed{display:inline-block;padding:0 6px;font-weight:900;white-space:nowrap;border:1.5px solid currentColor}
.em-ok{color:var(--good)}.em-running{color:var(--rose)}.em-review{color:var(--ink);background:var(--gold);border-color:var(--ink)}.em-failed{color:var(--card);background:var(--alert);border-color:var(--alert)}
.em-note{font-size:12px;line-height:1.5}.em-note small{display:block;font:500 var(--fs-label) var(--font-mono);opacity:.7}
.emp{margin:0 0 14px}
.emp-h{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px}.emp-h .h3{flex:1 1 auto}
.emp-n{font:500 13px var(--font-sans)}.emp-n b{font:700 24px var(--font-mono);margin-right:4px}.emp-n small{margin-left:8px;font:700 13px var(--font-mono)}
.emp-bar{position:relative;height:14px;margin:6px 0 8px;background:var(--sheet);border:1.5px solid var(--ink);box-shadow:var(--shadow)}
.emp-bar i{position:absolute;inset:0 auto 0 0;background:var(--good)}
.emp-meta{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0;font-size:12px;line-height:1.7}
.emp-st{display:flex;flex-wrap:wrap;gap:6px}.emp-st span{font-size:var(--fs-label)}
.nxs{list-style:none;margin:0 0 20px;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.nx{display:flex;flex-direction:column;gap:2px;padding:10px 12px;background:var(--card);border:1.5px solid var(--ink);box-shadow:var(--shadow);min-width:0}
.nx-n{all:unset;cursor:pointer;font:900 14px/1.35 var(--font-sans)}.nx-n:hover,.nx-n:focus-visible{color:var(--rose);text-decoration:underline}
.nx-t{font:700 22px/1.2 var(--font-mono)}.nx-t.ev{font:700 13px/1.5 var(--font-sans)}
.nx-l{font:700 12px var(--font-sans);color:var(--rose)}.nx-p,.lv small{font:500 var(--fs-label) var(--font-sans);opacity:.75}
.nx.soon{background:var(--gold)}.nx.soon .nx-l{color:var(--ink)}
.nx-do{font:500 12px/1.5 var(--font-sans);margin-top:4px}
.pbar{position:relative;display:block;height:8px;margin:6px 0 2px;background:var(--sheet);border:1.5px solid var(--ink);overflow:hidden}
.pbar i{position:absolute;inset:0 auto 0 0;width:0;background:repeating-linear-gradient(-45deg,var(--rose) 0 6px,color-mix(in srgb,var(--rose) 70%,var(--card)) 6px 12px);
 background-size:17px 17px;animation:pb-move 1.2s linear infinite;transition:width .6s ease}
.nx.run .pbar i{width:40%!important;animation:pb-move 1.2s linear infinite,pb-run 1.6s ease-in-out infinite;background-color:var(--good)}
.nx.run{border-color:var(--good)}.pbar.ev{display:none}.nx.run .pbar.ev{display:block}
@keyframes pb-move{to{background-position:17px 0}}
@keyframes pb-run{0%{left:-40%}100%{left:100%}}
.emp-bar i{background:repeating-linear-gradient(-45deg,var(--good) 0 8px,color-mix(in srgb,var(--good) 75%,var(--card)) 8px 16px);background-size:22px 22px;animation:pb-move 1.4s linear infinite}
@media (prefers-reduced-motion:reduce){.pbar i,.emp-bar i,.nx.run .pbar i,.mt-bar i{animation:none}}
.bgtwo{margin-bottom:20px}
.rsrc{margin-bottom:20px}
.mt{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;align-items:baseline;margin:0 0 10px}
.mt-l{font:700 12px var(--font-sans)}.mt-v{font:500 12px var(--font-mono);white-space:nowrap}.mt-v b{font-weight:700}.mt-v small{margin-left:6px;opacity:.75}
.mt-bar{grid-column:1/-1;position:relative;height:10px;background:var(--sheet);border:1.5px solid var(--ink);overflow:hidden}
.mt-bar i{position:absolute;inset:0 auto 0 0;background:repeating-linear-gradient(-45deg,var(--good) 0 6px,color-mix(in srgb,var(--good) 70%,var(--card)) 6px 12px);
 background-size:17px 17px;animation:pb-move 1.6s linear infinite}
.mt.warn .mt-bar i{background:repeating-linear-gradient(-45deg,var(--alert) 0 6px,color-mix(in srgb,var(--alert) 70%,var(--card)) 6px 12px);background-size:17px 17px}
.mt-n{grid-column:1/-1;font:500 var(--fs-label)/1.5 var(--font-sans);opacity:.8}
.mt-x{margin:0 0 14px;font:500 var(--fs-label)/1.6 var(--font-sans);opacity:.85}.mt-x a{text-decoration:underline}
.srv{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
.srv li{padding:10px 12px;background:var(--card);border:1.5px solid var(--ink)}
.srv li>b{font:900 13px var(--font-sans)}.srv li>small{display:block;margin:2px 0 8px;font:500 var(--fs-label)/1.5 var(--font-sans);opacity:.85}
.tok{list-style:none;margin:0 0 8px;padding:0}
.tok li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:0 10px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--hair);font-size:13px}
.tok b{font:700 15px var(--font-mono);text-align:right}.tok b.na{font:700 12px var(--font-sans);opacity:.6}
.tok small{grid-column:1/-1;text-align:right;font:500 var(--fs-label) var(--font-sans);opacity:.8}
.lims{list-style:none;margin:0 0 20px;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px 18px}
.lims li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;align-items:baseline;padding:7px 0;border-bottom:1px solid var(--hair)}
.lims b{font:900 13px/1.4 var(--font-sans)}.lim-n{font:700 12px var(--font-mono);padding:0 6px;background:var(--ink);color:var(--card);white-space:nowrap}
.lims small{grid-column:1/-1;font:500 var(--fs-label)/1.55 var(--font-sans);opacity:.85}
.bgq,.blog{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.bgq li{display:grid;grid-template-columns:64px minmax(0,1fr);gap:0 10px;padding:8px 0;border-bottom:1px solid var(--hair);font-size:13px}
.bgq li.next{background:color-mix(in srgb,var(--gold) 35%,transparent)}
.bgq time{font:700 15px/1.3 var(--font-mono)}.bgq time small{display:block;font:700 var(--fs-label) var(--font-sans);color:var(--rose)}
.bgq b{font:900 13px/1.4 var(--font-sans)}.bgq .q-t{display:block;font-size:12px;line-height:1.5}
.bgq .q-i{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.bgq .q-i i{font-style:normal;padding:0 6px;border:1px solid var(--hair);font:500 var(--fs-label)/1.6 var(--font-sans)}
.blog{max-height:420px;overflow:auto}
.blog li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 8px;padding:7px 0 7px 8px;border-bottom:1px solid var(--hair);border-left:3px solid var(--hair);font-size:12px;line-height:1.5}
.blog time{font:700 var(--fs-label) var(--font-mono);white-space:nowrap}.blog .lg-p{font:700 var(--fs-label) var(--font-sans);opacity:.8}
.blog .lg-t{grid-column:1/-1}
.blog .lg-ok{border-left-color:var(--good)}.blog .lg-warn{border-left-color:var(--gold)}.blog .lg-error{border-left-color:var(--alert)}
.lv{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;margin-top:2px}
.bgm thead th{vertical-align:bottom}.bgm thead th span{display:block}
.bgm thead small{display:block;font:500 var(--fs-label)/1.5 var(--font-sans);letter-spacing:0;opacity:.8}
.bgm thead .bgw{font-weight:700;color:var(--rose);opacity:1}
.bgm .bgs th{padding:14px 6px 6px;font:900 13px var(--font-sans);border-bottom:2px solid var(--ink);text-align:left}
.bgm .bgs i{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px}
.bgc b{display:inline-block;padding:0 6px;font:900 12px/1.6 var(--font-sans);border:1.5px solid currentColor;white-space:nowrap}
.bgc small{display:block;margin-top:2px;font:500 var(--fs-label)/1.45 var(--font-sans);opacity:.85}
.s-ok b{color:var(--good)}.s-wait b{color:var(--rose)}.s-review b{color:var(--ink);background:var(--gold);border-color:var(--ink)}
.s-failed b{color:var(--card);background:var(--alert);border-color:var(--alert)}.s-idle b{border-color:transparent;opacity:.5}
.h3{margin:0 0 10px;font:900 15px var(--font-sans);padding-bottom:4px;border-bottom:1.5px solid var(--ink)}
.h3 small{font:500 var(--fs-label) var(--font-sans);opacity:.75;margin-left:6px}
.kpis.k4{grid-template-columns:repeat(4,minmax(0,1fr));margin-bottom:18px}
.kpis:not(.k4){grid-template-columns:repeat(5,minmax(0,1fr))}
.kv b{font-size:30px}
.two{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:20px 32px}
table.adm{width:100%;border-collapse:collapse;font-size:13px}
.adm th,.adm td{padding:8px 6px;border-bottom:1px solid var(--hair);text-align:left;vertical-align:middle}
.adm thead th{font:700 var(--fs-label) var(--font-sans);letter-spacing:.04em;border-bottom:2px solid var(--ink);white-space:nowrap}
.adm .nm{min-width:150px}
.adm .nm a{font:900 14px/1.35 var(--font-sans)}.adm .nm a:hover{color:var(--rose);text-decoration:underline}
.adm .nm small{display:flex;align-items:center;gap:5px;margin-top:2px;font:500 var(--fs-label) var(--font-sans);opacity:.75}
.adm .nm small i{display:inline-block;width:8px;height:8px;border-radius:2px;flex:none}
.adm .sz,.adm .n{font:700 13px var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.adm .last{white-space:nowrap;font-weight:700}
.adm .last.stale{color:var(--alert)}
.adm .hz{white-space:nowrap}.adm .hz b{font:700 15px var(--font-mono);margin-right:6px}.adm .hz small{font:500 var(--fs-label) var(--font-mono);opacity:.8}
.adm .ms{line-height:1.9}
.chip{display:inline-block;margin:0 4px 0 0;padding:0 7px;border:1px solid var(--hair);font:500 var(--fs-label)/1.6 var(--font-mono);font-style:normal;white-space:nowrap}
.chip.web{border-color:var(--rose);color:var(--rose);font-family:var(--font-sans);font-weight:700}
.ok{font:500 12px var(--font-sans);opacity:.7}
.vworks,.vrecent,.runs,.qlist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
.vworks li{display:grid;grid-template-columns:120px minmax(0,1fr) 64px;gap:10px;align-items:center;padding:5px 0;font-size:13px}
.vbar{display:flex;height:12px;background:color-mix(in srgb,var(--ink) 8%,transparent)}
.vbar i{display:block;height:100%}.vbar .vu{background:var(--viz-1)}.vbar .vd{background:var(--viz-2)}
.vworks b{font:700 13px var(--font-mono);text-align:right;white-space:nowrap}.vworks b small{font-size:var(--fs-label);opacity:.7}
.vrecent li{display:grid;grid-template-columns:24px minmax(0,1fr);gap:0 8px;padding:7px 0;border-bottom:1px solid var(--hair);font-size:13px;line-height:1.5}
.vrecent a{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}.vrecent a:hover{color:var(--rose);text-decoration:underline}
.vrecent small{grid-column:2;font-size:var(--fs-label);opacity:.75}
.vv{grid-row:span 2}
.runs li,.qlist li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 12px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--hair);font-size:13px}
.runs b,.qlist b{font:900 14px var(--font-sans)}
.runs small,.qlist small{grid-column:1/-1;font-size:var(--fs-label);opacity:.75}
.runs a:hover{color:var(--rose);text-decoration:underline}
.qlist li.ph{grid-template-columns:48px minmax(0,1fr) auto}.qlist li.ph small{grid-column:2/-1}
.qlist img{grid-row:span 2;width:48px;height:48px;object-fit:cover;border:1px solid var(--hair)}
.st{display:inline-block;padding:0 8px;font:700 var(--fs-label)/1.7 var(--font-sans);white-space:nowrap;border:1.5px solid currentColor}
.st.good{color:var(--good)}.st.bad{color:var(--alert)}.st.wait{color:var(--rose)}.st.idle{opacity:.7}
.live .empty{margin-top:4px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px 28px}
@media (max-width:1100px){.kpis:not(.k4){grid-template-columns:repeat(3,minmax(0,1fr))}.grid3{grid-template-columns:minmax(0,1fr)}}
@media (max-width:860px){
 .two{grid-template-columns:minmax(0,1fr)}
 .adm thead{display:none}
 .adm,.adm tbody{display:block}
 .adm tr{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px 6px;padding:12px 0;border-bottom:1px solid var(--hair)}
 .adm td{border:0;padding:0}
 .adm .nm{grid-column:1/-1;min-width:0}
 .adm td[data-label]::before{content:attr(data-label);display:block;font:700 var(--fs-tag)/1.4 var(--font-sans);opacity:.7}
 .adm .ms{grid-column:1/-1}
 .kpis.k4{grid-template-columns:repeat(2,minmax(0,1fr))}
 .vworks li{grid-template-columns:96px minmax(0,1fr) 56px}
}
@media (max-width:860px){.adm.bgm tr{grid-template-columns:repeat(4,minmax(0,1fr))}.bgm .bgs{display:block}.bgm .bgs th{display:block}}
@media (max-width:560px){.kpis:not(.k4){grid-template-columns:repeat(2,minmax(0,1fr))}
 .adm tr{grid-template-columns:repeat(3,minmax(0,1fr))}
 .bgm tr{gap:4px}.bgm .bgc b{padding:0 4px;font-size:11px}.bgm .bgc small{font-size:var(--fs-label)}
 .nxs{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""

ADMIN_PAGE_JS = """
(function(){
  var CFG=JSON.parse(document.getElementById('adm-cfg').textContent);
  function el(tag,cls,text){var x=document.createElement(tag);if(cls)x.className=cls;if(text!=null)x.textContent=text;return x;}
  function when(s){var d=new Date(s);if(isNaN(d))return '';var m=Math.round((Date.now()-d)/60000);
    if(m<1)return 'たった今';if(m<60)return m+' 分前';if(m<1440)return Math.round(m/60)+' 時間前';return Math.round(m/1440)+' 日前';}
  function badge(text,cls){return el('span','st '+cls,text);}
  function fail(box,msg){box.textContent='';box.appendChild(el('p','empty',msg));}
  // バックグラウンド：定時（UTC の [時,分]）から前回・次回・残り時間。1 分ごとに数え直し、近い順に並べ替える
  function two(n){return ('0'+n).slice(-2);}
  // 時刻は設定の表示時区（display_timezone、いまは日本時間）で出す。端末の時計の時区には左右されない
  var FMT=new Intl.DateTimeFormat('ja-JP',{timeZone:CFG.tz,month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  function parts(t){var o={};FMT.formatToParts(t).forEach(function(p){o[p.type]=p.value;});return o;}
  function hm(t){var a=parts(t),b=parts(new Date());var day=(a.month===b.month&&a.day===b.day)?'':a.month+'/'+a.day+' ';return day+two(+a.hour)+':'+two(+a.minute);}
  function around(sl){var now=new Date(),nx=null,pv=null;for(var k=-1;k<=1;k++)sl.forEach(function(s){
    var t=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate()+k,s[0],s[1]));
    if(t>now){if(!nx||t<nx)nx=t;}else if(!pv||t>pv)pv=t;});return [pv,nx];}
  function left(ms){var m=Math.max(0,Math.ceil(ms/60000));return m<60?'あと '+m+' 分':'あと '+Math.floor(m/60)+' 時間 '+(m%60)+' 分';}
  function tick(){var list=document.querySelector('.nxs');
    Array.prototype.forEach.call(document.querySelectorAll('[data-slots]'),function(x){var sl=JSON.parse(x.getAttribute('data-slots')||'[]');
      if(!sl.length){x._next=Infinity;return;}var a=around(sl);x._next=+a[1];
      if(x.classList.contains('nx-h')){x.textContent='次回 '+hm(a[1])+'（'+left(a[1]-new Date())+'）';return;}
      x.querySelector('.nx-t').textContent=hm(a[1]);x.querySelector('.nx-l').textContent=left(a[1]-new Date());
      x.querySelector('.nx-p').textContent='前回 '+hm(a[0]);x.classList.toggle('soon',a[1]-new Date()<15*60000);});
    Array.prototype.forEach.call(document.querySelectorAll('.nx[data-slots]'),function(x){var sl=JSON.parse(x.getAttribute('data-slots')||'[]'),b=x.querySelector('.pbar i');
      if(!b||!sl.length)return;var a=around(sl);b.style.width=Math.min(100,Math.max(2,(new Date()-a[0])/(a[1]-a[0])*100)).toFixed(1)+'%';});
    if(list)Array.prototype.slice.call(list.children).sort(function(a,b){return a._next-b._next;}).forEach(function(c){list.appendChild(c);});
    queue();}
  // 待ち行列：これから 24 時間の実行を時刻順に。最初の回にだけ、処理する版面の名前を付ける
  var PLAN=JSON.parse((document.getElementById('bg-cfg')||{}).textContent||'[]');
  function queue(){var q=document.getElementById('bgq');if(!q)return;var now=new Date(),end=+now+864e5,runs=[];
    PLAN.forEach(function(p){for(var k=0;k<=1;k++)p.slots.forEach(function(s){var t=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate()+k,s[0],s[1]));
      if(t>now&&+t<=end)runs.push({t:t,p:p});});});
    runs.sort(function(a,b){return a.t-b.t;});q.textContent='';var seen={};
    runs.slice(0,12).forEach(function(r,i){var li=el('li',i?null:'next'),tm=el('time',null,hm(r.t));tm.appendChild(el('small',null,left(r.t-now)));li.appendChild(tm);
      var d=el('div');d.appendChild(el('b',null,r.p.name));var first=!seen[r.p.id];seen[r.p.id]=1;
      d.appendChild(el('span','q-t',first||r.p.id!=='emblem-cron'?r.p.text:'（前の回の続き）'));
      if(first&&r.p.items.length){var w=el('span','q-i');r.p.items.forEach(function(n,j){w.appendChild(el('i',null,(r.p.id==='emblem-cron'?(j+1)+'. ':'')+n));});d.appendChild(w);}
      li.appendChild(d);q.appendChild(li);});
    if(!runs.length)q.appendChild(el('li','empty','予定がありません。'));}
  tick();setInterval(tick,60000);
  // GitHub Actions：ワークフローごとに最新の実行
  var runs=document.getElementById('runs');
  fetch('https://api.github.com/repos/'+CFG.repo+'/actions/runs?per_page=60').then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){
    var seen={},ul=el('ul','runs');
    (j.workflow_runs||[]).forEach(function(w){
      var f=(w.path||'').split('/').pop();if(!CFG.flows[f]||seen[f])return;seen[f]=1;
      var li=el('li'),a=el('a',null,CFG.flows[f]);var http=/^https:\\/\\/github\\.com\\//.test(w.html_url||'');
      if(http){a.href=w.html_url;a.target='_blank';a.rel='noopener noreferrer';}
      var b=el('b');b.appendChild(a);li.appendChild(b);
      var c=w.status!=='completed'?['実行中','wait']:w.conclusion==='success'?['成功','good']:w.conclusion==='cancelled'||w.conclusion==='skipped'?['取消','idle']:['失敗','bad'];
      li.appendChild(badge(c[0],c[1]));li.appendChild(el('small',null,when(w.created_at)+' · '+(w.event||'')));ul.appendChild(li);
      var card=document.querySelector('.nx[data-wf="'+f+'"]');if(card&&w.status!=='completed')card.classList.add('run');
      var lv=document.querySelector('.nx[data-wf="'+f+'"] .lv');if(lv){lv.insertBefore(el('small',null,when(w.created_at)),lv.firstChild);lv.insertBefore(badge(c[0],c[1]),lv.firstChild);}
    });
    runs.textContent='';if(ul.children.length)runs.appendChild(ul);else fail(runs,'最近の実行がありません。');
  }).catch(function(){fail(runs,'GitHub から読めませんでした（1 時間に 60 回までの制限かもしれません）。');});
  if(!CFG.url||!CFG.key){['reqs','photos'].forEach(function(id){fail(document.getElementById(id),'データベースに未接続です。');});return;}
  function rpc(fn){return fetch(CFG.url+'/rest/v1/rpc/'+fn,{method:'POST',headers:{apikey:CFG.key,'Content-Type':'application/json'},body:'{}'})
    .then(function(r){if(!r.ok)throw 0;return r.json();});}
  var ST={pending:['待ち','wait'],done:['反映済み','good'],skipped:['見送り','bad'],'new':['受付','wait'],exported:['認識待ち','wait']};
  // 設定ページの依頼（ウォッチ項目の追加・修正）：待ちのものと、3 日以内に処理したもの
  var reqs=document.getElementById('reqs');
  rpc('list_item_requests').then(function(list){
    reqs.textContent='';if(!list||!list.length){fail(reqs,'依頼はありません。');return;}
    var ul=el('ul','qlist');list.forEach(function(x){var li=el('li');
      li.appendChild(el('b',null,(x.action==='edit'?'修正：':'追加：')+x.name));var s=ST[x.status]||[x.status,'idle'];li.appendChild(badge(s[0],s[1]));
      li.appendChild(el('small',null,when(x.created_at)+(x.note?' · '+x.note:'')));ul.appendChild(li);});
    reqs.appendChild(ul);
  }).catch(function(){fail(reqs,'読めませんでした。');});
  // ウィッシュリストの写真の受付
  var photos=document.getElementById('photos');
  rpc('get_photo_inbox').then(function(list){
    photos.textContent='';if(!list||!list.length){fail(photos,'写真はありません。');return;}
    var ul=el('ul','qlist');list.slice(0,12).forEach(function(x){var li=el('li','ph');
      if(/^data:image\\/jpeg;base64,/.test(x.thumb||'')){var im=el('img');im.src=x.thumb;im.alt='';im.loading='lazy';li.appendChild(im);}else li.appendChild(el('span'));
      li.appendChild(el('b',null,x.wish_name||('#'+x.id+' '+(x.status||''))));var s=x.state==='done'?['追加済み','good']:(ST[x.state]||[x.state,'idle']);li.appendChild(badge(s[0],s[1]));
      li.appendChild(el('small',null,when(x.created_at)+(x.note?' · '+x.note:'')));ul.appendChild(li);});
    photos.appendChild(ul);
  }).catch(function(){fail(photos,'読めませんでした。');});
})();
"""


def render_admin(data, db, updated):
    """管理ページ（docs/admin.html）。見るだけ・口令なし。
    data = {"pipeline": {...}, "items": [行], "votes": {...}}（digest.admin_data が作る）；
    db = {url, key}（公開の publishable key。依頼と写真の受付をページを開いたときに読む）。"""
    cfg = json.dumps({"url": (db or {}).get("url") or "", "key": (db or {}).get("key") or "",
                      "repo": (db or {}).get("repo") or "CxElegy/Wishlist", "flows": ADMIN_WORKFLOWS,
                      "tz": (db or {}).get("tz") or "Asia/Tokyo"},
                     ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>管理ページ</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}{ADMIN_PAGE_CSS}{processes.CSS}</style>
</head>
<body>
<div class="page">
<header class="mast">
<div class="mtitle"><h1>管理ページ</h1><span class="stamp">ウォッチリスト通信</span></div>
<div class="tools"><div class="meta"><small>更新</small><b>{e(updated)}</b></div></div>
</header>
<a class="back" href="./">← ウォッチリスト通信に戻る</a>
<p class="lede">収集・編集が止まっていないか、依頼や写真が溜まっていないか、どの作品の記事が少ないかを一目で見るためのページです。
見るだけで、ここから何かを変えることはできません。篇幅やウォッチ項目の変更は<a href="settings.html">設定ページ</a>で。</p>
<section class="panel" id="status"><h2 class="sh"><span>運行状況</span><small>ページを生成した時点</small></h2>{_admin_pipeline(data.get("pipeline") or {})}</section>
<section class="panel" id="backend"><h2 class="sh"><span>バックグラウンド</span><small>何が待っていて、次にいつ動くか · 表は {e(updated)} 時点</small></h2>{_admin_backend(data.get("items") or [], data.get("todo"), data.get("log"), data.get("resources"))}</section>
<section class="panel" id="procs"><h2 class="sh"><span>全体の構成</span><small>どこで何が動き、データがどう流れるか · 部品をクリックで詳しい流れ</small></h2>{processes.render()}</section>
<section class="panel live" id="queue"><h2 class="sh"><span>いまの状況</span><small>開いたときに読み込み</small></h2>
<div class="grid3"><div><h3 class="h3">GitHub Actions</h3><div id="runs"><p class="empty">読み込み中…</p></div></div>
<div><h3 class="h3">ウォッチ項目の依頼</h3><div id="reqs"><p class="empty">読み込み中…</p></div></div>
<div><h3 class="h3">写真の受付</h3><div id="photos"><p class="empty">読み込み中…</p></div></div></div></section>
<section class="panel" id="items"><h2 class="sh"><span>ウォッチ項目</span><small>赤い「最新の記事」= {ADMIN_STALE_DAYS} 日以上 新しい記事なし</small></h2>{_admin_items(data.get("items") or [])}</section>
<section class="panel" id="emblems"><h2 class="sh"><span>小元素</span><small>版面右上のステッカー · 種類ごとの目標枚数</small></h2>{_admin_emblems(data.get("items") or [], data.get("emblem_run"))}</section>
<section class="panel" id="votes"><h2 class="sh"><span>投票</span><small>👍 / 👎 · 前回の収集時点</small></h2>{_admin_votes(data.get("votes") or {})}</section>
</div>
<script type="application/json" id="adm-cfg">{cfg}</script>
<script>{ADMIN_PAGE_JS}</script>
<script>{processes.JS}</script>
</body>
</html>
"""
