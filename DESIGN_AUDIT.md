# 店長のページ デザイン点検（impeccable・Taste・Emil、2026-10-24）

対象：本番 https://cxelegy.github.io/Wishlist/home/ （コミット 9c63a03c）。生成元 `scripts/render.py`（CSS・NAV_STYLES・NAV_JS・FIT_JS・SHUFFLE_JS・EMB_JS・LIVE_CSS/JS・BUSY_CSS/JS・AUTH_CSS）・`scripts/likefx.py`（👍 の演出）。コードは読んだだけ（直していない）。

前提（守るもの）：DESIGN_PRINCIPLES A1〜A13、とくに **A4 P5 の手法**（硬い影 `--shadow`・1〜2.5° の傾き `--tilt`・平行四辺形の札 `--skew`・2px の枠・紙の色 `--paper`）と D5（見せ場は頭条のポスターだけ）。Taste の「許すもの」（shadow・button-fx・text-shadow・outlined-box・eyebrow・micro-label・palette-cream・emoji・gradient・off-centre）は直さない。

## 0. 点検したこと・道具の結果

| 道具 | コマンド | 結果 |
|---|---|---|
| impeccable detect | `impeccable detect --json da/home.html`（本番を保存した 2.4MB の html） | 1052 件。うち broken-image 790 は保存した html の相対パス・遅延読み込み（`<img>` に src なし）のせいで**本番の不具合ではない**。残り 262：low-contrast 107・undersized-ui-text 76・tiny-text 31・bounce-easing 23・wide-tracking 7・cramped-padding 6・dark-glow 3・organic-clip-path 2・pulsing-dot・radial-halo・skipped-heading・cream-palette・ai-color-palette 各 1 |
| Taste inspect | `inspect.mjs …/home/ --widths 1440,390 --allow …`（CHROME_PATH = taste/chrome.sh） | **FAIL 6・WARN 8**（前回 2026-10-24 朝の FAIL 15・WARN 9 から減った）。写真：`scratchpad/taste2/desktop-*.jpg`・`mobile-*.jpg`、数字：`taste2/report.json` |
| Emil（improve-animations） | recon → 8 分類で audit → コードの行で確かめて vet → 下の直し方 | 動きの決まりごと（令牌）がない、何度も起きる動きが 2 つ重い、reduced-motion の抜けが 2 つ、レイアウトを動かすアニメが 2 つ |

Taste の FAIL / WARN（許すもの以外）：headline-lines（1440 で 5 行・390 で 4 行）・hairline（`.pfoot` の 1.5px 線・欲しい物リストの点線）・contrast（「FRONT PAGE」1.2:1）・small-text（13px 未満 211 か所）・edge-text（390 の上の帯「スポーツ」が端から 1px）／WARN：size-count 20 段・body-size 15px・font-fallback Noto Serif JP・dashed 9・card-rows 2・ragged-edges 12 本・mixed-font-headline 1・no-footage（動画なし＝ニュースの版面なので弁護できる、直さない）。

写真で見えたこと（コードの数字では出ない）：
- **右上の `wl-auth`（店長のページ・見るだけ／はじめのページ／ログイン）が 1440 で版面の見出しの帯・話題度の数字・小元素の上に重なる**（desktop-page-02・03 の全コマ）。
- **390 の最初の画面で、右下に浮いた「はじめのページ／ログイン」がポスターの下の行（「ウォッチリスト通信・10.…」）を隠す**（mobile-fold）。
- 頭条の英語の見出しが黒い箱 5 段で、ポスターの左の欄がいちばん重くなる（日付 10.24 と見出しが競う）。

---

## 1. 見つけたこと（効き目の大きい順）

列：**決まり**＝どのスキルの何、**場所**＝関数・選択子、**今 → 直す**、**見た目**＝変わる（testground の見本をユーザーに見せてから）／変わらない（規則の直し、すぐ）。

