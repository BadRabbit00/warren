# Lint, format and verification rules (source: leonardomso `lint-*`, Microsoft `M-STATIC-VERIFICATION`, `M-LINT-OVERRIDE-EXPECT`)

Full text of the kept rules. Short form and ids: `../SKILL.md`. Every lint name and group below was checked against clippy 0.1.99 (`cargo clippy -- -W help`), and the workspace configuration in R-RSPJ-LINT-WORKSPACE was run on a two-crate workspace. Group membership changes between releases; re-check with `cargo clippy -- -W help` when a lint is missing.

## Who changes lint configuration

### R-RSPJ-LINT-OWNER — only ci-engineer changes lint configuration [own rule]

Why: one place decides the lint set; a coder who loosens a lint to get a green build hides the problem for the next person.

Lint configuration is: `[workspace.lints]` and `[lints]` in `Cargo.toml`, `clippy.toml`, `rustfmt.toml`, crate-level `#![allow/warn/deny]` attributes, and the clippy and rustfmt steps in CI. In our projects only ci-engineer edits it. Anyone else who needs a different level for one item writes `#[expect(lint, reason = "...")]` on that item (R-RSPJ-LINT-EXPECT) and reports the question; a change for the whole project is a task for ci-engineer.

Bad:
```rust
// top of lib.rs, added to make the build pass
#![allow(clippy::pedantic)]
#![allow(unused)]
```

Good:
```rust
#[expect(clippy::too_many_arguments, reason = "mirrors the wire format; a struct would add a copy")]
pub fn encode(a: u8, b: u8, c: u8, d: u8, e: u8, f: u8, g: u8, h: u8) -> [u8; 8] {
    [a, b, c, d, e, f, g, h]
}
```

## Workspace configuration

### R-RSPJ-LINT-WORKSPACE — one lint table at the workspace root [lint-workspace-lints, M-STATIC-VERIFICATION]

Why: crates that choose their own lints drift apart. Cargo can share one table: `[workspace.lints]` at the root, `[lints] workspace = true` in each member.

Bad:
```toml
# crates/a/Cargo.toml
[lints.clippy]
unwrap_used = "deny"

# crates/b/Cargo.toml: no lint section
# crates/c/Cargo.toml
[lints.clippy]
unwrap_used = "warn"
```

Good:
```toml
# Cargo.toml (root)
[workspace.lints.rust]
unsafe_code = "deny"
ambiguous_negative_literals = "warn"
missing_debug_implementations = "warn"
redundant_imports = "warn"
redundant_lifetimes = "warn"
trivial_numeric_casts = "warn"
unsafe_op_in_unsafe_fn = "warn"
unused_lifetimes = "warn"
unexpected_cfgs = { level = "warn", check-cfg = ["cfg(tokio_unstable)"] }

[workspace.lints.clippy]
# groups first, at a lower priority than single lints
correctness = { level = "deny", priority = -1 }
suspicious = { level = "warn", priority = -1 }
style = { level = "warn", priority = -1 }
complexity = { level = "warn", priority = -1 }
perf = { level = "warn", priority = -1 }
pedantic = { level = "warn", priority = -1 }

# restriction picks
unwrap_used = "deny"
dbg_macro = "warn"
todo = "warn"
unimplemented = "warn"
allow_attributes = "warn"
allow_attributes_without_reason = "warn"
undocumented_unsafe_blocks = "warn"
multiple_unsafe_ops_per_block = "warn"
clone_on_ref_ptr = "warn"
map_err_ignore = "warn"
unused_result_ok = "warn"
assertions_on_result_states = "warn"

# pedantic opt-outs
missing_errors_doc = "allow"
missing_panics_doc = "allow"
must_use_candidate = "allow"

# crates/a/Cargo.toml, crates/b/Cargo.toml, ...
[lints]
workspace = true
```

```toml
# clippy.toml
allow-unwrap-in-tests = true
```

Consistent levels: the panic policy of `rules/rust.md` decides the restriction picks. A detected bug panics with a message, so `clippy::panic` is not denied; `unwrap()` outside tests is banned, so `unwrap_used` is denied; `expect("why it cannot fail")` is allowed, so `expect_used` is not set. `unsafe_code = "deny"` (not `forbid`) lets a justified block opt out with `#[expect(unsafe_code, reason = "...")]`. `cargo clippy --workspace --all-targets -- -D warnings` in CI turns every `warn` above into an error. Published libraries add R-RSPJ-LINT-CARGO and R-RSPJ-LINT-MISSING-DOCS.

