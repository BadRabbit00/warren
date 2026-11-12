# Project structure rules (source: leonardomso `proj-*`, Microsoft `project/`)

Full text of the kept rules. Short form and ids: `../SKILL.md`. Examples were rewritten for edition 2024 and checked with `cargo check` / `cargo clippy` (Rust 1.99). Where the source was wrong the note under the rule says so.

## Module layout

### R-RSPJ-FLAT-SMALL — keep small crates flat [proj-flat-small]

Why: folders and `mod.rs` files that hold one or two small files cost navigation and give nothing. Add structure when the code asks for it.

Bad:
```text
src/
├── core/mod.rs            # only re-exports
├── domain/models/user.rs  # 50 lines
├── infrastructure/database/connection.rs  # 30 lines
└── main.rs
```

Good:
```text
src/
├── main.rs
├── lib.rs
├── config.rs
├── database.rs
├── user.rs
└── error.rs
```

Growth path (rules of thumb, not limits): up to about 10 files stay flat; a concept that grows several files (`order.rs`, `order_item.rs`, `order_repository.rs`) becomes a folder; signs of too much structure are folders with one or two files and `mod.rs` files that only re-export.

### R-RSPJ-MOD-BY-FEATURE — group by feature, name files `<entity>_<layer>` [proj-mod-by-feature]

Why: one entity is changed, tested and deleted as a unit; all of its code belongs in one place. The layer direction of `rules/layers.md` (handler → service → repository) still holds inside the feature.

Bad:
```text
src/
├── controllers/{user_controller.rs, order_controller.rs}
├── services/{user_service.rs, order_service.rs}
├── repositories/{user_repository.rs, order_repository.rs}
└── shared/helpers.rs
```

Good:
```text
src/
├── order.rs                    # declares the submodules, exports the public items
├── order/
│   ├── order_handler.rs
│   ├── order_service.rs
│   └── order_repository.rs
├── user.rs
├── user/
│   └── ...
├── database.rs                 # infrastructure: named by content
├── error.rs
└── lib.rs
```

```rust
// src/order.rs
mod order_handler;
mod order_repository;
mod order_service;

pub use order_handler::router;
pub use order_service::OrderService;
```

Rewritten: the source names the files `model.rs` / `service.rs` and keeps a `shared/` folder; this repository names entity files `<entity>_<layer>` and forbids `shared`, `common`, `utils`, `helpers` (R-LAYER-NAMING). Cross-cutting files are named by what they hold.

### R-RSPJ-MOD-STYLE — one module-file style per crate [proj-mod-rs-dir]

Why: both styles compile; mixing them makes a tree hard to read.

Bad:
```text
src/
├── user/mod.rs        # style 1
├── order.rs           # style 2
└── order/order_item.rs
```

Good:
```text
src/
├── user.rs            # style 2 everywhere: user.rs + user/
├── user/user_service.rs
├── order.rs
└── order/order_service.rs
```

The existing code decides. A new crate uses `name.rs` next to `name/` (no files called `mod.rs`, so editor tabs stay distinguishable). Two restriction lints enforce the choice: `clippy::mod_module_files` (forbids `mod.rs`) and `clippy::self_named_module_files` (forbids `name.rs` + `name/`); enable at most one, and only through ci-engineer (R-RSPJ-LINT-OWNER).

Rewritten: the source calls `mod.rs` "recommended for larger modules" and claims the other style "matches the 2018+ default lint preference"; neither is a Rust rule, so both claims are dropped.

### R-RSPJ-LIB-MAIN-SPLIT — thin `main.rs`, logic in `lib.rs` [proj-lib-main-split]

Why: integration tests in `<crate>/tests/` can only reach the library target, and a `main` full of logic cannot be reused by a second binary or a worker.

Bad:
```rust
// src/main.rs
fn main() {
    let args = parse_args();
    let config = load_config(&args.config_path).expect("config must load");
    let db = connect_database(&config.db_url).expect("database must connect");
    // hundreds of lines of application logic, unreachable from tests/
}
```

Good:
```rust
// src/main.rs
use my_app::{Config, run};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env()?;
    run(config).await
}

// src/lib.rs
pub mod config;
pub mod database;

pub use config::Config;

pub async fn run(config: Config) -> anyhow::Result<()> {
    let db = database::connect(&config.db_url).await?;
    // build the app, serve
    Ok(())
}
```

