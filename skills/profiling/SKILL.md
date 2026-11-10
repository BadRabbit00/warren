---
name: profiling
description: Use when a performance claim needs numbers - a slow endpoint, high CPU, growing memory - before proposing a change. Gives the measure-first method and exact py-spy, Go pprof and Rust cargo-flamegraph/perf commands, with outputs kept in a temp dir.
---

# Profiling

Measure first, propose second. Python, Go and Rust services only (no Node backends). Commands per language are in `references/`.

## When to use

- A finding says "slow", "wasteful", or "uses too much memory" and it can be checked by running the code.
- A before/after comparison is needed to confirm that a fix helps.
- Not for: database query plans (`db-reviewer`), guessing on cold paths.

## Contents

1. [Method](#method)
2. [Where outputs go](#where-outputs-go)
3. [Running the tools](#running-the-tools)
4. [Permissions](#permissions)
5. [Reading results](#reading-results)
6. [Stating a finding](#stating-a-finding)
7. [Rules](#rules)
8. [References](#references)

## Method

1. **Reproduce** the slow scenario or a realistic load first: the same request, input size, and data as in production terms. A profile of an idle process shows nothing. Only local test services; never a shared or production system.
2. **Baseline** before any proposal: wall time, CPU time, peak memory, repeated at least 3 times; note the spread.
3. **One profile per hypothesis.** Write the hypothesis ("the time goes to JSON encoding") before profiling; the profile confirms or kills it.
4. **Propose** the change only for what the profile shows.
5. **Compare** after: the same scenario, the same load, the same metrics, the same tool.

## Where outputs go

All profiles, flame graphs, binaries, and build output live in `/tmp/prof-<id>/` (`<id>` = task or wave id). Never in the project tree: no `flamegraph.svg`, `*.pprof`, `pkg.test`, or `target/` next to the code. Create the directory first (`mkdir -p /tmp/prof-<id>`). Delete nothing outside it.

## Running the tools

Run each tool directly; it must be on `PATH`:

| Tool | Command | Note |
|---|---|---|
| py-spy | `py-spy …` | Python sampling profiler |
| Go pprof | `go tool pprof …` (part of the Go toolchain) | Graphviz for graph reports |
| Rust | `cargo flamegraph …` | `cargo-flamegraph`, wraps `perf` |
| perf | `perf …` | Linux |
| flamegraph.pl | `flamegraph.pl …` | FlameGraph scripts |

The project's `requirements.md` lists the tools; if one is missing, report it, do not install it.

## Permissions

- `py-spy` attaching to a process that is not its child needs root or a relaxed `ptrace_scope` on Linux; in Docker it needs `SYS_PTRACE`. Launching the program under py-spy (`py-spy record … -- python prog.py`) avoids attaching.
- `perf` (and so `cargo flamegraph`) as an unprivileged user needs a lowered `kernel.perf_event_paranoid` or `CAP_PERFMON`.
- The agent never uses `sudo`, never writes `/proc/sys/*`, never changes `ptrace_scope`, capabilities, or container flags. When a profile is blocked, stop and report the exact requirement (see R-PROF-NO-SYSTEM-CHANGES), then continue with what works without it (for example `py-spy` launch mode, `go tool pprof`, `go test -cpuprofile`).

## Reading results

- **Self vs total.** Self (flat) = time in the function's own code; total (cumulative) = self plus everything it calls. High total, low self: look at its callees. High self: the cost is in that function.
- **Top functions.** Sort by self; the first 5 to 10 usually hold the answer. A function under 1-2% of samples is not worth a proposal.
- **Flame graph.** Width = share of samples (time), not call count. The x-axis order is alphabetical, not chronological. Height = stack depth. Look for wide boxes at the top of a stack (plateaus): that is where time is spent.
- **Memory.** Heap profiles show live allocations (what is held) or total allocations (churn); say which one you read.
- **Overhead.** Profilers cost something (the Go docs say enabling some profiles, such as CPU, adds cost); compare profiles taken with the same settings.
- **Samples.** A short run gives noisy profiles; use a run long enough for hundreds of samples in the hot function (U: py-spy default sampling rate, verify with `py-spy record --help`).

## Stating a finding

Give the scenario, the metric, before, after, and the delta in %, plus where the profile file is:

```text
scenario: GET /v1/catalog?limit=100, 50 sequential requests, local stack
before: p50 410 ms, CPU 100% of one core; json.dumps 46% self (/tmp/prof-W3/before.svg)
after:  p50 230 ms (-44%); json.dumps 9% self (/tmp/prof-W3/after.svg)
```

Without an "after", write `not measured` and give the expected gain as an estimate, labelled so.

## Rules

### R-PROF-BASELINE-FIRST — baseline before a proposal

Bad:
```text
fix: add an lru_cache to build_report(); it is probably the slow part
```
Why: no baseline and no profile; the change may not touch the real bottleneck.

Good:
```text
baseline: build_report() 1.8 s wall (3 runs: 1.78 / 1.81 / 1.83), 310 MB peak
profile:  /tmp/prof-W3/report.svg - 62% self in row_to_dict()
fix:      build dicts once per row, not per column
```

### R-PROF-TEMP-ONLY — outputs only in the temp dir

Bad:
```text
$ py-spy record -o profile.svg --pid 4242          # lands in the project dir
$ go test -cpuprofile cpu.out ./...                # also leaves ./pkg.test
```
Why: profiles and test binaries end up in the repository tree and can be committed.

Good:
```text
$ mkdir -p /tmp/prof-W3
$ py-spy record -o /tmp/prof-W3/before.svg --pid 4242
```

### R-PROF-NUMBERS — findings carry numbers

Bad:
```text
The serializer is slow and was optimised.
```
Why: no way to check the claim or rank it.

Good:
```text
serialize() 38% self before -> 7% after; request p50 410 ms -> 240 ms (-41%), same load, 3 runs each.
```

### R-PROF-NO-SYSTEM-CHANGES — report what is needed, do not change the system

Bad:
```text
$ echo -1 | sudo tee /proc/sys/kernel/perf_event_paranoid
```
Why: changes the machine's security settings, outside the task and without the user's consent.

Good:
```text
BLOCKED for perf: unprivileged perf needs a lowered kernel.perf_event_paranoid or CAP_PERFMON.
Needed from the user: one of those. Meanwhile: go tool pprof / py-spy launch mode, which need neither.
```

### R-PROF-ONE-HYPOTHESIS — one profile per hypothesis

Bad:
```text
One 10-minute profile of everything; "the top function is X, so X is the problem".
```
Why: it mixes scenarios; the top function may belong to an unrelated path.

Good:
```text
H1: the time is in JSON encoding -> profile only GET /v1/catalog under load -> json is 4% -> H1 rejected.
H2: the time is in the per-item price call -> profile again -> 71% waiting in PriceClient.get -> confirmed.
```

## References

- [Python (py-spy)](references/python.md)
- [Go (pprof)](references/go.md)
- [Rust (cargo-flamegraph, perf)](references/rust.md)

Items marked `(U)` were not confirmed by the research: check them with `--help` or the tool's docs before relying on them.
