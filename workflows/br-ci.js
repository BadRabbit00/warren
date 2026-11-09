// br-ci: write or fix CI workflows (files end in -br), check them locally, hand the push to the orchestrator, then read the failed ci-test runs.
export const meta = {
  name: 'br-ci',
  description: 'Write or change GitHub Actions workflows with ci-engineer, check them locally (actionlint, zizmor, project linters); after the user pushes ci-test, read the failed runs and fix them (at most 2 rounds)',
  whenToUse: 'For a CI task; args = { task?, files, brief, max_rounds?, after_push?, round?, id? }. The first run returns ready_to_push; the orchestrator pushes ci-test, then runs it again with after_push: true',
  phases: ['Preflight', 'Write', 'Check', 'Collect', 'Analyse', 'Fix'],
}

const MAX_AGENTS = 10
const HARD_ROUNDS = 2
const strArr = { type: 'array', items: { type: 'string' } }

const WORK_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: strArr,
    notes: { type: 'string' },
  },
}

const CHECK_SCHEMA = {
  type: 'object',
  required: ['ok', 'checks'],
  properties: {
    ok: { type: 'boolean' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['command', 'ok', 'output'],
        properties: { command: { type: 'string' }, ok: { type: 'boolean' }, output: { type: 'string', description: 'bounded excerpt of the failure, empty when ok' } },
      },
    },
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

const COLLECT_SCHEMA = {
  type: 'object',
  required: ['failed_runs', 'excerpt_paths', 'summary'],
  properties: {
    failed_runs: { type: 'array', items: { type: 'object', required: ['id', 'workflow', 'conclusion'], properties: { id: { type: 'string' }, workflow: { type: 'string' }, conclusion: { type: 'string' } } } },
    excerpt_paths: strArr,
    summary: { type: 'string' },
  },
}

const ANALYSIS_SCHEMA = {
  type: 'object',
  required: ['cause', 'evidence', 'fix', 'confidence', 'collect_more'],
  properties: {
    cause: { type: 'string' },
    evidence: { type: 'array', items: { type: 'object', required: ['line', 'source'], properties: { line: { type: 'string' }, source: { type: 'string' } } } },
    fix: { type: 'object', required: ['agent', 'files', 'steps'], properties: { agent: { type: 'string' }, files: strArr, steps: strArr } },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
    collect_more: strArr,
  },
}

function shellQuote(s) {
  return "'" + String(s).split("'").join("'\\''") + "'"
}

// Run id for docs/temp: letters, digits, - and _ only.
function safeId(s) {
  const ok = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
  const out = String(s).split('').map((c) => (ok.includes(c) ? c : '-')).join('')
  return out === '' ? 'run' : out.slice(0, 40)
}

function stemOf(f) {
  const base = f.split('/').pop()
  const i = base.lastIndexOf('.')
  return i <= 0 ? base : base.slice(0, i)
}

let used = 0
function take(label) {
  if (used >= MAX_AGENTS) {
    log(`skipped ${label}: agent cap ${MAX_AGENTS} reached`)
    return false
  }
  used += 1
  return true
}

const a = args || {}
const files = Array.isArray(a.files) ? a.files.filter((f) => typeof f === 'string' && f !== '') : []
const brief = typeof a.brief === 'string' ? a.brief : ''
const task = typeof a.task === 'string' ? a.task : ''
const afterPush = a.after_push === true
const maxRounds = Math.min(Number.isInteger(a.max_rounds) && a.max_rounds > 0 ? a.max_rounds : HARD_ROUNDS, HARD_ROUNDS)
const dir = `docs/temp/br-ci-${safeId(a.id || task || 'run')}`

const problems = []
if (files.length === 0) problems.push('args.files is missing or empty')
if (brief === '') problems.push('args.brief is missing')
files.filter((f) => f.startsWith('.github/workflows/') && !stemOf(f).endsWith('-br')).forEach((f) => problems.push(`${f}: workflow files written by the warren end in -br`))
if (problems.length > 0) {
  problems.forEach((p) => log(`stopped: ${p}`))
  return { stopped: true, problems }
}

function engineerBrief(extra) {
  return [
    `Task: ${task || 'CI change'}`,
    `Write set (only these files): ${files.join(', ')}`,
    `Brief: ${brief}`,
    extra,
    'Rules: do not commit, do not push, do not touch the ci-test branch; the orchestrator does. Workflow files end in -br.',
    'Return {status: done|blocked, files, notes}. Stop and report instead of guessing if a file outside the write set is needed or the brief is unclear.',
  ].filter((l) => l !== '').join('\n')
}

async function check() {
  if (!take('local checks')) return null
  return agent(
    `Do not edit files. Check these CI files locally: ${files.join(', ')}. Run: actionlint on the workflow files, zizmor on them (both through \`nix shell nixpkgs#actionlint -c actionlint\` and \`nix shell nixpkgs#zizmor -c zizmor\`), ` +
      'and the project linters/formatters the workflow itself will run (read the workflow, run the same commands through `nix develop -c`). ' +
      'Return every command with ok and a bounded excerpt of the failure output. ok is true only when every check passed.',
    { agentType: 'test-runner', phase: 'Check', label: 'local checks', schema: CHECK_SCHEMA },
  )
}

function failedText(res) {
  return res.checks.filter((c) => !c.ok).map((c) => `${c.command}\n${c.output}`).join('\n---\n')
}

const pushCommands = [
  `git add -- ${files.map(shellQuote).join(' ')}`,
  `git commit -m ${shellQuote(`ci: ${task || 'update workflows'}`)}`,
  'git push origin HEAD:ci-test',
]

if (!afterPush) {
  let rounds = 0
  if (!take('ci-engineer')) return { stopped: true, problems: ['agent cap reached'] }
  let work = await agent(engineerBrief(''), { agentType: 'ci-engineer', phase: 'Write', label: 'ci-engineer', schema: WORK_SCHEMA })
  if (!work || work.status !== 'done') {
    const why = work ? work.notes : 'ci-engineer returned nothing'
    log(`stopped: ci-engineer ${work ? 'blocked' : 'failed'}: ${why}`)
    return { stopped: true, problems: [why], work }
  }
  let res = await check()
  while (res && !res.ok && rounds < maxRounds) {
    rounds += 1
    if (!take(`fix round ${rounds}`)) break
    const fixed = await agent(engineerBrief(`Local checks failed (round ${rounds}); fix the cause in your write set:\n${failedText(res)}`), { agentType: 'ci-engineer', phase: 'Fix', label: `ci-engineer fix ${rounds}`, schema: WORK_SCHEMA })
    if (!fixed || fixed.status !== 'done') {
      log(`stopped: ci-engineer fix ${rounds} ${fixed ? 'blocked' : 'returned nothing'}`)
      work = fixed || work
      break
    }
    work = fixed
    res = await check()
  }
  if (!res) {
    log('stopped: local checks returned nothing or were skipped')
    return { ready_to_push: false, rounds, work, problems: ['local checks did not run'] }
  }
  if (!res.ok) {
    log('stopped for the user: local checks still fail')
    return { ready_to_push: false, rounds, work, checks: res.checks, problems: ['local checks fail'], stop_for_user: true }
  }
  return {
    ready_to_push: true,
    rounds,
    work,
    checks: res.checks,
    user_commands: pushCommands,
    next: 'After the push to ci-test, run /br-ci again with after_push: true and the same files and brief',
  }
}

// Second invocation: the user (orchestrator) has pushed ci-test.
const round = Number.isInteger(a.round) && a.round > 0 ? a.round : 1
if (round > maxRounds) {
  log(`stopped for the user: round ${round} is over the limit ${maxRounds}`)
  return { stop_for_user: true, problems: [`${maxRounds} fix rounds are used up`] }
}
if (!take('gh login preflight')) return { stopped: true, problems: ['agent cap reached'] }
const login = await agent(
  'Check the login of the gh CLI with the status command from the cli-gh skill, through `nix shell nixpkgs#gh -c <cmd>`; read-only. ' +
    'Return logged_in and, when not logged in, user_command: the exact one command the user runs as `! nix shell nixpkgs#gh -c <cmd>`.',
  { agentType: 'log-collector', phase: 'Preflight', label: 'login preflight', schema: LOGIN_SCHEMA },
)
if (!login) return { stopped: true, problems: ['login preflight returned nothing'] }
const missing = login.logins.filter((l) => !l.logged_in)
if (missing.length > 0) {
  missing.forEach((l) => log(`stopped: ${l.cli} is not logged in`))
  return { stopped: true, problems: ['login needed'], login_needed: missing.map((l) => ({ cli: l.cli, user_command: l.user_command })) }
}

if (!take('collect failed runs')) return { stopped: true, problems: ['agent cap reached'] }
const got = await agent(
  `Read-only. List runs of the ci-test branch (\`gh run list --branch ci-test\`) and for each failed one take \`gh run view <id> --log-failed\`. ` +
    `Write bounded raw excerpts (no reasoning) to ${dir}/ and return failed_runs, excerpt_paths and a short summary. If no run failed, return empty lists.`,
  { agentType: 'log-collector', phase: 'Collect', label: 'failed runs', schema: COLLECT_SCHEMA },
)
if (!got) return { stopped: true, problems: ['log collector returned nothing'] }
if (got.failed_runs.length === 0) {
  log('no failed runs on ci-test')
  return { green: true, summary: got.summary, rounds: round - 1 }
}

if (!take('analyse')) return { stopped: true, problems: ['agent cap reached'] }
const analysis = await agent(
  `Analyse the failed CI runs. Excerpts: ${got.excerpt_paths.join(', ')}. You may run read-only commands. Files under repair: ${files.join(', ')}. ` +
    'Return cause, evidence (quoted lines with source), fix as a task proposal {agent, files, steps}, confidence, and what else to collect if unsure.',
  { agentType: 'deploy-error-reader', phase: 'Analyse', label: 'failure analysis', schema: ANALYSIS_SCHEMA },
)
if (!analysis) return { stopped: true, problems: ['analyst returned nothing'], excerpt_paths: got.excerpt_paths }

if (!take('ci-engineer fix')) return { stopped: true, problems: ['agent cap reached'], analysis }
const fix = await agent(
  engineerBrief(`The ci-test run failed (round ${round}). Cause: ${analysis.cause}\nProposed steps: ${analysis.fix.steps.join('; ')}\nExcerpts: ${got.excerpt_paths.join(', ')}`),
  { agentType: 'ci-engineer', phase: 'Fix', label: `ci-engineer fix ${round}`, schema: WORK_SCHEMA },
)
if (!fix || fix.status !== 'done') {
  log(`stopped: ci-engineer fix ${fix ? 'blocked' : 'returned nothing'}`)
  return { stopped: true, problems: [fix ? fix.notes : 'ci-engineer returned nothing'], analysis }
}
return {
  ready_to_push: true,
  round,
  next_round: round + 1,
  analysis,
  work: fix,
  excerpt_paths: got.excerpt_paths,
  user_commands: pushCommands,
  next: round >= maxRounds ? 'This was the last round: if ci-test still fails, stop for the user' : 'After the push run /br-ci again with after_push: true and round: ' + (round + 1),
}
