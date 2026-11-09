---
name: cli-yc
description: Use when you must read Yandex Cloud state (Serverless Containers, Cloud Logging, Container Registry, Managed PostgreSQL and Redis, VMs) with the yc CLI, or hand off a revision deploy or rollback to deploy-engineer.
---

# yc (Yandex Cloud CLI): serverless containers, logs, registry, managed databases

Verified locally with yc 1.25.0 (`--help` of every command below; nothing was run against a real cloud). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (hook allowlist today: `yc config list`, `yc logging read`; `yc config list` is a hook-vs-skill conflict, see section 5). `E` = read-only, but only for `deploy-engineer` / `ci-engineer`. `M` = mutating. Marks other than the allowlisted commands are the intended policy; the hook follows in T1.

## 1. Run

yc is unfree software in nixpkgs, so the shell needs the unfree switch:
`NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc <args>`
Never the install script from `storage.yandexcloud.net` piped into a shell, never a bare `yc`.
Pick the folder with `--folder-id <id>` on every command (or `yc config get folder-id` to see the default).

## 2. Login check FIRST

```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc iam whoami
```
- exit 0 and a subject printed = logged in. Report only yes/no.
- exit 1 with "Failed to get credentials" = stop. Do not try other commands.
- Do NOT use `yc config list` as the check: it prints the OAuth `token:` in plain text. Do NOT use `yc iam create-token`: it prints a live IAM token.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc init`
CI or service-account mode (docs, not run): a service-account key via `yc config profile` / an IAM token in the environment; see <https://yandex.cloud/en/docs/cli/operations/authentication/service-account> and <https://yandex.cloud/en/docs/cli/operations/authentication/iam-token-env>. An IAM token lives at most 12 hours.

## 3. Read-only commands

### Why did the container fail (R)
```
# 1. find the log group
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc logging group list --folder-id <id> --limit 20
# 2. its recent logs, bounded
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc logging read --group-name <group> --folder-id <id> --since 1h --levels ERROR,FATAL --limit 100
```
- Always `--since` (or `--until`) and `--limit`. `--follow` cannot be combined with `--since`/`--until` and never returns: do not use it.
- `--filter`, `--resource-types`, `--resource-ids`, `--stream-names` narrow the result. Default response cap is 3.5 MiB (`--max-response-size`).
- Level names and filter syntax: not verified; run `yc logging read --help` and `yc logging group list` first.

### Which revision serves the container (E)
```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container list --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container get --name <name> --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container revision list --container-name <name> --folder-id <id> --limit 10
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container list-operations --name <name> --folder-id <id> --limit 10
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc operation get <operation-id>
```
Revision output can contain environment values and secret references: report names, not values.

### Registry (E)
```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc container registry list --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc container repository list --registry-name <reg> --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc container image list --registry-name <reg> --repository-name <repo> --folder-id <id> --limit 10
```

### Managed PostgreSQL and Redis (E, logs: R-like but not on the allowlist)
```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc managed-postgresql cluster list --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc managed-postgresql cluster get --name <cluster> --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc managed-postgresql cluster list-logs --name <cluster> --folder-id <id> --service-type postgresql --since 1h --limit 100
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc managed-postgresql cluster list-operations --name <cluster> --folder-id <id> --limit 10
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc managed-redis cluster list-logs --name <cluster> --folder-id <id> --since 1h --limit 100
```
`list-logs --follow` is `tail -f`: never. `--filter "message.error_severity IN ('ERROR','FATAL','PANIC')"` is the example from the help.

### VMs and folders (E)
```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc compute instance list --folder-id <id>
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc compute instance get-serial-port-output --name <vm> --folder-id <id> | tail -n 200
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc resource-manager folder list
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc config get folder-id
```

## 4. Mutating commands: only deploy-engineer / ci-engineer, only on request

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
# M: deploy a new revision (flags from the help; --image is the one that matters)
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container revision deploy --container-name <name> --image <registry-image> --folder-id <id> [--memory 512MB --cores 1 --execution-timeout 30s --concurrency 8 --service-account-id <id> --environment K=V --secret ...]
# M: roll back to an earlier revision
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc serverless container rollback <name> --revision-id <revision-id> --folder-id <id>
```
Both take `--async` (return at once with the operation; then follow with `yc operation get <id>`). Find a good `<revision-id>` with `revision list` first. `--environment K=V` puts values on the command line and in shell history: use `--secret` references for anything sensitive (flag shape: `PROPERTY=VALUE[,...]`, semantics not verified).

## 5. Patterns and anti-patterns

Bad: `yc config list` as the login check or in a report (prints the OAuth `token:` in plain text; it is on the reader allowlist today, so readers must never paste its output)
Good: `yc iam whoami` for login, `yc config get folder-id` and `yc config get cloud-id` for the context

Bad: `yc iam create-token` (prints a live IAM token)
Good: not needed by agents; only the user or CI creates tokens

Bad: `yc logging read <group> --follow`
Good: `yc logging read --group-name <g> --since 1h --limit 1000`; `--follow` cannot be combined with `--since`

Bad: `yc logging read` without `--since`/`--limit` (long history, up to 3.5 MiB per response)
Good: `--since 1h --levels ERROR --limit 100`

Bad: name collisions: several folders or profiles and no `--folder-id`
Good: pass `--folder-id` on every command and write it in the report

Bad: `yc managed-postgresql cluster list-logs ... --follow`
Good: `--since 1h --limit 100`

Bad: unfree package without the switch (the `nix shell` fails)
Good: `NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc ...`

Bad: rollback by guessing a revision id
Good: `revision list`, pick the last one seen healthy, then `rollback --revision-id`

## 6. Report shape (collectors)

Put in the report:
- source: `yc logging read` (group, folder), time range, level filter
- the exact command line and its exit code
- the log excerpt (at most ~40 lines) with timestamps and levels
- revision ids and operation ids when asked what is deployed

Do not put in the report:
- the whole log, tokens, the `token:` line of `yc config list`, environment values (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
