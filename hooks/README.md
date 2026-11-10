# BR hooks

Deterministic guards for the `br` flavour. Zero tokens until they fire; a denial reaches the model as a one-line reason prefixed `[br-hook]` that says what to do instead.

Python standard library only. Run through the pinned wrapper `br-hook <entry>` (built in `nix/hook.nix`), which `hooks.json` references as `@BR_HOOK@ <entry>`.

## Entry points

Four entry points instead of one script per rule: every hook call is a process start (~60 ms), and Bash/Edit run constantly.

| Entry | Event · matcher | What it does |
|---|---|---|
| `guard_bash` | PreToolUse · `Bash` | host installs; git rules; destructive commands; secret output; test edits through the shell |
| `guard_write` | PreToolUse · `Edit\|Write\|MultiEdit\|NotebookEdit` | test boundary by `agent_type`; linter/formatter configs closed to executors; task write sets from `.plan/PLAN.md`; orchestrator writes only docs and the plan |
| `guard_read` | PreToolUse · `Read\|Grep` | `.env*` (not `.example`), private keys, age/sops key files |
| `check_written` | PostToolUse · `Edit\|Write\|MultiEdit` | strips BOM and fixes mixed line endings silently; blocks non-UTF-8 and written secrets; compose/Dockerfile advice as context |

Code: `brhooks/common.py` (event, decisions, PLAN.md parser), `bash_checks.py`, `write_checks.py`, `post_checks.py`.

## Who may write what

