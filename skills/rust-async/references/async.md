# async rules in full

Adapted from leonardomso/rust-skills `async-*` (see ../NOTICE.md). Stable Rust, edition 2024, tokio. The tokio examples compile against tokio 1.54.1 and tokio-util 0.7.19; `futures`, `rayon` and `trait-variant` examples are marked as dependencies. Logging is `tracing`, not `log`.

## R-RSA-SPAWN-BLOCKING — blocking work off the async threads

A tokio worker thread that runs a long synchronous step cannot poll any other task. Hashing, compression, large parsing and sync-only drivers belong on the blocking pool. Tokio cannot abort a blocking task once it runs, and runtime shutdown waits for it, so keep each closure short. The old rule of thumb "over 1 ms is definitely blocking" is rough: what matters is the time between two `.await` points (tens of microseconds is fine).

Bad:
```rust
async fn hash_password(password: String) -> u64 {
    // CPU-heavy work on a worker thread: every other task on it stalls
    slow_hash(&password)
}
# fn slow_hash(_: &str) -> u64 { 0 }
```
Why: with a few workers, a few concurrent logins freeze the whole service.

Good:
```rust
async fn hash_password(password: String) -> Result<u64, tokio::task::JoinError> {
    tokio::task::spawn_blocking(move || slow_hash(&password)).await
}
# fn slow_hash(_: &str) -> u64 { 0 }
```
The `JoinError` means the closure panicked (a bug) or the runtime is shutting down; map it into your `thiserror` enum instead of `unwrap()`.

Parallel CPU work over a collection: run `rayon` inside the closure (see R-RSA-RAYON). Blocking threads default to 512 (`max_blocking_threads`); a pool that large hides a design that blocks too much.

## R-RSA-TOKIO-FS — tokio::fs, or one blocking hop

`tokio::fs` runs each operation on the blocking pool, so it keeps the executor free but costs one hop per call.

Bad:
```rust
async fn read_all(paths: &[std::path::PathBuf]) -> std::io::Result<Vec<String>> {
    let mut out = Vec::new();
    for p in paths {
        out.push(std::fs::read_to_string(p)?); // blocks the worker thread
    }
    Ok(out)
}
```
Why: the thread cannot run other tasks while the syscall waits.

Good:
```rust
async fn read_one(path: &std::path::Path) -> std::io::Result<String> {
    tokio::fs::read_to_string(path).await
}

// many small files: one hop, plain std::fs inside
async fn read_many(paths: Vec<std::path::PathBuf>) -> std::io::Result<Vec<String>> {
    tokio::task::spawn_blocking(move || paths.iter().map(std::fs::read_to_string).collect())
        .await
        .expect("blocking read task panicked")
}
```
`std::fs` is acceptable in `main` before the runtime starts (reading config). A `current_thread` runtime does not make blocking calls harmless: it has only one thread to stall. Dropped from the source: "std::fs is acceptable on current_thread".

## R-RSA-RUNTIME — one runtime, measured tuning

`#[tokio::main]` (multi-thread, one worker per core) fits services. `current_thread` suits tests and small tools. Custom `Builder` settings are for a measured problem.

Bad:
```rust
// two runtimes to "separate" CPU and I/O: extra threads, no isolation from bad code
struct App { io: tokio::runtime::Runtime, cpu: tokio::runtime::Runtime }
```
Why: async worker threads must never run CPU loops; a second runtime does not fix that, `spawn_blocking` does.

Good:
```rust
fn main() -> std::io::Result<()> {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("app-worker")
        .build()?;
    runtime.block_on(run())
}
# async fn run() -> std::io::Result<()> { Ok(()) }
```

| Runtime | Use |
|---|---|
| Multi-thread (default) | services, many connections |
| `current_thread` | tests (`#[tokio::test]`), small CLIs, `LocalSet` code |
| Custom `Builder` | named threads, shutdown hooks, measured `worker_threads` or `max_blocking_threads` |

