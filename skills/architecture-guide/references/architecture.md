# Architecture rules (`04-architecture`, condensed)

Alexey's house rules for splitting a system into services and modules and laying out code inside them. Code-level rules (layer direction, naming, config, errors) are enforced by `rules/layers.md`, `rules/db.md`, `rules/tests.md`; this file keeps the **system-level** decisions in full and the code-level parts as a short reminder.

Applying them:
- In an existing project, learn its structure and follow its conventions. Do not copy anti-patterns (§12) into new code even if they are nearby.
- Do not move old code unasked. A violation goes into the report with a refactoring proposal as a separate task.
- Precedence: the user's direct request > project rules (`AGENTS.md`, `CLAUDE.md`) > these rules. On a conflict follow the higher one and mention it.

## 1. In short

1. A microservice is autonomous: own code, config, DB, migrations, tests; its build recipe lives separately in `nix/`. It talks to others only through an API or events.
2. Inside a service each file does one clear thing: router, schemas, models, repository, service, permissions, config, constants apart.
3. Dependencies go one way: router → service → repository → models.
4. A modular monolith uses the same layers plus hard module boundaries: another module only through its public interface.
5. A service keeps no state in the process and runs as N instances without code changes.
6. The DB is accessed through an ORM; raw SQL is a justified exception living only in the repository.
7. No fanaticism: a layer appears when it has work to do.

## 2. System shape

- The shape (monolith, modular monolith, microservices) is set by the user or the existing project. **Never change it on your own.**
- New project, no shape given → propose a **modular monolith** whose boundaries let a module become a service. Split out a service only if that part has **its own deploy rhythm or load**, its **failure must not hit the rest** (payments, external APIs, LLM generation), it needs **another runtime** (GPU, heavy deps, another language), or **separate secrets** (key handling).
- **Authentication is ALWAYS a separate `auth` service** with its own PostgreSQL, Python + FastAPI + AuthX, in any shape including a monolith. Everything else only verifies its JWTs (§3.3). Auth as a monolith module, an external IdP (Keycloak, Authentik, OIDC providers) or server sessions instead of JWT — **only on the user's explicit requirement**. Details: skill `auth-service`.
- A flat `main.py + models.py + schemas.py + database.py` is fine for a teaching example or a two-endpoint script. If the app will grow, lay it out by layers at once.
- One repository layout for every shape. Root: `README.md`, `AGENTS.md`/`CLAUDE.md`, `docs/`, build and run files (`flake.nix`, `flake.lock`, `compose.yaml`, `compose.override.yaml`, `.env.example`, optional `Makefile`), `nix/` and `deploy/`, with sops `.sops.yaml` and `secrets/`, service files (`.gitignore`, `.gitattributes`, `.editorconfig`, CI configs). **All code in `src/<component>/`** (monolith, service, `auth`, frontend, worker), each with its manifest, `.env.example`, migrations and tests. No `tests/`, `scripts/`, `migrations/` in the root.

```text
project/
├── README.md, AGENTS.md, CLAUDE.md, docs/
├── flake.nix, flake.lock, compose.yaml, .env.example, .gitignore, .gitattributes, .editorconfig
├── nix/            # api.nix, auth.nix, web.nix, images.nix, module.nix, vm-test.nix
├── deploy/         # server units and release scripts, if any
└── src/
    ├── api/        # monolith or service: app/, migrations/, tests/, pyproject.toml
    ├── auth/
    └── web/        # frontend: own src/, package.json
```

## 3. Microservices: autonomy and isolation

### 3.1 What a service owns
A service can be moved to its own repo with its `src/` folder and `nix/` recipe and still build, run and pass tests.

| What | Rule |
|---|---|
| Code | only in the service folder; no imports of another service's code |
| Config | own settings module and `.env.example`; the root `.env.example` only aggregates for compose |
| DB | own database — at least a separate DB or schema and a DB user with rights only to it |
| Migrations | in the service folder, applied only to its DB |
| Build | own recipe `nix/<service>.nix` (and Dockerfile in the service folder if used); needing a neighbour's code to build is coupling — remove it |
| Tests | in the service folder, run without other services |

### 3.2 How services talk
- **Sync:** the other service's public HTTP or gRPC API. Internal endpoints under `/internal/...`, protected by a service token or mTLS, not a user JWT.
- **Async:** events through a broker — **default RabbitMQ**; Kafka, Redis Streams and others **only on the user's explicit request**. An event states a fact that happened: `order.paid`, `user.registered`.
- **Never:** import another service's modules; connect to its DB, even read-only or "temporarily"; keep an ORM model of the same table in two services or JOIN across services; exchange data through a shared volume, files or Redis keys.
- Choosing: the answer is needed now and the operation cannot proceed without it → API. Others must learn that something happened → event. **In doubt → event**: it couples less.

