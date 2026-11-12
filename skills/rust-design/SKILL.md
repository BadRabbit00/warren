---
name: rust-design
description: Use when designing or reviewing the shape of Rust code - newtypes and validated types, enums for states, typestate, builders, traits and generics versus dyn, From/TryFrom/FromStr/AsRef conversions, derives, Display/Debug, and naming (as_/to_/into_, getters, iterators, casing).
---

# Rust design

Rules for the shape of Rust types, traits, APIs and names (edition 2024, stable Rust). Rule ids `R-RSD-*`; source ids in brackets (all `api-`, `type-`, `trait-`, `conv-`, `name-` ids are leonardomso/rust-skills). Full rules with Bad/Good examples are in `references/`.

We write services first and libraries second. Rules that matter only for a crate published to other people are marked `(published crates only)`; inside a service workspace skip them. Errors are `thiserror` enums; panic policy and test location are in `rules/rust.md` and win over anything here.

## When to use

- You are adding a type, trait, builder, conversion or public function and choosing its shape.
- You review a diff for stringly-typed values, bool flags, loose IDs, needless `dyn`, or odd names.
- You name a method (`as_`, `to_`, `into_`, `get`, `is_`, `iter`) or wonder whether to derive a trait.

## Contents

1. [Decide first](#decide-first)
2. [Rules](#rules)
3. [Example](#example)
4. [Where to look](#where-to-look)

## Decide first

| Situation | Use |
|---|---|
| Value is one of several exclusive states, each with its own data | enum (`R-RSD-ENUM-STATES`) |
| Same state machine, illegal transitions must not compile, state not stored in a DB column | typestate (`R-RSD-TYPESTATE`) |
| State is loaded from the database or changes at runtime | enum, not typestate |
| Function only reads a string/path/slice | `&str`, `&Path`, `&[T]`; `impl AsRef<T>` when many input types matter |
| Function stores the argument | `impl Into<String>` / `impl Into<PathBuf>` or the owned type |
| Map or set lookup by a borrowed key | `Borrow<Q>` (the std maps already do this) |
| Each implementor has exactly one output type | associated type |
| One type implements the trait for many input types | generic parameter |
| One known type, hot path | generic / `impl Trait` |
| Mix of types chosen at runtime, plug-ins, stored collaborators | `dyn Trait` |
| Trait has `async fn` and you need `dyn` | generic parameter or an enum; native `async fn` in a trait is not dyn-compatible |
| Conversion cannot fail | `From` |
| Conversion can fail on a value | `TryFrom` |
| Conversion parses text | `FromStr` |
| Need to add methods to a foreign type | extension trait |
| Need a foreign trait on a foreign type | newtype |

Which traits to derive:

| Trait | Derive when |
|---|---|
| `Debug` | every type; hand-write it only to hide secrets |
| `Clone` | duplicating is meaningful and cheap enough to be explicit |
| `Copy` | small plain value, all fields `Copy`, no `Drop` |
| `PartialEq` + `Eq` | comparison makes sense; `Eq` unless a float is inside |
| `Hash` | used as a `HashMap` / `HashSet` key; must agree with `Eq` |
| `PartialOrd` + `Ord` | a total order exists and is meaningful |
| `Default` | an obvious empty or zero value exists |
| `Display` | never derived; write it by hand (or `thiserror`'s `#[error]`) |

## Rules

Types

- R-RSD-NEWTYPE-IDS: wrap identifiers and units in newtypes (`OrderId(Uuid)`, `Seconds(u64)`); a function taking two IDs must not accept them swapped [type-newtype-ids, api-newtype-safety]
- R-RSD-PARSE-DONT-VALIDATE: validate once at the boundary and return a type that can only hold valid data (`Email::parse`); inner code takes the type and does not re-check [api-parse-dont-validate, type-newtype-validated]
- R-RSD-NO-STRINGLY: no `&str` for a closed set of values or a structured value; use an enum, a newtype or `FromStr` at the boundary [type-no-stringly]
- R-RSD-ENUM-STATES: exclusive states are an enum whose variants carry their own data; no bool flags plus `Option` fields that allow impossible combinations [type-enum-states]
- R-RSD-OPTION-VS-RESULT: `Option` means absence, `Result` means failure with a reason, an enum means a closed set of outcomes; no sentinel values (`-1`, empty struct) [type-option-nullable, type-result-fallible]
- R-RSD-TYPESTATE: encode a protocol whose order is fixed in the type (`Conn<Open>` to `Conn<Authed>`) when misuse is a real bug; transitions consume `self` [api-typestate]
- R-RSD-PHANTOM: use `PhantomData<T>` for a type parameter no field uses; pick the form that gives the right variance and drop-check [type-phantom-marker]
- R-RSD-NEVER: a function that never returns is `-> !`; on stable use `std::convert::Infallible` where a type argument must be uninhabited [type-never-diverge]
- R-RSD-NO-DEREF-INHERITANCE: implement `Deref` only for smart pointers and transparent wrappers, never to "inherit" methods of an inner domain type [type-deref-coercion]
- R-RSD-DISPLAY-DEBUG: `Debug` is derived for developers, `Display` is written for users and for error messages; a secret's `Debug` prints a placeholder [type-display-vs-debug]
- R-RSD-GENERIC-BOUNDS: no bounds on the struct, bounds on the impl or function that needs them, `where` clauses once a signature gets long [type-generic-bounds]
- R-RSD-REPR-TRANSPARENT: `#[repr(transparent)]` on a newtype that crosses an FFI boundary; in pure Rust it is optional [type-repr-transparent]
- R-RSD-NUMERIC-FMT: a numeric newtype that is a mask, address or identifier forwards `LowerHex`, `UpperHex`, `Octal`, `Binary` to the inner value (published crates only) [type-numeric-fmt]

Traits and generics

- R-RSD-ASSOC-TYPE: an associated type when each implementor has one output; a generic parameter when one type implements the trait for many inputs [trait-associated-type-vs-generic]
- R-RSD-DYN-VS-GENERIC: generics by default; `dyn Trait` for heterogeneous collections, runtime-selected collaborators and plug-ins [trait-dyn-vs-generic]
- R-RSD-DYN-COMPATIBLE: if a trait is used as `dyn`, keep it dyn-compatible: no generic methods, no `Self` by value, no associated consts; gate the rest with `where Self: Sized` [trait-object-safety]
- R-RSD-DEFAULT-METHODS: a trait has a few required methods and defaulted ones built on them; an override keeps the same observable behaviour [trait-default-methods]
- R-RSD-BLANKET-IMPL: a blanket `impl<T: Bound> Trait for T` gives behaviour to every type with the bound; it forbids a specific impl, and adding one to a published trait is a breaking change [trait-blanket-impl]
- R-RSD-ORPHAN-NEWTYPE: to implement a foreign trait on a foreign type, wrap the type in a local newtype [trait-coherence-newtype]
- R-RSD-EXTENSION-TRAIT: add methods to a foreign type with a `TypeExt` trait that the caller imports [api-extension-trait]
- R-RSD-SEALED-TRAIT: seal a trait with a private supertrait when only your crate may implement it (published crates only) [api-sealed-trait]

Conversions and parameters

- R-RSD-FROM-NOT-INTO: implement `From`, never `Into`; `Into` comes for free [api-from-not-into]
- R-RSD-ACCEPT-INTO: a parameter that is stored is `impl Into<String>` / `impl Into<PathBuf>`, converted once inside; avoid it on hot paths and for `dyn` [api-impl-into]
- R-RSD-ACCEPT-ASREF: a parameter that is only read is `&T` or `impl AsRef<T>`; for a mutable buffer `impl AsMut<[u8]>` when several buffer types matter [api-impl-asref, conv-asmut-mutable]
- R-RSD-TRYFROM: a conversion that can fail is `TryFrom` with a concrete `thiserror` error, not a `fn to_x(..) -> Result<_, String>` [conv-tryfrom-fallible]
- R-RSD-FROMSTR: parsing text into a type is `FromStr`, so `.parse::<T>()`, clap and config readers work [conv-fromstr-parsing]
- R-RSD-FROMITER: a collection you own implements `FromIterator`, `Extend` and `IntoIterator` for `T`, `&T`, `&mut T` (published crates only) [api-impl-fromiterator]

Public API

- R-RSD-BUILDER: a type with many optional settings gets a builder that takes `self` and ends in `build() -> Result<T, BuildError>`; a required field you cannot default is checked there or by typestate [api-builder-pattern]
- R-RSD-MUST-USE: `#[must_use = "..."]` on builders, pure functions and guards whose dropped result is a bug; `Result` already has it [api-must-use, api-builder-must-use]
- R-RSD-COMMON-TRAITS: public types derive `Debug` and whatever else of the table above fits; never `Copy` on a type that owns heap data [api-common-traits]
- R-RSD-DEFAULT: implement `Default` when a sensible default exists (derive when all fields default, by hand otherwise); not when a field has no sensible default [api-default-impl]
- R-RSD-OPERATORS: overload an operator only when its meaning is obvious (numeric newtypes, vectors, sets); also implement the `*Assign` form and the `&T` form; otherwise name a method [api-operator-overload]
- R-RSD-NON-EXHAUSTIVE: `#[non_exhaustive]` on public enums and structs that will grow (published crates only); not on enums your own workspace matches exhaustively [api-non-exhaustive]
- R-RSD-SERDE-FEATURE: serde is an optional feature of a general-purpose library (published crates only); in a service it is a plain dependency [api-serde-optional]

Naming

- R-RSD-NAME-CASING: `UpperCamelCase` for types, traits and variants; `snake_case` for functions, methods, variables and modules; `SCREAMING_SNAKE_CASE` for consts and statics [name-types-camel, name-variants-camel, name-funcs-snake, name-consts-screaming]
- R-RSD-NAME-ACRONYM: acronyms are words: `HttpServer`, `Uuid`, `parse_json` [name-acronym-word]
- R-RSD-NAME-CONVERSIONS: `as_` is a free borrow, `to_` costs (allocates or computes), `into_` consumes `self`; the prefix must tell the truth [name-as-free, name-to-expensive, name-into-ownership]
- R-RSD-NAME-NO-GET: a plain getter is the field name (`name()`), a setter is `set_name`; `get` is for lookups that return `Option` [name-no-get-prefix]
- R-RSD-NAME-BOOL: methods returning `bool` read as a question: `is_`, `has_`, `can_`, `should_`; no negated names [name-is-has-bool]
- R-RSD-NAME-ITER: iterator methods are `iter()`, `iter_mut()` and `IntoIterator`; never `elements()`, `iterate()` or `get_iter()` [name-iter-convention, name-iter-method]
- R-RSD-NAME-ITER-TYPES: the iterator type is named after its method (`iter` gives `Iter`, `keys` gives `Keys`) (published crates only) [name-iter-type-match]
- R-RSD-NAME-PARAMS: type parameters are `T`, `E`, `K`, `V`, `F`; lifetimes are `'a`, `'b`, or a short meaningful `'de`, `'src`; let elision work [name-type-param-single, name-lifetime-short]
- R-RSD-NAME-CRATE: no `-rs` or `-rust` suffix or `rust-` prefix in a crate name (published crates only) [name-crate-no-rs]

## Example

Bad:
```rust
fn charge(user: u64, order: u64, currency: &str, cents: i64) -> Result<(), String> {
    if currency != "EUR" && currency != "USD" {
        return Err("bad currency".into());
    }
    // ... charge(order, user, ...) compiles just as well
    Ok(())
}
```
Why: two loose `u64`, a stringly currency and a `String` error; swapped arguments or a typo compile and fail at runtime.

Good:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UserId(Uuid);
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct OrderId(Uuid);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Currency { Eur, Usd }

#[derive(Debug, thiserror::Error)]
pub enum ChargeError {
    #[error("order {0:?} is already paid")]
    AlreadyPaid(OrderId),
}

fn charge(user: UserId, order: OrderId, currency: Currency, cents: u64) -> Result<(), ChargeError> {
    // arguments cannot be swapped, currency cannot be misspelled
    Ok(())
}
```

## Where to look

- `references/api.md` - 17 `api-` rules in full (builders, conversions, sealing, `non_exhaustive`, typestate).
- `references/type.md` - 13 `type-` rules in full (newtypes, enums, `Deref`, bounds, `Display` vs `Debug`).
- `references/trait.md` - 6 `trait-` rules in full (associated types, dyn, blanket impls, orphan rule).
- `references/conv.md` - 3 `conv-` rules in full (`TryFrom`, `FromStr`, `AsMut`).
- `references/name.md` - the `name-` rules in full, with the iterator pair merged.
- `NOTICE.md` - sources and licences.
