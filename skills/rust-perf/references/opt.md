# Optimisation: layout, inlining, cold paths, PGO, target-cpu, SIMD

Source prefix `opt-` (leonardomso). Release-profile rules (LTO, codegen-units) are merged into `perf.md` as R-RSPERF-RELEASE-PROFILE. Bounds-check rules are merged with R-RSPERF-ITER-OVER-INDEX in `perf.md`. Everything here comes after R-RSPERF-MEASURE-FIRST.

## R-RSPERF-CACHE-LAYOUT — touch only the data the loop needs

Why: a cache miss costs tens to hundreds of cycles; layout decides how many a loop takes. Applies to loops over many records, not to a handful of config structs.

Bad:
```rust
// Every particle drags 40 bytes through the cache to update 24.
struct Particle {
    position: [f32; 3],
    velocity: [f32; 3],
    mass: f32,
    id: u64,
    flags: u8,
}

fn step(particles: &mut [Particle], dt: f32) {
    for p in particles {
        for axis in 0..3 {
            p.position[axis] += p.velocity[axis] * dt;
        }
    }
}
```
Why: mass, id and flags are loaded with every particle and never used by the loop.

Good:
```rust
// Hot data in its own array; cold data elsewhere, same index.
struct Motion {
    position: [f32; 3],
    velocity: [f32; 3],
}
struct Particles {
    motion: Vec<Motion>,
    meta: Vec<ParticleMeta>, // mass, id, flags: not touched by step()
}

fn step(p: &mut Particles, dt: f32) {
    for m in &mut p.motion {
        for axis in 0..3 {
            m.position[axis] += m.velocity[axis] * dt;
        }
    }
}
```
Why: the loop reads contiguous 24-byte records. Splitting every field into its own `Vec` (struct of arrays) goes further and helps vectorisation; do it when the profile shows the loop is memory-bound.

More:

- Pointer chasing (linked lists, `Box` trees) misses the cache at every hop: prefer a `Vec` and indices into it for graphs and trees (`edges: Vec<usize>`).
- False sharing: counters written by different threads must not share a 64-byte line. `#[repr(align(64))] struct PaddedCounter(AtomicU64);` is enough (the alignment pads the size); the `crossbeam_utils::CachePadded` wrapper is the **(dep)** alternative.
- Measure with `perf stat -e cache-references,cache-misses` or cachegrind (skill `profiling`). Manual prefetch and blocked loops are for numeric kernels with a benchmark behind them; the source's prefetch and blocked-matmul sketches were incomplete and are not repeated.

## R-RSPERF-INLINE — leave inlining to the compiler

Why: inlining removes call overhead and enables further optimisation, but inlined bodies grow the binary and push hot code out of the instruction cache. The compiler's heuristics are usually better than hand annotation.

Bad:
```rust
// Annotated by intuition, no benchmark.
#[inline(always)]
pub fn get_name(&self) -> &str {
    &self.name
}

#[inline(always)]
fn parse_everything(input: &[u8]) -> Parsed {
    // 120 lines
    todo!()
}
```
Why: the first gains nothing (it would be inlined anyway); the second bloats every call site.

Good:
```rust
// No attribute: same crate, the compiler decides.
pub fn get_name(&self) -> &str {
    &self.name
}

// A small non-generic function in a library crate, called from other crates.
#[inline]
pub fn is_digit(b: u8) -> bool {
    b.is_ascii_digit()
}

// Forced only for a tiny function in the innermost loop, with a benchmark that shows it.
#[inline(always)]
fn mix(a: u64, b: u64) -> u64 {
    a.wrapping_mul(b).wrapping_add(a)
}
```
Why: a plain function body is available to other crates only with `#[inline]` (or with LTO); the compiler also inlines tiny leaf functions across crates by itself in recent releases, so measure before adding it. Generic functions are monomorphised in the calling crate and need no `#[inline]` for that reason. `#[inline(never)]` keeps cold code out of hot callers (R-RSPERF-COLD-PATH). Check what happened with `cargo asm` or `cargo rustc --release -- --emit=asm`.

