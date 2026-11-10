---
name: security-review
description: Use when reviewing code, configs, or a design for security - threat model by data flow, an ASVS-L2-style checklist, role x endpoint and object-rights matrix, auth/JWT, secrets, supply chain, containers, logging, SSRF and uploads, with vulnerable-to-fixed examples.
---

# Security review

A defensive review method for application code and its delivery: find weaknesses, prove them with a source → sink trace, grade them, and give the fix. It is written to be used by `security-reviewer` and by a future blue-team model; nothing here is about attacking systems you do not own.

## Contents

1. [When to use](#when-to-use) · 2. [Method](#method) · 3. [Threat model](#threat-model-stride-lite) · 4. [Access matrix](#access-matrix) · 5. [Grading](#grading) · 6. [Report](#report) · 7. [Reference files](#reference-files)

## When to use

- A task's diff touches routes, auth, input handling, files, outgoing requests, secrets, Dockerfiles, compose, CI, or dependencies.
- The docs stage: an architecture or API needs a threat model before code.
- A full component audit on request.

## Method

1. **Scope.** List the entry points in scope: HTTP routes, consumers, webhooks, CLI, scheduled jobs, CI workflows. For a diff: only those it adds or changes, plus everything they now reach.
2. **Map data flows.** For each entry point: who calls it (anonymous, user, role, service, third party) → what it reads → what it writes or calls → where data leaves (response, log, outgoing request, file, event). Mark trust boundaries: internet → proxy → service → DB / Redis / S3 / neighbour service / third party.
3. **Threat model** each flow with STRIDE-lite (below). Write only threats that apply.
4. **Checklist.** Open the reference files for the areas the flows touch (`references/checklist.md` always; the others as needed). Each item is checked against the code, not assumed.
5. **Prove.** Every finding is a trace: **source** (untrusted input, with its file:line) → **path** (functions it passes through) → **sink** (query, file path, URL fetch, HTML, shell, deserialiser, authorisation decision) with what is missing at the sink.
6. **Grade** (below) and write the **fix** in the project's stack, short enough to apply.
7. **Matrix.** If routes changed, produce the access matrix (below).

## Threat model (STRIDE-lite)

| Letter | Question for this flow | Typical controls to look for |
|---|---|---|
| **S** Spoofing | Can a caller pretend to be another user or service? | JWT verification per `auth-jwt.md`, service tokens with `aud`, webhook signatures, no trust in `X-User-Id` |
| **T** Tampering | Can a caller change data they should not, or change it in transit? | object-level checks, mass-assignment protection, CSRF on cookie auth, TLS, signed URLs with expiry |
| **R** Repudiation | Could someone deny a sensitive action? | audit log with actor, action, object, time; append-only |
| **I** Information disclosure | Can data reach someone who should not see it? | response schemas (no internal fields), error messages, logs without secrets/PII, existence leaks (404 vs 403) |
| **D** Denial of service | Can one caller exhaust the service? | body and upload limits, pagination caps, rate limits in Redis, timeouts, bounded work per request |
| **E** Elevation of privilege | Can a caller gain a role or reach admin actions? | role dependency on the route, role never from the request body, admin routes grouped and guarded |

## Access matrix

For every changed or new route, fill one row. Roles come from the project's role enum; "expected" comes from `docs/API.md` or the AC; "enforced" is what the code does (quote the dependency or check).

| Route | Anonymous | Customer | Manager | Admin | Service | Object rule | Enforced at |
|---|---|---|---|---|---|---|---|
| `GET /v1/orders/{id}` | 401 | own only | org only | all | 403 | owner or same org | `require_roles` dep + `OrderService.get(actor, id)` |

A cell where expected ≠ enforced is a finding. "Hidden in the UI" is never enforcement.

## Grading

Two questions: how easy is it to exploit, and what is lost if it is.

| Severity | Rule of thumb |
|---|---|
| CRITICAL | remote, unauthenticated or any logged-in user; leads to account takeover, other users' data, admin rights, code execution, or money movement |
| HIGH | needs a normal account or one extra condition; exposes or changes other users' data, or takes the service down cheaply |
| MEDIUM | needs an unusual position (insider, specific config) or leaks low-value data; missing defence-in-depth with a real gap behind it |
| LOW | hardening with no concrete path today |

Verdict mapping is the br scale: CRITICAL/HIGH → must fix, MEDIUM → suboptimal, LOW → nit. Confidence `medium` caps the severity at MEDIUM unless the trace is complete.

## Report

```text
- [CRITICAL|HIGH|MEDIUM|LOW · high|medium] <S-… checklist id> <STRIDE letter> <file:line>
  trace: <source file:line> → <path> → <sink file:line>; missing: <control>
  impact: <who can do what to whom>
  fix: <concrete change>
```

## Reference files

Read only the ones the flows need.

| File | Covers |
|---|---|
| `references/checklist.md` | the ASVS-L2-style checklist with `S-*` ids: architecture, authN, sessions, access control, input and output, crypto, errors and logs, data protection, API and web, files, config |
| `references/auth-jwt.md` | the project's auth model (`06-auth`): JWKS verification, claims, cookies + CSRF, refresh rotation, rate limits, enumeration, service tokens |
| `references/secrets-supply-chain.md` | secrets (`10-secrets`), dependencies and lock files, GitHub Actions, containers and compose |
| `references/ssrf-uploads.md` | outgoing requests to user-influenced URLs, webhooks, file uploads and downloads, archives, images |
| `references/examples.md` | vulnerable → fixed pairs in Python, Go, and TypeScript |
