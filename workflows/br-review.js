// br-review: reviewers in parallel, then three refuters per must-fix finding.
export const meta = {
  name: 'br-review',
  description: 'Review step for plan tasks: code-reviewer, language reviewers and security-reviewer in parallel, then three refuters per must-fix',
  whenToUse: 'Inside a wave, after the tasks are green and the orchestrator set them to review',
  phases: ['Plan', 'Review', 'Verify'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings', 'commands'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'file', 'line', 'title', 'evidence', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['must_fix', 'suboptimal', 'nit'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          title: { type: 'string' },
          evidence: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
    commands: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['refuted', 'reason'],
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
}

const BY_EXTENSION = {
  py: 'python-reviewer',
  go: 'go-reviewer',
  rs: 'rust-reviewer',
  ts: 'ts-react-reviewer',
  tsx: 'ts-react-reviewer',
  dart: 'flutter-dart-reviewer',
  nix: 'nix-reviewer',
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

function pickReviewers(task) {
  const names = ['code-reviewer']
  for (const file of [...task.writes, ...task.tests]) {
    const m = /\.([a-z]+)$/.exec(file)
    const reviewer = m ? BY_EXTENSION[m[1]] : undefined
    if (reviewer && !names.includes(reviewer)) names.push(reviewer)
  }
  if (names.length === 1) log(`${task.id}: no language reviewer for these paths, code-reviewer only`)
  if (task.security_relevant || (args && args.security === true)) names.push('security-reviewer')
  return names
}

function reviewTask(plan) {
  return async (task) => {
    const reviewers = pickReviewers(task)
    const paths = [...task.writes, ...task.tests].join(' ')
    const prompt = (name) =>
      `Review task ${task.id} — ${task.name} as ${name}. Read-only: do not edit files, do not commit.\n` +
      `Diff: git diff ${plan.base_branch}...HEAD -- ${paths}\n` +
      'Check it against the acceptance criteria:\n' +
      task.acceptance.map((a) => `- ${a}`).join('\n') +
      '\nReturn findings with severity must_fix, suboptimal or nit, each with file, line, evidence and fix.'
    const outcomes = await parallel(
      reviewers.map((name) => () =>
        agent(prompt(name), { agentType: name, phase: 'Review', label: `${task.id} ${name}`, schema: FINDINGS_SCHEMA })),
    )
    const findings = []
    outcomes.forEach((o, i) => {
      if (!o) return log(`${task.id}: ${reviewers[i]} returned nothing`)
      o.findings.forEach((f) => findings.push({ ...f, reviewer: reviewers[i] }))
    })
    return { task, reviewers, findings }
  }
}

function verifyTask() {
  return async ({ task, reviewers, findings }) => {
    const mustFix = findings.filter((f) => f.severity === 'must_fix')
    const checked = await parallel(
      mustFix.map((f) => async () => {
        const verdicts = await parallel(
          [1, 2, 3].map((n) => () =>
            agent(
              `Try to refute this finding about task ${task.id}. Read-only; read the code. ` +
                'Set refuted=false unless you can reproduce the problem or point to the exact line that disproves the finding.\n' +
                `Finding (${f.reviewer}): ${f.title}\n${f.file}:${f.line}\nEvidence: ${f.evidence}\nFix: ${f.fix}`,
              { agentType: 'code-reviewer', phase: 'Verify', label: `${task.id} refute ${n}/3`, schema: VERDICT_SCHEMA },
            )),
        )
        const got = verdicts.filter(Boolean)
        const upheld = got.filter((v) => !v.refuted).length
        const verdict = got.length < 2 ? 'unverified' : upheld >= 2 ? 'survives' : 'refuted'
        return { ...f, verdict, verdicts: got }
      }),
    )
    checked.filter((f) => f.verdict !== 'survives').forEach((f) => log(`${task.id}: "${f.title}" ${f.verdict}`))
    return {
      id: task.id,
      reviewers,
      must_fix: checked.filter((f) => f.verdict === 'survives'),
      refuted: checked.filter((f) => f.verdict === 'refuted'),
      unverified: checked.filter((f) => f.verdict === 'unverified'),
      suboptimal: findings.filter((f) => f.severity === 'suboptimal'),
      nits: findings.filter((f) => f.severity === 'nit'),
    }
  }
}

const plan = await readPlan('review')
if (plan.stopped) return plan

const results = await pipeline(plan.tasks, reviewTask(plan), verifyTask())
return { tasks: results }
