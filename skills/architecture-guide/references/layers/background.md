# Layer: background work and orchestration

Source: Alexey's «Фоновая работа и оркестрация» (checked 30 October 2026). Everything that runs outside an HTTP request: job queues, schedulers, durable workflows for long processes and AI agents, data pipeline orchestrators, low-code automation.

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **Job queue** — "do this soon". One task, retries on error. A complex process has to keep its state itself.
- **Durable workflow** — ordinary code made of steps; the engine records each step's result. After a crash the code continues from the same place, even a week later.
- **Data orchestrator (DAG)** — a scheduled task graph: "extract → clean → compute → load". Dependencies, reruns and run history are the point.

## Rule 0

First check whether cron plus a Postgres queue is enough. A durable engine is needed when the process is **long, multi-step, and a failure in the middle costs money**: payment, onboarding, an agent with dozens of LLM calls. Airflow is needed when there are **many data pipelines with dependencies**.

## Classes and technologies

### CRON — schedulers
Run something at 03:00 or every 5 minutes. The most underrated class: half of "we need Airflow" is closed by a plain timer. Remember **idempotency** and protection against double runs.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **systemd timers** | open (LGPL 2.1) · base | timer unit starts a service unit; OnCalendar, OnBootSec, random delay; `Persistent=true` catches up missed runs; logs in journald, resource limits, sandbox, own user; declared as `.timer` and `.service` units kept in git | backups, rotation, reports on one server; isolated jobs (DynamicUser, ProtectSystem) | jobs across several machines with double-run protection; dependencies between jobs |
| **Kubernetes CronJob** | open (Apache 2.0) · base | CronJob → Job → Pod; cron expression with time zone; `concurrencyPolicy: Forbid`; limits, backoffLimit, deadlines; logs live as long as pods — collect them | periodic jobs when the app is already in k8s | runs every few seconds; job chains with dependencies |
| **pg_cron** | open (PostgreSQL) · pop | schedule in a table, jobs are SQL; cron expressions and second intervals; history in `cron.job_run_details`; in most managed Postgres | database upkeep without an external scheduler (purge old data, refresh materialised views, archive); Supabase and managed Postgres | calling external APIs and long jobs |

### JOBS — job queues
Libraries in your app: put a job in a store (Redis/Valkey, Postgres, broker), workers execute it. Retries with backoff, priorities, delayed runs, rate limiting.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Celery** | open (BSD-3) · base | Python; broker RabbitMQ or Redis/Valkey, results in Redis or DB; beat schedules, canvas chains/groups, limits; huge ecosystem (Django, FastAPI). Awkward defaults and unclear crash behaviour: **enable `acks_late` and make tasks idempotent**, or jobs vanish on worker restart | Python backends with background jobs; Django projects | multi-day processes with state; transparent run history (weak in Celery) |
| **BullMQ** | open (MIT) · pop | TypeScript (Python and Elixir ports); Redis / Valkey / Dragonfly; Lua scripts for atomicity; at-least-once, retries, rate limit; flows (parent–child), priorities, repeatable jobs; Pro adds groups and batches; Bull Board, Taskforce | Node/Nest backends; emails, notifications, media processing | long processes waiting for humans; no Valkey in the stack |
| **River** | open (MPL 2.0) · grow | Go on Postgres; **the job is created in the same transaction as the data** — rollback removes it; unique and periodic jobs, web UI; LISTEN/NOTIFY wakes workers | Go services on Postgres | tens of thousands of jobs/s sustained |
| **pg-boss / Graphile Worker** | open (MIT) · pop | TypeScript on Postgres, transactional, SKIP LOCKED; cron, retries, delayed jobs. pg-boss is general with pub/sub; Graphile Worker is very fast and can enqueue from SQL triggers | Node projects with Postgres and no Redis | huge queue loads |
| **Sidekiq** | open (LGPL 3 + Pro/Enterprise) · base | Ruby; Redis / Valkey / Dragonfly; reliable delivery in Pro, cron in Enterprise; Rails 8 ships Solid Queue (DB queue) as default, Sidekiq still the usual pick for load | Rails apps | outside Ruby |
| **Oban** | open (Apache 2.0 + Pro) · pop | Elixir on Postgres/SQLite, transactional; cron, uniqueness, workflows in Pro — the reference for "queue in the database" | Elixir/Phoenix | outside Elixir |

