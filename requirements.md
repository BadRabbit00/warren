# Requirements

What warren needs on the machine. This file says **what** to install and why, not how: ask Claude
to install everything listed here for your OS (macOS, Linux, Windows with WSL, native Windows), then
run `python3 tools/install.py` (see [install_guide.md](install_guide.md)).

Every tool must be on `PATH`. Only Python has a minimum version; for the rest any current release works.

## Required

| Tool | Version | Why |
|---|---|---|
| Claude Code | current | the CLI warren configures (`~/.claude`) |
| Python | 3.11+ (the tests use `tomllib`), started by the command `python3` on every OS, Windows included | `tools/install.py`, `tools/build.py`, the validator and every hook (each hook runs as `python3`); standard library only, no packages |
| Git | — | hooks read the current branch; agents commit on feature branches; janitor checks tracked files |
| A POSIX shell | — | Claude Code's Bash tool; on native Windows this is Git Bash (comes with Git for Windows) |

## Used by agents and skills (install what your projects need)

| Tool | Used by | Why |
|---|---|---|
| GitHub CLI `gh` | `ci-engineer`, `log-collector`, `deploy-error-reader`, `/br-ci`, `/br-diagnose`, skill `cli-gh` | read CI runs and failed logs, PRs |
| Docker Engine (or Docker Desktop) with Compose v2 (`docker compose`) | `deploy-engineer`, `stand-operator`, `janitor`, `/br-deploy`, `/br-e2e`, skills `cli-docker`, `docker-patterns`, `deploy-variants` | local stands, image builds, smoke tests |
| `jq` | readers (`log-collector`, `deploy-error-reader`) | filter JSON output of CLIs in pipes |
| OpenTofu `tofu` | `deploy-engineer`, `/br-deploy`, skill `iac` | infrastructure plans (apply is always the user's step) |
| `actionlint` | `ci-engineer`, `/br-ci` | lint GitHub Actions workflows |
| `zizmor` | `ci-engineer`, `/br-ci` | security lint of GitHub Actions workflows |
| `trivy` | `ci-engineer`, skill `ci-github-actions` | image and dependency scans |
| `sops` and `age` | skill `sops` | encrypted secrets in the repo |

## Cloud CLIs (only for the clouds you use)

| Tool | Cloud | Skill |
|---|---|---|
| `wrangler` (Node.js package; `npx wrangler` also works) | Cloudflare | `cli-cloudflare`, `cloud-cloudflare` |
| `railway` | Railway (also the dev stand) | `cli-railway`, `cloud-railway` |
| `gcloud` (Google Cloud SDK) | Google Cloud | `cli-gcloud`, `cloud-gcp` |
| `doctl` | DigitalOcean | `cli-doctl`, `cloud-digitalocean` |
| `yc` | Yandex Cloud | `cli-yc`, `cloud-yandex` |

You log each CLI in yourself (`gh auth login`, `wrangler login`, `railway login`, `gcloud auth login`, `doctl auth init`, `yc init`). Agents check the login first and stop with "login needed" when it is missing; they never log in for you.

## Language toolchains (per project)

Agents run a project's own commands — the ones its README, Makefile or manifest names. Install the toolchain of each project you work on:

| Stack | Tools | Used by |
|---|---|---|
| Python | `uv` (`uv run pytest`, `uv run ruff`, `uv run mypy`) | `python-coder`, `python-reviewer`, skill `python-service` |
| TypeScript / React | Node.js with npm | `ts-coder`, `ts-react-reviewer`, `wrangler` via npx |
| Go | Go (`golangci-lint` for reviews) | `go-coder`, `go-reviewer` |
| Rust | rustup with `cargo` and `clippy` | `rust-coder`, `rust-reviewer` |
| Flutter / Dart | Flutter SDK | `flutter-dart-reviewer` |
| End-to-end tests | Playwright with its browsers (`npx playwright install`) | `/br-e2e`, `ui-verifier`, skill `e2e-testing` |

## Optional: second opinions

| Tool | Used by |
|---|---|
| Codex CLI | `/ask-astra`, `/write-astra`; warren also exports its agents to `~/.codex` |
| Antigravity CLI `agy` | `/ask-agy`, `/write-agy`, `/ask-argon`, `/write-argon`; agents exported to `~/.gemini/config` |

These commands call wrapper scripts (`ask-astra`, `write-astra`, …) that are not part of warren; without them the commands report that the wrapper is missing.

## Not needed

Nix is not used on this branch. Agents never install anything: the hooks block package installs for subagents, and the main session installs only what this file lists, when you ask it to.
