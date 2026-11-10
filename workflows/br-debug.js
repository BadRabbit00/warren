// br-debug: reproduces a reported bug and finds its root cause. Nobody fixes code: the result is a report and the failing test to write.
export const meta = {
  name: 'br-debug',
  description: 'Reproduce a reported bug in a temp dir, run the repro N times, find the root cause with file:line evidence and describe the failing test to write; no code is fixed',
  whenToUse: 'When a bug is reported and its cause is unknown; args = { report, id?, runs?, context? }',
  phases: ['Reproduce', 'Run', 'Root cause'],
}

const strArr = { type: 'array', items: { type: 'string' } }

const REPRO_SCHEMA = {
  type: 'object',
  required: ['result', 'dir', 'command', 'script', 'environment', 'expected', 'actual', 'runs_suggested', 'notes'],
  properties: {
    result: { type: 'string', enum: ['reproduced', 'could_not_reproduce'] },
    dir: { type: 'string', description: '/tmp/repro-<id>/' },
    command: { type: 'string', description: 'exact line, exit codes: 0 bug absent, 1 present, 125 cannot test' },
    script: { type: 'string', description: 'path of repro.sh' },
    environment: { type: 'string', description: 'commit, versions, seed, config without secrets' },
    expected: { type: 'string' },
    actual: { type: 'string', description: 'exact error text' },
    runs_suggested: { type: 'integer', description: '5 for a stable-looking bug, 20 when the report says it happens sometimes' },
    notes: { type: 'string', description: 'what was tried if not reproduced, missing information' },
  },
}

const RUNS_SCHEMA = {
  type: 'object',
  required: ['runs', 'failed', 'verdict', 'exit_codes', 'same_error', 'excerpts'],
  properties: {
    runs: { type: 'integer' },
    failed: { type: 'integer', description: 'runs that exited 1 (bug present)' },
    verdict: { type: 'string', enum: ['stable', 'flaky', 'not reproduced'] },
    rate: { type: 'string', description: 'k/N' },
    exit_codes: { type: 'array', items: { type: 'integer' }, description: 'one per run, in order' },
    same_error: { type: 'boolean', description: 'error text identical in all failed runs' },
    differences: { type: 'string' },
    excerpts: { type: 'string', description: '10-20 log lines around the first wrong value, secrets masked' },
    files: { type: 'string', description: '/tmp/repro-<id>/runs/' },
  },
}

const ANALYSIS_SCHEMA = {
  type: 'object',
  required: ['root_cause', 'chain', 'evidence', 'why_tests_missed', 'test', 'confidence'],
  properties: {
    root_cause: { type: 'string', description: 'one sentence' },
    chain: {
      type: 'array',
      items: { type: 'object', required: ['at', 'what'], properties: { at: { type: 'string', description: 'file:line' }, what: { type: 'string', description: 'what happens, observed value' } } },
    },
    evidence: strArr,
    why_tests_missed: { type: 'string', description: 'gap, with file:line of the nearest tests' },
    test: { type: 'string', description: 'failing test to write: layer, input, expected, why it fails now' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    confidence_note: { type: 'string', description: 'what is proven, what is hypothesis' },
    notes: { type: 'string', description: 'other bugs seen, not fixed; information still needed' },
  },
}


// Deterministic short slug from the report text.
function slugOf(text) {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) % 1679616
  return 'bug' + h.toString(36)
}

const report = args && typeof args.report === 'string' ? args.report.trim() : ''
if (report === '') return { stopped: true, problems: ['args.report is missing or empty'] }
if (args.id !== undefined && !(typeof args.id === 'string' && new RegExp('^[a-z0-9][a-z0-9-]{0,39}$').test(args.id))) {
  return { stopped: true, problems: ['args.id must match [a-z0-9][a-z0-9-]{0,39}'] }
}
if (args.runs !== undefined && !(Number.isInteger(args.runs) && args.runs >= 1 && args.runs <= 100)) {
  return { stopped: true, problems: ['args.runs must be an integer from 1 to 100'] }
}
if (args.context !== undefined && typeof args.context !== 'string') return { stopped: true, problems: ['args.context must be a string'] }
const context = args.context ? args.context.trim() : ''
const id = args.id || slugOf(report)
const dir = `/tmp/repro-${id}/`

