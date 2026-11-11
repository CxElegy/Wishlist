# ハーネス v2（2026-11-12，店長：係が 7 時間止まった・主の会話が手で直した・見た目の確認が遅い）

旧ループ（`.claude/workflows/harness-forever.js`・`BACKLOG.md`）はそのまま残してある。v2 は別の台本 `.claude/workflows/harness-v2.js`。
**同じ段を両方で進めない**（v2 を回す間、旧ループは止めておく）。考え方（目標・審美基準・連動して直す）は `HARNESS.md` と `docs/rules/aesthetic.md` のまま。

## 何が変わったか

| 困ったこと | v2 の答え |
|---|---|
| 係が 7 時間止まった | 係は小さい仕事だけ（作る係は手元のコミットまで）。全部の係が心拍（`harness/hb.py beat`）を書き、外の見張り（`harness/watchdog.ps1`）が 20 分 心拍のない係を `alerts.jsonl` に書く |
| CI と CPU の取り合い | 同時に作るのは 2 段まで。CI のコンテナ・ブラウザーは鍵（`harness/lock.py ci｜browser`）で 1 つずつ |
| 主の会話が手で直した | 直しは 2 回まで → 見立ての係（強いモデル・手順だけ書く）→ もう 1 回 → だめなら止めて（parked）次の段へ。ループ全体は止めない |
| 店長が見た目を後から直させた | 画面の段は、1333×677 と 390×844 の絵を撮り、審美基準の番号（A1〜I2）ごとに ○✗。1 つでも ✗ なら合併しない |
| BACKLOG.md が 551KB | 1 段 1 ファイル（`harness/tasks/T-NNNN.json`）。係は `q.py next` で次の段だけ受け取る |
| GitHub が不安定・Pages が遅い | 取った印・途中の状態は手元（push しない）。合併は 1 つずつ・やり直し付き（`harness/net.sh`）。本番の確かめは待たずに `verify` の段を残す |

## 係（役）とモデル

| 役 | 既定のモデル | すること | しないこと |
|---|---|---|---|
| 主の会話（brain） | — | 台本を起こす・`summary.json` と `alerts.jsonl` を読む・店長と話す・止まった段を決める | サイトのコードを直す |
| 受付 intake | sonnet | 店長の言葉（AgentBoard の書き込み・`D:/Claude/hf/inbox/`）→ 審美基準の差分＋段＋返事 | 作る |
| 計画 plan | **fable**（Fable を使うのはここだけ） | 範囲のファイルが重ならない段を選び、約束（範囲・できたと言える条件・重さ complexity）を凍らせる | 作る |
| 下調べ scout | haiku（`search`） | 触る所の地図（パス:行） | 書く |
| 作る build／直す fix | 段の重さで：light＝haiku・normal＝sonnet・hard＝opus | 段ごとの作業ツリーで手元のコミットまで | push・合併 |
| 新規ユーザーの点検 kpi | haiku | 測る（board_kpi.py）・目標を越えた所を段にする | 直す |
| 機能の審査 evalF | sonnet | 条件を 1 つずつ自分で流して確かめる・的を絞った試験 | 直す |
| 見た目の審査 evalV | opus | 絵を撮って審美基準の番号で採点（kind=visual・options だけ） | 直す |
| 見立て diag | opus | 直らない理由と次の手順 | コードを書く |
| 合併 ship | sonnet | rebase → `ci_local.sh`（鍵）→ push → PR → **全部の検査が通ってから** squash 合併 | コードを直す・検査待ちのまま合併 |
| 確かめ verify／知らせ／記録 learn | haiku | 本番に出たか・Discord・列と要約の更新 | 直す |

モデルの決まり（2026-11-12 店長：トークンの節約）：**Fable は計画だけ**。ほかは仕事の重さで決める — Haiku＝探す・数える・記録を読む・決まった手順／Sonnet＝ふつうの作る・直す・試験・案のページ・受付・合併／Opus＝難しい所だけ（見立て・見た目の最後の審査・重さが hard の段）。
段の重さ（`complexity`：light｜normal｜hard）は段のファイルの約束の 1 つで、計画の係が `q.py contract --complexity` で付ける（迷ったら軽い方・hard は 1 周に 1 つまで）。
`args.models = {hard: 'sonnet', evalV: 'sonnet', …}` で役ごと・重さごとに変えられる。`args.model` は「全部の役を 1 つに」する試し用で、**fable を入れても使われない**（台本が断って既定のモデルで回す）。

## 1 周の流れ（`harness-v2.js`）

```
Intake   受付（店長の言葉 → 決まり＋段＋返事）｜同時に：前の回の「本番でまだ」（verify の段）を確かめる
Plan     q.py next → 約束を凍らせる → 範囲が重ならない段を max 個（台本がもう一度重なりを落とす）
Build    2 段ずつ：下調べ → 作る（kind=kpi は新規ユーザーの点検）→ 手元のコミット
Evaluate 機能 →（画面の段は）見た目。✗ が 1 つでもあれば不合格
Fix      直し 2 回まで／同じ所で落ちた・新しいコミットがない → 見立て 1 回 → 直し → だめなら止める
Ship     1 つずつ（受付の枝が先）：rebase・記録（段を済みに・PROGRESS.md 1 行・INDEX.md）・CI・push・PR・検査・合併
Verify   本番に出たか（10 分まで）。出ていなければ verify の段を残して先へ。案のページは出てから Discord（ask_remind.yml cmd=say）
Learn    q.py done／park・結果 1 行・INDEX・summary.json・合併した段の作業ツリーを消す
```