A member crate cannot extend the shared table. `[lints] workspace = true` together with a `[lints.clippy]` table in the same manifest does not load: Cargo stops with "cannot override `workspace.lints` in `lints`, either remove the overrides or `lints.workspace = true` and manually specify the lints" (checked). For one item use `#[expect]`; for one crate that really needs another set, drop `workspace = true` there and write its whole table, with ci-engineer's agreement.

Groups are listed before single lints only for readability; Cargo ignores table order. What matters is `priority = -1` on the groups: a group at the default priority 0 next to single lints triggers the deny-by-default lint `clippy::lint_groups_priority` (checked).

Corrected from the source: its example put `[lints] workspace = true` and a per-crate `[lints.clippy]` override side by side (does not load), denied `clippy::panic`, listed `cognitive_complexity` under nursery (it is restriction), and used edition 2021 and old dependency versions in its examples.

### R-RSPJ-LINT-GROUPS — correctness denied, suspicious / style / complexity / perf warned [lint-deny-correctness, lint-warn-suspicious, lint-warn-style, lint-warn-complexity, lint-warn-perf]

Why: these five groups are the stable, low-noise part of clippy. Correctness lints flag code that is wrong; the others flag likely bugs, clumsy code and avoidable cost. Clippy already denies `correctness` and warns the other four by default; writing them in the workspace table pins the set, so a clippy upgrade or a stray attribute does not change it quietly.

Bad:
```rust
pub fn pi() -> f64 {
    3.14159                       // clippy::approx_constant (correctness, deny)
}

pub fn first(v: &[u32]) -> u32 {
    for x in v {
        return *x;                // clippy::never_loop (correctness, deny)
    }
    0
}

pub async fn hold(m: &std::sync::Mutex<u32>) {
    let g = m.lock().expect("lock poisoned");
    other().await;                // clippy::await_holding_lock (suspicious, warn)
    drop(g);
}
```

Good:
```rust
pub fn pi() -> f64 {
    std::f64::consts::PI
}

pub fn first(v: &[u32]) -> u32 {
    v.first().copied().unwrap_or(0)
}

pub async fn hold(m: &std::sync::Mutex<u32>) {
    let value = *m.lock().expect("lock poisoned");   // guard dropped at the end of the statement
    other().await;
    let _ = value;
}
```

Members you will meet (all checked in clippy 0.1.99):

| Group | Level | Examples |
|---|---|---|
| `correctness` | deny | `approx_constant`, `eq_op`, `invalid_regex`, `iter_next_loop`, `never_loop`, `unit_cmp`, `absurd_extreme_comparisons`, `not_unsafe_ptr_arg_deref`, `nonsensical_open_options` |
| `suspicious` | warn | `await_holding_lock`, `await_holding_refcell_ref`, `arc_with_non_send_sync`, `mutable_key_type`, `unconditional_recursion`, `suspicious_arithmetic_impl`, `suspicious_else_formatting`, `suspicious_map`, `empty_loop` |
| `style` | warn | `len_zero`, `needless_return`, `redundant_closure`, `redundant_field_names`, `collapsible_if`, `single_match`, `match_like_matches_macro`, `question_mark`, `let_and_return` |
| `complexity` | warn | `bind_instead_of_map`, `bool_comparison`, `clone_on_copy`, `filter_next`, `manual_flatten`, `unnecessary_cast`, `useless_conversion`, `unnecessary_literal_unwrap` |
| `perf` | warn | `large_enum_variant`, `manual_memcpy`, `redundant_allocation`, `slow_vector_initialization`, `unnecessary_to_owned`, `useless_vec`, `vec_init_then_push`, `extend_with_drain` |

An `await_holding_lock` finding is a real defect in async code (R-RS-ASYNC): fix the code, do not silence the lint.

Corrected from the source: the four `warn` rules invented behaviour. `lint-warn-suspicious` said `clippy.toml` accepts `warn = ["clippy::suspicious"]` (clippy rejects it: "unknown field name"; levels belong in `Cargo.toml` or in attributes) and listed things that are not in the group (`--x`, `x % 1`, the float cast, `if (x = 5)`, which is a compile error and not a lint). `lint-deny-correctness` showed a use-after-free and an assignment in a condition, which are compiler errors. `single_char_pattern` and `search_is_some` are not in `perf` / `complexity` now (pedantic and nursery); `iter_nth` is style. The tables above replace them.

### R-RSPJ-LINT-PEDANTIC — pedantic as a baseline with listed opt-outs [lint-pedantic-selective]

