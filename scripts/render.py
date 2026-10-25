"""把所有期的数据渲染成一张报纸式简报网页（docs/index.html）。消息永远保留，不随新一期消失。

版式规则：
- 左侧目录（撑满屏幕高度）：按板块分组列出每个作品，滚动时当前所在的一项放大并换成板块色，点击直达
- 最上面一张「头版」：最近一周的实时总览（最重要的一条做头条 + 各作品最新一条 + 最新消息列表）
- 版面数量固定；顺序：板块固定 → 板块内按小分类的话题度 → 小分类内按作品的话题度（heat.heat_order，左边目录同顺序）
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
import lang
import processes
import likefx
import livelog
import overview
import sitedir
import taxonomy
import theme
from images import FAVICON_SERVICE, GENERIC, base_domain  # 网站 logo / 默认分享图的判断，和找图用同一条规则

# Web フォントは日本語 UI の Noto Sans JP だけ（＋数字の Anton・手書き風の Yusei Magic・等幅）。中国語・韓国語の記事の字は端末のフォントで出す
# （2026-10-22 全体の検査 H6：SC/TC/KR/Serif SC まで読んで CSS 480KB・フォント 239 本 8.8MB、遅い回線で最初の表示まで 5.7 秒）
FONTS = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700;900"
    "&family=Anton&family=Yusei+Magic&family=JetBrains+Mono:wght@500;700&display=swap"
)

CSS = """
:root{--ink:#1A1C22;--paper:#EDEBE6;--rose:#B8336A;--sheet:#F4EDE4;--card:#FBF8F1;--gold:#FFD23F;--alert:#D7261E;--flame:#FF7A1A;--ember:#5A1410;--blueflame:#4F8BFF;--good:#1F7A55;--discord:#5865F2;
 --by-ai:#6B3FC4;--by-rule:#1F7A55;   /* 流れの図：AI（Claude）が判断する手順 / 規則（プログラム）で決まる手順 */
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
 font:900 clamp(15px,2.2vw,26px)/1.2 var(--font-sans);letter-spacing:.04em;color:#FFF;text-shadow:0 1px 2px color-mix(in srgb,var(--ink) 70%,transparent);
 background:radial-gradient(circle,color-mix(in srgb,#000 22%,transparent) 1px,transparent 1.5px) 0 0/7px 7px,linear-gradient(color-mix(in srgb,var(--ink) 34%,transparent),color-mix(in srgb,var(--ink) 34%,transparent)),var(--ac,var(--rose))}   /* 明るい作品色でも白い字が読めるよう墨を 34% 重ねる */
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
/* 本文の小分類の区切り（目次と同じ「板块 → 小分類」。目立たせない：細い線と小さな字だけ） */
.subhead{display:flex;align-items:center;gap:10px;margin:0 0 -22px;padding-bottom:5px;border-bottom:2px solid color-mix(in srgb,var(--sc) 40%,transparent)}
.subhead .tg{font:800 var(--fs-label) var(--font-sans);padding:1px 9px}
.subhead b{font:800 15px var(--font-sans);color:var(--ink)}
.subhead small{font:700 11px var(--font-mono);color:var(--ink);opacity:.62;margin-left:auto}
/* ---------- トップ：毎日刷り直すポスター。地色はその日のトップ記事の写真から（--tint / --deep / --hacc） ---------- */
.front{display:flex;flex-direction:column;gap:40px}
.poster{position:relative;background:var(--tint,var(--sheet));color:var(--ink);border:2px solid var(--ink);box-shadow:var(--shadow-l);padding:22px 28px 18px}
/* 見せ場は頭条 1 枚（D5、2026-10-24 ユーザーが見本の右を選んだ）：倍の影・少し傾けた枠・傾けた見出し・平行四辺形の札をポスターに集める。下の照片墙・棚・版面は今のまま */
.poster{--tilt:-2.2deg;--skew:-10deg;box-shadow:10px 10px 0 var(--rose),20px 20px 0 var(--ink);transform:rotate(-.6deg)}
.poster .phead .lab{transform:skewX(var(--skew));box-shadow:4px 4px 0 var(--rose)}
.poster .top h2{transform:rotate(var(--tilt))}
.poster .tag,.poster .tg{transform:skewX(var(--skew));box-shadow:3px 3px 0 var(--ink)}
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
.mgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,280px);gap:22px;align-items:start}
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
.swish .sempty{margin:6px 0 10px;font-size:13px;line-height:1.6;color:color-mix(in srgb,var(--ink) 72%,transparent)}
.swish li[hidden],.agenda li[hidden]{display:none}
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
.wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));grid-auto-flow:dense;gap:18px;align-content:start}
.wc{position:relative;display:flex;flex-direction:column;gap:8px;min-width:0;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);
 padding:8px 10px 11px;transition:transform .12s,box-shadow .12s}
.wc{transform:rotate(var(--r,0deg))}
.wc:hover{transform:rotate(var(--r,0deg)) translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
/* P5 の手法：上下の端はそろえ、中のカードだけ 0.4〜1.2° ずつ不ぞろいに傾ける（同じ向きが続かない） */
.mgrid .wc:nth-child(1){--r:-.6deg}.mgrid .wc:nth-child(2){--r:1.1deg}.mgrid .wc:nth-child(3){--r:-.8deg}
.mgrid .wc:nth-child(4){--r:.5deg}.mgrid .wc:nth-child(5){--r:-1.2deg}.mgrid .wc:nth-child(6){--r:.9deg}
.mgrid .wc:nth-child(7){--r:-.4deg}.mgrid .wc:nth-child(8){--r:1deg}.mgrid .wc:nth-child(9){--r:-.7deg}
.fside .agenda{transform:rotate(.7deg)}.fside .swish{transform:rotate(-.9deg)}
.wc.lead{grid-column:span 2;grid-row:span 2}
.wc .pic{border:1.5px solid var(--ink);aspect-ratio:16/10;--ac:var(--sc)}
.wall{align-items:stretch}  /* 同じ段のカードは同じ高さ（写真枠 16:10・見出し 3 行分でそろえる） */
.wc.lead .pic{flex:1;aspect-ratio:auto;min-height:200px}  /* 大きい一枚は横の 2 枚と同じ高さ：写真は端を少し切って埋める */
.wc[hidden]{display:none}.wc:not(.lead) .pic{height:auto}.wc:not(.lead) .pic[style*='height']{aspect-ratio:auto}  /* WALL_JS が右の列とそろえるため写真枠を少し高くすることがある */
.wc .tg{position:absolute;left:-8px;top:-13px;z-index:2;box-shadow:2px 2px 0 var(--ink)}  /* 作品名の札はカードの上の縁に（写真に重ねない） */
.wc em{font:15px/1 var(--font-num);font-style:normal;letter-spacing:.04em}
.wc b{font:700 14px/1.45 var(--font-sans);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:4.35em}  /* 3 行分：段のカードの高さがそろう */
.wc.lead b{font-size:20px;font-weight:900;line-height:1.45;-webkit-line-clamp:2;min-height:2.9em}
.wc:hover b{text-decoration:underline;text-underline-offset:3px}
/* ジャンルの棚：ジャンルごとに看板、作品ごとに最新の 1 本をテープのように並べる（版面へのリンク） */
/* 棚は既定でたたむ（トップが長くなりすぎないように）。1 行の帯を押すとひらく */
.shelfbox>summary{list-style:none;cursor:pointer;display:flex;align-items:baseline;gap:12px;padding:8px 14px;background:var(--card);border:2px solid var(--ink);box-shadow:3px 3px 0 var(--ink);font:900 14px var(--font-sans);letter-spacing:.06em}
.shelfbox>summary::-webkit-details-marker{display:none}
.shelfbox>summary small{font:700 11px var(--font-sans);opacity:.75}
.shelfbox>summary span{margin-left:auto;padding:1px 10px;background:var(--ink);color:var(--card);font:700 12px var(--font-sans)}
.shelfbox>summary:hover span{background:var(--rose)}
.shelfbox .shclose,.shelfbox[open] .shopen{display:none}.shelfbox[open] .shclose{display:inline}
.shelfbox[open]>summary{margin-bottom:18px}
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
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:28px 22px;padding:20px 26px 22px}
.card{position:relative;display:flex;flex-direction:column;gap:8px;min-width:0}
/* 記事の近さ（2026-10-24，用户定的）：写真が上の記事か下の記事か迷わせない。同じ記事の中の隙間（8px）は記事どうしの隙間の 1/3 以下、
   記事は下の線で閉じる（.mini と同じ線）。ux_check の「近さ」が測る */
.grid>.card:not(.hero),.side>.card{padding-bottom:16px;border-bottom:1px solid color-mix(in srgb,currentColor 22%,transparent)}
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
/* 写真のない記事：字だけ（出典と日付・大きな見出し），左に作品色の線 */
.card.nophoto{display:flex;flex-direction:column;justify-content:center;gap:8px;padding:10px 0 14px 14px;border-left:5px solid var(--ac,var(--acc))}
.card.nophoto h2,.card.nophoto h3{font-size:20px;line-height:1.5;font-weight:900}
.card.mini.nophoto h3{font-size:17px}
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
.older summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:center;gap:2px 12px;padding:12px 26px;font:900 13px var(--font-sans);letter-spacing:.1em}
.older summary::-webkit-details-marker{display:none}
.older summary::before{content:"+";display:inline-grid;place-items:center;width:22px;height:22px;background:var(--aacc);color:var(--abg);transform:skewX(var(--skew));
 font:900 15px/1 var(--font-sans)}
.older[open] summary::before{content:"−"}
.older summary:hover,.older summary:focus-visible{color:var(--aacc);outline:none}  /* 折叠区是副色底：用副色的强调色 */
.older summary .lb{font:inherit;white-space:nowrap}   /* 「もっと見る · 9 件」は途中で折り返さない（狭い画面では内訳が次の行へ） */
.older summary span{font-weight:500;letter-spacing:.04em}
.older .grid{padding-top:8px}
.pend{border-top:1px dashed var(--line)}
.pend summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;padding:10px 26px;font:700 var(--fs-label) var(--font-sans);letter-spacing:.08em;opacity:.85}
.pend summary::-webkit-details-marker{display:none}
.pend summary::before{content:"…";font-weight:900;color:var(--acc)}
.pend summary span{font-weight:400;letter-spacing:.02em;opacity:.85}
.pend summary:hover,.pend summary:focus-visible{opacity:1;color:var(--acc);outline:none}
.pend ul{list-style:none;margin:0;padding:0 26px 14px;display:grid;gap:6px}
.pend li{display:flex;flex-wrap:wrap;gap:2px 10px;align-items:baseline;font-size:13px;line-height:1.5;overflow-wrap:anywhere}
.pend li a{color:inherit}
.pend li a:hover,.pend li a:focus-visible{color:var(--acc);text-decoration:underline}
.pend li small{font:var(--fs-label) var(--font-num);opacity:.7}
.older .card.c3 h3{font-size:15px;line-height:1.45}
/* 副色が鮮やかな作品（漫威の赤など）：「もっと見る」の広い面は主面の色に副色を薄く混ぜた落ち着いた色にして、
   副色そのものは上の細い線と＋ボタンだけに使う（広い面積に原色の赤・黄・ピンクを塗ると目が疲れる） */
.softalt .older{background:color-mix(in srgb,var(--abg) 20%,var(--bg));color:var(--fg);border-top:3px solid var(--abg)}
.softalt .older summary::before{background:var(--abg);color:var(--afg)}
.softalt .older summary:hover,.softalt .older summary:focus-visible{color:var(--acc)}
.softalt .older .card.a{color:var(--fg);--ac:var(--acc)}
.softalt .older .card.a .when b{color:var(--bg)}
.softalt .older .card.a .vt{--vt:var(--bg);--vf:var(--fg)}
.softalt .older .hl{color:color-mix(in srgb,var(--acc) 65%,var(--fg))}  /* 強調色は背景が少し明るくなった分だけ本文色に寄せる（文字として 4.5:1 以上） */
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
.pkgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:26px 22px;margin-top:18px;align-items:start}
.pkgrid.row{grid-template-columns:repeat(var(--n),minmax(0,1fr))}
.pksub{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px 12px;margin-top:22px;font:900 15px var(--font-sans);letter-spacing:.1em}
.pksub::before{content:"";flex:none;width:18px;height:18px;background:var(--rose);transform:skewX(var(--skew));align-self:center}
.pksub span{font:500 12px var(--font-sans);letter-spacing:0;opacity:.75}
.pk{position:relative;display:flex;flex-direction:column;gap:0;min-width:0;color:var(--ink)}
.pk.big{grid-column:span 2;grid-row:span 2;align-self:stretch}
.pk.big>a{flex:1}.pk.big .pic{flex:1 1 auto;aspect-ratio:auto;min-height:160px}  /* 大きいカードは 2 段分の高さまで写真を伸ばす（下に空白を残さない） */
.pk>a{display:flex;flex-direction:column;min-width:0;flex:1}
.pk .pic{background:#FFF;color:var(--ink);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink);aspect-ratio:16/10}
.pk .pic{--pko:18px}.pk.big .pic{--pko:40px}  /* 下に手書きの札（.pkt）が重なる高さ：写真はその上に収め、重なる帯はぼかしだけ */
.pk .pic img:not(.bg):not(.ico){bottom:var(--pko)}.pk .pic.fill img.bg{display:block}
.pk.big .pic{aspect-ratio:4/3}
.pk .pkt{position:relative;z-index:1;display:flex;flex-direction:column;gap:5px;min-width:0;margin:-18px 10px 0;padding:14px 14px 10px;background:var(--card);
 box-shadow:var(--shadow);transform:rotate(-1deg)}
.pk:nth-child(even) .pkt{transform:rotate(1deg)}
.pk.big .pkt{margin:-40px 24px 0;padding:22px 22px 16px;transform:rotate(-1.2deg)}
.pk .why{order:-1;font:15px/1.45 var(--font-hand);color:var(--ink)}
.pk .why mark{color:inherit;background:linear-gradient(transparent 55%,var(--gold) 55% 92%,transparent 92%);-webkit-box-decoration-break:clone;box-decoration-break:clone;padding:0 2px}
.pk .why small{display:block;margin-top:3px;font-size:12px;opacity:.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pk.big .why{font-size:22px;line-height:1.4}
.pk.big .why small{font-size:15px}
.pk .src{font:500 12px/1.4 var(--font-sans);opacity:.7}
.pk b{font:700 14px/1.45 var(--font-sans);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pk.big b{font-size:19px;font-weight:900;line-height:1.4;-webkit-line-clamp:3}
.pk .tags{display:flex;flex-wrap:wrap;gap:5px}
.pk .tags:empty{display:none}
.pk .tags i{font-style:normal;padding:2px 8px;border:1.5px solid var(--ink);background:#FFF;font:700 11px/1.3 var(--font-sans)}
.pk>a:hover b{text-decoration:underline;text-underline-offset:3px}
.pk .taste{font-size:11px;opacity:.7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pkgrid[style*='--pkh'] .pk:not(.big) .pic{height:var(--pkh);aspect-ratio:auto}  /* fitPk が 1 画面に収めるため写真枠の高さを決めることがある */
.pkgrid[style*='--pkbig'] .pk.big .pic{height:var(--pkbig);flex:none;aspect-ratio:auto}
/* PC の「似たジャンルの新着」は横長の小さいカード（写真を左、文字を右）：上の段と形を変え、1 段を低く */
@media (min-width:761px){
 .pkgrid.row .pk>a{flex-direction:row;align-items:flex-start}
 .pkgrid.row .pk .pic{flex:none;width:88px;aspect-ratio:1;--pko:0px;box-shadow:4px 4px 0 var(--ink);transform:rotate(-2deg)}
 .pkgrid.row .pk:nth-child(even) .pic{transform:rotate(2deg)}
 .pkgrid.row .pk .pkt{flex:1;margin:10px 0 0 -8px;padding:10px 12px 9px}
 .pkgrid.row .pk .tags,.pkgrid.row .pk .taste,.pkgrid.row .pk .why small{display:none}
 .pkgrid.row .pk .why{font-size:13px}.pkgrid.row .pk b{font-size:13px}
 .pkgrid.row .pk .vote{margin:4px 0 0 96px}
 .pkgrid:not(.row) .pk:not(.big) .taste{display:none}  /* 「あなたの投票」は大きい 1 枚だけ */
}
@media (min-width:761px) and (max-height:1000px){.pkgrid:not(.row) .pk:not(.big) .tags{display:none}}
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
.emb{clip-path:inset(-100vh -100vw -14px -100vw)}  /* 帯の線より下は見せない（飛び出す動きの途中）：下のニュースの字・ボタンに重ねない。絵そのものは線より上に置くので切れない。-14px はフチ（5.5px）と影（8px）の分 */
.emb img{display:block;height:calc(100% * var(--k,1));width:auto;max-width:190px;object-fit:contain;object-position:bottom}  /* --k：顔の大きさをそろえる（アップの絵は小さく） */
.emb{--leg:116px;--legc:290px;--anc:62px;--bmax:200px}  /* 全身の立ち絵の「目から足の裏まで」の長さ（emblem.body_marks）。どのキャラも同じ背の高さに見える */
.emb img.body{--bh:calc(var(--leg) / var(--bl));--bz:min(var(--bh), var(--bmax));height:var(--bz);width:calc(var(--bz) * var(--ba));max-width:none;
 margin-bottom:0;  /* 絵の下端を帯の線に（足より下の尻尾・武器・裾があれば、その分だけ足が少し上がる）。帯の線より下へは出さない：下のニュースの字に重ねず、切れもしない。高さは --bmax まで */
 margin-right:calc(var(--anc) - var(--bz) * var(--ba) * (1 - var(--bc)))}  /* 重心を右端から --anc のところに：武器・尻尾が長くても体は同じ位置 */
.emb img.body.cut{--bh:calc(var(--legc) / var(--bl));margin-bottom:0}  /* 上半身に切ったもの：目から足の裏（画像の外）を --legc にそろえ、切り口を帯の線に。顔の大きさがほかの胸像と同じくらい */
.emb img.logo{height:62%;max-width:150px}.emb img.logo.wide{height:auto;width:220px;max-width:220px;margin-bottom:12%}  /* 横長の文字のロゴは幅で大きく */
.emb img.icon{height:70%}  /* ロゴ・物のアイコン：人物より小さめ */
/* 透明な立ち絵が見つからない写真は、丸ではなく P5 風の傾いた四辺形のカードに（中身はそのまま、顔が入るよう上寄り） */
.emb img.badge{width:auto;aspect-ratio:4/5;object-fit:cover;object-position:50% 20%;clip-path:polygon(8% 0,100% 5%,92% 100%,0 94%)}
.emb img.badge.whole{aspect-ratio:auto;height:auto;width:auto;max-width:210px;max-height:100%;object-fit:contain;background:color-mix(in srgb,var(--fg) 10%,var(--bg));padding:0;border:5px solid var(--card);box-sizing:content-box;clip-path:polygon(1.5% 0,100% 2.5%,98.5% 100%,0 97.5%)}  /* 横長・縦長すぎる画像は切らず、余白なしで写真そのままに斜めの枠だけ */
.emb .crop{display:block;height:100%;aspect-ratio:4/5;overflow:hidden;clip-path:polygon(8% 0,100% 5%,92% 100%,0 94%)}
.emb .crop img{width:calc(100% / var(--cw));max-width:none;height:auto;aspect-ratio:auto;object-fit:fill;clip-path:none;
 margin-left:calc(-100% * var(--cx) / var(--cw));margin-top:calc(-100% * var(--cy) * var(--ar) / var(--cw))}  /* 顔が入る範囲だけ（emblem.py の crop） */
.emb-js .emb:not(.in) .emb-in{opacity:0;transform:translate(56px,44px) rotate(26deg) scale(.45);--sx:0px;--sy:0px}
.emb-js .emb.out .emb-in{transition:transform .38s cubic-bezier(.6,0,.9,.4),opacity .3s ease-in .08s,--sx .15s,--sy .15s;
 transform:translate(18px,70px) rotate(-18deg) scale(.55)}  /* 上へ戻ったとき：影が縮んで、下へ沈みながら消える */
@supports (animation-timeline:view()){.emb{animation:embdrift linear both;animation-timeline:view();animation-range:cover}}
@keyframes embdrift{from{translate:0 0}to{translate:0 -36px}}  /* スクロールに合わせてゆっくり浮く。上へだけ動く（下へ動くと帯の下のニュースの字に重なる） */
.has-emb .band{padding-right:260px}  /* 小元素の右からの位置（〜52px）＋幅（〜190px）＋傾きの分 */
.has-emb .deco{display:none}  /* 小元素がその版面の飾り：題字横の装飾字は出さない（右に寄せた数字と重なるため） */
@media (max-width:600px){.emb{height:100px;right:8px;--leg:74px;--legc:186px;--anc:40px;--bmax:130px}.emb img{max-width:140px}.emb img.logo.wide{width:130px;max-width:130px}.has-emb .band{padding-right:118px}}
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
 .poster{padding:16px 14px 14px;box-shadow:6px 6px 0 var(--rose),12px 12px 0 var(--ink)}
 .top{grid-template-columns:minmax(0,1fr);grid-template-rows:auto;gap:18px}
 .pdate b{font-size:84px}.pdate span{font-size:28px;padding:6px 10px 4px}
 .frame{grid-column:1;grid-row:auto;margin:4px 6px 6px 0;padding:6px;transform:rotate(-1.5deg)}
 .burst{width:72px;height:72px;font-size:16px;top:-16px;left:-14px}
 .top h2{font-size:20px;transform:rotate(-1deg)}
  .wall{grid-template-columns:minmax(0,1fr);gap:16px}.wall>.wc:nth-child(n+7){display:none}.wc.lead{grid-column:auto;grid-row:auto}.wc.lead .pic{min-height:0;aspect-ratio:16/10}
 .wc:not(.lead){display:grid;grid-template-columns:120px minmax(0,1fr);grid-template-rows:auto 1fr;gap:4px 12px;align-items:start}
 .wc:not(.lead) .pic{grid-row:1/3}.wc:not(.lead) .tg{left:-6px;top:-11px;font-size:11px}
  .fside{display:none}  /* スマホは右の列を出さない（欲しい物は報頭のボタン、予定は各版面で） */
 .shelves{gap:28px 0}.shelf{flex:none;width:100%}
 .tapes{grid-template-columns:minmax(0,1fr);gap:10px;padding:0 4px 0 0}
 .tape{grid-template-columns:6px 110px minmax(0,1fr);align-items:start}.tape .spine{grid-row:auto;align-self:stretch}
 .tape .pic{margin:6px 0 6px 6px}.tape .lbl{padding:7px 10px 9px}
 .tape:nth-child(n+4){display:none}  /* スマホは各ジャンル 3 作品まで（ほかは下の各版面で） */
 .picks{padding:18px 14px 22px;box-shadow:5px 5px 0 var(--rose)}.pknav{margin-left:0;width:100%}
 .pkgrid,.pkgrid.row{grid-template-columns:minmax(0,1fr);gap:28px}.pk.big .pic{flex:none;min-height:0;aspect-ratio:16/10}
 .pk.big .pic{--pko:26px}.pk.big .pkt{margin:-26px 10px 0;padding:18px 16px 14px}.pk.big .why{font-size:20px}.pk.big b{font-size:17px}.pk.big .vote{margin:10px 10px 0}
 .sec{box-shadow:5px 5px 0 var(--ink)}.band{padding:16px 14px 2px}.band .title{font-size:22px;padding:6px 14px}.band .cnt,.band .heat{margin-left:0}.band .deco{display:none}
 .hx{position:static;width:auto;margin-top:10px}.heat[open]{flex-basis:100%}
 .grid{padding:16px 14px 18px;gap:24px 14px}.facts{padding:14px 14px 0}.brief{padding:12px 14px 16px}.older summary{padding:12px 14px}.pend summary{padding:10px 14px}.pend ul{padding:0 14px 12px}
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
/* ---------- 左侧目录（v6：testground/compare.html で決めた形。宽屏的样子见 NAV_STYLES，窄屏是顶部两排横条） ---------- */
html{scroll-behavior:smooth}
[data-k]{scroll-margin-top:24px}
.spot,.front .poster{scroll-margin-top:16px}
.page{max-width:1480px;display:grid;grid-template-columns:268px minmax(0,1fr);gap:28px 32px;align-items:start}
.mast{grid-column:1/-1}
.issues{display:flex;flex-direction:column;gap:28px;min-width:0}
.nav{position:sticky;top:0;display:flex;flex-direction:column;z-index:50}
.nav .pill{display:flex;align-items:center;gap:8px;position:relative;text-decoration:none}
.nav .pill .no{font:700 10px var(--font-mono);font-style:normal;font-variant-numeric:tabular-nums}
.nav a:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
/* 作品のアイコン：items.yaml の emblem → 記事の写真 → 板块色の丸に頭文字。板块のアイコンは twemoji */
.nav .ic{flex:none;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;overflow:hidden;
 background:var(--img,none) center/cover no-repeat,var(--sc);color:#FFF;font:900 10px/1 var(--font-sans);font-style:normal}
.nav .ic.has{color:transparent;background-color:var(--card)}
.nav .si{flex:none;width:18px;height:18px}
.nav .x{display:none!important}   /* v6 で隠した行（NAV_JS が付け外し） */
.nav .bar,.nav .mtabs{display:none}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.nav *{transition:none!important}}
/* 宽屏：目录占左栏从页面最上面开始（报头只在右栏），上下滚动时位置都不动。
   页面底部的留白挪进右栏，滚到底时目录也不会被顶上去 */
@media (min-width:1001px){
 .page{padding-bottom:0}.mast{grid-column:2;grid-row:1}.issues{grid-column:2;grid-row:2;padding-bottom:40px}
 .nav{grid-column:1;grid-row:1/3}}
/* 窄屏：顶部两排横条。上排是板块，下排是现在这个板块的作品（v6 的隐藏规则不用，简单就好） */
@media (max-width:1000px){
 .page{grid-template-columns:minmax(0,1fr)}
 .nav{top:env(safe-area-inset-top,0px);background:var(--ink);color:var(--card);padding:8px 0 0;margin:0 -24px}
 .nav .nhead,.nav .navwish,.nav .logo{display:none}
 .nav .mtabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:2px 16px 10px}
 .nav .mtabs::-webkit-scrollbar,.nav .rail::-webkit-scrollbar{display:none}
 .nav .mtabs a{flex:none;padding:4px 12px;font-size:13px;opacity:.55;text-decoration:none}
 .nav .mtabs a.on{opacity:1;box-shadow:3px 3px 0 var(--gold)}
 .nav .rail{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:8px 16px;border-top:1px solid rgba(251,248,241,.18)}
 .nav:not(.insec) .rail{display:none}
 .nav .nslot{display:none}
 .nav .nslot.cur,.nav .nbody{display:contents}
 .nav .nsec,.nav .nsubs,.nav .nlab,.nav .nmore{display:none!important}
 .nav .pill{display:flex!important;flex:none;padding:5px 10px;border:1px solid rgba(251,248,241,.35);color:var(--card);
  font:700 13px/1.3 var(--font-sans);white-space:nowrap}
 .nav .pill .no,.nav .pill .ic,.nav .pill .cnt,.nav .pill .new,.nav .pill .br,.nav .pill .xref{display:none}
 .nav .pill.media,.nav .nsum{display:none!important}   /* スマホの横帯にはシリーズの中身・作品名の行を出さない */
 .nav .pill.on{background:var(--card);color:var(--ink);border-color:var(--card)}
 .nav .bar{display:block;position:absolute;left:0;bottom:0;height:3px;background:var(--cur,var(--alert));width:calc(var(--prog,0) * 100%)}
 [data-k]{scroll-margin-top:104px}
}
@media (max-width:600px){.nav{margin:0 -16px}}
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
    def link(m):   # 外のサイトは新しいタブ、サイトの中（相対の網址）は同じタブ
        out = m.group(2).startswith(("http://", "https://"))
        return f'<a href="{m.group(2)}"' + (' target="_blank" rel="noopener"' if out else "") + f'>{m.group(1)}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, e(text, quote=False))


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


_LOCAL = []  # [原図の網址 → 本站の高清版（docs/pics/…）]：hdimg.py が作る。最初に使うときに読む


def _img_url(u, local=True):
    """配図の網址を整える。本站に高清版（小さい図を OpenCV で拡大したもの・防盗链で直接は出せない図）があればそれ
    （local=False で元の網址）。Bing ニュースの縮小画像（bing.com/th?id=…&w=1200）は、元が小さいと
    指定の幅まで白い余白を足して返すので、w / h を外して元の大きさで取る（枠の中に白い帯ができない）。"""
    if local and isinstance(u, str):
        if not _LOCAL:
            import hdimg
            _LOCAL.append(hdimg.local_map())
        if u in _LOCAL[0]:
            return _LOCAL[0][u]
    if isinstance(u, str) and re.match(r"^https://(www\.)?bing\.com/th\?", u):
        u = re.sub(r"&(amp;)?[wh]=\d+", "", u)
    return u


def _pic(story):
    """配图。底层模糊铺满，上层完整显示：图片不裁切，也不留空白条。
    兜底顺序：自己的图 → _fbs 里的备用图（作品封面）→ 来源网站的图标和网站名 → 作品名排版的封面块。
    前一个打不开（防盗链、网站删图、图标太小……）网页上自动换下一个。"""
    img, name = story.get("image"), story.get("_work", "")
    fbs = story.get("_fbs") if story.get("_fbs") is not None else [story.get("_cover")]
    # 第一张是 src，其余按顺序备用。本站的高清版打不开时还有原图
    chain = list(dict.fromkeys(v for u in [img, *fbs] if u for v in (_img_url(u), _img_url(u, local=False))))
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
    html_ = _tcard_(story, span, i, today, small, mini)
    if _has_photo(story):
        return html_
    # 写真のない記事（2026-10-25）：出典のアイコンの札で空っぽの箱に見せず、字だけの記事の形（大きな見出し・出典と日付）にする
    html_ = re.sub(r'<div class="pic[^"]*">.*?</div>', "", html_, count=1, flags=re.S)
    return html_.replace('<article class="card ', '<article class="card nophoto ', 1)


def _tcard_(story, span, i, today, small=False, mini=False):
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


def _own_photo(x):
    """报道自己的图（不算借来的作品封面）。トップのポスターは同じ重要度ならこちらを先に。"""
    return bool(x.get("image")) and not x.get("_borrowed")


def _story_key(work, title):
    """同じ作品の同じ出来事かを見るための語（digest.story_tokens から作品名を除いたもの）。"""
    import digest  # digest が render を import しているので、使うときに読む
    names = [work.get("name", "")] + list(work.get("keywords") or []) + list(work.get("match") or [])
    generic = set().union(*(digest.story_tokens(str(n)) for n in names)) if names else set()
    return digest.story_tokens(title) - generic - FRONT_COMMON


# 見出しによく出るが「どの出来事か」を表さない語（同じ作品の別の記事でも共通）。これ以外の語が重なれば同じ出来事とみなす
FRONT_COMMON = {"update", "updates", "news", "official", "report", "reports", "release", "date", "revealed", "reveals",
                "announced", "announces", "confirmed", "confirms", "fans", "movie", "film", "game", "series", "season"}


def _front_pick(ranked, n):
    """ポスター 1 本＋写真の壁 n 本を選ぶ（ranked は重要度・新しさ順の (作品, 記事)）。
    - 作品ごとに 1 本目を全部出してから 2 本目（同じ作品の記事ばかり並ばない）
    - 同じ写真は 2 回出さない
    - 同じ作品の 2 本目以降は、すでに出した記事と「どの出来事か」を表す語（作品名と FRONT_COMMON を除く）が
      1 つでも重なれば出さない（trailer・doom が重なる＝同じ予告編・同じ人物の話）。迷ったら出さない：
      同じニュースが 2 回並ぶより、壁が 1 枚少ないほうがいい"""
    picked, imgs, keys = [], set(), {}
    for rnd in (1, 2):
        for w, x in ranked:
            if len(picked) > n:
                return picked
            img = x.get("image") or (x.get("_fbs") or [None])[0]
            if any(x is y for _, y in picked) or img in imgs:
                continue
            name = w["name"]
            if rnd == 1 and name in keys:
                continue
            k = _story_key(w, x["headline"])
            if any(k & old for old in keys.get(name, [])):
                continue
            picked.append((w, x))
            imgs.add(img)
            keys.setdefault(name, []).append(k)
    return picked


def _photo_head(stories):
    """版面の頭（重大・頭条の大きい枠）は写真のある記事だけ（2026-10-25）。写真のない頭条・重大は普通の記事に下げ、
    頭が空いたら、写真のある記事のうち新しいものを頭条に上げる。元の記事は書き換えない（写しを返す）。"""
    out, demoted = [], None
    for x in stories:
        if x.get("weight") in ("hero", "lead") and not _has_photo(x):
            demoted = demoted or x["weight"]
            x = {**x, "weight": "normal"}
        out.append(x)
    if demoted and not any(x.get("weight") in ("hero", "lead") for x in out):
        pic = [x for x in out if _has_photo(x)]
        if pic:
            best = max(pic, key=lambda x: x.get("date") or x["_issue"])
            out[out.index(best)] = {**best, "weight": "lead"}
    return out


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


PENDING_SHOW = 20   # 「整理待ち」に並べる最大件数（それ以上は「ほか N 件」）


def _pending(items):
    """AI 編集がまだ整理していない新着（digest.split_unedited、報告の block["pending"]）。版面には載せず、
    版面の下に折りたたんだ「整理待ち N 件」として原題・出典・日付だけを並べる（ふだんは閉じている）。
    要紧消息はここに入らない（その場で「重大」として版面に載る）。ないときは空文字。リンクは http(s) だけ。"""
    rows = [x for x in items or [] if isinstance(x, dict) and x.get("title") and not _spam(x["title"], x.get("url") or "")]   # 古い号に残った垃圾页も出さない
    if not rows:
        return ""
    lis = ""
    for x in rows[:PENDING_SHOW]:
        u, src = _safe_url(x.get("url")), str(x.get("source") or "")[:40]
        title = f'<a href="{e(u)}" target="_blank" rel="noopener">{e(x["title"])}</a>' if u else f'<span>{e(x["title"])}</span>'
        meta = " · ".join(v for v in (e(_md(x.get("date"))), e(src)) if v)
        lis += f'<li>{title}{f"<small>{meta}</small>" if meta else ""}</li>'
    if len(rows) > PENDING_SHOW:
        lis += f'<li class="more">ほか {len(rows) - PENDING_SHOW} 件</li>'
    return (f'<details class="pend"><summary>整理待ち · {len(rows)} 件'
            f'<span>AI 編集がまとめたら記事になります（原題のまま）</span></summary><ul>{lis}</ul></details>')


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
    return (f'<details class="older"><summary><b class="lb">{label} · {len(stories) + len(texts)} 件</b><span>{detail}</span></summary>'
            f'<div class="grid">{cards}</div>{_brief(texts)}</details>')


def _spam(title, url=""):
    """垃圾页（digest.is_spam）。収集・出刊で落としているが、古い号に残ったものもページに出さない。"""
    import digest  # digest が render を import しているので、使うときに読む
    return digest.is_spam(title, url)


def collect(issues, order=None, langs=None):
    """把各期按作品汇总：外观以最新一期为准；消息按链接去重，按时间排列（新的在前）。
    langs：読者の言語（lang.order，主言語 → 副言語）。違う号に入った言語違いの同じニュースは好みの言語の 1 本だけ残す（lang.dedupe）。
    作品顺序固定：先按板块（sections.yaml 的顺序，其他最后），同板块内按 order（items.yaml 的顺序）。
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
                # 見出し・網址のない記事は読まない（2026-10-21 KeyError: 'headline' でページ生成が 4 回止まり、その回の収集ごと消えた）
                if not st.get("headline") or not st.get("url"):
                    continue
                if st["url"] in w["_seen"] or _spam(st.get("headline", ""), st["url"]):
                    continue
                w["_seen"].add(st["url"])
                w["stories"].append({**st, "_issue": issue["date"], "_work": b["name"],
                                     "_cover": w.get("cover") or b.get("cover")})
    for w in works.values():
        w["_langs"] = langs or lang.order()
        w["stories"] = lang.dedupe(w["stories"], w["_langs"])
        w["stories"].sort(key=lambda x: x.get("date") or x["_issue"], reverse=True)  # 按消息本身的日期
        # 没有自己图的报道：作品封面每个版面只用一次（几张卡片同一张图很难看），其余显示作品名封面块。
        # 不拿同一项别的报道的图来顶：那是另一件事的图，放上去是错的
        cover = w.get("cover")
        if cover and GENERIC.search(urllib.parse.urlparse(cover).path):
            cover = None  # 封面是品牌 logo（gelato pique）：不拿来顶替报道的图
        # 收集时没图的报道已经把作品封面写进了 image（image_via「作品封面」）：那不是它自己的图，
        # 也照「每个版面只用一次」处理，只留最新的一条，其余当作没图（不然几天的报道都是同一张封面）
        cover_used = not cover
        for x in w["stories"]:
            if x.get("image") and (x.get("image_via") == "作品封面" or x["image"] in (cover, w.get("cover"))):
                x["_borrowed"] = True
                if cover_used:
                    x["image"] = None
                cover_used = True
        w["_fbs"] = [cover] if cover else []
        # 代表整个关注项的小图（目录、暂无新消息小栏）：封面，没有就用它最近一条报道的图
        w["_thumb"] = cover or next((x["image"] for x in w["stories"] if x.get("image")), None)
        for x in w["stories"]:
            if x.get("image"):
                x["_fbs"] = [cover] if cover and cover != x["image"] else []  # 自己的图打不开时才换封面
            elif not cover_used:
                x["_fbs"], cover_used = [cover], True
                x["_borrowed"] = True
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
    tag = "収 集 中" if block.get("collecting") else "整 理 待 ち" if block.get("pending") else "新 着 な し"
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


def _loud(hex_):
    """副色の背景が「鮮やか」か：色度が高く、しかも暗くない（原色の赤・黄・ピンクなど）。暗い赤（#740001）や淡い色は対象外。"""
    try:
        rgb = theme._rgb(hex_)
    except (ValueError, TypeError):
        return False
    return theme._chroma(rgb) >= 0.45 and theme._lum(rgb) >= 0.12


FACE_SHARE = 0.32   # emblem.FACE_SHARE と同じ：顔が小元素の高さのこの割合になる大きさで表示する
CARD_AR = (0.95, 1.6)   # emblem.CARD_AR と同じ：カード（4:5）の窓で切ってよい縦横比（高さ ÷ 幅）


BODY_CROUCH = 1.15   # 「体の大きさ ÷ 目から足の長さ」が版面の中央値のこれ倍を超える = しゃがんでいる・前かがみ


def _body_len(alts):
    """全身の小元素の「そろえる長さ」（高さに対する割合）を a["body"] の 6 番目に足す。ふつうは目から足の裏まで。
    しゃがんだ・前かがみのキャラ（dota2 の Slark）は目から足が短いので、そのままそろえると大きくなりすぎる。
    同じ版面の中央値と比べて体の大きさ（面積の平方根）が目立って大きいものは、大きさから立ったときの長さを見積もって使う。"""
    import statistics
    for cut in (True, False):   # 上半身に切ったもの（人の体つき）と全身のまま（頭の大きいキャラ・マスコット）は体つきが違うので、別々に比べる
        bs = [a["body"] for a in alts if a.get("body") and (a["body"][1] > 1) == cut]
        if not bs:
            continue
        ratio = statistics.median(b[4] / (b[1] - b[0]) for b in bs)
        for b in bs:
            if len(b) != 5:
                continue
            leg = b[1] - b[0]
            b.append(round(max(leg, b[4] / ratio) if b[4] / leg > ratio * BODY_CROUCH else leg, 3))


WIDE_LOGO = 0.5   # ロゴの 高さ÷幅 がこれ未満 = 横長の文字のロゴ。高さでそろえると字が小さすぎる（The Mandalorian）ので幅で大きく


def _emblem_img(a):
    """小元素 1 枚の HTML。カード（badge）で取景（crop）があれば 4:5 の窓にその範囲だけを見せる。
    顔の割合（fs）が基準より大きい（アップの）ものは小さく表示して、どの版面でも顔が同じくらいの大きさに見えるように。"""
    k = f' style="--k:{min(1, FACE_SHARE / a["fs"]):.3f}"' if a.get("fs") else ""
    if a.get("body"):   # 全身：目から足の裏までの長さをどのキャラも同じに、足の裏を帯の線に
        b = a["body"]
        k = ' style="--bl:{:.3f};--bf:{:.3f};--bc:{:.3f};--ba:{:.3f}"'.format(b[5] if len(b) > 5 else b[1] - b[0], b[1], b[2], b[3])
    body_cls = (" body cut" if a["body"][1] > 1 else " body") if a.get("body") else ""
    img = (f'<img class="{a["shape"]}{body_cls}"{k} src="{e(a["src"])}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" '
           f'onerror="var s=this.closest(\'.sec\');if(s)s.classList.remove(\'has-emb\');this.closest(\'.emb\').remove()">')
    c = a.get("crop")
    ar = a.get("ar")
    if a["shape"] == "badge" and not c and (a.get("plate") or ar and not (CARD_AR[0] <= float(ar) <= CARD_AR[1])):
        img = img.replace('class="badge"', 'class="badge whole"', 1)   # 縦横比がカードと離れている：切らずに全体を見せる
    if a["shape"] == "logo" and ar and float(ar) < WIDE_LOGO:
        img = img.replace('class="logo"', 'class="logo wide"', 1)   # 横長の文字のロゴ（タイトルロゴ）：高さでなく幅で大きく
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
        elif isinstance(x.get("ar"), (int, float)) and x["ar"] > 0:
            a["ar"] = float(x["ar"])
        b = x.get("body")
        if (isinstance(b, list) and len(b) == 5 and all(isinstance(v, (int, float)) for v in b)
                and 0 <= b[0] < b[1] <= 6 and 0 <= b[2] <= 1 and 0 < b[3] < 10 and 0 < b[4] <= 6):   # 足の裏 > 1 = 上半身に切った
            a["body"] = [float(v) for v in b]
        fs = x.get("fs")
        if isinstance(fs, (int, float)) and 0.05 < fs <= 1:
            a["fs"] = float(fs)
        if x.get("shape") in ("logo", "icon"):
            a["shape"] = x["shape"]
        if x.get("plate"):   # 濃い地の板ごとのタイトルロゴ：カードの窓で切らず、板そのものに枠
            a["plate"] = True
        alts.append(a)
    _body_len(alts)
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
    recent = _photo_head([x for x in block["stories"] if x["_issue"] >= cutoff and _has_pic(x)])
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
    grid += _brief(texts) + _older(more + older, today, len(more), old_texts) + _pending(block.get("pending"))
    recent = recent or texts
    quiet = "" if recent else " quiet"
    quiet += " softalt" if _loud(t["alt_bg"]) else ""
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
    # 垃圾页（digest.is_spam）はここでも落とす：recommend.json は別の仕組み（後台作業）が古い内容で書き戻すことがあり、
    # 作る側で除いていても古いファイルから戻ってくる（2026-10-19 Unisba Media が推薦に残った）
    picks = [x for x in picks or [] if not _spam(x.get("title") or "", x.get("url") or "")]
    if not picks:
        return ""
    covers = {w["name"]: [w["_thumb"]] if w.get("_thumb") else [] for w in works}

    def cards_of(group, big_first):
        return "".join(card(x, big_first and i == 0) for i, x in enumerate(group))

    def card(x, big):
        follow = x.get("kind") in ("follow", "hesitate")  # 同类新发现不是那个作品本身，没图时不能用它的封面
        story = {"image": x.get("image"), "_fbs": [] if follow else covers.get(x["work"], []),
                 "_work": (x.get("hits") or [x["work"]])[0] if follow else x["work"],
                 "url": x.get("url"), "source": x.get("source")}   # 图都打不开时退到来源网站的图标（不再留一个空框）
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
  // 「気になるかも？」全体を 1 画面に収める（PC だけ）：はみ出す分を小さいカードの写真枠から段ごとに等分して削る（最低 72px）。
  // 大きい 1 枚は 2 段分の高さに合わせて一緒に縮む
  const fitPk = () => {
    // 高さは CSS 変数で渡す（写真が開けず FIT_JS が .pic を作り直しても効くように）
    if (!wishGrid) return;
    wishGrid.style.removeProperty('--pkh'); wishGrid.style.removeProperty('--pkbig');
    if (innerWidth <= 760) return;
    const q = sel => [...wishGrid.querySelectorAll(sel)];
    const over = sec.getBoundingClientRect().height - (innerHeight - 16);
    const sm = q('.pk:not(.big)'), big = wishGrid.querySelector('.pk.big'), bigPic = big && big.querySelector('.pic');
    if (over > 0 && sm.length > 1) {
      const h = Math.max(...sm.map(k => k.querySelector('.pic')?.getBoundingClientRect().height || 0));
      wishGrid.style.setProperty('--pkh', Math.max(72, h - over / 2) + 'px');
    }
    // 大きい 1 枚は横の 2 段とちょうど同じ高さに（下端をそろえる）
    if (bigPic && sm.length >= 3) {
      // 大きい 1 枚が高いと段そのものが伸びるので、横のカード自身の高さ（2 枚ずつの大きいほう）＋段の間で測る
      const hk = k => k ? k.getBoundingClientRect().height : 0;
      const want = Math.max(hk(sm[0]), hk(sm[1])) + parseFloat(getComputedStyle(wishGrid).rowGap) + Math.max(hk(sm[2]), hk(sm[3]));
      const h = bigPic.getBoundingClientRect().height - (big.getBoundingClientRect().height - want);
      wishGrid.style.setProperty('--pkbig', Math.max(140, h) + 'px');
    }
  };
  let rt;
  addEventListener('resize', ev => { if (ev.isTrusted) { clearTimeout(rt); rt = setTimeout(fitPk, 200); } });
  if (document.fonts) document.fonts.ready.then(fitPk);
  addEventListener('load', fitPk);
  const history = [];
  let pos = -1;
  const show = ([w, f]) => {
    cards.forEach(el => { el.classList.remove('big'); pool.appendChild(el); });
    if (wishGrid) w.forEach((el, i) => { el.classList.toggle('big', i === 0); wishGrid.appendChild(el); });
    if (followGrid) { f.forEach(el => followGrid.appendChild(el)); followGrid.style.setProperty('--n', f.length); }
    fitPk();
    dispatchEvent(new Event('resize'));   // 入れ替えたカードの写真を枠に合わせ直す（FIT_JS）
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
    { method: 'POST', headers, body: JSON.stringify({ ...data, vote: v, account: window.WL_ACCOUNT || 'test1' }), keepalive: true })
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
  fetch(cfg.url.replace(/\\/$/, '') + '/rest/v1/rpc/my_votes', { method: 'POST', headers, body: JSON.stringify({ p_account: window.WL_ACCOUNT || 'test1' }) })
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
      const n = img.cloneNode(); n.src = a.src;
      const whole = a.shape === 'badge' && !a.crop && (a.plate || a.ar && (a.ar < 0.95 || a.ar > 1.6));   // render.CARD_AR：カードと比率が離れたら切らない
      n.className = a.shape + (a.body ? (a.body[1] > 1 ? ' body cut' : ' body') : '') + (whole ? ' whole' : '') + (a.shape === 'logo' && a.ar && a.ar < 0.5 ? ' wide' : '');   // 0.5 = render.WIDE_LOGO
      n.style.cssText = a.body ? '--bl:' + (a.body[5] || (a.body[1] - a.body[0])) + ';--bf:' + a.body[1] + ';--bc:' + a.body[2] + ';--ba:' + a.body[3] : a.fs ? '--k:' + Math.min(1, 0.32 / a.fs).toFixed(3) : '';
      if (a.shape === 'badge' && a.crop) {
        const c = document.createElement('span'); c.className = 'crop';
        c.style.cssText = '--cx:' + a.crop[0] + ';--cy:' + a.crop[1] + ';--cw:' + a.crop[2] + ';--ar:' + (a.ar || 1);
        c.appendChild(n); inner.replaceChildren(c);
      } else inner.replaceChildren(n);
    }
  });
  // 小元素の本当の幅だけ、見出しの帯の右を空ける（画像ごとに幅が違う。固定の幅だと横長の絵が題字・副題の上に乗る）
  const room = el => { const band = el.parentElement, img = el.querySelector('img'); if (!band || !img) return;
    const go = () => { const b = band.getBoundingClientRect(), r = el.getBoundingClientRect();
      if (r.width) band.style.paddingRight = Math.ceil(b.right - r.left + 12) + 'px'; };
    if (img.complete) go(); else img.addEventListener('load', go, { once: true }); };
  els.forEach(room);
  addEventListener('resize', () => els.forEach(room));
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
    """主页面上去愿望清单子页面的入口（报头右上角、左侧目录底部）。0 件でも出す（新しいアカウントが最初の 1 件を足す入口）。"""
    want = sum(1 for x in wishes if (x.get("status") or "想要") == "想要")
    return (f'<a class="{cls}" href="wishlist.html"><b>♥</b><span>{"欲しい物" if cls == "navwish" else "欲しい物リスト"}</span>'
            f'<small>{f"欲しい {want} 件" if wishes else "まだ 0 件"}</small></a>')


def _asset_ver(name):
    """docs/ のファイルの中身の指紋（8 桁）。<script src="…?v=指紋"> にして、中身が変わったら必ず新しい版を読ませる
    （GitHub Pages は 10 分キャッシュ、スマホのブラウザはもっと長く古い版を使い続ける）。"""
    try:
        return hashlib.sha1((sitedir.SITE_DIR / name).read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


SETTINGS_ZH = {
    "lang": "zh-CN", "title": "设置", "back": "← 回到简报", "back_href": "index.html", "updated": "更新于", "add": "",
    "links": '<p class="hint"><a href="themes.html">版面主题（30 套）和 👍 演出（20 种）一览 →</a>　<a href="admin.html">管理页（运行状况・投票・各关注项的记事数）→</a></p>',
    "intro": '点 S / M / L 改篇幅，点「改」修改这一项关注什么；想关注新的东西，在最下面「新增关注项」里只写个名字，一步一步回答几个问题就行。改完立刻存进数据库，<span id="wl-eta">下次更新时（最多 2 小时）网页按新的设置更新</span>。',
    "legend": "<dt>S</dt><dd>少：每期最多 3 条，大约一行</dd><dt>M</dt><dd>中等：每期最多 5 条</dd><dt>L</dt><dd>多：每期最多 8 条，满满一整屏</dd>",
    "sch_h": "目录的小分类分法", "sch_intro": "每个板块选一种分法：左边目录的小分类札、板块里版面的排序都按它来。选了网页大约 1 分钟后更新。",
    "sch_aria": "的小分类分法", "size_aria": "的篇幅",
    "js_nodb": "未连数据库", "js_saving": "保存中…", "js_saved": "已保存 ✓", "js_fail": "没存上", "js_offline": "连不上"}
# お客さま本人の設定ページ（user_pages.py）。画面の文字は日本語（app_users.ui_lang、今の登録者は日本語）
SETTINGS_JA = {
    "lang": "ja", "title": "設定", "back": "← 自分のページへ", "back_href": "./", "updated": "更新", "add": "＋ 追いかけるものを足す", "links": "",
    "intro": "S / M / L で版面の大きさを、ジャンルごとに目次の分け方を選べます。選ぶとすぐ保存され、数分でページに反映されます。",
    "legend": "<dt>S</dt><dd>小：1 回に 3 本まで、だいたい 1 行</dd><dt>M</dt><dd>中：1 回に 5 本まで</dd><dt>L</dt><dd>大：1 回に 8 本まで、画面いっぱい</dd>",
    "sch_h": "目次の小分類の分け方", "sch_intro": "ジャンルごとに 1 つ選ぶと、左の目次の札とジャンルの中の版面の並びがその分け方になります。",
    "sch_aria": "の小分類の分け方", "size_aria": "の大きさ",
    "js_nodb": "つながっていません", "js_saving": "保存しています…", "js_saved": "保存しました ✓", "js_fail": "保存できませんでした", "js_offline": "つながりません"}


def render_settings(items, db, updated, schemes=(), own=None):
    """设置页（docs/settings.html）：改每个关注项的篇幅 S / M / L，新增 / 修改关注项。都不用口令。
    items：[{name, section, subtitle, size, fields}]（items.yaml 的顺序；fields 是网页上能改的那些字段的现值）；
    db：{url, key} Supabase 的地址和公开的 publishable key。篇幅用 get_sizes() 读、set_size() 改；
    新增 / 修改关注项是一问一答的向导（docs/additem.js），提交到 submit_item()（db/item_requests.sql），
    下一次更新时写进 items.yaml。
    schemes：板块ごとの「小分類の分け方」（digest.nav_scheme_rows）。選ぶと set_nav_scheme()（db/nav_schemes.sql）に保存、網页がすぐ作り直される。
    own：お客さま本人の設定ページ（scripts/user_pages.py が作る。{picks, add}）。同じ部品・同じ画面で、文字は日本語、
    書くのは本人の分だけ（my_size_set → follows.size・my_nav_scheme_set → nav_schemes、db/my_layout.sql）。
    向導・改・删の代わりに「＋ 追いかけるものを足す」（入口と同じ流れ）と各行の「外す」（my_keywords_set）。"""
    T = SETTINGS_JA if own else SETTINGS_ZH
    sch = []
    for r in schemes or ():
        btns = "".join(f'<button type="button" data-v="{e(o["id"])}" aria-pressed="{str(o["id"] == r["chosen"]).lower()}">{e(o["label"])}</button>'
                       for o in r["options"])
        prev = "".join(f'<p class="pv" data-v="{e(o["id"])}"{"" if o["id"] == r["chosen"] else " hidden"}>'
                       + " · ".join(f"{e(g)} <b>{n}</b>" for g, n in o["groups"]) + "</p>" for o in r["options"])
        sch.append(f'<div class="srow" data-sec="{e(r["section"])}" style="--sc:{_sec_color(r["section"])}">'
                   f'<div class="nm"><b>{e(_sec_name(r["section"]))}</b>{prev}</div>'
                   f'<div class="seg wide" role="group" aria-label="{e(_sec_name(r["section"]))} {T["sch_aria"]}">{btns}</div>'
                   f'<span class="st" aria-live="polite"></span></div>')
    sch_html = (f'<section class="schemes"><h2>{T["sch_h"]}</h2><p class="intro">{T["sch_intro"]}</p>'
                + "".join(sch) + '</section>') if sch else ""
    groups = {}
    for it in items:
        groups.setdefault(it.get("section") or "其他", []).append(it)
    order = [n for n in SECTIONS if n in groups] + [n for n in groups if n not in SECTIONS]
    rows = []
    for name in order:
        secdel = "" if own else (f'<button type="button" class="secdel" aria-label="删除板块 {e(_sec_name(name))} 里的全部关注项">'
                                 '删除这个板块</button>')
        rows.append(f'<h2 style="--sc:{_sec_color(name)}" data-sec="{e(name)}">{e(_sec_name(name))}<small>{_sec_en(name)}</small>'
                    f'{secdel}<span class="st" aria-live="polite"></span></h2>')
        for it in groups[name]:
            sub = f'<small>{e(it["subtitle"])}</small>' if it.get("subtitle") else ""
            also = (it.get("fields") or {}).get("also") or {}
            if also:   # ほかの板块にも乗換の駅がある
                sub += f'<small>⇄ {e("・".join(_sec_name(k) for k in also))} にも</small>'
            btns = "".join(f'<button type="button" data-v="{v}" aria-pressed="{str(v == (it.get("size") or "M")).lower()}">'
                           f'{v}</button>' for v in ("S", "M", "L"))
            tail = (f'<button type="button" class="edit out" aria-label="{e(it["name"])} を外す">外す</button>' if own else
                    f'<button type="button" class="edit" aria-label="修改 {e(it["name"])}">改</button>'
                    f'<button type="button" class="del" aria-label="删除 {e(it["name"])}">删</button>')
            rows.append(f'<div class="row" data-item="{e(it["name"])}"><div class="nm"><b>{e(it["name"])}</b>{sub}</div>'
                        f'<div class="seg" role="group" aria-label="{e(it["name"])} {T["size_aria"]}">{btns}</div>'
                        f'{tail}<span class="st" aria-live="polite"></span></div>')
    data = {"url": (db or {}).get("url") or "", "key": (db or {}).get("key") or "",
            "langs": (db or {}).get("langs") or ["zh-TW", "en-US"], "sections": taxonomy.for_page(),
            "items": [{"name": it["name"], **(it.get("fields") or {})} for it in items],
            **({"own": True, "picks": list(own.get("picks") or []), "t": {k: v for k, v in T.items() if k.startswith("js_")}} if own else
               {"t": {k: v for k, v in T.items() if k.startswith("js_")}})}
    cfg = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="{T["lang"]}">
<head>
<meta charset="utf-8">
{_account_tag("settings")}
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{T["title"]}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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
.row .del{{height:36px;padding:0 10px;border:2px solid #B8336A;background:transparent;color:#B8336A;font:900 14px 'Noto Sans SC',sans-serif;cursor:pointer}}
.row .del:hover,.secdel:hover{{background:#B8336A;color:#FBF8F1}}
.secdel{{margin-left:auto;height:28px;padding:0 10px;border:1.5px solid #B8336A;background:transparent;color:#B8336A;font:700 12px 'Noto Sans SC',sans-serif;cursor:pointer}}
.row.gone .nm{{text-decoration:line-through;opacity:.5}}
.row .del:focus-visible,.secdel:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.seg button:focus-visible,.row .edit:focus-visible{{outline:2px solid #B8336A;outline-offset:2px}}
.seg button:disabled{{cursor:wait;opacity:.6}}
.st{{width:64px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.05em;text-align:right}}
.st.ok{{color:#1F9D6B}}.st.err{{color:#C0392B}}
.schemes{{align-self:stretch;display:flex;flex-direction:column}}
.schemes h2{{margin:8px 0 4px;font:900 20px/1 'Noto Sans SC',sans-serif;letter-spacing:.08em}}
.srow{{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid color-mix(in srgb,var(--ink) 15%,transparent)}}
.srow .nm b{{color:var(--sc)}}
.srow .pv{{margin:0;font-size:12px;opacity:.7}}
.srow .pv b{{font:700 12px var(--font-mono)}}
.seg.wide button{{width:auto;min-width:56px;padding:0 10px;font:900 13px 'Noto Sans SC',sans-serif}}
@media (max-width:600px){{.srow{{flex-wrap:wrap}}.srow .nm{{flex-basis:100%}}}}
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
.subrow{{display:flex;flex-direction:column;gap:6px}}.subrow h4{{margin:0;font:700 13px 'Noto Sans SC',sans-serif}}
.subrow .opts{{flex-direction:row;flex-wrap:wrap}}.subrow .opt{{padding:6px 10px;font-size:14px}}
.facets .fh{{display:flex;flex-wrap:wrap;align-items:center;gap:8px}}.facets .fh i{{font:700 11px 'JetBrains Mono',monospace;font-style:normal;letter-spacing:.06em;padding:1px 6px;border:1px solid currentColor}}
.facets .fh .frec{{background:#FFD23F;color:#1A1C22;border-color:#FFD23F}}.simnote{{padding:8px 10px;border-left:3px solid #B8336A;background:#FFF}}
.kids{{display:flex;flex-direction:column;gap:8px;padding:10px 12px;border:1px dashed #1A1C22}}.kids>span{{font-weight:700;font-size:13px}}
.kids .kid{{display:grid;grid-template-columns:auto 1fr;gap:4px 8px;align-items:center}}.kids .kid small{{grid-column:2;opacity:.7;font-size:12px;line-height:1.5}}
.opts.secgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}}.opts.secgrid .opt{{padding:8px 10px}}
.alsoh{{margin:6px 0 0;font:900 14px 'Noto Sans SC',sans-serif}}.alsobox{{display:flex;flex-direction:column;gap:8px}}.alsobox>span{{font-weight:700;font-size:13px}}
/* 第 3 问「版面里收哪些新闻」（test2）：上＝加进去以后的样子（1 个版面＋枝），下＝按层一行一个面（勾选框・札・找到的东西） */
.facets2{{display:flex;flex-direction:column;gap:14px}}
.fprev{{display:grid;gap:6px;padding:12px 14px;border:2px solid #1A1C22;background:#FBF8F1;box-shadow:4px 4px 0 #1A1C22}}
.fprev .fp-h{{font:700 11px 'JetBrains Mono',monospace;letter-spacing:.16em;opacity:.6}}
.fprev .fp-path{{display:flex;align-items:center;gap:8px;font:700 13px 'Noto Sans SC',sans-serif}}
.fprev .t-tag{{display:inline-block;padding:1px 10px;background:var(--sc);color:#FFF;font:900 13px 'Noto Sans SC',sans-serif;transform:skewX(-8deg)}}
.fprev .fp-st{{display:flex;align-items:baseline;gap:10px;margin-left:9px;padding-left:14px;border-left:3px solid var(--sc)}}
.fprev .fp-st b{{font:900 18px 'Noto Sans SC',sans-serif}}.fprev .fp-st small{{font-size:12px;opacity:.65}}
.fprev .fp-br{{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0 0 0 9px;padding:0 0 0 14px;list-style:none;border-left:3px solid var(--sc)}}
.fprev .fp-br li{{position:relative;padding-left:14px;font:700 13px 'Noto Sans SC',sans-serif;color:#3A3D46}}
.fprev .fp-br li::before{{content:"";position:absolute;left:0;top:.65em;width:9px;border-top:2px solid var(--sc)}}
.fprev .fp-note{{font-size:12px;opacity:.65}}
.fgrp h4{{display:flex;align-items:baseline;gap:8px;margin:0 0 6px;font:900 14px 'Noto Sans SC',sans-serif}}
.fgrp h4 small{{font:500 12px 'Noto Sans SC',sans-serif;opacity:.6}}
.fgrp ul{{display:flex;flex-direction:column;gap:6px;margin:0;padding:0;list-style:none}}
.fr{{display:grid;grid-template-columns:20px 1fr;gap:2px 10px;align-items:center;padding:9px 12px;border:1px solid #C9C6BE;background:#FFF;cursor:pointer}}
.fr:hover{{border-color:#1A1C22}}.fr.on{{border-color:#1A1C22;box-shadow:inset 4px 0 0 #1A1C22}}
.fr input{{width:18px;height:18px;margin:0;accent-color:#1A1C22}}
.fr .fn{{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font:900 15px 'Noto Sans SC',sans-serif}}
.fr .fn i{{font:700 11px 'Noto Sans SC',sans-serif;font-style:normal;padding:0 6px;border:1px solid #1A1C22}}
.fr .fn .fmain{{background:#FFD23F;border-color:#FFD23F}}
.fr small{{grid-column:2;font-size:12px;line-height:1.5;color:#5A5D66;overflow-wrap:anywhere}}
.fr.thin:not(.on) .fn{{color:#5A5D66}}
.fmiss{{font-size:12px!important}}
.fgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}}
.fchips{{display:flex!important;flex-direction:row!important;flex-wrap:wrap;gap:6px!important}}
.fc{{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:1px solid #C9C6BE;background:#FFF;font:700 13px 'Noto Sans SC',sans-serif;cursor:pointer}}
.fc:hover,.fc.on{{border-color:#1A1C22}}.fc.on{{box-shadow:inset 0 -3px 0 #1A1C22}}.fc input{{width:15px;height:15px;margin:0;accent-color:#1A1C22}}
.fkw summary{{cursor:pointer;font-size:12px;font-weight:700}}.fkw ul{{margin:6px 0 0;padding-left:18px;font-size:12px;line-height:1.6;color:#5A5D66}}
/* 加进去以后的目录（树状图预览）：板块的色签 → 小分类 → 关注项，枝用细线 */
.tree{{display:flex;flex-direction:column;gap:8px;padding:12px 14px;border:2px dashed #1A1C22;background:#FBF8F1}}
.tree .t-h{{font:900 14px 'Noto Sans SC',sans-serif}}
.tree ul{{list-style:none;margin:0;padding:0}}
.tree .t-sec{{margin-top:6px}}.tree .t-tag{{display:inline-block;padding:1px 10px;background:var(--sc);color:#FFF;font:900 13px 'Noto Sans SC',sans-serif;transform:skewX(-8deg)}}
.tree .t-sec>ul,.tree .t-sub>ul,.tree .t-it>ul{{margin-left:9px;padding-left:14px;border-left:2px solid color-mix(in srgb,var(--sc) 55%,transparent)}}
.tree .t-sub,.tree .t-it{{position:relative;padding-top:4px}}
.tree .t-sub::before,.tree .t-it::before{{content:"";position:absolute;left:-14px;top:15px;width:10px;border-top:2px solid color-mix(in srgb,var(--sc) 55%,transparent)}}
.tree .t-sn{{font:700 13px 'Noto Sans SC',sans-serif;color:#1A1C22}}
.tree .t-nm{{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px;font:900 14px 'Noto Sans SC',sans-serif}}
.tree .t-nm i{{font:700 11px 'Noto Sans SC',sans-serif;font-style:normal;padding:0 6px;background:#FFD23F;color:#1A1C22}}
.tree .t-it.xfer .t-nm i{{background:#FFF;border:1px solid #1A1C22}}
.tree .t-it>small{{display:block;font-size:12px;color:#5A5D66}}
.tree .t-it.old>.t-nm{{font-weight:500;color:#5A5D66}}.tree .t-it.more>.t-nm{{font-size:12px}}
.tree .t-root{{display:block;font:500 12px/1.5 'Noto Sans SC',sans-serif;color:#5A5D66}}
.tree .t-it>.opt{{margin:4px 0;width:100%}}
.tree .t-md{{font:500 13px 'Noto Sans SC',sans-serif;color:#3A3D46}}
.selall{{align-self:flex-start;padding:6px 14px;border:2px solid #1A1C22;background:#FFF;color:#1A1C22;font:900 14px 'Noto Sans SC',sans-serif;cursor:pointer}}
.selall[aria-pressed="true"]{{background:#1A1C22;color:#F4EDE4}}
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
<a class="back" href="{T["back_href"]}">{T["back"]}</a>
<header><h1 style="margin:0;font:900 40px/1.1 var(--font-sans);letter-spacing:.04em">{T["title"]}</h1></header>
{T["links"] if not own else f'<p class="hint"><a class="go" href="{e(own.get("add") or "../?add")}">{T["add"]}</a></p>'}
<p class="intro">{T["intro"]}</p>
<dl class="legend">{T["legend"]}</dl>
{sch_html}
<div class="cfg">{''.join(rows)}</div>
{"" if own else '<section class="wiz" id="wiz" aria-live="polite"><h2>＋ 新增关注项</h2><p class="hint">正在加载…</p></section>'}
<p class="intro" style="font-size:12px">{T["updated"]} {e(updated)}</p>
</div>
<script type="application/json" id="wl-cfg">{cfg}</script>
<script>
(() => {{
  const CFG = JSON.parse(document.getElementById("wl-cfg").textContent);
  const T = CFG.t || {{}};
  // どの関数も自分のアカウント（db/accounts.sql）。お客さま本人のページ（CFG.own）は p_account を渡さない my_* 関数（db/my_layout.sql、ログインの鍵は AUTH_JS が付ける）
  const OWNFN = {{set_size: "my_size_set", set_nav_scheme: "my_nav_scheme_set"}};
  const rpc = (fn, body) => fetch(`${{CFG.url}}/rest/v1/rpc/${{CFG.own ? (OWNFN[fn] || fn) : fn}}`, {{
    method: "POST", headers: {{apikey: CFG.key, "Content-Type": "application/json"}},
    body: JSON.stringify(CFG.own ? (body || {{}}) : {{...(body || {{}}), p_account: window.WL_ACCOUNT}}),
  }});
  const show = (row, v) => row.querySelectorAll(".seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
  const say = (row, text, cls) => {{ const st = row.querySelector(".st"); st.textContent = text; st.className = "st " + (cls || ""); }};
  if (!CFG.url || !CFG.key) {{
    document.querySelectorAll(".row, .srow").forEach(r => {{ r.querySelectorAll(".seg button").forEach(b => b.disabled = true); say(r, T.js_nodb, "err"); }});
    return;
  }}
  if (!CFG.own) rpc("get_sizes").then(r => r.ok ? r.json() : []).then(list => {{
    const now = Object.fromEntries((list || []).map(x => [x.item, x.size]));
    document.querySelectorAll(".row").forEach(r => {{ if (now[r.dataset.item]) show(r, now[r.dataset.item]); }});
  }}).catch(() => {{}});
  // 小分類の分け方（板块ごと）。お客さま本人のページは作ったときの値（user_pages.py が本人の nav_schemes から）
  if (!CFG.own) rpc("get_nav_schemes").then(r => r.ok ? r.json() : []).then(list => {{
    (list || []).forEach(x => {{ const row = document.querySelector(`.srow[data-sec="${{CSS.escape(x.section)}}"]`); if (row && row.querySelector(`[data-v="${{CSS.escape(x.scheme)}}"]`)) pick(row, x.scheme); }});
  }}).catch(() => {{}});
  const pick = (row, v) => {{
    row.querySelectorAll(".seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
    row.querySelectorAll(".pv").forEach(p => p.hidden = p.dataset.v !== v);
  }};
  document.querySelector(".schemes")?.addEventListener("click", async ev => {{
    const btn = ev.target.closest(".seg button");
    if (!btn || btn.getAttribute("aria-pressed") === "true") return;
    const row = btn.closest(".srow"), before = row.querySelector('.seg button[aria-pressed="true"]')?.dataset.v;
    const btns = row.querySelectorAll(".seg button");
    pick(row, btn.dataset.v); btns.forEach(b => b.disabled = true); say(row, T.js_saving);
    try {{
      const r = await rpc("set_nav_scheme", {{p_section: row.dataset.sec, p_scheme: btn.dataset.v}});
      if (r.ok) say(row, T.js_saved, "ok");
      else {{ if (before) pick(row, before); say(row, T.js_fail, "err"); }}
    }} catch (_) {{ if (before) pick(row, before); say(row, T.js_offline, "err"); }}
    btns.forEach(b => b.disabled = false);
  }});
  // 删除：关注项 1 个（删）／板块里的全部（删除这个板块）。数据库只收「修改」请求，所以写成 edit + {{_delete: true}}，
  // 下次处理请求时从 items.yaml 删掉（下级去掉 parent 留下，digest.delete_item）。板块是事先定好的，没有关注项就不显示
  const delItem = name => rpc("submit_item", {{p_action: "edit", p_name: name, p_config: {{_delete: true}}}});
  const gone = row => {{ row.classList.add("gone"); row.querySelectorAll("button").forEach(b => b.disabled = true); }};
  document.querySelector(".cfg").addEventListener("click", async ev => {{
    const del = ev.target.closest(".del"), secdel = ev.target.closest(".secdel");
    if (del) {{
      const row = del.closest(".row"), name = row.dataset.item;
      const kids = CFG.items.filter(i => i.parent === name).map(i => `「${{i.name}}」`).join("");
      if (!confirm(`删除「${{name}}」？\\n版面和设置都会删掉（下次更新时，通常几分钟）。` + (kids ? `\\n下级 ${{kids}} 会留下，变成单独的版面。` : ""))) return;
      say(row, "提交中…");
      try {{ const r = await delItem(name); if (r.ok) {{ gone(row); say(row, "已提交删除 ✓", "ok"); }} else say(row, "没提交上", "err"); }}
      catch (_) {{ say(row, "连不上", "err"); }}
      return;
    }}
    if (secdel) {{
      const h2 = secdel.closest("h2"), rows = [];
      for (let el = h2.nextElementSibling; el && el.classList.contains("row"); el = el.nextElementSibling) if (!el.classList.contains("gone")) rows.push(el);
      if (!rows.length) return;
      const names = rows.map(r => r.dataset.item);
      if (!confirm(`删除「${{h2.firstChild.textContent}}」板块里的 ${{names.length}} 个关注项？\\n${{names.map(n => `・${{n}}`).join("\\n")}}\\n\\n版面和设置都会删掉（下次更新时）。`)) return;
      say(h2, "提交中…");
      let ok = 0;
      for (const row of rows) {{
        try {{ const r = await delItem(row.dataset.item); if (r.ok) {{ ok++; gone(row); say(row, "已提交删除 ✓", "ok"); }} else say(row, "没提交上", "err"); }}
        catch (_) {{ say(row, "连不上", "err"); }}
      }}
      say(h2, ok === rows.length ? `已提交删除 ${{ok}} 项 ✓` : `提交了 ${{ok}} / ${{rows.length}} 项`, ok === rows.length ? "ok" : "err");
      return;
    }}
    const out = ev.target.closest(".out");
    if (out && CFG.own) {{   // お客さま：追いかけるもの（app_users.prefs.picks）から外す。入口・トップの「外す」と同じ my_keywords_set
      const row = out.closest(".row"), name = row.dataset.item;
      if (!confirm(`「${{name}}」を外しますか？\nページからこの版面がなくなります（次の作り直しで、通常数分）。`)) return;
      const rest = (CFG.picks || []).filter(p => p.name !== name);
      say(row, T.js_saving);
      try {{
        const r = await fetch(`${{CFG.url}}/rest/v1/rpc/my_keywords_set`, {{method: "POST", headers: {{apikey: CFG.key, "Content-Type": "application/json"}},
          body: JSON.stringify({{p_picks: rest}})}});
        if (r.ok) {{ CFG.picks = rest; gone(row); say(row, "外しました ✓", "ok"); }} else say(row, T.js_fail, "err");
      }} catch (_) {{ say(row, T.js_offline, "err"); }}
      return;
    }}
    const edit = ev.target.closest(".edit");
    if (edit) {{ window.wlEditItem && window.wlEditItem(edit.closest(".row").dataset.item); return; }}
    const btn = ev.target.closest(".seg button");
    if (!btn || btn.getAttribute("aria-pressed") === "true") return;
    const row = btn.closest(".row");
    const before = row.querySelector('.seg button[aria-pressed="true"]')?.dataset.v;
    const btns = row.querySelectorAll(".seg button");
    show(row, btn.dataset.v); btns.forEach(b => b.disabled = true); say(row, T.js_saving);
    try {{
      const r = await rpc("set_size", CFG.own ? {{p_name: row.dataset.item, p_size: btn.dataset.v}} : {{p_item: row.dataset.item, p_size: btn.dataset.v, p_pass: ""}});
      if (r.ok) say(row, T.js_saved, "ok");
      else {{ if (before) show(row, before); say(row, T.js_fail, "err"); }}
    }} catch (_) {{ if (before) show(row, before); say(row, T.js_offline, "err"); }}
    btns.forEach(b => b.disabled = false);
  }});
}})();
</script>
{"" if own else f'<script src="additem.js?v={_asset_ver("additem.js")}"></script>'}
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
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
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
{_live_head("wishlist")}
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
<script>{LIVE_JS}</script>
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
    { method: 'POST', headers: { apikey: CFG.key, 'Content-Type': 'application/json' }, body: JSON.stringify({ ...(body || {}), p_account: window.WL_ACCOUNT }) });
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
            f'<article class="wcard{" solo" if len(wishes) == 1 else ""}" data-status="{e(status)}" data-key="{e(x["name"])}">'
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


# 头版板块：sections.yaml 里事先定全的板块（scripts/taxonomy.py），按表的顺序排，颜色各不相同（白字、浅底上的小字都过 WCAG AA 4.5:1）。
# 数据里的板块名照旧是中文（items.yaml / 设置页），网页上显示日语名
SECTIONS = {k: r["color"] for k, r in taxonomy.SECTIONS.items() if k != taxonomy.OTHER}
SECTION_EN = {k: r["en"] for k, r in taxonomy.SECTIONS.items()}
SECTION_JA = {k: r["ja"] for k, r in taxonomy.SECTIONS.items()}


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
SPOT_COUNT = 24  # 「ほかの注目ニュース」の写真の壁の候補：大きい 1 枚（2×2）+ 小さい 23 枚。列の数は幅しだい（1 列 220px 以上）、WALL_JS が画面の高さに収まる段数だけ出す。スマホは 6 枚まで


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
    """トップの右の列（PC だけ。スマホでは消す）：これからの予定（日付のある記事があるときだけ）と欲しい物リスト（2026-10-18 に話題度ランキングとあなたの好みは外した）。
    どちらもデータがなければ出さず、両方なければ列ごと消えて写真の壁が横いっぱいになる。"""
    out = []
    ag = _agenda(works, today, 6)
    if ag:
        out.append(ag)
    want = [x for x in wishes if (x.get("status") or "想要") in ("想要", "纠结")]
    if not want:   # 0 件でも箱は出す：ここから最初の 1 件を足せる
        out.append('<div class="sbox swish"><h4><a href="wishlist.html">欲しい物リスト</a><small>0 件</small></h4>'
                   '<p class="sempty">まだありません。欲しい物の写真を送ると、ここに並びます。</p>'
                   '<a class="smore" href="wishlist.html#snap">♥ 欲しい物を足す</a></div>')
    else:
        rows = []
        for x in want[:7]:  # 入りきらない分は WALL_JS が下から隠す
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
    return f'<aside class="fside">{"".join(out)}</aside>' if out else ""


def _front(works, today, updated, themes=None, wishes=(), taste=()):
    """トップ：直近一週間の総覧。
    - ポスター：直近一週間でいちばん重要な 1 本（同じ重要度なら新しいほう）。地色はその記事の写真から
    - ほかの注目ニュース：次に重要な写真つきの記事（SPOT_COUNT 本）の写真の壁（文字だけの一覧は出さない）
    - ジャンルの棚：作品ごとに最新の 1 本（ポスターと壁に出たものはなるべく避ける）。押すとその作品の版面へ"""
    pool = [(w, x) for w in works for x in _recent(w, today)]
    newest = sorted(pool, key=lambda p: p[1].get("date") or p[1]["_issue"], reverse=True)
    # ポスターと壁は写真があるものだけ（来源アイコンは数えない）。借りた作品の表紙は、同じ重要度なら記事自身の写真の後ろ
    pictured = [p for p in newest if _has_photo(p[1])]
    ranked = sorted(pictured, key=lambda p: (RANK.get(p[1].get("weight"), 2), not _own_photo(p[1])))
    chosen = _front_pick(ranked, SPOT_COUNT)
    top_w, top = chosen[0] if chosen else (None, None)
    more = chosen[1:]

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
    shelves, n_works = [], 0
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
        n_works += len(tapes)
        shelves.append(f'<div class="shelf" style="--sc:{_sec_color(name)};--n:{len(tapes)}">'
                       f'<h3 class="sign">{e(_sec_name(name))}<small>{en + " · " if en else ""}{len(tapes)} 作品</small></h3>'
                       f'<div class="tapes">{"".join(tapes)}</div><div class="plank"></div></div>')
    side = _side(works, today, wishes, taste)
    spot = ""
    if more or shelves:
        spot = (f'<div class="spot"><h2 class="sh"><span>ほかの注目ニュース</span><small>直近 {HOLD_DAYS} 日から · 作品ごとの最新は下の棚（たたんであります）</small></h2>'
                + (f'<div class="mgrid"><div class="wall">{wall}</div>{side}</div>' if more else "")
                + (f'<details class="shelfbox"><summary><b>ジャンル別の最新</b><small>{n_works} 作品 · {len(shelves)} ジャンル</small>'
                   f'<span class="shopen">ひらく</span><span class="shclose">たたむ</span></summary>'
                   f'<div class="shelves">{"".join(shelves)}</div></details>' if shelves else "") + "</div>")
    return f'<section class="front" data-k="front" id="front">{poster}{spot}</section>'


AGENDA_MAX = 8


def _left(d, today):
    """あと何日（当日は「今日」）。"""
    n = (dt.date.fromisoformat(d[:10]) - dt.date.fromisoformat(today)).days
    return "今日" if n == 0 else f"あと {n} 日"


def _agenda(works, today, limit=None):
    """これからの予定：記事に event（日程）があるものを、今日以降・日付順に最大 AGENDA_MAX 件。
    同じ日・同じ見出しは 1 回だけ。同じ作品・同じ日・同じラベル（配信日など）も 1 回だけ：言語違いの記事が
    lang.dedupe をすり抜けても、予定の欄に同じ予定を 2 回出さない（好みの言語の記事を先に見る）。予定が 1 件もなければ何も出さない。"""
    rows, seen = [], set()
    for w in works:
        langs = w.get("_langs") or lang.order()
        for x in sorted(w["stories"], key=lambda x: lang.rank(lang.detect(x["headline"]), langs)):
            ev = x.get("event") if isinstance(x.get("event"), dict) else None
            d = str((ev or {}).get("date") or "")
            same = (d[:10], w["name"], (ev or {}).get("label") or "")
            if len(d) < 10 or d[:10] < today or (d[:10], x["headline"]) in seen or same in seen:
                continue
            seen.update({(d[:10], x["headline"]), same})
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


# 左侧目录的宽屏样式（v6）。items.yaml 的 settings.nav_style 以前可选 4 种，现在只有这一种（写别的也用它）
NAV_STYLES = {
    "line": """
/* v6（testground/compare.html）：板块ごとの枠を画面の高さいっぱいに並べる。作品が少ないうちは何も隠さず行の間隔を広げ、
   増えたら NAV_JS が ①ほかの板块は新着順に数件 ②ほかは見出しだけ ③いまの小分類だけ ④入るだけ＋「ほか N 件」の順に隠す。
   見た目は原版の線路：読んでいる駅のアイコンが弾んで大きくなり、読んだ駅は線が板块色で埋まる */
.nav{top:0;height:100vh;margin-top:-40px;padding:16px 0 12px 14px;border-left:6px solid var(--cur,var(--alert));color:var(--ink);transition:border-color .15s}   /* 左の縦線は読んでいる板块の色 */
/* ---------- ロゴ：炎（話題度で燃え方が変わる）＋ 仮の名前 TBD ---------- */
.nav .logo{position:relative;z-index:3;flex:none;display:flex;align-items:center;gap:10px;margin:16px 8px 10px 0;text-decoration:none;color:var(--ink)}
.nav .flame{position:relative;flex:none;width:50px;height:68px;margin:-6px -4px 0 -2px;--h:var(--heat,.3);
 /* 温度の色：冷めた火（0）＝暗い赤の熾火 → 熱い火（1）＝橙・金・白。--hc は NAV_JS が毎フレーム滑らかに入れる */
 --hc:var(--h);transform-origin:50% 45%;
 /* 作品の色（版面の --acc）と板块の色（--sc）を NAV_JS が --tint・強さ --tw に入れ、外側ほど強く混ぜる（白い芯はそのまま）。2 色の間をゆっくり行き来する */
 --fo:color-mix(in oklab,color-mix(in oklab,color-mix(in oklab,var(--ember),var(--alert) calc(clamp(0,var(--hc) * 1.8,1) * 100%)),var(--flame) calc(clamp(0,(var(--hc) - .55) * 2.2,1) * 100%)),var(--tint,var(--flame)) calc(var(--tw,0) * 70%));
 --fm:color-mix(in oklab,color-mix(in oklab,color-mix(in oklab,var(--ember),var(--flame) calc(clamp(0,var(--hc) * 1.6,1) * 100%)),var(--gold) calc(clamp(0,(var(--hc) - .5) * 2,1) * 100%)),var(--tint,var(--flame)) calc(var(--tw,0) * 50%));
 --fi:color-mix(in oklab,color-mix(in oklab,var(--flame),var(--gold) calc(clamp(0,var(--hc) * 1.4,1) * 100%)),var(--tint,var(--flame)) calc(var(--tw,0) * 25%));
 --fc:color-mix(in oklab,var(--gold),var(--card) calc(clamp(.15,var(--hc),1) * 100%))}

.nav .flame svg{position:absolute;left:0;bottom:0;width:100%;height:100%;overflow:visible;transform-origin:50% 100%;
 transform:scale(calc(.42 + var(--h) * .98));transition:transform .5s cubic-bezier(.2,.8,.2,1);
 filter:brightness(calc(.9 + var(--hc) * .25 + var(--fx,0) * .45))}   /* --fx：ぶわっ（燃え上がる瞬間）の明るさ */
/* 後ろの光：話題度が高いほど広く濃く、ゆっくり息をする */
.nav .flame .blue{opacity:clamp(0,(var(--hc) - .75) * 2.6,.55)}   /* 沸騰に近づくと底に青い炎 */
.nav .flame .glow{position:absolute;left:50%;bottom:-6px;width:calc(16px + var(--h) * 84px);aspect-ratio:1;translate:-50% 0;border-radius:50%;
 background:radial-gradient(closest-side,color-mix(in srgb,var(--fm) 70%,transparent),transparent);opacity:calc(.05 + var(--h) * .9);
 transition:opacity .5s,width .5s;animation:breathe calc(3s - var(--h) * 2.2s) ease-in-out infinite alternate}
/* ぶわっの演出（NAV_JS）：canvas は画面に重ねるが、ふだんはロゴのまわりにしか描かない（「沸騰」に上がったときだけ少し広く） */
.sparkfx{position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:60;display:none}
/* 話題度の数字が弾んで数え上がり、ロゴが小さく揺れる */
.nav .hm .hv.hvpop{animation:hvpop .7s cubic-bezier(.2,1.6,.4,1)}
@keyframes hvpop{0%{transform:scale(1.9) rotate(-8deg);color:var(--flame);text-shadow:0 0 12px var(--gold)}100%{transform:none}}
.nav .logo.quake{animation:quake .35s linear}
@keyframes quake{20%{transform:translate(-2px,1px) rotate(-1deg)}40%{transform:translate(2px,-1px) rotate(1deg)}60%{transform:translate(-1px,-1px)}80%{transform:translate(1px,1px)}}
@keyframes breathe{to{transform:scale(1.12);filter:brightness(1.15)}}
/* 火の粉：位置・寿命・道筋は NAV_JS が 1 粒ずつ決める */
.nav .flame .em{position:absolute;left:50%;bottom:22%;width:3px;height:3px;margin-left:-1.5px;border-radius:50%;background:var(--gold);
 box-shadow:0 0 4px var(--flame);opacity:0;will-change:transform,opacity}
.nav .wm{display:flex;flex-direction:column;line-height:1;transform:rotate(-3deg)}
.nav .wm b{font:30px/.95 var(--font-num);letter-spacing:.04em;font-style:italic;background:var(--ink);color:var(--card);padding:2px 10px 1px 8px;
 transform:skewX(var(--skew));box-shadow:3px 3px 0 var(--cur,var(--alert))}
.nav .wm small{margin-top:5px;font:800 10px var(--font-sans);letter-spacing:.18em;color:rgba(26,28,34,.7)}
.nav .hm{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;line-height:1}
.nav .hm .hv{font:26px/1 var(--font-num);color:var(--cur,var(--alert))}
.nav .hm .hl{margin-top:3px;font:900 10px var(--font-sans);letter-spacing:.1em;color:rgba(26,28,34,.7)}
@media (prefers-reduced-motion:reduce){.nav .flame *{animation:none!important}}
.nav .nhead{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:0 12px;margin:0 8px 6px 0;padding-bottom:4px;border-bottom:2px solid var(--ink)}
.nav .nhead .pill{flex:none;height:30px;padding-left:4px;font-size:13px}
.nav .nhead .pill.on{padding-left:58px;padding-right:12px}
.nav .nhead .pill.on::before{display:block}   /* 読んでいるときは黒い斜めの箱を出す */
.nav .nhead .pill::before,.nav .nhead .pill::after{display:none}   /* トップ・気になるかも？は横 1 列（線路にはつなげない） */
.nav .nhead .pill.on .nm{flex-direction:row;align-items:baseline;gap:6px}
.nav .rail{flex:1;min-height:0;position:relative;overflow:hidden;margin-right:8px;scrollbar-width:thin}
.nav .pill{height:34px;padding:0 6px 0 34px;color:rgba(26,28,34,.86);font:800 15px/1.35 var(--font-sans)}
.nav .nbody .pill{height:var(--ih,34px)}   /* 高さはアニメーションしない（毎フレーム組み直しになって重い） */
.nav .pill .no{display:none}
.nav .pill .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav .pill .cnt{display:none;font:700 11px var(--font-mono);letter-spacing:.06em;color:rgba(26,28,34,.62)}
.nav .rail.roomy .pill .nm{display:flex;flex-direction:column;gap:1px}
.nav .rail.roomy .pill .cnt{display:block}
.nav .pill .new{flex:none;font:700 11px var(--font-mono);color:rgba(26,28,34,.5)}   /* 件数は控えめに（赤は読んでいる作品だけ） */
/* 線路：板块色の細い線に、駅は P5 の斜めの小さな札（丸は使わない）。読んだ駅は板块色で塗る */
.nav .pill::before{content:"";position:absolute;inset:0 auto 0 15px;width:2px;z-index:-1;background:rgba(26,28,34,.13)}
.nav .pill::after{content:"";position:absolute;left:9px;top:50%;width:14px;height:8px;margin-top:-4px;transform:skewX(var(--skew));
 background:var(--paper);border:2px solid rgba(26,28,34,.32);transition:background .2s,border-color .2s}
.nav .pill:hover{color:var(--ink)}
.nav .pill:hover::after{border-color:var(--sc)}
.nav .pill.past::before{background:var(--sc)}
.nav .pill.past::after{background:var(--sc);border-color:var(--sc)}
/* アイコンは読んでいる作品だけ：P5 のカットインのように、白フチ＋墨の硬い影で少し傾けて貼る。ほかの行には出さない */
.nav .pill .ic{display:none}
/* 読んでいる作品：原版（P5）の黒い斜めの箱＋赤い硬い影 */
.nav .pill.on::before{inset:4px -2px 4px 24px;width:auto;transform:skewX(var(--skew));background:var(--ink);box-shadow:4px 4px 0 var(--sc)}   /* 硬い影は板块の色 */
.nav .pill.on::after{display:none}
.nav .pill.on{color:var(--card);font-size:17px;font-weight:900;letter-spacing:-.01em;padding-left:58px}
.nav .pill.on .ic{display:grid;position:absolute;left:2px;top:50%;width:44px;height:44px;margin-top:-22px;border-radius:0;
 border:3px solid #FFF;box-shadow:3px 3px 0 var(--ink);transform:rotate(-7deg);font-size:18px;
 animation:cutin .2s cubic-bezier(.3,1.4,.5,1)}
@keyframes cutin{from{transform:rotate(-20deg) scale(.3);opacity:0}to{transform:rotate(-7deg) scale(1);opacity:1}}
.nav .pill.on .nm{display:flex;flex-direction:column;gap:1px}
.nav .pill.on .cnt{display:block;color:var(--gold)}
.nav .pill.on .new{color:var(--gold)}
.nav .nhead .pill.on{height:52px}
.nav .nbody .pill.on{height:calc(var(--ih,34px) + 22px)}
/* 板块のアイコン（twemoji）は宽屏では出さない：板块は色つきの斜めのラベルで十分 */
.nav .nsec .si{display:none}
/* 板块の枠：位置と高さは NAV_JS が決める（動くときはなめらかに） */
/* 枠の移動は transform だけ（GPU で動くので滑らか）。高さは即座に変え、下の枠が上に重なって隠す（背景は紙の色） */
.nav .nslot{position:absolute;left:0;right:0;top:0;overflow:hidden;background:var(--paper);will-change:transform;
 transition:transform .18s cubic-bezier(.2,.9,.3,1)}
.nav .nslot::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:var(--hair)}
.nav .nsec{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:4px 8px;height:42px;padding:8px 4px 0 0;text-decoration:none;color:var(--ink)}
.nav .nsec .tg{transform-origin:left center;transition:transform .18s cubic-bezier(.2,.9,.3,1),box-shadow .18s}
.nav .nsec .tg{font-size:14px;padding:1px 12px}
.nav .nslot.cur .nsec .tg{transform:skewX(var(--skew)) scale(1.22);box-shadow:3px 3px 0 var(--ink)}
.nav .nsec .meter{grid-column:1/-1;height:4px;background:var(--sc)}   /* 板块の色の下線（新着の件数は出さない、2026-10-18） */
.nav .nbody{position:absolute;left:0;right:0;top:52px}
.nav .nsum{margin:0 4px 0 6px;font:500 11px/1.55 var(--font-sans);color:rgba(26,28,34,.5);
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}   /* たたんだ板块の作品名：目立たせない */
.nav .nsum a{color:inherit;text-decoration:none}.nav .nsum a:hover{color:var(--ink);text-decoration:underline}
.nav .nsum b{margin-left:2px;font:700 10px var(--font-mono);color:var(--sc)}.nav .nsum span{margin-left:4px;opacity:.8}
.nav .nsum.x{display:none}
/* 上下級（案 A）：下級は上級の駅から出た枝線（拐角 └）の上の駅。大きさは普通の駅と同じ */
.nav .pill.kid{padding-left:52px}
.nav .pill.media .nm{font-size:13px;font-weight:700;color:rgba(26,28,34,.62)}   /* シリーズの中身：作品より小さめの字 */
.nav .pill.media::after{width:10px;height:6px;margin-top:-3px;left:32px}
.nav .pill.kid .br{position:absolute;left:14.5px;top:-17px;width:18px;bottom:50%;border-left:2px solid var(--sc);border-bottom:2px solid var(--sc);z-index:-1}
.nav .pill.kid::after{left:30px}
.nav .pill.kid.on{padding-left:76px}
.nav .pill.kid.on::before{inset:4px -2px 4px 48px}
.nav .pill.kid.on .ic{left:26px}
.nav .pill .xref{flex:none;font:700 10px var(--font-mono);letter-spacing:.06em;color:var(--sc);border:1px solid var(--sc);padding:0 4px}
.nav .pill.on .xref{color:var(--gold);border-color:var(--gold)}
.nav .pill.xfer{color:rgba(26,28,34,.62)}   /* 乗換の駅：版面はほかの板块。駅の印は白抜きの点線 */
.nav .pill.xfer::after{background:var(--card);border-style:dashed}
/* 小分類の札（横並び）：いまの板块に小分類が 2 つ以上あれば必ず出す。押すとその小分類の最初の作品へ */
.nav .nsubs{display:flex;flex-wrap:wrap;gap:5px 7px;margin:0 0 6px 4px}
.nav .nsubs a{display:flex;align-items:center;gap:5px;height:22px;padding:0 8px;border:1.5px solid rgba(26,28,34,.35);color:rgba(26,28,34,.75);
 font:800 11px/1 var(--font-sans);white-space:nowrap;text-decoration:none;transform:skewX(var(--skew))}
.nav .nsubs a small{font:12px var(--font-num)}
.nav .nsubs a:hover{color:var(--ink);border-color:var(--ink)}
.nav .nsubs a.on{background:var(--sc);border-color:var(--ink);color:#FFF;box-shadow:2px 2px 0 var(--ink)}
.nav .nlab{height:20px;display:flex;align-items:flex-end;gap:4px;padding:0 0 2px 6px;font:900 11px var(--font-sans);letter-spacing:.14em;color:var(--sc);
 transform:rotate(-2deg);transform-origin:left bottom}
.nav .nlab::before{content:"／";font-weight:900}
.nav .nlab b{margin-left:4px;font:14px/1 var(--font-num);letter-spacing:.02em}
.nav .nmore{display:flex;align-items:center;height:26px;padding:0 8px 0 34px;text-decoration:none}
.nav .nmore{font:900 12px var(--font-sans);color:var(--sc);letter-spacing:.04em}
.nav .nmore:hover{color:var(--alert)}
/* ---------- P5 の手ざわり：揃えすぎない ----------
   板块の行：日本語の札は少し傾け、右端に英字（GAMES…）を透かしで（新着の件数は 2026-10-18 にやめた） */
.nav .nsec{position:relative;isolation:isolate}
.nav .nsec .tg{font-size:15px;padding:1px 13px;transform:skewX(var(--skew)) rotate(-2deg);box-shadow:2px 2px 0 var(--ink)}
.nav .nslot.cur .nsec .tg{transform:skewX(var(--skew)) rotate(-3deg) scale(1.22);box-shadow:4px 4px 0 var(--ink)}
.nav .nsec .en{position:absolute;right:2px;top:5px;z-index:-1;font:28px/1 var(--font-num);letter-spacing:.01em;color:var(--sc);opacity:.16;
 transform:skewX(var(--skew)) rotate(-3deg);white-space:nowrap;pointer-events:none}
.nav .nslot.cur .nsec .en{opacity:.26}
/* 作品の行：名前を 1 行ごとに少しずつずらし・傾ける（線路の駅は揃えたまま）。+N は Anton */
.nav .nbody .pill .nm{transform-origin:left center}
.nav .nbody .pill:nth-of-type(3n+1) .nm{transform:rotate(-.9deg)}
.nav .nbody .pill:nth-of-type(3n+2) .nm{transform:translateX(4px) rotate(.5deg)}
.nav .nbody .pill:nth-of-type(3n) .nm{transform:translateX(1px) rotate(-.3deg)}
.nav .pill .new{font:14px/1 var(--font-num);letter-spacing:.02em;color:rgba(26,28,34,.42)}
/* 読んでいる作品：黒い斜めの箱の右端に黄色の斜線、名前は大きく・赤い影。頭の 1 文字だけさらに大きく */
.nav .nbody .pill.on .nm{transform:rotate(-2deg) translateY(-1px)}
.nav .pill.on{font-size:18px}
.nav .pill.on .nm{text-shadow:2px 2px 0 var(--sc);letter-spacing:.01em}
.nav .pill.on .nm::first-letter{font-size:1.3em}
.nav .pill.on .cnt{text-shadow:none;letter-spacing:.1em}
.nav .pill.on .new{font-size:20px;color:var(--gold);text-shadow:2px 2px 0 var(--sc)}
.nav .pill.on::after{display:block;content:"";position:absolute;left:auto;right:4px;top:-3px;bottom:-3px;width:9px;height:auto;margin:0;border:0;
 background:var(--gold);transform:skewX(-24deg);box-shadow:2px 2px 0 var(--ink)}
.nav .pill.on .new{margin-right:14px}
.nav .nhead .pill.on::after{display:block}
.nav .navwish{margin:8px 8px 0 0}
""",
}


# 板块のアイコン（twemoji、sections.yaml の icon）。表にない板块はアイコンなし
SECTION_ICON = {k: str(r["icon"]) for k, r in taxonomy.SECTIONS.items() if r.get("icon")}
TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/svg/{}.svg"
NAV_HIDE = 24   # 左の目次で隠し始める作品の数（items.yaml の settings.nav_hide。"auto" なら画面の高さで決める）


def _nav_icon(w):
    """目次の作品アイコン：items.yaml の icon（作品・ブランドを一目で表す 1 枚、docs/icons/）→ emblem → 封面・最近の記事の写真。
    なければ None（頭文字を出す）。"""
    icon = str(w.get("_icon") or "")
    if re.fullmatch(r"icons/[a-z0-9-]+\.webp", icon) or icon.startswith("https://"):
        return icon
    for x in w.get("_emblems") or []:
        img = str(x.get("image") or "") if isinstance(x, dict) else ""
        if re.fullmatch(r"emblems/[a-z0-9-]+\.webp", img) or img.startswith("https://"):
            return img
    t = w.get("_thumb") or next((x.get("image") for x in w.get("stories") or [] if x.get("image")), None)
    return _img_url(t) if t and str(t).startswith("https://") else None


# 目次の左上のロゴの炎（testground/flame.html で決めた形）。先の尖った涙形を 4 層（赤・橙・金・白い芯）重ね、話題度が高いと左右に舌が出る。
# 縁は SVG の乱流（feTurbulence → feDisplacementMap）で揺らし、層ごとの伸び縮み・傾き・揺れは NAV_JS が周期の違う波を足して不規則に動かす。
# 話題度（heat.py の 0〜100）で 大きさ・揺れの速さと大きさ・舌・光・火の粉の数が変わり、読んでいる間ずっとその強さで燃える
_TEAR = "M50 6C55 30 66 44 76 60C84 73 86 86 84 98C81 118 67 132 50 132C33 132 19 118 16 98C14 86 16 73 24 60C34 44 45 30 50 6Z"
_TONGUE = "M50 40C53 60 62 72 66 88C70 104 62 118 50 120C38 118 30 104 34 88C38 72 47 60 50 40Z"


def _flame_grad(n, color, mid, top_alpha):
    return (f'<linearGradient id="navfl-{n}" x1="0" y1="1" x2="0" y2="0"><stop offset="0" style="stop-color:var({color})"/>'
            f'<stop offset="{mid}" style="stop-color:var({color});stop-opacity:{top_alpha}"/>'
            f'<stop offset="1" style="stop-color:var({color});stop-opacity:0"/></linearGradient>')


# 目次のロゴの炎（と、ぶわっ・版面の火）は保留中（2026-10-18、PENDING.md）：True に戻せば全部また動く
NAV_FLAME = False
FLAME_SVG = (
    '<span class="flame" aria-hidden="true"><i class="glow"></i><svg viewBox="0 0 100 140"><defs>'
    '<filter id="navfl-f" x="-30%" y="-30%" width="160%" height="140%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.03 0.07" numOctaves="1" seed="13"/>'
    '<feDisplacementMap in="SourceGraphic" scale="12" xChannelSelector="R" yChannelSelector="G"/>'
    '<feGaussianBlur stdDeviation=".8"/></filter>'
    + _flame_grad("o", "--fo", .55, .95) + _flame_grad("m", "--fm", .6, .9)
    + _flame_grad("i", "--fi", .65, .85) + _flame_grad("c", "--fc", .6, .7)
    + '<radialGradient id="navfl-b" cx="50%" cy="50%" r="50%"><stop offset="0" style="stop-color:var(--blueflame)"/>'
      '<stop offset="1" style="stop-color:var(--blueflame);stop-opacity:0"/></radialGradient>'
    + '</defs><g filter="url(#navfl-f)">'
    + "".join(f'<path class="L" data-k="{k}" d="{_TONGUE if k in ("tl", "tr") else _TEAR}" fill="url(#navfl-{g})"/>'
              for k, g in (("tl", "m"), ("tr", "m"), ("o", "o"), ("m", "m"), ("i", "i"), ("c", "c")))
    + '<ellipse class="blue" cx="50" cy="130" rx="15" ry="5" fill="url(#navfl-b)"/>'
    + '<ellipse class="puff" cx="50" cy="80" rx="0" ry="0" fill="url(#navfl-m)" opacity="0"/>'
    + '</g></svg>' + '<i class="em"></i>' * 16 + '</span>')


# シリーズの中身（items.yaml の media）：目次でシリーズの駅の下に枝で出す媒体と、その媒体の記事を数える語
MEDIA_WORDS = {
    "マンガ": "漫画|漫畫|マンガ|manga|comic|単行本|单行本|連載|连载|最新刊|最新話",
    "アニメ": "アニメ|anime|动画|動畫|TVアニメ|放送|配信",
    "映画": "映画|劇場版|剧场版|電影|电影|movie|film|興行|公開",
    "ドラマ": "ドラマ|drama|電視劇|电视剧|剧集|劇集|実写|series",
    "小説・ラノベ": "小説|小说|小說|novel|ラノベ|ライトノベル",
    "ゲーム": "ゲーム|game|游戏|遊戲|アプリ",
    "グッズ": "グッズ|コラボ|一番くじ|フィギュア|ぬいぐるみ|周边|周邊|联名|聯名|merch",
    "イベント": "イベント|展覧会|展示|カフェ|ポップアップ|POP ?UP|フェア",
    "舞台・ライブ": "舞台|ミュージカル|ライブ|コンサート|musical|concert",
}


def _nav(works, date, wishes=(), picks=(), subs=None, hide=NAV_HIDE, parents=None, sub_heat=None, also=None, media=None):
    """左侧目录（v6）：板块ごとの枠に作品を並べる（小分類ごと）。どこを隠すかは NAV_JS が画面の高さで決める。
    subs：{作品: 小分類}（items.yaml の sub）。hide：隠し始める作品の数（"auto" なら画面の高さで決める）。
    parents：{下級: 上級}（items.yaml の parent）。下級は上級の駅のすぐ下に、上級の小分類で、枝線（拐角 └）つきで並ぶ（案 A）。
    上下級は同じ関注項なので、下級を小さくしたり特別にたたんだりしない。
    並びは works の順（digest が heat.heat_order で「小分類の話題度 → 作品の話題度」に並べて渡す）。sub_heat：{(板块, 小分類): 話題度}。
    also：{作品: [(ほかの板块, その板块での小分類)]}（items.yaml の also）。版面は本来の板块に 1 つだけ。ほかの板块には「乗換」の駅
    （.pill.xfer、「⇄ 本来の板块」の札）を置き、押すと同じ版面へ飛ぶ。同じニュースは 1 回しか出ない。
    media：{作品: [媒体…]}（items.yaml の media、シリーズの中身）。その駅の下に枝（└ マンガ / アニメ / 映画）で出し、
    直近の記事のうちその媒体の語（MEDIA_WORDS）が見出し・要約にある件数を「+n」で。押すと同じ版面へ。"""
    groups, xfers = {}, {}
    for w in works:
        groups.setdefault(w.get("section") or "其他", []).append(w)
    for w in works:
        for sec, sb in (also or {}).get(w["name"], ()):
            if sec != (w.get("section") or "其他"):
                xfers.setdefault(sec, []).append((w, sb))
                groups.setdefault(sec, [])
    order = [n for n in SECTIONS if n in groups] + [n for n in groups if n not in SECTIONS]
    cutoff = (dt.date.fromisoformat(date) - dt.timedelta(days=HOLD_DAYS - 1)).isoformat()
    page_no = {w["name"]: i + 1 for i, w in enumerate(works)}   # 版面の順（読んだ印・新着順の同点はこの順）
    subs, parents, sub_heat = subs or {}, parents or {}, sub_heat or {}

    def pill(w, sc, sub="", kid=False):
        if isinstance(kid, str) and kid.startswith("m:"):   # シリーズの中身の枝：data-for は付けない（読んでいる印は作品の駅に）
            lab = kid[2:]
            rx = re.compile(MEDIA_WORDS.get(lab) or re.escape(lab), re.I)
            n = sum(1 for x in w["stories"] if x["_issue"] >= cutoff and rx.search(f'{x.get("headline", "")} {x.get("blurb", "")}'))
            return (f'<a class="pill kid media" style="--sc:{sc}" data-x="{e(w["name"])}" data-n="{page_no[w["name"]]}" data-hot="{n}" '
                    f'data-sub="{e(sub)}" href="#{_wid(w["name"])}" title="{e(w["name"])} の{e(lab)}"><span class="br"></span>'
                    f'<span class="nm">{e(lab)}</span>' + (f'<span class="new">+{n}</span>' if n else "") + '</a>')
        recent = sum(1 for x in w["stories"] if x["_issue"] >= cutoff)
        icon = _nav_icon(w)
        ic = (f'<i class="ic has" style="--img:url({e(urllib.parse.quote(icon, safe=":/?&=%#@+,;~"))})"></i>' if icon
              else f'<i class="ic">{e(w["name"][:1])}</i>')
        own = subs.get(w["name"], "")
        xref = f'<span class="xref">{e(own)}</span>' if kid is True and own and own != sub else ""   # 自分の小分類が上級と違うときは小さく
        if kid == "x":   # 乗換の駅：data-for は付けない（読んでいる版面の印は本来の板块の駅に出す）
            home = w.get("section") or "其他"
            return (f'<a class="pill xfer" style="--sc:{sc}" data-x="{e(w["name"])}" data-n="{page_no[w["name"]]}" data-hot="{recent}" '
                    f'data-sub="{e(sub)}" href="#{_wid(w["name"])}" title="版面は「{e(_sec_name(home))}」にあります">'
                    f'<i class="no">{page_no[w["name"]]:02d}</i>{ic}'
                    f'<span class="nm">{e(w["name"])}<small class="cnt">{f"今週 {recent} 件" if recent else "新着なし"}</small></span>'
                    f'<span class="xref" style="--sc:{_sec_color(home)}">⇄ {e(_sec_name(home))}</span></a>')
        return (f'<a class="pill{" kid" if kid else ""}" style="--sc:{sc}" data-for="{e(w["name"])}" data-n="{page_no[w["name"]]}" data-hot="{recent}" data-heat="{int((w.get("_heat") or {}).get("score") or 0)}" '
                f'data-sub="{e(sub)}" href="#{_wid(w["name"])}"><i class="no">{page_no[w["name"]]:02d}</i>{ic}'
                + ('<span class="br"></span>' if kid else "")
                + f'<span class="nm">{e(w["name"])}<small class="cnt">{f"今週 {recent} 件" if recent else "新着なし"}</small></span>'
                + xref + (f'<span class="new">+{recent}</span>' if recent else "") + '</a>')

    head = [f'<a class="pill" style="--sc:#D7261E" data-for="front" data-n="0" href="#front"><i class="no">00</i>'
            f'<i class="ic">★</i><span class="nm">トップ<small class="cnt">FRONT PAGE</small></span></a>']
    if picks:
        head.append(f'<a class="pill" style="--sc:#B8336A" data-for="picks" data-n="0" href="#picks"><i class="no">?</i>'
                    f'<i class="ic">?</i><span class="nm">気になるかも？<small class="cnt">候補 {len(picks)} 件</small></span></a>')
    tabs = ['<a class="tg on" style="--sc:var(--ink)" data-sec="" href="#front"><span>トップ</span></a>']
    slots = []
    for name in order:
        sc, ws = _sec_color(name), groups[name]
        icon = (f'<img class="si" src="{TWEMOJI.format(SECTION_ICON[name])}" alt="" loading="lazy">' if name in SECTION_ICON else "")
        # 上下級：上級が同じ板块にいる下級は、上級のすぐ下に並べる（小分類も上級に従う）
        names = {w["name"] for w in ws}
        is_kid = lambda w: parents.get(w["name"]) in names and parents.get(w["name"]) != w["name"]
        rows = []   # (作品, 目次での小分類, 下級か)
        for w in ws:
            if is_kid(w):
                continue
            rows.append((w, subs.get(w["name"], ""), False))
            rows += [(w, subs.get(w["name"], ""), "m:" + m) for m in (media or {}).get(w["name"], ())]   # シリーズの中身
            for k in ws:
                if is_kid(k) and parents[k["name"]] == w["name"]:
                    rows.append((k, subs.get(w["name"], ""), True))
                    rows += [(k, subs.get(w["name"], ""), "m:" + m) for m in (media or {}).get(k["name"], ())]
        rows += [(w, sb, "x") for w, sb in xfers.get(name, ())]   # ほかの板块の作品の乗換駅（その板块での小分類に入れる）
        if not rows:
            continue
        top_href = _wid(rows[0][0]["name"])
        sub_order = list(dict.fromkeys(sb for _, sb, _ in rows))
        tabs.append(f'<a class="tg" style="--sc:{sc}" data-sec="{e(name)}" href="#{top_href}"><span>{e(_sec_name(name))}</span></a>')
        body = ""
        if any(sub_order):   # 小分類があれば（1 つだけでも）必ず札を出し、作品は小分類ごとにまとめる（小見出しつき）
            first = {sb: next(w for w, x, _ in rows if x == sb) for sb in sub_order}
            body += ('<div class="nsubs">' + "".join(
                f'<a data-sub="{e(sb)}" href="#{_wid(first[sb]["name"])}">{e(sb or "その他")}'
                f'<small>{sum(1 for _, x, kd in rows if x == sb and not (isinstance(kd, str) and kd.startswith("m:")))}</small></a>' for sb in sub_order) + '</div>')
            for sb in sub_order:
                hs = sub_heat.get((name, sb))
                body += (f'<div class="nlab" data-sub="{e(sb)}">{e(sb or "その他")}'
                         + (f'<b title="小分類の話題度">{int(hs)}</b>' if isinstance(hs, (int, float)) else "") + '</div>')
                body += "".join(pill(w, sc, x, kid) for w, x, kid in rows if x == sb)
        else:
            body += "".join(pill(w, sc, x, kid) for w, x, kid in rows)
        body += f'<a class="nmore x" href="#{top_href}"></a>'
        # 板块が見出しだけにたたまれたときの空きに、中の作品名を薄い小さな字で 1〜2 行（新着の多い順・+n）。メインは板块なので目立たせない
        own = [w for w, _, kd in rows if kd in (False, True)]
        cnt = {w["name"]: sum(1 for x in w["stories"] if x["_issue"] >= cutoff) for w in own}
        own.sort(key=lambda w: (-cnt[w["name"]], page_no[w["name"]]))
        if own:
            body = ('<div class="nsum x">' + "・".join(
                f'<a href="#{_wid(w["name"])}">{e(w["name"])}' + (f'<b>+{cnt[w["name"]]}</b>' if cnt[w["name"]] else "") + '</a>'
                for w in own[:8]) + (f'<span>ほか {len(own) - 8} 件</span>' if len(own) > 8 else "") + '</div>') + body
        slots.append(f'<div class="nslot" style="--sc:{sc}" data-sec="{e(name)}">'
                     f'<a class="nsec" href="#{top_href}">{icon}<span class="tg"><span>{e(_sec_name(name))}</span></span>'
                     f'<span class="en" aria-hidden="true">{e(_sec_en(name))}</span>'
                     f'<span class="meter"></span></a>'
                     f'<div class="nbody">{body}</div></div>')
    hide = "auto" if str(hide).lower() == "auto" else max(1, int(hide or NAV_HIDE))
    levels = json.dumps([[low, lab] for low, lab in heat.LEVELS], ensure_ascii=False)
    return (f'<nav class="nav" aria-label="目次" data-hide="{hide}" data-levels="{e(levels)}">'
            f'<div class="mtabs">{"".join(tabs)}</div>'
            f'<a class="logo" href="#front" aria-label="トップへ">{FLAME_SVG if NAV_FLAME else ""}'
            f'<span class="wm"><b>TBD</b><small>ウォッチリスト通信</small></span>'
            f'<span class="hm" aria-live="polite"><b class="hv"></b><small class="hl"></small></span></a>'
            f'<div class="nhead">{"".join(head)}</div>'
            f'<div class="rail" id="nav-rail">{"".join(slots)}</div>{_wish_link(wishes, "navwish")}'
            f'<div class="bar" id="nav-bar"></div></nav>')


# 写真の収め方：縦横比が枠とだいたい同じ（±30%）なら枠いっぱいに（.fill）、違えばぼかしの上に全体を表示（既定）。
# どんな記事の写真でも同じ型に収まる。スクリプトがないときは全部「全体を表示」
FIT_JS = """
(() => {
  const fit = img => {
    const p = img.closest('.pic');
    // 期限切れ・削除された図の代わりに返ってくる 1×1 の空白（Yahoo の exp= 付き画像など）は「開けない」と同じ扱い：次の候補へ
    if (img.naturalWidth && img.naturalWidth < 3 && img.naturalHeight < 3 && img.onerror) { img.onerror(); return; }
    if (!p || !img.naturalWidth || !p.clientHeight) return;
    const nat = img.naturalWidth / img.naturalHeight;
    const pk = p.closest('.pk');
    if (pk) {   // 気になるかも？：写真は切らない（文字入りのバナーが多い）。下に重なる札の分（--pko）は写真の外
      const pko = parseFloat(getComputedStyle(p).getPropertyValue('--pko')) || 0;
      p.style.height = p.style.aspectRatio = p.style.minHeight = '';
      if (innerWidth <= 760) {   // 1 列：枠を写真の比率にする（縦長すぎ・横長すぎは 1.1〜2.4 倍の範囲でぼかしを足す）
        const w = p.clientWidth, h = Math.min(Math.max(w / nat, w / 2.4), w * 1.1);
        Object.assign(p.style, {aspectRatio: 'auto', minHeight: '0', height: (h + pko) + 'px'});
        p.classList.remove('fill');
        return;
      }
      const r = nat / (p.clientWidth / Math.max(1, p.clientHeight - pko));
      p.classList.toggle('fill', Math.abs(Math.log(r)) < 0.08);   // ほぼ同じ比率のときだけ埋める（切れるのは 8% まで）
      return;
    }
    // 枠の大きさは変えない（写真の壁は 16:10 のまま段の高さがそろう）。写真は切らない：ほぼ同じ比率（切れるのは 8% まで）のときだけ埋め、
    // そうでなければぼかしの上に全体を見せる。配図は文字・ロゴ入りのバナーが多く、端を切ると欠ける（2026-10-17 ユーザー指摘）
    const r = nat / (p.clientWidth / p.clientHeight);
    p.classList.toggle('fill', Math.abs(Math.log(r)) < 0.08);
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
    if (side) side.style.minHeight = '';
    if (innerWidth <= 760) return;
    // 2 列しか入らない幅（右の列が下に回る）では大きい 1 枚＋4 枚まで
    if (getComputedStyle(w).gridTemplateColumns.split(' ').length < 3) { cards.forEach((c, i) => { c.hidden = i >= 5; }); return; }
    // 「ほかの注目ニュース」全体（見出し・棚の帯まで）を 1 画面に収める：画面の高さから見出しと棚の帯の分を引いたのが壁と右の列の上限
    const hh = sel => document.querySelector(sel)?.getBoundingClientRect().height || 0;
    const target = Math.max(520, innerHeight - (hh('.spot > .sh') || 56) - (hh('.spot > .shelfbox > summary') || 44) - 22 * 2 - 24);
    if (side) {
      // 入りきらないときは欲しい物（3 件目以降）→ 予定（4 件目以降）→ 欲しい物（2 件目）→ 予定（2・3 件目）の順に下から隠す
      const rows = sel => [...side.querySelectorAll(sel)];
      const ag = rows('.agenda li'), wi = rows('.swish li');
      const order = [...wi.slice(2).reverse(), ...ag.slice(3).reverse(), ...wi.slice(1, 2), ...ag.slice(1, 3).reverse()];
      [...ag, ...wi].forEach(l => l.hidden = false);
      for (const l of order) { if (side.getBoundingClientRect().height <= target) break; l.hidden = true; }
    }
    // 大きい 1 枚（2 列 × 2 段）＋横の (列数 − 2) × 2 枚で 2 段、そのあと列数ずつ 1 段
    const cols = getComputedStyle(w).gridTemplateColumns.split(' ').length;
    const upto = r => 1 + (cols - 2) * 2 + (r - 2) * cols;
    let rows = 2;
    const show = r => cards.forEach((c, i) => { c.hidden = i >= upto(r); });
    show(rows);
    while (upto(rows + 1) <= cards.length) {
      show(rows + 1);
      if (w.getBoundingClientRect().height > target) { show(rows); break; }
      rows++;
    }
    // 左の壁と右の列の上端・下端をそろえる：高いほうに合わせ、壁は各段の写真枠に等分して足し、右の列は最後の箱が伸びる
    const H = Math.max(w.getBoundingClientRect().height, side ? side.getBoundingClientRect().height : 0);
    if (side) side.style.minHeight = H + 'px';
    const gap = H - w.getBoundingClientRect().height;
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
  // 軽い吸着（PC だけ）：スクロールが止まったとき、版面などの上端が画面の上から 72px 以内なら、そこへそっと合わせる。
  // それより離れていれば何もしない（CSS の scroll-snap は吸い付く範囲がブラウザまかせで強すぎるので使わない）
  const SNAP = 72, snapAt = () => document.querySelectorAll('.front .poster, .spot, .picks, .sec');
  let st, snapping = false;
  const snap = () => {
    if (snapping) { snapping = false; return; }
    if (innerWidth <= 760 || document.querySelector('dialog[open]') || document.activeElement?.matches('input, textarea, select')) return;
    let best = null;
    for (const el of snapAt()) {
      const d = el.getBoundingClientRect().top - (parseFloat(getComputedStyle(el).scrollMarginTop) || 16);
      if (Math.abs(d) <= SNAP && (best === null || Math.abs(d) < Math.abs(best))) best = d;
    }
    if (best !== null && Math.abs(best) >= 2) {
      snapping = true;
      scrollBy({ top: best, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  };
  if ('onscrollend' in window) addEventListener('scrollend', snap);
  else addEventListener('scroll', () => { clearTimeout(st); st = setTimeout(snap, 160); }, { passive: true });
})();
"""


NAV_JS = """
(() => {
  // 左の目次（v6・testground/compare.html で決めた形）
  const nav = document.querySelector('.nav'), rail = document.getElementById('nav-rail');
  if (!nav || !rail) return;
  // 只认版面级的区块（头版、我会喜欢？、各作品版面），卡片上的 data-k（投票用）不算
  // 出ている版面・駅だけを数える（お客さまのページでは AUTH_JS が版面を .wl-off で隠し・自分の版面と駅を足して 'wl-nav' を送る → 数え直す）
  const vis = el => !el.classList.contains('wl-off');
  let marks, pills, byKey, tabs, S, slotOf, TOTAL;
  const firstIssue = document.querySelector('.issue');
  function scan() {
    marks = [...document.querySelectorAll('.issue > [data-k]')].filter(vis);
    pills = [...nav.querySelectorAll('.pill')].filter(vis);
    byKey = new Map(pills.map((p, i) => [p.dataset.for, i]));
    tabs = [...nav.querySelectorAll('.mtabs a')].filter(vis);
    S = [...rail.querySelectorAll('.nslot')].filter(vis).map(el => ({el, sec: el.dataset.sec,
      pills: [...el.querySelectorAll('.nbody .pill')].filter(vis), subs: el.querySelector('.nsubs'), chips: [...el.querySelectorAll('.nsubs a')].filter(vis),
      labs: [...el.querySelectorAll('.nlab')].filter(vis), more: el.querySelector('.nmore'), sum: el.querySelector('.nsum')}));
    slotOf = new Map();
    S.forEach((s, i) => s.pills.forEach(p => slotOf.set(p, i)));
    TOTAL = S.reduce((a, s) => a + s.pills.length, 0);
  }
  scan();
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches, wide = matchMedia('(min-width: 1001px)');
  // 隠し始める作品の数（items.yaml の settings.nav_hide、既定 24）。auto なら画面の高さだけで決める。
  // どちらでも、行を 30px まで詰めても入らないときは隠す（窮屈にもスクロールにもしない）
  const HIDE = nav.dataset.hide === 'auto' ? 0 : (+nav.dataset.hide || 24);
  const SEC_H = 52, ITEM_H = 34, R_MIN = 30, MORE_H = 26, MIN_H = 46, EXTRA = 22, LAB_H = 20, SPARE_MAX = 28;   // 行の高さ（NAV_STYLES と同じ）
  const hot = p => +p.dataset.hot || 0, num = p => +p.dataset.n || 0, subOf = p => p.dataset.sub || '';
  const topN = (l, n) => l.slice().sort((a, b) => hot(b) - hot(a) || num(a) - num(b)).slice(0, n);
  let curIdx = -2, curProg = -1, ticking = false, lk = null, lsub = null, lon = null;
  const isMed = p => p.classList.contains('media');   // シリーズの中身の枝：読んでいる作品の分だけ開く

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

  // 宽屏：何も隠さない → 行を 30px まで詰める（それ以上は詰めない：窮屈になる）→ ①ほかの板块は新着順に数件 ②ほかは見出しだけ ③いまの小分類だけ ④入るだけ＋「ほか N 件」
  function layout(force) {
    const on = pills[curIdx], k = on && slotOf.has(on) ? slotOf.get(on) : -1, sub = on ? subOf(on) : '';
    if (!force && k === lk && sub === lsub && on === lon && !(on && on.classList.contains('x'))) return;
    lk = k; lsub = sub; lon = on;
    const H = Math.floor(rail.getBoundingClientRect().height), n = S.length;
    if (!n || !H) return;
    const L = S.map(s => s.pills.filter(p => !isMed(p))), subsK = k >= 0 && S[k].chips.length > 0;
    let chipsH = 0;
    if (subsK) { S[k].subs.classList.remove('x'); chipsH = S[k].subs.offsetHeight + 6; }   // 札の高さは実際に測る
    const labsH = k >= 0 ? S[k].labs.length * LAB_H : 0;
    const med = k >= 0 && on ? S[k].pills.filter(p => isMed(p) && p.dataset.x === on.dataset.for) : [];   // 読んでいる作品の枝
    const cnt = (x, i) => x.items.length + (i === k ? med.length : 0);
    const hOf = (x, i, r) => !x ? MIN_H : SEC_H + (i === k ? 6 : 2) + cnt(x, i) * r + (x.more ? MORE_H : 0)
      + (i === k ? EXTRA + (x.labs ? labsH : 0) + (x.chips ? chipsH : 0) : 0);
    const sum = (p, r) => p.reduce((a, x, i) => a + hOf(x, i, r), 0);
    const fitR = p => { for (let r = ITEM_H; r >= R_MIN; r--) if (sum(p, r) <= H) return r; return 0; };
    const full = i => ({items: L[i], more: 0, labs: i === k && subsK, chips: i === k && subsK});
    let plan = L.map((_, i) => full(i)), r = fitR(plan), lvl = 0;
    if (!r && subsK) { const p = plan.map((x, i) => i === k ? {...x, labs: false} : x); r = fitR(p); if (r) plan = p; }
    // 件数で決めるとき：その件数を超えたら隠す。件数以内でも、行を詰めても入らない（窮屈になる）なら隠す（＝閾値を自動で下げる）
    if (HIDE && TOTAL > HIDE) r = 0;
    if (!r) {
      lvl = -1;
      const maxLen = Math.max(0, ...L.map((l, i) => i === k ? 0 : l.length));
      for (let kk = maxLen - 1; kk >= 1 && lvl < 0; kk--) {   // ① ほかの板块は新着の多い順に kk 件まで
        const p = L.map((l, i) => i === k ? {...full(i), labs: false} : l.length <= kk ? full(i) : {items: topN(l, kk), more: l.length - kk});
        const rr = fitR(p);
        if (rr) { plan = p; r = rr; lvl = 1; }
      }
      for (const labs of [true, false]) {   // ② ほかは見出しだけ、いまの板块は全部
        if (lvl >= 0) break;
        const p = L.map((_, i) => i === k ? {...full(i), labs: labs && subsK} : null);
        const rr = fitR(p);
        if (rr) { plan = p; r = rr; lvl = 2; }
      }
      if (lvl < 0 && k < 0) { plan = L.map(() => null); r = ITEM_H; lvl = 2; }
      if (lvl < 0 && subsK) {   // ③ 小分類の札＋いまの小分類を全部
        const p = L.map((l, i) => i === k ? {items: l.filter(w => subOf(w) === sub), more: 0, chips: true} : null);
        const rr = fitR(p);
        if (rr) { plan = p; r = rr; lvl = 3; }
      }
      if (lvl < 0) {   // ④ 入るだけ＋「ほか N 件」（読んでいる作品は必ず入れる）
        const sl = subsK ? L[k].filter(w => subOf(w) === sub) : L[k];
        r = R_MIN + 2;
        const room = H - (n - 1) * MIN_H - SEC_H - 6 - EXTRA - (subsK ? chipsH : 0) - MORE_H;
        let items = topN(sl, Math.max(1, Math.floor(room / r)));
        if (on && sl.includes(on) && !items.includes(on)) items = items.slice(0, -1).concat(on);
        plan = L.map((_, i) => i === k ? {items, more: sl.length - items.length, chips: subsK} : null);
      }
    }
    // 余った高さは、まず行の間隔を広げる（1 行 56px まで。48px 以上で 2 行目に今週の件数）。それでも余れば全板块に均等に
    const shown = plan.reduce((a, x, i) => a + (x ? cnt(x, i) : 0), 0);
    const ih = Math.max(r, Math.min(56, Math.floor(r + Math.max(0, H - sum(plan, r)) / Math.max(1, shown))));
    const hOf2 = (x, i) => hOf(x, i, r) + (x ? cnt(x, i) * (ih - r) : 0);
    // 板块の間に足すのは 1 つ SPARE_MAX まで（駅が少ない＝お客さまの版面が数個のときに、板块の間が大きく空かないように。残りは下に）
    const spare = Math.min(SPARE_MAX, Math.max(0, H - plan.reduce((a, x, i) => a + hOf2(x, i), 0)) / n);
    rail.style.setProperty('--ih', ih + 'px');
    rail.classList.toggle('roomy', ih >= 48);
    let y = 0;
    S.forEach((s, i) => {
      const x = plan[i], h = hOf2(x, i) + spare, show = new Set(x ? x.items.concat(i === k ? med : []) : []);
      s.el.style.transform = `translateY(${y}px)`; s.el.style.height = h + 'px'; y += h;
      s.el.classList.toggle('cur', i === k);
      s.pills.forEach(p => p.classList.toggle('x', !show.has(p)));
      if (s.subs) s.subs.classList.toggle('x', !(x && x.chips));
      s.chips.forEach(c => c.classList.toggle('on', i === k && c.dataset.sub === sub));
      s.labs.forEach(l => l.classList.toggle('x', !(x && x.labs) || !s.pills.some(p => show.has(p) && subOf(p) === l.dataset.sub)));
      if (s.more) s.more.classList.toggle('x', !(x && x.more));
      if (s.more && x && x.more) s.more.textContent = `ほか ${x.more} 件 →`;
      // 見出しだけになった板块の空き（作品の駅が 1 つも出ていない・字が入る高さがある）にだけ、作品名の薄い 1〜2 行
      if (s.sum) s.sum.classList.toggle('x', show.size > 0 || h < 84);
    });
  }

  // 窄屏：上排の板块のうち読んでいる板块を光らせ、下排にその板块の作品を全部並べる（隠さない）
  function narrow(k) {
    S.forEach((s, i) => {
      s.el.classList.toggle('cur', i === k);
      s.el.style.transform = s.el.style.height = '';
      s.pills.forEach(p => p.classList.remove('x'));
    });
    lk = null;
    const center = (row, el) => el && row.scrollTo({left: el.offsetLeft - row.clientWidth / 2 + el.offsetWidth / 2, behavior: reduce ? 'auto' : 'smooth'});
    center(nav.querySelector('.mtabs'), tabs.find(t => t.classList.contains('on')));
    center(rail, pills[curIdx]);
  }

  function update(force) {
    ticking = false;
    const top = wide.matches ? 0 : nav.getBoundingClientRect().bottom;
    const m = pick(top, innerHeight);
    if (!m) return;
    // 进度：这个区块读了多少（屏幕底边走过了它的几成）
    const rc = m.getBoundingClientRect();
    const prog = Math.round(Math.min(1, Math.max(0, (innerHeight - rc.top) / rc.height)) * 100) / 100;
    const idx = m.closest('.issue') === firstIssue && byKey.has(m.dataset.k) ? byKey.get(m.dataset.k) : -1;
    if (idx !== curIdx || force) {   // 选中项变了才动所有条目的样式
      const on = pills[idx], k = on && slotOf.has(on) ? slotOf.get(on) : -1;
      // 通り過ぎた駅＝目次（線路）の上で読んでいる駅より前の駅。版面の番号（data-n）は目次の並び（板块 → 小分類）と違うことがあるので、
      // 目次の並びで決める（番号で決めていたら、目次で前にある駅が白いままのことがあった）
      pills.forEach((p, i) => {
        p.classList.toggle('on', p === on);
        p.classList.toggle('past', !!on && num(p) > 0 && i < idx);
      });
      curIdx = idx; curProg = -1;
      nav.style.setProperty('--cur', on ? getComputedStyle(on).getPropertyValue('--sc') : 'var(--alert)');   // トップ・気になるかも？を読んでいるときは赤
      nav.classList.toggle('insec', k >= 0);
      tabs.forEach(t => t.classList.toggle('on', t.dataset.sec === (k >= 0 ? S[k].sec : '')));
      flame(on);
      kindle(on ? m : null, on ? +on.dataset.heat || 0 : 0);
      if (wide.matches) layout(force); else narrow(k);
    }
    if (prog !== curProg) { curProg = prog; nav.style.setProperty('--prog', prog); }
  }
  // ロゴの炎：読んでいる作品の話題度（0〜100）の強さで燃え続ける（切り替えると 0.5 秒ほどでその強さへ）。トップでは全体の最高点を小さめの火で。
  // 層ごとの伸び縮み・傾き・揺れは、周期が割り切れない 4 つの波の和（同じ動きの繰り返しに見えない）。火の粉は 1 粒ずつ道筋と寿命が違う
  const logo = nav.querySelector('.logo'), fl = logo && logo.querySelector('.flame');
  const LV = (() => { try { return JSON.parse(nav.dataset.levels || '[]'); } catch (_) { return []; } })();
  const maxHeat = Math.max(0, ...pills.map(p => +p.dataset.heat || 0));
  const FL = {h: .3, target: .3, t: Math.random() * 50, run: false, sg: null, first: true, sh: null, shT: null};
  const SPEC = {tl: [.5, -17, -16, 1.4, 1.25], tr: [.46, 17, 15, 1.4, 1.1], o: [1, 0, 0, 1, .9], m: [.8, 0, 0, 1.1, 1.05],
                i: [.56, 0, 0, 1.2, 1.3], c: [.3, 0, 0, 1, 1.5]};   // 大きさ・横の位置・傾き・揺れの大きさ・速さ
  // 作品ごとの炎の形：層ごとに横のずれ・大きさ・傾きを少しずつ変える（作品の名前から決まるので、同じ作品はいつも同じ形）
  function shapeOf(key) {
    let s = 7; for (const ch of key) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
    const r = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
    return Object.fromEntries(Object.keys(SPEC).map(q => { const t = q[0] === 't'; return [q, [(r() - .5) * (t ? 10 : 5), t ? .72 + r() * .6 : .88 + r() * .26, (r() - .5) * (t ? 16 : 7)]]; }));
  }
  FL.shT = shapeOf('top'); FL.sh = JSON.parse(JSON.stringify(FL.shT));
  // 炎に混ぜる色：作品の色（版面の --acc）と板块の色（目次の --sc）。色の薄い（灰・白に近い）色は弱く混ぜる
  const cvs = document.createElement('canvas').getContext('2d');
  function tintOf(el, prop) {
    const c = el && getComputedStyle(el).getPropertyValue(prop).trim();
    if (!c) return [0, [0, 0, 0]];
    cvs.fillStyle = '#000'; cvs.fillStyle = c; const x = cvs.fillStyle;
    const v = x[0] === '#' ? [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16)) : (x.match(/[\\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
    return [Math.min(1, (Math.max(...v) - Math.min(...v)) / 255 * 1.6), v];
  }
  FL.tw = 0; FL.tint = [255, 122, 26]; FL.cA = [0, FL.tint]; FL.cB = [0, FL.tint];
  const GOLD = tintOf(document.documentElement, '--gold')[1], CARD = tintOf(document.documentElement, '--card')[1];
  const layers = fl ? [...fl.querySelectorAll('.L')].map(n => ({n, k: n.dataset.k, s: SPEC[n.dataset.k], ph: Math.random() * 100})) : [];
  const turb = fl && fl.querySelector('feTurbulence'), disp = fl && fl.querySelector('feDisplacementMap');
  const ems = fl ? [...fl.querySelectorAll('.em')].map(e => ({e, life: Math.random(), dur: 1, dx: 0, sway: 0, ph: 0, b: 0})) : [];
  const glow = fl && fl.querySelector('.glow'), puff = fl && fl.querySelector('.puff');
  // ぶわっ：話題度が上がる切り替えのときだけ。本物の火に燃料が入ったときのように 0.07 秒で一気に何倍にも伸び上がり、
  // 火の玉が上へ抜け、火の粉が散って、1 秒ほどで新しい強さに落ち着く（上がり幅が大きいほど強い。testground/flame.html）
  // 炎ぜんたいが 一瞬で最大 約 3 倍に膨らみ（.flame の scale）、さらに層が縦に伸びる。同時に画面じゅうに火の粉
  const UP = {tl: .9, tr: .9, o: 1.1, m: 1, i: .8, c: .6};   // 縦に伸びる倍率（外側ほど高く）
  // 燃え上がり方の曲線。山までの速さ・山の長さ・落ち着く速さ・揺れ・後から来るもう一度の小さな燃え上がり（余震）は ぶわっ ごとにくじで決める
  const env = (t, g) => {
    let e = t < g.att ? 1 - (1 - t / g.att) ** 2 : t < g.att + g.hold ? 1 : Math.exp(-(t - g.att - g.hold) * g.dec) * (1 + .12 * Math.sin((t - g.att - g.hold) * g.wig));
    if (g.af && t > g.af.at) { const u = t - g.af.at; e += g.af.k * (u < .05 ? u / .05 : Math.exp(-(u - .05) * 5)); }
    return e;
  };
  function flare(up, to) {
    const k = Math.min(1.5, .45 + up * 1.6);
    const cur = FL.sg ? env(FL.sg.t, FL.sg) * FL.sg.k : 0;   // 続けて上がったとき：燃え上がっている最中のほうが強ければそのまま（小さい ぶわっ で打ち消さない）
    if (cur >= k) return;
    const R = Math.random;
    FL.sg = {t: 0, k, att: .04 + R() * .06, hold: .06 + R() * .16, dec: 2.2 + R() * 1.6, wig: 22 + R() * 24,
             af: R() < .55 ? {at: .3 + R() * .35, k: .2 + R() * .3} : null,      // 半分くらいは後からもう一度小さく燃え上がる
             lean: (R() - .5) * 26, wide: .5 + R() * .5, tall: .75 + R() * .6,   // 傾き（±13°）・横への広がり・縦への伸び
             lay: Object.fromEntries(Object.keys(SPEC).map(q => [q, .5 + R() * 1.1])),   // 層ごとの伸び方（片方の舌だけ高く跳ねる など）
             col: [FL.cA[1], FL.cB[1], GOLD, CARD][(R() * 4) | 0]};   // ぶわっの色もくじ（作品の色・板块の色・金・白）
    if (cur > .05) FL.sg.t = FL.sg.att;   // 燃え上がっている最中なら山から続ける
    blast(fl, k, to >= .85 && FL.target < .85);   // 画面全体を使うのは「沸騰」に上がったときだけ
    logo.classList.remove('quake'); void logo.offsetWidth; logo.classList.add('quake');   // ロゴが小さく揺れる
    ems.forEach((m, i) => { if (i < Math.round(6 + k * 7)) { m.life = Math.random() * .15; m.dur = .45 + Math.random() * .5; m.dx = (Math.random() - .5) * 4.5; m.sway = Math.random() * 4; m.ph = Math.random() * 6; m.b = k; } });
  }
  // ぶわっの演出。ふだんはロゴのまわりだけ：炎のまわりの光・小さな衝撃波の輪・近くに散る火の粉・煙（画面全体は使わない）。
  // 「沸騰」（話題度 85 以上）に上がったときだけ画面全体を少し：画面がうすく照らされ、ふちがかすかに火の色・火の粉が遠くまで飛び、下からも少し舞い上がる。
  // 毎回ちがう：火の粉の向き・数、輪が 1 重か 2 重か、煙の数はその都度くじで決める。canvas 1 枚、終わったら隠してループも止める
  const FX = {sp: [], sm: [], ring: null, flash: 0, run: false, at: 0, last: 0, ox: 0, oy: 0};
  function fxCanvas(cls) { const c = document.createElement('canvas'); c.className = cls; c.setAttribute('aria-hidden', 'true'); document.body.appendChild(c); return c; }
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
  function rgb(c) {   // トークンの色 → [r, g, b]
    const x = FX.cx; x.fillStyle = '#000'; x.fillStyle = c; const h = x.fillStyle;
    return h[0] === '#' ? [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)) : (h.match(/[\\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
  }
  function fxInit() {   // canvas は初めて使うときに作る（ぶわっ・版面の火の粉で共用）
    if (!FX.cv) {
      FX.cv = fxCanvas('sparkfx'); FX.cx = FX.cv.getContext('2d');
      const cs = getComputedStyle(document.documentElement), tok = v => cs.getPropertyValue(v).trim() || '#FF7A1A';
      FX.col = ['--gold', '--flame', '--flame', '--alert', '--gold'].map(tok);
      [FX.cFlame, FX.cGold, FX.cInk] = ['--flame', '--gold', '--ink'].map(v => rgb(tok(v)));
    }
    const W = innerWidth, H = innerHeight, dpr = Math.min(2, devicePixelRatio || 1);
    if (FX.cv.width !== Math.round(W * dpr) || FX.cv.height !== Math.round(H * dpr)) { FX.cv.width = Math.round(W * dpr); FX.cv.height = Math.round(H * dpr); }
    FX.cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function fxRun() { FX.cv.style.display = 'block'; if (!FX.run) { FX.run = true; FX.last = 0; requestAnimationFrame(fxLoop); } }
  function blast(from, k, big) {
    const now = performance.now();
    if (now - FX.at < 500) return; FX.at = now;   // 速くスクロールして続けて上がっても 0.5 秒に 1 回
    fxInit();
    const W = innerWidth, H = innerHeight;
    const r = from.getBoundingClientRect(), R = Math.random, n = Math.round((big ? 80 + k * 60 : 30 + k * 30) * (.7 + R() * .6)), a0 = (R() - .5) * 60;   // 数と向きは毎回くじ
    FX.ox = r.left + r.width / 2; FX.oy = r.top + r.height * .55;
    for (let i = 0; i < n; i++) {
      const burst = !big || i < n * .75, s = {life: 0, dur: big ? .9 + R() * 1.4 : .5 + R() * .6, w: (big ? 1.3 : 1) + R() * 2, c: FX.col[i % FX.col.length], ph: R() * 6, burst, near: !big};
      if (burst) {   // 炎から：ふだんは上と横へ近くだけ（ロゴのまわり 200px ほど）、沸騰は上・右・下へ画面全体まで
        const a = (a0 + (big ? -110 + R() * 190 : -165 + R() * 150)) * Math.PI / 180, v = big ? 220 + R() ** .6 * 900 * (.55 + Math.min(1, k) * .45) : 120 + R() ** .6 * 420 * (.6 + Math.min(1, k) * .4);
        Object.assign(s, {x: FX.ox, y: FX.oy, vx: Math.cos(a) * v, vy: Math.sin(a) * v});
      } else {        // 画面の下から：ばらばらの位置・時間で舞い上がる
        Object.assign(s, {x: R() * W, y: H + 10 + R() * 60, vx: (R() - .5) * 90, vy: -(160 + R() * 380), life: -R() * .6});
      }
      FX.sp.push(s);
    }
    FX.ring = {t: 0, k, big, two: R() < .45, w: .7 + R() * .6}; FX.flash = Math.min(1, .5 + k * .4); FX.big = big;
    for (let i = 0, m = 3 + (R() * (big ? 6 : 4) | 0); i < m; i++) FX.sm.push({x: FX.ox + (R() - .5) * 30, y: FX.oy - 40 - R() * 30, vx: 20 + R() * 50, vy: -(40 + R() * 70), r: 14 + R() * 16, life: -(.2 + R() * .35), dur: 1.4 + R()});
    fxRun();
  }
  function fxLoop(now) {
    const dt = Math.min(.05, (now - (FX.last || now)) / 1000), c = FX.cx, W = innerWidth, H = innerHeight; FX.last = now;
    c.clearRect(0, 0, W, H);
    if (FX.flash > .01) {   // 閃光：ふだんはロゴのまわりだけ明るく、沸騰は画面全体
      const f = FX.flash, R0 = FX.big ? Math.max(W, H) * .9 : 170;
      let g = c.createRadialGradient(FX.ox, FX.oy, 0, FX.ox, FX.oy, R0);
      g.addColorStop(0, rgba(FX.cGold, .9)); g.addColorStop(.3, rgba(FX.cFlame, .5)); g.addColorStop(1, rgba(FX.cFlame, 0));
      c.globalAlpha = f * (FX.big ? .26 : .45); c.fillStyle = g; c.fillRect(FX.ox - R0, FX.oy - R0, R0 * 2, R0 * 2);
      if (FX.big) g = c.createRadialGradient(W / 2, H / 2, Math.min(W, H) * .3, W / 2, H / 2, Math.hypot(W, H) / 2);
      if (FX.big) { g.addColorStop(0, rgba(FX.cFlame, 0)); g.addColorStop(1, rgba(FX.cFlame, .9));
        c.globalAlpha = f * (.14 + Math.random() * .08); c.fillStyle = g; c.fillRect(0, 0, W, H); }
      FX.flash *= Math.exp(-2.4 * dt);
    }
    if (FX.ring) {   // 衝撃波の輪
      const P = (FX.ring.t += dt / .75);
      if (P >= 1 + (FX.ring.two ? .18 : 0)) FX.ring = null;
      else for (const p of FX.ring.two ? [P, P - .18] : [P]) {   // 2 重の輪は 0.13 秒遅れてもう 1 本
        if (p <= 0 || p >= 1) continue;
        const rad = 14 + (1 - (1 - p) ** 3) * (FX.ring.big ? 260 + FX.ring.k * 420 : 50 + FX.ring.k * 60), lw = (FX.ring.big ? .8 : .45) * FX.ring.w;
        c.globalAlpha = (1 - p) * .35; c.strokeStyle = rgba(FX.cFlame, 1); c.lineWidth = (6 + 34 * (1 - p)) * lw;
        c.beginPath(); c.arc(FX.ox, FX.oy, rad * .95, 0, 7); c.stroke();
        c.globalAlpha = (1 - p) ** 1.4; c.strokeStyle = rgba(FX.cGold, 1); c.lineWidth = (2 + 10 * (1 - p)) * lw;
        c.beginPath(); c.arc(FX.ox, FX.oy, rad, 0, 7); c.stroke();
      }
    }
    FX.sm = FX.sm.filter(s => (s.life += dt / s.dur) < 1);
    for (const s of FX.sm) {   // 煙：ふくらみながら上へ流れて消える
      if (s.life < 0) continue;
      s.x += s.vx * dt; s.y += s.vy * dt;
      const rr = s.r * (1 + s.life * 2.5), g = c.createRadialGradient(s.x, s.y, 0, s.x, s.y, rr);
      g.addColorStop(0, rgba(FX.cInk, .2)); g.addColorStop(1, rgba(FX.cInk, 0));
      c.globalAlpha = Math.sin(Math.PI * s.life); c.fillStyle = g; c.beginPath(); c.arc(s.x, s.y, rr, 0, 7); c.fill();
    }
    FX.sp = FX.sp.filter(s => (s.life += dt / s.dur) < 1);
    c.lineCap = 'round';
    for (const s of FX.sp) {   // 火の粉：熱いので浮き上がり、ゆらゆら
      if (s.life < 0) continue;
      const drag = Math.exp(-(s.slow ? .5 : s.near ? 3.2 : s.burst ? 1.7 : .6) * dt);   // slow：版面から昇る熾火の粉（ゆっくり漂う）
      s.vx = s.vx * drag + Math.sin(now / (s.slow ? 420 : 160) + s.ph) * (s.slow ? 22 : 40) * dt; s.vy = s.vy * drag - (s.slow ? 18 : s.near ? 60 : 160) * dt;
      s.x += s.vx * dt; s.y += s.vy * dt;
      const a = s.life < .08 ? s.life / .08 : (1 - s.life) ** 1.3, tl = s.near ? .03 : .05, tx = s.x - s.vx * tl, ty = s.y - s.vy * tl;
      c.strokeStyle = s.c;
      c.globalAlpha = a * .25; c.lineWidth = s.w * 3.2; c.beginPath(); c.moveTo(tx, ty); c.lineTo(s.x, s.y); c.stroke();
      c.globalAlpha = a; c.lineWidth = s.w; c.beginPath(); c.moveTo(tx, ty); c.lineTo(s.x, s.y); c.stroke();
    }
    c.globalAlpha = 1;
    if (FX.sp.length || FX.sm.length || FX.ring || FX.flash > .01) requestAnimationFrame(fxLoop);
    else { FX.run = false; c.clearRect(0, 0, W, H); FX.cv.style.display = 'none'; }
  }
  // 版面も炎と一緒に燃える：入った版面の上辺を火が左から右へ走り（導火線、0.7 秒）、火の粉が上へ散る（画面のどこへ飛んでもよい）。
  // 読んでいる間は上辺が熾火のように炎と同じ揺れで明滅し、版面の見えている下のほうから時々火の粉が昇る。強さはその作品の話題度（炎と同じ値）
  const SF = {sec: null, line: null, k: 0, acc: 0, sweep: null};
  function kindle(sec, heat) {
    if (SF.line) { const old = SF.line; old.classList.add('out'); setTimeout(() => old.remove(), 700); SF.line = null; }
    SF.sec = sec && sec.classList.contains('sec') ? sec : null;
    SF.k = Math.min(1, Math.max(0, (heat || 0) / 100)); SF.acc = 0;
    if (!SF.sec || !FL.run) return;   // 宽屏・動きを減らす設定でない・タブが見えているときだけ（炎と同じ）
    const ln = document.createElement('i');
    ln.className = 'secfire'; ln.setAttribute('aria-hidden', 'true'); ln.style.setProperty('--k', SF.k.toFixed(2));
    SF.sec.appendChild(ln); SF.line = ln;
    SF.sweep = {t: 0, n: Math.round(12 + SF.k * 48), sent: 0};
  }
  function secBurn(dt, E) {
    if (!SF.line) return;
    const r = SF.sec.getBoundingClientRect();
    if (r.bottom < 0 || r.top > innerHeight) return;
    fxInit();
    const k = SF.k, R = Math.random, col = FX.col;
    const add = s => { if (FX.sp.length < 180) FX.sp.push(Object.assign({life: 0, ph: R() * 6, c: col[(R() * col.length) | 0], near: true}, s)); };
    if (SF.sweep) {   // 導火線：先端から上と横へ火の粉
      const w = SF.sweep; w.t += dt / .7;
      const p = Math.min(1, w.t), x = r.left + r.width * p;
      SF.line.style.setProperty('--sw', p.toFixed(3));
      for (const want = Math.round(w.n * p); w.sent < want; w.sent++)
        add({x: x - R() * 18, y: r.top, vx: (R() - .35) * 220, vy: -(110 + R() ** .6 * (220 + k * 380)), dur: .55 + R() * .75, w: 1 + R() * 1.8, burst: true});
      if (p >= 1) SF.sweep = null;
    }
    SF.line.style.setProperty('--burn', Math.min(1, .3 + k * .45 + wob(FL.t * 1.3, 11) * (.12 + k * .14) + E * .3).toFixed(3));
    SF.acc += dt * (.25 + 4.5 * k ** 1.5);   // 1 秒あたり 0.25（冷めた作品）〜 4.75 粒（沸騰）
    for (; SF.acc >= 1; SF.acc--)
      add({x: r.left + R() * r.width, y: Math.min(r.bottom, innerHeight) - 2, vx: (R() - .5) * 24, vy: -(35 + R() * (50 + k * 60)),
           dur: 1.6 + R() * 1.8, w: .8 + R() * (1 + k), slow: true});
    if (FX.sp.length) fxRun();
  }
  const wob = (t, p) => Math.sin(t * 1.13 + p) * .45 + Math.sin(t * 2.71 + p * 1.7) * .3 + Math.sin(t * 5.87 + p * 2.3) * .17 + Math.sin(t * 11.3 + p * .7) * .08;
  // 層ごとの形：周期の割り切れない波で伸び縮み・傾き・揺れ
  function drawLayers(list, T, h, amp, E, g) {
    for (const L of list) {
      const [sz1, x1, rot1, la, sp] = L.s, side = L.k === 'tl' || L.k === 'tr', [shx, shs, shr] = FL.sh[L.k];
      const sz0 = sz1 * shs, x0 = x1 + shx, rot0 = rot1 + shr;
      const sz = L.k === 'i' || L.k === 'c' ? sz0 * (.65 + h * .7) : sz0;   // 熱いほど白い芯が大きい
      const on = side ? Math.min(1.25, Math.max(0, (h - .25) / .45)) : 1, tt = T * sp + L.ph;
      const sy = sz * (1 + (wob(tt, 1) * .16 + Math.max(0, wob(tt * 1.7, 4)) * .14) * amp * la) * (side ? .6 + on * .5 : 1) * (1 + E * UP[L.k] * (g ? g.lay[L.k] : 1));
      const sx = sz * (1 - wob(tt, 1) * .06 * amp) * (1 + E * .3), skew = wob(tt * .8, 7) * 9 * amp * la;
      const rot = rot0 * on + wob(tt * .6, 3) * 3 * amp, x = x0 * (side ? .8 + on * .4 : 1) + wob(tt * .9, 9) * 1.6 * amp;
      L.n.setAttribute('transform', `translate(${(50 + x).toFixed(2)} 132) rotate(${rot.toFixed(2)}) skewX(${skew.toFixed(2)}) scale(${sx.toFixed(3)} ${sy.toFixed(3)}) translate(-50 -132)`);
      if (side) L.n.style.opacity = Math.min(1, on + E).toFixed(2);
    }
  }
  let flLast = 0;
  function burn(now) {
    const dt = Math.min(.05, (now - (flLast || now)) / 1000); flLast = now;
    FL.h += (FL.target - FL.h) * Math.min(1, dt * 4);
    let E = 0;   // ぶわっの強さ（0〜1.5）
    const g = FL.sg;
    if (g) { g.t += dt; E = env(g.t, g) * g.k; if (g.t > 2.2) FL.sg = null; }
    fl.style.setProperty('--hc', Math.min(1, FL.h + E * .35).toFixed(3));   // 色は毎フレーム滑らかに（燃え上がる瞬間は熱く白く）
    fl.style.setProperty('--fx', E.toFixed(3));
    glow.style.scale = (1 + E * 1.3).toFixed(3);
    const S = Math.min(2.1, E * 2.2);   // 上がり幅が大きいと 約 3 倍（縦横の比・傾きは毎回ちがう）
    fl.style.scale = g ? `${(1 + S * g.wide).toFixed(3)} ${(1 + S * g.tall).toFixed(3)}` : '1';
    fl.style.rotate = g ? (g.lean * E / g.k).toFixed(2) + 'deg' : '0deg';
    for (const q in FL.shT) for (let j = 0; j < 3; j++) FL.sh[q][j] += (FL.shT[q][j] - FL.sh[q][j]) * Math.min(1, dt * 3);   // 作品ごとの形へ滑らかに
    // 色：作品の色と板块の色の間をゆっくり行き来（どちらかが薄い色ならもう一方）。ぶわっの瞬間はくじで選んだ色がぱっと差す
    const [wA, cA] = FL.cA, [wB, cB] = FL.cB, d = wA && wB ? .5 + .5 * Math.sin(now / 2600 + Math.sin(now / 4100) * 1.5) : wB ? 1 : 0;
    let tw = wA * (1 - d) + wB * d, tc = cA.map((v, j) => v + (cB[j] - v) * d);
    if (g && g.col) { const m = Math.min(1, E); tc = tc.map((v, j) => v + (g.col[j] - v) * m); tw = Math.max(tw, m * .9); }
    const mx = Math.min(1, dt * 3); FL.tw += (tw - FL.tw) * mx;
    for (let j = 0; j < 3; j++) FL.tint[j] += (tc[j] - FL.tint[j]) * mx;
    fl.style.setProperty('--tint', `rgb(${FL.tint.map(Math.round).join(',')})`); fl.style.setProperty('--tw', FL.tw.toFixed(3));
    const h = FL.h, amp = .18 + h * 1.5 + E * .8;
    FL.t += dt * (.6 + h * 3.8 + E * 4);
    drawLayers(layers, FL.t, h, amp, E, g);
    // 火の玉：根元からちぎれて上へ抜け、広がりながら消える
    if (FL.sg && FL.sg.t < 1.1) {
      const p = FL.sg.t / 1.1, r = (10 + p * 22) * Math.min(1, FL.sg.k);
      puff.setAttribute('cy', (70 - p * (120 + FL.sg.k * 60)).toFixed(1));
      puff.setAttribute('rx', (r * .85).toFixed(1)); puff.setAttribute('ry', r.toFixed(1));
      puff.setAttribute('opacity', (p < .12 ? p / .12 : (1 - p) ** 1.5).toFixed(2));
    } else puff.setAttribute('opacity', 0);
    turb.setAttribute('baseFrequency', `${(.03 + wob(FL.t * .3, 2) * .006).toFixed(4)} ${(.07 + wob(FL.t * .4, 5) * .015).toFixed(4)}`);
    disp.setAttribute('scale', (3 + h * 24 + E * 26 + wob(FL.t, 8) * 2).toFixed(1));
    const n = Math.round(h * h * ems.length);
    ems.forEach((m, k) => {
      if (k >= n && !m.b) { m.e.style.opacity = 0; return; }
      m.life += dt / m.dur;
      if (m.life >= 1) { m.life = 0; m.b = 0; m.dur = .9 + Math.random() * .9 - h * .4; m.dx = (Math.random() - .5) * 2; m.sway = Math.random() * 6; m.ph = Math.random() * 6; }
      if (k >= n && !m.b) { m.e.style.opacity = 0; return; }
      const l = m.life, y = -(8 + l * (18 + h * 80) * (1 + m.b * 1.4)), x = m.dx * l * 12 + Math.sin(l * 9 + m.ph) * m.sway;
      m.e.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scale(${(1 - l * .7).toFixed(2)})`;
      m.e.style.opacity = (l < .1 ? l * 10 : 1 - (l - .1) / .9).toFixed(2);
    });
    secBurn(dt, E);
    if (FL.run) requestAnimationFrame(burn);
  }
  // 宽屏で、動きを減らす設定でなく、タブが見えているときだけ回す（それ以外は止めて電池を使わない）
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  function burnning() {
    const go = !!fl && wide.matches && !still.matches && !document.hidden;
    if (go && !FL.run) { FL.run = true; flLast = 0; requestAnimationFrame(burn); }
    else if (!go) { FL.run = false; if (fl && still.matches) { FL.h = FL.target; flLast = 0; burn(performance.now()); } }
    if (!go && SF.line) { SF.line.remove(); SF.line = null; }
  }
  document.addEventListener('visibilitychange', burnning);
  wide.addEventListener && wide.addEventListener('change', burnning);
  function flame(on) {
    const own = on && on.dataset.heat != null ? +on.dataset.heat || 0 : null;
    const v = own == null ? maxHeat : own;
    if (!fl) {   // 炎を出さないとき（NAV_FLAME）も、ロゴの右の点数と等級は入れる
      if (logo) { logo.querySelector('.hv').textContent = v ? String(v) : '';
        logo.querySelector('.hl').textContent = own == null ? (v ? '今日の最高' : '') : ((LV.find(l => v >= l[0]) || [0, ''])[1] || '話題度'); }
      return;
    }
    const to = own == null ? Math.min(.35, v / 100) : v / 100;
    const go = !FL.first && to - FL.target > .04 && FL.run, hv = logo.querySelector('.hv'), was = +hv.textContent || 0;
    const sec = on && on.getAttribute('href') && document.querySelector(on.getAttribute('href'));
    FL.cA = tintOf(sec, '--acc'); FL.cB = tintOf(on, '--sc');   // 先に新しい作品の色にしてから ぶわっ（ぶわっの色のくじに使う）
    if (go) flare(to - FL.target, to);   // 強くなる切り替えだけ ぶわっ（開いた直後・止まっているときは出さない）
    FL.first = false; FL.target = to; FL.shT = shapeOf(on && on.getAttribute('href') || 'top');
    nav.style.setProperty('--heat', FL.target.toFixed(2));
    hv.textContent = v ? String(v) : '';
    if (go && v) {   // 数字が弾んで、前の点から数え上がる（0.5 秒）
      hv.classList.remove('hvpop'); void hv.offsetWidth; hv.classList.add('hvpop');
      const t0 = performance.now(), cnt = t => { if (FL.target !== to) return; const p = Math.min(1, (t - t0) / 500); hv.textContent = String(Math.round(was + (v - was) * (1 - (1 - p) ** 3))); if (p < 1) requestAnimationFrame(cnt); };
      requestAnimationFrame(cnt);
    }
    logo.querySelector('.hl').textContent = own == null ? (v ? '今日の最高' : '') : ((LV.find(l => v >= l[0]) || [0, ''])[1] || '話題度');
    burnning();
  }
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => update()); } }, {passive: true});
  addEventListener('resize', () => update(true));
  document.addEventListener('wl-nav', () => { scan(); curIdx = -2; lk = null; update(true); });
  // 字体の読み込みなどで目次の高さが変わったら置き直す
  if (window.ResizeObserver) new ResizeObserver(() => { if (wide.matches) layout(true); }).observe(rail);
  update(true);
})();
"""


def _dedupe_parents(works, parents):
    """同じニュースを 2 回出さない（PRODUCT.md 原則 4）：下級（スパイダーマン）のニュースは上級（漫威电影）の match にも当たりやすい。
    両方に入ったら下級の版面だけに残し、上級の版面からは外す。"""
    by = {w["name"]: w for w in works}
    for kid, par in (parents or {}).items():
        if kid in by and par in by and kid != par:
            urls = {x["url"] for x in by[kid]["stories"]}
            by[par]["stories"] = [x for x in by[par]["stories"] if x["url"] not in urls]
    return works


def _sub_heads(works, subs, parents):
    """本文の版面を目次と同じ「板块 → 小分類」で区切る：小分類が変わる所に細い見出し（板块が変わる所は板块の札も）。
    目立たせない（メインは各版面）。下級は上級の小分類（目次と同じ）。小分類がなければ区切らない。"""
    subs, parents = subs or {}, parents or {}
    sec_of = {w["name"]: w.get("section") or "其他" for w in works}
    def sub_of(w):
        par = parents.get(w["name"])
        return subs.get(par, "") if par in sec_of and sec_of[par] == sec_of[w["name"]] else subs.get(w["name"], "")
    first = {}
    for w in works:   # 板块の中は小分類ごとにまとめる（小分類の並びは最初に出た順、作品の並びはそのまま）
        first.setdefault((sec_of[w["name"]], sub_of(w)), len(first))
    sec_first = {}
    for k in first:
        sec_first.setdefault(k[0], first[k])
    works = sorted(works, key=lambda w: (sec_first[sec_of[w["name"]]], first[(sec_of[w["name"]], sub_of(w))]))
    keys = [(sec_of[w["name"]], sub_of(w)) for w in works]
    out, prev = [], (None, None)
    for w, key in zip(works, keys):
        if key != prev and any(k[1] for k in keys if k[0] == key[0]):
            sec, sb = key
            tag = (f'<span class="tg"><span>{e(_sec_name(sec))}</span></span>' if sec != prev[0] else "")
            out.append(f'<div class="subhead" style="--sc:{_sec_color(sec)}">{tag}'
                       f'<b>{e(sb or "その他")}</b><small>{keys.count(key)} 件</small></div>')
        prev = key
        out.append(_section(w, _wid(w["name"])))
    return "".join(out)


def render(issues, nav_style="line", order=None, updated=None, wishes=(), picks=(), feedback=None, sizes=None,
           motifs=None, themes=None, taste=(), heat=None, emblems=None, like_fx=None, subs=None, nav_hide=NAV_HIDE, icons=None,
           busy=None, generated=None, parents=None, sub_heat=None, langs=None, also=None, media=None):
    """issues：按时间倒序的各期数据（全部）。nav_style：左侧目录风格，见 NAV_STYLES。
    sub_heat：{(板块, 小分類): 話題度}（heat.group_scores。目次の小見出しに出す）。order は heat.heat_order の並び。
    parents：{下級: 上級}（items.yaml の parent。上下級に同じニュースが入ったら下級だけに）。icons：{作品: 目次のアイコン}（items.yaml の icon.image）；subs：{作品: 小分類}（items.yaml 的 sub，目次の札）；nav_hide：目次で隠し始める作品の数（"auto" なら画面の高さ）。
    order：items.yaml 里作品的顺序；updated：网页更新时间（显示用）；sizes：{作品: S / M / L} 篇幅。
    motifs：{作品: 装饰名}（items.yaml 的 motif，见 MOTIFS）；themes：取色キャッシュ（トップのポスターの色を書き足す）。
    heat：{作品: 話題度}（heat.compute 的结果，版面的见出し和トップの右の列に出す）。
    busy：busy_plan() の結果（版面の「更新中」の帯）；generated：生成時刻（UTC の ISO。帯が「もう終わった回」を見分ける）。
    langs：読者の言語（lang.order：主言語 → 副言語）。言語違いの同じニュースは主言語の 1 本だけ。
    also：{作品: [(ほかの板块, 小分類)]}（items.yaml の also。目次のほかの板块に乗換の駅を出す）。"""
    latest = issues[0]
    works = _dedupe_parents(collect(issues, order, langs), parents)
    for w in works:
        w["_today"] = latest["date"]
        w["_size"] = (sizes or {}).get(w["name"], "M")
        w["_motif"] = (motifs or {}).get(w["name"], "")
        # 👍 の演出：items.yaml の like_fx（版面ごとに AI が決める）＞ テーマの fx
        own = (like_fx or {}).get(w["name"])
        _FX_OF[w["name"]] = own if own in likefx.FX else TEMPLATE_FX.get(w["_motif"], "pop")
        w["_emblems"], w["_ring"] = (emblems or {}).get(w["name"]) or ([], "accent")
        w["_heat"] = (heat or {}).get(w["name"])  # 話題度（heat.compute）
        w["_icon"] = (icons or {}).get(w["name"])  # 目次のアイコン
    updated = updated or latest["date"].replace("-", ".")
    fb = feedback if feedback and feedback.get("url") and feedback.get("key") else None
    # id 保留 issue-日期：Discord 通知里的链接指向这里
    body = (f'<div class="issue" id="issue-{latest["date"]}" data-label="更新 {updated}">'
            + _front(works, latest["date"], updated, themes, wishes, taste) + _picks(picks, works, fb)
            + _sub_heads(works, subs, parents) + "</div>")
    parts = [body]
    return _board_marks(f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ウォッチリスト通信</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}@media (min-width:1001px){{{NAV_STYLES.get(nav_style, NAV_STYLES["line"])}}}</style>
{LIKEFX_HEAD if fb else ""}
{_live_head("index")}{f"<style>{BUSY_CSS}</style>" if busy else ""}
<script>{EMB_HEAD_JS}</script>
</head>
<body>
<div class="page">
<header class="mast">
<div class="mtitle"><h1>ウォッチリスト通信</h1><span class="stamp">新着は開いたまま自動で表示</span></div>
<div class="tools"><div class="meta"><small>更新</small><b>{e(updated)}</b></div>
{_wish_link(wishes, "mastwish")}
<a class="mastset" href="settings.html" title="設定">⚙ 設定</a></div>
</header>
{_nav(works, latest['date'], wishes, picks, subs, nav_hide, parents, sub_heat, also, media)}
<main class="issues">{''.join(parts)}</main>
</div>
<script>{NAV_JS}</script>
<script>{FIT_JS}</script>
{f"<script>{LIKEFX_JS}</script><script>{VOTE_JS.replace('__CFG__', json.dumps(fb))}</script>" if fb else ""}
<script>{EMB_JS}</script>
<script>{LIVE_JS}</script>
{_busy_tag(busy, generated)}
</body>
</html>
""", updated)


# ---------- 自動更新：開いたままのページに新しい内容を出す（簡報・管理ページ）----------
# 生成のたびに docs/version.json に「ページごとの内容の指紋」を書く（digest.write_page → stamp）。
# ページは 1 分ごとにそれを読み、自分の指紋（<meta name="wl-ver">）と違えば、
# 操作していないとき（20 秒触っていない・タブが裏にある）に読み直す。読み直しの前後で見ていた場所を保ち、
# 簡報では新しく増えた記事に「たった今」、管理ページでは中身が変わったパネルに「更新」を付ける。
# 入力中・ダイアログを開いているあいだは待つ。下の帯の「今すぐ表示」でもすぐ読み直せる。
VER_MARK = "__WL_VER__"
LIVE_EVERY = 60  # 秒：version.json を見に行く間隔
LIVE_IDLE = 20   # 秒：この間なにも触っていなければ自動で読み直す

LIVE_CSS = """
.wl-live{position:fixed;left:50%;bottom:20px;z-index:80;display:flex;align-items:center;gap:12px;width:max-content;max-width:calc(100vw - 32px);
 transform:translateX(-50%) rotate(var(--tilt));background:var(--ink);color:var(--card);padding:10px 16px;box-shadow:4px 4px 0 var(--rose);
 font:700 14px/1.4 var(--font-sans);letter-spacing:.03em}
.wl-live[hidden]{display:none}
.wl-live span{flex:1 1 auto;min-width:0}
.wl-live button{flex:none;border:0;cursor:pointer;background:var(--gold);color:var(--ink);padding:4px 12px;font:700 13px/1.4 var(--font-sans)}
.wl-live .x{background:none;color:var(--card);padding:4px 6px}
.fresh{outline:3px solid var(--gold);outline-offset:3px}
.wl-live .wl-to{color:var(--gold);text-decoration:underline;text-underline-offset:3px;font-weight:900}
.wl-live span{min-width:0}
.fresh-tag{position:absolute;top:6px;right:6px;z-index:6;background:var(--alert);color:#FFF;padding:1px 9px;transform:skewX(var(--skew));
 box-shadow:2px 2px 0 var(--ink);font:900 var(--fs-label)/1.6 var(--font-sans);letter-spacing:.08em;pointer-events:none}
section.fresh{position:relative}
@media (prefers-reduced-motion:no-preference){.fresh{animation:wlfresh 1.6s ease-out 3}}
@keyframes wlfresh{50%{outline-color:var(--rose)}}
"""

LIVE_JS = """
(function(){
  var M=document.querySelector('meta[name="wl-ver"]');if(!M||!window.fetch||!window.JSON)return;
  // お客さまのページ（user_pages.py が作り、AUTH_JS が差し替えたもの）は version.json の版と比べない：
  // 印が店長のページと違うので「古い」と見て開き直し、また差し替える、をくり返してしまう（2026-10-24）
  if(document.querySelector('meta[name="wl-own"]'))return;
  var PAGE=M.getAttribute('data-page'),VER=M.content,KEY='wl-live:'+PAGE,EVERY=__EVERY__*1000,IDLE=__IDLE__*1000;
  var ss={get:function(k){try{return JSON.parse(sessionStorage.getItem(k)||'null');}catch(e){return null;}},
          set:function(k,v){try{sessionStorage.setItem(k,JSON.stringify(v));}catch(e){}},del:function(k){try{sessionStorage.removeItem(k);}catch(e){}}};
  var touched=Date.now(),LOADED=Date.now(),pending=null,bar=null;
  ['scroll','pointerdown','keydown','wheel','touchstart'].forEach(function(t){addEventListener(t,function(){touched=Date.now();},{passive:true});});
  var ZH=/^zh/.test(document.documentElement.lang||''),T=ZH?{n:'新增 %n 条',m:'有更新',s:'已是最新内容',p:'有新内容（停止操作后自动显示）',b:'马上显示',x:'关闭',tag:'刚刚',upd:'更新',more:'等 %n 处',sep:'：'}
    :{n:'新着 %n 件',m:'更新',s:'最新の内容にしました',p:'新しい内容があります（操作をやめると自動で表示）',b:'今すぐ表示',x:'閉じる',tag:'たった今',upd:'更新',more:'ほか %n か所',sep:'：'};
  // 版面・パネルの名前（data-k か見出し）。ここでの id は section の id
  function label(s){var k=s.getAttribute('data-k');if(k)return {front:'トップ',picks:'気になるかも？',wishlist:'愿望清单'}[k]||k;var h=s.querySelector('.sh>span');return h?h.textContent:s.id;}
  function art(a){return a.closest('article');}
  function keyed(){var l=[];Array.prototype.forEach.call(document.querySelectorAll('article a.lk[href]'),function(a){l.push([a.getAttribute('href'),art(a)]);});
    Array.prototype.forEach.call(document.querySelectorAll('article[data-key]'),function(c){l.push(['k:'+c.getAttribute('data-key'),c]);});return l;}
  function keys(){var o={};keyed().forEach(function(x){o[x[0]]=1;});return o;}
  // 裏のタブで新しい記事が届いたら、タブの題に件数を出す（表に戻したら消す）
  var TITLE=document.title;function badge(n){document.title=n?'('+n+') '+TITLE:TITLE;}
  document.addEventListener('visibilitychange',function(){if(!document.hidden)badge(0);});
  function marks(){var o={};Array.prototype.forEach.call(document.querySelectorAll('section[id][data-h]'),function(s){o[s.id]=s.getAttribute('data-h');});return o;}
  function anchor(){var l=document.querySelectorAll('section[id]');for(var i=0;i<l.length;i++){var r=l[i].getBoundingClientRect();if(r.bottom>0)return [l[i].id,r.top];}return null;}
  // items = [[名前, 詳しい言葉, セクションの id]]：名前をクリックするとその版面へ飛ぶ
  function toast(msg,act,items){if(!bar){bar=document.createElement('div');bar.className='wl-live';bar.setAttribute('role','status');bar.setAttribute('aria-live','polite');document.body.appendChild(bar);}
    bar.textContent='';var t=document.createElement('span');t.appendChild(document.createTextNode(msg));
    (items||[]).forEach(function(it,i){t.appendChild(document.createTextNode(i?'、':T.sep));var a=document.createElement('a');a.href='#'+it[2];a.textContent=it[0];a.className='wl-to';t.appendChild(a);
      if(it[1])t.appendChild(document.createTextNode(' '+it[1]));});
    bar.appendChild(t);
    if(act){var b=document.createElement('button');b.type='button';b.textContent=T.b;b.onclick=go;bar.appendChild(b);}
    var x=document.createElement('button');x.type='button';x.className='x';x.textContent='×';x.setAttribute('aria-label',T.x);x.onclick=function(){bar.hidden=true;};bar.appendChild(x);
    bar.hidden=false;clearTimeout(bar._t);if(!act)bar._t=setTimeout(function(){bar.hidden=true;},16000);}
  // 読み直したあと：見ていた場所に戻し、増えた記事・変わったパネルに印を付ける
  var was=ss.get(KEY);ss.del(KEY);
  if(location.search.indexOf('wlv=')>=0&&history.replaceState)history.replaceState(null,'',location.pathname+location.hash);
  if(was){
    if(was.to&&was.to!==VER&&!was.retry){was.retry=1;ss.set(KEY,was);location.replace(location.pathname+'?wlv='+encodeURIComponent(was.to)+location.hash);return;}
    if(was.to&&was.to!==VER)ss.set(KEY+':skip',was.to);  // CDN がまだ古い：この版は諦めて次の版を待つ
    function to(y){try{scrollTo({top:y,behavior:'instant'});}catch(e){scrollTo(0,y);}}
    function back(){var s=was.at&&document.getElementById(was.at[0]);if(s)to(s.getBoundingClientRect().top+pageYOffset-was.at[1]);else if(was.y)to(was.y);}
    if('scrollRestoration' in history)history.scrollRestoration='manual';
    back();addEventListener('load',back);
    var n=0,by={},order=[];   // by[版面の id] = 新しい記事の数
    keyed().forEach(function(x){var c=x[1];if(was.keys&&!was.keys[x[0]]&&c&&!c.classList.contains('fresh')){
      c.classList.add('fresh');var t=document.createElement('span');t.className='fresh-tag';t.textContent=T.tag;c.appendChild(t);n++;
      var sec=c.closest('section[id]');if(sec){if(!by[sec.id]){by[sec.id]=0;order.push(sec);}by[sec.id]++;}}});
    var other=[];   // 新しい記事はないが中身が変わった版面・パネル（話題度・小元素・順位など）
    if(was.marks)Array.prototype.forEach.call(document.querySelectorAll('section[id][data-h]'),function(s){var h=was.marks[s.id];
      if(h&&h!==s.getAttribute('data-h')){if(!by[s.id]){other.push(s);}
        if(s.classList.contains('panel')){s.classList.add('fresh');var t=document.createElement('span');t.className='fresh-tag';t.textContent=T.upd;s.appendChild(t);}}});
    var items=order.map(function(s){return [label(s),T.n.replace('%n',by[s.id]),s.id];}).concat(other.map(function(s){return [label(s),T.m,s.id];}));
    var shown=items.slice(0,4),rest=items.length-shown.length;
    if(items.length||n){toast(ZH?'有新内容':'更新しました',false,shown);
      if(rest>0){var r=document.createElement('span');r.textContent=' '+T.more.replace('%n',rest);bar.firstChild.appendChild(r);}}
    if(document.hidden)badge(n||other.length);
  }
  // 待つとき：ダイアログを開いている・入力欄にいる・書きかけ／選んだファイルがある（読み直すと消えてしまう）
  function dirty(){return Array.prototype.some.call(document.querySelectorAll('input,textarea'),function(i){
    return i.type==='file'?!!(i.files&&i.files.length):!/^(button|submit|checkbox|radio|hidden)$/.test(i.type)&&i.value!==i.defaultValue;});}
  function busy(){var a=document.activeElement;return !!document.querySelector('dialog[open]')||!!(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))||!!a&&a.isContentEditable||dirty();}
  function go(){if(!pending)return;ss.set(KEY,{to:pending,keys:keys(),marks:marks(),at:anchor(),y:pageYOffset});
    if('scrollRestoration' in history)history.scrollRestoration='manual';location.reload();}
  function maybe(){if(pending&&!busy()&&(document.hidden||Date.now()-touched>IDLE))go();}
  // 開いた直後（15 秒以内・まだ入力していない）に、ブラウザの控え（GitHub Pages は 10 分残す）の古いページだと分かったら、
  // ?v=新しい指紋 で開き直して控えを飛ばす。着いたら ?v= は網址から消す。同じ v でまだ古い（配信の控え）ときは繰り返さない
  function cleanV(){try{var u=new URL(location.href);if(u.searchParams.has('v')){u.searchParams.delete('v');history.replaceState(history.state,'',u.pathname+u.search+u.hash);}}catch(e){}}
  function fresh(v){try{var u=new URL(location.href);if(u.searchParams.get('v')===v||Date.now()-LOADED>15000||busy())return false;
    ss.set(KEY,{to:v,keys:keys(),marks:marks(),at:anchor(),y:pageYOffset});   // 開き直したあとも見ていた場所に戻し、増えた記事に印
    u.searchParams.set('v',v);location.replace(u.toString());return true;}catch(e){return false;}}
  function check(){fetch('version.json?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(j){
      var v=j&&j[PAGE];if(!v||v===VER){cleanV();return;}
      if(fresh(v))return;
      if(v===ss.get(KEY+':skip'))return;
      if(pending!==v){pending=v;
        // version.json の <ページ>_marks と自分の data-h を見比べて、どの版面が変わったかを先に言う
        var mk=j[PAGE+'_marks']||{},mine=marks(),ch=[];Object.keys(mk).forEach(function(id){if(mine[id]&&mine[id]!==mk[id][1])ch.push([mk[id][0],'',id]);});
        // 名前を挙げられる変化（AI 編集が整理した記事の増減など）がないときは何も出さない。静かに（操作していないとき）読み直すだけ
        if(ch.length){var sh=ch.slice(0,3);toast(T.p,true,sh);
          if(ch.length>3){var r=document.createElement('span');r.textContent=' '+T.more.replace('%n',ch.length-3);bar.firstChild.appendChild(r);}}}
      maybe();}).catch(function(){});}
  setInterval(check,EVERY);setInterval(maybe,5000);
  // 戻る・タブの復元（bfcache：JS が止まったまま戻る）と、30 秒以上ほかのタブにいたあと表に戻ったときは、開いた直後と同じ扱い：
  // 古ければすぐ ?v= で開き直す（2026-10-25：合併したのに開き直しても古いまま、をなくす。プライベートウィンドウを使わせない）
  var hiddenAt=0;
  document.addEventListener('visibilitychange',function(){if(document.hidden){hiddenAt=Date.now();maybe();return;}if(hiddenAt&&Date.now()-hiddenAt>30000)LOADED=Date.now();check();});
  addEventListener('pageshow',function(ev){if(ev.persisted){LOADED=Date.now();check();}});
  check();   // 開いたらすぐ確かめる（古い控えならすぐ最新に）
})();
""".replace("__EVERY__", str(LIVE_EVERY)).replace("__IDLE__", str(LIVE_IDLE))


# 版面の「更新中」の帯：裏の仕組みがその版面を作り直しているあいだ、**その版面だけ**、上の枠に細い帯を往復させ、
# 予想の進み具合を塗り、「あと約 N 分」を小さく出す。色は版面の --acc。
# 重なり：帯（z-index 4）は版面の上、小元素（.emb、z-index 5）の下。小元素は版面の外にはみ出して帯に重なってよい。
# どの版面がいま何をしているかは、仕組み自身が Supabase の live_status 表に書く（推定はしない）。網页は live_boards() を 30 秒ごとに読む。
#   ニュース収集（digest.live_mark）：探し始め「記事を探しています」→ 探し終えたらすぐ：新着なし＝消える／あり＝「新着 N 件 · AI 整理待ち · 一覧まで約 N 分」
#     （新着は AI 編集が整理するまで記事にならず、版面の下の「整理待ち」に並ぶ。要紧消息だけはすぐ「重大」で載る）
#   AI 編集（digest live-edit / pick-images / publish）：「AI が編集しています」→「配図を選んでいます」→「反映を待っています」
#   小元素の自動補完（emblem_fill.background）：処理中の版面に「小元素を集めています」→ 増えた版面だけ「反映を待っています」
#   「あと約 N 分」はそれぞれの仕組みの最近の実際の長さ（runlog.typical）から。ページ生成（コードの変更）は帯なし。
#   このページより前に始まった作業はもう反映済みなので出さない。

BUSY_CSS = """
/* 版面の火（NAV_JS の kindle / secBurn）：上辺を左から右へ火が走り、そのあと熾火のように明滅。下に火の照り返し */
.sec>.secfire{position:absolute;left:-2px;right:-2px;top:-2px;height:3px;z-index:3;pointer-events:none;transform-origin:0 50%;
 transform:scaleX(var(--sw,0));opacity:var(--burn,0);background:linear-gradient(90deg,var(--alert),var(--flame) 45%,var(--gold) 85%,var(--card));
 box-shadow:0 0 calc(5px + var(--k,0) * 12px) var(--flame),0 0 calc(12px + var(--k,0) * 26px) color-mix(in oklab,var(--flame) 45%,transparent)}
.sec>.secfire::after{content:"";position:absolute;left:0;right:0;top:100%;height:calc(14px + var(--k,0) * 46px);
 background:linear-gradient(color-mix(in oklab,var(--flame) calc(14% + var(--k,0) * 22%),transparent),transparent)}
.sec>.secfire.out{opacity:0;transition:opacity .6s}
@media (prefers-reduced-motion:reduce){.sec>.secfire{display:none}}
.sec>.busy{position:absolute;left:-2px;right:-2px;top:-2px;height:4px;z-index:4;pointer-events:none;overflow:visible}
.busy .bf{position:absolute;left:0;top:0;bottom:0;width:var(--bp,0%);background:color-mix(in srgb,var(--acc) 45%,transparent);transition:width 1s}
.busy .br{position:absolute;top:0;bottom:0;width:24%;left:0;background:linear-gradient(90deg,transparent,var(--acc),transparent)}
.busy .bt{position:absolute;left:18px;top:-10px;white-space:nowrap;background:var(--bg);color:var(--fg);border:1.5px solid var(--acc);
 padding:0 8px;font:700 var(--fs-label)/1.6 var(--font-sans);letter-spacing:.04em}
@media (prefers-reduced-motion:no-preference){.busy .br{animation:wlbusy 1.8s ease-in-out infinite alternate}}
@keyframes wlbusy{to{left:76%}}
"""

BUSY_JS = """
(function(){
  var C=document.getElementById('wl-busy');if(!C)return;var B=JSON.parse(C.textContent),GEN=Date.parse(B.gen)||0,live=[],MIN=60000;
  function read(){if(document.hidden||!B.url||!B.key)return;
    fetch(B.url+'/rest/v1/rpc/live_boards',{method:'POST',headers:{apikey:B.key,'Content-Type':'application/json'},body:JSON.stringify({p_account:window.WL_ACCOUNT})})
      .then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(l){live=l||[];paint();}).catch(function(){});}
  function left(eta,now){var l=eta-now;return l>MIN?'あと約 '+Math.ceil(l/MIN)+' 分':'まもなく反映';}
  function paint(){var now=Date.now(),on={};
    live.forEach(function(x){var id=B.ids[x.board],st=Date.parse(x.started_at),eta=Date.parse(x.eta_at)||0,text;
      if(!id||st<GEN-MIN)return;   // このページより前に始まった作業はもう反映済み
      if(x.proc==='collect')text=x.state==='fetch'?'記事を探しています':'新着 '+x.found+' 件 · AI 整理待ち'+(eta-now>MIN?' · 一覧まで約 '+Math.ceil((eta-now)/MIN)+' 分':'');
      else text=(x.note||'更新しています')+(eta?' · '+left(eta,now):'');
      var o={start:st,text:text,pc:eta>st?(now-st)/(eta-st):null};if(!on[id]||st<on[id].start)on[id]=o;});
    Array.prototype.forEach.call(document.querySelectorAll('section.sec[id]'),function(sec){var o=on[sec.id],bar=sec.querySelector(':scope>.busy');
      if(!o){if(bar)bar.remove();return;}
      if(!bar){bar=document.createElement('div');bar.className='busy';bar.setAttribute('role','status');
        bar.innerHTML='<i class="bf"></i><i class="br"></i><span class="bt"></span>';sec.insertBefore(bar,sec.firstChild);}
      bar.style.setProperty('--bp',o.pc==null?'0%':Math.max(3,Math.min(97,o.pc*100)).toFixed(1)+'%');
      bar.querySelector('.bt').textContent=o.text;});}
  paint();read();setInterval(paint,20000);setInterval(read,30000);
  document.addEventListener('visibilitychange',function(){if(!document.hidden)read();});
})();
"""


def _busy_tag(busy, generated):
    if not busy:
        return ""
    cfg = json.dumps({**busy, "gen": generated or ""}, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/json" id="wl-busy">{cfg}</script><script>{BUSY_JS}</script>'


def busy_plan(names=(), db=None):
    """版面の「更新中」の帯の設定（BUSY_JS が読む）。names = 全部の関注項の名前（live_status の版面名 → 版面の id）；
    db = {url, key}（公開の publishable key）。"""
    return {"url": (db or {}).get("url") or "", "key": (db or {}).get("key") or "", "ids": {n: _wid(n) for n in names}}


def _account_tag(page=""):
    """網页が Supabase に渡すアカウント（db/accounts.sql の p_account）。ページごとの JS は window.WL_ACCOUNT を読む。
    ログイン（AUTH_JS）も一緒に入れる：どのページにも右上のログインボタンが出る。"""
    return f'<script>window.WL_ACCOUNT={json.dumps(sitedir.NAME)};</script>{_auth_tag(page)}'


# ---- ログイン（2026-10-20，用户定的）-------------------------------------------------------------
# 访客（ログインしていない）= 見るだけ；一般用户 = メールアドレスで入った人（運営者のページは見るだけ）；管理者 = 全部・管理ページ。
# 本当の門番はデータベース（db/auth.sql・db/auth_guard.sql の can_edit / is_admin）。ここはボタンを止めて理由を出すだけ。
# 開關（private.auth_flags の enforce、db/auth_enforce.sql）が閉じている間は前と同じ（だれでも変えられる・管理ページも見える）。
# 2026-10-21，用户定的：だれでもメールアドレス＋パスワード（Supabase Auth、メールは送らない・再発行なし）・重ならない（public.app_users）・はじめに利用規約に同意（TERMS_VERSION）。
# このブラウザが覚える（localStorage の wl-user と Supabase のセッション wl-auth）。Google は保留（PENDING.md）。
AUTH_DB = {}   # {url, key}：digest.cmd_render が入れる（公開の publishable key）
SUPABASE_JS = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js"
# ページごとに「見るだけ」のとき止める操作（それ以外のクリック・リンク・絞り込みはそのまま）
AUTH_LOCK = {"index": "[data-vote]", "heat": "[data-vote]", "wishlist": "[data-vote],#snap button,#snap input,#snap textarea",
             "settings": "button,input,select,textarea,[contenteditable]",
             "admin": "button,input,select,textarea"}
ROLE_JA = {"admin": "店長", "user": "お客さま", "guest": "ゲスト"}   # 運営者 = 店長（「店長のおすすめ」と同じ設定）

AUTH_CSS = """
.wl-auth{position:fixed;top:10px;right:12px;z-index:90;display:flex;align-items:center;gap:8px;font:700 13px/1.4 var(--font-sans)}
.wl-auth .shop{padding:2px 9px;background:var(--ink);color:var(--card);font:500 var(--fs-label)/1.6 var(--font-sans);letter-spacing:.06em;transform:skewX(var(--skew));box-shadow:2px 2px 0 var(--rose)}
.wl-auth>button{display:flex;align-items:center;gap:8px;max-width:220px;min-height:36px;padding:4px 12px 4px 4px;border:2px solid var(--ink);
 background:var(--card);color:var(--ink);box-shadow:3px 3px 0 var(--ink);cursor:pointer;font:inherit}
.wl-auth>button.in{padding-left:12px}
.wl-auth>a.new{display:flex;align-items:center;min-height:36px;padding:4px 12px;border:2px solid var(--ink);background:var(--gold);color:var(--ink);
 box-shadow:3px 3px 0 var(--ink);text-decoration:none;font:inherit}
.wl-auth>a.new:hover,.wl-auth>a.new:focus-visible{background:var(--card)}
.wl-auth>a.new.home{background:var(--card)}
.wl-auth>a.new.home:hover,.wl-auth>a.new.home:focus-visible{background:var(--gold)}
.wl-auth .menu a.about{display:block;margin-top:4px}
.wl-auth .menu .st{margin:0;font-size:12px;line-height:1.5}
.wl-auth>button:hover,.wl-auth>button:focus-visible{background:var(--gold)}
.wl-auth img{width:26px;height:26px;border-radius:50%;object-fit:cover;flex:none}
.wl-auth .ini{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;flex:none;background:var(--ink);color:var(--card);font:900 13px/1 var(--font-sans)}
.wl-auth .rl.wait{background:var(--alert)}
.wl-auth .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wl-auth .rl{flex:none;padding:0 6px;background:var(--ink);color:var(--card);font-size:var(--fs-tag);letter-spacing:.06em;transform:skewX(var(--skew))}
.wl-auth .rl.admin{background:var(--rose)}
.wl-auth .menu{position:absolute;right:0;top:calc(100% + 8px);min-width:220px;background:var(--card);color:var(--ink);border:2px solid var(--ink);
 box-shadow:4px 4px 0 var(--ink);padding:12px;display:flex;flex-direction:column;gap:8px;font-weight:500}
.wl-auth .menu[hidden]{display:none}
.wl-auth .menu small{opacity:.75;line-height:1.5}
.wl-auth .menu button{border:2px solid var(--ink);background:transparent;color:var(--ink);padding:5px 10px;font:700 13px var(--font-sans);cursor:pointer;text-align:left}
.wl-auth .menu button:hover{background:var(--gold)}
.wl-login{display:flex;flex-direction:column;gap:8px}
.wl-login label{display:flex;flex-direction:column;gap:4px;font-weight:700}
.wl-login label[hidden]{display:none}
.wl-login input{min-width:0;padding:6px 8px;border:2px solid var(--ink);background:var(--card);color:var(--ink);font:500 14px var(--font-sans)}
.wl-login button{align-self:flex-start;border:2px solid var(--ink);background:var(--gold);color:var(--ink);padding:6px 12px;font:700 13px var(--font-sans);cursor:pointer}
.wl-login button:disabled{opacity:.6;cursor:wait}
.wl-auth .wl-login .st,.wl-auth .menu .st{display:block;width:auto;max-width:none;margin:0;padding:0;border:0;background:none;text-align:left;font-size:13px;line-height:1.5}
.wl-login .first{margin:4px 0 0;padding-top:8px;border-top:1px solid var(--hair);font-size:13px;line-height:1.6}
.wl-login .tabs{display:flex;border-bottom:2px solid var(--ink)}
.wl-login .tabs button{flex:1;align-self:auto;border:0;background:transparent;padding:6px 8px;font:700 13px var(--font-sans);color:var(--ink);opacity:.6;cursor:pointer;box-shadow:none}
.wl-login .tabs button[aria-selected=true]{opacity:1;background:var(--ink);color:var(--card)}
.wl-login .hint{margin:0;min-height:1.4em;font-size:12px}
.wl-login .hint.ok{color:var(--good)}
.wl-login .hint.ng{color:var(--alert)}
.wl-login .agree,.wl-agree .agree{display:flex;gap:6px;align-items:flex-start;font:500 13px/1.5 var(--font-sans)}
.wl-login .agree[hidden]{display:none}
.wl-login a,.wl-agree a,.wl-auth .menu>a{color:var(--rose);text-decoration:underline;text-underline-offset:2px}
.wl-auth .menu .quiet{border-color:var(--hair);opacity:.75}
.wl-agree{position:fixed;inset:0;z-index:96;display:grid;place-items:center;padding:16px;background:color-mix(in srgb,var(--ink) 55%,transparent)}
.wl-agree>div{max-width:440px;background:var(--card);color:var(--ink);border:3px solid var(--ink);box-shadow:var(--shadow-l);padding:20px 22px;display:flex;flex-direction:column;gap:12px}
.wl-agree h2{margin:0;font:900 20px/1.3 var(--font-sans)}
.wl-agree p{margin:0;line-height:1.7;font-size:14px}
.wl-agree form{display:flex;flex-direction:column;gap:12px}
.wl-agree .row{display:flex;flex-wrap:wrap;gap:8px}
.wl-agree button{border:2px solid var(--ink);background:var(--gold);color:var(--ink);padding:6px 14px;font:700 14px var(--font-sans);cursor:pointer}
.wl-agree button[data-out]{background:transparent}
.wl-auth .menu{width:min(300px,calc(100vw - 24px))}
.wl-toast{position:fixed;left:50%;bottom:72px;z-index:95;transform:translateX(-50%);max-width:calc(100vw - 32px);background:var(--ink);color:var(--card);
 padding:9px 16px;box-shadow:4px 4px 0 var(--rose);font:700 14px/1.5 var(--font-sans)}
.wl-toast[hidden]{display:none}
html[data-lock="1"] [data-vote]{cursor:not-allowed}
.wl-ro{margin:0 0 4px;padding:8px 12px;border:2px dashed var(--ink);background:var(--sheet);font:700 13px/1.6 var(--font-sans)}
html[data-gate="1"] body>*:not(.wl-auth):not(.wl-gate):not(.wl-toast):not(.wl-agree){display:none!important}
html[data-page="admin"][data-auth="wait"] body>*:not(.wl-auth){visibility:hidden}
html[data-maybe-mine="1"][data-auth="wait"] body>*:not(.wl-auth){visibility:hidden}
html[data-mine="1"] body>*:not(.wl-auth):not(.wl-mine):not(.wl-toast):not(.wl-agree){display:none!important}
html[data-mine="2"] .wl-off{display:none!important}
html[data-mine="2"] .mastwish,html[data-mine="2"] .navwish,html[data-mine="2"] .swish,html[data-mine="2"] .nav .logo .hm,
html[data-mine="2"] .vt,html[data-mine="2"] .vote,html[data-mine="2"] [data-vote]{display:none!important}
html[data-mine="2"] .subhead small,html[data-mine="2"] details.pend{display:none}
.wl-cards>a.np{padding-top:8px}
@media (max-width:560px){html[data-mine="2"] body{padding-bottom:72px}.wl-cards>a.np{display:flex}}
.wl-mybar{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin:0 0 14px;padding:6px 2px;border-bottom:2px solid var(--ink);font:700 13px/1.5 var(--font-sans);color:var(--ink)}   /* 箱にしない：店長のページの上に 1 本の帯だけ */
.wl-mybar b{font:900 18px/1.3 var(--font-sans)}.wl-mybar a{color:var(--ink)}.wl-mybar small{flex-basis:100%;font-weight:500;opacity:.8}
.wl-mybar a.add{padding:4px 12px;background:var(--gold);border:2px solid var(--ink);text-decoration:none}.wl-mybar small.ok{opacity:1;color:var(--ink);background:var(--paper);padding:4px 8px}
.wl-wait{margin:0 0 18px;padding:16px 18px;background:var(--card);border:3px solid var(--ink);border-top:8px solid var(--sc);box-shadow:var(--shadow);color:var(--ink);font:500 14px/1.6 var(--font-sans)}
.wl-wait small{font:700 var(--fs-label) var(--font-sans);opacity:.75}.wl-wait h2{margin:2px 0 6px;font:900 22px/1.3 var(--font-sans)}
.wl-wait .dot{display:inline-block;width:10px;height:10px;margin-right:8px;border-radius:50%;background:var(--sc);animation:wlpulse 1.2s ease-in-out infinite}
@keyframes wlpulse{50%{opacity:.25}}@media (prefers-reduced-motion:reduce){.wl-wait .dot{animation:none}}
.wl-today,.wl-maybe{margin:0 0 18px;padding:14px 16px;background:var(--card);border:3px solid var(--ink);box-shadow:var(--shadow);color:var(--ink);font:500 14px/1.6 var(--font-sans)}
.wl-today h2,.wl-maybe h2{margin:0 0 10px;font:900 20px/1.3 var(--font-sans)}.wl-maybe .hint{margin:-6px 0 10px;font-size:13px;opacity:.8}
.wl-today .empty{margin:0;padding:14px 16px;border:2px dashed var(--ink);background:var(--sheet)}.wl-today .empty b{display:block;font:900 16px/1.5 var(--font-sans)}
.wl-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(220px,100%),1fr));gap:10px;margin:8px 0 0}
.wl-cards>a{display:flex;flex-direction:column;gap:4px;min-width:0;padding:0 0 8px;border:2px solid var(--ink);background:var(--paper);color:var(--ink);text-decoration:none}
.wl-cards .pic{position:relative;display:block;aspect-ratio:16/10;background:var(--sheet);overflow:hidden}
.wl-cards .pic img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;z-index:1}
.wl-cards .pic .ph{position:absolute;inset:0;display:grid;place-items:center;padding:8px;text-align:center;font:900 15px/1.3 var(--font-sans);opacity:.55}
.wl-cards .k{padding:4px 10px 0;font:700 var(--fs-label) var(--font-sans);opacity:.8}
.wl-cards b{padding:0 10px;font:700 15px/1.45 var(--font-sans);overflow-wrap:anywhere}
.wl-cards b i{font-style:normal;font-weight:900;color:var(--rose);margin-right:6px}
.wl-cards small{padding:0 10px;font:500 var(--fs-label) var(--font-sans);opacity:.75}
.wl-maybe .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.wl-maybe .chips a{padding:2px 10px;border:2px solid var(--ink);background:var(--gold);color:var(--ink);text-decoration:none;font:700 13px/1.6 var(--font-sans)}
@media (max-width:560px){.wl-cards>a{display:grid;grid-template-columns:88px minmax(0,1fr);grid-auto-rows:min-content;column-gap:0;padding:0}
 .wl-cards .pic{grid-row:1/span 3;aspect-ratio:auto;min-height:88px;height:100%}.wl-cards .pic .ph{font-size:12px}
 .wl-cards .k{padding-top:6px}.wl-cards b{padding-top:4px;font-size:14px}.wl-cards small{padding-bottom:8px}}
.wl-mine .tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin:0 0 8px}
.wl-mine .tiles button{margin:0;min-height:52px;padding:8px 10px;text-align:left;background:var(--card);border:3px solid var(--sc);font:900 14px/1.3 var(--font-sans);color:var(--ink);display:flex;flex-direction:column;gap:2px}
.wl-mine .tiles button small{font:500 var(--fs-label) var(--font-sans);opacity:.75}
.wl-mine .tiles button[aria-pressed=true]{background:var(--sc);color:var(--card)}
.wl-mine .save{display:block;width:100%;min-height:48px;margin-top:14px;font-size:16px}.wl-mine .save[disabled]{opacity:.5;cursor:default}
.wl-mine{max-width:880px;margin:0 auto;padding:72px 16px 64px;color:var(--ink);font:500 15px/1.7 var(--font-sans)}
.wl-mine .mn{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.wl-mine .mn a{padding:4px 12px;border:2px solid var(--ink);background:var(--card);color:var(--ink);text-decoration:none;font:700 13px var(--font-sans)}
.wl-mine .mn a[aria-current]{background:var(--ink);color:var(--card)}
.wl-mine header{margin:0 0 22px;padding:18px 20px;background:var(--card);border:3px solid var(--ink);box-shadow:var(--shadow)}
.wl-mine header small{display:inline-block;padding:0 8px;background:var(--rose);color:var(--card);font:700 var(--fs-label)/1.8 var(--font-sans);transform:skewX(var(--skew))}
.wl-mine h1{margin:6px 0 4px;font:900 26px/1.3 var(--font-sans);overflow-wrap:anywhere}
.wl-mine h2{margin:26px 0 10px;font:900 18px/1.4 var(--font-sans)}.wl-mine h2 small{font:500 var(--fs-label) var(--font-sans);opacity:.75;margin-left:6px}
.wl-mine h3{margin:14px 0 6px;font:700 14px/1.4 var(--font-sans);display:flex;align-items:center;gap:6px}.wl-mine h3 i{width:10px;height:10px;display:inline-block}
.wl-mine p{margin:4px 0}
.wl-mine button,.wl-mine .go{display:inline-block;margin-top:10px;padding:6px 14px;border:2px solid var(--ink);background:var(--gold);color:var(--ink);font:700 13px var(--font-sans);cursor:pointer;text-decoration:none}
.wl-mine button.ghost{background:var(--card)}
.wl-mine ul.kw{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.wl-mine ul.kw li{display:flex;align-items:center;gap:8px;padding:4px 6px 4px 10px;background:var(--card);border:1.5px solid var(--ink);font:700 14px/1.4 var(--font-sans)}
.wl-mine ul.kw li small{font:500 var(--fs-label) var(--font-sans);opacity:.7}
.wl-mine ul.kw li button{margin:0;padding:0 7px;background:var(--card);font-size:12px}
.wl-mine .wl-back{display:flex;flex-wrap:wrap;gap:8px 18px;margin:-8px 0 18px;font:700 14px/1.5 var(--font-sans)}.wl-mine .wl-back a{color:var(--ink)}
.wl-mine .empty{padding:22px 20px;border:2px dashed var(--ink);background:var(--sheet)}.wl-mine .empty b{display:block;font:900 17px/1.4 var(--font-sans)}
.wl-mine .note{margin-top:18px;font-size:13px;opacity:.85}
.wl-mine form.add{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}
.wl-mine form.add input,.wl-mine form.add select{min-width:0;padding:6px 8px;border:2px solid var(--ink);background:var(--card);color:var(--ink);font:500 14px var(--font-sans)}
.wl-mine form.add input{flex:1 1 220px}.wl-mine form.add button{margin:0}
.wl-mine form.add label{flex-basis:100%;margin-bottom:-4px;font:700 13px var(--font-sans)}.wl-mine form.add label+select{flex:none}
.wl-mine form.add label[for$="s"]{flex-basis:auto;align-self:center;margin:0}
.wl-mine .go.ghost{background:var(--card);margin-top:18px}.wl-mine .hint{font-size:13px;opacity:.8}
.wl-mine .wl-msg .undo{margin:0 0 0 10px;padding:2px 10px;background:var(--card)}
.wl-mine .wl-msg{display:block;width:auto;max-width:none;min-height:1.5em;margin:0 0 10px;font-size:13px}
@media (max-width:560px){.wl-mine{padding-top:24px}.wl-mine h1{font-size:22px}}
.wl-gate{min-height:100vh;display:grid;place-items:center;padding:16px;background:var(--paper)}
.wl-gate>div{max-width:420px;background:var(--card);border:3px solid var(--ink);box-shadow:var(--shadow-l);padding:22px 24px;display:flex;flex-direction:column;gap:12px}
.wl-gate h1{margin:0;font:900 22px/1.3 var(--font-sans)}
.wl-gate p{margin:0;line-height:1.7}
.wl-gate a,.wl-gate button{align-self:flex-start;border:2px solid var(--ink);background:var(--gold);color:var(--ink);padding:6px 14px;font:700 14px var(--font-sans);cursor:pointer;text-decoration:none}
.wl-mem table{width:100%;border-collapse:collapse;font-size:13px}
.wl-mem th,.wl-mem td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--hair)}
.wl-mem form{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.wl-mem input,.wl-mem select{min-width:0;padding:5px 8px;border:2px solid var(--ink);background:var(--card);font:500 14px var(--font-sans)}
.wl-mem input{flex:1 1 220px}
.wl-mem button{border:2px solid var(--ink);background:var(--ink);color:var(--card);padding:5px 14px;font:700 13px var(--font-sans);cursor:pointer}
.wl-mem .st{min-height:1.4em;font-size:13px}
@media (max-width:560px){.wl-auth{top:auto;bottom:12px;right:12px;transition:transform .25s ease,opacity .25s ease}.wl-auth .menu{top:auto;bottom:calc(100% + 8px)}.wl-auth .shop{display:none}
  .wl-auth.away{transform:translateY(calc(100% + 24px));opacity:0;pointer-events:none}}
@media (max-width:560px) and (prefers-reduced-motion:reduce){.wl-auth{transition:none}}
"""

AUTH_JS = r"""
(function(){
  var A=__AUTH__, R=document.documentElement, base=(A.url||'').replace(/\/$/,'');
  if(!base||!A.key||!window.fetch) return;
  var page=A.page||((document.querySelector('meta[name="wl-ver"]')||{}).dataset||{}).page||'';
  R.dataset.page=page; R.dataset.role='guest'; R.dataset.auth='wait';
  var OWN=!!document.querySelector('meta[name="wl-own"]'), signedOut=false;   // 本人のページ（user_pages.py）の中か
  try{ if(!OWN&&/^(index|wishlist|heat|settings)$/.test(page)&&(localStorage.getItem('wl-user')||localStorage.getItem('wl-auth'))) R.dataset.maybeMine='1'; }catch(e){}   // ログインを覚えている：自分のページか決まるまで店長の中身を見せない（本人のページはもう本人のものなので隠さない）
  var ROLE=__ROLE__, LOCK=__LOCK__[page]||'', tok=null, user=null, sb=null, of=window.fetch.bind(window);
  // 自分のデータベース（REST）への呼び出しにだけ、ログインした人の鍵を付ける。ページの JS はそのまま
  window.fetch=function(input,init){
    try{
      var u=typeof input==='string'?input:(input&&input.url)||'';
      if(tok&&u.indexOf(base+'/rest/')===0){
        init=Object.assign({},init||{});
        var h=new Headers(init.headers||(typeof input!=='string'&&input.headers)||undefined);
        h.set('Authorization','Bearer '+tok); init.headers=h;
      }
    }catch(e){}
    return of(input,init);
  };
  function rpc(fn,body){
    var h={apikey:A.key,'Content-Type':'application/json'}; if(tok) h.Authorization='Bearer '+tok;
    return of(base+'/rest/v1/rpc/'+fn,{method:'POST',headers:h,body:JSON.stringify(body||{})})
      .then(function(r){return r.text().then(function(t){var j=null; try{j=t?JSON.parse(t):null;}catch(e){} if(!r.ok) throw new Error((j&&j.message)||r.status); return j;});});   // void の関数は 204（本文なし）
  }
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return '&#'+c.charCodeAt(0)+';';});}
  var toastT=0;
  function toast(t){
    var el=document.querySelector('.wl-toast'); if(!el){el=document.createElement('div');el.className='wl-toast';el.setAttribute('role','status');document.body.appendChild(el);}
    el.textContent=t; el.hidden=false; clearTimeout(toastT); toastT=setTimeout(function(){el.hidden=true;},4000);
  }
  // ログイン（2026-10-21，用户定的）：メールアドレス＋パスワード・重ならない（データベースで確かめる、大文字小文字は区別しない）。
  // 新しく始めるときは利用規約・プライバシーポリシーに同意（どの版にいつ同意したかを app_users に残す。版が上がったらもう一度聞く）。
  // このブラウザが覚える（localStorage の wl-user、ログアウトまで）。店長のメール（invites の role=admin）だけパスワードも聞く
  // （Supabase Auth の signInWithPassword。2026-10-21 に「最初の 1 回メールのリンク」から変えた：毎回のメール確認は面倒）。
  var ME='wl-user', me=null, TV=A.terms||1, TURL=A.termsUrl||'terms.html', START=A.start||'../#name', HOME=A.home||'../?stay', SHOP=/^(index|wishlist|heat|settings)$/.test(page);   // 店長のものを見せているページ
  try{ me=JSON.parse(localStorage.getItem(ME)||'null'); if(me&&!me.name) me=null; }catch(e){}
  function saveMe(o){ me=o; try{ if(o) localStorage.setItem(ME,JSON.stringify(o)); else localStorage.removeItem(ME); }catch(e){} }
  var isMail=function(n){return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(n||'');};
  function sayErr(m){
    m=String(m||'');
    if(/not authorized/i.test(m)) return '確認のメールを送れませんでした（メール送信の設定待ち）';
    if(/rate limit|security purposes|too many/i.test(m)) return '送りすぎです。少し待ってからもう一度';
    return m||'うまくいきませんでした';
  }
  var agreeBox=function(){return '<label class="agree"><input type="checkbox"> <span><a href="'+esc(TURL)+'" target="_blank" rel="noopener">利用規約・プライバシーポリシー</a>に同意する</span></label>';};
  // 右上はログインだけ。新しく始めるのは入口の流れ（言語・ジャンル・最初の版面を選ぶ）に一本化（2026-10-21，サイト全体で同じ始め方に）
  function loginForm(){
    return '<form class="wl-login" data-mode="old" novalidate>'+
      '<label>メールアドレス<input type="email" required maxlength="80" autocomplete="username" autocapitalize="off" spellcheck="false" placeholder="登録したメールアドレス"></label>'+
      '<label class="pw"><span class="pwl">パスワード</span><input type="password" maxlength="72" autocomplete="current-password"></label>'+
      '<button type="submit" class="go">ログイン</button><p class="st" aria-live="polite"></p>'+
      '<p class="first">はじめての方：<a href="'+esc(START)+'">新しく始める →</a><br><small>メールアドレスとパスワード・ニュースの言語・好きなジャンルを選ぶだけ（1 分）</small></p></form>';
  }
  function after(name,agreed,st){
    if(agreed<TV){ askAgree(); return; }
    toast('ようこそ、'+(isMail(name)?name.split('@')[0]:name)+' さん'); refresh();   // 成功は短く（clarify）
  }
  function bindLogin(root){
    var f=root.querySelector('.wl-login'); if(!f) return;
    var inp=f.querySelector('input[type=email]'), pw=f.querySelector('.pw input'), st=f.querySelector('.st'), go=f.querySelector('.go');
    // だれでもメール＋パスワード（Supabase Auth の signInWithPassword。2026-10-21，用户定的：ログインの形を全員そろえる・メールは送らない）
    f.onsubmit=function(ev){
      ev.preventDefault(); ev.stopImmediatePropagation();
      var n=inp.value.trim().toLowerCase(), p=pw.value;
      if(!isMail(n)){ st.textContent='メールアドレスを入れてください（例：name@example.com）'; return; }
      if(!p){ st.textContent='パスワードを入れてください'; pw.focus(); return; }
      if(!sb){ st.textContent='準備中です。少し待ってからもう一度'; return; }
      go.disabled=true; st.textContent='';
      sb.auth.signInWithPassword({email:n,password:p})
        .then(function(r){ if(r.error) throw new Error(/invalid/i.test(r.error.message)?'メールアドレスかパスワードが違います':r.error.message);
          return rpc('user_login',{p_name:n}).catch(function(){ return {name:n,agreed_version:TV}; }); })
        .then(function(r){ go.disabled=false; saveMe({name:r.name||n,v:r.agreed_version||0,at:Date.now()}); after(r.name||n,r.agreed_version||0,st); })
        .catch(function(e){ go.disabled=false; st.textContent=sayErr(e.message); });
    };
  }
  // 規約の版が上がった・まだ同意していない人：同意するまで画面を覆う（見るだけには戻れる＝ログアウト）
  function askAgree(){
    if(!me) return;
    var d=document.querySelector('.wl-agree'); if(!d){d=document.createElement('div');d.className='wl-agree';d.setAttribute('role','dialog');d.setAttribute('aria-modal','true');document.body.appendChild(d);}
    d.innerHTML='<div><h2>利用規約・プライバシーポリシー</h2><p>'+(me.v?'内容が新しくなりました。':'')+'続けて使うには、同意をお願いします。'+
      '関心のある作品・投票などの情報（興味・関心の情報）を、サービスのためだけに使います。</p><form>'+agreeBox()+
      '<div class="row"><button type="submit">同意して続ける</button><button type="button" data-out>同意しない（ログアウト）</button></div></form></div>';
    var f=d.querySelector('form');
    d.querySelector('[data-out]').onclick=logout;
    f.onsubmit=function(ev){ev.preventDefault();
      if(!f.querySelector('.agree input').checked){ toast('チェックを入れてください'); return; }
      rpc('user_agree',{p_name:me.name,p_version:TV}).then(function(){ me.v=TV; saveMe(me); d.remove(); toast('ありがとうございます'); refresh(); })
        .catch(function(e){ toast(sayErr(e.message)); });};
  }
  function logout(){
    saveMe(null);
    (sb&&tok?sb.auth.signOut():Promise.resolve()).then(function(){location.reload();});
  }
  var locked=function(){return R.dataset.lock==='1';};
  document.addEventListener('click',function(ev){
    if(!locked()||!LOCK) return;
    var t=ev.target.closest&&ev.target.closest(LOCK);
    if(!t||t.closest('.wl-auth,.wl-gate,.wl-toast,.wl-live,.wl-agree,.wl-mine')) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    toast(R.dataset.role==='guest'?'見るだけです。変えるには右上の「ログイン」から':'ここは店長のページなので、見るだけです');
  },true);
  document.addEventListener('submit',function(ev){ if(locked()&&LOCK&&!(ev.target.closest&&ev.target.closest('.wl-auth,.wl-gate,.wl-agree,.wl-mine'))){ev.preventDefault();ev.stopImmediatePropagation();} },true);
  // スマホ（右下に固定）：下へ読み進めると札をしまい、上へ戻す・ページの上と下の端で出す（本文の写真・文字に重ねたままにしない。よくある「下へで隠す・上へで出す」）
  (function(){var y0=scrollY,mq=matchMedia('(max-width:560px)');
    function set(off){var b=document.querySelector('.wl-auth');if(b&&!(off&&b.querySelector('.menu:not([hidden])')))b.classList.toggle('away',off);}
    addEventListener('scroll',function(){if(!mq.matches)return set(false);var y=scrollY,end=innerHeight+y>=document.documentElement.scrollHeight-8;
      if(y>y0+4&&y>120&&!end)set(true);else if(y<y0-4||end||y<=120)set(false);y0=y;},{passive:true});})();
  function chip(keepOpen){
    var box=document.querySelector('.wl-auth'); if(!box){box=document.createElement('div');box.className='wl-auth';document.body.appendChild(box);}
    var role=R.dataset.role, name=(me&&me.name)||(user&&user.email)||'';
    if(!name){
      // 見るだけの人：「はじめのページ」（入口＝紹介・新しく始める・ログイン・店長のページ）と「ログイン」をいつも見える所に
      // （2026-10-21，用户定的：網址を打たせない。どの画面からも入口へ戻れる。「新しく始める」は入口にある）
      box.innerHTML=(SHOP?'<span class="shop">店長のページ · 見るだけ</span>':'')+'<a class="new home" href="'+esc(HOME)+'">はじめのページ</a>'+
        '<button type="button" class="in" aria-haspopup="true" aria-expanded="false">ログイン</button><div class="menu" hidden>'+loginForm()+
        '<a class="about" href="'+esc(HOME)+'">このサイトについて（はじめのページ）</a></div>';
      var lb=box.querySelector(':scope>button'), lm=box.querySelector('.menu');
      lb.onclick=function(){var o=lm.hidden;lm.hidden=!o;lb.setAttribute('aria-expanded',String(o));if(o) lm.querySelector('input[type=email]').focus();};
      bindLogin(box); return;
    }
    var label=ROLE[role]||role, sh=isMail(name)?name.split('@')[0]:name;
    // ログイン中も「はじめのページ」は画面に見える所に（メニューの中だけだと見つからない。2026-10-21，用户指摘）
    box.innerHTML=(role!=='admin'&&SHOP&&!isMine()?'<span class="shop">店長のページ · 見るだけ</span>':'')+'<a class="new home" href="'+esc(HOME)+'">はじめのページ</a>'+'<button type="button" aria-haspopup="true" aria-expanded="false"><span class="ini" aria-hidden="true">'+esc(sh.charAt(0).toUpperCase())+'</span>'+
      '<span class="nm">'+esc(sh)+'</span><span class="rl '+esc(role)+'">'+esc(label)+'</span></button>'+
      '<div class="menu"'+(keepOpen?'':' hidden')+'><small>'+esc(name)+'<br>このブラウザが覚えています</small>'+
      (role==='admin'&&page!=='admin'?'<button type="button" data-go="admin">管理ページへ</button>':'')+
      (tok?'<button type="button" data-pw>パスワードを変える</button>':'')+
      '<a href="'+esc(HOME)+'">このサイトについて（はじめのページ）</a>'+
      '<a href="'+esc(TURL)+'">利用規約・プライバシーポリシー</a>'+
      '<button type="button" data-out>ログアウト</button></div>';
    var b=box.querySelector(':scope>button'), menu=box.querySelector('.menu');
    b.onclick=function(){var o=menu.hidden;menu.hidden=!o;b.setAttribute('aria-expanded',String(o));};
    menu.querySelector('[data-out]').onclick=logout;
    var go=menu.querySelector('[data-go]'); if(go) go.onclick=function(){location.href='admin.html';};
    var pb=menu.querySelector('[data-pw]'); if(pb) pb.onclick=function(){   // ログインしたまま新しいパスワードに
      var p=prompt('新しいパスワード（8 文字以上）'); if(p===null) return;
      if(p.length<8){ toast('8 文字以上にしてください'); return; }
      if(prompt('もう一度')!==p){ toast('2 回のパスワードが違います'); return; }
      sb.auth.updateUser({password:p}).then(function(r){ toast(r.error?sayErr(r.error.message):'パスワードを変えました'); });
    };
  }
  function gate(){
    var need=page==='admin'&&R.dataset.enf==='1'&&R.dataset.role!=='admin';
    R.dataset.gate=need?'1':'0';
    var g=document.querySelector('.wl-gate'); if(!need){if(g) g.remove(); return;}
    if(!g){g=document.createElement('div');g.className='wl-gate';document.body.appendChild(g);}
    g.innerHTML='<div><h1>管理ページ</h1><p>'+(me?'このページは店長だけが見られます。店長はログアウトして、メールとパスワードでログインしてください。':
      '店長だけが見られます。店長のメールアドレスとパスワードでログインしてください。')+'</p>'+
      (me?'':loginForm())+
      '<a href="./">← ウォッチリスト通信に戻る</a></div>';
    bindLogin(g);
  }
  function readOnlyNote(){
    if(page!=='settings') return;
    var n=document.querySelector('.wl-ro');
    if(!locked()){if(n) n.remove(); return;}
    if(n) return;
    n=document.createElement('p'); n.className='wl-ro';
    n.textContent='見るだけです。設定を変えるには右上の「ログイン」から。';
    var at=document.querySelector('.page'); if(at) at.insertBefore(n,at.firstChild);
  }
  // お客さま自分のページ（2026-10-22，用户定的：アカウントは 1 つずつ独立。ログインしたお客さまに店長の中身は出さない）。
  // 簡報・欲しい物・話題度・設定で、店長の中身の代わりに自分の（最初は空の）ページを出す。中身は Supabase の my_page()（本人の行だけ、db/my_page.sql）。
  // 画面の言葉は skill（impeccable の clarify・distill、onboarding、web-design-guidelines）に合わせる（2026-10-22，用户指摘）：
  //   ・お客さまに要らない内部の事情（仕組みの説明・準備中・店長のページへの切り替え）は出さない。1 つの状態に、今わかること 1 つと次の一手 1 つ
  //   ・空の状態は行き止まりにしない：何のための場所か＋最初の 1 つを足す道（まだ使えない「欲しい物」「話題度」は目次に出さない）
  //   ・入力には見える名前（例の文字は名前の代わりにならない）。外したら「元に戻す」（確認より元に戻せるほうがよい）
  var SECS=A.secs||[], ADD='../?add';   // 足す = 入口と同じ「ジャンル → 左右に払うカード → 確認」（welcome.py の ?add）
  function isMine(){return SHOP&&R.dataset.role==='user'&&!!(me||user);}
  function secJa(k){for(var i=0;i<SECS.length;i++)if(SECS[i][0]===k)return SECS[i][1];return k||'その他';}
  function secColor(k){for(var i=0;i<SECS.length;i++)if(SECS[i][0]===k)return SECS[i][2]||'';return '';}
  function norm(s){return String(s||'').toLowerCase().replace(/\s+/g,'');}
  // 店長の版面と同じものか（scripts/userfeed.py の shop_hit と同じ規則。変えるときは両方）：空白・大小を無視して同じ、
  // または短いほうが長いほうに含まれ、かな・漢字を含む 2 字以上か、英数字だけなら前後が英数字でない（From Software は FROM にしない）
  function an(c){return /[a-z0-9]/.test(c||'');}
  function shopHit(a,b){a=norm(a);b=norm(b);if(!a||!b)return false;if(a===b)return true;
    var s=a.length<=b.length?a:b,l=s===a?b:a;if(s.length<2)return false;
    if(/[^\x00-\x7f]/.test(s))return l.indexOf(s)>=0;
    for(var i=l.indexOf(s);i>=0;i=l.indexOf(s,i+1)){var j=i+s.length;if((i===0||!an(l[i-1]))&&(j===l.length||!an(l[j])))return true;}
    return false;}
  function hit(name,picks){return picks.some(function(x){return shopHit(name,x.name);});}
  function mine(){
    var on=isMine(), box=document.querySelector('.wl-mine');
    // お客さま → 访客（ログアウト・「見つかりません」）：showMine が版面・駅・目次の網址を書き換えているので、開き直して店長のページに戻す
    // 本人のページの中では、ログインの確かめの途中で一瞬「お客さまでない」と出ても開き直さない。開き直すのはログアウトしたときだけ
    if(!on&&OWN){if(signedOut)location.reload();return;}
    if(!on&&R.dataset.mine==='2'){R.dataset.mine='0';clearInterval(R._wlub);location.reload();return;}
    if(!on){R.dataset.mine='0';clearInterval(R._wlub);R._wlmb=null;if(box) box.remove();var b0=document.querySelector('.wl-mybar');if(b0)b0.remove();
      document.querySelectorAll('.wl-off').forEach(function(x){x.classList.remove('wl-off');});return;}
    if(R.dataset.mine!=='2') R.dataset.mine='1';
    if(!box){box=document.createElement('main');box.className='wl-mine';box.id='mine';document.body.appendChild(box);}
    if(!box.dataset.ready) box.innerHTML='<p class="wl-msg" role="status">読み込み中…</p>';
    (tok?rpc('my_page'):Promise.resolve(null)).then(function(p){route(box,p,'');},function(e){route(box,null,e.message);});
  }
  function picksOf(p){return ((p&&p.prefs&&p.prefs.picks)||[]).filter(function(x){return x&&x.name;});}
  // 選んだものがあれば、店長のページと同じ版面のうち自分の選んだものだけを出す（2026-10-22，用户定的：お客さまも店長と同じ機能。記事は同じ公開のニュース）
  // 本人のページ（scripts/user_pages.py が店長と同じ部品で作り、非公開の箱 pages/<account>/index.html に置く）は、
  // 小さな殻のページ me.html が読み込んで描く（render.render_me）。このページの中で差し替えると、店長のページの JS
  // （ログインの見張り・版の確かめ）が同じ窓に残って、差し替え → 開き直し をくり返し、白い画面にもなった（2026-10-24）。
  // ここではお客さまを me.html へ送るだけ。殻が読めなかったとき（?own=0）は送らずに前の画面。30 秒に 3 回まで
  function ownPage(){
    if(!tok||(page!=='index'&&page!=='settings')||/[?&]own=0/.test(location.search)) return Promise.resolve(false);
    var hist=[];try{hist=JSON.parse(sessionStorage.getItem('wl-own-at')||'[]').filter(function(x){return Date.now()-x<30000;});}catch(_){}
    if(hist.length>=3) return Promise.resolve(false);
    try{hist.push(Date.now());sessionStorage.setItem('wl-own-at',JSON.stringify(hist));}catch(_){}
    location.replace('me.html'+(page==='settings'?'?p=settings':'')+location.hash);   // 設定も本人の分（同じ部品の render_settings）
    return Promise.resolve(true);
  }
  function route(box,p,err){
    var picks=picksOf(p);
    if(document.querySelector('meta[name="wl-own"]')){box.remove();R.dataset.mine='2';return;}   // もう本人のページの中
    // ログインしたお客さまはだれでも、まず本人のページ（店長と同じ枠組み）。版面の数によらない（HARNESS.md「一番大事な決まり」）
    if(page==='settings'&&!err&&tok){box.remove();ownPage().then(function(done){if(!done){var b3=document.createElement('main');b3.className='wl-mine';b3.id='mine';document.body.appendChild(b3);drawMine(b3,p,'');}});return;}
    if(page==='index'&&!err&&tok&&document.querySelector('section.sec[data-k]')){
      box.remove();ownPage().then(function(done){if(done)return;
        if(picks.length)showMine(p,picks);else{var b2=document.createElement('main');b2.className='wl-mine';b2.id='mine';document.body.appendChild(b2);drawMine(b2,p,'');}});return;}
    drawMine(box,p,err);
  }
  var UB='あなたが足したもの';   // お客さまが足した版面の小分類（本文の見出し・目次の札）
  function showMine(p,picks){
    R.dataset.mine='2';
    var got={};
    document.querySelectorAll('section.sec[data-k]').forEach(function(s){var on=hit(s.dataset.k,picks);s.classList.toggle('wl-off',!on);if(on)got[norm(s.dataset.k)]=1;});
    document.querySelectorAll('.pill[data-for]:not(.wl-upill),.pill.xfer').forEach(function(a){a.classList.toggle('wl-off',!a.dataset.for||!hit(a.dataset.for,picks));});
    document.querySelectorAll('.pill[data-x]').forEach(function(a){a.classList.toggle('wl-off',!hit(a.dataset.x,picks));});   // シリーズの枝も、出ている版面の分だけ
    // トップのポスターと「気になるかも？」は店長と同じ作りのまま、中身を自分の版面のものに絞る（2026-10-23，用户定的：お客さまのページも店長と同じ枠組み。箱だけの画面にしない）
    var fr=document.getElementById('front'), keepFront=false;
    if(fr){fr.querySelectorAll('article[data-k]').forEach(function(a){a.classList.toggle('wl-off',!hit(a.dataset.k,picks));});
      var tp=fr.querySelector('article.top');keepFront=!!tp&&hit(tp.dataset.k,picks);fr.classList.toggle('wl-off',!keepFront);}
    var pkS=document.getElementById('picks'), keepPicks=false;
    if(pkS){pkS.querySelectorAll('.pk[data-w]').forEach(function(c){var on=hit(c.dataset.w,picks);c.classList.toggle('wl-off',!on);if(on)keepPicks=true;});
      pkS.classList.toggle('wl-off',!keepPicks);}
    document.querySelectorAll('.nmore,.nsum').forEach(function(x){x.classList.add('wl-off');});
    var wait=picks.filter(function(x){return !Object.keys(got).some(function(k){return shopHit(k,x.name);});});
    var name=(p&&p.name)||(user&&user.email)||'', sh=isMail(name)?name.split('@')[0]:name;
    var bar=document.querySelector('.wl-mybar')||document.createElement('div');bar.className='wl-mybar';
    var added=(location.search.match(/[?&]added=([^&]*)/)||[])[1];
    if(added&&history.replaceState) history.replaceState(null,'',location.pathname+location.hash);   // 開き直したときにはもう出さない
    try{added=added?decodeURIComponent(added):'';}catch(_){added='';}
    bar.innerHTML='<b>'+esc(sh)+' さんのページ</b><span>追いかけているもの '+picks.length+'</span><a class="add" href="'+ADD+'">＋ 追いかけるものを足す</a><a href="settings.html">外す</a>'+
      (added?'<small class="ok">'+esc(added)+' を足しました。記事が集まりしだい、下の版面に並びます（数時間かかることがあります）。</small>':'')+
      '<small>新しい記事は 1 日に何度か届きます。</small>';
    var m=document.querySelector('main.issues')||document.body; if(!bar.parentNode) m.insertBefore(bar,m.firstChild);
    var issue=document.querySelector('main.issues .issue')||m;
    var secOf={};(A.items||[]).forEach(function(x){secOf[norm(x[0])]=x[1];});
    function secIdx(k){for(var i=0;i<SECS.length;i++)if(SECS[i][0]===k)return i;return SECS.length;}
    // 店長の版面にないもの：my_boards()（db/user_boards.sql、本人の行だけ）の記事で版面を描く。まだなら「集めています」。
    // 前に読んだ分は覚えておく（ログインの更新で描き直しても「集めています」に戻らない）
    var mineB=R._wlmb||{}, bad=false;
    function draw(){
      document.querySelectorAll('.wl-wait,.wl-today,.wl-maybe,.wl-uhead,.wl-upill,.wl-uslot,.wl-utab,.wl-utg,.wl-uchip,.wl-ulab').forEach(function(x){x.remove();});
      var today=document.createElement('section');today.className='wl-today';today.id='wl-today';if(keepFront)today.hidden=true;bar.after(today);
      // 本文も店長のページと同じ「板块 → 小分類」の順に：自分の版面は同じ板块の店長の版面のあと。その板块に店長の版面がなければ、板块の順の位置に見出しを立てて
      function shown(){return [].slice.call(issue.querySelectorAll(':scope>[data-k]:not(.wl-off)')).filter(function(v){return v.id!=='front'&&v.id!=='picks';});}
      function secEl(v){return v.dataset.sec||secOf[norm(v.dataset.k)];}
      var last={};
      wait.forEach(function(x,i){var b=mineB[norm(x.name)]||{state:bad?'err':'wait',stories:[]}, sec=b.sec||x.sec||'其他';
        var s=document.createElement('section');s.className='wl-wait'+(b.state==='ok'?' wl-ub':'');s.id='wl-ub-'+i;s.dataset.k=x.name;s.dataset.sec=sec;s.dataset.sub=UB;
        s.style.setProperty('--sc',secColor(sec)||'var(--ink)');
        s.innerHTML='<small>'+esc(secJa(sec))+'</small><h2>'+esc(x.name)+'</h2>'+board(b);
        var at=shown().filter(function(v){return secEl(v)===sec&&!v.classList.contains('wl-wait');}).pop();
        if(last[sec]){last[sec].after(s);}
        else if(at){   // 同じ板块の店長の版面のあと：店長の小分類の見出しの下に見えないよう、自分の見出し（小分類「あなたが足したもの」）を立てる
          var h0=document.createElement('div');h0.className='subhead wl-uhead';h0.style.setProperty('--sc',secColor(sec)||'var(--ink)');
          h0.innerHTML='<b>'+UB+'</b>';at.after(h0);h0.after(s);}
        else{
          var nx=shown().filter(function(v){return secIdx(secEl(v))>secIdx(sec);})[0];   // 店長の版面・もう置いた自分の版面のうち、後ろの板块の最初
          // 次の板块の見出し（隠れた版面・見出しも越えて）の前に
          if(nx)while(nx.previousElementSibling&&/(^|\s)(subhead|wl-off)(\s|$)/.test(nx.previousElementSibling.className)&&!nx.previousElementSibling.classList.contains('wl-wait'))nx=nx.previousElementSibling;
          var hd=document.createElement('div');hd.className='subhead wl-uhead';hd.style.setProperty('--sc',secColor(sec)||'var(--ink)');
          hd.innerHTML='<span class="tg"><span>'+esc(secJa(sec))+'</span></span><b>'+UB+'</b>';
          if(nx){issue.insertBefore(hd,nx);hd.after(s);}else{issue.appendChild(hd);issue.appendChild(s);}
        }
        last[sec]=s;pill(x.name,sec,s.id,b);});
      if(!keepFront) todayBox(today);   // 店長と同じポスターが出ているときは箱の「今日の主なニュース」は出さない
      var mb=keepPicks?null:maybeBox();if(mb)issue.appendChild(mb);
      tidyNav();
      document.dispatchEvent(new Event('wl-nav'));
    }
    // 目次：自分の版面の駅を、その板块の線路に足す（板块がなければ板块の順の位置に作る）。駅のない板块・小分類の札は隠す
    var nav=document.querySelector('.nav'), rail=document.getElementById('nav-rail');
    function slotFor(sec){
      if(!rail)return null;
      var all=[].slice.call(rail.querySelectorAll('.nslot'));
      for(var i=0;i<all.length;i++)if(all[i].dataset.sec===sec)return all[i];
      var d=document.createElement('div');d.className='nslot wl-uslot';d.dataset.sec=sec;d.style.setProperty('--sc',secColor(sec)||'var(--ink)');
      d.innerHTML='<a class="nsec" href="#"><span class="tg"><span>'+esc(secJa(sec))+'</span></span></a><div class="nbody"></div>';
      var nx=all.filter(function(x){return secIdx(x.dataset.sec)>secIdx(sec);})[0];
      if(nx)rail.insertBefore(d,nx);else rail.appendChild(d);
      var tabs=nav&&nav.querySelector('.mtabs');
      if(tabs){var t=document.createElement('a');t.className='tg wl-utab';t.dataset.sec=sec;t.style.setProperty('--sc',secColor(sec)||'var(--ink)');t.innerHTML='<span>'+esc(secJa(sec))+'</span>';
        var tn=[].slice.call(tabs.querySelectorAll('a[data-sec]')).filter(function(x){return x.dataset.sec&&secIdx(x.dataset.sec)>secIdx(sec);})[0];
        if(tn)tabs.insertBefore(t,tn);else tabs.appendChild(t);}
      return d;
    }
    function pill(n,sec,id,b){var d=slotFor(sec);if(!d)return;
      var st=b.state==='ok'?'記事 '+(b.stories||[]).length+' 件':b.state==='none'?'まだ記事なし':b.state==='limit'?'お休み中':b.state==='err'?'読み込めません':'集めています';
      var nb=d.querySelector('.nbody'),subs=nb.querySelector('.nsubs'),sub=subs?UB:'';
      // 店長の板块（小分類の札がある）に足すときは、札と小見出しも「あなたが足したもの」を 1 つ（店長の小分類の下に見えないように）
      if(subs&&!subs.querySelector('.wl-uchip')){var c=document.createElement('a');c.className='wl-uchip';c.dataset.sub=UB;c.href='#'+id;c.innerHTML=UB+'<small>0</small>';subs.appendChild(c);
        var l=document.createElement('div');l.className='nlab wl-ulab';l.dataset.sub=UB;l.textContent=UB;var mo=nb.querySelector('.nmore');if(mo)nb.insertBefore(l,mo);else nb.appendChild(l);}
      var a=document.createElement('a');a.className='pill wl-upill';a.dataset.for=n;a.dataset.n='0';a.dataset.sub=sub;a.href='#'+id;a.style.setProperty('--sc',secColor(sec)||'var(--ink)');
      a.innerHTML='<i class="no">+</i><i class="ic">'+esc(String(n).charAt(0))+'</i><span class="nm">'+esc(n)+'<small class="cnt">'+esc(st)+'</small></span>';
      var mo2=nb.querySelector('.nmore');if(mo2)nb.insertBefore(a,mo2);else nb.appendChild(a);
      if(subs){var cs=subs.querySelector('.wl-uchip small');if(cs)cs.textContent=String(+cs.textContent+1);}}
    function tidyNav(){
      if(!rail)return;
      var first={};
      [].slice.call(issue.querySelectorAll(':scope>[data-k]:not(.wl-off)')).forEach(function(s){var k=s.dataset.sec||secOf[norm(s.dataset.k)];if(k&&!first[k])first[k]='#'+s.id;});
      rail.querySelectorAll('.nslot').forEach(function(d){
        var ps=[].slice.call(d.querySelectorAll('.nbody .pill:not(.wl-off)')), subs={};ps.forEach(function(p){subs[p.dataset.sub||'']=1;});
        d.classList.toggle('wl-off',!ps.length);
        d.querySelectorAll('.nsubs a[data-sub],.nlab[data-sub]').forEach(function(c){c.classList.toggle('wl-off',!subs[c.dataset.sub]);});
        var a=d.querySelector('.nsec');if(a&&first[d.dataset.sec])a.setAttribute('href',first[d.dataset.sec]);});
      if(nav)nav.querySelectorAll('.mtabs a').forEach(function(t){var k=t.dataset.sec;
        if(!k){t.setAttribute('href','#wl-today');return;}
        t.classList.toggle('wl-off',!first[k]);if(first[k])t.setAttribute('href',first[k]);});
      var lg=nav&&nav.querySelector('.logo');if(lg)lg.setAttribute('href','#wl-today');
      // 板块の名前の札は板块の最初の見出しにだけある：それが隠れたら、出ている最初の見出しに付ける
      var prev=null;[].slice.call(issue.querySelectorAll(':scope>.subhead:not(.wl-off)')).forEach(function(h){var n=h.nextElementSibling;
        while(n&&(!n.dataset||!n.dataset.k||n.classList.contains('wl-off'))&&!n.classList.contains('subhead'))n=n.nextElementSibling;
        var k=n&&n.dataset&&n.dataset.k?(n.dataset.sec||secOf[norm(n.dataset.k)]):null;
        if(k&&k!==prev&&!h.querySelector('.tg')){var g=document.createElement('span');g.className='tg wl-utg';g.innerHTML='<span>'+esc(secJa(k))+'</span>';h.insertBefore(g,h.firstChild);}
        if(k)prev=k;});
    }
    // お客さまのページでは「小分類の見出し」も、下に出ている版面があるときだけ
    document.querySelectorAll('.subhead:not(.wl-uhead)').forEach(function(h){var n=h.nextElementSibling,on=false;
      while(n&&!n.classList.contains('subhead')){if(n.matches('section.sec[data-k]')&&!n.classList.contains('wl-off')){on=true;break;}n=n.nextElementSibling;}
      h.classList.toggle('wl-off',!on);});
    function safe(u){u=String(u||'');return /^https?:\/\//.test(u)?u:'';}
    // 画像：店長の版面の「本站保存」（pics/… の相対の網址）も、このページの網址に直してから確かめる
    function pic(u){if(!u)return '';try{var x=new URL(u,location.href);return x.protocol==='https:'||x.origin===location.origin?x.href:'';}catch(_){return '';}}
    function md(d){var t=Date.parse(d||'');if(isNaN(t))return '';var x=new Date(t);return (x.getMonth()+1)+'.'+x.getDate();}
    function fresh(d){var t=Date.parse(d||'');return !isNaN(t)&&Date.now()-t<36*3600e3;}
    // カード 1 枚。見出し・出典は外から来た文字なので必ず esc。網址は http(s) だけ。画像がなければ字だけのカード（同じ仮の絵を並べない）
    function card(c){var u=safe(c.url);if(!u||!c.title)return '';var img=pic(c.img);
      return '<a href="'+esc(u)+'" target="_blank" rel="noopener"'+(img?'':' class="np"')+'>'+(img?'<span class="pic"><img src="'+esc(img)+'" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></span>':'')+
        (c.board?'<span class="k">'+esc(c.board)+'</span>':'')+'<b>'+(c.isNew?'<i>NEW</i>':'')+esc(c.title)+'</b>'+
        '<small>'+esc([c.when,c.source].filter(Boolean).join(' · '))+'</small></a>';}
    function story2card(st,bn){return {title:st.title,url:st.url,img:st.image,source:st.source,when:md(st.date||st.seen),isNew:fresh(st.date||st.seen),board:bn,t:Date.parse(st.date||st.seen||'')||0};}
    function board(b){
      if(b.state==='ok')return '<div class="wl-cards">'+(b.stories||[]).map(function(st){return card(story2card(st,''));}).join('')+'</div>';
      if(b.state==='none')return '<p>まだ記事が見つかっていません。新しい記事が出たら、ここに並びます。</p>';
      if(b.state==='limit')return '<p>追いかけられるのは 100 個までです。<a href="settings.html">ほかのものを外す</a>と、これも集め始めます。</p>';
      if(b.state==='err')return '<p>記事を読み込めませんでした。少し時間をおいて、ページを開き直してください。</p>';
      return '<p><i class="dot"></i>記事を集めています。集まりしだい、ここに並びます（数時間かかることがあります）。</p>';
    }
    // ニュースらしくないもの（攻略・一覧のページ、予約・通販の商品）は「新着」として出さない
    var NOTNEWS=/攻略|一覧と|最新版】?$|[《【(（]\s*\d+\s*月予約|予約受付|予約開始中|最終値下げ|在庫あり|送料無料/;
    // 店長のページの版面の記事（いま出ている版面だけ）。カードの形にそろえる
    function shopCards(sec,n){var out=[];sec.querySelectorAll('article').forEach(function(a){if(out.length>=n)return;var lk=a.querySelector('a.lk');if(!lk)return;
      var t=lk.getAttribute('aria-label')||'';if(!t||NOTNEWS.test(t))return;
      var im=a.querySelector('.pic img:not(.bg)'),w=a.querySelector('.when');
      out.push({title:t,url:lk.getAttribute('href'),img:im?im.getAttribute('src'):'',board:a.dataset.k||sec.dataset.k,
        isNew:!!(w&&w.querySelector('b')),when:w?(w.firstChild&&w.firstChild.nodeType===3?w.firstChild.nodeValue:''):''});});return out;}
    // 今日の主なニュース（店長のトップの頭条・ほかの注目ニュースに当たるもの）：店長が選んだ頭条のうち自分の版面のもの → 自分の版面の新着 → 店長の版面の先頭
    function todayBox(box){
      var list=[],seen={};function add(c){var u=safe(c.url);if(!u||seen[u]||!c.title||NOTNEWS.test(c.title))return;seen[u]=1;list.push(c);}
      var fr=document.getElementById('front');
      if(fr)fr.querySelectorAll('article[data-k]').forEach(function(a){if(!hit(a.dataset.k,picks))return;var lk=a.querySelector('a.lk'),im=a.querySelector('img:not(.bg)'),w=a.querySelector('.when');
        if(lk)add({title:lk.getAttribute('aria-label')||'',url:lk.getAttribute('href'),img:im?im.getAttribute('src'):'',board:a.dataset.k,isNew:!!(w&&w.querySelector('b'))});});
      var mine=[];wait.forEach(function(x){var b=mineB[norm(x.name)];if(b&&b.state==='ok')(b.stories||[]).slice(0,2).forEach(function(st){var c=story2card(st,x.name);if(c.isNew)mine.push(c);});});
      mine.sort(function(a,b){return b.t-a.t;}).forEach(add);
      issue.querySelectorAll(':scope>section.sec[data-k]:not(.wl-off)').forEach(function(s){shopCards(s,1).forEach(add);});
      list=list.slice(0,6);
      box.innerHTML='<h2>今日の主なニュース</h2>'+(list.length?'<div class="wl-cards">'+list.map(card).join('')+'</div>':
        '<p class="empty"><b>ここに、あなたが追いかけているものの今日の主なニュースが並びます</b>記事が届いたものから、大事なものを先頭に。下には追いかけているものごとの版面が並び、記事が集まりしだい埋まっていきます。</p>');
    }
    // 気になるかも？（規則・AI なし）：選んだジャンルにある、まだ追いかけていない店長の版面の新着 → 名前だけの候補。
    // 「＋ X を追いかける」は X を選んだ状態で足す流れ（入口の ?add の確認の画面）へ
    function maybeBox(){
      var secs={};picks.forEach(function(x){secs[x.sec]=1;});
      var cards=[];issue.querySelectorAll(':scope>section.sec[data-k].wl-off').forEach(function(s){if(cards.length>=4||!secs[secOf[norm(s.dataset.k)]]||hit(s.dataset.k,picks))return;shopCards(s,1).forEach(function(c){cards.push(c);});});
      var names=(A.items||[]).filter(function(x){return secs[x[1]]&&!hit(x[0],picks)&&!cards.some(function(c){return norm(c.board)===norm(x[0]);});}).slice(0,6);
      if(!cards.length&&!names.length)return null;
      var s=document.createElement('section');s.className='wl-maybe';
      var cand=cards.map(function(c){return [c.board,secOf[norm(c.board)]||''];}).concat(names).slice(0,6);
      s.innerHTML='<h2>気になるかも？</h2><p class="hint">追いかけているものと同じジャンルの新着です。</p>'+(cards.length?'<div class="wl-cards">'+cards.map(card).join('')+'</div>':'')+
        '<div class="chips">'+cand.map(function(x){return '<a href="'+esc(ADD+'&pick='+encodeURIComponent(x[0])+'&s='+encodeURIComponent(x[1]||''))+'">＋ '+esc(x[0])+' を追いかける</a>';}).join('')+'</div>';
      return s;
    }
    draw();
    // 返事が前と同じなら描き直さない（読んでいる最中に画像の読み直し・目次の組み直しを起こさない）
    function load(){if(!tok||!wait.length)return;rpc('my_boards').then(function(r){var sig=JSON.stringify((r&&r.boards)||[]);
        if(sig===R._wlsig&&!bad)return;R._wlsig=sig;bad=false;mineB={};((r&&r.boards)||[]).forEach(function(b){if(b&&b.name)mineB[norm(b.name)]=b;});R._wlmb=mineB;draw();},
      function(){if(!Object.keys(mineB).length&&!bad){bad=true;draw();}});}
    load();clearInterval(R._wlub);R._wlub=setInterval(function(){if(!document.hidden)load();},5*60e3);   // 開いている間も 5 分ごとに読み直す（集まりしだい本物の版面に）
  }
  // 選んだものがまだないとき・設定の「外す」の画面（足すのは入口と同じ「ジャンル → 左右に払うカード → 確認」＝ ADD。ここは押して選ぶ・外す）
  function drawMine(box,p,err){
    box.dataset.ready='1';
    var name=(p&&p.name)||(me&&me.name)||(user&&user.email)||'', sh=isMail(name)?name.split('@')[0]:name;
    var picks=picksOf(p);
    var h='<header><h1>'+esc(sh)+' さんのページ</h1></header>';
    if(err){box.innerHTML=h+'<p class="wl-msg" role="alert">読み込めませんでした。ページを開き直してください。</p>';return;}
    if(!tok){box.innerHTML=h+'<p class="wl-msg" role="alert">もう一度ログインしてください。</p>';return;}
    if(page==='index'&&!picks.length){   // 最初：何ができるか＋選ぶ（左右に払うカードの流れ）へ
      box.innerHTML=h+'<div class="empty"><b>ここは、あなたが追いかけたいものの新しいニュースが毎日並ぶページです</b>'+
        '<p>好きなジャンルを選んで、出てくるカードを「気になる」か「パス」に分けるだけ。店長が集めに行き、記事が届いた版面から順に並びます。</p>'+
        '<a class="go" href="'+ADD+'">好きなものを選ぶ →</a></div>';return;}
    if(page!=='index'&&page!=='settings'){
      box.innerHTML=h+'<div class="empty">'+(picks.length?'<b>追いかけているものの記事は、トップにまとまっています</b><p>'+picks.length+' つを追いかけています。</p>':
        '<b>まだ何も追いかけていません</b><p>トップで追いかけたいものを選ぶと、記事が並びます。</p>')+'<a class="go" href="./">トップへ</a></div>';return;}
    var items=(A.items||[]), chosen={}, secsOn={};
    picks.forEach(function(x){chosen[x.name]=x.sec;secsOn[x.sec]=1;});
    // 設定の画面から自分のトップへ戻る道と、トップと同じ「カードで選んで足す」流れへの道（網址を打たせない・ブラウザの戻るに頼らない）
    var back=page==='settings'?'<p class="wl-back"><a href="./">← '+esc(sh)+' さんのページへ</a><a href="'+ADD+'">＋ カードで選んで足す</a></p>':'';
    function draw(){
      var t=h+back+'<h2>'+(picks.length?'追いかけるものを足す・外す':'好きなジャンルは？')+'</h2><p class="hint">押して選ぶ（いくつでも）。押してある札をもう一度押すと外れます。</p><div class="tiles secs">'+
        SECS.map(function(x){return '<button type="button" data-gsec="'+esc(x[0])+'" aria-pressed="'+(!!secsOn[x[0]])+'" style="--sc:'+esc(x[2]||'var(--ink)')+'">'+esc(x[1])+'</button>';}).join('')+'</div>';
      var keys=Object.keys(secsOn).filter(function(k){return secsOn[k];});
      if(keys.length){
        var cand=items.filter(function(x){return secsOn[x[1]];}).map(function(x){return x[0];});
        Object.keys(chosen).forEach(function(n){if(cand.indexOf(n)<0)cand.push(n);});
        t+='<h2>どれを追いかける？</h2><div class="tiles its">'+cand.map(function(n){var sec=chosen[n]||(items.filter(function(x){return x[0]===n;})[0]||[])[1]||keys[0];
            return '<button type="button" data-it="'+esc(n)+'" data-s="'+esc(sec)+'" aria-pressed="'+(n in chosen)+'" style="--sc:'+esc(secColor(sec)||'var(--ink)')+'">'+esc(n)+'<small>'+esc(secJa(sec))+'</small></button>';}).join('')+'</div>'+
          '<form class="add"><label for="wl-addn">ほかに追いかけたいもの</label><input id="wl-addn" name="n" maxlength="80" autocomplete="off" placeholder="作品・ブランド・人の名前">'+
          '<select name="s" aria-label="ジャンル">'+keys.map(function(k){return '<option value="'+esc(k)+'">'+esc(secJa(k))+'</option>';}).join('')+'</select><button type="submit" class="ghost">足す</button></form>';
      }
      var n=Object.keys(chosen).length;
      t+='<p class="wl-msg" role="status" aria-live="polite"></p><button type="button" class="save"'+(n?'':' disabled')+'>'+(n?n+' つで保存する':'ひとつ以上えらぶ')+'</button>';
      box.innerHTML=t;
      box.querySelectorAll('[data-gsec]').forEach(function(b){b.onclick=function(){secsOn[b.dataset.gsec]=!secsOn[b.dataset.gsec];draw();};});
      box.querySelectorAll('[data-it]').forEach(function(b){b.onclick=function(){var k=b.dataset.it;if(k in chosen)delete chosen[k];else chosen[k]=b.dataset.s;draw();};});
      var f=box.querySelector('form.add');
      if(f) f.onsubmit=function(ev){ev.preventDefault();var v=f.n.value.trim();if(!v)return;chosen[v]=f.s.value;draw();};
      var st=box.querySelector('.wl-msg'), sv=box.querySelector('.save');
      sv.onclick=function(){
        var list=Object.keys(chosen).map(function(k){return {name:k,sec:chosen[k]};});
        st.textContent='保存しています…';sv.disabled=true;
        rpc('my_keywords_set',{p_picks:list}).then(function(){
          if(page==='index'){p=p||{};p.prefs=p.prefs||{};p.prefs.picks=list;box.remove();showMine(p,list);scrollTo(0,0);}
          else{picks=list;st.innerHTML='保存しました（'+list.length+' つ）。<a href="./">ページで見る →</a>';sv.disabled=false;}
        }).catch(function(){st.textContent='保存できませんでした。もう一度お試しください。';sv.disabled=false;});};
    }
    draw();
  }
  function members(){
    var box=document.getElementById('wl-members'); if(!box) return;
    if(R.dataset.role!=='admin'){box.closest('section').hidden=true; return;}
    box.closest('section').hidden=false;
    if(!tok){ box.innerHTML='<p class="st">店長のメールとパスワードでログインすると、ここでお客さまを管理できます。</p>'; return; }
    // お客さま（テスト用を含む）の一覧：パスワードを変える。店長を足す（5 人まで）。退会の機能はいらない（2026-10-21，用户定的）
    Promise.all([rpc('admin_users'),rpc('admin_list_invites')]).then(function(v){
      var us=v[0]||[], inv=v[1]||[];
      box.innerHTML='<table><thead><tr><th>メールアドレス</th><th>種類</th><th>規約</th><th>最後に見た日</th><th></th></tr></thead><tbody>'+
        us.map(function(u){var shop=u.role==='admin';
          return '<tr data-mail="'+esc(u.email)+'"><td>'+esc(u.email)+'</td><td>'+(shop?'店長':u.is_test?'テスト用':'お客さま')+(u.has_password?'':'（パスワードなし）')+'</td>'+
            '<td>'+(u.agreed_version>=TV?'同意済み':'未同意')+'</td><td>'+esc(String(u.last_seen||'').slice(0,10))+'</td>'+
            '<td>'+(shop?'':'<button type="button" data-upw>パスワードを変える</button>')+'</td></tr>';}).join('')+
        '</tbody></table><p class="st" aria-live="polite"></p>'+
        '<form><input type="email" required placeholder="店長にする人のメールアドレス（5 人まで）" aria-label="メール"><button type="submit">店長にする</button></form>'+
        '<p class="st">店長：'+inv.filter(function(x){return x.role==='admin';}).map(function(x){return esc(x.email);}).join('、')+'</p>';
      var st=box.querySelector('.st');
      box.querySelectorAll('[data-upw]').forEach(function(b){ b.onclick=function(){ var m=b.closest('tr').dataset.mail;
        var p=prompt(m+' の新しいパスワード（4 文字以上）'); if(p===null) return;
        rpc('admin_user_password',{p_email:m,p_password:p}).then(function(){ st.textContent=m+' のパスワードを変えました'; }).catch(function(e){ st.textContent='できませんでした：'+e.message; }); }; });
      var f=box.querySelector('form');
      f.onsubmit=function(ev){ev.preventDefault();
        rpc('admin_invite',{p_email:f.querySelector('input').value,p_role:'admin'})
          .then(function(a){st.textContent=a+' を店長にしました。お客さまとして登録済みなら、そのパスワードでログインすると店長になります。';members();})
          .catch(function(e){st.textContent='できませんでした：'+e.message;});};
    }).catch(function(e){box.innerHTML='<p class="st">読み込めませんでした：'+esc(e.message)+'</p>';});
  }
  function refresh(){
    return Promise.all([rpc('auth_enforced'),tok?rpc('my_role'):Promise.resolve('guest'),rpc('can_edit',{p_account:window.WL_ACCOUNT||''})])
      .then(function(v){var r=v[1]||'guest'; if(r==='guest'&&me) r='user';
        R.dataset.enf=v[0]?'1':'0';R.dataset.role=r;R.dataset.lock=v[0]&&!v[2]&&!(OWN&&tok)?'1':'0';R.dataset.auth='ok';})
      .catch(function(){R.dataset.enf='1';R.dataset.lock='1';R.dataset.auth='err';})
      .then(function(){mine();chip();gate();readOnlyNote();members();
        if(/[?&]login=1/.test(location.search)&&!me){   // 入口の「ログイン」から来た：ログインの欄を開いておく
          var b=document.querySelector('.wl-auth>button.in'); if(b) b.click();
          if(history.replaceState) history.replaceState(null,'',location.pathname+location.hash);
        }});
  }
  function start(){
    if(me&&me.admin){ me.admin=false; saveMe(me); }   // メールの確認を待っていた人（前の仕組み）
    if(me&&me.name&&!me.admin) rpc('user_login',{p_name:me.name}).then(function(r){ if((r.agreed_version||0)<TV){ me.v=r.agreed_version||0; saveMe(me); askAgree(); } })
      .catch(function(e){ if(/見つかりません|登録されていません/.test(e.message)){ saveMe(null); refresh(); } });   // 退会した名前・消えた名前ならログアウト
    var q=new URLSearchParams(location.search+'&'+location.hash.replace(/^#/,'')), err=q.get('error_description');
    if(err){ toast(sayErr(err)); if(history.replaceState) history.replaceState(null,'',location.pathname); }
    if(!window.supabase){refresh();return;}
    sb=window.supabase.createClient(base,A.key,{auth:{flowType:'implicit',detectSessionInUrl:true,persistSession:true,storageKey:'wl-auth'}});
    sb.auth.onAuthStateChange(function(ev,s){
      var t=s&&s.access_token||null, changed=t!==tok; tok=t; user=s&&s.user||null; if(ev==='SIGNED_OUT')signedOut=true;
      if(changed||ev==='INITIAL_SESSION') setTimeout(refresh,0);   // Supabase の公式ドキュメント：コールバックの中で直接 Supabase を呼ぶと固まることがある → 後に回す
      if(ev==='SIGNED_IN'&&/access_token=|[?&]code=/.test(location.hash+location.search)) history.replaceState(null,'',location.pathname);
    });
  }
  function boot(){
    var s=document.createElement('script'); s.src=A.lib; s.async=true; s.onload=start; s.onerror=function(){refresh();};
    document.head.appendChild(s);
  }
  if(document.body) boot(); else document.addEventListener('DOMContentLoaded',boot);
})();
"""


AUTH_ITEMS = []   # [[名前, 板块]]


def _auth_tag(page=""):
    """どのページの <head> にも入れるログインの部品（AUTH_CSS・AUTH_JS）。AUTH_DB が空（テスト・手元）なら何も出さない。"""
    if not (AUTH_DB.get("url") and AUTH_DB.get("key")):
        return ""
    cfg = {"url": AUTH_DB["url"], "key": AUTH_DB["key"], "lib": SUPABASE_JS, "page": page,
           "terms": TERMS_VERSION, "termsUrl": "terms.html", "start": "../#name", "home": "../?stay",
           "secs": [[k, SECTION_JA.get(k, k), SECTIONS.get(k, "")] for k in list(SECTIONS) + ["其他"]],
           "items": AUTH_ITEMS}   # お客さまの選び方の候補（店長の関注項の名前と板块。digest.write_page が入れる）   # お客さま自分のページの大類   # 新しく始める = 入口（docs/index.html）の流れ
    js = (AUTH_JS.replace("__AUTH__", json.dumps(cfg)).replace("__ROLE__", json.dumps(ROLE_JA, ensure_ascii=False))
          .replace("__LOCK__", json.dumps(AUTH_LOCK)))
    js = js.replace("</", "<\\/")
    return f'<style>{AUTH_CSS}</style><script>{js}</script>'


def _live_head(page, ver=None):
    """<head> に入れる：自分の指紋（digest.write_page の stamp が VER_MARK を置き換える）と帯・印の CSS・アカウント。
    ver：version.json で見比べる名前（管理ページの 6 つは page="admin"〔ログインの門〕のまま、ver="admin-now" など）。"""
    return f'<meta name="wl-ver" data-page="{e(ver or page)}" content="{VER_MARK}"><style>{LIVE_CSS}</style>{_account_tag(page)}'


def stamp(html_, *volatile):
    """生成した HTML に指紋を入れて (html, 指紋) を返す。volatile（「更新 10.17 08:35」の時刻など）だけ違うときは同じ指紋。"""
    body = html_
    for v in volatile:
        body = body.replace(v, "") if v else body
    ver = hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]
    return html_.replace(VER_MARK, ver), ver


def _section_marks(html_, updated=""):
    """管理ページの各パネルに data-h（中身の指紋）を付ける。読み直したとき、変わったパネルに「更新」を出すため。
    パネルの中に <section> が入れ子になる（全体の構成図）ので、次のパネルの始まりまでを 1 つと数える。"""
    parts = re.split(r'(?=<section class="panel[^"]*" id="[^"]+">)', html_)
    out = []
    for part in parts:
        m = re.match(r'<section class="panel([^"]*)" id="([^"]+)">', part)
        if m:
            h = hashlib.sha1((part.replace(updated, "") if updated else part).encode("utf-8")).hexdigest()[:8]
            part = f'<section class="panel{m.group(1)}" id="{m.group(2)}" data-h="{h}">' + part[m.end():]
        out.append(part)
    return "".join(out)


BOARD_LABEL = {"front": "トップ", "picks": "気になるかも？", "wishlist": "愿望清单"}


def _board_hash(part):
    """版面の「中身の指紋」：**AI 編集が整理した記事（<article>）だけ**を見る。
    整理待ち（<details class="pend">）・話題度の数字・小元素・帯などが変わっても、版面が更新されたことにはしない
    （まだ AI が整理していない新着は、読者に見せる更新ではないから）。記事が 1 本もない版面は一定の指紋。"""
    body = re.sub(r'<details class="pend">.*?</details>', "", part, flags=re.S)
    arts = re.findall(r'<article\b.*?</article>', body, flags=re.S)
    return hashlib.sha1("".join(arts).encode("utf-8")).hexdigest()[:8]


def _board_marks(html_, updated=""):
    """簡報の各版面・トップ・気になるかも（data-k を持つ <section>）に data-h（AI 編集した記事の指紋）を付ける。
    開いたままのページが「どの版面が変わったか」を読み直す前から言えるように（version.json の *_marks と見比べる）。"""
    parts = re.split(r'(?=<section\b[^>]*\bdata-k=")', html_)
    out = []
    for part in parts:
        m = re.match(r'<section\b[^>]*\bdata-k="', part)
        if m and 'id="' in part[:part.index(">")]:
            part = f'<section data-h="{_board_hash(part)}"' + part[len("<section"):]
        out.append(part)
    return "".join(out)


def page_marks(html_):
    """生成した HTML の {版面・パネルの id: [表示名, 指紋]}。docs/version.json の <ページ>_marks に入れる。
    ページ側（LIVE_JS）は、自分の data-h と見比べて「どの版面が変わったか」を新着の通知に出す。"""
    out = {}
    for m in re.finditer(r'<section\b([^>]*)>', html_):
        attrs = m.group(1)
        i, h = re.search(r'\bid="([^"]+)"', attrs), re.search(r'\bdata-h="(\w+)"', attrs)
        if not (i and h):
            continue
        k = re.search(r'\bdata-k="([^"]*)"', attrs)
        name = BOARD_LABEL.get(k.group(1)) if k and k.group(1) in BOARD_LABEL else (html.unescape(k.group(1)) if k else None)
        if not name:  # 管理ページのパネル：見出しの文字
            t = re.search(r'<h2 class="sh"><span>([^<]+)</span>', html_[m.end():m.end() + 400])
            name = html.unescape(t.group(1)) if t else i.group(1)
        out[i.group(1)] = [name, h.group(1)]
    return out


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


TERMS_VERSION = 3          # 利用規約・プライバシーポリシーの版。中身を変えたら上げる → ログインしている人にもう一度同意を聞く（AUTH_JS の askAgree）
TERMS_DATE = "2026年10月21日"
TERMS_CONTACT = ""         # 開示・訂正・削除の請求の連絡先（運営者が決める。空なら「サイト内でお知らせします」）
TERMS_PAGE_CSS = """
.page{display:flex;flex-direction:column;gap:18px;max-width:820px}
.back{display:inline-flex;align-items:center;gap:8px;font:700 12px var(--font-mono);letter-spacing:.12em}.back:hover{color:var(--rose)}
.terms{background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);padding:22px 26px;line-height:1.85;font-size:15px}
.terms h2{margin:26px 0 8px;font:900 18px/1.4 var(--font-sans);border-left:6px solid var(--rose);padding-left:10px}
.terms h2:first-child{margin-top:0}
.terms ul,.terms ol{margin:6px 0;padding-left:1.4em}
.terms li{margin:3px 0}
.terms .note{background:var(--sheet);border:2px dashed var(--ink);padding:10px 14px;margin:10px 0}
.terms small{opacity:.8}
"""


def render_me():
    """お客さまの本人のページを読み込む殻（docs/home/me.html）。ほかの JS を持たない窓で、ログインした本人の鍵で
    Supabase Storage pages/<account>/index.html を読み、そのページに替える（scripts/user_pages.py が作ったもの、店長と同じ枠組み）。
    ログインしていない → 店長のページへ。読めない（まだ作られていない・つながらない）→ 店長のページの前の画面（?own=0）。"""
    cfg = json.dumps({"url": AUTH_DB.get("url") or "", "key": AUTH_DB.get("key") or "", "lib": SUPABASE_JS})
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>ウォッチリスト通信</title>
<style>{re.search(r":root\{[^}]*\}", CSS).group(0)}html,body{{margin:0;background:var(--paper);color:var(--ink);font:700 14px/1.6 var(--font-sans)}}
.ld{{position:fixed;inset:0;display:grid;place-items:center}}.ld b{{background:var(--ink);color:var(--card);padding:.5em 1em;transform:rotate(-2deg);box-shadow:4px 4px 0 var(--rose)}}</style>
</head><body><div class="ld" role="status"><b>読み込み中…</b></div>
<script>
(function(){{
  var C={cfg};
  var SET=/[?&]p=settings/.test(location.search), PG=SET?'settings.html':'index.html';   // どのページか（AUTH_JS の ownPage）
  function back(q){{location.replace('./'+(SET?'settings.html':'')+(q||'')+location.hash);}}
  var s=document.createElement('script');s.src=C.lib;s.onerror=function(){{back('?own=0');}};
  s.onload=function(){{
    var sb=window.supabase.createClient(C.url,C.key,{{auth:{{persistSession:true,storageKey:'wl-auth',detectSessionInUrl:false}}}});
    sb.auth.getSession().then(function(r){{
      var se=r&&r.data&&r.data.session;if(!se){{back('');return null;}}
      return sb.rpc('my_page_path').then(function(p){{
        if(p.error||!p.data){{back('?own=0');return null;}}
        return sb.storage.from('pages').download(p.data+'/'+PG);
      }});
    }}).then(function(d){{
      if(!d)return;
      if(d.error||!d.data){{back('?own=0');return;}}
      return d.data.text().then(function(h){{
        if(h.indexOf('name="wl-own"')<0){{back('?own=0');return;}}
        document.open();document.write(h);document.close();
        try{{history.replaceState(null,'','./'+(SET?'settings.html':'')+location.hash);}}catch(_){{}}
      }});
    }}).catch(function(){{back('?own=0');}});
  }};
  document.head.appendChild(s);
}})();
</script></body></html>"""


def render_terms(updated=""):
    """利用規約・プライバシーポリシー（docs/<account>/terms.html）。新しく始めるときに同意してもらう（AUTH_JS）。
    関心のある作品・投票は「興味・関心の情報」＝ メールアドレスと結びつくと個人情報（個人情報保護法）なので、集めるもの・使い道・預け先を書く。"""
    contact = (f'<a href="mailto:{e(TERMS_CONTACT)}">{e(TERMS_CONTACT)}</a>' if TERMS_CONTACT
               else "このサイト内でお知らせします")
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>利用規約・プライバシーポリシー</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}{TERMS_PAGE_CSS}</style>
{_account_tag("terms")}
</head>
<body>
<div class="page">
<header class="mast"><div class="mtitle"><h1>利用規約・プライバシーポリシー</h1><span class="stamp">ウォッチリスト通信 · 第 {TERMS_VERSION} 版</span></div>
<div class="tools"><div class="meta"><small>制定</small><b>{e(TERMS_DATE)}</b></div></div></header>
<a class="back" href="./">← ウォッチリスト通信に戻る</a>
<article class="terms">
<p>「ウォッチリスト通信」（以下「本サービス」）は、運営者（以下「店長」）が気になる作品・グッズ・ニュースを集めて見せるサイトです。
「新しく始める」で同意したときから、この規約とプライバシーポリシーが適用されます。</p>
<div class="note"><b>大事なこと：</b>ログインはメールアドレスとパスワードです。パスワードを忘れたときの再発行はありません（メールを送らないため）。ほかのサービスと同じパスワードは使わないでください。
人に知られて困る情報（本名・住所・電話番号など）は入力欄に書かないでください。</div>

<h2>1. 集める情報</h2>
<ul>
<li><b>メールアドレスとパスワード</b>（ログインに使います。パスワードは元に戻せない形（bcrypt）にして保存し、だれも読めません。お知らせ・広告のメールは送りません）</li>
<li><b>同意の記録</b>：同意した規約の版と日時、最後に使った日時</li>
<li><b>興味・関心の情報</b>：フォローした作品、👍 / 👎、欲しい物リスト、設定など、本サービスで操作した内容</li>
<li><b>好みの設定</b>：ニュースの言語、好きなジャンル、はじめに「気になる」を選んだ作品</li>
<li><b>ブラウザに保存するもの</b>：ログインしたままにするため、メールアドレスをこのブラウザの保存領域（localStorage）に置きます。Cookie による広告・追跡はしません</li>
</ul>

<h2>2. 使い道</h2>
<ul>
<li>ログインしたままにする・ページを表示する</li>
<li>関心に合わせて記事やおすすめ（店長のおすすめ）を選ぶ</li>
<li>本サービスの不具合を直す・改善する</li>
</ul>
<p>これ以外の目的には使いません。広告のために使ったり、売ったりしません。</p>

<h2>3. 第三者への提供・預け先</h2>
<p>法令にもとづく場合を除き、本人の同意なく第三者に提供しません。本サービスを動かすため、次の会社のサービスを使っています（情報の管理を預けています）。</p>
<ul>
<li><b>Supabase, Inc.</b>（米国の会社）：メールアドレス・同意の記録・関心の情報の保存。データはオーストラリア（シドニー）のサーバーにあります</li>
<li><b>GitHub, Inc.</b>（米国）：ページの公開。店長のページはだれでも見られます。メールアドレスは公開のページに載せません</li>
<li><b>Anthropic, PBC</b>（米国）：ニュース記事の整理（AI）。記事の内容だけを送り、メールアドレスは送りません</li>
<li>ページを表示するため、Google Fonts（文字）・jsDelivr（プログラム）からファイルを読み込みます。その際、お使いの端末の IP アドレスなどがそれぞれの会社に届きます</li>
</ul>
<p>外国（米国・オーストラリア）にある会社に預けることになります。各社はそれぞれの国の法令と自社の方針にもとづいて情報を守っています。</p>

<h2>4. 保存する期間</h2>
<p>サービスを続けている間は保存します。消してほしいときは店長に伝えてください。メールアドレスと同意の記録・関心の情報を消します。</p>

<h2>5. 開示・訂正・削除などのご請求</h2>
<p>ご自身の情報の開示・訂正・利用停止・削除を求めることができます。連絡先：{contact}</p>

<h2>6. 禁止すること</h2>
<ul>
<li>ほかの人のメールアドレスを使ってログインすること</li>
<li>本サービスや他の利用者に迷惑をかけること、不正にアクセスすること</li>
<li>法令や公序良俗に反すること</li>
</ul>

<h2>7. 記事・リンクについて</h2>
<p>記事は外部のサイトの見出し・要約と、そのサイトへのリンクです。内容の正しさは保証できません。リンク先のサイトの内容には責任を負いません。
著作権は各サイト・権利者にあります。</p>

<h2>8. 未成年の方</h2>
<p>16 歳未満の方は、保護者の同意を得てから使ってください。</p>

<h2>9. 変更</h2>
<p>この内容を変えるときは版を上げ、ログイン中の方にもう一度同意をお願いします。同意しない場合はログアウトして、見るだけでお使いいただけます。</p>

<h2>10. 準拠法</h2>
<p>日本の法律にもとづきます。</p>
<p><small>第 {TERMS_VERSION} 版 · {e(TERMS_DATE)} 制定</small></p>
</article>
</div>
</body>
</html>
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
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}{THEMES_PAGE_CSS}</style>
{LIKEFX_HEAD}{_account_tag("themes")}
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
    return _section_marks(f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>話題度アナリシス</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}</style>
{_live_head("heat")}
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
<script>{LIVE_JS}</script>
</body>
</html>
""", updated)


# ---------- 管理ページ（docs/admin.html）：見るだけ。口令なし・ボタンで何かを変えることはしない ----------
# 生成時に分かるもの（収集・編集の状況、作品ごとの記事数、投票）は HTML に書き込み、
# その場で変わるもの（GitHub Actions の実行結果、設定ページの依頼、写真の受付）はページを開いたときに読む。
ADMIN_WORKFLOWS = {"digest.yml": "収集・出刊", "background.yml": "後台作業（ゲート・小元素）", "render.yml": "ページの再生成", "requests.yml": "設定ページの依頼", "ci.yml": "テスト"}
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
RUN_JOBS = {"gate": "background", "collect": "collect", "render": "render", "edit": "edit_now"}   # 「今すぐ実行」で起こせる仕組み → db/run_now.sql の job
RUN_TITLE = {"gate": "小元素の補完を今すぐ。失敗した版面も待たずにやり直す・作業は上のライブログに流れる（3 分に 1 回まで）",
             "collect": "ニュース収集を今すぐ（10 分に 1 回まで）", "render": "網页を今すぐ作り直す（1 分に 1 回まで）",
             "edit": "9:00・18:00 を待たずに、整理待ちがあれば AI 編集を今すぐ起こす（10 分に 1 回まで）"}
EDIT_STATE = {"running": ("編集中のはず", "ok"), "progress": ("進んでいる", "ok"), "idle": ("次の回を待つ", "ok"),
              "unpublished": ("出刊されていない", "ng"), "stalled": ("止まっている？", "ng"),
              "gave_up": ("起こしても動かない", "ng")}
EDIT_WHY_MAX = 24   # 管理ページの AI 編集の列の見出しに出す理由の字数（表が 1400px で右にはみ出さないように）
RUN_LABEL = {"edit": "今すぐ AI 整理"}   # ボタンの文字（ないものは「今すぐ実行」）
BG_ON_EVENT = {"render": "main に push されたとき", "requests": "設定ページから依頼が来たとき"}


def _slots_attr(pid):
    p = next((x for x in processes.PROCESSES if x["id"] == pid), None)
    return e(json.dumps(processes.slots(p))) if p else "[]"


BG_THUMBS = 10   # 表の行に並べる小元素の数。残りは「+N」、全部は「小元素の探し方」を開くと見える
BG_AFTER_COLLECT = ("design",)   # 定時のない列：ゲートが収集のあとに AI 編集を起こす


def _bg_thumb(t):
    """小元素 1 枚（表の行の小さい丸・「小元素の探し方」の中）。押して操作するのは管理ページ「小元素」の欄（_admin_emm）。"""
    u, sh, subj = (list(t) + ["", ""])[:3] if isinstance(t, (list, tuple)) else (t, "", "")
    return f'<img src="{e(u)}" alt="{e(subj)}" loading="lazy"{" class=fit" if sh in ("logo", "icon") else ""}>'


def _bg_retry(k, r):
    """失敗した小元素の格子：自動の再挑戦までの残り時間と「今すぐ再挑戦」ボタン（run_now('background') = retry_now つきの後台作業。
    失敗した版面は待たずにやり直す。作業の 1 行 1 行はライブログに流れる。3 分に 1 回まで）。ほかの格子は空。"""
    if k != "emblem" or r["bg"][k]["state"] != "failed":
        return ""
    at = (r["bg"][k].get("detail") or {}).get("next_at") or ""
    cd = f'<small class="bg-cd" data-at="{e(at)}"></small>' if at else ""
    return (f'{cd}<span class="nx-go"><button type="button" class="nx-run bg-redo" data-run="{RUN_JOBS["gate"]}" data-label="今すぐ再挑戦"'
            f' title="失敗した版面を待たずにやり直す（後台作業を今すぐ。作業はページ上のライブログに流れる。3 分に 1 回まで）">今すぐ再挑戦</button>'
            f'<small class="nx-msg" aria-live="polite"></small></span>')


def _admin_backend(rows, todo=None, log=None, res=None):
    """バックグラウンド：裏で動く仕組みの「次の実行」（前回・次回・残り時間はページを開いた端末で計算）と、
    版面（行）× プロセス（列）の今の状態の表。何が待っていて、次にいつ動くかを一目で見る。
    管理ページが 6 つに分かれたので 3 つに分けて返す：now（①いま）・table（③エンブレム）・sys（⑤しくみ）。"""
    cards, plan = [], []
    for p in processes.PROCESSES:
        sl = processes.slots(p)
        if isinstance(p.get("schedule"), str) or not (sl or p.get("workflow") or p["id"] in BG_ON_EVENT):
            continue   # 別のプロセスと同じ回に動くもの（小元素の選定＝AI 編集）は出さない
        when = (f'<b class="nx-t">--:--</b><small class="nx-l"></small><small class="nx-p"></small>' if sl
                else f'<b class="nx-t ev">{e(BG_ON_EVENT.get(p["id"], "必要なとき"))}</b>')
        wf = f' data-wf="{e(p["workflow"])}"' if p.get("workflow") else ""
        td = (todo or {}).get(p["id"]) or {}
        # 今の回（18:00 など）をまだ起こしていない：カードも列の見出しと同じく次の日の 9:00 を数えず「まもなく」（JS の tick が data-due を見る）
        due = f' data-due="{e(td["due"])}"' if p["id"] == "edit" and td.get("due") else ""
        cards.append(f'<li class="nx" data-slots="{e(json.dumps(sl))}"{wf}{due}>'
                     f'<button type="button" class="nx-n" data-open="proc-{e(p["id"])}">{e(p["name"])}</button>{when}'
                     + ('<span class="pbar" aria-hidden="true"><i></i></span>' if sl
                        else '<span class="pbar ev" aria-hidden="true"><i></i></span>')   # 定時でないものは実行中だけ出す
                     + (f'<small class="nx-do">{e(td["text"])}</small>' if td.get("text") else "")
                     + (f'<span class="nx-go"><button type="button" class="nx-run" data-run="{RUN_JOBS[p["id"]]}"'
                        f' data-label="{e(RUN_LABEL.get(p["id"], "今すぐ実行"))}" title="{e(RUN_TITLE.get(p["id"], "定時を待たずに今すぐ動かす"))}">{e(RUN_LABEL.get(p["id"], "今すぐ実行"))}</button>'
                        f'<small class="nx-msg" aria-live="polite"></small></span>' if p["id"] in RUN_JOBS else "")
                     + f'<span class="lv">{_lane_short(p["lane"])}</span></li>')
        if sl:
            plan.append({"id": p["id"], "name": p["name"], "slots": sl, "text": td.get("text", ""), "items": td.get("items", [])[:12]})
    rows = [r for r in rows if r.get("bg")]
    cfg = json.dumps(plan, ensure_ascii=False).replace("</", "<\\/")
    now = ('<h3 class="h3">いま動いているもの <small>裏で処理中の版面と段 · 30 秒ごとに読み直す</small></h3>'
           '<div id="livenow" class="livenow"><p class="empty">読み込み中…</p></div>'
           f'<h3 class="h3">次の実行 <small>近い順 · 時刻は日本時間 · バーは前回から次回までの経過 · 名前をクリックで流れ</small></h3>'
           f'<ol class="nxs">{"".join(cards)}</ol>'
           '<div class="two bgtwo"><div><h3 class="h3">待ち行列 <small>これから 24 時間の実行と、そのとき処理するもの</small></h3>'
           '<ol class="bgq" id="bgq"><li class="empty">計算中…</li></ol></div>'
           '<div><h3 class="h3">ログ <small>このページの一番上の「ライブログ」に移しました（自動で流れる）</small></h3>'
           '<p class="empty"><a href="#term-panel">↑ ライブログを見る</a></p></div></div>'
           f'<script type="application/json" id="bg-cfg">{cfg}</script>')
    sys_ = ('<h3 class="h3">リソース <small>サーバーの残り · 容量 · トークン</small></h3>' + _admin_resources(res) +
            '<h3 class="h3">AI を使うか <small>前に AI でやっていた判断ごとに · 規則にできたものは AI なし（トークン 0）</small></h3>'
            '<ul class="aiu">' + "".join(f'<li class="aiu-{k}"><span class="aiu-s">{e(processes.AI_STATE_JA[k])}</span><b>{e(t)}</b><small>{e(why)}</small></li>'
                                         for t, k, why in processes.AI_TASKS) + '</ul>'
            '<h3 class="h3">並列と制限 <small>同時にいくつ動かすか · それ以上速くできない理由</small></h3>'
            '<ul class="lims">' + "".join(f'<li><b>{e(a)}</b><span class="lim-n">{e(b)}</span><small>{e(c)}</small></li>'
                                          for a, b, c in processes.LIMITS) + '</ul>')
    if not rows:
        return {"now": now, "sys": sys_, "manage": _admin_emm([]), "table": '<p class="empty">データがありません。</p>'}
    order = list(SECTIONS) + ["其他"]
    rows = sorted(rows, key=lambda r: (order.index(r.get("section")) if r.get("section") in order else len(order),
                                       r.get("section") or "", r["name"]))
    waits = {k: sum(1 for r in rows if r["bg"][k]["state"] in ("wait", "review", "failed")) for k, _, _ in BG_COLS}
    ed = (todo or {}).get("edit") or {}

    def th(k, t, pid):
        if k in BG_AFTER_COLLECT:   # 定時なし：ゲートが収集のあとに起こす（AI 編集・版面の設計）→ 次の収集までの残り時間
            when = f'<small class="nx-h" data-slots="{_slots_attr("collect")}" data-pre="次の収集のあと "></small>'
        elif k == "edit" and ed.get("due"):   # 今の回をまだ起こしていない（cron の遅れ）：次の日の 9:00 を数えない
            when = f'<small class="nx-h">{e(ed["due"])} の回はまもなく（次のゲートで起こす）</small>'
        else:
            when = f'<small class="nx-h" data-slots="{_slots_attr(pid)}"></small>'
        extra = ""
        if k == "edit":
            if ed.get("n"):
                extra += f'<small class="bgw-d">記事 {ed["n"]} 件が版面の下の「整理待ち」に</small>'
            if ed.get("fired"):
                extra += f'<small class="bgw-d nx-ago" data-at="{e(ed["fired"])}"></small>'
            lab, cls = EDIT_STATE.get(ed.get("state"), ("", ""))
            if lab:   # 列の見出しは nowrap：長い理由（出刊されていない・失敗の文）は短く切り、全文は title と「いま待っているもの」に
                why = ed.get("why") or ""
                short = why if len(why) <= EDIT_WHY_MAX else why[:EDIT_WHY_MAX - 1] + "…"
                extra += (f'<small class="bgw-d es-{cls}" title="{e(why)}"><b>{e(lab)}</b> {e(short)}'
                          + (f'（{ed["attempts"]} 回目）' if ed.get("attempts", 0) > 1 else "") + '</small>')
            if ed.get("n"):   # 動いていなくても人が押せる：間隔・停滞の判断を飛ばして起こす
                extra += (f'<span class="nx-go"><button type="button" class="nx-run bg-redo" data-run="{RUN_JOBS["edit"]}" data-label="AI 編集をもう一度起こす"'
                          f' title="{e(RUN_TITLE["edit"])}">AI 編集をもう一度起こす</button><small class="nx-msg" aria-live="polite"></small></span>')
        return f'<th><span>{e(t)}</span>{when}<small class="bgw">待ち {waits[k]}{" 版面" if k == "edit" else ""}</small>{extra}</th>'
    head = "".join(th(k, t, pid) for k, t, pid in BG_COLS)
    body, sec = [], None
    for r in rows:
        if r.get("section") != sec:
            sec = r.get("section")
            body.append(f'<tr class="bgs"><th colspan="{len(BG_COLS) + 1}"><i style="background:{_sec_color(sec or "其他")}"></i>'
                        f'{e(_sec_name(sec or "其他"))}</th></tr>')
        cells = "".join(f'<td class="bgc s-{r["bg"][k]["state"]}" data-label="{e(t)}"><b>{BG_STATES[r["bg"][k]["state"]]}</b>'
                        f'<small>{e(r["bg"][k]["text"])}</small>{_bg_retry(k, r)}</td>' for k, t, _ in BG_COLS)
        pics = [_bg_thumb(t) for t in r.get("thumbs") or []]
        more = f'<small class="bg-more">+{len(pics) - BG_THUMBS}</small>' if len(pics) > BG_THUMBS else ""
        body.append(f'<tr><td class="nm"><a href="index.html#{_wid(r["name"])}">{e(r["name"])}</a>'
                    + (f'<span class="bg-th">{"".join(pics[:BG_THUMBS])}{more}</span>' if pics else "") + f'</td>{cells}</tr>')
        d = r["bg"]["emblem"].get("detail")
        if d:
            body.append(f'<tr class="bgx"><td colspan="{len(BG_COLS) + 1}">{_emblem_flow(d, r["bg"]["emblem"]["state"], pics)}</td></tr>')
    return {"now": now, "sys": sys_,
            "table": ('<h3 class="h3">版面ごとの状態 <small>済 = 終わった · 待ち = 次の回で動く · 要確認 = AI が目で選ぶ · 失敗 = 時間をおいて再挑戦</small></h3>'
                      f'<div class="tw"><table class="adm bgm"><thead><tr><th>版面</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
                      + _admin_emx_stats(rows)),
            "manage": _admin_emm(rows)}


# 小元素の管理（2026-10-25，用户定的）：管理ページの専用の欄。版面を選ぶと大きい写真＋名前＋取り方。押すと「どうしたい？」：
# 🔄 同じ人の別の写真に替える（_emblem_swap：今の写真は emblem_reject・人は emblem_redo に残す）／📌 この写真で固定（_emblem_lock：lock: true）／
# ✕ この人ごと外す（_emblem_reject：理由 1 つ必須）。下の帯でまとめて submit_item の edit に送る → requests.yml の take-items が digest.take_item_requests で items.yaml へ。
def _admin_emm(rows):
    """「小元素」の欄：版面のボタン → その版面の小元素を大きく並べる（押すと EMM_JS の「どうしたい？」の札）。"""
    import emblem_rules
    rows = [r for r in rows if r.get("emblems")]
    if not rows:
        return '<p class="empty">小元素のある版面がありません。</p>'
    btns, boards = [], []
    for n, r in enumerate(rows):
        em = r["emblems"]
        d = (r.get("bg") or {}).get("emblem", {}).get("detail") or {}
        btns.append(f'<button type="button" class="emm-bt" data-bi="{n}" data-n="{e(r["name"])}" aria-pressed="{"true" if n == 0 else "false"}">{e(r["name"])}<small>{len(em)}</small></button>')
        tiles = "".join(
            f'<button type="button" class="emm-tile" data-b="{e(r["name"])}" data-img="{e(x["image"])}" data-lock="{1 if x["lock"] else 0}"'
            f' data-subj="{e(x["subject"])}" data-why="{e(x["why"])}" aria-haspopup="dialog">'
            f'<span class="emm-ph"><img src="{e(x["image"])}" alt="" loading="lazy"></span>'
            f'<b>{e(x["subject"] or "小元素")}</b><small>{e(x["why"])}</small></button>' for x in em)
        boards.append(f'<div class="emm-board" data-bi="{n}"{"" if n == 0 else " hidden"}><p class="emm-h"><b>{e(r["name"])}</b>'
                      f'<span>{e(d.get("kind") or "")} · 今 {len(em)} / 目標 {d.get("target") or "?"} 枚 · 押すと「どうしたい？」</span></p>'
                      f'<div class="emm-grid">{tiles}</div></div>')
    opts = "".join(f'<button type="button" aria-pressed="false" data-r="{e(k)}">{e(t)}</button>' for k, t, _ in emblem_rules.REJECT_REASONS)
    sheet = ('<div class="emm-sheet" id="emm-sheet" role="dialog" aria-modal="false" aria-labelledby="emm-name" hidden>'
             '<div class="emm-sh"><span class="emm-ph"><img id="emm-img" alt=""></span><div><b id="emm-name"></b><small id="emm-why"></small></div></div>'
             '<div class="emm-acts">'
             '<button type="button" class="emm-act" data-a="swap" aria-expanded="false"><i>🔄</i><b>同じ人の別の写真に替える</b>'
             '<span>この人はそのまま、写真だけ取り直す。今の写真は二度と選ばない。次の後台作業（1 時間以内）で別の写真になる</span></button>'
             f'<div class="emm-more" data-for="swap" hidden><h3>今の写真のどこがだめ？（任意・今後の規則の手がかり）</h3><div class="emm-chips" data-chips="swap">{opts}</div>'
             '<input type="text" class="emm-note" maxlength="200" placeholder="ひとこと（任意）" aria-label="ひとこと（任意）">'
             '<button type="button" class="emm-go" data-go="swap">替える依頼に入れる</button></div>'
             '<button type="button" class="emm-act" data-a="lock" aria-expanded="false"><i>📌</i><b id="emm-lock-t">この写真で固定</b>'
             '<span id="emm-lock-d">自動の補完・規則の作り直し・検査でも替えない</span></button>'
             '<div class="emm-more" data-for="lock" hidden><button type="button" class="emm-go" data-go="lock" id="emm-lock-go">固定する</button></div>'
             '<button type="button" class="emm-act" data-a="drop" aria-expanded="false"><i>✕</i><b>この人ごと外す</b>'
             '<span>別人・作品と関係ない・重複のとき。空いた枠は別の人で埋める</span></button>'
             f'<div class="emm-more" data-for="drop" hidden><h3>なぜ？（ひとつ選ぶ）</h3><div class="emm-chips" data-chips="drop">{opts}</div>'
             '<input type="text" class="emm-note" maxlength="200" placeholder="ひとこと（任意）：だれが写っている・どこがだめ" aria-label="ひとこと（任意）">'
             '<button type="button" class="emm-go" data-go="drop" disabled>外す依頼に入れる</button></div>'
             '</div><button type="button" class="emm-x" id="emm-close">閉じる</button></div>'
             '<div class="emm-bar" id="emm-bar" role="region" aria-label="小元素の依頼" hidden><b id="emm-n"></b>'
             '<button type="button" id="emm-go">送る</button><button type="button" id="emm-clr">全部取り消す</button>'
             '<small id="emm-msg" aria-live="polite"></small></div>')
    return (f'<div class="emm-boards" role="group" aria-label="版面">{"".join(btns)}</div>{"".join(boards)}{sheet}')


def _admin_emx_stats(rows):
    """「違う」の理由：管理ページで外した小元素（state/emblem_rejects.json）を理由ごとに数え、多い取り方・網域・近い判断を並べる。
    同じ理由・同じ取り方が溜まったら、その判断を締める（規則がまだない理由は emblem_rules.rules() に 1 行足す）。"""
    import emblem_rules
    from collections import Counter
    log = [x for r in rows for x in ((r.get("bg") or {}).get("emblem", {}).get("detail") or {}).get("reject_log") or []]
    head = ('<h3 class="h3">「違う」の理由 <small>管理ページで外した小元素 · 同じ理由・同じ取り方が溜まったら、近い判断を締める（今後の規則の手がかり）</small></h3>')
    if not log:
        return head + '<p class="empty">まだありません。上の表の小元素を押すと、理由を選んで外せます。</p>'
    label = {k: t for k, t, _ in emblem_rules.REJECT_REASONS}
    rule = {k: r for k, _, r in emblem_rules.REJECT_REASONS}
    by = Counter(x.get("reason") for x in log)
    trs = []
    for k, n in by.most_common():
        xs = [x for x in log if x.get("reason") == k]
        top = lambda f: "、".join(f"{v} ×{c}" for v, c in Counter(f(x) for x in xs if f(x)).most_common(2)) or "—"
        trs.append(f'<tr><td><b>{e(label.get(k, k))}</b></td><td class="n">{n}</td>'
                   f'<td>{e(top(lambda x: (x.get("why") or "")[:28]))}</td><td>{e(top(lambda x: x.get("host")))}</td>'
                   f'<td>{e(top(lambda x: x.get("kind")))}</td>'
                   f'<td>{e(rule.get(k) or "まだ規則なし → emblem_rules に足す")}</td></tr>')
    recent = "".join(f'<li><b>{e(x.get("board"))}</b> {e(x.get("subject"))} · {e(label.get(x.get("reason"), x.get("reason")))}'
                     + (f' · 「{e(x["note"])}」' if x.get("note") else "") + f'<small>{e((x.get("at") or "")[:10])}</small></li>'
                     for x in sorted(log, key=lambda x: x.get("at") or "", reverse=True)[:8])
    return (head + '<div class="tw"><table class="adm emxs"><thead><tr><th>理由</th><th>枚数</th><th>多い取り方（why）</th><th>多い網域</th>'
            '<th>種類</th><th>近い判断（締める先）</th></tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
            f'<ul class="emx-recent">{recent}</ul>')


EMM_JS = r"""
(function(){
  var sheet=document.getElementById('emm-sheet');if(!sheet)return;
  var CFG=JSON.parse((document.getElementById('adm-cfg')||{}).textContent||'{}'),$=function(id){return document.getElementById(id);};
  var KEY='wl-emm-'+(window.WL_ACCOUNT||''),sent={},req={},cur=null,anchor=null;   // req[版面|画像] = {a,reason,note,board,img}。送った印はこのブラウザが 6 時間覚える
  try{sent=JSON.parse(localStorage.getItem(KEY)||'{}')||{};}catch(e){}
  Object.keys(sent).forEach(function(k){if(Date.now()-sent[k]>21600000)delete sent[k];});
  var AL={swap:'替える',lock:'固定',unlock:'固定をはずす',drop:'外す'},RL={};
  [].forEach.call(sheet.querySelectorAll('[data-chips=drop] [data-r]'),function(b){RL[b.dataset.r]=b.textContent;});
  function key(t){return t.dataset.b+'|'+t.dataset.img;}
  var lib={};   // お客さまの版面（ライブラリ）：名前 → 版面の id。店長（管理者）でログインしているときだけ読める（RLS）
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
  function addLib(rows){
    var bts=document.querySelector('.emm-boards');if(!bts||!rows||!rows.length)return;
    var shop={};[].forEach.call(bts.querySelectorAll('[data-n]'),function(b){shop[b.dataset.n]=1;});
    var host=bts.parentNode,sh=document.getElementById('emm-sheet'),n=0;
    rows.forEach(function(r){
      var em=((r.config||{}).emblem||[]).filter(function(x){return x&&/^https?:/.test(x.image||'');});
      if(shop[r.name]||!em.length)return;
      lib[r.name]=r.id;var bi='L'+r.id;n++;
      var b=document.createElement('button');b.type='button';b.className='emm-bt';b.dataset.bi=bi;b.dataset.n=r.name;b.setAttribute('aria-pressed','false');
      b.innerHTML=esc(r.name)+'<small>'+em.length+'</small>';bts.appendChild(b);
      var d=document.createElement('div');d.className='emm-board';d.dataset.bi=bi;d.hidden=true;
      d.innerHTML='<p class="emm-h"><b>'+esc(r.name)+'</b><span>お客さまの版面（ライブラリ） · 今 '+em.length+' 枚 · 押すと「どうしたい？」</span></p><div class="emm-grid">'+
        '</div>';
      var g=d.querySelector('.emm-grid');
      em.forEach(function(x){var tl=document.createElement('button');tl.type='button';tl.className='emm-tile';tl.dataset.b=r.name;tl.dataset.img=x.image;tl.dataset.lock=x.lock?'1':'0';
        tl.dataset.subj=x.subject||'';tl.dataset.why=x.why||'';tl.setAttribute('aria-haspopup','dialog');
        tl.innerHTML='<span class="emm-ph"><img alt="" loading="lazy"></span><b></b><small></small>';
        tl.querySelector('img').src=x.image;tl.querySelector('b').textContent=x.subject||'小元素';tl.querySelector('small').textContent=x.why||'';g.appendChild(tl);});
      host.insertBefore(d,sh);});
    if(n)paint();}
  if(CFG.url&&window.fetch)fetch(CFG.url.replace(/\/$/,'')+'/rest/v1/boards?followers=gt.0&select=id,name,config&order=id',{headers:{apikey:CFG.key}})
    .then(function(r){return r.ok?r.json():[];}).then(addLib,function(){});
  function paint(){
    [].forEach.call(document.querySelectorAll('.emm-tile'),function(t){
      var r=req[key(t)],s=sent[key(t)],old=t.querySelector('.emm-st');if(old)old.remove();
      var st=r?r.a:(s?'sent':(t.dataset.lock==='1'?'lock':''));
      t.dataset.st=st;t.disabled=!!s;
      if(st){var m=document.createElement('span');m.className='emm-st '+st;m.textContent=st==='sent'?'送信済':st==='lock'?'📌 固定':AL[st];t.querySelector('.emm-ph').appendChild(m);}});
    var ks=Object.keys(req),c={};ks.forEach(function(k){c[req[k].a]=(c[req[k].a]||0)+1;});
    $('emm-bar').hidden=!ks.length&&!$('emm-msg').textContent;
    $('emm-n').textContent=ks.length?'依頼 '+ks.length+' 件：'+Object.keys(AL).filter(function(a){return c[a];}).map(function(a){return AL[a]+' '+c[a];}).join(' · '):'';
    $('emm-go').hidden=$('emm-clr').hidden=!ks.length;
  }
  function place(){
    if(innerWidth<=600||!anchor){sheet.style.left=sheet.style.top='';return;}
    var r=anchor.getBoundingClientRect(),w=sheet.offsetWidth,h=sheet.offsetHeight;
    sheet.style.left=Math.max(12,Math.min(r.right+12,innerWidth-w-12))+'px';sheet.style.top=Math.max(12,Math.min(r.top,innerHeight-h-12))+'px';}
  function close(){sheet.hidden=true;if(cur)cur.focus();cur=null;}
  function open(t){
    cur=t;anchor=t;var lock=t.dataset.lock==='1';
    $('emm-img').src=t.dataset.img;$('emm-name').textContent=t.dataset.subj||'小元素';$('emm-why').textContent=t.dataset.why?'取り方：'+t.dataset.why:'';
    $('emm-lock-t').textContent=lock?'固定をはずす':'この写真で固定';
    $('emm-lock-d').textContent=lock?'いまは固定中。はずすと自動の補完・作り直しで替わることがある':'自動の補完・規則の作り直し・検査でも替えない';
    $('emm-lock-go').textContent=lock?'固定をはずす':'固定する';
    [].forEach.call(sheet.querySelectorAll('.emm-act'),function(a){a.setAttribute('aria-expanded','false');});
    [].forEach.call(sheet.querySelectorAll('.emm-more'),function(m){m.hidden=true;});
    [].forEach.call(sheet.querySelectorAll('[data-r]'),function(b){b.setAttribute('aria-pressed','false');});
    [].forEach.call(sheet.querySelectorAll('.emm-note'),function(i){i.value='';});
    sheet.querySelector('[data-go=drop]').disabled=true;
    sheet.hidden=false;place();sheet.querySelector('.emm-act').focus();}
  document.addEventListener('click',function(ev){
    var bt=ev.target.closest('.emm-bt');
    if(bt){[].forEach.call(document.querySelectorAll('.emm-bt'),function(x){x.setAttribute('aria-pressed',x===bt);});
      [].forEach.call(document.querySelectorAll('.emm-board'),function(b){b.hidden=b.dataset.bi!==bt.dataset.bi;});if(!sheet.hidden)close();return;}
    var t=ev.target.closest('.emm-tile');
    if(t&&!t.disabled){if(req[key(t)]){delete req[key(t)];paint();return;}open(t);return;}   // 依頼に入れた写真をもう一度押すと取り消し
    var a=ev.target.closest('.emm-act');
    if(a){var o=a.getAttribute('aria-expanded')!=='true';
      [].forEach.call(sheet.querySelectorAll('.emm-act'),function(x){x.setAttribute('aria-expanded',x===a&&o);});
      [].forEach.call(sheet.querySelectorAll('.emm-more'),function(m){m.hidden=!(o&&m.dataset.for===a.dataset.a);});place();return;}
    var c=ev.target.closest('.emm-chips [data-r]');
    if(c){var box=c.parentNode,was=c.getAttribute('aria-pressed')==='true';
      [].forEach.call(box.children,function(x){x.setAttribute('aria-pressed','false');});c.setAttribute('aria-pressed',!was);
      if(box.dataset.chips==='drop')sheet.querySelector('[data-go=drop]').disabled=was;return;}
    var g=ev.target.closest('.emm-go');
    if(g&&!g.disabled&&cur){var kind=g.dataset.go,more=g.closest('.emm-more'),on=more.querySelector('[aria-pressed=true]'),nt=more.querySelector('.emm-note');
      req[key(cur)]={a:kind==='lock'&&cur.dataset.lock==='1'?'unlock':kind,reason:on?on.dataset.r:'',note:nt?nt.value.trim():'',board:cur.dataset.b,img:cur.dataset.img};
      $('emm-msg').textContent='';close();paint();return;}
    if(ev.target.closest('#emm-close')){close();return;}
    if(!sheet.hidden&&!ev.target.closest('#emm-sheet'))close();});
  document.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&!sheet.hidden)close();});
  window.addEventListener('resize',place);
  $('emm-clr').addEventListener('click',function(){req={};$('emm-msg').textContent='';paint();});
  $('emm-go').addEventListener('click',function(){
    var by={},ks=Object.keys(req);if(!ks.length)return;
    ks.forEach(function(k){var r=req[k],c=by[r.board]=by[r.board]||{};
      if(r.a==='swap')(c._emblem_swap=c._emblem_swap||[]).push({image:r.img,reason:r.reason||'misc',note:r.note});
      else if(r.a==='drop')(c._emblem_reject=c._emblem_reject||[]).push({image:r.img,reason:r.reason,note:r.note});
      else(c._emblem_lock=c._emblem_lock||[]).push({image:r.img,on:r.a==='lock'});});
    if(!confirm(Object.keys(by).map(function(b){return b+'：'+ks.filter(function(k){return req[k].board===b;}).map(function(k){return AL[req[k].a];}).join('、');}).join('\n')+'\n\nこの依頼を送りますか？（外した・替えた画像は二度と自動で選ばれません）'))return;
    if(!CFG.url||!CFG.key){$('emm-msg').textContent='データベースに未接続です。';paint();return;}
    var go=this;go.disabled=true;$('emm-msg').textContent='送っています…';
    var names=Object.keys(by),ok=0,ng=[];
    (function next(i){
      if(i>=names.length){
        try{localStorage.setItem(KEY,JSON.stringify(sent));}catch(e){}
        $('emm-msg').textContent=(ok?ok+' 版面の依頼を送りました · 1〜2 分で反映（お客さまの版面は次のライブラリの小元素の回で）（替える写真は次の後台作業で探す）':'')+(ng.length?' 送れなかった：'+ng.join('、'):'');
        go.disabled=false;paint();return;}
      var name=names[i];
      fetch(CFG.url.replace(/\/$/,'')+'/rest/v1/rpc/'+(lib[name]?'board_emblem_request':'submit_item'),{method:'POST',headers:{apikey:CFG.key,'Content-Type':'application/json'},
        body:JSON.stringify(lib[name]?{p_board:lib[name],p_edit:by[name]}:{p_account:window.WL_ACCOUNT,p_action:'edit',p_name:name,p_config:by[name]})})
        .then(function(r){return r.text().then(function(t){var j=null;try{j=t?JSON.parse(t):null;}catch(e){}if(!r.ok)throw new Error((j&&j.message)||r.status);});})
        .then(function(){ok++;Object.keys(req).forEach(function(k){if(req[k].board===name){if(req[k].a!=='lock'&&req[k].a!=='unlock')sent[k]=Date.now();delete req[k];}});},
              function(err){ng.push(name+'（'+err.message+'）');})
        .then(function(){next(i+1);});
    })(0);
  });
  paint();
})();
"""


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
        mem = (_meter("メモリ（この処理のピーク）", x.get("peak", 0), x["mem_total"],
                      f'終わったときの空き {_mb(x.get("mem_free", 0))}') if x.get("mem_total") else "")
        used = x.get("disk_used", x.get("disk_total", 0) - x.get("disk_free", 0))   # 古い記録（disk_used なし）はマシン全体の値
        disk = (_meter("ディスク（このセッション）", used, used + x.get("disk_free", 0), f'残り {_mb(x.get("disk_free", 0))}')
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


def _emblem_flow(d, state, pics=()):
    """「小元素の探し方」：種類 → 目標 → 取り方（順に、試した数）→ 確かめる → 結果 → 次にやること を横一列の図に。
    閉じているときは 1 行の要約（いまどこで止まっているか）。開くと、いまある小元素を全部（pics：_bg_thumb の img）。"""
    chain = []
    for c in d.get("chain") or []:
        n = c.get("n")
        cls = "na" if n is None else ("zero" if not n else "got")
        val = "未" if n is None else f"{n}"
        chain.append(f'<li class="ef-{cls}{"" if c.get("auto") else " ef-eye"}" title="{"自動で選べる" if c.get("auto") else "一覧で目で選ぶだけ"}">'
                     f'<b>{e(c["src"])}</b><i>{val}</i>{"" if c.get("auto") else "<small>目視</small>"}</li>')
    f = d.get("funnel") or {}
    funnel = (f'<span>集めた <b>{f.get("found", 0)}</b></span><span>使える <b>{f.get("usable", 0)}</b></span>'
              f'<span>書いた <b>{f.get("added", f.get("auto", 0))}</b></span>') if f else ""
    rej = f.get("rejected") or {}
    if rej:   # 規則で外した理由（前は目で見ていた）
        funnel += "".join(f'<span class="ef-rj">{e(k)} <b>{v}</b></span>' for k, v in sorted(rej.items(), key=lambda kv: -kv[1]))
    check = ("規則：顔の大きさ・人数・本人（YuNet + SFace cos ≥ 0.363）・切り抜きの穴" if d.get("faces") else "規則：取り方の決まり・同じ画像") + \
            (f" · 目で外した {d['rejects']} 枚" if d.get("rejects") else "")
    if d.get("reject_log"):   # 管理ページの「違う」で選ばれた理由
        import emblem_rules
        from collections import Counter
        label = {k: t for k, t, _ in emblem_rules.REJECT_REASONS}
        check += " · 「違う」：" + "、".join(f"{label.get(k, k)} {n}" for k, n in Counter(x.get("reason") for x in d["reject_log"]).most_common())
    pct = min(100, round(100 * (d.get("have") or 0) / max(1, d.get("target") or 1)))
    tried = [c for c in d.get("chain") or [] if c.get("n") is not None]
    now_at = ("、".join(f'{c["src"]} {c["n"]}' for c in tried) or "まだ試していない")
    summary = (f'<span class="ef-k">{e(d.get("kind") or "")}</span>{e(d.get("why") or "")} → 目標 {d.get("target")} 枚'
               f' · 取り方：{e(now_at)} · <b class="ef-next">次：{e(d.get("todo") or "")}</b>')
    return (f'<details class="ef ef-st-{e(state)}"><summary>{summary}</summary><div class="ef-flow">'
            f'<div class="ef-box"><small>① 種類と目標</small><b>{e(d.get("kind") or "")}：{e(d.get("why") or "")}</b>'
            f'<span>目標 {d.get("target")} 枚（{d.get("lo")}〜{d.get("hi")}）</span></div>'
            f'<div class="ef-box ef-wide"><small>② 取り方（上から順に・足りるまで · 数字 = 集めた候補）</small><ol class="ef-chain">{"".join(chain)}</ol></div>'
            f'<div class="ef-box"><small>③ 確かめる</small><b>{e(check)}</b>' + (f'<span class="ef-fun">{funnel}</span>' if funnel else "") + '</div>'
            f'<div class="ef-box"><small>④ 結果{(" · " + e(d["at"])) if d.get("at") else ""}</small>'
            f'<b>{d.get("have")} / {d.get("target")} 枚</b><span class="em-bar"><i style="width:{pct}%"></i></span>'
            + (f'<span>{e(d["note"])}</span>' if d.get("note") else "") + '</div>'
            f'<div class="ef-box ef-todo"><small>⑤ 次にやること</small><b>{e(d.get("todo") or "")}</b>'
            + (f'<span class="ef-adv">{e(d["advice"])}</span>' if d.get("advice") else "") + "</div></div>"
            + (f'<div class="ef-all"><small>いまの小元素 · {len(pics)} 枚 · 替える・固定する・外すのは上の「小元素」の欄で'
               f'<span class="ef-pics">{"".join(pics)}</span></div>' if pics else "")
            + "</details>")


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


def _admin_edit_diff(d):
    """「AI 編集の前後」：作品ごとに、集めた記事（横棒の長さ）のうち AI 編集が記事に使ったもの（色）・使わなかったもの（灰）・
    まだ整理していないもの（金＝整理待ち：版面には載らず、版面の下の折りたたみに原題だけ並ぶ。要紧消息だけは先に「重大」で載る）、
    右に載せた記事の本数。横棒は全作品で同じ目盛り（1 本の軸）。"""
    if not d:
        return '<p class="empty">まだ収集がありません。</p>'
    rows = d.get("rows") or []
    if not rows:
        return f'<p class="empty">{e(_md(d["date"]))} はまだ AI 編集していません。</p>'
    mx = max([r["total"] for r in rows] + [1])
    new, urg = d.get("new") or 0, d.get("urgent") or 0
    wait = (f'<span>整理待ち {new} 件は版面に載せず、各版面の下の「整理待ち」に原題だけ並べる（次の AI 編集で記事に）'
            + (f' · うち要紧 {urg} 件は先に「重大」で掲載' if urg else "") + "</span>") if new else ""
    if d.get("edited"):
        head = (f'<p class="ed-sum"><b>{d["total"]}</b> 件を集めて → <b>{d["used"]}</b> 件を使い → '
                f'<b>{d["stories"]}</b> 本の記事に（同じ出来事はまとめ、宣伝・雑談・古い話は落とす）'
                f'<span>配図を選んだ記事 {d["images"]} 本 · 重大ニュース {d["hero"]} 本</span>{wait}</p>')
    else:
        head = (f'<p class="ed-sum">{e(_md(d["date"]))} はまだ AI 編集していません：<b>{d["total"]}</b> 件すべて整理待ち'
                f'{wait}</p>')
    head += ('<p class="ed-key"><span><i class="ed-u"></i>記事に使った</span><span><i class="ed-d"></i>使わなかった</span>'
             '<span><i class="ed-p"></i>整理待ち（版面に載せない）</span></p>')
    out = []
    for r in rows:
        nw = r.get("new") or 0
        u, dr = r["used"], max(0, r["total"] - r["used"] - nw)
        tip = f'{r["name"]}：集めた {r["total"]} 件のうち {u} 件を使い、{r["stories"]} 本の記事に' + (f'・整理待ち {nw} 件' if nw else "")
        badge = ("".join(f'<i class="ed-w">{k}</i>' for k, n in (("重大", r["hero"]), ("頭", r["lead"])) if n)
                 + (f'<i class="ed-new">整理待ち {nw}</i>' if nw else ""))
        out.append(
            f'<li title="{e(tip)}"><span class="ed-n">{e(r["name"])}</span>'
            f'<span class="ed-bar" style="--w:{100 * r["total"] / mx:.1f}%">'
            f'<i class="ed-u" style="flex:{u}"></i><i class="ed-d" style="flex:{dr}"></i><i class="ed-p" style="flex:{nw}"></i></span>'
            f'<span class="ed-v">{u} / {r["total"]} 件 → <b>{r["stories"]}</b> 本{badge}</span></li>')
    return head + f'<ol class="ed-rows">{"".join(out)}</ol>'


def _tk(n):
    n = int(n or 0)
    return f"{n / 10000:.1f}万" if n >= 10000 else f"{n:,}"


def _admin_edit_tokens(d):
    """「AI 編集のトークン」：AI 編集の回ごと・バッチ（5 版面ずつ編集 → 出刊 → push）ごとに使ったトークン（本物の数字、usage.py）。
    新規入力（キャッシュ書きを含む）・キャッシュ読み（安い）・出力。棒はその回でいちばん多いバッチを 100% に。"""
    runs = (d or {}).get("runs") or []
    if not runs:
        return ('<p class="empty">まだ記録がありません。次の AI 編集から、バッチ（5 版面）ごとに使ったトークンが残ります。</p>')
    def kp(label, u):
        u = u or {}
        return (f'<div class="kpi"><span class="kl">{e(label)}</span><span class="kv"><b>{_tk(int(u.get("in", 0)) + int(u.get("cw", 0)) + int(u.get("out", 0)))}</b>'
                f'<small>新規入力＋出力</small></span><span class="kd">キャッシュ読み {_tk(u.get("cr"))}</span></div>')
    out = '<div class="kpis k2">' + kp("今日", d.get("today")) + kp("この 7 日", d.get("week")) + "</div>"
    if d.get("cap"):   # gate.EDIT_DAILY_TOKENS：これを超えた日は、溜まった版面があっても起こさない（ボタンは別）
        out += (f'<p class="mt-x">1 日の上限：新規入力＋出力 {_tk(d["cap"])}（北京時間の 1 日）。超えたら、整理待ちが溜まっても次の日まで AI 編集を起こさない'
                '（「AI 編集をもう一度起こす」は起こせる）。</p>')
    for g in runs:
        peak = max([b["total"] for b in g["batches"]] + [1])
        rows = "".join(
            f'<li><span class="tk-w">{e(b["when"])} · 第 {e(str(b.get("batch") or "?"))} バッチ</span>'
            f'<span class="tk-b">{e("、".join(b["boards"][:5]) + (" ほか" if len(b["boards"]) > 5 else "")) or "—"}'
            f'<small>{len(b["boards"])} 版面・{e(str(b.get("stories") or 0))} 本</small></span>'
            f'<span class="tk-bar"><i style="width:{100 * b["total"] / peak:.1f}%"></i></span>'
            f'<span class="tk-n">入力 {_tk(int(b["tok"].get("in", 0)) + int(b["tok"].get("cw", 0)))} · 読み {_tk(b["tok"].get("cr"))} · 出力 {_tk(b["tok"].get("out"))}</span></li>'
            for b in g["batches"])
        sm = g["sum"]
        out += (f'<h3 class="h3">{e(g["when"])} の回 <small>{len(g["batches"])} バッチ · 新規入力 {_tk(sm.get("in", 0) + sm.get("cw", 0))}'
                f' · キャッシュ読み {_tk(sm.get("cr"))} · 出力 {_tk(sm.get("out"))}</small></h3><ol class="tks">{rows}</ol>')
    return out + ('<p class="mt-x">数字は Claude のセッションの記録から（推定ではない）。キャッシュ読みは料金がずっと安い。'
                  'サブスク枠の残りは <a href="https://claude.ai/settings/usage" target="_blank" rel="noopener noreferrer">Claude の設定 → 使用量</a> で。</p>')


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
.kpis.k2{grid-template-columns:repeat(2,minmax(0,1fr))}
.tks{list-style:none;margin:0 0 12px;padding:0;display:grid;gap:6px}
.tks li{display:grid;grid-template-columns:150px minmax(0,1fr) 160px 260px;gap:4px 12px;align-items:center;font-size:13px}
.tk-w{font:700 12px var(--font-mono)}.tk-b{overflow-wrap:anywhere}.tk-b small{display:block;opacity:.7;font-size:var(--fs-label)}
.tk-bar{height:10px;background:color-mix(in srgb,var(--ink) 10%,transparent)}.tk-bar i{display:block;height:100%;background:var(--viz-5)}
.tk-n{font:500 12px var(--font-mono)}
@media (max-width:860px){.tks li{grid-template-columns:minmax(0,1fr)}}
.ed-sum{margin:0 0 6px;font-size:14px;line-height:1.8}.ed-sum b{font:900 20px var(--font-mono);margin:0 2px}
.ed-sum span{display:block;font-size:12px;opacity:.75}
.ed-key{display:flex;gap:16px;margin:0 0 10px;font-size:12px}.ed-key span{display:inline-flex;align-items:center;gap:6px}
.ed-key i{display:inline-block;width:14px;height:10px;border-radius:2px}
.ed-rows{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.ed-rows li{display:grid;grid-template-columns:150px minmax(0,1fr) 210px;gap:10px;align-items:center;font-size:13px}
.ed-n{font-weight:900;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ed-bar{display:flex;gap:2px;width:var(--w);min-width:6px;height:14px}
.ed-bar i{display:block;min-width:0;border-radius:0 4px 4px 0}.ed-bar i:first-child{border-radius:4px 0 0 4px}
.ed-bar i:only-child,.ed-bar i[style*="flex:0"]{border-radius:4px}
.ed-u{background:var(--viz-1)}.ed-p{background:var(--gold)}.ed-d{background:color-mix(in srgb,var(--ink) 18%,transparent)}
.ed-bar i[style*="flex:0"]{display:none}
.ed-v{font:700 12px var(--font-mono);white-space:nowrap}.ed-v b{font-size:15px}
.ed-w,.ed-new{display:inline-block;font:700 10px var(--font-sans);font-style:normal;margin-left:6px;padding:0 6px;background:var(--ink);color:var(--card);transform:skewX(var(--skew))}
.ed-new{background:var(--gold);color:var(--ink)}
@media (max-width:640px){.ed-rows li{grid-template-columns:1fr;gap:3px}.ed-v{white-space:normal}}
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
.nx-go{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;margin-top:6px}
.nx-run{font:900 12px/1 var(--font-sans);padding:7px 12px;background:var(--ink);color:var(--card);border:2px solid var(--ink);box-shadow:3px 3px 0 var(--rose);cursor:pointer}
.nx-run:hover:not(:disabled){background:var(--rose);border-color:var(--rose);box-shadow:3px 3px 0 var(--ink)}
.nx-run:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.nx-run:disabled{opacity:.55;cursor:default}
.nx-msg{font:700 var(--fs-label)/1.4 var(--font-sans)}.nx-msg.ok{color:var(--good)}.nx-msg.ng{color:var(--alert)}
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
.bg-th{display:flex;flex-wrap:wrap;align-items:center;gap:3px;margin-top:4px}.bg-more{font:700 var(--fs-label) var(--font-mono);opacity:.7}
.ef-all{padding:10px 12px 12px;border-top:1px dashed var(--hair)}.ef-all>small{display:block;font:700 var(--fs-label) var(--font-sans);margin-bottom:6px;opacity:.8}
.ef-pics{display:flex;flex-wrap:wrap;gap:6px}.ef-pics img{width:44px;height:44px;object-fit:cover;object-position:top;border-radius:50%;border:1.5px solid var(--ink);background:var(--card)}
.ef-pics img.fit{object-fit:contain;border-radius:6px;padding:3px}
.bgw-d{display:block;font-weight:400;font-size:var(--fs-label);opacity:.75}
.bgw-d.es-ng{opacity:1;color:var(--alert)}.bgw-d b{font-weight:900}
th .nx-go{display:flex;flex-direction:column;align-items:flex-start;gap:4px;margin-top:6px;font-weight:400}
.bgc .bg-cd{display:block;font:700 var(--fs-label) var(--font-mono);color:var(--alert)}
.bgc .nx-go{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;margin-top:6px}.bg-redo{padding:5px 10px}
.bg-th img{width:26px;height:26px;object-fit:cover;object-position:top;border-radius:50%;border:1.5px solid var(--ink);background:var(--card)}.bg-th img.fit{object-fit:contain;border-radius:4px;padding:2px}
.emm-boards{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.emm-bt{background:var(--card);border:2px solid var(--ink);padding:5px 14px;font:900 14px var(--font-sans);color:var(--ink);cursor:pointer}
.emm-bt small{margin-left:6px;font:700 var(--fs-label) var(--font-mono);opacity:.6}
.emm-bt[aria-pressed=true]{background:var(--ink);color:var(--card);box-shadow:3px 3px 0 var(--rose)}
.emm-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px;margin:0 0 12px}.emm-h b{font:900 18px var(--font-sans);background:var(--ink);color:var(--card);padding:2px 12px;transform:rotate(var(--tilt))}
.emm-h span{font-size:13px;opacity:.7}
.emm-board[hidden],.emm-sheet[hidden],.emm-bar[hidden],.emm-more[hidden]{display:none}
.emm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:14px}
.emm-tile{position:relative;display:flex;flex-direction:column;gap:6px;background:none;border:0;padding:0;text-align:left;color:var(--ink);cursor:pointer;font:inherit}
.emm-tile:disabled{cursor:default;opacity:.55}
.emm-ph{position:relative;display:block;aspect-ratio:4/5;background:repeating-linear-gradient(45deg,color-mix(in srgb,var(--ink) 8%,var(--card)) 0 6px,var(--sheet) 6px 12px);border:2px solid var(--ink);overflow:hidden}
.emm-ph img{width:100%;height:100%;object-fit:contain;display:block}
.emm-tile b{font:900 13px/1.35 var(--font-sans)}.emm-tile small{font-size:var(--fs-label);line-height:1.4;opacity:.65}
.emm-tile:hover .emm-ph{box-shadow:3px 3px 0 var(--rose)}
.emm-st{position:absolute;left:-4px;top:8px;padding:1px 8px;font:900 11px/1.6 var(--font-sans);color:var(--card);transform:skewX(var(--skew));background:var(--ink)}
.emm-st.swap{background:var(--rose)}.emm-st.lock{background:var(--good)}.emm-st.unlock{background:var(--ink)}.emm-st.drop{background:var(--alert)}
.emm-tile[data-st=drop] img,.emm-tile[data-st=sent] img{opacity:.35}
.emm-sheet{position:fixed;z-index:96;background:var(--card);border:2px solid var(--ink);box-shadow:6px 6px 0 var(--ink);width:min(420px,calc(100vw - 24px));max-height:calc(100vh - 24px);overflow:auto;padding:16px 16px 14px;font:500 13px/1.5 var(--font-sans)}
.emm-sh{display:grid;grid-template-columns:72px minmax(0,1fr);gap:12px;align-items:center;margin-bottom:12px}
.emm-sh b{display:block;font:900 17px/1.3 var(--font-sans)}.emm-sh small{font-size:12px;opacity:.65}
.emm-acts{display:flex;flex-direction:column;gap:8px}
.emm-act{display:grid;grid-template-columns:30px minmax(0,1fr);gap:2px 8px;align-items:start;text-align:left;background:var(--card);border:2px solid var(--ink);padding:9px 12px;color:var(--ink);cursor:pointer;font:inherit}
.emm-act i{font-style:normal;font-size:20px;line-height:1.3;grid-row:span 2}.emm-act b{font:900 15px/1.4 var(--font-sans)}.emm-act span{font-size:12px;opacity:.65;line-height:1.5}
.emm-act[aria-expanded=true]{background:var(--ink);color:var(--card)}
.emm-more{border-left:4px solid var(--rose);margin:2px 0 4px;padding:8px 0 4px 12px;display:flex;flex-direction:column;gap:10px}
.emm-more h3{margin:0;font:900 13px var(--font-sans)}
.emm-chips{display:flex;flex-wrap:wrap;gap:6px}
.emm-chips button{background:var(--card);border:1.5px solid var(--ink);padding:3px 10px;font:700 12px var(--font-sans);color:var(--ink);cursor:pointer}
.emm-chips button[aria-pressed=true]{background:var(--ink);color:var(--card)}
.emm-note{min-width:0;padding:5px 8px;border:1.5px solid var(--ink);background:var(--card);font:500 13px var(--font-sans)}
.emm-go{align-self:flex-start;background:var(--rose);color:var(--card);border:2px solid var(--ink);padding:6px 16px;font:900 13px var(--font-sans);box-shadow:3px 3px 0 var(--ink);cursor:pointer}
.emm-go:disabled{opacity:.45;cursor:not-allowed}
.emm-x{margin-top:10px;background:none;border:0;text-decoration:underline;font:500 13px var(--font-sans);color:var(--ink);opacity:.7;cursor:pointer}
.emm-bar{position:fixed;left:50%;bottom:16px;z-index:90;transform:translateX(-50%);display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;
 max-width:calc(100vw - 32px);padding:10px 14px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);font:700 13px/1.5 var(--font-sans)}
.emm-bar button{border:2px solid var(--ink);background:var(--card);color:var(--ink);padding:5px 12px;font:700 13px var(--font-sans);cursor:pointer}
.emm-bar button[hidden]{display:none}.emm-bar #emm-go{background:var(--gold)}.emm-bar small{font:500 var(--fs-label)/1.5 var(--font-sans)}
@media (max-width:600px){
 .emm-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.emm-tile small{display:none}
 .emm-sheet{left:0!important;right:0;bottom:0;top:auto!important;width:100%;max-height:82vh;border-width:2px 0 0;box-shadow:0 -4px 0 var(--ink)}}
.emxs td.n{font:700 13px var(--font-mono);text-align:right}
.emx-recent{list-style:none;margin:8px 0 0;padding:0;font-size:13px}.emx-recent li{padding:4px 0;border-bottom:1px solid var(--hair)}
.emx-recent small{margin-left:8px;font:500 var(--fs-label) var(--font-mono);opacity:.7}
.bgm tr.bgx td{padding:0 6px 10px;border-bottom:1px solid var(--hair)}
.bgm tr:has(+ .bgx) td{border-bottom:0}
.ef summary{cursor:pointer;font:500 12px/1.6 var(--font-sans);list-style:none;padding:4px 8px;background:var(--sheet);border-left:4px solid var(--hair)}
.ef summary::-webkit-details-marker{display:none}
.ef summary::before{content:"▸ 小元素の探し方　";font-weight:900}.ef[open] summary::before{content:"▾ 小元素の探し方　"}
.ef-st-ok summary{border-left-color:var(--good)}.ef-st-review summary{border-left-color:var(--gold)}
.ef-st-failed summary{border-left-color:var(--alert)}.ef-st-running summary{border-left-color:var(--rose)}
.ef-k{font:700 var(--fs-label) var(--font-mono);padding:0 5px;margin-right:6px;background:var(--ink);color:var(--card)}
.ef-next{font-weight:900}
.ef-flow{display:flex;flex-wrap:wrap;align-items:stretch;gap:10px 22px;padding:10px 4px 4px}
.ef-box{position:relative;flex:1 1 150px;display:flex;flex-direction:column;gap:3px;padding:8px 10px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);min-width:0}
.ef-box:not(:last-child)::after{content:"→";position:absolute;right:-18px;top:50%;transform:translateY(-50%);font:900 15px var(--font-mono);color:var(--rose)}
.ef-wide{flex:3 1 330px}
.ef-box>small{font:700 var(--fs-label) var(--font-sans);opacity:.75}.ef-box>b{font:900 13px/1.45 var(--font-sans)}
.ef-box>span{font:500 12px/1.5 var(--font-sans)}
.ef-chain{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:4px 14px}
.ef-chain li{position:relative;display:flex;align-items:baseline;gap:5px;padding:2px 7px;border:1.5px solid var(--ink);font-size:12px}
.ef-chain li:not(:last-child)::after{content:"›";position:absolute;right:-11px;font:900 13px var(--font-mono);color:var(--rose)}
.ef-chain b{font:700 12px var(--font-sans)}.ef-chain i{font:700 12px var(--font-mono);font-style:normal}
.ef-chain small{font:700 var(--fs-tag) var(--font-sans);padding:0 4px;border:1px dashed currentColor}
.ef-got{background:color-mix(in srgb,var(--good) 18%,var(--card))}.ef-got i{color:var(--good)}
.ef-zero{opacity:.75}.ef-zero i{color:var(--alert)}
.ef-na{opacity:.45;border-style:dotted!important}
.ef-eye{border-style:dashed!important}
.ef-fun{display:flex;flex-wrap:wrap;gap:2px 10px;font-size:var(--fs-label)!important}
.ef-rj{color:var(--alert)}.ef-todo{border-color:var(--rose)}.ef-adv{color:var(--alert);font-weight:700!important}
@media (max-width:860px){.bgm tr.bgx{display:block;padding:0 0 10px}.bgm tr.bgx td{display:block;padding:0}.ef-box:not(:last-child)::after{content:"↓";right:auto;left:50%;top:auto;bottom:-17px;transform:translateX(-50%)}.ef-flow{gap:20px}.ef-box{flex-basis:100%}}
.aiu{list-style:none;margin:0 0 20px;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px 18px}
.aiu li{display:grid;grid-template-columns:minmax(0,1fr);gap:2px;padding:7px 10px;border-left:4px solid var(--hair);background:var(--card)}
.aiu b{font:900 13px/1.4 var(--font-sans)}.aiu small{font:500 var(--fs-label)/1.55 var(--font-sans);opacity:.85}
.aiu-s{justify-self:start;font:700 var(--fs-label) var(--font-sans);padding:0 6px;border:1.5px solid currentColor}
.aiu-rule{border-left-color:var(--good)}.aiu-rule .aiu-s{color:var(--good)}
.aiu-gate{border-left-color:var(--gold)}.aiu-gate .aiu-s{color:var(--ink);background:var(--gold);border-color:var(--ink)}
.aiu-ai{border-left-color:var(--rose)}.aiu-ai .aiu-s{color:var(--rose)}
.livenow{margin:0 0 20px}
.livenow ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}
.livenow li{position:relative;display:flex;flex-direction:column;gap:2px;padding:8px 10px 12px;background:var(--card);border:2px solid var(--ink);box-shadow:var(--shadow);overflow:hidden}
.livenow li b{font:900 13px/1.35 var(--font-sans)}.livenow li small{font:500 var(--fs-label)/1.5 var(--font-sans)}
.livenow li .ln-p{font:700 var(--fs-label) var(--font-sans);color:var(--rose)}
.livenow li::after{content:"";position:absolute;left:0;right:0;bottom:0;height:5px;
 background:repeating-linear-gradient(-45deg,var(--good) 0 6px,color-mix(in srgb,var(--good) 60%,var(--card)) 6px 12px);background-size:17px 17px;animation:pb-move 1.2s linear infinite}
@media (prefers-reduced-motion:reduce){.livenow li::after{animation:none}}
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
      if(x.classList.contains('nx-h')){x.textContent=(x.getAttribute('data-pre')||'次回 ')+hm(a[1])+'（'+left(a[1]-new Date())+'）';return;}
      var du=x.getAttribute('data-due');   // 今の回をまだ起こしていない（ゲート待ち）：次の日の回を数えない
      if(du){x._next=0;x.querySelector('.nx-t').textContent=du;x.querySelector('.nx-l').textContent='の回はまもなく';
        x.querySelector('.nx-p').textContent='次のゲートで起こす';x.classList.add('soon');return;}
      x.querySelector('.nx-t').textContent=hm(a[1]);x.querySelector('.nx-l').textContent=left(a[1]-new Date());
      x.querySelector('.nx-p').textContent='前回 '+hm(a[0]);x.classList.toggle('soon',a[1]-new Date()<15*60000);});
    Array.prototype.forEach.call(document.querySelectorAll('.nx[data-slots]'),function(x){var sl=JSON.parse(x.getAttribute('data-slots')||'[]'),b=x.querySelector('.pbar i');
      if(!b||!sl.length)return;var a=around(sl);b.style.width=Math.min(100,Math.max(2,(new Date()-a[0])/(a[1]-a[0])*100)).toFixed(1)+'%';});
    // 失敗した小元素の自動の再挑戦まで（data-at）・ゲートが前回 AI 編集を起こした時刻
    Array.prototype.forEach.call(document.querySelectorAll('.bgc .bg-cd[data-at]'),function(x){var t=new Date(x.getAttribute('data-at'));
      x.textContent=t>new Date()?'自動の再挑戦 '+hm(t)+'（'+left(t-new Date())+'）':'まもなく自動で再挑戦';});
    Array.prototype.forEach.call(document.querySelectorAll('.nx-ago[data-at]'),function(x){x.textContent='ゲートが前回起こした '+hm(new Date(x.getAttribute('data-at')));});
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
      if(first&&r.p.items.length){var w=el('span','q-i');r.p.items.forEach(function(n,j){w.appendChild(el('i',null,(r.p.id==='gate'?(j+1)+'. ':'')+n));});d.appendChild(w);}
      li.appendChild(d);q.appendChild(li);});
    if(!runs.length)q.appendChild(el('li','empty','予定がありません。'));}
  tick();setInterval(tick,60000);
  // GitHub Actions：ワークフローごとに最新の実行（3 分ごとに読み直す。GitHub は 1 時間 60 回まで）
  var runs=document.getElementById('runs');   // ①いま にだけある（管理ページは 6 つ。ほかのページの「次の実行」の札もない）
  // GitHub の API はログインなしだと 1 時間 60 回まで。管理ページをいくつ開いていても、3 分以内に誰かが読んだ結果は使い回す（localStorage）
  function actionsRuns(){var K='wl-actions',c=null;try{c=JSON.parse(localStorage.getItem(K)||'null');}catch(e){}
    if(c&&Date.now()-c.t<170000)return Promise.resolve(c.j);
    return fetch('https://api.github.com/repos/'+CFG.repo+'/actions/runs?per_page=60').then(function(r){if(!r.ok)throw 0;return r.json();})
      .then(function(j){try{localStorage.setItem(K,JSON.stringify({t:Date.now(),j:{workflow_runs:(j.workflow_runs||[]).map(function(w){
        return {path:w.path,html_url:w.html_url,status:w.status,conclusion:w.conclusion,created_at:w.created_at,event:w.event};})}}));}catch(e){}return j;});}
  function loadRuns(){
  actionsRuns().then(function(j){
    var seen={},ul=el('ul','runs');
    Array.prototype.forEach.call(document.querySelectorAll('.nx .lvx'),function(x){x.remove();});
    Array.prototype.forEach.call(document.querySelectorAll('.nx.run'),function(x){x.classList.remove('run');});
    (j.workflow_runs||[]).forEach(function(w){
      var f=(w.path||'').split('/').pop();if(!CFG.flows[f]||seen[f])return;seen[f]=1;
      var li=el('li'),a=el('a',null,CFG.flows[f]);var http=/^https:\\/\\/github\\.com\\//.test(w.html_url||'');
      if(http){a.href=w.html_url;a.target='_blank';a.rel='noopener noreferrer';}
      var b=el('b');b.appendChild(a);li.appendChild(b);
      var c=w.status!=='completed'?['実行中','wait']:w.conclusion==='success'?['成功','good']:w.conclusion==='cancelled'||w.conclusion==='skipped'?['取消','idle']:['失敗','bad'];
      li.appendChild(badge(c[0],c[1]));li.appendChild(el('small',null,when(w.created_at)+' · '+(w.event||'')));ul.appendChild(li);
      var card=document.querySelector('.nx[data-wf="'+f+'"]');if(card&&w.status!=='completed')card.classList.add('run');
      var lv=document.querySelector('.nx[data-wf="'+f+'"] .lv');if(lv){var s1=el('small','lvx',when(w.created_at)),b1=badge(c[0],c[1]);b1.classList.add('lvx');lv.insertBefore(s1,lv.firstChild);lv.insertBefore(b1,lv.firstChild);}
    });
    if(!runs)return;runs.textContent='';if(ul.children.length)runs.appendChild(ul);else fail(runs,'最近の実行がありません。');
  }).catch(function(){if(runs)fail(runs,'GitHub から読めませんでした（1 時間に 60 回までの制限かもしれません）。');});
  }
  if(runs||document.querySelector('.nx')){loadRuns();setInterval(function(){if(!document.hidden)loadRuns();},180000);}
  if(!CFG.url||!CFG.key){['reqs','photos','livenow'].forEach(function(id){var b=document.getElementById(id);if(b)fail(b,'データベースに未接続です。');});
    Array.prototype.forEach.call(document.querySelectorAll('[data-run]'),function(b){b.disabled=true;b.title='データベースに未接続';});return;}
  // 今すぐ実行：定時を待たずに GitHub Actions を起こす（Supabase の run_now() が Vault の令牌で頼む。網页に令牌は置かない）
  document.addEventListener('click',function(ev){var b=ev.target.closest('[data-run]');if(!b)return;
    var msg=b.parentNode.querySelector('.nx-msg'),card=b.closest('.nx');b.disabled=true;b.textContent='起動中…';msg.className='nx-msg';msg.textContent='';
    fetch(CFG.url+'/rest/v1/rpc/run_now',{method:'POST',headers:{apikey:CFG.key,'Content-Type':'application/json'},body:JSON.stringify({job:b.dataset.run})})
      .then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(x){
        var nx=x&&x.next_at?new Date(x.next_at):null,left=nx?Math.max(1,Math.ceil((nx-new Date())/60000)):0;
        if(x&&x.ok){msg.className='nx-msg ok';msg.textContent='起こしました · 数十秒で「実行中」に';if(card)card.classList.add('run');
          if(b.dataset.run==='background'){msg.textContent='起こしました · 1 分ほどで作業の 1 行 1 行が ';var a=el('a',null,'ライブログ');a.href='admin-now.html#term-panel';msg.appendChild(a);msg.appendChild(document.createTextNode(' に流れます'));
            var cd=b.closest('td')&&b.closest('td').querySelector('.bg-cd');if(cd){cd.removeAttribute('data-at');cd.textContent='いま再挑戦中（次の時刻は終わってから決まる）';}}
          setTimeout(loadRuns,20000);setTimeout(loadRuns,60000);}
        else{msg.className='nx-msg ng';msg.textContent=(x&&x.msg||'起こせませんでした')+(left?' · あと '+left+' 分で押せます':'');}
        b.textContent=b.dataset.label||'今すぐ実行';setTimeout(function(){b.disabled=false;},left?left*60000:5000);})
      .catch(function(){msg.className='nx-msg ng';msg.textContent='起こせませんでした（データベースに届かない）';b.textContent=b.dataset.label||'今すぐ実行';b.disabled=false;});});
  function rpc(fn){return fetch(CFG.url+'/rest/v1/rpc/'+fn,{method:'POST',headers:{apikey:CFG.key,'Content-Type':'application/json'},body:JSON.stringify({p_account:window.WL_ACCOUNT})})
    .then(function(r){if(!r.ok)throw 0;return r.json();});}
  var ST={pending:['待ち','wait'],done:['反映済み','good'],skipped:['見送り','bad'],'new':['受付','wait'],exported:['認識待ち','wait']};
  // いま動いているもの：live_status()（収集・小元素の補完が版面ごとに書く）を 30 秒ごとに
  var LP={collect:'ニュース収集',emblem:'小元素の自動補完',edit:'AI 編集'};
  function liveState(x){if(x.state==='fetch')return '記事を探している';if(x.state==='found')return '新着 '+x.found+' 件 · AI 整理待ち';
    if(x.note)return x.note+(x.state==='wait'&&Date.now()-new Date(x.started_at)>1800000?'（30 分以上たっている：push が通っていないかも）':'');
    var m=/^emblem:(.*)$/.exec(x.state||'');if(m)return '取り方 '+m[1]+'（'+x.found+' / 3 段目）';return x.state;}
  function loadLive(){var box=document.getElementById('livenow');if(!box)return;
    rpc('live_boards').then(function(list){box.textContent='';if(!list||!list.length){box.appendChild(el('p','empty','いまは何も動いていません（次の実行は下の「次の実行」）。'));return;}
      var ul=el('ul');list.forEach(function(x){var li=el('li');li.appendChild(el('span','ln-p',LP[x.proc]||x.proc));li.appendChild(el('b',null,x.board));
        li.appendChild(el('small',null,liveState(x)+' · '+when(x.started_at)+'から'));ul.appendChild(li);});box.appendChild(ul);})
    .catch(function(){fail(box,'読めませんでした。');});}
  loadLive();setInterval(loadLive,30000);
  // 設定ページの依頼（ウォッチ項目の追加・修正）：待ちのものと、3 日以内に処理したもの
  var reqs=document.getElementById('reqs'),photos=document.getElementById('photos');
  function loadDb(){if(!reqs||!photos)return;
  rpc('list_item_requests').then(function(list){
    reqs.textContent='';if(!list||!list.length){fail(reqs,'依頼はありません。');return;}
    var ul=el('ul','qlist');list.forEach(function(x){var li=el('li');
      li.appendChild(el('b',null,(x.action==='edit'?'修正：':'追加：')+x.name));var s=ST[x.status]||[x.status,'idle'];li.appendChild(badge(s[0],s[1]));
      li.appendChild(el('small',null,when(x.created_at)+(x.note?' · '+x.note:'')));ul.appendChild(li);});
    reqs.appendChild(ul);
  }).catch(function(){fail(reqs,'読めませんでした。');});
  // ウィッシュリストの写真の受付
  rpc('get_photo_inbox').then(function(list){
    photos.textContent='';if(!list||!list.length){fail(photos,'写真はありません。');return;}
    var ul=el('ul','qlist');list.slice(0,12).forEach(function(x){var li=el('li','ph');
      if(/^data:image\\/jpeg;base64,/.test(x.thumb||'')){var im=el('img');im.src=x.thumb;im.alt='';im.loading='lazy';li.appendChild(im);}else li.appendChild(el('span'));
      li.appendChild(el('b',null,x.wish_name||('#'+x.id+' '+(x.status||''))));var s=x.state==='done'?['追加済み','good']:(ST[x.state]||[x.state,'idle']);li.appendChild(badge(s[0],s[1]));
      li.appendChild(el('small',null,when(x.created_at)+(x.note?' · '+x.note:'')));ul.appendChild(li);});
    photos.appendChild(ul);
  }).catch(function(){fail(photos,'読めませんでした。');});
  }
  // 依頼と写真：1 分ごとに読み直す（タブが裏にあるあいだは休み、戻ったらすぐ）
  loadDb();setInterval(function(){if(!document.hidden)loadDb();},60000);
  document.addEventListener('visibilitychange',function(){if(!document.hidden)loadDb();});
})();
"""


# 管理ページは 6 つ＋トップ（2026-10-25，用户定的：1 枚はややこしすぎる）。中身は前の 1 枚の欄をそのまま移した（作り直さない）。
# (ファイル, 印, 名前, 中身の説明, 欄の id)。前の網址 admin.html#<id> はトップの JS がその欄のあるページへ送る。
ADMIN_PAGES = [
    ("admin-now.html", "①", "いま", "ライブログ・運行状況・次の実行・Actions と依頼", ["term-panel", "status", "nextrun", "queue"]),
    ("admin-boards.html", "②", "版面", "ウォッチ項目の表・投票", ["items", "votes"]),
    ("admin-emblem.html", "③", "エンブレム", "小元素の管理（替える・固定・外す）・進捗・版面ごとの状態・判断の例", ["emblem-manage", "emblems", "backend", "emblem-ex"]),
    ("admin-ai.html", "④", "AI 編集", "トークン・編集の前後", ["tokens", "editdiff"]),
    ("admin-system.html", "⑤", "しくみ", "全体図・詳しい図・リソース・並列と制限", ["ov", "procs", "res"]),
    ("admin-members.html", "⑥", "お客さまと店長", "登録した人・パスワード・店長（店長のログインで）", ["members"]),
]
ADMIN_NAV_CSS = """
.admnav{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0 18px;padding:0;list-style:none}
.admnav a{display:inline-flex;align-items:center;min-height:36px;padding:4px 12px;background:var(--card);color:var(--ink);border:2px solid var(--ink);
 box-shadow:3px 3px 0 var(--ink);font:900 13px var(--font-sans);text-decoration:none;transform:skewX(var(--skew))}
.admnav a>span{display:inline-block;transform:skewX(calc(-1*var(--skew)))}
.admnav a[aria-current]{background:var(--ink);color:var(--card)}.admnav a.adm-top{background:var(--gold)}
.admnav a:active{transform:skewX(var(--skew)) translate(2px,2px);box-shadow:1px 1px 0 var(--ink)}
.admhub{list-style:none;margin:20px 0 24px;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.admhub a{display:flex;flex-direction:column;gap:8px;height:100%;padding:16px 18px;background:var(--card);color:var(--ink);border:2px solid var(--ink);
 box-shadow:var(--shadow);text-decoration:none;transition:transform .12s,box-shadow .12s}
.admhub a:hover{transform:translate(-2px,-2px);box-shadow:6px 6px 0 var(--ink)}
.admhub a:active{transform:translate(2px,2px);box-shadow:1px 1px 0 var(--ink)}
.admhub b{font:900 22px var(--font-sans)}.admhub b i{font-style:normal;margin-right:8px;color:var(--rose)}
.admhub small{font-size:13px;line-height:1.6;opacity:.8}
.admhub .n{align-self:flex-start;padding:2px 10px;background:var(--ink);color:var(--card);font:700 13px var(--font-mono);transform:skewX(var(--skew))}
.admhub .n.warn{background:var(--alert)}
@media (max-width:860px){.admhub{grid-template-columns:minmax(0,1fr)}}
@media (prefers-reduced-motion:reduce){.admhub a{transition:none}}
"""
# 前の 1 枚の管理ページの網址（admin.html#backend など）を、その欄のあるページへ送る
ADMIN_HUB_JS = """(function(){var M=__MAP__,h=location.hash.slice(1);if(h&&M[h])location.replace(M[h]+'#'+h);})();"""
ADMIN_QUEUE = """<section class="panel live" id="queue"><h2 class="sh"><span>いまの状況</span><small>開いている間ずっと読み直す（依頼・写真 1 分 / Actions 3 分）</small></h2>
<div class="grid3"><div><h3 class="h3">GitHub Actions</h3><div id="runs"><p class="empty">読み込み中…</p></div></div>
<div><h3 class="h3">ウォッチ項目の依頼</h3><div id="reqs"><p class="empty">読み込み中…</p></div></div>
<div><h3 class="h3">写真の受付</h3><div id="photos"><p class="empty">読み込み中…</p></div></div></div></section>"""


def _admin_counts(data):
    """トップのカードの数（生成した時点）。「見に行くべきか」が分かる 1 つの数と、赤くするか。"""
    items = data.get("items") or []
    failed = sum(1 for r in items for c in (r.get("bg") or {}).values() if isinstance(c, dict) and c.get("state") == "failed")
    stale = sum(1 for r in items if "last_days" in r and (r["last_days"] is None or r["last_days"] >= ADMIN_STALE_DAYS))
    gap = sum(1 for r in items if r.get("emblem") and r["emblem"].get("state") != "ok")
    pend = ((data.get("todo") or {}).get("edit") or {}).get("n") or 0
    return {"admin-now.html": (f"失敗 {failed}", True) if failed else ("止まっていない", False),
            "admin-boards.html": (f"{len(items)} 版面" + (f" · 新しい記事なし {stale}" if stale else ""), bool(stale)),
            "admin-emblem.html": (f"目標に届かない {gap}", True) if gap else ("全部が目標に", False),
            "admin-ai.html": (f"整理待ち {pend} 件" if pend else "整理待ちなし", False),
            "admin-system.html": (f"仕組み {len(processes.PROCESSES)}", False),
            "admin-members.html": ("店長だけ", False)}


def render_admin(data, db, updated):
    """管理ページ（docs/home/admin.html ＝トップ、admin-*.html ＝ 6 つの別ページ）。見るだけ・口令なし。
    data = {"pipeline": {...}, "items": [行], "votes": {...}}（digest.admin_data が作る）；
    db = {url, key}（公開の publishable key。依頼と写真の受付をページを開いたときに読む）。
    返すのは {ファイル名: HTML}（digest.write_page がそれぞれに指紋を入れて書く）。"""
    cfg = json.dumps({"url": (db or {}).get("url") or "", "key": (db or {}).get("key") or "",
                      "repo": (db or {}).get("repo") or "CxElegy/Wishlist", "flows": ADMIN_WORKFLOWS,
                      "tz": (db or {}).get("tz") or "Asia/Tokyo"},
                     ensure_ascii=False).replace("</", "<\\/")
    items = data.get("items") or []
    bg = _admin_backend(items, data.get("todo"), data.get("log"), data.get("resources"))
    dialogs = "".join(processes.detail(p) for p in processes.PROCESSES)   # 「次の実行」の名前・全体図の部品を押すと開く流れの図

    def panel(i, title, sub, body, cls=""):
        return f'<section class="panel{cls}" id="{i}"><h2 class="sh"><span>{title}</span><small>{sub}</small></h2>{body}</section>'
    S = {
        "members": '<section class="panel" id="members" hidden><h2 class="sh"><span>お客さまと店長</span><small>だれでもメールアドレス＋パスワードで始められる（重ならない・規約に同意・メールは送らない）· お客さまのパスワードを変える · 店長は 5 人まで</small></h2><div class="wl-mem" id="wl-members"><p class="empty">読み込み中…</p></div></section>'
                   '<p class="empty">この欄は店長がログインしたときだけ出ます。</p>',
        "term-panel": panel("term-panel", "ライブログ", "裏の仕組みが版面ごとに始めた・終えたことが自動で流れる · 開いている間ずっと",
                            livelog.panel(data.get("log"), (db or {}).get("repo") or "CxElegy/Wishlist", [x.get("name") for x in items if x.get("name")])),
        "tokens": panel("tokens", "AI 編集のトークン", "回ごと・バッチ（5 版面ずつ編集 → 出刊 → 公開）ごと · 本物の数字", _admin_edit_tokens(data.get("edit_tokens"))),
        "ov": panel("ov", "しくみの全体図", "1 ページ 1 画面 · 光る部品 = いま動いている · 部品をクリックで詳しい流れ", overview.panel(data)),
        "status": panel("status", "運行状況", "ページを生成した時点", _admin_pipeline(data.get("pipeline") or {})),
        "editdiff": panel("editdiff", "AI 編集の前後", f'最新号 {e(_md((data.get("edit_diff") or {}).get("date") or ""))}：集めた記事 → 版面に載せた記事',
                          _admin_edit_diff(data.get("edit_diff"))),
        "nextrun": panel("nextrun", "次の実行", f"何が待っていて、次にいつ動くか · {e(updated)} 時点", bg["now"]),
        "backend": panel("backend", "版面ごとの状態", f"収集・AI 編集・版面の設計・小元素 · 表は {e(updated)} 時点", bg["table"]),
        "res": panel("res", "リソース・並列と制限", "サーバーの残り · 容量 · トークン · AI を使うか", bg["sys"]),
        "emblem-ex": panel("emblem-ex", "小元素の判断の例", "本物の画像で 前 → 後 · 赤枠 = 使わなかった画像 · 緑枠 = 使った画像 · 規則の全部は「⑤しくみ → 全体の構成 → 小元素の自動補完」",
                           processes.examples_panel({r.get("name") for r in items})),
        "procs": panel("procs", "全体の構成（詳しい図）", "場所ごとに全部の部品と矢印を 1 枚に · 大きいので、まずは上の「しくみの全体図」を", processes.architecture()),
        "queue": ADMIN_QUEUE,
        "items": panel("items", "ウォッチ項目", f'赤い「最新の記事」= {ADMIN_STALE_DAYS} 日以上 新しい記事なし · 主題と配色の見本は <a href="themes.html">テーマ見本</a>', _admin_items(items)),
        "emblems": panel("emblems", "小元素", '版面右上のステッカー · 種類ごとの目標枚数 · 見本：<a href="../testground/emblem-pop.html">はみ出し・立体 3 案</a>', _admin_emblems(items, data.get("emblem_run"))),
        "emblem-manage": panel("emblem-manage", "小元素の管理", "版面を選ぶ → 押して「どうしたい？」：同じ人の別の写真に替える · この写真で固定 · この人ごと外す", bg["manage"]),
        "votes": panel("votes", "投票", "👍 / 👎 · 前回の収集時点", _admin_votes(data.get("votes") or {})),
    }
    counts = _admin_counts(data)

    def nav(cur):
        return ('<nav aria-label="管理ページの切り替え"><ul class="admnav"><li><a class="adm-top" href="admin.html"'
                + (' aria-current="page"' if cur == "admin.html" else "") + '><span>← 管理のトップ</span></a></li>'
                + "".join(f'<li><a href="{f}"' + (' aria-current="page"' if f == cur else "") + f'><span>{m} {e(n)}</span></a></li>'
                          for f, m, n, _, _ in ADMIN_PAGES) + '</ul></nav>')

    def page(fname, title, ver, body, scripts):
        return _section_marks(f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{e(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}{HEAT_PAGE_CSS}{ADMIN_PAGE_CSS}{ADMIN_NAV_CSS}{processes.CSS}{overview.CSS}{livelog.CSS}</style>
{_live_head("admin", ver)}
</head>
<body>
<div class="page">
<header class="mast">
<div class="mtitle"><h1>{e(title)}</h1><span class="stamp">ウォッチリスト通信 · 自動更新</span></div>
<div class="tools"><div class="meta"><small>更新</small><b>{e(updated)}</b></div></div>
</header>
<a class="back" href="./">← ウォッチリスト通信に戻る</a>
{nav(fname)}
{body}
</div>
{scripts}
<script>{LIVE_JS}</script>
</body>
</html>
""", updated)

    js = (f'<script type="application/json" id="adm-cfg">{cfg}</script><script>{ADMIN_PAGE_JS}</script><script>{EMM_JS}</script>'
          f'<script>{overview.JS}</script><script>{livelog.JS.replace("__ACC__", sitedir.NAME)}</script><script>{processes.JS}</script>')
    hub = ('<p class="lede">収集・編集が止まっていないか、依頼や写真が溜まっていないか、どの作品の記事が少ないかを見るためのページです。下の 6 つから選んでください。'
           'データを変えることはできません（できるのは「今すぐ実行」で裏の仕組みを定時より早く動かすことと、小元素の「替える・固定・外す」だけ）。篇幅やウォッチ項目の変更は<a href="settings.html">設定ページ</a>で。</p>'
           '<ul class="admhub">' + "".join(
               f'<li><a href="{f}"><b><i>{m}</i>{e(n)}</b><span class="n{" warn" if counts[f][1] else ""}">{e(counts[f][0])}</span><small>{e(d)}</small></a></li>'
               for f, m, n, d, _ in ADMIN_PAGES) + '</ul>')
    move = json.dumps({i: f for f, _, _, _, ids in ADMIN_PAGES for i in ids})
    out = {"admin.html": page("admin.html", "管理ページ", "admin", hub, f"<script>{ADMIN_HUB_JS.replace('__MAP__', move)}</script>")}
    for f, m, n, _, ids in ADMIN_PAGES:
        body = "".join(S[i] for i in ids) + (dialogs if f in ("admin-now.html", "admin-system.html") else "")
        out[f] = page(f, f"管理ページ {m} {n}", f[:-5], body, js)
    return out
