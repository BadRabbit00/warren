# Trait rules

Full text of the `trait-` rules (leonardomso/rust-skills), rewritten and corrected. One-line forms are in `../SKILL.md`. Edition 2024, stable Rust.

## Contents

1. [Associated type or generic parameter](#r-rsd-assoc-type---one-output-or-many-inputs)
2. [Static or dynamic dispatch](#r-rsd-dyn-vs-generic---choose-dispatch-on-purpose)
3. [Dyn compatibility](#r-rsd-dyn-compatible---keep-a-dyn-trait-dyn-compatible)
4. [Default methods](#r-rsd-default-methods---few-required-methods-many-defaults)
5. [Blanket impls](#r-rsd-blanket-impl---behaviour-for-every-type-with-a-bound)
6. [Orphan rule and newtypes](#r-rsd-orphan-newtype---a-foreign-trait-on-a-foreign-type)

### R-RSD-ASSOC-TYPE - one output or many inputs

Source: trait-associated-type-vs-generic.

An associated type is fixed per implementing type: `Iterator::Item`, `Deref::Target`, `Future::Output`. Callers never name it, and a bound reads `P: Parser<Output = Ast>`. A generic parameter lets one type implement the trait several times with different arguments: `Add<f64>` and `Add<Vec2>` for `Vec2`, `From<A>` and `From<B>` for one target. Choose the associated type when each implementor has one natural answer; choose the parameter when a type should implement the trait for many inputs. A parameter used where one output is right forces turbofish or annotations on every call.

Bad:
```rust
trait Parser<Output> {
    fn parse(&self, input: &str) -> Option<Output>;
}

fn run<P: Parser<String>>(p: &P, s: &str) -> Option<String> { p.parse(s) }
```
Why: a parser has exactly one output type, yet every user must repeat it.

Good:
```rust
trait Parser {
    type Output;
    fn parse(&self, input: &str) -> Option<Self::Output>;
}

struct NumberParser;
impl Parser for NumberParser {
    type Output = f64;
    fn parse(&self, input: &str) -> Option<f64> { input.trim().parse().ok() }
}

fn run<P: Parser>(p: &P, s: &str) -> Option<P::Output> { p.parse(s) }

// many inputs on one type: a generic parameter is right
#[derive(Clone, Copy)]
struct Vec2 { x: f64, y: f64 }
impl std::ops::Add<Vec2> for Vec2 {
    type Output = Vec2;
    fn add(self, r: Vec2) -> Vec2 { Vec2 { x: self.x + r.x, y: self.y + r.y } }
}
impl std::ops::Add<f64> for Vec2 {
    type Output = Vec2;
    fn add(self, r: f64) -> Vec2 { Vec2 { x: self.x + r, y: self.y + r } }
}
```

### R-RSD-DYN-VS-GENERIC - choose dispatch on purpose

Source: trait-dyn-vs-generic.

Generics and `impl Trait` are monomorphised: each concrete type gets its own optimised copy, calls can be inlined, binary size grows. `dyn Trait` is a fat pointer (data + vtable): one copy of the code, one indirect call, and the only way to hold different types in one collection or to pick an implementation at run time. Default to generics. Use `dyn` for heterogeneous collections, plug-ins, and collaborators chosen by configuration (a payment gateway, a mailer). In an async service, a native `async fn` in a trait is not dyn-compatible: take the collaborator as a generic parameter, or make an enum of the implementations; do not reach for `async_trait`.

| Situation | Prefer |
|---|---|
| One known concrete type | generic / `impl Trait` |
| Hot path, inlining matters | generic |
| Different types in one `Vec` | `dyn Trait` (`Box<dyn Trait>`) |
| Implementation chosen at run time | `dyn Trait`, or an enum when the set is closed |
| Callback registered at run time | `Box<dyn Fn..>` |
| Trait has `async fn` | generic parameter or enum |
| Binary size matters more than speed | `dyn Trait` |
| Return one hidden type | `impl Trait` |

Bad:
```rust
// one concrete type is ever used, but every call goes through a vtable
fn total_area(shapes: &[Box<dyn Shape>]) -> f64 {
    shapes.iter().map(|s| s.area()).sum()
}
let shapes: Vec<Box<dyn Shape>> = circles.into_iter().map(|c| Box::new(c) as _).collect();
```
Why: allocation and indirection with no heterogeneity to pay for it.

Good:
```rust
fn total_area<S: Shape>(shapes: &[S]) -> f64 {
    shapes.iter().map(|s| s.area()).sum()
}

// really mixed: dyn is the right tool
fn total_area_mixed(shapes: &[Box<dyn Shape>]) -> f64 {
    shapes.iter().map(|s| s.area()).sum()
}
```

### R-RSD-DYN-COMPATIBLE - keep a dyn trait dyn-compatible

Source: trait-object-safety.

A trait can be used as `dyn Trait` only when every method can go through a vtable. Violations are reported at the `dyn` use site, often far from the trait. Mark a method that cannot be dispatched with `where Self: Sized`: it stays callable on concrete types and is left out of the vtable.

| Item | In `dyn Trait`? |
|---|---|
| `&self` / `&mut self` methods | yes |
| Methods taking or returning `Self` by value | no; gate with `where Self: Sized` |
| Generic methods (`fn f<T>`) | no; gate with `where Self: Sized` |
| Associated consts | no |
| Associated types | yes (fixed per impl; name it in `dyn Trait<Item = X>`) |
| `async fn` / `impl Trait` return | no; box the future by hand or use generics |
| `where Self: Sized` methods | allowed, excluded from the vtable |

Bad:
```rust
trait Transformer {
    fn transform<T: std::fmt::Debug>(&self, value: T) -> String;   // generic method
    fn name(&self) -> &str;
}

// error[E0038]: the trait `Transformer` is not dyn compatible
fn apply(t: &dyn Transformer) {}
```
Why: the trait cannot be a trait object at all.

Good:
```rust
trait Transformer {
    fn transform_str(&self, value: &str) -> String;
    fn name(&self) -> &str;

    fn transform_debug<T: std::fmt::Debug>(&self, value: T) -> String
    where
        Self: Sized,
    {
        self.transform_str(&format!("{value:?}"))
    }
}

fn apply_all(ts: &[Box<dyn Transformer>], input: &str) {
    for t in ts {
        println!("[{}] {}", t.name(), t.transform_str(input));
    }
}
```

### R-RSD-DEFAULT-METHODS - few required methods, many defaults

Source: trait-default-methods.

Make implementors write the smallest orthogonal set of methods (ideally one or two) and build the rest on top as default methods: `Iterator` needs `next` and gives `map`, `filter`, `fold`. A default may only use other methods of the trait. An implementor may override a default for speed, but it must keep the same observable behaviour. Say in the trait's doc comment which methods are required.

Bad:
```rust
trait Summarise {
    fn sentences(&self) -> Vec<String>;
    fn first_sentence(&self) -> Option<String>;   // always sentences().next()
    fn word_count(&self) -> usize;                // always derived from sentences()
}
// every implementor repeats the same two bodies
```
Why: duplicated logic that drifts apart.

Good:
```rust
trait Summarise {
    /// Required: split the text into sentences.
    fn sentences(&self) -> Vec<String>;

    fn first_sentence(&self) -> Option<String> { self.sentences().into_iter().next() }

    fn word_count(&self) -> usize {
        self.sentences().iter().map(|s| s.split_whitespace().count()).sum()
    }
}

struct Article { body: String }
impl Summarise for Article {
    fn sentences(&self) -> Vec<String> {
        self.body.split('.').map(str::trim).filter(|s| !s.is_empty()).map(str::to_owned).collect()
    }
}
```

### R-RSD-BLANKET-IMPL - behaviour for every type with a bound

Source: trait-blanket-impl.

`impl<T: Display> Describe for T` gives the method to every type that implements `Display`, as std does for `ToString`. Properties to know before writing one:

- A blanket impl overlaps with every specific impl it covers, so `impl Describe for MyType` next to it is error E0119 (stable Rust has no specialisation). If one type needs different behaviour, do not use a blanket impl, or wrap that type in a newtype.
- Adding a blanket impl to a trait that other crates can see is a breaking change (downstream impls may now overlap); so is adding a new bound to an existing one. Treat it as semver-major for published crates.
- A blanket impl lives in the crate that defines the trait.
- Combine it with a sealed trait (R-RSD-SEALED-TRAIT) when you want the behaviour but no outside implementations.

Bad:
```rust
trait Describe { fn describe(&self) -> String; }

impl Describe for i32  { fn describe(&self) -> String { format!("i32: {self}") } }
impl Describe for f64  { fn describe(&self) -> String { format!("f64: {self}") } }
impl Describe for bool { fn describe(&self) -> String { format!("bool: {self}") } }
// ...repeated for every Display type
```
Why: boilerplate that never covers the next type.

Good:
```rust
use std::fmt::Display;

trait Describe { fn describe(&self) -> String; }

impl<T: Display + ?Sized> Describe for T {
    fn describe(&self) -> String { format!("{self} ({})", std::any::type_name::<T>()) }
}

assert_eq!(42_i32.describe(), "42 (i32)");
```

### R-RSD-ORPHAN-NEWTYPE - a foreign trait on a foreign type

Source: trait-coherence-newtype.

The orphan rule says an `impl Trait for Type` needs the trait or the type to be defined in your crate; otherwise two crates could provide conflicting impls (error E0117). It holds even with type parameters. Wrap the foreign type in a local tuple struct and implement the trait on the wrapper; add `From` both ways and an `into_inner` so callers move in and out. `#[repr(transparent)]` is needed only when the layout matters (FFI, pointer casts), not for ordinary wrapping. Use the same trick to add impls to types of a dependency you do not control.

Bad:
```rust
// error[E0117]: both `Display` and `Vec` are foreign
impl std::fmt::Display for Vec<i32> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { Ok(()) }
}
```
Why: it does not compile.

Good:
```rust
use std::fmt;

struct CommaSeparated(Vec<i32>);

impl fmt::Display for CommaSeparated {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for (i, n) in self.0.iter().enumerate() {
            if i > 0 { f.write_str(", ")?; }
            write!(f, "{n}")?;
        }
        Ok(())
    }
}

impl From<Vec<i32>> for CommaSeparated { fn from(v: Vec<i32>) -> Self { Self(v) } }
impl From<CommaSeparated> for Vec<i32> { fn from(w: CommaSeparated) -> Self { w.0 } }

assert_eq!(CommaSeparated(vec![1, 2, 3]).to_string(), "1, 2, 3");
```
