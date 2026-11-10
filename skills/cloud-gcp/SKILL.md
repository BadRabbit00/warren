---
name: cloud-gcp
description: Use when a project deploys to or considers Google Cloud - Cloud Run, Cloud SQL for PostgreSQL, Memorystore, Cloud Storage, Artifact Registry - the login check (gcloud versus ADC), deploy and traffic-based rollback, OpenTofu with a GCS backend, plan in CI with Workload Identity Federation, human apply.
---

# Cloud: Google Cloud (GCP)

Provider skill. Commands: `cli-gcloud`. IaC basics: `iac`. Secrets: `sops`, `secrets.md`. Containers: `docker-patterns`, `registry-dockerhub-ghcr`. CI: `ci-github-actions`.

## When to choose

- Containers on Cloud Run with revisions and percentage traffic splits (canary, rollback by moving traffic) [source](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).
- All three managed data services exist: Cloud SQL for PostgreSQL, Memorystore for Redis, Cloud Storage; Artifact Registry for images.
- Keyless CI through Workload Identity Federation (WIF) [source](https://github.com/google-github-actions/auth).
- Pricing and regions were not researched. Memorystore access from Cloud Run needs a VPC network (Direct VPC egress or a connector).

## CLI and login check (D3)

Run: `nix shell nixpkgs#google-cloud-sdk -c gcloud ...` (`gcloud components install` is disabled in the nixpkgs build; extra components such as `beta` and `log-streaming` need `google-cloud-sdk.withExtraComponents [ ... ]` in the project devShell [source](https://github.com/NixOS/nixpkgs/blob/nixos-unstable/pkgs/by-name/go/google-cloud-sdk/package.nix); the expression syntax is not verified). See `cli-gcloud`.

1. `gcloud auth list --filter=status:ACTIVE --format="value(account)"`: empty output = not logged in (with an empty config it prints a WARNING and exits 0, verified google-cloud-sdk 583.0.0: test the output, not the exit code). `gcloud config get-value project` shows the project.
2. gcloud credentials and Application Default Credentials (ADC) are separate. OpenTofu and SDKs need ADC: `gcloud auth application-default login`, or `GOOGLE_APPLICATION_CREDENTIALS` [source](https://docs.cloud.google.com/docs/authentication/application-default-credentials). Check ADC separately.
3. Not logged in: stop with `STATUS: blocked — login needed` and give the user:
   - `! nix shell nixpkgs#google-cloud-sdk -c gcloud auth login --no-launch-browser`
   - for IaC also `! nix shell nixpkgs#google-cloud-sdk -c gcloud auth application-default login --no-launch-browser`
4. Never run the login, never ask for a key in chat. Service account keys "create a security risk and are not recommended" [source](https://docs.cloud.google.com/sdk/gcloud/reference/auth/activate-service-account); CI uses WIF (`references/iac.md`).

## Deploy

All `gcloud` commands below run through `nix shell nixpkgs#google-cloud-sdk -c` (see `cli-gcloud`).

```
gcloud run deploy SERVICE --image=REGION-docker.pkg.dev/PROJECT/REPO/IMAGE@sha256:<digest> --region=REGION \
  [--service-account=SA] [--add-cloudsql-instances=INSTANCE] [--set-secrets=ENV=secret:version]
```

- Deploy images by digest (see `registry-dockerhub-ghcr`, `deploy-variants`). Canary: `--no-traffic --tag=TAG`, then move traffic.
- After one `--no-traffic` deploy, later deploys also get no traffic to LATEST: run `gcloud run services update-traffic SERVICE --to-latest` or set traffic explicitly [source](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).
- Verify: `gcloud run revisions list --service=SERVICE --region=REGION`, `gcloud run services describe SERVICE --format export`, `gcloud run services logs read SERVICE --limit=50`.
- Production deploy from CI on `main` or after the user's «да».

## Rollback

| What | Command | Notes |
|---|---|---|
| App | `gcloud run services update-traffic SERVICE --to-revisions REVISION=100` | Instant, needs the user's «да». Gradual: `--to-revisions LATEST=5`. |
| Back to newest | `gcloud run services update-traffic SERVICE --to-latest` | |
| Database | `gcloud sql instances clone SOURCE NEW --point-in-time 'TS'` | Prefer a clone or restore into a new instance. In-place `gcloud sql backups restore` overwrites all data and needs replicas deleted first [source](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restoring). |
| Infra | revert the IaC commit, new plan, human apply | `iac` |

Keep migrations backward-compatible (expand/contract): traffic rollback does not undo a schema change.

## More

- `references/iac.md`: provider, auth, GCS backend, WIF for CI, plan/apply split.
- `references/managed-services.md`: Cloud SQL, Memorystore, Cloud Storage, Artifact Registry, how Cloud Run connects.
- `references/pitfalls.md`: Bad/Good with sources.

## Not verified

- (`gcloud run services logs read` exists in GA, `--help` checked on 583.0.0.)
- Current Memorystore versions beyond the docs example (`redis_6_x`), Memorystore Cluster/Valkey.
- `gcloud storage buckets create` flags; the pinned hashicorp/google provider version.
