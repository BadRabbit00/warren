---
paths:
  - "**/*.rs"
  - "**/Cargo.toml"
---

# Rust

## Scope

Rust services and libraries (tokio, axum, sqlx/diesel). Layers, DB, and tests have their own rules; this is the language core every writer gets. `language-reviewer` checks it in depth; the `rust-*` skills hold the long forms.

Checks: `cargo test`; `cargo clippy --all-targets -- -D warnings`; `cargo fmt --check`.

## Rules

- R-RS-PANIC-POLICY: a detected bug (broken invariant) panics with a message; an expected failure (input, I/O, DB, network) returns `Result`. Never use a panic to report an error upstream.
- R-RS-PANICS: request handlers and workers never panic on input: no slice indexing on untrusted lengths (`get`), no `unwrap` on parsed data, no `unreachable!` for reachable states.
- R-RS-NO-UNWRAP: `unwrap()` only in tests; elsewhere `?`, or `expect("why it cannot fail")` for a true invariant (an `expect` on user data is a bug).
- R-RS-PANIC-MESSAGE: `panic!`, `assert!`, `unreachable!` and `todo!` in production carry a message with the reason and the offending values.
- R-RS-NO-CATCH-UNWIND: never use `catch_unwind` to carry on after a panic; at most at a process boundary, followed by a controlled restart.
- R-RS-ERRORS: libraries and domain code return `thiserror` enums, one per module or domain; `anyhow` only in binaries and top-level glue.
- R-RS-ERR-CONVERT: convert between error layers with `#[from]` / `From` so `?` works; keep the cause with `#[source]`, never flatten it into a `String`.
- R-RS-ERR-CONTEXT: add context where an error crosses a boundary (`.context()` / `.with_context()` in glue, a typed variant in libraries).
- R-RS-ERR-MESSAGE: error messages are lowercase, with no trailing period and no cause text that the source chain already prints.
- R-RS-ERR-DOCS: a public fallible function documents its failure cases in an `# Errors` section.
- R-RS-NO-SWALLOW: never drop an error silently (`let _ =`, `if let Err(_)`, `.ok()`, an empty `Err` arm): handle it, propagate it, or log it once with a reason.
- R-RS-ASYNC: nothing blocking in async code (`std::fs`, `std::thread::sleep`, heavy CPU): use `tokio::fs`, `tokio::time::sleep`, `spawn_blocking`. Never hold a `std::sync::Mutex` guard across `.await`.
- R-RS-OWNERSHIP: take `&str`, `&[T]`, `impl AsRef<…>` in parameters, never `&String` / `&Vec<T>`; borrow instead of `clone()`; a `clone()` in a hot loop needs a reason.
- R-RS-CLONE-COST: derive `Copy` only on small plain-data types; for expensive types keep `Clone` explicit at the call site and move big values instead of copying.
- R-RS-COW: use `Cow<'a, T>` when a function only sometimes needs to allocate.
- R-RS-LIFETIMES: rely on lifetime elision; write explicit lifetimes only where the compiler requires them.
- R-RS-SHARING: `Arc` for sharing across threads, `Rc` only in single-threaded code; interior mutability by `Mutex` (threads) or `RefCell` (one thread), `RwLock` only when reads far outnumber writes.
- R-RS-TAKE: move a value out of a `&mut` with `mem::take` / `mem::replace`, not with a clone.
- R-RS-DROP-ORDER: fields drop top to bottom, locals in reverse; when drop order matters (guards, flushes), say so in a comment.
- R-RS-CAPACITY: `with_capacity` when the size is known; clear and reuse a buffer in a loop; `clone_from` to reuse an allocation.
- R-RS-NO-FORMAT: no `format!` for a plain literal; `write!` into an existing buffer in loops.
- R-RS-BOX-VARIANT: box the large variant of an enum with one big and many small variants; fixed-size heap data is `Box<[T]>`.
- R-RS-SIZE-GUARD: guard the size of types stored in bulk with `const { assert!(size_of::<T>() <= N) }`; integers are as wide as the range needs and no wider.
- R-RS-ZERO-COPY: parse by borrowing slices of the input when the result does not outlive it.
- R-RS-UNSAFE: no `unsafe` without a valid reason (a new abstraction, measured performance, FFI) and a `// SAFETY:` comment proving the invariant; every `unsafe fn` has a `# Safety` section.
- R-RS-UNSAFE-SCOPE: an `unsafe` block holds only the operation that needs it; never use `unsafe` to bypass `Send` or lifetimes, or to shorten safe code (`transmute`).
- R-RS-UNSAFE-MEANS-UB: mark `unsafe` only where misuse risks undefined behaviour; a merely dangerous function (delete everything) stays safe.
- R-RS-SOUND: a safe function must not cause UB for any caller, however contrived; if it can, make it `unsafe` or change the signature.
- R-RS-UNINIT: `MaybeUninit<T>` for uninitialized memory; never `mem::uninitialized()` or `mem::zeroed()` for types with validity invariants.
- R-RS-SEND-SYNC: no `unsafe impl Send` / `Sync` to silence the compiler; where a manual impl is needed, document the invariants.
- R-RS-FFI-EDITION: in edition 2024 write `unsafe extern { }` with `safe` / `unsafe` items and `#[unsafe(no_mangle)]`.
- R-RS-MIRI: a crate with `unsafe` code has its tests run under `cargo miri test` where miri is available.
- R-RS-OVERFLOW: choose overflow behaviour on purpose: `checked_` / `saturating_` / `wrapping_` / `overflowing_`; never rely on a debug-only panic.
- R-RS-CAST: `From` for widening, `TryFrom` for narrowing; `as` for narrowing or sign change only with a comment.
- R-RS-FLOAT: no `==` on floats: compare with a tolerance, order with `total_cmp`, bound with `clamp`.
- R-RS-NONZERO: `NonZero*` where zero is invalid (counts, sizes, ids).
- R-RS-TYPES: newtypes for identifiers and validated values (`struct OrderId(Uuid)`); enums for exclusive states; `match` on your own enums lists every variant (no `_` arm).
- R-RS-RUST-SHAPED: when porting from Java, C#, Python or Go keep the domain logic and redo the technical shape in Rust idioms (traits, ownership, `Result`, no class hierarchies, no global statics).
- R-RS-NO-OVER-ABSTRACTION: no generic parameter, trait or builder with one user; start with a concrete type and generalise when a second case appears.
- R-RS-REGULAR-FN: a function with no receiver stays a free function; `impl` blocks hold constructors and methods only.
- R-RS-SINGLE-PATH: a public item is reachable through one path; no `pub use` duplicate of an item that is already public elsewhere in the crate.
- R-RS-DEBUG: every public type implements `Debug`; a type with secrets gets a custom `Debug` that hides them, covered by a test.
- R-RS-MAGIC: no bare magic value: a named constant with a comment on why this value, what changing it affects, and which system depends on it.
- R-RS-LINTS: `cargo clippy --all-targets -- -D warnings` and `cargo fmt --check` are clean; override a lint with `#[expect(lint, reason = "…")]`, not `#[allow]` (`allow` only in generated code and macros).
- R-RS-NO-META-DOCS: crate and module docs describe the end state, not how it was designed or which guidelines were followed.
- R-RS-TESTS-REAL: a test checks behaviour or a property, never a constant against its own copy or a branch against itself; tests live in `<crate>/tests/`.

## Examples

### R-RS-ERRORS — no unwrap on input

Bad:
```rust
async fn get_order(Path(id): Path<String>, State(db): State<Db>) -> Json<Order> {
    let id = Uuid::parse_str(&id).unwrap();
    Json(db.order(id).await.unwrap())
}
```
Why: a malformed id or a DB hiccup panics the task and returns a broken connection instead of 400/404/500.

Good:
```rust
async fn get_order(Path(id): Path<OrderId>, State(svc): State<OrderService>) -> Result<Json<OrderRead>, ApiError> {
    let order = svc.get(id).await?;          // OrderError → ApiError via From
    Ok(Json(order.into()))
}
```

### R-RS-ASYNC — a std mutex across await

Bad:
```rust
let mut cache = state.cache.lock().unwrap();    // std::sync::Mutex
let fresh = fetch(&client, key).await?;         // guard held across await
cache.insert(key, fresh);
```
Why: the guard blocks the executor thread and can deadlock; the future is also not `Send`.

Good:
```rust
let fresh = fetch(&client, key).await?;
state.cache.lock().expect("cache mutex poisoned").insert(key, fresh);   // lock only around the insert
```
