// br-deploy: write deploy artefacts (Dockerfile, compose, nix image, IaC), check them on a local stand, return the exact commands for the user. Never applies or deploys.
export const meta = {
  name: 'br-deploy',
  description: 'Write Dockerfile / compose / nix image / IaC with deploy-engineer, check (compose config, image build, local smoke, tofu plan), then return the plan, the diff and the exact apply/deploy commands for the user; it never applies or deploys',
  whenToUse: 'For a deployment task; args = { target: local|railway|gcp|digitalocean|yandex|cloudflare, files, brief, approved?, id? }',
  phases: ['Preflight', 'Write', 'Check', 'Collect', 'Analyse', 'Fix'],
}

const MAX_AGENTS = 10
const MAX_ROUNDS = 2
const TARGETS = ['local', 'railway', 'gcp', 'digitalocean', 'yandex', 'cloudflare']
const CLI_OF = { railway: 'railway', gcp: 'gcloud', digitalocean: 'doctl', yandex: 'yc', cloudflare: 'wrangler' }
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
    problems: { ...strArr, description: 'docker daemon down, ports or subnets of the compose files already taken, missing tools; empty when none' },
  },
}

const WORK_SCHEMA = {
  type: 'object',
  required: ['status', 'files', 'user_commands', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    files: strArr,
    user_commands: { ...strArr, description: 'the exact apply/deploy commands for the USER to run; never run them' },
    notes: { type: 'string' },
  },
}

const CHECK_SCHEMA = {
  type: 'object',
  required: ['ok', 'checks', 'plan_path', 'diff_summary'],
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
    plan_path: { type: 'string', description: 'file in docs/temp with the tofu plan, or "" if there is no IaC' },
    diff_summary: { type: 'string' },
  },
}

const SMOKE_SCHEMA = {
  type: 'object',
  required: ['ok', 'services', 'logs_path', 'notes'],
  properties: {
    ok: { type: 'boolean' },
    services: { type: 'array', items: { type: 'object', required: ['name', 'healthy'], properties: { name: { type: 'string' }, healthy: { type: 'boolean' } } } },
    logs_path: { type: 'string' },
    notes: { type: 'string' },
  },
}

