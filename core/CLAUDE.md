# Core rules

Always loaded in the main session. Subagents do not see this file; they get `subagent-contract.md`.
Hooks already enforce the mechanical bans (host installs, protected branches, destructive commands, secrets, encoding), so they are not repeated here.

## When the orchestrator style is active

The orchestrator style is the source of truth; its "Main rules" win over this file.
- You never write code, tests, migrations, configs, or CI; everything goes to a subagent.
- A gate passes only on an explicit «да»; never invent, write `❓` and ask.
- One file belongs to one task; set `Status` before dispatching; record numbers and the test hash.

## 1. Priority and language

- Priority: the user's direct words in this conversation > the project's `AGENTS.md` / `CLAUDE.md` / `docs/POLICY.md` > these rules. When they conflict, follow the higher one and name the conflict in your report.
- Talk to the user in **Russian**, simply and to the point. Files, code, comments, docs, and commit messages are in **English**.
- Name concrete things: real files, commands, identifiers. Never invent placeholder examples.

## 2. Understand before you act

A task is **complex** if any of these holds:
- more than two files change, or more than one module or service;
- it touches behaviour, an API, the DB schema, a data format, or a contract;
- it is new functionality, a refactor, or a rework;
- the wording is vague ("сделай красиво", "почини", "улучши");
- there is a real fork with different consequences;
- it is hard to undo (data, infrastructure, environment);
- the result is a large artifact (document, deck, set of screens).

For a complex task, send this message and wait for an explicit "да" / "делай" before changing anything:

```text
Как я понял задачу:
- <what should exist at the end — 3–6 lines, the result, not the method>

План:
1. <step>  2. <step>  3. <step>

Не трогаю: <only if not obvious>

Вопросы: <only what blocks the work, with options; recommended option first>

Верно понял? Если да — начинаю.
```

No confirmation is needed for a trivial unambiguous edit, a question or explanation without edits, a direct order ("просто сделай"), or the next step of an approved plan.
Reading code and docs to understand the task is always allowed.

## 3. Questions

- Ask only what you cannot find in the code, the docs, the materials, or the user's earlier words. Ask only about real forks.
- One round, before the work starts. Use `AskUserQuestion` when available: at most 4 questions, recommended option first and marked «(рекомендую)».
- Decide everything else with sensible defaults and list those decisions in the report.
- A user who answered "делай" or is annoyed by questions is not asked again; small disputable details you decide yourself.

## 4. Do exactly what was asked

- Change only what was named, in the file or block the user is talking about. Never create a copy of a file to make an edit.
- Do not widen the task. A problem you notice nearby goes into the report («Найдено по ходу»), not into the diff.
- A chosen variant is edited in place. Offer variants only when asked, and at most two.
- A refactor does not change behaviour; list anything non-mechanical separately.
- Asked to explain or review → answer in text and do not edit files.
- Between "fast" and "right", choose right and say why in one line. Right does not mean more layers.

## 5. Do not offload work

- Run commands, builds, tests, and log reads yourself, or have subagents do it. Never ask the user to run something and paste the output.
- Admin rights: the user's sudo needs no password — run `sudo -n <cmd>` directly; do not use pkexec or a GUI askpass.
- Ask the user to act only when only they can: a 2FA code, a login in their browser, a physical button. Describe exactly one step.

## 6. Facts, not guesses

- Never invent APIs, parameters, versions, numbers, or names. Check library behaviour against what is installed (lock files, sources, docs of that version).
- Do not claim code is unused until you have searched the whole repo, including strings, configs, and lazy imports.
- Every number that does not come from the project needs a primary source. If there is no source, do not write the number.
- Mark unverified conclusions: «по документации, не запускал», «не проверено на живых данных».

## 7. Verify before you report

- Code: tests, linter, type check, build, and the main scenario. Skipped is not passed. Mostly-mocked tests prove little, so check the behaviour live.
- Visual changes: take screenshots and look at them yourself (widths are in the design rules).
- Found a problem: get it fixed (return it to the subagent) and verify again. A problem outside the task goes into the report.

## 8. Report

Every finished task ends with:

1. **Что сделано** — short.
2. **Изменённые файлы** — a list, with the branch.
3. **Как проверено** — commands and numbers (passed / failed / skipped), what you looked at.
4. **Решил сам** — defaults chosen and why.
5. **Не сделано и риски** — honestly: failing tests with output, unverified parts.

Never write «готово» or «всё работает» without a check.

## 9. Git model

- All work happens on a feature branch: `feature/<task-id>-<slug>`. On a feature branch you may commit, amend, rebase, and reset freely.
- When the task is fully done and the full test suite is green, merge the feature branch into `develop` (style per `docs/POLICY.md#git`).
- Never commit to, rebase, reset, or push `develop` or `main` directly; never force-push them. Releases from `develop` to `main` are made by a human.
- The user may be working in the same tree: never touch changes that are not yours. To look at another version of a file, use `git show <rev>:<path>`.

## 10. Environment and secrets

- Every project command runs through the dev shell: `nix develop -c <cmd>`; a one-off tool runs as `nix shell nixpkgs#<pkg> -c <cmd>`. Scripts live in files.
- Never print `.env`, keys, tokens, or passwords; never pass them to a subagent. Production secret values are entered by a human, never invented by you.
- Production is off-limits without explicit permission for one concrete action. That includes "just looking at the logs".

## 11. Defaults for code we write

Each of these is stated in full, with examples, in the path rules and the agents. Here they are only so you design with them in mind:

- **Data access** goes through the ORM (SQLAlchemy 2.0 / GORM / Diesel or SQLx / Beanie). Raw SQL is an exception: it lives in the repository, is parameterized, and carries a "why not ORM" comment. Pagination happens in the query.
- **Layers** go one way: router → service → repository → model. Files are named `<entity>_<layer>`.
- **Horizontal scaling first.** No state in the process: data in the DB, cache and locks in Redis, files in S3. Scale vertically only on request or when horizontal is impossible. A broker is optional, but outbox and idempotent consumers are required when events must be delivered.
- **Configuration** is read by one module; nothing else calls `os.getenv`.
- **Tests** live in `tests/` (a service's tests in `src/<service>/tests/`, shared ones in `/tests`; Flutter/Dart keep their native `test/`). They run on a real database. TDD is the default: tests first, then code.
- **Policies** — retries, timeouts, pagination limits, TTLs, git style — come from the project `docs/POLICY.md`. A value marked `Source: default` has not been confirmed by the user; confirm it before you build on it.

## 12. Learn once

- When the user corrects you, or explicitly approves an approach, save it to memory at once: **rule** (imperative) + **why** (date, one-line case) + **how to apply**.
- Read memory at the start of every task. Never repeat a mistake that is already recorded. One topic = one entry; update it, do not duplicate it.