Dropped from the source: oversubscribing workers at twice the core count for I/O (async I/O does not park worker threads, so extra workers only add context switches) and the two-runtime `App` struct. Async tests belong in the crate's test directory.

## R-RSA-NO-LOCK-AWAIT — no guard across await

A guard held over `.await` keeps everyone else waiting for as long as the awaited operation takes. With `std::sync::Mutex` the future is also not `Send` (the compile error shows up at `tokio::spawn`) and can deadlock the worker thread.

Bad:
```rust
async fn update(state: &tokio::sync::Mutex<State>) {
    let mut guard = state.lock().await;
    guard.value = fetch_from_network().await; // lock held while waiting on the network
}
# struct State { value: u64, id: String }
# async fn fetch_from_network() -> u64 { 1 }
```
Why: every other task that needs `state` waits for the network call.

Good:
```rust
async fn update(state: &tokio::sync::Mutex<State>) {
    let id = state.lock().await.id.clone();   // guard dropped at the end of the statement
    let data = fetch_by_id(id).await;         // no lock
    state.lock().await.value = data;          // short critical section
}
# struct State { value: u64, id: String }
# async fn fetch_by_id(_: String) -> u64 { 2 }
```
Caveat: releasing and re-taking the lock means the state can change in between; if the check and the update must be atomic, let one task own the state and send it commands (R-RSA-MPSC), or hold a `tokio::sync::Mutex` deliberately (it is the right tool for guarding an async connection).

```rust
async fn quick_update(state: &std::sync::Mutex<Counter>) {
    state.lock().expect("counter mutex poisoned").hits += 1; // no await inside the scope
}
# struct Counter { hits: u64 }
```
Prefer `std::sync::Mutex` for sections without `.await`; `RwLock` follows the same rule. A cheap way to see the problem: the clippy lints `await_holding_lock` and `await_holding_refcell_ref` flag it.

## R-RSA-SEND-BEFORE-AWAIT — hold only Send state across await

`tokio::spawn` needs a `Send` future, so everything alive at an `.await` must be `Send`. The usual offenders are `Rc`, `RefCell` borrows, `std` mutex guards and `watch::Ref`. Rewritten: the source claimed that a borrow of `Arc` contents (`&[Item]`) is not `Send` and that cloning the data fixes it; a shared reference to `Sync` data is `Send`, and cloning a `Vec` just to hold it across an await is waste. Cloning the `Arc` handle into a spawned task is the real pattern.

Bad:
```rust
async fn run(rc: std::rc::Rc<u32>) {
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    println!("{rc}"); // Rc lives across the await: future is !Send
}
// tokio::spawn(run(rc)); // does not compile
```
Why: the task may resume on another thread, and `Rc` must not cross threads.

Good:
```rust
use std::sync::Arc;

async fn run(shared: Arc<u32>) {
    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
    println!("{shared}");
}

fn start_all(shared: &Arc<u32>) {
    for _ in 0..10 {
        let shared = Arc::clone(shared); // clone before the move, one handle per task
        tokio::spawn(run(shared));
    }
}
```
Limit the scope of a borrow by ending it in a block before the await: `let n = { let g = cell.borrow(); g.len() };`.

## R-RSA-CANCEL-SAFE — only cancel-safe futures in select!

`select!` drops every losing branch immediately. A future that had consumed input into its own state loses that input.

Bad:
```rust
use tokio::io::AsyncReadExt;

async fn step<R: tokio::io::AsyncRead + Unpin>(
    reader: &mut R,
    rx: &mut tokio::sync::mpsc::Receiver<String>,
) -> std::io::Result<()> {
    let mut buf = [0u8; 1024];
    tokio::select! {
        res = reader.read_exact(&mut buf) => { res?; } // dropped mid-read: bytes already read are lost
        msg = rx.recv() => { let _ = msg; }
    }
    Ok(())
}
```
Why: when `recv` wins, the part of the frame already read is gone and the stream is out of sync.

