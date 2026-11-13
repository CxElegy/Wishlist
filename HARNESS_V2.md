# ハーネス v2（2026-11-12，店長：係が 7 時間止まった・主の会話が手で直した・見た目の確認が遅い）

旧ループ（`.claude/workflows/harness-forever.js`・`BACKLOG.md`）はそのまま残してある。v2 は別の台本 `.claude/workflows/harness-v2.js`。
**同じ段を両方で進めない**（v2 を回す間、旧ループは止めておく）。考え方（目標・審美基準・連動して直す）は `HARNESS.md` と `docs/rules/aesthetic.md` のまま。

## 何が変わったか

| 困ったこと | v2 の答え |
|---|---|
| 係が 7 時間止まった | 係は小さい仕事だけ（作る係は手元のコミットまで）。全部の係が心拍（`harness/hb.py beat`）を書き、外の見張り（`harness/watchdog.ps1`）が 20 分 心拍のない係を `alerts.jsonl` に書く |
| CI と CPU の取り合い | 同時に作るのは 2 段まで。CI のコンテナ・ブラウザーは鍵（`harness/lock.py ci｜browser`）で 1 つずつ。**`ci_local.sh` は自分で ci の鍵を取り**、鍵を持たないほかのコンテナが終わるまで待つ（pre-push・ほかの会話から流しても並ばない） |
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

## 係の型（道具を絞る）

型なしの係には MCP を含む全部の道具（約 80 個）が毎回付き、最初の 1 手が約 9 万トークン。型（`.claude/agents/hw-*.md` の `tools:`）で絞ると約 1 万。型は道具だけを決め、モデルは台本が役ごとに決める（型に `model` は書かない）。

| 型 | 道具 | 付ける役 |
|---|---|---|
| hw-edit | Read, Edit, Write, Glob, Grep, Bash | intake・plan・build・fix・kpi |
| hw-read | Read, Glob, Grep, Bash | evalF・evalV |
| hw-diag | Read, Glob, Grep, Bash, WebSearch, WebFetch | diag |
| hw-ops | Bash, Read | verify・learn・ship・announce |
| search（元から） | Read, Glob, Grep, Bash | scout |

型のファイルはリポジトリの `.claude/agents/` が元。主の会話は D:/Claude にありリポジトリの外なので、`python harness/install_agents.py` で `~/.claude/agents/` にも入れる（`--check` で同じ中身か確かめる）。**型を使わない・戻す時は `args.types: false`**（scout 以外は型なし＝今までどおり）。`args.types = {evalV: 'x'}` でその役だけ別の型。

## 1 周の流れ（`harness-v2.js`）

