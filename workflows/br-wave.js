// br-wave: runs one wave from the manifest in .plan/PLAN.md. Item (steps red, green, log, refactor, fix-tests, fix-code, fix-log, check) = agent, then one test-runner per task with the hash guard.
export const meta = {
  name: 'br-wave',
  description: 'Run a wave from the plan manifest: items (red, green, log, refactor, fix-tests, fix-code, fix-log, check) by agent, then a test-runner per task with the tests-hash guard',
  whenToUse: 'Inside a wave, after the orchestrator wrote "## Manifest <wave-id>" into .plan/PLAN.md and set the task Statuses; args = { wave }',
  phases: ['Plan', 'Preflight', 'Work', 'Check'],
}

const STEPS = ['red', 'green', 'log', 'refactor', 'fix-tests', 'fix-code', 'fix-log', 'check']
const ALLOWED = ['test-writer', 'test-runner', 'refactorer', 'coder',
  'log-writer', 'build-fixer', 'nix-engineer', 'nix-test-runner', 'optimizer', 'ui-verifier']
const MAX_AGENTS = 20
// (role, extension) -> skills. br-review.js and br-e2e.js carry the same table. Role is the agent name; `code` is the
// table for code steps (green, fix-code, refactor).
const WEB = ['react-patterns', 'vite-patterns', 'frontend-data-layer']
const SKILLS_BY_ROLE = {
  'test-writer': { '.rs': ['rust-testing'] },
  refactorer: { '.rs': ['rust-docs'] },
  optimizer: { '.rs': ['rust-perf'] },
  code: { '.dart': ['dart-flutter-patterns'], '.py': ['python-service'], '.go': ['golang-patterns'], '.ts': WEB, '.tsx': WEB, '.js': WEB, '.jsx': WEB },
}
const RULES_BY_EXT = { '.py': '~/.claude/rules/br/python.md', '.go': '~/.claude/rules/br/go.md', '.rs': '~/.claude/rules/br/rust.md', '.ts': '~/.claude/rules/br/ts-react.md', '.tsx': '~/.claude/rules/br/ts-react.md', '.js': '~/.claude/rules/br/ts-react.md', '.jsx': '~/.claude/rules/br/ts-react.md', '.dart': '~/.claude/rules/br/dart.md' }
const CODE_STEPS = ['green', 'fix-code', 'refactor']
const strArr = { type: 'array', items: { type: 'string' } }

