# 引き継ぎ：クラウドのハーネスの係 → 店長の PC の Claude Code（2026-11-07）

**これを最初に読む。** 店長が「作業を全部 PC に任せたい」と決めたので、クラウドの「デフォルト環境」で動かしていたハーネスの係（と入口の会話）の中身を、GitHub だけで引き継げるように書く。
会話の記録（約 670 MB）はクラウドのコンテナにしか無いが、**結論と決まりは全部 GitHub にある**。PC の Claude は、下の「読む順」で足りる。

## 主セッション（2026-11-07，用户定的）

店長の PC の会話が主セッション。ハーネスのループは続けない。AI 編集だけクラウドで続け、連絡帳でつなぐ（`docs/rules/local-pc.md`）。この文書のループを回す説明より、こちらが優先。

## PC の用意（2026-11-07 済み）

- clone は `D:\Claude\Wishlist`。Python は `.venv`、`python3` は `~/bin/python3` が `.venv` へ渡す（Bash から使う）。`gh` は `~/bin/gh.exe`。
- `BACKLOG.md` は 500 KB を超えるので、全部を読まない。先頭と、必要な段だけ検索して読む（小さくする段がある）。
- 開いている古い PR（#771・#905・#915・#917）は「係の PR は 0」の数に入っていなかった。合併の前に中身を確かめる。

## 0. 読む順（PC の Claude は上から）

1. このファイル（全体と PC での回し方）
2. `CLAUDE.md` と `WORKING.md`（毎回守る決まり。`docs/rules/*.md` は触る分野の分だけ）
3. `HARNESS.md`（ハーネスの設計：1 回の進め方・ループの続け方・聞くこと・確かめ方）
4. `BACKLOG.md`（やることの一覧。`[ ]` 未着手・`[~]` 進行中・`[?]` 店長待ち・`[x]` 済み）と `PROGRESS.md`（日ごとの記録）
5. `harness/audits/2026-11-05-system.md`（全体点検の証拠）・`harness/audits/2026-11-05-scroll.md`（スクロールの測定）
6. `harness/lanes/next.md`（次に起こす係の台本）

## 1. 役割（クラウドでやっていたこと）

| 役 | 何をする | 触らないこと |
|---|---|---|
| 店長（ユーザー） | 決める。見て判断する（テストグラウンドの見本）。鍵・お金・DB の形・消すことの許可 | — |
| 入口の会話 | 店長と話す。聞いたことを BACKLOG の【依頼】に書いて PR にする。本番を測って依頼にする | 直さない。合併しない（二重にならないため） |
| ハーネスの係 | 係（ワークフロー）を起こして見回る。係の PR の CI を**自分で**読んで合併する。ディスク・worktree の後片付け。店長・入口への報告 | 店長の許可が要ること |
| 作る係（ワークフローの中） | 1 段を作る→PR→CI→合併→本番で確かめる。**別の目**の係が確かめて、落ちたら直す（2 回まで） | 持ち主のいる `[~]` を取らない |

PC では、入口とハーネスの係を同じ Claude Code の会話にまとめてもよい。ただし「聞いた→書く」と「作る」は分ける（`HARNESS.md`「会話は入口、作るのはループ」）。

## 2. PC での回し方（クラウドとの違い）

