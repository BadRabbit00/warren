// br-diagnose: finds the cause of a CI, compose or platform failure. Cheap collectors gather bounded excerpts, one analyst reasons.
export const meta = {
  name: 'br-diagnose',
  description: 'Diagnose a failing CI run, compose stand or cloud deploy: login preflight, log-collectors gather bounded excerpts per source group, one deploy-error-reader returns cause, quoted evidence, a fix as a task proposal and confidence',
  whenToUse: 'When a pipeline, container or platform deploy fails and the cause is unknown; args = { sources: [{ kind, target, since? }], prod?, approved_commands? }',
  phases: ['Preflight', 'Collect', 'Analyse'],
}

const KINDS = ['ci', 'compose', 'railway', 'gcloud', 'doctl', 'yc', 'wrangler', 'docker']
// kind -> [CLI to check, bucket]; the buckets keep the collectors at four at most.
const KIND_INFO = {
  ci: ['gh', 'ci'],
  compose: ['docker', 'local'],
  docker: ['docker', 'local'],
  railway: ['railway', 'edge'],
  wrangler: ['wrangler', 'edge'],
  gcloud: ['gcloud', 'cloud'],
  doctl: ['doctl', 'cloud'],
  yc: ['yc', 'cloud'],
}
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
    problems: { type: 'array', items: { type: 'string' }, description: 'missing tools or a docker daemon that does not answer `docker version`' },
  },
}

const EXCERPTS_SCHEMA = {
  type: 'object',
  required: ['excerpts', 'commands'],
  properties: {
    excerpts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['source', 'command', 'text'],
        properties: { source: { type: 'string' }, command: { type: 'string' }, text: { type: 'string', description: 'raw bounded excerpt, no interpretation' } },
      },
    },
    commands: { type: 'array', items: { type: 'string' }, description: 'every command that was run' },
  },
}

const DIAGNOSIS_SCHEMA = {
  type: 'object',
  required: ['cause', 'evidence', 'fix', 'confidence', 'collect_more'],
  properties: {
    cause: { type: 'string' },
    evidence: {
      type: 'array',
      items: { type: 'object', required: ['source', 'line'], properties: { source: { type: 'string' }, line: { type: 'string', description: 'quoted verbatim' } } },
    },
    fix: {
      type: 'object',
      required: ['agent', 'files', 'steps'],
      properties: { agent: { type: 'string' }, files: strArr, steps: strArr },
    },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    collect_more: { type: 'array', items: { type: 'string' }, description: 'what else to collect if unsure, else []' },
  },
}

function strings(v) {
  return Array.isArray(v) ? v.filter((s) => typeof s === 'string' && s !== '') : []
}

// Targets and times go into prompts as data; reject anything with control characters.
function clean(s) {
  return typeof s === 'string' && s !== '' && !s.split('').some((c) => c < ' ')
}

const input = args && Array.isArray(args.sources) ? args.sources : []
if (input.length === 0) return { stopped: true, problems: ['args.sources is missing or empty'] }

const sources = []
for (const s of input) {
  if (!s || !KINDS.includes(s.kind) || !clean(s.target) || (s.since !== undefined && !clean(s.since))) {
    log(`source skipped: bad entry ${JSON.stringify(s)}`)
    continue
  }
  sources.push({ kind: s.kind, target: s.target, since: s.since || '' })
}
if (sources.length === 0) return { stopped: true, problems: ['no valid source in args.sources'] }

const prod = !!(args && args.prod === true)
const approved = strings(args && args.approved_commands)
if (prod && approved.length === 0) {
  log('prod sources skipped: args.prod is set but approved_commands is empty (the user must approve every prod command)')
  return { stopped: true, problems: ['prod needs approved_commands: list every prod command the user approved'] }
}
const scope = prod
  ? `PRODUCTION targets. You may run only these exact commands, nothing else, and they are read-only: ${approved.join(' | ')}. If you need another command, report it in commands as needed-but-not-run and stop.`
  : 'Non-production targets only. If a target looks like production, do not touch it and say so.'

// Preflight: logins and tools.
const clis = [...new Set(sources.map((s) => KIND_INFO[s.kind][0]))]
const login = await agent(
  `Check the login of each CLI: ${clis.join(', ')}. Use the status commands from the cli-* skills (run the CLI directly; a missing CLI means install_needed with the requirements.md hint); read-only. ` +
    (clis.includes('docker') ? 'For docker also check the daemon answers `docker version`. ' : '') +
    'For each CLI return logged_in and, when not logged in, user_command: the exact one command the user runs as `! <cmd>`. Put missing tools into problems.',
  { agentType: 'log-collector', label: 'login preflight', phase: 'Preflight', schema: LOGIN_SCHEMA },
)
if (!login) return { stopped: true, problems: ['login preflight returned nothing'] }
const missing = login.logins.filter((l) => !l.logged_in)
missing.forEach((l) => log(`stopped: ${l.cli} is not logged in`))
login.problems.forEach((p) => log(`stopped: ${p}`))
if (missing.length > 0 || login.problems.length > 0) {
  return { stopped: true, problems: login.problems.length > 0 ? login.problems : ['login needed'], login_needed: missing.map((l) => ({ cli: l.cli, user_command: l.user_command })) }
}

// Stage 1: collect per bucket.
const buckets = ['ci', 'local', 'edge', 'cloud']
const groups = buckets.map((b) => sources.filter((s) => KIND_INFO[s.kind][1] === b)).filter((g) => g.length > 0)
const collected = await parallel(
  groups.map((g, i) => () =>
    agent(
      `Collect raw, bounded log excerpts (last ~200 lines or the failing step, whichever is smaller) for each source. ${scope}\n` +
        'Use the cli-* skills by running the CLI directly. Do not reason about causes; return the excerpts and every command you ran.\n' +
        g.map((s) => `- ${s.kind}: ${s.target}${s.since ? ` since ${s.since}` : ''}`).join('\n'),
      { agentType: 'log-collector', label: `collect ${g.map((s) => s.kind).join('+')}`, phase: 'Collect', schema: EXCERPTS_SCHEMA },
    )),
)
const excerpts = []
collected.forEach((c, i) => {
  if (!c) return log(`collector for ${groups[i].map((s) => s.kind).join('+')} returned nothing`)
  c.excerpts.forEach((e) => excerpts.push(e))
})
if (excerpts.length === 0) return { stopped: true, problems: ['no collector returned excerpts'] }

// Stage 2: one analyst.
const diagnosis = await agent(
  'Diagnose the failure from these excerpts. Return the cause, evidence as lines quoted verbatim with their source, the fix as a task proposal {agent, files, steps} ' +
    '(agent is one of our coder or engineer agents), confidence, and what else to collect if you are unsure. ' +
    `You may run read-only commands yourself. ${scope}\n\n` +
    excerpts.map((e, i) => `### ${i + 1}. ${e.source} (${e.command})\n${e.text}`).join('\n\n'),
  { agentType: 'deploy-error-reader', label: 'analyse', phase: 'Analyse', schema: DIAGNOSIS_SCHEMA },
)
if (!diagnosis) return { stopped: true, problems: ['analyst returned nothing'], excerpts }

return { diagnosis, sources_collected: excerpts.map((e) => e.source), commands: collected.filter(Boolean).flatMap((c) => c.commands) }