### DURABLE — durable execution (workflow in code)
The engine journals each step's result; after a crash the code is **replayed** from the journal and continues. Main rule: **workflow code must be deterministic; all side effects go inside steps**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Temporal** | open (MIT) · base | from Uber Cadence; Workflow (deterministic) + Activities (side effects); Go, Java, TS, Python, .NET, Ruby, PHP; stores in Postgres, MySQL or Cassandra, search via Elasticsearch/OpenSearch; services frontend/history/matching/worker; signals and queries, timers for months, child workflows, code versioning, Saga compensations; full event history per run (great audit). Heavy self-hosted ops, determinism learning curve; Temporal Cloud exists | payments, orders, onboarding; AI agents with dozens of steps and human waits; microservice orchestration with Saga; processes lasting days and weeks | simple background jobs (overkill); a small team unwilling to run a cluster; huge numbers of 10 ms tasks |
| **Restate** | src (BSL 1.1 server) · grow | one Rust binary; services, virtual objects with state, workflows; TS, Java/Kotlin, Python, Go, Rust; acts as a proxy — calls go through it and every step is journaled; own journal and K/V state, no separate DB; fits serverless (Lambda, Workers); UI and OpenTelemetry traces | durable logic without a heavy cluster; serverless functions needing state; reliable calls between services | an open server licence; conservative production needing years of maturity |
| **DBOS** | open (MIT) · grow | a library: `@workflow` / `@step` decorators; Python, TS, Go, Java; step state written to **your Postgres** next to the data; built-in queues and cron — Rule 0 for durable execution | step reliability without installing Temporal; agents and pipelines in a Python app | hundreds of services in many languages needing central control |
| **Inngest** | src (SSPL → Apache 2.0 after 3 years) · pop | `step.run`, `step.sleep`, `step.waitForEvent`; TS, Python, Go, Kotlin; Inngest calls your functions over HTTP, so they can live on Vercel, Railway, Workers; flow control: concurrency per key, throttling, debounce, batching; local dev server; self-hosted on SQLite or Postgres + Redis, single process for now | TS teams on serverless platforms; event-driven logic with per-customer limits; AI agents on Next.js | self-hosted HA; an open licence right now |
| **Trigger.dev** | open (Apache 2.0) · grow | TypeScript tasks with checkpoint/restore — hours-long without serverless timeouts, frozen while waiting; Postgres + Redis + object storage; realtime status streaming to the frontend; cloud or self-hosted (Docker, k8s) | video, report and AI generation with progress in the UI; Next.js projects | non-TypeScript; strict self-hosted ops requirements |
| **Hatchet** | open (MIT) · grow | tasks, DAGs, durable tasks; Python, TS, Go; Postgres only (no Redis, no broker); fair queueing between tenants, rate limits, clear dashboard — between Celery and Temporal | a Celery replacement with real visibility; multi-tenant queues with fair queueing | needing Temporal's maturity and community |
| **Camunda 8** | src (Camunda License 1.0; paid for production since 2024) · base | BPMN diagrams + DMN decision tables; Zeebe log + Elasticsearch/OpenSearch; human tasks (forms, approvals), timers, escalations; Java or any language via workers | approvals, document flow, banking processes; when the process diagram is a contract with the business | developers prefer code to diagrams; small budgets |

