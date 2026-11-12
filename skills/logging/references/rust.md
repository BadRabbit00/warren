# Rust logging templates (tracing + tracing-subscriber)

Copy per service (D12): `src/logging.rs`. Canonical fields: `timestamp level event module func file line request_id trace_id span_id` plus `duration_ms args result before after exception`. Levels `DEBUG INFO WARNING ERROR PANIC`; secrets always `***`; personal data masked unless DEBUG; time is UTC RFC 3339.

Facts used (research wf_6b111f8e-0e4, docs.rs latest on 2026-11-10): `tracing-subscriber` 0.3.23, `tracing-attributes` 0.1.31.
- `.with_file(true)`, `.with_line_number(true)`, `.with_target(true)` need no extra feature; `.with_timer(UtcTime::rfc_3339())` needs features `fmt`, `std`, `time` (alternative `ChronoUtc::rfc_3339()` with `chrono`, `fmt`, `std`).
- `.json()` needs feature `json` (newline-delimited, `target` and `spans` list by default); `.pretty()` needs `ansi`.
- `#[instrument]`: span named after the function, `name=`, `skip(...)`, `skip_all`, `fields(...)`, `ret`, `err`; default level INFO; skipped args need not implement `Debug`.
- Panic hook: `std::panic::set_hook` with `PanicHookInfo` (payload, location); `Backtrace::force_capture()` always captures, `capture()` only if `RUST_BACKTRACE`/`RUST_LIB_BACKTRACE` is set.

Marked UNVERIFIED (not in the research): the cargo feature `env-filter` and `EnvFilter` (needed for level filtering; check docs.rs for 0.3.23), whether JSON output prints `filename` / `line_number` keys (the research shows only `timestamp level fields target spans`), a `module` key in JSON (use `target`), level names `WARNING`/`PANIC` (tracing has only TRACE/DEBUG/INFO/WARN/ERROR), `request_id`/`trace_id` in lines (research: not covered; use root span fields), `FmtSpan::CLOSE` for durations.

## Cargo.toml

```toml
[dependencies]
tracing = "0.1"
tracing-subscriber = { version = "0.3.23", features = ["fmt", "std", "json", "ansi", "time", "env-filter"] } # env-filter: UNVERIFIED
```

## Level mapping

tracing has no WARNING or PANIC. Lines carry the tracing level name (`WARN`, `ERROR`); the log pipeline (or a custom `FormatEvent`) renames `WARN` to `WARNING`. PANIC is an `error!` event with the field `level_name = "PANIC"`; consumers treat `level_name` as the canonical `level` when present.

## Subscriber setup `src/logging.rs`

```rust
use tracing_subscriber::{fmt, fmt::time::UtcTime, EnvFilter};

/// `log_level` and `json` come from the config module (LOG_LEVEL, LOG_FORMAT); never read env here.
/// Per-module overrides are EnvFilter directives: "info,my_service::billing=debug".
pub fn init(log_level: &str, json: bool) {
    let filter = EnvFilter::try_new(log_level).unwrap_or_else(|_| EnvFilter::new("info"));
    let builder = fmt()
        .with_env_filter(filter)
        .with_timer(UtcTime::rfc_3339()) // 2026-11-10T09:30:00.123456Z
        .with_file(true)
        .with_line_number(true)
        .with_target(true); // target = module path, e.g. my_service::services::order

    if json {
        builder.json().init(); // prod: one JSON object per line, includes `spans`
    } else {
        builder.pretty().init(); // dev: readable console
    }
}
```

Call `logging::init(&config.log_level, config.log_json)` first in `main`. Tests run at DEBUG: call `init("debug", false)` once (`std::sync::Once`) or use `tracing_subscriber::fmt().with_test_writer()`.

`func` with its class: the span name is the function name only. For impl methods put the type in the span name explicitly (below). In JSON the span chain is under `spans` (innermost last), so the innermost name acts as `func`.

## Boundaries with `#[instrument]` (DEBUG entry/exit/duration)

```rust
use tracing::{debug, instrument};

pub struct OrderService { /* repo, clients */ }

impl OrderService {
    /// Span "OrderService::cancel" wraps the call; args are recorded except the skipped ones.
    #[instrument(
        name = "OrderService::cancel",
        level = "debug",
        skip(self, api_token),            // secrets and non-Debug state never recorded
        fields(order_id = %order_id, request_id = tracing::field::Empty),
        ret,                              // result as an event
        err                               // Err(..) as an ERROR event
    )]
    pub async fn cancel(&self, order_id: u64, api_token: &str) -> Result<(), OrderError> {
        debug!(event = "order.cancel.start");
        Ok(())
    }
}
```

- Every argument that may hold a secret is in `skip(...)`; or use `skip_all` and list safe values in `fields(...)`.
- `duration_ms`: enable span close events with `.with_span_events(fmt::format::FmtSpan::CLOSE)` on the builder (UNVERIFIED; the close event carries `time.busy` / `time.idle`).
- `request_id`: declared `Empty` on the root span and filled with `Span::current().record("request_id", &id)` in the HTTP middleware; the JSON `spans` list shows it for child spans.
- Free functions: `#[instrument(skip_all, fields(user_id = %user_id))]`, the span name is the function name.

## Masking secret and personal values

