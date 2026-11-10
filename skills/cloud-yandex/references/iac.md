# Yandex Cloud: IaC

General workflow: `iac` skill.

## Provider, mirror, auth

- OpenTofu: `nix shell nixpkgs#opentofu -c tofu ...` (same mirror and provider). `nixpkgs#terraform` is BUSL-1.1 and unfree; only if the project already uses it.
- Provider source `yandex-cloud/yandex`. Arguments and env: `token` / `YC_TOKEN` (IAM token), `service_account_key_file` / `YC_SERVICE_ACCOUNT_KEY_FILE`, `cloud_id` / `YC_CLOUD_ID`, `folder_id` / `YC_FOLDER_ID`, `zone` / `YC_ZONE`, `storage_access_key` / `YC_STORAGE_ACCESS_KEY` [source](https://raw.githubusercontent.com/yandex-cloud/terraform-provider-yandex/master/docs/index.md).
- Mirror, since registry.terraform.io may be unreachable from Russia: in `~/.terraformrc`

```
provider_installation {
  network_mirror {
    url     = "https://terraform-mirror.yandexcloud.net/"
    include = ["registry.terraform.io/*/*"]
  }
  direct {
    exclude = ["registry.terraform.io/*/*"]
  }
}
```

  [source](https://yandex.cloud/en/docs/tutorials/infrastructure-management/terraform-quickstart) (block reconstructed from the confirmed parts). Whether OpenTofu reads `~/.terraformrc` (or `~/.tofurc`) and uses `registry.opentofu.org` addresses was not checked: if `tofu init` cannot find the provider, adapt the `include` pattern.
- Token: `export YC_TOKEN=$(yc iam create-token --impersonate-service-account-id <sa_id>)` (needs the `iam.serviceAccounts.tokenCreator` role); `YC_CLOUD_ID=$(yc config get cloud-id)`, `YC_FOLDER_ID=$(yc config get folder-id)`. Tokens last at most 12 hours: request a new one per run. A key file through `YC_SERVICE_ACCOUNT_KEY_FILE` does not expire but is a long-lived secret (the docs call keys less secure than impersonation).

## Remote state: Object Storage

```hcl
terraform {
  backend "s3" {
    endpoints                   = { s3 = "https://storage.yandexcloud.net" }
    bucket                      = "<bucket>"
    region                      = "ru-central1"
    key                         = "terraform.tfstate"
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true   # required for Terraform >= 1.6.1
    skip_s3_checksum            = true   # required for Terraform >= 1.6.3
  }
}
```

[source](https://yandex.cloud/en/docs/tutorials/infrastructure-management/terraform-state-storage). Pass the keys through `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env (the tutorial uses `-backend-config`; env is safer, because `-backend-config` values land in `.terraform` and plan files). Locking in the tutorial goes through Managed YDB (separate page, not read); whether `use_lockfile = true` works on Object Storage is not verified. A region other than `ru-central1` gives auth errors.

## CI: plan, then a human applies

- Community Actions (`yc-actions`, MIT): auth by `yc-sa-json-credentials`, `yc-iam-token` or `yc-sa-id` (Workload Identity Federation) [source](https://github.com/yc-actions/yc-sls-container-deploy). Pin by SHA (`ci-github-actions`).
- Plan: `tofu init -input=false`, `tofu plan -input=false -lock-timeout=5m -out=tfplan`; the artifact is a secret.
- Apply: only after the user's «да», stand and prod both (decision 2026-11-09). The plan job identity is read-only, the apply identity is separate.
