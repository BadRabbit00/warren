---
name: rust-perf
description: Use when a Rust change is about speed or memory - hot loops, allocations, hashers, release profile (LTO, panic=abort, target-cpu), inlining, inline vectors, arenas, async future size. Gives measure-first rules, one-line rules with decision tables, and full Bad/Good references.
---

# Rust performance

Rule ids `R-RSPERF-*`. Stable Rust, edition 2024. Rules marked **(nightly)** need a nightly compiler and are not for our services. Rules marked **(dep)** add a dependency: say so in the change (P-DEP-NEW). Plain memory rules (`with_capacity`, `mem::take`, `clone_from`, `write!` over `format!`, boxing a large enum variant) live in `rules/rust.md` and clippy; this skill is the part that needs a measurement, a dependency, or a build setting.

Sources: leonardomso/rust-skills (`perf-`, `opt-`, some `mem-`) and Microsoft Pragmatic Rust Guidelines (`performance/`). Ids in brackets are the source ids. See `NOTICE.md`.

## When to use

- A finding says "slow", "allocates too much", "binary too big", or a task asks for a speed or memory gain.
- Choosing a release profile, a hasher, a small-vector type, or a SIMD approach.
- Reviewing a diff that adds `#[inline(always)]`, `unsafe` for speed, `panic = "abort"`, or `target-cpu`.

## Contents

