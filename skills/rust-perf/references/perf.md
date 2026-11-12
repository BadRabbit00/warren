# Performance: method, iterators, collections, IO, release profile

Source prefix `perf-` (leonardomso), with Microsoft M-HOTPATH and M-FAST-HASHER merged in. One-line forms are in `../SKILL.md`.

## R-RSPERF-MEASURE-FIRST — measure before you change

Why: intuition about where time goes is often wrong; effort spent on a cold path is lost, and an unmeasured change can be slower. Algorithm and data-structure changes usually beat low-level tuning.

Workflow: write the correct code, benchmark the hot path, profile under realistic load, find the real bottleneck, change one thing, measure again. Commands for profilers (cargo flamegraph, perf, DHAT, py-spy for neighbours) are in skill `profiling`, `references/rust.md`; do not copy them here.

Bad:
```rust
// "This clone must be slow", while the profile says 95% is in expensive_computation.
#[inline(always)]
fn rarely_called() { /* runs once at startup */ }
```
Why: the change targets a guess; nothing was measured before or after.

Good:
```rust
// Profile first: expensive_computation is 95% of the time, the clone 1%.
// Only the hot part is changed, and the benchmark is run again afterwards.
fn process(data: &[Item]) -> Vec<Output> {
    data.iter().map(expensive_computation).collect()
}
```

What a profile usually shows, and the rule to try:

| Finding | Try |
|---|---|
| Map operations dominate (internal keys) | R-RSPERF-HASHER |
| Allocation in a loop | R-RSPERF-REUSE-BUFFER, R-RSPERF-CAPACITY |
| `memcpy` / clone in a hot path | borrow, `Cow` (R-RSPERF-ZERO-COPY) |
| Bounds checks visible | R-RSPERF-ITER-OVER-INDEX |
| Lock contention | smaller critical section, `RwLock`, partitioned data |
| Futures large in `memcpy` | R-RSPERF-FUTURE-SIZE |

Lock choice (contestable): `parking_lot::Mutex` is often recommended over `std::sync::Mutex`. Since Rust 1.62 the std mutex is futex-based and small, so the advantage is workload-dependent. Measure first; adding the crate is a new dependency.

## R-RSPERF-BENCH-BLACK-BOX — keep the benchmarked work alive

Why: the optimiser removes computations whose result is unused and folds constants. A benchmark then measures nothing.

Bad:
```rust
fn bench(c: &mut Criterion) {
    c.bench_function("compute", |b| {
        b.iter(|| {
            let _ = expensive_computation(42); // constant input, unused result
        });
    });
}
```
Why: the call can be precomputed or deleted; the time reported is the loop, not the work.

Good:
```rust
use std::hint::black_box;

fn bench(c: &mut Criterion) {
    let data = generate_test_data(1000); // setup outside iter: not measured
    c.bench_function("process", |b| {
        b.iter(|| black_box(process(black_box(&data))));
    });
}
```
Why: `black_box` on the input stops constant folding, on the result stops dead-code removal. `black_box` inside a loop around `()` does nothing; wrap the value. `std::hint::black_box` is in std since 1.66. Benchmarks go in `benches/` (the bench harness, criterion or divan, is a dev-dependency: say so when adding it). Where possible record CPU time over all threads as well as wall time.

## R-RSPERF-ITER-LAZY — one chain, one collect

Why: every `collect()` allocates and adds a pass; lazy chains run in one pass and can stop early.

Bad:
```rust
fn process_users(users: Vec<User>) -> Vec<String> {
    let active: Vec<_> = users.into_iter().filter(|u| u.is_active).collect();
    let verified: Vec<_> = active.into_iter().filter(|u| u.is_verified).collect();
    verified.into_iter().map(|u| u.name).collect()
}

fn count_valid(items: &[Item]) -> usize {
    items.iter().filter(|i| i.is_valid()).collect::<Vec<_>>().len()
}
```
Why: three allocations and three passes; the second function allocates just to count.

Good:
```rust
fn process_users(users: Vec<User>) -> Vec<String> {
    users
        .into_iter()
        .filter(|u| u.is_active && u.is_verified)
        .map(|u| u.name)
        .collect()
}

fn count_valid(items: &[Item]) -> usize {
    items.iter().filter(|i| i.is_valid()).count()
}
```
Why: one pass, one allocation (or none). Collect in the middle only when you iterate the result more than once or need a concrete collection (sorting). Short-circuit with `find` / `any` instead of collecting and taking `first()`.

## R-RSPERF-ITER-OVER-INDEX — iterators and patterns instead of indices

