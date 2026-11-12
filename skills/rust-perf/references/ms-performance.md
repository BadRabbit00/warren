# Performance rules from the Microsoft guidelines

Source: Microsoft Pragmatic Rust Guidelines, `performance/`. M-HOTPATH and M-FAST-HASHER are merged into `perf.md` (R-RSPERF-MEASURE-FIRST, R-RSPERF-HASHER); M-BOX-DST into `mem.md` (R-RSPERF-BOX-DST). M-THROUGHPUT is not used (its thread-per-core framing does not match our tokio services). The remaining rules are here.

## R-RSPERF-REUSE-API — let the caller own the buffer

Why: an API that returns a fresh allocation per call forces one allocation per item in a loop, invisible until profiled. Hot paths should reuse; the allocating form is a convenience wrapper over the reusing one. [M-MEM-REUSE]

Bad:
```rust
impl Db {
    pub fn get(&self, id: Id) -> Value { /* allocates a Value every call */ todo!() }
}

for id in ids {
    let value = db.get(id);
    consume(&value);
}
```
Why: one allocation per id; the caller has no way to avoid it.

Good:
```rust
impl Db {
    pub fn get_into(&self, id: Id, out: &mut Value) { /* clears and refills `out` */ }

    pub fn get(&self, id: Id) -> Value {
        let mut value = Value::default();
        self.get_into(id, &mut value);
        value
    }
}

let mut value = Value::default();
for id in ids {
    db.get_into(id, &mut value); // `Vec` inside `Value` keeps its capacity
    consume(&value);
}
```
Why: the loop allocates only while warming up. `clear()` is the canonical reset. In deep call stacks a bump arena (R-RSPERF-ARENA) can be passed down or stored in the request type.

## R-RSPERF-CAPACITY — size collections up front, trim long-lived ones

Why: a collection grown by pushing reallocates and copies several times; one built without an exact reservation and kept for a long time may hold up to about twice the memory it needs. [M-INITIAL-CAPACITY, M-SHRINK-TO-FIT]

Bad:
```rust
let mut out = Vec::new();
for x in &input {
    out.push(convert(x)); // grows repeatedly
}
CACHE.insert(key, out);   // kept for hours, capacity up to 2x length
```
Why: avoidable reallocations, then wasted memory for the life of the entry.

Good:
```rust
let out: Vec<_> = input.iter().map(convert).collect(); // size_hint reserves once
cache.insert(key, out);

// When the size is not known and the result lives long:
let mut built = Vec::with_capacity(estimate);
built.extend(stream);
built.shrink_to_fit();
cache.insert(key, built);
```
Why: `collect` reserves from `size_hint`; `with_capacity` covers estimates; `shrink_to_fit` gives memory back before storing. It is not needed after `into_boxed_slice` / `into_boxed_str` (they shrink). Applies to `String`, `HashMap`, `HashSet` too (`HashMap::with_capacity`; with a custom hasher use `with_capacity_and_hasher`).

## R-RSPERF-YIELD-POINTS — CPU-bound async work must yield

Why: a tokio worker runs a task until it awaits. A long CPU-bound stretch with no `.await` starves other tasks on that worker; I/O awaits yield on their own, pure computation does not. [M-YIELD-POINTS]

Bad:
```rust
async fn decompress_all(items: Vec<Chunk>) -> Vec<Out> {
    let mut out = Vec::new();
    for item in items {
        out.push(decompress(item)); // seconds of CPU, no await
    }
    out
}
```
Why: other requests on this worker stall until the loop ends.

Good:
```rust
async fn decompress_all(items: Vec<Chunk>) -> Vec<Out> {
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        out.push(decompress(item));
        tokio::task::yield_now().await; // let other tasks run between items
    }
    out
}

// Heavy or unbounded CPU: leave the async runtime (R-RS-ASYNC).
async fn decompress_heavy(items: Vec<Chunk>) -> Result<Vec<Out>, JoinError> {
    tokio::task::spawn_blocking(move || items.into_iter().map(decompress).collect()).await
}
```
Why: items that take microseconds can share a worker with a yield between them; anything longer goes to the blocking pool. A starting point from the source is 10-100 microseconds of work between yields, so the switching cost stays below about 1%; tune with a measurement. Yielding every item of tiny work costs more than it saves: yield every N items or after a time slice. The source mentions a `has_budget_remaining()` call that is not a tokio API; tokio's own cooperative budget is spent by its own resources (channels, sockets, timers).