Good:
```rust
use std::pin::pin;
use tokio::io::AsyncReadExt;

async fn read_frame<R: tokio::io::AsyncRead + Unpin>(
    reader: &mut R,
    rx: &mut tokio::sync::mpsc::Receiver<String>,
) -> std::io::Result<[u8; 16]> {
    let mut buf = [0u8; 16];
    {
        let mut read = pin!(reader.read_exact(&mut buf)); // created once, outside the loop
        loop {
            tokio::select! {
                res = &mut read => { res?; break; }          // polled again, never restarted
                msg = rx.recv() => { let _ = msg; }
            }
        }
    }
    Ok(buf)
}
```
Other ways out: keep the accumulation buffer outside and use `read` (cancel-safe) in a loop; or `tokio::spawn` the multi-step operation and select on its `JoinHandle` (awaiting a `JoinHandle` is cancel-safe, the task keeps running). Each tokio method documents its cancel safety under "Cancel safety"; verified in tokio 1.54.1: `recv`, `changed`, `join_next`, `read` are safe; `read_exact`, `read_to_end`, `read_line`, `write_all` are not; `Mutex::lock`, `Semaphore::acquire` and `reserve` are safe but lose their queue place; `send` is safe but drops the message.

Dropped from the source: the `read_to_end` "pinned" example that never used `select!`, and `poll_read_buf` as a "cancel-safe adapter".

## R-RSA-CANCEL-TOKEN — shut down with a token

Dropping a `JoinHandle` detaches the task. For shutdown use `tokio_util::sync::CancellationToken` (dependency `tokio-util`): a child token per subsystem or connection, `cancelled()` as a `select!` branch, then wait for the tasks.

Bad:
```rust
let handle = tokio::spawn(async { loop { do_work().await; } });
drop(handle); // the task keeps running, nobody can stop it
# async fn do_work() {}
```
Why: a leaked task holds connections and memory until the process dies.

