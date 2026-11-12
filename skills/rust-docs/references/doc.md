# Doc rules (source: leonardomso `doc-*`)

Full text of the kept rules. Short form and ids: `../SKILL.md`. Examples were corrected where the source was wrong (see the note under each rule).

## R-RSDOC-ALL-PUBLIC — document every public item [doc-all-public]

Why: public items are the API contract. Without docs the reader has to read the source.

Bad:
```rust
pub struct Config {
    pub timeout: Duration,
    pub retries: u32,
}

pub enum Status {
    Pending,
    Active,
    Failed,
}
```

Good:
```rust
/// Settings for connecting to the service.
pub struct Config {
    /// Longest wait for a response before the call fails.
    pub timeout: Duration,
    /// Attempts made after the first failure.
    pub retries: u32,
}

/// Lifecycle state of a job.
pub enum Status {
    /// Waiting in the queue.
    Pending,
    /// Being processed.
    Active,
    /// Failed for good; no retry is scheduled.
    Failed,
}
```

| Item | What the comment says |
|---|---|
| Struct, enum | Purpose; an example when usage is not obvious |
| Field | What it represents, with the unit if any |
| Variant | The state or case it stands for |
| Function | What it does; parameters in prose (R-RSDOC-CANONICAL) |
| Trait | The contract and expected behaviour |
| Type alias | Why the alias exists |
| Constant | What the value means |

Enforcement: the `missing_docs` lint (`#![warn(missing_docs)]` or `[workspace.lints.rust] missing_docs = "warn"`). In our projects only `ci-engineer` changes lint configuration; ask for it instead of editing it.

Scope: public API of library crates. Binary crates are not documented for readers outside the repository; a summary line is enough there.

## R-RSDOC-MODULE — document modules with `//!` [doc-module-inner]

Merged with Microsoft M-MODULE-DOCS (see `microsoft.md`).

Why: `//!` documents the enclosing module and is the first thing a reader sees when opening it. A plain `//` comment is invisible to rustdoc.

Bad:
```rust
// This module handles authentication.
// It provides JWT and session-based auth.

mod auth;
```

Good:
```rust
//! Authentication for incoming requests.
//!
//! Two strategies are available:
//!
//! - [`JwtAuth`] checks a signed bearer token.
//! - [`SessionAuth`] checks a session cookie.
//!
//! # Examples
//!
//! ```
//! # use my_crate::auth::JwtAuth;
//! # fn main() -> Result<(), my_crate::auth::AuthError> {
//! let auth = JwtAuth::new("secret-key");
//! let claims = auth.verify("eyJ...")?;
//! # let _ = claims;
//! # Ok(())
//! # }
//! ```

pub struct JwtAuth { /* ... */ }
pub struct SessionAuth { /* ... */ }
```

Where it goes: the top of `lib.rs` for the crate root, the top of `mod.rs` or `<module>.rs` for a module.

Crate root (`lib.rs`): summary, a quick-start example, the list of modules, and, for published crates, the Cargo feature flags. Do not add a `prelude` module only to shorten imports: an item must have one path.

Corrections to the source: its `?` in a module example had no function around it and would not compile as a doctest; the crate-root example listed a `prelude` module and a glob import; both removed.

## R-RSDOC-ERRORS — write `# Errors` for fallible functions [doc-errors-section]

Why: the section tells the caller when the call fails, so that they can handle each case without reading the body.

Bad:
```rust
/// Opens a file and reads its contents.
pub fn read_file(path: &Path) -> Result<String, ReadError> {
    todo!()
}
```

Good:
```rust
/// Reads a file as UTF-8 text.
///
/// # Errors
///
/// Returns [`ReadError::NotFound`] if the file does not exist,
/// [`ReadError::PermissionDenied`] if the process may not read it, and
/// [`ReadError::InvalidUtf8`] if the contents are not valid UTF-8.
pub fn read_file(path: &Path) -> Result<String, ReadError> {
    todo!()
}
```

