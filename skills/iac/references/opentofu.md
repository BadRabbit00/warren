# OpenTofu / Terraform: state, drift, import

## Licences and tools

- HashiCorp moved Terraform from MPL 2.0 to BUSL 1.1 for future releases (announced 2023-08-10); HashiCorp APIs, SDKs and most libraries stay MPL 2.0 [source](https://www.hashicorp.com/en/blog/hashicorp-adopts-business-source-license).
- OpenTofu is MPL-2.0 with a Technical Steering Committee [source](https://github.com/opentofu/opentofu). 1.7.0 (2024-04-30) added client-side state encryption, provider-defined functions, the `removed` block and `for_each` import blocks [source](https://opentofu.org/blog/opentofu-1-7-0/).
- Other tools (versions checked in the research): `terraformer` 0.8.30, `ansible` (core 2.21.5), `ansible-lint` 25.8.2, `sops` 3.13.3, `tflint` 0.65.0, `terraform-docs` 0.24.0, `cf-terraforming` 0.29.0.

## Backends and locking

| Backend | Locking | Notes |
|---|---|---|
| S3 (Terraform) | `use_lockfile = true` (needs s3:GetObject, PutObject, DeleteObject on the `.tflock` object); `dynamodb_table` deprecated | [source](https://developer.hashicorp.com/terraform/language/backend/s3) |
| S3 (OpenTofu) | `use_lockfile = true` preferred; `dynamodb_table` still supported, no plan to deprecate; both set = both locks taken | [source](https://opentofu.org/docs/language/settings/backends/s3/) |
| GCS | native | `bucket`, `prefix`; Object Versioning highly recommended; Storage Object Admin on the bucket; `GOOGLE_BACKEND_CREDENTIALS` / `GOOGLE_CREDENTIALS`, else ADC [source](https://developer.hashicorp.com/terraform/language/backend/gcs). OpenTofu GCS specifics not checked. |
| S3-compatible (R2, Spaces, Yandex, MinIO) | varies | `endpoints = { s3 = "..." }`, `use_path_style = true`, `skip_credentials_validation`, `skip_requesting_account_id`, `skip_s3_checksum`, `skip_region_validation`, `skip_metadata_api_check`. Best-effort support, tested only against Amazon S3 [source](https://developer.hashicorp.com/terraform/language/backend/s3) |

Use `use_lockfile = true` on both tools for portability; set `dynamodb_table` too only during a migration window. Credentials: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_PROFILE`, `AWS_REGION` env. HCP Terraform token in CI: `TF_TOKEN_<hostname with _ for .>` (Terraform >= 1.2.0) [source](https://developer.hashicorp.com/terraform/cli/config/config-file).

## State encryption (OpenTofu only)

```hcl
terraform {
  encryption {
    key_provider "pbkdf2" "main" { passphrase = var.passphrase }
    method "aes_gcm" "main" { keys = key_provider.pbkdf2.main }
    state { method = method.aes_gcm.main }
  }
}
```

Key providers: pbkdf2, aws_kms, gcp_kms, azure_vault, openbao, external. `TF_ENCRYPTION` env overrides the code. Migrating an unencrypted state needs the `unencrypted` method plus a `fallback` block. A lost key means the state cannot be read. Terraform has no equivalent [source](https://opentofu.org/docs/language/state/encryption/). Pass the passphrase from a secret store, never a literal.

## Drift

- `plan -detailed-exitcode`: 0 no changes, 1 error, 2 changes present; run on a schedule. With the setup wrapper on, set `tofu_wrapper: false` / `terraform_wrapper: false` to read the raw exit code [source](https://opentofu.org/docs/cli/commands/plan/), [wrapper](https://github.com/hashicorp/setup-terraform).
- `plan -refresh-only` shows out-of-band changes. A normal apply after drift tries to undo them and may destroy or recreate resources [source](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift). Decide per resource: accept (`apply -refresh-only`) or revert (normal apply); both write and need the user's «да».
- PR comments: GitHub limits comments to 65,535 characters: write the plan to `$GITHUB_STEP_SUMMARY` or truncate.

## Import existing resources

Native import blocks are the modern path:

```hcl
import {
  to = aws_instance.example
  id = "i-abcd1234"
}
```

Optional `identity` (not with `id`), `for_each`, `provider`. `tofu plan -generate-config-out=generated.tf` writes HCL for import targets without a resource block; the target file must not exist, the feature is experimental, may emit invalid config for complex schemas, and does not work with `for_each` import blocks in OpenTofu [source](https://developer.hashicorp.com/terraform/language/block/import), [OpenTofu](https://opentofu.org/docs/language/import/). Review the generated file by hand, then require an empty `plan` before committing.

- `cf-terraforming` (Cloudflare): `generate` fetches resources as Terraform stanzas, `import` prints `terraform import` commands, `--modern-import-block` emits import blocks (Terraform 1.5+), per its `--help` (0.29.0). Maintenance status and compatibility with provider v5: not verified.
- Terraformer (GoogleCloudPlatform/terraformer): archived and read-only since 2026-03-16, no further updates or security patches; README targets Terraform 0.13; Cloudflare is marked broken [source](https://github.com/GoogleCloudPlatform/terraformer). Prefer import blocks. If you still must use it: `terraformer import aws --resources=vpc,subnet --regions=eu-west-1`, then fix old provider addresses with `tofu state replace-provider ...` (changes state: only after the user's «да»). Not verified with `--help`.

## CI actions

`hashicorp/setup-terraform@v4` (inputs `terraform_version`, `cli_config_credentials_token`, `terraform_wrapper`), `opentofu/setup-opentofu@v2` (`tofu_version`, `tofu_wrapper`, `cli_config_credentials_token`). Pin both by full SHA. PR plan jobs need `contents: read` and `pull-requests: write` only if they comment. Alternative: no action, install a pinned `tofu` release (version and checksum) and run `tofu ...` directly.
