# バックグラウンド・ゲート・收集・AI 编辑

## 后台・AI 编辑（原「管理ページ」の一部）

- **收集不停（2026-10-22 全体の検査 M3・M4）**：GitHub 的定时 `17 */2` 常抜ける（10-21〜22 12 回只来 5 回、空了 4 小时）→ **收集的控えの時計**由后台作業兼任（pg_cron 每小时必到）：`scripts/collect_watch.py` 看 `state/log/collect.json` 最后一次收集（带 `secs` 的行），过了 150 分、digest.yml 没有在跑・排队・60 分内（比 timeout 40 分长）开始的回，就 `gh workflow run digest.yml`（这步在 `gate.py check` 之前：判断那步出错也照样跑；GITHUB_TOKEN 的 workflow_dispatch 能起别的 workflow，`actions: write`），记进 `state/log/gate.json`（起不来・读不到回的样子也记、也提交：`tried`；同一个失败不重复写）。
  **締め切り**：收集开始 18 分（`digest.COLLECT_DEADLINE_MIN`）后不再开新的版面，剩下的写进日志「時間切れで N 版面を次の回へ」（`deferred`），下一回先抓它们（`deferred_from_log` / `fetch_order`，第一次抓的版面＝新关注项也排最前）；已经开始的版面卡住时，截止＋5 分（`COLLECT_GRACE_MIN`）就不等了（`digest.run_parallel` 用 daemon 线程，卡住的 1 本不挡进程结束），也算下一回（不等以后那条线程再写版面的条：`cut` 之后 `live_mark` 不写；`intel.health` 在锁里取副本，`logged_ingest` 出错只少 1 行日志）；截止后封面不上网（`find_cover` 只用已有的）；digest.yml `timeout-minutes: 40`。**1 个版面抓取・之后按顺序的处理（去重・match 的正则・状态・封面）出例外**只让那个版面空着（中途写的状态还原）、日志「取得・処理に失敗した N 版面は空で続けた」，收集照常（`ingest` 的 `fetch` / `_ingest_one`）；设置页的依赖里 `re:` 写错的 match / exclude 在 `take_item_requests` 就拒收。
  后台作業：小元素那步 `continue-on-error`（失败也照样叫 AI 编辑・提交；items.yaml 用 `emblem.write_atomic` 写，提交前读不了就 `git checkout` 回去，失败的回不接着再起）；`state/gate.json` 只在判断变了（最初的 check・小元素后的 check）・真的叫了 Claude・试着起收集时才提交（`GATE_FIRE` 开着不算）。
  digest.yml 的「新关注项 → 立刻 AI 编辑」也走ゲート：`GATE_NOW=edit python scripts/gate.py fire`（只跳过 9:00 / 18:00 的回；60 分内已叫起〔编辑中〕・停滞・一時停止・`GATE_FIRE` 都照守：AI 编辑只跑 1 本；叫了就记 `now: true` 并 push；因「60 分内」被拦时把请求记进 `state/gate.json` 的 `jobs.edit.now_pending` 并 push，过了 60 分的后台作業按 GATE_NOW 一样叫（叫了就删，12 小时没叫就作废））。
