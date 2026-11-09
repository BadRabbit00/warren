# docker and docker compose: command and flag reference

Source: `docker <command> --help` of docker 29.9.2 and compose 5.6.0 (checked locally). Official docs: https://docs.docker.com/reference/cli/docker/ and https://docs.docker.com/reference/cli/docker/compose/
R = allowed for log-collector / deploy-error-reader. E = deploy-engineer / ci-engineer. M = mutating.
Global: `-c/--context`, `-H/--host`. Compose global (before the subcommand): `-f/--file` (repeatable), `-p/--project-name`, `--env-file`, `--profile`, `--project-directory`. `--dry-run` exists on compose subcommands.

## Compose
| Command | Flags that matter |
|---|---|
| `docker compose ps` (R) | `-a`, `--status paused\|restarting\|removing\|running\|dead\|created\|exited`, `--filter status=`, `--format json\|table\|TEMPLATE`, `--services`, `-q`, `--no-trunc` |
| `docker compose logs` (R) | `-n/--tail` (default all), `--since`, `--until`, `-t`, `-f` (blocks), `--index`, `--no-color`, `--no-log-prefix` |
| `docker compose events` (E) | `--json`, `--since`, `--until` (without `--until` it streams) |
| `docker compose top` / `images` (E) | `images`: `--format`, `-q` |
| `docker compose config` (E) | `--quiet` (validate only), `--services`, `--images`, `--volumes`, `--networks`, `--profiles`, `--format yaml\|json`, `-o file`. `--environment`, `--variables` and the default full render show resolved values: not for readers |
| `docker compose pull` (M) | service names |
| `docker compose up` (M) | `-d`, `--no-deps`, `--force-recreate`, `--no-recreate`, `--build`, `--wait`, `--pull always\|missing\|never`, `--abort-on-container-exit` |
| `docker compose restart` / `stop` / `start` (M) | `-t seconds`, service names |
| `docker compose down` (M) | `-v/--volumes` (deletes volumes), `--rmi local\|all`, `--remove-orphans`, `-t` |

## Containers and images
| Command | Flags that matter |
|---|---|
| `docker ps` (E) | `-a`, `-f filter`, `--format`, `-n last`, `-l`, `-q`, `--no-trunc`, `-s` |
| `docker logs CONTAINER` (R) | `-n/--tail` (default all), `--since`, `--until`, `-t`, `-f` (blocks), `--details` |
| `docker inspect NAME\|ID` (E) | `-f/--format`, `--type`, `-s`. Full output includes `Config.Env` (secrets) |
| `docker events` (E) | `-f filter`, `--format`, `--since`, `--until` (`--until 0s` returns at once) |
| `docker top CONTAINER` (E) | ps options |
| `docker stats` (E) | `-a`, `--no-stream`, `--format`, `--no-trunc`. Streams unless `--no-stream` |
| `docker images` / `docker image inspect` (E) | `--format`, `--digests`; inspect: `-f` |
| `docker info` / `docker version` (E) | `--format`. `version --format '{{.Server.Version}}'` is the daemon check |
| `docker system df` (E) | `-v` |
| `docker manifest inspect IMAGE` (E) | `--verbose`; queries the registry |
| `docker buildx imagetools inspect IMAGE` (E) | `--format`, `--raw`; queries the registry |
| `docker start` / `stop` / `restart` / `rm` / `run` / `exec` (M) | `exec` runs code inside the container |

## Contexts
| Command | Notes |
|---|---|
| `docker context ls` (E) | `--format json`, `-q` |
| `docker context inspect [ctx]` (E) | `-f`; may include endpoint settings |
| `docker context create CTX` (M) | `--docker "host=...,ca=...,cert=...,key=...,skip-tls-verify"`, `--from`, `--description`. The `host=ssh://user@host` form: not verified |
| `docker context use CTX` (M) | changes the default for later commands; prefer `-c <ctx>` per command |

## Exit codes and environment
`docker version` exits 1 with `failed to connect to the docker API` when the daemon is unreachable. `DOCKER_HOST`, `DOCKER_CONTEXT`, `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`: not verified here; pass flags explicitly.
