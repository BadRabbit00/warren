---
name: iac
description: Use when writing, reviewing or running infrastructure as code - OpenTofu or Terraform (init, plan, apply, import blocks, remote state and locking, drift, importing existing resources), Ansible for VMs (inventory, check mode, ansible-lint), secrets in IaC with sops, and the CI plan with human apply flow.
---

# IaC: OpenTofu / Terraform and Ansible

Provider specifics (provider source, auth env, state backend, managed services): `cloud-cloudflare`, `cloud-railway`, `cloud-gcp`, `cloud-digitalocean`, `cloud-yandex`. Secrets: `sops`, `secrets.md`. CI shape: `ci-github-actions`. NixOS hosts are not Ansible targets: `nixos-module-patterns`.

## Rules

1. **Plan in CI, apply by a human.** CI runs `init`, `validate`, `plan`. `apply` is run only after the user's explicit «да» on the plan, for stand and prod both (decision 2026-11-09). No apply job in CI, no `-auto-approve` anywhere an agent can run it.
2. **OpenTofu by default.** `nix shell nixpkgs#opentofu -c tofu ...` (MPL-2.0, 1.13.2 at 2026-11-09). `nixpkgs#terraform` is BUSL-1.1 and unfree; use it only if the project already uses it: `NIXPKGS_ALLOW_UNFREE=1 nix shell --impure nixpkgs#terraform -c terraform ...` [source](https://search.nixos.org/packages?channel=unstable&query=terraform). OpenTofu "aims to maintain compatibility with Terraform configurations" [source](https://opentofu.org/docs/intro/migration/); setups using `terraform_remote_state` need extra care. Do not migrate a project between them unasked.
3. **Login check (D3)** before any plan that talks to a provider: use the provider skill's check; not logged in means `STATUS: blocked — login needed` and the user's `! nix shell ...` command. Credentials come from env or ADC/CLI profile, never from the repo.
4. **Remote state with locking**, versioning on the bucket, credentials only via env vars (values in the backend block or `-backend-config` end up in `.terraform` and plan files) [source](https://developer.hashicorp.com/terraform/language/backend/s3).
5. **One IaC tool per resource.** Do not manage the same resource from the console, the CLI and IaC.

## Daily workflow

```
nix shell nixpkgs#opentofu -c tofu fmt -check -diff
nix shell nixpkgs#opentofu -c tofu init -input=false
nix shell nixpkgs#opentofu -c tofu validate
nix shell nixpkgs#opentofu -c tofu plan -input=false -lock-timeout=5m -out=tfplan
# show the summary to the user; only after «да»:
nix shell nixpkgs#opentofu -c tofu apply tfplan
```

- Any change to the backend block needs `tofu init -reconfigure` [source](https://opentofu.org/docs/language/settings/backends/s3/).
- The saved plan holds config and variables in clear text: secret artifact, short retention, never committed, no `.tf` suffix [source](https://developer.hashicorp.com/terraform/cli/commands/plan).
- `TF_IN_AUTOMATION=1`, `TF_INPUT=0`, `TF_VAR_<name>` for CI [source](https://developer.hashicorp.com/terraform/cli/config/environment-variables).
- Rollback is roll-forward: revert the commit, new plan, review, apply. A broken state is recovered from a bucket object version [source](https://developer.hashicorp.com/terraform/language/backend/gcs).
- Extra checks available in nixpkgs: `tflint` 0.65.0, `terraform-docs` 0.24.0 (checked with `nix eval`, in the research card).

## State, drift, import

See `references/opentofu.md`:

- backends and locking (S3 `use_lockfile`, GCS, S3-compatible stores);
- drift: `plan -detailed-exitcode` on a schedule, `plan -refresh-only` before any decision;
- import blocks and `-generate-config-out`; `cf-terraforming`; why not Terraformer (archived 2026-03-16);
- OpenTofu state encryption.

## Secrets in IaC

- Preferred: nothing secret passes through IaC. Resources reference secrets by name in the platform's secret store.
- When a value must pass: ephemeral variables, outputs and `ephemeral` blocks (Terraform >= 1.10) and write-only arguments (>= 1.11) keep it out of state and plan [source](https://developer.hashicorp.com/terraform/language/manage-sensitive-data). OpenTofu support for these was not checked.
- sops provider `carlpett/sops`: `data "sops_file"` decrypts a local file but puts values in clear text in state; `ephemeral "sops_file"` (provider >= 1.3.0, Terraform >= 1.11) does not [source](https://github.com/carlpett/terraform-provider-sops). Encrypt the state too (OpenTofu `encryption` block) or use a locked-down backend.
- Never `echo` variables in CI; `sensitive = true` hides values from output but not from state.

## Ansible (VMs that are not NixOS)

See `references/ansible.md`: inventory, `--check --diff --limit`, `become`, vault, `ansible-lint` from the project root.

```
nix shell nixpkgs#ansible -c ansible-inventory -i inventory --graph
nix shell nixpkgs#ansible -c ansible-playbook site.yml --check --diff --limit <host>
nix shell nixpkgs#ansible-lint -c ansible-lint --profile=production
```

Before `--check`, grep playbook, roles and includes for `check_mode: false` / `check_mode: no` (such tasks apply even under `--check`): if found, treat the run as real and name those tasks in the «да» request. Real runs (without `--check`) change hosts: the user's «да», like `apply`.

## Bad / Good

Bad:
```
tofu apply -auto-approve          # in CI or by an agent
```
Good:
```
tofu plan -input=false -out=tfplan   # CI
tofu apply tfplan                    # after the user's «да», from the reviewed plan
```

Bad:
```
terraform refresh                    # silently overwrites state with real values, no diff
```
Good:
```
tofu plan -refresh-only              # review; accept with `apply -refresh-only` / revert with a normal apply, both only after the user's «да»
```
[source](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift)

## Not verified

- First BUSL Terraform version and last MPL version.
- OpenTofu support of ephemeral / write-only arguments; latest `carlpett/sops` version.
- `opentofu.withPlugins` in current nixpkgs; the `tofu login` / `TF_TOKEN_<host>` equivalent.
- Ansible-lint exit codes beyond "non-zero on errors".
