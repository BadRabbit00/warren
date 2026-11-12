# Macro rules (from leonardomso `macro-*`, with Microsoft merges)

Rust 2024 edition, stable. Where a source example was wrong it was corrected; the changes are listed at the end.

### R-RSM-LAST-RESORT — a macro only when the language runs out

Macros run before type checking, so they bypass inference, resist IDE navigation, give opaque errors, slow incremental builds and cannot be passed as values. They can also break at edition boundaries. The more complex the expansion, the worse the idea: a good macro makes the user think "I know exactly what this generates, I just do not want to type it".

Bad:
```rust
// No variadics, no DSL, no trait impl: a function does this.
macro_rules! double {
    ($x:expr) => { $x + $x };
}
```
Why: a macro here costs inference and readability and buys nothing.

Good:
```rust
fn double<T: std::ops::Add<Output = T> + Copy>(x: T) -> T {
    x + x
}
```

| Situation | Macro? |
|---|---|
| Fixed argument count, any types | No, generics |
| Truly variadic list | Yes, `macro_rules!` |
| Same trait impl for many unrelated types | Yes, `macro_rules!` |
| DSL with non-Rust syntax | Yes, proc macro |
| Boilerplate a derive can generate | Yes, derive proc macro |
| Simple computation or conversion | No, function or trait |

### R-RSM-FRAGMENTS — precise fragment specifiers

Specifiers tell the compiler what a macro arm expects: errors say "expected expression" instead of "no rules expected token", and parsing stays unambiguous. A raw `tt` pushes validation onto you and surfaces implementation details in errors.

Follow sets: after `expr` and `stmt` only `=>`, `,` or `;` may follow; after `ty` and `path` only `{`, `[`, `=>`, `,`, `>`, `=`, `:`, `;`, `|`, `as`, `where` or a `block` fragment; after `pat` only `=>`, `,`, `=`, `if`, `in`; after `pat_param` also `|`. Choose separators from these.

Edition 2024: `expr` also matches `const { ... }` blocks and `_`; use `expr_2021` to keep the old behaviour. Since edition 2021 `pat` accepts a top-level `|`; use `pat_param` when you need the old meaning.

Bad:
```rust
// :tt soup, accepts anything, fails late inside the expansion
macro_rules! debug_val {
    ($($t:tt)*) => {
        println!("{} = {:?}", stringify!($($t)*), $($t)*)
    };
}
```
Why: `debug_val!(let x = 1)` is accepted by the matcher and only blows up in the expansion.

Good:
```rust
macro_rules! debug_val {
    ($e:expr $(,)?) => {
        println!("{} = {:?}", stringify!($e), $e)
    };
}
```

Trailing comma: end repetitions with `$(,)?`:

```rust
macro_rules! my_vec {
    ($($e:expr),* $(,)?) => { vec![$($e),*] };
}
```

| Specifier | Matches |
|---|---|
| `expr` | expression |
| `ty` | type |
| `ident` | identifier |
| `pat` / `pat_param` | pattern (with / without top-level `\|`) |
| `path` | path `a::b::c` |
| `literal` | literal |
| `block` | `{ ... }` |
| `stmt` | statement |
| `meta` | attribute content |
| `vis` | visibility, possibly empty |
| `lifetime` | `'a` |
| `tt` | one token tree, last resort |

### R-RSM-CRATE-PATH — `$crate`, not `crate`

