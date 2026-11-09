// br-wave: runs one wave from the manifest in .plan/PLAN.md. Item = agent, then one test-runner per task with the hash guard.
export const meta = {
  name: 'br-wave',
  description: 'Run a wave from the plan manifest: items (red, green, refactor, fix-tests, fix-code, check) by agent, then a test-runner per task with the tests-hash guard',
  whenToUse: 'Inside a wave, after the orchestrator wrote "## Manifest <wave-id>" into .plan/PLAN.md and set the task Statuses; args = { wave }',
  phases: ['Plan', 'Preflight', 'Work', 'Check'],
}

const STEPS = ['red', 'green', 'refactor', 'fix-tests', 'fix-code', 'check']
const ALLOWED = ['test-writer', 'test-runner', 'refactorer', 'coder', 'python-coder', 'go-coder', 'ts-coder', 'rust-coder',
  'build-fixer', 'nix-engineer', 'nix-test-runner', 'optimizer', 'ui-verifier']
const MAX_AGENTS = 10
const strArr = { type: 'array', items: { type: 'string' } }

const WORK_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'tests', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: strArr,
    tests: { type: 'array', items: { type: 'object', required: ['name', 'ac'], properties: { name: { type: 'string' }, ac: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  required: ['ran', 'passed', 'failed', 'errors', 'skipped', 'per_test', 'tests_hash', 'files_hashed', 'command'],
  properties: {
    ran: { type: 'integer' }, passed: { type: 'integer' }, failed: { type: 'integer' }, errors: { type: 'integer' }, skipped: { type: 'integer' },
    per_test: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'outcome', 'verdict', 'message'],
        properties: {
          name: { type: 'string' },
          outcome: { type: 'string', enum: ['pass', 'fail', 'error', 'skip'] },
          verdict: { type: 'string', enum: ['right_reason', 'wrong_reason', 'n/a'] },
          message: { type: 'string' },
        },
      },
    },
    tests_hash: { type: 'string' },
    files_hashed: { type: 'integer' },
    command: { type: 'string' },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['manifest_text', 'tasks', 'problems'],
  properties: {
    manifest_text: { type: 'string', description: 'the fenced json block under "## Manifest <wave>", verbatim, or "" if missing' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'status', 'goal', 'writes', 'tests', 'acceptance', 'reads', 'skills', 'recorded_hash'],
        properties: {
          id: { type: 'string' }, name: { type: 'string' }, status: { type: 'string' }, goal: { type: 'string' },
          writes: strArr, tests: strArr, acceptance: strArr, reads: strArr, skills: strArr,
          recorded_hash: { type: 'string', description: 'last tests hash recorded in Evidence, or ""' },
        },
      },
    },
    problems: strArr,
  },
}

const LOGIN_SCHEMA = {
  type: 'object',
  required: ['logins'],
  properties: {
    logins: {
      type: 'array',
      items: {
        type: 'object',
        required: ['cli', 'logged_in', 'user_command'],
        properties: { cli: { type: 'string' }, logged_in: { type: 'boolean' }, user_command: { type: 'string' } },
      },
    },
  },
}

// The tests-hash command is built here from the task's Tests paths, never taken from the plan.
function shellQuote(s) {
  return "'" + String(s).split("'").join("'\\''") + "'"
}

function listFiles(paths) {
  return `git ls-files -co --exclude-standard -z -- ${paths.map(shellQuote).join(' ')}`
}

function hashCommand(paths) {
  return `set -o pipefail; ${listFiles(paths)} | LC_ALL=C sort -z | xargs -0 -r sha256sum | sha256sum`
}

function countCommand(paths) {
  return `${listFiles(paths)} | tr -cd '\\0' | wc -c`
}

// A runner name matches a writer name when equal, qualified by `.` or `::`, or a subtest (`name ` / `name(`).
function nameMatches(runner, writer) {
  return runner === writer || runner.endsWith('.' + writer) || runner.endsWith('::' + writer) ||
    runner.startsWith(writer + ' ') || runner.startsWith(writer + '(')
}

