# Registries: CI publishing, retention, rate limits

Workflow hygiene (permissions, SHA pinning, `persist-credentials: false`, concurrency): `ci-github-actions`.

## Publish job (GHCR)

Permissions of the publish job: `contents: read`, `packages: write`; add `attestations: write` and `id-token: write` for `actions/attest@v4` (inputs `subject-name`, `subject-digest: ${{ steps.push.outputs.digest }}`, `push-to-registry: true`). GitHub recommends pinning actions to a commit SHA and prefers `GITHUB_TOKEN` over a classic PAT [source](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions).

Action majors seen in the research (pin by full SHA when writing; the SHAs were not collected): `docker/login-action@v4`, `docker/setup-qemu-action@v4`, `docker/setup-buildx-action@v4`, `docker/build-push-action@v7` [source](https://github.com/docker/build-push-action).

- login: `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}` (Docker Hub: `username: ${{ vars.DOCKERHUB_USERNAME }}`, `password: ${{ secrets.DOCKERHUB_TOKEN }}`) [source](https://github.com/docker/login-action).
- build: `id: push`, `platforms: linux/amd64,linux/arm64`, `push: true`, `tags:`; outputs `digest`, `imageid`, `metadata`; `provenance: true` and `sbom: true` add attestations.
- Pass the digest to the deploy job as a job output, deploy `@sha256:<digest>`.
- Existing package or one created elsewhere: grant the repository write access under the package's "Manage Actions access" (Admin to delete), otherwise `GITHUB_TOKEN` pushes are denied [source](https://github.com/docker/login-action).

## Retention

`actions/delete-package-versions@v5`: `package-name`, `package-type: container`, `min-versions-to-keep: N`, `delete-only-untagged-versions: 'true'`, `ignore-versions: <regex>`. The token needs the delete-packages scope (and read-packages when `package-version-ids` is not set); the repository needs Admin in Manage Actions access [source](https://github.com/actions/delete-package-versions).

Multi-arch builds and provenance leave untagged per-platform and attestation manifests; deleting all untagged versions can break tagged multi-arch images. Use `min-versions-to-keep` or `ignore-versions`, or a manifest-aware tool [source](https://github.com/docker/build-push-action/issues/894).

## Docker Hub rate limit (read-only check)

A HEAD request does not count against the limit [source](https://docs.docker.com/docker-hub/usage/pulls/):

```
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:ratelimitpreview/test:pull" | jq -r .token)
curl --head -H "Authorization: Bearer $TOKEN" https://registry-1.docker.io/v2/ratelimitpreview/test/manifests/latest
# read the ratelimit-limit and ratelimit-remaining headers (w=21600 is the window in seconds)
```

The anonymous check above is enough for an agent. An authenticated limit needs a credential, and `curl --user user:token` puts it in argv (process list, shell history): if it is needed, the user runs it with a `--netrc-file` (exists in curl `--help all`) from a sops-decrypted file, never an agent. In CI log in before pulling.

## GHCR package listing

`gh api /user/packages/container/NAME/versions` (or `/orgs/{org}/...`) needs a classic PAT with `read:packages` [source](https://docs.github.com/en/rest/packages/packages). Commands: `cli-gh`.
