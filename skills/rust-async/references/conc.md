# conc rules in full

Adapted from leonardomso/rust-skills `conc-*` (see ../NOTICE.md). Stable Rust, edition 2024. `rayon` and `loom` are dependencies that need approval; the std-only examples compile with rustc 1.99.

## R-RSA-ATOMIC-ORDERING — pick the ordering you can justify

Ordering decides which other memory operations are visible together with the atomic one. A wrong weak ordering is a data race the compiler does not catch, so weaken only with an argument. Rewritten: the source's headline "use the weakest correct ordering" and its "Bad" example (a `static mut` read next to a `SeqCst` flag) mixed two issues; the practical advice is below.

Bad:
```rust
use std::sync::atomic::{AtomicU64, Ordering};

static HITS: AtomicU64 = AtomicU64::new(0);

fn record() {
    HITS.fetch_add(1, Ordering::SeqCst); // the strongest ordering for an independent counter
}
```
Why: not wrong, but it says "these operations are ordered with all others", which is not what a counter needs, and it hides the places where ordering does matter.

Good:
```rust
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};

static HITS: AtomicU64 = AtomicU64::new(0);
static READY: AtomicBool = AtomicBool::new(false);
static VALUE: AtomicU64 = AtomicU64::new(0);

fn record() {
    HITS.fetch_add(1, Ordering::Relaxed); // independent counter
}

fn publish(value: u64) {
    VALUE.store(value, Ordering::Relaxed);
    READY.store(true, Ordering::Release); // everything before this is visible to an Acquire reader
}

fn read() -> Option<u64> {
    if READY.load(Ordering::Acquire) {
        Some(VALUE.load(Ordering::Relaxed))
    } else {
        None
    }
}
```

| Ordering | Use when |
|---|---|
| `Relaxed` | the atomic is the whole story: counters, statistics, ids |
| `Release` (store) with `Acquire` (load) | publishing data: write the data, then set the flag |
| `AcqRel` | read-modify-write that both reads a published value and publishes (`compare_exchange`) |
| `SeqCst` | several atomics must agree on one global order, or you cannot prove a weaker one |
| none of them | more than one value must stay consistent: use a `Mutex` |

Verification with `loom` (dev-dependency, run with `RUSTFLAGS="--cfg loom"`): the library swaps `std::sync::atomic` for `loom::sync::atomic` under `cfg(loom)`, the model test sits in the crate's test directory, and the `cfg` is declared in `[lints.rust] unexpected_cfgs` by the project's config owner. Keep lock-free code rare; a `Mutex` is the default.

## R-RSA-RAYON — data parallelism with rayon

`rayon` (dependency) turns `.iter()` into `.par_iter()` for CPU-bound work and balances load by work stealing. It does not help I/O, and for small inputs the setup cost can outweigh the gain: measure.

Bad:
```rust
fn normalize(data: &mut [f64]) {
    let max = data.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    data.iter_mut().for_each(|x| *x /= max); // one core for a large, CPU-bound array
}
```
Why: wastes the other cores on an embarrassingly parallel loop.

Good:
```rust
use rayon::prelude::*;

fn normalize(data: &mut [f64]) {
    let max = data.par_iter().copied().reduce(|| f64::NEG_INFINITY, f64::max);
    data.par_iter_mut().for_each(|x| *x /= max);
}

fn sort_large(data: &mut [f64]) {
    data.par_sort_unstable_by(f64::total_cmp); // total order, no unwrap on NaN
}
```
In async code never run rayon on a worker thread: call it from `spawn_blocking`, or `rayon::spawn` and send the result through a `oneshot`. Fixed from the source: `partial_cmp(..).unwrap()` in the sort (panics on NaN) became `total_cmp`, and the claim that rayon needs `Mutex` or atomics "because it does not prevent data races" is wrong: closures must be `Send + Sync`, so the compiler rejects unsynchronized shared mutation.

| Concern | Guidance |
|---|---|
| I/O-bound | async, not rayon |
| Few items or cheap items | stay sequential; measure |
| Granularity | `with_min_len` / `with_max_len` |
| Ordering | `collect()` on indexed iterators keeps order |

## R-RSA-SCOPED-THREADS — borrow across threads with thread::scope

`std::thread::scope` (stable since 1.63) joins every spawned thread before it returns, so the threads may borrow local data: no `Arc`, no `clone`.

Bad:
```rust
fn parallel_sum(data: &[i64]) -> i64 {
    let data = std::sync::Arc::new(data.to_vec()); // copies the whole slice only to share it
    let mid = data.len() / 2;
    let (a, b) = (std::sync::Arc::clone(&data), std::sync::Arc::clone(&data));
    let h1 = std::thread::spawn(move || a[..mid].iter().sum::<i64>());
    let h2 = std::thread::spawn(move || b[mid..].iter().sum::<i64>());
    h1.join().expect("sum thread panicked") + h2.join().expect("sum thread panicked")
}
```
Why: heap copy and reference counting for data that outlives the work anyway.

Good:
```rust
fn parallel_sum(data: &[i64]) -> i64 {
    let (left, right) = data.split_at(data.len() / 2);
    std::thread::scope(|s| {
        let a = s.spawn(|| left.iter().sum::<i64>());
        let b = s.spawn(|| right.iter().sum::<i64>());
        a.join().expect("sum thread panicked") + b.join().expect("sum thread panicked")
    })
}

fn parallel_fill(left: &mut [u8], right: &mut [u8]) {
    std::thread::scope(|s| {
        s.spawn(|| left.fill(0xAA));
        s.spawn(|| right.fill(0xBB));
    }); // both writes are done here
}
```
A panic in a child is a bug in our code, so `join().expect("...")` is the right handling (R-RS-PANICS covers input; this is not input). If a child is not joined by hand and panics, `scope` panics after joining the rest. The scope blocks the calling thread: inside async code call it from `spawn_blocking`. For a homogeneous collection use rayon instead (R-RSA-RAYON).

## R-RSA-THREAD-LOCAL — thread_local! instead of static mut

`static mut` needs `unsafe` at each use, and references to it are denied by the `static_mut_refs` lint in edition 2024 (a deny-by-default lint, not a hard error as the source said). `thread_local!` gives each thread its own value through a safe API.

Bad:
```rust
static mut BUFFER: Vec<u8> = Vec::new();

fn append(data: &[u8]) {
    // SAFETY: none can be given; two threads calling this race
    unsafe { (*(&raw mut BUFFER)).extend_from_slice(data) }
}
```
Why: undefined behavior as soon as two threads call it.

Good:
```rust
use std::cell::{Cell, RefCell};

thread_local! {
    // `const { .. }` initializers avoid lazy-init bookkeeping
    static BUFFER: RefCell<Vec<u8>> = const { RefCell::new(Vec::new()) };
    static CALLS: Cell<u32> = const { Cell::new(0) };
}

fn append(data: &[u8]) {
    BUFFER.with_borrow_mut(|buf| buf.extend_from_slice(data));
    CALLS.with(|c| c.set(c.get() + 1));
}

fn take() -> Vec<u8> {
    BUFFER.with_borrow_mut(std::mem::take)
}
```
Good uses: scratch buffers and reusable allocations per thread. Not for state that belongs to an async task: a task can resume on another worker thread and would see a different value. Read-only globals are a plain `static`; shared mutable ones are a `Mutex` or an atomic.
