# /health and /ready

Rules: `../SKILL.md` (R-MT-LIVENESS-NO-DEPS, R-MT-READY-TIMEOUTS). Source marks: (R) research `docs/temp/observability/research-wf_35c2e079-c6c.json`; (U) not from the research, verify.

## Contents

1. [Contract](#1-contract)
2. [Python](#2-python)
3. [Go](#3-go)
4. [Rust](#4-rust)
5. [Compose and Kubernetes](#5-compose-and-kubernetes)

## 1. Contract

| | `/health` | `/ready` |
|---|---|---|
| Question | is the process alive and its event loop answering | can it serve traffic now |
| Dependencies | none | DB, Redis, broker: only those the service uses |
| Success | `200` | `200` |
| Failure | none expected | `503` |
| Auth | none | none |
| Per-check timeout | n/a | short, from `docs/POLICY.md`; ask if absent |

Body: JSON `{"status": "ok"}` for `/health`; `/ready` lists each check as `{"db": "ok", "redis": "fail"}` with no error text, hosts or credentials. Shape is common practice, no official source (R: low confidence).

- (R) A Kubernetes HTTP probe passes on status 200 to 399, anything else fails.
- (R) A failing liveness probe makes the kubelet restart the container; this is why `/health` has no dependencies.
- (R, low confidence) A failing readiness probe removes the Pod from Service endpoints without a restart. The handler's total time stays below the probe `timeoutSeconds` (default 1s per the API reference as relayed by the fetcher), so checks run in parallel and the sum of timeouts is bounded.
- Both routes sit outside the auth and rate-limit layers, and out of business metrics (route label `"unmatched"` rules apply; do not add them as high-cardinality labels).

## 2. Python

FastAPI (U: framework API; use the one the service has). Checks are small functions on the repositories/clients, called through a service so the router stays thin.

```python
import asyncio

@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(checks: ReadinessService = Depends(get_readiness_service)) -> JSONResponse:
    results = await checks.run()          # dict[str, bool]
    ok = all(results.values())
    return JSONResponse(
        {name: "ok" if good else "fail" for name, good in results.items()},
        status_code=200 if ok else 503,
    )


class ReadinessService:
    def __init__(self, db: AsyncSession, redis: Redis, timeout_s: float) -> None:  # timeout from Settings
        self._db, self._redis, self._timeout = db, redis, timeout_s

    async def _check(self, coro: Awaitable[object]) -> bool:
        try:
            await asyncio.wait_for(coro, timeout=self._timeout)
            return True
        except Exception:        # a failed dependency is a result, not a crash; log at WARNING via the logging module
            return False

    async def run(self) -> dict[str, bool]:
        db_ok, redis_ok = await asyncio.gather(
            self._check(self._db.execute(text("SELECT 1"))),
            self._check(self._redis.ping()),
        )
        return {"db": db_ok, "redis": redis_ok}
```

## 3. Go

net/http (U: Go 1.22 method patterns in `ServeMux`; use the router the service has). `context.WithTimeout` and `PingContext` are standard library (U).

```go
func (h *Health) Live(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (h *Health) Ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), h.timeout) // from config, POLICY value
	defer cancel()

	var (
		wg               sync.WaitGroup
		dbErr, redisErr  error
	)
	wg.Add(2)
	go func() { defer wg.Done(); dbErr = h.db.PingContext(ctx) }()
	go func() { defer wg.Done(); redisErr = h.redis.Ping(ctx).Err() }() // (U) go-redis shape
	wg.Wait()

	status := http.StatusOK
	if dbErr != nil || redisErr != nil {
		status = http.StatusServiceUnavailable
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"db": okOrFail(dbErr), "redis": okOrFail(redisErr)})
}
```

## 4. Rust

axum (U: framework API; use the one the service has). `tokio::time::timeout` is (U).

```rust
async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok"}))
}

async fn ready(State(s): State<AppState>) -> (StatusCode, Json<serde_json::Value>) {
    let t = s.config.ready_timeout; // from config, POLICY value
    let (db, redis) = tokio::join!(
        tokio::time::timeout(t, s.db.ping()),
        tokio::time::timeout(t, s.redis.ping()),
    );
    let (db_ok, redis_ok) = (matches!(db, Ok(Ok(_))), matches!(redis, Ok(Ok(_))));
    let code = if db_ok && redis_ok { StatusCode::OK } else { StatusCode::SERVICE_UNAVAILABLE };
    (code, Json(serde_json::json!({"db": db_ok, "redis": redis_ok})))
}
```

`ping()` stands for the service's own thin wrapper on the DB pool and Redis client.

## 5. Compose and Kubernetes

(R) Compose `services.<name>.healthcheck`: `test` (`CMD`, `CMD-SHELL` or `NONE`), `interval`, `timeout`, `retries`, `start_period`, `start_interval`; defaults match the Dockerfile `HEALTHCHECK` instruction (numbers not read: U). `depends_on` with `condition: service_healthy` waits for the dependency's healthcheck.

```yaml
services:
  orders:
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/health"]   # (U) the image must contain the tool
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 20s
  gateway:
    depends_on:
      orders:
        condition: service_healthy
```

Point the compose check at `/health` for process liveness, at `/ready` when the dependants must wait for DB and broker. Kubernetes: `livenessProbe` on `/health`, `readinessProbe` on `/ready`, a `startupProbe` for slow starts (R, low confidence); probe numbers (`periodSeconds`, `failureThreshold`) were not read from the docs (U), take them from the deployment policy.
