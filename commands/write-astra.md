---
description: Let GPT-6-Astra implement a well-specified change (Codex CLI, xhigh, workspace-write sandbox — it may edit files in the repo, no network). Use when the user explicitly wants Astra to write code; the result is reviewed with the right reviewer agent and tests before anything is committed.
argument-hint: "[task] [--files a b … | --plan path/to/plan.md] [-e effort]"
---

# /write-astra

Hand an implementation task to GPT-6-Astra through the pinned `write-astra` wrapper: `codex exec -s workspace-write -m gpt-6-astra`, effort `xhigh`. **The model may create and edit files inside the repository**; it has no network and no access outside the workspace. The report (`~/.local/state/ask-models/<repo>/write-astra-<timestamp>.md`) ends with `git status` and `diff --stat` after the run.

## Guardrails

- Only on an explicit request to have Astra write code. For opinions use `/ask-astra`.
- The working tree must be clean or the user must accept mixing changes: run `git status` first and say what is there.
- The task must be specified: files to touch, expected behaviour, acceptance tests. If a plan exists (`/plan`), pass it with `--plan`.
- Never let it commit, push, install tools globally or touch `.env` / secrets; say so in the prompt.

## Procedure

1. **Write the prompt** in the scratchpad:

   ```markdown
   # Role
   You are implementing a change in this repository. Edit files directly. Do not commit, do not push, do not install anything globally: run tools through the project's own toolchain. Do not touch .env, secrets or files outside the listed scope unless unavoidable (then say why).

   # Project
   <stack, build/test commands, conventions>

   # Task
   <what to build, acceptance criteria, files in scope>

   # Plan (if any)
   <approved plan>

   # Finish with
   A summary: files changed, how you tested, what is left, open questions.
   ```

2. **Run** `write-astra -f <prompt.md>`.
3. **Review the diff yourself**: `git diff`, then the language reviewer (`python-reviewer`, `rust-reviewer`, …) with an explicit scope, and `security-reviewer` if input/auth/secrets/SQL/network are involved.
4. **Run the project's tests** with the project's own test command. Fix or revert what fails (`git checkout -- <file>` for rejected changes).
5. **Report**: what Astra changed, review findings, test results, report path. Commit only when the user asks (`conventional-commit-review`).
