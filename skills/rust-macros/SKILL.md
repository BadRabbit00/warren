---
name: rust-macros
description: Use when writing, reviewing or deciding on a Rust macro - macro_rules!, derive or attribute proc macros, fragment specifiers, $crate paths, hidden helper modules, spanned compile errors with syn and quote, and when to use a plain function instead.
---

# Rust macros

Rules for macros in Rust (edition 2024, stable). Rule ids `R-RSM-*`; source ids in brackets (`macro-*` = leonardomso/rust-skills, `M-*` = Microsoft Rust guidelines). Full rules with Bad/Good examples are in `references/`.

## When to use

- You are about to write a `macro_rules!` macro or a proc macro, or review one.
- You wonder whether a function, a generic or a derive would do instead.
- A macro gives unreadable errors, breaks in another crate, or leaks helper items.

## Contents

1. [Decide first](#decide-first)
2. [Rules](#rules)
3. [Where to look](#where-to-look)

## Decide first

| Situation | Use |
|---|---|
| Fixed argument count, any types | generic function |
| Same `impl` for many unrelated types | `macro_rules!` |
| Variadic argument list (`vec![]`-like) | `macro_rules!` |
| Boilerplate a derive can generate from a type | derive proc macro |
| Embedded DSL with non-Rust syntax | proc macro |
| Needs to inspect or rewrite item attributes | proc macro (attribute) |
| Anything a `macro_rules!` can do | `macro_rules!`, not a proc macro |

## Rules

Choosing a macro

- R-RSM-LAST-RESORT: use a macro only when functions, generics and traits cannot do it; the best macro is one where the reader knows exactly what it generates [macro-prefer-functions, M-MACRO-LAST-RESORT]
- R-RSM-EXAMPLE-OVER-PROC: prefer `macro_rules!` to a proc macro when it can do the job: inspectable, faster to compile [M-EXAMPLE-OVER-PROC]
- R-RSM-DONT-LIE: a macro never changes the nature of an item: no struct to enum, no added parameters, no changed `async`-ness [M-MACROS-DONT-LIE]
- R-RSM-NO-IMPLIED-ITEMS: a macro does not invent extra named types or items next to the user's item; the same-name-other-namespace trick is the only tolerated form [M-PROC-IMPLIED-ITEMS]

`macro_rules!`

- R-RSM-FRAGMENTS: capture with the most specific fragment (`expr`, `ty`, `ident`, `path`), not `tt`; mind the follow sets; allow `$(,)?` [macro-fragment-specifiers]
- R-RSM-CRATE-PATH: refer to your own items as `$crate::...`, never `crate::...` [macro-rules-hygiene]
- R-RSM-EXPORT: export with `#[macro_export]` and import by path (`use mylib::m;`), not `#[macro_use]`; published crates only if the macro is used outside its crate [macro-export-crate-path]
- R-RSM-PRIVATE-HELPERS: helpers and third-party items a macro expansion needs go behind `#[doc(hidden)] pub mod __private`; callers need no extra dependency [macro-private-helpers, M-MACRO-HELPERS]

Proc macros

- R-RSM-PROC-CRATES: a `proc-macro = true` crate exports only macros; keep it a thin shim, put the logic in a normal crate working on `proc_macro2::TokenStream`, test it from `tests/` [macro-proc-two-crate, M-PROC-IMPL]
- R-RSM-PROC-SYN-QUOTE: parse with `syn`, generate with `quote`, enable only the `syn` features you use; these are new dependencies, name them in the plan [macro-proc-syn-quote]
- R-RSM-PROC-ERRORS: report bad input as `syn::Error` with a span, never by `panic!`, `unwrap()` or `expect()`; a broken internal invariant of the macro itself may still panic with a message [macro-proc-error-spans]

Published crates only: R-RSM-EXPORT's `#[macro_use]` remark, the `__private` semver note in R-RSM-PRIVATE-HELPERS, and the three-crate layout with `trybuild` in R-RSM-PROC-CRATES. Inside a service workspace a macro lives in one crate and is used by path.

## Example

Bad:
```rust
// crate:: resolves in the caller's crate; breaks outside this crate
#[macro_export]
macro_rules! log {
    ($val:expr) => { crate::log_value(&format!("{:?}", $val)) };
}
```
Why: the path is wrong as soon as the macro is used from another crate.

Good:
```rust
#[macro_export]
macro_rules! log {
    ($val:expr) => { $crate::log_value(&format!("{:?}", $val)) };
}
```

## Where to look

- `references/macro.md` - the eight leonardomso rules in full, corrected.
- `references/microsoft-macros.md` - the Microsoft rules in full.
- Dependencies and `[lints]` settings for a macro crate are not changed here; ci-engineer owns lint configuration.
