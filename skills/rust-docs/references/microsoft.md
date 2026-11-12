# Doc rules (source: Microsoft Rust Guidelines)

Rewritten from `docs/` and `ai/` of the Microsoft guidelines. Short form and ids: `../SKILL.md`.

## R-RSDOC-FIRST-SENTENCE — one-line summary, about 15 words [M-FIRST-DOC-SENTENCE]

Why: rustdoc shows the first sentence in module and search listings with a fixed width. A long first sentence wraps into a ragged block and the listing stops being skimmable.

Bad:
```rust
/// Creates a connection pool that keeps a configurable number of connections open to the database and hands them out to callers, recycling them when they are returned.
pub fn pool(config: PoolConfig) -> Pool {
    todo!()
}
```

Good:
```rust
/// Creates a pool of reusable database connections.
///
/// The pool keeps up to `config.max_size` connections open and hands them
/// out to callers; a connection is recycled when the guard is dropped.
pub fn pool(config: PoolConfig) -> Pool {
    todo!()
}
```

The first sentence stands alone as one line, at most about 15 words, and ends with a full stop. Everything else goes after a blank `///` line.

## R-RSDOC-MODULE — module documentation [M-MODULE-DOCS]

Merged with doc-module-inner (see `doc.md`).

A public library module must have `//!` docs whose first sentence follows R-RSDOC-FIRST-SENTENCE. The rest covers what applies from this list:

- what the module contains;
- when to use it, and when not;
- examples;
- a specification of a subsystem the module defines (for instance the format language of a formatting module);
- observable side effects and the guarantees made about them;
- relevant implementation details, such as the system APIs used.

Not every module needs every item. If there is something to say about how the contained types work together, the module docs are the place, not the individual items.

## R-RSDOC-CANONICAL — canonical sections [M-CANONICAL-DOCS]

Why: Rust readers expect the same section names everywhere.

The summary sentence is always present. Extended text and `# Examples` are strongly encouraged. The others are present when they apply:

```rust
/// Copies a file from `src` to `dst`.
///
/// Extended description in free form.
///
/// # Examples
/// One or more examples of use.
///
/// # Errors
/// Each condition under which the `Result` is an `Err`.
///
/// # Panics
/// Each precondition whose violation panics.
///
/// # Safety
/// For `unsafe` items: everything the caller must uphold.
///
/// # Abort
/// When the function may abort the process.
pub fn copy(src: &File, dst: &File) -> Result<(), CopyError> {
    todo!()
}
```

Parameters are described in prose, not in a table.

Bad:
```rust
/// Copies a file.
///
/// # Parameters
/// - src: The source.
/// - dst: The destination.
pub fn copy(src: &File, dst: &File) -> Result<(), CopyError> {
    todo!()
}
```

Good:
```rust
/// Copies the contents of `src` into `dst`.
pub fn copy(src: &File, dst: &File) -> Result<(), CopyError> {
    todo!()
}
```

Details of the individual sections: R-RSDOC-ERRORS, R-RSDOC-PANICS, R-RSDOC-SAFETY, R-RSDOC-EXAMPLES in `doc.md`. A section that does not apply is left out; do not write "# Panics: never".

## R-RSDOC-DOC-INLINE — inline re-exports [M-DOC-INLINE]

Published crates only, and only when the crate re-exports its own items. Prefer one path per item, so re-exports are the exception.

Why: a plain `pub use` shows up in rustdoc as an opaque "Re-exports" line. `#[doc(inline)]` renders the item as if it were defined at the re-export site.

Bad:
```rust
mod parser;

pub use parser::Parser;
```

Good:
```rust
mod parser;

#[doc(inline)]
pub use parser::Parser;
```

Do not inline items from `std` or other crates: re-export them without the attribute so that the reader sees they are external. `#[doc(inline)]` does not make a glob re-export acceptable; list the names instead.

## R-RSDOC-NO-HISTORY — document the end state [M-NO-META-DESIGN-DOCUMENTATION]

Why: doc comments are read by the people who use the code, not by the people who wrote it. Notes on how a change came about are noise to them and go stale.

Do not put in `///` or `//!`:

- a design journey or "why we picked X over Y" essay;
- words that describe the change: "now", "no longer", "previously", "new", "removed", "refactored", "fixed";
- a table or list claiming which guidelines or rules were followed;
- a task id, ticket, or PR number as the explanation of the code.

Bad:
```rust
//! Order totals.
//!
//! Refactored from the old float-based version; we picked integer cents over
//! `Decimal` after comparing both.
//!
//! | Rule | Applied |
//! | --- | :---: |
//! | M-SHORT-NAMES | yes |
```

Good:
```rust
//! Order totals in integer cents.
//!
//! All amounts are `i64` cents in the order's currency; there is no rounding
//! after the line items are summed.
```

What stays: a short "Design principles" section of a README that states lasting properties users depend on (allocation-free, `no_std`-ready). The history of a decision belongs in the commit message or an ADR, not in the code docs. Project documents in `docs/` are covered by skill `project-docs`.