| Attribute | Use |
|---|---|
| none | default; same-crate code |
| `#[inline]` | small non-generic library functions called from other crates |
| `#[inline(always)]` | measured, tiny, innermost-loop function |
| `#[inline(never)]` | cold or large code that should not be copied into hot callers |

## R-RSPERF-COLD-PATH — keep rare work out of the hot function

Why: error construction (formatting, allocation, backtrace capture) inlined into a hot function enlarges it and can block other optimisations. A `#[cold]` function tells the optimiser the call is unlikely, so it moves the branch out of the fall-through path and does not inline it into callers. Paths that end in `panic!` are already treated as cold.

Bad:
```rust
fn process(data: &[u8]) -> Result<Output, Error> {
    if data.is_empty() {
        return Err(Error::Empty {
            context: format!("expected data, got {} bytes", data.len()),
            suggestions: vec!["check input", "validate before calling"],
        });
    }
    do_processing(data)
}
```
Why: the allocation-heavy error code sits inside the hot function.

Good:
```rust
fn process(data: &[u8]) -> Result<Output, Error> {
    if data.is_empty() {
        return Err(empty_data_error());
    }
    do_processing(data)
}

#[cold]
#[inline(never)]
fn empty_data_error() -> Error {
    Error::Empty {
        context: String::from("expected data, got an empty slice"),
        suggestions: vec!["check input", "validate before calling"],
    }
}
```
Why: the hot function stays small. For a branch without a function to extract, call `std::hint::cold_path()` first in the rare branch (stable; 1.95 per the source, compiles on rustc 1.99.1). Do not mark a function cold on a guess: a wrong hint pessimises the common path. `#[cold]` on one trivial `Err(Variant)` constructor changes nothing; use it where the construction is expensive. Logging in the cold function uses `tracing`, not `log`.

## R-RSPERF-LIKELY-HINT (nightly) — likely and unlikely

Why: `std::hint::likely` / `unlikely` give the optimiser the branch probability. They are unstable (`#![feature(likely_unlikely)]`); using them needs a nightly compiler, which services do not use.

Bad:
```rust
#![feature(likely_unlikely)] // nightly only
use std::hint::unlikely;

fn process(data: &Data) -> i32 {
    if unlikely(data.is_corrupted()) {
        return handle_corruption(data);
    }
    fast_path(data)
}
```
Why: the build breaks on stable.

Good:
```rust
fn process(data: &Data) -> i32 {
    if data.is_corrupted() {
        std::hint::cold_path(); // stable: this branch is rare
        return handle_corruption(data);
    }
    fast_path(data)
}
```
Why: same information, stable. Profile first to know which branch is rare. The source's other "hints" (early return is "assumed unlikely", ordering of `match` arms, the `likely_stable` crate) are folklore or an extra dependency and were dropped.

## R-RSPERF-PGO — profile-guided optimisation (option)

Why: PGO rebuilds the program using counters from a real run, so layout and inlining follow the hot paths; the sources report 10-30% on some workloads. It adds a three-step build and the result is only as good as the profile.

Bad:
```bash
# Profile from a micro-benchmark that does not look like production.
RUSTFLAGS="-Cprofile-generate=/tmp/pgo" cargo build --release
./target/release/app --bench-small-op
RUSTFLAGS="-Cprofile-use=/tmp/pgo/merged.profdata" cargo build --release   # merge step missing
```
Why: the profile misrepresents real use, and `-Cprofile-use` needs a merged `.profdata`.

