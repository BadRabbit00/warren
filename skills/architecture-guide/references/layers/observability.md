# Layer: observability

Source: Alexey's «Наблюдаемость системы» (checked 30 October 2026). Metrics, logs, traces, profiles, application errors and uptime, dashboards and alerts, all-in-one stacks and telemetry collectors. Observability cost usually grows faster than the app's own cost — watch log volume and cardinality from day one.

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **Four signals.** Metrics — numbers over time, cheap, for alerts. Logs — text events, expensive at volume. Traces — the path of one request through services. Profiles — where CPU and memory go. Linked by `trace_id`.
- **Cardinality.** Each unique label combination is a separate series. A `user_id` label or a URL with IDs turns a thousand series into millions and kills Prometheus. **High-cardinality data goes into logs and traces, not metrics.**
- **OpenTelemetry.** One standard for all signals: SDK in code, OTLP protocol, Collector. Instrument once; the backend (Grafana, ClickStack, cloud, SaaS) changes by config. Traces, metrics, logs are stable; profiles are alpha.

## Rule 0

Instrument through **OpenTelemetry, not a vendor SDK**. Start small: **RED metrics** (rate, errors, duration) per service, structured JSON logs with `trace_id`, an error tracker, and an external uptime check. **An alert is about a symptom the user sees, not "CPU 80%".**

## Classes and technologies

### METRICS
Time series: name + labels + values. Model and query standard: Prometheus and PromQL; almost every metric store is compatible or accepts remote write.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Prometheus** | open (Apache 2.0) · base | pull from `/metrics`, local TSDB (usually weeks); PromQL, recording and alerting rules; v3: new UI, native OTLP intake, UTF-8 names, Remote Write 2.0; discovery from k8s, Consul, clouds; agent mode only collects and forwards | infrastructure and service metrics; alerts via Alertmanager; the base for everything else | long retention and a global view across clusters without an add-on; high cardinality |
| **VictoriaMetrics** | open (Apache 2.0) · pop | accepts remote write, Prometheus, Graphite, InfluxDB, OTLP; MetricsQL (PromQL superset); strong compression, months to years; several times less RAM and disk; vmagent, vmalert; single-node covers most companies, cluster exists | cheap long-term metrics; replacing Prometheus when it runs out of memory | needing the official Grafana Labs ecosystem |
| **Grafana Mimir** | open (AGPLv3) · pop | Cortex successor; microservices, data in S3 for years; PromQL; a billion series, multi-tenancy; harder to run than VictoriaMetrics | a metrics platform for many teams; the LGTM stack | small companies (overkill) |
| **Thanos** | open (Apache 2.0, CNCF) · base | sidecar to Prometheus + store in S3, downsampling; PromQL across many Prometheus servers | several existing Prometheus servers needing one query view | starting from scratch (VictoriaMetrics or Mimir are simpler) |

### LOGS
The most expensive signal by volume. Full-text index (fast search, expensive) vs labels-only index + compressed chunks (cheap, search by scan); columnar stores (ClickHouse) are a third path.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Grafana Loki** | open (AGPLv3) · pop | labels + compressed chunks in S3; LogQL; same labels as Prometheus; bloom filters speed content search; monolithic or microservices; dislikes high-cardinality labels | k8s and service logs in the Grafana stack; cheap storage of large volumes | full-text search over all fields (slower than indexing systems) |
| **VictoriaLogs** | open (Apache 2.0) · grow | one binary, schemaless columnar fields; LogsQL; strong compression; high-cardinality fields are fine; accepts Vector, Fluent Bit, OTel, Loki and Elasticsearch API; VictoriaTraces from the same authors | logs without heavy infrastructure; replacing Loki or ELK for small and medium systems | needing the huge ELK plugin ecosystem |
| **OpenSearch / Elasticsearch** | open (Apache 2.0, OpenSearch) · base | inverted index over all fields; DSL, PPL/ES\|QL, Dashboards/Kibana; hot/warm nodes, S3 snapshots; fast any-field search and aggregations, expensive in RAM and disk; base of many SIEMs (Wazuh); see `databases.md` | SIEM and security logs; complex log search | terabytes per day on a small budget |
| **ClickHouse for logs** | open (Apache 2.0) · pop | log tables with the OTel schema; SQL; 10–20× more compact than an index, instant aggregations; TTL, S3; base of ClickStack, SigNoz and many SaaS; logs and business data in one SQL | large log volumes cheaply; SQL analytics over logs | no ClickHouse operations experience |

