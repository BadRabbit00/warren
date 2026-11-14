# Collections (source prefix `coll-`)

Source: leonardomso/rust-skills `fd2a861a`, MIT. Rewritten; see `../NOTICE.md`.

## R-RSI-COLL-SEQ — `Vec`, `VecDeque`, not `LinkedList` [coll-seq-choice]

`Vec` is contiguous and cache-friendly: the default. `VecDeque` is a ring buffer with O(1) push and pop at both ends. `LinkedList` allocates per node and chases pointers; it loses to both in almost every real workload.

| Need | Choose |
|---|---|
| General growable list | `Vec<T>` |
| FIFO queue, deque, sliding window | `VecDeque<T>` |
| Linked list | `LinkedList<T>` only if a benchmark proves it wins |

`Vec` and `VecDeque` convert into each other cheaply with `From`/`Into`. (The source also suggested `VecDeque` for O(1) splice at arbitrary positions; it does not give that, so the row was dropped.)

Bad:
```rust
fn process_queue(mut queue: Vec<String>) {
    while !queue.is_empty() {
        let item = queue.remove(0); // O(n): shifts every remaining element
        handle(&item);
    }
}
```
Why: n items cost O(n^2).

Good:
```rust
use std::collections::VecDeque;

fn process_queue(items: impl IntoIterator<Item = String>) {
    let mut queue: VecDeque<String> = items.into_iter().collect();
    while let Some(item) = queue.pop_front() {
        handle(&item);
    }
}
```
If you only walk the items once, front to back, iterate the `Vec` (`for item in queue`) instead of draining it.

## R-RSI-COLL-MAP — pick the map by access pattern [coll-map-choice]

| Requirement | Choose |
|---|---|
| Fast lookup, order irrelevant | `HashMap` |
| Sorted iteration, range queries | `BTreeMap` |
| Insertion order plus fast lookup | `IndexMap` (crate `indexmap`: a new dependency, name it in the task) |
| Tiny map, a handful of entries | a slice of pairs may do |

`HashMap` iteration order differs between runs. Anything that reaches a report, a snapshot, a cache key or an API response must not depend on it: use `BTreeMap`, or sort at the edge. The default hasher (SipHash) resists hash flooding; swapping it is a performance decision for non-adversarial keys, see the `rust-perf` skill.

Bad:
```rust
use std::collections::HashMap;

fn print_report(counts: &HashMap<String, usize>) {
    for (word, n) in counts {
        println!("{word}: {n}"); // order changes from run to run
    }
}
```
Why: the output is not reproducible.

Good:
```rust
use std::collections::BTreeMap;

fn word_counts(text: &str) -> BTreeMap<&str, usize> {
    let mut counts = BTreeMap::new();
    for word in text.split_whitespace() {
        *counts.entry(word).or_insert(0) += 1;
    }
    counts // sorted by word
}

fn events_in_range(log: &BTreeMap<u64, String>, start: u64, end: u64) -> Vec<(&u64, &String)> {
    log.range(start..=end).collect() // only possible because keys are sorted
}
```
Keep `HashMap` (with `entry`) when order does not matter and the map is large or hot.

## R-RSI-COLL-SET — sets for membership and dedup [coll-set-membership]

`Vec::contains` is O(n); in a loop it is O(n*m). A `HashSet` makes each test O(1) on average. `BTreeSet` adds sorted iteration and ranges. Keep a `Vec` when order or duplicates matter, or the list is tiny.

Bad:
```rust
fn deduplicate(items: Vec<String>) -> Vec<String> {
    let mut seen: Vec<String> = Vec::new();
    for item in items {
        if !seen.contains(&item) { // O(n) per item
            seen.push(item);
        }
    }
    seen
}
```
Why: quadratic.

Good:
```rust
use std::collections::{BTreeSet, HashSet};

fn find_common(all: &[String], active: &[String]) -> Vec<String> {
    let active: HashSet<&String> = active.iter().collect();
    all.iter().filter(|u| active.contains(u)).cloned().collect()
}

// dedup, first occurrence wins, order kept
fn dedup_ordered(items: Vec<String>) -> Vec<String> {
    let mut seen = HashSet::with_capacity(items.len());
    items.into_iter().filter(|s| seen.insert(s.clone())).collect()
}

// dedup into sorted unique values
fn unique_sorted(items: Vec<String>) -> Vec<String> {
    items.into_iter().collect::<BTreeSet<_>>().into_iter().collect()
}
```

## R-RSI-COLL-HEAP — `BinaryHeap` for repeated max [coll-binaryheap]

A max-heap: O(log n) `push` and `pop`, O(1) `peek`. Scanning or sorting a `Vec` on every extraction is O(n) or worse. `Reverse<T>` gives a min-heap. No priority update and no removal of an arbitrary element; use lazy deletion (skip stale entries on pop) if you need that.

| Want | How |
|---|---|
| Largest first | `BinaryHeap<T>` |
| Smallest first | `BinaryHeap<Reverse<T>>` |
| Look without removing | `.peek()` |
| All items sorted | `.into_sorted_vec()` |

Bad:
```rust
fn take_top(tasks: &mut Vec<(u32, String)>) -> Option<String> {
    let idx = tasks.iter().enumerate().max_by_key(|(_, (p, _))| *p).map(|(i, _)| i)?;
    Some(tasks.remove(idx).1) // O(n) scan plus O(n) shift on every call
}
```
Why: draining n tasks is O(n^2).

Good:
```rust
use std::cmp::Reverse;
use std::collections::BinaryHeap;

// tuples compare field by field: priority first
fn run_scheduler(tasks: impl IntoIterator<Item = (u32, String)>) {
    let mut heap: BinaryHeap<(u32, String)> = tasks.into_iter().collect();
    while let Some((priority, name)) = heap.pop() {
        run(priority, &name);
    }
}

// the k largest values, O(n log k)
fn top_k(values: &[i32], k: usize) -> Vec<i32> {
    let mut heap: BinaryHeap<Reverse<i32>> = BinaryHeap::with_capacity(k + 1);
    for &v in values {
        heap.push(Reverse(v));
        if heap.len() > k {
            heap.pop(); // drop the smallest kept value
        }
    }
    let mut out: Vec<i32> = heap.into_iter().map(|Reverse(v)| v).collect();
    out.sort_unstable_by(|a, b| b.cmp(a)); // heap iteration order is arbitrary
    out
}
```

## R-RSI-COLL-COLLECT — `collect()` into the right container [carried over from rust-patterns]

The target type drives `collect()`; annotate the binding (or use the turbofish). Collecting an iterator of `Result` or `Option` yields one `Result<Vec<_>, _>` and stops at the first failure.

Bad:
```rust
let mut parsed = Vec::new();
for s in &strings {
    match s.parse::<i32>() {
        Ok(n) => parsed.push(n),
        Err(e) => return Err(e.into()),
    }
}
```
Why: hand-written version of what `collect` already does.

Good:
```rust
let parsed: Vec<i32> = strings.iter().map(|s| s.parse()).collect::<Result<_, _>>()?;
let by_id: HashMap<_, _> = items.iter().map(|i| (i.id, i)).collect();
let joined: String = parts.iter().copied().collect();
```
Keep a loop when the body has several steps or side effects.
