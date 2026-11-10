---
name: user-flows
description: Use when you must derive user flows from docs and UI routes for end-to-end tests - business-critical flows first, flow format with steps, expectations, DB checks and timing, navigation, roles, error states, concurrency.
metadata:
  origin: warren
---

# User Flows

How to turn project docs and UI routes into a list of flows that e2e tests can run. Pair it with `e2e-testing` for the Playwright side.

## Sources

Read in this order: the general process docs (what the business does), the API docs or OpenAPI (what the backend offers), the specification (rules and edge cases), then the UI routes (what the user can reach). A flow that no doc describes is reported as a question, not invented.

## Order of work

1. Business-critical flows first: the path that earns money or delivers the product, end to end. Example: open app, search "coffee", pick a merchant, add items, pay, order received.
2. Every other interaction the UI allows: assemble the leftovers (settings, profile, lists, filters, empty pages) into meaningful flows, grouped by what the user is trying to do, not by route.
3. Add the probes below to the flows they fit; do not make a separate flow for each.

## Flow format

```
id: F03
name: Order a coffee
priority: critical | high | normal
persona: customer
steps:
  - action: open /search and type "coffee"
    expect: list of merchants, first page of 20
    db_checks: []
    timing: p95 under the budget in docs/POLICY.md
  - action: press "Pay"
    expect: confirmation page with order number
    db_checks: [orders row status=paid, payments row amount equals cart total]
```

Every step has an action and an observable expectation. Every step that writes has a DB check: table, key, expected columns. Timing names the budget and its source; it is reported, not failing.

## Probes to add

- Navigation: back returns to the previous page, not home or a 404; forward works; refresh keeps or restores state; a deep link opens the right page and asks for login when needed.
- Roles: the same route as each role (anonymous, user, other user, admin); forbidden means 403 or redirect, and no data in the response.
- Empty states: new account, no results, empty cart.
- Error states: invalid input, server error, offline, expired session; the message is shown and no half-written rows remain.
- Concurrency: two tabs doing the same action (double submit, stale cart); the DB ends in one consistent state.
- Long and odd inputs: maximum lengths, unicode, leading spaces; the limit from the docs is the boundary.

## Anti-patterns

- Testing implementation details (CSS classes, internal ids) instead of what the user sees and what the DB holds.
- One giant flow covering everything: a failure in step 2 hides steps 3 to 30. Keep a flow to one goal, about 5 to 12 steps.
- Flows without DB assertions: the page says "paid" while no row was written.
- Flows that depend on each other's data; each flow creates its own data through the harness.
- Inventing behaviour the docs do not state; list it as a question for research.

## Output

A flows document (`docs/temp/e2e-<id>/flows.md`) with flows ordered by priority, plus the list of API endpoints with method, path and group, so contract tests can be split by group.