1. [Method](#method)
2. [Iterators, collections, IO](#iterators-collections-io)
3. [Memory layout and types](#memory-layout-and-types)
4. [Async and telemetry](#async-and-telemetry)
5. [Compiler and build](#compiler-and-build)
6. [Decision tables](#decision-tables)
7. [References](#references)

## Method

- R-RSPERF-MEASURE-FIRST: no optimisation without a number. Benchmark the hot path, profile it under realistic load, change one thing, measure again; algorithm and data structure beat micro-tuning. Profilers and exact commands: skill `profiling`. Every rule below is a candidate to try after the profile points at it, not a default. [perf-profile-first, M-HOTPATH]
- R-RSPERF-BENCH-BLACK-BOX: wrap benchmark inputs and results in `std::hint::black_box`, or the compiler may fold the work away; benchmarks live in `benches/`, not in `src/`. [perf-black-box-bench]

## Iterators, collections, IO

- R-RSPERF-ITER-LAZY: keep iterator chains lazy and `collect()` once at the end; use `count`, `any`, `find`, `sum` instead of collecting to measure or test. [perf-iter-lazy, perf-collect-once]
- R-RSPERF-ITER-OVER-INDEX: iterate with `iter()`, `zip`, `windows`, `chunks_exact` instead of `for i in 0..len` indexing; destructure fixed headers with slice patterns. Check the assembly before claiming a bounds check is gone. `get_unchecked` is a last resort under R-RS-UNSAFE, never the first move. [perf-iter-over-index, opt-bounds-check]
- R-RSPERF-CHAIN-HOT: `chain` is fine; in a measured hot inner loop prefer two loops, `extend_from_slice`, or `fold` / `for_each` (internal iteration). [perf-chain-avoid]
- R-RSPERF-ENTRY-API: insert-or-update a map with `entry()` (one lookup), not `contains_key` + `insert`. [perf-entry-api]
- R-RSPERF-EXTEND-BATCH: add many items with `extend`, `extend_from_slice`, `append`, or `collect`, not a `push` loop; join strings with `concat` / `join`. [perf-extend-batch]
- R-RSPERF-REUSE-BUFFER: in a loop, hold one buffer, `clear()` it and refill with `extend` (or `drain`); do not allocate a new `Vec` per iteration. [perf-drain-reuse, perf-collect-into]
- R-RSPERF-COLLECT-INTO **(nightly)**: `Iterator::collect_into` is the same idea but needs `#![feature(iter_collect_into)]`; on stable use `extend`. [perf-collect-into]
- R-RSPERF-IO-BUFFER: wrap `File` and `TcpStream` in `BufReader` / `BufWriter` for many small reads or writes, and call `flush()?` before drop (drop swallows the error). Async: `tokio::io::BufReader` / `BufWriter`; never `std::fs` in async code (R-RS-ASYNC). [perf-io-buffering]
- R-RSPERF-HASHER **(dep)**: the default `HashMap` hasher is DoS-resistant; swap it (`foldhash`, `rustc-hash`, `ahash`) only for internal keys that no client controls (ids, handles), only after the profile shows hashing, and never for keys from requests. [perf-ahash, M-FAST-HASHER]
- R-RSPERF-CAPACITY: `with_capacity` when the size is known or estimable; `shrink_to_fit` on a large long-lived collection built by pushing. [M-INITIAL-CAPACITY, M-SHRINK-TO-FIT]
- R-RSPERF-REUSE-API: design hot APIs so the caller owns the buffer (`get_into(id, &mut buf)`); the allocating form is the convenience wrapper. [M-MEM-REUSE]

## Memory layout and types

- R-RSPERF-BOX-DST: a frequently created, immutable owned sequence is `Box<[T]>` / `Box<str>` / `Arc<str>`, not `Vec` / `String` (one word less, no spare capacity); only when it is internal and there are thousands of instances. [mem-boxed-slice, M-BOX-DST]
- R-RSPERF-INLINE-VEC **(dep)**: usually-small vectors: `SmallVec<[T; N]>` (spills to heap), `ArrayVec<T, N>` (hard limit, never heap; `try_push` on input), `TinyVec` (no unsafe). Pick N from measured data; a hard-limit overflow on input is an error, not a panic. [mem-smallvec, mem-arrayvec]
- R-RSPERF-THIN-VEC **(dep)**: many collections that are usually empty: `ThinVec` is one pointer wide; slower to iterate than `Vec`; not for hot loops. [mem-thinvec]
- R-RSPERF-COMPACT-STRING **(dep)**: millions of short strings: `CompactString` (inline, no allocation) or `EcoString` (cheap clone); keep `String` / `&str` at API boundaries. [mem-compact-string]
- R-RSPERF-INT-SIZES: use the smallest integer that fits the domain in large arrays and hot structs; `NonZero*` makes `Option<id>` free; `rustc` already reorders fields, so do not hand-reorder for padding. [mem-smaller-integers]
- R-RSPERF-TYPE-SIZE-ASSERT: pin the size of types stored in huge collections with `const _: () = assert!(size_of::<T>() <= N)` next to the type. [mem-assert-type-size]
- R-RSPERF-ARENA **(dep)**: many short-lived allocations freed together (parse tree, one batch): a `bumpalo::Bump` per unit of work; the arena never lives across `.await` in a `Send` future and never in a `thread_local!` under tokio. [mem-arena-allocator]
- R-RSPERF-ZERO-COPY: return `&str` / `&[u8]` slices and `Cow` instead of owned copies when the input outlives the result; `bytes::Bytes` for shared buffers across tasks. [mem-zero-copy]
- R-RSPERF-AVOID-INDIRECTION: on hot types, no layers of `Arc<Arc<..>>`; embed the data, or lift the hot field to the outer struct. [M-AVOID-INDIRECTION]
- R-RSPERF-CACHE-LAYOUT: for hot loops over many records, touch only the hot fields: split hot and cold data, or store fields in separate vectors (SoA); prefer indices into a `Vec` over linked pointers; pad per-thread counters against false sharing (`#[repr(align(64))]`). [opt-cache-friendly]

## Async and telemetry

- R-RSPERF-YIELD-POINTS: CPU-bound work in an async fn yields: `tokio::task::yield_now().await` between chunks of roughly 10-100 microseconds; heavy or unbounded CPU goes to `spawn_blocking` (R-RS-ASYNC). [M-YIELD-POINTS]
- R-RSPERF-FUTURE-SIZE: on a hot async path, measure the future with `size_of_val` and keep large values out of parameters and out of locals held across `.await`. [M-ASYNC-STACK-SIZE]
- R-RSPERF-LOG-OVERHEAD: no events and no `format!` inside hot inner loops; one event per batch with structured fields (skill `logging`). [M-LOG-OVERHEAD]

## Compiler and build

- R-RSPERF-RELEASE-PROFILE: the default release profile is fine until measured. Options with a price: `lto = "thin"` (small build cost) or `"fat"` (slow build), `codegen-units = 1` (slow build), `strip`. Keep a separate `[profile.profiling]` with `debug = 1`. [perf-release-profile, opt-lto-release, opt-codegen-units]
- R-RSPERF-PANIC-ABORT: `panic = "abort"` is an option, not a default: one panic then kills the whole process (no task isolation, no unwinding, no `catch_unwind`, destructors do not run). Choose it only when the supervisor restarts the service and the gain is measured. [perf-release-profile, opt-lto-release]
- R-RSPERF-INLINE: leave inlining to the compiler; `#[inline]` for small non-generic functions called across crates; `#[inline(always)]` only for a measured, tiny hot function; never on a big function. [opt-inline-small, opt-inline-always-rare]
- R-RSPERF-COLD-PATH: build errors and other rare-branch work in a `#[cold] #[inline(never)]` function, or call `std::hint::cold_path()` (stable since 1.95) in the rare branch; do not guess which branch is rare. [opt-cold-unlikely, opt-inline-never-cold]
- R-RSPERF-LIKELY-HINT **(nightly)**: `std::hint::likely` / `unlikely` need `#![feature(likely_unlikely)]`; on stable use `cold_path`. [opt-likely-hint]
- R-RSPERF-PGO: profile-guided optimisation is an option for a stable, measured workload; it adds a three-step build and the profile must be representative. [opt-pgo-profile]
- R-RSPERF-TARGET-CPU: `target-cpu` is the fleet baseline (for example `x86-64-v3` when every machine supports it), never `native` in CI or container builds: the build host is not the run host and a wrong guess ends in `SIGILL`. For one hot kernel use runtime detection. [opt-target-cpu]
- R-RSPERF-SIMD: rely on auto-vectorisation first (iterators, `chunks_exact`); then `std::arch` behind `is_x86_feature_detected!`; `std::simd` is **(nightly)**; a crate such as `wide` is **(dep)**. [opt-simd-portable]

## Decision tables

| Situation | Choice |
|---|---|
| Keys come from requests or the network | default hasher (SipHash) |
| Internal integer or id keys, hashing shows in the profile | `foldhash` or `rustc-hash`; `ahash` if you want a random seed |
| Usually small, may grow | `SmallVec<[T; N]>` |
| Hard upper bound, no heap allowed | `ArrayVec<T, N>` (`try_push`) |
| Usually empty, millions of instances | `ThinVec<T>` |
| Never resized after build, many instances | `Box<[T]>` / `Box<str>` |
| Built by pushing, kept long | `shrink_to_fit` |
| Many short allocations freed together | `Bump` arena per unit of work |
| Many short strings in memory | `CompactString` |

| Build option | Gain | Price | Our default |
|---|---|---|---|
| `lto = "thin"` | modest | little build time | try first |
| `lto = "fat"` | a bit more | slow build | only if measured |
| `codegen-units = 1` | a bit | slower build, more RAM | with fat LTO |
| `panic = "abort"` | smaller binary, a bit faster | a panic kills the process | off |
| `target-cpu=native` | machine-specific | `SIGILL` elsewhere | never |
| `target-cpu=x86-64-v3` | AVX2 everywhere | fails on old CPUs | only for a known fleet |
| PGO | workload-specific | build pipeline | off |

| Hint | Stable? |
|---|---|
| `#[cold]`, `#[inline(never)]` | yes |
| `std::hint::cold_path()` | yes (1.95) |
| `std::hint::likely` / `unlikely` | nightly |
| `Iterator::collect_into` | nightly |
| `std::simd` | nightly |

Locks: `parking_lot` is often recommended over `std::sync::Mutex` for speed. That is contestable: the std mutex has been futex-based since Rust 1.62 and the gap is small; measure under your own contention before adding the dependency.

## References

- `references/perf.md` - method, iterators, collections, IO, hasher, release profile
- `references/opt.md` - bounds checks, cache layout, inlining, cold paths, PGO, target-cpu, SIMD
- `references/mem.md` - boxed slices, small vectors, compact strings, arenas, zero-copy, type sizes
- `references/ms-performance.md` - buffer-owning APIs, capacity, yield points, telemetry cost, indirection, future size
