# Rust

Verified:

| Need | Command |
|---|---|
| Locked dependencies | `cargo build --locked`, `cargo test --locked` (or `--frozen`) |
| Batch lldb | `lldb -b -o 'cmd' -o 'cmd' target` (batch runs `-s`/`-S`/`-o`/`-O`, then quits) |
| Record and replay | `rr record <app> [args]`, `rr replay`, `rr -M replay -a` (replay without a debugger client) |
| Logs | `LOG_LEVEL=DEBUG` |

Not verified:

- Error handling of lldb in batch mode is not documented: (U) verify; check the exit code and output of a trivial run first.
- The rr page names C/C++ on Linux (modern x86 or some ARM); Rust is not mentioned: (U) verify before relying on it.
- `RUST_BACKTRACE=1` / `RUST_BACKTRACE=full` for panic traces, `cargo test <name> -- --nocapture`: standard cargo/std behaviour but not covered by the research: (U) verify.

Example batch session (U verify on the project's toolchain):

```bash
cargo build --locked && lldb -b -o 'breakpoint set -f src/orders.rs -l 88' -o run -o 'frame variable' -o quit target/debug/app
```