```text
my_app/
├── Cargo.toml
├── src/{main.rs, lib.rs, config.rs, database.rs}
└── tests/order_flow.rs      # imports my_app::{Config, run, ...}
```

`anyhow` in `main` is allowed (R-RS-ERRORS); the library returns typed errors. Rewritten: source tests used `unwrap()` and `#[test]` in a sync `run`.

### R-RSPJ-BIN-DIR — several binaries live in `src/bin/` [proj-bin-dir]

Why: Cargo discovers every `src/bin/<name>.rs` (or `src/bin/<name>/main.rs`) as a binary; hand-written `[[bin]]` tables are noise and drift.

Bad:
```toml
[[bin]]
name = "server"
path = "src/server.rs"

[[bin]]
name = "cli"
path = "src/cli.rs"
```

Good:
```text
src/
├── lib.rs          # shared code
├── main.rs         # default binary, named after the package
└── bin/
    ├── server.rs   # binary `server`
    └── cli/main.rs # binary `cli`, with private modules next to it
```

Write a `[[bin]]` table only for what discovery cannot say: another name, `required-features`. `default-run = "<name>"` in `[package]` picks the binary for a bare `cargo run`.

## Visibility and exports

### R-RSPJ-VISIBILITY — the narrowest visibility that works [proj-pub-crate-internal, proj-pub-super-parent]

Why: every `pub` item is a promise; narrow items can be refactored freely.

| Visibility | Reach |
|---|---|
| (private) | the module and its descendants |
| `pub(super)` | the parent of the module that declares the item, and the parent's descendants |
| `pub(crate)` | the crate |
| `pub(in path)` | the named ancestor module |
| `pub` | everyone (in a binary crate effectively the crate) |

Bad:
```rust
// src/parser.rs
pub mod lexer;   // the whole crate sees the lexer and its helpers
pub mod ast;

// src/parser/lexer.rs
pub struct Token(pub char);
pub fn lex(input: &str) -> Vec<Token> { input.chars().map(Token).collect() }
```

Good:
```rust
// src/parser.rs
mod ast;
mod lexer;

pub fn parse(input: &str) -> usize {
    ast::count(lexer::lex(input))
}

// src/parser/lexer.rs
#[derive(Debug)]
pub(super) struct Token(pub(super) char);

pub(super) fn lex(input: &str) -> Vec<Token> {
    input.chars().map(Token).collect()
}

// src/parser/ast.rs
use super::lexer::Token;

pub(super) fn count(tokens: Vec<Token>) -> usize {
    tokens.iter().filter(|t| t.0 != ' ').count()
}
```

Rules of use: start private; widen to `pub(super)` for a helper shared by sibling modules, to `pub(crate)` for a helper used across the crate, to `pub` only for the real API. A private item is already visible to the module's child modules, so `pub(super)` is for siblings.

Corrected from the source: it declares `pub(super)` in `parser/mod.rs` and says `codegen.rs` cannot see it. A `pub(super)` item in `parser` is visible in the crate root and everything below it, `codegen` included; it was checked with `cargo check`. The test-visibility patterns (`#[cfg(test)] pub(crate) fn`, `__test_helpers`, `mod tests` in `src/`) are dropped: tests live in `<crate>/tests/` and use the public API (rules/tests.md).

### R-RSPJ-REEXPORT — library crates: one public path per item [proj-pub-use-reexport, M-SINGLE-ITEM-PATH]

Why: users import from one stable place and you can move files without breaking them. An item that is public at two paths gives two spellings in every codebase and doubles the surface you must keep.

Bad:
```rust
// lib.rs: reachable as my_crate::error::MyError and my_crate::MyError
pub mod error;
pub use error::MyError;
```

Good:
```rust
// lib.rs: the module is private, the item has one path
mod client;
mod error;

pub use client::HttpClient;
pub use error::MyError;
```

Users write `use my_crate::{HttpClient, MyError};`. Keep modules public (and do not re-export) when the module path is the API (`my_crate::http::Client`).