```
Intake   受付（店長の言葉 → 決まり＋段＋返事）｜同時に：前の回の「本番でまだ」（verify の段）を確かめる
Plan     q.py next → 約束を凍らせる → 範囲が重ならない段を max 個（台本がもう一度重なりを落とす）
Build    同時に 2 段（1 段終われば次が入る）：下調べ → 作る（kind=kpi は新規ユーザーの点検）→ 手元のコミット。続きの段（resume）は前の枝・作業ツリーから
Evaluate 機能 →（画面の段は）見た目。✗ が 1 つでもあれば不合格
Fix      直し 2 回まで／同じ所（不合格の条件の番号＋落ちた試験の名前が同じ）・新しいコミットがない → 見立て 1 回 → 直し → だめなら止める。1 段の係は 9 まで（args.maxAgents）
Ship     1 つずつ（受付の枝が先、あとは審査を通った順。ほかの段を待たない）：rebase・記録・CI（終了コード 3＝負荷の不安定だけ → 落ちた試験だけ流し直し → まだなら GitHub の検査を関所に）・push・PR・`gh pr checks --watch && gh pr merge --squash`
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
| `harness/q.py` | 列：`next`・`claim`・`release`・`contract`・`done`・`park`・`reopen`・`add`・`repair`・`index`・`show`（push しない）。`contract`／`add` は `--from-json <UTF-8 の JSON>` が勧め。Git Bash の path 変換で壊れた文字（`C:`+バックスラッシュ+`Program Files`+バックスラッシュ+`Git` や `;C:` など）は書く前に断る。係の命令は全部 `env MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' …` で呼ぶ。凍った約束の書き直しは主の会話だけが `repair <id> --from-json F --reason …` |
| `harness/hb.py` | 心拍 `beat`／`end`・`stale --minutes N`・`summary`・`result`・`choice`・`inbox`／`reply`（AgentBoard） |
| `harness/lock.py` | 鍵（`ci`・`browser`）：空くまで待って命令を流す。`--timeout <秒>`・`status`。Windows では `bash`・`timeout` を Git for Windows のものに読み替える（System32 の timeout.exe・WSL の bash が動いた） |
| `harness/run_tests.py` | 試験。落ちたのが Playwright の起動・goto の時間切れ・切断・つながりの失敗だけなら終了コード 3（基盤の不安定）。`ci_local.sh <名前 …>` で落ちた試験だけを同じコンテナで |
| `harness/cost.py` | 回のあと主の会話が流す：`python harness/cost.py <ワークフローの記録のフォルダ> --run <run>` → 段ごとの係の数・重さ（input＋output＋cache_creation）・分を `state/costs.jsonl` に。summary.json の `cost` に「合併できた段 1 つあたり」 |
| `harness/net.sh` | 網の命令のやり直し（5 回・間をあける） |
| `harness/shots.py`・`shots.sh` | 1333×677・390×844 の絵（`shots.sh` はコミットした中身でページを作ってコンテナの中で撮る＋自己点検の数） |
| `harness/watchdog.ps1` | 外の見張り（5 分ごと。**登録は店長が**：ファイルの頭の `schtasks` の 1 行） |
| `D:/Claude/hf/state/`（手元・git の外） | `claims/`（取った印）・`q/`（段の途中の状態）・`tasks_local/`（まだ合併していない段・凍らせた約束）・`hb/`（心拍）・`locks/`・`results.jsonl`・`alerts.jsonl`・`pending_choices.json`・`INDEX.md`・**`summary.json`** |
| `D:/Claude/hf/v2r/wt/<段>` | 段ごとの作業ツリー（枝 `harness/<run>-<段>`）。止めた段のものは残る（主の会話が見てから消す） |

## 止めた段の続き・分けた段（2026-11-12 run 1112b のあと）

最初の本番（run 1112b：max 4・1 周）は 17 係・47 分・重さ 155 万（cache_read を入れると 2950 万）で合併 0 件だった。重さの内訳（`harness/cost.py`）：
T-0002 が 11 係・85 万（55%。審査 3 回＋直し 3 回＋見立て＋合併 22 万）、T-0009 が 2 係・29 万（作る係 1 人で 26 分）、共通（受付・確かめ・計画・記録）41 万。

| 何が起きた | 直したこと |
|---|---|
| 合併の係の CI（915 秒）がほかの会話の `ci_local.sh` と同時に走り、test_wall_shapes が Page.goto 30 秒切れ。手元の流し直しも同じ負荷の中で赤 → push しない | `ci_local.sh` が自分で鍵を取り、鍵なしのコンテナが終わるまで待つ。`run_tests.py` が負荷の不安定を分けて終了コード 3 → 合併の係は落ちた試験だけを静かになってから流し直し、まだなら push して GitHub の検査を関所に（赤・待ちでは合併しない） |
| `lock.py ci -- timeout 1500 bash …` が Windows で System32 の timeout.exe と WSL の bash を動かした・hb.py が cp932 で ♥ を書けず落ちた | `lock.py` が Git for Windows のものに読み替える・`--timeout`。q.py・hb.py・lock.py は画面の文字コードで落ちない |
| 合併の係が CI の終わりを 20 回以上見に行った（重さ 22 万・使い回し 460 万） | 長い命令は run_in_background で流して終わりの知らせを 1 回待つ（全部の係の決まり） |
| T-0002：前からある Windows だけの赤（test_free_tier_gate）と、範囲の外の同じ壊れ方を審査が不合格にし、直し 3 回＋見立て、4 → 15 ファイル | 審査は落ちた試験を main（`wt/base`）でも流し、main でも落ちるものは `preexisting`（不合格にしない）。この段の規則と関係ない壊れは `q.py add` で新しい段に。「同じ所で落ちた」は条件の番号＋試験の名前で比べる（自由な文の signature は毎回変わった）。約束の試験は `run_tests.py`（venv に pytest は無い） |
| T-0009：点検を足す＋render.py の組み方＋前後の絵＋試験を 1 係に。作る係は写真 4000 枚超の全ページを 1 回 5 分で測り続けて時間切れ・「failed」で返り続きの手がかりが段に残らない | 計画が大きさを見積もり `q.py split` で順番つきの子に（条件 4 つ以上・点検＋実装・FIT_JS を変える、など）。作る係は `partial`＋`resume_note` で返せる。測るのは test_wall_shapes と同じ小さいページ |
| T-0002 は審査を通ってから 12 分、同じ組の T-0009 を待った | 合併は審査を通った順に 1 つずつ（組の待ち合わせをやめた） |
| 計画が取った T-0006 を台本が外し、印が 60 分残った | 記録の係が外した段の印を返す（`q.py release`） |

