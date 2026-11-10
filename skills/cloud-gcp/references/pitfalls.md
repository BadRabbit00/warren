# GCP: pitfalls

Bad:
```
gcloud components install beta log-streaming        # fails: the updater is disabled in the nixpkgs build
```
Good:
```
# project devShell: google-cloud-sdk.withExtraComponents [ google-cloud-sdk.components.beta google-cloud-sdk.components.log-streaming ]
```
[source](https://github.com/NixOS/nixpkgs/blob/nixos-unstable/pkgs/by-name/go/google-cloud-sdk/package.nix)

Bad:
```
gcloud auth login && tofu plan        # tofu fails: no application default credentials
```
Good:
```
gcloud auth application-default login --no-launch-browser     # the user runs it; or gcloud auth login --update-adc
```
gcloud credentials and ADC are separate. [source](https://docs.cloud.google.com/docs/authentication/application-default-credentials)

Bad:
```
gcloud run deploy api --image ... --no-traffic      # once; later deploys silently get no traffic
```
Good:
```
gcloud run deploy api --image ... --no-traffic --tag=canary
gcloud run services update-traffic api --to-latest        # or --to-revisions REV=100
```
[source](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy)

Bad:
```
gcloud iam workload-identity-pools providers create-oidc my-repo ... --issuer-uri=https://token.actions.githubusercontent.com
# no --attribute-condition: any GitHub repo's token can enter the pool
```
Good:
```
... --attribute-condition="assertion.repository_owner == 'ORG'"
# bind IAM to principalSet://.../attribute.repository/OWNER/REPO, not to the whole pool
```
[source](https://raw.githubusercontent.com/google-github-actions/auth/main/README.md)

Bad:
```
- uses: google-github-actions/auth@v3
  with: { workload_identity_provider: projects/.../providers/PROVIDER }     # direct WIF: cannot mint access/ID tokens
```
Good:
```
- uses: google-github-actions/auth@v3        # pin by SHA
  with:
    workload_identity_provider: projects/.../providers/PROVIDER
    service_account: ci-plan@PROJECT.iam.gserviceaccount.com     # grant roles/iam.workloadIdentityUser
```
[source](https://raw.githubusercontent.com/google-github-actions/auth/main/README.md)

Bad:
```
gcloud sql backups restore BACKUP_ID --restore-instance=prod       # overwrites everything on prod, incl. PITR logs; fails with replicas
```
Good:
```
gcloud sql instances clone prod prod-restored --point-in-time '2026-11-09T10:00:00Z'     # then switch the app after the user's «да»
```
[source](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restoring)

Bad:
```
host=/cloudsql/PROJECT:REGION:INSTANCE        # some Postgres drivers cannot connect
```
Good:
```
host=/cloudsql/PROJECT:REGION:INSTANCE/.s.PGSQL.5432
```
[source](https://docs.cloud.google.com/sql/docs/postgres/connect-run)

Bad:
```
nix shell nixpkgs#terraform -c terraform plan        # unfree (BUSL-1.1): evaluation error
```
Good:
```
nix shell nixpkgs#opentofu -c tofu plan
```
[source](https://search.nixos.org/packages?channel=unstable&query=terraform)