- **省 token：AI 做过的判断，能写成规则的就写成规则（用户定的）**：以前用 AI（Claude）做的判断，逐个看能不能变成程序的规则；
  能的就改成 Python（不花 token），太复杂的（意思的判断、图里是什么东西）继续用 AI，但只在有活的时候叫。
  一览和理由在 `processes.AI_TASKS`（管理页「バックグラウンド → AI を使うか」），新加 / 改了判断时同步改。
  **小元素补全不要停着等**：每小时 + 每次收集完马上 + 40 分钟用完还有活就自己接着跑（最多 3 次），6 个版面并行；
  每个版面在同一回里按「① 标准 → ② 名前を広げる → ③ 公式・記事のページ」逐段试，到目标为止；三段都不行才算失败，
  失败的版面只要有新材料（新记事・新线索，`emblem_fill.material` 的指纹变了）就马上再试，没有也最多等 1 小时（`emblem_fill.RETRY_HOURS = 1`，2026-10-22 用户定的：不用 AI，6 小时太久 → 每小时的后台都再试）。
  正在处理的版面和段写进 Supabase `live_status`（proc=emblem），管理页「いま動いているもの」每 30 秒读一次。
  **后台的ゲート**（`scripts/gate.py` + `.github/workflows/background.yml`）：先数有没有活；小元素补全直接在 Actions 用 Python 做（不用 AI，
  原来要目视的「别人・远景・合照・抠图有洞・重复」都改成规则了）；AI 编辑・照片加愿望只在有活时用 API 叫 Claude（同一份活 6 小时内不重复叫，
  需要各定时任务的 API 令牌 Secret；**仓库变量** `GATE_FIRE`（Settings → Secrets and variables → Actions → Variables）打开才真的叫：
  没设 = `edit`（默认，2026-10-17 打开）、`0` = 不叫、`edit` = 只叫 AI 编辑、`1` = AI 编辑和照片都叫。AI 编辑自己的定时 2026-10-17 已停（cron 改成只在 2/29 跑），现在只靠ゲート叫）。
- **版面只放 AI 整理过的报道（2026-10-17 定）**：收集（Actions）出刊时，没被 AI 编辑覆盖的条目（编号 > `_covered`、或 edit.json 里没有的关注项）
  不上版面，放进版面底部折叠的「整理待ち N 件」（`digest.split_unedited` → 报告的 `pending` → `render._pending`）；例外是要紧消息，马上做「重大」+ Discord。
  **前の日の整理待ちは持ち越す（2026-10-22 全体の検査 H3）**：AI 编辑只看最新的 inbox，JST 18:00 那回之后〜1:00 收集的会永远留在昨天。`digest.carry_over`：新的一天第一次收集时（`_carried` 记号，一天一次），把前一天（2 天以内）`_covered` 之后・不是要紧的条目接到今天的 inbox：1 版面最多「篇幅 × 2」件（S 6・M 10・L 16，留新的，`CARRY_PER_SIZE`），前一天已经持ち越し过的（`carried`）不再带；今天和前 3 天的 reports 里已经载了的（同网址・同标题 `title_key`；只把要带的那条去掉末尾「 - 媒体名」「｜媒体名」后剩 12 字以上・6 成以上的也拿去比 reports 的原标题，`_title_keys`，不让「討論牆 | …」「共通の頭 | 品目」只剩头）不带（实际很少命中，主要靠上限：2026-10-22 168 → 82 件）。不用 StoryDeduper：真数据里会把别的比赛・别的爆料也当成同一件事。
  **网页生成失败也要 push 数据（H4）**：本番的 workflow（digest・background・requests）设 `WL_RENDER_SOFT=1`，`digest.write_page` 出错只记日志、不停；CI 照旧失败。`render.collect` 跳过没有 headline / url 的报道，`publish` 用依据的原题补 headline。
  **AI 编辑一天 2 次（用户定的，2026-10-19）**：日本时间 9:00 和 18:00（`gate.SLOTS`，`background.yml` 在 0:07 / 9:07 UTC 有定时：过了回再起，0 分整点 GitHub 最挤），那一回还没叫过、今天有整理待ち（`gate.edit_work`）就叫；
  管理页「次の実行」AI 編集卡片的「今すぐ実行」和「AI 编辑をもう一度起こす」随时强制叫（`run_now('edit_now')`）。
  **叫了不等于做了（2026-10-18）**：API 返回 200 只说明触发成功，定时任务绑定的会话停了的话什么也不会发生（2026-10-17 就叫了 2 次都没编）。
  所以 `gate.work_state` 看「叫起后编辑済み数（edit.json 的 _covered 合计）有没有增加」：60 分钟内 = 编辑中；60 分钟后没增加 = 停滞 → 再叫（最多 3 次，之后等 6 小时，管理页写「起こしても動かない」）。
  **日付が変わったら数え直す（2026-10-22）**：_covered 合计按北京时间的「今天」数，0 点后归 0。叫起时记 `fired.day`（没有的旧记录用 `fired.at` 换成北京时间的日期），不是今天就不算停滞（`none`），交给 9:00 / 18:00 的定时判断（10-19・10-20・10-21 夜里 1〜2 点误叫了 3 次）；北京时间 0 点后也不再补叫前一天 18:00 那回（`gate.slot_pending`），等 9:00。
  管理页的「動いている」只在这次叫起之后的最后一批出刊（`state/log/edit.json`，`gate.last_batch`）30 分钟以内；过了是 `idle`「前回 HH:MM に終わった・次は HH:MM」（这回还没叫时改成「18:00 の回はまもなく」，列标题和「次の実行」卡片也一样 `due`；「あと N 分」由 `data-slots` 在浏览器里数，不写死）；叫起后编辑済み增加了、60 分钟还没有出刊的行 = `unpublished`「出刊されていない」（带最后一条失败 `gate.last_error`，2026-10-22 出刊に失敗：No module named 'requests'）。叫不叫的规则和 progress 一样。
  叫起时记下 API 返回的会话 id（`fired.resp`）。管理页 AI 编辑列有「AI 编辑をもう一度起こす」按钮 = `run_now('edit_now')` → `background.yml` 的 `force_edit` → `GATE_FORCE=edit`（不看 `GATE_FIRE`・间隔・停滞判断）。