### push の点検の重複をなくす（2026-11-12 pre-push-once）

- docker が使える PC では pre-push の ②（変えた所の試験）を飛ばす：④（`ci_local.sh`、Linux で全部の試験）が同じ試験を含むため。docker が無い PC は今までどおり ② を流す。
- `ci_local.sh` が引数なしで全部緑なら、`HEAD^{tree}` の指紋で緑の印を残す（`HF_CI_GREEN_DIR`、既定 `D:/Claude/hf/state/ci_green/`、無ければ印なし）。pre-push の ④ は同じ指紋の印が 2 時間以内（`HF_CI_GREEN_TTL`）なら流さない。赤・終了コード 3・一部の試験だけの流しは印を残さない。
- ④ が終了コード 3（負荷の時間切れ）なら pre-push も 3 で返す（本物の赤は 1）。試験は `tests/test_pre_push_once.py`。
- `lock.py` は別の鍵を持ったまま（`HF_LOCK_*` あり）別の鍵を取ろうとすると即エラー（終了コード 64）。ci の鍵を ci_local.sh 以外で取ると警告。試験は `tests/test_lock_nested.py`。
- `lock.py` は先着順（整理券）：待つ人は `lockq/<名前>/` に並び、先頭だけが取れる。死んだ待ち人・死んだ持ち主は pid で外す。試験は `tests/test_lock_fifo.py`。

### run 1112d のあと（2026-11-12）：赤の直し 1 回・測る場所で分ける

| 何が起きた | 直したこと |
|---|---|
| T-0004：手元の CI の赤が fake-402 の名簿に 1 行足し忘れただけ（本物の試験の赤）なのに、合併の係は即止めた | `shipOne`：failed_class=work で failed_tests があれば、**作る係（段の重さのモデル）に 1 回だけ直させ**（同じ作業ツリー・落ちた試験の名前を渡す・試験は弱めない）、もう一度合併へ。それでも赤なら止める（`x.shipFixed`）。rc=3（基盤）・conflict はこれまでどおり |
| T-0229：「35 → 10 以下」は rembg のあるクラウドの後台でしか測れず、仕組みを入れたまま止まった | 計画の 2c：この PC で測れない条件（クラウドの定時の仕事・合併して何回か回ったあと・デプロイ後の本番のデータ）は、「仕組みを作る段（試験と安全が条件）」と、あとの軽い「測る段（kpi／verify・after で順つき）」に分ける |

止めるとき（`q.py park`）は `--cls infra｜work｜size｜conflict` と `--resume-branch/-worktree/-commit/-stage/-note` を残す。
- `infra`（中身は良い・負荷や網で合併できなかった）：次の回の `q.py next` でいちばん先に出る（3 回まで）。`resume.stage=ship` なら台本は作る・審査をとばして合併から。
- `work`・`size`・`conflict`：主の会話が見て `q.py reopen` か `q.py split`。開け直しても resume は残り、作る係は前の枝・作業ツリーから続ける（`-B` で作り直さない）。
- 作業ツリーは回の名前つき（`${scratch}/wt/<run>-<段>`）。前の回で止めた段の作業ツリーとぶつからない。

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
| `maxAgents` | 9 | 1 つの段に使う係の上限（下調べ〜合併）。越えたら枝とコミットを残して止める（次の回に続き） |
| `intake` `scout` `kpi`（`newuser`） `options` `ship` | 全部 true | false で止める。`ship: false` は合併しない試運転（枝は手元に残り、段は止めた扱い） |
| `repo` `scratch` `state` `board` `inbox` `python` `site` | PC の決まった場所 | 変えるのは試験のときだけ |

