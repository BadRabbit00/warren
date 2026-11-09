---
name: cloud-digitalocean
description: Use when a project deploys to or considers DigitalOcean - App Platform with an app spec, managed databases, Spaces, Container Registry - the doctl login check, deploy by image digest or unique tag, rollback through the API, OpenTofu with the digitalocean provider, plan in CI and human apply.
---

# Cloud: DigitalOcean

Provider skill. Commands: `cli-doctl`. IaC basics: `iac`. Secrets: `sops`, `secrets.md`. Images: `registry-dockerhub-ghcr`, `docker-patterns`. CI: `ci-github-actions`.

## When to choose

- App Platform deploys an app described by one spec file (services, workers, jobs, static sites, databases, envs, domains) and can pull images from DOCR, Docker Hub or GHCR [source](https://docs.digitalocean.com/products/app-platform/reference/app-spec/).
- Managed databases for PostgreSQL, MySQL, Redis, Valkey, MongoDB, Kafka, OpenSearch; S3-compatible Spaces [source](https://docs.digitalocean.com/reference/doctl/reference/databases/create/).
- Limits from the research: Spaces does not support cross-region copy, tag-based lifecycle rules or bucket-level encryption (only SSE-C) [source](https://docs.digitalocean.com/products/spaces/reference/s3-compatibility/); App Platform rollback reaches only the 10 most recent successful deployments and restores no database data [source](https://docs.digitalocean.com/products/app-platform/how-to/manage-deployments/); doctl has no rollback command.

## CLI and login check (D3)

Run: `nix shell nixpkgs#doctl -c doctl ...` (see `cli-doctl`).

1. `nix shell nixpkgs#doctl -c doctl account get --format Email,Status --no-header`. The exit code with a bad token is not documented (non-zero expected, not verified): treat an error message or empty output as "not logged in".
2. `DIGITALOCEAN_ACCESS_TOKEN` (CI) applies only to the `default` context; a named context or `DIGITALOCEAN_CONTEXT` ignores it, and `doctl auth init` would overwrite the stored default token with it [source](https://github.com/digitalocean/doctl). In CI use only the env var and do not run `auth init`.
3. Not logged in: stop with `STATUS: blocked — login needed` and give the user `! nix shell nixpkgs#doctl -c doctl auth login --no-browser` (OAuth) or `! nix shell nixpkgs#doctl -c doctl auth init` (asks for a token). Never run them, never ask for a token in chat.

## Deploy

1. Build and push an image with a unique tag or digest (never reuse `:latest`): `doctl registry login`, `docker push registry.digitalocean.com/<registry>/<image>:<sha>`.
2. Set the tag in the spec, validate: `doctl apps spec validate app.yaml` (`--schema-only` needs no auth).
3. Update: `doctl apps update <app id> --spec app.yaml --wait --wait-timeout 30m`. By default it does not fetch new sources or images. `doctl apps create-deployment <app id> [--force-rebuild] --wait` redeploys.
4. Verify: `doctl apps list-deployments <app id>`, `doctl apps get-deployment <app id> <deployment id>`, `doctl apps logs <app> web --type deploy`.
5. When `--wait-timeout` expires, doctl exits with an error but the deployment keeps running: check the real state before reporting failure.

Production deploy from CI on `main` or after the user's «да».

## Rollback

doctl has none; use the REST API (needs the user's «да») [source](https://docs.digitalocean.com/reference/pydo/reference/apps/validate_rollback/):

1. Candidate ids: `doctl apps list-deployments <app id>` (the 10 most recent successful ones are valid).
2. Validate: `POST /v2/apps/{app_id}/rollback/validate` with `{"deployment_id":"<id>"}`.
3. Roll back: `POST /v2/apps/{app_id}/rollback`, e.g. `nix shell nixpkgs#curl -c curl -X POST -H "Authorization: Bearer $DIGITALOCEAN_ACCESS_TOKEN" -H "Content-Type: application/json" -d '{"deployment_id":"<id>"}' https://api.digitalocean.com/v2/apps/<app id>/rollback`.
4. A pinned rollback blocks new deployments, including deploy-on-push, until `/rollback/commit` or `/rollback/revert` (or `skip_pin: true` to commit at once).

Database data and migrations are not rolled back: keep migrations backward-compatible; restore data into a new cluster (`doctl databases create <new> --engine pg --restore-from-cluster-name <src> --restore-from-timestamp '...'`).
Dashboard alternative: app > Activity > Rollback.

## More

- `references/iac.md`: digitalocean provider, Spaces state, plan/apply split.
- `references/managed-services.md`: databases, Spaces, DOCR, how the app gets connection values.
- `references/pitfalls.md`: Bad/Good with sources.

## Not verified

- Exit code of `doctl account get` with a bad token.
- Current provider version (docs example `~> 2.0`).
- Default lifetime of `doctl registry login` credentials (docs contradict themselves).
- How to read managed database logs (no `doctl databases logs`).
