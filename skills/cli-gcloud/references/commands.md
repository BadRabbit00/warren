# gcloud: command and flag reference

Source: `gcloud <command> --help` of gcloud 583.0.0 (checked locally; the commands were not run against a real project).
R = allowed for log-collector / deploy-error-reader. E = deploy-engineer / ci-engineer. M = mutating.
Every command takes the global flags `--project`, `--format`, `--quiet` (not listed in each synopsis; `--project` and `--format` are used in the help examples; `--quiet` not verified).

## Auth and config
| Command | Notes |
|---|---|
| `gcloud auth list` (R) | `--filter=EXPRESSION`, `--filter-account`, `--limit`. Use `--filter=status:ACTIVE --format="value(account)"`; empty output = logged out, exit 0 |
| `gcloud auth login` (M) | user runs it: `--no-launch-browser`, `--no-browser`, `--cred-file`, `--update-adc` |
| `gcloud auth activate-service-account` | key-file login: not for agents (secret key; CI uses Workload Identity Federation via `google-github-actions/auth`) |
| `gcloud auth print-access-token` | prints a live token. Never for agents |
| `gcloud config list` (E) | `--all`, `SECTION/PROPERTY` |
| `gcloud config get-value` (E) | `SECTION/PROPERTY`, e.g. `core/project` |
| `gcloud projects list` (E) | `--filter`, `--limit` |

## Cloud Run
| Command | Flags that matter |
|---|---|
| `gcloud run services list` (E) | `--region`, `--filter`, `--limit`, `--sort-by`, `--uri` |
| `gcloud run services describe SERVICE` (E) | `--region`, `--namespace` |
| `gcloud run services logs read SERVICE` (R, intended; hook follows in T1) | `--freshness` (default 1d), `--log-filter`, `--order` (default desc), `--region`, `--limit` |
| `gcloud run revisions list` (E) | `--service`, `--region`, `--filter`, `--limit`, `--sort-by`, `--uri` |
| `gcloud run revisions describe REVISION` (E) | `--region` |
| `gcloud run services update-traffic [SERVICE]` (M) | `--to-revisions=REV=PERCENT,...` (`LATEST` allowed), `--to-latest`, `--to-tags`, `--set-tags`, `--update-tags`, `--remove-tags`, `--clear-tags`, `--async`, `--region` |
| `gcloud run deploy [SERVICE]` (M) | `--image`, `--source`, `--region`, `--no-traffic`, `--tag`, `--revision-suffix`, `--set-env-vars`, `--update-env-vars`, `--set-secrets`, `--add-cloudsql-instances`, `--service-account`, `--min-instances`, `--max-instances`, `--memory`, `--cpu`, `--port`, `--timeout`, `--[no-]allow-unauthenticated`, `--async` |

Rollback = `update-traffic --to-revisions=<good>=100` (examples in the `--help` text). Docs: <https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration>.
Cloud Run logs and log filter fields: <https://docs.cloud.google.com/run/docs/logging>.

## Logging
| Command | Flags that matter |
|---|---|
| `gcloud logging read [LOG_FILTER]` (R) | `--freshness` (default 1d), `--order` (default desc), `--limit`, `--project` / `--folder` / `--organization` / `--billing-account`, `--resource-names`, `--bucket` + `--location` + `--view`, `--format` |

Filter examples from the help: `severity>=ERROR`, `resource.type=gce_instance`, `timestamp>="2015-05-31T00:00:00Z" AND timestamp<="2015-05-31T23:59:59Z"`, `textPayload:SyncAddress`.
Cloud Run: `resource.type="cloud_run_revision" AND resource.labels.service_name="<service>"` (field names from the docs page above; not run locally).

## Builds, registry, secrets
| Command | Flags that matter |
|---|---|
| `gcloud builds list` (E) | `--ongoing`, `--region`, `--filter`, `--limit` (default 50), `--sort-by`, `--uri` |
| `gcloud builds log BUILD` (E) | `--region`, `--stream` (blocks while the build runs) |
| `gcloud artifacts docker images list [IMAGE_PATH]` (E) | `--include-tags`, `--show-occurrences`, `--filter`, `--limit`, `--sort-by` |
| `gcloud secrets list` (E) | `--location`, `--filter`, `--limit`, `--page-size` (default 100). Names only |

## Cloud SQL
| Command | Flags that matter |
|---|---|
| `gcloud sql instances list` (E) | `--filter`, `--limit`, `--sort-by`, `--uri` |
| `gcloud sql instances describe INSTANCE` (E) | `--format` |
| `gcloud sql backups list` (E) | `--instance` / `-i`, `--filter`, `--limit` |
| `gcloud sql operations list` (E) | `--instance` / `-i` (required), `--filter`, `--limit` |

Restore docs (not run): <https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restoring>.

## Environment
`CLOUDSDK_CONFIG` points gcloud at another config directory (used to test the logged-out state with an empty dir). Other `CLOUDSDK_*` variables: not verified.
Credentials for libraries (Application Default Credentials) are separate from `gcloud auth`: <https://docs.cloud.google.com/docs/authentication/application-default-credentials>.
