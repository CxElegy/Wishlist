---
name: wishlist-harness
description: ウォッチリスト通信（CxElegy/Wishlist）のハーネスを 1 段進める。BACKLOG.md の次の段を作る → テスト → PR → CI → 合併 → 本番で確かめる → BACKLOG・PROGRESS を更新。1 時間ごとの定時で呼ぶ。
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    category: software-development
    tags: [harness, wishlist, github, supabase]
required_environment_variables:
  - name: GITHUB_TOKEN
    prompt: CxElegy/Wishlist に push・PR・合併できる GitHub のトークン
    required_for: git push・gh pr
  - name: WISHLIST_DIR
    prompt: リポジトリを置いた場所（例 ~/Wishlist）
    required_for: すべて
---

# ウォッチリスト通信のハーネス（Hermes 版）

決まりの本体はリポジトリの `HARNESS.md`・`CLAUDE.md`（詳しい仕様は `docs/rules/*.md`）・`WORKING.md`・`BACKLOG.md`。このスキルは手順だけ。
会話・コミット以外のユーザー向けの文章は日本語。

## When to Use

- 定時（1 時間ごと）に起こされたとき、または Discord で「次の段を進めて」と言われたとき。
- 1 回で 1 段だけ進める。

## Procedure

1. `cd $WISHLIST_DIR && git fetch origin main && git checkout -B hermes/step origin/main`。
   `HARNESS.md`・`BACKLOG.md`・`PROGRESS.md`・`CLAUDE.md`・`WORKING.md` を読む（毎回。決まりはよく変わる）。
2. 作る係は 1 つだけ：`hermes/ACTIVE` が main に無ければ、何もせず「Hermes は待機中」と返して終わる（いまは Claude のループが作る係）。
3. `BACKLOG.md` の `[~]` が 3 時間以内に始まったものなら重ねずに終わる。なければ上から最初の `[ ]` を `[~] …（開始 日時 Hermes）` にして、その 1 行だけの PR を出して合併する（ほかの係に取られないように）。
4. 作る：その段の「できたと言える条件」まで。HARNESS.md の「一番大事な決まり」を必ず守る：
   - test-a・test-b などを個別に直さない（データの手直し・特定のアカウントの分岐は禁止）。直すのはいつも規則。
   - ログインしたお客さまはだれでも店長と同じ P5 の枠組み。違うのは中身だけ。素の箱を出さない。
5. 確かめる：`python -m unittest discover -s tests`、`python scripts/check_arch.py origin/main`（scripts/*.py か workflow を変えたら `scripts/processes.py` も変える）。
   画面を変えたら Playwright で 1400 / 390 px を撮り、test-a（多い）・test-b（1 つ）・test-c（0 個）を並べて見る。
6. PR：`git push -u origin hermes/step` → `gh pr create --fill`（本文は日本語で何を・なぜ・確かめたこと）。生成物の `docs/home/` は PR に入れない。
   `gh pr checks --watch` が緑なら `gh pr merge --squash --delete-branch`。赤なら直して push（3 回落ちたら BACKLOG を `[?]` にして Discord で聞く）。
7. 本番で確かめる：Actions の結果、Supabase の行（MCP の supabase で読むだけ）、https://cxelegy.github.io/Wishlist/home/ 。
8. `BACKLOG.md` を `[x] …（PR の網址、日付）`、`PROGRESS.md` に 1 行（日付・何をした・PR・確かめた結果・次）、気づいた次の段を足して PR・合併。
9. Discord（ホームチャンネル）に 3 行で報告：何をした・PR・次。

## Pitfalls

- 本番のデータベースの形を変える・行を消す・開關を変えるときは、作らずに `BACKLOG.md` を `[?]`（何を・なぜ・どう戻すか、案ごとの良い点・困る点・おすすめを木の形で）にして Discord で聞く。
- 答えが設計書から決まることは聞かない。説明のない言葉（「鍵」「面」など）を使わない。
- `pkill -f` は使わない（PID で止める）。置き換えは 1 か所だけかを確かめてから。
- main に直接 push しない（必ず PR）。他人の枝の履歴は書き換えない。
- お客さまの名前・メールをログ・PR・Discord に書かない（数だけ）。

## Verification

- PR が合併され、CI が緑、本番の画面とデータベースで動いたことを確かめた。
- `BACKLOG.md`・`PROGRESS.md` が更新され、Discord に報告した。
