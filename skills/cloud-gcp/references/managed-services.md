# GCP: managed services instead of self-hosted

Create through IaC (`references/iac.md`); the gcloud forms below are for one-off checks and come from the official reference pages named in brackets. Cloud Run connection details are the part the app depends on.

| Need | Service | Create (gcloud form) | How Cloud Run connects |
|---|---|---|---|
| PostgreSQL | Cloud SQL | `gcloud sql instances create NAME --database-version=POSTGRES_16 --cpu=2 --memory=7680MB --region=REGION` [source](https://docs.cloud.google.com/sql/docs/postgres/create-instance) | `--add-cloudsql-instances=INSTANCE_CONNECTION_NAME` gives the unix socket `/cloudsql/INSTANCE_CONNECTION_NAME` (some drivers need `/cloudsql/INSTANCE_CONNECTION_NAME/.s.PGSQL.5432`); the runtime service account needs the Cloud SQL Client role. Alternative: private IP over Direct VPC egress, TCP 5432 [source](https://docs.cloud.google.com/sql/docs/postgres/connect-run) |
| Redis | Memorystore for Redis | `gcloud redis instances create NAME --size=2 --region=REGION --redis-version=redis_6_x` [source](https://docs.cloud.google.com/memorystore/docs/redis/create-instance-gcloud) | Direct VPC egress (recommended): `--network NETWORK --subnet SUBNET --set-env-vars REDISHOST=<ip>,REDISPORT=<port>`, subnet /26 or larger [source](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run). Host and port: `gcloud redis instances describe NAME --region=REGION`. Valkey: not researched. |
| Object storage | Cloud Storage | `gcloud storage buckets create ...` (flags not verified) | Runtime service account with a bucket role; no key file. CLI: `gcloud storage cp|ls|rsync` [source](https://docs.cloud.google.com/sdk/gcloud/reference/storage) |
| Images | Artifact Registry | `gcloud artifacts repositories create REPO --repository-format=docker --location=LOCATION` [source](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos) | Path `LOCATION-docker.pkg.dev/PROJECT/REPO/IMAGE`; `gcloud auth configure-docker LOCATION-docker.pkg.dev` for push [source](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication) |

Secrets: never in the repo or in image env. Keep values in Secret Manager and pass `--set-secrets=ENV=secret:version`, or encrypt repo files with `sops` (see that skill). The Cloud SQL password is a secret; the connection name is not.

Backups: Cloud SQL `gcloud sql backups list --instance=NAME`; point-in-time clone `gcloud sql instances clone SOURCE NEW --point-in-time 'TIMESTAMP'` (UTC RFC 3339). Local access for debugging: `nixpkgs#google-cloud-sql-proxy` (there is no `nixpkgs#cloud-sql-proxy`).