#### Services in different languages
A link between a Go and a Rust service is the same service boundary as above: its own DB per service, no shared database, no shared code. The language pair changes only the contract tooling. Facts below are by the vendors' documentation (read 12 November 2026), **not cross-checked** against a second source; rows marked "guide rule" are this guide's own advice, not a vendor statement.

| Link | Use when | Do not use when | Where the contract lives | Failure mode to design for |
|---|---|---|---|---|
| **gRPC** | an internal call needs the answer now; generated client and server stubs in each language ([grpc.io](https://grpc.io/docs/what-is-grpc/introduction/)); server, client or bidirectional streams ([grpc.io](https://grpc.io/docs/what-is-grpc/core-concepts/)) | the caller is a browser: it needs gRPC-Web and a proxy, Envoy in the official tutorial ([grpc.io](https://grpc.io/docs/platforms/web/basics/)); the Rust side would have to use the official `grpc` crate, which is a preview, "not recommended for production use" ([grpc.io](https://grpc.io/blog/grpc-rust-announcement/)) | `.proto` files in a Buf module (`buf.yaml`); `buf lint` checks style ([buf.build](https://buf.build/docs/lint/)); `buf breaking --against '.git#branch=main'` compares with a past version ([buf.build](https://buf.build/docs/breaking/)); `buf generate` makes code per language ([buf.build](https://buf.build/docs/generate/)) | a deadline expires: the RPC ends with `DEADLINE_EXCEEDED` ([grpc.io](https://grpc.io/docs/what-is-grpc/core-concepts/)); old and new versions run together during a rollout, "clients and servers are never updated at exactly the same time" ([protobuf.dev](https://protobuf.dev/best-practices/dos-donts/)) |
| **HTTP + OpenAPI** | a public or browser-facing API; the spec is a language-agnostic description usable for code generation of servers and clients ([OAS](https://spec.openapis.org/oas/latest.html)) | the generators of the two languages disagree on the spec version: `progenitor` (Rust client) reads OpenAPI 3.0.x and "may fail for some OpenAPI documents" ([progenitor](https://github.com/oxidecomputer/progenitor)), `utoipa` (Rust, code-first) writes 3.1 ([utoipa](https://github.com/juhaku/utoipa)) | one OpenAPI file; Go: `oapi-codegen` reads 3.0 and 3.1 and generates servers and clients ([oapi-codegen](https://github.com/oapi-codegen/oapi-codegen)); multi-language: `openapi-generator` ([releases](https://github.com/OpenAPITools/openapi-generator/releases)). None of these is an OpenAPI Initiative tool | generator output differs per language or fails on a spec feature; the spec drifts from the code when it is not generated or checked in CI (guide rule) |
| **Broker** (RabbitMQ default) | others must learn that something happened (§3.2 above); the producer must not wait for consumers | the caller needs the answer to continue (guide rule) | an event schema in the owner's service folder (guide rule): the broker does not check it, RabbitMQ "does not validate or use" type, content-type or headers ([rabbitmq.com](https://www.rabbitmq.com/docs/publishers)). Optional envelope: CloudEvents, required `id`, `source`, `specversion`, `type`; incompatible schema changes should use a different `dataschema` URI ([cloudevents](https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md)) | duplicates: acknowledgements give at-least-once delivery and "it is recommended that consumer implementation is designed to be idempotent" ([rabbitmq.com](https://www.rabbitmq.com/docs/reliability)); the relay of an outbox can publish duplicates too ([microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)) |
| **FFI** (Go cgo, Rust `extern "C"`) | last resort inside **one process**: a library exists only in the other language and cannot become a service | connecting two services (it is not a way to connect services); the build has no C toolchain: cross-compiling needs a C cross-compiler ([cmd/cgo](https://pkg.go.dev/cmd/cgo)) | a C header; `cbindgen` makes it from Rust code but "may randomly fail to support some particular situation" ([cbindgen](https://github.com/mozilla/cbindgen)); Rust types crossing the boundary need `#[repr(C)]` ([Nomicon](https://doc.rust-lang.org/nomicon/ffi.html)) | one process is one crash domain: unwinding with the wrong ABI is undefined behavior ([Rust Reference](https://doc.rust-lang.org/reference/panic.html)), so catch panics inside the exported function (guide rule); Go pointers passed to C must point to pinned memory and C may not keep them ([cmd/cgo](https://pkg.go.dev/cmd/cgo)) |

Rules:
- **At most two backend languages per project** (`stack-choice`). A third language is a new decision record, not a new row.
- A cross-language call is a service call (gRPC, HTTP or an event). Sharing a database or a library of generated models between services is still forbidden by §3.1–3.2.
- The contract is a file in the owner's service folder; consumers generate their own code from it, so no service imports another's code. CI runs the breaking-change check (`buf breaking`) or compares the OpenAPI file with `main`.
- Never reuse or renumber a protobuf field; reserve deleted numbers and names ([protobuf.dev](https://protobuf.dev/programming-guides/proto3/)).
- Rust gRPC: use `tonic` (its README speaks of production systems, version 0.x, not 1.0 — [tonic](https://github.com/hyperium/tonic)); the official `grpc` crate is a preview ([grpc.io](https://grpc.io/blog/grpc-rust-announcement/)).
- FFI only inside one process, when no service boundary is acceptable and the library has no other form; record the reason in the decision record.

### 3.3 Foreign data and authentication
- Get another service's data through its API, or keep a **projection** of only the needed fields updated by the owner's events. The owner stays the source of truth.
- Reference a foreign entity by id (`customer_id: UUID`) **without a foreign key**.
- Tokens (JWT RS256/ES256) are issued **only by `auth`**. Others verify locally with the public key from JWKS (`/.well-known/jwks.json`; Python PyJWT, Go `golang-jwt/jwt/v5` + `MicahParks/keyfunc/v3`), take `sub` and `roles`, and **never read the users table**. Access = non-empty intersection of user roles and required roles. Private key only at `auth`. Access-token TTL is a project setting and **never infinite**. HS256 with a shared secret or several issuers — only on explicit requirement.

### 3.4 One failure does not drop the rest
- **Every outgoing call has a timeout** (default 2–10 s) and a bounded number of retries with backoff. No infinite retries.
- Neighbour down → a domain error (`PaymentsUnavailable`) and a degraded mode: serve cache, queue the operation, or switch the feature off. Never a 500 with a stack trace.
- **Readiness checks only the service's own infrastructure** (its DB, Redis, broker); tying it to neighbours cascades one failure into all.
- Publish events through a **transactional outbox**: the event row is written in the same transaction as the data; a separate process sends it. Never publish from the request handler.
- **Consumers are idempotent**: a table of processed `event_id`s or a conditional `UPDATE`.

### 3.5 Shared packages
**By default there are none.** A little duplication beats coupling; a 30–80-line JWT check or logger setup is copied per service.

| May be shared | Must NOT be shared |
|---|---|
| contracts as spec files: OpenAPI, proto, event JSON Schema | ORM models, DB schema, migrations |
| clients and types **generated** from contracts | repositories, services, any business logic |
| UI kit and API client for several frontends of one product | domain enums and constants: statuses, roles, plans |
| small technical utilities without domain knowledge — only under the conditions below | one shared `Settings` class; hand-written DTOs everyone imports |

A technical utility may be shared only if all three hold: it knows no domain entity and imports no service code; it is a **versioned** dependency a service can stay behind on (no `COPY ../common`); changing it never forces a simultaneous redeploy of several services. Test: if editing the shared package forces two services to change or redeploy together, it is coupling — remove it and give copies. DTOs: each service declares only the foreign fields it needs and ignores unknown ones (tolerant reader).

### 3.6 Microservice monorepo
`src/users/`, `src/orders/` (each fully independent: `app/`, `migrations/`, `tests/`, manifest, `.env.example`), `src/notifications/` (no DB: listens to events, calls external APIs), `src/web/` (public APIs only), optional `src/contracts/` (specs, not code). Isolation must be visible in compose: each service has its own `<SERVICE>_DATABASE_URL` with its own DB and user, no address of a foreign DB, `depends_on` only on its own infrastructure. One Postgres instance with several databases is fine if each service has its own DB user limited to its DB; **one superuser for all databases is forbidden**.

## 4. Inside a service (reminder; enforced by `rules/layers.md`)

Layers: router (`api/routers/<entity>_router.py`), schemas, models, repository (ORM queries, no `commit`), service (rules, scenario, transaction, clients, events; no HTTP), permissions/deps (`require_roles`), `domain/` (enums, domain errors, pure rules; imports nothing from the project), clients (timeouts, foreign errors → domain errors), workers (thin wrappers over services), `core/` (config, database). Direction `api → services → repositories → models`; `core` and `domain` for all. A cycle means wrong boundaries — move shared code down or reverse the dependency; never hide it with an in-function import. Role checks in a router dependency; **object rights** ("own order", "own organisation") in the service with `actor_id`. Go: Gin by default (Fiber only with measured evidence or existing use), `cmd/` assembles, `internal/{config,domain,service,repository,http,client,worker}`, interfaces declared by the consumer. Large services may split by feature instead of by layer.

## 5. Database access (reminder; enforced by `rules/db.md`)

ORM by default: SQLAlchemy ORM, GORM (or the project's ORM, e.g. ent), Beanie or typed `mongo-driver/v2` structs. Raw SQL only when the ORM cannot (analytics, `COPY`, `LISTEN/NOTIFY`, recursive CTEs, complex full text) or a measured performance problem — then only in the repository, parameterised, with a "why not ORM" comment. **Never build SQL by concatenation or formatting**; sort fields from a whitelist.

## 6. Horizontal scaling

Every service is designed to run as **N instances** (`docker compose up --scale orders=3`, several replicas behind a balancer) without code changes.

- **Stateless.** Nothing in process memory or local disk that another request needs. Data in the DB; cache, locks, rate-limit counters, idempotency keys and temporary codes in Redis; the user from the JWT, not an in-memory session; uploaded and generated files in object storage with only the key in the DB; jobs in a broker or a queue table. In-process cache only for immutable data (config, templates), never a source of truth.
- **IDs** come from the DB or a UUID generator, never an in-memory counter.
- **Workers and consumers** are safe in parallel: take jobs with `with_for_update(skip_locked=True)`, cut duplicates with a unique key, send events via outbox.
- **Periodic jobs run in exactly one executor**: a separate scheduler service or a replica holding a leader lock. Cron or a scheduler inside every API replica (including `lifespan`) is forbidden.
- **Migrations** run as a separate step (`migrate` service or a locked process), never by every replica at startup.
- **WebSocket and SSE** deliver events between replicas through pub/sub (Redis Pub/Sub or a broker); no reliance on sticky sessions.
- **Connection pool**: pool size × processes × replicas < `max_connections`.
- **Health**: `/health` = process alive; `/ready` = own DB, Redis, broker reachable.
- **Graceful shutdown** on SIGTERM: stop accepting, finish current requests, return unfinished jobs to the queue, close pools.
- **Config only from env**; replicas differ only by environment.

Check: run three instances and the main scenario — same result as one instance: no duplicate emails or jobs, files reachable from any replica, shared limits.

## 7. Modular monolith

Same layers, but module boundaries instead of service isolation. The monolith is one component `src/<name>/`.

```text
app/
├── main.py              # wires module routers
├── core/                # ONLY infrastructure: config, database, logging, security, base errors
├── modules/
│   ├── catalog/
│   │   ├── __init__.py        # public interface: CatalogFacade, ProductRef, facade domain errors
│   │   ├── catalog_facade.py  # methods for other modules; DTOs in and out, never ORM objects
│   │   ├── product_model.py   # catalog_* tables or a `catalog` Postgres schema
│   │   └── product_router.py, product_schema.py, product_service.py, product_repository.py, …
│   ├── orders/          # uses the catalog only through CatalogFacade
│   └── notifications/   # listens to orders.* events, imports nothing from orders
├── workers/
└── migrations/
tests/                   # modules/<module>/…, test_module_boundaries.py
```

- Auth is not a module — it is the `auth` service; the monolith only verifies JWTs in `core/security.py`.
- A module is a **business area** (catalog, orders, billing), not a technical layer. No monolith-wide `models/` or `services/`.
- Public interface = what `__init__.py` exports: facade, DTOs, facade errors. Other modules never import foreign `*_repository`, `*_model`, `*_router`, `*_service` or `_`-prefixed functions.
- The facade takes and returns DTOs, never ORM objects.
- **Each table belongs to one module** (module prefix or own schema); no cross-module SQL, no cross-module `relationship`, references by id, **no cross-module foreign keys by default** (an exception is agreed with the user). One migration touches one module's tables.
- `core/` holds only infrastructure; a business concept there moves into a module.
- Need an answer now → call the facade; announce a fact → internal domain event. A ↔ B calls both ways → replace one direction with an event or redraw the boundary.
- **Extraction test**: replace the facade with an HTTP client of the same interface; if anything else in the caller must change, the boundary leaks.
- Absolute cross-module imports only; enforce boundaries with a test or linter (import-linter, eslint-plugin-boundaries) in CI.

## 8. Frontend (reminder; enforced by the TS/React rules and `rules/design.md`)

`src/web/src/`: `app/`, `pages/` (compose features, no requests), `features/<f>/` (components display only, hooks fetch via the API layer, store), `shared/{api,config/env.ts,constants,ui,lib}`, `styles/`, `i18n/`. Chain: component → hook → API module → `http.ts` (base URL, headers, 401, error format live only there). Types generated from OpenAPI or in `shared/api/<entity>Types.ts`. Features do not import each other. **Prices, rights and status transitions are computed by the backend**; a hidden button is not protection. Env read only in `shared/config/env.ts`.

## 9–10. Tests and cross-cutting rules (pointers)

Tests by layer and the TDD offer criteria: `rules/tests.md` and the orchestrator's TDD loop. Config, errors, migrations (no `create_all`/`AutoMigrate`/DDL at startup), transactions (service commits, no external calls inside an open transaction, races closed by conditional update or row lock), naming, typing, structured logs with `request_id`: `rules/layers.md`, `rules/db.md` and the language rules.

## 11. No fanaticism

A layer, file, package or abstraction appears when it has work. A 150-line module is 3–5 files, not fifteen.

- One resource → `order_router.py`, `order_service.py`, `order_repository.py` side by side, no layer folders yet.
- A service without a DB needs no models or repositories (notifications: `main.py`, `config.py`, `notification_schema.py`, `notification_router.py`, `notification_service.py`, `clients/sms_client.py`).
- Plain reads without rules may call the repository directly; the first rule, check, side effect or multi-step transaction brings a service, and then all the entity's endpoints go through it.

**Time to split** if any: a file > ~400 lines or a function > ~50 (guideline); describing the file needs "and"; one file imports the web framework, the ORM and an HTTP client; a rule cannot be tested without an HTTP client; different tasks keep editing the same file.

**Overdone** if any: 5–10-line files that only re-export or proxy; a call crosses 3–4 layers that add nothing; an interface with one implementation and no second planned; `BaseRepository[T]`/`BaseService[T]` for a couple of CRUD calls; three identical models of one object with hand mappers; factories, DI containers or strategies with one behaviour.

**Abstractions**: an interface only when there are already two implementations (payment, LLM providers, S3 vs local storage) or it is a boundary with an external system tests must fake. No repository interface (fake via dependencies in Python; narrow consumer-side interface in Go). No abstractions "for the future".

## 12. System-level anti-patterns

| Anti-pattern | Why | Instead |
|---|---|---|
| Shared DB for several services, one superuser for all databases | distributed monolith: one migration breaks others, no separate deploy | own DB and user; data through API or events |
| A service reads another's tables or keeps an ORM model of them | hidden schema contract; a renamed column breaks a foreign service | the owner's API or a local projection fed by events |
| Shared package of models, enums, business logic; `COPY ../common` | every change needs a simultaneous release; a service cannot build alone | §3.5: contracts and generated clients, copies for the rest |
| A module imports a private function from another module's router | the boundary exists only on paper | a facade method of the owning module |
| In-process state: global dict as storage, in-memory rate limiter, uploads into the container, in-memory ID counter | each replica has its own truth: limits bypassed, files lost, IDs duplicated | DB, Redis, S3 (§6) |
| A scheduler or cron in every API replica, incl. `lifespan` | three replicas → the job runs three times | a scheduler service or a leader lock |
| Publishing to the broker straight from the request handler | event lost, or sent about data that never committed | transactional outbox |
| Ten abstraction layers for simple CRUD | lots of code without logic, slow to read and change | §11 |

Code-level anti-patterns (god files, SQL in routers, scattered role checks, magic strings, `os.getenv` everywhere, `create_all`, `commit` in the repository, `HTTPException` in services, `fetch` in components, `utils.py`) are in the rules files.

## 13. Design checklist

- [ ] The shape was given by the user or the project, or a modular monolith was proposed; every separate service has a named reason (own load or deploy rhythm, failure isolation, another runtime, separate secrets).
- [ ] `auth` is a separate service; others verify RS256/ES256 JWTs locally via JWKS; access-token TTL is finite.
- [ ] Each service owns its code, config, DB + DB user, migrations, build recipe and tests; none connects to a foreign DB or imports foreign code.
- [ ] Sync calls only through public/`/internal` APIs; events (RabbitMQ by default) through outbox; consumers idempotent.
- [ ] Every outgoing call has a timeout, bounded retries and a degraded mode; readiness checks only own infrastructure.
- [ ] Nothing domain-level in shared packages.
- [ ] Every component runs in N replicas: no in-process state, periodic jobs and migrations run once, WebSocket/SSE via pub/sub, pool sizes fit `max_connections`.
- [ ] In a modular monolith: business-area modules, facades with DTOs, one owner per table, a boundary test in CI.
- [ ] No layer, service, store or abstraction without work to do.
