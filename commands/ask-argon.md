---
description: Second opinion from Gemini 4 Argon via Antigravity CLI (ask-argon wrapper, plan mode + sandbox — the model cannot write anything). Argon has a real 1M-token window for whole-repo reasoning: cross-language ports, repo-wide refactor plans, deep security audits across many files. Expensive — only when the task needs that much context in one head. Report saved to a file.
argument-hint: "[task] [--files a b … | --dirs src/ lib/ | range] [-e high|xhigh|max]"
---

# /ask-argon

Consult Gemini 4 Argon through the pinned `ask-argon` wrapper: `agy --print --model gemini-4-argon-high --effort high --mode plan --sandbox`. **Plan mode: it cannot edit files**; for implementation use `/write-argon`. Report: `~/.local/state/ask-models/<repo>/ask-argon-<timestamp>.md`.

## When it is justified

- Porting a large codebase to another language, or a repo-wide refactor plan.
- Security audit across dozens of files where the connections between them matter.
- Migration plans that need the whole schema, all callers and all tests at once.

Not for ordinary reviews or a single diff: say so and offer `/ask-agy` or `/ask-astra` if the user asks for Argon on a small change. It burns tokens fast.

## Procedure

1. **Collect the whole material** into a prompt file in the scratchpad: `--dirs` → every source file under the directories with a `### path` header before each (`find … -type f -name '*.py' -exec sh -c 'printf "### %s\n" "$1"; cat "$1"' _ {} \;` style, written to the file, not inline); `--files` / range as in `/ask-astra`. Exclude generated files, vendored code, lockfiles, secrets. State the size (files, lines) to the user before running.
2. **Write the prompt**:

   ```markdown
   # Role
   You are a principal engineer with the entire codebase in front of you. Reason about cross-module connections, not single files. Cite file:line. Use the project's own toolchain; no global installs.

   # Project
   <stack, build system, constraints, goal>

   # Material
   <files with headers>

   # Task
   <e.g. "Produce a step-by-step plan to port this to Rust: module map, order of work, risky spots, what breaks, tests to write first", or "Audit for security across all modules">

   # Output
   Verdict / executive summary first, then a numbered plan or findings by severity with file:line, then risks, then open questions.
   ```

3. **Run** `ask-argon -f <prompt.md>` (`-e xhigh` only if the user accepts the cost).
4. **Verify** the key claims against the code; mark confirmed / disputed.
5. **Report**: summary, confirmed findings or the plan, disputed points, report path. Apply nothing without a request.
