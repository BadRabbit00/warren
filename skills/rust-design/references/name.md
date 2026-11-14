# Naming rules

Full text of the `name-` rules (leonardomso/rust-skills), rewritten. The duplicated pair `name-iter-convention` and `name-iter-method` is one rule here, and the four casing rules and the three conversion-prefix rules are merged. Casing is also checked by `rustc` and clippy (`cargo clippy --all-targets -- -D warnings`), so these rules cost nothing to follow. `rules/rust.md` and `rules/code.md` win when they disagree.

## Contents

1. [Casing and acronyms](#casing-and-acronyms)
2. [Method prefixes](#method-prefixes)
3. [Iterators](#iterators)
4. [Generic parameters and crates](#generic-parameters-and-crates)

## Casing and acronyms

### R-RSD-NAME-CASING - the three cases

Sources: name-types-camel, name-variants-camel, name-funcs-snake, name-consts-screaming.

| Item | Case | Example |
|---|---|---|
| types, traits, enums, type aliases, enum variants | `UpperCamelCase` | `HttpClient`, `Status::InProgress` |
| functions, methods, variables, modules, fields | `snake_case` | `fetch_order`, `user_service` |
| constants, statics, associated consts | `SCREAMING_SNAKE_CASE` | `MAX_CONNECTIONS` |

The compiler warns on a violation (`non_camel_case_types`, `non_snake_case`, `non_upper_case_globals`), and the warnings fail the build under `-D warnings`. A variant name does not repeat the enum name (`ConnectionState::Connected`, not `ConnectionState::ConnectionConnected`) and is specific (`NotFound`, not `Error`). A `static` holding lazily built data is still upper case. Set `LazyLock` or `OnceLock` for compiled regexes and similar, and use `expect("static regex is valid")` for a literal that cannot fail.

Bad:
```rust
struct http_client;
enum Status { pending, COMPLETED }
fn calculateTotal() -> f64 { 0.0 }
const maxConnections: u32 = 100;
```
Why: four compiler warnings, and the reader cannot tell a type from a value.

Good:
```rust
use std::sync::LazyLock;

struct HttpClient;
enum Status { Pending, Completed }
fn calculate_total() -> f64 { 0.0 }
const MAX_CONNECTIONS: u32 = 100;
static EMAIL_RE: LazyLock<regex::Regex> =
    LazyLock::new(|| regex::Regex::new(r"^\S+@\S+$").expect("static regex is valid"));
```

### R-RSD-NAME-ACRONYM - acronyms are words

Source: name-acronym-word.

In `CamelCase` capitalise only the first letter of an acronym: `HttpServer`, `JsonParser`, `Uuid`, `TcpStream`. In `snake_case` write it in lower case: `parse_json`, `connect_tcp`. All capitals blur word boundaries (`HTTPSHandler`: `HTTPS Handler` or `HTTP SHandler`?). Two-letter acronyms follow the same rule (`IoError`, `IdGenerator`); the standard library does too.

Bad:
```rust
struct HTTPServer;
struct XMLHTTPRequest;
fn parseJSON(input: &str) {}
```
Why: unclear word boundaries, and a naming-case warning.

Good:
```rust
struct HttpServer;
struct XmlHttpRequest;
fn parse_json(input: &str) {}
```

## Method prefixes

### R-RSD-NAME-CONVERSIONS - as_, to_, into_ say what it costs

Sources: name-as-free, name-to-expensive, name-into-ownership.

| Prefix | Receiver | Cost | Returns | Examples |
|---|---|---|---|---|
| `as_` | `&self` or `&mut self` | free, O(1), no allocation | a reference or view | `as_str`, `as_bytes`, `as_slice` |
| `to_` | `&self` | allocates or computes | an owned value | `to_vec`, `to_lowercase`, `to_owned` |
| `into_` | `self` | usually free | the owned inner value or parts | `into_inner`, `into_bytes`, `into_parts` |

The prefix must tell the truth: an `as_` method that allocates, or a `to_` that only returns a reference, misleads the caller about cost and ownership. For a type with a `Display` impl, use `.to_string()` through `ToString` and do not write an inherent `to_string` (clippy `inherent_to_string`). A `fn get_inner(self)` that consumes `self` is `into_inner`.

Bad:
```rust
impl Name {
    fn as_uppercase(&self) -> String { self.0.to_uppercase() }   // allocates
    fn get_inner(self) -> String { self.0 }                       // consumes
}
```
Why: `as_` promises a free borrow and `get_` hides a move.

Good:
```rust
impl Name {
    fn as_str(&self) -> &str { &self.0 }
    fn to_uppercase(&self) -> String { self.0.to_uppercase() }
    fn into_inner(self) -> String { self.0 }
}

impl std::fmt::Display for Name {          // gives .to_string()
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str(&self.0) }
}
```

### R-RSD-NAME-NO-GET - getters carry the field name

Source: name-no-get-prefix.

A plain accessor is named after what it returns: `name()`, `len()`, `timeout()`. This is the Rust convention; it wins over the neutral "name functions with verbs" rule in `rules/code.md`. A setter is `set_timeout`. A builder method on a consuming builder is also the bare name (`timeout(mut self, ..) -> Self`). `get` is kept for lookups that can fail and return `Option` (`Vec::get`, `HashMap::get`, `get_mut`), and for methods that do real work to find the value. A boolean accessor uses `is_` (R-RSD-NAME-BOOL).

| Pattern | Name |
|---|---|
| plain field access | `name()`, `value()` |
| boolean property | `is_valid()`, `has_items()` |
| fallible lookup | `get()`, `get_mut()` |
| setter | `set_name()` |
| consuming builder step | `name(self, ..)` |

Bad:
```rust
impl User {
    fn get_name(&self) -> &str { &self.name }
    fn get_is_adult(&self) -> bool { self.age >= 18 }
}
```
Why: noise in every call, and `get_is_adult` is worse.

Good:
```rust
impl User {
    fn name(&self) -> &str { &self.name }
    fn is_adult(&self) -> bool { self.age >= 18 }
    fn set_name(&mut self, name: impl Into<String>) { self.name = name.into(); }
}
```

### R-RSD-NAME-BOOL - a bool method is a question

Source: name-is-has-bool.

A method that returns `bool` is named so that `if x.method()` reads as a sentence: `is_active`, `has_permission(perm)`, `can_edit`, `should_retry`, `needs_update`. Methods that take an argument and are already verb phrases keep their verb (`contains`, `starts_with`). Name the positive form and negate at the call site (`!user.is_active()`), not `is_inactive`. A `bool` field may be a bare adjective (`enabled`); its accessor gets the prefix.

Bad:
```rust
impl User {
    fn active(&self) -> bool { self.active }      // checks or activates?
    fn is_not_deleted(&self) -> bool { !self.deleted }
}
```
Why: ambiguous verb, and a double negative at the call site.

Good:
```rust
impl User {
    fn is_active(&self) -> bool { self.active }
    fn is_deleted(&self) -> bool { self.deleted }
    fn has_permission(&self, perm: Permission) -> bool { self.permissions.contains(&perm) }
}

if user.is_active() && !user.is_deleted() { /* ... */ }
```

## Iterators

### R-RSD-NAME-ITER - iter, iter_mut, into_iter

Sources: name-iter-convention, name-iter-method (the two are the same rule; merged).

| Method | Receiver | Yields | Use |
|---|---|---|---|
| `iter()` | `&self` | `&T` | read-only iteration |
| `iter_mut()` | `&mut self` | `&mut T` | change in place |
| `into_iter()` | `self` | `T` | consume the collection |

Implement `IntoIterator` for `T`, `&T` and `&mut T` so `for x in &c`, `for x in &mut c` and `for x in c` work (see R-RSD-FROMITER for the full set). Domain-specific iterators follow the pattern with a noun: `keys()`, `values()`, `values_mut()`, `drain()`, `iter_valid()`. Do not invent `elements()`, `iterate()`, `get_iterator()`, `as_iter()` or `to_iter()`.

Bad:
```rust
impl<T> Collection<T> {
    fn elements(&self) -> impl Iterator<Item = &T> { self.items.iter() }
    fn to_iter(self) -> impl Iterator<Item = T> { self.items.into_iter() }
}
```
Why: callers have to look up the name; `for x in &collection` does not work.

Good:
```rust
impl<T> Collection<T> {
    fn iter(&self) -> impl Iterator<Item = &T> { self.items.iter() }
    fn iter_mut(&mut self) -> impl Iterator<Item = &mut T> { self.items.iter_mut() }
}

impl<'a, T> IntoIterator for &'a Collection<T> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter { self.items.iter() }
}
```

### R-RSD-NAME-ITER-TYPES - the iterator type matches its method (published crates only)

Source: name-iter-type-match.

When you expose a named iterator type (instead of `impl Iterator`), name it after the method: `iter()` returns `Iter`, `iter_mut()` returns `IterMut`, `into_iter()` returns `IntoIter`, `keys()` returns `Keys`, `drain()` returns `Drain`; a custom `neighbors()` returns `Neighbors`. Keep them in the module of the collection, as std does. Do not call a type `Iterator` (it shadows the trait) or `I`. In a service, `impl Iterator` in the return type is the simpler choice, and no type name is needed.

Bad:
```rust
impl<T> MyCollection<T> {
    fn iter(&self) -> MyCollectionIterator<'_, T> { todo!() }
    fn keys(&self) -> KeyIterator<'_> { todo!() }
}
```
Why: the names differ from std and from each other.

Good:
```rust
pub mod my_collection {
    pub struct MyCollection<T> { items: Vec<T> }
    pub struct Iter<'a, T> { inner: std::slice::Iter<'a, T> }

    impl<T> MyCollection<T> {
        pub fn iter(&self) -> Iter<'_, T> { Iter { inner: self.items.iter() } }
    }

    impl<'a, T> Iterator for Iter<'a, T> {
        type Item = &'a T;
        fn next(&mut self) -> Option<Self::Item> { self.inner.next() }
    }
}
```

## Generic parameters and crates

### R-RSD-NAME-PARAMS - short type parameters and lifetimes

Sources: name-type-param-single, name-lifetime-short.

Type parameters are single capital letters with the conventional meaning: `T` a type, `E` an error, `K`/`V` key and value, `I` an iterator or input, `O` output, `F` a function, `S` a state. Related parameters take related letters or `T`, `U`, `V`; a long name is acceptable only when many parameters need telling apart (`Query<Db, Row>`). Lifetimes are `'a`, `'b`; use a meaningful short one only where the convention exists (`'de` for serde, `'src` for the source text, `'ctx` for a context). Let lifetime elision work and write a lifetime only when the compiler needs it. Move long bounds into a `where` clause (R-RSD-GENERIC-BOUNDS).

Bad:
```rust
struct Container<ElementType> { items: Vec<ElementType> }

fn first_word<'input_lifetime>(s: &'input_lifetime str) -> &'input_lifetime str {
    s.split_whitespace().next().unwrap_or("")
}
```
Why: noise; elision would do the lifetimes.

Good:
```rust
struct Container<T> { items: Vec<T> }

fn first_word(s: &str) -> &str {
    s.split_whitespace().next().unwrap_or("")
}

struct Lexer<'src> { source: &'src str }
```

### R-RSD-NAME-CRATE - no -rs or -rust in a crate name (published crates only)

Source: name-crate-no-rs.

On crates.io every crate is Rust, so `json-parser-rs`, `my-lib-rust` and `rust-sqlite` carry no information. Name the crate for what it does. Context is allowed when it describes the target, not the language: a binding crate named after the library (`openssl`), a platform crate (`windows-sys`), or a port of a library from another language named for the thing it ports. This does not apply to your private workspace crates.

Bad:
```toml
[package]
name = "http-client-rs"
```
Why: the suffix says nothing and makes the name longer to type.

Good:
```toml
[package]
name = "http-client"
```