| Writer | Without `.plan/` | With `.plan/` (orchestrated project) |
|---|---|---|
| main thread (orchestrator) | anything | `docs/**`, `.plan/**`, `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `.claude/rules/**` |
| `test-writer` | only test paths | only `Tests (test-writer)` of tasks with status `red` (the union when several tasks are `red`) |
| `coder` | anything except test paths | only `Writes (exclusive)` of tasks with status `green` |
| `python-coder`, `go-coder`, `ts-coder`, `rust-coder` | same as `coder` | same as `coder` (step `green`) |
| `deploy-engineer` | anything except test paths | only `Writes (exclusive)` of tasks with status `green`, like `coder` |
| `ci-engineer` | anything except test paths; may edit linter/formatter/type-check configs | only `Writes (exclusive)` of tasks with status `green`; configs only if inside that write set |
| `refactorer` | anything except test paths | only `Writes (exclusive)` of tasks with status `refactor` |
| `log-writer` | anything except test paths | only `Writes (exclusive)` of tasks with status `log`; never test files |
| `build-fixer` | anything except test paths | same, not limited by the plan |
| `presenter` | `docs/slides/**`, `.plan/PLAN.html` | same |
| `deploy-error-reader`, `log-collector`, `web-researcher`, `stand-operator`, `janitor` | nothing (no Write/Edit) | nothing |
| any other subagent | nothing outside the project (temp dirs are fine) | same |

Status in a task card is read tolerantly: backticks and trailing words are ignored (`` `red` ``, `red (round 2)` both mean `red`).

A path listed explicitly in `Writes (exclusive)` of a `green` task is writable by its executor even when it matches a test-path pattern (for example `e2e/dev-stand.yml`, `scripts/seed/tests/x.py`); test files that are not listed stay forbidden.

Executors (`coder`, language coders, `deploy-engineer`, `ci-engineer`, `refactorer`, `test-writer`) may also write under `/tmp/` and the session scratchpad.

### Bash writes follow the write sets

For subagents, the targets of `>` / `>>` redirections, `tee`, `sed -i` / `perl -i`, `cp` / `mv` / `install` / `ln` destinations (also `-t DIR`, `-tDIR`, `--target-directory=DIR`; `mv` also its sources, `ln` the link name), `touch`, `truncate`, `dd of=` and `cat > f <<EOF` inside the project are checked with exactly the rules of Write/Edit (readers write nothing; test-writer only the Tests of `red` tasks, and never production code even without a plan; executors their Writes, the explicit-write rule and the test and config boundaries). The denial names the target and the rule. Heredoc bodies are data. Redirections are found glued to a word or in another form (`echo x>f`, `x>>f`, `x>|f`, `2>f`, `&>f`, `>&f`, `cat <<EOF>f`); `>/dev/null`, `2>&1` and a quoted `>` are not writes. Relative targets are resolved against earlier `cd`s of the same command line (`cd dir && echo x > f` writes `dir/f`). Executors skip a target built from another `$VAR` or a substitution, but `~`, `$HOME` and `${HOME}` are expanded to the home directory (so they are refused as outside the project); readers fail closed: such a target, or any target outside `/tmp`, `/var/tmp` and the scratchpad, is denied. Executors write outside the project only to `/tmp/`, `/var/tmp/` and the scratchpad, as with Write/Edit (any other outside target is denied). The main session is not checked, and agents in a project without a plan keep only the always-on test boundary and the outside-the-project rule.

### Read-only agents and Bash

`deploy-error-reader` (analyst) and `log-collector` (fetches raw logs) share one rule set. Besides having no Write/Edit, their Bash is an **allowlist**: a command runs only if every resolved command word is one of
- a read/status subcommand of a deploy CLI: `gh auth status`, `gh run list|view`, `railway whoami|logs`, `gcloud auth list`, `gcloud logging read`, `doctl account get`, `doctl apps logs`, `yc logging read`, `wrangler whoami|tail`, `cf auth whoami|list`, `cf docs search`, `cf cli search`, `cf schema`, `cf workers list|get|deployments|versions`, `docker compose ps|logs|ls` (also `docker-compose`), `docker logs`, `docker ps`, `docker container|volume|network ls`, `docker version`;
- a stdin filter on a pipe, `head tail grep jq wc sort uniq cut tr`, with no file operand (AC23), or a shell helper `date echo printf test [ true sleep` and `ss -ltn` (listing flags only).

**Readers' Bash is CLI-only (AC23).** Files are read with Read, Grep and Glob, which reach only the project, `/tmp`, `/var/tmp`, the scratchpad and `/nix/store`. In Bash, `cat sed awk ls stat file find rg cd git tee cp mv touch` are denied for the four readers (the janitor keeps `git ls-files` and `git status` inside its own gate), and so is a filter with a file operand, `grep -r|-f`, `jq -f|--arg…file` or a jq program that reads `env`. A lowercase shell variable assigned alone (`out=$(docker compose -p x ps)`) is allowed, which keeps the `stand-operator` health-wait loop (`until out=$(…); [ … ] && ! printf … | grep -Eq …; do sleep 2; done`, inside `timeout … nix shell nixpkgs#docker -c sh -c '…'`) working. Main session and executors are unaffected.

Everything else (`rm`, `git push`, `podman`, `kubectl`, `terraform`, `curl`, `python3`, unknown binaries, `gh run rerun`, `railway up`, `docker compose up|down`, …) is denied. The gate sees through the same wrappers as the Nix-only check: `nix shell|run … -c`, `bash -lc '…'`, `$(…)`, backticks, `xargs`, `eval`, `find -exec`, pipes and `&&`/`;` chains. A flag before the subcommand must be a known global flag (`gh -R owner/repo run list`, `docker compose -f x.yml logs`, `docker --context stand logs`); an unknown one is refused. A command word built from a variable or substitution, or a path outside the system bin directories, is refused. Every denial quotes the command or names the target.

**The allowlist runs nothing and writes nothing (AC20).** `sed` with an `e`, `w` or `W` command, an `s///e` or `s///w` flag, or `-f` is denied (the script is walked command by command); `git -c`, `--config-env`, `--exec-path`, `-p`/`--paginate`, `--ext-diff` and `--textconv` are denied; `sort --compress-program`, `awk -f|-i|--include` and `less` are denied; an environment assignment in front of a command (also behind `env`, `nix shell -c`, `bash -c`) is denied except `TZ`, `LC_*`, `NO_COLOR`. A reader cannot name a CLI credential file (`~/.config/gh/`, `~/.config/gcloud/`, `~/.config/yandex-cloud/`, `~/.railway/`, `~/.config/doctl/`, `~/.wrangler/`, `~/.config/.wrangler/`, `~/.docker/config.json`, `~/.kube/config`, also as `$HOME/…` or the absolute home path): this check (`check_reader_inputs`) covers `stand-operator` and `janitor` too. `gh auth status --show-token` is denied in every spelling (`-R` first, `--show-token=true`, `-t`) and the secret-printing commands are matched after the global flags (`yc --profile x iam create-token`). The generic Docker-volume check looks past `docker --context x …` flags. Readers (also `stand-operator` and `janitor`) may not `cd` to `~`, `$HOME`, a bare `cd`, `cd -` or any directory outside the project and the temp dirs, so `cd ~/.config && cat gh/hosts.yml` cannot reach a credential file.

### Secrets, stand-operator, janitor, infrastructure changes

- **No secrets for readers (AC15).** For `deploy-error-reader`, `log-collector`, `stand-operator` and `janitor`, commands that print a secret are denied: `yc config list`, `yc iam create-token`, `gh auth status --show-token`, `gh auth token`, `railway variable list`, `doctl auth token`, `doctl databases connection`, `printenv`, bare `env`. The reader allowlist follows the R marks of `skills/cli-*`: `yc iam whoami`, `yc config get folder-id|cloud-id`, `yc logging group list`, `railway status`, `railway deployment list`, `doctl apps list|get|list-deployments|get-deployment`, `gcloud run services logs read`, `docker version` (`yc config list` is no longer allowed).
- **`stand-operator` (AC16).** No Write/Edit. Bash = reader commands plus `docker compose -p NAME [-f FILE] up -d|up --wait|restart SVC|down` and `nix run .#TARGET` / `.#TARGET-down` for the targets named in `.plan/PLAN.md`. Every compose command needs `-p`; `down` never takes the volumes or `--rmi` flags; `docker system prune`, volume and container removal are denied.
- **`janitor` (AC17).** No Write/Edit. Bash = reader commands plus `rm FILE...` (explicit, untracked, non-recursive, no globs; tracked files per `git ls-files` are refused), `docker rm|container rm|volume rm NAME...` by explicit name, `docker compose -p NAME down`. `find -delete`, `git clean`, `git rm` and anything outside the project (except docker) are denied. The generic Docker-volume check yields to the janitor for an explicit volume name.
- **Hidden infrastructure changes (AC19).** The AC18 gate resolves package launchers (`npx`, `bunx`, `pnpm dlx|exec`, `npm exec`, `yarn dlx`, `uvx`) and skips global flags with a value before the subcommand (`gcloud --project p run deploy`, `doctl --context x apps create`, `wrangler -c f deploy`, `railway -s s up`); an unknown flag, a nesting or a parse failure is a denial for subagents; `doctl apps create-deployment` counts as a change.
- **Stand and janitor gates (AC22).** `stand-operator` accepts compose `-f`, `--project-directory` and `--env-file` only inside the project and `nix run .#TARGET` only for targets on `- **Stand:**` lines of the plan; docker `-H`, `--host`, `--context`, `DOCKER_HOST` and `DOCKER_CONTEXT` are denied for both agents; the janitor may remove a docker network by explicit name; the tracked-file check fails closed (a git error counts as tracked); `cd` tracking gives up on unknown options or nested scripts, and then `rm` is denied.
- **Infrastructure changes (AC18, `infra_checks.py`).** Runs first for every subagent, including `deploy-engineer` and `ci-engineer`, also inside `nix shell`, `bash -c`, `xargs`, `eval`, chains: `tofu|terraform apply|destroy`, `railway up|redeploy|down`, `gh run rerun`, `gh workflow run`, `wrangler deploy|rollback|versions deploy`, `gcloud run deploy`, `gcloud run services delete`, `doctl apps create|update|delete`. The denial tells the agent to prepare the exact command for the user (or the orchestrator after the user's «да»). Plans and dry runs (`tofu plan`, `wrangler deploy --dry-run`) and the main session are not limited.

A test path is any path with a `test`, `tests`, `__tests__`, `e2e`, `integration_test`, or `testdata` directory segment, or a test file name: `test_*.py`, `*_test.py`, `conftest.py`, `*_test.go`, `*_test.dart`, `*.test.{js,jsx,ts,tsx}`, `*.spec.{js,jsx,ts,tsx}`. Our layout uses `tests/` (Flutter/Dart: `test/`); the rest keeps the boundary in existing projects with other conventions.

Parallel executors of the same kind get the union of their tasks' write sets; R-PLAN-WRITESET keeps those disjoint, and the orchestrator's sha256 check of test files is the backstop.

Executors (`coder`, `refactorer`, `build-fixer`, `test-writer`) never edit linter, formatter, type-checker, or coverage configs (`ruff.toml`, `eslint.config.*`, `.golangci.yml`, `mypy.ini`, `.coveragerc`, …). `[tool.ruff]` inside `pyproject.toml` is not caught; review is the backstop.

## Git

Free on any branch except `main`, `master`, `develop`.

- On develop/main: no commit, add, reset, rebase, cherry-pick, revert, am, apply, pull (except `--ff-only`), merge.
- The one write to develop: `git merge [--no-ff] feature/…` (or `hotfix/…`), plus `merge --abort`.
- Never: push develop/main (including `HEAD` while on them, `--all`, `--mirror`, `--tags`), delete or force-move them, `--no-verify`, `git clean -x`.

## Nix only

`guard_bash` denies a bare interpreter (`python3`, `node`, `ruby`, `perl`, `ipython`, `tsx`, … and launchers `npx`, `bunx`, `uvx`, `uv run`, `pnpm dlx|exec`, `poetry run`, `npm exec`, `yarn dlx`, `pipx run`, `bundle exec`, `conda run`, …) unless the command runs inside `nix develop … -c`, `nix shell … -c`, `nix run`, `nix-shell --run`, or the interpreter is a `/nix/store` path. The check looks through quotes, `bash -c '…'` (also `-lc`, `-o pipefail -c`), `$(…)`, backticks, `( )`, `{ }`, `if/then/do`, wrappers with options (`sudo -u x`, `env -S`, `timeout 5`, `nice -n`), `xargs`, `find -exec`, redirections, and skips comments and the heredoc bodies of `cat`/`tee`/`git commit -F` (the body of `bash <<EOF`, `cat <<EOF | bash`, `source /dev/stdin <<EOF` and the text of `bash <<< '…'` is checked as a script; `| tee` and `| grep` leave it as data). A command word that is a bare variable or substitution that may hold an interpreter (`p=python3; $p x`, `${PYTHON:-python3} x`, `$(which python3) x`) is denied outside Nix; `$EDITOR f` and `$VAR/path` are not. `eval` is checked through its argument. `export`/`declare`/`local`/`readonly`/`typeset` assignments are tracked like plain ones. Nesting deeper than 8 levels and commands longer than 200 000 characters are denied, and an exception inside any check of `guard_bash` becomes a deny, not a skipped check. `perl -pi -e` one-liners are denied outside Nix like any other `perl`.

It also denies running anything from an agent skills directory (`~/.claude/skills`, `~/.codex/skills`, `~/.gemini/config/skills`, `/nix/store/…/skills`, `/nix/store/*-skills`, `$CLAUDE_SKILL_DIR`; paths are normalised: `//`, `/./`, `..`, `$HOME`, other users' homes), directly or as an argument of an interpreter, shell, `source`, after `cd|pushd <skills dir>` (also reached by a chain of relative `cd`s) in the same command line (`./x`, `source x`, a relative script for an interpreter), or piped into a shell or interpreter (`cat skill.sh | bash`), even inside a Nix wrapper. Use the skill's packaged `/nix/store/…/bin/<name>` command named in its SKILL.md. Reading skill files (`cat`, `grep`, `ls`) is not affected.

Known limits: `cd` into a skills directory in one Bash call and `./x` in another; copying a script out and running it; `cat` of a copy of a script into a shell; symlinks into a skills directory; paths built from variables; `cd` through a variable or `cd -` (the directory becomes unknown, so the taint is dropped); `echo '…' | bash` and other pipes that are not heredocs; a variable that holds an interpreter but is neither assigned in the same command line nor named like one.

## Upstream ECC hooks

The br flavour installs **none** of the 27 upstream hooks. Every hook is a process start on every matching tool call, and several inject text into the context.

| Upstream hook | Decision | Why |
|---|---|---|
| `pre:config-protection` | ported into `guard_write` | useful; narrowed to executors |
| `pre:bash:dispatcher` (quality, tmux, push, GateGuard) | dropped | git/push rules are in `guard_bash`; the rest is upstream workflow |
| `pre:edit-write:gateguard-fact-force`, `pre:powershell:*` | dropped | forces questions on first edit: tokens on every file; PowerShell is not used |
| `pre:write:doc-file-warning` | dropped | docs-kit defines the docs layout; `docs.md` rule covers it |
| `pre:edit-write:suggest-compact`, `pre:compact` | dropped | adds context; the plan file is the durable state |
| `pre:observe:continuous-learning`, `stop:evaluate-session` | dropped | logs every tool call; "learn once" lives in core CLAUDE.md |
| `pre:governance-capture` | dropped | off upstream by default; secrets are covered by `guard_*` and `check_written` |
| `pre:mcp-health-check`, `post:mcp-health-check` | dropped | subagents have no MCP; main session handles failures itself |
| `pre/prompt/stop:hookify-runtime` | dropped | no Hookify rules in Alexey's projects |
| `session:start`, `stop:session-end`, `session:end:marker` | dropped | loads previous context into every session = tokens |
| `session-start/stop:plan-canvas-*` | dropped | Plan Canvas is not used; `.plan/` replaces it |
| `post:dispatcher:sync/async` | dropped | upstream formatters/console.log checks; executors run linters through `nix develop -c` |
| `stop:format-typecheck`, `stop:check-console-log` | dropped | JS-only, runs Biome/Prettier from the host |
| `stop:cost-tracker` | dropped for now | stage 10 measures tokens with `/context` and transcripts; revisit if needed |
| `stop:desktop-notify` | dropped | macOS/WSL only |
| `post:skill:track` | dropped | Skill tool is off in subagents |

## Limits (by design)

- Bash checks read the command text. They catch mistakes, not a determined bypass (a script that writes into `tests/` passes). Backstops: sha256 of test files in PLAN evidence, code review.
- A hook that crashes exits 1: Claude Code shows the error and the tool call proceeds (fail-open). The tests below are what keeps them correct.
- An unknown or malformed entry name passed to `br-hook` exits 2 (fail-closed for PreToolUse); runtime errors inside a hook still exit 1 (fail-open) as before.

## Tests

```bash
cd hooks && python3 -m unittest discover -s test -t test
```