tracing has no central processor. The research gives only `skip` and `fields`; the types below are plain Rust, your own code.

```rust
use std::fmt;
use std::sync::atomic::{AtomicBool, Ordering};

/// Secret: Debug and Display always print `***`.
pub struct Secret<T>(pub T);
impl<T> fmt::Debug for Secret<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { f.write_str("***") }
}
impl<T> fmt::Display for Secret<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { f.write_str("***") }
}

/// Personal data: full only when debug logging is on (set once in `init`), `***` otherwise.
pub static DEBUG_ENABLED: AtomicBool = AtomicBool::new(false);
pub struct Personal<T>(pub T);
impl<T: fmt::Debug> fmt::Debug for Personal<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if DEBUG_ENABLED.load(Ordering::Relaxed) { self.0.fmt(f) } else { f.write_str("***") }
    }
}
```

Use these types in logged domain structs (`#[derive(Debug)]` then masks automatically) and in `fields(email = ?Personal(&email))`. Set `DEBUG_ENABLED` in `init` when `log_level` starts with `debug` or `trace`.

## Panic hook: PANIC with message and backtrace

```rust
use std::backtrace::Backtrace;
use std::panic::{self, PanicHookInfo};

pub fn install_panic_hook() {
    panic::set_hook(Box::new(|info: &PanicHookInfo<'_>| {
        let message = info
            .payload()
            .downcast_ref::<&str>().map(|s| (*s).to_owned())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "non-string panic payload".to_owned());
        let location = info.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
        let backtrace = Backtrace::force_capture(); // ignores RUST_BACKTRACE

        tracing::error!(
            level_name = "PANIC",
            event = "panic",
            exception = %message,
            panic_location = %location,
            backtrace = %backtrace,
        );
        // Event file/line point at this hook; the real place is `panic_location`.
        // Flush: the default fmt writer writes per event. With a non-blocking writer
        // (tracing-appender, not in the research) keep its guard alive until exit.
    }));
}
```

Call `install_panic_hook()` right after `logging::init`. Panics inside spawned tasks do not stop the process by themselves; also log a failed `JoinHandle` result at ERROR (tokio, not in the research).

## Library crates: emit only, never install a subscriber

A library crate depends on `tracing` only and emits events and spans. Only the binary installs the subscriber (`logging::init` and `install_panic_hook` above, called from `main`). A library that calls `init()` takes the process-wide subscriber away from the application, and a second global install fails or is ignored.

- Library `Cargo.toml`: `tracing = "0.1"` under `[dependencies]`; `tracing-subscriber` only under `[dev-dependencies]`.
- Library tests: `tracing_subscriber::fmt().with_test_writer().try_init()` and ignore the `Err` (a subscriber is already set by another test). Plain `init()` panics on the second call. `try_init` on the fmt builder is UNVERIFIED against 0.3.23 (not in the research); check docs.rs.
- `logging::init` in this file is for services. Do not copy it into a library.

## Log an error once, at the boundary that handles it

Matches R-LG-ERROR-ONCE in `skills/logging/SKILL.md`. Layers that only pass an error up do not log it; they add context and return it with `?`. The layer that handles it (HTTP handler, job runner, `main`) emits one `ERROR` event with the whole error.

```rust
use tracing::error;

// Intermediate layer: add context, no log call.
async fn load_order(id: u64) -> Result<Order, OrderError> {
    repo.get(id).await.map_err(|e| OrderError::Load { id, source: e })
}

// Boundary: handled here (response is built), so logged here, once.
async fn handle(id: u64) -> Response {
    match load_order(id).await {
        Ok(order) => ok(order),
        Err(e) => {
            error!(event = "order.load.failed", exception = %e, order_id = id);
            internal_error()
        }
    }
}
```

- `#[instrument(err)]` emits an `ERROR` event at every instrumented function it is put on. Use `err` only on the boundary function, not on each layer, or the same failure is logged several times.
- `Debug` (`?e`) does not in general print the `source()` chain; it depends on the error type's own `Debug` impl. To record the causes, walk `std::error::Error::source()` yourself and put the messages in one field (for example `exception_chain`). `anyhow`'s `{:#}` prints the chain but `anyhow` is not in the research (UNVERIFIED).
- Do not log and then return the same error (`error!(..); return Err(e)`).

## Compile-time level limits (tracing Cargo features)

Runtime filtering (`EnvFilter`, `LOG_LEVEL`) stays the normal control. The `tracing` crate can also remove verbose call sites at build time with Cargo features:

```toml
# binary Cargo.toml
tracing = { version = "0.1", features = ["max_level_debug", "release_max_level_info"] } # feature names: UNVERIFIED
```

- `max_level_*` caps the level in every build; `release_max_level_*` caps it only when `debug_assertions` are off. Names follow the pattern `max_level_{off,error,warn,info,debug,trace}`. UNVERIFIED against the `tracing` version in use (the research pins only `tracing-subscriber` and `tracing-attributes`); check docs.rs.
- A compiled-out level cannot be turned on again by `LOG_LEVEL`. With `release_max_level_info`, `LOG_LEVEL=debug` has no effect in a release build, which conflicts with the rule that tests and incident debugging run at DEBUG. Set it only in the binary, never in a library (features are additive and apply to the whole build), and only if production never needs DEBUG without a rebuild. Otherwise leave the features off.