## R-RSPERF-LOG-OVERHEAD — telemetry on a hot path

Why: logging and metrics are assumed to be on in production and under load. A `format!` in an event allocates per item; an event per item in an inner loop dominates a cheap loop. [M-LOG-OVERHEAD]

Bad:
```rust
for m in &messages {
    tracing::debug!("{}", format!("emitting message {}", m.id())); // allocates, one event per item
    send(m);
}
```
Why: an allocation and an event per message, inside the loop.

Good:
```rust
tracing::debug!(batch_id = %batch.id(), count = messages.len(), "emitting batch");
for m in &messages {
    send(m); // hot loop: no events
}
```
Why: structured fields instead of a built string (no allocation for the message), one event per batch; a reader reconstructs the per-message story from the batch fields or from a metric. What to log, at which level, and with which fields is skill `logging` (R-LG-*); this rule only keeps the hot loop free of it. Errors are still logged once, at the boundary.

## R-RSPERF-AVOID-INDIRECTION — no chains of Arc on hot types

Why: each `Arc` hop is a pointer to follow; two or three in a row are sequential cache misses. Porting code from garbage-collected languages often wraps every nested object in `Arc` by reflex. [M-AVOID-INDIRECTION]

Bad:
```rust
struct Item {
    config: Arc<Config>,
    payload: Payload,
}
struct Config {
    feature: Arc<Feature>,
}

impl Item {
    fn print(&self) {
        if self.config.feature.is_enabled() { /* two pointer hops per call */ }
    }
}
```
Why: `print` is hot and reads one flag through two heap hops.

Good:
```rust
struct Item {
    config: Arc<Config>,
    payload: Payload,
    enabled: bool, // lifted from config.feature when the Item is built
}

impl Item {
    fn print(&self) {
        if self.enabled { /* the flag sits next to the data */ }
    }
}
```
Why: the hot read is local. Start with embedded data and add `Arc` only where several owners genuinely share a large value. A lifted copy is valid only while the source cannot change; if it can, keep the indirection and measure.

## R-RSPERF-FUTURE-SIZE — measure hot futures

Why: values held across `.await` and the arguments of an `async fn` live inside the future's state machine. Large ones inflate every future, cost a `memcpy` when it is boxed or spawned, and add up in deep call chains. Only matters for futures created thousands of times per second. [M-ASYNC-STACK-SIZE]

Bad:
```rust
async fn handle(request: LargeRequest) -> Result<Reply, Error> {
    let buf = [0u8; 4096];           // used across the await below
    let reply = backend.call(&buf).await?;
    audit(&buf, &reply);
    Ok(reply)
}
```
Why: the 4 KiB buffer and the whole `LargeRequest` become part of the future, even if the request is only read at the start.

Good:
```rust
fn handle(request: LargeRequest) -> impl Future<Output = Result<Reply, Error>> {
    let summary = request.summarize(); // synchronous work done outside the future
    async move {
        let reply = backend.call(&summary).await?;
        audit(&summary, &reply);
        Ok(reply)
    }
}
```
Why: only `summary` is captured. Other levers: smaller types held across `.await`; boxing a rarely used large sub-future; scoping a big local so it is dropped before the await (a value with a destructor lives to the end of its block, even if unused). Guard the size in a test in `tests/` for public hot functions:
```rust
#[test]
fn handle_future_stays_small() {
    let future = my_crate::handle(my_crate::LargeRequest::default());
    assert!(std::mem::size_of_val(&future) <= 512, "future grew; see R-RSPERF-FUTURE-SIZE");
}
```
Why: the limit is set from the first measurement (the number here is an example), so growth becomes a visible change.
