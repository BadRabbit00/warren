---
name: sops
description: Use when a project's secrets are or may become sops-encrypted - when to ask the user about sops, age keys and .sops.yaml, running with exec-env, adding values without printing them, CI and server setup, and what is never done.
---

# sops

Secrets encrypted in the repository with sops + age (source: `10-secrets` §4–5). Base rules for secrets: `secrets.md` (R-SECRET-*). Hooks already block decrypting to the terminal.

## Asking first

sops keeps secrets in the repo encrypted: the team gets them with the code, access is per key, history is visible. The cost is key management and onboarding. **The user decides.**

- **When to ask**: when secrets are set up in a new project, and before **every** pull request into `main` while sops is not enabled — especially if the PR adds secrets or changes how they are passed.
- **How**: one question in the same message that prepares the PR, no separate round. «В этом PR добавлены `PAYMENT_API_KEY` и `SMTP_PASSWORD`; сейчас они в `.env` и GitHub Secrets. Перевести секреты проекта в sops (зашифрованные `secrets/*.env` в репозитории)? Если нет — оставлю как есть».
- **Answers**: «нет» → stay with `.env` and GitHub Secrets; ask again before the next PR into `main`. «да» → a separate task or commit following this skill, never mixed with the PR's code. Without an explicit «да» no `.sops.yaml`, no `secrets/`.

## Layout

- age encryption; `sops`, `age`, `ssh-to-age` installed on the machine (missing → `STATUS: blocked — install needed (requirements.md)`).
- Files `secrets/<env>.env` (dotenv: names visible, values encrypted). `.sops.yaml` in the root says who decrypts what:

```yaml
creation_rules:
  - path_regex: ^secrets/dev\.env$
    age: >-
      age1<developer-1>,age1<developer-2>,age1<ci>
  - path_regex: ^secrets/prod\.env$
    age: >-
      age1<admin>,age1<prod-host>
```

## Keys

- Every person and every server has its own age key. A person's key: `~/.config/sops/age/keys.txt` (or `SOPS_AGE_KEY_FILE`), from `age-keygen` or an ed25519 SSH key via `ssh-to-age`; never in the repo. A server's key: its SSH host key (`ssh-to-age < /etc/ssh/ssh_host_ed25519_key.pub`).
- The prod file is decrypted only by admins and prod hosts.
- New member: they send the public key → added to `.sops.yaml` → `sops updatekeys`. Member leaves: key removed → `sops updatekeys` → `sops rotate` → rotate the secrets they saw.
- Recipients in `.sops.yaml` change only on the user's direct request.

## Daily use

- Run without writing secrets to disk: `sops exec-env secrets/dev.env 'docker compose up -d'`. Compose passes them explicitly: `environment:` with `${VAR:?hint}`.
- New dev value, never printed: `openssl rand -hex 32 | sops set --value-stdin secrets/dev.env '["DB_PASSWORD"]'`. Prod values are entered by a person: `sops edit secrets/prod.env`.
- Check a value exists: `sops decrypt --extract '["DB_PASSWORD"]' secrets/dev.env >/dev/null`.
- Before a commit: `sops filestatus secrets/<file>` confirms it is encrypted.

## CI and servers

- CI has its own age key in the GitHub Secret `SOPS_AGE_KEY` and is a recipient only of the files it needs; of prod only if CI deploys, and only in the `production` environment with human approval.
- On a server: decrypt with the host key at deploy time into tmpfs (`/run/<project>/<component>.env`, mode `0400`) and use `EnvironmentFile=`.

## Never

`sops decrypt` to the terminal, a file, or a log · `sops decrypt … > .env` · committing a decrypted file · `sops exec-env … 'env'` (prints everything) · changing recipients unasked · enabling sops without the user's «да».