### 1-1 浮いているボタン（wl-auth）が中身を隠す ― 変わる
- 決まり：impeccable layout（固定の部品が読むものを覆わない）・Taste「LOOK AT THE RENDER」（写真で見えたものは本物）。
- 場所：`AUTH_CSS` の `.wl-auth{position:fixed;top:10px;right:12px;z-index:90}`、`@media (max-width:560px){.wl-auth{bottom:12px} .wl-auth.away{…}}`。
- 今：PC は常に右上に固定（版面の帯の右端＝話題度・小元素の場所と重なる）。スマホは右下に固定、最初の画面からポスターの字に乗る。
- 直す（おすすめ）：**PC も `.away` を使う**（下へ読み進めている間はしまい、上へ戻る・ページの最上部で出す。スマホと同じ規則 1 つ）。スマホは**最初は報頭の `.tools` の行に置き（固定しない）、報頭が画面から出てから右下に浮かせる**。P5 の箱（2px 枠・硬い影）はそのまま。
- 確かめ：1440 で版面の帯の右上に何も重ならない・390 の最初の画面で字が隠れない（ux_check の写真）。

### 1-2 頭条の見出しが 5 段・見出しの長さに段がない ― 変わる
- 決まり：Taste house rule「見出しは 2 行まで」（ニュースの見出しの長さは選べないので、ここでは **3 行まで** を目標に置き直す）・impeccable typeset（長さに合わせて段を選ぶ）。
- 場所：`.top h2{max-width:600px;font:900 clamp(21px,2.2vw,31px)/1.55}`（`.top` の左の欄は 5fr ≒ 440px）、版面の `.hero h2{font-size:30px;-webkit-line-clamp:4}`、`.lead h2{28px}`。
- 今：英語 13 語の見出しが 1440 で 5 行（31px）、版面で 4 行（30px）、韓国語 9 語が 3 行。
- 直す：**見出しの文字数で段を選ぶ規則**（AI なし、render で数える）：かな・漢字換算 ≤24 字＝大（ポスター 30px／版面 30px）、≤44 字＝中（26px）、それより長い＝小（21px）＋ `line-clamp:3`。ポスターは中・小のとき見出しの欄を写真の下まで広げる（`grid-column:1/-1`）案と、段だけ落とす案の 2 つを見本に。黒い箱 `.hb` と傾き `--tilt` は残す。D2（見出し 16 字）と一緒に進めると効く。
- 行間：見出しの `line-height:1.55` は黒箱の間を空けるため。段を落とした後は 1.45 に（箱の上下 3px が詰まらない範囲）。

### 1-3 字の大きさが 20 段・読む字が 13px 未満 211 か所 ― 変わる
- 決まり：Taste size-count（5〜7 段）・small-text（読む字 13px 以上、HARNESS「直すもの」）・impeccable undersized-ui-text（札でも 11px 以上）・body-size。
- 場所：`CSS` 冒頭の `:root`（`--fs-label:11px;--fs-tag:10px` しか令牌がない）、残りは各選択子に直書き。数えた値（render.py の CSS と NAV_STYLES）：10・11・12・13・14・15・16・17・18・19・20・21・22・24・26・28・30・36・40・84（本番では 31・48・137 も）。
- 今 → 直す（**9 段の令牌**、比 ≒1.2、和文に合わせる）：

| 令牌（案） | 値 | 使う所 | いま混ざっている値 |
|---|---|---|---|
| `--fs-tag` | 11px | P5 の札・NEW・数の札（読ませない札だけ） | 10・11 |
| `--fs-meta` | 13px | 出典・日付の横・注・「整理待ち」・目次の件数 | 11・12・13・14 |
| `--fs-body` | 15px（見本で 16px も） | 本文・要約 `.blurb`・小さいカードの見出し | 14・15・16 |
| `--fs-h4` | 17px | 小さいカードの見出し・目次の今の駅 | 16・17・18・19 |
| `--fs-h3` | 21px | カードの見出し・照片墙の大 1 枚 | 20・21・22 |
| `--fs-h2` | 26px | 版面の大見出し（中）・棚の看板の大 | 24・26・28 |
| `--fs-h1` | 30px | 版面の題字 `.band .title`・ポスターの見出し（大） | 30・31 |
| `--fs-num` | 40px（Anton） | SAT の箱・話題度の大 | 36・40・48 |
| `--fs-display` | clamp(84px,9.5vw,164px)（Anton） | ポスターの日付だけ | 84・137 |

