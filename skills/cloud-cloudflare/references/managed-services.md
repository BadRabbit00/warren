# Cloudflare: managed services instead of self-hosted

All commands are in `cli-cloudflare`. Always pass `--remote` for production and `--local` for dev: without it D1/KV/R2 commands may touch local (Miniflare) storage [source](https://developers.cloudflare.com/d1/wrangler-commands/).

| Need | Service | Create (via IaC; CLI only for a one-off) | App gets access |
|---|---|---|---|
| SQL database for Workers | D1 | IaC resource from the provider docs; CLI `wrangler d1 ...` | Binding in the Worker config; no connection string |
| PostgreSQL | none at Cloudflare; Hyperdrive fronts an external Postgres | `wrangler hyperdrive create <NAME> --connection-string ...` or IaC | Hyperdrive binding; the origin password is passed once at creation, from sops or a CI secret, not typed in a shared log |
| Redis/Valkey | none found in the research | use another provider | n/a |
| Object storage | R2 | `wrangler r2 bucket create <NAME>`; IaC | Binding, or S3 API: endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, region `auto`, keys from an R2 API token [source](https://developers.cloudflare.com/r2/api/s3/api/) |
| Key-value | KV | `wrangler kv namespace create <NAMESPACE> --binding <B> --update-config` | Binding |

Secrets for Workers: `wrangler secret put` deploys immediately; for staged change use `wrangler versions secret` [source](https://raw.githubusercontent.com/cloudflare/skills/main/skills/wrangler/SKILL.md). Never put secret values in `wrangler.jsonc`, `[vars]`, or the repo; encrypted files go through `sops`. Do not print `--connection-string` values into logs.

Backups: D1 Time Travel (`wrangler d1 time-travel info|restore`). R2 and KV backup strategy was not researched.