Other points: re-export a dependency's type when it appears in your public signatures, so users can name it without adding the dependency; never `pub use dep::*`; rename on re-export only to resolve a clash (`pub use v1::Client as LegacyClient`). A `prelude` module re-exports the same items a second time and invites glob imports (`clippy::wildcard_imports` is on in the pedantic group); it is dropped, see "Dropped" in `../SKILL.md`. For a service crate this rule matters less: nobody outside the repository imports it.

## Cargo workspace and manifests

### R-RSPJ-WORKSPACE — two or more related crates form a workspace [proj-workspace-large, M-CARGO-WORKSPACE]

Why: one `Cargo.lock`, one target directory, shared versions, lints and metadata.

Bad:
```text
my-app-core/Cargo.toml     # own Cargo.lock
my-app-server/Cargo.toml   # own Cargo.lock, own copy of every dependency version
```

Good:
```text
my-app/
├── Cargo.toml        # virtual workspace root: no [package]
├── Cargo.lock
└── crates/
    ├── core/Cargo.toml
    └── server/Cargo.toml
```

```toml
# Cargo.toml (root)
[workspace]
members = ["crates/*"]
resolver = "3"

[workspace.package]
edition = "2024"
rust-version = "1.85"
```

```toml
# crates/core/Cargo.toml
[package]
name = "my-app-core"
version = "0.1.0"
edition.workspace = true
rust-version.workspace = true
publish = false

[lints]
workspace = true
```

| Situation | Choice |
|---|---|
| one binary or one library | no workspace |
| library + its CLI, small | optional; a package with `src/bin/` is enough |
| two or more crates that belong together, shared internal libraries, several services in one repository | workspace |

Commands: `cargo build --workspace`, `cargo test --workspace`, `cargo clippy --workspace --all-targets`, `cargo run -p my-app-server`.

Rewritten: edition 2024 in every example. A virtual root has no edition of its own, so `resolver = "3"` must be written there (Cargo warns that it falls back to resolver 1 otherwise; checked).

### R-RSPJ-WS-DEPS — dependencies are declared once, in the workspace [proj-workspace-deps, M-CARGO-WORKSPACE]

Why: version drift gives several copies of one crate, slower builds and subtle behaviour differences.

Bad:
```toml
# crates/a/Cargo.toml
[dependencies]
serde = "1.0.150"

# crates/b/Cargo.toml
[dependencies]
serde = "1.0.188"
```

Good:
```toml
# Cargo.toml (root)
[workspace.dependencies]
serde = { version = "1", default-features = false }
thiserror = "2"
tokio = { version = "1", default-features = false }

# crates/a/Cargo.toml
[dependencies]
serde = { workspace = true, features = ["derive"] }
thiserror.workspace = true
tokio = { workspace = true, features = ["rt-multi-thread", "macros"] }
```

Rules: a dependency used by one crate only is still declared in the workspace; the workspace entry carries the version and `default-features = false` (plus basic features such as `std` if the crate needs them); each member adds the features it uses (member features are added to the workspace ones); default features are decided in the workspace entry, not per member. `optional = true` is not allowed in `[workspace.dependencies]` (Cargo rejects it: "workspace dependencies cannot be optional"), so write `serde = { workspace = true, optional = true }` in the member and the `dep:serde` feature there. Dev and build dependencies follow the same pattern.

A new dependency is a decision, not a side effect: say that it is new and why the standard library or an existing dependency is not enough.

Rewritten: the source pinned old versions (`thiserror = "1.0"`, `tokio` with `full`); versions here are major-only placeholders, take the real ones from `Cargo.lock` or the registry.

### R-RSPJ-WS-CRATES — list every crate as a member and depend through the workspace [M-CRATES-IN-WORKSPACE]

Why: one canonical version and path for each intra-workspace dependency, and simple debugging.

Bad:
```toml
# crates/server/Cargo.toml
[dependencies]
my-app-core = { path = "../core" }
```

Good:
```toml
# Cargo.toml (root)
[workspace.dependencies]
my-app-core = { path = "crates/core", version = "0.1.0" }

# crates/server/Cargo.toml
[dependencies]
my-app-core.workspace = true
```

`members = ["crates/*"]` lists every crate the repository produces. `version` on a path dependency is needed only for crates that are published; for private crates (`publish = false`) the path alone is enough.

### R-RSPJ-EDITION — new crates use the latest stable edition [M-LATEST-EDITION]

