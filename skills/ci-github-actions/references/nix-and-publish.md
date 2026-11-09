# CI: Nix and image publishing

## Nix in CI

Two installer actions were researched. Pin either by full SHA.

| Action | Inputs and facts |
|---|---|
| `DeterminateSystems/nix-installer-action` | `determinate` (default true: Determinate Nix + FlakeHub login; `false` = upstream Nix, unsupported, may be removed), `extra-conf`, `extra-args`, `github-token`, `kvm` (true), `planner`, `init`, `start-daemon`, `trust-runner-user` (true), `summarize` (true), `diagnostic-endpoint` (empty disables telemetry), `source-tag` / `source-revision` / `source-url`, `reinstall`, `force-no-systemd`. README examples use `@main`: use a SHA. FlakeHub cache or private flakes need `id-token: write` and `DeterminateSystems/determinate-nix-action@v3` [source](https://raw.githubusercontent.com/DeterminateSystems/nix-installer-action/main/action.yml) |
| `cachix/install-nix-action` (v31) | `extra_nix_config`, `github_access_token` (defaults to `$GITHUB_TOKEN`; avoids rate limits; ignored if `access-tokens` is set in `extra_nix_config`), `install_url`, `install_options`, `nix_path`, `enable_kvm` (true), `set_as_trusted_user` (true). Pair with `cachix/cachix-action` for a binary cache [source](https://raw.githubusercontent.com/cachix/install-nix-action/master/README.md) |

Which one the project uses is the existing CI's choice; with neither present, ask which (the Determinate default sends diagnostics unless `diagnostic-endpoint` is empty).

Then run everything through the flake so CI equals local:

```yaml
- run: nix flake check --print-build-logs
- run: nix build .#<package> --print-build-logs
- run: nix develop -c ruff check .
```

Project-specific Nix rules: `nix-flake-patterns`, `nix-testing`, `project-flake`.

## Publish images by digest

Details of registries, permissions, retention: `registry-dockerhub-ghcr` (`references/ci-and-retention.md`).

```yaml
publish:
  needs: [lint, test]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
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
- Nix `dockerTools` image: `nix build .#image`, then `skopeo copy docker-archive:./result docker://ghcr.io/OWNER/IMAGE:TAG --digestfile digest.txt` (see the registry skill); the digest goes to the job output the same way.
- Production deploy and `apply` are not part of this job: deploy after the user's «да» or in a protected environment job; infrastructure apply is never in CI.
- Scan the pushed image (trivy, `references/security-and-lint.md`) before the deploy job.