- 段の種類（kind）：`fix`（機能・点検）・`visual`（画面が変わる）・`options`（テストグラウンドに案を並べて店長が選ぶ）・`kpi`（新規ユーザーの点検。毎回やる段＝済みにしても次の回にまた出る）・`verify`（ループが自分で足す）。
- `options` の段：作る係が `docs/testground/choice-<段>.html` に 2〜4 案（名前・良い点・困る点・おすすめ）。全部の案が見た目の審査を通ってから合併。本番で開けるのを確かめてから Discord に網址、質問は `D:/Claude/hf/state/pending_choices.json`、段は店長待ち（waiting）。店長の答えは受付が次の段にする。
- 止まるもの：DB の変更・新しい設計の決めごと → 作らずに店長待ち（`q.py park --waiting`）。主の会話が決める。

## ファイル

| どこ | 何 |
|---|---|
| `harness/tasks/T-NNNN.json` | 段（約束：title・why・quote・kind・complexity・scope・done_when。凍ったら変えない）。`INDEX.md` は `q.py index` が作る |
| `harness/q.py` | 列：`next`・`claim`・`release`・`contract`・`done`・`park`・`reopen`・`add`・`index`・`show`（push しない） |
| `harness/hb.py` | 心拍 `beat`／`end`・`stale --minutes N`・`summary`・`result`・`choice`・`inbox`／`reply`（AgentBoard） |
| `harness/lock.py` | 鍵（`ci`・`browser`）：空くまで待って命令を流す |
| `harness/net.sh` | 網の命令のやり直し（5 回・間をあける） |
| `harness/shots.py`・`shots.sh` | 1333×677・390×844 の絵（`shots.sh` はコミットした中身でページを作ってコンテナの中で撮る＋自己点検の数） |
| `harness/watchdog.ps1` | 外の見張り（5 分ごと。**登録は店長が**：ファイルの頭の `schtasks` の 1 行） |
| `D:/Claude/hf/state/`（手元・git の外） | `claims/`（取った印）・`q/`（段の途中の状態）・`tasks_local/`（まだ合併していない段・凍らせた約束）・`hb/`（心拍）・`locks/`・`results.jsonl`・`alerts.jsonl`・`pending_choices.json`・`INDEX.md`・**`summary.json`** |
| `D:/Claude/hf/v2r/wt/<段>` | 段ごとの作業ツリー（枝 `harness/<run>-<段>`）。止めた段のものは残る（主の会話が見てから消す） |

## 主の会話の起こし方

Workflow ツールで：

```
scriptPath: D:/Claude/Wishlist/.claude/workflows/harness-v2.js
args: { "run": "1112a", "max": 4, "cycles": 1 }
```

| args | 既定 | 意味 |
|---|---|---|
| `run` | `v2` | 起動ごとの名前（枝・作業ツリーの名前に入る）。**毎回変える**（日付＋a,b,c…） |
| `models` | 上の表 | 役ごと：`plan scout verify learn kpi intake evalF ship evalV diag`、重さごと：`light normal hard`（`build` を言えば重さに関係なくそれ） |
| `model` | なし | 試し用：全部の役をこのモデルに。`fable` は受け付けない（ふだんは使わない） |
| `max` / `width` / `cycles` | 4 / 2 / 1 | 1 周の段の数・同時に作る数（2 まで）・何周するか |
| `intake` `scout` `kpi`（`newuser`） `options` `ship` | 全部 true | false で止める。`ship: false` は合併しない試運転（枝は手元に残り、段は止めた扱い） |
| `repo` `scratch` `state` `board` `inbox` `python` `site` | PC の決まった場所 | 変えるのは試験のときだけ |

起こす前に：この PR が main に入っていること（係は origin/main の `harness/q.py` を使う）。止まったら同じ args と `resumeFromRunId` で続きから。
最初の 1 回は `{"run": "…", "max": 1, "kpi": false, "ship": false}` で 1 段だけ通して、`summary.json` と作業ツリーを見るのがおすすめ。

## ダッシュボード（AgentBoard）が読むもの

`D:/Claude/hf/state/summary.json` だけ（`hb.py summary` が作る。見張りが 5 分ごと・記録の係が毎周）：

- `agents`：動いている係（役・段・いま何をしているか・最後の心拍からの分 `quiet`・始めてからの分）／`stale`：20 分 心拍なし
- `queue`：open・claimed・waiting・parked・done の数／`next`：次の 5 段／`waiting`・`parked`：理由つき
- `results`：最近の 10 件（段・結果・PR）／`choices`：店長に選んでもらっている案のページ／`alerts`：見張りの最近の 5 件
- `kpi`：`harness/kpi/latest.json` のうち目標を越えた段

店長の書き込みは `D:/Claude/AgentBoard/inbox.jsonl`（`{t, text}`）、返事は `outbox.jsonl`（`{t, re, text}`）。

## まだ入れていないもの（次の段）

合格の見本の絵との画素の比べ（golden）・店長の判定の記録（owner_verdicts.jsonl）で審査の係を合わせる・1 つの PR に 3 段まとめる合併・本番のページに build の印・ダッシュボードのボタン（優先を変える・飛ばす）・見張りが残ったプロセスを止める。設計は `D:/Claude/hf/research/harness-v2.md`。
