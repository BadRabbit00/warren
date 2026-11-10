---
name: cli-docker
description: Use when you must read container and Compose state (ps, logs, events, inspect, images, contexts, remote manifests) with the docker CLI, or hand off an up, restart or rollback to deploy-engineer.
---

# docker and docker compose: container state and logs

Verified locally with docker 29.9.2 and compose 5.6.0 (`--help` of every command below). Full flag tables: `references/commands.md`.
Who: `R` = allowed for `log-collector` and `deploy-error-reader` (intended allowlist: `docker compose ps`, `docker compose logs`, `docker logs`). `E` = read-only, but only for `deploy-engineer` / `ci-engineer`. `M` = mutating, those two only, after the user's «да» for the command.

## 1. Run

Always `nix shell nixpkgs#docker -c docker <args>` (the compose plugin is in the same package). Never a bare `docker`, never an install script piped into a shell.
Compose project: `-f <file>` (repeatable), `-p <project>`, `--env-file`, `--profile` go BEFORE the subcommand: `docker compose -f compose.prod.yaml -p app ps`.
Remote host: `docker -c <context> …` or `-H ssh://user@host` (ssh form: not verified). Always name the target; the default context may be the wrong machine.
Streams (`logs -f`, `events`, `stats`) are bounded (see 5); `timeout` goes BEFORE nix.

## 2. Login check FIRST

```
nix shell nixpkgs#docker -c docker version --format '{{.Server.Version}}'
```
- exit 0 and a version number = the daemon answers.
- exit 1 and `failed to connect to the docker API` = stop: the daemon is down, the socket is not reachable, or the wrong context is active. Check `docker context ls` once, then report.

This is a daemon check, not a registry login. Registry login (private images) is the user's: `! nix shell nixpkgs#docker -c docker login <registry>`. Never run `docker login` yourself and never print `~/.docker/config.json`.

## 3. Read-only commands

### Is it running, why did it stop (R)
```
nix shell nixpkgs#docker -c docker compose -f <file> ps -a --format json
nix shell nixpkgs#docker -c docker compose -f <file> ps -a --status exited
nix shell nixpkgs#docker -c docker compose -f <file> ps --services
```
Look at `State`, `ExitCode`, `Health` in the JSON. A restarting container shows `restarting`.

### Logs (R)
```
nix shell nixpkgs#docker -c docker compose -f <file> logs --tail 200 --since 30m -t <service>
nix shell nixpkgs#docker -c docker logs --tail 200 --since 30m -t <container>
```
- Always `--tail N` (default is `all`). Add `--until <t>` to cut a window. `--no-color --no-log-prefix` give clean text.
- Never `-f/--follow` without `timeout`: `timeout 30 nix shell nixpkgs#docker -c docker logs -f --tail 50 <container>`.
- `--index N` picks one replica of a scaled service.

### Why did it exit: exit code, OOM, health (E)
```
nix shell nixpkgs#docker -c docker inspect <container> --format '{{json .State}}'
nix shell nixpkgs#docker -c docker events --since 1h --until 0s --filter container=<name> --filter event=die --filter event=oom
nix shell nixpkgs#docker -c docker compose -f <file> events --since 1h --until 0s --json
```
`.State` has `ExitCode`, `OOMKilled`, `Error`, `StartedAt`, `FinishedAt`, `Health`. `--until 0s` makes `events` return at once.

### Config, images, resources (E)
```
nix shell nixpkgs#docker -c docker compose -f <file> config --quiet        # validates only, prints nothing
nix shell nixpkgs#docker -c docker compose -f <file> config --services     # names only
nix shell nixpkgs#docker -c docker compose -f <file> config --images       # image names only
nix shell nixpkgs#docker -c docker compose -f <file> images
nix shell nixpkgs#docker -c docker compose -f <file> top
nix shell nixpkgs#docker -c docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
nix shell nixpkgs#docker -c docker stats --no-stream --format json
nix shell nixpkgs#docker -c docker system df
nix shell nixpkgs#docker -c docker image inspect <image> --format '{{.Id}} {{.Created}}'
nix shell nixpkgs#docker -c docker version --format '{{.Server.Version}}'
```

