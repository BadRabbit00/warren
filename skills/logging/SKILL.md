---
name: logging
description: Use when adding or reviewing logging in service code - levels (DEBUG, INFO, WARNING, ERROR, PANIC), canonical fields, masking of secrets and personal data, what DEBUG logs, panic handling, and per-language templates (Python, Go, TypeScript, Rust, OpenTelemetry).
---

# Logging

Rules for logging in service code. Rule ids `R-LG-*`. Per-language templates live in `references/`.

## When to use

- `log-writer` adds logging to a task's code after the tests are green (step `log`, and `fix-log` after a review).
- Reviewers in `/br-review` (pass `logging`) check a diff against these rules; their findings go back to `log-writer`.
- Nobody else loads this skill: coders keep their context free of logging detail.

## Contents

1. [Levels](#levels)
2. [Canonical fields](#canonical-fields)
3. [Masking and limits](#masking-and-limits)
4. [The shared logging module](#the-shared-logging-module)
5. [Rules](#rules)
6. [Reviewer checklist](#reviewer-checklist)
7. [References](#references)

## Levels

| Level | Meaning | What goes here |
|---|---|---|
| DEBUG | Every boundary and data movement. Most lines. | Function entry with `args`, exit with `result` and `duration_ms` (decorator / middleware / span, not by hand); every external call: HTTP request and response, SQL with params, cache hit/miss, broker publish/consume; entity changes `before` → `after`; branch decisions (which path and why). |
| INFO | Business events. Less than DEBUG, but still a lot. | State transitions (order paid, user blocked), job start/finish, startup config summary without secrets. Never inside a loop. |
| WARNING | Not broken, needs attention. | Retry, fallback used, slow call over a `docs/POLICY.md` threshold, near a limit, deprecated path used. |
| ERROR | Something failed and the code goes on. | Missing key, handled external failure. Stack and context. Logged once, where it is handled. |
| PANIC | Unrecoverable. | A global hook logs message, full stack and context, flushes, then exits. Python `CRITICAL` plus `sys.excepthook` / asyncio handler; Go `recover` in `main` and in goroutines; Rust panic hook; Node and browser uncaught handlers. |

The level is named `PANIC` in the output of every language (renamed from the library's own name, e.g. `CRITICAL`, `FATAL`).

## Canonical fields

Every line carries the same fields in every language. They come from the logger configuration (processors / handlers / layers), never from hand-written text in the message.

| Field | Content |
|---|---|
| `timestamp` | UTC, ISO 8601, with zone: `2026-11-10T08:15:30.123Z` |
| `level` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `PANIC` |
| `event` | short fixed message, snake_case or a sentence without values |
| `module` | `app.services.order_service` |
| `func` | full name including the class: `app.services.order_service.OrderService.cancel`; frontend: component + function |
| `file`, `line` | source file and line of the call |
| `request_id`, `trace_id`, `span_id` | bound per request; trace and span from OpenTelemetry |

Extra fields when they apply: `duration_ms`, `args`, `result`, `before`, `after`, `exception`.

Output: JSON in prod, readable console in dev. The level comes from the config module (`LOG_LEVEL`, per-module overrides). Tests run at DEBUG.

## Masking and limits

| Data | DEBUG | INFO and above |
|---|---|---|
| Secrets: passwords, tokens, keys, cookies, `Authorization` | `***` | `***` |
| Personal data: name, email, phone, address, document numbers | full | `***` |
| Large values (bodies, lists, blobs) | truncated to the POLICY limit | truncated |

- The mask value is `***`. One central processor does the masking; code never masks by hand.
- Truncation limits and slow-call thresholds come from `docs/POLICY.md`. If the policy has no number for it, ask (❓) and wait; never invent one.

## The shared logging module

Each service has one shared logging module (Python `core/logging.py`, Go `internal/logging`, and so on). It is copied per service, not shared as a library. It holds: config, the masking processor, the boundary decorator / middleware, `request_id` binding, the panic hook, OpenTelemetry correlation.

- `log-writer` uses this module and never rebuilds or edits it for a task.
- The module is a wave-1 contract task of the project plan. If it is missing, stop with `STATUS: blocked` and report it.

## Rules

### R-LG-FIELDS — values are fields, the context is configured

Bad:
```python
logger.info(f"order_service.OrderService.cancel: order {order_id} cancelled by {user_id} at {datetime.now()}")
```
Why: file, function and time are typed by hand and drift; values glued into the text cannot be searched or masked.

Good:
```python
logger.info("order_cancelled", order_id=order_id, user_id=user_id)
```

### R-LG-BOUNDARY — entry and exit by decorator, not by hand

Bad:
```python
async def cancel(self, order_id: UUID) -> Order:
    logger.debug("cancel start", order_id=order_id)
    start = time.time()
    order = await self._repo.get(order_id)
    logger.debug("cancel end", took=time.time() - start)
    return order
```
Why: copied into every function, easy to forget, wrong units, and it hides the logic.

Good:
```python
@log_boundary  # from core.logging: args on entry, result and duration_ms on exit
async def cancel(self, order_id: UUID) -> Order:
    return await self._repo.get(order_id)
```

### R-LG-EXTERNAL — every external call is logged at DEBUG

HTTP request and response, SQL with params, cache hit/miss, broker publish/consume. Prefer a client hook, middleware or span over a log line next to each call.

Bad:
```python
resp = await self._http.get(url)  # the call is invisible
```
Why: when a payment provider misbehaves there is no record of what was sent and received.

Good:
```python
logger.debug("http_request", method="GET", url=url, params=params)
resp = await self._http.get(url, params=params)
logger.debug("http_response", status=resp.status_code, body=resp.text, duration_ms=resp.elapsed_ms)
```

### R-LG-ENTITY-CHANGE — changes are logged as before → after

Bad:
```python
order.status = OrderStatus.CANCELLED
logger.debug("order changed")
```
Why: the line cannot answer what the status was before.

Good:
```python
before = order.status
order.status = OrderStatus.CANCELLED
logger.debug("order_status_changed", order_id=order.id, before=before, after=order.status)
```

### R-LG-LEVELS — the level matches the meaning

Bad:
```python
for item in items:
    logger.info("processing item", item_id=item.id)   # INFO in a loop
logger.error("retrying payment")                      # not a failure
logger.info("config missing key PAYMENT_URL")         # a failure
```
Why: INFO floods, ERROR cries wolf, a real failure hides at INFO.

Good:
```python
for item in items:
    logger.debug("process_item", item_id=item.id)
logger.warning("payment_retry", attempt=attempt, max_attempts=max_attempts)
logger.error("config_key_missing", key="PAYMENT_URL")
```

### R-LG-ERROR-ONCE — log an error once, where it is handled

Bad:
```python
try:
    await repo.save(order)
except DBError:
    logger.error("save failed", exc_info=True)
    raise                      # the caller logs it again
```
Why: one failure becomes three lines at three layers.

Good:
```python
try:
    await repo.save(order)
except DBError as err:
    raise OrderSaveError(order_id=order.id) from err   # logged once at the handler
```
At the place that handles it: `logger.error("order_save_failed", order_id=order.id, exc_info=True)`.

### R-LG-PANIC-HOOK — unrecoverable errors go through one global hook

Bad:
```go
func main() {
	go worker() // a panic here dies with a raw stderr dump and no request context
	run()
}
```
Why: no structured line, no flush, the cause is lost in container logs.

Good:
```go
func main() {
	defer logging.RecoverPanic() // logs message, stack, context as level PANIC, flushes, exits
	go logging.Go(worker)        // same recover inside goroutines
	run()
}
```
The hook belongs to the shared module; task code does not install its own.

### R-LG-MASK — secrets are never in a log, personal data only at DEBUG

Bad:
```python
logger.info("login", email=user.email, password=password, token=token)
```
Why: secrets and personal data land in the log store and in backups.

Good:
```python
logger.info("login", user_id=user.id)
logger.debug("login_attempt", email=user.email)   # personal data: DEBUG only; secrets stay out
```
The central processor still replaces any `password`, `token`, `Authorization` value with `***` at every level.

### R-LG-NO-PRINT — one logger, no print

Bad:
```typescript
console.log("order cancelled", orderId);
```
Why: no level, no fields, no masking, no request_id.

Good:
```typescript
logger.info({ orderId }, "order_cancelled");
```
Python `print`, Go `fmt.Println` / `log.Printf`, Rust `println!` are forbidden for the same reason (see `references/`).

### R-LG-NO-BEHAVIOUR-CHANGE — logging never changes behaviour

Logging does not alter return values, exceptions, ordering, transactions or timing-dependent logic. Tests stay green and untouched; you never edit them. If a test breaks after logging, undo the line that caused it.

Bad:
```python
logger.debug("rows", count=len(list(rows_iter)))   # consumes the iterator
return rows_iter
```
Why: the log call changes what the function returns.

Good:
```python
rows = list(rows_iter)
logger.debug("rows", count=len(rows))
return rows
```
Only when the original code already materialised the value; otherwise log nothing about it.

## Reviewer checklist

- Every external call and entity change has a DEBUG line (or is covered by the shared decorator / middleware / span).
- Values are fields; no f-strings, `%`, or concatenation in the message.
- No hand-written file, function, class or time in the message.
- INFO appears only for business events and never in a loop; WARNING / ERROR match the table.
- Each error is logged once, where it is handled, with stack and context.
- No secret and no personal data above DEBUG; no new masking code outside the shared module.
- No `print` / `console.log` / `fmt.Println` / `println!`.
- Truncation and slow thresholds cite `docs/POLICY.md`; no invented numbers.
- The diff changes no behaviour: return values, exceptions, tests, hashes of tests are unchanged.
- The shared module was used, not rebuilt.

## References

- [references/python.md](references/python.md) - structlog
- [references/go.md](references/go.md) - log/slog
- [references/typescript.md](references/typescript.md) - pino, Node and browser
- [references/rust.md](references/rust.md) - tracing
- [references/opentelemetry.md](references/opentelemetry.md) - trace and span correlation
