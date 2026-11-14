# Changelog

## 0.3.0 — unreleased

- Agent architecture: skill `agent-architecture` from Alexey's November 2026 business-agent base and eight
  harness maps — nine layers, thirteen mechanisms (simple / smart / pitfall), 2026 shifts, take-or-write, three agent
  types, always / never rules, build order, and layer guides for frameworks, knowledge base, memory, tools and skills,
  model gateway, protection, channels and handoff, observation and evaluation (each option with good for / bad for,
  clouds, task table), the rule of two, Kazakhstan data rules and supply-chain red flags. `architect-critic` preloads
  it, checks every agent's rule-of-two profile and the `agent/<layer>` lines (rule `R-ARCH-AGENT`); the orchestrator
  loads it at stage 2 when the system has an AI agent or LLM calls.
- Metrics on demand: agent `metrics-writer` (status `metrics`) adds OpenTelemetry metrics through one connector
  module per service and `/health` + `/ready`; skill `metrics` (Python, Go, Rust templates, semconv names,
  cardinality). Agent `observability-engineer` writes Prometheus, alert and recording rules, Alertmanager and
  Grafana provisioning as checked files (skill `observability-infra`); deployment goes through `/br-deploy`.
- Debugging: workflow `/br-debug` — `bug-reproducer` builds a reproduction package, `repro-runner` (Haiku) runs it
  N times, `root-cause-analyst` (Opus) finds the cause with file:line; the result names the failing test to write.
  Skill `debugging` (repro exit contract shared with `git bisect run`, batch debuggers per language).
- `optimizer` measures with skill `profiling` (py-spy, Go pprof, cargo-flamegraph/perf), outputs in temp dirs only.
- Logging as its own step: agent `log-writer` adds logging after green (status `log`, `/br-wave` steps `log` and
  `fix-log`), never touching behaviour or tests; skill `logging` holds the levels (DEBUG, INFO, WARNING, ERROR,
  PANIC), the fields of every line (UTC time, file:line, module, function with class, request and trace ids),
  masking (secrets always, personal data outside DEBUG) and templates for structlog, slog, tracing, pino in the
  browser and OpenTelemetry; `/br-review` gets a logging pass. Hooks know the `log` status.
- Janitor lists the project (`ls`, `find` without exec/delete, `stat`, `readlink`, `du`) inside the root and reads
  `docker volume inspect`; `docker inspect` stays refused (it prints the container Env).
- Saved workflows in `workflows/`, installed to `$out/claude/workflows/`, every agent by `agentType` (pins,
  contract, hooks apply), at most 15 agents per run:
  - `/br-wave` runs one wave from a manifest in the plan (red, green, refactor, fix-tests, fix-code, check items,
    parts per agent, a `test-runner` per task with the tests-hash guard and an empty-diff guard);
  - `/br-review` is the checkpoint review (deep and broad passes, db and migrations-only reviews, refuters for
    security must-fix, `fix_items` for the next wave);
  - `/br-research`, `/br-diagnose`, `/br-ci`, `/br-deploy`, `/br-e2e`, `/br-janitor` for research, failure
    diagnosis, CI pipelines, deployment, end-to-end tests and cleanup. They never push, deploy or apply.
  The earlier `/br-red` and `/br-green` (never released) are replaced by `/br-wave`.
- Eleven agents: `python-coder`, `go-coder`, `ts-coder`, `rust-coder`, `deploy-engineer`, `ci-engineer`,
  `stand-operator`, `log-collector`, `deploy-error-reader`, `web-researcher`, `janitor`.
- Skills: `python-service`, `frontend-data-layer`, `user-flows`, `iac`, `ci-github-actions`, `registry-dockerhub-ghcr`,
  `cloud-*` for Cloudflare, Railway, GCP, DigitalOcean and Yandex Cloud (with the official Cloudflare skills
  vendored under Apache-2.0), and `cli-*` for gh, docker, wrangler, railway, doctl, gcloud and yc with a login
  check first and read / effect / mutating marks per command.
- Hooks: the reader gate is an allowlist that resolves wrappers; Bash writes are scoped like Write;
  secret-printing commands are denied for readers; `stand-operator` and `janitor` have their own gates;
  infrastructure-changing commands (`tofu`/`terraform` apply and destroy, `railway up`/`redeploy`/`down`,
  `wrangler deploy`/`rollback`, `gcloud run deploy`, `doctl apps create`/`update`/`delete`, `gh run rerun`,
  `gh workflow run`) are never run by a subagent; plans and dry runs stay allowed.
- The orchestrator style opens and closes with the main rules, asks questions as popups, lists the workflow
  catalog, manifests, parts and checkpoints; `templates/PLAN.md` gains Dispatch, Parts, Checkpoint and Manifest.
- The payload checks that every workflow starts with `export const meta`; the validator rejects `agent(` calls
  without an existing `agentType` and calls the workflow runtime forbids.

## 0.2.0 — 2026-11-09

- Codex CLI and Antigravity CLI (`agy`) exports in the payload: `$out/codex/{agents/*.toml,agents.toml,prompts,skills,AGENTS.md}`
  and `$out/agy/{agents/*.md,AGENTS.md}`, generated from the same agents, commands, skills and `core/CLAUDE.md`.
- `agent-models.json` carries `codex.model`, `codex.effort` and `agy.model` per agent; the validator requires them,
  checks the agy tier vocabulary, the codex effort, agent-name rules (charset, codex reserved keys), block-scalar
  descriptions and `'''` in agent bodies; the exporter re-parses every generated TOML file.
- No export of `tools`, `disallowedTools`, `maxTurns`, hooks or the orchestrator output style: the other CLIs have no
  equivalent. Codex roles get `sandbox_mode` read-only unless the agent keeps a write tool; agy agents get `inheritMcp: false`.

## 0.1.0 — 2026-11-06

First standalone release as **warren**. Until now this layer lived as the `badrabbit/` directory and the
`br` payload flavour inside a fork of [ECC](https://github.com/affaan-m/ecc).

- Repository root is the warren layer (internal prefix `br`): `agents/`, `rules/`, `skills/`, `commands/`, `core/`,
  `output-styles/`, `templates/`, `hooks/`, `tools/`.
- Nix: `packages.br-payload`, `packages.br-hook`, `lib.mk { pkgs }`; no Node in the build;
  the validator and the Python test suites run in `checkPhase`.
- Removed: the legacy ECC payload, `ecc-run` / `ecc-hook`, `/astra-review`, the allowlist,
  and every upstream agent, command, hook, rule and skill that the `br` payload flavour did not install.
- Kept from ECC: 22 reference skills (see README, "From ECC").
