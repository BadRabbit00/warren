# CI: toolchain setup and image publishing

## Toolchain setup

Set the language up with the official setup actions, each pinned by full SHA, then run the project's own commands so CI equals local:

| Language | Setup |
|---|---|
| Python | `actions/setup-python` (`python-version-file`, `cache: pip`) |
| Node | `actions/setup-node` (`node-version-file`, `cache: npm`) |
| Go | `actions/setup-go` (`go-version-file: go.mod`) |
| Rust | `dtolnay/rust-toolchain` (toolchain and `components: clippy, rustfmt`) |

```yaml
- uses: actions/setup-python@<full-sha> # vN
  with: { python-version-file: .python-version, cache: pip }
- run: pip install -r requirements.txt
- run: ruff check .
```

## Publish images by digest

Details of registries, permissions, retention: `registry-dockerhub-ghcr` (`references/ci-and-retention.md`).

Never cancel a publish: if the workflow has a workflow-level `concurrency` with `cancel-in-progress: true`, move it to the `lint` and `test` jobs and give `publish` its own group (below), or put `publish` in a separate workflow.

```yaml
publish:
  needs: [lint, test]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  concurrency: { group: "publish-${{ github.ref }}", cancel-in-progress: false }
  permissions: { contents: read, packages: write, id-token: write, attestations: write }
  outputs: { digest: "${{ steps.push.outputs.digest }}" }
  steps:
    - uses: actions/checkout@<full-sha> # vN
      with: { persist-credentials: false }
    - uses: docker/login-action@<full-sha> # v4
      with: { registry: ghcr.io, username: "${{ github.actor }}", password: "${{ secrets.GITHUB_TOKEN }}" }
    - uses: docker/build-push-action@<full-sha> # v7
      id: push
      with: { push: true, tags: "ghcr.io/${{ github.repository }}:${{ github.sha }}" }
    - uses: actions/attest@<full-sha> # v4
      with:
        subject-name: ghcr.io/${{ github.repository }}
        subject-digest: ${{ steps.push.outputs.digest }}
        push-to-registry: true
```

- Tag with the commit SHA; deploy jobs consume `needs.publish.outputs.digest` and deploy `image@sha256:<digest>`.
- Images are built from the project's multi-stage Dockerfile (final stage distroless or slim) with `docker/build-push-action`; the digest comes from its `digest` output (see the registry skill).
- Production deploy and `apply` are not part of this job: deploy after the user's «да» or in a protected environment job; infrastructure apply is never in CI.
- Scan the pushed image (trivy, `references/security-and-lint.md`) before the deploy job.
