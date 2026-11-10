# Metrics templates: Go (OpenTelemetry SDK)

Copy-ready templates for one service. The package is per service (`internal/metrics/metrics.go`), copied with the service. Rules: `../SKILL.md`. A new dependency is reported to the orchestrator, not added.

Source marks:
- (R) stated in the research `docs/temp/observability/research-wf_35c2e079-c6c.json`.
- (U) NOT from the research: verify against the installed version before relying on it.

Modules (R, latest on 2026-11-10, nothing pinned): `go.opentelemetry.io/otel/sdk/metric` v1.47.0, `go.opentelemetry.io/otel/exporters/prometheus` v0.69.0. OTLP exporter packages (`otlpmetrichttp`, `otlpmetricgrpc`) were not confirmed by the research (U).

## Contents

1. [Config fields](#1-config-fields)
2. [Connector package](#2-connector-package)
3. [Request duration middleware](#3-request-duration-middleware)
4. [Domain method in use](#4-domain-method-in-use)
5. [Tests](#5-tests)

## 1. Config fields

Only `internal/config` reads env (R-MT-CONFIG).

```go
// internal/config/config.go (excerpt)
type Config struct {
	ServiceName         string
	MetricsExporter     string // "prometheus" | "otlp" | "none"
	MetricsOTLPEndpoint string
}
```

## 2. Connector package

(R) `sdkmetric.NewMeterProvider`, `WithReader`, `WithView`, `NewView`, `AggregationExplicitBucketHistogram`, `WithCardinalityLimit`, `NewPeriodicReader` (default interval 60s per pkg.go.dev summary); `otelprom.New()` registers on the default Prometheus registerer, `otelprom.WithRegisterer(reg)` for a custom one; `promhttp.Handler()` / `promhttp.HandlerFor(reg, ...)`. Struct field names of `Instrument` / `Stream`, `provider.Meter`, and the instrument constructors (`Int64Counter`, `Float64Histogram`, `Int64UpDownCounter`, option names) are (U).

```go
package metrics

import (
	"context"
	"fmt"
	"net/http"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	otelprom "go.opentelemetry.io/otel/exporters/prometheus"
	"go.opentelemetry.io/otel/attribute" // (U)
	"go.opentelemetry.io/otel/metric"    // (U) used here only, never in business code
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"

	"example.com/orders/internal/config"
)

var httpBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10} // (R) semconv

// OrderStatus is a closed set: the only values allowed as the status attribute.
type OrderStatus string

const (
	StatusNew       OrderStatus = "new"
	StatusPaid      OrderStatus = "paid"
	StatusCancelled OrderStatus = "cancelled"
)

// Metrics is the only place that knows OpenTelemetry. Business code calls the methods.
type Metrics struct {
	requestDuration metric.Float64Histogram // (U)
	activeRequests  metric.Int64UpDownCounter
	ordersCreated   metric.Int64Counter
	handler         http.Handler // /metrics, nil unless exporter is prometheus
	provider        *sdkmetric.MeterProvider
}

func New(cfg config.Config) (*Metrics, error) {
	m := &Metrics{}
	opts := []sdkmetric.Option{
		sdkmetric.WithView(sdkmetric.NewView( // (R) names, (U) fields
			sdkmetric.Instrument{Name: "http.server.request.duration"},
			sdkmetric.Stream{Aggregation: sdkmetric.AggregationExplicitBucketHistogram{Boundaries: httpBuckets}},
		)),
	}
	switch cfg.MetricsExporter {
	case "prometheus":
		reg := prometheus.NewRegistry()
		exp, err := otelprom.New(otelprom.WithRegisterer(reg)) // (R)
		if err != nil {
			return nil, fmt.Errorf("prometheus exporter: %w", err)
		}
		opts = append(opts, sdkmetric.WithReader(exp)) // (R) exporter is a Reader
		m.handler = promhttp.HandlerFor(reg, promhttp.HandlerOpts{}) // (R)
	case "otlp":
		// (U) build an OTLP exporter (otlpmetrichttp) with cfg.MetricsOTLPEndpoint, then:
		// opts = append(opts, sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exp))) // NewPeriodicReader (R)
		return nil, fmt.Errorf("otlp exporter: package names not confirmed by the research, verify and fill in")
	}
	m.provider = sdkmetric.NewMeterProvider(opts...) // (R)
	meter := m.provider.Meter("orders")              // (U)

	var err error
	if m.requestDuration, err = meter.Float64Histogram("http.server.request.duration",
		metric.WithUnit("s"), metric.WithDescription("Duration of HTTP server requests.")); err != nil { // (U)
		return nil, err
	}
	if m.activeRequests, err = meter.Int64UpDownCounter("http.server.active_requests",
		metric.WithUnit("{request}"), metric.WithDescription("Requests in flight.")); err != nil {
		return nil, err
	}
	if m.ordersCreated, err = meter.Int64Counter("orders.created",
		metric.WithUnit("{order}"), metric.WithDescription("Orders created, by resulting status.")); err != nil {
		return nil, err
	}
	return m, nil
}

// Handler serves /metrics when the exporter is prometheus; mount it in the router.
func (m *Metrics) Handler() http.Handler { return m.handler }

func (m *Metrics) Shutdown(ctx context.Context) error { return m.provider.Shutdown(ctx) } // (U)

// ObserveRequest: route is a template ("/orders/{order_id}"), never the raw path.
func (m *Metrics) ObserveRequest(ctx context.Context, route, method string, status int, seconds float64) {
	m.requestDuration.Record(ctx, seconds, metric.WithAttributes(
		attribute.String("http.route", route),
		attribute.String("http.request.method", method),
		attribute.Int("http.response.status_code", status),
	))
}

func (m *Metrics) RequestStarted(ctx context.Context)  { m.activeRequests.Add(ctx, 1) }
func (m *Metrics) RequestFinished(ctx context.Context) { m.activeRequests.Add(ctx, -1) }

func (m *Metrics) OrderCreated(ctx context.Context, status OrderStatus) {
	m.ordersCreated.Add(ctx, 1, metric.WithAttributes(attribute.String("status", string(status))))
}
```

Cardinality cap: add `sdkmetric.WithCardinalityLimit(n)` (R) only with a number from `docs/POLICY.md`; the spec default is 2000 (R).

## 3. Request duration middleware

net/http (U: the router the service uses decides how to get the route template; with Go 1.22 `ServeMux`, `r.Pattern` after routing is (U)).

```go
func (m *Metrics) Middleware(routeOf func(*http.Request) string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ctx := r.Context()
			m.RequestStarted(ctx)
			start := time.Now()
			rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
			defer func() {
				m.RequestFinished(ctx)
				m.ObserveRequest(ctx, routeOf(r), r.Method, rec.status, time.Since(start).Seconds())
			}()
			next.ServeHTTP(rec, r)
		})
	}
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (s *statusRecorder) WriteHeader(code int) { s.status = code; s.ResponseWriter.WriteHeader(code) }
```

`routeOf` returns the template, or `"unmatched"` when none matched.

## 4. Domain method in use

```go
// internal/service/order_service.go: depends on a small interface declared next to the service, so tests pass a fake
type orderMetrics interface {
	OrderCreated(ctx context.Context, status metrics.OrderStatus)
}

func (s *OrderService) Create(ctx context.Context, in OrderCreate) (Order, error) {
	order, err := s.repo.Add(ctx, in)
	if err != nil {
		return Order{}, err
	}
	s.metrics.OrderCreated(ctx, metrics.StatusNew)
	return order, nil
}
```

The service imports `internal/metrics` for the typed values, never `go.opentelemetry.io`.

## 5. Tests

The research names no in-memory reader for Go. (U) The SDK has a manual reader (`sdkmetric.NewManualReader`) and `metricdata` types in `sdk/metric/metricdata`; verify against v1.47.0 before using. Otherwise inject a fake of the small interface above. Tests are never edited by `metrics-writer`.
