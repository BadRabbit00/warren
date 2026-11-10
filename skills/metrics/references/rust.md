# Metrics templates: Rust (OpenTelemetry SDK, OTLP)

Copy-ready templates for one service. The module is per service (`src/metrics.rs`), copied with the service. Rules: `../SKILL.md`. A new dependency is reported to the orchestrator, not added.

Source marks:
- (R) stated in the research `docs/temp/observability/research-wf_35c2e079-c6c.json` or the follow-up `research-wf_340d5dfb-77e.json`.
- (U) NOT from the research: verify against the installed version before relying on it.

Crates (R, latest on 2026-11-10, nothing pinned): `opentelemetry_sdk` 0.33.1, `opentelemetry-otlp` 0.33.1. Source of the OTLP setup: `docs/temp/observability/research-wf_340d5dfb-77e.json` (confidence medium).

Export decision (R): the `opentelemetry-prometheus` README says "For new projects, consider using the opentelemetry-otlp crate instead", because Prometheus supports native OTLP ingestion. So Rust services push OTLP (to a Collector, or to Prometheus with OTLP ingestion enabled). No `/metrics` pull endpoint is generated. Whether the Prometheus crate is formally deprecated is unconfirmed.

## Contents

1. [Config fields](#1-config-fields)
2. [Connector module](#2-connector-module-srcmetricsrs)
3. [Request duration layer](#3-request-duration-layer)
4. [Domain method in use](#4-domain-method-in-use)
5. [Tests](#5-tests)

## 1. Config fields

Only the config module reads env (R-MT-CONFIG); nothing else calls `std::env::var`.

```rust
// src/config.rs (excerpt)
pub struct Config {
    pub service_name: String,
    pub metrics_otlp_endpoint: String,
}
```

## 2. Connector module `src/metrics.rs`

(R, follow-up research wf_340d5dfb-77e, opentelemetry-otlp 0.33.1 docs and the `metrics-basic` example; the OTLP wiring below is assembled from verified pieces, since the official example uses the stdout exporter): `MetricExporter::builder().with_http()` / `.with_tonic()`, `with_protocol`, `with_endpoint`, `with_timeout`, `build`; `SdkMeterProvider::builder().with_periodic_exporter(exporter)` (also `with_reader`), `with_resource(Resource::builder().with_service_name(..).build())`; `global::set_meter_provider`; `meter.u64_counter(..).build()`; `meter.f64_histogram(..).with_boundaries(vec![..]).build()`; `shutdown()`. Still (U): `with_unit`, `with_description`, `i64_up_down_counter`, the exact import paths of `Counter`/`Histogram`/`UpDownCounter`. Compile against 0.33.1 before reporting done.

```rust
use opentelemetry::{global, metrics::{Counter, Histogram, Meter, UpDownCounter}, KeyValue}; // (R) global, KeyValue; (U) metrics paths
use opentelemetry_otlp::{Protocol, WithExportConfig}; // (R) Protocol; WithExportConfig gives with_endpoint (U: trait name)
use opentelemetry_sdk::{metrics::SdkMeterProvider, Resource}; // (R)

use crate::config::Config;

const HTTP_BUCKETS: [f64; 14] =
    [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]; // (R) semconv

/// Closed set: the only values allowed as the `status` attribute.
#[derive(Clone, Copy)]
pub enum OrderStatus {
    New,
    Paid,
    Cancelled,
}

impl OrderStatus {
    fn as_str(self) -> &'static str {
        match self {
            Self::New => "new",
            Self::Paid => "paid",
            Self::Cancelled => "cancelled",
        }
    }
}

/// The only place that knows OpenTelemetry. Business code calls the methods.
#[derive(Clone)]
pub struct Metrics {
    request_duration: Histogram<f64>,
    active_requests: UpDownCounter<i64>,
    orders_created: Counter<u64>,
}

impl Metrics {
    fn new(meter: &Meter) -> Self {
        Self {
            request_duration: meter
                .f64_histogram("http.server.request.duration")
                .with_unit("s")
                .with_description("Duration of HTTP server requests.")
                .with_boundaries(HTTP_BUCKETS.to_vec()) // (R) explicit bucket boundaries on the builder
                .build(),
            active_requests: meter
                .i64_up_down_counter("http.server.active_requests")
                .with_unit("{request}")
                .build(),
            orders_created: meter
                .u64_counter("orders.created")
                .with_unit("{order}")
                .build(),
        }
    }

    /// `route` is a template ("/orders/{order_id}"), never the raw path.
    pub fn observe_request(&self, route: &str, method: &str, status: u16, seconds: f64) {
        self.request_duration.record(
            seconds,
            &[
                KeyValue::new("http.route", route.to_owned()),
                KeyValue::new("http.request.method", method.to_owned()),
                KeyValue::new("http.response.status_code", i64::from(status)),
            ],
        );
    }

    pub fn request_started(&self) { self.active_requests.add(1, &[]); }
    pub fn request_finished(&self) { self.active_requests.add(-1, &[]); }

    pub fn order_created(&self, status: OrderStatus) {
        self.orders_created.add(1, &[KeyValue::new("status", status.as_str())]);
    }
}

/// Call once at startup. Returns the provider (call `shutdown` on exit) and the connector.
pub fn init(cfg: &Config) -> Result<(SdkMeterProvider, Metrics), Box<dyn std::error::Error>> {
    // (R) HTTP/protobuf; pass the full path, the docs example does (whether the exporter appends /v1/metrics itself is (U)).
    let exporter = opentelemetry_otlp::MetricExporter::builder()
        .with_http()
        .with_protocol(Protocol::HttpBinary)
        .with_endpoint(cfg.metrics_otlp_endpoint.clone()) // e.g. http://collector:4318/v1/metrics
        .build()?;
    // gRPC instead (R): .with_tonic().with_endpoint("http://my-collector:4317").with_timeout(Duration::from_secs(5)).build()?

    let provider = SdkMeterProvider::builder()
        .with_periodic_exporter(exporter) // (R) PeriodicReader, default interval 60 s
        .with_resource(Resource::builder().with_service_name(cfg.service_name.clone()).build()) // (R)
        .build();
    global::set_meter_provider(provider.clone()); // (R)
    let metrics = Metrics::new(&global::meter("orders")); // (R) global::meter
    Ok((provider, metrics))
}
```

Shutdown on exit (R): `provider.shutdown()?;` flushes at once instead of waiting for the interval; its error type is `opentelemetry_sdk::error::ShutdownError` (`InternalFailure`, `AlreadyShutdown`, `Timeout`).

Cargo features (R, 0.33.1):

```toml
opentelemetry = { version = "0.33", features = ["metrics"] }          # (U) feature set of this crate not checked
opentelemetry_sdk = { version = "0.33", features = ["metrics"] }      # (U) rt-tokio and similar not checked
# HTTP: `http-proto` and `reqwest-blocking-client` are default features of opentelemetry-otlp
opentelemetry-otlp = { version = "0.33", features = ["metrics"] }
# gRPC instead of HTTP:
# opentelemetry-otlp = { version = "0.33", default-features = false, features = ["metrics", "grpc-tonic"] }
```

(R) `metrics` in `opentelemetry-otlp` enables `opentelemetry/metrics` and `opentelemetry_sdk/metrics`. (U) Whether the periodic reader needs a tokio runtime with `reqwest-blocking-client`; check before wiring into an async main. Versions are the latest on 2026-11-10; no `Cargo.lock` was read, so a project pin may differ.

## 3. Request duration layer

(U) With axum / tower the idiom is a middleware function around `next.run(req)`; the route template comes from the matched-path extension. Shape:

```rust
// inside the middleware, with `metrics: Metrics` from state
metrics.request_started();
let start = std::time::Instant::now();
let response = next.run(req).await;
metrics.request_finished();
metrics.observe_request(route_template, method, response.status().as_u16(), start.elapsed().as_secs_f64());
response
```

`route_template` is the template or `"unmatched"`, never `req.uri().path()`.

## 4. Domain method in use

```rust
// src/service/order_service.rs
pub async fn create(&self, input: OrderCreate) -> Result<Order, OrderError> {
    let order = self.repo.add(input).await?;
    self.metrics.order_created(OrderStatus::New);
    Ok(order)
}
```

The service holds a `Metrics` (cheap clone) passed at construction, and imports `crate::metrics` only, never `opentelemetry`.

## 5. Tests

The research names no in-memory reader for Rust. (U) `opentelemetry_sdk` may provide an in-memory exporter under a testing feature; verify against 0.33.1 on docs.rs. Otherwise test the service with a `Metrics` built on a provider with no reader (calls are no-ops). Tests are never edited by `metrics-writer`.
