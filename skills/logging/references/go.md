# Logging templates: Go (log/slog)

Copy-ready templates for one service. The module is per service (`internal/logging/logging.go`), copied with the service, never a shared library (D12). Rules and levels: `../SKILL.md`. Only the standard library `log/slog` (Go 1.21+; the research read docs up to go1.26) plus, for trace ids, the OpenTelemetry API module. No `fmt.Println` / `log.Printf` in services (R-GO-LOGGING).

Source marks used below:
- (R) stated in the research `docs/temp/logging/research-wf_6b111f8e-0e4.json`.
- (U) NOT from the research: general knowledge or the research marks it unverified; verify before relying on it.

## Contents

1. [Config and module `internal/logging/logging.go`](#1-config-and-module)
2. [Boundary logging: HTTP middleware and `defer` helper](#2-boundary-logging)
3. [External calls at DEBUG: HTTP client, SQL](#3-external-calls-at-debug)
4. [Levels in use: entity change, branch, INFO, WARNING, ERROR](#4-levels-in-use)
5. [PANIC: recover in main and goroutines](#5-panic)
6. [Tests](#6-tests)

## 1. Config and module

`internal/logging` does not read the environment. The service's config package reads `LOG_LEVEL` and the truncation limit once, and `main` passes them in. Nothing else calls `os.Getenv`.

```go
// internal/config/config.go (excerpt: only what logging needs)
type Config struct {
	LogLevel       string // DEBUG | INFO | WARNING | ERROR | PANIC  (LOG_LEVEL)
	LogMaxValueLen int    // truncation limit, the number comes from docs/POLICY.md; required, no default in code
}
```

Add `LOG_LEVEL` and `LOG_MAX_VALUE_LEN` to `.env.example` in the same change.

What the handler gives:

| Field | Source |
|---|---|
| `timestamp` | `ReplaceAttr` on `slog.TimeKey`: `t.UTC().Format("2006-01-02T15:04:05.000Z07:00")`, `Z` for UTC, fixed milliseconds (R) |
| `level` | `ReplaceAttr` on `slog.LevelKey`: `DEBUG/INFO/WARNING/ERROR/PANIC` (custom level names by `ReplaceAttr`, as in the official custom-levels example, R) |
| `event` | the slog message, renamed from `msg` (renaming the key in `ReplaceAttr`: U) |
| `module`, `func`, `file`, `line` | `AddSource: true`; `ReplaceAttr` on `slog.SourceKey` gets `*slog.Source{Function, File, Line}` (R) |
| `request_id`, `trace_id`, `span_id` | context-reading `slog.Handler` wrapper (R for `request_id`; the `trace.SpanContextFromContext` wrapper is not in the docs the research read: U) |

Known limits, state them to the user instead of hiding:
- `Source.Function` is package-path-qualified; the research could not verify that methods print as `pkg.(*OrderService).Cancel` (observed runtime behaviour, not documented). The template keeps the value as given.
- The canonical fields `module`, `func`, `file`, `line` are emitted as a group under `source` here, because `ReplaceAttr` returns one attribute per call. Returning a group value from `ReplaceAttr` is (U); if the installed Go does not flatten it as expected, the fallback verified by the research is the default `source` group `{function, file, line}`, and `module` is then derived by the log pipeline.

```go
// Package logging configures the service logger: canonical fields, masking, request and trace ids.
package logging

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"strings"

	"go.opentelemetry.io/otel/trace"
)

// LevelPanic is above ERROR; slog has no such level, the name comes from ReplaceAttr.
const LevelPanic = slog.Level(12)

const mask = "***"

// secretKeys are masked at every level, DEBUG included. Substring match on the lower-cased key.
var secretKeys = []string{"password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie", "private_key"}

// personalKeys are shown only at DEBUG and masked at INFO and above. Adapt to the service.
var personalKeys = []string{"email", "phone", "first_name", "last_name", "full_name", "address", "birth", "passport", "iin"}

// Config is filled by main from the service config package.
type Config struct {
	Level       string // DEBUG, INFO, WARNING, ERROR, PANIC
	JSON        bool   // true in prod (JSON), false in dev (text)
	MaxValueLen int    // from POLICY
}

type ctxKey struct{}

// WithRequestID stores the request id in the context (typed key, R).
func WithRequestID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, ctxKey{}, id)
}

// RequestID returns the request id stored by WithRequestID.
func RequestID(ctx context.Context) string {
	id, _ := ctx.Value(ctxKey{}).(string)
	return id
}

func parseLevel(name string) (slog.Level, error) {
	switch strings.ToUpper(name) {
	case "DEBUG":
		return slog.LevelDebug, nil
	case "INFO":
		return slog.LevelInfo, nil
	case "WARNING":
		return slog.LevelWarn, nil
	case "ERROR":
		return slog.LevelError, nil
	case "PANIC":
		return LevelPanic, nil
	}
	return 0, fmt.Errorf("unknown LOG_LEVEL %q", name)
}

func levelName(l slog.Level) string {
	switch {
	case l >= LevelPanic:
		return "PANIC"
	case l >= slog.LevelError:
		return "ERROR"
	case l >= slog.LevelWarn:
		return "WARNING"
	case l >= slog.LevelInfo:
		return "INFO"
	}
	return "DEBUG"
}

func hasAny(key string, parts []string) bool {
	key = strings.ToLower(key)
	for _, p := range parts {
		if strings.Contains(key, p) {
			return true
		}
	}
	return false
}

func truncate(s string, limit int) string {
	if len(s) <= limit {
		return s
	}
	return fmt.Sprintf("%s...<truncated %d>", s[:limit], len(s)-limit)
}

// modulePath returns the package path of a function name like
// "github.com/acme/orders/internal/service.(*OrderService).Cancel".
func modulePath(function string) string {
	slash := strings.LastIndex(function, "/")
	dot := strings.Index(function[slash+1:], ".")
	if dot < 0 {
		return function
	}
	return function[:slash+1+dot]
}

// New builds the logger and makes it the default. Call once at the start of main.
func New(cfg Config) (*slog.Logger, error) {
	level, err := parseLevel(cfg.Level)
	if err != nil {
		return nil, err
	}
	var lv slog.LevelVar
	lv.Set(level)

	replace := func(groups []string, a slog.Attr) slog.Attr {
		if len(groups) == 0 {
			switch a.Key {
			case slog.TimeKey:
				return slog.String("timestamp", a.Value.Time().UTC().Format("2006-01-02T15:04:05.000Z07:00"))
			case slog.LevelKey:
				return slog.String("level", levelName(a.Value.Any().(slog.Level)))
			case slog.MessageKey:
				return slog.Attr{Key: "event", Value: a.Value}
			case slog.SourceKey:
				src := a.Value.Any().(*slog.Source)
				return slog.Attr{Key: "source", Value: slog.GroupValue(
					slog.String("module", modulePath(src.Function)),
					slog.String("func", src.Function),
					slog.String("file", src.File),
					slog.Int("line", src.Line),
				)}
			}
		}
		// Central masking: secrets always, personal data unless DEBUG is on right now.
		if hasAny(a.Key, secretKeys) || (hasAny(a.Key, personalKeys) && lv.Level() > slog.LevelDebug) {
			return slog.String(a.Key, mask)
		}
		v := a.Value.Resolve()
		switch v.Kind() {
		case slog.KindString:
			return slog.String(a.Key, truncate(v.String(), cfg.MaxValueLen))
		case slog.KindAny:
			// Structs may hold secrets under keys we cannot see: pass groups (slog.Group), not structs.
			return slog.String(a.Key, truncate(fmt.Sprintf("%v", v.Any()), cfg.MaxValueLen))
		}
		return a
	}

	opts := &slog.HandlerOptions{AddSource: true, Level: &lv, ReplaceAttr: replace}
	var base slog.Handler
	if cfg.JSON {
		base = slog.NewJSONHandler(os.Stdout, opts)
	} else {
		base = slog.NewTextHandler(os.Stdout, opts)
	}
	logger := slog.New(contextHandler{base})
	slog.SetDefault(logger)
	return logger, nil
}

// contextHandler adds request_id, trace_id and span_id from the context to every record.
type contextHandler struct{ slog.Handler }

func (h contextHandler) Handle(ctx context.Context, r slog.Record) error {
	if id := RequestID(ctx); id != "" {
		r.AddAttrs(slog.String("request_id", id))
	}
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() { // (U) wrapper pattern, not in the docs read
		r.AddAttrs(slog.String("trace_id", sc.TraceID().String()), slog.String("span_id", sc.SpanID().String()))
	}
	return h.Handler.Handle(ctx, r)
}

func (h contextHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return contextHandler{h.Handler.WithAttrs(attrs)}
}

func (h contextHandler) WithGroup(name string) slog.Handler {
	return contextHandler{h.Handler.WithGroup(name)}
}

```

Notes:
- Always log with the context: `slog.InfoContext(ctx, ...)`, `DebugContext`, `ErrorContext`. Without `ctx` the wrapper cannot add `request_id` (R).
- Truncation and masking happen in `ReplaceAttr`, which sees leaf attributes by key; build nested data with `slog.Group("args", slog.String("password", p))` so keys are visible. Never log a struct with `slog.Any`.
- State: pass `*slog.Logger` into constructors, or call the `slog.*Context` functions that use the default set by `New`; keep no other logger global.
- A text handler in dev prints `source` as `source.func=...` pairs; that is expected.
- Per-module level overrides (D6) are not in the research and not in this template.

`main`:

```go
func main() {
	cfg := config.Load() // the only place that reads the environment
	if _, err := logging.New(logging.Config{
		Level: cfg.LogLevel, JSON: cfg.Env == "prod", MaxValueLen: cfg.LogMaxValueLen,
	}); err != nil {
		fmt.Fprintln(os.Stderr, err) // logger is not ready yet
		os.Exit(1)
	}
	defer logging.Recover(context.Background())
	slog.Info("service.started", "log_level", cfg.LogLevel) // non-secret settings only
	// ...
}
```

## 2. Boundary logging

HTTP middleware: sets `request_id` (from `X-Request-ID` or generated), puts it into the context, logs request and response at DEBUG with status and `duration_ms`.

```go
// internal/logging/http.go
package logging

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"time"
)

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}

func newID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// Middleware assigns a request id and logs each request and response at DEBUG.
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-ID")
		if id == "" {
			id = newID()
		}
		ctx := WithRequestID(r.Context(), id)
		w.Header().Set("X-Request-ID", id)

		started := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		slog.DebugContext(ctx, "http.request", "method", r.Method, "path", r.URL.Path)
		next.ServeHTTP(sw, r.WithContext(ctx))
		slog.DebugContext(ctx, "http.response", "method", r.Method, "path", r.URL.Path,
			"status", sw.status, "duration_ms", float64(time.Since(started).Microseconds())/1000)
	})
}
```

Put `Middleware` outermost, around the router and OTel's `otelhttp.NewHandler` (R: the OTel getting-started wraps the mux with `otelhttp.NewHandler`), so the span exists when handlers log. Query strings are not logged (they can carry tokens).

Function entry and exit with a `defer` helper. The helper itself is the call site of its log lines, so the traced function's name is passed as `target` (taken from the runtime: `runtime.Caller` and `runtime.FuncForPC`, U), full package-qualified name.

```go
// internal/logging/trace.go
package logging

import (
	"context"
	"log/slog"
	"runtime"
	"time"
)

// Trace logs entry with args at DEBUG and returns a function that logs exit with
// the error and duration. Use: defer logging.Trace(ctx, slog.Group("args", ...))(&err)
func Trace(ctx context.Context, args ...any) func(err *error) {
	if !slog.Default().Enabled(ctx, slog.LevelDebug) {
		return func(*error) {}
	}
	pc, _, _, _ := runtime.Caller(1)
	target := runtime.FuncForPC(pc).Name()
	started := time.Now()
	slog.DebugContext(ctx, "enter", append([]any{"target", target}, args...)...)
	return func(err *error) {
		attrs := []any{"target", target, "duration_ms", float64(time.Since(started).Microseconds()) / 1000}
		if err != nil && *err != nil {
			attrs = append(attrs, "error", (*err).Error())
		}
		slog.DebugContext(ctx, "exit", attrs...)
	}
}
```

Use it with a named return so the exit line sees the error. Results go in as a group when useful:

```go
func (s *OrderService) Cancel(ctx context.Context, id string, reason string) (order Order, err error) {
	defer logging.Trace(ctx, slog.Group("args", slog.String("order_id", id), slog.String("reason", reason)))(&err)
	// ...
}
```

Use it at boundaries (service, repository, client methods), not inside loops or hot helpers. Where OpenTelemetry spans wrap the same function, the span replaces the entry/exit pair (D3); do not stack both. Spans: `ctx, span := tracer.Start(ctx, "OrderService.Cancel"); defer span.End()` (R, OTel getting-started).

## 3. External calls at DEBUG

### HTTP client: `http.RoundTripper` wrapper

Logs method, URL without query, header group (masked by key), status and duration. The client keeps its own `Timeout` and retry policy from `docs/POLICY.md`; this wrapper only logs.

```go
// internal/logging/transport.go
package logging

import (
	"log/slog"
	"net/http"
	"time"
)

// Transport logs each outgoing request and its response at DEBUG.
type Transport struct{ Base http.RoundTripper }

func headerAttrs(h http.Header) []any {
	attrs := make([]any, 0, len(h))
	for k, v := range h {
		if len(v) > 0 {
			attrs = append(attrs, slog.String(k, v[0])) // Authorization, Cookie... masked by key in ReplaceAttr
		}
	}
	return attrs
}

// RoundTrip implements http.RoundTripper.
func (t Transport) RoundTrip(r *http.Request) (*http.Response, error) {
	base := t.Base
	if base == nil {
		base = http.DefaultTransport
	}
	ctx := r.Context()
	target := r.URL.Scheme + "://" + r.URL.Host + r.URL.Path
	slog.DebugContext(ctx, "http.client.request", "method", r.Method, "url", target,
		slog.Group("headers", headerAttrs(r.Header)...))

	started := time.Now()
	resp, err := base.RoundTrip(r)
	ms := float64(time.Since(started).Microseconds()) / 1000
	if err != nil {
		slog.DebugContext(ctx, "http.client.error", "method", r.Method, "url", target, "duration_ms", ms, "error", err.Error())
		return nil, err
	}
	slog.DebugContext(ctx, "http.client.response", "method", r.Method, "url", target, "status", resp.StatusCode, "duration_ms", ms)
	return resp, nil
}
```

`&http.Client{Transport: logging.Transport{}, Timeout: timeout}`. For spans on outgoing calls use `otelhttp.NewTransport` (the research names only `otelhttp` for `net/http`, R); compose them: `logging.Transport{Base: otelhttp.NewTransport(http.DefaultTransport)}`; `otelhttp.NewTransport` itself is (U).

### SQL with parameters

The research found no official `database/sql` instrumentation in OpenTelemetry Go contrib (R), so wrap the repository call with `Trace` and a manual span, or use the ORM's logger. For GORM, implement `gorm.io/gorm/logger.Interface`, whose `Trace(ctx, begin time.Time, fc func() (sql string, rowsAffected int64), err error)` method receives every statement with its duration. This is (U): not from the research; check the installed GORM version, and check that the statement it gives has parameters substituted (secrets in values would then appear in `sql`). Prefer the logger's parameterized-query mode if the installed version has one (U), and log the parameters as a `slog.Group` so `ReplaceAttr` masks them by name. Log the statement at DEBUG only, with `slog.DebugContext(ctx, "sql.execute", "statement", sql, "rows", rows, "duration_ms", ms)`.

## 4. Levels in use

Entity change (before → after) at DEBUG, as groups so the masker sees the keys:

```go
before := slog.Group("before", slog.String("status", string(order.Status)), slog.Int64("total", order.Total))
order.Status = newStatus
if err = s.repo.Save(ctx, &order); err != nil {
	return Order{}, fmt.Errorf("save order: %w", err)
}
slog.DebugContext(ctx, "order.updated", "order_id", id, before,
	slog.Group("after", slog.String("status", string(order.Status)), slog.Int64("total", order.Total)))
slog.InfoContext(ctx, "order.status_changed", "order_id", id, "status", order.Status) // business event, once, not in a loop
```

Branch decision at DEBUG: the inputs and the branch taken.

```go
if order.PaidAt == nil {
	slog.DebugContext(ctx, "cancel.branch", "branch", "unpaid_no_refund", "status", order.Status)
} else {
	slog.DebugContext(ctx, "cancel.branch", "branch", "paid_refund", "amount", order.Total)
}
```

WARNING (works, needs attention):

```go
slog.WarnContext(ctx, "payments.retry", "attempt", attempt, "max_attempts", maxAttempts, "delay_ms", delay.Milliseconds(), "error", err.Error())
```

`slog.Warn*` prints as `WARNING` through `levelName`.

ERROR (failed, the code goes on): once, where handled, with the stack. slog has no stack attribute; add it from `runtime/debug`.

```go
if err := s.mail.Send(ctx, msg); err != nil {
	slog.ErrorContext(ctx, "order.mail_failed", "order_id", order.ID, "error", err.Error(),
		"stack", string(debug.Stack())) // runtime/debug; once here, not at each layer the error passed through
}
```

Functions that only return an error wrap it (`fmt.Errorf("...: %w", err)`, R-GO-ERRORS) and do not log it.

## 5. PANIC

Unrecoverable: log at PANIC with the panic value, the stack and context, flush, exit non-zero. `recover` works only inside a deferred function, and `debug.Stack` must be called inside it to show the panic origin (R). An unrecovered panic in any goroutine ends the program and `debug.Stack` covers only the calling goroutine, so every goroutine gets its own deferred `Recover` (R).

```go
// internal/logging/panic.go
package logging

import (
	"context"
	"log/slog"
	"os"
	"runtime/debug"
)

// Recover is deferred (directly) at the top of main and of every goroutine:
//
//	defer logging.Recover(ctx)
func Recover(ctx context.Context) {
	r := recover()
	if r == nil {
		return
	}
	slog.Default().Log(ctx, LevelPanic, "panic", slog.Any("panic", r), slog.String("stack", string(debug.Stack())))
	// slog writes to os.Stdout without buffering; sync in case stdout is a file or pipe wrapper.
	_ = os.Stdout.Sync()
	os.Exit(1)
}

// Go starts fn in a goroutine that panics through Recover.
func Go(ctx context.Context, fn func(ctx context.Context)) {
	go func() {
		defer Recover(ctx)
		fn(ctx)
	}()
}
```

`slog.Any("panic", r)` goes through `ReplaceAttr` as `KindAny` and is printed with `%v`. A panic recovered on purpose (an HTTP handler where `net/http` already recovers, a library boundary that converts it into an error) is not PANIC: log it at ERROR, once. Use `Recover` only where the process must stop.

## 6. Tests

Tests run with `LOG_LEVEL=DEBUG`: the test setup builds `logging.New(logging.Config{Level: "DEBUG", JSON: false, MaxValueLen: <test value>})` or the test environment file sets `LOG_LEVEL=DEBUG` for the config package. At DEBUG the boundary, HTTP and SQL lines appear and personal data is unmasked, so test data must be synthetic; secrets stay `***` in tests too. To assert on output, point a handler built with the same `HandlerOptions` at a `bytes.Buffer` (U, ordinary slog usage) and check the masked keys; test `truncate`, `hasAny` and `levelName` directly.
