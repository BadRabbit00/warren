---
name: cli-cloudflare
description: Use when you must read Cloudflare Workers, Pages, D1, KV or R2 state (deployments, versions, live logs, secret names) with wrangler or the cf CLI, or hand off a deploy, rollback or migration to deploy-engineer.
---

# wrangler and cf (Cloudflare): deploy state and logs

Verified locally with wrangler 4.151.1 and cf 1.0.0-beta.21 (`--help` of every wrangler command below). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (intended allowlist: `wrangler whoami`, `wrangler tail`; `cf` is not on it). `E` = read-only, but only for `deploy-engineer` / `ci-engineer`. `M` = mutating, those two only, after the user's «да» for the command.
Use wrangler in a project that has `wrangler.jsonc` / `.json` / `.toml`. Use `cf` only for things wrangler does not cover (docs, API schema). The two keep separate logins.

## 1. Run

Always `nix shell nixpkgs#wrangler -c wrangler <args>` (or `nixpkgs#cf -c cf <args>`). Never a bare `wrangler`, never `npm i -g`, `npx`, or an install script piped into a shell.
Streams (`tail`) go under `timeout`, written BEFORE nix: `timeout 30 nix shell nixpkgs#wrangler -c wrangler tail <worker>`.
Pick the Worker with `--name <worker>` (or run in the project dir: the config decides) and the config environment with `-e <env>`.

## 2. Login check FIRST

```
nix shell nixpkgs#wrangler -c wrangler whoami --json
```
- exit 0 and JSON with the account = ok.
- exit 1 and `{"loggedIn":false}` = stop. Do not try other commands.
- If `CLOUDFLARE_API_TOKEN` is set it overrides a stored login: the identity may differ from the expected one. Check with `test -n "$CLOUDFLARE_API_TOKEN"`; never print it.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! nix shell nixpkgs#wrangler -c wrangler login --device`
(`--device` works over SSH and in containers; `--browser=false` prints the link instead. Default callback port 8976 is unreachable there.) CI: `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`.

`cf` check: `nix shell nixpkgs#cf -c cf auth whoami`. It exits 0 even when logged out: read the JSON, `"authenticated": false` = stop. Login: `! nix shell nixpkgs#cf -c cf auth login --no-browser`. Its output suggests `cf deploy --temporary-account`: do NOT follow it. `cf` does not reuse a wrangler login.

## 3. Read-only commands

### What is deployed now / what changed (E)
```
nix shell nixpkgs#wrangler -c wrangler deployments status --name <worker> --json
nix shell nixpkgs#wrangler -c wrangler deployments list --name <worker> --json   # 10 most recent
nix shell nixpkgs#wrangler -c wrangler versions list --name <worker> --json      # 10 most recent
nix shell nixpkgs#wrangler -c wrangler versions view <version-id> --name <worker> --json
```
Compare the version ids and `created_on` times with the time of the first error.

### Live errors of a Worker (R)
```
timeout 30 nix shell nixpkgs#wrangler -c wrangler tail <worker> --format json --status error | head -n 100
```
- Filters: `--status ok|error|canceled`, `--method`, `--search <text>`, `--header`, `--ip`, `--version-id <id>`, `--sampling-rate`.
- `tail` only shows requests that arrive while it runs. No traffic = empty output; say so, do not conclude "no errors".

### Pages (E)
```
nix shell nixpkgs#wrangler -c wrangler pages project list --json
nix shell nixpkgs#wrangler -c wrangler pages deployment list --project-name <name> --json
timeout 30 nix shell nixpkgs#wrangler -c wrangler pages deployment tail --project-name <name> --environment production | head -n 100
```

### Data stores (E): always pass `--remote` explicitly
```
nix shell nixpkgs#wrangler -c wrangler d1 list --json
nix shell nixpkgs#wrangler -c wrangler d1 info <name> --json
nix shell nixpkgs#wrangler -c wrangler d1 migrations list <db> --remote
nix shell nixpkgs#wrangler -c wrangler d1 execute <db> --remote --json --command "SELECT count(*) FROM <table>"
nix shell nixpkgs#wrangler -c wrangler d1 time-travel info <db> --json
nix shell nixpkgs#wrangler -c wrangler kv namespace list
nix shell nixpkgs#wrangler -c wrangler kv key list --namespace-id <id> --remote --prefix <p>
nix shell nixpkgs#wrangler -c wrangler r2 bucket list
nix shell nixpkgs#wrangler -c wrangler r2 bucket info <bucket> --json
nix shell nixpkgs#wrangler -c wrangler secret list --name <worker>
```
- Without `--remote` a command may hit local (Miniflare) storage: reads look empty (docs, not run).
- `d1 execute` runs any SQL. As E only `SELECT`; an `INSERT/UPDATE/DELETE/DROP` is M.
- `secret list` prints names only (json); never read values. `kv key get` prints a value: it can be a secret, ask first (see 5).

