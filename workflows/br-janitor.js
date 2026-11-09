// br-janitor: survey the project for garbage, or delete exactly the entries the user approved, then survey again.
export const meta = {
  name: 'br-janitor',
  description: 'Survey the project for garbage (finished stands, result symlinks, docs/temp leftovers, stale plan lines, untracked junk, outdated docs), or delete only the exact approved entries and confirm with a second survey',
  whenToUse: 'After a stand or task is finished; args = { mode: "survey" } to get the list, then { mode: "delete", approved: [exact entries the user said «да» to] }',
  phases: ['Survey', 'Delete', 'Confirm'],
}

const SURVEY_SCHEMA = {
  type: 'object',
  required: ['status', 'items', 'plan_lines', 'stale_docs', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'kind', 'reason', 'size', 'age', 'tracked', 'proposed'],
        properties: {
          name: { type: 'string', description: 'path, or container / volume / network name, exactly as it would be deleted' },
          kind: { type: 'string', enum: ['file', 'container', 'volume', 'network', 'other'] },
          reason: { type: 'string' },
          size: { type: 'string' },
          age: { type: 'string' },
          tracked: { type: 'boolean' },
          proposed: { type: 'string', enum: ['delete', 'report-only'] },
        },
      },
    },
    plan_lines: { type: 'array', items: { type: 'object', required: ['line', 'reason'], properties: { line: { type: 'string' }, reason: { type: 'string' } } } },
    stale_docs: { type: 'array', items: { type: 'object', required: ['doc', 'mismatch'], properties: { doc: { type: 'string' }, mismatch: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}

const DELETE_SCHEMA = {
  type: 'object',
  required: ['status', 'deleted', 'left', 'notes'],
  properties: {
    status: { type: 'string', enum: ['done', 'blocked'] },
    deleted: { type: 'array', items: { type: 'object', required: ['name', 'exit_code'], properties: { name: { type: 'string' }, exit_code: { type: 'integer' } } } },
    left: { type: 'array', items: { type: 'object', required: ['name', 'reason'], properties: { name: { type: 'string' }, reason: { type: 'string' } } } },
    notes: { type: 'string' },
  },
}

const mode = args && typeof args.mode === 'string' ? args.mode : 'survey'
const approved = args && Array.isArray(args.approved) ? args.approved.filter((a) => typeof a === 'string' && a.trim() !== '') : []

const SURVEY_BRIEF =
  'Mode: survey. Change nothing. Find: dev containers and volumes of finished stands (by compose project name, `docker compose -p <project>`), networks of finished stands,result and result-* symlinks, ' +
  'leftovers in docs/temp/, untracked junk files, helper scripts of finished tasks, stale or duplicated lines in .plan/PLAN.md (plan_lines, report only), ' +
  'and specs or docs that no longer match the code (stale_docs, report only). For each item give name, kind, reason, size, age, tracked (git ls-files) and proposed. ' +
  'Tracked files get proposed report-only. Use only read-only commands: `docker ps -a`, `docker volume ls`, `docker network ls`, `docker compose ls`.'

async function survey(phase, label) {
  const got = await agent(SURVEY_BRIEF, { agentType: 'janitor', phase, label, schema: SURVEY_SCHEMA })
  if (!got) log(`${label}: janitor returned nothing`)
  else if (got.status === 'blocked') log(`${label}: janitor blocked: ${got.notes}`)
  return got
}

if (mode !== 'survey' && mode !== 'delete') {
  log(`stopped: unknown mode ${mode}`)
  return { stopped: true, problems: [`mode must be survey or delete, got ${mode}`] }
}

if (mode === 'survey') {
  const found = await survey('Survey', 'survey')
  if (!found || found.status === 'blocked') return { stopped: true, problems: [found ? found.notes : 'survey returned nothing'] }
  return { mode, items: found.items, plan_lines: found.plan_lines, stale_docs: found.stale_docs, notes: found.notes }
}

if (approved.length === 0) {
  log('stopped: delete needs a non-empty args.approved list')
  return { stopped: true, problems: ['args.approved is missing or empty; run survey first and get the user\'s «да» for the exact list'] }
}

const removed = await agent(
  'Mode: delete. The user approved exactly this list with «да»; remove only these entries and nothing else:\n' +
    approved.map((a) => `- ${a}`).join('\n') + '\n' +
    'One command per entry, by exact name: rm for a file, docker rm for a container, `docker volume rm NAME` for a volume, `docker network rm NAME` for a network; no globs, no rm -rf, no prune. ' +
    'Never delete a tracked file (git ls-files) or an entry of another compose project: leave it and say why in left. ' +
    'Do not edit .plan/PLAN.md or any doc. Report each removal with its exit code.',
  { agentType: 'janitor', phase: 'Delete', label: 'delete', schema: DELETE_SCHEMA },
)
if (!removed) {
  log('stopped: delete returned nothing')
  return { stopped: true, problems: ['delete returned nothing'] }
}
if (removed.status === 'blocked') log(`delete blocked: ${removed.notes}`)

const after = await survey('Confirm', 'confirm survey')
const still = after && after.items ? approved.filter((a) => after.items.some((i) => i.name === a)) : []
still.forEach((a) => log(`still present after delete: ${a}`))
return {
  mode,
  deleted: removed.deleted,
  left: removed.left,
  still_present: still,
  survey: after ? { items: after.items, plan_lines: after.plan_lines, stale_docs: after.stale_docs, notes: after.notes } : null,
  notes: removed.notes,
}
