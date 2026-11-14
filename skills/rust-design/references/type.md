# Type design rules

Full text of the `type-` rules plus `api-newtype-safety` and `api-parse-dont-validate` (leonardomso/rust-skills), rewritten and corrected. One-line forms are in `../SKILL.md`. Edition 2024, stable Rust; errors are `thiserror` enums.

## Contents

1. [Newtypes and validated types](#newtypes-and-validated-types)
2. [Enums, Option, Result](#enums-option-result)
3. [Markers and layout](#markers-and-layout)
4. [Traits of a type](#traits-of-a-type)
5. [Generics](#generics)

## Newtypes and validated types

### R-RSD-NEWTYPE-IDS - one type per kind of identifier

Sources: type-newtype-ids, api-newtype-safety.

`fn add_to_group(user: u64, group: u64)` accepts its arguments swapped, or a timestamp in place of an ID, and the compiler is silent. A newtype per identifier or unit turns that into a compile error at no runtime cost. In a service the ID is usually a `Uuid` or a database integer: `OrderId(Uuid)`. Derive `Debug, Clone, Copy, PartialEq, Eq, Hash` (add `Ord` when you sort or use `BTreeMap`); `Copy` only when the inner type is `Copy`, not for `String` IDs. Keep the field private when the ID has rules; make it `pub` only for a plain label. Add the derives your boundaries need: `#[serde(transparent)]` so JSON shows the bare value, and `#[sqlx(transparent)]` with `sqlx::Type` for database columns (both are dependencies the project already has or must name in its plan). Same idea for units (`Seconds` against `Milliseconds`) and for things that must never be logged (`Password`). It is overkill for a value used once in one place.

Bad:
```rust
fn add_user_to_group(user_id: u64, group_id: u64) { /* ... */ }

add_user_to_group(user.group_id, user.id);     // swapped, compiles
add_user_to_group(user.created_at, user.group_id); // a timestamp, compiles
```
Why: the bug appears in production data, not in the compiler.

Good:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[derive(serde::Serialize, serde::Deserialize)]
#[serde(transparent)]
pub struct UserId(Uuid);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct GroupId(Uuid);

impl UserId {
    pub const fn new(id: Uuid) -> Self { Self(id) }
    pub const fn get(self) -> Uuid { self.0 }
}

impl std::fmt::Display for UserId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { self.0.fmt(f) }
}

fn add_user_to_group(user: UserId, group: GroupId) { /* ... */ }
// add_user_to_group(group_id, user_id) does not compile
```

A `macro_rules!` that stamps out many ID types is fine when there are more than a few; it must use `$crate` paths if exported (skill `rust-macros`).

### R-RSD-PARSE-DONT-VALIDATE - validate once, carry the proof in the type

Sources: api-parse-dont-validate, type-newtype-validated.

A function that takes `&str` and checks `is_valid_email` is repeated in every function that receives the email, and one of them forgets. Parse at the boundary (HTTP handler, CLI, config, queue message) into a type whose only constructors validate. From there on, functions take `Email`, `Port`, `NonEmptyString`, `Percentage` and need no checks. The constructor returns `Result` with a typed error when the reason matters, `Option` when there is only one way to fail. Keep the inner field private; expose `as_str()` / `get()`. For wire formats, validate during deserialisation so invalid input never becomes a value (skill `rust-serde`: `#[serde(try_from = "String")]`). A constructor that skips validation (`new_unchecked`) is allowed only for compile-time literals and tests and must be `pub(crate)` or clearly named.

Bad:
```rust
fn send_email(to: &str) -> Result<(), MailError> {
    if !is_valid_email(to) { return Err(MailError::InvalidEmail); }   // checked here...
    smtp_send(to)
}

fn add_to_list(list: &mut Vec<String>, email: &str) {
    list.push(email.to_string());                                    // ...forgotten here
}
```
Why: validity is a convention, so one forgotten call stores bad data.

Good:
```rust
#[derive(Debug, thiserror::Error)]
#[error("invalid email address: {0:?}")]
pub struct InvalidEmail(String);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Email(String);

impl Email {
    pub fn parse(s: impl Into<String>) -> Result<Self, InvalidEmail> {
        let s = s.into();
        if s.contains('@') && s.len() > 3 { Ok(Email(s)) } else { Err(InvalidEmail(s)) }
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

fn send_email(to: &Email) -> Result<(), MailError> { smtp_send(to.as_str()) }
fn add_to_list(list: &mut Vec<Email>, email: Email) { list.push(email); }

// at the boundary, once:
fn handle(raw: RawRequest) -> Result<(), ApiError> {
    let email = Email::parse(raw.email)?;      // InvalidEmail -> ApiError via From
    process(email)
}
```

The same shape covers `Port(u16)` (non-zero), `NonEmptyString`, `Percentage(u8)`, `Url`. The simplified check above is an example, not an email validator.

### R-RSD-NO-STRINGLY - a closed set is an enum

Source: type-no-stringly.

A `&str` accepts typos, wrong case and values nobody handles, and the failure shows up at run time. Replace strings that name one of a fixed set with an enum, and strings with structure (email, URL, ID, path) with a validated newtype or the std type (`Uuid`, `Url`, `PathBuf`, `Duration`). Parse once at the boundary with `FromStr` (R-RSD-FROMSTR) or serde. Keep a string only where the data really is free text.

Bad:
```rust
fn set_status(status: &str) {
    match status {
        "pending" => {}
        "active" => {}
        other => panic!("unknown status {other}"),     // typo found in production
    }
}
set_status("aktive");
```
Why: every call can fail at run time and the compiler cannot check the match.

Good:
```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[derive(serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
enum Status { Pending, Active, Completed }

fn set_status(status: Status) {
    match status {
        Status::Pending => {}
        Status::Active => {}
        Status::Completed => {}      // adding a variant breaks the build here
    }
}
```

## Enums, Option, Result

### R-RSD-ENUM-STATES - exclusive states are an enum

Source: type-enum-states.

Several bool flags plus `Option` fields describe impossible states (`is_connected && is_disconnected`, `socket: None` while `is_connected`). An enum whose variants hold exactly the data of their state makes those states unrepresentable, and a `match` without `_` makes the compiler list every place to update. This is the default for state that is stored, loaded from a database or changed at runtime. For a state machine whose order must be enforced by the compiler use typestate (R-RSD-TYPESTATE).

Bad:
```rust
struct Task {
    is_running: bool,
    is_completed: bool,
    is_failed: bool,
    error: Option<TaskError>,
}
```
Why: eight flag combinations, three of them meaningful; `error` is `Some` or `None` independently of `is_failed`.

Good:
```rust
enum TaskState {
    Pending,
    Running { started_at: Instant },
    Completed { output: Output },
    Failed { error: TaskError },
}

struct Task { state: TaskState }

impl Task {
    fn describe(&self) -> String {
        match &self.state {
            TaskState::Pending => "pending".into(),
            TaskState::Running { started_at } => format!("running for {:?}", started_at.elapsed()),
            TaskState::Completed { .. } => "done".into(),
            TaskState::Failed { error } => format!("failed: {error}"),
        }
    }
}
```

Transitions that move data out of a state use `std::mem::replace` or `std::mem::take` on the old state, or consume `self` and return a new value.

### R-RSD-OPTION-VS-RESULT - absence, failure, or a closed outcome

Sources: type-option-nullable, type-result-fallible.

| The function can... | Return |
|---|---|
| find nothing and that is normal (lookup) | `Option<T>` |
| fail and the caller needs to know why | `Result<T, E>` with a typed error |
| end in one of a few named outcomes | an enum |
| never fail | `T` |

Do not return a sentinel (`-1`, an "empty" `User`, a null pointer), do not turn an error into `Option` with `.ok()` unless dropping the reason is deliberate, and do not panic for an expected failure. The `?` operator moves `Option`/`Result` up one level; `ok_or(Error::NotFound)?` turns an `Option` into a `Result`. Optional struct fields are `Option`; read them as `Option<&str>` with `as_deref()`. The error type is a `thiserror` enum with `#[from]` for the sources it wraps; the details of error design are in `rules/rust.md`.

Bad:
```rust
fn read_config(path: &str) -> Option<Config> {
    let content = std::fs::read_to_string(path).ok()?;   // why did it fail?
    toml::from_str(&content).ok()
}

fn divide(a: i32, b: i32) -> i32 {
    if b == 0 { return -1; }      // magic value
    a / b
}
```
Why: the caller cannot tell a missing file from a syntax error, nor a result of -1 from a division by zero.

Good:
```rust
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("cannot read config: {0}")]
    Io(#[from] std::io::Error),
    #[error("invalid config: {0}")]
    Parse(#[from] toml::de::Error),
}

fn read_config(path: &str) -> Result<Config, ConfigError> {
    let content = std::fs::read_to_string(path)?;
    Ok(toml::from_str(&content)?)
}

fn find_user(users: &HashMap<UserId, User>, id: UserId) -> Option<&User> { users.get(&id) }

let user = find_user(&users, id).ok_or(ApiError::NotFound)?;
```

### R-RSD-NEVER - say when a function does not return

Source: type-never-diverge.

`-> !` tells the compiler and the reader that the function never returns (loops forever, exits the process, always panics). `!` coerces to any type, so a diverging call fits in any `match` arm. Using `!` as a function return type has been stable since Rust 1.41; using it as a type argument (`Result<(), !>`) is nightly-only (`#![feature(never_type)]`). On stable write `std::convert::Infallible` for "this `Result` is never `Err`".

Bad:
```rust
fn run_forever() {            // looks like it returns ()
    loop { handle_next_event(); }
}
```
Why: callers and tools cannot see that nothing after the call runs.

Good:
```rust
fn run_forever() -> ! {
    loop { handle_next_event(); }
}

fn exit_with(msg: &str) -> ! {
    eprintln!("fatal: {msg}");
    std::process::exit(1)
}

fn must_load() -> Config {
    match load_config() {
        Ok(c) => c,
        Err(e) => exit_with(&e.to_string()),     // `!` coerces to Config
    }
}

type NeverFails = Result<(), std::convert::Infallible>;   // stable stand-in for Result<(), !>
```

A function that exits the process belongs in `main`/startup code; elsewhere return an error (`rules/rust.md`, panic policy).

## Markers and layout

### R-RSD-PHANTOM - PhantomData for an unused type parameter

Source: type-phantom-marker.

A type parameter that appears in no field is a compile error (`parameter T is never used`). Add a `PhantomData<..>` field: it has size zero and tells the compiler how `T` relates to the type. The form you choose sets variance, drop check and auto traits.

| You mean | Field | Notes |
|---|---|---|
| a tag, no `T` is owned (typed handle, unit marker) | `PhantomData<fn() -> T>` | covariant, always `Send + Sync` |
| the type conceptually owns a `T` (raw pointer owner) | `PhantomData<T>` | covariant, affects drop check and auto traits |
| the type borrows a `T` for `'a` | `PhantomData<&'a T>` | |
| invariant in `T` | `PhantomData<fn(T) -> T>` | |
| contravariant in `T` | `PhantomData<fn(T)>` | |

The simple `PhantomData<T>` is fine for state markers of unit structs. Do not store a throw-away `Option<T>` instead. For compile-time state machines see R-RSD-TYPESTATE.

Bad:
```rust
struct Handle<T> {
    id: u64,
    _type: Option<T>,       // stores a real Option<T> slot
}
```
Why: it wastes memory, and the type now owns a possible `T` that changes auto traits.

Good:
```rust
use std::marker::PhantomData;

struct Handle<T> {
    id: u64,
    _marker: PhantomData<fn() -> T>,
}

impl<T> Handle<T> {
    fn new(id: u64) -> Self { Handle { id, _marker: PhantomData } }
}

struct User;
struct Order;

fn load_user(h: Handle<User>) { /* ... */ }
// load_user(Handle::<Order>::new(1)) does not compile
```

### R-RSD-REPR-TRANSPARENT - same layout as the inner type, for FFI

Source: type-repr-transparent.

`#[repr(transparent)]` guarantees a single-field struct (plus zero-sized fields such as `PhantomData`) has the layout and ABI of that field. It is required when the newtype is passed through `extern "C"` and useful for `NonZero` wrappers that keep the niche. For pure-Rust newtypes it is optional. In edition 2024 `extern` blocks are written `unsafe extern`, and each item is marked `safe` or `unsafe`; the code that calls it needs a `// SAFETY:` comment (`rules/rust.md`).

Bad:
```rust
struct Handle(u64);           // layout is unspecified for the C ABI

unsafe extern "C" {
    fn process_handle(h: Handle);
}
```
Why: Rust does not promise that `Handle` is passed like a `u64`.

Good:
```rust
#[repr(transparent)]
pub struct Handle(u64);

unsafe extern "C" {
    pub safe fn handle_is_valid(h: &Handle) -> bool;
    pub unsafe fn handle_close(h: Handle);
}

impl Handle {
    pub fn close(self) {
        // SAFETY: `self` is consumed, so the handle is closed once.
        unsafe { handle_close(self) }
    }
}
```

## Traits of a type

### R-RSD-NO-DEREF-INHERITANCE - Deref is for pointers

Source: type-deref-coercion.

`Deref` is what lets `Box<T>`, `Arc<T>`, `String` (to `str`), `Vec<T>` (to `[T]`) and `MutexGuard<T>` expose the inner type's methods. Implement it when your type is a smart pointer or a transparent container. Do not use it to make `AdminUser` "inherit" from `User`: callers can no longer tell what the wrapper owns, and a new method on `User` silently changes `AdminUser`. Expose the methods you mean, or use composition with explicit delegating methods.

Bad:
```rust
struct AdminUser(User);

impl std::ops::Deref for AdminUser {
    type Target = User;
    fn deref(&self) -> &User { &self.0 }
}

fn greet(admin: &AdminUser) { println!("hello, {}", admin.name); }   // implicit
```
Why: the wrapper's public API is whatever `User` happens to have today.

Good:
```rust
struct AdminUser(User);

impl AdminUser {
    pub fn name(&self) -> &str { &self.0.name }
    pub fn can_delete_users(&self) -> bool { true }
}

struct MyBox<T>(T);
impl<T> std::ops::Deref for MyBox<T> {         // a real pointer-like wrapper
    type Target = T;
    fn deref(&self) -> &T { &self.0 }
}
```

### R-RSD-DISPLAY-DEBUG - Debug for developers, Display for users

Source: type-display-vs-debug.

`Debug` (`{:?}`) shows structure for logs, panics and test failures; derive it on every type. `Display` (`{}`) is the sentence a person reads: an error message, a CLI line. Never derive `Display` and never implement it by calling `{:?}`. `std::error::Error` needs `Display`; with `thiserror` the `#[error("...")]` attribute writes it. A type holding a secret (token, password, key) implements `Debug` by hand and prints a placeholder, so the secret cannot leak through `{:?}` in a log or a panic message. Pretty `{:#?}` is still `Debug`; use it in tests, not in user output.

Bad:
```rust
#[derive(Debug)]
struct ApiKey(String);                     // prints the key in every log line

#[derive(Debug)]
struct ParseError { input: String, line: u32 }

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self)            // user sees internal field names
    }
}
```
Why: a leaked secret and a message that is a debug dump.

Good:
```rust
struct ApiKey(String);

impl std::fmt::Debug for ApiKey {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("ApiKey([redacted])")
    }
}

#[derive(Debug, thiserror::Error)]
#[error("parse error on line {line}: {input:?}")]
struct ParseError { input: String, line: u32 }
```

### R-RSD-NUMERIC-FMT - numeric newtypes keep the hex/binary formats (published crates only)

Source: type-numeric-fmt.

A newtype around an integer that is a bit mask, address, hash or identifier should support `{:x}`, `{:X}`, `{:o}`, `{:b}` as the inner integer does, by forwarding to the inner value's trait so that flags (`#`, `0`, width) still work. Skip octal and binary when there is no reason to print the type in those bases. In a service this matters rarely; apply it when you design a reusable numeric type.

Bad:
```rust
struct Mask(u32);

impl std::fmt::Display for Mask {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}
// println!("{:x}", Mask(255)) does not compile
```
Why: callers debugging a bit mask lose `{:x}`, and `write!` ignores width and flags.

Good:
```rust
use std::fmt;

struct Mask(u32);

impl fmt::Display for Mask {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { fmt::Display::fmt(&self.0, f) }
}
impl fmt::LowerHex for Mask {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { fmt::LowerHex::fmt(&self.0, f) }
}
impl fmt::UpperHex for Mask {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { fmt::UpperHex::fmt(&self.0, f) }
}
impl fmt::Binary for Mask {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { fmt::Binary::fmt(&self.0, f) }
}

assert_eq!(format!("{:#010x}", Mask(255)), "0x000000ff");
```

## Generics

### R-RSD-GENERIC-BOUNDS - bounds where they are needed

Source: type-generic-bounds.

A bound on the struct (`struct Container<T: Clone>`) forces it on every user, even those who only store values. Put bounds on the `impl` block or the function that uses them, so that `Container<NonClone>` still exists and only `duplicate()` is missing. Use a `where` clause when a signature has more than one or two bounds, or for bounds on associated types (`I::Item: Clone`). Do not repeat a bound, and do not add `Debug`, `Send` and `'static` "just in case". A supertrait bound is implied wherever the trait is a bound. `#[derive]` already adds `T: Trait` bounds to its impls; write the impl by hand when that is too strict.

Bad:
```rust
struct Container<T: Clone + std::fmt::Debug> {     // storage requires Clone + Debug
    items: Vec<T>,
}

fn process<T: Clone + std::fmt::Debug + Send + Sync + 'static, E: std::error::Error + Send + Clone>(
    value: T,
) -> Result<T, E> { todo!() }
```
Why: the struct is unusable for types that are not `Clone`, and the signature does not fit on a line.

Good:
```rust
struct Container<T> {
    items: Vec<T>,
}

impl<T: Clone> Container<T> {
    fn duplicate(&self) -> Self { Container { items: self.items.clone() } }
}

fn process<T, E>(value: T) -> Result<T, E>
where
    T: Clone + std::fmt::Debug + Send + Sync + 'static,
    E: std::error::Error + Send,
{ todo!() }

fn longest<I>(items: I) -> Option<I::Item>
where
    I: Iterator,
    I::Item: AsRef<str>,
{ todo!() }
```
