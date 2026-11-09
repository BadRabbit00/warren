// br-review: checkpoint review. Deep pass on risky areas, broad pass over the whole diff,
// db review of accumulated DB work, migrations-only "must not take prod down" review.
export const meta = {
  name: 'br-review',
  description: 'Checkpoint review: deep pass (code, security, language reviewers) on risky paths, broad pass for small bugs, db-reviewer, migrations-only db-reviewer; refuters only for security must-fix; returns fix items for the next wave',
  whenToUse: 'At a plan Checkpoint, in the background while coding continues; args = { checkpoint, base?, tasks?, risky?, db?, migrations? }',
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

const CHECKPOINT_SCHEMA = {
  type: 'object',
  required: ['tasks', 'paths', 'risky', 'db', 'migrations', 'problems'],
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'acceptance'],
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          acceptance: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    paths: { type: 'array', items: { type: 'string' }, description: 'Writes and Tests paths of the covered tasks' },
    risky: { type: 'array', items: { type: 'string' }, description: 'risky areas listed in the checkpoint (paths)' },
    db: { type: 'boolean', description: 'checkpoint says DB work accumulated' },
    migrations: { type: 'array', items: { type: 'string' }, description: 'migration paths listed in the checkpoint' },
    problems: { type: 'array', items: { type: 'string' }, description: 'checkpoint or requested task ids missing' },
  },
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

const MIGRATIONS_BRIEF =
  'Nothing may take production down: locks and lock timeouts, long ALTERs on big tables, NOT NULL without default on big tables, ' +
  'batched backfills, expand-contract for renames, indexes CONCURRENTLY, reversibility, data loss.'

const MAX_PER_REVIEWER = 15

// Plan-derived paths are shell-quoted before they go into a command.
function shellQuote(s) {
  return "'" + String(s).split("'").join("'\\''") + "'"
}

function strings(v) {
  return Array.isArray(v) ? v.filter((s) => typeof s === 'string' && s !== '') : []
}

function diffCommand(base, paths) {
  const scope = paths.length > 0 ? ` -- ${paths.map(shellQuote).join(' ')}` : ''
  return `git diff $(git merge-base ${shellQuote(base)} HEAD)...HEAD${scope}`
}

function languageReviewers(paths) {
  const names = []
  for (const file of paths) {
    const ext = file.slice(file.lastIndexOf('.') + 1)
    const reviewer = file.includes('.') && ext.split('').every((c) => c >= 'a' && c <= 'z') ? BY_EXTENSION[ext] : undefined
    if (reviewer && !names.includes(reviewer)) names.push(reviewer)
  }
  return names
}

function chunks(list, size) {
  const out = []
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size))
  return out
}

// Stage 0: read the checkpoint in the plan; skipped when args already carry everything.
async function readCheckpoint() {
  const risky = strings(args && args.risky)
  const migrations = strings(args && args.migrations)
  const ids = strings(args && args.tasks)
  if (args && Array.isArray(args.risky) && typeof args.db === 'boolean') {
    log('plan read skipped: args carry risky and db')
    return { tasks: [], paths: [], risky, db: args.db, migrations, problems: [] }
  }
  const cp = await agent(
    `Read .plan/PLAN.md only. Find the heading "## Checkpoint ${args && args.checkpoint}". Return: the tasks it covers` +
      (ids.length > 0 ? ` (restrict to ${ids.join(', ')})` : '') +
      ' with id, name and acceptance criteria; the union of their Writes and Tests paths; the risky areas; whether DB work accumulated (db); the migration paths. ' +
      'Copy verbatim; do not invent anything. If the checkpoint is missing, say so in problems.',
    { agentType: 'researcher', label: 'checkpoint', phase: 'Plan', schema: CHECKPOINT_SCHEMA },
  )
  if (!cp) return { problems: ['checkpoint reader returned nothing'] }
  return {
    ...cp,
    risky: risky.length > 0 ? risky : cp.risky,
    migrations: migrations.length > 0 ? migrations : cp.migrations,
    db: args && typeof args.db === 'boolean' ? args.db : cp.db,
  }
}

function review(base, cp, specs) {
  const acceptance = cp.tasks.map((t) => `${t.id} ${t.name}:\n` + t.acceptance.map((a) => `- ${a}`).join('\n')).join('\n')
  const context = acceptance ? `\nCovered tasks and acceptance criteria:\n${acceptance}` : ''
  return parallel(
    specs.map((s) => () =>
      agent(
        `Checkpoint ${args.checkpoint}: review as ${s.agentType}, ${s.focus}. Read-only: do not edit files, do not commit.\n` +
          `Diff: ${diffCommand(base, s.paths)}${context}\n` +
          'Return findings with severity must_fix, suboptimal or nit, each with file, line, evidence and fix. ' +
          `${s.severity} Report only what you saw in the code.`,
        { agentType: s.agentType, phase: 'Review', label: s.label, schema: FINDINGS_SCHEMA },
      )),
  )
}

