# PLAN — <feature or project name>

<!-- BR plan template v2. Installed at ~/.claude/br/templates/PLAN.md, copied to <repo>/.plan/PLAN.md.
Working memory of the orchestrator, in English. A fresh session must be able to resume from this file alone.
Hooks read this file: task headings `### T<n> — …`, and the bold fields `Status`, `Writes (exclusive)`, `Tests (test-writer)`.
Keep those exact spellings. No other bold field in a task card may start with "Writes" or "Tests".
Delete every hint comment and <…> placeholder as you fill. -->

## Status

- **Plan id:** <P261031> · **Branch:** `feature/<P261031>-<slug>`
- **Mode:** <A — new project / B — existing project> · **Track:** <S — small change / F — full>
- **Stage:** <0 intake / 1 business / 2 architecture / 3 docs / 4 plan / 5 execution / 6 wrap-up>
- **Gates:** G1 <☐ / ✅ YYYY-MM-DD> · G2 <☐> · G3 <☐> · G4 <☐> · G5 <☐>
- **Execution:** <manual / auto> · **Order:** <tests first (default) / code first — confirmed YYYY-MM-DD> · **Coder model:** <sonnet (default)> · **Dispatch:** <workflows (/br-wave per wave, /br-review at checkpoints) / manual> — confirmed YYYY-MM-DD
- **Next action:** <one line>

## Sources

<!-- Everything read. Mark what the user gave as examples. -->

- `<path or name>` — <what it is>

## Gaps

<!-- Unknowns. Each becomes a question in the next batch. Remove when answered (the answer goes to Decisions or docs). -->

- [ ] <gap> — <where it matters>

## Decisions

<!-- Every agreed decision, including pushback outcomes and confirmed policies. Newest last. -->

| Date | Decision | Why | Rejected |
|---|---|---|---|
| <YYYY-MM-DD> | <...> | <...> | <...> |

---

## Before → After

<!-- Mode B only. One row per changed item. Mode A: delete this section. -->

### Files

| File | Before | After | Task |
|---|---|---|---|
| `<path>` | <does X / absent> | <does X and Y / removed> | <T2> |

### Entities

| Entity | Before | After | Task |
|---|---|---|---|

### API and events

| Endpoint / event | Before | After | Task |
|---|---|---|---|

### Database

| Table / field | Before | After | Migration task |
|---|---|---|---|

### Docs

| Doc file | What changes |
|---|---|
| `docs/<FILE>.md` | <...> |

---

## Contracts

<!-- Everything two or more tasks talk through. Defined in docs, created in code by a contract task in wave 1. -->

| Contract | Defined in | Created by | Used by |
|---|---|---|---|
| `<OrderCreated event>` | `docs/API.md#<...>` | <T1> | <T3, T4> |

---

## Tasks

<!-- One card per task.
Status = the step running now: todo → red → green → refactor → review → done (or blocked).
Set it BEFORE dispatching: red → test-writer, green → coder, refactor → refactorer. Hooks give each executor
only the write set of tasks in its step, so a stale status blocks the executor.
Writes (exclusive): production files only, never a test path. Tests (test-writer): test paths only (`tests/`, `*_test.go`, …).
Evidence: one line per step, numbers from test-runner, combined sha256 of the task's test files. -->

### T1 — <name>

- **Goal:** <one or two sentences>
- **Wave:** <1> · **Depends on:** <— / T0>
- **Writes (exclusive):** `<src/orders/app/services/order_service.py>`, `<src/orders/app/repositories/**>`
- **Tests (test-writer):** `<src/orders/tests/services/test_order_service.py>`
- **Reads:** `docs/<FILE>.md#<anchor>`, ...
- **Skills:** <skill names the agents must read first, or —>
- **Provides contracts:** <...> · **Uses contracts:** <...>
- **Coder:** <sonnet / astra — agreed YYYY-MM-DD, why>
- **Parts:** <filled at dispatch: P1 `files` → agent; P2 `files` → agent (after P1); disjoint files, each sized to one agent; or —>
- **Subtasks:**
  1. <T1.1 ...>
  2. <T1.2 ...>
- **Acceptance criteria:**
  - AC1: <observable behaviour> → test: <test name>
  - AC2: <...>
- **Status:** todo
- **Evidence:**
  - red: <command> → <0 passed, 3 failed (reason: missing behaviour)>; tests sha256 `<…>`
  - green: → <3 passed, 0 failed, 0 skipped>; tests sha256 `<…>` (unchanged)
  - refactor: → <3 passed>; tests sha256 `<…>` (unchanged)
- **Review:** <reviewers run → must-fix count / suboptimal count; round 1/2>
- **Commits:** <test: sha · feat: sha · refactor: sha>
- **Notes:** <blockers, decisions taken during execution>

---

## Checkpoint C1

<!-- Review point (placed at G4) after risky steps and important tasks. /br-review {checkpoint: "C1"} reads it and runs in the background; findings become fix items of the next manifest. Copy per checkpoint. -->

- **After:** <T1, T3>
- **Risky areas:** `<src/orders/app/auth/**>` — <security / contracts / data / money>
- **DB work:** <yes / no> · **Migrations:** `<migrations/0007_orders.sql>` or —

## Manifest W1

<!-- Written by the orchestrator at dispatch, one per wave. /br-wave {wave: "W1"} reads it. step: red, green, refactor, fix-tests, fix-code, check.
agent is optional (defaults by step and file extension). Parts of one task must not share files. At most 15 agents per run. Task Status must match the steps. -->

```json
{ "wave": "W1", "items": [
  { "id": "T1a", "task": "T1", "step": "red", "files": ["src/orders/tests/services/test_order_service.py"],
    "brief": "AC1-AC2: create and cancel order", "expect_green": [], "after": [] },
  { "id": "T1b", "task": "T1", "step": "red", "files": ["src/orders/tests/api/test_orders_api.py"],
    "brief": "AC3: HTTP errors", "after": ["T1a"] }
] }
```

---

## Dependency map

<!-- Arrow = "is needed by". Then the waves. No cycles. -->

```
T1 ──► T3 ──► T5
T2 ──► T4 ──┘
```

| Wave | Tasks (parallel) | Wave check |
|---|---|---|
| 1 | T1, T2 | <optimizer on wave diff: n findings> |
| 2 | T3, T4 | |
| 3 | T5 | |

## Write-set check

<!-- Every file written in this plan, exactly once, tests included. A file in two rows = a broken plan. -->

| File / glob | Task | Kind |
|---|---|---|
| `<src/orders/app/services/order_service.py>` | <T1> | code |
| `<src/orders/tests/services/test_order_service.py>` | <T1> | test |

## Follow-ups

<!-- Reviewer findings marked "suboptimal", things noticed outside the scope. Not done in this plan. -->

- <finding> — <source: reviewer / task>

## Risks

- <risk> — <what we do if it happens>
