---
paths:
  - ".plan/**"
---

# Change plan

## Scope

`.plan/PLAN.md` (for agents) and `.plan/PLAN.html` (slides for the user). Only the orchestrator writes `PLAN.md`; executors read their task card. `todo.md` is never created.

## Rules

- R-PLAN-WRITESET: every task card has `Writes (exclusive)`. No file or glob appears in two tasks; the "Write-set check" table lists every written file exactly once. Shared files go to an earlier contract task that the others depend on.
- R-PLAN-TESTS-SEPARATE: test files of a task are listed under `Tests (test-writer)`, not under `Writes`. The coder's write set never contains a test path (`tests/`, `test/`, `*_test.go`, …).
- R-PLAN-AC: every task has acceptance criteria. Each criterion maps to at least one test.
- R-PLAN-WAVES: dependencies form waves with no cycles. Tasks in one wave never share a write set.
- R-PLAN-EVIDENCE: each executed step records its evidence: the test run (passed/failed/skipped numbers), the `sha256` of the task's test files after the red step, and the same hash after `coder` and `refactorer`.
- R-PLAN-STATUS: status moves `todo → red → green → refactor → review → done` (or `blocked`) and names the step running now. The orchestrator sets `red` before dispatching test-writer, `green` before coder, `refactor` before refactorer. Hooks give each executor only the write set of tasks in its step, so a wrong status blocks the executor. Gates G1–G5 carry dates.

## Examples

### R-PLAN-WRITESET — disjoint write sets

Bad:
```markdown
### T2 — order status filter
- **Writes (exclusive):** `src/orders/app/services/order_service.py`
### T3 — order export
- **Writes (exclusive):** `src/orders/app/services/order_service.py`, `src/orders/app/services/export_service.py`
- **Wave:** 1 · **Depends on:** —
```
Why: T2 and T3 run in parallel and edit the same file; one overwrites the other.

Good:
```markdown
### T2 — order status filter
- **Writes (exclusive):** `src/orders/app/services/order_service.py`
- **Wave:** 1
### T3 — order export
- **Writes (exclusive):** `src/orders/app/services/export_service.py`
- **Uses contracts:** `OrderService.list_filtered` (provided by T2)
- **Wave:** 2 · **Depends on:** T2
```

### R-PLAN-EVIDENCE — record the proof

Bad:
```markdown
- **Status:** done
```
Why: there is no way to tell whether the tests were written first or whether the coder touched them.

Good:
```markdown
- **Status:** done
- **Evidence:**
  - red: `pytest src/orders/tests/services -q` → 0 passed, 3 failed; tests sha256 `9f1c…`
  - green: → 3 passed, 0 failed, 0 skipped; tests sha256 `9f1c…` (unchanged)
  - refactor: → 3 passed; tests sha256 `9f1c…`; full suite 214 passed
```
