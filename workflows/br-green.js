// br-green: coder, test-runner, refactorer, test-runner, with the tests-hash guard.
export const meta = {
  name: 'br-green',
  description: 'Green and refactor steps for plan tasks: coder, test-runner, refactorer, test-runner with the tests-hash guard',
  whenToUse: 'Inside a wave, after the red step passed and the orchestrator set the tasks to green',
  phases: ['Plan', 'Code', 'Green check', 'Refactor', 'Refactor check'],
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
  required: ['ran', 'passed', 'failed', 'errors', 'skipped', 'tests_hash', 'command'],
  properties: {
    ran: { type: 'integer' },
    passed: { type: 'integer' },
    failed: { type: 'integer' },
    errors: { type: 'integer' },
    skipped: { type: 'integer' },
    tests_hash: { type: 'string' },
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
    hash_command: { type: 'string' },
    base_branch: { type: 'string' },
  },
}

// Stage 0, shared by all br workflows: read the plan, nothing else.
async function readPlan(status) {
  const ids = args && Array.isArray(args.tasks) ? args.tasks : null
  const which = ids
    ? `the tasks with these ids: ${ids.join(', ')}. Report in problems every requested id that is missing or whose Status is not exactly "${status}".`
    : `every task whose Status is exactly "${status}".`
  const plan = await agent(
    `Read .plan/PLAN.md only. Return ${which}\n` +
      'Copy every field verbatim from the plan; do not invent anything. ' +
      'Also return hash_command (the tests-hash line from the plan, in the form ' +
      '"git ls-files -co --exclude-standard -- <Tests globs> | sort | xargs sha256sum | sha256sum") and base_branch ("develop").',
    { agentType: 'researcher', label: 'plan', phase: 'Plan', schema: PLAN_SCHEMA },
  )
  if (!plan) return { stopped: true, problems: ['plan reader returned nothing'] }
  if (plan.problems.length > 0) {
    plan.problems.forEach((p) => log(`stopped: ${p}`))
    return { stopped: true, problems: plan.problems }
  }
  if (plan.tasks.length === 0) return { stopped: true, problems: [`no tasks with status ${status}`] }
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
  const run = await agent(
    `Mode: affected. Task ${task.id} — ${task.name}. Do not edit files.\n` +
      `Tests: ${task.tests.join(', ')}\n` +
      'Run the task\'s tests with the project\'s command (through `nix develop -c`) and report the exact numbers. ' +
      `Compute tests_hash with: ${plan.hash_command}`,
    { agentType: 'test-runner', phase: phaseTitle, label: `${task.id} test-runner`, schema: RUN_SCHEMA },
  )
  const hashOk = Boolean(run) && (task.recorded_hash === '' || run.tests_hash === task.recorded_hash)
  return { run, ok: isGreen(run) && hashOk, hashOk }
}

function code() {
  return async (task) => {
    const coder = await agent(
      brief(task, task.writes, '{status: done|blocked, files, notes}'),
      { agentType: 'coder', phase: 'Code', label: `${task.id} coder`, schema: CODER_SCHEMA },
    )
    return { task, coder }
  }
}

function greenCheck(plan) {
  return async (state) => {
    if (!state.coder || state.coder.status === 'blocked') {
      return stop(state, state.coder ? `coder blocked: ${state.coder.notes}` : 'coder returned nothing')
    }
    const { run, ok, hashOk } = await check(plan, state, 'Green check')
    if (!ok) return stop({ ...state, green: run }, run ? (hashOk ? 'tests not green' : 'tests hash changed') : 'test-runner returned nothing')
    return { ...state, green: run }
  }
}

function refactor() {
  return async (state) => {
    if (state.stopped) return state
    const task = state.task
    const refactorer = await agent(
      brief(task, task.writes, '{status: done|blocked, files, changes: [string], notes}') +
        '\nBehaviour must stay unchanged; do not touch the tests.',
      { agentType: 'refactorer', phase: 'Refactor', label: `${task.id} refactorer`, schema: REFACTOR_SCHEMA },
    )
    if (!refactorer || refactorer.status === 'blocked') {
      return stop({ ...state, refactorer }, refactorer ? `refactorer blocked: ${refactorer.notes}` : 'refactorer returned nothing')
    }
    return { ...state, refactorer }
  }
}

function refactorCheck(plan) {
  return async (state) => {
    if (state.stopped) return state
    const { run, ok, hashOk } = await check(plan, state, 'Refactor check')
    if (!ok) return stop({ ...state, refactor_run: run }, run ? (hashOk ? 'tests not green after refactor' : 'tests hash changed after refactor') : 'test-runner returned nothing')
    log(`${state.task.id} done`)
    return { ...state, refactor_run: run, done: true }
  }
}

const plan = await readPlan('green')
if (plan.stopped) return plan

const results = await pipeline(plan.tasks, code(), greenCheck(plan), refactor(), refactorCheck(plan))
return {
  tasks: results.map((r) => ({
    id: r.task.id,
    coder: r.coder || null,
    green: r.green || null,
    refactorer: r.refactorer || null,
    refactor_run: r.refactor_run || null,
    done: Boolean(r.done),
    reason: r.reason || '',
  })),
}
