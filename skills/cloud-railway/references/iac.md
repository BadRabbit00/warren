# Railway: IaC

General workflow: `iac` skill.

## Vendor path: `railway config` (`.railway/railway.ts`)

[source](https://docs.railway.com/cli/config)

- npm package `railway`, imports from `railway/iac`; TypeScript is GA, Python and Go beta. The `config` subcommand is present in nixpkgs railway 5.30.4.
- Commands: `railway config init`, `railway config pull`, `railway config plan [--detailed-exit-code]` (exit 0 no changes, 2 changes pending), `railway config apply --yes --confirm-destructive`. `railway config migrate` is in the docs only: `railway config --help` in nixpkgs railway 5.30.4 lists only plan, apply, init, pull, and `migrate` gives "unrecognized subcommand". For an existing project use `railway config pull` or `init` (import from the linked project).
- CI: run `plan --detailed-exit-code` (which token type it accepts is not verified), publish the plan, stop. Apply: only a human with «да», stand and prod both. `apply --yes --confirm-destructive` must never be in a CI job.
- Some settings may still need the dashboard; verify the ones you need are covered before relying on it [source](https://station.railway.com/feedback/iac-does-not-feel-production-ready-for-r-da53d29a).

## Deprecated: `railway.toml` / `railway.json`

Config as Code is deprecated: new services cannot opt in, existing files stop being read on 2026-12-01 [source](https://docs.railway.com/reference/config-as-code). Import the linked project with `railway config pull` (or `init`), then `railway config plan --detailed-exit-code`.

## Community Terraform provider (OpenTofu)

`terraform-community-providers/railway`, 0.6.3 (2026-10-19), community-maintained and not a Railway product [source](https://github.com/terraform-community-providers/terraform-provider-railway). Resources: project, environment, service, service_domain, custom_domain, tcp_proxy, variable, variable_collection, shared_variable; no volume or database resources listed (list may be truncated).

- Token: provider `token` argument or env `RAILWAY_TOKEN`, and it must be an account or workspace token, not a project token, although the CLI uses `RAILWAY_TOKEN` for a project token [source](https://raw.githubusercontent.com/terraform-community-providers/terraform-provider-railway/master/docs/index.md). Pass it as `TF_VAR_...` into the `token` argument and isolate the environment so the CLI's project token is not passed to OpenTofu.
- Remote state: Railway offers no state backend in the research. Use an S3-compatible or GCS backend from another provider (`cloud-cloudflare` R2, `cloud-gcp` GCS); see `iac`. Not verified for Railway specifically.
- Pick one IaC path per project (`railway config` or the provider), not both on the same resources.

## Secrets

Service variables with secrets are set through the platform (`railway variable`, dashboard, or IaC fed from a CI secret), never committed. Do not run `railway variable` in a shared log: output contains secrets [source](https://docs.railway.com/cli/deployment).