- **場所**：PC にこのリポジトリを clone し、PC の Claude Code で開く。DB は PC の自前版 Supabase（`https://elegy.tailc8cfff.ts.net`、接続先は `items.yaml` の設定）。旧 Supabase（`bzokpnbcjscbcehdxtjq`）は 402 で止まった旧側の話。
- **係の起こし方**：`Workflow` ツールで `.claude/workflows/harness-forever.js` を `scriptPath` に（`args: {max, lane, scratch}`）。`lane: "request"` は【依頼】の段だけ。台本の下の「この回の仕事」だけを差し替えた版が `.claude/workflows/harness-lane-cloud-example.js`（クラウドで使った例。PC では道具名とパスを読み替える：GitHub は `gh` か git、`/home/user/Wishlist` はこのフォルダ、`scratch` は PC の一時フォルダ）。
- **走っている係は途中で指示を足せない**。指示を変えたいときは、BACKLOG の文を PR で直して合併する（係は段ごとに BACKLOG と `docs/rules/` を読み直す）か、止めて起こし直す。止まった係（書き込みが 15 分ない）は `resumeFromRunId` で続きから。
- **見回り**：クラウドの `send_later`（予約）は PC では使えない。PC の定期実行（Windows のタスクスケジューラ、または Claude Code の定期の仕組み）で、次を見る：①動いている係の最後の書き込み ②開いている PR の `check_runs` ③ディスクの空き（80% 超で worktree の後片付け）。
- **重い仕事は同時に 1 つまで**（5 時間の枠で止まった経験：2026-11-05）。モデルの指定は店長が決める（`model:` を台本で切り替える）。
- **PC で最初に 1 回**：`git config core.hooksPath .githooks`（`.githooks/pre-push` が check_arch・変えた所の試験・render の JS 文法を push の前に回す）。node と playwright(chromium) を入れる（`pip install -r requirements.txt` と `playwright install chromium`）。

## 3. 合併のやり方（毎回これ）

1. PR を出す前に手元で `python scripts/check_arch.py origin/main` と変えた scripts の試験。図を変えない PR は説明に**簡体字で**「架构图：不用改（理由）」の 1 行（「架構図」だと通らない）。
2. CI は 2 つ：「测试 · 网页能生成」（約 10〜20 分）と「402 通し点検」（約 1〜3 分、fake402.yml）。**両方が緑なのを `check_runs` で自分で読む**（係の「CI 緑」の自己申告を信じない）。必須チェックにはしていない（main へ Actions が直接 push するため）。
3. 合併は `expectedHeadSha` つきの squash。衝突は `origin/main` を取り込み、BACKLOG・PROGRESS は**両方を残す**。
4. 合併したら本番を確かめる（`harness/browser.py` の launch で 1400/390、写真は Pages の写しから、各段 1 回・timeout 付き）。

## 4. 守る制約（会話にだけあって md に薄かったもの）

- **Pro にしない**（Supabase）。無料枠の決まりは `docs/rules/free-tier.md`。いまは自前版 DB なので 402 は旧側の話。
- DB の形を変える・消す・鍵・お金は、作らずに `[?]`（木の形・案ごとの良い点と困る点・おすすめ）で店長に聞く。足すだけは可。
- 答え待ちの段（審査の見本の続き・欲しい物・製品の先頭の本番化・顔の大きさの 2 段目）は飛ばす。
- 個別に直さない（test-a だけの手直しをしない）。直すのは規則。同じ型を数えて全部直す（`HARNESS.md`「その箇所だけ直さない」）。
- 本物のお客さまを招く前に、DB の窓口（anon で呼べる関数）を絞る。いまは「テストだけ」なので保留（BACKLOG の `[?]`）。
- `pkill -f` は使わない（自分のシェルを止める）。worktree は終わったら消す（`HARNESS.md`「作業ツリーの後片付け」）。

## 5. ここまでの流れ（2026-10-23 〜 11-07）

- **10/23〜**：ハーネスの考え（`HARNESS.md`）。作る→確かめる→直す→合併のループを BACKLOG で回す。
- **11/2〜11/5：無料枠の危機**。写真の配信が Supabase の転送量を食い、11/5 から 402 になる見込みになった。写真・小元素を Pages の `/p/` から配る形に移し（photo_cache・manifest）、Supabase の読みは写しから（sbread・browser.py の止め）、402 のときは休止の札（SB_DEG_JS）、Actions は最後の写しで回り続ける形にした。#782〜#900 付近。
- **11/4〜5：CI の整理**。402 通し点検（fake402）を別 workflow に分けた（#894・#896・#898）。pre-push と JS の文法・例外 0 の確かめ（#941）。402 通し点検が全 PR で赤だった根を 2 つ直した（#945）。push の取り合いを共通の `push_main.py` に（#921・#940）。公開ログからお客さまの名前を消した（#922）。
- **11/5：機能の確かめ**。本番で機能を確かめ、壊れを直した：test-a の小元素 0（#919）、永遠の読み込み直し・記事 1 本・設定・ログアウト・話題度（#926・#934）、お客さまの版面の AI 編集の入口（#928・#931・#946）、E15 の公式の立ち絵（#910〜#936・#947）、本 4 の名簿（#924・#933・#942）。
- **11/6**：スマホの左写真カード（#952〜#955）、スクロールの測定（#948）。11/5 23:40 UTC から Supabase が 402（休止の札は 7 ページとも出た）。
- **11/7**：DB を店長の PC の自前版 Supabase に引っ越し（#959）。402 は解消。

