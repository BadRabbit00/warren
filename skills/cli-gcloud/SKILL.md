---
name: cli-gcloud
description: Use when you must read Google Cloud state (Cloud Run services and revisions, logs, Cloud SQL, builds, Artifact Registry) with the gcloud CLI, or hand off a deploy or traffic rollback to deploy-engineer.
---

# gcloud (Google Cloud CLI): Cloud Run, logs, Cloud SQL, builds

Verified locally with gcloud 583.0.0 (`--help` of every command below; nothing was run against a real project). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (hook allowlist today: `gcloud auth list`, `gcloud logging read`). `E` = read-only, but only for `deploy-engineer` / `ci-engineer` (the readers' hook denies it). `M` = mutating. Marks other than the two allowlisted commands are the intended policy; the hook follows in T1.

## 1. Run

Always `nix shell nixpkgs#google-cloud-sdk -c gcloud <args>`. Never a bare `gcloud`, never an install script piped into a shell, never `brew` or `apt`.
Pick the project with `--project <id>` and the Cloud Run region with `--region <region>` on every command; otherwise the defaults of `gcloud config` decide, and that may be the wrong project.

## 2. Login check FIRST

```
nix shell nixpkgs#google-cloud-sdk -c gcloud auth list --filter=status:ACTIVE --format="value(account)"
```
- one account name printed = logged in. Say "yes", do not copy the account into the report.
- empty output = NOT logged in, even though the exit code is 0. Judge by the output, not by the exit code.
- A later command that fails with a credentials or "reauthentication" error = same stop.
- `gcloud auth print-access-token` also exits 1 without credentials, but it prints a live token on success: never use it as the check.

Not logged in: report `STATUS: blocked — login needed` and give the user this one command:
`! nix shell nixpkgs#google-cloud-sdk -c gcloud auth login --no-launch-browser`
CI or service-account mode: `gcloud auth activate-service-account --key-file=<file>` needs a key file (a secret; never print it). In GitHub Actions the documented way is the `google-github-actions/auth` action (workload identity, no key file). Both are from the research card, not run locally.

## 3. Read-only commands

### Why did the Cloud Run service fail (R)
```
# 1. the logs of one service, errors only, bounded
nix shell nixpkgs#google-cloud-sdk -c gcloud run services logs read <service> --region <region> --project <id> --log-filter="severity>=ERROR" --freshness=1h --limit=100
# 2. the same through Cloud Logging with a filter (R, on the hook allowlist)
nix shell nixpkgs#google-cloud-sdk -c gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="<service>" AND severity>=ERROR' --project <id> --freshness=1h --limit=100 --format=json
```
- Both are bounded by `--limit` plus `--freshness` (default freshness is 1 day, default order is newest first).
- `--format=json` gives `timestamp`, `severity`, `textPayload` / `jsonPayload`; table output cuts long lines.

### Which revision serves traffic (E)
```
nix shell nixpkgs#google-cloud-sdk -c gcloud run services describe <service> --region <region> --project <id> --format=json
nix shell nixpkgs#google-cloud-sdk -c gcloud run revisions list --service <service> --region <region> --project <id> --limit=10
nix shell nixpkgs#google-cloud-sdk -c gcloud run revisions describe <revision> --region <region> --project <id> --format=json
nix shell nixpkgs#google-cloud-sdk -c gcloud run services list --region <region> --project <id> --limit=20
```
`services describe --format=json` shows the traffic split (`status.traffic`) and the latest ready revision. Environment variable values are part of that output: do not paste them into a report.

### Builds and images (E)
```
nix shell nixpkgs#google-cloud-sdk -c gcloud builds list --project <id> --limit=5 --filter="status=FAILURE"
nix shell nixpkgs#google-cloud-sdk -c gcloud builds log <build-id> --project <id> | tail -n 200
nix shell nixpkgs#google-cloud-sdk -c gcloud artifacts docker images list <LOCATION-docker.pkg.dev/project/repo> --include-tags --limit=10
```
`builds log --stream` follows a running build and blocks: only under `timeout`.

### Cloud SQL (E)
```
nix shell nixpkgs#google-cloud-sdk -c gcloud sql instances list --project <id>
nix shell nixpkgs#google-cloud-sdk -c gcloud sql instances describe <instance> --project <id> --format=json
nix shell nixpkgs#google-cloud-sdk -c gcloud sql backups list --instance <instance> --project <id> --limit=10
nix shell nixpkgs#google-cloud-sdk -c gcloud sql operations list --instance <instance> --project <id> --limit=10
```

### Who am I, which project (E)
```
nix shell nixpkgs#google-cloud-sdk -c gcloud config list
nix shell nixpkgs#google-cloud-sdk -c gcloud projects list --limit=20
nix shell nixpkgs#google-cloud-sdk -c gcloud secrets list --project <id> --limit=50
```
`secrets list` shows names only. Reading a secret value (`gcloud secrets versions access`) is never done: not verified locally, and it prints the secret.

## 4. Mutating commands: only deploy-engineer / ci-engineer, only on request

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
# M: roll back = send 100% of traffic to a known good revision (help read, not run)
nix shell nixpkgs#google-cloud-sdk -c gcloud run services update-traffic <service> --to-revisions=<good-revision>=100 --region <region> --project <id>
# M: back to the newest revision
nix shell nixpkgs#google-cloud-sdk -c gcloud run services update-traffic <service> --to-latest --region <region> --project <id>
# M: deploy an image; --no-traffic creates the revision without sending traffic to it
nix shell nixpkgs#google-cloud-sdk -c gcloud run deploy <service> --image <image> --region <region> --project <id> --no-traffic
# M: login with a key file (secret) in CI
nix shell nixpkgs#google-cloud-sdk -c gcloud auth activate-service-account --key-file=<file>
```
Check the revision list first: roll back to a revision you have seen serve traffic. Rollback after a bad migration does not undo the migration.

## 5. Patterns and anti-patterns

Bad: `gcloud logging read "resource.type=cloud_run_revision"` (default freshness is 1 day, no limit: thousands of entries)
Good: add `--freshness=1h --limit=100` and a `severity>=ERROR` filter

Bad: `gcloud auth print-access-token`, `gcloud auth list` without `--filter`/`--format` pasted into a report
Good: the `value(account)` check above, report only yes/no

Bad: judge the login by the exit code of `gcloud auth list`
Good: it exits 0 when logged out; empty output is the signal

Bad: no `--project` / `--region` (the default config decides)
Good: pass both on every command and write them in the report

Bad: `gcloud builds log <id> --stream` with no timeout
Good: `timeout 120 nix shell nixpkgs#google-cloud-sdk -c gcloud builds log <id> --stream`, or plain `builds log <id> | tail -n 200`

Bad: `--format=json` of `run services describe` pasted whole (it holds env var values)
Good: `--format="value(status.traffic)"` or a `--filter` on one field; redact values as `<redacted>`

Bad: `gcloud secrets versions access ...`, `gcloud auth print-access-token`, `cat <key-file>`, `env`
Good: `gcloud secrets list` (names only)

## 6. Report shape (collectors)

Put in the report:
- source: `gcloud logging read` or `run services logs read`, project, region, service, revision
- the exact command line and its exit code
- the log excerpt (at most ~40 lines) with timestamps and severity, and the time range of the excerpt
- the traffic split and the revision names when asked which version is live

Do not put in the report:
- the whole log, access tokens, key files, env var values (write `<redacted>`), the account name
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
