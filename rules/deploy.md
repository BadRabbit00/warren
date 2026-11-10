---
paths:
  - "deploy/**"
  - ".github/workflows/**"
---

# Build and delivery

## Scope

Build variants, CI, publishing, and rollout. Compose and local run are in `compose.md`; the full guide is the `deploy-variants` skill.

## Rules

- R-DEPLOY-SURVEY-FIRST: before touching the build, look at what exists: build scripts, Dockerfiles, compose files, `deploy/`, CI. Continue with what is there. Add a new way only on request.
- R-DEPLOY-DEFAULT: for Alexey's projects, a multi-stage Dockerfile to a distroless (or slim) non-root image, published to GHCR.
- R-DEPLOY-ALL-VARIANTS: when several build variants exist, one change updates all of them in the same commit: dependencies, runtime version, env, ports, entrypoint, healthcheck, user, volumes. Each touched variant is checked.
- R-DEPLOY-BUILD-ONCE: CI builds the artifact once and deploys by digest. The server never builds from `git pull`.
- R-DEPLOY-CI: on PR, run lint, types, tests with a real DB, every build variant, and an image smoke test. Actions and tools are pinned to versions. The publishing workflow is separate from the checking one; `pull_request_target` never runs PR code.
- R-DEPLOY-TAGS: image tags `sha-<short>`, `main`, `vX.Y.Z`; releases happen only from `main` after full CI, set by a human.
- R-DEPLOY-ROLLOUT: backup → migrations as a separate step → version switch → health check → main scenario. The rollback (previous digest or generation) is known before rollout. Production only with explicit permission.

## Examples

### R-DEPLOY-BUILD-ONCE — deploy by digest

Bad:
```yaml
- name: Deploy
  run: ssh prod 'cd /srv/app && git pull && docker compose up -d --build'
```
Why: the server compiles whatever `main` is right now; no reproducibility, downtime during the build, no rollback.

Good:
```yaml
- name: Deploy
  run: |
    ssh prod "sed -i 's|^API_IMAGE=.*|API_IMAGE=ghcr.io/org/app-api@${{ needs.build.outputs.digest }}|' /etc/app/release.env \
      && docker compose --env-file /etc/app/release.env up -d api"
```

### R-DEPLOY-CI — pinned tools

Bad:
```yaml
- uses: actions/checkout@main
- uses: golangci/golangci-lint-action@v6
  with: { version: latest }
```
Why: CI breaks or changes behaviour without any change in the repo.

Good:
```yaml
- uses: actions/checkout@<commit-sha>      # pinned; Dependabot bumps it
- run: golangci-lint run    # version pinned in the toolchain file
```
