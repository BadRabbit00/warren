# OpenTelemetry templates (Python, Go, Rust, Node)

Goal (D3): spans around function boundaries and every outgoing HTTP/DB call, and `trace_id` / `span_id` in every log line. Exporter endpoint and service name come from the config module (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`), never hard-coded. Each logger keeps the canonical keys `trace_id`, `span_id` (D13).

Facts used (research wf_6b111f8e-0e4, latest on the pages read 2026-11-10; no project lock files, so pin versions in the service):
- Python: `tracer.start_as_current_span` (context manager or decorator); packages `opentelemetry-instrumentation-{requests,httpx,urllib3,aiohttp-client,sqlalchemy,psycopg,psycopg2,asyncpg,redis,fastapi,django,flask,celery,...}`; `HTTPXClientInstrumentor().instrument()`; `opentelemetry-instrumentation-logging` 0.66b2 patches stdlib logging only (structlog not mentioned).
- Go: `otelhttp.NewHandler`, `otel.Tracer(name).Start(ctx, ...)` + `defer span.End()`; SDK 1.39.0, otelhttp 0.64.0 in the guide; contrib has no `database/sql` instrumentation.
- Rust: traces Beta; `tracing-opentelemetry` 0.34.0 (depends on `opentelemetry ^0.33.0`, unstable, pin exact versions) with `tracing_opentelemetry::layer().with_tracer(...)`; `opentelemetry-appender-tracing` 0.33.1 attaches TraceId/SpanId to OTel log records.
- Node: `@opentelemetry/sdk-node`, `@opentelemetry/api`, `@opentelemetry/auto-instrumentations-node`, `NodeSDK` + `getNodeAutoInstrumentations()`; `@opentelemetry/instrumentation-pino` (pino >=5.14 <11) injects `trace_id`, `span_id`, `trace_flags`, keys renamable with `logKeys`.

UNVERIFIED items are marked in the sections.

## Python

Dependencies (add to `pyproject.toml`, do not install on the host): `opentelemetry-sdk`, `opentelemetry-exporter-otlp` (both names UNVERIFIED, not in the research; check the Python getting-started page), `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-instrumentation-fastapi`.

```python
# core/tracing.py: init once at startup, values from the config module
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

def init_tracing(engine) -> None:
    # TracerProvider + OTLP exporter setup: UNVERIFIED API, see the Python getting-started guide.
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(engine=engine)  # engine= argument: UNVERIFIED

tracer = trace.get_tracer(__name__)

# Boundary span: context manager or decorator, both documented
@tracer.start_as_current_span("OrderService.cancel")
def cancel(order_id: int) -> None: ...
```

structlog processor (shape from structlog docs 26.1.0); put it in `core/logging.py` before the renderer:

```python
from opentelemetry import trace

def add_otel_ids(logger, method_name, event_dict):
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
```

`is_valid` and the `"016x"` span format follow the OTel API and are not in the research (UNVERIFIED; structlog docs show `"032x"` for trace_id). `opentelemetry-instrumentation-logging` is for stdlib `logging` only; do not rely on it with structlog.

## Go

```go
import (
	"context"
	"net/http"
	"time"

	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
)

var tracer = otel.Tracer("order-service")

func (s *OrderService) Cancel(ctx context.Context, id int64) error {
	ctx, span := tracer.Start(ctx, "OrderService.Cancel")
	defer span.End()
	_ = ctx // pass ctx to every call
	return nil
}

// Inbound: wrap the router. Outbound: wrap the transport.
handler := otelhttp.NewHandler(mux, "/")
client := &http.Client{Transport: otelhttp.NewTransport(http.DefaultTransport), Timeout: 10 * time.Second}
```

`otelhttp.NewTransport` is not in the research (only `NewHandler` is; UNVERIFIED); `setupOTelSDK(ctx)` from the getting-started guide installs the provider. SQL: contrib has no `database/sql` instrumentation, so wrap queries in manual spans (`tracer.Start(ctx, "db.query")`, `defer span.End()`) or evaluate a third-party `otelsql` (not verified as official). Timeout and retries from `docs/POLICY.md`; 10 s is a placeholder.

Log lines: `otelslog` is a bridge to the OTel Logs SDK and the page does not say it writes ids to stdout. Wrap your slog handler in `internal/logging` (custom wrapper, not in the docs, UNVERIFIED):

```go
import "go.opentelemetry.io/otel/trace"

type otelHandler struct{ slog.Handler }

func (h otelHandler) Handle(ctx context.Context, r slog.Record) error {
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() {
		r.AddAttrs(slog.String("trace_id", sc.TraceID().String()), slog.String("span_id", sc.SpanID().String()))
	}
	return h.Handler.Handle(ctx, r)
}
// WithAttrs / WithGroup must re-wrap: return otelHandler{h.Handler.WithAttrs(a)}.
```

Log with `logger.InfoContext(ctx, ...)` so the context reaches the handler.

## Rust

`#[instrument]` spans become OTel spans through the tracing layer; logs keep using `tracing` events.

```toml
tracing-opentelemetry = "=0.34.0"   # exact pins: the opentelemetry crate is unstable
opentelemetry = "=0.33"             # tracing-opentelemetry 0.34 depends on ^0.33.0
```

```rust
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, Registry};

// `tracer` comes from an opentelemetry_sdk TracerProvider with an OTLP exporter: UNVERIFIED API,
// follow the opentelemetry-rust getting-started page for the pinned version.
Registry::default()
    .with(tracing_opentelemetry::layer().with_tracer(tracer))
    .with(tracing_subscriber::fmt::layer().json()) // options as in rust.md
    .init();
```

- Spans: `#[instrument(skip_all)]` on boundaries (see `rust.md`). The research names no official HTTP/DB instrumentation crates for Rust: wrap `reqwest` / `sqlx` calls in `#[instrument]` functions and look in the OTel registry.
- Ids in stdout lines: `opentelemetry-appender-tracing` 0.33.1 attaches TraceId/SpanId but exports OTel log records; it is not a text formatter. Putting `trace_id` / `span_id` into the fmt JSON line is not covered by the research (UNVERIFIED). A possible approach: read the ids from the span's OTel context (`tracing_opentelemetry::OpenTelemetrySpanExt`, not in the research) and record them as span fields once, so they show in the JSON `spans` list. Check against the pinned versions.

## Node.js

Dependencies: `@opentelemetry/api`, `@opentelemetry/sdk-node`, `@opentelemetry/auto-instrumentations-node`, `@opentelemetry/instrumentation-pino`.

```ts
// src/instrumentation.ts, loaded first:  node --import ./instrumentation.js dist/main.js
import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { PinoInstrumentation } from "@opentelemetry/instrumentation-pino";

const sdk = new NodeSDK({
  instrumentations: [
    getNodeAutoInstrumentations(), // outgoing HTTP and DB clients
    new PinoInstrumentation({ disableLogSending: true }), // trace_id, span_id, trace_flags (logKeys renames them)
  ],
});
sdk.start();
```

Exporter configuration comes from `OTEL_*` variables set by the config module or the deployment (exporter setup is not shown in the research). ESM apps need a loader hook for auto-instrumentation (research). Manual boundary span:

```ts
import { trace } from "@opentelemetry/api";
const tracer = trace.getTracer("order-service");

export async function cancel(id: number): Promise<void> {
  await tracer.startActiveSpan("OrderService.cancel", async (span) => {
    try { /* work */ } finally { span.end(); }
  });
}
```

`startActiveSpan` is named in the research, but its callback shape is not shown on the page read (UNVERIFIED). `disableLogSending: true` turns off forwarding pino records to the OTel Logs SDK (research). The browser logger from `typescript.md` has no OTel setup here.

## Checklist

- `trace_id` in logs equals the id in the tracing backend: outgoing calls carry `traceparent` (instrumentation packages add it).
- `trace_id` / `span_id` never come from user input.
- Secrets follow D5: no request bodies or `Authorization` in span attributes.
