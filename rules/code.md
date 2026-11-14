---
paths:
  - "**/*.py"
  - "**/*.go"
  - "**/*.rs"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.dart"
---

# Code shape rules

## Scope

Any source file in any language of the stack. These rules say how code reads; layering is in `layers.md`, the model ladder in `agents/coder.md`, method size in `P-CODE-METHOD-JOBS`. There is no limit on lines or nesting depth here, and no preference between classes and functions.

## Rules

- R-SHAPE-NAMES: name things from the domain, in full words; no `data`, `tmp`, `mgr`, no abbreviations the team would not say aloud.
- R-SHAPE-VERBS: name a function by what it does (`load_order`, `send_receipt`), a predicate `is_` / `has_`; where the language rule differs (Rust getters have no `get_`, Go `Name()` not `GetName()`), the language rule wins.
- R-SHAPE-ONE-JOB: a function does one job; extract a part only when it changes independently or the flow is hard to follow without a name for it.
- R-SHAPE-EARLY-RETURN: handle the failure and edge cases first and return; keep the main path flat.
- R-SHAPE-ERRORS: handle an error with the context of what was being done, or pass it up; never swallow it (no empty `except`, no `_ = err`, no `.ok()` to hide it).
- R-SHAPE-NO-IMPOSSIBLE: do not guard against cases the types, the caller or the contract already rule out; validate at the boundary only.
- R-SHAPE-NO-SINGLE-USE-ABSTRACTION: no helper, wrapper or generic for one caller; wait for the third real case.
- R-SHAPE-DUPLICATION: extract a duplicate when it appears the third time and means the same thing; between services, duplication beats shared coupling.
- R-SHAPE-NAMED-VALUES: a magic number or string with a meaning becomes a named constant at the place that owns it.
- R-SHAPE-COMMENTS: a comment explains why, a limitation or a contract, never what the next line does; no commented-out code, git keeps history.
- R-SHAPE-INJECT: pass dependencies in (arguments, constructor) instead of creating them inside; no interface for a single implementation unless tests must fake the boundary.
- R-SHAPE-PURE-CORE: keep the transformation of data apart from side effects (I/O, clock, randomness) so it can be tested without them.
- R-SHAPE-ONE-SOURCE: one place for each setting and each piece of knowledge; others read it, they do not restate it.
- R-SHAPE-LOCAL-STYLE: follow the style of the surrounding code even if you would write it differently; remove only what your own change made unused, and mention other dead code instead of deleting it.

## Examples

### R-SHAPE-EARLY-RETURN — flat main path

Bad:
```python
def ship(order):
    if order is not None:
        if order.paid:
            if order.items:
                return create_parcel(order)
    return None
```
Why: the real work sits three levels deep and the failure cases are scattered at the end.

Good:
```python
def ship(order):
    if order is None or not order.paid:
        return None
    if not order.items:
        return None
    return create_parcel(order)
```

### R-SHAPE-NO-SINGLE-USE-ABSTRACTION — wait for the third case

Bad:
```rust
trait Greeter { fn greet(&self, name: &str) -> String; }
struct PlainGreeter;
impl Greeter for PlainGreeter {
    fn greet(&self, name: &str) -> String { format!("Hello, {name}") }
}
fn welcome(g: &dyn Greeter, name: &str) -> String { g.greet(name) }
```
Why: one implementation, no test fake, three items to read instead of one line.

Good:
```rust
fn welcome(name: &str) -> String {
    format!("Hello, {name}")
}
```

### R-SHAPE-COMMENTS — say why, not what

Bad:
```go
// increment retries by one
retries++
```
Why: the comment repeats the code and will rot when the code changes.

Good:
```go
// The provider drops the first request after an idle period, so one retry is expected.
retries++
```

### R-SHAPE-VERBS — the language rule wins

Bad:
```rust
impl Order {
    pub fn get_total(&self) -> Money { self.total }
}
```
Why: Rust getters carry the field name without a verb.

Good:
```rust
impl Order {
    pub fn total(&self) -> Money { self.total }
}
```