- とくに直すもの：`.from`（出典）11px → 13px、`.pfoot`・`.mast .stamp`・`.snote`・`.hx li small`・`.staste p`・`.nav .nsum` 11〜12px → 13px、`--fs-tag` 10 → 11px（`.when b` の NEW、`.mast .meta small`、`.nav .wm small`、`.nav .hm .hl`）。
- 等幅（JetBrains Mono）は数字の飾りに使っているだけ（`.nav .pill .new`・`.subhead small`・`.nav .nsum b`・`.mono`）。Taste「等幅はコードだけ」→ `font-variant-numeric:tabular-nums` の Noto Sans JP か Anton に替えれば **Web 字体が 1 つ減る**（tests/test_perf.py の字体の数にも効く）。
- 確かめ：inspect の size-count が 9 以下、small-text は札（aria-hidden・P5 の札）だけ、tests/test_design.py の「字号 ≥10px」を「≥11px・読む字 ≥13px」に。

### 1-4 目次の今の駅のカットインが scale(.3) から弾む・動きを減らす設定で止まらない ― 変わらない（手触りだけ）
- 決まり：Emil「scale(0) から出さない（0.9〜0.97）」「何度も起きる動きは減らす」・AUDIT 6（reduced-motion）。
- 場所：`NAV_STYLES["line"]` の `.nav .pill.on .ic{animation:cutin .2s cubic-bezier(.3,1.4,.5,1)}`、`@keyframes cutin{from{transform:rotate(-20deg) scale(.3);opacity:0}…}`。reduced-motion は `.nav *{transition:none!important}`（595 行）と `.nav .flame *{animation:none}` だけで **cutin は止まらない**。
- 頻度：スクロールで読んでいる版面が変わるたび（1 回の訪問で数十回、速く流すと連続で再開）。
- 直す：`from{transform:rotate(-12deg) scale(.86);opacity:0}`、`animation:cutin .16s cubic-bezier(.23,1,.32,1)`（行き過ぎなし）。`@media (prefers-reduced-motion:reduce){.nav .pill.on .ic{animation:none}}`。P5 のカットイン（傾き −7°・白フチ・硬い影）は残る。

### 1-5 小元素（ステッカー）の飛び出し：毎回くり返す・影の伸びが重い ― ほぼ変わらない
- 決まり：Emil AUDIT 1（くり返し見る飾りの動きは減らす）・5（transform / opacity だけ、filter を毎コマ描き直さない）・2（UI の出入りは ease-out、出るほうを速く）。
- 場所：`.emb-in{transition:transform .6s cubic-bezier(.2,1.5,.4,1),opacity .2s,--sx .35s ease-out .45s,--sy .35s ease-out .45s; filter:drop-shadow ×9}`、`.emb.out .emb-in{transition:transform .38s cubic-bezier(.6,0,.9,.4),opacity .3s ease-in .08s,…}`、`EMB_JS` の IntersectionObserver（上へ戻ると `.out`、また下へ来ると `.in` で毎回飛び出す）。impeccable の bounce-easing 23 件はこれ。
- 今：1 枚 0.6s の弾み × 版面の数 × 行き来の回数。`@property --sx/--sy` を動かすと 9 枚重ねの `drop-shadow` を 0.35s 毎コマ描き直す（GPU で動かない）。
- 直す：① **1 回の訪問で 1 版面 1 回だけ飛び出す**（`.out` に戻さない。`EMB_JS` で `io.unobserve(el)` を `.in` のあと）。② 影は最初から 8px（`--sx/--sy` の transition をやめる、`@property` も不要に）。③ 弾みは「めったに起きない喜び」なので残してよいが 0.6s → 0.42s、`cubic-bezier(.2,1.4,.4,1)`（likefx の `UP` と同じ値にそろえる＝令牌 `--ease-pop`）。④ `.out` の ease-in をやめるなら ①で不要。