Why: indexing is bounds-checked on every access and can block vectorisation. Iterators, `windows`, `chunks_exact` and slice patterns give the compiler the length once. Elimination is likely, not guaranteed: for a hot function check the assembly (`cargo asm`, skill `profiling`).

Bad:
```rust
fn dot_product(a: &[f64], b: &[f64]) -> f64 {
    let mut sum = 0.0;
    for i in 0..a.len().min(b.len()) {
        sum += a[i] * b[i];
    }
    sum
}

fn smooth(data: &mut [u8]) {
    for i in 1..data.len() - 1 {
        data[i] = ((u16::from(data[i - 1]) + u16::from(data[i]) + u16::from(data[i + 1])) / 3) as u8;
    }
}
```
Why: two or three checks per iteration, and `data.len() - 1` underflows on an empty slice.

Good:
```rust
fn dot_product(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

fn smoothed(data: &[u8]) -> Vec<u8> {
    data.windows(3)
        .map(|w| ((u16::from(w[0]) + u16::from(w[1]) + u16::from(w[2])) / 3) as u8)
        .collect()
}

fn parse_header(data: &[u8]) -> Option<(u8, u8, u16, &[u8])> {
    // One length check for all four bytes.
    let [version, flags, lo, hi, rest @ ..] = data else {
        return None;
    };
    Some((*version, *flags, u16::from_le_bytes([*lo, *hi]), rest))
}
```
Why: no per-access checks; the slice pattern also removes the panic on short input (R-RS-PANICS).

Indices stay right when you need the position (`iter().enumerate()`) or access is non-sequential; use `get(i)` then. `get_unchecked` is a last resort: only with a `// SAFETY:` comment, an assertion that proves the bounds, and a benchmark showing the gain (R-RS-UNSAFE). Cheaper first step: re-slice once before the loop (`let b = &b[..a.len()];`) so the compiler sees equal lengths.

## R-RSPERF-CHAIN-HOT — chain in a measured hot loop

Why: `a.iter().chain(b.iter())` adds a branch per item to find the active half. Usually negligible; it matters only in a measured inner loop. `for_each`, `fold` and `sum` over a chain use internal iteration and avoid most of that cost.

Bad:
```rust
for _ in 0..1_000_000 {
    for x in a.iter().chain(b.iter()) {
        sum += i64::from(*x);
    }
}
```
Why: in a hot inner loop the chain costs a branch per item (only after the profile says so).

Good:
```rust
for _ in 0..1_000_000 {
    sum += a.iter().chain(b).map(|&x| i64::from(x)).sum::<i64>(); // internal iteration
    // or two plain loops, or merge once outside the loop:
    // all.extend_from_slice(a); all.extend_from_slice(b);
}
```
Why: `sum` drives the chain through `fold`, one loop per half. `chain` stays fine for one-off code and for short-circuiting searches.

## R-RSPERF-ENTRY-API — one lookup

Why: `contains_key` + `insert`/`get_mut` hashes and probes twice.

Bad:
```rust
fn increment(map: &mut HashMap<String, u32>, key: String) {
    if map.contains_key(&key) {
        *map.get_mut(&key).expect("key checked above") += 1;
    } else {
        map.insert(key, 1);
    }
}
```
Why: two hashes and two probes for one update.

Good:
```rust
fn increment(map: &mut HashMap<String, u32>, key: String) {
    *map.entry(key).or_default() += 1;
}

fn group(items: Vec<Item>) -> HashMap<Category, Vec<Item>> {
    let mut groups: HashMap<Category, Vec<Item>> = HashMap::new();
    for item in items {
        groups.entry(item.category).or_default().push(item);
    }
    groups
}
```
Why: one hash and one probe. `or_insert_with(f)` is lazy, `and_modify(f).or_insert(v)` updates or inserts; for branching logic `match map.entry(k) { Entry::Occupied(..) .. Entry::Vacant(..) .. }`. `entry` takes the key by value; with only a `&str` and a hit expected, do `get_mut` first to avoid allocating the key.

## R-RSPERF-EXTEND-BATCH — add many items at once

Why: `extend` reserves from the iterator's `size_hint` and copies in bulk; a `push` loop can reallocate repeatedly.

Bad:
```rust
fn combine(mut a: Vec<i32>, b: Vec<i32>) -> Vec<i32> {
    for item in b {
        a.push(item);
    }
    a
}

fn build_list() -> Vec<i32> {
    let mut list = Vec::new();
    for i in 0..1000 {
        list.push(i);
    }
    list
}
```
Why: repeated growth and copying.

