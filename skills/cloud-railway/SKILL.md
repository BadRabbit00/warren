---
name: cloud-railway
description: Use when a project deploys to or considers Railway - when it fits, the login check with project versus account tokens, deploy and rollback, Railway IaC (railway config) versus the community Terraform provider, managed Postgres and Redis and volumes, and pitfalls.
---

# Cloud: Railway

Provider skill. Commands: `cli-railway`. IaC basics: `iac`. Secrets: `sops`, `secrets.md`. Images: `registry-dockerhub-ghcr`. Local/other deploy shapes: `deploy-variants`.

## When to choose

- Managed Postgres and Redis added in one command (`railway add --database postgres|redis`), private network by default, variables injected into services [source](https://docs.railway.com/databases/postgresql).
- Deploy from source or image with a single CLI call (`railway up`) and dashboard rollback.
- Limits from the research: databases are single-node unless the HA option is enabled; changing a database image or start command "makes the database yours to manage" (same source). A service with a volume cannot have more than one replica [source](https://station.railway.com/questions/service-stuck-at-2-replicas-with-an-atta-70a44553). IaC is young (below); a user report says it "does not feel production-ready" [source](https://station.railway.com/feedback/iac-does-not-feel-production-ready-for-r-da53d29a).

## Login check (D3)

Which token is set decides which check works [source](https://docs.railway.com/cli/deploying):

| Credentials in the environment | Check |
|---|---|
| none, or `RAILWAY_API_TOKEN` (account/workspace token) | `nix shell nixpkgs#railway -c railway whoami` (exit 1 and `Unauthorized` when missing) |
| only `RAILWAY_TOKEN` (project token) | `railway status --json` or `railway deployment list --service <svc> --json`; `whoami` fails for project tokens by design |

Not logged in: stop with `STATUS: blocked — login needed`, give `! nix shell nixpkgs#railway -c railway login` (or `! nix shell nixpkgs#railway -c railway login --browserless` without a browser). Never run it yourself; never ask for tokens in chat. A stale login that still says Unauthorized: user deletes `~/.railway/config.json` and logs in again (user-reported fix, not official). Which of `RAILWAY_TOKEN` / `RAILWAY_API_TOKEN` wins when both are set is not documented: set only one.

Never run an unauthenticated `railway up`: it chains into OAuth and can create a project [source](https://docs.railway.com/cli/up). Always pass `--service` and `--environment`.

## Deploy

```
RAILWAY_TOKEN=<project token from CI secret> nix shell nixpkgs#railway -c railway up --ci --service <svc> --environment <env>
```

- `--ci` streams build logs, then exits. `--detach --json` returns before the deployment is healthy: poll `railway deployment list --json` and `railway logs --json -n 50`.
- `railway redeploy` rebuilds the latest deployment; `railway restart` restarts without a rebuild. Neither is a rollback.
- Production deploy only from CI on `main` or after the user's «да».

## Rollback

There is no CLI rollback command. Options [source](https://railway.com/guides/roll-back-bad-deploy.md):

1. Dashboard: Service > Deployments > three dots on the last good deployment > Rollback (restores image and custom variables; limited by plan retention).
2. API: GraphQL `deploymentRollback` mutation through `railway api '<mutation>'`, with the last good id from `railway deployment list --json`. Returns a Boolean, not the new id; the argument shape is not verified (`railway api describe deploymentRollback` needs auth). API errors come back as HTTP 200: read the `errors` array.
3. Git: revert the commit and deploy again.

Ask the user for «да» before any of them. Database data is not rolled back; use the database's Backups/PITR.

## IaC

`references/iac.md`: `railway config` (`.railway/railway.ts`) is the vendor path; the old `railway.toml/json` is deprecated and stops being read on 2026-12-01. Plan in CI, apply by a human with «да», stand and prod both.

## Managed services

`references/managed-services.md`: Postgres, Redis, volumes, variables.

## Pitfalls

`references/pitfalls.md` (Bad/Good with sources).

## Not verified

- `deploymentRollback` argument shape; rollback retention per plan.
- Whether the community Terraform provider covers volumes or databases (not in its 0.6.x resource list).
- Private network hostname format.
