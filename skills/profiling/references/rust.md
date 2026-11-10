# Rust - cargo-flamegraph and perf

Tools: `cargo-flamegraph` (wraps `perf`), `perf`, `flamegraph.pl` (FlameGraph; whether the stackcollapse scripts ship with it is (U)). Linux only; cargo-flamegraph uses `perf` there.

## Commands

| Goal | Command |
|---|---|
| Flame graph of the default binary | `CARGO_PROFILE_RELEASE_DEBUG=true cargo flamegraph` |
| Output file | `-o /tmp/prof-<id>/before.svg` (U: verify `-o` with `cargo flamegraph --help`) |
| A specific binary / benchmark | `--bin <name>`, `--bench <name>` (U: verify with `--help`) |
| Raw perf | `perf record …`, `perf report` (U: exact flags) |

Without `-o` the SVG is written to the current directory (U) - always pass `-o`.

By default `cargo flamegraph` profiles `cargo run --release`. Symbols need debug info in the release profile: `debug = true` under `[profile.release]`, or the environment variable `CARGO_PROFILE_RELEASE_DEBUG=true`. Use the variable: the agent does not edit `Cargo.toml`.

Build output goes to `target/` in the project by default; redirect it with `CARGO_TARGET_DIR=/tmp/prof-<id>/target` (U: not in the research, a standard cargo variable - verify).

## Workflow

1. `mkdir -p /tmp/prof-<id>`; baseline wall time and peak memory of the scenario first.
2. Run the scenario under `cargo flamegraph` with the load; for a service, the load script runs from another shell and the program is stopped when the run ends (U: how the service is stopped cleanly so the SVG is written).
3. Read the SVG: wide plateaus at the top of stacks. Inlined functions may be merged; that is normal in release builds.
4. After the change: same scenario, `after.svg`.

## Permissions

Unprivileged `perf` needs a lowered `kernel.perf_event_paranoid` or `CAP_PERFMON` (the flamegraph README suggests `echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid`; the agent does not do that). Report the requirement. Inside containers, `CAP_PERFMON` and seccomp are (U). Fallback without perf: time and allocation counts from the project's own benchmarks.

## Memory

Not covered by the research. Use peak RSS from the OS (U: `/usr/bin/time -v`), and say `not measured` if unavailable.
