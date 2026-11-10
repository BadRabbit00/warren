# Checklist (ASVS-L2 style)

Ids are ours (`S-<AREA>-<n>`), grouped like OWASP ASVS chapters so a finding maps to a familiar area. Check each item against the code; mark it N/A only with a reason.

## S-ARCH — architecture and trust boundaries
- S-ARCH-1: every trust boundary in the data-flow map has an explicit control (auth, validation, signature).
- S-ARCH-2: services never read another service's DB or Redis; cross-service calls use service tokens with `aud`.
- S-ARCH-3: secrets, keys, and admin functions are reachable only from where they must be (internal network, admin role).
- S-ARCH-4: security decisions live on the server; the UI only hides what the server already refuses.

## S-AUTHN — authentication
- S-AUTHN-1: tokens verified per `auth-jwt.md` (signature from JWKS by `kid`, algorithm whitelist, `exp` `iat` `sub` `jti` `iss` `aud` `type`).
- S-AUTHN-2: no bypass flags (`AUTH_DISABLED`, trust in `X-User-Id`) reachable outside `env == dev`, checked at startup and per request.
- S-AUTHN-3: passwords hashed with argon2id (pwdlib); no length truncation or stripping; minimum length, breached-password check if the project has one.
- S-AUTHN-4: login, refresh, registration, reset, and code endpoints are rate-limited in Redis; failure on Redis down is closed for login.
- S-AUTHN-5: one response and similar timing for "no such user" and "wrong password"; registration and reset do not reveal whether an address exists.
- S-AUTHN-6: webhooks from third parties verify a signature (HMAC with `compare_digest`, timestamp window, replay protection).

## S-SESS — sessions and tokens
- S-SESS-1: browser tokens only in `HttpOnly; Secure; SameSite` cookies; CSRF header on every mutating request with cookie auth.
- S-SESS-2: access TTL 5–60 min, refresh rotates on use, reuse revokes the family; logout revokes.
- S-SESS-3: tokens never in URLs, `localStorage`, logs, or error messages.

## S-ACCESS — access control
- S-ACCESS-1: every route has an explicit role dependency or is listed as public in `API.md`; default deny.
- S-ACCESS-2: object-level rights checked in the service with the actor passed in (own order, own org); IDs from the path are never trusted alone.
- S-ACCESS-3: list endpoints filter by the actor's scope in the query, not after loading.
- S-ACCESS-4: no mass assignment: request schemas list allowed fields; role, owner, status, price, and IDs are never taken from the body unless the route exists to change them and checks the actor's right to.
- S-ACCESS-5: 404 vs 403 per project rule, without revealing that someone else's object exists.

## S-INPUT — input and output
- S-INPUT-1: every external input is parsed into a typed schema with limits (length, range, enum, format) at the boundary.
- S-INPUT-2: SQL only through the ORM or bound parameters; sort and column names from a whitelist.
- S-INPUT-3: no shell with interpolated input; subprocess with argument lists.
- S-INPUT-4: no unsafe deserialisation of untrusted data (`pickle`, `yaml.load` without SafeLoader, Java/PHP-style object deserialisers, `eval`).
- S-INPUT-5: output encoding by context: React text by default; `dangerouslySetInnerHTML` only with DOMPurify; templates with autoescape; `Content-Type` correct on every response.
- S-INPUT-6: redirects only to allowlisted targets or relative paths.
- S-INPUT-7: regular expressions on user input are bounded (no catastrophic backtracking on long input).

## S-CRYPTO — cryptography
- S-CRYPTO-1: no home-made crypto; tokens and IDs from `secrets` / `crypto/rand` / `crypto.getRandomValues`, never `random`.
- S-CRYPTO-2: secret comparisons in constant time (`hmac.compare_digest`, `subtle.ConstantTimeCompare`).
- S-CRYPTO-3: signing ES256/RS256; no HS256 with shared secrets across services; keys only where they must be.
- S-CRYPTO-4: TLS verification never disabled (`verify=False`, `InsecureSkipVerify`).

## S-LOG — errors, logging, audit
- S-LOG-1: errors to clients are generic with a code; no stack traces, SQL, or internal hostnames.
- S-LOG-2: no secrets, tokens, cookies, passwords, or full personal data in logs (even prefixes of tokens).
- S-LOG-3: security events are logged with actor, IP, and object: failed logins, refresh reuse, permission denials, admin actions, exports.
- S-LOG-4: audit records for sensitive business actions (money, roles, exports, deletions) are append-only and kept per retention.

## S-DATA — data protection
- S-DATA-1: response schemas expose only intended fields (no `password_hash`, internal flags, other users' data).
- S-DATA-2: personal data minimised; exports and bulk endpoints require an elevated role and are audited.
- S-DATA-3: files and objects in S3 are private by default; access through short-lived signed URLs after an authorisation check.
- S-DATA-4: caches do not mix users' data (per-user keys, `Cache-Control: private` / `no-store` on personal responses).

## S-API — API and web
- S-API-1: request body and upload size limits (P-API-LIMITS); pagination max size enforced.
- S-API-2: CORS: explicit origins; never `*` together with credentials.
- S-API-3: security headers on HTML responses (CSP, `X-Content-Type-Options`, `Referrer-Policy`, frame ancestors) set at the proxy or app.
- S-API-4: state-changing operations are not `GET`.
- S-API-5: idempotency keys on payments and creation by external key (P-API-IDEMPOTENCY).

## S-FILE — files
- S-FILE-1 … see `ssrf-uploads.md` (uploads, downloads, archives, images).

## S-SSRF — outgoing requests
- S-SSRF-1 … see `ssrf-uploads.md`.

## S-CONF — configuration and delivery
- S-CONF-1 … see `secrets-supply-chain.md` (secrets, dependencies, CI, containers).
- S-CONF-2: production refuses to start with dev values (default secrets, `CORS=*`, auth bypass, debug mode).
