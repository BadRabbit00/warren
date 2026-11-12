---
name: rust-idioms
description: Use when writing or reviewing Rust pattern matching, closures and callbacks, collection choice, or const/static items. One-line rules with decision tables; full Bad/Good in references/.
---

# Rust idioms: patterns, closures, collections, const

Stable Rust, edition 2024. Complements `rules/rust.md` (panic policy, `thiserror`, integration tests in the crate's test directory, `#[expect]`); nothing here overrides it. Lint levels are set by the project config, not by these rules.

## When to use

- Writing `match`, `if let`, `let ... else`, or enum handling.
- Passing, storing or returning closures.
- Picking `Vec` / `VecDeque` / `HashMap` / `BTreeMap` / sets / heaps.
- Adding a `const`, `static`, `const fn` or const generic.

## Contents

1. [Patterns](#patterns) · full text: [references/pat.md](references/pat.md)
2. [Closures](#closures) · [references/closure.md](references/closure.md)
3. [Collections](#collections) · [references/coll.md](references/coll.md)
4. [Const and static](#const-and-static) · [references/const.md](references/const.md)

## Patterns

- R-RSI-PAT-EXHAUSTIVE: match your own enums with every variant listed, no `_` arm; `_` only for foreign `#[non_exhaustive]` enums, with a comment. [pat-exhaustive-enum]
- R-RSI-PAT-LET-ELSE: extract-or-leave with `let Some(x) = e else { return ... };` to keep the happy path flat; use `?` when the else branch only propagates. [pat-let-else]
- R-RSI-PAT-IF-LET-CHAIN: several bindings plus conditions in one `if let ... && let ... && cond` (edition 2024, stable since 1.88). [pat-if-let-chains]
- R-RSI-PAT-MATCHES: a boolean pattern test is `matches!(v, P)`, not a `match` returning `true`/`false`. [pat-matches-macro]
- R-RSI-PAT-AT-BINDING: bind and test in one place with `name @ pattern`; do not repeat a range in a guard. [pat-at-bindings]
- R-RSI-PAT-COMBINATORS: for a single transformation of an `Option`/`Result` use `map`, `and_then`, `ok_or`; a nested `match` that only re-wraps is noise. [rust-patterns]

| Situation | Use |
|---|---|
| Fail early, keep the rest flat | `let ... else` |
| Several optional bindings and a condition, then a body | `if let` chain |
| Only a yes/no answer | `matches!` |
| Need the whole value and a part of it | `whole @ Pattern(..)` |
| Error should propagate | `?` |
| Foreign `#[non_exhaustive]` enum | explicit arms plus a commented `_` |

## Closures

- R-RSI-CLOSURE-FN-BOUNDS: bound a callback by the weakest trait the body needs: `FnOnce` if called once, `FnMut` if repeated and stateful, `Fn` only when it must be shareable or re-entrant. [closure-fn-trait-bounds]
- R-RSI-CLOSURE-MOVE: a closure that escapes (thread, spawned task, returned, stored) uses `move`; clone first what you still need outside. [closure-move-capture]
- R-RSI-CLOSURE-CAPTURE: closures capture only the fields they use (edition 2021+, also with `move`), so a sibling field stays usable; `move` through a reference or `self` captures the reference, so bind the value to a local first. [closure-disjoint-capture]
- R-RSI-CLOSURE-RETURN-IMPL: return `impl Fn...`; `Box<dyn Fn...>` only when the branches return different closures or the value goes into a struct or collection. [closure-impl-fn-return]
- R-RSI-CLOSURE-STATIC-DYN: take a generic `F: Fn` by default; `&dyn Fn` for a borrowed non-generic callee; `Box<dyn Fn>` to store mixed closures. [closure-static-vs-dyn]

| Situation | Use |
|---|---|
| Called once, may consume captures | `FnOnce` |
| Called repeatedly, mutates state | `FnMut` (binding must be `mut`) |
| Called repeatedly, read-only, shared | `Fn` |
| Hot loop, one call site | generic `F` / `impl Fn` |
| Stored callbacks of different types | `Vec<Box<dyn Fn(..) + Send + Sync>>` |
| Return one closure type | `impl Fn` |
| Return one of several closures | `Box<dyn Fn>` |

## Collections

- R-RSI-COLL-SEQ: `Vec` by default; `VecDeque` for queues and windows (`pop_front` is O(1)); `LinkedList` only with a measurement. `Vec::remove(0)` in a loop is a bug. [coll-seq-choice]
- R-RSI-COLL-MAP: `HashMap` by default; `BTreeMap` for sorted iteration or range queries; `IndexMap` (a new dependency, say so) for insertion order. [coll-map-choice]
- R-RSI-COLL-SET: membership tests and dedup go through `HashSet` / `BTreeSet`, not `Vec::contains` in a loop (tiny lists excepted). [coll-set-membership]
- R-RSI-COLL-HEAP: repeated "give me the largest" is `BinaryHeap`; `Reverse` for a min-heap; it has no priority update or arbitrary removal. [coll-binaryheap]
- R-RSI-COLL-COLLECT: build the target with `collect()` and a type annotation; collecting into `Result<Vec<_>, _>` stops at the first error. [rust-patterns]

| Need | Choose |
|---|---|
| Growable list | `Vec` |
| FIFO, deque, sliding window | `VecDeque` |
| Lookup by key, order irrelevant | `HashMap` |
| Sorted keys or `range(a..b)` | `BTreeMap` / `BTreeSet` |
| Insertion order plus lookup | `IndexMap` (dependency) |
| Membership, dedup | `HashSet` |
| Top-k, scheduler | `BinaryHeap` |

Output that must be stable (reports, snapshots, API responses) must not iterate a `HashMap`; sort, or use `BTreeMap`.

## Const and static

- R-RSI-CONST-FN: make pure, simple functions `const fn` so they work in const contexts; adding `const` later is not a breaking change. [const-fn]
- R-RSI-CONST-BLOCK: `const { ... }` for an inline compile-time assertion on generic parameters, or a per-element constant such as `[const { Vec::new() }; N]` (stable since 1.79). [const-block]
- R-RSI-CONST-GENERICS: a size known at compile time is a const generic parameter, not a copy per size and not a runtime length. [const-generics]
- R-RSI-CONST-VS-STATIC: `const` for small values, `static` for one addressed instance; never `static mut`; global mutable state is an atomic, `OnceLock` or `LazyLock`, and configuration still comes only through the config module. [const-vs-static]

| Situation | Use |
|---|---|
| Number, flag, mask, tiny array | `const` |
| Large table, or a `&'static T` is required | `static` |
| Counter or flag shared across threads | `static` atomic |
| Lazily built global (compiled table) | `static LazyLock<T>` |
| Set once at start-up | `static OnceLock<T>` |
| Build-time check of a constant | `const _: () = assert!(...)` |
