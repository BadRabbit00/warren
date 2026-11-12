---
name: rust-testing
description: Use when writing or reviewing Rust tests: where they live, naming, async tests with tokio, fakes and mockall at external boundaries, property tests, snapshots, doctests, benchmarks, loom. Gives one-line rules, decision tables and full rules in references/.
---

# Rust testing

Rust-specific testing rules. Language-neutral rules (layers, real DB, behaviour over calls, determinism) are in `rules/tests.md`; this skill shows how they look in Rust. Only `test-writer` writes tests; others read this to review them.

## When to use

- Writing, reviewing or planning Rust tests (`test-writer`, `rust-reviewer`).
- Choosing between a hand-written fake, `mockall`, a property test, a snapshot.
- Testing async code, panics, concurrency, doctests, benchmarks.

## Contents

1. [Layout and style](#layout-and-style)
2. [Async](#async)
3. [Doubles and fixtures](#doubles-and-fixtures)
4. [Kinds of test](#kinds-of-test)
5. [Decision tables](#decision-tables)
6. [References](#references)

Source ids are in brackets: `test-*` leonardomso, `M-*` Microsoft. Crates named below (`mockall`, `proptest`, `insta`, `criterion`, `loom`, `tempfile`) are dev-dependencies: adding one is a decision to state in the task, not a default.

## Layout and style

- R-RST-LOCATION: tests live in `<crate>/tests/`, one file = one test binary, shared helpers in `tests/common/mod.rs`; no `#[cfg(test)] mod tests` in `src/`, no `use super::*`. Test through the public API; a private function that needs its own test belongs in its own module or crate. Doctests (in `///`) are the only tests next to the code. Rewrites `test-integration-dir`; `test-cfg-test-module` and `test-use-super` are dropped. [test-integration-dir]
- R-RST-NAMES: the name states behaviour, `rejects_empty_name`, `paid_order_cannot_be_cancelled`; never `test1`, `test_parse`, `it_works`. [test-descriptive-names]
- R-RST-AAA: one behaviour per test, in three visible steps: arrange, act, assert. No second act after an assert. [test-arrange-act-assert]
- R-RST-NOT-TAUTOLOGICAL: an assertion must not restate the value or the branch the code itself defines; check a property (ordering, spacing, round trip) or an outcome. Do not write a test just to satisfy a mutation tool. [M-TAUTOLOGICAL-TESTS]

## Async

- R-RST-TOKIO-TEST: `#[tokio::test]` for async tests; the default flavour is `current_thread`, ask for `multi_thread` only when the code needs it. `#[tokio::test(start_paused = true)]` plus `tokio::time::advance` makes timeouts and retries instant and deterministic (needs tokio feature `test-util`). [test-tokio-async]

## Doubles and fixtures

- R-RST-FAKE-BOUNDARY: put a trait only on a boundary you cannot run for real (external HTTP API, LLM, mail, payments, clock). Repositories and the database are not faked in repository tests: use the real DB (R-TEST-REAL-DB). Traits use native `async fn`; no `async_trait`. Native `async fn` traits are not dyn-compatible: take a generic `C: Trait`. [test-mock-traits]
- R-RST-MOCKALL: `mockall` (one version in the workspace) for external boundaries only; declare mocks with `mock!` in `tests/common/`, because `#[automock]` under `cfg(test)` is invisible to `tests/`. Assert on call count or order only when the call itself is the outcome (one email sent). Per-call return values need separate expectations, not several `.returning`. [test-mockall-mocking]
- R-RST-RAII: setup that must be undone is a value with `Drop`: `tempfile::NamedTempFile` / `TempDir`, a sqlx transaction dropped without commit (rolls back). Never a fixed path in `/tmp`. Do not mutate the environment from tests (`set_var` is `unsafe` in edition 2024 and races with parallel tests): pass configuration as a parameter. [test-fixture-raii]

## Kinds of test

- R-RST-PROPERTY: `proptest` for invariants over many inputs (round trip, idempotence, ordering); the property must not be implied by the generator; use `prop_assert_eq!`; commit the `proptest-regressions` files it writes. [test-proptest-properties]
- R-RST-SNAPSHOT: `insta` for large or structured output (JSON, rendered text); snapshots are committed and reviewed; CI runs with `INSTA_UPDATE=no`; redact ids and timestamps. [test-snapshot-testing]
- R-RST-SHOULD-PANIC: `#[should_panic(expected = "...")]` only for a bug-class panic (broken invariant) and always with `expected`; an expected failure returns `Result` and the test matches the error. The test function returns `()`. [test-should-panic]
- R-RST-DOCTEST: every public item with an example gets a runnable doctest (`?` with a hidden `Ok::<(), E>(())`, not `unwrap`); `no_run` over `ignore`. Library crates only; a binary crate has no doctests. Text of docs: skill `rust-docs`. [test-doctest-examples]
- R-RST-BENCH: benchmarks go in `benches/` with `criterion` and `std::hint::black_box`; measure before and after, on the same machine. Method: skills `rust-perf`, `profiling`. [test-criterion-bench]
- R-RST-LOOM: `loom` for lock-free code and hand-written synchronisation (rare; skip for code that only uses `tokio::sync`). Gated by `#[cfg(loom)]`; the test is in `tests/` and run with `RUSTFLAGS="--cfg loom"`. Works on stable. [test-loom-concurrency]

## Decision tables

What to use for a collaborator:

| Collaborator | In a repository or integration test | In a service test |
|---|---|---|
| Own database | real DB (R-TEST-REAL-DB) | fake repository or real DB |
| External HTTP / LLM / mail / payments | fake at the trait | fake at the trait |
| Time | `start_paused` or injected clock | same |
| Filesystem | `tempfile` | `tempfile` |

Fake or mockall:

| Situation | Choice |
|---|---|
| Fixed answers, few cases | hand-written fake struct in `tests/common/` |
| Many cases, per-test answers, error injection | `mockall` via `mock!` |
| The call is the outcome (email sent once) | `mockall` with `times(1)` |
| Own repository | neither: real DB |

Which kind of test:

| You want to check | Use |
|---|---|
| One behaviour, known inputs | plain test (R-RST-AAA) |
| A law over many inputs | R-RST-PROPERTY |
| Big structured output | R-RST-SNAPSHOT |
| A broken invariant panics | R-RST-SHOULD-PANIC |
| An example in the docs still compiles | R-RST-DOCTEST |
| Speed | R-RST-BENCH |
| Memory ordering | R-RST-LOOM |

## References

Full rules with Bad/Good examples, grouped by source prefix:

- [references/test.md](references/test.md): the `R-RST-*` rules adapted from leonardomso `test-*`.
- [references/ms-ai.md](references/ms-ai.md): R-RST-NOT-TAUTOLOGICAL from Microsoft.