### 1-6 読ませる字の色が 4.5:1 にわずかに届かない・札の下の写真なし枠の白字 ― 変わらない〜わずか
- 決まり：impeccable low-contrast・Taste contrast（4.5:1）。
- 場所と値：
  - `rgba(26,28,34,.62)`（`.nav .pill .cnt` など 5 か所）・`.62`〜`.7` の opacity の字（`.subhead small`・`.mast .stamp` `.65`・`.snote` `.75`）→ 紙の上で 4.48:1（39 か所）。**不透明度の下限を .72 に**（紙の上で ≒5.3:1）。`.nav .pill .new` の `.5` は件数の飾り → 札扱いなら残す、読ませるなら .72。
  - `.pic .ph`（写真がない枠の作品名）：白字 × 板块色＋墨 34%。ゲームの黄緑 #D7F03C で 1.3:1（墨を足しても ≒2.3:1）、グレー #C7C7C7 1.7:1。→ **板块色から白字／墨字を規則で選ぶ**（sections.yaml の色は生成時にわかる。AA を満たすほう）か、墨を 34% → 55%。A7（見えないものの代わり）なので読めないと意味がない。
  - 「FRONT PAGE」（`.nhead .pill .cnt` の金色 11px）：黒い斜めの箱 `::before` の外へはみ出して紙の上に乗る（1.2:1）。→ `.nav .nhead .pill.on{padding-right:18px}` で箱の中に収めるか、英字の札をやめる。
  - 版面の帯の副題（例：#F1DECF on #DD8355 2.2:1、テーマの縞の上）：テーマ（templates/*.css）の帯の字の対比はテストがない → tests/test_design.py の対比の検査を「テーマの `--fg` × 帯の地」まで広げる。

### 1-7 動きの令牌がない（手書きの曲線 10 種）・レイアウトを動かすアニメ ― 変わらない
- 決まり：Emil AUDIT 7（曲線と長さは共有の令牌）・5（`left` / `width` を動かさない）。
- 場所：手書きの曲線 `(.2,1.5,.4,1)` `(.6,0,.9,.4)` `(.2,.9,.3,1)`×4 `(.2,.8,.2,1)` `(.2,1.6,.4,1)` `(.3,1.4,.5,1)`、likefx の `UP (.2,1.4,.4,1)` `BACK (.6,0,.9,.5)`。長さは .1/.12/.15/.18/.2/.25/.38/.4/.5/.6/1s。
  - `BUSY_CSS`：`.busy .br{animation:wlbusy 1.8s ease-in-out infinite alternate}` `@keyframes wlbusy{to{left:76%}}`（**left を無限に動かす**＝毎コマ組み直し）、`.busy .bf{transition:width 1s}`。
  - 管理ページ `.pbar i`：`pb-run{left:-40% → 100%}`・`transition:width .6s ease`（同じ形）。
- 直す：`:root` に動きの令牌を足す
  `--ease-out:cubic-bezier(.23,1,.32,1); --ease-in-out:cubic-bezier(.77,0,.175,1); --ease-pop:cubic-bezier(.2,1.4,.4,1); --dur-press:120ms; --dur-ui:180ms; --dur-pop:420ms`。
  `.busy .br` は `left:0;width:24%` を固定し `@keyframes wlbusy{to{transform:translateX(316%)}}`（76%÷24% ≒3.17）、`.bf` は `width:100%;transform-origin:0 50%;transform:scaleX(var(--bp-n,0));transition:transform 1s var(--ease-out)`（BUSY_JS が `--bp` を 0〜1 で入れる形に）。管理ページも同じ。見た目は同じ。

