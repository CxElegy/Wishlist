// harness-v2.js を、係（agent）・parallel・log を偽物にして 1 回通す（tests/test_harness_v2.py が node で呼ぶ）。
//   node tests/fixtures/harness_v2_smoke.js <happy|stuck> ['{"model":"fable"}']
// 出力（JSON）：calls＝呼ばれた係の順（label・model・phase・agentType）、logs、result（台本の返り値）、prompts（label → 文）
const fs = require('fs'), path = require('path')
const scenario = process.argv[2] || 'happy'
const args = Object.assign({ run: 'smoke' }, JSON.parse(process.argv[3] || '{}'))
const src = fs.readFileSync(path.join(__dirname, '..', '..', '.claude', 'workflows', 'harness-v2.js'), 'utf8')
if (!/^export const meta = \{/.test(src)) throw new Error('台本は export const meta = {...} で始める')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const body = new AsyncFunction('args', 'agent', 'log', 'phase', 'parallel', 'pipeline', src.replace(/^export const meta/, 'const meta'))
const meta = new Function('return ' + src.match(/^export const meta = (\{[\s\S]*?\n\})\n/)[1])()   // 変数・関数を使わない純粋な値であること

const calls = [], logs = [], prompts = {}, seen = {}
const built = id => ({ status: 'built', branch: `harness/smoke-${id}`, worktree: `D:/x/wt/${id}`, commit: `c${(seen['b' + id] = (seen['b' + id] || 0) + 1)}`, summary: '作った',
  screens: [{ page: 'home/index.html', sel: '#sec-a' }], prod_check: { url: 'https://example.invalid/home/', contains: 'marker' },
  choice_url: 'https://example.invalid/testground/choice-t-0003.html', question: 'どの案にしますか' })
const TASKS = {
  happy: [
    { id: 'T-0001', title: '見た目の段', kind: 'visual', complexity: 'hard', scope: ['docs/home/style.css'], done_when: ['A1 の空き 0'] },
    { id: 'T-0002', title: '重なる段', kind: 'fix', complexity: 'normal', scope: ['./Docs/home/style.css', 'scripts/x.py'], done_when: ['試験が通る'] },
    { id: 'T-0003', title: '案の段', kind: 'options', complexity: 'normal', scope: ['docs/testground/choice-t-0003.html'], done_when: ['案が 3 つ'] },
    { id: 'T-0004', title: '毎回の点検', kind: 'kpi', complexity: 'light', scope: ['harness/board_kpi.py'], done_when: ['数字が出る'] },
  ],
  stuck: [{ id: 'T-0009', title: '直らない段', kind: 'fix', complexity: 'light', scope: ['scripts/y.py'], done_when: ['試験が通る'] }],
}
async function agent(prompt, opts) {
  const label = opts.label, [role, id, n] = label.split(':')
  calls.push({ label, model: opts.model || '', phase: opts.phase || '', agentType: opts.agentType || '', schema: !!opts.schema })
  prompts[label] = prompt
  if (role === 'intake') return scenario === 'happy' ? { status: 'done', branch: 'harness/smoke-intake1', worktree: 'D:/x/wt/intake1', tasks: ['T-0100'], replies: 1, summary: '1 件を決まりと段に' } : { status: 'none', summary: '0 件' }
  if (role === 'verify') return { results: n === 'a' ? [] : (prompt.match(/^- (T-\d+)/gm) || []).map(m => ({ id: m.slice(2), live: true })) }
  if (role === 'plan') return { tasks: calls.filter(c => c.label.startsWith('plan:')).length === 1 ? TASKS[scenario] : [] }
  if (role === 'scout') return { map: 'scripts/x.py:1 — 入口' }
  if (role === 'build' || role === 'fix' || role === 'kpi') return built(id)
  if (role === 'evalF') return scenario === 'stuck' ? { ok: false, problems: ['条件 1：試験 test_y が赤'], signature: '1|test_y' } : { ok: true, problems: [], signature: '' }
  if (role === 'evalV') {   // 1 回目は「ok と言いながら番号に ✗」：台本が不合格にするはず
    const first = n === '0' && id === 'T-0001'
    return { ok: true, problems: first ? ['A1：写真の下に 40px の帯'] : [], signature: first ? 'A1@sec-a' : '', rules: [{ id: 'A1', pass: !first, shot: 's.png', why: '' }] }
  }
  if (role === 'diag') return { plan: '原因：…\n1. …' }
  if (role === 'ship') return { status: 'merged', pr: `https://github.com/x/y/pull/${calls.length}`, sha: 'abc1234', summary: '合併' }
  if (role === 'announce' || role === 'learn') return { ok: true, summary: '' }
  throw new Error('知らない係 ' + label)
}
const parallel = thunks => Promise.all(thunks.map(f => Promise.resolve().then(f).catch(e => { logs.push('ERR ' + e.message); return null })))
body(args, agent, m => logs.push(m), () => {}, parallel, async () => { throw new Error('pipeline は使わない') })
  .then(result => process.stdout.write(JSON.stringify({ meta, calls, logs, result, prompts })))
  .catch(e => { console.error(e); process.exit(1) })
