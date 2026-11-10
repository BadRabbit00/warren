---
name: stack-choice
description: Use when choosing or checking a technology for a project - backend language and framework, frontend kind, database, cache and queues, files, background work, auth, observability - with Alexey's defaults, when to deviate, and the anti-patterns.
---

# Stack choice

Alexey's default stack and the rules for leaving it (source: `02-tech-stack`). Environment and builds: `deploy-variants`. Auth details: `auth-service`.

## Contents

1. [Priorities](#priorities) · 2. [Defaults](#defaults) · 3. [Backend](#backend) · 4. [Frontend](#frontend) · 5. [Data](#data) · 6. [Background work and integrations](#background-work-and-integrations) · 7. [Observability and CI](#observability-and-ci) · 8. [Anti-patterns](#anti-patterns) · 9. [Checklist](#checklist)

## Priorities

1. The user's explicit request > the project's `AGENTS.md`/`CLAUDE.md` > this skill.
2. An existing project keeps its stack. Never rewrite working code in another language or framework unasked; a conflict with these defaults is reported and offered as a separate task.
3. A technology not listed here (library, compose service, SaaS) is added only after the user agrees, with one sentence: which problem it solves and why what exists is not enough (P-DEP-NEW).
4. One job, one tool: no two HTTP clients, ORMs, state managers, queue systems, or proxies in the same role.
5. Versions: current stable at project start, pinned (lock file or exact versions), upgraded deliberately as a separate task.

## Defaults

| Layer | Default | Allowed | Only on explicit request |
|---|---|---|---|
| Backend | Python + FastAPI | Go + Gin (Fiber by §Backend) | Node.js servers, Java, PHP, C#, Ruby; Django, Flask |
| Frontend | React + Vite + TypeScript for apps | plain HTML/CSS/JS; Next.js strictly by the table in §Frontend | Vue, Nuxt, Angular, Svelte, jQuery |
| Database | PostgreSQL | MongoDB by §Data | SQLite (except serverless single-user tools), MySQL, Elasticsearch, graph or vector DBMS |
| Cache, counters, task broker | Redis | RabbitMQ for events between services | Memcached, Kafka; in-process cache with several replicas |
| Auth | separate `auth` service: FastAPI + AuthX, own PostgreSQL, ES256/RS256 JWT | — | external IdP, HS256 shared secret, auth module inside an app. Hand-written JWT and python-jose: never |
| Files | S3-compatible storage | — | files on the container disk, binaries in the DB |
| Run | Dockerfile (multi-stage, distroless or slim) + docker compose | podman Quadlet on request | running services outside compose as the main path; host installs |

## Backend

**Python + FastAPI by default.** Go only when one of these holds, and the reason is named in the plan:

| Python + FastAPI | Go |
|---|---|
| CRUD, business rules, admin panels, cabinets | gateway, proxy, traffic routing |
| integrations, webhooks, payments | public API with high load and strict latency |
| LLM, ML, data processing, documents (PDF, DOCX, XLSX) | thousands of long-lived connections (WebSocket, SSE) |
| Telegram bots, parsers, background jobs | CPU-heavy parallel work, mass network polling |
| MVPs and prototypes | a tool shipped as one binary |

One service, one language; its tooling (migrations, seeds, CLI) in the same language. At most two backend languages per project.

**Gin by default.** Fiber only for a simple high-load API with a measured HTTP-layer bottleneck, or if the project already uses it (fasthttp: no `net/http` middleware, no HTTP/2, context values valid only inside the handler).

**Python components**: FastAPI + uvicorn · Pydantic v2 · pydantic-settings with a per-service prefix (`ORDERS_`) · SQLAlchemy 2.0 ORM (`Mapped`, `select()`), asyncpg (psycopg 3 for sync) · Alembic · Beanie (or async PyMongo + Pydantic) for MongoDB; never Motor · httpx with explicit timeouts · structlog (JSON in prod) · auth service: AuthX + PyJWT for JWKS; consumers: PyJWT; passwords: pwdlib argon2id (bcrypt only to verify and rehash old hashes) · boto3/aioboto3 · deps listed in `pyproject.toml`, locked with `uv.lock` · pytest + pytest-asyncio + httpx `AsyncClient` · ruff + mypy strict. One Python version across CI, `requires-python`, Dockerfile. Async by default; nothing blocking inside `async def`.

**Go components**: Gin · GORM (pgx inside) · golang-migrate or goose (Atlas may generate from GORM models); never `AutoMigrate` at start · `mongo-driver/v2` with typed structs · `golang-jwt/jwt/v5` + `MicahParks/keyfunc/v3` · env → struct (`caarlos0/env`) · `log/slog` · air in dev · `go vet` + pinned golangci-lint · `go test -race`, `httptest`, testcontainers-go. Raw SQL via pgx/sqlc only as the data exception. One Go version everywhere; code generators pinned to their runtime library version.

## Frontend

| Choose | When | Serve |
|---|---|---|
| Plain HTML/CSS/JS | 1–5 pages: landing, invitation, promo, a form; no login, no complex state | static from Caddy/nginx |
| Jinja2 in FastAPI + a little JS | pages rendered by the backend: simple shop front, checkout forms, emails | FastAPI |
| React SPA (Vite + TS) | everything behind a login: admin, CRM, cabinets, dashboards, complex forms; no SEO | `dist/` in nginx/Caddy, `/api` proxied |
| Next.js (App Router, TS) | public site where SEO, OG previews, first-screen speed matter: many pages, catalog, blog, i18n | content changes only with releases → `output: 'export'` static; per-request data → `output: 'standalone'` in Node |

Never Next.js for one or two static pages, never React for a three-field form. Next.js is only a frontend: business logic, DB access, and secrets stay in FastAPI/Go.

**React libraries**: TypeScript `strict` · React Router · TanStack Query over `fetch`/openapi-fetch · types generated from OpenAPI (openapi-typescript) · react-hook-form + zod · zustand only when Query and local state are not enough · Tailwind with tokens in CSS variables (or CSS Modules; one system) · Radix/shadcn, lucide-react · Motion; GSAP for complex scroll scenes · react-i18next / next-intl · self-hosted fonts · Leaflet · `tsc --noEmit`, ESLint, Vitest + Testing Library, Playwright e2e · npm + `package-lock.json`, `npm ci`.

The frontend calls `/api` on the same origin (Vite proxy in dev, nginx/Caddy in prod); CORS only when origins really differ. `VITE_*`/`NEXT_PUBLIC_*` reach the browser: never secrets. Node is only a build tool and the Next.js runtime.

## Data

**PostgreSQL by default.** Search: full-text + `pg_trgm` first; embeddings: `pgvector`; flexible fields: `JSONB` + GIN. ORM only; raw SQL as the documented exception (`db.md`). Migrations only, applied automatically by a `migrate` step; idempotent seeds. Pool × processes × replicas < `max_connections`. SQLite only in single-user tools without a server. Tests on real PostgreSQL.

**MongoDB only when all hold**: the record is an aggregate read and written whole by id; its structure varies between records and changes often; few relations, none changed in the same transaction; queries use a small known set of indexed fields; large, mostly append-only volume. **Stop signs** (any → PostgreSQL): money, stock, or money-relevant statuses; a transaction spanning these and PostgreSQL data; reports joining relational entities; the only argument is "no schema is simpler".

| Signal | Choice |
|---|---|
| money, orders, stock, balances, bookings; users, roles, rights; many joins, reports; atomic multi-entity changes | PostgreSQL |
| a few flexible fields on a relational entity; heterogeneous catalog attributes alongside orders | PostgreSQL + `JSONB` |
| block page content, CMS documents | MongoDB or `JSONB` |
| raw API responses, webhook bodies | MongoDB with TTL or a `JSONB` table |
| event/action logs with varied payload, high volume | MongoDB with a TTL index |
| chats, LLM dialogue history | MongoDB (messages in their own collection) |
| embeddings | PostgreSQL + `pgvector` |
| cache, counters, OTP codes | Redis |
| unsure | PostgreSQL |

Mixed setups: PostgreSQL is the source of truth; MongoDB lives in a **separate** service that owns its collections, linked by UUID strings, consistent through events (outbox). Two DBMS in one service only with an agreed reason. MongoDB rules (Beanie/typed driver, `$jsonSchema`, `schema_version`, indexes in code, no unbounded arrays, no manual joins, replica set for transactions, versioned data migrations, real Mongo in tests) are in `db.md` R-DB-MONGO.

**Redis** is a derived, fast layer; losing it loses speed and temporary state, never data. Uses: cache with TTL and versioned keys (falls back to the DB); rate limits (`INCR` + `EXPIRE`); carts, OTP, CSRF with TTL; Celery broker; Pub/Sub only after commit; locks `SET NX EX` (advisory locks for critical sections); bot FSM state. Never the only copy of users, orders, payments, balances, history, files, or must-deliver events (outbox). Cache-only Redis: `allkeys-lru`, no volume. Broker or must-keep temporary data: `appendonly yes`, `noeviction`, named volume. One module (`core/cache.py`) talks to Redis.

**Files** always in S3 (locally SeaweedFS or MinIO, pinned, plus a bucket-init container); DB stores metadata and the key; served by presigned URL (signed with the public host) or proxied with a rights check; heavy processing in a worker.

## Background work and integrations

| Need | Use | Note |
|---|---|---|
| background and delayed jobs | Celery + Redis, worker as its own compose service | idempotent tasks, retries with backoff |
| periodic jobs | Celery beat in exactly one instance; simple cases: a scheduler service (APScheduler) | lock with `SET NX` or an advisory lock when replicated |
| events between services with delivery guarantee | RabbitMQ (aio-pika) + transactional outbox | publish only after commit |
| short "after the response" action without guarantees | FastAPI `BackgroundTasks` | lost on restart: not for anything important |
| live updates in the browser | SSE or WebSocket + Redis Pub/Sub across replicas | long proxy timeouts, no buffering |
| Telegram bot | aiogram 3 as its own service; webhook in prod, polling locally | notifications only → Bot API via httpx |
| acting as a Telegram user | Telethon, only on an explicit task | the session file is a secret |
| LLM | official SDKs behind the project's provider interface | local models in their own container |
| documents | python-docx, openpyxl, reportlab, in a worker | — |
| content edited by non-developers | a ready headless CMS (e.g. Directus) in compose | only with the user's agreement |

No arq, RQ, Dramatiq, or Kafka next to Celery and RabbitMQ without an explicit request.

## Observability and CI

- `/health` = process alive, no dependency calls; `/ready` = the service's own infrastructure only (its DB, Redis, broker), never neighbours. Logs to stdout, structured, with request id.
- Three or more services calling each other → OpenTelemetry + Jaeger under a compose profile, Prometheus metrics.
- CI on GitHub Actions: linters, types, tests with PostgreSQL, every build variant, `docker compose config --quiet`. Tags, pushes, and deploys only on the user's direct request. Secrets only in GitHub Secrets; actions pinned.
- Hosting: own server (Dockerfile images + compose or podman Quadlet) or a PaaS from a Dockerfile (e.g. Railway) per `deploy-variants`.

## Anti-patterns

Node.js backends next to Python services · new APIs on Django/Flask · SQLite or JSON files as an app's store · MongoDB for relational data or "because schemaless is simpler" · two DBMS in one service without reason · one JSON column "for everything" · raw SQL strings without reason · `create_all()` at start · in-process caches or rate limiters · critical data only in Redis · uploads to the container disk · parts of the system started by hand or by an author-only script · `make` as the only run instructions · secrets in compose, code, or CI files; missing `.env.example` · `latest` tags or `version: latest` linters · `depends_on` without healthchecks · DB ports on `0.0.0.0` · Next.js/React for one static page · Next.js with Prisma and business logic · `npm install` without a lock in images; unpinned Python deps · disabled TLS checks in builds · host installs of any kind · building on the server with `git pull && docker compose up --build` · extra dependencies for one function; python-jose, passlib · per-service JWT issuing, HS256, auth modules, unrequested IdPs.

## Checklist

- [ ] `cp .env.example .env && docker compose up -d --build` brings up everything, migrations and seeds included.
- [ ] Backend is FastAPI, or Go (Gin; Fiber only by §Backend) with the reason named.
- [ ] Frontend chosen by the §Frontend table; one frontend framework.
- [ ] Persistent data in PostgreSQL; MongoDB only by §Data with the reason named; schema only through migrations.
- [ ] Data access through ORM/ODM; raw SQL only as a parameterised, documented exception.
- [ ] Nothing installed on the host beyond the requirements (`requirements.md`); services run in compose.
- [ ] Redis holds only derived/temporary data with TTLs; memory policy matches its role.
- [ ] Files in S3, keys in the DB.
- [ ] Auth is the separate service; consumers verify JWT via JWKS; access TTL is finite.
- [ ] Every new technology was agreed with the user.