With many variants a table is fine:
```rust
/// Sends a request and returns the response.
///
/// # Errors
///
/// | Error | When |
/// |---|---|
/// | [`HttpError::Timeout`] | the request exceeded the timeout |
/// | [`HttpError::ConnectionRefused`] | the server refused the connection |
/// | [`HttpError::Tls`] | the TLS handshake failed |
pub fn send(request: Request) -> Result<Response, HttpError> {
    todo!()
}
```

Link each variant of the `thiserror` enum (R-RS-ERRORS). When the function only forwards the error of the callee, say so in one line and link the callee.

Corrections to the source: the `anyhow::Error` example is dropped (libraries return typed errors).

## R-RSDOC-PANICS — write `# Panics` for documented preconditions [doc-panics-section]

Why: the caller must know which precondition to uphold. A panic is for a bug (a broken precondition), never for bad input at runtime (`rules/rust.md`); if the failure is expected, return `Result` and write `# Errors`.

Bad:
```rust
/// Splits the buffer at `mid`.
pub fn split(&self, mid: usize) -> (&[u8], &[u8]) {
    self.data.split_at(mid)
}
```

Good:
```rust
/// Splits the buffer at `mid`.
///
/// # Panics
///
/// Panics if `mid > self.len()`. Use [`try_split`](Self::try_split) when
/// `mid` comes from outside.
pub fn split(&self, mid: usize) -> (&[u8], &[u8]) {
    self.data.split_at(mid)
}

/// Splits the buffer at `mid`, or returns `None` if `mid > self.len()`.
pub fn try_split(&self, mid: usize) -> Option<(&[u8], &[u8])> {
    (mid <= self.data.len()).then(|| self.data.split_at(mid))
}
```

What can panic, for the audit of a function body:

| Operation | Condition |
|---|---|
| Index `v[i]` | out of bounds |
| `/`, `%` | divisor zero |
| `.unwrap()`, `.expect()` | `None` or `Err` |
| `slice::split_at(mid)` | `mid > len` |
| `Vec::remove(i)` | `i >= len` |
| `assert!` and friends | the asserted condition fails |

State the reason for panicking in the docs when it is not obvious, for example "a zero capacity is a programming error, not a runtime condition".

Corrections to the source: its example indexed `self.data` in a function without `self` and asserted a `Vec::get` result against a reference, which does not compile. The "debug-only panic" pattern is dropped: documenting behaviour that differs between build profiles invites bugs. For request handlers and workers the rule is stronger: no panics on input (R-RS-PANICS).

## R-RSDOC-SAFETY — write `# Safety` for unsafe items [doc-safety-section]

Why: the compiler cannot check the invariants of an `unsafe fn`; the section is the contract that makes calling it sound. `unsafe` itself needs a `// SAFETY:` comment at each block (R-RS-UNSAFE).

Bad:
```rust
/// Reads a value from a raw pointer.
pub unsafe fn read_ptr<T>(ptr: *const T) -> T {
    unsafe { ptr.read() }
}
```

Good:
```rust
/// Reads a value from a raw pointer.
///
/// # Safety
///
/// The caller must ensure that:
/// - `ptr` is non-null, aligned for `T`, and valid for reads of `size_of::<T>()` bytes;
/// - `ptr` points to an initialised value of `T`;
/// - the memory is not written through another pointer during the call.
pub unsafe fn read_ptr<T>(ptr: *const T) -> T {
    // SAFETY: the caller upholds the contract in `# Safety` above.
    unsafe { ptr.read() }
}
```

Elements to cover: preconditions, pointer validity (alignment, null, lifetime), ownership and who frees, type invariants, and what happens on violation.

For `unsafe trait`, `# Safety` states what the implementer guarantees, and each `unsafe impl` carries a `// SAFETY:` comment saying why this type satisfies it.

Corrections to the source: in edition 2024 the body of an `unsafe fn` needs its own `unsafe {}` block (`unsafe_op_in_unsafe_fn` warns by default); examples now have them with SAFETY comments.

## R-RSDOC-EXAMPLES — add `# Examples` with runnable code [doc-examples-section]

Why: an example shows the intended use faster than prose, and the doctest keeps it correct as the code changes.

Bad:
```rust
/// Parses a string into a `Foo`.
pub fn parse(s: &str) -> Result<Foo, ParseError> {
    todo!()
}
```

