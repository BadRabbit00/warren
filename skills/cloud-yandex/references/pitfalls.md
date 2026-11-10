# Yandex Cloud: pitfalls

Bad:
```
nix shell nixpkgs#yandex-cloud -c yc version         # fails: unfree package
# or: the vendor's install.sh from storage.yandexcloud.net run on the host (edits PATH and the system)
```
Good:
```
NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc version
```
Flake mode ignores `~/.config/nixpkgs/config.nix`; alternatively use a devShell with `config.allowUnfree = true`. [source](https://raw.githubusercontent.com/NixOS/nixpkgs/master/pkgs/by-name/ya/yandex-cloud/package.nix)

Bad:
```
yc config set token <OAuth token>      # new OAuth tokens are not accepted since 2026-06-01
```
Good:
```
! ... yc init --federation-id=<federation_ID>      # the user logs in; or impersonation: yc iam create-token --impersonate-service-account-id <sa_id>
```
[source](https://yandex.cloud/en/docs/iam/concepts/authorization/oauth-token)

Bad:
```
export YC_TOKEN=<IAM token>; yc serverless container list      # yc reads YC_IAM_TOKEN, not YC_TOKEN
```
Good:
```
export YC_IAM_TOKEN=<IAM token>      # for yc
export YC_TOKEN=<IAM token>          # for the Terraform provider; tokens expire in <= 12 h: request a fresh one per run
```
[source](https://yandex.cloud/en/docs/cli/operations/authentication/iam-token-env)

Bad:
```
yc container registry configure-docker
docker login --username iam --password-stdin cr.yandex     # error: docker login is not supported with yc credential helper
```
Good:
```
# remove the "cr.yandex" entry from credHelpers in ~/.docker/config.json first (the helper also fails under sudo)
```
[source](https://yandex.cloud/en/docs/container-registry/operations/authentication)

Bad:
```
yc logging read --group-name=default --follow --since 3h        # not allowed together
```
Good:
```
yc logging read --group-name=default --since 3h --limit 1000 --format json     # history
yc logging read --group-name=default --follow                                  # streaming
```
[source](https://yandex.cloud/en/docs/logging/operations/read-logs)

Bad:
```
backend "s3" { endpoints = { s3 = "https://storage.yandexcloud.net" }  bucket = "b"  key = "k" }     # fails on newer Terraform
```
Good:
```
region = "ru-central1"; skip_region_validation = true; skip_credentials_validation = true
skip_requesting_account_id = true; skip_s3_checksum = true       # the last two are required for TF >= 1.6.1 / 1.6.3
```
[source](https://yandex.cloud/en/docs/tutorials/infrastructure-management/terraform-state-storage)

Bad:
```
tofu init       # from Russia: cannot reach registry.terraform.io to download yandex-cloud/yandex
```
Good:
```
# network_mirror https://terraform-mirror.yandexcloud.net/ in the CLI config (see references/iac.md)
```
[source](https://yandex.cloud/en/docs/tutorials/infrastructure-management/terraform-quickstart)

Bad:
```
yc serverless container revision deploy --container-name api --image cr.yandex/<id>/api:latest      # defaults: 128MB, 3s timeout; mutable tag
```
Good:
```
yc serverless container revision deploy --container-name api --image cr.yandex/<id>/api:<sha> --memory 1GB --execution-timeout 30s --service-account-id <sa_id>
```
Revisions are immutable and cannot be updated or deleted; roll back with `yc serverless container rollback`. [source](https://yandex.cloud/en/docs/serverless-containers/operations/manage-revision)
