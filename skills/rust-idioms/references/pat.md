# Patterns (source prefix `pat-`)

Source: leonardomso/rust-skills `fd2a861a`, MIT. Rewritten; see `../NOTICE.md`.

## R-RSI-PAT-EXHAUSTIVE — match your own enums exhaustively [pat-exhaustive-enum]

A `_` arm turns "a new variant was added" from a compile error into a silent no-op. List every variant; group with `|` when handling is shared. The only place a wildcard is required is a foreign `#[non_exhaustive]` enum; comment why.

Bad:
```rust
enum Status { Active, Pending, Closed }

fn describe(s: &Status) -> &'static str {
    match s {
        Status::Active => "active",
        _ => "inactive", // Pending and any future variant land here unnoticed
    }
}
```
Why: adding `Suspended` compiles and is reported as "inactive".

Good:
```rust
fn describe(s: &Status) -> &'static str {
    match s {
        Status::Active => "active",
        Status::Pending => "pending",
        Status::Closed => "closed",
    }
}

fn is_terminal(s: &Status) -> bool {
    match s {
        Status::Closed | Status::Pending => true,
        Status::Active => false,
    }
}
```

State enums with data combine well with guards; keep every variant visible:

```rust
enum Connection {
    Disconnected,
    Connecting { attempt: u32 },
    Connected { session_id: String },
}

fn next_step(c: &Connection) -> &'static str {
    match c {
        Connection::Disconnected => "connect",
        Connection::Connecting { attempt } if *attempt > 3 => "abort",
        Connection::Connecting { .. } => "wait",
        Connection::Connected { .. } => "use",
    }
}
```

Foreign enum, wildcard required:
```rust
match event {
    their_crate::Event::Click => on_click(),
    their_crate::Event::Hover => on_hover(),
    // `Event` is #[non_exhaustive]: unknown future variants are ignored on purpose
    _ => {}
}
```

Clippy `wildcard_enum_match_arm` (restriction group) can enforce this; whether it is on is decided by the project lint config, not here.

## R-RSI-PAT-LET-ELSE — `let ... else` for early exit [pat-let-else]

Stable since 1.65. The `else` block must diverge (`return`, `continue`, `break`, `panic!`). The binding is in scope after the statement. If the else branch would only propagate an error, use `?`.

Bad:
```rust
fn process(input: Option<String>) -> Option<u32> {
    if let Some(s) = input {
        if let Ok(n) = s.trim().parse::<u32>() {
            if n > 0 {
                return Some(n * 2);
            }
        }
    }
    None
}
```
Why: each step adds a nesting level and the failure path is scattered.

Good:
```rust
fn process(input: Option<String>) -> Option<u32> {
    let s = input?;
    let Ok(n) = s.trim().parse::<u32>() else { return None };
    if n == 0 {
        return None;
    }
    Some(n * 2)
}
```

With a typed error:
```rust
fn get_id(map: &std::collections::HashMap<String, u64>, key: &str) -> Result<u64, LookupError> {
    let Some(&id) = map.get(key) else {
        return Err(LookupError::MissingKey(key.to_owned()));
    };
    Ok(id)
}
```
`LookupError` is a `thiserror` enum as in `rules/rust.md`. Clippy `manual_let_else` finds convertible code.

## R-RSI-PAT-IF-LET-CHAIN — `if let` chains [pat-if-let-chains]

Stable since Rust 1.88, edition 2024 only (`edition = "2024"` in `Cargo.toml`). `let` patterns and boolean conditions join with `&&`, evaluated left to right with short circuit.

Bad:
```rust
fn handle(input: Option<String>, limit: Option<u32>) -> Option<String> {
    if let Some(s) = input {
        if let Ok(n) = s.trim().parse::<u32>() {
            if let Some(max) = limit {
                if n <= max {
                    return Some(format!("valid: {n}"));
                }
            }
        }
    }
    None
}
```
Why: four nesting levels for one conjunction.

Good:
```rust
fn handle(input: Option<String>, limit: Option<u32>) -> Option<String> {
    if let Some(s) = input
        && let Ok(n) = s.trim().parse::<u32>()
        && let Some(max) = limit
        && n <= max
    {
        return Some(format!("valid: {n}"));
    }
    None
}
```

Plain booleans mix freely: `if cfg.debug && let Some(t) = cfg.timeout && t > 0 { ... }`. Choose `let ... else` when the goal is leaving early on failure, a chain when a body runs only if everything holds.

## R-RSI-PAT-MATCHES — `matches!` for yes/no [pat-matches-macro]

Bad:
```rust
fn is_active(s: &Status) -> bool {
    match s {
        Status::Active => true,
        _ => false,
    }
}
```
Why: five lines for a boolean; clippy `match_like_matches_macro` flags it. (This `_` is fine: the result is boolean, not a handler per variant.)

Good:
```rust
impl Status {
    pub fn is_active(&self) -> bool {
        matches!(self, Self::Active)
    }
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Closed | Self::Pending)
    }
}

fn is_positive(opt: Option<i32>) -> bool {
    matches!(opt, Some(v) if v > 0)
}
```

Use a real `match` or `if let` when the matched value is needed afterwards. `assert_matches!` is not assumed available: check your toolchain's release notes before using it; otherwise write `assert!(matches!(..))` or `let Ok(n) = r else { panic!("got {r:?}") }`.

## R-RSI-PAT-AT-BINDING — `name @ pattern` [pat-at-bindings]

Binds a value while testing it, so a range or sub-pattern is not repeated in a guard.

Bad:
```rust
match cmd {
    Command::Move { x, y } if (0..=100).contains(x) => go(*x, *y),
    _ => reject(),
}
```
Why: the range is a guard, the binding is separate.

Good:
```rust
match cmd {
    Command::Move { x: x_pos @ 0..=100, y } => go(*x_pos, *y),
    Command::Move { .. } => reject(),
}

fn classify(n: u32) -> String {
    match n {
        id @ 1..=9 => format!("single digit: {id}"),
        id @ 10..=99 => format!("two digits: {id}"),
        _ => String::from("large"), // u32 is not an enum: `_` is fine
    }
}
```
Bind the whole value while inspecting the payload: `whole @ Packet::Data(bytes) if !bytes.is_empty() => log(whole)`. Works in `match`, `if let`, `while let`, `let ... else` and parameters.

## R-RSI-PAT-COMBINATORS — combinators over a re-wrapping `match` [carried over from rust-patterns]

Bad:
```rust
fn email_of(users: &[User], id: u64) -> Option<String> {
    match users.iter().find(|u| u.id == id) {
        Some(user) => Some(user.email.clone()),
        None => None,
    }
}
```
Why: the `match` only maps `Some` to `Some`.

Good:
```rust
fn email_of(users: &[User], id: u64) -> Option<String> {
    users.iter().find(|u| u.id == id).map(|u| u.email.clone())
}
```
Use `ok_or` / `ok_or_else` to turn a missing value into a typed error, then `?`. Stop chaining when a closure needs several statements; a named function or `let ... else` reads better.