`macro_rules!` is hygienic for local bindings (a `let tmp` inside the macro never clashes with the caller's `tmp`), but item paths are resolved at the call site. `crate::` means the caller's crate; `$crate` always means the crate that defined the macro, also when it is re-exported.

Bad:
```rust
pub fn log_value(v: &str) { println!("[log] {v}"); }

#[macro_export]
macro_rules! log {
    ($val:expr) => { crate::log_value(&format!("{:?}", $val)) };
}
// consumer: log!(42)  -> error, `crate::log_value` not found
```
Why: `crate::` resolves in the consumer.

Good:
```rust
pub fn log_value(v: &str) { println!("[log] {v}"); }

#[macro_export]
macro_rules! log {
    ($val:expr) => { $crate::log_value(&format!("{:?}", $val)) };
}
```

Hygiene does not cover identifiers the caller passes in (`$name:ident`): those come from the caller's scope on purpose. For helper items use `$crate::__private::...` (R-RSM-PRIVATE-HELPERS).

### R-RSM-EXPORT — export by path, not `#[macro_use]`

`#[macro_export]` puts the macro at the crate root, importable like any item: `use mylib::greet;`. The legacy `#[macro_use] extern crate` imports every macro into the global scope and depends on order. Needed only for consumers on pre-2018 editions. Relevant when the macro is used from another crate (published crates only); inside one crate use `pub(crate) use name;` after the definition.

A macro defined with `#[macro_export]` lives at the root wherever it is written. To also expose it under a module path, re-export it with a `pub use crate::name;` inside that module. The root path needs no `pub use`.

Bad:
```rust
// lib.rs: no export, consumers need #[macro_use] extern crate mylib;
macro_rules! greet {
    ($name:expr) => { println!("hello, {}", $name) };
}
```
Why: order-sensitive and pollutes the consumer's namespace.

Good:
```rust
// lib.rs
#[macro_export]
macro_rules! greet {
    ($name:expr) => { $crate::__private::print_greeting($name) };
}

#[doc(hidden)]
pub mod __private {
    pub fn print_greeting(name: &str) { println!("hello, {name}"); }
}

// optional: also reachable as mylib::macros::greet
pub mod macros {
    pub use crate::greet;
}
// consumer: use mylib::greet;  greet!("world");
```

Document exported macros with `///` like any public item.

### R-RSM-PRIVATE-HELPERS — helpers behind a hidden module

Helpers, types and third-party items that an expansion refers to must be reachable from the caller, so they are `pub`. Putting them in the public API freezes them under semver and shows them in the docs. Route every reference through `#[doc(hidden)] pub mod __private` and emit fully qualified paths (`$crate::__private::...`, or `::mycrate::__private::...` from a proc macro). Re-export third-party items there too (`pub use ::bar::Bar;`), so the caller does not need `bar` in its own `Cargo.toml`. Use one name, `__private`, in the whole repo. For a published crate state in the README that `__private` is outside semver.

Bad:
```rust
// the helper is public API and visible in the docs
pub fn __format_value(v: &dyn std::fmt::Debug) -> String { format!("{v:?}") }

#[macro_export]
macro_rules! debug_print {
    ($val:expr) => { println!("{}", $crate::__format_value(&$val)) };
}
```
Why: removing the helper later is a breaking change.

Good:
```rust
mod helpers {
    pub fn format_value(v: &dyn std::fmt::Debug) -> String { format!("{v:?}") }
}

#[doc(hidden)]
pub mod __private {
    pub use crate::helpers::format_value;
    // third-party items the expansion needs
    pub use ::serde_json;
}

#[macro_export]
macro_rules! debug_print {
    ($val:expr) => { println!("{}", $crate::__private::format_value(&$val)) };
}
```

(`serde_json` stands for any third-party crate here; re-export only what an expansion really needs.)

### R-RSM-PROC-CRATES — a thin proc-macro crate, logic elsewhere

A crate with `proc-macro = true` compiles for the host and can export only proc macros. A library that needs both a derive and ordinary items needs a facade crate that re-exports the derive. Proc-macro crates are also awkward to test, so keep the macro function a one-line shim and put the transformation in a normal crate that takes and returns `proc_macro2::TokenStream`. Tests for that logic live in that crate's `tests/` (not in `#[cfg(test)]` modules in `src/`); `trybuild` UI tests with failing inputs live in the facade's `tests/`. Both `trybuild` and snapshot crates such as `insta` are new dev-dependencies: name them in the plan. Generated code refers to `::mycrate::...`; do not try to support renamed imports.

Layout: `mycrate` (facade, re-exports the derive and defines the trait), `mycrate-derive` (`proc-macro = true`, shim), `mycrate-derive-impl` (logic, `tests/`). For a small internal macro two crates are enough: the shim and the facade, with logic in a module of the shim tested only through `trybuild`. Pin the companion crates of a published facade to the exact version (`=x.y.z`) so generated code always matches its library (published crates only).

Bad:
```rust
// one crate, proc-macro = true, also trying to export a trait
#[proc_macro_derive(Greet)]
pub fn derive_greet(input: TokenStream) -> TokenStream { todo!() }

pub trait Greet { fn greet(&self) -> String; } // error: proc-macro crate can only export macros
```
Why: a proc-macro crate cannot export anything else.

Good:
```toml
# Cargo.toml (workspace)
[workspace]
members = ["mycrate", "mycrate-derive", "mycrate-derive-impl"]
resolver = "3"

[workspace.dependencies]
mycrate-derive = { path = "mycrate-derive", version = "0.1" }
mycrate-derive-impl = { path = "mycrate-derive-impl", version = "0.1" }
syn = { version = "2", features = ["derive"] }
quote = "1"
proc-macro2 = "1"

# mycrate-derive/Cargo.toml
[package]
name = "mycrate-derive"
version = "0.1.0"
edition = "2024"

[lib]
proc-macro = true

[dependencies]
mycrate-derive-impl.workspace = true
```

```rust
// mycrate-derive/src/lib.rs: only a shim
use proc_macro::TokenStream;

#[proc_macro_derive(Greet)]
pub fn derive_greet(input: TokenStream) -> TokenStream {
    mycrate_derive_impl::derive_greet(input.into()).into()
}
```

```rust
// mycrate/src/lib.rs
pub use mycrate_derive::Greet; // derive and trait share the name, different namespaces

pub trait Greet {
    fn greet(&self) -> String;
}

#[doc(hidden)]
pub mod __private {
    pub fn format_greeting(name: &str) -> String { format!("hello, {name}") }
}
```

```rust
// mycrate-derive-impl/tests/greet.rs: runs as a normal test
use quote::quote;

#[test]
fn derive_names_the_type() {
    let out = mycrate_derive_impl::derive_greet(quote! { struct Robot; });
    assert!(out.to_string().contains("Robot"));
}
```

### R-RSM-PROC-SYN-QUOTE — syn and quote, not hand-parsed tokens

Parsing `proc_macro::TokenStream` by hand breaks on generics, attributes and visibility. `syn` parses to a typed AST, `quote` generates tokens, `proc-macro2` makes the token type usable outside the compiler (so the logic is testable, see R-RSM-PROC-CRATES). Enable only the `syn` features you use: `derive` is enough for derives, `full` adds compile time. These three crates are dependencies; adding them is a decision to state, not an implementation detail.

Bad:
```rust
use proc_macro::TokenStream;

#[proc_macro_derive(Hello)]
pub fn derive_hello(input: TokenStream) -> TokenStream {
    let mut iter = input.into_iter();
    iter.next(); // "struct", assumed
    let name = iter.next().expect("name").to_string(); // breaks on pub, attributes, generics
    format!("impl Hello for {name} {{ fn hello(&self) {{}} }}").parse().expect("valid tokens")
}
```
Why: any item that is not exactly `struct Name` produces a wrong or panicking expansion.

Good:
```rust
use proc_macro2::TokenStream;
use quote::quote;
use syn::DeriveInput;

pub fn derive_hello(input: TokenStream) -> TokenStream {
    let input: DeriveInput = match syn::parse2(input) {
        Ok(v) => v,
        Err(e) => return e.to_compile_error(),
    };
    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();
    quote! {
        impl #impl_generics ::mycrate::Hello for #name #ty_generics #where_clause {
            fn hello(&self) -> &'static str { stringify!(#name) }
        }
    }
}
```

To make an error in generated code point at the user's code, build it with `quote_spanned!` on the span of the user's token:

```rust
use quote::quote_spanned;
use syn::{spanned::Spanned, Field};

fn assert_field_is_clone(field: &Field) -> proc_macro2::TokenStream {
    let ty = &field.ty;
    quote_spanned! { ty.span() =>
        const _: fn() = || {
            fn assert_clone<T: Clone>() {}
            assert_clone::<#ty>();
        };
    }
}
```

### R-RSM-PROC-ERRORS — spanned errors, not panics

A `panic!`, `unwrap()` or `expect()` on user input gives "proc macro panicked" with little location. A `syn::Error` turned into `compile_error!` tokens points at the offending input like a normal compiler error. This is the macro-side counterpart of the repo panic policy: bad input from the user is an expected failure and returns an error; only a broken invariant inside the macro itself is a bug and may panic with a message.

Write the logic as a function returning `Result<TokenStream, syn::Error>`, convert once at the edge with `unwrap_or_else(|e| e.to_compile_error())`. Use `Error::new_spanned(tokens, msg)` to attach to input tokens, `Error::new(span, msg)` with only a span, and `Error::combine` to report several problems at once. Messages: lowercase, no trailing period.

Do not use `parse_macro_input!` inside a function that returns `Result`: it expands to an early `return` of a `TokenStream` and does not type-check there. Use `syn::parse2` (above) or `syn::parse` with `?`.

Bad:
```rust
use proc_macro::TokenStream;
use syn::{parse_macro_input, Data, DeriveInput};

#[proc_macro_derive(MyTrait)]
pub fn derive_my_trait(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let Data::Struct(s) = &input.data else {
        panic!("MyTrait can only be derived on structs"); // "proc macro panicked"
    };
    let first = s.fields.iter().next().unwrap(); // no location in user code
    let _ = first;
    TokenStream::new()
}
```
Why: the user gets no span and, with `unwrap()`, no explanation either.

Good:
```rust
use proc_macro2::TokenStream;
use quote::quote;
use syn::{Data, DeriveInput, Error};

pub fn derive_my_trait(input: TokenStream) -> TokenStream {
    expand(input).unwrap_or_else(|e| e.to_compile_error())
}

fn expand(input: TokenStream) -> Result<TokenStream, Error> {
    let input: DeriveInput = syn::parse2(input)?;
    let fields = match &input.data {
        Data::Struct(s) => &s.fields,
        Data::Enum(_) | Data::Union(_) => {
            return Err(Error::new_spanned(&input.ident, "MyTrait can only be derived on structs"));
        }
    };
    let first = fields
        .iter()
        .next()
        .ok_or_else(|| Error::new_spanned(&input.ident, "MyTrait needs at least one field"))?;
    let field_name = first
        .ident
        .as_ref()
        .ok_or_else(|| Error::new_spanned(first, "MyTrait needs named fields"))?;
    let name = &input.ident;
    Ok(quote! {
        impl ::mycrate::MyTrait for #name {
            fn first_field_name() -> &'static str { stringify!(#field_name) }
        }
    })
}
```

## Corrections to the sources

- macro-export-crate-path: the Good example ended in a bare `pub use greet;`, which does not resolve and is redundant; removed. The module re-export is shown as `pub use crate::greet;` inside a module, and the example now defines the helper it calls.
- macro-prefer-functions: the Good `double` computed `x * x` (a square) and was named double; now `x + x` with an `Add` bound.
- macro-fragment-specifiers: the follow-set note listed `|` after `expr`; it is `=>`, `,`, `;`. Edition 2024 `expr` change added.
- macro-proc-error-spans: `parse_macro_input!` inside a `Result`-returning function does not compile, and `e`/`u` were unused bindings; rewritten on `syn::parse2`.
- macro-proc-syn-quote: the `#[cfg(test)] mod tests` unit test moved to a `tests/` integration test (repo rule), `expect("named field")` on a possibly unnamed field dropped, `quote_spanned!` example replaced by the standard type assertion.
- macro-proc-two-crate: unit test location as above; a third crate for the logic added from M-PROC-IMPL; the facade no longer puts a trait in the same crate as the proc macro without saying why the names may coincide.
- macro-private-helpers: the `__private` name is fixed repo-wide (Microsoft writes `_private`).