Why: an older edition buys no compatibility (a 2015 crate can use 2024 libraries) and forces older, less safe idioms.

Bad:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2021"
```

Good:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
```

In a package, `resolver` is not needed (edition 2024 implies resolver 3). Every example in this skill uses edition 2024. Migrating an existing crate is a separate, planned change (`cargo fix --edition`), not part of a feature.

### R-RSPJ-MSRV — declare `rust-version`; a published crate keeps it a few releases behind [proj-msrv-declare, M-MSRV]

Why: Cargo refuses an old toolchain with a clear message instead of a cryptic error, and the MSRV-aware resolver (resolver 3) avoids dependency versions that need a newer compiler.

Bad:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
rust-version = "1.80"   # edition 2024 needs 1.85: the manifest does not even parse
```

Good:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
```

| Crate | `rust-version` means | Updating it |
|---|---|---|
| service or internal crate (`publish = false`) | the toolchain the project pins | with the toolchain |
| published library | the oldest compiler you promise; set when the crate is created; kept a few releases behind the newest | when a needed feature requires it; a minor release is enough; write it in the changelog |

A CI job that builds with the MSRV toolchain belongs to ci-engineer. The tool `cargo-msrv` can search for the real floor; it is an extra tool, add it to the dev shell only with a reason.

Rewritten: the source example paired edition 2024 with `rust-version = "1.80"` (checked: Cargo rejects it), and asserted a GitHub Actions workflow that this repository does not use.

### R-RSPJ-FEATURES-ADDITIVE — Cargo features only add [proj-feature-additive]

Why: Cargo unions the features requested anywhere in the dependency graph. If enabling a feature removes behaviour, a third crate enabling it breaks everyone else.

Bad:
```toml
[features]
no_std = []   # enabling it removes std support
```

```rust
#[cfg(not(feature = "no_std"))]
use std::vec::Vec;
```

Good:
```toml
[features]
default = ["std"]
std = []
serde = ["dep:serde"]

[dependencies]
serde = { version = "1", optional = true, default-features = false }
```

```rust
#![cfg_attr(not(feature = "std"), no_std)]
```

Rules: a feature adds items, impls or dependencies, never removes them; mutually exclusive features cannot be enforced by Cargo, so avoid them or add `compile_error!` when both are on; use `dep:name` to keep optional dependency names out of the feature namespace. Test every combination with `cargo hack` (R-RSPJ-STATIC-VERIFY). A feature that changes behaviour inside an application (for example a database backend chosen at build time) is a configuration choice of the final binary and is fine there; the rule is about library crates.

### R-RSPJ-BUILD-RS — a build script is small, deterministic and says what it reads [proj-build-rs-minimal]

Why: Cargo reruns a script that emits no `rerun-if` directive on every build; network access and timestamps break reproducible and offline builds.

Bad:
```rust
// build.rs
use std::process::Command;

fn main() {
    // no rerun-if directive: runs on every build
    let out = Command::new("rustc").arg("--version").output().expect("rustc runs");
    if String::from_utf8_lossy(&out.stdout).contains("1.8") {   // parses a version string
        println!("cargo::rustc-cfg=has_feature");
    }
    // plus a download from the network: breaks offline builds
}
```

Good:
```rust
// build.rs
fn main() {
    println!("cargo::rerun-if-changed=build.rs");
    println!("cargo::rerun-if-changed=schema/api.json");
    println!("cargo::rerun-if-env-changed=MY_BUILD_FLAG");

    if std::env::var_os("MY_BUILD_FLAG").is_some() {
        println!("cargo::rustc-cfg=my_flag");
    }
}
```

Rules: always emit `rerun-if-changed` for the script and every file it reads; never touch the network (check the inputs in, or vendor them); write only under `OUT_DIR`; keep the script short and move complex code generation into a library crate; probe compiler capabilities by compiling a snippet (the `autocfg` crate does this) rather than parsing `rustc --version`, and treat `autocfg` as a new dependency; declare custom cfgs in `unexpected_cfgs` (R-RSPJ-LINT-CFG-CHECK).

Rewritten: the source Good example called two `autocfg` methods that were not verified; the example here uses only `std`. The `cargo::` directive form needs Rust 1.77 or newer, which every edition 2024 crate already has.