Good:
```bash
# 1. instrumented build
RUSTFLAGS="-Cprofile-generate=/tmp/pgo" cargo build --release
# 2. run representative traffic or a recorded workload
./target/release/app < typical_workload.txt
# 3. merge: llvm-profdata must match rustc's LLVM (rustup component llvm-tools, or cargo-pgo)
llvm-profdata merge -o /tmp/pgo/merged.profdata /tmp/pgo
# 4. optimised build
RUSTFLAGS="-Cprofile-use=/tmp/pgo/merged.profdata" cargo build --release
```
Why: the four steps are explicit. (U) Under Nix the `llvm-profdata` version must match the Rust toolchain's LLVM; not checked here. Skip PGO for libraries, variable workloads, and quick iteration. BOLT post-link optimisation is a further, separate option and is not recommended without a benchmark and a reproducible pipeline.

## R-RSPERF-TARGET-CPU — the fleet baseline, never native

Why: the default x86-64 target uses only baseline SSE2. Newer instruction sets (AVX2) speed up vectorised code, but a binary built for them crashes with `SIGILL` on an older CPU. `target-cpu=native` builds for the machine that compiles, which in CI or a container build is not the machine that runs.

Bad:
```toml
# .cargo/config.toml
[build]
rustflags = ["-C", "target-cpu=native"]
```
Why: the artefact depends on the build host; deploy to an older node and it dies on the first AVX2 instruction.

Good:
```toml
# .cargo/config.toml: the lowest CPU level of the whole fleet.
[target.x86_64-unknown-linux-gnu]
rustflags = ["-C", "target-cpu=x86-64-v3"] # only if every deployment target has AVX2 and BMI2
```
Why: the baseline is a fleet fact, written down. Levels: `x86-64` (default, SSE2), `x86-64-v2` (SSE4.2, POPCNT), `x86-64-v3` (AVX2, BMI2), `x86-64-v4` (AVX-512). Check what a level enables with `rustc --print cfg -C target-cpu=x86-64-v3`. `native` is acceptable only for a binary built and run on the same machine (a local benchmark).

For one hot kernel in a binary that must run everywhere, detect at run time:
```rust
#[cfg(target_arch = "x86_64")]
fn sum(data: &[u8]) -> u64 {
    if is_x86_feature_detected!("avx2") {
        // SAFETY: avx2 was detected at run time.
        unsafe { sum_avx2(data) }
    } else {
        sum_generic(data)
    }
}

#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn sum_avx2(data: &[u8]) -> u64 {
    sum_generic(data) // compiled with AVX2 enabled: the loop auto-vectorises with it
}

fn sum_generic(data: &[u8]) -> u64 {
    data.iter().map(|&b| u64::from(b)).sum()
}
```
Why: one binary, the fast path only where the CPU has it. `unsafe` stays inside R-RS-UNSAFE (SAFETY comment, only where the safe API cannot do it).

## R-RSPERF-SIMD — vectorisation, in order of effort

Why: SIMD does several values per instruction. Most of the gain is available without writing SIMD.

Bad:
```rust
fn add(a: &[f32], b: &[f32], out: &mut [f32]) {
    for i in 0..a.len() {
        out[i] = a[i] + b[i]; // bounds checks stop the vectoriser
    }
}
```
Why: three checks per element.

Good:
```rust
fn add(a: &[f32], b: &[f32], out: &mut [f32]) {
    for ((x, y), o) in a.iter().zip(b).zip(out.iter_mut()) {
        *o = x + y; // LLVM usually vectorises this
    }
}
```
Why: no checks, no early exits. Help the compiler: iterators over indexing, `chunks_exact` for blocked loops, no early `break` in the loop body.

| Approach | Stability | Portable | Control |
|---|---|---|---|
| auto-vectorisation | stable | yes | low |
| `std::arch` + runtime detection | stable, `unsafe` | one architecture per path | maximum |
| `wide` crate (dep) | stable | yes | medium |
| `std::simd` (portable SIMD) | nightly | yes | high |

`std::simd` needs `#![feature(portable_simd)]` and is not used in services. Check that vectorisation happened (`cargo asm`) before writing intrinsics, and keep a scalar reference version to test the fast one against (tests in `tests/`).
