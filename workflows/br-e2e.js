// br-e2e: derives user flows from the docs, brings a stand up, has test-writers build the e2e harness, contract and journey tests, then one test-runner classifies the failures.
export const meta = {
  name: 'br-e2e',
  description: 'End-to-end testing of a stand: user flows from the docs, stand up, harness, contract and journey tests in parallel, one final run with app/test/stand classification and p50/p95 timings',
  whenToUse: 'When the app has docs and a way to start a stand and you want the whole system exercised; args = { stand: "docker"|"nix", target: "local"|"dev-stand", flows_doc?, new_stand? }. No deploys; the stand stays up.',
  phases: ['Preflight', 'Flows', 'Stand', 'Harness', 'Tests', 'Run'],
}

const MAX_AGENTS = 10
const MAX_WRITERS = 6
const MAX_ENDPOINTS_PER_WRITER = 15
const strArr = { type: 'array', items: { type: 'string' } }

const LOGIN_SCHEMA = {
  type: 'object',
  required: ['logins', 'problems'],
  properties: {
    logins: {
      type: 'array',
      items: {
        type: 'object',
        required: ['cli', 'logged_in', 'user_command'],
        properties: { cli: { type: 'string' }, logged_in: { type: 'boolean' }, user_command: { type: 'string' } },
      },
    },
    problems: { ...strArr, description: 'missing tools, docker daemon not reachable, busy ports or subnets of the compose files' },
  },
}

const FLOWS_SCHEMA = {
  type: 'object',
  required: ['flows_path', 'flows', 'endpoints', 'notes'],
  properties: {
    flows_path: { type: 'string' },
    flows: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'priority', 'steps'],
        properties: {
          id: { type: 'string' }, name: { type: 'string' }, priority: { type: 'string', enum: ['critical', 'high', 'normal'] },
          steps: {
            type: 'array',
            items: {
              type: 'object',
              required: ['action', 'expect', 'db_checks'],
              properties: { action: { type: 'string' }, expect: { type: 'string' }, db_checks: strArr, timing: { type: 'string' } },
            },
          },
        },
      },
    },
    endpoints: {
      type: 'array',
      items: { type: 'object', required: ['method', 'path', 'group'], properties: { method: { type: 'string' }, path: { type: 'string' }, group: { type: 'string' } } },
    },
    notes: { type: 'string' },
  },
}

const STAND_SCHEMA = {
  type: 'object',
  required: ['up', 'files', 'project_name', 'base_url', 'services', 'notes'],
  properties: {
    up: { type: 'boolean' }, files: strArr, project_name: { type: 'string' }, base_url: { type: 'string' },
    services: { type: 'array', items: { type: 'object', required: ['name', 'healthy'], properties: { name: { type: 'string' }, healthy: { type: 'boolean' } } } },
    notes: { type: 'string' },
  },
}

const LOGS_SCHEMA = {
  type: 'object',
  required: ['excerpts_path', 'summary'],
  properties: { excerpts_path: { type: 'string' }, summary: { type: 'string' } },
}

const ERROR_SCHEMA = {
  type: 'object',
  required: ['cause', 'evidence', 'fix', 'confidence'],
  properties: { cause: { type: 'string' }, evidence: strArr, fix: { type: 'string' }, confidence: { type: 'string', enum: ['low', 'medium', 'high'] } },
}

const WRITER_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'tests', 'app_failures', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: strArr,
    tests: strArr,
    app_failures: { type: 'array', items: { type: 'object', required: ['test', 'message'], properties: { test: { type: 'string' }, message: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}

const RUN_SCHEMA = {
  type: 'object',
  required: ['ran', 'passed', 'failed', 'per_test', 'timings', 'report_paths', 'questions', 'summary'],
  properties: {
    ran: { type: 'integer' }, passed: { type: 'integer' }, failed: { type: 'integer' },
    per_test: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'phase', 'outcome', 'classification', 'message', 'file'],
        properties: {
          name: { type: 'string' }, phase: { type: 'string', enum: ['api', 'access', 'journeys'] },
          outcome: { type: 'string', enum: ['pass', 'fail', 'error', 'skip'] },
          classification: { type: 'string', enum: ['app', 'test', 'stand', 'n/a'], description: 'n/a for passing tests' },
          message: { type: 'string' }, file: { type: 'string', description: 'the file the fix belongs in: application source for app, test file for test, "" for stand' },
        },
      },
    },
    timings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['step', 'p50_ms', 'p95_ms', 'budget_ms', 'over_budget'],
        properties: { step: { type: 'string' }, p50_ms: { type: 'number' }, p95_ms: { type: 'number' }, budget_ms: { type: 'number', description: '0 when docs/POLICY.md has no budget' }, over_budget: { type: 'boolean' } },
      },
    },
    report_paths: strArr,
    questions: { ...strArr, description: 'where the expected behaviour is unclear from the docs: questions for /br-research' },
    summary: { type: 'string' },
  },
}