Good:
```rust
/// Parses a string into a `Foo`.
///
/// # Examples
///
/// ```
/// use my_crate::parse;
///
/// let foo = parse("hello")?;
/// assert_eq!(foo.name(), "hello");
/// # Ok::<(), my_crate::ParseError>(())
/// ```
///
/// An empty string is rejected:
///
/// ```
/// use my_crate::{parse, ParseError};
///
/// assert_eq!(parse(""), Err(ParseError::Empty));
/// ```
pub fn parse(s: &str) -> Result<Foo, ParseError> {
    todo!()
}
```

Rules of thumb:

- Several small examples with a sentence before each beat one long one.
- Show the error case when it is part of the contract.
- Run them with `cargo test --doc`.
- Doctests only exist in library crates.

Corrections to the source: `.unwrap()` replaced by `?` (R-RSDOC-QUESTION-MARK); the examples that mocked a database inside a doctest are dropped, because docs describe the API, and database-backed behaviour is tested in the crate's `tests` directory against a real database (`rules/tests.md`).

## R-RSDOC-QUESTION-MARK — `?` in examples, not `.unwrap()` [doc-question-mark]

Why: an example is copied. `.unwrap()` teaches ignoring errors; `?` shows the real pattern and fails the doctest if the call fails.

A doctest body is wrapped in `fn main()` that returns `()`. So `?` only compiles if you either end the example with `Ok::<(), E>(())` or write the `fn main() -> Result<..>` yourself.

Bad:
```rust
/// ```
/// let config = Config::from_file("config.toml").unwrap();
/// ```
pub fn from_file(path: &str) -> Result<Config, ConfigError> {
    todo!()
}
```

Good (type-annotated final line):
```rust
/// ```no_run
/// # use my_crate::{Config, ConfigError};
/// let config = Config::from_file("config.toml")?;
/// println!("{}", config.database_url);
/// # Ok::<(), ConfigError>(())
/// ```
pub fn from_file(path: &str) -> Result<Config, ConfigError> {
    todo!()
}
```

Good (async, hidden wrapper):
```rust
/// ```no_run
/// # use my_crate::{Client, Data, ClientError};
/// # async fn example() -> Result<(), ClientError> {
/// let client = Client::new();
/// let data: Data = client.get("https://api.example.com").await?.json().await?;
/// # Ok(())
/// # }
/// ```
pub async fn get(&self, url: &str) -> Result<Response, ClientError> {
    todo!()
}
```

When `?` is impossible (a literal that cannot fail), write `.expect("why it cannot fail")`, never a bare `.unwrap()`; this matches `rules/rust.md`.

Corrections to the source: it said the wrapper returns `Result` by default (it does not); it allowed `.unwrap()` for static values (replaced by `expect` with a reason).

## R-RSDOC-HIDDEN-SETUP — hide setup with `# ` [doc-hidden-setup]

Why: imports and fixtures bury the one line the reader came for. A line starting with `# ` is compiled and run but not rendered.

