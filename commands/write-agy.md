---
description: Let Gemini 3.8 Flash implement a well-specified change (Antigravity CLI, accept-edits mode + sandbox — it may edit files in the repo; commands needing approval are denied). Use when the user explicitly wants Gemini to write code; the result is reviewed and tested before any commit.
argument-hint: "[task] [--files a b … | --plan path/to/plan.md] [-e effort]"
---

# /write-agy

Hand an implementation task to Gemini 3.8 Flash through the pinned `write-agy` wrapper: `agy --print --model gemini-3.8-flash-high --effort high --mode accept-edits --sandbox`. **File edits are auto-approved; commands that would need a permission prompt are denied**, there is no network. The report (`~/.local/state/ask-models/<repo>/write-agy-<timestamp>.md`) ends with `git status` and `diff --stat`.

## Guardrails

Same as `/write-astra`: explicit request only, clean tree or the user's consent, specified task with acceptance criteria, no commits, no global installs, no secrets. For repo-wide work use `/write-argon`.

## Procedure

1. **Write the prompt** in the scratchpad (template as in `/write-astra`: role with the project's toolchain rules, project, task, plan, finish-with summary).
2. **Run** `write-agy -f <prompt.md>`.
3. **Review the diff** with the right reviewer agents (explicit scope), `security-reviewer` when relevant.
4. **Run tests** with the project's own test command; fix or revert.
5. **Report**: changes, findings, test results, report path. Commit only on request.
