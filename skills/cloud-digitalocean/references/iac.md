# DigitalOcean: IaC

General workflow: `iac` skill.

## Provider and auth

- `nix shell nixpkgs#opentofu -c tofu ...` (MPL-2.0). `nixpkgs#terraform` is BUSL-1.1 and unfree: only if the project already uses it.
- `required_providers { digitalocean = { source = "digitalocean/digitalocean", version = "~> 2.0" } }` [source](https://raw.githubusercontent.com/digitalocean/terraform-provider-digitalocean/main/docs/index.md). The latest version was not confirmed; pin when writing.
- Token env, in this precedence: `DIGITALOCEAN_TOKEN`, then `DIGITALOCEAN_ACCESS_TOKEN`. Spaces keys: `SPACES_ACCESS_KEY_ID`, `SPACES_SECRET_ACCESS_KEY` (same source). Token from CI secrets or `sops exec-env`, never committed.
- Resource names: read the provider docs of the pinned version or `tofu providers schema -json`.

## Remote state

No DigitalOcean-specific backend was found in the research. Spaces is S3-compatible (endpoint `https://<region>.digitaloceanspaces.com`, SigV4 keys), and the S3 backend supports S3-compatible stores on a best-effort basis (`endpoints = { s3 = ... }`, `use_path_style`, the `skip_*` flags) [source](https://developer.hashicorp.com/terraform/language/backend/s3). Whether Spaces works as a backend, which flags it needs, and whether `use_lockfile = true` locks there are not verified: test with a scratch bucket first. Use Spaces keys through `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env, never in the backend block. Enable bucket versioning if Spaces supports it for state recovery (not verified).

## CI: plan, then a human applies

- `digitalocean/action-doctl@v2` (inputs `token`, `version`, `no_auth`) installs doctl for CLI steps, pin by SHA (see `ci-github-actions`) [source](https://github.com/digitalocean/action-doctl). For OpenTofu use `opentofu/setup-opentofu` and pass the token as env.
- `doctl apps spec validate app.yaml --schema-only` works with `no_auth: true`: a safe PR check.
- Plan: `tofu init -input=false`, `tofu plan -input=false -lock-timeout=5m -out=tfplan`; artifact is a secret.
- Apply: only after the user's «да» on the plan, stand and prod both (decision 2026-11-09).
- App Platform apps can be managed by the provider or by the spec file with `doctl apps update`. Choose one per app.

## Secrets

Env vars of type `SECRET` in the app spec are encrypted on first submit, and `doctl apps spec get` returns the encrypted value; re-applying a plaintext spec changes it. Keep secret values out of the committed spec: inject at deploy time from a CI secret or use encrypted values. Encrypted repo files: `sops`.