async function refute(f) {
  const verdicts = await parallel(
    [1, 2, 3].map((n) => () =>
      agent(
        'Try to refute this security finding. Read-only; read the code. ' +
          'Set refuted=false unless you can reproduce the problem or point to the exact line that disproves the finding.\n' +
          `Finding (${f.reviewer}): ${f.title}\n${f.file}:${f.line}\nEvidence: ${f.evidence}\nFix: ${f.fix}`,
        { agentType: 'code-reviewer', phase: 'Verify', label: `refute ${n}/3 ${f.file}`, schema: VERDICT_SCHEMA },
      )),
  )
  const got = verdicts.filter(Boolean)
  const refutedN = got.filter((v) => v.refuted).length
  const upheld = got.length - refutedN
  const verdict = got.length < 2 ? 'unverified' : refutedN >= 2 ? 'refuted' : upheld >= 2 ? 'survives' : 'unverified'
  log(`security "${f.title}" ${verdict}`)
  return { ...f, verdict, verdicts: got }
}

// One fix item per file, so parts of the next wave never share files.
function fixItems(sections) {
  const byFile = {}
  for (const [section, list] of Object.entries(sections)) {
    list.forEach((f) => {
      byFile[f.file] = byFile[f.file] || []
      byFile[f.file].push(`[${section}] ${f.title} (line ${f.line}): ${f.fix}`)
    })
  }
  return Object.keys(byFile).map((file, i) => ({
    id: `F${i + 1}`,
    task: '',
    step: 'fix-code',
    files: [file],
    brief: byFile[file].join('\n'),
    after: [],
  }))
}

const BASE = (args && typeof args.base === 'string' && args.base) || 'develop'
const BASE_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/-'
if (BASE.startsWith('-') || BASE.split('').some((c) => !BASE_CHARS.includes(c))) {
  return { stopped: true, problems: ['bad args.base'] }
}
if (!args || typeof args.checkpoint !== 'string' || args.checkpoint === '') {
  return { stopped: true, problems: ['args.checkpoint is required'] }
}

const cp = await readCheckpoint()
if (cp.problems.length > 0) {
  cp.problems.forEach((p) => log(`stopped: ${p}`))
  return { stopped: true, problems: cp.problems }
}

const specs = []
const riskyChunks = chunks(cp.risky, MAX_PER_REVIEWER)
if (riskyChunks.length === 0) log('deep pass skipped: no risky paths in the checkpoint')
riskyChunks.forEach((paths, i) => {
  const part = riskyChunks.length > 1 ? ` part ${i + 1}/${riskyChunks.length}` : ''
  const deep = ['code-reviewer', 'security-reviewer', ...languageReviewers(paths)]
  if (deep.length === 2) log(`deep${part}: no language reviewer for these paths`)
  deep.forEach((name) =>
    specs.push({
      pass: 'deep',
      agentType: name,
      paths,
      label: `deep${part} ${name}`,
      focus: 'deep pass on risky areas: contracts, data, money, security, correctness',
      severity: 'must_fix only for real defects with evidence.',
    }))
})
specs.push({
  pass: 'broad',
  agentType: 'code-reviewer',
  paths: cp.paths,
  label: 'broad code-reviewer',
  focus: 'broad pass over the whole checkpoint diff for small bugs',
  severity: 'Severity is mostly suboptimal or nit; must_fix only for real bugs.',
})
if (cp.db) {
  specs.push({
    pass: 'db',
    agentType: 'db-reviewer',
    paths: cp.paths,
    label: 'db db-reviewer',
    focus: 'accumulated DB work: models, queries, repositories',
    severity: 'must_fix only for real defects with evidence.',
  })
} else log('db review skipped: db is not set for this checkpoint')
if (cp.migrations.length > 0) {
  specs.push({
    pass: 'migrations',
    agentType: 'db-reviewer',
    paths: cp.migrations,
    label: 'migrations db-reviewer',
    focus: `migrations only. ${MIGRATIONS_BRIEF}`,
    severity: 'must_fix for anything that can take production down or lose data.',
  })
} else log('migrations review skipped: no migration paths')

const outcomes = await review(BASE, cp, specs)
const sections = { deep: [], broad: [], db: [], migrations: [] }
outcomes.forEach((o, i) => {
  if (!o) return log(`${specs[i].label} returned nothing`)
  o.findings.forEach((f) => sections[specs[i].pass].push({ ...f, reviewer: specs[i].agentType }))
})

const security = sections.deep.filter((f) => f.reviewer === 'security-reviewer' && f.severity === 'must_fix')
const checked = await parallel(security.map((f) => () => refute(f)))
const dropped = checked.filter((f) => f.verdict === 'refuted')
const unverified = checked.filter((f) => f.verdict === 'unverified')
sections.deep = sections.deep.filter((f) => !dropped.some((d) => d.file === f.file && d.line === f.line && d.title === f.title))

const mustFix = (list) => list.filter((f) => f.severity === 'must_fix')
return {
  checkpoint: args.checkpoint,
  deep: sections.deep,
  broad: sections.broad,
  db: sections.db,
  migrations: sections.migrations,
  refuted: dropped,
  unverified,
  fix_items: fixItems({
    deep: mustFix(sections.deep),
    broad: mustFix(sections.broad),
    db: mustFix(sections.db),
    migrations: mustFix(sections.migrations),
  }),
}