### 1-8 ホバーの浮き上がりが指でも残る・押した感触が 2 つのボタンだけ ― 変わらない（PC）／押したときだけ変わる
- 決まり：Emil「ホバーの動きは `(hover:hover) and (pointer:fine)` の中」「押せるものには押した感触（0.95〜0.98 か、P5 なら影の分だけ沈む）」・AUDIT 2（押した反応 100〜160ms、ease-out）。
- 場所：`.wc:hover{transform:rotate(var(--r)) translate(-2px,-2px)}`・`.tape:hover{translateY(-4px)}`・`.top:hover .frame{rotate(-1deg) translateY(-2px)}`・`.wcard:hover .wimg img{scale(1.04)}` は全部ゲートなし（スマホで押して戻ると浮いたまま）。`:active` は `.shuffle,.mastwish` だけ（`transform:translate(3px,3px);box-shadow:none`＝P5 の沈み、良い）。transition は時間だけで曲線なし（＝`ease`。ホバーは ease で正しい）。
- 直す：上の 4 つを `@media (hover:hover) and (pointer:fine){…}` に入れる。P5 の沈みを**硬い影を持つ押せるもの全部**に：`.mastset,.smore,.hx-more,.shelfbox>summary,.wl-auth>button,.wl-auth>a.new,.navwish` に `:active{transform:translate(2px,2px);box-shadow:1px 1px 0 var(--ink)}`、`transition:transform var(--dur-press) var(--ease-out),box-shadow var(--dur-press) var(--ease-out)`。👍👎（`.vt button`）は skew があるので `:active{transform:skewX(var(--skew)) scale(.94)}`。

### 1-9 👍 の演出：毎回 0.8〜1.1 秒・動きを減らす設定でも拇指が 1.45 倍 ― 変わる（2 回目以降だけ）
- 決まり：Emil の頻度表（1 日に数十回押すものは減らす）。ただし **20 種の演出は決定事項（A3・TEMPLATES）なので消さない**（improve-animations の Hard Rule 5）。
- 場所：`likefx.FX_JS` の `MOTION`（pop 760ms … float 1100ms、粒・擬音・confetti）、`go` の前に `btn.animate([{scale:1},{scale:1.45},{scale:.9},{scale:1}],{duration:320,easing:'ease-out'})` は `reduce` の判定より前（48 行）。
- 今：店長は 623 票（1 日数十回）。毎回画面いっぱいの演出が 1 秒前後、押した直後に次のカードへ行きにくい。
- 直す：① 同じ訪問で 2 回目以降（または前の演出から 20 秒以内）は**短い版**（拇指のポップ 1.25 倍・粒 1 回・合わせて 400ms 以下、擬音なし）、最初の 1 回だけ全部。② `reduce` のときは `btn.animate` も scale をやめて色だけ（`aria-pressed` の塗りがすぐ出るので足りる）。③ 演出中も次のボタンを押せる（`pointer-events:none` は今どおり）。

