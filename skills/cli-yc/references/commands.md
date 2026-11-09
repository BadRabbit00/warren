# yc: command and flag reference

Source: `yc <command> --help` of yc 1.25.0 (checked locally; the commands were not run against a real cloud).
Run as `yc ...`.
R = allowed for log-collector / deploy-error-reader. E = deploy-engineer / ci-engineer. M = mutating.
Most list commands: `--limit` (default 1000 items). Folder selection flag `--folder-id` is a global flag (not shown in the per-command help; usage: `[Global Flags...]`).

## Auth and config
| Command | Notes |
|---|---|
| `yc iam whoami` (R, intended; hook follows in T1) | login check, prints the subject. Exit 1 "Failed to get credentials" when logged out |
| `yc iam create-token` | prints a live IAM token. Never for agents. `--impersonate-service-account-id` exists (docs) |
| `yc config list` (R today) | prints the OAuth `token:` in plain text. Never paste the output |
| `yc config get folder-id` / `cloud-id` (E) | safe way to read context |
| `yc config profile list` (E) | profile names |
| `yc init` (M) | user runs it. Flags: `--federation-id`, `--userpool-id`, `--username`, `--endpoint`, `--region`, `--dpop` |

## Logging
| Command | Flags that matter |
|---|---|
| `yc logging group list` (R, intended; hook follows in T1) | `--limit` |
| `yc logging read <group-name\|id> [SINCE] [FILTER]` (R) | `--group-id`, `--group-name`, `--since`, `--until`, `--limit`, `-f/--follow`, `--levels`, `--filter`, `--resource-types`, `--resource-ids`, `--stream-names`, `--max-response-size` (default 3.5 MiB) |

Timestamps: `HH:MM:SS`, RFC-3339, or a duration (`2h`, `3h30m ago`). `--follow` cannot be combined with `--since`/`--until` (FINDINGS, not re-run).
Docs: <https://yandex.cloud/en/docs/logging/operations/read-logs>.

## Serverless Containers
| Command | Flags that matter |
|---|---|
| `yc serverless container list` (E) | `--limit` |
| `yc serverless container get` (E) | `<name\|id>`, `--id`, `--name` (aliases `describe`, `show`) |
| `yc serverless container revision list` (E) | `--container-id`, `--container-name`, `--limit` |
| `yc serverless container list-operations` (E) | `<name\|id>`, `--id`, `--name`, `--limit` |
| `yc serverless container revision deploy` (M) | `--container-id` or `--container-name`, `--image`, `--memory`, `--cores`, `--core-fraction`, `--concurrency`, `--execution-timeout`, `--service-account-id`, `--environment`, `--secret`, `--log-group-id/-name`, `--log-folder-id/-name`, `--min-log-level`, `--async-service-account-id`, `--async` |
| `yc serverless container rollback` (M) | `<name\|id>`, `--id`, `--name`, `--revision-id` (required), `--async` |
| `yc operation get` (E) | `OPERATION-ID...` |

Docs: <https://yandex.cloud/en/docs/cli/cli-ref/serverless/cli-ref/container/revision/deploy>, <https://yandex.cloud/en/docs/cli/cli-ref/serverless/cli-ref/container/rollback>. GitHub Action for deploys: <https://github.com/yc-actions/yc-sls-container-deploy>.

## Container Registry
| Command | Flags |
|---|---|
| `yc container registry list` (E) | `--limit`, `--page-token` |
| `yc container repository list` (E) | `--registry-id` or `--registry-name`, `--limit`, `--page-token` |
| `yc container image list` (E) | `--registry-id` or `--registry-name`, `--repository-name`, `--limit`, `--page-token` |

Registry authentication for docker: <https://yandex.cloud/en/docs/container-registry/operations/authentication> (not run).

## Managed PostgreSQL / Redis
| Command | Flags |
|---|---|
| `yc managed-postgresql cluster list` (E) | `--limit` |
| `yc managed-postgresql cluster get` (E) | `<name\|id>`, `--id`, `--name`, `--full` (also default and effective configs) |
| `yc managed-postgresql cluster list-logs` (E) | `<name\|id>`, `--service-type postgresql\|pooler\|repack`, `--columns`, `--filter`, `--since`, `--until` (exclusive with `--follow`), `--follow`, `--limit` |
| `yc managed-postgresql cluster list-operations` (E) | `<name\|id>`, `--limit` |
| `yc managed-redis cluster list` (E) | `--limit` |
| `yc managed-redis cluster list-logs` (E) | `--service-type redis`, `--columns`, `--filter`, `--since`, `--until`, `--follow`, `--limit` |

Docs: <https://yandex.cloud/en/docs/managed-postgresql/operations/cluster-logs>.

## Compute and resource manager
| Command | Flags |
|---|---|
| `yc compute instance list` (E) | `--limit` |
| `yc compute instance get-serial-port-output` (E) | `<name\|id>`, `--id`, `--name`, `--port` |
| `yc resource-manager folder list` (E) | `--limit` |
