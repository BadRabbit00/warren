# Go

Verified:

| Need | Command |
|---|---|
| Bypass the test cache | `go test -count=1 ./pkg -run TestName` |
| Debug a test | `dlv test [pkg] -- -test.run X` |
| Debug a binary | `dlv exec <bin>` |
| Delve flags documented | `--init` (init file run by the terminal client), `--headless`, `--continue` (exec), `--accept-multiclient`, `--allow-non-terminal-interactive` |
| Logs | `LOG_LEVEL=DEBUG` |

Not verified: a fully scripted batch run (init file contents, how the session exits). (U) verify locally with a trivial program before using Delve in a package; until then prefer `-count=1` runs with DEBUG logs and `go test -run X -v`.

Plain `dlv test` without an init file or flags waits on a prompt: never start it that way (R-DBG-NON-INTERACTIVE).

(U) verify: `go test -race`, `-failfast`, `-shuffle` for flaky bugs; they are standard `go test` flags but were not covered by the research.