Bad (setup is visible, the point is on line 12):
```rust
/// ```
/// use my_crate::{Processor, Config, Item};
/// let config = Config { batch_size: 100, timeout_ms: 5000 };
/// let processor = Processor::new(config);
/// let items = vec![Item::new("a"), Item::new("b")];
/// let results = processor.process_batch(&items)?;
/// # Ok::<(), my_crate::Error>(())
/// ```
```

Good:
```rust
/// ```
/// # use my_crate::{Processor, Config, Item, Error};
/// # let processor = Processor::new(Config { batch_size: 100, timeout_ms: 5000 });
/// # let items = vec![Item::new("a"), Item::new("b")];
/// let results = processor.process_batch(&items)?;
/// assert!(results.all_succeeded());
/// # Ok::<(), Error>(())
/// ```
```

| Hide | Keep visible |
|---|---|
| `use` lines | the API call under discussion |
| Type definitions, fixtures | key arguments |
| The final `Ok(())` | assertions that show the result |

Do not hide setup that is the point (for example a builder whose options are what the example teaches).

Examples that must not run: `no_run` compiles but does not execute (servers, network). `ignore` neither compiles nor runs, so it can rot; prefer `no_run`, or `text` for pseudocode, and give a reason if you must use `ignore`.

Corrections to the source: its `no_run` example used `.await?` outside an async function; moved into the wrapper pattern of R-RSDOC-QUESTION-MARK.

## R-RSDOC-LINKS — intra-doc links [doc-intra-links, doc-link-types]

The two source rules were duplicates and are merged.

Why: `` [`Type`] `` produces a clickable link that `cargo doc` verifies and that follows renames. Bare names rot silently.

Bad:
```rust
/// Parses the input into a ParseResult.
///
/// See also: ParseError, and capacity() for the allocated size.
pub fn parse(input: &str) -> ParseResult {
    todo!()
}
```

Good:
```rust
/// Parses the input into a [`ParseResult`].
///
/// Failures are reported as [`ParseError`]; see [`capacity()`](Self::capacity)
/// for the allocated size and [`FromStr`] for the trait this builds on.
///
/// [`FromStr`]: std::str::FromStr
pub fn parse(input: &str) -> ParseResult {
    todo!()
}
```

| Syntax | Links to |
|---|---|
| `` [`Name`] `` | item in scope |
| `` [`crate::a::Name`] `` / `` [`super::Name`] `` | item by path |
| `` [`Self::method`] `` | member of the current type |
| `` [`Type::method`] ``, `` [`Type::CONST`] `` | member of another type |
| `` [`Iterator::next`] `` | trait method |
| `` [text](Self::len) `` | custom link text |
| `` [`foo`](fn@foo) ``, `mod@`, `struct@`, `enum@`, `trait@`, `type@`, `const@`, `macro@` | disambiguation when names clash |

Reference-style definitions at the end of the comment keep long paths out of the text:
```rust
/// Decodes with [`Deserialize`] and returns a [`Result`].
///
/// [`Deserialize`]: serde::Deserialize
/// [`Result`]: std::result::Result
```

Link only to items the crate depends on; `` [`rayon::ParallelIterator`] `` needs `rayon` in the dependency graph.

Verification in CI:
```bash
RUSTDOCFLAGS="-D warnings" cargo doc --no-deps
```
The lint is `rustdoc::broken_intra_doc_links`; to set it in `[lints.rustdoc]` ask `ci-engineer`.

## R-RSDOC-CARGO-META — Cargo.toml metadata [doc-cargo-metadata]

Published crates only. Internal workspace crates (`publish = false`) skip this.

Why: crates.io and docs.rs build their pages from the manifest.

Bad:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
```

Good:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
description = "A small HTTP client with typed errors"
license = "MIT OR Apache-2.0"
repository = "https://github.com/example/my-crate"
readme = "README.md"
keywords = ["http", "client", "async"]
categories = ["network-programming", "web-programming::http-client"]
```

| Field | Rule |
|---|---|
| `description` | one line, at most 256 characters; required for publishing |
| `license` or `license-file` | SPDX expression; required |
| `keywords` | at most 5, specific and searchable (not "rust", "fast") |
| `categories` | slugs from the crates.io list |
| `rust-version` | the MSRV, kept in step with CI |
| `include` / `exclude` | pick one; control what is packaged |

Check what ships: `cargo package --list`, then `cargo publish --dry-run`.

Corrections to the source: edition 2024 in all examples, the deprecated `[badges]` block and the `homepage` / `authors` extras dropped, `rust-version` consistent with edition 2024 (1.85 is the first release that supports it).

## R-RSDOC-README — README as crate root docs [doc-crate-readme]

Published crates only.

Why: a README and a hand-written `//!` block drift apart. One file serves GitHub, crates.io and docs.rs.

Bad:
```rust
//! # my-crate
//!
//! A library for doing things (a copy that will go stale).
```

Good:
```rust
#![doc = include_str!("../README.md")]
```
with `readme = "README.md"` in `Cargo.toml`.

Every fenced block in the README is compiled as a doctest unless tagged. Tag non-Rust blocks (`bash`, `toml`, `text`) and use `no_run` for Rust that should not execute. The README is a project document; its contents belong to skill `project-docs`, this rule only governs how it is wired in as the crate doc.
