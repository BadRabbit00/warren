---
name: cloud-cloudflare
description: Use when a project deploys to or manages Cloudflare (Workers, Pages, D1, KV, R2, Hyperdrive, DNS) - choosing it, the login check, deploy and rollback, OpenTofu IaC with plan in CI and human apply, managed storage instead of self-hosted, and the vendored official Cloudflare agent skills.
---

# Cloud: Cloudflare

Provider skill. Commands live in `cli-cloudflare` (wrangler + `cf`); do not copy command lists here. IaC basics: `iac`. Secrets: `sops`, `secrets.md`. Registries: `registry-dockerhub-ghcr`. CI: `ci-github-actions`.

## When to choose

- Workers + Static Assets for new sites, SPAs and full-stack apps: the official Cloudflare skill recommends it for all new projects and keeps existing Pages projects as they are (`references/official/cloudflare/SKILL.md`).
- Object storage with an S3 API: R2 (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, region `auto`) [source](https://developers.cloudflare.com/r2/api/s3/api/).
- SQL database next to Workers: D1; Postgres from Workers: Hyperdrive in front of an external Postgres (pooling and caching, it is not a database) [source](https://developers.cloudflare.com/hyperdrive/reference/wrangler-commands/).
- Not a fit, from the research: no managed PostgreSQL and no Redis/Valkey service were found. Use another provider for them (`cloud-gcp`, `cloud-digitalocean`, `cloud-yandex`, `cloud-railway`). Whether Cloudflare has one is not verified.

## Official skills (vendored, unchanged)

Copied from github.com/cloudflare/skills (Apache-2.0), see `references/official/NOTICE.md` and `references/official/LICENSE`.

| Read when | File |
|---|---|
| Choosing Cloudflare products, 52x / 1xxx errors | `references/official/cloudflare/SKILL.md` (+ `references/<product>/` for kv, r2, d1, hyperdrive, queues, workflows, tunnel, waf, ...) |
| Project has `wrangler.jsonc/json/toml` | `references/official/wrangler/SKILL.md` |
| New project or `cloudflare.config.ts` | `references/official/cf-cli/SKILL.md` |
| Writing or reviewing Worker code | `references/official/workers-best-practices/SKILL.md` |

Warren rules override the official text where they differ:

- Run tools only as `nix shell nixpkgs#wrangler -c wrangler ...` or `nix shell nixpkgs#cf -c cf ...`. The official skills suggest `npm install --global cf` and `npx wrangler`; do not do that here. If the project pins wrangler in `node_modules`, the official skill prefers that version; use the project script, never a global install.
- Login is checked first and done only by the user (below).
- The `skill-feedback.md` files describe posting public GitHub issues. Do it only if the user asks and approves the exact text.
- IaC is OpenTofu; apply only by a human (below).

## Login check (D3)

1. `nix shell nixpkgs#wrangler -c wrangler whoami --json` (non-zero exit = not logged in) [source](https://developers.cloudflare.com/workers/wrangler/commands/general/). For `cf`: `nix shell nixpkgs#cf -c cf auth whoami`. The two tools do not share credentials; check the one you will use [source](https://raw.githubusercontent.com/cloudflare/skills/main/skills/cf-cli/SKILL.md).
2. If `CLOUDFLARE_API_TOKEN` is set it overrides the stored login, so `whoami` may show another identity than expected [source](https://developers.cloudflare.com/workers/wrangler/commands/general/). Note which one you are on.
3. Not logged in: stop with `STATUS: blocked — login needed` and give the user the command:
   - `! nix shell nixpkgs#wrangler -c wrangler login --device` (device flow, works over SSH)
   - or `! nix shell nixpkgs#cf -c cf auth login --no-browser`
4. Never run the login, never ask for a token in chat. CI uses `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` from CI secrets.

## Deploy and rollback

| Step | Command (details in `cli-cloudflare`) |
|---|---|
| Dry run | `wrangler deploy --dry-run` |
| Deploy | `wrangler deploy [--env <env>] --message "<why>"`; gradual: `wrangler versions upload` then `wrangler versions deploy <id>@<pct>%` |
| Verify | `wrangler deployments status --name <worker> --json`, `wrangler tail <worker> --format json --status error` |
| Rollback Worker | `wrangler rollback [<VERSION_ID>] --name <worker> --message "<why>"` (needs the user's «да»: effect is immediate on all routes) |
| Rollback Pages | dashboard only (Deployments > Rollback), or redeploy the previous commit with `wrangler pages deploy` |
| Rollback D1 data | `wrangler d1 time-travel info <DB> --json`, then `restore --bookmark <B>` (user's «да») |

Worker rollback does not roll back D1/KV/R2 data. It is blocked if a bound resource was deleted, if KV/D1 changed between versions, or after a Durable Object migration [source](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/). Keep migrations forward-compatible (expand/contract).

## IaC, managed services, pitfalls

- `references/iac.md`: provider, auth, R2 state, plan in CI, human apply, import of existing resources.
- `references/managed-services.md`: D1, R2, KV, Hyperdrive: create, connect, secrets.
- `references/pitfalls.md`: Bad/Good from the research, each with its source.

## Not verified

- `cf` subcommands for deploy, logs and rollback beyond `cf auth login/whoami` (beta; use `cf cli search`, `--help`).
- Minimal API-token permissions for R2/D1/Hyperdrive/KV management beyond the "Edit Cloudflare Workers" template.
- Pages rollback through the API.