const bounds =
  `Boundaries: write only inside ${dir}; do not edit project files, do not deploy, do not touch production, do not read or print secrets (mask them in output). Nobody fixes the bug in this workflow.`

// Step 1: reproduce.
const repro = await agent(
  `Turn this bug report into a reproduction package in ${dir} (README.md, repro.sh, input/) following the debugging skill. ` +
    'repro.sh exits 0 when the bug is absent, 1 when present, 125 when it cannot be tested. ' +
    'State the exact command, the environment, expected vs actual (exact error text), and in runs_suggested how many runs the runner should do: 5 for a stable-looking bug, 20 when the report says it happens sometimes. ' +
    'If you cannot reproduce it, return result could_not_reproduce and say in notes what you tried and what information is missing.\n' +
    `${bounds}\n\n` +
    (context ? `Suspected files/areas (a hint, not a fact):\n${context}\n\n` : '') +
    `Bug report:\n${report}`,
  { agentType: 'bug-reproducer', label: 'reproduce', phase: 'Reproduce', schema: REPRO_SCHEMA },
)
if (!repro) return { stopped: true, problems: ['bug-reproducer returned nothing'], id }
if (repro.result !== 'reproduced') return { id, status: 'could_not_reproduce', repro, runs: null, analysis: null, next: 'ask the user for the missing information in repro.notes, then run again' }

const n = args.runs || (Number.isInteger(repro.runs_suggested) && repro.runs_suggested >= 1 && repro.runs_suggested <= 100 ? repro.runs_suggested : 5)
const pkg =
  `Package: ${repro.dir || dir}\nScript: ${repro.script}\nCommand: ${repro.command}\nEnvironment: ${repro.environment}\nExpected: ${repro.expected}\nActual: ${repro.actual}`

// Step 2: run N times.
const runs = await agent(
  `Run the reproduction ${n} times and report per-run exit codes (0 bug absent, 1 present, 125 cannot test), the failure rate, whether the error text is identical in all failed runs, and 10-20 log lines around the first wrong value (LOG_LEVEL=DEBUG, secrets masked). Do not analyse the cause.\n` +
    `${bounds}\n\n${pkg}`,
  { agentType: 'repro-runner', label: `run x${n}`, phase: 'Run', schema: RUNS_SCHEMA },
)
if (!runs) return { stopped: true, problems: ['repro-runner returned nothing'], id, repro }
if (runs.failed === 0 || runs.verdict === 'not reproduced') {
  return { id, status: 'not_reproduced_by_runner', repro, runs, analysis: null, next: 'the reproducer saw the bug but 0 runs did; revisit the environment or seed in repro.environment, or ask the user' }
}

// Step 3: root cause.
const analysis = await agent(
  'Find the root cause of the bug from this reproduction and run report. Return the root cause in one sentence, the causal chain with file:line and observed values, evidence (commands run, bisect result if used), why the existing tests missed it (with file:line of the nearest tests), the failing test to write (layer, input, expected, why it fails now), and confidence with what is proven vs hypothesis. Do not fix anything.\n' +
    `${bounds} Read the project freely; clones and worktrees for bisect go under ${dir} or /tmp.\n\n` +
    (context ? `Suspected files/areas (a hint, not a fact):\n${context}\n\n` : '') +
    `Bug report:\n${report}\n\n${pkg}\n\nRunner report: ${JSON.stringify(runs)}`,
  { agentType: 'root-cause-analyst', label: 'root cause', phase: 'Root cause', schema: ANALYSIS_SCHEMA },
)
if (!analysis) return { stopped: true, problems: ['root-cause-analyst returned nothing'], id, repro, runs }

return {
  id,
  status: 'root_cause',
  repro,
  runs,
  analysis,
  next: 'test-writer: write the failing test described in analysis.test, then the normal red → green',
}
