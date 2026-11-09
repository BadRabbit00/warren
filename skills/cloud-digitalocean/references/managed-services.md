# DigitalOcean: managed services instead of self-hosted

| Need | Service | Create | App gets access |
|---|---|---|---|
| PostgreSQL | Managed Database `pg` | in the app spec: `databases: [{ engine: PG, production: true, cluster_name: ... }]` [source](https://docs.digitalocean.com/products/app-platform/reference/app-spec/); or `doctl databases create <name> --engine pg --wait` | Bindable variables in env values, e.g. `${<db-component-name>.DATABASE_URL}` / `.HOSTNAME`; a dev database without `cluster_name` gets a new cluster |
| Redis / Valkey | Managed Database `redis` / `valkey` | same, `engine: REDIS` or `VALKEY` | same bindable variables |
| Object storage | Spaces (S3-compatible) | IaC (provider docs) | Endpoint `https://<space>.<region>.digitaloceanspaces.com`, Spaces access keys (SigV4) as `SECRET` env vars; only ACLs private / public-read [source](https://docs.digitalocean.com/products/spaces/reference/s3-compatibility/) |
| Images | Container Registry (DOCR) | `doctl registry create` | `registry.digitalocean.com/<registry>/<image>`; spec `registry_type: DOCR`, `registry` empty for DOCR; `tag` and `digest` are mutually exclusive; `deploy_on_push` only with DOCR and not with a fixed digest |

- Do not print `doctl databases connection`: in nixpkgs doctl 1.169.0 it may print the password (a `Password` column exists, there is no masking flag), so readers never run it and values can leak into logs [source](https://docs.digitalocean.com/reference/doctl/reference/databases/connection/). Use bindable variables in the spec.
- Backups: `doctl databases backups <cluster-id>`; restore into a new cluster with `--restore-from-cluster-name` and optionally `--restore-from-timestamp`.
- Not supported on Spaces: cross-region copy, tag lifecycle rules, bucket-level encryption (SSE-C only). Unsupported calls return `NotImplemented`.
- Secrets never in the repo: spec `type: SECRET` values injected at deploy time, encrypted files with `sops`.