### TRACES
A request split into spans across services. Shows exactly where it is slow or fails. **Sampling** matters: keep errors and slow traces, not everything.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Jaeger** | open (Apache 2.0, CNCF graduated) · base | v2 is essentially an OTel Collector distribution with the Jaeger UI; OTLP; Cassandra, Elasticsearch/OpenSearch, ClickHouse, Badger | tracing without the Grafana stack; finding and analysing single traces | metrics and logs in the same UI |
| **Grafana Tempo** | open (AGPLv3) · pop | traces as Parquet in S3 without indexes — keeps 100% cheaply; OTLP, Jaeger, Zipkin; TraceQL; log ↔ trace ↔ metric jumps with Loki and Mimir | the LGTM stack; keeping all traces without sampling | outside Grafana (less point) |
| **Zipkin** | open (Apache 2.0) · base | Zipkin format, B3 headers; Cassandra, Elasticsearch, MySQL; lives in old Java/Spring systems | maintaining existing systems | new projects (→ OTel + Jaeger or Tempo) |

### ALL-IN-ONE stacks
Metrics, logs and traces in one product and UI; the new wave is built on OpenTelemetry and ClickHouse. Plus: correlation out of the box. Minus: tied to one product.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Grafana LGTM** | open (AGPLv3, Alloy Apache 2.0) · base | Loki + Grafana + Tempo + Mimir, plus Pyroscope and Alloy; S3 for everything; many components but monolithic modes exist; AGPL is fine internally; Grafana Cloud free tier; Grafana 13 in 2026 | a company-wide observability platform; one standard stack | small projects (too many components) |
| **ClickStack (HyperDX)** | open (MIT, HyperDX) · grow | ClickHouse bought HyperDX in 2025: OTel Collector + ClickHouse + UI; logs, traces, metrics, session replay; Lucene-style search + SQL; built into ClickHouse Cloud; high cardinality and big volumes cheaply | lots of logs and traces on a limited budget; ClickHouse already present | needing a long product track record |
| **SigNoz** | open (MIT core + Enterprise) · pop | OTel-native from day one, on ClickHouse; ready APM pages (latency, errors, external calls), alerts, dashboards; Docker Compose or Helm | Datadog-like APM self-hosted | Grafana-level dashboard flexibility |
| **OpenObserve** | open (AGPLv3) · grow | Rust; logs, metrics, traces, RUM in Parquet on S3; own UI, SQL and PromQL; one binary or cluster; claims ~140× cheaper storage than Elasticsearch | replacing ELK with minimal operations | conservative production |
| **Datadog / Grafana Cloud / Honeycomb** | prop (SaaS) · pop | everything plus RUM, synthetics, security; data at the vendor. **The bill grows with log volume, hosts and custom metrics** — a frequent unpleasant surprise; Honeycomb strong on high-cardinality events | no people to run your own stack | data that must not leave the country; large volumes on a small budget |