## 6. 次にやること（順番。詳しくは BACKLOG の先頭と `harness/lanes/next.md`）

1. **「記事の重さで組む」見本**（案 C：縦長の写真を細くして見出しの列を広げ、右下の余白を次のニュース・要約で埋める）を、テストグラウンドに本物のデータで前／後（1400/390・空き面積の数字つき）で出す。**店長が見て決める**までは本番に入れない。
2. **スクロールの流畅性**（`harness/audits/2026-11-05-scroll.md` の原因 8 つ。効く順：content-visibility → 画像ごとの IntersectionObserver を共有 1 個に → NAV_JS の scroll 書き → AUTH_JS のスマホ scroll）。作る前に `.claude/skills/` の core-web-vitals・performance・animation-performance 等を読む。前／後を `harness/scroll_measure.py` で測る。
3. **引っ越しの後片付け**（BACKLOG に 3 つ）：①写真の配信の毎日の見張りを新サーバーの死活（`/auth/v1/health`）に替える ②旧 Supabase の ref を指す残りを `items.yaml` の接続先から読む形に直す（`scripts/choice_sample.py`・`face_sample.py`・`layout_ba.py`、`harness/emblem_pick_rules.py`・`fake402_check.py`、`.github/workflows/requests.yml`、`hermes/config.example.yaml`、`CLAUDE.md`・`LOGIN.md`・`PENDING.md`）③休止の札を新サーバーの停止（5xx・接続失敗）にも効かせる。
4. 残りの機能の直し：機能 C④（AI 編集の入口）の本番の確かめ、機能 A の残り（Q… の小元素が `/p/` に無いときの文字の札）、機能 D（pg_cron から起こす）、本 1 ②〜⑤・本 2・本 3 ④⑤・本 4 の残り（浦原＝夜一・BLEACH の枚数・E8）、Ado の小元素 0 枚。
5. `live_*` の書き込みの数え直し（係を止めた静かな日の 24 時間で。目標 log 250・status 450・report 200 以下）。

## 7. 店長が決めること

- `git config core.hooksPath .githooks` をどの PC で有効にするか（pre-push を必ず回す）。
- Reddit・TMDB の鍵を Actions の Secrets に入れるか（`[?]` F12）。
- 設定ページの残り 2 つ（render の起動をまとめる・画面の言語）を作るか（F4）。
- GitHub Actions の収集などを PC の自前の実行環境（self-hosted runner）に移すか。PC が止まると収集も止まる。
- 本物のお客さまを招く前に DB の窓口を絞る件（保留中）。

## 8. 予約（クラウド側の状態）

- ハーネスの係の予約は全部止めてある（「写真の配信の毎日の見張り」は無効）。ほかの会話の予約（公募メール・JevInvest・期限ボードなど）は別の仕事なので触らない。
- PC では、上の「見回り」と「新サーバーの死活の見張り」を OS の定期実行で作り直す。

## 9. 手元にしか無かったものの保存

- `ux_check` の「見えるのに押せない入口を数える点検（DEAD_JS）」のコミット（2026-10-26）は GitHub の `backup/f1f1-hf7-dead-js` に保存した。まだ main には無い。使うなら main を取り込んでから PR に。
- 係の台本は、リポジトリの `.claude/workflows/harness-forever.js`（本体）と `harness-lane-cloud-example.js`（クラウドで使った例）、次の台本の文は `harness/lanes/next.md`。
