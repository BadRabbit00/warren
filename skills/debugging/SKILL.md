---
name: debugging
description: Use when reproducing a reported bug and finding its root cause without fixing it - the reproduction package, N-run verdicts, narrowing (minimise input, git bisect run, config toggles), non-interactive debuggers for Python, Go, Rust and browser frontends, and the root-cause report with file:line evidence.
---

# Debugging

Discipline for the `/br-debug` workflow. Rule ids `R-DBG-*`. Nobody in this workflow fixes code: the product is a report. The orchestrator then sends `test-writer` for a failing test and the normal red → green → log → refactor follows.

Facts marked `(U) verify` are not confirmed by sources read for this project; check them locally before relying on them.

## When to use

- `bug-reproducer` (Sonnet): turns a user's bug report into exact reproduction steps or a script, with expected vs actual.
- `repro-runner` (Haiku): runs the reproduction N times, collects output, logs, exit codes, and decides flaky or stable.
- `root-cause-analyst` (Opus): finds the root cause with file:line evidence.

## Contents

1. [Roles and hand-offs](#roles-and-hand-offs)
2. [What counts as reproduced](#what-counts-as-reproduced)
3. [Evidence sources](#evidence-sources)
4. [Narrowing techniques](#narrowing-techniques)
5. [Non-interactive debuggers](#non-interactive-debuggers)
6. [Boundaries](#boundaries)
7. [Rules](#rules)
8. [References](#references)

## Roles and hand-offs

| Role | Receives | Hands over |
|---|---|---|
| `bug-reproducer` | the user's bug report, the repo | **Repro package** in `/tmp/repro-<id>/`: steps or a script; environment (language and tool versions, commit, seed, time, config without secrets); expected vs actual; the exact command |
| `repro-runner` | the repro package | **Runner report**: N runs; pass/fail per run; exit code and output per run; log excerpts at DEBUG; verdict stable or flaky with the rate |
| `root-cause-analyst` | package and runner report | **Analysis**: root cause; causal chain with `file:line` for each link; why existing tests did not catch it; the smallest failing test to write, described in words (inputs, call, expected result), not written |

If a stage cannot do its part (no reproduction, 0 of N), it hands back that fact with what was tried. It does not guess forward.

## What counts as reproduced

All three hold:

1. The same symptom as in the report (same wrong value, same screen state, same exit).
2. The same error: the same exception type or message, status code, or panic text. A different error is a different bug; report it separately.
3. A stated frequency: N of N runs, or `k of N` with N given. "Sometimes" is not a result.

Run counts: default N = 5 for a deterministic-looking bug, N = 20 when the report says "sometimes" (the orchestrator may override).

## Evidence sources

In order of cost:

1. Logs at DEBUG. Set `LOG_LEVEL=DEBUG` for the run (see the `logging` skill; the lines carry `file`, `line`, `request_id`, `trace_id`). Read the lines before and at the first wrong value.
2. Exit code and stderr of the exact command.
3. Stack trace, panic text, browser console.
4. Non-interactive debugger session (below).
5. Temporary DEBUG logging in a temp copy of the code (never in the project).

## Narrowing techniques

| Technique | Use when | How |
|---|---|---|
| Minimise the input | the failing input is large | halve it, keep the half that still fails; repeat until removing anything makes it pass |
| `git bisect run` | it worked in an older commit | script with the exit-code contract, see below |
| Toggle config | the cause may be a flag, env var, version | change one value at a time, record each run |
| Temp DEBUG logging | logs do not show the branch taken | only in a copy under `/tmp/repro-<id>/src/`, see R-DBG-TEMP-ONLY |
| Fix environment | results differ between runs | pin seed, time, versions, see [references/reproduce.md](references/reproduce.md) |

`git bisect run <script>` exit codes: `0` = good (old); `1`-`127` except `125` = bad (new); `125` = skip (this commit cannot be tested); any other code (`>=128`, `255`) aborts the bisect. The script must therefore return `125` for build failures and never let a crash of the tooling look like a bad commit. Bisect runs in a separate worktree or clone in `/tmp`, not in the project checkout.

## Non-interactive debuggers

No agent can type into a prompt. Use batch forms; interactive sessions hang.

| Language | Verified form | Limits |
|---|---|---|
| Python | `python -m pdb -c continue script.py` (`-c` runs pdb commands as `.pdbrc`, since 3.2); `breakpoint()` calls `sys.breakpointhook` (3.7+); `PYTHONBREAKPOINT=0` makes it a no-op | `debugpy` (`python -m debugpy --listen host:port [--wait-for-client] file.py`) needs a DAP client: not self-driving, do not use |
| Go | `dlv test [pkg] -- -test.run X`, `dlv exec <bin>`; flags `--init`, `--headless`, `--continue` (exec), `--accept-multiclient`, `--allow-non-terminal-interactive` | a fully scripted batch recipe (init file contents, exit behaviour) is not verified: (U) verify locally |
| Rust | `lldb -b -o 'cmd' -o 'cmd' target` (batch runs `-s`/`-S`/`-o`/`-O`, then quits) | error handling in batch mode not documented: (U) verify. `rr record <app>`, `rr replay`, `rr -M replay -a` exist, but the rr page names C/C++ on Linux and does not mention Rust: (U) verify |
| Browser frontend | (U) verify: a headless browser driven by the project's e2e tooling (`e2e-testing` skill), reading console and network logs | not covered by the research |

Details and commands: [references/python.md](references/python.md), [references/go.md](references/go.md), [references/rust.md](references/rust.md).

## Boundaries

| Never | Instead |
|---|---|
| Change, create or delete files in the project checkout | work in `/tmp/repro-<id>/` (copy or worktree) |
| Deploy, restart services, run migrations on shared databases | use local or test instances |
| Read production data, logs or hosts | ask the orchestrator; permission is per command, not per task |
| Print secrets from `.env`, tokens, keys | record only that a variable is set (`grep -q '^NAME=.' .env`); mask in excerpts |
| Fix the bug "while there" | describe the fix direction in the analysis, nothing more |

## Rules

### R-DBG-REPRO-FIRST — no analysis without a reproduction

Bad:
```text
Report: "Likely the cache TTL in order_service.py:88 is too short."
(no command was run; no failing output exists)
```
Why: a hypothesis without a run cannot be told from a guess; the fix and the test then aim at the wrong place.

Good:
```text
Reproduced 5/5: `LOG_LEVEL=DEBUG pytest tests/orders/test_cancel.py::test_cancel_twice -x` exits 1,
AssertionError: expected status 'cancelled', got 'paid'. Analysis starts from this output.
```

### R-DBG-EXACT-COMMAND — the repro is one command anyone can paste

Bad:
```text
1. Start the app. 2. Create an order. 3. Cancel it twice. You should see the error.
```
Why: nobody can run it N times or compare two runs.

Good:
```text
cd /tmp/repro-a1b2 && LOG_LEVEL=DEBUG PYTHONHASHSEED=0 python repro.py
exit code 1 on bug, 0 when fixed; stdout ends with the line `ACTUAL: status=paid`
```

### R-DBG-NO-FIX — report, do not repair

Bad:
```diff
--- a/app/services/order_service.py
+++ b/app/services/order_service.py
-    if order.status == "paid":
+    if order.status in ("paid", "cancelled"):
```
Why: a fix without a failing test breaks the red → green order and hides the cause behind a patch.

Good:
```text
Root cause: OrderService.cancel (app/services/order_service.py:88) does not check the
`cancelled` state, so a second call overwrites it. Test to write: cancel an order twice;
expect the second call to raise OrderAlreadyCancelled. (not written here)
```

### R-DBG-EVIDENCE — every claim has file:line or a command output

Bad:
```text
Root cause: the repository returns stale rows because of caching.
```
Why: no way to check the claim; a reviewer must redo the whole investigation.

Good:
```text
1. app/api/orders.py:41 calls service.cancel(order_id)
2. app/services/order_service.py:88 reads order.status without lock (DEBUG line: event=cancel_check status=paid)
3. app/repositories/order_repository.py:57 saves the new status after the second read
Chain confirmed by run 3/5, log excerpt in runner report.
```

### R-DBG-TEMP-ONLY — instrumentation lives in /tmp

Bad:
```bash
sed -i '88i print("DEBUG", order)' app/services/order_service.py   # inside the project
```
Why: the project tree is changed, the print can be committed, and the next run is not the same code.

Good:
```bash
git worktree add /tmp/repro-a1b2/src HEAD
sed -i '88i print("DEBUG", order)' /tmp/repro-a1b2/src/app/services/order_service.py
```

### R-DBG-STATED-RATE — a verdict carries the count

Bad:
```text
Runner: it fails sometimes.
```
Why: stable and flaky bugs need different analysis; without a count nobody knows which.

Good:
```text
Runner: 20 runs, 7 failed (35%), identical error in all 7; exit codes 1 and 0. Verdict: flaky.
Failed runs: 2, 5, 6, 11, 12, 17, 19 (outputs in /tmp/repro-a1b2/runs/).
```

### R-DBG-NON-INTERACTIVE — debuggers run from a command line

Bad:
```bash
dlv test ./orders        # waits for typed input, the run hangs
```
Why: an agent cannot answer a prompt; the step times out with no evidence.

Good:
```bash
python -m pdb -c 'break app/services/order_service.py:88' -c continue -c 'p order' -c quit repro.py
```
(`-c` commands are run as `.pdbrc`; verified for pdb. For Go and Rust see the references and the (U) marks.)

## References

- [references/reproduce.md](references/reproduce.md): repro package template, runner report template, bisect script, environment capture.
- [references/python.md](references/python.md)
- [references/go.md](references/go.md)
- [references/rust.md](references/rust.md)
