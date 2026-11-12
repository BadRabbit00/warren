---
name: rust-docs
description: Use when writing or reviewing rustdoc comments (`///` and `//!`) in Rust code. Gives the rules for summary lines, canonical sections, examples, intra-doc links, and what doc comments must not contain.
---

# Rust doc comments

## When to use

- Writing or changing `///` and `//!` comments on Rust items and modules.
- Reviewing or refactoring public Rust API that lacks docs, or whose docs lie or describe history.
- Not for project documents in `docs/` (README, architecture, ADR): that is skill `project-docs`.

## Contents

1. [Rules](#rules)
2. [Which section when](#which-section-when)
3. [Which fence attribute for an example](#which-fence-attribute-for-an-example)
4. [Where these rules apply](#where-these-rules-apply)
5. Full rules with Bad/Good: `references/doc.md` (from leonardomso, prefix `doc-`) and `references/microsoft.md` (Microsoft docs rules)

## Rules

### Summary and structure

- R-RSDOC-FIRST-SENTENCE: the first sentence of every doc comment is one line, about 15 words, and says what the item is or does. [M-FIRST-DOC-SENTENCE]
- R-RSDOC-ALL-PUBLIC: every public item of a library crate has a `///` comment; fields and variants say what they mean. [doc-all-public]
- R-RSDOC-MODULE: a public library module has `//!` docs: what it holds, when to use it, when not, examples; the first line follows R-RSDOC-FIRST-SENTENCE. [doc-module-inner, M-MODULE-DOCS]
- R-RSDOC-CANONICAL: use the canonical sections (`# Examples`, `# Errors`, `# Panics`, `# Safety`, `# Abort`) when they apply; describe parameters in prose, never in a parameter table. [M-CANONICAL-DOCS]

### Sections

- R-RSDOC-ERRORS: a function returning `Result` has `# Errors` that lists each condition and links the error variant. [doc-errors-section]
- R-RSDOC-PANICS: a function that panics on a violated precondition has `# Panics` naming the precondition; point to a non-panicking sibling when one exists. [doc-panics-section]
- R-RSDOC-SAFETY: an `unsafe fn` or `unsafe trait` has `# Safety` listing everything the caller or implementer must uphold. [doc-safety-section]

### Examples

- R-RSDOC-EXAMPLES: public API has a `# Examples` section with a runnable doctest; show the error case as well when it matters. [doc-examples-section]
- R-RSDOC-QUESTION-MARK: examples use `?`, not `.unwrap()`; end the example with `Ok::<(), E>(())` or wrap it in `fn main() -> Result<..>`. [doc-question-mark]
- R-RSDOC-HIDDEN-SETUP: hide imports and setup with a `# ` line prefix; keep visible what the reader must learn. [doc-hidden-setup]

### Links and re-exports

- R-RSDOC-LINKS: reference items with intra-doc links (`` [`Type`] ``, `` [`Self::method`] ``), never as bare text; check them with `RUSTDOCFLAGS="-D warnings" cargo doc --no-deps`. [doc-intra-links, doc-link-types]
- R-RSDOC-DOC-INLINE: published crates only: a `pub use` of your own crate's item carries `#[doc(inline)]`; never inline `std` or third-party re-exports, never glob re-export. [M-DOC-INLINE]

### Content

- R-RSDOC-NO-HISTORY: docs describe the end state: no design journey, no "we chose X over Y", no changelog, no guideline compliance tables, no "previously / now / new / removed". [M-NO-META-DESIGN-DOCUMENTATION]

### Published crates only

- R-RSDOC-CARGO-META: published crates only: fill `description`, `license`, `repository`, `readme`, `keywords`, `categories`, `rust-version` in `Cargo.toml`. [doc-cargo-metadata]
- R-RSDOC-README: published crates only: make the README the crate root doc with `#![doc = include_str!("../README.md")]`. [doc-crate-readme]

## Which section when

| The item | Section |
|---|---|
| Any public item | Summary line (one line, ~15 words) |
| Has non-obvious behaviour or a usage idiom | Extended text, then `# Examples` |
| Returns `Result` | `# Errors` |
| Panics on a violated precondition | `# Panics` |
| `unsafe fn`, `unsafe trait`, or can cause UB | `# Safety` |
| May abort the process | `# Abort` |
| Public module | `//!` with contents, when to use, example |
| Has parameters | Prose in the summary or body, no table |

## Which fence attribute for an example

| The example | Fence |
|---|---|
| Runs fast and deterministically | `rust` (or a bare fence) |
| Must compile but would start a server or touch the network | `no_run` |
| Not Rust (shell, TOML, output) | `bash`, `toml`, `text` |
| Must fail to compile (shows an error) | `compile_fail` |
| Pseudocode | prefer `text`; `ignore` hides breakage, use only with a comment saying why |

## Where these rules apply

- Doctests run only for library crates. In a binary crate (service `main.rs` and its modules) examples are not compiled: keep them out or mark them `text`.
- "Public" means the public API of a library crate. In a service, items exposed only inside the workspace need at least the summary line; the sections apply when the item is used across crates.
- Rules marked "published crates only" do not apply to internal workspace crates.
- Doctests are documentation, not the test suite: behaviour tests live in the crate's `tests` directory (`rules/rust.md`).
- Lint levels (`missing_docs`, `rustdoc::broken_intra_doc_links`) live in lint configuration; in our projects only `ci-engineer` changes it. This skill names the lints but does not change the config.
- The rules agree with the panic policy: a bug panics with a message, an expected failure returns `Result`; `# Panics` documents the first, `# Errors` the second.