function extOf(f) {
  const base = f.split('/').pop()
  const i = base.lastIndexOf('.')
  return i < 0 ? '' : base.slice(i)
}

function coderFor(files) {
  const byExt = { '.py': 'python-coder', '.go': 'go-coder', '.ts': 'ts-coder', '.tsx': 'ts-coder', '.js': 'ts-coder', '.jsx': 'ts-coder', '.rs': 'rust-coder' }
  const names = [...new Set(files.map((f) => byExt[extOf(f)] || 'coder'))]
  return names.length === 1 ? names[0] : 'coder'
}

function agentFor(item) {
  if (item.agent) return item.agent
  if (item.step === 'red' || item.step === 'fix-tests') return 'test-writer'
  if (item.step === 'refactor') return 'refactorer'
  if (item.step === 'check') return 'test-runner'
  return coderFor(item.files)
}

function neededStatus(step) {
  return step === 'red' || step === 'fix-tests' ? 'red' : step === 'green' || step === 'fix-code' ? 'green' : step === 'refactor' ? 'refactor' : ''
}

function hasCycle(items) {
  const state = {}
  const visit = (id) => {
    if (state[id] === 2) return false
    if (state[id] === 1) return true
    state[id] = 1
    const item = items.find((i) => i.id === id)
    const cyc = item.after.some(visit)
    state[id] = 2
    return cyc
  }
  return items.some((i) => visit(i.id))
}

function validate(items, tasks) {
  const bad = []
  const ids = items.map((i) => i.id)
  items.forEach((i) => {
    if (ids.indexOf(i.id) !== ids.lastIndexOf(i.id)) bad.push(`duplicate item id ${i.id}`)
    if (!STEPS.includes(i.step)) bad.push(`${i.id}: unknown step ${i.step}`)
    if (!tasks.some((t) => t.id === i.task)) bad.push(`${i.id}: task ${i.task} not found in the plan`)
    if (i.agent && !ALLOWED.includes(i.agent)) bad.push(`${i.id}: agent ${i.agent} is not one of our agents`)
    i.after.filter((a) => !ids.includes(a)).forEach((a) => bad.push(`${i.id}: unknown after id ${a}`))
  })
  const owner = {}
  items.forEach((i) => i.files.forEach((f) => {
    if (owner[f] && owner[f] !== i.id) bad.push(`file ${f} is in two items: ${owner[f]} and ${i.id}`)
    owner[f] = i.id
  }))
  if (bad.length === 0 && hasCycle(items)) bad.push('cycle in after')
  tasks.forEach((t) => {
    const need = [...new Set(items.filter((i) => i.task === t.id).map((i) => neededStatus(i.step)).filter(Boolean))]
    if (need.length > 1) bad.push(`task ${t.id} cannot be ${need.join(' and ')} in the same run`)
    else if (need.length === 1 && t.status.toLowerCase() !== need[0]) bad.push(`task ${t.id} has Status ${t.status}, its items need ${need[0]}`)
  })
  const runners = new Set(items.map((i) => i.task)).size
  const total = items.filter((i) => i.step !== 'check').length + runners
  if (total > MAX_AGENTS) bad.push(`${total} agents needed, the cap is ${MAX_AGENTS}: split the wave`)
  return bad
}

async function readPlan() {
  const wave = args && typeof args.wave === 'string' ? args.wave : ''
  if (wave === '') return { stopped: true, problems: ['args.wave is missing'] }
  const plan = await agent(
    `Read .plan/PLAN.md only. Find the heading "## Manifest ${wave}" and return the fenced json block under it verbatim as manifest_text ("" if the heading or block is missing). ` +
      'Return every task that the block references (the "task" field of its items) with all fields copied verbatim from the plan; do not invent anything. ' +
      'Put in problems every referenced task id that is not in the plan.',
    { agentType: 'researcher', label: 'plan', phase: 'Plan', schema: PLAN_SCHEMA },
  )
  if (!plan) return { stopped: true, problems: ['plan reader returned nothing'] }
  if (plan.problems.length > 0) return { stopped: true, problems: plan.problems }
  let manifest = null
  try { manifest = JSON.parse(plan.manifest_text) } catch (e) { manifest = null }
  if (!manifest || !Array.isArray(manifest.items) || manifest.items.length === 0) {
    return { stopped: true, problems: [`manifest ${wave} is missing, not valid JSON, or has no items`] }
  }
  const items = manifest.items.map((i) => ({ ...i, files: i.files || [], after: i.after || [], expect_green: i.expect_green || [], needs_login: i.needs_login || [], brief: i.brief || '' }))
  const problems = validate(items, plan.tasks)
  return problems.length > 0 ? { stopped: true, problems } : { wave, items, tasks: plan.tasks }
}