const COLLECT_SCHEMA = {
  type: 'object',
  required: ['excerpt_paths', 'summary'],
  properties: { excerpt_paths: strArr, summary: { type: 'string' } },
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

function safeId(s) {
  const ok = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
  const out = String(s).split('').map((c) => (ok.includes(c) ? c : '-')).join('')
  return out === '' ? 'run' : out.slice(0, 40)
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
const target = typeof a.target === 'string' ? a.target : ''
const files = Array.isArray(a.files) ? a.files.filter((f) => typeof f === 'string' && f !== '') : []
const brief = typeof a.brief === 'string' ? a.brief : ''
const dir = `docs/temp/br-deploy-${safeId(a.id || target)}`
const stack = `br-deploy-${safeId(a.id || target)}`

const problems = []
if (!TARGETS.includes(target)) problems.push(`args.target must be one of ${TARGETS.join(', ')}`)
if (files.length === 0) problems.push('args.files is missing or empty')
if (brief === '') problems.push('args.brief is missing')
if (problems.length > 0) {
  problems.forEach((p) => log(`stopped: ${p}`))
  return { stopped: true, problems }
}
if (a.approved === true) log('approved is set, but this workflow still applies and deploys nothing: it only returns the commands')

function engineerBrief(extra) {
  return [
    `Target: ${target}`,
    `Write set (only these files): ${files.join(', ')}`,
    `Brief: ${brief}`,
    extra,
    'Rules: do not commit, do not push, never apply, deploy or run tofu apply / railway up / gcloud deploy and the like; those are for the user. ' +
      (target === 'railway' ? 'The dev stand on Railway goes through a PR into develop-br; merge and deploy are the user\'s. ' : '') +
      'Return user_commands: the exact apply/deploy commands for the user (as text).',
    'Return {status: done|blocked, files, user_commands, notes}. Stop and report instead of guessing if a file outside the write set is needed or the brief is unclear.',
  ].filter((l) => l !== '').join('\n')
}

// Stage 0: preflight.
if (!take('preflight')) return { stopped: true, problems: ['agent cap reached'] }
const cli = CLI_OF[target]
const pre = await agent(
  `Preflight, read-only. ${cli ? `Check the login of the ${cli} CLI with the status command from its cli-* skill, through \`nix shell nixpkgs#<pkg> -c <cmd>\`. ` : ''}` +
    'Check that the docker daemon answers (`docker version`) and that the ports and subnets used by these files are free: ' + files.join(', ') + '. ' +
    'For each CLI return logged_in and, when not logged in, user_command: the exact one command the user runs as `! nix shell nixpkgs#<pkg> -c <cmd>`. List every other missing tool or taken port/subnet in problems.',
  { agentType: 'log-collector', phase: 'Preflight', label: 'preflight', schema: LOGIN_SCHEMA },
)
if (!pre) return { stopped: true, problems: ['preflight returned nothing'] }
const missing = pre.logins.filter((l) => !l.logged_in)
if (missing.length > 0 || pre.problems.length > 0) {
  missing.forEach((l) => log(`stopped: ${l.cli} is not logged in`))
  pre.problems.forEach((p) => log(`stopped: ${p}`))
  return { stopped: true, login_needed: missing.map((l) => ({ cli: l.cli, user_command: l.user_command })), problems: pre.problems }
}

// Stage 1: write.
if (!take('deploy-engineer')) return { stopped: true, problems: ['agent cap reached'] }
let work = await agent(engineerBrief(''), { agentType: 'deploy-engineer', phase: 'Write', label: 'deploy-engineer', schema: WORK_SCHEMA })
if (!work || work.status !== 'done') {
  const why = work ? work.notes : 'deploy-engineer returned nothing'
  log(`stopped: deploy-engineer ${work ? 'blocked' : 'failed'}: ${why}`)
  return { stopped: true, problems: [why], work }
}

// Stage 2: checks. Static checks by test-runner, smoke on a local stand by stand-operator.
async function checks() {
  const out = { ok: false, static: null, smoke: null }
  if (!take('static checks')) return out
  out.static = await agent(
    `Do not edit source files. Check these deploy files: ${files.join(', ')}. Run what applies: \`docker compose config --quiet\` for compose files, the image build (docker build or the nix image build), ` +
      `and \`tofu plan\` (never apply) with the plan text written to ${dir}/plan.txt, through \`nix develop -c\` or \`nix shell nixpkgs#<pkg> -c\`. ` +
      'Return every command with ok and a bounded excerpt of the failure output, plan_path ("" without IaC) and diff_summary (`git diff --stat` of these files). ok is true only when every check passed.',
    { agentType: 'test-runner', phase: 'Check', label: 'static checks', schema: CHECK_SCHEMA },
  )
  const hasCompose = files.some((f) => f.includes('compose'))
  if (out.static && out.static.ok && hasCompose) {
    if (take('smoke')) {
      out.smoke = await agent(
        `Bring up the local stand from ${files.filter((f) => f.includes('compose')).join(', ')} with \`docker compose -p ${stack} -f <file> up -d\`, wait for the healthchecks of all services, ` +
          `then take it down again with \`docker compose -p ${stack} down\` (keep the volumes unless the brief says otherwise). Write bounded logs of any failing service to ${dir}/. Run nothing against any cloud.`,
        { agentType: 'stand-operator', phase: 'Check', label: 'smoke stand', schema: SMOKE_SCHEMA },
      )
    }
  }
  out.ok = !!out.static && out.static.ok && (!hasCompose || (!!out.smoke && out.smoke.ok))
  return out
}

function failureText(res) {
  const parts = []
  if (!res.static) parts.push('static checks returned nothing')
  else res.static.checks.filter((c) => !c.ok).forEach((c) => parts.push(`${c.command}\n${c.output}`))
  if (res.smoke && !res.smoke.ok) parts.push(`smoke failed: ${res.smoke.notes}; logs: ${res.smoke.logs_path}`)
  return parts.join('\n---\n')
}

let res = await checks()
let rounds = 0
const analyses = []
while (!res.ok && rounds < MAX_ROUNDS) {
  rounds += 1
  if (!take(`collect round ${rounds}`)) break
  const got = await agent(
    `Read-only. Collect bounded raw excerpts (no reasoning) of the failures of the deploy checks into ${dir}/. Failures:\n${failureText(res)}\nReturn excerpt_paths and a short summary.`,
    { agentType: 'log-collector', phase: 'Collect', label: `collect ${rounds}`, schema: COLLECT_SCHEMA },
  )
  if (!got) { log('stopped: log collector returned nothing'); break }
  if (!take(`analyse round ${rounds}`)) break
  const analysis = await agent(
    `Analyse the failed deploy checks. Excerpts: ${got.excerpt_paths.join(', ')}. You may run read-only commands. Files under repair: ${files.join(', ')}. ` +
      'Return cause, evidence (quoted lines with source), fix as a task proposal {agent, files, steps}, confidence, and what else to collect if unsure.',
    { agentType: 'deploy-error-reader', phase: 'Analyse', label: `analyse ${rounds}`, schema: ANALYSIS_SCHEMA },
  )
  if (!analysis) { log('stopped: analyst returned nothing'); break }
  analyses.push(analysis)
  if (!take(`fix round ${rounds}`)) break
  const fixed = await agent(
    engineerBrief(`Checks failed (round ${rounds}). Cause: ${analysis.cause}\nProposed steps: ${analysis.fix.steps.join('; ')}\nExcerpts: ${got.excerpt_paths.join(', ')}`),
    { agentType: 'deploy-engineer', phase: 'Fix', label: `fix ${rounds}`, schema: WORK_SCHEMA },
  )
  if (!fixed || fixed.status !== 'done') {
    log(`stopped: deploy-engineer fix ${fixed ? 'blocked' : 'returned nothing'}`)
    break
  }
  work = fixed
  res = await checks()
}

// Stage 3: stop and hand over. Nothing is applied here.
if (!res.ok) log('stopped for the user: checks still fail')
return {
  ready_for_user: res.ok,
  stop_for_user: !res.ok,
  target,
  rounds,
  files: work.files,
  plan_path: res.static ? res.static.plan_path : '',
  diff_summary: res.static ? res.static.diff_summary : '',
  checks: res.static ? res.static.checks : [],
  smoke: res.smoke,
  analyses,
  user_commands: work.user_commands,
  notes: work.notes,
  agents_used: used,
}
