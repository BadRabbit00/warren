# Go - pprof

Tool: `go tool pprof` is part of the Go toolchain. Graph reports need Graphviz (`dot`) on `PATH`. All files in `/tmp/prof-<id>/`.

## Live service

The service imports `net/http/pprof` for its side effect, which registers `/debug/pprof/*`. That is a code change in the project: the optimizer does not make it; if the endpoint is absent, report that it is needed (U: whether the service already exposes it - read the code).

| Goal | Command |
|---|---|
| CPU profile, 30 s | `go tool pprof "http://localhost:6060/debug/pprof/profile?seconds=30"` |
| Heap profile | `go tool pprof http://localhost:6060/debug/pprof/heap` |
| Goroutines | listed in the index at `/debug/pprof/`; the goroutine profile reports the stack traces of all current goroutines |
| Delta over a period | `seconds=N` on heap or goroutine returns a delta profile |
| Web UI with flame graph | `go tool pprof -http=localhost:8081 <binary> <profile-file>`; pick Flame Graph in the View menu |

Run the 30 s CPU profile while the load runs. Port 6060 is the doc example; use the service's real port (U). To keep the profile file, save the URL response to `/tmp/prof-<id>/cpu.pb.gz` (U: `curl -o`, and that `go tool pprof` reads a saved file with the binary as above).

Text view in the terminal (`top`, `-top`, `list <func>`): U, verify in `go tool pprof -h`.

## Tests and benchmarks

```text
go test -cpuprofile /tmp/prof-<id>/cpu.out -memprofile /tmp/prof-<id>/mem.out <pkg>
```

The profile flags (`-cpuprofile`, `-memprofile`, `-blockprofile`) also write the test binary, left as `pkg.test`. Keep it out of the project: `-o /tmp/prof-<id>/pkg.test` (U: verify the `-o` flag with `go help test`). Then `go tool pprof -http=localhost:8081 /tmp/prof-<id>/pkg.test /tmp/prof-<id>/cpu.out`. Selecting a benchmark with `-bench` and `-run` is (U) here.

## Notes

- The Go docs: profiling in production is safe, but some profiles (CPU) add cost.
- Do not expose `/debug/pprof` publicly: (U) the research found no official warning; treat it as internal-only anyway.
- Read: flat = self, cum = total. Heap: say whether in-use or allocated.
