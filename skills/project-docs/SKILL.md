---
name: project-docs
description: Use when writing, updating, or reading project documentation in docs/ - the 10-file standard, one home per fact, templates, fill order for new and existing projects, and what to update after a code change.
---

# Project docs

Docs let an agent understand a project without reading the whole codebase: it opens one file, takes the facts it needs, and goes to work. Docs are written **before** code and are the source of truth; code is written to match them.

Docs are in **English**. Slides for people (`docs/slides/`, `.plan/PLAN.html`) are in Russian and are made by `presenter`; agents never read slides.

Templates: `templates/` next to this file (`~/.claude/skills/project-docs/templates/`). Copy them into `<repo>/docs/` and fill them. `example_db.dbml` is renamed after the database (`orders_db.dbml`); one database = one `.dbml`.

## Contents

1. [Files](#files) · 2. [One home per fact](#one-home-per-fact) · 3. [Format](#format) · 4. [Jobs](#jobs) · 5. [Fill order](#fill-order) · 6. [After a code change](#after-a-code-change) · 7. [Checklist](#checklist) · 8. [Examples](#examples)

## Files

| File | Answers | Soft limit |
|---|---|---|
| `OVERVIEW.md` | the project in 2 minutes + "question → file" table. **Agent entry point**, written last | 80 lines |
| `GENERAL.md` | the business problem (user's words), actors, processes, glossary | 400 |
| `API.md` | endpoints, service-to-service calls, webhooks, broker events | 600 |
| `DATABASE.md` + `<db>.dbml` | what is stored and why, owner, record lifecycle; types and indexes only in `.dbml` | 400 |
| `STRUCTURE.md` | where each file is and what is inside, one line per item | 400 |
| `ENTITY.md` | entities in code: purpose, type, relations, invariants, contract (method names only) | 500 |
| `METHOD.md` | only methods with 3+ jobs, each with a verdict | 300 |
| `SPECIFICATION.md` | services, stack, protocols, auth, limits, secrets (names only), environments | 400 |
| `PATTERN.md` | how we usually do things (observation) | 300 |
| `POLICY.md` | what is mandatory or forbidden (rule), from `POLICY.defaults.md` with `Source:` | 300 |

Over the limit → first look for facts duplicated from another file.

## One home per fact

A fact is written in full in exactly one file; others link to it with one line. A fact in two places goes stale in one of them, and the agent gets a contradiction.

| Fact | Home | Linked from |
|---|---|---|
| business process, roles, terms | `GENERAL.md` | `OVERVIEW.md`, `ENTITY.md` |
| endpoint: path, method, body, codes | `API.md` | `SPECIFICATION.md`, `STRUCTURE.md` |
| broker event, webhook | `API.md` | `SPECIFICATION.md` |
| field types, keys, indexes | `<db>.dbml` | `DATABASE.md` |
| table meaning, owner, lifecycle | `DATABASE.md` | `ENTITY.md`, `SPECIFICATION.md` |
| what each file is for | `STRUCTURE.md` | — |
| entity: purpose, relations, invariants | `ENTITY.md` | `STRUCTURE.md`, `METHOD.md` |
| method details | `METHOD.md` (fat methods only) | `ENTITY.md` |
| services, stack, limits, environments | `SPECIFICATION.md` | `API.md`, `OVERVIEW.md` |
| "how we usually do it" | `PATTERN.md` | `POLICY.md` |
| "mandatory / forbidden", retries, data classes | `POLICY.md` | `API.md`, `PATTERN.md`, `METHOD.md` |

Link = file + heading anchor: `Retries → POLICY.md#p-http-retries`, `Auth → SPECIFICATION.md#external-auth`. Do not retell what you link to.

**PATTERN vs POLICY vs SPECIFICATION.** PATTERN is an observation ("we log with `structlog`, every record has `request_id`"). POLICY is a rule with a level ("delete only via `DELETE`"). SPECIFICATION is how the system is built and its hard limits ("upload max 20 MB", "access token lives 15 min"). A pattern becomes a policy when the user says it is mandatory; then the pattern links to the policy.

**Policies** start from `~/.claude/br/templates/POLICY.defaults.md`. Copy the ones that apply with their `P-…` id as the heading and `Source: default (P-…)`. The orchestrator confirms the `Ask: yes` ones with the user and sets `Source: confirmed YYYY-MM-DD`.

## Format

- **Cards, not wide tables.** A heading, then `- **Field:** value` lines. Tables only for short columns (summaries, lookups).
- **Heading = anchor.** Put the entity, endpoint, or rule id into the heading so it can be linked.
- **Do not invent.** A fact not in the code and not said by the user → `❓ <question>` in its place. All `❓` are collected in `OVERVIEW.md#open-questions`.
- **Change markers.** `🆕` at the end of a heading = planned, not implemented. `🗑️` = exists now, will be removed. The orchestrator removes the marker (or the whole `🗑️` card) when the task is done. A card without a marker describes the code as it is now.
- **No template leftovers.** Every `<!-- … -->` hint and `<…>` placeholder is deleted after filling: they cost tokens on every read.
- **No empty sections.** No webhooks → delete the section, do not write "none". Exception: "Exceptions: none" inside a rule.
- **Tests** live in `tests/`: a service's own in `src/<service>/tests/`, shared ones in `/tests` (Flutter/Dart: native `test/`). `STRUCTURE.md` lists test folders, not test files.

## Jobs

`METHOD.md` lists only methods with **more than two jobs**; it exists to catch bloated methods. A job is a separate action with its own result:

1. input check (validation, permission check);
2. DB read;
3. DB write;
4. call to an external service or API;
5. sending an event or message (broker, email, push, webhook);
6. data transformation (mapping, calculation, building a response from several sources);
7. side effect (file, cache, audit log).

Not a job: logging, returning, re-raising. Identical actions in a row are one job (three reads for one response = "DB read").

Verdict for each: `✅ Justified` + reason (an orchestrator method that only glues steps), or `✂️ Split` + into what. The rule itself is `POLICY.md#p-code-method-jobs`.

## Fill order

**Mode A — new project** (from the conversation, before code): GENERAL (the problem is asked, in the user's words) → SPECIFICATION → DATABASE + `.dbml` → API → ENTITY → METHOD (usually empty; add an orchestrator method if visible) → STRUCTURE → PATTERN (from skills and conversation) → POLICY → OVERVIEW.

**Mode B — existing project** (from code): STRUCTURE first (the map makes the rest fast) → ENTITY → METHOD (count jobs) → DATABASE + `.dbml` (from migrations and models) → API (routers, clients, consumers) → SPECIFICATION (configs, compose, CI) → PATTERN (repetition in code) → POLICY (only what is enforced by linters/CI or confirmed by the user) → GENERAL (processes from code; the problem is **always** asked) → OVERVIEW.

Mode B with researchers: split the repo into disjoint areas (per service or top directory); each `researcher` returns cards for its area in the formats above. The writer merges them. Conflicting facts → one more researcher to verify, never a guess.

After mode B the docs describe the current state. A change is then added as the target state with 🆕 / 🗑️ before any code is written.

## After a code change

| Changed | Update |
|---|---|
| file added or removed | `STRUCTURE.md` |
| new entity, contract changed | `ENTITY.md` (+ `STRUCTURE.md`) |
| method grew to 3+ jobs or shrank | `METHOD.md` |
| endpoint, event, webhook | `API.md` |
| migration | `.dbml`, `DATABASE.md` |
| service, library, limit, secret name, environment | `SPECIFICATION.md` |
| new mandatory rule | `POLICY.md` |
| repeated technique noticed | `PATTERN.md` |
| business process | `GENERAL.md` |
| the big picture | `OVERVIEW.md` |
| planned item implemented | remove its 🆕 / 🗑️ |

## Checklist

- [ ] No fact is written out in two files; a link stands instead.
- [ ] Every `FILE.md#anchor` points to an existing heading.
- [ ] The problem in `GENERAL.md` is in the user's words.
- [ ] Contracts in `ENTITY.md` are method names only.
- [ ] `METHOD.md` has only 3+ job methods, each with a verdict.
- [ ] Field types live only in `.dbml`.
- [ ] Rules in `API.md` are one line with a link to `POLICY.md`.
- [ ] Every policy has `Source:`; `default` ones were shown to the user.
- [ ] No hints, placeholders, or empty sections left.
- [ ] 🆕 / 🗑️ match reality.
- [ ] All `❓` are in `OVERVIEW.md`; `OVERVIEW.md` was written last.

## Examples

### R-DOCS-API-LINKS — API cards link to policies

Bad:
```markdown
### POST /v1/orders
- **Retries:** clients retry 3 times with 0.5 s → 1 s → 2 s backoff on 429/502/503/504.
```
Why: the same rule also lives in POLICY.md; when one is changed the other lies.

Good:
```markdown
### POST /v1/orders
- **Retries:** → `POLICY.md#p-http-retries`
```

### R-DOCS-CONTRACT-NAMES — the contract lists names, not bodies

Bad:
```markdown
- **Contract:**
  - `create(cart, user) -> Order` — validates the cart, writes the order, calls billing, publishes `order.created`
```
Why: method details duplicate METHOD.md and the code; they go stale first.

Good:
```markdown
- **Contract:** `create`, `cancel`, `recalculate_total` → details of `create` in `METHOD.md#ordercreate`
```

### R-DOCS-UNKNOWN-VALUES — ask, do not fill

Bad:
```markdown
- **Max upload size:** 10 MB
```
Why: nobody said 10 MB; the number becomes a "fact" that code and tests are built on.

Good:
```markdown
- **Max upload size:** ❓ what is the largest file a user uploads? (default in P-API-LIMITS: 20 MB)
```
