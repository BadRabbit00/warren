# Changelog

## 0.3.0-no-nix — unreleased (branch `no-nix`)

The same warren without Nix, for machines that do not use it.

- Install with `python tools/install.py` (Windows, macOS, Linux; Python 3.11+, stdlib only): builds with
  `tools/build.py` (was `nix/payload.py`), lays out `~/.claude`, `~/.codex`, `~/.gemini/config`, merges
  `settings.json` keeping the user's keys and hooks; `--dry-run`, `--dest`, `--check`. `requirements.md`
  lists what to install, `install_guide.md` the script and the manual way.
- Hooks run as `"<python>" -I -B "~/.claude/br/hooks/<entry>.py"`; no `br-hook` wrapper. The Nix-first rule
  is gone (bare tools and interpreters run); package installs are refused for subagents and allowed for
  the main session; no hook message mentions Nix.
- Removed: `flake.nix`, `nix/`, the agents `nix-architect`, `nix-engineer`, `nix-reviewer`,
  `nix-build-resolver`, `nix-test-runner`, the skills `nix-debugging`, `nix-flake-patterns`,
  `nix-packaging`, `nix-testing`, `nix-toolkit`, `nixos-module-patterns`, `project-flake`, the 14 `nix-*`
  commands and `rules/nix.md`.
- Every agent, skill, command, rule and workflow runs commands directly through the project's own
  toolchain (`uv run`, `npm`, `go`, `cargo`); a missing CLI stops with "install needed (requirements.md)".
  Images are multi-stage Dockerfiles to a distroless or slim base. Renamed rules: R-DEPLOY-NIX-JOBS →
  R-DEPLOY-MULTISTAGE, R-PYS-NIX → R-PYS-ENV.
- The validator rejects Nix wording and nix-named files in everything agents read.

## 0.3.0 — unreleased

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