Why: `clippy::pedantic` is opinionated; enabling it whole and then listing the lints that do not fit gives a documented, reviewable set. Enabling it with no opt-outs fights every project.

Bad:
```toml
[lints.clippy]
pedantic = "warn"
missing_errors_doc = "allow"      # same priority as the group: clippy::lint_groups_priority fires
```

Good:
```toml
[workspace.lints.clippy]
pedantic = { level = "warn", priority = -1 }
missing_errors_doc = "allow"        # errors are documented in the type, not on each fn
missing_panics_doc = "allow"
must_use_candidate = "allow"        # too many findings on plain getters
```

Useful pedantic members to keep: `doc_markdown`, `needless_pass_by_value`, `redundant_closure_for_method_calls`, `semicolon_if_nothing_returned`, `unused_self`, `wildcard_imports`, `match_wildcard_for_single_variants` (agrees with R-RS-TYPES), `unused_async`, `redundant_else`, `unnested_or_patterns`, `string_add_assign`. Common opt-outs: `missing_errors_doc`, `missing_panics_doc`, `must_use_candidate`, `too_many_lines`, `similar_names`, `struct_excessive_bools`.

Write every opt-out in the workspace table with a comment. Removing an opt-out later is a ci-engineer change (R-RSPJ-LINT-OWNER); adding one needs the reason in the diff.

Corrected from the source: it opted out of `module_name_repetitions`, which is a restriction lint and not on by default (the line did nothing); its "Full configuration" listed pedantic lints that the group already enables; its `#![allow(...)]` and `#[allow(...)]` examples are replaced by the workspace table and `#[expect]`.

### R-RSPJ-LINT-NURSERY — pick nursery lints one by one [lint-clippy-nursery-selected]

Why: `clippy::nursery` lints are still being refined, so the group produces false positives and changes between releases. A few of them are worth it as single lints.

Bad:
```toml
[lints.clippy]
nursery = "warn"
```

Good:
```toml
[workspace.lints.clippy]
significant_drop_tightening = "warn"   # a lock guard lives longer than the code that needs it
redundant_clone = "warn"               # .clone() where a move would do
use_self = "warn"                      # repeated type name inside impl
or_fun_call = "warn"                   # unwrap_or(String::from("x")) -> unwrap_or_else
```

```rust
// significant_drop_tightening fires: the guard is alive during other()
pub fn tight(m: &std::sync::Mutex<Vec<u32>>) -> usize {
    let g = m.lock().expect("lock poisoned");
    let n = g.len();
    other();
    n
}

// fixed
pub fn tight(m: &std::sync::Mutex<Vec<u32>>) -> usize {
    let n = m.lock().expect("lock poisoned").len();
    other();
    n
}
```

Treat the list as optional: add a nursery lint only after running it over the code base and reading the findings. `redundant_clone` and the others can disappear or move groups on a clippy upgrade; a lint name clippy no longer knows becomes a warning.

Corrected from the source: it put `redundant_else` in nursery (it is pedantic, so already on), described `or_fun_call` as "prefer `or_default()`" (it asks for a lazy `or_else` / `unwrap_or_else` when the argument is a function call) and claimed `significant_drop_tightening` catches guards held across `.await` (that is `clippy::await_holding_lock`, suspicious).

### R-RSPJ-LINT-UNWRAP — `unwrap()` is denied outside tests [own rule from rules/rust.md, lint-workspace-lints]

Why: R-RS-ERRORS bans `unwrap()` outside tests; the lint makes the compiler say it. `expect("why it cannot fail")` stays legal because it states the invariant.

Bad:
```rust
let id = Uuid::parse_str(&raw).unwrap();      // clippy::unwrap_used: error
```

Good:
```rust
let id = Uuid::parse_str(&raw).map_err(|_| OrderError::BadId)?;
let state = CACHE.lock().expect("cache mutex is never poisoned: no code panics while holding it");
```

Test code: `allow-unwrap-in-tests = true` in `clippy.toml` covers functions marked `#[test]` and `#[cfg(test)]` modules. It does not cover helper functions in files under `<crate>/tests/` (checked: clippy still reports `unwrap_used` there), so write `.expect("what the helper needs")` in helpers. The test files themselves belong to test-writer; the lint table belongs to ci-engineer.

### R-RSPJ-LINT-EXPECT — override a lint with `#[expect]` and a reason [M-LINT-OVERRIDE-EXPECT]