### 1-10 細かいもの（まとめて 1 段で）
- **Noto Serif JP を宣言しているが読み込んでいない**（`--font-serif`、templates の ink・magic・cafe など 7 つが題字に使う）→ 今は OS の明朝に落ちる。おすすめ：`--font-serif:'Hiragino Mincho ProN','Yu Mincho','Noto Serif JP',serif` と OS の明朝を先に書いて「意図した落ち方」にする（字体を増やさない、test_perf.py を守る）。変わらない。
- **細い線・点線**：`.pfoot{border-top:1.5px solid}`・`.swish li{border-bottom:1px dashed var(--hair)}`・`.nav .nslot::after` 1px。P5 の線は 2px の墨（`.sbox h4` と同じ）→ `.pfoot` は 2px に、欲しい物の行は点線をやめ間を 8px に（紙と `--card` の段で分ける）。わずかに変わる。
- **英字の札の字間 .12〜.2em**（impeccable wide-tracking 7）：英字の小さな札（P5 の micro-label、許すもの）は残す。和文の本文・見出しに .1em 以上がある所（`.navwish` .1em・`.band .sub` .12em）は .04em に。わずかに変わる。
- **上の帯「スポーツ」が画面の端から 1px**（390、横に送る帯）：横スクロールの合図として切れているのは弁護できる。`scroll-padding-inline:16px` と最後のタブの後ろ 16px の余白で、止まったとき端に字が付かないように。変わらない。
- **見出しの段の飛び**（h2「ほかの注目ニュース」→ h4「これからの予定」）：h3 に。変わらない。
- **更新の帯 `.wl-live` が瞬間で出る・消える**（`bar.hidden` の付け外し）→ Emil「出どころのある部品は動きで説明」：`@starting-style{opacity:0;transform:translate(-50%,16px) rotate(var(--tilt))}`、`transition:opacity 220ms var(--ease-out),transform 220ms var(--ease-out)`、消えるときは 150ms（出るより速く）。reduced-motion は opacity だけ。少し変わる（見本不要の範囲だが、出す段で 1 枚写真）。
- **`.fresh` の枠の点滅 1.6s × 3 回**：outline の色を 3 回変える＝毎コマ描き直しは軽いので可。4.8 秒は長い → 2 回に。
- **wl-auth のしまう動き** `transition:transform .25s ease,opacity .25s ease` → しまうときは `180ms var(--ease-out)`、出すとき `220ms`。

### 1-11 これは今のままでよい（Emil「すでに正しい」も結果のうち）
- 目次の枠の移動：`transform` だけ・`.18s cubic-bezier(.2,.9,.3,1)`・高さは即座（コメントのとおり GPU に優しい）。曲線を `--ease-out` の令牌に替えるだけ。
- スクロールの吸着（`FIT_JS` の `snap`）：CSS scroll-snap を使わず 72px 以内だけ・`scrollend`・PC だけ・入力中と dialog 中はしない・reduced-motion で `auto`。良い作り。
- 押した感触 `.shuffle:active,.mastwish:active`（影の分だけ沈む）は P5 らしく正しい。これを全部に広げる（1-8）。
- 炎の演出（`NAV_FLAME=False` で止まっている）は保留中なので点検しない（PENDING.md）。`hvpop`・`quake` も炎があるときだけ動く。
- 照片墙のカードの不ぞろいの傾き（`--r` −1.2〜1.1°）・ポスターの倍の影（D5）は A4・D5 の決定どおり。

---

## 2. P5 の作りの中での磨き方（守るものを変えずに）

| P5 の作り | 今 | 磨き方 |
|---|---|---|
| 硬い影 `--shadow` 4px／`--shadow-l` 8px／ポスター 10+20px | 影の大きさが 2・3・4・5・6・8・10px と手書き | 影も 3 段の令牌に（`--shadow-s:3px 3px 0`・`--shadow`・`--shadow-l`）。押すと「影の分だけ沈む」を全部のボタンで同じに（1-8） |
| 傾き `--tilt` −1.5°、ポスター −2.2° | 見出し・枠・カードで −3〜+1.1° が混ざる | 見出しの箱は `--tilt` だけ、カードの不ぞろいは ±1.2° 以内（今どおり）。**見出しが長いとき傾いた黒箱が 4〜5 段になると傾きが「崩れ」に見える** → 1-2 で 3 段まで |
| 平行四辺形の札 `.tg` `--skew` −8° | 札の字が 10〜14px の 4 種 | 札は `--fs-tag` 11px と 13px の 2 種に。impeccable の cramped-padding（札の上下に余白なし）は P5 の詰めた札として許す |
| 2px の墨の枠 | 1px・1.5px・2px・点線が混ざる | 枠は 2px（大）と 1.5px（写真の枠）の 2 種。1px の線と点線はやめ、紙と `--card` の段で分ける（Taste の hairline） |
| 紙の色 `--paper` `--sheet` `--card` | 良い | 読ませる灰色の字は不透明度 .72 以上（1-6） |
| 英字の飾り（WORKS・GAMES の透かし、FRONT PAGE・UPCOMING） | 透かしは aria-hidden で装飾（可）、FRONT PAGE は箱から出て読めない | 透かしは今のまま。札として出す英字は箱の中に収める |