async function preflight(items) {
  const clis = [...new Set(items.flatMap((i) => i.needs_login))]
  if (clis.length === 0) return null
  const got = await agent(
    `Check the login of each CLI: ${clis.join(', ')}. Use the status commands from the cli-* skills, through \`nix shell nixpkgs#<pkg> -c <cmd>\`; read-only. ` +
      'For each CLI return logged_in and, when not logged in, user_command: the exact one command the user runs as `! nix shell nixpkgs#<pkg> -c <cmd>`.',
    { agentType: 'log-collector', label: 'login preflight', phase: 'Preflight', schema: LOGIN_SCHEMA },
  )
  if (!got) return { stopped: true, problems: ['login preflight returned nothing'] }
  const missing = got.logins.filter((l) => !l.logged_in)
  missing.forEach((l) => log(`stopped: ${l.cli} is not logged in`))
  return missing.length > 0 ? { stopped: true, problems: ['login needed'], login_needed: missing.map((l) => ({ cli: l.cli, user_command: l.user_command })) } : null
}

function workBrief(task, item) {
  const skills = task.skills.map((s) => `~/.claude/skills/${s}/SKILL.md`).join(', ')
  return [
    `Task: ${task.id} — ${task.name}; part ${item.id} (${item.step})`,
    `Goal: ${task.goal}`,
    `Write set (only these files): ${item.files.join(', ')}`,
    `Read first: .plan/PLAN.md#${task.id.toLowerCase()}, ${task.reads.join(', ')}; skills (read them before starting): ${skills || 'none'}`,
    'Acceptance criteria:',
    ...task.acceptance.map((a) => `- ${a}`),
    `Part brief: ${item.brief}`,
    'Rules: do not commit, do not edit .plan/PLAN.md; the orchestrator does both. The write hook scopes by the plan Status of the task, which the orchestrator already set.',
    item.step === 'red' || item.step === 'fix-tests'
      ? 'Return {status: done|blocked, files, tests: [{name, ac}], notes}; tests only, no production code; report test names as the bare test function name.'
      : 'Return {status: done|blocked, files, tests: [], notes}. Behaviour of the tests must not change; do not touch the tests.',
    'Stop and report instead of guessing if: a contract looks wrong, a file outside the write set is needed, an AC is unclear.',
  ].join('\n')
}

async function runItem(item, task) {
  if (item.step === 'check') return { id: item.id, task: item.task, step: item.step, agent: 'test-runner', result: null, status: 'done' }
  const name = agentFor(item)
  const result = await agent(workBrief(task, item), { agentType: name, phase: 'Work', label: `${item.id} ${name}`, schema: WORK_SCHEMA })
  const status = !result ? 'failed' : result.status === 'blocked' ? 'blocked' : 'done'
  if (status !== 'done') log(`${item.id} ${status}: ${result ? result.notes : name + ' returned nothing'}`)
  return { id: item.id, task: item.task, step: item.step, agent: name, result, status }
}

