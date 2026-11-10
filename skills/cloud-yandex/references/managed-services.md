# Yandex Cloud: managed services instead of self-hosted

Create through IaC (provider docs for exact resources); inspect with the read-only `yc` commands below.

| Need | Service | Inspect | App gets access |
|---|---|---|---|
| PostgreSQL | Managed Service for PostgreSQL | `yc managed-postgresql cluster list`, `get <name or id>`, `list-operations`, `list-logs <name or id> --service-type postgresql --since <t> --limit N --format json` (`pooler` for the pooler) [source](https://yandex.cloud/en/docs/managed-postgresql/operations/cluster-logs) | Host, user and password as Lockbox secrets passed with `--secret name=..,key=..,environment-variable=..` on `revision deploy`; the container needs network access (`--network-id`) |
| Valkey (ex-Redis) | Managed Service for Valkey; CLI namespace `managed-redis` | `yc managed-redis cluster list`, `get`, `list-operations` [source](https://yandex.cloud/en/docs/managed-redis/operations/cluster-list) | same |
| Object storage | Object Storage, S3-compatible | `aws s3 ls --recursive s3://bucket --endpoint-url=https://storage.yandexcloud.net` with `nixpkgs#awscli2` | Endpoint `https://storage.yandexcloud.net`, region `ru-central1`; static keys: `yc iam access-key create --service-account-name <sa>`; the secret is shown once, store it straight into Lockbox or CI secrets, never the repo [source](https://yandex.cloud/en/docs/iam/operations/authentication/manage-access-keys) |
| Images | Container Registry | `yc container image list`, `get` | `cr.yandex/<registry_id>/<image>:<tag>` |

- Backups: `cluster backup`, `list-backups`, `restore` exist for PostgreSQL and Valkey; restore creates a cluster from a backup. These are write actions: the user's «да».
- Platform secrets: Lockbox via `--secret`. Encrypted repo files: `sops`.
- Container logs: Cloud Logging, `yc logging read --group-name=default`; `--follow` cannot be combined with `--since` / `--until`; without time flags only the last hour is read; `--limit` is 1-1000 [source](https://yandex.cloud/en/docs/logging/operations/read-logs).
