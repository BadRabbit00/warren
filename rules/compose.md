---
paths:
  - "compose.yaml"
  - "compose.yml"
  - "compose.*.yaml"
  - "docker-compose*.yml"
  - "docker-compose*.yaml"
  - "**/Dockerfile"
  - "**/.dockerignore"
  - ".env.example"
---

# Compose, images, and the local stack

## Scope

How a project starts locally and what the containers look like. Build variants and release flow are in `deploy.md`; the full guide is the `deploy-variants` skill.

## Rules

- R-COMPOSE-THREE-COMMANDS: `cp .env.example .env && docker compose build && docker compose up -d` brings up everything: services, DB, cache, workers, proxy, plus applied migrations and seeds. Anything else needed is a bug.
- R-COMPOSE-OWN-IMAGES: our services use `build:` with a multi-stage Dockerfile to a distroless (or slim) non-root image; third-party services use `image:`.
- R-COMPOSE-PINNED: third-party images carry an exact tag (`postgres:17-alpine`). Never `latest` or a tag without a version.
- R-COMPOSE-HEALTH: every long-running service has a `healthcheck`. `depends_on` uses `condition: service_healthy`, or `service_completed_successfully` for one-shot jobs (`migrate`, bucket init), which get `restart: "no"`.
- R-COMPOSE-MIGRATE-STEP: migrations and idempotent seeds run in a separate `migrate` service that API and workers depend on. Replicas never migrate on startup.
- R-COMPOSE-PORTS: publish only what a human opens, bound to `127.0.0.1` with an overridable non-default port: `"127.0.0.1:${API_HOST_PORT:-18000}:8000"`. Workers, Redis, and internal services publish nothing. Services reach each other by service name, never `localhost`.
- R-COMPOSE-VOLUMES: data lives only in named volumes. Bind mounts are for dev sources and read-only configs.
- R-COMPOSE-ENV: settings come from `.env`; required ones use `${VAR:?hint}`. `.env.example` lists every variable with a working local value (`change-me-…` for secrets). External integrations without keys must not break startup.
- R-COMPOSE-NONROOT: containers run as non-root, with exec-form `CMD`/entrypoint so SIGTERM reaches the process.
- R-COMPOSE-NO-DESTROY: `down -v`, `volume rm/prune` destroy data. Never run them without a named list and the user's "да".

## Examples

### R-COMPOSE-HEALTH — wait for readiness

Bad:
```yaml
api:
  image: app-api:dev
  depends_on: [postgres]          # starts as soon as the container exists
  ports: ["8000:8000"]            # 0.0.0.0, fixed port
```
Why: the API crashes on startup before Postgres accepts connections, and the port is open to the LAN.

Good:
```yaml
api:
  image: app-api:dev
  depends_on:
    migrate: { condition: service_completed_successfully }
    redis: { condition: service_healthy }
  ports: ["127.0.0.1:${API_HOST_PORT:-18000}:8000"]
  healthcheck: { test: ["CMD", "/bin/api", "healthcheck"], interval: 10s, retries: 10 }
```

### R-COMPOSE-PINNED — exact image tags

Bad:
```yaml
redis:
  image: redis
```
Why: the next pull can bring a new major version with different persistence defaults.

Good:
```yaml
redis:   # Celery broker + OTP codes → AOF and noeviction
  image: redis:7-alpine
  command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
  volumes: ["redis-data:/data"]
  healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, retries: 20 }
```
