---
name: rust-async
description: Use when writing or reviewing async Rust on tokio (tasks, channels, select, locks, cancellation, blocking work) or threads and atomics. One-line rules with decision tables; full Bad/Good in references/.
---

# Rust async and concurrency

Stable Rust, edition 2024, tokio as the runtime. Complements `rules/rust.md` (R-RS-ASYNC, panic policy, `thiserror`, tests in the crate's test directory, `#[expect]`); nothing here overrides it. Crates outside `std` and `tokio` are dependencies and need approval: `tokio-util` (`CancellationToken`), `futures`, `rayon`, `loom`, `trait-variant`.

## When to use

- Writing an `async fn`, spawning tasks, or wiring channels between them.
- Using `select!`, `timeout`, `join!`, `JoinSet`, or a shutdown signal.
- Sharing state between tasks or threads (locks, atomics, thread-locals).
- Moving CPU or blocking work off the async runtime.
- Reviewing async code for deadlocks, lost data, or leaked tasks.

## Contents

1. [Blocking and the runtime](#blocking-and-the-runtime) · [references/async.md](references/async.md)
2. [Locks and shared state](#locks-and-shared-state)
3. [Cancellation](#cancellation)
4. [Futures and traits](#futures-and-traits)
5. [Running things concurrently](#running-things-concurrently)
6. [Channels](#channels)
7. [Threads and atomics](#threads-and-atomics) · [references/conc.md](references/conc.md)

## Blocking and the runtime

- R-RSA-SPAWN-BLOCKING: CPU-heavy or blocking synchronous work (hashing, compression, big parsing, a sync driver) goes into `tokio::task::spawn_blocking`; the closure takes owned data, and the `JoinError` is handled, not unwrapped. A running blocking task cannot be aborted. [async-spawn-blocking]
- R-RSA-TOKIO-FS: use `tokio::fs` in async code; for a batch of many small files, one `spawn_blocking` with `std::fs` beats many hops. `std::fs` is fine before the runtime starts. [async-tokio-fs]
- R-RSA-RUNTIME: one multi-thread runtime from `#[tokio::main]`; tune `worker_threads` / `max_blocking_threads` only after measuring; `current_thread` for tests and small tools, never as a fix for blocking code. [async-tokio-runtime]

| Work | Where |
|---|---|
| Await on I/O, timers, channels | async task |
| Short steps between awaits (tens of µs, rule of thumb) | async task |
| CPU-bound, sync library, `std::fs` batch | `spawn_blocking` |
| Parallel CPU over a collection | `rayon` inside `spawn_blocking` (or `rayon::spawn` plus `oneshot`) |
| Runs for the process lifetime | a dedicated `std::thread` |

## Locks and shared state

- R-RSA-NO-LOCK-AWAIT: never hold a lock guard across `.await`: compute or fetch first, lock briefly to update, or clone out, work, lock again. `std::sync::Mutex` for short non-awaiting sections; `tokio::sync::Mutex` only when the lock itself must guard an async resource, and then on purpose. [async-no-lock-await]
- R-RSA-SEND-BEFORE-AWAIT: state held across `.await` must be `Send`: drop `Rc`, `RefCell` borrows, `std` guards and `watch::Ref` before the await; clone the `Arc` before moving it into `spawn`. [async-clone-before-await]

| Need | Use |
|---|---|
| Counter or map touched without awaiting | `std::sync::Mutex` (`expect("mutex poisoned")`) |
| Guard an async connection or file | `tokio::sync::Mutex`, held across await on purpose |
| Many readers, rare writer | `RwLock`, same await rule |
| Single owner of the state | a task owning it plus an `mpsc` command channel |

## Cancellation

- R-RSA-CANCEL-SAFE: every `select!` branch future must be cancellation-safe, because the losing branches are dropped at once: `recv`, `changed`, `join_next`, `read` are; `read_exact`, `read_to_end`, `read_line`, `write_all` and your own multi-step futures are not. Keep partial state outside the future, pin and reuse the future, or `spawn` it. [async-cancel-safety]
- R-RSA-CANCEL-TOKEN: shut down with a `CancellationToken` (child tokens per subsystem); dropping a `JoinHandle` detaches, it does not stop the task. Handle SIGTERM as well as Ctrl+C. [async-cancellation-token]
- R-RSA-SELECT: `select!` to race different futures; a plain deadline is `tokio::time::timeout`; `biased;` only when priority matters. Branches are dropped, not "stopped at the next await". Every outgoing call has a timeout. [async-select-racing]

| Operation | Cancel-safe in `select!` |
|---|---|
| `mpsc::Receiver::recv`, `broadcast::Receiver::recv`, `watch::Receiver::changed`, `JoinSet::join_next`, `&mut oneshot::Receiver` | yes |
| `AsyncReadExt::read`, `sleep`, `mpsc::Sender::closed` | yes |
| `mpsc::Sender::send` | no data sent, but the message is dropped |
| `Mutex::lock`, `Semaphore::acquire`, `Sender::reserve` | yes, but you lose your place in the fair queue |
| `read_exact`, `read_to_end`, `read_to_string`, `read_line`, `write_all` | no |

## Futures and traits

- R-RSA-FN-IN-TRAIT: write `async fn` directly in traits; no `#[async_trait]`. Native async trait methods are not `dyn`-compatible: use generics or an enum, or return a boxed future by hand. For spawned work declare `fn f(&self) -> impl Future<Output = T> + Send`. [async-fn-in-trait]
- R-RSA-FN-BOUNDS: a callback that returns a future is bounded by `AsyncFn` / `AsyncFnMut` / `AsyncFnOnce` (stable since 1.85) and accepts `async ||` closures; when the future must be `Send` (it goes to `tokio::spawn`) use `F: Fn() -> Fut, Fut: Future + Send`. [async-async-fn-bounds]

## Running things concurrently

- R-RSA-JOIN: independent awaits run together with `tokio::join!`, fallible ones with `try_join!` (first `Err` wins, the rest are dropped); `join!` is concurrency in one task, not parallelism. A dynamic or large set uses `JoinSet`, or `buffer_unordered(n)`, never unbounded `join_all`. [async-join-parallel, async-try-join]
- R-RSA-JOINSET: a variable number of tasks lives in a `JoinSet`: results as they finish, `abort_all`, abort on drop; always look at the `JoinError` (panic or cancel). [async-joinset-structured]

| Situation | Use |
|---|---|
| Two or three fixed independent futures | `join!` / `try_join!` |
| N futures, all results, bounded | `buffer_unordered(n)` or `JoinSet` plus `Semaphore` |
| First result wins | `select!`, or `JoinSet::join_next` then `abort_all` |
| Tasks that must run on other threads | `tokio::spawn` |
| Steps depend on each other | plain sequential `.await` |

## Channels

- R-RSA-BOUNDED-CHANNEL: channels are bounded (`mpsc::channel(n)`); decide what a full channel means (wait, `try_send` and shed, or error). `unbounded_channel` needs a written reason. [async-bounded-channel]
- R-RSA-MPSC: `tokio::sync::mpsc` for task queues and for command channels to a task that owns state; never `std::sync::mpsc` in async code; drop the original sender so the receiver ends. [async-mpsc-queue]
- R-RSA-ONESHOT: one request, one answer: put a `oneshot::Sender` in the command and await the receiver, with a timeout; treat a dropped sender as "service gone". [async-oneshot-response]
- R-RSA-BROADCAST: every subscriber must see every event: `broadcast` (message is `Clone`, wrap big ones in `Arc`); handle `Lagged`. [async-broadcast-pubsub]
- R-RSA-WATCH: only the latest value matters (config, status): `watch`; copy the value out of `borrow()` before awaiting; `wait_for` to wait on a condition. [async-watch-latest]

| Channel | Receivers | Delivery | Slow receiver | Use for |
|---|---|---|---|---|
| `mpsc` | one | all, in order | backpressure | work queues, commands |
| `oneshot` | one | one value | n/a | replies |
| `broadcast` | many | all | `Lagged`, oldest lost | events |
| `watch` | many | latest only | skips values | config, state |

## Threads and atomics

- R-RSA-ATOMIC-ORDERING: `Relaxed` only for independent counters and stats; `Release` store with `Acquire` load to publish data; `SeqCst` when you cannot prove less; a `Mutex` when more than one value must stay consistent. [conc-atomic-ordering]
- R-RSA-RAYON: CPU-bound data parallelism over a collection is `rayon::par_iter` (dependency), only for non-trivial per-item work, never for I/O, and never directly on an async worker thread. [conc-rayon-par-iter]
- R-RSA-SCOPED-THREADS: a few threads borrowing local data use `std::thread::scope`, not `Arc` plus `clone`; a panicked child is a bug, so `join().expect("...")`. [conc-scoped-threads]
- R-RSA-THREAD-LOCAL: per-thread scratch state is `thread_local!` with `Cell` / `RefCell` (`const` initializer), never `static mut`; not for state that must follow an async task, which can change threads. [conc-thread-local]

Sources: leonardomso/rust-skills `async-`, `conc-`; see [NOTICE.md](NOTICE.md).
