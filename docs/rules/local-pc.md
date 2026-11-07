# 店長の PC で動かす（2026-11-07，用户定的）

旧 Supabase（クラウド・`bzokpnbcjscbcehdxtjq`）が無料枠超過で 402 になり、店長が「料金はかけない・自分のサーバーを使う」と決めた。
DB とログインは店長の PC に引っ越した。作業（会話・係・予約）も PC に移していく。
この文書は「GitHub を読めば続きができる」ための記録。

## データベース（済み 2026-11-07）

| 項目 | 中身 |
|---|---|
| 何 | 自前版 Supabase（Docker）。店長の PC（Windows「Elegy」）で動く |
| 公開の URL | `https://elegy.tailc8cfff.ts.net`（Tailscale Funnel。再起動しても変わらない） |
| 外に出しているもの | `/rest/v1` `/auth/v1` `/storage/v1` `/realtime/v1` `/functions/v1` だけ。管理画面（Studio）は出さない |
| 公開してよい鍵 | `items.yaml` の `supabase_key`（publishable） |
| 秘密の鍵 | service_role は GitHub Secrets の `SUPABASE_SERVICE_KEY`（店長が入れる）。会話・リポジトリに書かない |
| サイト・Actions の接続先 | `items.yaml` の `supabase_url`・`.github/workflows/requests.yml` の `SUPABASE_URL`（PR #959） |
| 移した中身 | 2026-11-07 のダンプから：public 23 表＋関数 80・private・auth.users 6・storage の名簿（ファイル本体は未移行）・RLS・招待制の Auth フック・pg_cron（毎時 17 分 `run_now('tick')`）・vault の `github_dispatch_token` |
| 旧 Supabase | 消さない（読むだけの控え）。請求期間が変わったら、photos・emblems のファイル本体をここから取り込む |

### 止まるとき

- PC が止まる・再起動して Windows にログオンする前は、**ログイン・👍👎・設定の保存・お客さまのページ**が止まる。記事を読むのは GitHub Pages なので止まらない。
- 休止の札（`render.SB_DEG_JS`）は今 `*.supabase.co` だけを見ている → 新しいサーバーの 5xx・つながらないときにも札を出す段が BACKLOG にある。

### 決まり

1. DB を変える SQL は PC の会話で行う（Supabase の連携ツールは旧プロジェクトにしかつながらない）。`db/*.sql` に書いてから流す。
2. 毎日のバックアップ（`pg_dump` を PC の別フォルダに 7 日分）。お客さまのデータが入るので GitHub・クラウドに上げない。
   - 道具：`D:\Claude\SupabaseLocal\backup.ps1`（置き場 `backups\`）・`restore-test.ps1`（使い捨てのコンテナに戻して本番と行数を比べる。2026-11-07 に合格）・`register-tasks.ps1`（Windows のタスクに登録）。
   - vault の `github_dispatch_token` は、別の DB に戻すと復号の鍵が変わることがある。読めなければ `set-github-token.ps1` で入れ直す。
3. 見張り：旧 Supabase の `query_logs` は使えない。PC が止まると PC では知らせられないので、外側の `pc_watch.yml` が毎時 `/auth/v1/health` を見て（200・401 は届いている）、変わったときだけ Discord へ知らせる。
4. 旧 Supabase の住所が残っている所（見本を作る scripts の `SUPA`、harness・hermes の例）は `items.yaml` から読む形に直す（BACKLOG）。

## 作業を PC に移す（途中）

GitHub に入っていて、PC の会話が読めば続けられるもの：BACKLOG.md・PROGRESS.md・DESIGN_PRINCIPLES.md・HARNESS.md・docs/rules/・`.claude/`（スキル・ワークフロー）。

GitHub に入っていないもの（移すときに要るもの）：

- 会話の記録そのもの（決めたことは上の文書に書いてある）
- クラウドの作業場所だけにあるファイル（係の台本 `hf-*.js` など → リポジトリの `.claude/workflows/` へ移す段はハーネスが持つ）
- クラウドの予約（下）。PC ではタスクスケジューラか Claude Code の定期実行で作り直す

### クラウドの予約（2026-11-07 の写し。作り直すときはこの文をそのまま使う）

**1. 2 時間ごとの 30 字の報告**（日本時間 毎時 7 分・2 時間おき。入口の会話にひもづく）

```
【2 時間ごとの報告】いま（会話・裏のループ harness-forever・ほかの係）で何をしているかを確かめ、30 字以内の日本語 1 文にまとめる（例：「AI 編集を届いたら即時に直す段を作成中」）。mcp__github__actions_run_trigger で CxElegy/Wishlist の ask_remind.yml を run_workflow（ref: main、inputs: {cmd: "say", text: "<30 字>"}）。夜（日本時間 0〜8 時）は送らない。ユーザーへの返事は 1 行。
```

**2. 关注清单通信 · AI 编辑**（定時はなく、ゲート〔`run_now`・workflow〕が起こす。モデル sonnet）

```
【定时：AI 编辑】这是新的一次运行，不要依赖之前几次运行的记忆，以仓库的最新状态为准。

