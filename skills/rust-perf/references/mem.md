# Memory: compact types and allocation strategy

Source prefix `mem-` (leonardomso), only the rules that need a dependency or are pure optimisation. The plain ones (`with_capacity`, `reuse-collections`, `take-replace`, `clone-from`, `avoid-format`, `write-over-format`, `drop-order`, `box-large-variant`) live in `rules/rust.md` and clippy (`large_enum_variant`) and are not repeated. Rules marked (dep) add a crate: say so in the change. Crate versions below were not verified against a registry in this task; take them from the lock file or the crate's docs.

All of this follows R-RSPERF-MEASURE-FIRST: a smaller type is worth its complexity only where there are many instances.

## R-RSPERF-BOX-DST — boxed slices and strings for immutable data

Why: `Vec<T>` and `String` carry `(ptr, len, capacity)`. Data that is built once and never grows can be `Box<[T]>` / `Box<str>` (`(ptr, len)`, no spare capacity). `Arc<str>` does the same when the value is shared.

Bad:
```rust
struct Index {
    // Millions of names, never modified after loading, each with spare capacity.
    names: Vec<String>,
}
```
Why: 24 bytes per name plus unused capacity on the heap.

Good:
```rust
struct Index {
    names: Vec<Box<str>>, // 16 bytes per handle, exact allocation
}

impl Index {
    fn from_lines(lines: &[&str]) -> Self {
        Self { names: lines.iter().map(|&l| Box::from(l)).collect() }
    }
}

fn freeze(paragraphs: Vec<Paragraph>) -> Box<[Paragraph]> {
    paragraphs.into_boxed_slice() // shrinks, then drops the capacity word
}
```
Why: measured: `size_of::<String>() == 24`, `size_of::<Box<str>>() == 16` on 64-bit. Use it only when the type is internal (callers see `&str`), immutable, and instantiated in the thousands; `into_vec()` converts back. `into_boxed_*` already shrinks, so no extra `shrink_to_fit`.

## R-RSPERF-INLINE-VEC — usually-small vectors (dep)

Why: a `Vec` always allocates on first push. When most instances hold a few items, storing them inline avoids the allocation.

Bad:
```rust
fn path_components(path: &str) -> Vec<&str> {
    path.split('/').collect() // usually 2-4 parts, always heap
}
```
Why: one allocation per call for a handful of items.

Good:
```rust
use smallvec::SmallVec; // dependency: smallvec (check the lock file for the major version)

fn path_components(path: &str) -> SmallVec<[&str; 8]> {
    path.split('/').collect() // inline up to 8, spills to the heap beyond
}

use arrayvec::ArrayVec; // dependency: arrayvec

fn parse_rgb(s: &str) -> Option<ArrayVec<u8, 3>> {
    let mut out = ArrayVec::new();
    for part in s.split(',') {
        out.try_push(part.trim().parse().ok()?).ok()?; // overflow and bad input are both None
    }
    Some(out)
}
```
Why: input never panics (R-RS-PANICS): `try_push` and `parse().ok()?` instead of `push` and `unwrap`.

| Type | Heap | Use when |
|---|---|---|
| `Vec<T>` | always | size unknown, may grow |
| `SmallVec<[T; N]>` | beyond N | usually small, sometimes large |
| `ArrayVec<T, N>` | never | hard upper bound; `push` panics when full, so use `try_push` on input |
| `TinyVec<[T; N]>` | beyond N | same as SmallVec, no `unsafe` in the crate |

Choose N from measured sizes, not from a table. A `SmallVec` is larger than a `Vec` and branches on inline-or-heap at each operation, so it can lose on large or hot-iterated data. Keep large N off the stack (`ArrayVec<u8, 1_000_000>` is a megabyte of stack).

## R-RSPERF-THIN-VEC — usually-empty vectors (dep)

Why: `Vec` is 24 bytes even when empty. `thin_vec::ThinVec<T>` is one pointer (8 bytes); an empty one points to a shared static header, so it does not allocate, and `Option<ThinVec<T>>` is also 8 bytes.

Bad:
```rust
struct TreeNode {
    value: i32,
    children: Vec<TreeNode>, // most nodes are leaves: 24 bytes each for nothing
}
```
Why: leaves pay for a field they never use.

Good:
```rust
use thin_vec::ThinVec; // dependency: thin-vec

struct TreeNode {
    value: i32,
    children: ThinVec<TreeNode>, // 8 bytes; empty = no allocation
}
```
Why: millions of nodes save 16 bytes each. Length and capacity live on the heap, so iteration touches one more cache line: not for hot loops, not for a few instances. Convert with `Vec::from(thin)` / `ThinVec::from(vec)`.

## R-RSPERF-COMPACT-STRING — short strings stored inline (dep)

Why: a `String` is 24 bytes plus a heap allocation for even a three-letter value. `compact_str::CompactString` keeps short strings inline in the same 24 bytes; `ecow::EcoString` is 16 bytes and clones in O(1).

Bad:
```rust
struct User {
    id: u64,
    username: String, // usually under 20 bytes, one allocation each
    email: String,
}
```
Why: millions of users mean millions of tiny allocations.

Good:
```rust
use compact_str::CompactString; // dependency: compact_str

struct User {
    id: u64,
    username: CompactString, // short values: no heap
    email: CompactString,
}
```
Why: fewer allocations, same field size. Check the inline capacity of the pinned version with `size_of` and the crate docs (it is about the string size on 64-bit; not verified here). Keep `&str` / `String` in public APIs so callers do not inherit the dependency; do not use it for strings that are mostly edited (`String` is better optimised for that). `smartstring` is an alternative; `EcoString` fits text cloned often.

## R-RSPERF-INT-SIZES — the smallest integer that fits

