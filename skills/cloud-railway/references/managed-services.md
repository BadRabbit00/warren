# Railway: managed services instead of self-hosted

| Need | Create | App gets access |
|---|---|---|
| PostgreSQL | `railway add --database postgres` [source](https://docs.railway.com/databases/postgresql) | Variables `PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE DATABASE_URL` (private). `DATABASE_PUBLIC_URL` only after enabling Public Access: do not enable it unless the user decides. |
| Redis | `railway add --database redis` [source](https://docs.railway.com/databases/redis) | `REDISHOST REDISUSER REDISPORT REDISPASSWORD REDIS_URL`; runs the Docker Hub `redis` image, single node, HA option (Sentinel + HAProxy). Valkey: not found in the research. |
| Object storage | none found in the research; use `cloud-cloudflare` R2 or another provider | S3 keys as service variables |
| Files on disk | `railway volume add --service api --mount-path /data --json` [source](https://docs.railway.com/volumes) | `RAILWAY_VOLUME_MOUNT_PATH`, `RAILWAY_VOLUME_NAME` at runtime |

- Reference another service's variable as `${{SERVICE_NAME.VAR}}` in a service variable, so the connection string is not copied.
- Postgres: native Backups, PITR and an HA option exist; the database is single-node by default. Changing its image, start command or variables makes it yours to manage.
- Volume: mounted at container start, not at build or pre-deploy; mounted as root (`RAILWAY_RUN_UID=0` for non-root images); `/app` prefix for app-relative paths; one replica only; removing a volume deletes its data, back up first.
- Secrets: never in the repo. Platform variables, set by the user or by IaC from a CI secret; encrypted repo files through `sops`.