Good:
```rust
fn combine(mut a: Vec<i32>, b: Vec<i32>) -> Vec<i32> {
    a.extend(b); // or a.append(&mut b) when b is borrowed
    a
}

fn build_list() -> Vec<i32> {
    (0..1000).collect()
}

fn merge_all(chunks: Vec<Vec<Item>>) -> Vec<Item> {
    let total: usize = chunks.iter().map(Vec::len).sum();
    let mut result = Vec::with_capacity(total);
    for chunk in chunks {
        result.extend(chunk);
    }
    result
}
```
Why: one reservation. Strings: `parts.concat()` or `parts.join(",")`.

## R-RSPERF-REUSE-BUFFER — keep the allocation across iterations

Why: `Vec::new()` per iteration allocates and frees every time; `clear()` and `drain(..)` keep the capacity.

Bad:
```rust
for batch in data {
    let filtered: Vec<_> = batch.iter().filter(|&&x| x > 0).copied().collect();
    process(&filtered);
}
```
Why: a new allocation for every batch.

Good:
```rust
let mut buffer = Vec::new();
for batch in data {
    buffer.clear(); // keeps capacity
    buffer.extend(batch.iter().filter(|&&x| x > 0).copied());
    process(&buffer);
}
```
Why: after warm-up the loop does not allocate. Differences: `clear()` drops the items and keeps capacity; `drain(..)` yields the items, keeps capacity; `mem::take(&mut v)` hands out the vector and leaves capacity 0. For batching a large Vec, `drain(..n)` into a reused batch buffer avoids a collect per batch.

## R-RSPERF-COLLECT-INTO (nightly) — collect_into

Why: `collect_into(&mut buf)` does the same job as `buf.extend(iter)`. It is unstable (`#![feature(iter_collect_into)]`, tracking issue 94780) and stays out of service code. Use `extend` on stable.

Bad:
```rust
#![feature(iter_collect_into)] // nightly only
fn refill(buffer: &mut Vec<i32>, batch: &[i32]) {
    buffer.clear();
    batch.iter().copied().filter(|&x| x > 0).collect_into(buffer);
}
```
Why: needs a nightly toolchain for no gain over `extend`.

Good:
```rust
fn refill(buffer: &mut Vec<i32>, batch: &[i32]) {
    buffer.clear();
    buffer.extend(batch.iter().copied().filter(|&x| x > 0));
}
```
Why: stable, same allocation behaviour.

## R-RSPERF-IO-BUFFER — buffer small reads and writes

Why: every unbuffered `read` or `write` on a file or socket is a syscall. `BufReader` / `BufWriter` batch them (8 KiB by default).

Bad:
```rust
use std::fs::File;
use std::io::Write;

fn write_records(path: &str, records: &[String]) -> std::io::Result<()> {
    let mut file = File::create(path)?;
    for record in records {
        file.write_all(record.as_bytes())?; // one syscall
        file.write_all(b"\n")?;             // another
    }
    Ok(())
}
```
Why: two syscalls per record.

Good:
```rust
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};

fn write_records(path: &str, records: &[String]) -> io::Result<()> {
    let mut writer = BufWriter::new(File::create(path)?);
    for record in records {
        writer.write_all(record.as_bytes())?;
        writer.write_all(b"\n")?;
    }
    writer.flush() // explicit: drop would swallow a flush error
}

fn count_lines(path: &str) -> io::Result<usize> {
    let mut count = 0;
    for line in BufReader::new(File::open(path)?).lines() {
        line?;
        count += 1;
    }
    Ok(count)
}
```
Why: few syscalls, and the error of the final flush is returned. `lines()` allocates a `String` per line; for the hottest loops reuse one with `read_line(&mut buf)` and `buf.clear()`. A larger buffer (`with_capacity(64 * 1024, ..)`) helps large sequential files. In async code use `tokio::io::BufReader` / `BufWriter` (and `shutdown().await` or `flush().await`); do not wrap an already-buffered type twice. This is file and socket code in a blocking context; in async handlers the std calls themselves are forbidden (R-RS-ASYNC).

## R-RSPERF-HASHER — a faster hasher for internal keys (dep)

Why: the std `HashMap` uses SipHash-1-3, which resists hash flooding and costs time on short keys. For keys that no client controls, a non-cryptographic hasher is measurably faster. For keys from requests it is a security bug.

