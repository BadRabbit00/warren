// br-review: checkpoint review. Deep pass on risky areas, broad pass over the whole diff,
// logging pass against skill logging, db review of accumulated DB work, migrations-only "must not take prod down" review.
export const meta = {
  name: 'br-review',
  description: 'Checkpoint review: deep pass (code, security, language-reviewer, nix-reviewer) on risky paths, broad pass for small bugs, logging pass (skill logging), db-reviewer, migrations-only db-reviewer; refuters only for security must-fix; returns fix items for the next wave',
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
  required: ['tasks', 'paths', 'risky', 'risky_files', 'db', 'migrations', 'problems'],
  properties: {
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'acceptance', 'writes', 'tests', 'skills'],
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          acceptance: { type: 'array', items: { type: 'string' } },
          writes: { type: 'array', items: { type: 'string' }, description: 'Writes paths of this task' },
          tests: { type: 'array', items: { type: 'string' }, description: 'Tests paths of this task' },
          skills: { type: 'array', items: { type: 'string' }, description: 'Skills line of this task (skill names)' },
        },
      },
    },
    paths: { type: 'array', items: { type: 'string' }, description: 'Writes and Tests paths of the covered tasks' },
    risky: { type: 'array', items: { type: 'string' }, description: 'risky areas listed in the checkpoint (paths)' },
    risky_files: { type: 'array', items: { type: 'string' }, description: 'files found under risky entries that are directories (real paths, one per file)' },
    db: { type: 'boolean', description: 'checkpoint says DB work accumulated' },
    migrations: { type: 'array', items: { type: 'string' }, description: 'migration paths listed in the checkpoint' },
    problems: { type: 'array', items: { type: 'string' }, description: 'checkpoint or requested task ids missing' },
  },
}

// extension -> language label for language-reviewer; nix files go to nix-reviewer.
const LANGUAGE_BY_EXTENSION = { py: 'py', go: 'go', rs: 'rs', ts: 'ts/tsx/js/jsx', tsx: 'ts/tsx/js/jsx', js: 'ts/tsx/js/jsx', jsx: 'ts/tsx/js/jsx', dart: 'dart' }

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

function extensionOf(file) {
  const ext = file.slice(file.lastIndexOf('.') + 1)
  return file.includes('.') && ext.split('').every((c) => c >= 'a' && c <= 'z') ? ext : ''
}

function languagesOf(paths) {
  const names = []
  for (const file of paths) {
    const language = LANGUAGE_BY_EXTENSION[extensionOf(file)]
    if (language && !names.includes(language)) names.push(language)
  }
  return names
}