- **AI 编辑推上去了、网页却没变（2026-10-19 修）**：收集（digest.yml）排队时是用触发时的提交 checkout 的，等它跑完，AI 编辑早把 `edit.json` push 上去了；
  收集的 `git pull --rebase -X theirs` 之后只 `render`（只从 reports 生成），reports 是没有编排的旧版，网页就一直是「整理待ち」。
  现在：① digest.yml 的 checkout 取 `github.ref`（main 的最新）② 出刊时把 `edit.json` 的指纹写进报告（`edit_sig`）③ `digest.py render` 先看 `stale_report()`，
  报告没取进最新的 `edit.json` 就先 `publish(heal=True)`（只取进编排，不重找配图）再生成。所以任何一次 render（render.yml・收集后）都会自己补上。
- **AI 编辑一个一个版面・暂停・重做（2026-10-19，用户定的）**：每个版面之前 `digest.py edit-next`（`EDIT_BATCH = 1`）问管理页的开关（Supabase `edit_control`，`db/edit_control.sql`）：
  `run`=全部一个一个、`step`=只编下一个就自动变 `pause`、`pause`=编完当前版面就停（9:00 / 18:00 也不叫，按钮照样能叫）；管理页「ライブログ」上面的「AI 編集」条：▶ 続けて全部・⏭ 次の 1 版面（这两个会顺便叫起 AI 编辑）・⏸ 一時停止・↺ この版面をやり直す（`redo`，编过的也最先重编，编完自动拿掉）。
  正在编的那个版面中途停不了（会话没有外部中断的口子），停在版面之间。
- **AI 编辑分批・token 记录（2026-10-19，用户定的）**：AI 编辑按 `digest.py edit-queue`（やり直し最先，然后整理待ち多的先，1 个版面一批）一批一批「编排 → 配图 → 出刊 → push」，推完 1〜2 分钟网页上这几个版面就更新（推送不花 token）。
  每批出刊时 `_log_edit_batch` 把这批编完的版面・本数・**这批用掉的 token**（`usage.py`：读 Claude Code 会话记录 `~/.claude/projects/*/*.jsonl` 里每条回复的 usage，真实数字，前一批之后的差）写进 `state/log/edit.json`，
  管理页「AI 編集のトークン」（今天・7 天・每回每批）和「ライブログ」显示。**省 token**：AI 读的是 `edit-brief`（不含网址的短一览），只给 hero・lead 看候选图（`PICK_WEIGHTS`，一张一览 ≈ 570 token），普通报道配图交给规则。
