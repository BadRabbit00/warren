# Ansible

For non-NixOS VMs. Tools: `nix shell nixpkgs#ansible -c ansible-playbook ...` (ansible-core 2.21.5, GPL-3.0-or-later), `nix shell nixpkgs#ansible-lint -c ansible-lint` (MIT).

## Inventory

- INI or YAML. `group_vars/<group>` and `host_vars/<host>` files are YAML (`.yml`, `.yaml`, `.json` or no extension). `ansible_host` sets the connect address, `ansible_user` the login user [source](https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html).
- Read-only inspection: `ansible-inventory -i <inventory> --graph`, `--list`, `--host <host>` [source](https://docs.ansible.com/ansible/latest/cli/ansible-inventory.html).
- Hosts created by OpenTofu: output the addresses, generate or point the inventory from them; do not hand-copy IPs.

## Check mode

```
ansible-playbook site.yml --check --diff --limit <host>
```

Modules without check-mode support "report nothing and do nothing", and tasks depending on registered vars give no output: a green dry run does not prove a change is safe. Mark `command` / `shell` tasks with `check_mode: true` (always dry) or `check_mode: false` (applies even under `--check`; use sparingly) [source](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_checkmode.html).

Before any `--check` run, grep the playbook, roles and includes for `check_mode: false` and `check_mode: no`. If any is found, the run is a real run: it needs the user's «да», and the request names those tasks. Otherwise flow like IaC: dry run in CI or by the agent, the real run only after the user's «да», `--limit` to one host first.

## Privilege and secrets

`become: true`, `become_user`, `become_method` (sudo or su). CLI: `-b` / `--become`, `-K` / `--ask-become-pass`. `ansible_become_password` is never plain text: encrypt with Ansible Vault [source](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_privilege_escalation.html). Vault password and other secrets come from the environment or `sops` (see that skill), never from the repo. A comparison of Vault and sops for a given project is the user's decision.

## ansible-lint

Run from the project root (running it from `roles/` or `tasks/` is unsupported and may report 0 errors). `ansible-lint --profile=production`; `--fix`; `-f sarif` or `--sarif-file FILE` for CI; `-s` / `--strict` also fails on warnings. Config: `.ansible-lint`, `.ansible-lint.yml` or `.config/ansible-lint.yml` [source](https://docs.ansible.com/projects/lint/usage/).

Bad:
```
cd roles/web && ansible-lint            # may report zero errors
```
Good:
```
ansible-lint --profile=production       # from the project root
```
