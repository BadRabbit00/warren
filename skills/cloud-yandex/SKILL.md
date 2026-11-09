---
name: cloud-yandex
description: Use when a project deploys to or considers Yandex Cloud - Serverless Containers, Container Registry, Managed PostgreSQL and Valkey, Object Storage - the yc login check (OAuth tokens ended), unfree yc in Nix, deploy and revision rollback, OpenTofu with the Yandex mirror, plan in CI and human apply.
---

# Cloud: Yandex Cloud

Provider skill. Commands: `cli-yc`. IaC basics: `iac`. Secrets: `sops`, `secrets.md` (Yandex Lockbox for platform secrets). Images: `registry-dockerhub-ghcr`, `docker-patterns`. CI: `ci-github-actions`.

## When to choose

- A project that must run in Russia or needs Yandex services: Serverless Containers (immutable revisions, rollback by revision id), Container Registry (`cr.yandex`), Managed PostgreSQL, Managed Valkey (CLI namespace `managed-redis`), S3-compatible Object Storage [source](https://yandex.cloud/en/docs/serverless-containers/operations/manage-revision).
- Practical limits from the research: `yc` is proprietary (nixpkgs unfree); `registry.terraform.io` may be unreachable from Russia, so the provider needs Yandex's mirror; GitHub Actions for Serverless Containers come from the community org `yc-actions`, not from Yandex. Whether Yandex publishes an official Action is not verified.

## CLI and login check (D3)

Run (unfree): `NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc ...`, or a project devShell with `config.allowUnfree = true` [source](https://raw.githubusercontent.com/NixOS/nixpkgs/master/pkgs/by-name/ya/yandex-cloud/package.nix). A plain `nix shell nixpkgs#yandex-cloud` fails. See `cli-yc`. Do not use the vendor's installer script.

1. `NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc iam whoami`; fallback probe `yc iam create-token >/dev/null` (non-zero when auth is missing or expired). `yc config list` shows the profile but does not prove the credentials are valid.
2. Newly issued OAuth tokens are not accepted since 2026-06-01; old ones expire 12 months after issue. A profile with a `token` key may stop working [source](https://yandex.cloud/en/docs/iam/concepts/authorization/oauth-token).
3. Not logged in or expired: stop with `STATUS: blocked — login needed` and give the user `! NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#yandex-cloud -c yc init --federation-id=<federation_ID>` (or `--username=<email>` / `--userpool-id=<id>`). Never run it, never ask for a token in chat.
4. CI: `YC_IAM_TOKEN` for `yc` (IAM tokens live up to 12 hours, request a new one about hourly), `YC_TOKEN` for the Terraform provider: different names for the same kind of token [source](https://yandex.cloud/en/docs/cli/operations/authentication/iam-token-env). Prefer Workload Identity Federation (`yc-sa-id` input) or impersonation over long-lived service account keys.

## Deploy (Serverless Containers)

1. Registry auth: `yc container registry configure-docker` (credential helper) for humans; for CI `docker login --username iam --password-stdin cr.yandex` with an IAM token. Image `cr.yandex/<registry_id>/<image>:<tag>`; use unique tags or digests.
2. `yc serverless container revision deploy --container-name <name> --image cr.yandex/... --cores 1 --memory 1GB --execution-timeout 30s --service-account-id <sa_id>` (defaults are memory 128MB, timeout 3s) [source](https://yandex.cloud/en/docs/serverless-containers/operations/manage-revision). Secrets: `--secret name=..,key=..,environment-variable=..` (Lockbox).
3. Verify: `yc serverless container revision list --container-name <name>`, `yc logging read --group-name=default --since 1h --format json` (container logs go to Cloud Logging; filtering by `--resource-ids` is not confirmed as the documented way).
4. Production deploy from CI on `main` or after the user's «да».

## Rollback

Revisions are immutable. `yc serverless container revision list --container-name <name>` to find the previous revision id, then (user's «да»):

```
yc serverless container rollback <CONTAINER-NAME> --revision-id <REVISION-ID>
```

[source](https://yandex.cloud/en/docs/cli/cli-ref/serverless/cli-ref/container/rollback). Databases: `cluster list-backups` / `restore` create a new cluster from a backup (write actions, only on the user's «да»). Keep migrations backward-compatible.

## More

- `references/iac.md`: provider, mirror, Object Storage state, plan/apply split.
- `references/managed-services.md`: PostgreSQL, Valkey, Object Storage, how a container gets connection values.
- `references/pitfalls.md`: Bad/Good with sources.

## Not verified

- Flags of `yc managed-redis cluster list-logs`.
- Reading container logs via `--resource-ids` as the official way.
- The verbatim `.terraformrc` block (reconstructed from the parts the page confirmed).
- An official non-community GitHub Action.
