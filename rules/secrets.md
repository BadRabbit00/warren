---
paths:
  - ".env"
  - ".env.*"
  - "**/.env.example"
  - "secrets/**"
  - ".sops.yaml"
  - "**/config.py"
  - "**/config/config.go"
---

# Secrets

## Scope

Where secrets live and how code reads them. Hooks already block printing `.env` and passing secrets as command arguments. The sops workflow is the `sops` skill.

## Rules

- R-SECRET-WHERE: app secrets live in `.env` (gitignored); CI secrets live in GitHub Secrets; prod secrets live in a file on the server (`0600`) or in GitHub environment secrets. sops is used only after the user explicitly says yes. Before every PR into `main`, ask whether to move the secrets to sops.
- R-SECRET-EXAMPLE: every variable is in `.env.example` in the same change that introduces it, with a working local value. Secrets get `change-me-…`; external keys stay empty.
- R-SECRET-NO-DEFAULTS: code has no default value for a secret. A missing secret stops startup and names the variable, never the value.
- R-SECRET-GENERATE-LOCAL: a local dev value may be generated without printing it: `printf 'DB_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> .env`. Prod values are entered by a human.
- R-SECRET-NOT-IN-ARTIFACTS: no secrets in images (`ARG`/`ENV`/`COPY .env`), in committed config files, in logs, in docs, or in subagent briefs.
- R-SECRET-LEAK: a secret that reached git, a log, a chat, or an image is compromised. Report it and propose rotation; never rewrite git history yourself.

## Examples

### R-SECRET-NO-DEFAULTS — fail closed

Bad:
```python
class Settings(BaseSettings):
    jwt_secret: str = "dev-secret"           # silently used in production if unset
    stripe_key: str = os.getenv("STRIPE_KEY", "")
```
Why: production runs with a known secret or an empty key, and nothing fails.

Good:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BILLING_")
    stripe_key: SecretStr                     # required: startup fails with "BILLING_STRIPE_KEY missing"
    env: Literal["dev", "prod"] = "prod"

    @model_validator(mode="after")
    def no_dev_values_in_prod(self) -> "Settings":
        if self.env == "prod" and self.stripe_key.get_secret_value().startswith("change-me"):
            raise ValueError("BILLING_STRIPE_KEY has a placeholder value in prod")
        return self
```

### R-SECRET-NOT-IN-ARTIFACTS — not in committed config

Bad:
```ini
# committed unit file
Environment=DATABASE_URL=postgresql://api:S3cret@db/api
```
Why: the value lands in the repository and in a world-readable unit file.

Good:
```ini
EnvironmentFile=/run/secrets/api.env   # a 0600 file outside the repo
```