function shellQuote(s) {
  return "'" + String(s).split("'").join("'\\''") + "'"
}

// Base-branch style validation without regex literals: only [A-Za-z0-9._/-], no leading dash or "..".
function safeId(s) {
  const ok = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-'
  return typeof s === 'string' && s !== '' && s.split('').every((c) => ok.includes(c)) && !s.startsWith('-') && !s.includes('..')
}

function chunkBy(list, n) {
  const size = Math.ceil(list.length / n)
  return Array.from({ length: n }, (_, k) => list.slice(k * size, (k + 1) * size)).filter((c) => c.length > 0)
}

// Splits endpoints (kept grouped by their group) into at most n chunks; chunks stay within the per-writer limit when n allows.
function contractChunks(endpoints, n) {
  const sorted = [...endpoints].sort((a, b) => (a.group < b.group ? -1 : a.group > b.group ? 1 : 0))
  const chunks = []
  sorted.forEach((e) => {
    const last = chunks[chunks.length - 1]
    if (last && last.length < MAX_ENDPOINTS_PER_WRITER && chunks.length <= n) last.push(e)
    else chunks.push([e])
  })
  return chunks.length <= n ? chunks : chunkBy(sorted, n)
}

function journeyChunks(flows, n) {
  const chunks = Array.from({ length: n }, () => [])
  flows.forEach((f, k) => chunks[k % n].push(f))
  return chunks.filter((c) => c.length > 0)
}

// Splits the writer slots between contract and journey tests, at least one each when both have work.
function allocate(endpoints, flows, slots) {
  const wantC = endpoints.length === 0 ? 0 : Math.ceil(endpoints.length / MAX_ENDPOINTS_PER_WRITER)
  const wantJ = flows.length === 0 ? 0 : Math.ceil(flows.length / 4)
  if (wantC + wantJ <= slots) return { c: wantC, j: wantJ }
  if (wantC === 0) return { c: 0, j: slots }
  if (wantJ === 0) return { c: slots, j: 0 }
  const c = Math.min(wantC, Math.max(1, Math.round((slots * wantC) / (wantC + wantJ))), slots - 1)
  return { c, j: slots - c }
}

const OUT = typeof args === 'object' && args !== null ? args : {}
const stand = OUT.stand
const target = OUT.target
if (!['docker', 'nix'].includes(stand) || !['local', 'dev-stand'].includes(target)) {
  log('stopped: args.stand must be docker|nix and args.target local|dev-stand')
  return { stopped: true, problems: ['args.stand must be docker|nix and args.target local|dev-stand'] }
}
const newStand = OUT.new_stand === true
const flowsDoc = typeof OUT.flows_doc === 'string' ? OUT.flows_doc : ''
if (flowsDoc !== '' && (flowsDoc.startsWith('-') || flowsDoc.includes('..'))) {
  log('stopped: args.flows_doc is not a plain path')
  return { stopped: true, problems: ['args.flows_doc is not a plain path'] }
}

let used = 0