---

## 3. Emil の書式（Before / After / Why）

| Before | After | Why |
| --- | --- | --- |
| `.nav .pill.on .ic{animation:cutin .2s cubic-bezier(.3,1.4,.5,1)}`、`from{scale(.3)}` | `.16s cubic-bezier(.23,1,.32,1)`、`from{rotate(-12deg) scale(.86);opacity:0}`、reduced-motion で `animation:none` | スクロールのたびに起きる。ほぼ 0 から弾ませない |
| `.emb-in{transition:transform .6s cubic-bezier(.2,1.5,.4,1),…,--sx .35s,--sy .35s}` ＋ 戻ると `.out` | 1 版面 1 回だけ `.in`（`io.unobserve`）、`transform .42s var(--ease-pop)`、影は最初から 8px | くり返す飾り・filter の毎コマ描き直し |
| `.emb.out .emb-in{transition:transform .38s cubic-bezier(.6,0,.9,.4)}` | （上で不要） | UI に ease-in を使わない |
| `@keyframes wlbusy{to{left:76%}}` infinite | `to{transform:translateX(316%)}` | left は毎コマ組み直し |
| `.busy .bf{transition:width 1s}` | `transform:scaleX(var(--bp-n));transition:transform 1s var(--ease-out)` | width は組み直し |
| `.wc:hover{transform:…translate(-2px,-2px)}` ほか 4 つ | `@media (hover:hover) and (pointer:fine){…}` | 指で押すと浮いたまま残る |
| `:active` が `.shuffle,.mastwish` だけ | 硬い影のボタン全部に `translate(2px,2px)`＋影 1px、`120ms var(--ease-out)` | 押せるものは押した感触 |
| 👍 毎回 760〜1100ms | 2 回目以降は ≤400ms の短い版 | 1 日数十回押す |
| `btn.animate(scale 1→1.45→.9→1)` が reduce でも動く | reduce のときは色だけ | 動きを減らす設定 |
| `.wl-live` を `hidden` で瞬間に出し入れ | `@starting-style` から 220ms で上がる、消えるのは 150ms | 出どころを動きで説明・出るより消えるを速く |
| 曲線 10 種・長さ 11 種を手書き | `--ease-out` `--ease-in-out` `--ease-pop` `--dur-press` `--dur-ui` `--dur-pop` | 令牌にそろえる |

足りない動き（足すもの、多くて 2 つ）：① `.wl-live` の入り（上）。② 「気になるかも？」の「入れ替え」で次の束が瞬間に替わる → 次の束のカードを 40ms ずつずらして opacity＋translateY(8px) で出す（`--dur-ui`、操作は止めない）。どちらも「めったにない」側なので許される。

---

## 4. 直す段の案（BACKLOG にそのまま貼れる形）

