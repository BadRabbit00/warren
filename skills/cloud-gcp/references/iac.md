# GCP: IaC

General workflow: `iac` skill.

## Provider and auth

- `nix shell nixpkgs#opentofu -c tofu ...` (MPL-2.0). `nixpkgs#terraform` (BUSL-1.1, unfree) only if the project already uses it: `NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#terraform -c terraform ...`.
- Provider `hashicorp/google`; pinned version not checked, pin from the registry at write time. Auth names: `GOOGLE_CREDENTIALS`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_OAUTH_ACCESS_TOKEN`, `GOOGLE_PROJECT`, `GOOGLE_REGION`, ADC from `gcloud auth application-default login`, provider argument `impersonate_service_account` [source](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_reference).
- Local human run: ADC (`! ... gcloud auth application-default login`), preferably with `impersonate_service_account` so no key file exists.

## Remote state: GCS

```hcl
terraform {
  backend "gcs" {
    bucket = "tf-state-prod"     # must exist; enable Object Versioning
    prefix = "terraform/state"
  }
}
```

Locking is native. The identity needs Storage Object Admin on the bucket. Credentials: `GOOGLE_BACKEND_CREDENTIALS` / `GOOGLE_CREDENTIALS`, else ADC; impersonation `GOOGLE_BACKEND_IMPERSONATE_SERVICE_ACCOUNT` [source](https://developer.hashicorp.com/terraform/language/backend/gcs). Object Versioning is "highly recommended" and is how a broken state is recovered. OpenTofu-specific GCS backend notes were not checked. The state bucket is created once by hand or by a bootstrap config, not by the config that uses it.

## CI: plan with WIF, apply by a human

Setup (once, by the user or in a bootstrap config) [source](https://raw.githubusercontent.com/google-github-actions/auth/main/README.md):

```
gcloud iam workload-identity-pools create "github" --project="${PROJECT_ID}" --location="global" --display-name="GitHub Actions Pool"
gcloud iam workload-identity-pools providers create-oidc "my-repo" --project="${PROJECT_ID}" --location="global" \
  --workload-identity-pool="github" --display-name="My GitHub repo Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_ORG}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

Grant roles to `principalSet://iam.googleapis.com/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${REPO}`; IAM changes can take up to 5 minutes.

Workflow job: `permissions: { contents: read, id-token: write }`, step `google-github-actions/auth@v3` (pin by SHA, see `ci-github-actions`) with `workload_identity_provider: projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER` and `service_account` (impersonation; direct WIF cannot mint access or ID tokens). Plan job uses a read-only service account; the apply identity is separate and used only in the manual run.

- Plan: `tofu init -input=false`, `tofu plan -input=false -lock-timeout=5m -out=tfplan`; plan file is a secret artifact.
- Apply: only after the user's «да», stand and prod both (decision 2026-11-09).
- Deploy action `google-github-actions/deploy-cloudrun@v3` (`service`, `image`, `region`, `flags`, `no_traffic`, `tag`; output `url`) is for the app deploy, not for infra [source](https://github.com/google-github-actions/deploy-cloudrun).

## Secrets in IaC

Passwords for Cloud SQL users and similar: generate in IaC with write-only or ephemeral values where the Terraform/OpenTofu version supports it, or keep them in Secret Manager and reference with `--set-secrets` at deploy. Avoid plain values in state (`iac`). Encrypted repo files: `sops`.