used += 1
const pre = await agent(
  'Preflight, read-only. Check: ' +
    `the docker daemon (run \`docker version\`), free ports and subnets for the compose files of the stand (${stand === 'nix' ? 'the nix stand target' : 'docker-compose*.yaml'}), nix develop works` +
    (target === 'dev-stand' ? ', and the Railway login (`railway status`, through `nix shell nixpkgs#railway -c railway status`)' : '') +
    '. Also create the directory docs/temp/e2e-<id>/ with <id> = the output of `date +%Y%m%d-%H%M%S` and return its name in problems as "dir: docs/temp/e2e-<id>" as the FIRST entry. ' +
    'For each CLI that is not logged in return user_command: the exact one command the user runs as `! nix shell nixpkgs#<pkg> -c <cmd>`. Any other missing tool or busy port goes into problems.',
  { agentType: 'log-collector', label: 'preflight', phase: 'Preflight', schema: LOGIN_SCHEMA },
)
if (!pre) {
  log('stopped: preflight returned nothing')
  return { stopped: true, problems: ['preflight returned nothing'] }
}
const dirEntry = pre.problems.find((p) => p.startsWith('dir: docs/temp/e2e-'))
const dir = dirEntry ? dirEntry.slice(5).trim() : ''
const missing = pre.logins.filter((l) => !l.logged_in)
const blockers = pre.problems.filter((p) => p !== dirEntry)
if (missing.length > 0 || blockers.length > 0 || !dir.startsWith('docs/temp/e2e-') || !safeId(dir.slice('docs/temp/'.length))) {
  missing.forEach((l) => log(`stopped: ${l.cli} is not logged in`))
  blockers.forEach((p) => log(`stopped: ${p}`))
  if (dirEntry === undefined) log('stopped: preflight did not report the report directory')
  return {
    stopped: true,
    login_needed: missing.map((l) => ({ cli: l.cli, user_command: l.user_command })),
    problems: dirEntry === undefined ? [...blockers, 'preflight did not report the report directory'] : blockers,
  }
}

used += 1
const flows = await agent(
  `Read the skill ~/.claude/skills/user-flows/SKILL.md first. Then read docs/ (the GENERAL processes, API docs / OpenAPI, SPECIFICATION${flowsDoc !== '' ? `, and ${flowsDoc}` : ''}) and the UI routes of the app. ` +
    'Return ALL user flows: business-critical ones first (for example open the app, search a product, pick a merchant, ..., order received), then assemble the remaining interactions into meaningful flows that also probe navigation (the back button returns to the previous page, not home or 404), roles, and errors. ' +
    'Each flow: id, name, priority, steps with action, expect, db_checks (rows to assert after the step) and timing (budget from docs/POLICY.md if any). ' +
    `Write the flows as markdown to ${dir}/flows.md and return that path as flows_path. Also return endpoints [{method, path, group}] from the API docs / OpenAPI. Do not edit anything else.`,
  { agentType: 'researcher', label: 'flows', phase: 'Flows', schema: FLOWS_SCHEMA },
)
if (!flows || flows.flows.length === 0) {
  log('stopped: no user flows were derived')
  return { stopped: true, problems: ['flows researcher returned nothing or no flows'], report_dir: dir }
}

async function standFailure(what, detail) {
  used += 1
  const logs = await agent(
    `The e2e stand failed (${what}). Collect bounded raw excerpts (no reasoning): \`docker compose -p <project> ps\`, \`logs --tail 200\` per failing service, the compose file or nix stand target. Write them to ${dir}/stand-logs.txt and return the path.`,
    { agentType: 'log-collector', label: 'stand logs', phase: 'Stand', schema: LOGS_SCHEMA },
  )
  used += logs ? 1 : 0
  const why = logs
    ? await agent(
      `Analyse the stand failure from ${logs.excerpts_path}. Detail from the operator: ${detail}. You may run read-only commands. Return cause, evidence (quoted lines with source), fix as a short proposal, confidence.`,
      { agentType: 'deploy-error-reader', label: 'stand error', phase: 'Stand', schema: ERROR_SCHEMA },
    )
    : null
  log(`stopped: stand did not come up (${what})`)
  return { stopped: true, problems: [`stand did not come up: ${what}`], stand_error: why, logs_path: logs ? logs.excerpts_path : '', flows_path: flows.flows_path, report_dir: dir }
}

