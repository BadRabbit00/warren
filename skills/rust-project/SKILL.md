---
name: rust-project
description: Use when creating or restructuring a Rust crate or Cargo workspace, choosing module layout, visibility, features, edition or MSRV, or when a clippy, rustc or rustfmt finding needs a decision. Gives project-structure and lint rules with a verified workspace lint table.
---

# Rust project structure and lints

## When to use

- Starting a crate or workspace, or splitting a crate into modules, a library and binaries.
- Deciding visibility (`pub`, `pub(crate)`, `pub(super)`), re-exports, features, `build.rs`, edition, `rust-version`.
- Reading or answering a clippy / rustc / rustfmt finding, or writing `#[expect(...)]`.
- Not for: naming and API shape (skill `rust-design`), doc comments (`rust-docs`), test layout (`rules/tests.md`), the lint-config edit itself (only ci-engineer, R-RSPJ-LINT-OWNER).

## Contents

1. [Rules: project structure](#rules-project-structure)
2. [Rules: lints and verification](#rules-lints-and-verification)
3. [Decision tables](#decision-tables)
4. [Dropped and rewritten](#dropped-and-rewritten)
5. Full rules with Bad/Good: `references/proj.md` (from leonardomso `proj-`, Microsoft `project/`) and `references/lint.md` (from leonardomso `lint-`, Microsoft universal rules)

"Published crates only" marks rules that do not matter for a service with `publish = false`.

## Rules: project structure

### Modules and crates

- R-RSPJ-FLAT-SMALL: a small crate stays flat; add folders when a concept grows several files, not before; no folder with one or two small files. [proj-flat-small]
- R-RSPJ-MOD-BY-FEATURE: group by feature, not by type; files bound to an entity are `<entity>_<layer>.rs` (R-LAYER-NAMING); cross-cutting files are named by content, never `shared` / `common` / `utils`. [proj-mod-by-feature]
- R-RSPJ-MOD-STYLE: one module-file style per crate, the existing one wins; a new crate uses `name.rs` + `name/`. [proj-mod-rs-dir]
- R-RSPJ-LIB-MAIN-SPLIT: `main.rs` only reads config and calls `run`; logic is in `lib.rs`, so `<crate>/tests/` can reach it. [proj-lib-main-split]
- R-RSPJ-BIN-DIR: extra binaries go in `src/bin/`; a `[[bin]]` table only for a custom name or `required-features`. [proj-bin-dir]
- R-RSPJ-VISIBILITY: start private, widen to `pub(super)` (siblings), `pub(crate)` (crate), `pub` (API); no `#[cfg(test)]` accessors for tests, test through the public API. [proj-pub-crate-internal, proj-pub-super-parent]
- R-RSPJ-REEXPORT: published crates only: private modules plus `pub use` at the root, one public path per item; no `pub use dep::*`, no prelude module. [proj-pub-use-reexport, M-SINGLE-ITEM-PATH]

### Cargo

- R-RSPJ-WORKSPACE: two or more related crates form a workspace with a virtual root, shared `Cargo.lock`, `[workspace.package]` and `[lints] workspace = true`; set `resolver = "3"` in a virtual root. [proj-workspace-large, M-CARGO-WORKSPACE]
- R-RSPJ-WS-DEPS: every dependency is declared once in `[workspace.dependencies]` with `default-features = false`; members use `dep.workspace = true` and add their own features; `optional` is written in the member. A new dependency is named as new. [proj-workspace-deps, M-CARGO-WORKSPACE]
- R-RSPJ-WS-CRATES: every crate is a workspace member and sibling crates are depended on through `[workspace.dependencies]`, not `path = "../x"`. [M-CRATES-IN-WORKSPACE]
- R-RSPJ-EDITION: new crates and workspaces use edition 2024 (latest stable); every example here does. [M-LATEST-EDITION]
- R-RSPJ-MSRV: always set `rust-version` (edition 2024 needs at least 1.85); a service sets it to its pinned toolchain; published crates only: keep it a few releases behind and bump it in a minor release. [proj-msrv-declare, M-MSRV]
- R-RSPJ-FEATURES-ADDITIVE: a Cargo feature only adds; `std` is a feature, `no-std` is not; no mutually exclusive features in libraries. [proj-feature-additive]
- R-RSPJ-BUILD-RS: `build.rs` is short, deterministic, emits `rerun-if-changed` for everything it reads, never uses the network, writes only to `OUT_DIR`. [proj-build-rs-minimal]

## Rules: lints and verification

- R-RSPJ-LINT-OWNER: only ci-engineer changes lint configuration (`[workspace.lints]`, `[lints]`, `clippy.toml`, `rustfmt.toml`, crate-level lint attributes, CI lint steps); everyone else uses `#[expect]` on one item and reports the question. [own rule]
- R-RSPJ-LINT-WORKSPACE: one lint table in the workspace root, members take it with `[lints] workspace = true`; a member cannot add `[lints.clippy]` beside it (Cargo rejects the manifest); groups get `priority = -1`. [lint-workspace-lints, M-STATIC-VERIFICATION]
- R-RSPJ-LINT-GROUPS: `correctness` deny; `suspicious`, `style`, `complexity`, `perf` warn; CI runs `cargo clippy --workspace --all-targets -- -D warnings`; an `await_holding_lock` finding is fixed, not silenced. [lint-deny-correctness, lint-warn-suspicious, lint-warn-style, lint-warn-complexity, lint-warn-perf]
- R-RSPJ-LINT-PEDANTIC: `pedantic` warn at `priority = -1` with a short, commented list of opt-outs (`missing_errors_doc`, `missing_panics_doc`, `must_use_candidate`). [lint-pedantic-selective]
- R-RSPJ-LINT-NURSERY: never the whole `nursery` group; pick single lints after reading their findings. [lint-clippy-nursery-selected]
- R-RSPJ-LINT-UNWRAP: `unwrap_used` deny, `expect_used` not set, `panic` not set (panic policy of `rules/rust.md`); `allow-unwrap-in-tests = true` covers `#[test]` functions, not helpers in `tests/` files, which use `expect("why")`. [lint-workspace-lints, rules/rust.md]
- R-RSPJ-LINT-EXPECT: override a lint with `#[expect(lint, reason = "...")]`, never `#[allow]`; `#[allow]` only in generated code and macros. [M-LINT-OVERRIDE-EXPECT]
- R-RSPJ-LINT-UNSAFE-DOC: every `unsafe` block has a `// SAFETY:` comment naming a check that holds in release builds; one unsafe operation per block; an `unsafe fn` has `# Safety`; `unsafe_code = "deny"` and `#[expect(unsafe_code, reason)]` on the block or fn. [lint-unsafe-doc, M-STATIC-VERIFICATION]
- R-RSPJ-LINT-CFG-CHECK: custom cfgs are declared in `unexpected_cfgs` `check-cfg` so a typo in `cfg(feature = "...")` warns. [lint-cfg-check]
- R-RSPJ-LINT-FMT: `cargo fmt --all --check` is a gate; default rustfmt config; only stable options; `imports_granularity`, `group_imports`, `wrap_comments` are nightly. [lint-rustfmt-check]
- R-RSPJ-LINT-CARGO: published crates only: `clippy::cargo` at warn, full package metadata, no `*` versions, `multiple_crate_versions` allowed. [lint-cargo-metadata]
- R-RSPJ-LINT-MISSING-DOCS: published crates only: `missing_docs = "warn"`; exceptions by `#[expect]`. [lint-missing-docs]
- R-RSPJ-STATIC-VERIFY: fmt, clippy `-D warnings`, tests and `cargo audit` gate check-in; `cargo hack` for libraries with features; `cargo miri` (nightly) for crates with `unsafe`; wiring is ci-engineer's. [M-STATIC-VERIFICATION]

## Decision tables

### Layout by size

| Size | Layout |
|---|---|
| under about 10 files | flat `src/`, `lib.rs` + `main.rs` |
| a concept with 3+ files | folder per entity: `order.rs` + `order/order_{handler,service,repository}.rs` |
| 2+ crates that belong together | workspace, `crates/*`, virtual root |
| several binaries, one library | `src/bin/<name>.rs` |

### Visibility

| Who needs the item | Write |
|---|---|
| only this module (and its children) | nothing |
| sibling modules under the same parent | `pub(super)` |
| anywhere in the crate | `pub(crate)` |
| other crates (a real API) | `pub`, and for a library the root path via `pub use` |
| a test | nothing: tests use the public API from `<crate>/tests/` |

### Lint level

| Lint set | Level | Where |
|---|---|---|
| `correctness` | deny | workspace table |
| `suspicious`, `style`, `complexity`, `perf` | warn (`-D warnings` in CI) | workspace table |
| `pedantic` | warn, `priority = -1`, listed opt-outs | workspace table |
| `unwrap_used` | deny | workspace table + `clippy.toml` |
| `nursery` | single lints only | workspace table, ci-engineer |
| `cargo`, `missing_docs` | warn, published crates only | workspace table |
| one item that needs an exception | `#[expect(lint, reason = "...")]` | the item |

### Which rule applies to a service or a library

| Rule | Service (`publish = false`) | Published library |
|---|---|---|
| R-RSPJ-REEXPORT, R-RSPJ-LINT-CARGO, R-RSPJ-LINT-MISSING-DOCS | no | yes |
| R-RSPJ-MSRV: conservative window | no (pinned toolchain) | yes |
| R-RSPJ-FEATURES-ADDITIVE | as a habit | strict |
| all others | yes | yes |

## Dropped and rewritten

Dropped:

- `proj-prelude-module`: a `prelude` module makes every item reachable by two paths (M-SINGLE-ITEM-PATH) and invites glob imports (`clippy::wildcard_imports`).
- The test-visibility patterns of `proj-pub-crate-internal` and `proj-pub-super-parent` (`#[cfg(test)]` accessors, `__test_helpers`, `mod tests` in `src/`): tests live in `<crate>/tests/`.

Rewritten (details under each rule in the references): `lint-warn-suspicious` (no `warn` key in `clippy.toml`; real group members), `lint-workspace-lints` (no per-crate override next to `workspace = true`), `lint-deny-correctness` (compiler errors shown as lints), `lint-clippy-nursery-selected` (wrong groups), `lint-pedantic-selective` (missing priority), `lint-unsafe-doc` (unsound safe fn), `proj-msrv-declare` (edition 2024 with `rust-version = "1.80"`), `proj-pub-super-parent` (wrong visibility diagram), `proj-mod-by-feature` (file names), `proj-workspace-deps` and `proj-workspace-large` (editions, versions), `proj-build-rs-minimal` (unverified API), `proj-mod-rs-dir` (unsupported claims).
