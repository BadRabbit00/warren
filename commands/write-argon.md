---
description: Let Gemini 4 Argon implement a repo-scale change (Antigravity CLI, accept-edits mode + sandbox — it may edit files in the repo). Its 1M-token window is for cross-language ports, repo-wide refactors and multi-module migrations; expensive, only with an approved plan. Reviewed and tested before any commit.
argument-hint: "[task] [--plan path/to/plan.md] [--dirs src/ lib/] [-e high|xhigh]"
---

# /write-argon

Hand a large implementation task to Gemini 4 Argon through the pinned `write-argon` wrapper: `agy --print --model gemini-4-argon-high --effort high --mode accept-edits --sandbox`. **Edits auto-approved, permission-requiring commands denied, no network.** The report (`~/.local/state/ask-models/<repo>/write-argon-<timestamp>.md`) ends with `git status` and `diff --stat`.

## Guardrails

- Only for work that needs the whole repo in context (port, repo-wide refactor, multi-module migration) and only with an approved plan (`/ask-argon` or `/plan` first). For a normal feature use `/write-agy` or `/write-astra`.
- Clean working tree, ideally a fresh branch: suggest `git switch -c argon/<task>` first.
- Task with scope, order of work and acceptance tests; no commits, no global installs, no secrets.
- Warn the user about cost before running; `-e xhigh` only if accepted.

## Procedure

1. **Write the prompt** in the scratchpad: role with NixOS rules, project, the approved plan step by step, scope (`--dirs`), acceptance criteria, finish-with summary (files changed, tests run, what remains).
2. **Run** `write-argon -f <prompt.md>`.
3. **Review the diff** per language with explicit folder scopes (`language-reviewer` on `backend/**`, `language-reviewer` on `crates/**`, …) plus `security-reviewer`.
4. **Run the full test gate** via the devShell (`verification-loop`); fix or revert.
5. **Report**: what changed, review findings, test results, what is left, report path. Commit only on request.
