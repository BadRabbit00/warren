# Const and static (source prefix `const-`)

Source: leonardomso/rust-skills `fd2a861a`, MIT. Rewritten; see `../NOTICE.md`.

## R-RSI-CONST-FN — `const fn` for pure, simple functions [const-fn]

A `const fn` can run at compile time (array lengths, `const` and `static` initialisers, const generic arguments) and at run time. Arithmetic, bit operations, conditionals, loops and slice indexing are allowed; heap allocation and most trait method calls are not. Adding `const` to a public function is not a breaking change; removing it is. Do not mark a function `const` that needs a feature unstable on your toolchain.

Bad:
```rust
fn header_len() -> usize { 4 }

fn make_buf() -> [u8; 8] {
    let buf = [0u8; header_len()]; // error: `header_len` is not a `const fn`
    buf
}
```
Why: the length must be a constant expression.

Good:
```rust
const fn header_len() -> usize { 4 }

const fn align_up(n: usize, align: usize) -> usize {
    (n + align - 1) & !(align - 1)
}

const HEADER: usize = header_len();
const ALIGNED: usize = align_up(13, 8); // 16, computed at compile time
static MAGIC: [u8; header_len()] = [0xCA, 0xFE, 0xBA, 0xBE];
```

## R-RSI-CONST-BLOCK — inline `const { }` [const-block]

Stable since 1.79. The block is evaluated at compile time wherever an expression is allowed. Uses: a build-failing assertion that depends on generic parameters; a per-element constant for arrays of non-`Copy` types. For an assertion on a plain named constant, a `const _: () = assert!(...);` item is simpler. A named `const` stays the choice for shared values.

Bad:
```rust
fn new_buckets() -> [Vec<u32>; 8] {
    [Vec::new(); 8] // error: `Vec<u32>` is not `Copy`
}

fn check<const HDR: usize, const BODY: usize>() {
    assert!(HDR + BODY <= 1500, "packet exceeds MTU"); // fails only when executed
}
```
Why: the second one passes the build and panics in production.

Good:
```rust
fn new_buckets() -> [Vec<u32>; 8] {
    [const { Vec::new() }; 8] // non-Copy element repeated through a const block
}

struct Packet<const HDR: usize, const BODY: usize>;

impl<const HDR: usize, const BODY: usize> Packet<HDR, BODY> {
    fn new() -> Self {
        const { assert!(HDR + BODY <= 1500, "packet exceeds MTU") }; // build error
        Packet
    }
}

const SIZE: usize = 64;
const _: () = assert!(SIZE.is_power_of_two());
```
The assertion fires when the generic function is instantiated with the bad values, so the error appears at the caller's build.

## R-RSI-CONST-GENERICS — const generic parameters [const-generics]

One definition for every size, no macro, no runtime length, no heap. Stable: integers, `bool`, `char` as parameter types; defaults (`<const N: usize = 64>`) since 1.59. Arbitrary expressions such as `N + 1` in types are not stable. Where `N` can be inferred from an argument, do not write it.

Bad:
```rust
fn sum_4(arr: [i32; 4]) -> i32 { arr.iter().sum() }
fn sum_8(arr: [i32; 8]) -> i32 { arr.iter().sum() }

struct Buffer {
    data: Vec<u8>,
    capacity: usize, // runtime state for a compile-time fact
}
```
Why: copies per size, or a heap allocation and a field that can disagree with reality.

Good:
```rust
fn sum<const N: usize>(arr: [i32; N]) -> i32 {
    arr.iter().sum()
}

struct Buffer<const N: usize> {
    data: [u8; N],
    len: usize,
}

impl<const N: usize> Buffer<N> {
    const fn new() -> Self {
        Self { data: [0; N], len: 0 }
    }

    fn push(&mut self, byte: u8) -> Result<(), BufferFull> {
        let Some(slot) = self.data.get_mut(self.len) else {
            return Err(BufferFull);
        };
        *slot = byte;
        self.len += 1;
        Ok(())
    }

    fn as_slice(&self) -> &[u8] {
        &self.data[..self.len]
    }
}

fn xor_block<const N: usize>(a: [u8; N], b: [u8; N]) -> [u8; N] {
    let mut out = a;
    for (o, x) in out.iter_mut().zip(b) {
        *o ^= x;
    }
    out
}
```
`BufferFull` is a unit error type (a `thiserror` enum when it crosses a crate boundary). The source returned a `bool` and indexed in a counting loop; both were replaced.

## R-RSI-CONST-VS-STATIC — `const` or `static` [const-vs-static]

`const` is substituted at each use: no address, right for small values. `static` has one address for the whole run and gives a `&'static`: right for large tables and for global state. `static mut` is not an option: taking a reference to it is denied by default in edition 2024 (`static_mut_refs`), and it is unsound with threads. Global mutable state is an atomic, `OnceLock` or `LazyLock`. Process configuration is not read inside a `static` initialiser; it comes through the project's config module.

| Situation | Use |
|---|---|
| Small number, flag, mask | `const` |
| String literal | `const` |
| Large lookup table, `&'static T` needed | `static` |
| Shared counter or flag | `static` atomic |
| Lazily built value | `static LazyLock<T>` (stable since 1.80) |
| Set once, read many | `static OnceLock<T>` |

Bad:
```rust
const LOOKUP: [u8; 4096] = [0; 4096]; // may be duplicated at each use
static mut COUNTER: u64 = 0;          // unsafe, denied by default in 2024
static TIMEOUT_MS: u64 = 5_000;       // needs no address
```
Why: wrong item kind in each line.

Good:
```rust
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{LazyLock, OnceLock};

const MAX_RETRIES: u32 = 3;
const FLAG_MASK: u8 = 0b0000_1111;

static LOOKUP: [u8; 4096] = [0; 4096];
static REQUEST_COUNT: AtomicU64 = AtomicU64::new(0);

fn record_request() {
    REQUEST_COUNT.fetch_add(1, Ordering::Relaxed);
}

static SQUARES: LazyLock<Vec<u32>> = LazyLock::new(|| (0..256).map(|n| n * n).collect());

static NODE_ID: OnceLock<String> = OnceLock::new();

fn init_node_id(id: String) {
    if NODE_ID.set(id).is_err() {
        panic!("node id initialised twice"); // a bug in start-up order
    }
}
```
