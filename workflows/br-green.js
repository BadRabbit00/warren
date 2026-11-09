// br-green: one step per task by its plan Status (green: coder; refactor: refactorer), then test-runner, with the tests-hash guard.
export const meta = {
  name: 'br-green',
  description: 'Green or refactor step per task by its plan Status: coder or refactorer, then test-runner with the tests-hash guard',
  whenToUse: 'Inside a wave: run once with tasks at Status green (coder), then again with tasks at Status refactor (refactorer)',
  phases: ['Plan', 'Code', 'Refactor', 'Check'],
}

const CODER_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const REFACTOR_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'changes', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: { type: 'array', items: { type: 'string' } },
    changes: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  required: ['ran', 'passed', 'failed', 'errors', 'skipped', 'tests_hash', 'files_hashed', 'command'],
  properties: {
    ran: { type: 'integer' },
    passed: { type: 'integer' },
    failed: { type: 'integer' },
    errors: { type: 'integer' },
    skipped: { type: 'integer' },
    tests_hash: { type: 'string' },
    files_hashed: { type: 'integer' },
    command: { type: 'string' },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['tasks', 'problems'],
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'status', 'goal', 'writes', 'tests', 'acceptance', 'reads', 'skills', 'recorded_hash', 'security_relevant'],
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          status: { type: 'string' },
          goal: { type: 'string' },
          writes: { type: 'array', items: { type: 'string' } },
          tests: { type: 'array', items: { type: 'string' } },
          acceptance: { type: 'array', items: { type: 'string' } },
          reads: { type: 'array', items: { type: 'string' } },
          skills: { type: 'array', items: { type: 'string' } },
          recorded_hash: { type: 'string', description: 'last tests hash recorded in Evidence, or ""' },
          security_relevant: { type: 'boolean', description: 'Writes touch auth, input handling, secrets, files, network calls, or the task says so' },
        },
      },
    },
    problems: { type: 'array', items: { type: 'string' }, description: 'requested ids missing or with a different Status' },
  },
}

// The tests-hash command is built here from the task's Tests paths, never taken from the plan.
function shellQuote(s) {
  return "'" + String(s).split("'").join("'\\''") + "'"
}

function hashCommand(paths) {
  return `set -o pipefail; ${listFiles(paths)} | sort -z | xargs -0 -r sha256sum | sha256sum`
}

function listFiles(paths) {
  return `git ls-files -co --exclude-standard -z -- ${paths.map(shellQuote).join(' ')}`
}

function countCommand(paths) {
  return `${listFiles(paths)} | tr -cd '\\0' | wc -c`
}

// Stage 0, shared by all br workflows: read the plan, nothing else.
async function readPlan(statuses) {
  const list = statuses.map((x) => `"${x}"`).join(' or ')
  const ids = args && Array.isArray(args.tasks) ? args.tasks : null
  const which = ids
    ? `the tasks with these ids: ${ids.join(', ')}. Report in problems every requested id that is missing or whose Status is not exactly ${list}.`
    : `every task whose Status is exactly ${list}.`
  const plan = await agent(
    `Read .plan/PLAN.md only. Return ${which}\n` +
      'Copy every field verbatim from the plan; do not invent anything.',
    { agentType: 'researcher', label: 'plan', phase: 'Plan', schema: PLAN_SCHEMA },
  )
  if (!plan) return { stopped: true, problems: ['plan reader returned nothing'] }
  if (plan.problems.length > 0) {
    plan.problems.forEach((p) => log(`stopped: ${p}`))
    return { stopped: true, problems: plan.problems }
  }
  if (plan.tasks.length === 0) return { stopped: true, problems: [`no tasks with status ${statuses.join(' or ')}`] }
  return plan
}

