# やることの列（harness/q.py が作る。手で書かない）

開いている 222（うち進行中 1）・店長待ち 2・止めた 0・済み 3

## 次の 30 個

- T-0001 [kpi] 【依頼・新規ユーザー 2026-11-11・最優先】新規ユーザーの通し点検を毎回（harness/board_kpi.py・ループの newuser の係）
- T-0229 [fix] 小元素の顔 32px（2/2）：届かない 35 枚の版面を新しい規則で選び直し、10 枚以下にする
- T-0004 [fix] 【依頼・新規ユーザー 2026-11-11】library_design（版面の主題・配色）を回す担い手がない
- T-0227 [visual] 小元素：幅の広い小元素のとき、スマホで「今週」の数字が次の行に折れる（dota2・绝区零）
- T-0005 [fix] 【依頼・新規ユーザー 2026-11-11】gate.py fire が push より前に走る
- T-0006 [fix] 【計画 2026-11-11 f1・最優先】guest の ux_check の残りの ✗：E15 主役がいない（漫威电影 Chris Hemsworth〔何人も写る 4・別人 3
- T-0007 [fix] 【計画 2026-11-11 f1】PENDING.md の Google OAuth の「Authorized domains」の記述が旧 `bzokpnbcjscbcehdxt
- T-0008 [fix] 【計画 2026-11-07】休止の札（SB_DEG_JS）を新サーバーの停止にも効かせる
- T-0223 [fix] 【T-0009 の 1】縦長の写真のカードの空きを数える点検（ux_check の tallHole）を小さいページで確かめ、前の数を出す
- T-0010 [visual] 【依頼】版面の記事の並べ方を「型を選ぶ」から「その日の記事の重さで組む」に変える・空きを残さない
- T-0011 [fix] 【計画 2026-11-06 plan1】402 が外れた日の「再測定 1 本」— 左写真カードの残り（上の【続き】①④と .pk.sb）・ux_check の test-a/b/
- T-0012 [fix] 【計画 2026-11-06 plan1】scroll_measure の数字を日に 1 回 Pages（Supabase は route.abort）で記録して退行を数える
- T-0013 [fix] 【計画 2026-11-06 plan1】PC 1400 の「写真の横の字」カード（.nx・.pk・.card.mini）にも sideGap と同じ点検
- T-0014 [visual] 【続き・2026-11-06 f1】スマホの左写真カードの残り：①本番で test-a・test-b・test-c の 390px を測る（いま Supabase 402 でログイ
- T-0017 [visual] 【計画 2026-11-06 plan2】制限中に『登録』を押したお客さまの画面を通して見る
- T-0018 [fix] 【計画 2026-11-06 plan2】毎日の記録を 1 本にまとめる
- T-0019 [visual] 【計画 2026-11-06 plan2】『写真の横の字』の点検を、同じ部品を使う全部の画面に（連動の範囲：同じ部品の画面）— 左写真カードの sideGap は店長・お客さまのト
- T-0020 [fix] 【依頼】最優先・今すぐ：係の PR が CI で赤になるのを止める（失敗メール）
- T-0021 [fix] 【依頼】スクロールの流畅性（一卡一卡）を直す
- T-0022 [fix] Ado の版面の小元素が 0 枚（別人を外したあと）— Ado は顔を出さない歌手
- T-0023 [fix] 402 通し点検の render が main でも赤（2026-11-05 15:5x JST f1f1 が origin/main で `fake402_check.py --
- T-0024 [fix] キャラの名簿に残る「集まり・役の名前」（情報、2026-11-05 f1f1）：スプラ 3 の Animals・King Salmonids（分類 Characters に入る集ま
- T-0025 [fix] お客さまの版面の外の小元素の残り（#919 のあと pages_served：Pages の外から出た画像のうち commons.wikimedia.org 18 件・thumb.
- T-0026 [fix] お客さまのページの「先頭の写真が置き場に無い」（#919 合併後の ux_check --fast：test-a 1400 33 版面・390 34、test-b front 1）
- T-0027 [fix] 【依頼】最優先：機能の直し（2026-11-05 本番の機能の確かめ）
- T-0028 [fix] 【依頼】2026-11-05 全体点検：19:00 JST まで 4 本を並べて直す
- T-0029 [fix] 本番の API 呼び出しの内訳（Actions／点検／本物の人）を毎日 1 行にする（plan2 2026-11-05）：測った事実（query_logs の edge_logs 
- T-0030 [fix] ux_check（点検）が本番へ出す Supabase 呼び出しに予算を付ける（plan2 2026-11-05）：測った事実＝点検由来の 24h は auth_enforced 
- T-0031 [fix] Actions の Supabase 読みを「工程をまたいで」減らす（plan2 2026-11-05）：測った事実＝Python-urllib の nav_schemes GET
- T-0032 [fix] docs/404.html を作り、打ち間違い・古い網址の人を入口へ戻す（plan2 2026-11-05）：測った事実＝docs/ 直下に 404.html が無く（ls doc

## 店長待ち

- T-0003 【依頼・新規ユーザー 2026-11-11】library_emblem.yml の 15 分の定時が実測 4〜6 時間に 1 回（harn — 2026-11-12T08:09:40+09:00 店長待ち：[?] 何を：library_emblem を GitHub の cron でなく pg_cron の tick（run_now）から起こすには、店長の PC の自前 Supab
- T-0016 【計画 2026-11-06 plan2】制限中（402）の札に「戻る目安」を出す — 2026-11-12T08:44:18+09:00 店長待ち：[?] 402 の札に戻る目安を出す段：旧クラウド Supabase の 402 は自前版への移行（docs/rules/local-pc.md）でもう起きず、前提の「期間リセッ
