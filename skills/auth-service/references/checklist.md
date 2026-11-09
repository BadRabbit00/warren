# Anti-patterns and checklist

## Anti-patterns

| Anti-pattern | Instead |
|---|---|
| login and users as a monolith module; auth tables in the business DB | separate auth service with its own DB |
| another service reads `users` or auth's Redis | claims, `/internal/users/{id}`, events |
| HS256 with a shared secret; a "backup" shared secret | ES256/RS256, private key only in auth |
| keys, signing secrets, admin passwords with defaults in code, compose, images, git | platform secret or file secret; no start without a key |
| verifying tokens by calling auth per request; an introspection endpoint that fails open | local verification by JWKS; short TTL and events for revocation |
| trusting `X-User-Id` or `DISABLE_AUTH` without a prod guard | JWT on every request; dev bypass only with the double guard |
| tokens without `exp`; access for hours or days | access 5–30 min + rotating refresh, validated TTL range |
| algorithm from the token/JWK; `iss`/`aud`/`type` unchecked | whitelist in code, required claims, `type == "access"` |
| refresh without storage and rotation; logout that revokes nothing | rotation, `jti` in PostgreSQL, reuse detection, family revocation |
| refresh accepted by DB hash without JWT verification; "revoke then issue" without a lock | `refresh_token_required` + `FOR UPDATE` or conditional `UPDATE` |
| raw refresh tokens as Redis keys; token prefixes in logs | store SHA-256 or `jti`; never log tokens |
| email, name, phone in the payload | `sub` + roles/scopes; the rest via API |
| tokens in `localStorage`/`sessionStorage`, URLs, SharedPreferences | httpOnly cookies + CSRF; Keychain/Keystore on mobile |
| `auth.handle_errors(app)` as is | own `AuthXException` handler → 401/403 |
| rate limiter, blocklist, sessions in process memory (AuthX defaults) | Redis and PostgreSQL |
| login without rate limits; different answers or timing for "no user" and "wrong password"; "email taken" in the API response | Redis limits, one answer, dummy hash |
| role from the registration body | minimal role; admins change roles |
| passlib, python-jose, low-iteration PBKDF2, time-based salts, `.strip()` on passwords | pwdlib + argon2id, PyJWT, the password as given |
| `create_all()` at start | Alembic, `auth-migrate` service |
| Keycloak/Authentik "just in case" | own auth; IdP only by explicit requirement |
| static shared API keys between services compared with `==` | service tokens with `aud` and short TTL |
| JWKS without `kid` in tokens; no rotation plan | `kid` in every token, the rotation steps |

## Checklist
- [ ] Auth is a separate service with its own code, PostgreSQL, migrations, Redis; nobody else touches its DB or Redis.
- [ ] FastAPI + AuthX (pinned in `pyproject.toml` and `uv.lock`); passwords pwdlib/argon2id via `run_in_threadpool`; deps from the lock, no ad-hoc environment.
- [ ] Layers respected: HTTP and cookies in routers, rules and `commit` in services, ORM in repositories; no raw SQL or `create_all`.
- [ ] Files named `<entity>_<layer>.py`; tests `test_<module>.py`.
- [ ] ES256 (or justified RS256); no HS256 or shared signing secrets anywhere.
- [ ] Private key only in auth: not in git, image, or compose; no start without it; one key for all replicas.
- [ ] `/.well-known/jwks.json` exists; every token has `kid`.
- [ ] `AuthXConfig` built explicitly from `Settings` (`AUTH_` prefix); TTLs validated by range; `None` impossible; prod validator rejects dev settings.
- [ ] Tokens carry `sub`, `exp`, `iat`, `jti`, `iss`, `aud`, `type`; no personal data or secrets.
- [ ] Refresh verified by AuthX, rotated atomically, `jti` in PostgreSQL, reuse revokes the family, absolute session limit.
- [ ] Logout is `POST`, revokes the session, blocklists the access `jti` until `exp`.
- [ ] AuthX errors answer 401/403 as `{"detail","code"}`, not 422.
- [ ] Every consumer verifies by JWKS with an algorithm whitelist, `exp`, `iss`, `aud`, `type`; roles by dependency, objects in the service; no dependency on auth in `depends_on` or `/ready`.
- [ ] Browser: httpOnly + Secure + SameSite cookies, CSRF header on mutations, single-flight refresh in `http.ts`; no tokens in `localStorage` or URLs.
- [ ] Service calls use service tokens with the target's `aud` and TTL ≤ 15 min.
- [ ] Login, refresh, registration, reset rate-limited in Redis; answers and timing reveal no accounts; registration role not from the request.
- [ ] `docker compose up -d --build` brings up auth with DB, Redis, keys, migrations; `--scale auth=3` changes nothing.
- [ ] An external IdP only by explicit requirement, with auth still the issuer (or direct IdP trust explicitly agreed).
- [ ] Tests on real PostgreSQL: login, expired and forged tokens, refresh as access, refresh reuse, logout, rate limit, role × endpoint matrix.
