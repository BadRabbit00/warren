# Conversion rules

Full text of the `conv-` rules (leonardomso/rust-skills), rewritten. The related `api-` rules (`R-RSD-FROM-NOT-INTO`, `R-RSD-ACCEPT-INTO`, `R-RSD-ACCEPT-ASREF`) are in `api.md`. Errors are `thiserror` enums; the source examples hand-wrote `Display` and `Error`, which `thiserror` replaces.

## Contents

1. [TryFrom](#r-rsd-tryfrom---a-conversion-that-can-fail)
2. [FromStr](#r-rsd-fromstr---parse-text-into-a-type)
3. [AsMut](#asmut)

### R-RSD-TRYFROM - a conversion that can fail

Source: conv-tryfrom-fallible.

`TryFrom<T>` is the standard trait for conversions that can fail on a value; it gives callers `.try_into()?` through a blanket impl (so implement `TryFrom`, never `TryInto`), works with `?`, and composes in generic bounds (`T: TryFrom<u32>`). A private `fn port_from_u32(..) -> Result<_, String>` hides the conversion under a name nobody knows and loses the error type. Use a concrete error, a `thiserror` enum or struct, so callers can match on it. If the conversion cannot fail, implement `From`.

Bad:
```rust
struct Port(u16);

fn port_from_u32(n: u32) -> Result<Port, String> {
    if n > u16::MAX as u32 { return Err(format!("port {n} out of range")); }
    Ok(Port(n as u16))
}
```
Why: custom name, `String` error, and a lossy `as` cast that the check has to guard.

Good:
```rust
#[derive(Debug)]
struct Port(u16);

#[derive(Debug, thiserror::Error)]
#[error("port {0} is out of range (0-65535)")]
struct PortError(u32);

impl TryFrom<u32> for Port {
    type Error = PortError;

    fn try_from(value: u32) -> Result<Self, Self::Error> {
        u16::try_from(value).map(Port).map_err(|_| PortError(value))
    }
}

fn accept(n: u32) -> Result<Port, PortError> { n.try_into() }
```

### R-RSD-FROMSTR - parse text into a type

Source: conv-fromstr-parsing.

`FromStr` is the one standard hook for `&str` to a typed value: it gives `.parse::<T>()` and is what clap, config loaders and generic `T: FromStr` code look for. A private `parse_color` function does none of that. Use a concrete error type, not `String`. A type that can be parsed should also print (`Display`) so it round-trips. For an infallible wrap of a string, `From<&str>` / `From<String>` is enough. To check what the text means (an email, a URL) use the validated-newtype rule (`R-RSD-PARSE-DONT-VALIDATE`), whose `parse` constructor can also back a `FromStr` impl.

Bad:
```rust
enum Color { Red, Green }

fn parse_color(s: &str) -> Result<Color, String> {
    match s {
        "red" => Ok(Color::Red),
        "green" => Ok(Color::Green),
        other => Err(format!("unknown color: {other}")),
    }
}
```
Why: no `.parse()`, no clap integration, untyped error.

Good:
```rust
use std::str::FromStr;

#[derive(Debug, PartialEq)]
enum Color { Red, Green }

#[derive(Debug, thiserror::Error)]
#[error("unknown color: {0}")]
struct ParseColorError(String);

impl FromStr for Color {
    type Err = ParseColorError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "red" => Ok(Color::Red),
            "green" => Ok(Color::Green),
            other => Err(ParseColorError(other.to_owned())),
        }
    }
}

let c: Color = "green".parse()?;      // inside a function returning Result
```

### AsMut

`conv-asmut-mutable` (accept `impl AsMut<[T]>` instead of `&mut Vec<T>` when callers have several buffer kinds) is written out together with `AsRef` in `api.md`, rule `R-RSD-ACCEPT-ASREF`.
