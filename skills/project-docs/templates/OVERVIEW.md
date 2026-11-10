# OVERVIEW — <project name>

<!-- Filled LAST and only from the finished docs. Nothing new here —
only a compression of what is already in other files. Guideline: up to 80 lines.
This is the first file an agent opens. -->

**In one sentence:** <what it is and for whom>

## Business

- **Problem:** <compressed from GENERAL.md>
- **Solution:** <compressed from GENERAL.md>
- **Main processes:**
  - <process> → `GENERAL.md#<...>`
  - <process> → `GENERAL.md#<...>`

## Tech

- **Stack:** <Python 3.12 · FastAPI · PostgreSQL 16 · RabbitMQ>
- **Services:**
  - `<svc-orders>` — <one line>
  - `<svc-billing>` — <one line>
- **Data:** <which DBs, who owns them>
- **Auth:** <one line: JWT for users, mTLS between services>

## Key rules

<!-- 3–5 MUST-level rules from POLICY.md that are broken most often. -->

1. <...> → `POLICY.md#<...>`
2. <...>
3. <...>

## Where to look

| I want to know | Open |
|---|---|
| Why the project exists, how the business works | `GENERAL.md` |
| Endpoints, events, webhooks | `API.md` |
| What is stored in the DB | `DATABASE.md` + `<db_name>.dbml` |
| Where each file is | `STRUCTURE.md` |
| Entities in code and how they relate | `ENTITY.md` |
| Which methods are bloated | `METHOD.md` |
| What the system is built from, limits, secrets, environments | `SPECIFICATION.md` |
| How we usually write code | `PATTERN.md` |
| What is mandatory and forbidden | `POLICY.md` |
| What is being changed right now | `../.plan/PLAN.md` |

## Open questions

<!-- All ❓ from other files. No questions — delete the section. -->

- [ ] <question> — from `<FILE.md#...>`