### DAG — pipeline orchestrators
Task graphs with dependencies, schedules and history — data and ML: exports, ETL, retraining. New approach: **asset-based** — describe the data that must exist; the orchestrator decides what to recompute.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Apache Airflow** | open (Apache 2.0) · base | Python DAGs of operators; schedules, events (assets), manual runs; metadata in Postgres/MySQL; Celery, Kubernetes or Edge executor. Airflow 3: React UI, DAG versioning, Task SDK separating task code from the core, asset events; 3.1 adds Human-in-the-Loop forms; thousands of providers | many data pipelines with dependencies; a data engineering team; integrations with everything | application business logic and request handling; jobs every few seconds; a small project with a couple of scripts |
| **Dagster** | open (Apache 2.0) · pop | software-defined assets, partitions; schedules, sensors, declarative automation; Postgres metadata; graph of tables/models with freshness and lineage; strong dbt integration; easy local tests; Docker, k8s, Dagster+ | analytics platforms and dbt; ML pipelines with visible lineage | simple cron jobs; non-Python teams |
| **Prefect** | open (Apache 2.0) · pop | `@flow` / `@task` decorators give retries, cache, logs, UI; Postgres or SQLite; work pools: processes, Docker, k8s, serverless | Python scripts that grew up; ML jobs and scrapers | huge enterprise data platforms (Airflow's ecosystem is wider) |
| **Kestra** | open (Apache 2.0) · grow | YAML flows of plugin tasks, editor in the UI; schedules, webhooks, queue events; any language via scripts and containers; Postgres/MySQL/H2, Kafka in Enterprise; fits GitOps | teams where not everyone writes Python; IaC-style infra automation | complex logic (easier in code than YAML) |
| **Argo Workflows** | open (Apache 2.0, CNCF) · base | Workflow CRD of steps or a DAG, each step a container; CronWorkflow, Argo Events; etcd, archive in Postgres; base of Kubeflow Pipelines | ML training and heavy batches in k8s | no Kubernetes; small frequent jobs (pod start is expensive) |

### LOWCODE — low-code automation
Visual builders: "webhook → LLM → Google Sheets → Telegram". Fast for integrations and prototypes; **dangerous when critical business logic moves there without tests and review**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **n8n** | src (Sustainable Use License) · pop | nodes and links, JS/Python code inside; hundreds of nodes + AI agent / LangChain nodes; SQLite/Postgres, queue mode on Redis with workers. Allowed: internal company use and consulting on the client's server. Not allowed without a separate contract: selling access, hosting for clients, embedding in your product. SSO, environments need an enterprise key | internal automations and business AI agents; quick integration prototypes | a client SaaS on n8n without a commercial licence; critical logic without tests and versioning |
| **Windmill** | open (AGPLv3 + Enterprise) · grow | scripts (Python, TS, Go, Bash, SQL) → flows and apps; each script gets a UI form and API automatically; Postgres, Rust workers; Git sync — a hybrid of Airflow, n8n and Retool | internal tools and admin scripts with a UI; developers cramped in n8n | non-technical users |
| **Activepieces** | open (MIT Community) · grow | flows of "pieces" written in TS, usable as MCP tools; hundreds of connectors; Postgres + Redis | a Zapier-like service you may embed in your product | complex logic with branches and code |
| **Node-RED** | open (Apache 2.0, OpenJS) · base | Node.js nodes; MQTT, Modbus, serial, HTTP, thousands of packages; `flows.json`; one machine, runs on Raspberry Pi and gateways | IoT, telemetry, edge automation | business processes needing audit and fault tolerance |

## Clouds

Cloud serverless orchestrators (Step Functions, Workflows, Durable Functions) are convenient, but the process description is their own and must be rewritten on a move. Code on Temporal, Restate or Celery moves with the app.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Cloud Functions + timers/triggers | functions on schedule or event (queues, storage, logs) | cron and queue handlers without servers |
| | Serverless Containers | a container on request or trigger | jobs cramped in functions |
| | Workflows (Serverless Integrations) | step processes in YaWL, UI builder | chains of cloud service calls |
| | Managed Service for Apache Airflow | managed Airflow | data pipelines |
| | Message Queue + trigger | SQS-compatible queue → function | background jobs |
| DigitalOcean | App Platform workers and jobs | background processes and one-off jobs next to the app | Celery, BullMQ workers |
| | Functions (scheduled triggers) | serverless functions on cron | light periodic jobs |
| | Droplet / DOKS | Temporal, Airflow, n8n yourself | everything else |
| Railway | Cron Jobs | any service can have a cron schedule: starts, works, stops | periodic jobs |
| | worker services | permanent processes next to the API | Celery, BullMQ |
| | templates: Temporal, Hatchet, Inngest, Trigger.dev, n8n, Windmill, Airflow | engines in your project; backups and upgrades on you | MVP, small loads |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Step Functions (ASL JSON, Standard up to a year, Express); EventBridge Scheduler (millions of schedules and one-off runs); Lambda + SQS; MWAA (managed Airflow); AWS Batch / ECS tasks (heavy container batches, ML) |
| Google Cloud | Cloud Tasks (HTTP job queue with retries and rate limits — for Cloud Run); Cloud Scheduler; Workflows (YAML); Cloud Composer (managed Airflow, incl. 3); Cloud Run jobs |
| Azure | Durable Functions / Durable Task Scheduler (durable execution in C#, JS, Python, Java); Logic Apps (low-code enterprise); Data Factory (ETL); Container Apps jobs |
| Cloudflare | Workflows (GA: `step.do` with retries, sleep, waiting for events such as human approval, state up to 30 days on paid plans, Python support); Cron Triggers; Queues |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Periodic job on one server | systemd timer | several machines → k8s CronJob or cron in the queue engine |
| Scheduled database upkeep | pg_cron | — |
| Background jobs in a backend | Postgres queue (River, pg-boss, Graphile, Oban) | Python → Celery; Node with Valkey → BullMQ |
| Jobs for many customers with fair queueing | Hatchet | — |
| Multi-step process whose failure costs money | DBOS (if Postgres is enough) | many services and languages → Temporal |
| AI agent with dozens of steps and human waits | Temporal / Restate | on Cloudflare → Workflows; TS on serverless → Inngest or Trigger.dev |
| Long AI generations with progress in the UI | Trigger.dev | — |
| Approvals with BPMN diagrams for the business | Camunda | simple approvals → durable engine + a form |
| Data pipelines with dependencies | Airflow | platform around data and dbt → Dagster; YAML and GitOps → Kestra |
| Outgrown Python scripts | Prefect | — |
| ML training in Kubernetes | Argo Workflows | — |
| Internal automations and integrations | n8n | embedding in a product → Activepieces; for developers → Windmill |
| IoT glue at the edge | Node-RED | — |
