# Secrets, supply chain, containers

## Secrets (from `10-secrets`)
- App secrets in `.env` (gitignored); CI secrets in GitHub Secrets; prod secrets in a `0600` file on the server or environment secrets. sops only after the user's explicit "yes".
- Every variable in `.env.example` with a working local value; secrets as `change-me-…`; external keys empty.
- Code has no default for a secret; a missing secret stops startup naming the variable, never the value. Production refuses dev values.
- No secrets in images (`ARG`/`ENV`/`COPY .env`), logs, docs, error messages, or subagent briefs.
- A secret that reached git, a log, a chat, or an image is compromised: report it and propose rotation. Never rewrite git history as the fix.
- Checks: `gitleaks` on the diff range if available; grep for key formats (AKIA, `-----BEGIN`, `ghp_`, `sk-`, JWTs).

## Dependencies
- Every dependency is in a lock file (`uv.lock`/`poetry.lock`, `go.sum`, `Cargo.lock`, `pnpm-lock.yaml`, `pubspec.lock`) and the lock is committed.
- New dependencies follow P-DEP-NEW: maintained, license compatible, no install scripts doing network or shell work, name checked against typosquats.
- Versions: no `*`/`latest`; ranges only where the ecosystem expects them, with the lock as the truth.
- Known vulnerabilities: `osv-scanner` on changed lock files when available (`osv-scanner --lockfile <file>`), `cargo audit`, `pip-audit`, `npm audit --omit=dev`, `govulncheck`.

## GitHub Actions
- Actions pinned to a full commit SHA; `permissions:` set minimally per workflow or job (default `contents: read`).
- `pull_request_target` never checks out or runs PR code; untrusted input (`github.event.*.title`, `body`, branch names) never interpolated into `run:` (pass through `env:`).
- Publishing workflows are separate, run only on `main`/tags, and use OIDC or environment-scoped secrets.
- Self-hosted runners never run fork PRs.

## Containers and compose
- Images distroless or slim without a shell; non-root `USER`; exact tags or digests; no secrets in layers; `.dockerignore` excludes `.env`, `.git`, keys.
- Runtime: read-only root filesystem where possible, `cap_drop: [ALL]`, `no-new-privileges:true`, no `privileged`, no Docker socket mounts, no host network.
- Ports published only for what a human opens, bound to `127.0.0.1` locally; DB, Redis, and internal services publish nothing.
- Healthchecks do not leak data; debug endpoints off in production.