Why: `#[expect]` warns when the lint no longer fires, so overrides cannot go stale. `#[allow]` stays silent forever. The reason tells the reviewer why the exception is legitimate. Enforce it with `allow_attributes` and `allow_attributes_without_reason` (R-RSPJ-LINT-WORKSPACE).

Bad:
```rust
#[allow(dead_code)]
fn parse_legacy() {}
```

Good:
```rust
#[expect(dead_code, reason = "called from the legacy importer behind the `legacy` feature")]
fn parse_legacy() {}
```

Checked: a stale `#[expect(dead_code, reason = "stale")]` on a used function produces "this lint expectation is unfulfilled". `#[allow]` remains right for generated code and macro output, where the lint may or may not fire.

## Unsafe

### R-RSPJ-LINT-UNSAFE-DOC — every unsafe block has a `// SAFETY:` comment [lint-unsafe-doc, M-STATIC-VERIFICATION]

Why: unsafe code is where memory-safety bugs live. The comment states why this block is sound, so a reviewer can check the claim. Enable `clippy::undocumented_unsafe_blocks` and `clippy::multiple_unsafe_ops_per_block` (one unsafe operation per block). Together with `unsafe_op_in_unsafe_fn` they enforce R-RS-UNSAFE.

Bad:
```rust
pub fn read_data(ptr: *const u8, len: usize) -> &'static [u8] {
    unsafe { std::slice::from_raw_parts(ptr, len) }
}
```

Good:
```rust
/// Reads `len` bytes starting at `ptr`.
///
/// # Safety
///
/// `ptr` must be valid for reads of `len` initialized bytes and aligned for `u8`,
/// and no `&mut` to that memory may exist for `'a`.
#[expect(unsafe_code, reason = "raw slice view for the FFI layer")]
pub unsafe fn read_data<'a>(ptr: *const u8, len: usize) -> &'a [u8] {
    // SAFETY: the caller upholds the contract in `# Safety`.
    unsafe { std::slice::from_raw_parts(ptr, len) }
}
```

A SAFETY comment states which invariants are relied on and why they hold at this place. It names a check that exists in every build profile.

```rust
pub fn byte(&self, index: usize) -> Option<u8> {
    if index < self.data.len() {
        #[expect(unsafe_code, reason = "bounds checked on the line above")]
        // SAFETY: `index < self.data.len()` was checked just above, in every build profile.
        let b = unsafe { *self.data.get_unchecked(index) };
        Some(b)
    } else {
        None
    }
}
```

Both examples were compiled and linted with `unsafe_code = "deny"` and the lints above; the expectations were fulfilled.

Corrected from the source: its Good example was a safe `pub fn` taking a raw pointer and returning a reference, which is unsound (a safe function must not be able to cause undefined behaviour; clippy denies it as `not_unsafe_ptr_arg_deref`) and has no lifetime. Its second example justified `get_unchecked` with a `debug_assert!`, which is absent in release builds, so the comment was false.

## Cfg, format, metadata and docs

### R-RSPJ-LINT-CFG-CHECK — declare custom cfgs so typos are caught [lint-cfg-check]

Why: `#[cfg(feature = "serde_")]` compiles and silently disables the block. The `unexpected_cfgs` lint (Rust 1.80+) warns about names and values the compiler does not know. Cargo declares your features automatically; other cfgs must be listed.

Bad:
```rust
#[cfg(feature = "serde_")]          // typo: never true, no warning without the lint
impl serde::Serialize for Order { /* ... */ }
```

Good:
```toml
[workspace.lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ["cfg(tokio_unstable)", "cfg(coverage_nightly)"] }
```

```rust
#[cfg(feature = "serde")]           // known feature; a typo now warns
impl serde::Serialize for Order { /* ... */ }
```

Entries are `cfg(name)` or `cfg(name, values("a", "b"))`. In a workspace put the table at the root (R-RSPJ-LINT-WORKSPACE). Custom cfgs emitted by `build.rs` are declared with `cargo::rustc-check-cfg=cfg(my_flag)` in the script (R-RSPJ-BUILD-RS).

### R-RSPJ-LINT-FMT — `cargo fmt --all --check` is a gate [lint-rustfmt-check]

Why: one format ends style discussion and keeps diffs small. The default rustfmt configuration is the baseline; do not add a `rustfmt.toml` without a reason.

Bad:
```toml
# rustfmt.toml: needs a nightly rustfmt; stable ignores the options with a warning
unstable_features = true
imports_granularity = "Crate"
group_imports = "StdExternalCrate"
wrap_comments = true
```