起こす前に：この PR が main に入っていること（係は origin/main の `harness/q.py` を使う）。止まったら同じ args と `resumeFromRunId` で続きから。
最初の 1 回は `{"run": "…", "max": 1, "kpi": false, "ship": false}` で 1 段だけ通して、`summary.json` と作業ツリーを見るのがおすすめ。
回のあとは `python harness/cost.py <ワークフローの記録のフォルダ（journal.jsonl のある所）> --run <run>` で重さを記録する（台本からはトークンが見えない）。
**ほかの会話が Playwright・CI を流している間は回さない**（`docker ps` に wishlist-ci が無く、`python harness/lock.py status` が空のとき）。

## ダッシュボード（AgentBoard）が読むもの

`D:/Claude/hf/state/summary.json` だけ（`hb.py summary` が作る。見張りが 5 分ごと・記録の係が毎周）：

- `agents`：動いている係（役・段・いま何をしているか・最後の心拍からの分 `quiet`・始めてからの分）／`stale`：20 分 心拍なし
- `queue`：open・claimed・waiting・parked・done の数／`next`：次の 5 段／`waiting`・`parked`：理由つき
- `results`：最近の 10 件（段・結果・PR）／`choices`：店長に選んでもらっている案のページ／`alerts`：見張りの最近の 5 件
- `kpi`：`harness/kpi/latest.json` のうち目標を越えた段
- `cost`：最後の回の段ごとの係の数・重さ・分と、合併できた段 1 つあたりの重さ（`harness/cost.py` が書いた `costs.jsonl`）

店長の書き込みは `D:/Claude/AgentBoard/inbox.jsonl`（`{t, text}`）、返事は `outbox.jsonl`（`{t, re, text}`）。

## まだ入れていないもの（次の段）

合格の見本の絵との画素の比べ（golden）・店長の判定の記録（owner_verdicts.jsonl）で審査の係を合わせる・1 つの PR に 3 段まとめる合併・本番のページに build の印・ダッシュボードのボタン（優先を変える・飛ばす）・見張りが残ったプロセスを止める。設計は `D:/Claude/hf/research/harness-v2.md`。

## ハーネス v3（2026-11-13）：失敗を溜めて直す・計画で断る・見た目を数で止める・git を隔離する

| 道具 | することと決まり |
|---|---|
| `harness/lessons.py`（失敗の台帳） | `add --type 鍵 --task T-… --what … --why-missed …`・`list`・`due [--min 3] [--out DIR]`。1 行 1 件の JSONL を **手元の state（`D:/Claude/hf/state/lessons.jsonl`、`HF_STATE` で変更）** に置く＝q.py の取った印と同じ置き場で、リポジトリには入れない。同じ種類（type）が **3 回** たまると、直す段（「手元で見つかる検査を足す」）の JSON を出す。`q.py add --from-json` にそのまま渡せる。CI が赤になったら「なぜ手元で見つからなかったか」を `add` する（WORKING.md §1-5） |
| `q.py contract <id> --lint` | 凍らせず約束を点検。✗ なら終了コード 1。**あとでしか測れない条件**（「合併後」「マージ後」「本番で」「デプロイ後」「何回か回った」／after merge・in production・post-merge など）は、仕組みを作る段と あとの測る段（verify／kpi・after）に分ける。**大きすぎる段**：scope が **9 ファイル以上**（上限 8）・done_when が **7 個以上**（上限 6）は `q.py split`。計画の係は凍らせる前に必ず流す |
| `harness/visual_gate.py` ＋ `harness/aesthetic_map.json` | 審美基準の番号（A1〜I2）→ 検査の名前（self_review の gap crop band clip icon over wide face／aesthetic_count の edge hid solo herogap emrel cgap ell strong）。`visual_gate.py 結果.json …` が番号ごとに ○✗、1 つでも ✗ なら終了コード 1。結果に名前の無い検査は未測定（既定は落とさない・`--strict` で落とす。aesthetic_count.py が main に入る前でも動く）。検査の無い番号は人の目（evalV）に残す |
| `harness/gitsafe.py` | `clean_env()`（GIT_* を外す）・`guard(cwd)`（本物のリポジトリの中・最上位なら AssertionError）・`run(cwd, …)`。git を書く試験（test_pull_rebase・test_push_main・test_gate_fire）はこれを通す。`tests/test_harness_v3.py` が「git を流す試験は gitsafe か GIT_* の除去を使う」を全試験ファイルで確かめる。`tests/test_ship.py`・`harness/ship.py` は無い（合併は台本の係が `gh` で行う）ので、作るときは同じ入口を使う |