### Remote image and contexts (E)
```
nix shell nixpkgs#docker -c docker manifest inspect <image:tag>
nix shell nixpkgs#docker -c docker buildx imagetools inspect <image:tag>
nix shell nixpkgs#docker -c docker context ls --format json
```
Does a tag exist in the registry, and its digest: use these before blaming the deploy. `context inspect` may list endpoint settings: read only the name and host.

## 4. Mutating commands: only deploy-engineer / ci-engineer, only after the user's «да» for this command (prod: «да» per command)

Readers never run these. A reader that thinks one is needed reports it to the orchestrator.
```
nix shell nixpkgs#docker -c docker compose -f <file> pull <service>
nix shell nixpkgs#docker -c docker compose -f <file> up -d --no-deps <service>   # M: recreates the service
nix shell nixpkgs#docker -c docker compose -f <file> restart <service>           # M
nix shell nixpkgs#docker -c docker compose -f <file> stop <service>              # M
nix shell nixpkgs#docker -c docker compose -f <file> down                        # M: removes containers and networks
nix shell nixpkgs#docker -c docker context create <name> --docker "host=ssh://user@host"   # M: ssh form not verified
nix shell nixpkgs#docker -c docker exec <container> <cmd>                        # M: runs code in production
```
- `compose down -v` / `--volumes` deletes named volumes (data): never without an explicit request; `--rmi all` and `--remove-orphans` also delete. `docker rm`, `docker run`, `docker system prune`: M.
- `--dry-run` is a compose option on its commands: use it first.
- Rollback = `up -d` with the previous image tag or digest (read it from `images` or the registry first). There is no `docker rollback`.
- Before `up` or `down` say what will be recreated or removed, and run only after the user's «да».

## 5. Patterns and anti-patterns

Bad: `docker logs <c>` or `docker compose logs` (the default tail is `all`: floods the context)
Good: `docker logs --tail 200 --since 30m <c>`

Bad: `docker logs -f <c>`, `docker events`, `docker stats` with no bound (never return)
Good: `timeout 30 nix shell nixpkgs#docker -c docker logs -f --tail 50 <c>`; `docker events --since 1h --until 0s`; `docker stats --no-stream`

Bad: the full render of the compose file, `docker compose config --environment` (resolved env: passwords, tokens)
Good: `docker compose config --quiet`, `--services`, `--images`

Bad: `docker inspect <c>` whole, `--format '{{.Config.Env}}'` (environment variables with secrets)
Good: `docker inspect <c> --format '{{json .State}}'`; or `{{.Config.Image}}`

Bad: `docker context inspect` pasted into a report, `cat ~/.docker/config.json` (registry auth)
Good: `docker context ls --format json`, only name and host

Bad: `docker compose ps` with no `-f`/`-p` in the wrong directory (shows an empty or wrong project)
Good: `-f <file> -p <project>` on every compose command

Bad: `docker exec <c> env`, `docker exec <c> cat .env`
Good: do not; `exec` is M, and prints secrets

Bad: `docker compose down -v` to "fix" a service
Good: `restart <service>` after the user's «да»; `down -v` only when the user named the data loss

Bad: judge by `docker ps` alone (the container is "Up" while unhealthy)
Good: `compose ps --format json` and read `Health`; `.State.Health` in inspect

Bad: table output parsed with grep/awk
Good: `--format json` or a Go template

## 6. Report shape (collectors)

Put in the report:
- source: `docker compose logs` / `docker logs` / `docker inspect`, the context or host, compose file and project, service, container id
- the exact command line and its exit code
- state facts: `State`, `ExitCode`, `OOMKilled`, `Health`, `FinishedAt`, image tag and digest
- the log excerpt (at most ~40 lines) with line numbers (`cat -n`) and the time range

Do not put in the report:
- the whole log, or output of `config`, `inspect` or `exec` that contains environment variables
- passwords, tokens, connection strings, registry auth (write `<redacted>`)
- guesses about the cause: write "observed" lines only; a cause is a hypothesis, labelled as one
