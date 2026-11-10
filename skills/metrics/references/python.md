# Metrics templates: Python (OpenTelemetry SDK)

Copy-ready templates for one service. The module is per service (`app/core/metrics.py`), copied with the service. Rules: `../SKILL.md`. A new dependency is reported to the orchestrator, not added.

Source marks:
- (R) stated in the research `docs/temp/observability/research-wf_35c2e079-c6c.json`.
- (U) NOT from the research: verify against the installed version before relying on it.

Packages (R, latest on 2026-11-10, nothing pinned in the project): `opentelemetry-sdk` 1.45.2, `opentelemetry-exporter-otlp-proto-http` 1.45.2, `opentelemetry-exporter-prometheus` 0.66b2 (beta; needs sdk `~=1.45.2`, `prometheus-client>=0.5.0,<1.0.0`).

## Contents

1. [Config fields](#1-config-fields)
2. [Connector module](#2-connector-module-appcoremetricspy)
3. [Request duration hook](#3-request-duration-hook)
4. [Domain method in use](#4-domain-method-in-use)
5. [Tests](#5-tests)

## 1. Config fields

Only the config module reads env (R-MT-CONFIG). Add to `Settings` and `.env.example` in the same change.

```python
# app/core/config.py (excerpt)
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_")

    metrics_exporter: Literal["prometheus", "otlp", "none"]
    metrics_prometheus_port: int          # 9464 is the port in the research examples (R)
    metrics_otlp_endpoint: str            # used when metrics_exporter == "otlp"
    service_name: str
```

## 2. Connector module `app/core/metrics.py`

(R) `MeterProvider(metric_readers=[...])` from `opentelemetry.sdk.metrics`; `PeriodicExportingMetricReader(OTLPMetricExporter(...))`; `PrometheusMetricReader` plus `prometheus_client.start_http_server(port=9464)`, served at `/metrics`; `meter.create_counter`, `meter.create_observable_gauge(callbacks=[...])`. `create_histogram` and `create_up_down_counter` exist in the API but the research shows no example (U for call shape). Import paths other than `opentelemetry.sdk.metrics`, the `View` and `ExplicitBucketHistogramAggregation` classes, `Resource`, and `metrics.get_meter` are (U).

```python
from __future__ import annotations

from enum import StrEnum

from opentelemetry import metrics as otel_metrics                      # (U)
from opentelemetry.sdk.metrics import MeterProvider                    # (R)
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # (U path; class R)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View  # (U)
from opentelemetry.sdk.resources import Resource                       # (U)

from app.core.config import Settings

HTTP_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]  # (R) semconv
DB_BUCKETS = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 10]                                  # (R) semconv


class OrderStatus(StrEnum):
    """Closed set: the only values allowed as the `status` attribute."""

    NEW = "new"
    PAID = "paid"
    CANCELLED = "cancelled"


class Metrics:
    """The only place that knows OpenTelemetry. Business code calls the methods."""

    def __init__(self, meter: otel_metrics.Meter) -> None:
        self._request_duration = meter.create_histogram(
            "http.server.request.duration", unit="s",
            description="Duration of HTTP server requests.",
        )
        self._active_requests = meter.create_up_down_counter(
            "http.server.active_requests", unit="{request}",
            description="Requests in flight.",
        )
        self._orders_created = meter.create_counter(
            "orders.created", unit="{order}",
            description="Orders created, by resulting status.",
        )

    def observe_request(self, *, route: str, method: str, status: int, seconds: float) -> None:
        # route is a template ("/orders/{order_id}"), never the raw path
        self._request_duration.record(
            seconds,
            {"http.route": route, "http.request.method": method, "http.response.status_code": status},
        )

    def request_started(self) -> None:
        self._active_requests.add(1)

    def request_finished(self) -> None:
        self._active_requests.add(-1)

    def order_created(self, *, status: OrderStatus) -> None:
        self._orders_created.add(1, {"status": status.value})


def _build_provider(settings: Settings) -> MeterProvider:
    readers: list[object] = []
    if settings.metrics_exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter  # (U path)

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=settings.metrics_otlp_endpoint)))
    elif settings.metrics_exporter == "prometheus":
        from opentelemetry.exporter.prometheus import PrometheusMetricReader  # (U path; class R)
        from prometheus_client import start_http_server                      # (R)

        start_http_server(port=settings.metrics_prometheus_port)  # serves /metrics (R)
        readers.append(PrometheusMetricReader())
    views = [
        View(instrument_name="http.server.request.duration",
             aggregation=ExplicitBucketHistogramAggregation(HTTP_BUCKETS)),  # (U) View signature
    ]
    return MeterProvider(
        metric_readers=readers,  # (R)
        views=views,             # (U)
        resource=Resource.create({"service.name": settings.service_name}),  # (U)
    )


def build_metrics(settings: Settings) -> Metrics:
    """Call once at startup; keep the result on the application (dependency), not in a module global."""
    provider = _build_provider(settings)
    return Metrics(provider.get_meter("orders"))  # (U) get_meter
```

Shutdown: call `provider.shutdown()` on exit so the last batch is exported (U). Keep the provider on the app object created in the startup hook.

## 3. Request duration hook

FastAPI / Starlette middleware (U: framework API, use the one the service already has). The route template is read after the call, when routing has run.

```python
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]  # starlette's own signature
        metrics: Metrics = request.app.state.metrics
        metrics.request_started()
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            metrics.request_finished()
            metrics.observe_request(
                route=route.path if route is not None else "unmatched",  # never request.url.path
                method=request.method, status=status,
                seconds=time.perf_counter() - start,
            )
```

`unmatched` keeps 404 scans from creating one series per URL.

## 4. Domain method in use

```python
# app/services/order_service.py
class OrderService:
    def __init__(self, repo: OrderRepository, metrics: Metrics) -> None:
        self._repo = repo
        self._metrics = metrics

    async def create(self, data: OrderCreate) -> Order:
        order = await self._repo.add(data)
        self._metrics.order_created(status=OrderStatus(order.status))
        return order
```

`Metrics` arrives by dependency injection (the service constructor), so tests pass a fake. The service imports `app.core.metrics`, never `opentelemetry`.

## 5. Tests

The research names no in-memory reader for Python. (U) The SDK ships `InMemoryMetricReader` in `opentelemetry.sdk.metrics.export`; verify the import and `get_metrics_data()` against the installed 1.45.x before using it. Without it, pass a fake `Metrics` (a plain class recording calls) to the service tests. Tests are never edited by `metrics-writer`.
