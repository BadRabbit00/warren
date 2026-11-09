# Registries: pitfalls

Bad:
```
skopeo copy docker-archive:./result docker://myimage:1.0         # no host: resolves to docker.io/library/myimage
```
Good:
```
skopeo copy docker-archive:./result docker://ghcr.io/OWNER/IMAGE:1.0 --digestfile digest.txt
```
[source](https://github.com/containers/image/blob/main/docs/containers-transports.5.md)

Bad:
```
docker login ghcr.io -u me -p <token>      # token in argv and shell history
```
Good:
```
# CI: docker/login-action with GITHUB_TOKEN (logout: true is the default); or a token piped on stdin: --password-stdin
# human: the user runs `! skopeo login -u <user> ghcr.io` and types the token at the prompt
```
Without a credential store the token is stored base64-encoded in `~/.docker/config.json`. [source](https://docs.docker.com/reference/cli/docker/login/)

Bad:
```
# classic PAT created with write:packages from the Settings UI checkboxes: also gets the full `repo` scope
```
Good:
```
https://github.com/settings/tokens/new?scopes=write:packages      # or GITHUB_TOKEN in Actions
```
[source](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

Bad:
```
skopeo copy --format v2s2 docker://src/IMAGE:1 docker://dst/IMAGE:1     # new manifest, new digest, recorded digest no longer matches
```
Good:
```
skopeo copy --all --preserve-digests docker://src/IMAGE@sha256:<d> docker://dst/IMAGE:1 --digestfile digest.txt
```
`--multi-arch=<subset>` creates a sparse manifest list that usually fails; use `--all` to mirror multi-arch images. [source](https://github.com/containers/skopeo/blob/main/docs/skopeo-copy.1.md)

Bad:
```
- uses: actions/delete-package-versions@v5
  with: { package-name: app, package-type: container, delete-only-untagged-versions: 'true' }   # deletes per-platform manifests of tagged multi-arch images
```
Good:
```
- uses: actions/delete-package-versions@v5      # pin by SHA
  with: { package-name: app, package-type: container, min-versions-to-keep: 20, ignore-versions: '^v' }
```
[source](https://github.com/docker/build-push-action/issues/894)

Bad:
```
# CI pulls base images from Docker Hub anonymously on shared runners: 100 pulls / 6 h per IP are exhausted
```
Good:
```
# log in with a PAT or organization access token before pulling (200 / 6 h for Personal accounts, more on paid plans)
# check remaining with a HEAD request (not counted), see ci-and-retention.md
```
[source](https://docs.docker.com/docker-hub/usage/pulls/)

Bad:
```
# deploy manifest: image: ghcr.io/OWNER/app:latest      # moves under you; rollback means rebuilding
```
Good:
```
# deploy manifest: image: ghcr.io/OWNER/app@sha256:<digest>      # rollback = previous digest
docker buildx imagetools create -t ghcr.io/OWNER/app:prod ghcr.io/OWNER/app@sha256:<old>
```
[source](https://docs.docker.com/reference/cli/docker/buildx/imagetools/create/)

Bad:
```
# workflow without `permissions: packages: write` pushing to an existing package created elsewhere: denied
```
Good:
```
permissions: { contents: read, packages: write }
# and in the package settings: Manage Actions access -> add the repository with write (Admin to delete)
```
[source](https://github.com/docker/login-action)