- [ ] 動きの令牌と GPU に優しい形（見た目は変わらない） — `:root` に `--ease-out:cubic-bezier(.23,1,.32,1)`・`--ease-in-out:cubic-bezier(.77,0,.175,1)`・`--ease-pop:cubic-bezier(.2,1.4,.4,1)`・`--dur-press:120ms`・`--dur-ui:180ms`・`--dur-pop:420ms` を足し、render.py・likefx.py の手書きの曲線を置き換える（`grep -c "cubic-bezier(" scripts/render.py` が令牌の定義だけになる）。更新中の帯 `.busy .br` と管理ページ `.pbar` の `left`・`width` のアニメを `transform` に。impeccable detect の bounce-easing・Taste の結果が前より増えない、1400 / 390 の写真で帯の見た目が同じ
- [ ] 動きを減らす設定とスマホのホバーの抜けを埋める（見た目は変わらない） — 目次のカットイン（`cutin`）を `scale(.86)` から 160ms・`--ease-out`・reduced-motion で止める、`.wc` `.tape` `.top .frame` `.wcard` のホバーを `(hover:hover) and (pointer:fine)` の中へ、👍 の `btn.animate` を reduce では色だけに。Playwright で `reducedMotion:'reduce'` を付けて開き、`getAnimations()` に transform の動きが残らないこと
- [ ] 小元素は 1 版面 1 回だけ飛び出す・影を伸ばさない（ほぼ変わらない） — `EMB_JS` で `.in` のあと `unobserve`、`.emb-in` の `--sx/--sy` の transition と `@property` をやめ影を最初から 8px、弾み 0.6s → 0.42s `--ease-pop`。Chrome の Performance で版面を行き来しても「Paint」が版面ごとに 1 回だけ、testground に前後の動画（またはコマ送りの写真）を置く
- [ ] 押した感触を全部のボタンにそろえる（押したときだけ変わる） — 硬い影を持つ押せるもの（`.mastset` `.smore` `.hx-more` `.shelfbox>summary` `.wl-auth>button` `.wl-auth>a.new` `.navwish` `.vt button`）に P5 の沈み（`translate(2px,2px)`＋影 1px、`--dur-press` `--ease-out`）。testground に「押した瞬間」の写真を並べた見本 → ユーザーに見せて決めてもらってから本番
- [ ] 浮いているボタンが中身を隠さない（見た目が変わる） — PC も読み進める間 `wl-auth` をしまう（`.away` を全幅で）、スマホは最初は報頭の行に置き報頭が出てから浮かせる。testground に今と案の 1400 / 390 の写真 → ユーザーに見せてから本番。本番の写真で版面の帯・話題度・ポスターの字に何も重ならない（ux_check に「固定の部品が字に重なる」を足す）
- [ ] 見出しの長さで字の段を選ぶ（見た目が変わる、D2 と一緒に） — ポスター・版面の大見出しを文字数で 30 / 26 / 21px の 3 段（render で数える、AI なし）、`line-clamp:3`。ポスターは「見出しを写真の下まで広げる」案と「段だけ落とす」案の 2 つを testground に → ユーザーに見せてから本番。inspect の headline-lines が 1440・390 とも「3 行を超える見出し 0」
- [ ] 字の大きさを 9 段の令牌に・読む字 13px（見た目が変わる、既存の「字の大きさの段を減らす見本」を置き換え） — `--fs-tag 11`・`--fs-meta 13`・`--fs-body 15/16`・`--fs-h4 17`・`--fs-h3 21`・`--fs-h2 26`・`--fs-h1 30`・`--fs-num 40`・`--fs-display`。出典 `.from` ほか 11〜12px の読む字を 13px に、等幅の数字を tabular-nums に替えて JetBrains Mono を外す。testground に今と案（本文 15 と 16 の 2 つ）を 1400 / 390 で → ユーザーに見せてから本番。inspect の size-count ≤9・small-text は札だけ・tests/test_design.py に「読む字 ≥13px」
- [ ] 対比と細い線の直し（ほぼ変わらない） — 読ませる灰色の字の不透明度を .72 以上、写真なし枠 `.pic .ph` の字色を板块色から規則で白／墨に、「FRONT PAGE」を箱の中へ、`--font-serif` を OS の明朝から始める、`.pfoot` を 2px・欲しい物の点線をやめる、テーマの帯の字の対比を tests/test_design.py で検査。inspect の contrast・hairline・font-fallback が 0、impeccable の low-contrast が札・装飾（aria-hidden）だけ

（既存の BACKLOG「AI っぽさの点検で見つかった本物の不具合を直す」は、上の「対比と細い線」「見出しの長さで字の段を選ぶ」に分けて置き換えると、見せる段と見せない段が分かれる。）