Why: in arrays with millions of elements, `u64` where `u8` suffices is a factor of eight in memory and cache traffic. Applies to large collections and hot structs, not to every local.

Bad:
```rust
struct Pixel {
    r: u64,
    g: u64,
    b: u64,
    a: u64, // 32 bytes for four 8-bit channels
}
```
Why: eight times the memory of the data.

Good:
```rust
use std::num::NonZeroU64;

struct Pixel {
    r: u8,
    g: u8,
    b: u8,
    a: u8, // 4 bytes
}

struct Row {
    id: Option<NonZeroU64>, // 8 bytes; Option<u64> is 16
    status: u16,
}
```
Why: `NonZero*` gives `Option` a free niche. Convert with `u8::try_from(x)` for narrowing (no lossy `as` on input). Field order: Rust's default layout already reorders fields to minimise padding (a `{u8, u64, u8}` struct measures 16 bytes, not 24), so do not reorder by hand; `#[repr(C)]` is the case where order matters. Flag sets: a `bitflags!` type (dep) packs eight booleans into one byte.

## R-RSPERF-TYPE-SIZE-ASSERT — pin the size of hot types

Why: adding a field to a type stored by the million silently adds memory; a compile-time assertion makes the growth a decision in review.

Bad:
```rust
struct Event {
    timestamp: u64,
    id: u32,
    kind: u8,
    payload: [u8; 32],
    metadata: String, // added later: +24 bytes on ten million events, nobody noticed
}
```
Why: no check ties the size to anything.

Good:
```rust
struct Event {
    timestamp: u64,
    id: u32,
    kind: u8,
    payload: [u8; 32],
}

// Compile-time guard, next to the type. Change the number only on purpose.
const _: () = assert!(
    std::mem::size_of::<Event>() <= 48,
    "Event grew; justify the new size in review",
);
```
Why: the build fails when the size changes. Use `<=` for a budget and `==` for wire formats (`#[repr(C)]`). The source also tests sizes in a `#[cfg(test)]` module; our tests live in `<crate>/tests/` and cannot see private types, so the `const` assertion replaces that. No `static_assertions` crate is needed since `assert!` in `const` is std. Skip rarely created types.

## R-RSPERF-ARENA — bump allocation for work freed together (dep)

Why: a bump arena (`bumpalo::Bump`) allocates by moving a pointer and frees everything at once; good for parse trees and one batch of temporary nodes. The speedup depends on workload and allocator: measure it.

Bad:
```rust
fn parse(input: &str) -> Vec<Box<Node>> {
    tokenize(input)
        .map(|t| Box::new(Node::new(t))) // one heap allocation per node
        .collect()
}
```
Why: allocation cost per node, freed one by one.

Good:
```rust
use bumpalo::Bump; // dependency: bumpalo

fn parse<'a>(input: &str, arena: &'a Bump) -> Vec<&'a Node> {
    tokenize(input).map(|t| &*arena.alloc(Node::new(t))).collect()
}

fn handle(input: &str) -> Summary {
    let arena = Bump::new();      // one arena per unit of work
    let nodes = parse(input, &arena);
    summarize(&nodes)             // returns owned data; the arena drops here
}
```
Why: output is owned before the arena is dropped.

Rules of use:

- Nothing arena-allocated may escape the arena; copy out an owned result.
- `Bump` is not `Sync`: do not hold one across `.await` in a future that must be `Send` (tokio tasks), and do not keep it in `thread_local!` under tokio (a task can move between threads). Create it inside a synchronous function, or `spawn_blocking`.
- Types with a `Drop` impl are not dropped by the arena unless wrapped (`bumpalo::boxed::Box`).
- Arena-backed `Vec` / `String` come from `bumpalo::collections` (`Vec::new_in(&arena)`).

The source's thread-local scratch-arena sketch called `reset()` while the arena was still borrowed (a `RefCell` panic) and is not repeated. `reset()` needs `&mut Bump`: call it between units of work, at the owner.

| Situation | Arena? |
|---|---|
| Parsing into a tree | yes |
| One request/batch of temporaries | yes, in a sync function |
| Data that outlives the unit of work | no |
| A few allocations | no |

## R-RSPERF-ZERO-COPY — borrow, do not copy

Why: copying bytes costs allocation and memory bandwidth; slices, `Cow` and `Bytes` share the original.

Bad:
```rust
fn get_lines(data: &str) -> Vec<String> {
    data.lines().map(str::to_string).collect() // allocates per line
}

fn split_packet(buffer: &[u8]) -> Option<(Vec<u8>, Vec<u8>)> {
    let (head, body) = buffer.split_at_checked(16)?;
    Some((head.to_vec(), body.to_vec())) // two copies
}
```
Why: every line and both halves are copied though the input outlives them.

Good:
```rust
use std::borrow::Cow;

fn get_lines(data: &str) -> Vec<&str> {
    data.lines().collect()
}

fn split_packet(buffer: &[u8]) -> Option<(&[u8], &[u8])> {
    buffer.split_at_checked(16)
}

// Copy only when something changes.
fn normalize(input: &str) -> Cow<'_, str> {
    if input.contains('\t') {
        Cow::Owned(input.replace('\t', "    "))
    } else {
        Cow::Borrowed(input)
    }
}
```
Why: no allocation on the common path, and `split_at_checked` returns `None` on short input instead of panicking.

Across tasks, `bytes::Bytes` (dep, already in the tokio ecosystem) slices a shared buffer by reference count: `data.slice(0..5)` does not copy. `memchr` (dep) gives SIMD byte search without allocation. Copy when the data must outlive its source, be modified, or cross a thread without `Arc`. Zero-copy parsing structs with lifetimes (`Parsed<'a>`) make the struct borrow the input; for types that live in a cache or in a response, own the data.