let standInfo = null
if (newStand) {
  used += 1
  const written = await agent(
    `Write the local stand for the e2e run: ${stand === 'nix' ? 'a nix stand target (flake output)' : 'docker-compose.dev.yaml'} with every service the app needs, healthchecks, and no host-port clashes. ` +
      'Write only the stand files. Do not apply anything beyond a local `docker compose config --quiet` check; the stand-operator starts it. Return up false, the files, project_name (a unique -p name), base_url, services (healthy false), notes.',
    { agentType: 'deploy-engineer', label: 'new stand', phase: 'Stand', schema: STAND_SCHEMA },
  )
  if (!written || written.files.length === 0) return standFailure('deploy-engineer wrote no stand', written ? written.notes : 'returned nothing')
}
if (target === 'dev-stand') {
  log('target dev-stand: the stand-operator only checks the Railway dev stand; nothing is deployed')
}
used += 1
standInfo = await agent(
  target === 'dev-stand'
    ? 'Verify the Railway dev stand is reachable (`railway status`, health URL from docs), read-only. Do not deploy. Return up, files [], project_name, base_url, services with healthy, notes.'
    : `Bring the ${stand} stand up with a unique project name (\`docker compose -p <name> up -d --wait\` or the nix stand target) and wait until every service is healthy. Leave it up. Return up, files, project_name, base_url, services with healthy, notes.`,
  { agentType: 'stand-operator', label: 'stand up', phase: 'Stand', schema: STAND_SCHEMA },
)
if (!standInfo || !standInfo.up || standInfo.services.some((s) => !s.healthy)) {
  return standFailure('stand-operator reported not up', standInfo ? standInfo.notes : 'returned nothing')
}
const standLine = `Stand: project ${standInfo.project_name}, base URL ${standInfo.base_url}, services ${standInfo.services.map((s) => s.name).join(', ')}; target ${target}.`

used += 1
const harness = await agent(
  `Read the skill ~/.claude/skills/e2e-testing/SKILL.md first. ${standLine} Flows: ${flows.flows_path}. ` +
    'Write the e2e harness only (base part): API clients, personas with roles, a DB inspector to assert rows written at each step, timing capture (p50/p95), Playwright fixtures using the browsers from nixpkgs. No tests of your own beyond a smoke check that the harness imports and reaches the stand. ' +
    'Return {status: done|blocked, files, tests: [], app_failures: [], notes}.',
  { agentType: 'test-writer', label: 'harness', phase: 'Harness', schema: WRITER_SCHEMA },
)
if (!harness || harness.status !== 'done') {
  log(`stopped: harness ${harness ? 'blocked: ' + harness.notes : 'returned nothing'}`)
  return { stopped: true, problems: ['e2e harness was not written'], harness, flows_path: flows.flows_path, report_dir: dir }
}

// Agents so far are in `used`; one is kept for the final test-runner.
const slots = Math.min(MAX_WRITERS, MAX_AGENTS - used - 1)
const plan = allocate(flows.endpoints, flows.flows, slots)
const contract = plan.c > 0 ? contractChunks(flows.endpoints, plan.c) : []
const journeys = plan.j > 0 ? journeyChunks(flows.flows, plan.j) : []
if (contract.some((c) => c.length > MAX_ENDPOINTS_PER_WRITER)) log(`contract groups exceed ${MAX_ENDPOINTS_PER_WRITER} endpoints: the ${MAX_AGENTS}-agent cap leaves ${slots} writers`)
if (contract.length + journeys.length === 0) log('no endpoints and no flows to write tests for')

const commonRules =
  `${standLine} Harness files: ${harness.files.join(', ')}. Flows: ${flows.flows_path}. Write only your own test files next to the harness; do not edit the harness or other writers' files. ` +
  'Run your tests against the stand. Fix errors in the tests themselves (collection, fixtures, selectors, wrong assumptions). A failure caused by the application stays: do not weaken the test, and list it in app_failures {test, message}. ' +
  'Return {status: done|blocked, files, tests (bare names), app_failures, notes}.'