### COLLECT — collectors and telemetry pipelines
Agents and gateways that collect, enrich, filter and ship telemetry. A good pipeline saves money: **sample traces and drop junk logs before storage**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenTelemetry Collector** | open (Apache 2.0) · base | receivers (OTLP, Prometheus, Jaeger, files, k8s…), processors (batch, filter, **tail sampling** keeps whole error and slow traces, k8s metadata), any exporters; custom distributions via OCB; the central point — apps send to it, it decides where | any new observability system; backend independence | — |
| **OBI (OpenTelemetry eBPF Instrumentation)** | open (Apache 2.0) · grow | from Grafana Beyla donated to OTel; eBPF captures HTTP, gRPC, SQL at the kernel level, any language without SDK; emits OTel spans and metrics; 1.0 targeted for 2026, plus MQTT, AMQP, NATS, Redis pub/sub, .NET | RED metrics per service without code changes; legacy and third-party binaries | business attributes in spans (need an SDK) |
| **Grafana Alloy** | open (Apache 2.0) · pop | OTel Collector distribution with a programmable component config; Prometheus metrics, Loki logs, OTel, profiles in one agent; debug UI; replaces Grafana Agent | the Grafana stack | no Grafana (→ plain OTel Collector) |
| **Fluent Bit / Vector** | open (Apache 2.0 / MPL 2.0) · base | files, journald, k8s, syslog → parsing, filters (Vector's VRL) → Loki, ClickHouse, Elastic, S3, Kafka, OTLP; Fluent Bit in C, CNCF, the k8s log standard, very light; Vector in Rust, more flexible transforms | logs from hosts and pods | traces (→ OTel Collector) |

### ERRORS — application errors and uptime
An error tracker groups exceptions with stack, release and user. Uptime monitoring checks the service from outside, as the user sees it. **Both from day one.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Sentry** | src (FSL → Apache 2.0 after 2 years) · base | errors, performance, session replay, profiles, cron monitors; SDKs for almost every platform — the de facto standard; self-hosted is heavy (Postgres, Kafka, ClickHouse, Redis…) and Sentry itself calls it for small volumes and trials | cloud Sentry for almost any project | self-hosted on a small server |
| **GlitchTip** | open (MIT) · pop | uses Sentry SDKs (change only the DSN); errors, basic performance, uptime; Postgres + one app, from 512 MB | a self-hosted error tracker with an open licence | session replay and deep performance |
| **Bugsink** | src (Polyform Shield — no competing service) · grow | one container + SQLite/Postgres/MySQL; Sentry SDKs; >1M events/day on a €5 VPS | very small infrastructure | an open licence (→ GlitchTip) |
| **Uptime Kuma** | open (MIT) · pop | one container; HTTP, TCP, DNS, ping, keyword, Docker, databases; notifications to Telegram, Slack and dozens more; status page. **Keep it outside the infrastructure it checks** | uptime monitoring of sites and services; a customer status page | checks from many world regions |
| **Gatus** | open (Apache 2.0) · pop | one binary, YAML config in git; HTTP, TCP, DNS, ICMP, content and certificate checks | checks in git and GitOps | a UI for non-technical people |

### ALERT — dashboards, alerts, on-call
A good alert is about a user symptom, has a **runbook**, and no noise. Bad alerts teach people to ignore them.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Grafana** | open (AGPLv3) · base | Prometheus, Loki, Tempo, ClickHouse, Postgres, clouds, hundreds of plugins; Grafana Alerting; provisioning, Terraform, dashboards as code (keep them in git or they sprawl); Grafana 13 in 2026 | almost any observability stack | — |
| **Perses** | open (Apache 2.0, CNCF sandbox) · grow | open dashboard standard as code: CUE and Go SDK, k8s CRDs; no alerts; used in Red Hat OpenShift | dashboards strictly as code in k8s | Grafana's plugin richness |
| **Alertmanager** | open (Apache 2.0, part of Prometheus) · base | grouping, inhibition (a dead node does not alert for every service on it), silences, routes; Telegram, Slack, email, webhooks; YAML | alerts from the Prometheus ecosystem | on-call schedules and escalations (a separate tool) |
| **Grafana OnCall OSS** | open (AGPLv3, **archived**) · base | maintenance mode since 2025, archived in 2026; development moved to cloud Grafana IRM. Self-hosted on-call needs another scheme: Alertmanager + ntfy or a Telegram bot, or SaaS (PagerDuty, incident.io) | old installs only | new projects |
| **Pyroscope / Parca** | open (AGPLv3 / Apache 2.0) · pop | continuous profiling: CPU and memory flame graphs in production over time (which function ate the CPU after a release); eBPF profiler and language SDKs; Pyroscope in the Grafana stack, Parca by Polar Signals; OTel Profiles alpha | CPU cost optimisation; finding memory leaks in production | small projects without performance problems |

## Clouds

Cloud tools are handy for **infrastructure** metrics. For applications with frequent migrations, keep your own stack or a SaaS and ship through the **OTel Collector** — on a move only the export address changes.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud (Monium family) | Monitoring | cloud service metrics, dashboards, alerts | infrastructure in Yandex |
| | Managed Service for Prometheus | PromQL, remote write; **no exemplars, native histograms or staleness markers** | app metrics, Grafana dashboards |
| | Cloud Logging | service and app logs, Fluent Bit and OTel integration | central logs |
| | Traces, alerts, SLO | tracing and SLOs on the same platform | APM without your own stack |
| | Audit Trails | action audit | security |
| DigitalOcean | Monitoring + alert policies | Droplet metrics, alerts | infrastructure |
| | Uptime | external availability checks | uptime |
| | App Platform log forwarding | logs to external systems | PaaS logs |
| | DOKS 1-Click Monitoring | kube-prometheus-stack | cluster metrics |
| Railway | Logs Explorer | build, deploy, runtime logs with filters | debugging |
| | Metrics | CPU, RAM, disk, network per service | resources |
| | Traces | request path from the edge through services | finding slow spots |
| | Monitors | thresholds → email, in-app, webhooks (Pro) | resource alerts |
| | Grafana / SigNoz / Uptime Kuma templates | own stack in the project | app metrics and long retention (otherwise ship to an external provider) |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | CloudWatch Metrics / Logs / Alarms; CloudWatch Application Signals (APM on OTel) / X-Ray; Amazon Managed Prometheus; Amazon Managed Grafana |
| Google Cloud | Cloud Monitoring / Logging (Log Analytics in SQL); Cloud Trace / Profiler; Managed Service for Prometheus (on Monarch) |
| Azure | Azure Monitor + Log Analytics (KQL); Application Insights (APM on the OTel distro); Managed Prometheus / Managed Grafana |
| Cloudflare | Workers Observability (logs and traces of Workers); Logpush (HTTP, WAF, Workers logs → S3, R2, ClickHouse, SaaS); Analytics Engine (own metrics with SQL) |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Service and infrastructure metrics | Prometheus | long retention and savings → VictoriaMetrics; platform for many teams → Mimir |
| Logs for a small or medium project | VictoriaLogs | already on the Grafana stack → Loki |
| Large log and trace volumes cheaply | ClickStack or SigNoz (ClickHouse) | — |
| SIEM and security logs | OpenSearch (Wazuh) | — |
| Traces | Tempo (Grafana stack) or Jaeger | — |
| One standard stack for the company | Grafana LGTM + Alloy | Datadog-like APM → SigNoz |
| Telemetry collection | OpenTelemetry Collector | host logs → Fluent Bit or Vector |
| Metrics without code changes | OBI (eBPF) | business attributes needed → OTel SDK |
| Error tracking | Sentry Cloud | self-hosted → GlitchTip |
| Uptime and status page | Uptime Kuma | checks as code → Gatus |
| Alerts | Alertmanager / Grafana Alerting | — |
| Self-hosted on-call | Alertmanager + ntfy or Telegram | schedules and phone calls → PagerDuty, incident.io, Grafana IRM |
| CPU optimisation in production | Pyroscope | — |
| No people to operate a stack | Grafana Cloud (free tier) or Datadog | data must not leave → own stack in an in-country cloud |
