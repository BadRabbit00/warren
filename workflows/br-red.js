// br-red: test-writer writes failing tests, test-runner checks they fail for the right reason.
export const meta = {
  name: 'br-red',
  description: 'Red step for plan tasks: test-writer writes failing tests, test-runner checks they fail for the right reason',
  whenToUse: 'Inside a wave, after the orchestrator set the tasks to red',
  phases: ['Plan', 'Tests', 'Red check'],
}

const WRITER_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'tests', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: { type: 'array', items: { type: 'string' } },
    tests: {
      type: 'array',
      items: { type: 'object', required: ['name', 'ac'], properties: { name: { type: 'string' }, ac: { type: 'string' } } },
    },
    notes: { type: 'string' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  required: ['ran', 'passed', 'failed', 'errors', 'skipped', 'per_test', 'tests_hash', 'command'],
  properties: {
    ran: { type: 'integer' },
    passed: { type: 'integer' },
    failed: { type: 'integer' },
    errors: { type: 'integer' },
    skipped: { type: 'integer' },
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

function writeTests() {
  return async (task) => {
    const writer = await agent(
      brief(task, task.tests, '{status: done|blocked, files, tests: [{name, ac}], notes}; tests only, no production code'),
      { agentType: 'test-writer', phase: 'Tests', label: `${task.id} test-writer`, schema: WRITER_SCHEMA },
    )
    return { task, writer }
  }
}

function redCheck(plan) {
  return async ({ task, writer }) => {
    if (!writer || writer.status === 'blocked') {
      const reason = writer ? `test-writer blocked: ${writer.notes}` : 'test-writer returned nothing'
      log(`${task.id} stopped: ${reason}`)
      return { id: task.id, stopped: true, reason, writer, run: null, red_ok: false }
    }
    const run = await agent(
      `Mode: red. Task ${task.id} — ${task.name}. Do not edit files.\n` +
        `Tests: ${task.tests.join(', ')}\n` +
        'Run the task\'s tests with the project\'s command (through `nix develop -c`) and report the exact numbers. ' +
        'For every failing test give a verdict: right_reason (fails on an assertion about missing behaviour) or ' +
        'wrong_reason (import, syntax or fixture error); n/a for tests that do not fail. ' +
        `Compute tests_hash with: ${plan.hash_command}`,
      { agentType: 'test-runner', phase: 'Red check', label: `${task.id} test-runner`, schema: RUN_SCHEMA },
    )
    const failing = run ? run.per_test.filter((t) => t.outcome === 'fail' || t.outcome === 'error') : []
    const red_ok = Boolean(run) && run.errors === 0 && run.failed > 0 &&
      failing.every((t) => t.verdict === 'right_reason') &&
      run.per_test.every((t) => t.outcome === 'fail')
    log(`${task.id} red: ${run ? `${run.failed} failed, ${run.errors} errors, ${run.passed} passed` : 'no run'} -> ${red_ok ? 'ok' : 'NOT ok'}`)
    return { id: task.id, writer, run, red_ok }
  }
}

const plan = await readPlan('red')
if (plan.stopped) return plan

const results = await pipeline(plan.tasks, writeTests(), redCheck(plan))
return { tasks: results }