Good:
```toml
# rustfmt.toml: stable options only (and only if the default does not fit)
max_width = 100
use_small_heuristics = "Max"
```

```text
cargo fmt --all            # fix
cargo fmt --all --check    # gate, in CI and before a commit
```

Nightly only (marked): `imports_granularity`, `group_imports`, `wrap_comments`, `format_code_in_doc_comments`; `rustfmt --help=config` on the stable toolchain does not list them. Use `#[rustfmt::skip]` for hand-aligned tables, with a comment. Editors format on save from the project `rustfmt.toml`; the CI step is ci-engineer's. The edition comes from `Cargo.toml`, so `edition` is not repeated in `rustfmt.toml`.

### R-RSPJ-LINT-CARGO — published crates: `clippy::cargo` and complete metadata [lint-cargo-metadata]

Why: for a crate that goes to a registry, missing description, licence or repository, wildcard versions and badly named features are defects. Services (`publish = false`) skip this rule.

Bad:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"

[dependencies]
serde = "*"
```

Good:
```toml
[package]
name = "my-crate"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
description = "What the crate does in one line"
license = "MIT OR Apache-2.0"
repository = "https://github.com/example/my-crate"
readme = "README.md"
keywords = ["example"]
categories = ["development-tools"]

[dependencies]
serde = { version = "1", default-features = false }

[lints.clippy]
cargo = { level = "warn", priority = -1 }
multiple_crate_versions = "allow"   # a large tree cannot always be deduplicated
```

`clippy::cargo` members: `cargo_common_metadata`, `multiple_crate_versions`, `wildcard_dependencies`, `negative_feature_names`, `redundant_feature_names`. Name a feature for what it adds (`std`), not what it removes (`no-std`). The `[lints.clippy]` table above is for a single published crate; in a workspace it goes into `[workspace.lints.clippy]` (R-RSPJ-LINT-WORKSPACE), and `[package]` fields can come from `[workspace.package]`.

### R-RSPJ-LINT-MISSING-DOCS — published crates: `missing_docs` [lint-missing-docs]

Why: for a library the documentation is the interface. The lint finds public items without `///`. Services have no external readers and skip this rule; what a doc comment should contain is in skill `rust-docs`.

Bad:
```rust
pub struct User {
    pub name: String,           // warning: missing documentation for a struct field
}
```

Good:
```toml
[workspace.lints.rust]
missing_docs = "warn"
```

```rust
/// A registered user.
pub struct User {
    /// Display name shown in the interface.
    pub name: String,
}
```

For an item that is deliberately undocumented, `#[expect(missing_docs, reason = "...")]`. Roll the lint out in an old crate as `warn` first and fix the findings before `-D warnings` makes it an error. `missing_docs` only looks at public items; private ones never warn.

Corrected from the source: `#[allow(missing_docs)]` is replaced by `#[expect]`.

## Verification tools

### R-RSPJ-STATIC-VERIFY — static checks are a check-in gate [M-STATIC-VERIFICATION]

Why: tools that run on every change keep the code consistent and free of common defects; run by hand they are skipped.

| Tool | Checks | Notes |
|---|---|---|
| compiler lints | bugs, quality | the `[workspace.lints.rust]` set in R-RSPJ-LINT-WORKSPACE |
| `cargo clippy --workspace --all-targets -- -D warnings` | hundreds of lints | the gate from `rules/rust.md` |
| `cargo fmt --all --check` | formatting | R-RSPJ-LINT-FMT |
| `cargo audit` | dependencies with known vulnerabilities | not in the dev shell by default; a new tool is a dependency, say so |
| `cargo hack check --feature-powerset` | every feature combination builds | libraries with features (R-RSPJ-FEATURES-ADDITIVE) |
| `cargo udeps` | unused dependencies | needs a nightly toolchain (U: check the current tool documentation) |
| `cargo miri test` | undefined behaviour in unsafe code | nightly only; for crates with `unsafe` |

Bad:
```text
CI: cargo build && cargo test           # no lint, format or audit step
```

Good:
```text
CI: cargo fmt --all --check
    cargo clippy --workspace --all-targets -- -D warnings
    cargo test --workspace
    cargo audit
```

Wiring these steps into CI is ci-engineer's task; this rule says which checks a project should have. The compiler and clippy sets are in R-RSPJ-LINT-WORKSPACE (the Microsoft lists were merged with leonardomso's groups and with our panic policy: Microsoft's `correctness = "warn"` became `deny`, and `unwrap_used` was added).