你是 GitHub 仓库 CxElegy/Wishlist（分支 main）的「关注清单通信」AI 编辑。

1. 在仓库目录里切到分支 main，执行 git fetch origin main && git reset --hard origin/main（丢掉上次可能残留的本地改动），再 pip install -q -r requirements.txt。
2. 完整阅读仓库根目录的 EDITING.md，严格按其中的步骤和规则工作（标题和摘要保留原文语言，不翻译）。分批做：先 python scripts/digest.py edit-queue 看顺序，每批 5 个版面「edit-brief 读 → 写这批版面进 edit.json（含 _covered）→ pick-images（只看 hero・lead）→ python scripts/digest.py publish → 提交并推送到 main」，推完再做下一批。
3. 如果最新 inbox 的日期不是今天（北京时间），或者今天 inbox 里每个有条目的关注项都已经在 edit.json 里、且 _covered 等于它当前的条目数（没有新条目），就什么都不改，直接结束。
4. 如果这次是被工作流叫起来的（消息里有 <routine-fire-payload>，说明刚新加了关注项）：照样整份重写当天的 edit.json，并确保 payload 里列出的关注项都编排进去。
5. 不要修改 scripts/、.github/ 下的任何文件，items.yaml 只能按 EDITING.md / TEMPLATES.md 说的改版面相关字段；不要发 Discord，不要开 PR。
6. 推送失败（403 等）时立刻停下，不要接着编下一批，不要说「已完成」，把错误原文写出来。
7. 最后用一两句话说明：编排了哪一天、多少条报道、有没有 hero（重大）消息，推送是否成功。
```

注意：この予約は workflow から API の鍵（予約ごとの token）で起こされる。PC に移すときは、起こす側（`gate.py`・workflow）の呼び先も替える段が要る。

**3. 愿望清单 · 照片加愿望**（北京時間 毎日 21:47。モデル sonnet）

```
【定时：照片加愿望】这是新的一次运行，不要依赖之前几次运行的记忆，以仓库的最新状态为准。

你是 GitHub 仓库 CxElegy/Wishlist（分支 main）的「照片加愿望」助手。

1. 在仓库目录里切到分支 main，执行 git fetch origin main && git reset --hard origin/main（丢掉上次可能残留的本地改动），再 pip install -q -r requirements.txt。
2. 完整阅读仓库根目录的 PHOTOS.md，严格按其中的步骤和规则工作：处理 inbox/photos/ 里每一张照片（<编号>.jpg + <编号>.json），认出照片里的东西，按 .claude/skills/wishlist/SKILL.md 的「加一件」整理好加进 wishlist.yaml（status 照抄 .json 里用户选的「想要 / 纠结」，并写上 photo: <编号>），删掉处理过的照片文件，然后提交并推送到 main。
3. 如果 inbox/photos/ 里没有 .json 文件，就什么都不改，直接结束。
4. 不要修改 scripts/、items.yaml、.github/ 下的任何文件，不要发 Discord，不要开 PR，不要动数据库。
5. 推送失败（403 等）时，不要说「已完成」，把错误原文写出来。
6. 最后用一两句话说明：处理了几张照片、分别加成了什么（想要 / 纠结），推送是否成功。
```