// Standard brief; `files` is the write set for the role.
function brief(task, files, ret) {
  const skills = task.skills.map((s) => `~/.claude/skills/${s}/SKILL.md`).join(', ')
  return [
    `Task: ${task.id} — ${task.name}`,
    `Goal: ${task.goal}`,
    `Write set: ${files.join(', ')}`,
    `Read first: .plan/PLAN.md#${task.id.toLowerCase()}, ${task.reads.join(', ')}; skills (read them before starting): ${skills || 'none'}`,
    'Acceptance criteria:',
    ...task.acceptance.map((a) => `- ${a}`),
    'Rules: do not commit, do not edit .plan/PLAN.md; the orchestrator does both.',
    `Return: ${ret}`,
    'Stop and report instead of guessing if: a contract looks wrong, a file outside the write set is needed, an AC is unclear.',
  ].join('\n')
}

function stop(state, reason) {
  log(`${state.task.id} stopped: ${reason}`)
  return { ...state, stopped: true, reason, done: false }
}

function isGreen(run) {
  return Boolean(run) && run.ran > 0 && run.failed === 0 && run.errors === 0 && run.skipped === 0
}

// Runs the task's tests and applies the green + hash rule; `phaseTitle` is the meta phase.
async function check(plan, state, phaseTitle) {
  const task = state.task
  if (task.tests.length === 0) return { run: null, ok: true, hashOk: true }
  if (task.recorded_hash === '') return { run: null, ok: false, hashOk: false, noHash: true }
  const run = await agent(
    `Mode: affected. Task ${task.id} — ${task.name}. Do not edit files.\n` +
      `Tests: ${task.tests.join(', ')}\n` +
      'Run the task\'s tests with the project\'s command (through `nix develop -c`) and report the exact numbers. ' +
      `Compute tests_hash with exactly this command and return the first field of its output: ${hashCommand(task.tests)}\n` +
        `Also return files_hashed, the number of files matched, from this command: ${countCommand(task.tests)}`,
    { agentType: 'test-runner', phase: phaseTitle, label: `${task.id} test-runner`, schema: RUN_SCHEMA },
  )
  if (run && run.files_hashed === 0) return { run, ok: false, hashOk: false, noFiles: true }
  const hashOk = Boolean(run) && run.tests_hash === task.recorded_hash
  return { run, ok: isGreen(run) && hashOk, hashOk }
}

// The write hook allows coder only under Status green and refactorer only under refactor,
// so each task runs the one step its Status names.
function work() {
  return async (task) => {
    if (task.status === 'refactor') {
      const refactorer = await agent(
        brief(task, task.writes, '{status: done|blocked, files, changes: [string], notes}') +
          '\nBehaviour must stay unchanged; do not touch the tests.',
        { agentType: 'refactorer', phase: 'Refactor', label: `${task.id} refactorer`, schema: REFACTOR_SCHEMA },
      )
      return { task, step: 'refactor', worker: refactorer }
    }
    const coder = await agent(
      brief(task, task.writes, '{status: done|blocked, files, notes}'),
      { agentType: 'coder', phase: 'Code', label: `${task.id} coder`, schema: CODER_SCHEMA },
    )
    return { task, step: 'green', worker: coder }
  }
}

function verify(plan) {
  return async (state) => {
    const who = state.step === 'refactor' ? 'refactorer' : 'coder'
    if (!state.worker || state.worker.status === 'blocked') {
      return stop(state, state.worker ? `${who} blocked: ${state.worker.notes}` : `${who} returned nothing`)
    }
    const { run, ok, hashOk, noHash, noFiles } = await check(plan, state, 'Check')
    if (noHash) return stop(state, 'no recorded tests hash')
    if (noFiles) return stop({ ...state, run }, 'tests hash covers no files')
    const after = state.step === 'refactor' ? ' after refactor' : ''
    if (!ok) return stop({ ...state, run }, run ? (hashOk ? `tests not green${after}` : `tests hash changed${after}`) : 'test-runner returned nothing')
    log(`${state.task.id} done`)
    return { ...state, run, done: true }
  }
}

const plan = await readPlan(['green', 'refactor'])
if (plan.stopped) return plan

const results = await pipeline(plan.tasks, work(), verify(plan))
return {
  tasks: results.map((r) => ({
    id: r.task.id,
    step: r.step,
    agent: r.worker || null,
    run: r.run || null,
    done: Boolean(r.done),
    reason: r.reason || '',
  })),
}
