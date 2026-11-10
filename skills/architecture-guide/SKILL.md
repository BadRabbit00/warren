---
name: architecture-guide
description: Use when designing, choosing components for, or critiquing a system architecture - system shape and service boundaries (04-architecture), then a per-layer decision (needed? → choice → why → rejected) across databases, brokers, background work, files, ingress, access and secrets, coordination, observability, realtime, AI and delivery, with clouds and licence risks.
---

# Architecture guide

Alexey's architecture rules (`04-architecture`) plus his eleven layer guides (October 2026) in one place. The orchestrator uses it at the architecture stage; `architect-critic` uses it to check a draft. Load only the reference files the decision needs.

## Contents

1. [When to use](#when-to-use) · 2. [Precedence](#precedence) · 3. [Procedure](#procedure) · 4. [Decision record](#decision-record) · 5. [Layers](#layers) · 6. [Clouds and portability](#clouds-and-portability) · 7. [Red flags](#red-flags-checked-30-october-2026) · 8. [Reference files](#reference-files)

## When to use

- Stage 2 (architecture) of a new project, or a change that adds a service, a store, a broker, or an external product.
- Reviewing a draft architecture (`architect-critic`).
- A question like "do we need Kafka / Kubernetes / a second database / Elasticsearch here?".

Not for code layout inside a service — that is `rules/layers.md`; not for the stack of a single service — that is `stack-choice`.

## Precedence

1. The user's explicit request.
2. Project rules (`AGENTS.md`, `CLAUDE.md`, existing `docs/`).
3. House rules: `references/architecture.md` (`04`), skills `stack-choice`, `auth-service`, `deploy-variants`, `sops`.
4. Layer-guide defaults (`references/layers/*.md`).

The layer guides are a field guide of options; the house rules fix the stack where they speak. Known overlaps:

| Topic | House rule | Layer guide | Do |
|---|---|---|---|
| Product auth | own `auth` service, FastAPI + AuthX, RS256/ES256 JWT via JWKS | IdPs and auth libraries (`access.md`) | house rule; an IdP, auth module or server sessions only on explicit request. The guide's proxies (Authelia, Pomerium, Cloudflare Access) may be **proposed** for staff access to infrastructure tools, never for product users |
| Events between services | RabbitMQ + transactional outbox | Kafka, NATS, Redpanda (`brokers.md`) | house rule; another broker only on explicit request — if a stated need matches the guide's "switch when", say so in the record |
| Python background jobs | Celery + Redis; Celery beat once | Postgres queues, Temporal, DBOS (`background.md`) | house rule for Python; the guide for other stacks, for durable multi-step processes, or on request |
| Cache, locks, limits | Redis | Valkey (BSD fork, same protocol) | keep the project's choice; for a new project list the Redis/Valkey licence difference as a question for the user |
| Object storage example | `04` §6 names "S3, MinIO" | MinIO open source is archived (`files.md`) | never propose MinIO for a new project: the target cloud's S3, or SeaweedFS / Garage / RustFS self-hosted |

## Procedure

0. **Facts first.** Load and peaks (per second, not per day), data kinds, volume and growth, sensitivity and where it must live (KZ/RU residency), integrations and their limits, named extensions, realtime needs, hosting and budget, team and existing stack. Unknown facts are ❓ questions, not guesses.
1. **Shape.** Given by the user or project → keep it. New → modular monolith; split a service only for its own load or deploy rhythm, failure isolation, another runtime, or separate secrets (`references/architecture.md` §2). `auth` is always separate.
2. **Per layer**, in this order, open the layer file only if the layer may be needed:
   1. **Needed?** Apply the layer's Rule 0. Most layers for most projects end here: "not needed — Postgres / the platform covers it".
   2. **Choice.** Start from the default in the layer's *Task → default* table. Move to the "switch when" column only when a stated fact meets it.
   3. **Why.** Cite the facts it rests on (`300 rps peak`, `2 TB/year`, `data must stay in KZ`).
   4. **Rejected.** The nearest alternative and the fact that rules it out.
   5. **Fit.** The target cloud's service or self-hosted; licence (open / source-available / proprietary) and status (base / popular / growing, archived).
3. **Cross-check** the whole design: horizontal scaling (`references/architecture.md` §6), failure isolation (§3.4), ownership of every table, one owner per secret, the design checklist (§13). Every box maps to a stated need.

Simplest design that meets the stated facts wins. Complexity for unnamed future needs is an objection, not a feature.

## Decision record

One line per layer, in the architecture slides and in `docs/SPECIFICATION.md` → *Tech stack* (put the rejected option into the *Why* column):

```text
<layer>: not needed — <why> | <choice> (<licence>, <status>) — <why, with facts>; rejected: <alt> — <fact>
```

Example:

```text
databases: PostgreSQL 17 (open, base) — 40k orders/month, relational reports; rejected: MongoDB — data is relational, joins in every report
brokers: RabbitMQ + outbox (open, base) — orders → notifications, one consumer, delivery guarantee needed; rejected: Kafka — no replay need, 2k events/day
background: Celery + Redis (house stack) — emails and PDF exports; rejected: Temporal — no multi-day processes
search: not needed — catalog of 800 items, Postgres full text covers it
```

## Layers

| Layer | File | Rule 0 in one line |
|---|---|---|
| Databases | `layers/databases.md` | PostgreSQL first; a second database only after a measured problem |
| Brokers, streams, CDC | `layers/brokers.md` | a broker is one more database; jobs in Postgres or Redis/Valkey; Kafka only for many consumers or replay |
| Background work | `layers/background.md` | cron + a Postgres queue first; durable engine for long money-losing processes; Airflow for many dependent pipelines |
| Files and data lake | `layers/files.md` | user files in object storage, key in the DB; no lake while ClickHouse/Postgres hold the analytics |
| Traffic ingress | `layers/ingress.md` | one proxy with auto-TLS + CDN; API gateway for sold APIs; mesh for dozens of services |
| Access and secrets | `layers/access.md` | no home-made auth or crypto; secrets encrypted in git (SOPS), from a manager at runtime; actions pinned by SHA |
| Coordination and flags | `layers/coordination.md` | k8s DNS/Lease/ConfigMap and Postgres advisory locks first; flags in config until segments appear |
| Observability | `layers/observability.md` | OpenTelemetry; RED metrics, JSON logs with `trace_id`, error tracker, external uptime; alert on user symptoms |
| Realtime and comms | `layers/realtime.md` | SSE from the backend first; email through a delivery service; own media/TURN only with people to run UDP |
| AI infrastructure | `layers/ai.md` | provider API before own GPUs; all LLM calls through one gateway with tracing and evals; pin AI deps by hash |
| Platform and delivery | `layers/platform.md` | k8s only with many services, several teams and an owner; Compose + Kamal for 1–3 servers; IaC and tested backups from day one |

Each file has: concepts, Rule 0, classes with every option's licence, status, internals, good-for and bad-for, clouds, and the *Task → default → when to switch* table.

## Clouds and portability

- **Migration targets** (Alexey's projects move here): **Yandex Cloud**, **DigitalOcean**, **Railway**. Each layer file lists their services first, then AWS, Google Cloud, Azure, Cloudflare.
- Residency: for government and bank clients in KZ/RU, check where data is physically stored and processed (Yandex Cloud, AI Studio, SpeechKit, Postbox).
- Keep the parts that differ between clouds behind portable seams: OCI images; OpenTofu; own proxy (Caddy/Traefik/Envoy) with the cloud LB as plain L4; OTel Collector; OpenFeature; own LLM gateway; S3 API; protocol-compatible brokers (AMQP, Kafka, SQS, MQTT).
- Railway: no managed brokers (templates only), **no inbound UDP for WebRTC**, **no confirmed GPUs**; Buckets are private-only without versioning or object lock.

## Red flags (checked 30 October 2026)

A draft that names one of these needs a stated reason:

- **Archived or frozen:** MinIO open source (April 2026), ingress-nginx (March 2026), Kong OSS (frozen at 3.9.1), Hugging Face TGI (March 2026), Grafana OnCall OSS (2026).
- **Supply-chain incidents:** LiteLLM 1.82.7 / 1.82.8 on PyPI and Trivy 0.69.4–0.69.6 / `trivy-action` tags (March 2026) — pin by version and hash or SHA, give tools no extra secrets.
- **Licence shifts:** CockroachDB (no open Core), ScyllaDB (open version closed), Redis 8 (AGPL/RSAL/SSPL), MongoDB (SSPL), Elasticsearch, HashiCorp BSL (Vault, Terraform, Consul, Nomad), Linkerd stable builds (paid over 50 employees), Camunda 8, n8n (Sustainable Use), EMQX (BSL), Redpanda (BSL).
- **Unsafe defaults:** Ollama listens without auth; Coolify panel exposed without SSO and updates; static TURN credentials; Redis/Valkey locks used where double execution breaks data.
- **Single-maintainer risk:** check who maintains and funds a tool before betting on it (see External Secrets Operator, pgBackRest).

## Reference files

| File | Covers |
|---|---|
| `references/architecture.md` | `04-architecture` condensed: shape, repo layout, service autonomy and communication, auth model, failure isolation, shared packages, horizontal scaling, modular monolith, no fanaticism, system anti-patterns, design checklist |
| `references/layers/databases.md` | REL, distributed SQL, document, KV, wide-column, graph, multi-model, OLAP, time series, search, vector, streams; clouds; task table |
| `references/layers/brokers.md` | queues, Kafka-world logs, MQTT, stream processing, CDC; clouds; task table |
| `references/layers/background.md` | schedulers, job queues, durable execution, DAG orchestrators, low-code; clouds; task table |
| `references/layers/files.md` | self-hosted S3, table formats, catalogs, lake query engines, block/file storage; clouds; task table |
| `references/layers/ingress.md` | proxies, k8s ingress, API gateways, service mesh, CDN, tunnels; clouds; task table |
| `references/layers/access.md` | IdP/SSO, authorization engines, secrets and PKI, team passwords, ZTNA, perimeter and runtime defence; clouds; task table |
| `references/layers/coordination.md` | discovery, distributed config, locks and leader election, feature flags, distributed runtimes; clouds; task table |
| `references/layers/observability.md` | metrics, logs, traces, all-in-one stacks, collectors, errors and uptime, dashboards and on-call; clouds; task table |
| `references/layers/realtime.md` | WebSocket/pub-sub, sync and local-first, WebRTC and video, voice AI, email and notifications; clouds; task table |
| `references/layers/ai.md` | inference, LLM gateways, agent infrastructure, LLM observability and evals, MLOps; clouds; task table |
| `references/layers/platform.md` | orchestration, self-hosted PaaS, registries, CI/CD and GitOps, IaC, backups; clouds; task table |
