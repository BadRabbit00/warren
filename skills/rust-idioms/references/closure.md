# Closures (source prefix `closure-`)

Source: leonardomso/rust-skills `fd2a861a`, MIT. Rewritten; see `../NOTICE.md`.

## R-RSI-CLOSURE-FN-BOUNDS — weakest `Fn` trait that works [closure-fn-trait-bounds]

`Fn` implies `FnMut` implies `FnOnce`: every closure is `FnOnce`. A bound of `Fn` rejects closures that consume or mutate captures, so ask only for what the body does.

| Trait | Body does | Calls |
|---|---|---|
| `FnOnce` | may consume captures | once |
| `FnMut` | mutates captures | many, needs `mut f` |
| `Fn` | only reads captures | many, shareable |

Bad:
```rust
fn run_once<F: Fn() -> String>(f: F) -> String {
    f() // called once, yet `move || s` is rejected
}
```
Why: `Fn` is stricter than the single call needs.

Good:
```rust
fn run_once<F: FnOnce() -> String>(f: F) -> String {
    f()
}

fn retry<F: FnMut() -> bool>(mut f: F, attempts: usize) -> bool {
    (0..attempts).any(|_| f())
}

fn for_each<T, F: Fn(&T)>(items: &[T], f: F) {
    for item in items {
        f(item);
    }
}

let s = String::from("hello");
assert_eq!(run_once(move || s.to_uppercase()), "HELLO");
```
Std examples: `Iterator::map` takes `FnMut`; `thread::spawn` takes `FnOnce + Send + 'static`.

## R-RSI-CLOSURE-MOVE — `move` when the closure escapes [closure-move-capture]

A borrowing closure cannot outlive its environment. Threads, spawned tasks, returned or stored closures own their captures. If you still need the value afterwards, clone it first and move the clone. `move` changes how captures are taken, not whether the closure is `Fn` or `FnMut`.

Bad:
```rust
fn greeter(name: String) -> impl Fn() {
    || println!("hello, {name}") // error: closure may outlive `name`
}
```
Why: it borrows `name`, which dies at the end of the function.

Good:
```rust
fn greeter(name: String) -> impl Fn() {
    move || println!("hello, {name}")
}

fn spawn_and_keep(data: Vec<i32>) -> std::thread::JoinHandle<i32> {
    let for_thread = data.clone(); // only the clone is moved
    let handle = std::thread::spawn(move || for_thread.iter().sum());
    println!("still owned here: {data:?}");
    handle
}
```
Async: `tokio::spawn(async move { ... })` follows the same rule; clone shared handles (`Arc`, pool) before the block. Clone only what the closure uses.

## R-RSI-CLOSURE-CAPTURE — capture only what you use [closure-disjoint-capture]

Since edition 2021 a closure captures the minimal place it uses (`config.threshold`, not `config`), with or without `move`. A sibling field therefore stays usable. Captures stop at a dereference: `move || self.count` inside a `&self` method captures the reference `self`, not the field. Bind the value to a local first when you want a narrow capture.

Bad:
```rust
impl Worker {
    fn limiter(&self) -> impl Fn(u32) -> bool {
        move |n| n < self.limit // captures `self` (a reference); not 'static
    }
}
```
Why: the closure keeps the whole borrow of `self` alive.

Good:
```rust
struct Config {
    threshold: i32,
    label: String,
}

fn demo(config: Config) {
    let check = || config.threshold > 0;       // captures config.threshold only
    println!("label: {}", config.label);       // still usable
    assert!(check());
}

impl Worker {
    fn limiter(&self) -> impl Fn(u32) -> bool + use<> {
        let limit = self.limit;                // Copy value into a local
        move |n| n < limit                     // owns `limit`, borrows nothing
    }
}
```
The source claimed that `move || config.threshold > 0` moves all of `config`; that is wrong in edition 2021+, so the example was dropped.

## R-RSI-CLOSURE-RETURN-IMPL — return `impl Fn` [closure-impl-fn-return]

`impl Fn` in return position is statically dispatched and does not allocate. `Box<dyn Fn>` is needed when the function can return different closures, or the closure lives in a struct field or collection. A returned `FnMut` must be bound `mut` by the caller.

Bad:
```rust
fn adder(n: i32) -> Box<dyn Fn(i32) -> i32> {
    Box::new(move |x| x + n) // one concrete type, allocated for nothing
}
```
Why: heap allocation and a virtual call per use.

Good:
```rust
fn adder(n: i32) -> impl Fn(i32) -> i32 {
    move |x| x + n
}

fn counter(start: i32) -> impl FnMut() -> i32 {
    let mut n = start;
    move || {
        let current = n;
        n += 1;
        current
    }
}

// Different closures per branch need a box
fn transform(double: bool) -> Box<dyn Fn(i32) -> i32> {
    if double { Box::new(|x| x * 2) } else { Box::new(|x| x + 100) }
}

struct Pipeline {
    steps: Vec<Box<dyn Fn(i32) -> i32>>,
}

impl Pipeline {
    fn add_step(&mut self, f: impl Fn(i32) -> i32 + 'static) {
        self.steps.push(Box::new(f));
    }
    fn run(&self, value: i32) -> i32 {
        self.steps.iter().fold(value, |v, step| step(v))
    }
}
```

## R-RSI-CLOSURE-STATIC-DYN — generic or `dyn` callback [closure-static-vs-dyn]

A generic `F: Fn` is monomorphized per closure type: inlinable, no allocation, more code. `dyn` shares one copy through a vtable and is the only way to store closures of different types. Decide by use, not habit.

| Situation | Use |
|---|---|
| Hot loop, single call site | `impl Fn` / `F: Fn` |
| Callback stored in a struct | `Box<dyn Fn>` |
| Mixed closures in a collection | `Vec<Box<dyn Fn(..)>>` |
| Borrowed for one call, not stored, code size matters | `&dyn Fn` |
| Stored and called from other threads or tasks | `Box<dyn Fn(..) + Send + Sync>` |

Bad:
```rust
struct Registry<F: Fn(&str)> {
    handler: F, // one concrete closure type per registry
}
```
Why: cannot hold two different handlers.

Good:
```rust
fn transform<F: Fn(i32) -> i32>(xs: &[i32], f: F) -> Vec<i32> {
    xs.iter().map(|&x| f(x)).collect()
}

struct Registry {
    handlers: Vec<Box<dyn Fn(&str) + Send + Sync>>,
}

impl Registry {
    fn register(&mut self, handler: impl Fn(&str) + Send + Sync + 'static) {
        self.handlers.push(Box::new(handler));
    }
    fn dispatch(&self, event: &str) {
        for handler in &self.handlers {
            handler(event);
        }
    }
}

fn call_once_dyn(f: &dyn Fn() -> i32) -> i32 {
    f()
}
```
