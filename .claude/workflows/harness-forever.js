export const meta = {
  name: 'harness-forever',
  description: '止まらないハーネスのループ：BACKLOG.md の次の段を作る→確かめる→直す→合併→本番で確かめる、一覧が空なら計画の係が次の段を足して続ける',
  whenToUse: 'ウォッチリスト通信のハーネスを回すとき（HARNESS.md）。1 回の起動で最大 args.max 段（既定 6）、終わったら会話か定時タスクが次の回を起こす',
  phases: [
    { title: 'Plan', detail: '一覧が空・全部あなた待ちなら、点検して次の段を足す' },
    { title: 'Step', detail: '1 段を作って PR・合併・本番で確かめる' },
    { title: 'Check', detail: '別の目で本番と設計書に照らす' },
    { title: 'Fix', detail: '落ちたら直す（2 回まで）' },
  ],
}

const MAX = (args && args.max) || 6
const LANE = (args && args.lane) || ''   // 'request' = 依頼の係：【依頼】の段だけ（HARNESS.md「依頼の係」）
const SP = (args && args.scratch) || '/tmp/harness'
const COMMON = `リポジトリ /home/user/Wishlist（CxElegy/Wishlist）。最初に HARNESS.md・BACKLOG.md・CLAUDE.md・WORKING.md を main の最新で読み（触る分野の docs/rules/*.md も。CLAUDE.md の索引の表）、その決まりで動く。
作業は自分専用の worktree：\`git -C /home/user/Wishlist fetch -q origin main && git -C /home/user/Wishlist worktree add -f ${SP}/wt/{ID} -B harness/{ID} origin/main\`。メインの作業ツリーには書かない。一時ファイルは ${SP}/tmp/。
GitHub は mcp__github__ のツール（ToolSearch で読み込む）、Supabase は mcp__Supabase__（プロジェクト bzokpnbcjscbcehdxtjq。読む・足すだけ。DROP・DELETE・表の形を変える文はしない）。
PR は push → mcp__github__create_pull_request（本文の最後に「🤖 Generated with [Claude Code](https://claude.com/claude-code)」）。CI は get_check_runs で見て、走っている間は手元のテストや画面の点検など別の作業をする（ただ待たない）。緑なら squash で合併、赤なら直して push。
scripts/*.py か workflow を変えたら scripts/processes.py も（check_arch）。\`python -m unittest discover -s tests\` を全部通す。コミットの最後に
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
合併したら必ず python harness/ux_check.py を走らせ（本番をログインなし・test-a・test-b・test-c × 1400/390 で自動点検）、✗ があれば次の段より先に直す。そのうえで本番で確かめ（Actions の結果・データベースの行・https://cxelegy.github.io/Wishlist/home/ を 1400/390px）、BACKLOG.md のその段を [x]（PR の網址・日付）にし、気づいた次の段を足して合併する（進み具合は progress.yml が Discord に送る）。
待ち方：GitHub の定時（cron）の回が来るのを待たない（遅れる・抜ける）。確かめたいときは workflow_dispatch で起こしてその回を見る。待つ命令には必ず 15 分の上限、過ぎたら待ちをやめて次へ。
トークンの節約：コードを書くときは .claude/skills/ponytail（full）の考え、返す summary は caveman の書き方で短く（事実・数字・網址は残す。ユーザーに見せる日本語の文・画面の文字は普通の日本語）。大きな機能の前に BENCHMARKS.md（似たサイト・受賞デザイン）を読む。
設計の考え（DESIGN_PRINCIPLES.md）に照らして作る：まず店長（test1）のページで同じことをどうしているかを見て同じ部品で。あなた（ユーザー）が決める設定・見た目の方向は作る前に BACKLOG を [?] にして木の形で聞く。
エンブレム（小元素）はサイトの売り：出ない・表示が違うものはほかの段より先に、EMBLEM_PLAYBOOK.md の過去の直し方の型で規則を直す（1 枚ずつ手で直さない）。新しい壊れ方を直したら EMBLEM_PLAYBOOK.md に 1 行足す。
一番大事な決まり（HARNESS.md）：test-a・test-b などを個別に直さない（データの手直し・特定のアカウントだけの分岐はしない）、直すのはいつも規則。ログインしたお客さまはだれでも店長と同じ P5 の枠組み（令牌・硬い影・傾けた見出し・札・ポスター・版面の主題と配色・小元素・目次）を見て、違うのは中身だけ。素の箱は出さない。確かめは test-a（多い）・test-b（1 つ）・test-c（0 個）を並べて。段を終えたら PROGRESS.md に 1 行（日付・何をした・PR・確かめた結果・次）。
段を取る印：BACKLOG の `[~] … （開始 日付 時:分 JST・持ち主 {ID}）` の形で書く（持ち主 = この係の名前。書き込みのたびに「最終 日付 時:分 JST」を足す）。`python harness/claims.py BACKLOG.md --live <今動いている係の名前,…>` で持ち主のいない [~]（持ち主が動いていない・書き込みから 60 分・書き方が古い）を出し、それは取り直してよい。動いている持ち主の新しい [~] は飛ばす。「取った」と知らせるのは、その段の最初のコミットが main か PR に出てから（BACKLOG の印だけで言わない）。
設計書にない新しい決めごと・本番のデータベースの形を変える／消すことが要るときは、作らずに BACKLOG.md を [?]（聞きたいことを木の形で、案ごとに良い点・困る点とおすすめ）にして status=asked で返す。答えが設計書から決まることは聞かない。`
const RESULT = { type: 'object', properties: {
  status: { type: 'string', enum: ['done', 'asked', 'failed', 'none'] }, step: { type: 'string' }, pr: { type: 'string' }, summary: { type: 'string' } },
  required: ['status', 'summary'] }
