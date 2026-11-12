---
name: language-review
description: Use when reviewing the Python, Go, Rust, TypeScript/React or Flutter/Dart files of a diff for language-level bugs and idioms. Gives the common review method, the severity scale, and per-language tools, checklists, typical grades and examples.
---

# Language review

## When to use

- A task's diff contains `.py`, `.go`, `.rs`, `.ts`/`.tsx` or `.dart` files and you review their language-specific problems.
- Architecture, AC coverage and method size belong to `code-reviewer`; database queries to `db-reviewer`; security depth to `security-reviewer`.

## Contents

1. [Which reference to open](#which-reference-to-open)
2. [Method](#method)
3. [Severity](#severity)
4. [Must and must not](#must-and-must-not)
5. [Output](#output)

## Which reference to open

Open only the references for the languages present in the diff. Do not read the others.

| Files in the diff | Reference | Rule ids |
|---|---|---|
| `.py` | [references/python.md](references/python.md) | R-PYR-* |
| `.go` | [references/go.md](references/go.md) | R-GOR-* |
| `.rs` | [references/rust.md](references/rust.md) | R-RSR-* |
| `.ts`, `.tsx` | [references/typescript.md](references/typescript.md) | R-TSR-* |
| `.dart` | [references/dart.md](references/dart.md) | R-DARTR-* |

Each reference holds the tools to run, the checklist, the typical grades, the language's Must / Must not, and three examples.

## Method

Inputs: task id, base ref, the files of the language in the diff, and what `code-reviewer` already reported (do not repeat it).

1. `git diff <base>...HEAD -- <files>`; read each changed function whole, with its callers.
2. Run the tools listed in the reference through `nix develop -c` (only tools the project has).
3. Go through the checklist; every tool finding you keep is re-checked by reading the code.
4. Filter, grade, report.

## Severity

Same scale as `code-reviewer`: CRITICAL / HIGH -> must fix; MEDIUM -> suboptimal; LOW -> nit. A finding survives only if you can name the failing input or the rule id, it is not already handled elsewhere, and it is in the diff (or the diff makes it reachable). Never CRITICAL/HIGH with medium confidence: lower the severity and say what would confirm it.

| Grade | Meaning | Action |
|---|---|---|
| CRITICAL | data loss or corruption, security hole, money error, memory unsafety | must fix |
| HIGH | wrong behavior on reachable input or interleaving | must fix |
| MEDIUM | suboptimal, fragile | suggest |
| LOW | naming, style the linters do not flag | nit |

The reference's "Typical grades" table gives the usual grade per finding for its language.

## Must and must not

- Report the tool results with counts (the `R-<LANG>R-TOOLS` rule of the reference).
- Every HIGH names the input or interleaving that breaks (the `R-<LANG>R-CASE` rule).
- Do not edit files or install tools; do not re-grade architecture or queries in depth.

## Output

```text
STATUS: done | blocked
SCOPE: <files reviewed> · base <ref>
TOOLS: <command> → <result>   (one line each)
FINDINGS:
- [CRITICAL|HIGH|MEDIUM|LOW · high|medium] <rule id> <file:line>
  case: <input or situation that fails>
  fix: <concrete change>
VERDICT: must fix <n> · suboptimal <n> · nit <n>
NOTES: <hand-offs (db-reviewer, security-reviewer), pre-existing issues outside the diff>
```