Good:
```rust
use tokio_util::sync::CancellationToken;
use tokio::task::JoinSet;

async fn worker(token: CancellationToken, mut rx: tokio::sync::mpsc::Receiver<u32>) {
    loop {
        tokio::select! {
            _ = token.cancelled() => break,
            job = rx.recv() => match job {
                Some(job) => handle(job).await, // a handler body is never cancelled by select!
                None => break,
            },
        }
    }
}

async fn shutdown_signal() {
    use tokio::signal::unix::{signal, SignalKind};
    let mut term = signal(SignalKind::terminate()).expect("install SIGTERM handler");
    tokio::select! {
        _ = tokio::signal::ctrl_c() => {}
        _ = term.recv() => {}
    }
}

async fn run(tasks: &mut JoinSet<()>, token: &CancellationToken) {
    shutdown_signal().await;
    token.cancel();
    // bounded wait for the tasks to finish
    let _ = tokio::time::timeout(std::time::Duration::from_secs(30), async {
        while tasks.join_next().await.is_some() {}
    })
    .await;
}
# async fn handle(_: u32) {}
```
Containers send SIGTERM, not Ctrl+C, so handle both (the signal module for Unix is tokio's `signal::unix`). `token.child_token()` is cancelled with its parent, `token.clone()` is another handle to the same token, `token.drop_guard()` cancels on drop. Branches awaited in `select!` next to `cancelled()` must be cancel-safe (R-RSA-CANCEL-SAFE). An `AtomicBool` flag does not wake a task that is waiting; use the token.

## R-RSA-SELECT — racing futures

`select!` takes whichever future finishes first and drops the rest. A pure deadline is simpler as `timeout`.

Bad:
```rust
// sequential: the fallback starts only after the primary has failed or hung forever
async fn fetch() -> Result<u32, Error> {
    match fetch_primary().await {
        Ok(v) => Ok(v),
        Err(_) => fetch_fallback().await,
    }
}
# #[derive(Debug)] enum Error { Timeout }
# async fn fetch_primary() -> Result<u32, Error> { Ok(1) }
# async fn fetch_fallback() -> Result<u32, Error> { Ok(2) }
```
Why: no bound on how long the primary can take.

Good:
```rust
use std::time::Duration;
use tokio::time::timeout;

async fn fetch() -> Result<u32, Error> {
    // deadline on the call
    let primary = timeout(Duration::from_secs(1), fetch_primary()).await;
    match primary {
        Ok(Ok(v)) => Ok(v),
        Ok(Err(_)) | Err(_) => timeout(Duration::from_secs(5), fetch_fallback())
            .await
            .map_err(|_| Error::Timeout)?,
    }
}

// real racing, a branch is cancelled by the winner
async fn first_of_two() -> u32 {
    tokio::select! {
        v = fetch_primary_value() => v,
        v = fetch_fallback_value() => v,
    }
}
# #[derive(Debug)] enum Error { Timeout }
# async fn fetch_primary() -> Result<u32, Error> { Ok(1) }
# async fn fetch_fallback() -> Result<u32, Error> { Ok(2) }
# async fn fetch_primary_value() -> u32 { 1 }
# async fn fetch_fallback_value() -> u32 { 2 }
```
Notes. The losing futures are dropped at the moment a branch finishes (the source said "at their next await"; that is wrong). A branch pattern such as `Some(x) = rx.recv()` disables the branch if it does not match; `else =>` runs when all are disabled. `biased;` polls in order for deterministic priority and can starve later branches. Racing a dynamic set: put the futures in a `JoinSet`, take `join_next()` and call `abort_all()` (the source's `futures::future::select_all` needs `Unpin` futures, which `async fn` futures are not).

## R-RSA-JOIN — join!, try_join!, bounded fan-out

Sequential awaits take the sum of their durations; `join!` takes the longest. `join!` runs all futures in the current task, so it is concurrency, not parallelism; CPU-bound branches block each other (use `spawn`). `try_join!` returns the first `Err` and drops the other futures at that moment (the source said they "may still be running"; they do not).

Bad:
```rust
async fn load() -> Result<(Config, Settings), Error> {
    let config = read_config().await?;     // 20 ms
    let settings = read_settings().await?; // 20 ms, independent of the first
    Ok((config, settings))
}
# struct Config; struct Settings; #[derive(Debug)] enum Error {}
# async fn read_config() -> Result<Config, Error> { Ok(Config) }
# async fn read_settings() -> Result<Settings, Error> { Ok(Settings) }
```
Why: 40 ms instead of 20 ms for two independent reads.

Good:
```rust
async fn load() -> Result<(Config, Settings), Error> {
    let (config, settings) = tokio::try_join!(read_config(), read_settings())?;
    Ok((config, settings))
}
# struct Config; struct Settings; #[derive(Debug)] enum Error {}
# async fn read_config() -> Result<Config, Error> { Ok(Config) }
# async fn read_settings() -> Result<Settings, Error> { Ok(Settings) }
```
Different error types: convert with `.map_err(Error::from)` on each branch (needs `futures::TryFutureExt`, or write `async { f().await.map_err(Error::from) }`). Wrap the whole join in one `tokio::time::timeout`. Cleanup after a failure does not run in the dropped branches; use a drop guard or handle errors inside each branch.

Bounded fan-out over many items (`futures` dependency):
```rust
use futures::stream::{self, StreamExt, TryStreamExt};

async fn fetch_users(ids: &[u64]) -> Result<Vec<User>, Error> {
    stream::iter(ids)
        .map(|id| fetch_user(*id))
        .buffer_unordered(10) // at most 10 in flight
        .try_collect()
        .await
}
# struct User; #[derive(Debug)] enum Error {}
# async fn fetch_user(_: u64) -> Result<User, Error> { Ok(User) }
```
Do not `join!` dependent steps (each needs the previous result) or use it when you want "first success" (use `select!`). Dropped from the source: the "shared mutable state" warning (a `Mutex` counter in `join!` is fine) and unbounded `join_all` as the default.

## R-RSA-JOINSET — dynamic sets of tasks

`JoinSet` owns a changing set of spawned tasks, yields results as they finish, aborts the rest on drop and offers `abort_all`. A `Vec<JoinHandle>` plus `join_all` waits for all in order and cannot cancel.

Bad:
```rust
let mut handles = Vec::new();
for url in urls { handles.push(tokio::spawn(fetch(url))); }
let results = futures::future::join_all(handles).await; // all or nothing, in order, no cancel
```
Why: no early exit, no progressive error handling, and handles keep running if you stop waiting.

Good:
```rust
use tokio::task::JoinSet;

async fn fetch_all(urls: Vec<String>) -> Vec<Result<Data, FetchError>> {
    let mut set = JoinSet::new();
    for url in urls {
        set.spawn(async move { fetch(&url).await }); // the future must be 'static: own the url
    }
    let mut out = Vec::new();
    while let Some(joined) = set.join_next().await {
        out.push(match joined {
            Ok(result) => result,
            Err(e) if e.is_panic() => Err(FetchError::TaskPanicked),
            Err(_) => Err(FetchError::Cancelled),
        });
    }
    out
}
# struct Data; enum FetchError { TaskPanicked, Cancelled }
# async fn fetch(_: &str) -> Result<Data, FetchError> { Ok(Data) }
```
A worker pool with a limit combines `Semaphore::acquire_owned` with `set.spawn` (see R-RSA-BOUNDED-CHANNEL). Return the index with the result (`JoinSet<(usize, T)>`) when order matters. After `abort_all`, drain with `while set.join_next().await.is_some() {}` so the aborted tasks have really finished. Panics are reported through the `JoinError`; log them with `tracing::error!`.

| | `JoinSet` | `Vec<JoinHandle>` + `join_all` |
|---|---|---|
| Add tasks while running | yes | no |
| Results as they complete | yes | no, all at once |
| Abort on drop / `abort_all` | yes | no (tasks detach) |

## R-RSA-FN-IN-TRAIT — native async fn in traits

`async fn` in traits is stable since 1.75; no macro, no boxed future per call. `#[async_trait]` is not used in our code. Two limits:

1. Not `dyn`-compatible. Verified with rustc 1.99: `Box<dyn Repo>` fails with "not dyn compatible ... because method is `async`". Use a generic parameter (`impl Repo` / `R: Repo`) or an enum over the implementations. If trait objects are unavoidable, write the method as `fn get(&self) -> Pin<Box<dyn Future<Output = T> + Send + '_>>` by hand, and say why. The source suggested `trait-variant` for `dyn`; its `make` macro produces a `Send` variant, not a `dyn`-compatible one.
2. The returned future is not `Send` by default, but `tokio::spawn` needs `Send`. Declare the `Send` bound in the trait, implementors still write `async fn`.

Bad:
```rust
#[async_trait::async_trait]
trait Repo {
    async fn get(&self, id: u64) -> anyhow::Result<String>;
}
```
Why: a macro dependency, a heap allocation per call, and `anyhow` in a library-style interface (errors are `thiserror` enums).

Good:
```rust
use std::future::Future;

trait Repo {
    // Send bound stated once, here
    fn get(&self, id: u64) -> impl Future<Output = Result<String, RepoError>> + Send;
}

struct PgRepo;

impl Repo for PgRepo {
    async fn get(&self, id: u64) -> Result<String, RepoError> {
        Ok(format!("row-{id}"))
    }
}

#[derive(Debug, thiserror::Error)]
enum RepoError {
    #[error("row not found")]
    NotFound,
}
```
A trait used only with generics on a single-threaded runtime may keep the plain `async fn` form; the `async_fn_in_trait` lint warns for public traits and is silenced by the `-> impl Future + Send` spelling. `trait-variant` (dependency, version not verified here) can generate the `Send` variant instead of writing it by hand.

| Case | Do |
|---|---|
| Generic or `impl Trait` dispatch | `async fn` in trait |
| Futures go to `tokio::spawn` | `fn f(&self) -> impl Future<Output = T> + Send` |
| Needs `dyn` | enum or generics first; hand-written boxed future last |

## R-RSA-FN-BOUNDS — AsyncFn instead of two generics

Since 1.85 `AsyncFn`, `AsyncFnMut`, `AsyncFnOnce` express a callback that returns a future in one bound, and they accept `async ||` closures that borrow their environment; the `F: Fn() -> Fut, Fut: Future` form cannot lend those borrows to the future. In edition 2024 the traits are in scope without an import (compiled with rustc 1.99).

Bad:
```rust
use std::future::Future;

async fn retry<F, Fut, T, E>(times: usize, f: F) -> Result<T, E>
where
    F: Fn() -> Fut,
    Fut: Future<Output = Result<T, E>>,
{
    let mut n = 0;
    loop {
        match f().await {
            Ok(v) => return Ok(v),
            Err(e) => { n += 1; if n >= times { return Err(e); } }
        }
    }
}
```
Why: two type parameters, and a closure that borrows a local cannot be passed.

Good:
```rust
async fn retry<F, T, E>(times: usize, f: F) -> Result<T, E>
where
    F: AsyncFn() -> Result<T, E>,
{
    let mut n = 0;
    loop {
        match f().await {
            Ok(v) => return Ok(v),
            Err(e) => { n += 1; if n >= times { return Err(e); } }
        }
    }
}

async fn demo() {
    let prefix = "p".to_owned();
    let _ = retry(3, async || Ok::<_, std::io::Error>(format!("{prefix}-data"))).await;
}
```
Choose like `Fn` / `FnMut` / `FnOnce`: weakest that the body allows. Defect fixed: the source said to add `+ Send` to an `AsyncFn` bound for `tokio::spawn`; that bounds the closure, not the future it returns, and the future's `Send`-ness cannot be required with `AsyncFn` on stable. When the future must be `Send`, use the two-generic form with `Fut: Future<Output = T> + Send`:
```rust
fn spawn_repeating<F, Fut>(f: F)
where
    F: Fn() -> Fut + Send + 'static,
    Fut: std::future::Future<Output = ()> + Send,
{
    tokio::spawn(async move { loop { f().await; } });
}
```

## R-RSA-BOUNDED-CHANNEL — backpressure by default

An unbounded channel grows until the process runs out of memory when the producer is faster than the consumer. `mpsc::channel(n)` makes `send` wait when full.

Bad:
```rust
let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<Message>();
// fast producer, slow consumer: the queue grows without limit
# struct Message;
```
Why: memory grows until the service is killed, and nothing tells the producer to slow down.

Good:
```rust
use tokio::sync::mpsc::{self, error::TrySendError};

async fn produce(tx: mpsc::Sender<Message>, msg: Message) -> Result<(), Closed> {
    tx.send(msg).await.map_err(|_| Closed) // waits while the channel is full
}

// shed load instead of waiting
fn offer(tx: &mpsc::Sender<Message>, msg: Message) -> Result<(), Closed> {
    match tx.try_send(msg) {
        Ok(()) => Ok(()),
        Err(TrySendError::Full(_dropped)) => Ok(()), // count it in a metric
        Err(TrySendError::Closed(_)) => Err(Closed),
    }
}
# struct Message; struct Closed;
```
What a full channel means is a decision: wait (`send`), wait with a deadline (`timeout(.., tx.send(..))`), drop and count (`try_send`), or fail the request. Buffer size: start from the expected burst, measure, err small. `reserve().await` gives a permit first, so an expensive message is only built when there is room.

Worker pool with a limit. The source shared one receiver between workers through `Arc<Mutex<Receiver>>`, holding the lock across `recv().await`, which breaks R-RSA-NO-LOCK-AWAIT. Use one receiving loop and a semaphore:
```rust
use std::sync::Arc;
use tokio::sync::{mpsc, Semaphore};
use tokio::task::JoinSet;

async fn pool(mut rx: mpsc::Receiver<Job>, max: usize) {
    let permits = Arc::new(Semaphore::new(max));
    let mut set = JoinSet::new();
    while let Some(job) = rx.recv().await {
        let permit = permits.clone().acquire_owned().await.expect("semaphore is never closed");
        set.spawn(async move {
            let _permit = permit; // released when the job ends
            run(job).await;
        });
        while let Some(done) = set.try_join_next() {
            if let Err(e) = done { tracing::error!(error = %e, "job failed"); }
        }
    }
    while set.join_next().await.is_some() {}
}
# struct Job; async fn run(_: Job) {}
```

## R-RSA-MPSC — the default task channel

`tokio::sync::mpsc` has async `send` / `recv`, cheap `Sender` clones, backpressure, and closes when every sender is dropped. `std::sync::mpsc::recv` blocks the worker thread.

Bad:
```rust
let (tx, rx) = std::sync::mpsc::channel::<String>();
tokio::spawn(async move { let _ = rx.recv(); }); // blocks a runtime thread
# drop(tx);
```
Why: one blocked worker per waiting receiver.

Good:
```rust
use tokio::sync::mpsc;

enum Command {
    Set { key: String, value: u32 },
    Delete { key: String },
}

async fn run_store(mut commands: mpsc::Receiver<Command>) {
    let mut store = std::collections::HashMap::new();
    while let Some(cmd) = commands.recv().await {
        match cmd {
            Command::Set { key, value } => { store.insert(key, value); }
            Command::Delete { key } => { store.remove(&key); }
        }
    }
    // ends when every Sender is dropped
}
```
The state has one owner (the task), so it needs no lock; this is the alternative to a shared `Mutex`. Producers: `let tx = tx.clone();` per task, then `drop(tx)` of the original so the loop can end. Graceful stop: `select!` on `token.cancelled()` and `rx.recv()`; after cancellation drain with `try_recv` if messages must not be lost. `tx.downgrade()` gives a `WeakSender` that does not keep the channel open (niche). `reserve()` for expensive messages is covered in R-RSA-BOUNDED-CHANNEL.

## R-RSA-ONESHOT — request and reply

`oneshot` is a single-use channel: no buffer, consumed on use. Put the sender in the command message.

Bad:
```rust
// polling a shared slot for the answer
let slot = std::sync::Arc::new(tokio::sync::Mutex::new(None::<u32>));
while slot.lock().await.is_none() {
    tokio::time::sleep(std::time::Duration::from_millis(10)).await;
}
```
Why: latency and wasted wakeups for something a channel does directly.

Good:
```rust
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};
use tokio::time::timeout;

enum Cmd {
    Get { key: String, reply: oneshot::Sender<Option<u32>> },
}

#[derive(Debug, thiserror::Error)]
enum CallError {
    #[error("service is gone")]
    Down,
    #[error("service did not answer in time")]
    Timeout,
}

async fn get(tx: &mpsc::Sender<Cmd>, key: &str) -> Result<Option<u32>, CallError> {
    let (reply, answer) = oneshot::channel();
    tx.send(Cmd::Get { key: key.to_owned(), reply }).await.map_err(|_| CallError::Down)?;
    timeout(Duration::from_secs(5), answer)
        .await
        .map_err(|_| CallError::Timeout)?
        .map_err(|_| CallError::Down) // sender dropped without a reply
}
```
On the service side `let _ = reply.send(value);` ignoring the error is right: the caller may have timed out. `tx.is_closed()` / `tx.closed().await` let the service skip work nobody waits for. Dropped from the source: a generic `RpcRequest<Req, Res>` wrapper (one use, no gain) and a nonsensical `tx.clone()` line (a oneshot sender cannot be cloned).

## R-RSA-BROADCAST — every subscriber sees every event

`mpsc` gives each message to one consumer. `broadcast` clones each message to every subscriber. The channel is bounded; a slow subscriber gets `Lagged(n)` and misses the oldest `n` messages.

Bad:
```rust
// two consumers on one mpsc: each message goes to only one of them
let (tx, mut rx) = tokio::sync::mpsc::channel::<Event>(100);
# #[derive(Clone)] struct Event;
```
Why: there is no way to give the same event to the logger and the metrics task.

Good:
```rust
use tokio::sync::broadcast::{self, error::RecvError};

#[derive(Clone, Debug)]
enum Event { UserLoggedIn { user_id: u64 }, Shutdown }

async fn consume(mut rx: broadcast::Receiver<Event>) {
    loop {
        match rx.recv().await {
            Ok(event) => handle(&event),
            Err(RecvError::Lagged(missed)) => tracing::warn!(missed, "subscriber lagged"),
            Err(RecvError::Closed) => break,
        }
    }
}

fn start() -> broadcast::Sender<Event> {
    let (tx, rx) = broadcast::channel(1000);
    tokio::spawn(consume(rx));
    tokio::spawn(consume(tx.subscribe()));
    tx
}
# fn handle(_: &Event) {}
```
`send` returns `Err` when there are no subscribers; for an event bus that is usually fine to ignore (`let _ = tx.send(e);`). The message type must be `Clone`; wrap large ones in `Arc`. Pick the capacity for the worst burst, and decide whether losing events (`Lagged`) is acceptable; if not, `mpsc` per subscriber.

## R-RSA-WATCH — latest value

`watch` keeps one value; receivers see the newest, skipping intermediate ones, and a slow receiver never lags. Right for reloadable config and status.

Bad:
```rust
// broadcast for configuration: receivers process stale configs in order
let (tx, _rx) = tokio::sync::broadcast::channel::<AppConfig>(100);
# #[derive(Clone)] struct AppConfig;
```
Why: only the newest config matters, and the old ones cost work.

Good:
```rust
use std::sync::Arc;
use tokio::sync::watch;

#[derive(Clone, PartialEq, Debug)]
struct AppConfig { max_connections: usize }

fn publish(tx: &watch::Sender<Arc<AppConfig>>, new: AppConfig) {
    // notifies receivers only if the value really changed
    tx.send_if_modified(|current| {
        if **current != new { *current = Arc::new(new); true } else { false }
    });
}

async fn worker(mut rx: watch::Receiver<Arc<AppConfig>>) {
    loop {
        tokio::select! {
            changed = rx.changed() => {
                if changed.is_err() { break; } // sender dropped
                let config = Arc::clone(&rx.borrow_and_update()); // copy out, guard gone
                apply(&config).await;
            }
            _ = do_work() => {}
        }
    }
}

async fn wait_ready(mut rx: watch::Receiver<bool>) -> Result<(), watch::error::RecvError> {
    rx.wait_for(|ready| *ready).await?; // returns at once if already true
    Ok(())
}
# async fn apply(_: &AppConfig) {} async fn do_work() {}
```
`borrow()` returns a read guard: never hold it across `.await` (it blocks the sender and is not `Send`); copy or clone the value out. `changed()` completes only for values newer than the last one the receiver saw, a new receiver starts with the current value marked seen. `send` returns `Err` when no receiver exists; `send_replace` always stores. Fixed from the source: `*current != new_config` compared an `Arc<T>` with a `T` and did not compile; `wait_for` replaces the manual `loop { match borrow().clone() ... changed().await }`.

| | `watch` | `broadcast` | `mpsc` |
|---|---|---|---|
| Receivers | many | many | one |
| Delivery | latest only | all | all |
| Slow receiver | skips | `Lagged` | backpressure |
| `Clone` on the value | not needed | required | not needed |
| Best for | config, status | events | work queues |