async function checkTask(task, own, done) {
  const red = own.some((i) => neededStatus(i.step) === 'red')
  const out = { task: task.id, run: null, hash: '', files_hashed: 0, reason: '' }
  const key = red ? 'red_ok' : 'green_ok'
  const finish = (ok, reason) => {
    log(`${task.id} ${key}: ${ok ? 'ok' : 'NOT ok'}${reason ? ` (${reason})` : ''}`)
    return { ...out, [key]: ok, reason }
  }
  const notDone = done.filter((d) => d.status !== 'done')
  if (notDone.length > 0) return finish(false, `items not done: ${notDone.map((d) => d.id).join(', ')}`)
  if (task.tests.length === 0) return finish(true, 'no Tests: run skipped')
  if (!red && task.recorded_hash === '') return finish(false, 'no recorded tests hash')
  const checks = own.filter((i) => i.step === 'check' && i.brief !== '').map((i) => i.brief)
  const run = await agent(
    `Mode: ${red ? 'red' : 'affected'}. Task ${task.id} — ${task.name}. Do not edit files.\n` +
      `Tests: ${task.tests.join(', ')}\n` +
      (checks.length > 0 ? `Check brief: ${checks.join(' | ')}\n` : '') +
      'Run the task\'s tests with the project\'s command (through `nix develop -c`) and report the exact numbers. Report test names as the bare test function name. ' +
      (red ? 'For every failing test give a verdict: right_reason (fails on an assertion about missing behaviour) or wrong_reason (import, syntax or fixture error); n/a for tests that do not fail. ' : '') +
      `Compute tests_hash with exactly this command and return the first field of its output: ${hashCommand(task.tests)}\n` +
      `Also return files_hashed, the number of files matched, from this command: ${countCommand(task.tests)}`,
    { agentType: 'test-runner', phase: 'Check', label: `${task.id} test-runner`, schema: RUN_SCHEMA },
  )
  if (!run) return finish(false, 'test-runner returned nothing')
  out.run = run
  out.hash = run.tests_hash
  out.files_hashed = run.files_hashed
  if (run.files_hashed === 0) return finish(false, 'tests hash covers no files')
  if (red) {
    const written = done.flatMap((d) => (d.result ? d.result.tests : []))
    const expect = own.flatMap((i) => i.expect_green)
    const failing = run.per_test.filter((t) => t.outcome === 'fail' || t.outcome === 'error')
    const isExpected = (n) => expect.some((e) => nameMatches(n, e))
    const ok = run.errors === 0 && run.failed > 0 && failing.every((t) => t.verdict === 'right_reason') &&
      written.length > 0 &&
      written.every((w) => (isExpected(w.name) ? true : failing.some((t) => nameMatches(t.name, w.name)))) &&
      expect.every((e) => !failing.some((t) => nameMatches(t.name, e)))
    return finish(ok, ok ? '' : 'red check failed')
  }
  const green = run.ran > 0 && run.failed === 0 && run.errors === 0 && run.skipped === 0
  const hashOk = run.tests_hash === task.recorded_hash
  return finish(green && hashOk, green ? (hashOk ? '' : 'tests hash changed') : 'tests not green')
}

const wave = await readPlan()
if (wave.stopped) {
  wave.problems.forEach((p) => log(`stopped: ${p}`))
  return wave
}
const login = await preflight(wave.items)
if (login) return login

const started = {}
function start(item) {
  if (!started[item.id]) {
    started[item.id] = (async () => {
      const deps = await Promise.all(item.after.map((a) => start(wave.items.find((i) => i.id === a))))
      const bad = deps.filter((d) => d.status !== 'done')
      if (bad.length > 0) {
        log(`${item.id} skipped: dependency not done (${bad.map((d) => d.id).join(', ')})`)
        return { id: item.id, task: item.task, step: item.step, agent: agentFor(item), result: null, status: 'blocked' }
      }
      return runItem(item, wave.tasks.find((t) => t.id === item.task))
    })()
  }
  return started[item.id]
}

const taskResults = await parallel(
  wave.tasks.filter((t) => wave.items.some((i) => i.task === t.id)).map((task) => async () => {
    const own = wave.items.filter((i) => i.task === task.id)
    const done = await Promise.all(own.map(start))
    const checked = await checkTask(task, own, done)
    return { checked, done }
  }),
)

const finished = taskResults.filter(Boolean)
return {
  wave: wave.wave,
  items: finished.flatMap((r) => r.done),
  tasks: finished.map((r) => r.checked),
  problems: taskResults.length === finished.length ? [] : ['a task run returned nothing'],
}
