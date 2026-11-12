# API design rules

Full text of the `api-` rules (leonardomso/rust-skills), rewritten and corrected. One-line forms are in `../SKILL.md`. Examples assume edition 2024, stable Rust; errors are `thiserror` enums.

## Contents

1. [Parameters and conversions](#parameters-and-conversions)
2. [Construction](#construction)
3. [Traits on public types](#traits-on-public-types)
4. [Evolution of a public API](#evolution-of-a-public-api)
5. [Typestate](#typestate)

## Parameters and conversions

### R-RSD-FROM-NOT-INTO - implement From, never Into

Source: api-from-not-into.

`impl<T, U: From<T>> Into<U> for T` is in std, so `impl From<A> for B` gives callers both `B::from(a)` and `a.into()`, and `fn f(x: impl Into<B>)` accepts `A`. A hand-written `Into` gives only `.into()` and clippy flags it (`clippy::from_over_into`).

Bad:
```rust
struct UserId(u64);

impl Into<UserId> for u64 {
    fn into(self) -> UserId { UserId(self) }
}
// UserId::from(42) does not compile
```
Why: callers lose `From`, and `impl Into<UserId>` bounds work only by accident.

Good:
```rust
struct UserId(u64);

impl From<u64> for UserId {
    fn from(id: u64) -> Self { UserId(id) }
}

let a = UserId::from(42);
let b: UserId = 42u64.into();
```

When the target is a foreign type and the orphan rule blocks `From`, wrap it in a newtype (R-RSD-ORPHAN-NEWTYPE) instead of writing `Into`.

### R-RSD-ACCEPT-INTO - store what you are given with impl Into

Source: api-impl-into.

A parameter that ends up owned by the callee takes `impl Into<String>` (or `PathBuf`, `Box<str>`, ...) and calls `.into()` once. Callers pass `&str`, `String` or `format!(..)` without ceremony. Do not use it for a parameter you only read (R-RSD-ACCEPT-ASREF), in a hot loop where the extra monomorphisation hurts, for `dyn` values, or when the type must be named in the signature.

Bad:
```rust
fn set_name(name: String) { /* stores it */ }

set_name("Alice".to_string());
set_name(String::from("Alice"));
```
Why: every call site writes the conversion by hand.

Good:
```rust
struct Config { name: String, path: PathBuf }

impl Config {
    fn new(name: impl Into<String>) -> Self {
        Config { name: name.into(), path: PathBuf::new() }
    }

    #[must_use]
    fn path(mut self, path: impl Into<PathBuf>) -> Self {
        self.path = path.into();
        self
    }
}

let config = Config::new("myapp").path("/etc/myapp");
```

### R-RSD-ACCEPT-ASREF - borrow what you only read

Sources: api-impl-asref, conv-asmut-mutable.

`impl AsRef<T>` takes any type that can be viewed as `T` without copying: `AsRef<Path>` accepts `&str`, `String`, `Path`, `PathBuf`, `OsStr`. `AsMut<T>` is the mutable mirror. Use plain `&str` / `&[T]` when one input type is enough (the simplest signature wins). `Borrow<Q>` is `AsRef` plus the promise that `Eq` and `Hash` agree; it is what map lookups need.

| Parameter type | Use when |
|---|---|
| `&T` | one input type, simple API |
| `impl AsRef<T>` | read only, several input types (paths, strings, bytes) |
| `impl AsMut<[T]>` | writes into a caller buffer of several kinds |
| `impl Into<T>` | the value is stored |
| `Borrow<Q>` | key lookup in a map or set |

Bad:
```rust
fn read_file(path: &Path) -> std::io::Result<Vec<u8>> {
    std::fs::read(path)
}

read_file(Path::new("/etc/hosts"));   // callers wrap every &str
```
Why: callers must build a `Path` first.

Good:
```rust
fn read_file(path: impl AsRef<Path>) -> std::io::Result<Vec<u8>> {
    std::fs::read(path.as_ref())
}

read_file("/etc/hosts");
read_file(PathBuf::from("/etc/hosts"));

fn fill_zeros(mut buf: impl AsMut<[u8]>) {
    buf.as_mut().fill(0);
}

let mut v = vec![1u8, 2, 3];
fill_zeros(&mut v);          // &mut Vec<u8>
let mut a = [1u8; 4];
fill_zeros(&mut a);          // &mut [u8; 4]
```

Do not turn every `&mut T` into `AsMut`: if only one concrete type is ever passed, keep it. Do not put `AsRef` and `AsMut` on the same parameter unless the function really reads and writes.

### TryFrom and FromStr

These are the conversion rules from `conv-`; see `conv.md`.

## Construction

### R-RSD-BUILDER - a builder for many optional settings

Source: api-builder-pattern.

A constructor with five positional arguments (`Client::new(url, 30, true, None, Some(token), false)`) cannot be read. A builder names every option, has defaults, and validates in `build()`. The consuming form (`fn timeout(mut self, ..) -> Self`) is the common one; the `&mut self` form allows reuse of a half-built value. A required option with no default is checked in `build()` (returns the error) or, when forgetting it must not compile, enforced by typestate (R-RSD-TYPESTATE). A builder that fills a struct which can simply implement `Default` plus struct update syntax (`Config { retries: 5, ..Default::default() }`) is not needed.

Bad:
```rust
let client = Client::new("https://api.example.com", 30, true, None, Some("token"), false);
```
Why: nobody can tell which argument is which.

Good:
```rust
#[derive(Debug, thiserror::Error)]
pub enum BuildError {
    #[error("base_url is required")]
    MissingBaseUrl,
}

#[derive(Default)]
#[must_use = "a builder does nothing until build() is called"]
pub struct ClientBuilder {
    base_url: Option<String>,
    timeout: Option<Duration>,
    max_retries: u32,
}

impl ClientBuilder {
    pub fn new() -> Self { Self::default() }

    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = Some(url.into());
        self
    }

    pub fn timeout(mut self, timeout: Duration) -> Self {
        self.timeout = Some(timeout);
        self
    }

    pub fn max_retries(mut self, n: u32) -> Self {
        self.max_retries = n;
        self
    }

    pub fn build(self) -> Result<Client, BuildError> {
        Ok(Client {
            base_url: self.base_url.ok_or(BuildError::MissingBaseUrl)?,
            timeout: self.timeout.unwrap_or(Duration::from_secs(30)),
            max_retries: self.max_retries,
        })
    }
}
```

An infallible builder returns `T` from `build()`. For a service's own config, prefer a plain struct loaded by the config module over a hand-written builder.

### R-RSD-DEFAULT - implement Default where a default exists

Source: api-default-impl.

`Default` plugs into `Option::unwrap_or_default`, `#[derive(Default)]` on parents, `..Default::default()` and `T: Default` bounds. Derive it when every field's own default is the one you want (zero, empty, `false`, `None`). Write it by hand for a non-zero default. Per-field defaults in the struct definition (`default_field_values`) are nightly-only; do not use them. Do not implement `Default` when a field has no sensible default (an ID, a required URL): give the type a constructor instead, because a fake default hides a missing value.

Bad:
```rust
struct Config { timeout: Duration, retries: u32 }

impl Config {
    fn new() -> Self { Config { timeout: Duration::from_secs(30), retries: 3 } }
}
// Config::default() and ..Default::default() do not work
```
Why: the type does not fit the standard patterns.

Good:
```rust
struct Config { timeout: Duration, retries: u32, verbose: bool }

impl Default for Config {
    fn default() -> Self {
        Config { timeout: Duration::from_secs(30), retries: 3, verbose: false }
    }
}

let config = Config { retries: 5, ..Default::default() };

#[derive(Default)]
struct Counters { hits: u64, misses: u64 }   // zeros are the right default
```

## Traits on public types

### R-RSD-COMMON-TRAITS - derive what the type supports

Source: api-common-traits.

A public type without `Debug` cannot appear in `assert_eq!`, logs or `{:?}`; without `PartialEq` it cannot be compared in tests; without `Hash` it cannot be a map key. Start from the derive table in `../SKILL.md` and add traits by use. `Eq` is not available with floats; `Copy` requires every field to be `Copy` and is wrong for anything that owns heap data. Write `Hash` and `PartialEq` by hand together when equality is not field-wise, and keep them consistent. A type holding secrets implements `Debug` by hand with a placeholder (R-RSD-DISPLAY-DEBUG).

Bad:
```rust
pub struct Point { pub x: f64, pub y: f64 }

assert_eq!(a, b);                  // error: no PartialEq
println!("{:?}", a);               // error: no Debug
```
Why: the type cannot be tested, logged or compared.

Good:
```rust
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Point { pub x: f64, pub y: f64 }

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct EntityId(u64);

struct CaseInsensitive(String);

impl PartialEq for CaseInsensitive {
    fn eq(&self, other: &Self) -> bool { self.0.eq_ignore_ascii_case(&other.0) }
}
impl Eq for CaseInsensitive {}
impl std::hash::Hash for CaseInsensitive {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        for b in self.0.bytes() { state.write_u8(b.to_ascii_lowercase()); }
    }
}
```

Serde derives are a separate decision: see skill `rust-serde`.

### R-RSD-MUST-USE - mark values that must not be dropped

Sources: api-must-use, api-builder-must-use.

`Result`, `Option` returns of iterators and many std methods are already `#[must_use]`. Add the attribute where silently dropping the value is a bug: a method returning `Self` on a builder (or the whole builder type), a pure function whose only effect is its return value, an RAII guard. Give a message that says what to do. Do not add it where ignoring the result is normal (`HashMap::insert` returns the old value, `Vec::push` returns nothing). Applied to a type, it covers every function returning that type. Lint levels are set by `ci-engineer` in the project; do not edit lint config for this.

Bad:
```rust
impl RequestBuilder {
    fn timeout(mut self, d: Duration) -> Self { self.timeout = Some(d); self }
}

let request = RequestBuilder::new("https://api.example.com");
request.timeout(Duration::from_secs(30));   // dropped silently, no warning
request.send();
```
Why: the configuration is lost and nothing warns.

Good:
```rust
#[must_use = "builder methods return the modified builder; chain or assign it"]
struct RequestBuilder { url: String, timeout: Option<Duration> }

impl RequestBuilder {
    fn timeout(mut self, d: Duration) -> Self { self.timeout = Some(d); self }
}

#[must_use = "returns the checksum; the input is not modified"]
fn checksum(data: &[u8]) -> u32 { data.iter().map(|b| u32::from(*b)).sum() }
```

### R-RSD-EXTENSION-TRAIT - add methods to a foreign type with TypeExt

Source: api-extension-trait.

You cannot write an inherent `impl` for `Vec<u8>` or `Option<T>`, and you cannot implement a foreign trait for a foreign type. Declare your own trait with the methods and implement it for the foreign type. Name it `TypeExt`, keep it in a module, and make the caller import it: the extension is visible only where it is imported (as with `itertools::Itertools`, `tokio::io::AsyncReadExt`). When the trait should cover every type with a bound, use a blanket impl (R-RSD-BLANKET-IMPL).

Bad:
```rust
impl Vec<u8> {                       // error: cannot define inherent impl for a type outside this crate
    fn as_hex(&self) -> String { todo!() }
}
```
Why: it does not compile; the orphan rule forbids it.

Good:
```rust
pub trait ByteSliceExt {
    fn to_hex(&self) -> String;
}

impl ByteSliceExt for [u8] {
    fn to_hex(&self) -> String {
        self.iter().map(|b| format!("{b:02x}")).collect()
    }
}

use my_crate::ByteSliceExt;
assert_eq!(b"hi".as_slice().to_hex(), "6869");
```

The method is `to_hex` and not `as_hex` because it allocates (R-RSD-NAME-CONVERSIONS).

### R-RSD-OPERATORS - overload operators only when obvious

Source: api-operator-overload.

An operator is justified when any reader guesses what it does: arithmetic on numeric newtypes and vectors, `|` / `&` on sets, `+` on a string-like type, `Index` on a container. Never give an operator a side effect, I/O, or a meaning that depends on context. Implement the binary operator for owned and `&` operands so callers do not clone, and the matching `AddAssign` form. When in doubt, name a method.

| Situation | Verdict |
|---|---|
| Arithmetic on a numeric newtype or geometric type | implement |
| Set operations | implement |
| `Index` / `IndexMut` on a container | implement |
| `+` or `*` with visible side effects | never |
| Meaning depends on context the types do not capture | named method |

Bad:
```rust
impl std::ops::Add<String> for Logger {
    type Output = Logger;
    fn add(mut self, msg: String) -> Logger {
        println!("logged: {msg}");        // side effect in an operator
        self.0.push(msg);
        self
    }
}
```
Why: `logger + text` looks pure and writes to stdout.

Good:
```rust
use std::ops::{Add, AddAssign, Neg};

#[derive(Debug, Clone, Copy, PartialEq)]
struct Vector2 { x: f64, y: f64 }

impl Add for Vector2 {
    type Output = Vector2;
    fn add(self, rhs: Vector2) -> Vector2 { Vector2 { x: self.x + rhs.x, y: self.y + rhs.y } }
}
impl Add for &Vector2 {
    type Output = Vector2;
    fn add(self, rhs: &Vector2) -> Vector2 { *self + *rhs }
}
impl AddAssign for Vector2 {
    fn add_assign(&mut self, rhs: Vector2) { *self = *self + rhs; }
}
impl Neg for Vector2 {
    type Output = Vector2;
    fn neg(self) -> Vector2 { Vector2 { x: -self.x, y: -self.y } }
}
```

### R-RSD-FROMITER - collections implement FromIterator, Extend, IntoIterator

Source: api-impl-fromiterator. Published crates only; in a service, apply it when you really introduce a collection type.

A collection type should support `iter.collect::<Bag<_>>()` (`FromIterator`), `bag.extend(iter)` (`Extend`), and `for x in bag`, `for x in &bag`, `for x in &mut bag` (`IntoIterator` for the three forms). Delegate to the inner container.

Bad:
```rust
struct Bag<T>(Vec<T>);

impl<T> Bag<T> {
    fn push(&mut self, item: T) { self.0.push(item); }
}
// callers loop and push by hand; no collect(), no for loop
```
Why: the type does not take part in iterator code.

Good:
```rust
struct Bag<T>(Vec<T>);

impl<T> FromIterator<T> for Bag<T> {
    fn from_iter<I: IntoIterator<Item = T>>(iter: I) -> Self { Bag(iter.into_iter().collect()) }
}
impl<T> Extend<T> for Bag<T> {
    fn extend<I: IntoIterator<Item = T>>(&mut self, iter: I) { self.0.extend(iter); }
}
impl<T> IntoIterator for Bag<T> {
    type Item = T;
    type IntoIter = std::vec::IntoIter<T>;
    fn into_iter(self) -> Self::IntoIter { self.0.into_iter() }
}
impl<'a, T> IntoIterator for &'a Bag<T> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;
    fn into_iter(self) -> Self::IntoIter { self.0.iter() }
}
impl<'a, T> IntoIterator for &'a mut Bag<T> {
    type Item = &'a mut T;
    type IntoIter = std::slice::IterMut<'a, T>;
    fn into_iter(self) -> Self::IntoIter { self.0.iter_mut() }
}
```

## Evolution of a public API

The next three rules protect downstream crates from your changes. In a service workspace the compiler already shows every caller, so skip them.

### R-RSD-NON-EXHAUSTIVE - leave room to grow (published crates only)

Source: api-non-exhaustive.

Adding a variant to a public enum, or a field to a public struct with all-pub fields, breaks downstream code that matches exhaustively or builds the struct with a literal. `#[non_exhaustive]` forces downstream matches to have a `_` arm and forbids struct literals outside the crate, so you can add variants and fields in a minor release. It has no effect inside the defining crate. It conflicts with the rule that a `match` on your own enum lists every variant (`rules/rust.md`), so do not put it on enums that other crates of your own workspace match; use it for the error enums and option structs of a library you publish. Do not use it on complete types (`Ordering`).

Bad:
```rust
pub enum ErrorKind { NotFound, PermissionDenied }   // adding TimedOut breaks every exhaustive match
pub struct Options { pub verbose: bool }            // adding a field breaks every literal
```
Why: each addition is a semver-major change.

Good:
```rust
#[non_exhaustive]
pub enum ErrorKind { NotFound, PermissionDenied }

#[non_exhaustive]
#[derive(Default)]
pub struct Options { pub verbose: bool }

impl Options {
    pub fn new() -> Self { Self::default() }
}

// downstream
match kind {
    ErrorKind::NotFound => {}
    ErrorKind::PermissionDenied => {}
    _ => {}   // required
}
```

A single variant can also be marked `#[non_exhaustive]`; destructuring it then needs `..`.

### R-RSD-SEALED-TRAIT - only we implement it (published crates only)

Source: api-sealed-trait.

A public trait can be implemented by anyone, so adding a required method later breaks them. A sealed trait has a supertrait in a private module: downstream crates can use the trait (as a bound, in `dyn`) but cannot implement it. Seal when you control all implementors, when correctness of an implementation is hard, or when you expect to add methods. Do not seal an extension point that users are meant to implement.

| Seal when | Do not seal when |
|---|---|
| you will add methods later | users are expected to implement it |
| implementations must uphold a safety invariant | the trait is small and stable |
| the trait is a marker for your own types | it is a standard-style hook (like `Iterator`) |

Bad:
```rust
pub trait Driver {
    fn execute(&self, sql: &str) -> Result<Rows, DriverError>;
}
// a downstream impl exists; adding `fn transaction(&self)` breaks it
```
Why: the trait cannot grow without a major release.

Good:
```rust
mod private {
    pub trait Sealed {}
}

pub trait Driver: private::Sealed {
    fn execute(&self, sql: &str) -> Result<Rows, DriverError>;

    // added later: not breaking, nobody else implements Driver
    fn execute_one(&self, sql: &str) -> Result<Option<Row>, DriverError> {
        Ok(self.execute(sql)?.into_iter().next())
    }
}

pub struct Postgres;
impl private::Sealed for Postgres {}
impl Driver for Postgres {
    fn execute(&self, sql: &str) -> Result<Rows, DriverError> { todo!() }
}
```

The source also showed a "partially sealed" trait whose users could override some methods. That cannot work (a downstream crate cannot implement the trait at all), so it is dropped.

### R-RSD-SERDE-FEATURE - serde as an opt-in feature (published crates only)

Source: api-serde-optional.

A general-purpose library that makes `serde` mandatory adds compile time for every user. Make it `optional = true`, expose a `serde` feature that enables `dep:serde`, and derive with `cfg_attr`. Keep serde required when the crate is about serialisation or is an API client whose types are always sent. In a service, serde is an ordinary dependency (skill `rust-serde`). Test both configurations, `cargo test` and `cargo test --features serde`; tests live in the crate's `tests/` directory.

Bad:
```toml
[dependencies]
serde = { version = "1", features = ["derive"] }   # every user pays for it
```
Why: users who never serialise still compile serde and its derive macro.

Good:
```toml
[dependencies]
serde = { version = "1", features = ["derive"], optional = true }

[features]
serde = ["dep:serde"]
```
```rust
#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Config {
    pub name: String,
    pub value: i32,
}
```

## Typestate

### R-RSD-TYPESTATE - make invalid order a compile error

Source: api-typestate.

When a protocol has a fixed order (connect, then authenticate, then send) and misuse is a real bug, give each state its own type and make a transition a method that consumes `self` and returns the next state. A method that is only valid in one state exists only on that state's `impl`. The cost is more types and generic noise, so use it where a runtime check would otherwise guard every method (connections, transactions, request builders with a required field). Do not use it when the state lives in the database, arrives from outside, or changes dynamically: use an enum (R-RSD-ENUM-STATES). Typestate is also a way to enforce a required builder field.

Bad:
```rust
struct Connection { state: ConnectionState, socket: Option<TcpStream> }

impl Connection {
    fn send(&mut self, data: &[u8]) -> Result<(), SendError> {
        if self.state != ConnectionState::Authenticated {
            return Err(SendError::NotAuthenticated);     // found at runtime
        }
        self.socket.as_mut().expect("authenticated implies a socket").write_all(data)?;
        Ok(())
    }
}
```
Why: forgetting `authenticate` is discovered by a failing request, and `socket` is an `Option` that the state is supposed to guarantee.

Good:
```rust
struct Disconnected;
struct Connected { socket: TcpStream }
struct Authenticated { socket: TcpStream, session: Session }

struct Connection<S> { state: S }

impl Connection<Disconnected> {
    fn new() -> Self { Connection { state: Disconnected } }

    fn connect(self, addr: &str) -> Result<Connection<Connected>, ConnectError> {
        let socket = TcpStream::connect(addr)?;
        Ok(Connection { state: Connected { socket } })
    }
}

impl Connection<Connected> {
    fn authenticate(self, password: &str) -> Result<Connection<Authenticated>, AuthError> {
        let session = login(&self.state.socket, password)?;
        Ok(Connection { state: Authenticated { socket: self.state.socket, session } })
    }
}

impl Connection<Authenticated> {
    fn send(&mut self, data: &[u8]) -> std::io::Result<()> {
        self.state.socket.write_all(data)      // no check: the type proves it
    }
}

// Connection::new().connect(addr)?.send(b"x") does not compile
```

A builder follows the same shape: `RequestBuilder<NoUrl>` has `url(self, ..) -> RequestBuilder<HasUrl>`, and `build()` exists only on `RequestBuilder<HasUrl>`.

## Parse, don't validate, and newtypes

The two newtype rules from `api-` are written out in `type.md` together with their `type-` partners: `R-RSD-NEWTYPE-IDS` (api-newtype-safety, type-newtype-ids) and `R-RSD-PARSE-DONT-VALIDATE` (api-parse-dont-validate, type-newtype-validated).
