---
name: deploy-variants
description: Use when building, packaging, or deploying a project - surveying existing build variants, choosing between Dockerfile + compose, distroless or slim image, podman Quadlet, or a plain systemd service, keeping several variants in sync, CI publishing, rollout and rollback, and verification.
---

# Deploy variants

How a project is built and delivered (source: `09-deploy`). Writer rules: `deploy.md`, `compose.md`. Secrets: `sops` skill and `secrets.md`.

## Contents

1. [Short version](#short-version) · 2. [Survey first](#survey-first) · 3. [Several variants](#several-variants) · 4. [Variants](#variants) · 5. [File layout](#file-layout) · 6. [Image and service properties](#image-and-service-properties) · 7. [CI, publishing, versions](#ci-publishing-versions) · 8. [Rollout and rollback](#rollout-and-rollback) · 9. [Verification](#verification) · 10. [Anti-patterns](#anti-patterns)

## Short version

1. Survey the repository before touching the build; reread the task; then act.
2. Variants: Dockerfile + compose, distroless or slim multi-stage image, podman + Quadlet, plain systemd service.
3. The user asks for several variants → make each one complete and verified.
4. The repository has several → maintain **all** of them; one build/run change goes into every variant in one commit.
5. New project, nothing requested → multi-stage Dockerfile (distroless or slim final stage) + compose.
6. CI builds the artifact once; deploys by digest; servers never build.
7. Secrets arrive at runtime; never in images or the repository.
8. Every variant is verified: builds, starts, passes the main scenario (smoke test).

## Survey first

| Look at | Meaning |
|---|---|
| `src/<component>/Dockerfile`, `.dockerignore` | image builds |
| `compose.yaml`, `docker-compose*.yml`, `compose.override.yaml` | compose runs; `docker-compose.prod.yml` for prod |
| `deploy/`: `*.container`, `*.network`, `*.volume`, systemd units, install scripts | Quadlet or systemd on servers |
| `.github/workflows/` | what CI builds, tests, publishes, on which events |
| `Makefile`, `justfile`, `README.md` | the commands people really use |

Then: the user named a variant → use it, even against the project's habit (say so). Not named → continue what exists; add nothing new unasked. New project → multi-stage Dockerfile + compose. State the variants in the plan in one line: «Сборка: Dockerfile + compose + Quadlet — обновлю все три».

## Several variants

Requested → each complete: working, verified, with a run command in the README. A placeholder "for later" is not a variant.

Existing → keep all in sync in one commit:
- dependencies (manifest and lock file);
- language/runtime version (Dockerfile base image and CI: same major.minor);
- env vars, ports, entry point, command, healthcheck;
- user, volumes, working dirs, read-only filesystem;
- migration step and start order;
- runtime system libraries and binaries.

Verify each touched variant; an unverified one is named in the report. A variant is never deleted without a direct request.

## Variants

| Variant | Result | When |
|---|---|---|
| Dockerfile + compose | multi-stage image, stack started by compose | default for anything with a server; local development |
| Distroless / slim final stage | OCI image with no shell or package manager (distroless) or a minimal base (slim) | anything going to a server; slim when a shell is needed |
| Podman + Quadlet | containers as systemd units | single server; instead of compose in prod |
| Plain systemd service | program or venv on the host, unit in `deploy/` | on request; CLIs and small agents without containers |

**Dockerfile + compose.** Rules in `compose.md`: multi-stage, non-root, pinned bases, `.dockerignore` per context, `127.0.0.1` ports, named volumes, healthchecks. Dockerfile in `src/<component>/`, build context = that folder; compose in the root. Base image and runtime versions match CI and the manifest (`requires-python`, `go.mod`, `engines`).

**Distroless image.** Build in a full stage, copy only the result into the final stage. One image per component (one image with several commands is fine for API + worker that must match).

```dockerfile
FROM python:3.13-slim AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY app ./app

FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY --from=build /app /app
USER 65532:65532
EXPOSE 8000
LABEL org.opencontainers.image.source="https://github.com/<org>/<project>"
ENTRYPOINT ["/app/.venv/bin/python", "-m", "app"]
```

Build and run: `docker compose up -d --build`; one image: `docker build -t ghcr.io/<org>/<project>-api:sha-<short> src/api`. Publish with `docker push` from CI. Healthcheck is a subcommand of the program (`python -m app healthcheck`), never `curl`.

**Podman + Quadlet.** `deploy/*.container|network|volume` installed into `/etc/containers/systemd/`; image by digest; limits in the unit:

```ini
[Container]
Image=ghcr.io/<org>/<project>-api@sha256:<digest>
EnvironmentFile=/etc/<project>/api.env
PublishPort=127.0.0.1:8000:8000
Volume=<project>-data:/var/lib/<project>
ReadOnly=true
User=10001
HealthCmd=/bin/api healthcheck
```

A server already on compose stays on compose; moving to Quadlet is a separate agreed task.

**Plain systemd service.** `deploy/<component>.service`: `DynamicUser` or a dedicated user, `StateDirectory`, `ProtectSystem=strict`, `NoNewPrivileges`, `Restart=on-failure`; secrets via `EnvironmentFile`/`LoadCredential` from a root-only path (see `sops`). Install and restart are done by the user; rollback = previous release directory or tag.

## File layout

`compose.yaml` and `.env.example` in the root. Dockerfile and `.dockerignore` in `src/<component>/`. Quadlet/systemd units and install/backup scripts in `deploy/`. Build and deploy code never goes into `src/` (except the Dockerfile's context). A service moved to its own repository takes its Dockerfile along.

## Image and service properties

Non-root (numeric `User`, `DynamicUser`) · read-only root filesystem; writes to volumes, `StateDirectory`, `/tmp` · a healthcheck that checks readiness · graceful SIGTERM (finish requests, close connections) · labels `org.opencontainers.image.revision|version|source` · no secrets in `ENV`/`ARG`/layers · configuration only from env and mounted files: one artifact for test and prod.

## CI, publishing, versions

- PR: linters, types, tests, every existing variant built, image smoke test. Publishing is a separate workflow with write rights; the checking one is read-only.
- Build once; servers pull images, never `git pull` and build.
- Registry GHCR; tags `sha-<short>`, `main`, `vX.Y.Z` (semver tag on a commit already in `main` with full CI; matches the version in code). Provenance attestation on publish.
- Deploy by digest. Layer cache in CI (`cache-from`/`cache-to`); heavy builds with limited parallelism.

## Rollout and rollback

- Production only with the user's permission for one concrete action.
- Order: backup → migrations as their own step → version switch → health check → main scenario; failure → rollback.
- The rollback is known and tested beforehand: previous digest, previous tag. Migrations are expand-then-contract so the previous code runs on the new schema during a rollback.
- Before switching, workers stop gracefully: unfinished jobs save state or return to the queue.

## Verification

| Variant | Check |
|---|---|
| any image | smoke test as on the server: non-root, read-only root, no capabilities, data only in the volume; starts, healthcheck green, main scenario passes |
| Dockerfile + compose | `docker compose config --quiet`; `docker compose up -d --build` with `.env` from `.env.example` brings everything up |
| Quadlet, systemd units | install on a scratch host or container, start via the unit, main scenario, restart, stop |

Tests that bypass the real way of running do not prove the deployment; packaging-dependent behaviour (subprocesses, paths, permissions, env) is checked on the built artifact.

## Anti-patterns

| Anti-pattern | Instead |
|---|---|
| writing a second Dockerfile without noticing one already exists | survey, continue the accepted variant |
| updating a dependency in one variant only | every variant, one commit |
| deleting the "extra" variant because it looks redundant | only on request |
| a TODO variant "for later" | complete and verified, or not at all |
| building on the server from `git pull` | CI builds, deploy by digest |
| deploying `latest` or `main` tags | digest or semver |
| secrets in Dockerfile `ENV` or image `config.Env` | runtime env file, `LoadCredential`, sops |
| `curl` healthcheck in a distroless image | the program's own healthcheck subcommand |
| "tests are green, so the image works" | smoke test of the image |
| migrations at the start of every replica | a separate migration step before the switch |
