# doctl: command and flag reference

Source: `doctl <command> --help` of doctl 1.169.0 (checked locally); rows marked "docs" come from https://docs.digitalocean.com/reference/doctl/ and were not run.
R = allowed for log-collector / deploy-error-reader (intended). E = deploy-engineer / ci-engineer. M = mutating.

## Global flags (every command)
`-t/--access-token`, `-u/--api-url`, `-c/--config`, `--context <name>`, `--http-retry-max N` (default 5, retries 429 and 5xx), `-o/--output text|json`, `--trace` (logs network activity: may show headers, do not use), `-v/--verbose`.
Config file: `~/.config/doctl/config.yaml` (default). Env: `DIGITALOCEAN_ACCESS_TOKEN`, `DIGITALOCEAN_CONTEXT` (docs).

## Auth and account
| Command | Notes |
|---|---|
| `doctl account get` (R) | alias `g`; `--format Email,Team,DropletLimit,EmailVerified,UUID,Status`, `--no-header`. Exit 1 without a token. |
| `doctl auth init` (user) | `--context <name>`; asks for the token (docs: `--access-token` or the env var saves it without asking). |
| `doctl auth login` | does not exist in doctl 1.169.0; use `auth init`. |
| `doctl auth list` (E) | lists contexts; output not checked for secrets: not verified. |
| `doctl auth token` (secret) | docs: prints the token. Never. |

## Apps (App Platform)
Aliases: `apps`, `app`, `a`.
| Command | Flags that matter |
|---|---|
| `doctl apps list` (R) | alias `ls`; `--format ID,Spec.Name,DefaultIngress,ActiveDeployment.ID,InProgressDeployment.ID,Created,Updated`, `--no-header`, `--with-projects` |
| `doctl apps get <app id>` (R) | alias `g`; same `--format` columns |
| `doctl apps list-deployments <app id>` (R) | alias `lsd`; `--format ID,Cause,Progress,Phase,Created,Updated`, `--no-header` |
| `doctl apps get-deployment <app id> <deployment id>` (R) | alias `gd`; same columns; `-o json` for full detail |
| `doctl apps logs <app> [component]` (R) | alias `l`; `--type build\|deploy\|run\|run_restarted\|autoscale_event` (default run), `--deployment <id>`, `--job-invocation <id>`, `--event-id <id>`, `--tail N` (default -1 = all), `-f/--follow` (blocks: never), `--no-prefix` |
| `doctl apps list-events <app id>` (E) | alias `lse`; `--event-type DEPLOYMENT,AUTOSCALING`, `--format ID,Type,DeploymentID,Created,Phase` |
| `doctl apps list-instances <app id>` (E) | alias `i` |
| `doctl apps list-alerts <app id>` (E) | |
| `doctl apps spec get <app id>` (E) | `--deployment <id>`, `--format yaml\|json` (default yaml) |
| `doctl apps spec validate <file>` (E) | `--schema-only` (no auth needed, docs) |
| `doctl apps propose` (E) | proposes a spec; flags not verified: `--help` |
| `doctl apps create-deployment <app id>` (M) | alias `cd`; `--force-rebuild`, `--wait`, `--format`, `--no-header` |
| `doctl apps update <app id>` (M) | alias `u`; `--spec <file\|->` (required), `--update-sources`, `--wait`, `--format`, `--no-header` |
| `doctl apps create` (M, docs) | `--spec`, `--project-id`, `--upsert`, `--update-sources`, `--wait`, `--wait-timeout` |
| `doctl apps restart <app id>` (M) | in the command list; flags not verified |
| `doctl apps delete <app id>` (M) | aliases `d`, `rm`; `-f/--force` skips confirmation |

Other `apps` subcommands in the list (not verified, `--help` first): cancel-event, cancel-job-invocation, console, get-event, get-job-invocation, list-buildpacks, list-job-invocations, list-regions, tier, update-alert-destinations, upgrade-buildpack, dev (beta). `apps console` opens a shell in the container: not for agents.

## Droplets, databases, registry, monitoring (E)
| Command | Notes |
|---|---|
| `doctl compute droplet list` / `get <id>` | `--format`, `--no-header`; list shows ID, name, IPs, memory, vCPUs, disk, region, image |
| `doctl databases list` / `get <id>` | cluster id, name, engine, version, nodes, region, status, size |
| `doctl databases connection <id>` (secret) | prints the connection URI and password (not verified masked; no `--show` flag in 1.169.0). Never for agents |
| `doctl registry get` | registry details |
| `doctl registry repository list-tags <repo>` | alias `lt`; `--format Tag,CompressedSizeBytes,UpdatedAt,ManifestDigest`, `--registry <name>` |
| `doctl registry repository list-v2` | repositories; flags not verified |
| `doctl registry login` (M) | writes docker credentials; docs: `--expiry-seconds`, `--read-only`, `--never-expire` |
| `doctl monitoring alert list` | alias `ls` |

## REST fallback for what doctl lacks (docs, not run)
- Rollback: `POST /v2/apps/{app_id}/rollback` body `{"deployment_id":"<id>"}` (optional `skip_pin`); `/rollback/validate` checks first; `/rollback/commit` or `/rollback/revert` ends a pinned rollback. Call with `curl`. Keep the token out of argv: `printf 'Authorization: Bearer %s\n' "$DIGITALOCEAN_ACCESS_TOKEN" | curl -H @- ...` (`-H` takes `<header/@file>`; `@-` for stdin not verified). Never echo the token; report the command with `<token>`, never expanded.
- App spec keys, `registry_type` (DOCR, DOCKER_HUB, GHCR), `deploy_on_push`: https://docs.digitalocean.com/products/app-platform/reference/app-spec/

## Sources
- https://docs.digitalocean.com/reference/doctl/reference/apps/ (logs, create-deployment, update, spec/validate)
- https://docs.digitalocean.com/reference/doctl/reference/account/get/
- https://docs.digitalocean.com/reference/doctl/reference/auth/init/ , /auth/login/
- https://docs.digitalocean.com/reference/doctl/reference/databases/connection/
- https://docs.digitalocean.com/products/app-platform/how-to/manage-deployments/