Bad:
```rust
use std::collections::HashMap;

// Profile shows hashing of these internal node ids dominates.
fn index(nodes: &[(u32, String)]) -> HashMap<u32, String> {
    nodes.iter().cloned().collect()
}

// WRONG direction: a predictable hasher on request-controlled keys.
fn sessions_by_header(headers: &[String]) -> rustc_hash::FxHashMap<String, Session> {
    headers.iter().map(|h| (h.clone(), Session::new())).collect()
}
```
Why: the first pays for DoS protection it does not need; the second lets a client craft colliding keys and degrade the map to a list.

Good:
```rust
use std::collections::HashMap;
use rustc_hash::FxBuildHasher; // dependency: rustc-hash (version: check the lock file)

type FastMap<K, V> = HashMap<K, V, FxBuildHasher>;

fn index(nodes: &[(u32, String)]) -> FastMap<u32, String> {
    let mut map = FastMap::with_capacity_and_hasher(nodes.len(), FxBuildHasher);
    map.extend(nodes.iter().cloned());
    map
}
```
Why: internal integer keys, hasher named once in an alias. Request-keyed maps keep the default.

| Hasher | Crate | Flood-resistant | Use |
|---|---|---|---|
| SipHash-1-3 | std | yes | keys from outside (default) |
| `ahash` | `ahash` | random per-process seed; not a cryptographic guarantee | general internal upgrade |
| `foldhash` | `foldhash` | has a randomised variant | internal keys; MS guideline's pick |
| FxHash | `rustc-hash` | no | trusted integer or pointer keys |

(U) The crate APIs and versions were not compiled in this task (no network): `with_capacity_and_hasher(n, FxBuildHasher)` is rustc-hash 2.x; for `foldhash` use `HashMap::with_hasher(foldhash::fast::RandomState::default())`; check the crate docs for the pinned version. Pre-size with `with_capacity` as for any map.

## R-RSPERF-RELEASE-PROFILE — release profile options and their price

Why: the default release profile favours build speed over the last few percent. Each option below buys speed with build time, memory, or behaviour; measure the gain on your benchmark before accepting the price. Typical gains in the sources are 5-20%, workload-dependent.

Bad:
```toml
# Copied wholesale from a blog post: every option on, no benchmark behind any of it.
[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
panic = "abort"
strip = true
```
Why: it changes the failure behaviour of the service (R-RSPERF-PANIC-ABORT) and slows every build without evidence.

Good:
```toml
# Start from the defaults. Add one option at a time, keep it if the benchmark moves.
[profile.release]
lto = "thin"           # cross-crate inlining at a small build cost; "fat" only if measured better
# codegen-units = 1    # more optimisation, slower build, more RAM: with fat LTO for final artefacts

# Symbols for profilers (skill profiling); never shipped.
[profile.profiling]
inherits = "release"
debug = 1
strip = false
```
Why: each line has a reason and can be reverted separately.

| Option | Values | Effect |
|---|---|---|
| `opt-level` | 0-3, `"s"`, `"z"` | release default is 3; `"s"` / `"z"` trade speed for size |
| `lto` | `false` (thin, local to the crate), `"off"`, `"thin"`, `"fat"` / `true` | cross-crate optimisation; fat is the slowest build |
| `codegen-units` | 1-256 | fewer units: more optimisation, slower build (default 16 for release) |
| `strip` | `true`, `"symbols"`, `"debuginfo"` | smaller binary; no symbols in backtraces |
| `debug` | `false`, `1`, `2` | symbols for profiling |

Notes: `lto` and `codegen-units` are workspace-profile settings; `lto` cannot be switched per package. A faster-but-not-final profile (`inherits = "release"`, `lto = false`, `codegen-units = 16`) is useful for CI. Fat LTO does not guarantee a smaller binary; compare sizes. `[profile.dev.package."*"] opt-level = 3` makes dependencies fast in debug builds when tests are slow.

## R-RSPERF-PANIC-ABORT — an option with consequences

Why: `panic = "abort"` removes unwinding tables (smaller, a little faster), but a panic then aborts the whole process.

Bad:
```toml
[profile.release]
panic = "abort"   # "smaller binary, no unwinding" copied as a default
```
Why: in a service on tokio, a panic in one task normally ends that task (the join handle returns the panic); with abort it kills every request in flight, `catch_unwind` guards stop working, and destructors do not run.

Good:
```toml
# Default: panic = "unwind" (unset). Choose abort only if all hold:
#  - a supervisor restarts the process (systemd, container restart policy),
#  - the gain is measured (size or throughput),
#  - nothing relies on catch_unwind or on a panic being contained to a task.
[profile.release]
panic = "abort"
```
Why: the trade is stated where the option is set. This does not change R-RS-PANICS: handlers still never panic on input.
