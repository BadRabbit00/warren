---
name: cli-doctl
description: Use when you must read DigitalOcean state (App Platform deployments and logs, droplets, managed databases, registry tags) with the doctl CLI, or hand off a redeploy/spec update to deploy-engineer.
---

# doctl: DigitalOcean App Platform and resources

Verified locally with doctl 1.169.0 (`--help` of every command below). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (intended allowlist: `doctl account get`, `doctl apps logs`, plus `doctl apps list`, `get`, `list-deployments`, `get-deployment`; the hook today allows only `account get` and `apps logs`, the rest follows in T1). `E` = read-only, but only for `deploy-engineer` / `ci-engineer`. `M` = mutating, section 4.

## 1. Run

Always `nix shell nixpkgs#doctl -c doctl <args>`. Never a bare `doctl`, never `brew`, `snap`, or an install script piped into a shell.
Use `-o json` for machine-readable output and `--format Col1,Col2 --no-header` to cut columns.

## 2. Login check FIRST

```
nix shell nixpkgs#doctl -c doctl account get --format Status --no-header
```
- exit 0 and `active` = ok. `account get` also holds the email and UUID: do not put them in a report.
- exit 1 ("access token is required" or "401") = stop. Do not try other commands.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! nix shell nixpkgs#doctl -c doctl auth init`
(prompts for an API token created at https://cloud.digitalocean.com/account/api/tokens.)
CI or token mode: `DIGITALOCEAN_ACCESS_TOKEN` (applies to the `default` context only, never written to config; docs). Check that it is set with `test -n "$DIGITALOCEAN_ACCESS_TOKEN"`; never print it.

## 3. Read-only commands

### Why did the app deploy fail (R)
```
# 1. find the app: never guess the id
nix shell nixpkgs#doctl -c doctl apps list --format ID,Spec.Name,ActiveDeployment.ID,InProgressDeployment.ID --no-header
# 2. deployments of the app with cause and phase
nix shell nixpkgs#doctl -c doctl apps list-deployments <appId> --format ID,Cause,Phase,Progress,Created --no-header
# 3. build log of that deployment, bounded
nix shell nixpkgs#doctl -c doctl apps logs <appId> <component> --type build --deployment <deploymentId> --tail 200
# 4. runtime / deploy-phase log
nix shell nixpkgs#doctl -c doctl apps logs <appId> <component> --type deploy --deployment <deploymentId> --tail 200
nix shell nixpkgs#doctl -c doctl apps logs <appId> <component> --type run --tail 200
```
- `--type` is build, deploy, run (default), run_restarted or autoscale_event. `--tail N` is the bound (default -1 = all). Never `--follow`/`-f`.
- No component name = all components. Job runs: `--job-invocation <id>`; autoscale events: `--event-id <id>`.
- `doctl apps get-deployment <appId> <deploymentId> -o json` gives the full detail (large: bound it with `| head -c 4000`).

### What is deployed now (R)
```
nix shell nixpkgs#doctl -c doctl apps get <appId> --format ID,Spec.Name,DefaultIngress,ActiveDeployment.ID,Updated --no-header
```

### App events, instances, alerts, spec (E)
```
nix shell nixpkgs#doctl -c doctl apps list-events <appId> --event-type DEPLOYMENT --format ID,Type,DeploymentID,Phase,Created
nix shell nixpkgs#doctl -c doctl apps list-instances <appId>
nix shell nixpkgs#doctl -c doctl apps list-alerts <appId>
nix shell nixpkgs#doctl -c doctl apps spec get <appId> --format yaml           # --deployment <id> for an older spec
nix shell nixpkgs#doctl -c doctl apps spec validate <file> --schema-only       # local file; no account change; --schema-only needs no auth (docs)
```
`spec get` can contain env entries; secret-typed values are stored encrypted (docs: type SECRET). Not verified what it prints for them: do not paste a spec into a report without checking.

### Droplets, databases, registry, monitoring (E)
```
nix shell nixpkgs#doctl -c doctl compute droplet list --format ID,Name,PublicIPv4,Region,Status
nix shell nixpkgs#doctl -c doctl databases list
nix shell nixpkgs#doctl -c doctl databases get <clusterId>
nix shell nixpkgs#doctl -c doctl registry get
nix shell nixpkgs#doctl -c doctl registry repository list-tags <repository> --format Tag,UpdatedAt,ManifestDigest
nix shell nixpkgs#doctl -c doctl monitoring alert list
```
`doctl databases connection` prints the connection URI and password (not verified masked; it has no `--show` flag in doctl 1.169.0): it is secret-printing, never for agents. There is no `databases logs` command (docs).

## 4. Mutating commands (M): only deploy-engineer / ci-engineer, only after the user's «да» for this command (prod: «да» per command)

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
nix shell nixpkgs#doctl -c doctl apps create-deployment <appId> [--force-rebuild] --wait   # redeploy; alias cd
nix shell nixpkgs#doctl -c doctl apps update <appId> --spec <file> [--update-sources] [--wait]
nix shell nixpkgs#doctl -c doctl apps restart <appId>                                      # flags not verified
nix shell nixpkgs#doctl -c doctl apps delete <appId>                                       # asks for confirmation; -f skips it: never -f without an explicit request
nix shell nixpkgs#doctl -c doctl registry login                                            # writes docker credentials
```
- `apps update` by default does not fetch the newest image or source; add `--update-sources` (help). `apps create --spec <file> [--upsert]` is in docs only.
- `--wait` blocks: run under `timeout 900 nix shell …`. Docs: when `--wait-timeout` runs out doctl exits with an error but the operation keeps going (flag absent from the local help of `create-deployment`: not verified).
- Rollback: doctl has no command (docs). REST `POST https://api.digitalocean.com/v2/apps/{app_id}/rollback` with body `{"deployment_id":"<id>"}`; up to the 10 latest successful deployments; it does not restore database data. A pinned rollback blocks new deployments until `/rollback/commit` or `/rollback/revert`. Not run here.

## 5. Patterns and anti-patterns

Bad: `doctl apps logs <app> web` plus `--follow` (blocks), or no `--tail` (whole log)
Good: `doctl apps logs <app> web --type run --tail 200`

Bad: `doctl databases connection <id>`, `doctl auth token`, `doctl auth init --access-token <token>` typed in a command line, `env`, `echo $DIGITALOCEAN_ACCESS_TOKEN`
Good: `doctl account get --format Status --no-header`; `test -n "$DIGITALOCEAN_ACCESS_TOKEN"`

Bad: guess an app or deployment id from memory
Good: `doctl apps list --format ID,Spec.Name --no-header`, then `list-deployments <appId>`

Bad: `doctl apps list` parsed with grep/awk on the table
Good: `-o json` with a filter, or `--format ID,Spec.Name --no-header`

Bad: `doctl apps update` to "fix" a failed deploy before reading the build log
Good: read `logs --type build` first; change the spec only when deploy-engineer was asked

Bad: `doctl apps delete <id> -f`
Good: do not delete; report to the orchestrator

Bad: tell the user "run doctl apps rollback" (does not exist)
Good: name the REST call above and let deploy-engineer run it on request

## 6. Report shape (collectors)

Put in the report:
- source: `doctl apps logs`, app id (not secrets), component, deployment id, `--type`
- the exact command line and its exit code
- the log excerpt (at most ~40 lines) with line numbers (`| cat -n`) and its time range
- deployment phase and cause from `list-deployments`

Do not put in the report:
- the whole log, the account email or UUID, tokens, connection strings, secrets seen in a log (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
