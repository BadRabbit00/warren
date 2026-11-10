---
name: metrics
description: Use when adding or reviewing metrics, /health and /ready in a Python, Go or Rust service - the one-connector-module pattern over OpenTelemetry metrics, instrument choice, semconv names and units, histogram buckets via Views, cardinality, Prometheus pull and OTLP push export, liveness and readiness endpoints.
---

# Metrics

Rules for metrics in service code. Rule ids `R-MT-*`. Per-language templates live in `references/`. Backends are Python, Go and Rust only; browser frontends have no metrics here.

## When to use

- `metrics-writer` adds metrics, `/health` and `/ready` to the code of tasks in plan status `metrics` (on demand, not a `/br-wave` default step).
- Reviewers check a diff against these rules.

## Contents

1. [The connector module](#the-connector-module)
2. [Instrument choice](#instrument-choice)
3. [Names, units, buckets](#names-units-buckets)
4. [Cardinality](#cardinality)
5. [Export](#export)
6. [Health and readiness](#health-and-readiness)
7. [Rules](#rules)
8. [Reviewer checklist](#reviewer-checklist)
9. [References](#references)

Source marks: (R) stated in the research `docs/temp/observability/research-wf_35c2e079-c6c.json` or the follow-up `research-wf_340d5dfb-77e.json`; (U) not from the research, verify against the installed version.

## The connector module

One module per service, copied with the service like the logging module (not a shared library):

| Language | Module |
|---|---|
| Python | `app/core/metrics.py` |
| Go | `internal/metrics/metrics.go` |
| Rust | `src/metrics.rs` |

It is `core`, so every layer may import it (`rules/layers.md`, R-LAYER-DIRECTION). It holds:

- the provider and exporter setup, built from the config module;
- every instrument, defined once: name, type, unit, description, allowed attributes;
- one typed object with domain methods: `metrics.order_created(status=...)`, `metrics.observe_request(route=..., method=..., status=..., seconds=...)`.

Business code imports only that object. It never imports the OpenTelemetry API or SDK. Adding a metric means adding an instrument and a method to this one file.

If the module is missing, `metrics-writer` creates it from `references/` once per service, then adds methods. Settings go to the config module and `.env.example` in the same change.

## Instrument choice

| Question | Instrument |
|---|---|
| Counts events, only grows (orders created, errors) | Counter (non-negative) |
| Goes up and down, you control both sides (in-flight requests, queue items) | UpDownCounter |
| Distribution of durations or sizes | Histogram |
| Current value you read on demand, not additive (pool size, cache items) | observable Gauge with a callback |

(R) spec: Counter is non-negative, UpDownCounter increments and decrements, Gauge is non-additive, asynchronous variants report on observation.

## Names, units, buckets

Use the semantic-convention names where they exist (R):

| Metric | Type | Unit | Stability |
|---|---|---|---|
| `http.server.request.duration` | Histogram | `s` | Stable |
| `http.client.request.duration` | Histogram | `s` | Stable |
| `http.server.active_requests` | UpDownCounter | `{request}` | Development |
| `db.client.operation.duration` | Histogram | `s` | Stable |
| `db.client.connection.count` | UpDownCounter | `{connection}` | Development |
| `db.client.connection.timeouts` | Counter | `{timeout}` | Development |
| `db.client.response.returned_rows` | Histogram | `{row}` | Development |

Custom business metrics: dotted lowercase name with a namespace of the service (`orders.created`), unit in UCUM style (`s`, `By`, `{order}`), never the unit inside the name.

Buckets (R): the SDK default histogram bounds `[0,5,10,25,...,10000]` suit milliseconds, not seconds. Set seconds buckets through a View (or advisory boundaries):

- HTTP: `[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]`
- DB operation: `[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10]`

A View can also set an attribute allow-list (`attribute_keys`) (R, spec).

## Cardinality

Every distinct attribute combination is a time series held in memory.

- Allowed attribute values are a small closed set: route template (`/orders/{order_id}`), method, status class or code, enum values.
- Forbidden: user id, request id, trace id, raw URL or path with ids, email, free text, exception messages.
- (R) The SDK spec default limit is 2000 combinations per instrument; beyond it the data is reported under the single attribute `otel.metric.overflow=true`. Overflow means a bug in attributes, not a reason to raise the limit. Go: `WithCardinalityLimit` (R). Default limits of the Python and Rust SDKs were not confirmed (U).
- The connector methods take typed or enum arguments, so a free-form string cannot reach an attribute.

## Export

| Mode | When | Python | Go | Rust |
|---|---|---|---|---|
| Prometheus pull | Prometheus scrapes the service | `PrometheusMetricReader` + `prometheus_client.start_http_server(port=9464)`, served at `/metrics` (R) | `otelprom.New()` + `promhttp.Handler()` or `HandlerFor` (R) | not recommended: the crate README says new projects should use `opentelemetry-otlp` (R) |
| OTLP push | Collector, or Prometheus with native OTLP ingestion | `PeriodicExportingMetricReader(OTLPMetricExporter(...))` (R) | `NewPeriodicReader` over `otlpmetrichttp.New` / `otlpmetricgrpc.New` (R, wf_340d5dfb-77e; pin v1.43.0 or newer, GO-2026-4985) | `SdkMeterProvider::builder().with_periodic_exporter(MetricExporter::builder().with_http()/with_tonic()...build()?)` (R, wf_340d5dfb-77e, confidence medium) |

Versions seen on 2026-11-10 (R), none pinned in the project yet: Python `opentelemetry-sdk` 1.45.2, `opentelemetry-exporter-otlp-proto-http` 1.45.2, `opentelemetry-exporter-prometheus` 0.66b2 (beta, needs sdk `~=1.45.2`, `prometheus-client>=0.5,<1.0`); Go `go.opentelemetry.io/otel/sdk/metric` v1.47.0, `go.opentelemetry.io/otel/exporters/prometheus` v0.69.0; Rust `opentelemetry_sdk` 0.33.1, `opentelemetry-otlp` 0.33.1. New dependencies are reported to the orchestrator, not added by `metrics-writer`.

The exporter kind and endpoint come from the config module (R-MT-CONFIG).

## Health and readiness

Details and code: `references/health.md`.

| Endpoint | Meaning | Checks | Status |
|---|---|---|---|
| `/health` | liveness: process and event loop answer | none, no dependency calls | `200` |
| `/ready` | readiness: can serve traffic | DB, Redis, broker, each with a short timeout | `200` all ok, `503` any failed |

(R) A Kubernetes HTTP probe succeeds on any status from 200 to 399. A failing liveness probe restarts the container. Compose: `healthcheck.test`, `interval`, `timeout`, `retries`, `start_period`; `depends_on` with `condition: service_healthy` waits for it. (R, marked low confidence in the research) A failing readiness probe removes the Pod from Service endpoints without restart; the handler timeout must stay below the probe `timeoutSeconds`; 503 and per-check timeouts are common practice with no official source. The timeout numbers come from `docs/POLICY.md`; if absent, ask and wait.

Compose note: point `healthcheck` at `/health` for process liveness, at `/ready` when other services must wait for dependencies.

## Rules

### R-MT-ONE-CONNECTOR — every instrument is defined once, in the service's metrics module

Bad:
```python
# app/services/order_service.py
counter = meter.create_counter("orders_created")   # second place defining instruments
```
Why: names, units and attributes drift between files; there is no single list of what the service emits.

Good:
```python
# app/core/metrics.py defines the instrument and the method order_created(); the service calls it
metrics.order_created(status=order.status)
```

### R-MT-NO-RAW-API — business code never imports the OpenTelemetry API

Bad:
```go
import "go.opentelemetry.io/otel/metric"   // in internal/service/order_service.go
```
Why: the library leaks into every layer and every call site picks its own attributes.

Good:
```go
import "example.com/orders/internal/metrics"   // typed object only

m.OrderCreated(metrics.StatusPaid)
```

### R-MT-CARDINALITY — attributes come from a small closed set

Bad:
```python
metrics.observe_request(route=request.url.path, method="GET", status=200, seconds=dt)  # /orders/8f3a...
```
Why: each order id creates a new series; memory grows until the 2000 limit turns data into `otel.metric.overflow`.

Good:
```python
metrics.observe_request(route=request.scope["route"].path, method="GET", status=200, seconds=dt)  # /orders/{order_id}
```

### R-MT-UNITS — semconv name and unit, seconds for durations

Bad:
```rust
meter.f64_histogram("request_duration_ms").build();   // unit in the name, milliseconds
```
Why: dashboards and semconv tooling expect `http.server.request.duration` in `s`; a custom name and unit breaks both.

Good:
```rust
meter.f64_histogram("http.server.request.duration").with_unit("s").build();
```
Method names above are (U); name and unit are (R).

### R-MT-BUCKETS — histograms in seconds get a View with seconds buckets

Bad:
```go
// default bounds [0,5,10,25,...,10000] with values in seconds: every request lands in the first bucket
```
Why: the default bounds are for milliseconds; the histogram carries no information.

Good:
```go
sdkmetric.WithView(sdkmetric.NewView(
    sdkmetric.Instrument{Name: "http.server.request.duration"},
    sdkmetric.Stream{Aggregation: sdkmetric.AggregationExplicitBucketHistogram{Boundaries: httpBuckets}},
))
```
`NewView`, `WithView`, `AggregationExplicitBucketHistogram` are (R); the struct fields are (U).

### R-MT-INSTRUMENT — pick the instrument by meaning

Bad:
```python
queue_depth = meter.create_counter("jobs.queue.size")   # a value that goes down
```
Why: a Counter only grows; the series is wrong after the first decrement.

Good:
```python
queue_depth = meter.create_observable_gauge("jobs.queue.size", callbacks=[read_queue_size], unit="{job}")
```

### R-MT-CONFIG — exporter settings come from the config module

Bad:
```python
endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
```
Why: R-LAYER-CONFIG allows one place that reads env; a default hides a missing setting.

Good:
```python
OTLPMetricExporter(endpoint=settings.metrics_otlp_endpoint)
```

### R-MT-LIVENESS-NO-DEPS — /health calls no dependency

Bad:
```python
@router.get("/health")
async def health(db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))   # DB down restarts every replica
    return {"status": "ok"}
```
Why: a failing liveness probe restarts the container; a dependency outage must not restart healthy processes.

Good:
```python
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

### R-MT-READY-TIMEOUTS — /ready checks each dependency with a short timeout and answers 503 on failure

Bad:
```go
func ready(w http.ResponseWriter, r *http.Request) {
    _ = db.PingContext(r.Context())   // no timeout, result ignored, always 200
    w.WriteHeader(http.StatusOK)
}
```
Why: a hung dependency hangs the probe, and a failed one is reported as ready.

Good:
```go
func ready(w http.ResponseWriter, r *http.Request) {
    ctx, cancel := context.WithTimeout(r.Context(), readyTimeout) // from config, POLICY value
    defer cancel()
    if err := db.PingContext(ctx); err != nil {
        w.WriteHeader(http.StatusServiceUnavailable)
        return
    }
    w.WriteHeader(http.StatusOK)
}
```

### R-MT-NO-BEHAVIOUR-CHANGE — metrics never change behaviour

Metric calls do not alter return values, exceptions, ordering or transactions. Tests stay untouched; if a test breaks, undo the line that caused it.

Bad:
```python
metrics.rows_returned(count=len(list(rows_iter)))   # consumes the iterator
return rows_iter
```
Why: the metric call changes what the function returns.

Good:
```python
rows = list(rows_iter)
metrics.rows_returned(count=len(rows))
return rows
```
Only when the original code already materialised the value; otherwise record nothing about it.

## Reviewer checklist

- One metrics module per service; no instrument created elsewhere (R-MT-ONE-CONNECTOR).
- No OpenTelemetry or Prometheus imports outside the metrics module and the app wiring (R-MT-NO-RAW-API).
- Attributes are route templates, methods, status codes or enums; no ids, URLs, free text (R-MT-CARDINALITY).
- Names follow semconv where one exists; durations in `s`; units not in names (R-MT-UNITS).
- Seconds histograms have a View with the buckets above (R-MT-BUCKETS).
- Instrument type matches the meaning (R-MT-INSTRUMENT).
- No `os.getenv` / `os.Getenv` / `std::env::var` for metrics settings (R-MT-CONFIG).
- `/health` has no dependency call; `/ready` has per-check timeouts from POLICY and returns 503 on failure.
- `/health` and `/ready` are not counted as business traffic with unbounded labels.
- The diff changes no behaviour and no tests; new dependencies are reported, not added.

## References

- [references/python.md](references/python.md) - opentelemetry-sdk, Prometheus and OTLP
- [references/go.md](references/go.md) - otel sdk/metric, Prometheus exporter
- [references/rust.md](references/rust.md) - opentelemetry_sdk, OTLP
- [references/health.md](references/health.md) - /health, /ready, compose healthcheck
