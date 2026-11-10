# Cloudflare: IaC

General workflow, drift, import blocks, CI shape: `iac` skill. Here only what is specific to Cloudflare.

## Tool and provider

- OpenTofu: `tofu ...` (MPL-2.0). Terraform is BUSL-1.1; use it only if the project already uses it.
- Provider: `source = "cloudflare/cloudflare"`, `version = "~> 5"`; `provider "cloudflare" { api_token = var.cloudflare_api_token }` [source](https://raw.githubusercontent.com/cloudflare/terraform-provider-cloudflare/main/docs/index.md). The latest release number and the v4 to v5 upgrade guide were not confirmed.
- Auth env: `CLOUDFLARE_API_TOKEN` (recommended); legacy `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL`, `CLOUDFLARE_API_USER_SERVICE_KEY`. Only one of api_key / api_token / api_user_service_key may be set (same source). Take the token from CI secrets or `sops exec-env`, never from a committed file (see `sops`).
- Resource names and arguments: read them from the provider docs of the pinned version, or after `tofu init` with `tofu providers schema -json`; do not write them from memory.

## Remote state

No Cloudflare-native backend was found in the research. The S3 backend works with S3-compatible stores such as R2 through its S3 arguments (`endpoints = { s3 = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" }`, `region = "auto"`, `use_path_style`, the `skip_*` flags); HashiCorp supports S3-compatible stores on a best-effort basis only [source](https://developer.hashicorp.com/terraform/language/backend/s3). R2 specifics (which `skip_*` flags are needed, whether `use_lockfile = true` works on R2) are not verified: try `tofu init` and `tofu plan` against a test bucket first. Backend credentials only via `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, never in the backend block or `-backend-config`. R2 S3 keys: Access Key ID = token id, Secret = SHA-256 of the token value [source](https://developers.cloudflare.com/r2/api/s3/api/).

Optional second layer: OpenTofu state encryption (`iac` skill).

## Plan in CI, apply by a human

- CI: `tofu init -input=false`, `tofu plan -input=false -lock-timeout=5m -out=tfplan`; plan artifact is a secret (it holds variables in clear text), short retention.
- Apply: only after the user's explicit «да» on the plan summary, for stand and prod both (user decision 2026-11-09). The agent shows the plan; the human (or the agent after «да») runs `tofu apply tfplan`.
- Token for CI plan: a read-only API token. Token for apply: separate, used only in the manual run.

## Import existing resources

`cf-terraforming generate|import` (version 0.29.0; `--modern-import-block` emits HCL `import` blocks, Terraform 1.5+, from the tool's `--help`). Its maintenance status and compatibility with provider v5 were not verified: review the generated HCL by hand, then check with `tofu plan` that it shows no changes. Terraformer marks Cloudflare as broken and is archived (see `iac`).
