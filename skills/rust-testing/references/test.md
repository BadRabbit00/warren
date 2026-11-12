# Rust test rules

Source: leonardomso/rust-skills `rules/test-*` (MIT, © 2025 Leonardo Maldonado), adapted. The ids are ours; the source id is in brackets.

Contents:

- [R-RST-LOCATION](#r-rst-location)
- [R-RST-NAMES](#r-rst-names)
- [R-RST-AAA](#r-rst-aaa)
- [R-RST-TOKIO-TEST](#r-rst-tokio-test)
- [R-RST-FAKE-BOUNDARY](#r-rst-fake-boundary)
- [R-RST-MOCKALL](#r-rst-mockall)
- [R-RST-RAII](#r-rst-raii)
- [R-RST-PROPERTY](#r-rst-property)
- [R-RST-SNAPSHOT](#r-rst-snapshot)
- [R-RST-SHOULD-PANIC](#r-rst-should-panic)
- [R-RST-DOCTEST](#r-rst-doctest)
- [R-RST-BENCH](#r-rst-bench)
- [R-RST-LOOM](#r-rst-loom)

## R-RST-LOCATION

[test-integration-dir; replaces test-cfg-test-module and test-use-super]

Our layout puts tests in `<crate>/tests/`, never in `#[cfg(test)]` modules in `src/`. Each file in `tests/` is its own crate that sees only the public API, so tests cannot depend on internals and refactors inside the crate do not break them. A function that is too private to test through the API but too risky to leave untested is usually a separate unit: move it to its own module or crate with a small public interface and test that.

Structure:

```text
my_crate/
├── Cargo.toml
├── src/lib.rs
└── tests/
    ├── common/mod.rs      # shared helpers, not a test binary
    ├── orders.rs          # one test binary
    └── billing.rs
```

Each file in `tests/` links separately. For many files, one binary with modules is faster to build: `tests/it/main.rs` with `mod orders; mod billing; mod common;`.

Bad:
```rust
// src/orders.rs
fn total(items: &[Item]) -> u64 { items.iter().map(|i| i.cents).sum() }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn total_sums_items() {
        assert_eq!(total(&[Item { cents: 5 }, Item { cents: 7 }]), 12);
    }
}
```
Why: the test lives in `src/`, reaches private items with `use super::*`, and breaks on every internal rename.

Good:
```rust
// tests/orders.rs
mod common;

use my_crate::{Order, OrderError};

#[test]
fn order_total_is_the_sum_of_its_items() {
    let order = common::order_with_prices(&[5, 7]);

    assert_eq!(order.total_cents(), 12);
}

#[test]
fn empty_order_is_rejected() {
    let result = Order::new(vec![]);

    assert!(matches!(result, Err(OrderError::Empty)));
}
```

```rust
// tests/common/mod.rs
use my_crate::{Item, Order};

pub fn order_with_prices(prices: &[u64]) -> Order {
    let items = prices.iter().map(|&cents| Item { cents }).collect();
    Order::new(items).expect("fixture: non-empty order")
}
```

Notes: doctests are the one exception, they sit in `///` and run against the public API. A binary-only crate exposes no API to `tests/`; put the logic in a `lib.rs` and keep `main.rs` thin. Run: `cargo test`, `cargo test --test orders`, `cargo test --test orders paid`.

## R-RST-NAMES

[test-descriptive-names]

A test name appears in the failure output and is the only documentation of the behaviour that failed. State the behaviour: subject, condition, result. A `test_` prefix adds nothing.

Bad:
```rust
#[test]
fn test1() { /* ... */ }

#[test]
fn test_parse() { /* what about parse? */ }

#[test]
fn it_works() { /* ... */ }
```
Why: "test test_parse ... FAILED" does not say what broke.

Good:
```rust
#[test]
fn parse_rejects_empty_input() { /* ... */ }

#[test]
fn expired_token_is_rejected() { /* ... */ }

#[test]
fn empty_cart_has_zero_total() { /* ... */ }

#[test]
fn adding_an_item_increases_the_cart_total() { /* ... */ }
```

Patterns that read well: `<subject>_<condition>_<result>`, `<scenario>_<expectation>`. Group by file and `mod` inside `tests/`, so the output reads `orders::paid_order_cannot_be_cancelled`. Edge cases get their own name (`handles_max_length_input`, `rejects_negative_quantity`).

## R-RST-AAA

[test-arrange-act-assert]

A test has three steps in order: arrange the data, act once, assert the outcome. One test checks one behaviour. Several behaviours in one test hide which of them failed and stop at the first failure.

Bad:
```rust
#[test]
fn user() {
    assert_eq!(User::new("alice", "alice@example.com").unwrap().name(), "alice");
    assert!(User::new("", "email@example.com").is_err());
    let u = User::new("bob", "bob@example.com").unwrap();
    assert!(u.validate());
    assert_eq!(u.email(), "bob@example.com");
}
```
Why: four behaviours, no names for them, the first failure hides the rest.

Good:
```rust
use my_crate::{User, UserError};

#[test]
fn new_user_keeps_the_given_name() {
    let (name, email) = ("alice", "alice@example.com");

    let user = User::new(name, email).expect("valid input");

    assert_eq!(user.name(), "alice");
}

#[test]
fn user_creation_fails_with_empty_name() {
    let result = User::new("", "email@example.com");

    assert!(matches!(result, Err(UserError::EmptyName)));
}
```

Use `// Arrange`, `// Act`, `// Assert` comments only when the test is long enough to need them; a blank line between the steps is usually enough. Money in examples is integer cents, never `f64` compared with `assert_eq!`.

## R-RST-TOKIO-TEST

[test-tokio-async]

`#[tokio::test]` builds a runtime for the test and runs the async body on it. Do not hand-roll `Runtime::new().block_on`. Two corrections to common belief: the default flavour of `#[tokio::test]` is `current_thread` (not multi-thread), and `start_paused` needs tokio's `test-util` feature in dev-dependencies.

Bad:
```rust
#[test]
fn fetch_works() {
    let rt = tokio::runtime::Runtime::new().expect("runtime");
    rt.block_on(async {
        let result = fetch_data().await;
        assert!(result.is_ok());
    });
}

#[tokio::test]
async fn timeout_triggers() {
    // really waits 5 minutes
    let r = tokio::time::timeout(std::time::Duration::from_secs(300), never_completes()).await;
    assert!(r.is_err());
}
```
Why: boilerplate in the first; the second is slow and breaks R-TEST-DETERMINISM.

Good:
```rust
use std::time::Duration;

#[tokio::test]
async fn fetch_succeeds_for_known_user() {
    let result = fetch_user(1).await;

    assert!(result.is_ok());
}

#[tokio::test(start_paused = true)]
async fn operation_that_never_completes_times_out() {
    // virtual time: the 5-minute timeout elapses at once
    let result = tokio::time::timeout(Duration::from_secs(300), never_completes()).await;

    assert!(result.is_err());
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn works_across_worker_threads() {
    let (a, b) = tokio::join!(fetch_user(1), fetch_user(2));

    assert!(a.is_ok() && b.is_ok());
}
```

```toml
[dev-dependencies]
tokio = { version = "1", features = ["macros", "rt-multi-thread", "test-util"] }
```

`start_paused` needs the `current_thread` flavour (the default). Waiting for a spawned task: await its `JoinHandle` or a channel, never `sleep`.

## R-RST-FAKE-BOUNDARY

[test-mock-traits]

Put a trait where the system meets something you cannot run for real in a test: an external HTTP API, an LLM, a mail or payment provider, the clock. Inject the implementation as a generic parameter. The database is not such a boundary: repository and integration tests use the real DBMS (R-TEST-REAL-DB). A service-level test may use a hand-written fake repository for scenarios, next to a few tests on the real DB (R-TEST-LAYER).

Traits use native `async fn` (stable); do not add `async_trait`. A trait with native `async fn` is not dyn-compatible, so inject through a generic (`PaymentService<C: PaymentGateway>`). If you need runtime selection, use an enum of the implementations.

Bad:
```rust
pub struct PaymentService {
    http: reqwest::Client, // real network in every test
}

impl PaymentService {
    pub async fn charge(&self, cents: u64) -> Result<Receipt, PaymentError> {
        let resp = self.http.post("https://pay.example/charge").send().await?;
        /* ... */
    }
}
```
Why: tests need the network, are slow and flaky, and cannot produce a timeout on demand.

Good:
```rust
// src/payment.rs
pub trait PaymentGateway {
    async fn charge(&self, cents: u64) -> Result<Receipt, GatewayError>;
}

pub struct PaymentService<G: PaymentGateway> {
    gateway: G,
}

impl<G: PaymentGateway> PaymentService<G> {
    pub fn new(gateway: G) -> Self {
        Self { gateway }
    }

    pub async fn charge(&self, cents: u64) -> Result<Receipt, PaymentError> {
        self.gateway.charge(cents).await.map_err(PaymentError::Gateway)
    }
}
```

```rust
// tests/payment.rs: a hand-written fake that always fails
use my_crate::{GatewayError, PaymentError, PaymentGateway, PaymentService, Receipt};

struct TimingOutGateway;

impl PaymentGateway for TimingOutGateway {
    async fn charge(&self, _cents: u64) -> Result<Receipt, GatewayError> {
        Err(GatewayError::Timeout)
    }
}

#[tokio::test]
async fn gateway_timeout_is_reported_as_payment_error() {
    let service = PaymentService::new(TimingOutGateway);

    let result = service.charge(500).await;

    assert!(matches!(result, Err(PaymentError::Gateway(GatewayError::Timeout))));
}
```

If the future must be `Send` (spawned on a multi-thread runtime), declare the method as `fn charge(&self, cents: u64) -> impl Future<Output = Result<Receipt, GatewayError>> + Send;`.

## R-RST-MOCKALL

[test-mockall-mocking]

Use a hand-written fake when answers are fixed. Use `mockall` when a boundary needs per-test answers, error injection, or a check that a side effect happened. One `mockall` version for the whole workspace; at the time of writing the latest stable release is 0.15 (check crates.io when adding it). It is a new dev-dependency: name it in the task.

Corrections to the source: (1) `#[cfg_attr(test, automock)]` on a trait in `src/` is not seen by `tests/`, because `cfg(test)` is off when the library is built for an integration test; declare the mock with `mock!` in `tests/common/mod.rs` instead. (2) A second `.returning(...)` replaces the first; different results per call are separate expectations. (3) Native `async fn` works with `mock!`, no `async_trait`. (4) Expect call count or order only when the call is the outcome, see R-TEST-BEHAVIOUR.

Bad:
```rust
#[tokio::test]
async fn charge_calls_gateway() {
    let mut gateway = MockPaymentGateway::new();
    gateway.expect_charge().returning(|_| Ok(Receipt::default()));
    // and the same mock now used for "first call fails, second succeeds":
    gateway.expect_charge().returning(|_| Err(GatewayError::Timeout)); // never reached
}
```
Why: the first expectation matches every call; the second is dead code.

Good:
```rust
// tests/common/mod.rs
use mockall::mock;
use my_crate::{GatewayError, PaymentGateway, Receipt};

mock! {
    pub Gateway {}
    impl PaymentGateway for Gateway {
        async fn charge(&self, cents: u64) -> Result<Receipt, GatewayError>;
    }
}
```

```rust
// tests/payment.rs
mod common;

use common::MockGateway;
use mockall::{predicate::eq, Sequence};
use my_crate::{GatewayError, PaymentService, Receipt};

#[tokio::test]
async fn charge_is_retried_once_after_a_timeout() {
    let mut seq = Sequence::new();
    let mut gateway = MockGateway::new();
    gateway.expect_charge().with(eq(500)).times(1).in_sequence(&mut seq)
        .returning(|_| Err(GatewayError::Timeout));
    gateway.expect_charge().with(eq(500)).times(1).in_sequence(&mut seq)
        .returning(|_| Ok(Receipt::default()));
    let service = PaymentService::new(gateway);

    let result = service.charge_with_retry(500).await;

    assert!(result.is_ok());
    // expectations are verified when `gateway` is dropped
}
```

Predicates: `eq(x)`, `function(|v| ...)`, `.withf(|a, b| ...)` for several arguments. `times(1)`, `times(3..)` for counts.

## R-RST-RAII

[test-fixture-raii]

Cleanup placed after the assertions does not run when the test panics. Make the resource a value whose `Drop` cleans up. Our additions: no fixed paths (parallel tests collide); no environment mutation (in edition 2024 `std::env::set_var` is `unsafe` because it races with other threads, and tests run in parallel) so read configuration through a parameter or a config struct; database isolation is a transaction that is dropped without commit.

Bad:
```rust
#[test]
fn processes_a_file() {
    let path = "/tmp/test_file.txt";
    std::fs::write(path, "data").expect("write");

    let result = process_file(path);

    std::fs::remove_file(path).expect("remove"); // skipped if process_file panics
    assert!(result.is_ok());
}
```
Why: a panic leaves the file behind, and two parallel tests share the path.

Good:
```rust
use tempfile::NamedTempFile;

#[test]
fn processes_a_file() {
    let file = NamedTempFile::new().expect("temp file");
    std::fs::write(file.path(), "data").expect("write");

    let result = process_file(file.path());

    assert!(result.is_ok()); // the file is removed when `file` drops, panic or not
}

#[tokio::test]
async fn cancel_marks_order_cancelled() -> Result<(), sqlx::Error> {
    let pool = common::test_pool().await; // real PostgreSQL, schema from migrations
    let mut tx = pool.begin().await?;
    let id = common::insert_new_order(&mut *tx).await?;

    my_crate::orders::cancel(&mut *tx, id).await?;

    let status: String = sqlx::query_scalar("SELECT status FROM orders WHERE id = $1")
        .bind(id)
        .fetch_one(&mut *tx)
        .await?;
    assert_eq!(status, "cancelled");
    Ok(()) // `tx` is dropped without commit: sqlx rolls it back
}
```

`tempfile::TempDir` for a directory. A custom guard is a struct with a `Drop` impl; keep `drop` infallible (no `unwrap`).

## R-RST-PROPERTY

[test-proptest-properties]

A property test states a law and lets `proptest` search for a counter-example, then shrinks it. Typical laws: round trip (`decode(encode(x)) == x`), idempotence (`f(f(x)) == f(x)`), ordering, an invariant after an operation. The law must not follow from the generator itself (that is R-RST-NOT-TAUTOLOGICAL). Failing seeds are saved in `proptest-regressions/`; commit them so the case is replayed on every run (R-TEST-DETERMINISM). New dev-dependency: `proptest = "1"`; `proptest-derive` for `#[derive(Arbitrary)]` is a second one, avoid unless needed.

Bad:
```rust
proptest! {
    #[test]
    fn user_age_is_below_150(user in user_strategy()) {
        // the strategy is `0..120u8`: the assertion cannot fail
        assert!(user.age < 150);
    }
}
```
Why: it restates the generator and finds nothing.

Good:
```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn sorting_twice_changes_nothing(mut v in prop::collection::vec(any::<i32>(), 0..100)) {
        v.sort();
        let once = v.clone();
        v.sort();
        prop_assert_eq!(v, once);
    }

    #[test]
    fn config_survives_a_round_trip(config in valid_config_strategy()) {
        let text = config.to_string();
        let parsed = Config::parse(&text).expect("own output parses");
        prop_assert_eq!(parsed, config);
    }
}

fn valid_config_strategy() -> impl Strategy<Value = Config> {
    ("[a-z]{1,12}", 1u16..=65535).prop_map(|(host, port)| Config { host, port })
}
```

| Law | Form |
|---|---|
| Round trip | `decode(encode(x)) == x` |
| Idempotence | `f(f(x)) == f(x)` |
| Commutativity | `f(a, b) == f(b, a)` |
| Invariant | `len(push(v, x)) == len(v) + 1` |

More cases: `#![proptest_config(ProptestConfig { cases: 1000, ..ProptestConfig::default() })]` inside `proptest!`. Use `prop_assert!` / `prop_assert_eq!` so shrinking works.

## R-RST-SNAPSHOT

[test-snapshot-testing]

Hand-written `assert_eq!` against a long string or JSON is brittle. `insta` stores an approved snapshot in a file, diffs against it, and `cargo insta review` accepts intentional changes. Snapshots are committed and reviewed like code. For tests in `tests/`, files go to `tests/snapshots/`. New dev-dependency: `insta` with the features you use (`json`, `yaml`, `redactions`).

Corrections to the source: the rendered message is a string, so use `assert_snapshot!(err.to_string())`, not `assert_debug_snapshot!` of the error; `assert_json_snapshot!` needs the `json` feature; ids and timestamps must be redacted or the snapshot differs on each run.

Bad:
```rust
#[test]
fn config_serialises() {
    let json = serde_json::to_string_pretty(&Config::default()).expect("serialise");
    assert_eq!(json, "{\n  \"timeout\": 30,\n  \"retries\": 3\n}");
}
```
Why: hard to read, hard to update, one escape error from a false failure.

Good:
```rust
use insta::{assert_json_snapshot, assert_snapshot};

#[test]
fn not_found_error_message() {
    let err = AppError::NotFound { id: 42 };

    assert_snapshot!(err.to_string());
}

#[test]
fn order_response_shape() {
    let body = order_response_fixture();

    assert_json_snapshot!(body, { ".id" => "[uuid]", ".created_at" => "[timestamp]" });
}
```

```toml
[dev-dependencies]
insta = { version = "1", features = ["json", "redactions"] }
```

Flow: `cargo test` writes `.snap.new`, `cargo insta review` accepts, commit the `.snap` files. CI: `INSTA_UPDATE=no cargo test` so a new or changed snapshot fails.

| Output | Use |
|---|---|
| Short value (`true`, `42`) | `assert_eq!` |
| Multi-line text, error message | `assert_snapshot!` |
| Serialisable structure | `assert_json_snapshot!` / `assert_yaml_snapshot!` |
| Any `Debug` value | `assert_debug_snapshot!` |

## R-RST-SHOULD-PANIC

[test-should-panic]

Under the panic policy a bug (broken invariant, impossible state) panics with a message; an expected failure returns `Result`. `#[should_panic]` tests the first kind, and `expected = "..."` is mandatory: without it any unrelated panic makes the test pass. Expected failures are tested by matching the error value. Corrections to the source: a `#[should_panic]` test cannot return `Result` (the compiler rejects it); do not test `std` panics such as `v[100]`.

Bad:
```rust
#[test]
#[should_panic] // any panic passes, including a typo in the setup
fn bad_input_panics() {
    parse_config("invalid"); // expected failure: should be Err, not a panic
}
```
Why: it enforces the wrong contract and passes for the wrong reason.

Good:
```rust
use my_crate::{parse_config, ConfigError, NonEmpty};

#[test]
#[should_panic(expected = "NonEmpty requires at least one item")]
fn non_empty_rejects_an_empty_vec() {
    NonEmpty::new(Vec::<i32>::new()); // constructor asserts: an empty vec is a caller bug
}

#[test]
fn invalid_config_returns_a_syntax_error() {
    let result = parse_config("invalid");

    assert!(matches!(result, Err(ConfigError::Syntax { .. })));
}
```

## R-RST-DOCTEST

[test-doctest-examples]

An example in `///` compiles and runs under `cargo test`, so documentation cannot drift from the API. Doctests are the only tests that sit next to the code; they use the public API only. They exist for library crates (a binary crate has none). Prose and structure of doc comments: skill `rust-docs`.

Corrections to the source: examples return `Result` and use `?` with a hidden `Ok::<(), E>(())` instead of `unwrap()`; the documented functions themselves do not `unwrap` input. Prefer `no_run` to `ignore` (`ignore` is never compiled).

Bad:
```rust
/// Parses a number.
///
/// Example:
/// let n = parse("42");
/// assert_eq!(n, 42);
pub fn parse(s: &str) -> i32 {
    s.parse().unwrap()
}
```
Why: the example is plain text, nothing runs it, and the function panics on user input.

Good:
```rust
/// Parses a decimal number.
///
/// # Examples
///
/// ```
/// use my_crate::parse;
///
/// assert_eq!(parse("42")?, 42);
/// # Ok::<(), my_crate::ParseError>(())
/// ```
///
/// # Errors
///
/// Returns [`ParseError`] when `s` is not a number:
///
/// ```
/// use my_crate::parse;
///
/// assert!(parse("forty-two").is_err());
/// ```
pub fn parse(s: &str) -> Result<i32, ParseError> {
    s.parse().map_err(|_| ParseError)
}
```

Variants: `no_run` compiles but does not run (starts a server); `compile_fail` asserts a type does not compile (a type that must not be `Clone`); lines starting with `# ` are hidden from the rendered docs. Run: `cargo test --doc`.

## R-RST-BENCH

[test-criterion-bench]

`criterion` gives statistical benchmarks (warm-up, outliers, comparison with a saved baseline); `Instant::now()` loops do not. Benchmarks live in `benches/`, are not CI gates, and answer one question: was it faster on this machine. Measure before you optimise; profiler workflow is in skills `profiling` and `rust-perf`. New dev-dependency: `criterion` (0.8 at the time of writing; check crates.io). Corrections to the source: use `std::hint::black_box`, the `criterion::black_box` re-export is deprecated; the parameterised example must import `BenchmarkId`.

Bad:
```rust
#[test]
fn fib_is_fast() {
    let start = std::time::Instant::now();
    for _ in 0..1000 { fibonacci(20); }
    assert!(start.elapsed().as_millis() < 100); // flaky, optimised away
}
```
Why: a timing assert in a test is flaky, and the unused result may be removed by the optimiser.

Good:
```toml
[dev-dependencies]
criterion = "0.8"

[[bench]]
name = "fib"
harness = false
```

```rust
// benches/fib.rs
use std::hint::black_box;

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use my_crate::{fibonacci, parse};

fn bench_fib(c: &mut Criterion) {
    c.bench_function("fib 20", |b| b.iter(|| fibonacci(black_box(20))));
}

fn bench_parse(c: &mut Criterion) {
    let mut group = c.benchmark_group("parse");
    for size in [100usize, 1_000, 10_000] {
        let input = "x".repeat(size);
        group.throughput(Throughput::Bytes(size as u64));
        group.bench_with_input(BenchmarkId::from_parameter(size), &input, |b, input| {
            b.iter(|| parse(black_box(input)))
        });
    }
    group.finish();
}

criterion_group!(benches, bench_fib, bench_parse);
criterion_main!(benches);
```

Run: `cargo bench`, `cargo bench -- fib`, save and compare: `cargo bench -- --save-baseline main`, `cargo bench -- --baseline main`.

## R-RST-LOOM

[test-loom-concurrency]

Stress tests run a race a million times and still may never hit the bad interleaving. `loom` replaces the std synchronisation types with instrumented ones and runs the model under every schedule the memory model allows. Use it for lock-free structures and hand-written synchronisation; code that only uses `tokio::sync` or a `Mutex` does not need it. It works on stable. Loom is a dependency of the crate under `cfg(loom)`, not a dev-dependency, because `src/` imports it: this needs a cargo change, so state it in the task. Declaring the `loom` cfg is a lint-config change, owned by `ci-engineer`.

Corrections to the source: loom's `AtomicBool::new` is not `const`, so the type's constructor cannot be `const fn` under `cfg(loom)` (the compiler rejects it); the test in `tests/` must import from the crate by name, not `super`.

Bad:
```rust
#[test]
fn stress_flag() {
    let flag = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    for _ in 0..1_000_000 {
        let flag = std::sync::Arc::clone(&flag);
        std::thread::spawn(move || flag.store(true, std::sync::atomic::Ordering::Relaxed));
    }
    // may pass a billion times; proves nothing
}
```
Why: the OS scheduler may never produce the interleaving that breaks the code.

Good:
```rust
// src/flag.rs
#[cfg(loom)]
use loom::sync::atomic::{AtomicBool, Ordering};
#[cfg(not(loom))]
use std::sync::atomic::{AtomicBool, Ordering};

pub struct Flag(AtomicBool);

impl Flag {
    pub fn new() -> Self {                 // not `const fn`: loom's AtomicBool::new is not const
        Self(AtomicBool::new(false))
    }

    pub fn set(&self) {
        self.0.store(true, Ordering::Release);
    }

    pub fn is_set(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
}

impl Default for Flag {
    fn default() -> Self {
        Self::new()
    }
}
```

```rust
// tests/loom_flag.rs
#![cfg(loom)]

use loom::sync::Arc;
use my_crate::Flag;

#[test]
fn flag_is_set_after_the_writer_joins() {
    loom::model(|| {
        let flag = Arc::new(Flag::new());
        let writer = {
            let flag = Arc::clone(&flag);
            loom::thread::spawn(move || flag.set())
        };

        writer.join().expect("writer thread");

        assert!(flag.is_set());
    });
}
```

```toml
[target.'cfg(loom)'.dependencies]
loom = "0.7"

[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(loom)'] }
```

Run: `RUSTFLAGS="--cfg loom" cargo test --test loom_flag --release`. Keep each model small: the number of schedules grows quickly with atomic operations and threads. Loom checks the memory model, not logic errors unrelated to concurrency.
