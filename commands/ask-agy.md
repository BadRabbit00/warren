---
description: Second opinion from Gemini 3.8 Flash via Antigravity CLI (ask-agy wrapper, plan mode + sandbox — the model cannot write anything), effort high by default. Cheap reviews, alternatives, a third voice next to Claude and Astra. Prompt template, fixed model/effort, report saved to a file. For 1M-context jobs use /ask-argon.
argument-hint: "[question] [--diff | --staged | --files a b … | range] [-e medium|high|xhigh]"
---

# /ask-agy

Consult Gemini 3.8 Flash through the pinned `ask-agy` wrapper: `agy --print --model gemini-3.8-flash-high --effort high --mode plan --sandbox`. **Plan mode: the model reads and answers, it cannot edit files**; for implementation use `/write-agy`. Report: `~/.local/state/ask-models/<repo>/ask-agy-<timestamp>.md`.

This is also where Gemini gets a concrete model and effort: agent files for agy only accept tiers, the wrapper passes real ids. `-e medium` for cheap questions, `-m <id>` from `agy models` only on request.

## Procedure

1. **Collect context** into a prompt file in the scratchpad (never inline): `--diff` / `--staged` / `--files …` / a range, same rules as `/ask-astra`. No secrets.
2. **Write the prompt**:

   ```markdown
   # Role
   You are an independent senior engineer. You did not write this code. Be concrete; cite file:line. Use the project's own toolchain, never global installs.

   # Project
   <stack, build system, constraints>

   # Material
   <diff / files>

   # Question
   <question, or "Review for correctness, security, edge cases, design; what was missed?">

   # Output
   Verdict first, then findings by severity with file:line and the minimal fix, then what was missed, then open questions.
   ```

3. **Run** `ask-agy -f <prompt.md>`.
4. **Verify** findings against the code; mark confirmed / disputed.
5. **Report**: verdict, confirmed findings, disputed ones briefly, report path. Apply fixes only on request.