### cf (E, only when wrangler cannot answer)
```
nix shell nixpkgs#cf -c cf cli search "<describe the task, no names or ids>"
nix shell nixpkgs#cf -c cf docs search "<question>"
nix shell nixpkgs#cf -c cf schema <command path>
nix shell nixpkgs#cf -c cf workers list
nix shell nixpkgs#cf -c cf workers <get|deployments|versions> --help     # pick one subcommand, read its help first
```
`cf` is a huge API wrapper in beta and its commands may change: `cf cli search` first, then `--help`, then run. Subcommand `--help` in this version prints the top-level help in some cases: not verified for every path. Keep search queries free of names, domains and ids.

## 4. Mutating commands: only deploy-engineer / ci-engineer, only after the user's «да» for this command (prod: «да» per command)

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
nix shell nixpkgs#wrangler -c wrangler deploy --dry-run                       # compiles, uploads nothing (safe check first)
nix shell nixpkgs#wrangler -c wrangler deploy --message "<why>" --tag <tag>   # M: live at once
nix shell nixpkgs#wrangler -c wrangler versions upload --message "<why>"      # M: new version, not live
nix shell nixpkgs#wrangler -c wrangler versions deploy <id>@<pct>% -y         # M: gradual rollout
nix shell nixpkgs#wrangler -c wrangler rollback <version-id> --name <worker> --message "<why>"   # M: all routes at once
nix shell nixpkgs#wrangler -c wrangler d1 migrations apply <db> --remote      # M: asks to confirm
nix shell nixpkgs#wrangler -c wrangler d1 time-travel restore <db> --timestamp <T>   # M: data rewind
nix shell nixpkgs#wrangler -c wrangler secret put <key> --name <worker>       # M: live at once, value from stdin
nix shell nixpkgs#wrangler -c wrangler pages deploy <dir> --project-name <name> --branch <b>   # M
```
- Rollback restores code only, not D1/KV/R2 data; it is blocked after a Durable Object class migration or a deleted binding (docs).
- Pages has no CLI rollback (docs): dashboard "Rollback to this deployment", or redeploy the previous commit. `wrangler pages deployment delete` deletes: it is not a rollback.
- `secret put/delete` deploy immediately and bypass a gradual rollout (docs).
- Before `rollback` say what it undoes (`deployments list`), and rollback only after the user's «да» (the effect is immediate on all routes).

## 5. Patterns and anti-patterns

Bad: `wrangler tail <worker>` with no bound (streams forever, blocks the agent)
Good: `timeout 30 nix shell nixpkgs#wrangler -c wrangler tail <worker> --format json --status error | head -n 100`

Bad: `wrangler d1 execute <db> --command "..."` with no `--remote` or `--local`
Good: name the target: `--remote` for production, `--local` for dev

Bad: `wrangler kv key get <key>`, `wrangler d1 execute ... "SELECT * FROM users"` pasted into a report (values, personal data, secrets)
Good: `kv key list` (names), `SELECT count(*)`, selected non-sensitive columns with `LIMIT 20`

Bad: `wrangler secret put` with the value on the command line or in the report
Good: `secret list` for names; a value is given by the user on stdin, never echoed

Bad: `cf auth whoami` judged by exit code (always 0)
Good: read `"authenticated"` in the JSON

Bad: follow `cf deploy --temporary-account` from the login hint
Good: stop and give the user `! nix shell nixpkgs#cf -c cf auth login --no-browser`

Bad: `wrangler whoami` logged in, so assume `cf` is logged in
Good: check each tool; they keep separate credentials

Bad: `echo $CLOUDFLARE_API_TOKEN`, `env`, `wrangler login` run by the agent
Good: `test -n "$CLOUDFLARE_API_TOKEN"`; login is the user's `!` command

Bad: `npx wrangler …` or a global install
Good: `nix shell nixpkgs#wrangler -c wrangler …`

## 6. Report shape (collectors)

Put in the report:
- source: `wrangler deployments|versions|tail`, worker or project name, environment, version id
- the exact command line and its exit code; for `tail` the timeout used and how many events arrived
- the failing events: at most ~40 lines with time, status, exception message, `cat -n` numbers
- the deployed version id and time next to the first error time

Do not put in the report:
- raw `tail` output beyond the excerpt, request headers, cookies, bodies, query strings with tokens
- the account email, token, secret or KV/D1 values (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
