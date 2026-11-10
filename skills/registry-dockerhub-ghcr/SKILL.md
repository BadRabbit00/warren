---
name: registry-dockerhub-ghcr
description: Use when pushing, pulling, pinning or rolling back container images on GHCR (ghcr.io) or Docker Hub - choosing a registry, the login check with skopeo, pushing images from a multi-stage Dockerfile (distroless or slim), pinning by digest, retagging for rollback, CI publishing permissions, rate limits and retention.
---

# Registry: GHCR and Docker Hub

Provider skill for image registries. Build side: `deploy-variants` (variants, publishing), `docker-patterns` (Dockerfile, compose). Tool commands: `cli-docker` (docker, buildx), `cli-gh`. CI jobs: `ci-github-actions`. Secrets: `sops`, `secrets.md`.

## When to choose

| Registry | Choose when | Facts |
|---|---|---|
| GHCR `ghcr.io/OWNER/IMAGE` | The code is on GitHub and CI publishes it | CI logs in with `GITHUB_TOKEN` (`packages: write`), no stored secret. A new package is private; a package created by a workflow with `GITHUB_TOKEN` inherits the repository's visibility and permissions [source](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions). |
| Docker Hub `docker.io/USER/IMAGE` | Public images that must be pullable by default Docker configs, or the team already uses it | Needs a stored token (PAT, or organization access token for CI). Pull limits per 6 hours: 100 anonymous (per IPv4 or IPv6 /64), 200 authenticated Personal [source](https://docs.docker.com/docker-hub/usage/). |
| Cloud-owned (DOCR, Artifact Registry, `cr.yandex`) | The deploy target is that cloud | See `cloud-digitalocean`, `cloud-gcp`, `cloud-yandex`. Spec can also pull GHCR/Docker Hub on DigitalOcean. |

Always write the full name: a reference without a registry host silently becomes `docker.io/library/<name>` [source](https://github.com/containers/image/blob/main/docs/containers-transports.5.md).

## Login check (D3)

Check first that skopeo is installed (`skopeo --version`); missing: `STATUS: blocked — install needed (requirements.md)`. Docker has no documented login-state command; use skopeo [source](https://github.com/containers/skopeo/blob/main/docs/skopeo-login.1.md):

```
skopeo login --get-login ghcr.io      # prints the user, errors when not logged in
skopeo login --get-login docker.io
```

`--get-login` also reads `~/.docker/config.json` (verified with skopeo 1.24.1: exit 0 on a fake entry). But `skopeo login` by default writes to `${XDG_RUNTIME_DIR}/containers/auth.json`, which docker and buildx do not read: for a login that `docker buildx imagetools` also sees, add `--compat-auth-file ~/.docker/config.json` (`skopeo login --help`). Reading public images needs no login (`skopeo inspect --no-creds docker://...`).

Not logged in and a push or private pull is needed: stop with `STATUS: blocked — login needed` and give the user one of

- `! skopeo login --compat-auth-file ~/.docker/config.json -u <github-user> ghcr.io` (asks for a PAT; classic PAT scopes `read:packages`, `write:packages`, `delete:packages`; create it from `https://github.com/settings/tokens/new?scopes=write:packages` so `repo` is not added)
- `! skopeo login --compat-auth-file ~/.docker/config.json -u <user> docker.io` (PAT or organization access token)

Never run it, never ask for the token in chat, never pass it in argv. In CI: `docker/login-action` with `GITHUB_TOKEN` (ghcr) or `secrets.DOCKERHUB_TOKEN` (Hub). Credentials without a credential store sit base64-encoded in `~/.docker/config.json` (not encrypted): CI jobs log out at the end (`logout: true` is the login-action default) [source](https://docs.docker.com/reference/cli/docker/login/).

## Push

- With a daemon, CI: `docker/build-push-action` with an `id`, then use `steps.<id>.outputs.digest` (see `ci-github-actions`).
- Image without a daemon, for example an OCI archive built by buildkit (`docker buildx build --output type=oci,dest=image.tar`) [source](https://github.com/containers/skopeo/blob/main/docs/skopeo-copy.1.md):

```
skopeo copy oci-archive:./image.tar docker://ghcr.io/OWNER/IMAGE:TAG --digestfile digest.txt
```

  Build the image from a multi-stage Dockerfile: build stage with the toolchain, final stage `gcr.io/distroless/*` or a slim base, non-root user (`docker-patterns`). The archive transport was not run in the research: test once.
- Record the pushed digest (`--digestfile`) and deploy by `@sha256:<digest>`. Use `--preserve-digests` when copying between registries so a digest change fails loudly.
- Link a GHCR package to its repository: labels `org.opencontainers.image.source=https://github.com/OWNER/REPO`, `.description` (<= 512 chars), `.licenses` (SPDX, <= 256 chars) [source](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry). For multi-arch put the description in manifest `annotations`.  Set the labels with `LABEL` in the Dockerfile or `labels:` in `docker/build-push-action`.

## Pin and read

```
skopeo inspect docker://ghcr.io/OWNER/IMAGE:TAG        # Digest, RepoTags
skopeo list-tags docker://ghcr.io/OWNER/IMAGE
```

Pull and deploy by `ghcr.io/OWNER/IMAGE@sha256:<digest>`; the `docker://` transport takes `name:tag` or `name@digest`, not both. Tags are mutable pointers; digests are the identity.

## Rollback

Deploys that reference digests roll back by pointing to the previous digest (best option). To move a tag back without rebuilding (user's «да» for a prod tag) [source](https://docs.docker.com/reference/cli/docker/buildx/imagetools/create/):

```
docker buildx imagetools create -t REG/IMAGE:prod REG/IMAGE@sha256:<old>        # --dry-run previews; uses the ~/.docker/config.json login
skopeo copy --all docker://REG/IMAGE@sha256:<old> docker://REG/IMAGE:prod     # daemonless
```

A deleted GHCR version can be restored within 30 days if the namespace and version are unused: `POST /users/{username}/packages/container/{name}/versions/{id}/restore` (or `/orgs/`), classic PAT with `read:packages` and `write:packages` [source](https://docs.github.com/en/rest/packages/packages).

## IaC and managed services

None found in the research for registries: GHCR visibility is changed in the package settings UI (a REST/CLI command was not verified); Docker Hub tokens and repositories are created in the Hub UI. Do not add Terraform for them without a documented provider and the user's decision. Registry credentials live only in CI secrets or `sops`, never in the repo.

## More

`references/ci-and-retention.md` (CI permissions, attestations, retention, rate-limit check) and `references/pitfalls.md` (Bad/Good with sources).

## Not verified

- Docker Hub PAT / organization token scope names and expiry options; paid-plan limits.
- Whether `GITHUB_TOKEN` or fine-grained PATs work with the Packages REST API (docs say classic PAT).
- `skopeo logout` syntax; pinned SHAs of `docker/*` actions (collect them when pinning).