const jobs = [
  ...contract.map((eps, k) => ({
    label: `contract ${k + 1}`,
    prompt:
      'Contract tests per endpoint: exact status, response schema, data types, error codes, role matrix. Endpoints:\n' +
      eps.map((e) => `- ${e.method} ${e.path} (${e.group})`).join('\n') + '\n' + commonRules,
  })),
  ...journeys.map((fl, k) => ({
    label: `journeys ${k + 1}`,
    prompt:
      'Journey tests per flow. For each step assert the response, the DB rows (db_checks), the page render, and record timing; report p50/p95 against the budgets in docs/POLICY.md, never fail on them. Flows:\n' +
      fl.map((f) => `- ${f.id} ${f.name} [${f.priority}]: ${f.steps.map((s) => `${s.action} => ${s.expect}${s.db_checks.length ? ` (db: ${s.db_checks.join('; ')})` : ''}`).join(' | ')}`).join('\n') + '\n' + commonRules,
  })),
]
used += jobs.length
const written = await parallel(
  jobs.map((j) => () => agent('Read the skill ~/.claude/skills/e2e-testing/SKILL.md first. ' + j.prompt, { agentType: 'test-writer', label: j.label, phase: 'Tests', schema: WRITER_SCHEMA })),
)
written.forEach((w, k) => {
  if (!w) log(`${jobs[k].label} returned nothing`)
  else if (w.status !== 'done') log(`${jobs[k].label} blocked: ${w.notes}`)
})
const okWriters = written.filter((w) => w && w.status === 'done')
if (okWriters.length === 0) {
  log('stopped: no test writer finished')
  return { stopped: true, problems: ['no test writer finished'], report_dir: dir, flows_path: flows.flows_path }
}

const testFiles = [...harness.files, ...okWriters.flatMap((w) => w.files)]
used += 1
const run = await agent(
  `${standLine} Do not edit files. Run ALL e2e phases in order: api (contract), access (role matrix), journeys, with the project's commands through \`nix develop -c\`. Test files: ${testFiles.map(shellQuote).join(' ')}. ` +
    'Return every test with pass/fail/error/skip and, for a non-pass, a classification: app (the application is wrong), test (the test is wrong: collection, fixture, selector, bad assumption), stand (the stand or environment broke) and the file the fix belongs in (application source for app). ' +
    `Return a timings table of p50 and p95 per step against the budgets in docs/POLICY.md (over_budget is reported, not a failure). Write the full reports to ${dir}/ and return their paths in report_paths. Put in questions every place where the expected behaviour is unclear from the docs.`,
  { agentType: 'test-runner', label: 'final run', phase: 'Run', schema: RUN_SCHEMA },
)
if (!run) {
  log('stopped: final run returned nothing')
  return { stopped: true, problems: ['final test-runner returned nothing'], report_dir: dir, flows_path: flows.flows_path }
}

// fix_items in the /br-wave manifest-item shape; the agent follows the file extension, the task is filled by the orchestrator.
const byExt = { '.py': 'python-coder', '.go': 'go-coder', '.ts': 'ts-coder', '.tsx': 'ts-coder', '.js': 'ts-coder', '.jsx': 'ts-coder', '.rs': 'rust-coder' }
function extOf(f) {
  const base = f.split('/').pop()
  const i = base.lastIndexOf('.')
  return i < 0 ? '' : base.slice(i)
}
const appFails = run.per_test.filter((t) => (t.outcome === 'fail' || t.outcome === 'error') && t.classification === 'app')
const fixItems = appFails.map((t, k) => ({
  id: `e2e-fix-${k + 1}`,
  task: '',
  step: 'fix-code',
  agent: byExt[extOf(t.file)] || 'coder',
  files: t.file === '' ? [] : [t.file],
  after: [],
  brief: `e2e ${t.phase} test ${t.name} fails because of the application: ${t.message}`,
}))
fixItems.filter((i) => i.files.length === 0).forEach((i) => log(`${i.id}: the runner named no file for the app failure`))

const others = run.per_test.filter((t) => (t.outcome === 'fail' || t.outcome === 'error') && t.classification !== 'app')
return {
  stand: { project: standInfo.project_name, base_url: standInfo.base_url, left_up: true },
  report_dir: dir,
  flows_path: flows.flows_path,
  flows: flows.flows.length,
  endpoints: flows.endpoints.length,
  writers: written.map((w, k) => ({ label: jobs[k].label, status: w ? w.status : 'failed', files: w ? w.files : [], app_failures: w ? w.app_failures : [] })),
  run: { ran: run.ran, passed: run.passed, failed: run.failed, report_paths: run.report_paths, summary: run.summary },
  timings: run.timings,
  non_app_failures: others,
  fix_items: fixItems,
  research_questions: run.questions,
  agents_used: used,
}