const WORK_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'tests', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: strArr,
    tests: { type: 'array', items: { type: 'object', required: ['name', 'ac'], properties: { name: { type: 'string' }, ac: { type: 'string' }, expect_green: { type: 'boolean', description: 'true when this test must pass already (code-first or characterisation); omit otherwise' } } } },
    notes: { type: 'string' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  required: ['ran', 'passed', 'failed', 'errors', 'skipped', 'per_test', 'tests_hash', 'files_hashed', 'command', 'check_ok'],
  properties: {
    check_ok: { type: 'boolean', description: 'true when there is no check brief, or the check brief was carried out and passed; false when it failed' },
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

const HASHES_SCHEMA = {
  type: 'object',
  required: ['hashes'],
  properties: {
    hashes: { type: 'array', items: { type: 'object', required: ['id', 'hash'], properties: { id: { type: 'string' }, hash: { type: 'string' } } } },
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

// A runner name matches a writer name when equal, qualified by `.`, `::` or `/`, or followed by a subtest or
// parameter tail: `name `, `name(`, `name[...]` (pytest ids), `name/sub` (Go subtests).
function nameMatches(runner, writer) {
  const heads = ['.', '::', '/']
  const tails = [' ', '(', '[', '/']
  return runner === writer || heads.some((h) => runner.endsWith(h + writer)) ||
    tails.some((t) => runner.startsWith(writer + t) || heads.some((h) => runner.includes(h + writer + t)))
}

// Glob match for plan paths: `**` matches anything, `*` anything but `/`; a plain path also covers what is below it.
function globMatch(pat, str) {
  if (pat === '') return str === ''
  if (pat.startsWith('**')) {
    const rest = pat.slice(2)
    for (let k = 0; k <= str.length; k++) if (globMatch(rest, str.slice(k))) return true
    return false
  }
  if (pat[0] === '*') {
    const rest = pat.slice(1)
    for (let k = 0; k <= str.length; k++) {
      if (globMatch(rest, str.slice(k))) return true
      if (str[k] === '/') break
    }
    return false
  }
  return str[0] === pat[0] && globMatch(pat.slice(1), str.slice(1))
}

function covers(patterns, file) {
  return patterns.some((raw) => {
    const p = raw.split('`').join('').trim().replace('./', '')
    const dir = p.endsWith('/') ? p.slice(0, -1) : p
    return dir !== '' && (globMatch(dir, file) || file.startsWith(dir + '/'))
  })
}

function extOf(f) {
  const base = f.split('/').pop()
  const i = base.lastIndexOf('.')
  return i < 0 ? '' : base.slice(i)
}

function agentFor(item) {
  if (item.agent) return item.agent
  if (item.step === 'red' || item.step === 'fix-tests') return 'test-writer'
  if (item.step === 'refactor') return 'refactorer'
  if (item.step === 'log' || item.step === 'fix-log') return 'log-writer'
  if (item.step === 'check') return 'test-runner'
  return 'coder'
}

function neededStatus(step) {
  return step === 'red' || step === 'fix-tests' ? 'red' : step === 'green' || step === 'fix-code' ? 'green' : step === 'refactor' ? 'refactor' : step === 'log' || step === 'fix-log' ? 'log' : ''
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
    else if (need.length === 1 && t.status.trim().toLowerCase().split(' ')[0] !== need[0]) bad.push(`task ${t.id} has Status ${t.status}, its items need ${need[0]}`)
  })
  items.filter((i) => i.step !== 'check' && tasks.some((t) => t.id === i.task)).forEach((i) => {
    const task = tasks.find((t) => t.id === i.task)
    const testSide = i.step === 'red' || i.step === 'fix-tests'
    const allowed = testSide ? task.tests : task.writes
    i.files.filter((f) => !covers(allowed, f)).forEach((f) => bad.push(`${i.id}: file ${f} is outside the task's ${testSide ? 'Tests' : 'Writes'}`))
  })
  const runners = new Set(items.map((i) => i.task)).size
  const writing = items.filter((i) => i.step !== 'check' && i.files.length > 0).length
  // work agents + one hash check per writing item + the snapshot + one test-runner per task
  const total = items.filter((i) => i.step !== 'check').length + writing + (writing > 0 ? 1 : 0) + runners
  if (total > MAX_AGENTS) bad.push(`${total} agents needed, the cap is ${MAX_AGENTS}: split the wave`)
  return bad
}

async function readPlan() {
  const wave = args && typeof args.wave === 'string' ? args.wave : ''
  if (wave === '') return { stopped: true, problems: ['args.wave is missing'] }
  const plan = await agent(
    `Read .plan/PLAN.md only. Find the heading "## Manifest ${wave}" and return the fenced json block under it verbatim as manifest_text ("" if the heading or block is missing). ` +
      'Return every task that the block references (the "task" field of its items) with all fields copied verbatim from the plan; do not invent anything. ' +
      'Exception for tests: it is only the backticked paths on the task\'s "Tests (test-writer)" line; a line such as "— (validator)" with no backticked path means tests = []. ' +
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
  const tasks = plan.tasks.map((t) => ({
    ...t,
    tests: t.tests.filter((p) => {
      const isPath = p.includes('/') || p.includes('.')
      if (!isPath) log(`${t.id}: dropped Tests entry "${p}" (not a path)`)
      return isPath
    }),
  }))
  const problems = validate(items, tasks)
  return problems.length > 0 ? { stopped: true, problems } : { wave, items, tasks }
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

// One agent hashes the files of each listed item (the same command before and after the work), so staged edits count and
// pre-existing dirt does not.
async function hashItems(items, label, phase) {
  const lines = items.map((i) => `- ${i.id}: ${hashCommand(i.files)}`)
  return agent(
    `Mode: file-hash. Do not edit files and do not run tests. For each item run its command and return hashes {id, hash}; hash is the first field of the output.\n${lines.join('\n')}`,
    { agentType: 'test-runner', phase, label, schema: HASHES_SCHEMA },
  )
}

const before = {}
async function snapshot(items) {
  const w = items.filter((i) => i.step !== 'check' && i.files.length > 0)
  if (w.length === 0) return null
  const got = await hashItems(w, 'snapshot', 'Preflight')
  if (!got || !w.every((i) => got.hashes.some((h) => h.id === i.id))) return { stopped: true, problems: ['file snapshot returned nothing'] }
  w.forEach((i) => { before[i.id] = got.hashes.find((h) => h.id === i.id).hash })
  return null
}

function skillsFor(task, item) {
  const exts = [...new Set(item.files.map(extOf))]
  const tables = [SKILLS_BY_ROLE[agentFor(item)] || {}]
  const code = CODE_STEPS.includes(item.step)
  if (code) tables.push(SKILLS_BY_ROLE.code)
  const own = exts.flatMap((e) => tables.flatMap((t) => t[e] || []))
  return [...new Set([...(code ? task.skills : []), ...own])]
}

function workBrief(task, item) {
  const skills = skillsFor(task, item).map((s) => `~/.claude/skills/${s}/SKILL.md`).join(', ')
  const langRules = [...new Set(item.files.map((f) => RULES_BY_EXT[extOf(f)]).filter(Boolean))]
  const rules = langRules.length > 0 ? ['~/.claude/rules/br/code.md', ...langRules] : []
  const logging = item.step === 'log' || item.step === 'fix-log'
  return [
    `Task: ${task.id} — ${task.name}; part ${item.id} (${item.step})`,
    `Goal: ${task.goal}`,
    `Write set (only these files): ${item.files.join(', ')}`,
    `Read first: .plan/PLAN.md#${task.id.toLowerCase()}, ${task.reads.join(', ')}; skills (read them before starting): ${skills || 'none'}${logging ? ', ~/.claude/skills/logging/SKILL.md' : ''}`,
    'Acceptance criteria:',
    ...task.acceptance.map((a) => `- ${a}`),
    ...(rules.length > 0 ? [`Rule files (read them before starting): ${rules.join(', ')}`] : []),
    `Part brief: ${item.brief}`,
    'Rules: do not commit, do not edit .plan/PLAN.md; the orchestrator does both. The write hook scopes by the plan Status of the task, which the orchestrator already set.',
    item.step === 'red' || item.step === 'fix-tests'
      ? 'Return {status: done|blocked, files, tests: [{name, ac, expect_green?}], notes}; tests only, no production code; report test names as the bare test function name; set expect_green: true on a test that must pass already.'
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
  const out = { id: item.id, task: item.task, step: item.step, agent: name, result, status }
  if (status === 'done' && item.files.length > 0) {
    const got = await hashItems([item], `${item.id} diff check`, 'Check')
    const now = got ? got.hashes.find((h) => h.id === item.id) : null
    if (!now || now.hash === before[item.id]) {
      out.status = 'failed'
      out.reason = now ? 'agent reported done but its files did not change' : 'diff check returned nothing'
      log(`${item.id} failed: ${out.reason}`)
    }
  }
  return out
}

async function checkTask(task, own, done) {
  const red = own.some((i) => i.step === 'red')
  const fixTests = !red && own.some((i) => i.step === 'fix-tests')
  const out = { task: task.id, run: null, hash: '', files_hashed: 0, reason: '' }
  const key = red ? 'red_ok' : fixTests ? 'tests_ok' : 'green_ok'
  const finish = (ok, reason) => {
    log(`${task.id} ${key}: ${ok ? 'ok' : 'NOT ok'}${reason ? ` (${reason})` : ''}`)
    return { ...out, [key]: ok, reason }
  }
  const notDone = done.filter((d) => d.status !== 'done')
  if (notDone.length > 0) return finish(false, `items not done: ${notDone.map((d) => d.id).join(', ')}`)
  const noTests = task.tests.length === 0
  const checks = own.filter((i) => i.step === 'check' && i.brief !== '').map((i) => i.brief)
  if (noTests && checks.length === 0) return finish(true, 'no Tests: run skipped')
  if (!noTests && !red && !fixTests && task.recorded_hash === '') return finish(false, 'no recorded tests hash')
  const run = await agent(
    `Mode: ${noTests ? 'diff-only' : red ? 'red' : 'affected'}. Task ${task.id} — ${task.name}. Do not edit files.\n` +
      (checks.length > 0 ? `Check brief (carry it out, set check_ok false if it fails): ${checks.join(' | ')}\n` : 'No check brief: check_ok is true.\n') +
      (noTests
        ? 'This task has no Tests: do not run tests, only carry out the check brief; return ran, passed, failed, errors, skipped, files_hashed as 0, per_test [], tests_hash "", command "". '
        : `Tests: ${task.tests.join(', ')}\n` +
          'Run the task\'s tests with the project\'s command (through `nix develop -c`) and report the exact numbers. Report test names as the bare test function name. ' +
          (red ? 'For every failing test give a verdict: right_reason (fails on an assertion about missing behaviour) or wrong_reason (import, syntax or fixture error); n/a for tests that do not fail. ' : '') +
          `Compute tests_hash with exactly this command and return the first field of its output: ${hashCommand(task.tests)}\n` +
          `Also return files_hashed, the number of files matched, from this command: ${countCommand(task.tests)}\n`),
    { agentType: 'test-runner', phase: 'Check', label: `${task.id} test-runner`, schema: RUN_SCHEMA },
  )
  if (!run) return finish(false, 'test-runner returned nothing')
  out.run = run
  out.hash = run.tests_hash
  out.files_hashed = run.files_hashed
  if (!run.check_ok) return finish(false, 'check brief failed')
  if (noTests) return finish(true, 'no Tests: run skipped')
  if (run.files_hashed === 0) return finish(false, 'tests hash covers no files')
  if (red) {
    const written = done.flatMap((d) => (d.result ? d.result.tests : []))
    const expect = [...own.flatMap((i) => i.expect_green), ...written.filter((w) => w.expect_green).map((w) => w.name)]
    const failing = run.per_test.filter((t) => t.outcome === 'fail' || t.outcome === 'error')
    const isExpected = (n) => expect.some((e) => nameMatches(n, e))
    const ok = run.errors === 0 && (run.failed > 0 || written.every((w) => isExpected(w.name))) && failing.every((t) => t.verdict === 'right_reason') &&
      written.length > 0 &&
      written.every((w) => (isExpected(w.name) ? true : failing.some((t) => nameMatches(t.name, w.name)))) &&
      expect.every((e) => !failing.some((t) => nameMatches(t.name, e)))
    return finish(ok, ok ? '' : 'red check failed')
  }
  const green = run.ran > 0 && run.failed === 0 && run.errors === 0 && run.skipped === 0
  const hashOk = fixTests || run.tests_hash === task.recorded_hash
  return finish(green && hashOk, green ? (hashOk ? '' : 'tests hash changed') : 'tests not green')
}

const wave = await readPlan()
if (wave.stopped) {
  wave.problems.forEach((p) => log(`stopped: ${p}`))
  return wave
}
const login = await preflight(wave.items)
if (login) return login
const snap = await snapshot(wave.items)
if (snap) {
  snap.problems.forEach((p) => log(`stopped: ${p}`))
  return snap
}

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
