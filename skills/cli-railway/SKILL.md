---
name: cli-railway
description: Use when you must read Railway state (who is logged in, deployments, build/deploy/HTTP logs, metrics) with the railway CLI, or hand off a deploy/redeploy/restart to deploy-engineer.
---

# railway: deployments and logs

Verified locally with railway 5.30.4 (`--help` of every command below). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (intended allowlist: `railway whoami`, `railway logs`, plus `railway status` and `railway deployment list`; the hook today allows only `whoami` and `logs`, the rest follows in T1). `E` = read-only, but only for `deploy-engineer` / `ci-engineer`. `M` = mutating, section 4.

## 1. Run

Always `nix shell nixpkgs#railway -c railway <args>`. Never a bare `railway`, never `brew install railway`, `npm i -g @railway/cli`, or an install script piped into a shell.
Pick the target with `-s <service> -e <environment> -p <project>` (or run inside a linked directory). An explicit `--project` needs `--environment` too (`status` help).

## 2. Login check FIRST

```
nix shell nixpkgs#railway -c railway whoami
```
- exit 0 = logged in. The output contains the account email: report only "logged in: yes", never the email.
- exit 1 with `Unauthorized. Please login with railway login` = stop. Do not try other commands.

Only `RAILWAY_TOKEN` (a project token) is set: `whoami` cannot answer (account-level query). Check with a project-scoped read instead:
`nix shell nixpkgs#railway -c railway status --json` (exit 0 = token works). Check that the variable is set with `test -n "$RAILWAY_TOKEN"`; never print it.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! nix shell nixpkgs#railway -c railway login --browserless`
(`--browserless` = device code; plain `railway login` opens a browser.) Token mode for CI: `RAILWAY_TOKEN` (project token: deploy, redeploy, logs) or `RAILWAY_API_TOKEN` (account token: `whoami`, `link`, `list`).

## 3. Read-only commands

### Why did the deploy fail (R)
```
# 1. which deployment: never guess the id
nix shell nixpkgs#railway -c railway deployment list -s <service> -e <env> --limit 5 --json
# 2. build log of that deployment, bounded
nix shell nixpkgs#railway -c railway logs --build <deploymentId> -s <service> -e <env> -n 200
# 3. runtime log of it, errors only
nix shell nixpkgs#railway -c railway logs --deployment <deploymentId> -s <service> -e <env> -n 100 --filter "@level:error"
```
- `-n/--lines N` (alias `--tail`) disables streaming; so do `--since` / `--until` (`30m`, `2h`, or ISO 8601). Without one of them `railway logs` streams forever.
- No id = the most recent successful deployment; `--latest` = the latest one even if it failed or is building.
- `--json` makes one JSON object per line (timestamp, message, attributes).

### HTTP, network, DNS logs (R)
```
nix shell nixpkgs#railway -c railway logs --http --status ">=400" -n 50 -s <service> -e <env>
nix shell nixpkgs#railway -c railway logs --network --status dropped -n 100 -s <service> -e <env>
nix shell nixpkgs#railway -c railway logs --dns --status failed -n 50 -s <service> -e <env>
```

### Project and deployment state (R)
```
nix shell nixpkgs#railway -c railway status --json                    # linked project; with -p also pass -e
nix shell nixpkgs#railway -c railway deployment list -s <service> --limit 10 --json
```

### Account-level and metrics (E)
```
nix shell nixpkgs#railway -c railway list --json                      # projects; needs an account token
nix shell nixpkgs#railway -c railway metrics -s <service> -e <env> --since 6h --json
```
`metrics --watch` is a TUI: never use it.

### Variables: names only (E)
`railway variable list` shows values. `--json` and `--kv` print raw values (help text). Never run them for a report. Not verified: a names-only mode; to learn which variable exists, read the code or the service settings in the dashboard.

### Schema of the API (E)
`railway api schema`, `railway api search <term>`, `railway api describe <name>` read the GraphQL schema. A query or mutation passed to `railway api '<document>'` can change state: only deploy-engineer, only after the user's «да».

## 4. Mutating commands (M): only deploy-engineer / ci-engineer, only after the user's «да» for this command (prod: «да» per command)

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
nix shell nixpkgs#railway -c railway up --detach --json -m "<message>" -s <service> -e <env>   # upload + deploy, does not wait for healthy
nix shell nixpkgs#railway -c railway up --ci -s <service> -e <env>                             # streams build logs only, then exits
nix shell nixpkgs#railway -c railway redeploy -s <service> -e <env> -y [--from-source]        # latest deployment again; --from-source pulls the newest commit/image
nix shell nixpkgs#railway -c railway restart -s <service> -e <env> -y                         # no rebuild
nix shell nixpkgs#railway -c railway down -s <service> -e <env> -y                            # removes the most recent deployment
nix shell nixpkgs#railway -c railway link -p <project> -e <env> -s <service>
nix shell nixpkgs#railway -c railway add --database <postgres|mysql|redis|mongo> [--json]   # pick one value
```
- `railway up` with no linked project and no `-y` may start an interactive sign-in or project creation; `--new` creates a new project. Always pass `-s -e` and run it linked.
- After `up --detach --json` poll `deployment list --json` and read `logs --json -n 100` (help "Automation notes").
- Rollback (docs, not run): the dashboard (service, Deployments, Rollback) restores an older deployment's image and variables. Via the API: GraphQL mutation `deploymentRollback` through `railway api` (returns a Boolean, not the new id; find the new one with `deployment list --json`). `railway down` is not a rollback.
- IaC `railway config plan` is a read; `railway config apply` and `migrate --apply` only after the user's «да» on the shown plan output, never in CI, and a destructive change needs the «да» on that named change (skills `iac`, `cloud-railway`). Docs: `config` exists in 5.30.4; not run here.
- Config as Code (separate from the above): `railway.json` (deprecated, files stop being read on 2026-12-01, docs). `volume` and `service` subcommands: `--help` first, not verified beyond the help list.

## 5. Patterns and anti-patterns

Bad: `railway logs` (streams until killed: blocks the agent)
Good: `railway logs -n 200` or `railway logs --since 1h` (both disable streaming)

Bad: `railway variable list --json`, `railway variable list --kv`, `railway variables`, `env`, `echo $RAILWAY_TOKEN`
Good: `test -n "$RAILWAY_TOKEN"`; report variable names from the code, never values

Bad: `railway whoami` with only a project token, then reporting "not logged in"
Good: `railway status --json`

Bad: report "logged in as alice@example.com"
Good: report "railway whoami: exit 0"

Bad: `railway logs -n 200` with no service in an unlinked directory (wrong or no target)
Good: `railway logs -n 200 -s <service> -e <env> -p <project>`

Bad: `railway up` as a first reaction to a failed deploy
Good: read `logs --build` first; deploy only when deploy-engineer was asked

Bad: `railway metrics --watch`
Good: `railway metrics --since 1h --json`

Bad: guess a deployment id from memory
Good: `railway deployment list --limit 5 --json`

## 6. Report shape (collectors)

Put in the report:
- source: `railway logs`, project, service, environment, deployment id, log type (`--build` / `--deployment` / `--http`)
- the exact command line and its exit code
- the log excerpt (at most ~40 lines) with line numbers (`| cat -n`) and its time range
- the deployment status from `deployment list --json`

Do not put in the report:
- the whole log, the account email, any variable value, tokens, secrets seen in a log (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
