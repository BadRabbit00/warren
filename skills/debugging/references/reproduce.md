# Reproduction package, runner report, bisect

## Repro package: `/tmp/repro-<id>/`

```text
/tmp/repro-<id>/
  README.md      # the fields below
  repro.sh       # or repro.py / repro_test.go / a cargo test name: the exact command target
  input/         # minimised input files, no secrets, no personal data
  src/           # optional: worktree or copy, only if instrumentation is needed
  runs/          # written by repro-runner: run-1.out, run-1.log, ...
```

`README.md` fields:

| Field | Content |
|---|---|
| Report | the user's words, one paragraph |
| Environment | OS, language and tool versions, commit hash, lock file used, seed, time (fixed value or "real clock"), config as env var names and values with secrets replaced by `***` |
| Steps | numbered, only if no script covers them |
| Command | the exact line, run from `/tmp/repro-<id>`, with env vars |
| Expected | what should happen (cite the spec, doc or test if there is one) |
| Actual | the symptom and the exact error text |
| Pass/fail contract | exit 0 = bug absent, exit 1 = bug present, exit 125 = cannot be tested (build fails) |
| Reproduced | `k of N`, set by the reproducer in its own trial runs |

## Runner report

```text
Command: <exact line>
Runs: N        Failed: k        Verdict: stable | flaky (rate) | not reproduced
| run | exit | result | duration | note |
Error text identical in all failed runs: yes | no (list differences)
Log excerpts (LOG_LEVEL=DEBUG): first failing run, 10-20 lines around the first wrong value, secrets masked
Files: /tmp/repro-<id>/runs/
```

The runner changes nothing in the package. If the command does not run (missing tool, wrong path), it reports that instead of fixing the package.

## Environment capture

Verified:

| Item | How |
|---|---|
| Python hash seed | `PYTHONHASHSEED=<int 0-4294967295>`; `0` disables randomization |
| Rust | `cargo build --locked` / `cargo test --locked` (or `--frozen`) |
| Go | `go test -count=1` bypasses the test cache |
| Build time | `SOURCE_DATE_EPOCH` for time-dependent build output |
| Versions | record the commit hash and tool versions; use the lock files |

Not covered by sources read: faking runtime time and test seeds in each framework: (U) verify. Ask which seed or time source the code uses (see the code, not a guess), and pass it explicitly.

## git bisect run

Contract: `0` good, `1`-`127` except `125` bad, `125` skip, `>=128` or `255` abort.

`bisect.sh` (put in `/tmp/repro-<id>/`, run from a clone or worktree in `/tmp`):

```bash
#!/usr/bin/env bash
# build failure => 125 (skip), never 1
make build >/dev/null 2>&1 || exit 125
# the repro: 0 when the bug is absent, 1 when present
/tmp/repro-<id>/repro.sh
```

Commands:

```bash
git clone <project> /tmp/repro-<id>/bisect && cd /tmp/repro-<id>/bisect
git bisect start <bad-commit> <good-commit>
git bisect run /tmp/repro-<id>/bisect.sh
git bisect log        # attach to the analysis
git bisect reset
```

Check first that the script exits `1` on `<bad-commit>` and `0` on `<good-commit>`; a script that is wrong on either end gives a wrong commit. Record the first bad commit hash in the analysis and confirm with a normal run on it and on its parent.
