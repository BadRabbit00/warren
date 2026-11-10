// br-research: answers technical questions from the web. Group by meaning, one researcher per group, then a cross-check of weak answers.
export const meta = {
  name: 'br-research',
  description: 'Research questions on the web: group by meaning (up to 5 groups), one web-researcher per group (official docs first, every fact with URL), then a cross-check of answers with confidence below high or conflicting facts',
  whenToUse: 'When the plan or the code needs a checked answer from official docs, changelogs or issues before asking the user; args = { questions: [string], context? }',
  phases: ['Group', 'Research', 'Verify'],
}

const MAX_GROUPS = 5
const strArr = { type: 'array', items: { type: 'string' } }

const GROUPS_SCHEMA = {
  type: 'object',
  required: ['groups'],
  properties: {
    groups: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'questions'],
        properties: { title: { type: 'string' }, questions: strArr },
      },
    },
  },
}

const ANSWERS_SCHEMA = {
  type: 'object',
  required: ['answers'],
  properties: {
    answers: {
      type: 'array',
      items: {
        type: 'object',
        required: ['question', 'answer', 'facts', 'confidence', 'conflicting', 'unverified'],
        properties: {
          question: { type: 'string' },
          answer: { type: 'string' },
          facts: {
            type: 'array',
            items: {
              type: 'object',
              required: ['fact', 'url'],
              properties: { fact: { type: 'string' }, url: { type: 'string' }, date: { type: 'string' } },
            },
          },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          conflicting: { type: 'boolean', description: 'true when found sources disagree' },
          unverified: strArr,
        },
      },
    },
  },
}

const CHECK_SCHEMA = {
  type: 'object',
  required: ['checks'],
  properties: {
    checks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['question', 'status', 'source', 'note'],
        properties: {
          question: { type: 'string' },
          status: { type: 'string', enum: ['confirmed', 'contradicted', 'unverified'] },
          source: { type: 'string', description: 'URL of the newer or contradicting source, or "" when none was found' },
          note: { type: 'string' },
        },
      },
    },
  },
}

function strings(v) {
  return Array.isArray(v) ? v.filter((s) => typeof s === 'string' && s.trim() !== '') : []
}

function chunks(list, n) {
  const out = []
  for (let i = 0; i < list.length; i += n) out.push(list.slice(i, i + n))
  return out
}

const questions = strings(args && args.questions)
if (questions.length === 0) return { stopped: true, problems: ['args.questions is missing or empty'] }
const context = args && typeof args.context === 'string' && args.context !== '' ? `\nContext: ${args.context}` : ''

// Stage 1: group the questions by meaning.
let groups = null
if (questions.length === 1) {
  log('grouping skipped: one question')
  groups = [{ title: 'single', questions }]
} else {
  const got = await agent(
    `Group these questions by meaning into at most ${MAX_GROUPS} groups; every question goes into exactly one group, copied verbatim. Do not answer them.\n` +
      questions.map((q, i) => `${i + 1}. ${q}`).join('\n') + context,
    { agentType: 'web-researcher', label: 'group', phase: 'Group', schema: GROUPS_SCHEMA },
  )
  if (got && got.groups.length > 0) {
    groups = got.groups.filter((g) => g.questions.length > 0)
    if (groups.length > MAX_GROUPS) {
      log(`grouper returned ${groups.length} groups, merging into ${MAX_GROUPS}`)
      const per = Math.ceil(groups.length / MAX_GROUPS)
      groups = chunks(groups, per).map((part) => ({ title: part.map((g) => g.title).join(' / '), questions: part.flatMap((g) => g.questions) }))
    }
    const covered = groups.flatMap((g) => g.questions)
    const lost = questions.filter((q) => !covered.includes(q))
    if (lost.length > 0) {
      log(`grouper dropped ${lost.length} question(s), added to the last group`)
      groups[groups.length - 1].questions.push(...lost)
    }
  } else {
    log('grouping returned nothing: questions split into chunks')
    groups = chunks(questions, Math.ceil(questions.length / MAX_GROUPS)).map((qs, i) => ({ title: `group ${i + 1}`, questions: qs }))
  }
}

// Stage 2: one researcher per group.
const answered = await parallel(
  groups.map((g) => () =>
    agent(
      `Answer these questions (group: ${g.title}). Official documentation first, then changelogs, issues and forums. ` +
        'Match versions to the project\'s lock files. Every fact has a URL (and a date when the page has one). ' +
        'Put into unverified what you could not confirm; set confidence high only when official docs say it for the pinned version.\n' +
        g.questions.map((q, i) => `${i + 1}. ${q}`).join('\n') + context,
      { agentType: 'web-researcher', label: `research ${g.title}`, phase: 'Research', schema: ANSWERS_SCHEMA },
    )),
)
const answers = []
answered.forEach((r, i) => {
  if (!r) return log(`group "${groups[i].title}" returned nothing`)
  r.answers.forEach((a) => answers.push(a))
})
const missing = questions.filter((q) => !answers.some((a) => a.question === q))
if (answers.length === 0) return { stopped: true, problems: ['no researcher returned answers'], unanswered: questions }

// Stage 3: cross-check weak answers.
const weak = answers.filter((a) => a.confidence !== 'high' || a.conflicting || a.unverified.length > 0)
const checks = []
if (weak.length === 0) {
  log('cross-check skipped: every answer has high confidence')
} else {
  const got = await agent(
    'Cross-check these answers. For each, try to find a newer or contradicting source (changelog, issue, newer docs). ' +
      'Mark it confirmed, contradicted (give the source URL) or unverified. Read-only.\n' +
      weak.map((a, i) => `${i + 1}. Question: ${a.question}\nAnswer: ${a.answer}\nConfidence: ${a.confidence}\nFacts: ${a.facts.map((f) => `${f.fact} (${f.url})`).join('; ')}\nUnverified: ${a.unverified.join('; ')}`).join('\n'),
    { agentType: 'web-researcher', label: 'cross-check', phase: 'Verify', schema: CHECK_SCHEMA },
  )
  if (got) got.checks.forEach((c) => checks.push(c))
  else log('cross-check returned nothing: weak answers stay unchecked')
}

return {
  answers: answers.map((a) => {
    const c = checks.find((x) => x.question === a.question)
    const status = c ? c.status : weak.includes(a) ? 'unchecked' : 'high-confidence'
    return { ...a, check: status, check_source: c ? c.source : '', check_note: c ? c.note : '' }
  }),
  unanswered: missing,
}