const PLAN = { type: 'object', properties: { added: { type: 'array', items: { type: 'string' } }, pr: { type: 'string' } }, required: ['added'] }
const VERDICT = { type: 'object', properties: { ok: { type: 'boolean' }, problems: { type: 'array', items: { type: 'string' } } }, required: ['ok', 'problems'] }

const done = []
let planned = 0
for (let i = 1; i <= MAX; i++) {
  const id = `${LANE === 'request' ? 'r' : 'f'}${i}`
  let r = await agent(COMMON.replace(/\{ID\}/g, id) + `\n\nmain に hermes/ACTIVE があれば（Hermes が作る係）何もせず status=none で返す。なければ ${LANE === 'request' ? 'BACKLOG.md の【依頼】の付いた [ ] の上から最初の 1 つだけを進める（依頼の係）。取ったらまず main の BACKLOG.md でその段を [~] …（開始 日付 時:分 JST・持ち主 ${id}・依頼の係）にして push し、ふだんのループと重ならないようにする' : 'BACKLOG.md の「いちばん先」の上から最初の [ ]（持ち主のいない [~] も：claims.py で出る）を 1 つだけ進める'}。進める段がなければ（全部 [x] か [?]）何もせず status=none。最後に status・step（段の名前）・pr・summary（日本語 3 行）を返す。`,
    { label: `step:${id}`, phase: 'Step', model: 'sonnet', schema: RESULT })
  if (!r) { log(`${id}: 返事なし`); break }
  if (r.status === 'none') {
    if (LANE === 'request') { log('依頼の係：【依頼】の段がもうない'); break }
    if (planned >= 2) { log('計画を 2 回しても段がない：この回は終わる'); break }
    planned++
    const p = await agent(COMMON.replace(/\{ID\}/g, `plan${planned}`) + `\n\n計画の係。HARNESS.md「設計者として導く」と DESIGN_PRINCIPLES.md の E（考えから反推した次の一手）のやり方で、A の考えから「まだ足りないもの」を反推して段を足す（E の表にも 1 行足す）。HARNESS.md「目標から決める」で、お客さま（test-a・test-b・test-c）が 1 日使ったつもりで通し（登録 → 足す → 読む → 👍👎 → 欲しい物）、いちばん困る所から段にする。店長（test1）のページの同じ機能の作りを見て、同じ部品で直す段にする。進める段が一覧にない。HARNESS.md の目標（小さな Wikipedia・1 つの仕組み・ライブラリ・人ごとのページ・言語・入口・管理）と、本番の画面（店長・test-a・test-b・ログインなし、1400/390px）・設計書との食い違い・壊れた画像・遅いページ・テストの穴を点検し、次にやる段を 3〜6 個、BACKLOG.md に「- [ ] 段の名前 — できたと言える条件」で足して合併する（答えが要るものは [?] で）。`,
      { label: `plan:${planned}`, phase: 'Plan', model: 'sonnet', schema: PLAN })
    log(`計画：${(p && p.added || []).join(' / ')}`)
    if (!p || !(p.added || []).length) break
    i--
    continue
  }
  for (let round = 1; r.status === 'done' && round <= 2; round++) {
    const v = await agent(`${COMMON.replace(/\{ID\}/g, id + 'v' + round)}\n\n別の目として確かめるだけ（直さない）。段「${r.step}」が終わったと言っている：${r.summary}（${r.pr || ''}）。本番と HARNESS.md に照らして本当にできているか、店長のページが壊れていないか。`,
      { label: `check:${id}:${round}`, phase: 'Check', model: 'sonnet', schema: VERDICT })
    if (!v || v.ok) break
    r = await agent(COMMON.replace(/\{ID\}/g, id + 'f' + round) + `\n\n段「${r.step}」の続き。別の目の指摘を直して PR・合併・本番で確かめる：\n${v.problems.join('\n')}\n最後に同じ形で返す。`,
      { label: `fix:${id}:${round}`, phase: 'Fix', model: 'sonnet', schema: RESULT }) || r
  }
  log(`${r.step || id}: ${r.status} ${r.pr || ''}`)
  done.push(r)
  if (r.status === 'failed') break
}
return done
