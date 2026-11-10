---
description: Independent second opinion from GPT-6-Astra (Codex CLI, xhigh, read-only sandbox — the model cannot write anything). Prompt template, fixed model/effort via the ask-astra wrapper, report saved to a file. Use for high-stakes code, security-sensitive changes, disputed designs, or whenever the user asks "what would Astra say".
argument-hint: "[question] [--diff | --staged | --files a b … | range] [-e effort]"
---

# /ask-astra

Consult GPT-6-Astra through the pinned `ask-astra` wrapper: model `gpt-6-astra`, effort `xhigh`, Codex sandbox `read-only`. **The model cannot modify files**; if the user wants Astra to implement something, use `/write-astra` instead. The wrapper writes the report to `~/.local/state/ask-models/<repo>/ask-astra-<timestamp>.md` and prints the answer.

## Procedure

1. **Collect context** into a prompt file in the scratchpad (never inline):
   - `--diff` → `git diff`; `--staged` → `git diff --cached`; `--files` → contents of the named files; a range like `main..HEAD` → `git diff main..HEAD`. Default: current uncommitted diff plus the question.
   - One paragraph of project facts: language, framework, build system, what the change is supposed to do.
   - No secrets: `.env`, keys, tokens, sops files stay out.
2. **Write the prompt** with this template:

   ```markdown
   # Role
   You are an independent senior engineer and security reviewer. You did not write this code; be concrete, adversarial and specific. Cite file:line. Do not propose installing tools globally: use the project's own toolchain.

   # Project
   <stack, build system, constraints>

   # Material
   <diff or files>

   # Question
   <the user's question, or: "Review this change for correctness, security, edge cases and design. What did the author miss?">

   # Output
   1. Verdict: SHIP / FIX FIRST / REDESIGN, one sentence why.
   2. Findings, most severe first: severity (CRITICAL/HIGH/MEDIUM/LOW), file:line, what breaks, minimal fix.
   3. Things the author likely missed (tests, failure modes, migrations, perf).
   4. Open questions for the author.
   ```

3. **Run** `ask-astra -f <prompt.md>` (`-e` only on request). Wait for it to finish.
4. **Verify** every finding against the actual code before repeating it; mark each confirmed / disputed with a reason.
5. **Report**: verdict, confirmed findings with file:line, disputed ones briefly, report path. Do not apply fixes unless asked; if asked, fix CRITICAL/HIGH first and rerun the project's tests.

Pairs with `/ask-agy` or `/ask-argon` for another voice and with `council` for the decision.
