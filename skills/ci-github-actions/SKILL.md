---
name: ci-github-actions
description: Use when writing, changing or reviewing GitHub Actions workflows - least-privilege permissions, SHA-pinned actions, persist-credentials false, concurrency, linters per language, security scans (CodeQL, semgrep, gitleaks, trivy, osv-scanner, dependency-review), Lighthouse and axe for frontends, actionlint and zizmor, Nix in CI, publishing images by digest, testing on the ci-test branch.
---

# CI: GitHub Actions

For the CI engineer role. Images and registries: `registry-dockerhub-ghcr`. Deploy variants and publishing shape: `deploy-variants`. Secrets: `sops`, `secrets.md`. IaC jobs: `iac` (plan in CI, apply by a human). Commands for runs and logs: `cli-gh`. Details and per-tool inputs: `references/`.

## Rules (every workflow)

1. **`permissions: {}` at the top**, grant per job the minimum (`contents: read`, `security-events: write` for SARIF upload, `packages: write` for publish, `id-token: write` only for OIDC). Without a block the token inherits broad defaults [source](https://docs.zizmor.sh/audits/).
2. **Pin every third-party action by full commit SHA** with the tag as a comment (`uses: owner/action@<40-hex-sha> # v4`). Take the SHA from the action's own repo, not a fork. Mutable tags were rewritten in a real attack: on 2026-03-19 ~75 of 76 `aquasecurity/trivy-action` tags and all `setup-trivy` tags were force-pushed with malicious code (CVE-2026-33634) [source](https://www.aquasec.com/blog/trivy-supply-chain-attack-what-you-need-to-know). Tools to pin: `nix shell nixpkgs#pinact -c pinact run`, `nixpkgs#ratchet`. GitHub's allowed-actions policy can enforce SHA pinning [source](https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/). Reusable workflows (`jobs.<id>.uses`) are not covered by a lockfile: pin them too [source](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles).
3. **`actions/checkout` with `persist-credentials: false`** unless a later step needs git auth (the default is `true`; zizmor `artipacked`). `fetch-depth: 0` only for full-history scans (gitleaks).
4. **Concurrency**: `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` for CI; never cancel deploy or publish jobs [source](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
5. **No `${{ }}` inside `run:`** with untrusted values (title, branch, body): pass via `env:` and use `"${VAR}"` (zizmor `template-injection`). Avoid `pull_request_target`, `workflow_run`, `issue_comment` triggers unless reviewed [source](https://docs.github.com/en/actions/reference/security/secure-use).
6. **Secrets**: only from `secrets.*`, never echoed; no secrets for forks. Keyless cloud auth (OIDC/WIF) over stored keys (`cloud-gcp`). Apply for infrastructure is never a CI job.
7. **Lint the workflows themselves** (below), and run all tools from the pinned flake when possible (`nix shell nixpkgs#<tool> -c ...`) instead of unpinned third-party actions.

Skeleton:

```yaml
name: ci
on: { pull_request: {}, push: { branches: [main, develop, ci-test] } }
permissions: {}
concurrency: { group: "${{ github.workflow }}-${{ github.ref }}", cancel-in-progress: true }
jobs:
  lint:
    runs-on: ubuntu-latest
    permissions: { contents: read }
    steps:
      - uses: actions/checkout@<full-sha> # v6
        with: { persist-credentials: false }
      - run: nix develop -c ruff check --output-format=github .
```

The checkout major above is a placeholder: take the current tag and its SHA from the actions repo when writing.

## What to run

| Area | Check | Notes |
|---|---|---|
| Python | `ruff check --output-format=github .`, `ruff format --diff`, `mypy` | `astral-sh/ruff-action@v3` is an alternative |
| Go | `golangci/golangci-lint-action` (v9; v2 config needs >= v7, v8+ needs lint >= v2.1.0), after `actions/setup-go` | `permissions: contents: read` |
| TS/JS | `eslint`, `tsc --noEmit` | run through the project's package scripts |
| Rust | `cargo clippy -- -D warnings`; Cargo >= 1.97: `CARGO_BUILD_WARNINGS=deny cargo clippy` | |
| Workflows | `actionlint`, `zizmor` | `references/security-and-lint.md` |
| Security | gitleaks, trivy, osv-scanner, dependency-review, CodeQL or semgrep | `references/security-and-lint.md` |
| Frontend quality and a11y ("readability") | Lighthouse CI + axe | `references/frontend-quality.md` |
| Nix | installer action, `nix flake check`, `nix build` | `references/nix-and-publish.md` |
| Images | build, push, digest, attest | `references/nix-and-publish.md`, `registry-dockerhub-ghcr` |

Sources for the table: [ruff](https://docs.astral.sh/ruff/integrations/), [golangci-lint-action](https://raw.githubusercontent.com/golangci/golangci-lint-action/main/README.md), [clippy](https://raw.githubusercontent.com/rust-lang/rust-clippy/master/README.md), [tsc](https://www.typescriptlang.org/docs/handbook/compiler-options.html). The mypy CI invocation and `ruff format --check` as the recommended form were not researched.

## Testing a workflow: the `ci-test` branch (D13)

Never push to `develop` or `main` to see whether CI works. Push a branch `ci-test` (the hook protects only develop/main), open or reuse its run, read it with `cli-gh`:

```
git push origin HEAD:ci-test
gh run list --branch ci-test
gh run view <id> --log-failed        # failed steps only
```

Make sure the workflow's `on.push.branches` includes `ci-test`, or use `workflow_dispatch`. Lint locally before pushing: `nix shell nixpkgs#actionlint nixpkgs#shellcheck -c actionlint -color`. `nixpkgs#act` (0.2.92) exists for local runs; it was not researched.

## Bad / Good

Bad:
```yaml
- uses: aquasecurity/trivy-action@master
- uses: actions/checkout@v4
```
Good:
```yaml
- uses: aquasecurity/trivy-action@<full-sha> # vX.Y.Z, SHA verified against the official repo
- uses: actions/checkout@<full-sha> # vN
  with: { persist-credentials: false }
```

Bad:
```yaml
- run: echo "Title: ${{ github.event.pull_request.title }}"
```
Good:
```yaml
- env: { PR_TITLE: "${{ github.event.pull_request.title }}" }
  run: echo "Title: ${PR_TITLE}"
```

## Not verified

- `gh actions-lock` commands and whether workflow lockfiles are GA.
- Current major and inputs of `zizmorcore/zizmor-action`; the safe `trivy-action` major after the 2026 incident; the tag for `DeterminateSystems/nix-installer-action`.
- osv-scanner PR-mode failure behaviour (docs ambiguous).