function hasNix(paths) {
  return paths.some((file) => extensionOf(file) === 'nix')
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
    return { tasks: [], paths: [], risky, risky_files: [], db: args.db, migrations, problems: [] }
  }
  const cp = await agent(
    `Read .plan/PLAN.md only. Find the heading "## Checkpoint ${args && args.checkpoint}". Return: the tasks it covers` +
      (ids.length > 0 ? ` (restrict to ${ids.join(', ')})` : '') +
      ' with id, name and acceptance criteria; the union of their Writes and Tests paths, and per task its own Writes and Tests paths and its Skills (skill names); the risky areas; for every risky entry that is a directory, the real files under it (list them with ls or git ls-files, risky_files); whether DB work accumulated (db); the migration paths. ' +
      'Copy verbatim; do not invent anything. If the checkpoint is missing, say so in problems.',
    { agentType: 'researcher', label: 'checkpoint', phase: 'Plan', schema: CHECKPOINT_SCHEMA },
  )
  if (!cp) return { problems: ['checkpoint reader returned nothing'] }
  return {
    ...cp,
    risky: risky.length > 0 ? risky : cp.risky,
    risky_files: strings(cp.risky_files),
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
          (s.languages ? `Languages in these paths: ${s.languages.join(', ')}.${s.skills.length > 0 ? ` Task skills (read ${s.skills.map((k) => `~/.claude/skills/${k}/SKILL.md`).join(', ')} before reviewing).` : ' Task skills: none given.'}\n` : '') +
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

function covers(entry, file) {
  const dir = entry.endsWith('/') ? entry : entry + '/'
  return file === entry || file.startsWith(dir)
}

// Owning task and step per file: test files go to fix-tests, everything else to fix-code (fix-log for logging findings).
function ownerOf(tasks, file, codeStep) {
  const test = tasks.find((t) => strings(t.tests).some((e) => covers(e, file)))
  if (test) return { task: test.id, step: 'fix-tests' }
  const code = tasks.find((t) => strings(t.writes).some((e) => covers(e, file)))
  return { task: code ? code.id : '', step: codeStep }
}

// One fix item per file, so parts of the next wave never share files. A file with only logging findings gets fix-log;
// any other finding on a file makes it fix-code (a logging finding on a test file never becomes a fix item).
function fixItems(tasks, sections) {
  const byFile = {}
  const onlyLogging = {}
  for (const [section, list] of Object.entries(sections)) {
    list.forEach((f) => {
      if (section === 'logging' && ownerOf(tasks, f.file, 'fix-log').step === 'fix-tests') return
      byFile[f.file] = byFile[f.file] || []
      byFile[f.file].push(`[${section}] ${f.title} (line ${f.line}): ${f.fix}`)
      onlyLogging[f.file] = (onlyLogging[f.file] === undefined || onlyLogging[f.file]) && section === 'logging'
    })
  }
  return Object.keys(byFile).map((file, i) => ({
    id: `F${i + 1}`,
    ...ownerOf(tasks, file, onlyLogging[file] ? 'fix-log' : 'fix-code'),
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

const allSkills = [...new Set(cp.tasks.flatMap((t) => strings(t.skills)))]
// Skills of the tasks whose writes or tests cover a path of the chunk; all checkpoint skills when no task matches.
function skillsFor(files) {
  const hit = cp.tasks.filter((t) => [...strings(t.writes), ...strings(t.tests)].some((e) => files.some((f) => covers(e, f) || covers(f, e))))
  return hit.length > 0 ? [...new Set(hit.flatMap((t) => strings(t.skills)))] : allSkills
}
const specs = []
const riskyChunks = chunks(cp.risky, MAX_PER_REVIEWER)
if (riskyChunks.length === 0) log('deep pass skipped: no risky paths in the checkpoint')
riskyChunks.forEach((paths, i) => {
  const part = riskyChunks.length > 1 ? ` part ${i + 1}/${riskyChunks.length}` : ''
  const real = paths.concat(cp.risky_files.filter((f) => paths.some((p) => covers(p, f))))
  const languages = languagesOf(real)
  const deep = ['code-reviewer', 'security-reviewer', ...(languages.length > 0 ? ['language-reviewer'] : []), ...(hasNix(real) ? ['nix-reviewer'] : [])]
  if (deep.length === 2) log(`deep${part}: no language reviewer for these paths`)
  deep.forEach((name) =>
    specs.push({
      pass: 'deep',
      agentType: name,
      ...(name === 'language-reviewer' ? { languages, skills: skillsFor(real) } : {}),
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
specs.push({
  pass: 'logging',
  agentType: 'code-reviewer',
  paths: cp.paths,
  label: 'logging code-reviewer',
  focus: 'logging pass: read ~/.claude/skills/logging/SKILL.md and the reference for each file\'s language under ~/.claude/skills/logging/references/, ' +
    'then check levels, canonical fields from the logger config, masking of secrets and personal data, boundary/external-call/entity-change logging, ' +
    'errors logged once, panic hook, and that logging changes no behaviour. Skip test files',
  severity: 'must_fix only for real defects with evidence.',
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
const sections = { deep: [], broad: [], logging: [], db: [], migrations: [] }
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
  logging: sections.logging,
  db: sections.db,
  migrations: sections.migrations,
  refuted: dropped,
  unverified,
  fix_items: fixItems(cp.tasks, {
    deep: mustFix(sections.deep),
    broad: mustFix(sections.broad),
    logging: mustFix(sections.logging),
    db: mustFix(sections.db),
    migrations: mustFix(sections.migrations),
  }),
}
