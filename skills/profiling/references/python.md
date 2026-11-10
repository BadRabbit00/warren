# Python - py-spy

Tool: `py-spy` (nixpkgs `py-spy`). All outputs in `/tmp/prof-<id>/`. Run as `nix shell nixpkgs#py-spy -c py-spy …`.

## Commands

| Goal | Command |
|---|---|
| Flame graph of a running process | `py-spy record -o /tmp/prof-<id>/before.svg --pid <PID>` |
| Flame graph of a program launched under py-spy | `py-spy record -o /tmp/prof-<id>/before.svg -- python prog.py` |
| Live top-like view | `py-spy top --pid <PID>` |
| One-shot stack dump of every thread | `py-spy dump --pid <PID>` |
| Other output format | `py-spy record --format <fmt> -o /tmp/prof-<id>/before.json …` - speedscope and raw exist; full list (U) via `py-spy record --help` |
| Include native extensions | add `--native` |
| Include child Python processes | add `--subprocesses` |

Launch mode is preferred: no ptrace permission is needed because the program is py-spy's child. In the project environment launch the program as the project does, e.g. `nix develop -c py-spy …` is not possible unless py-spy is in the dev shell; use `nix shell nixpkgs#py-spy -c py-spy record … -- <project python> prog.py` (U: the project interpreter path, take it from the task).

## Workflow

1. `mkdir -p /tmp/prof-<id>`.
2. Start the reproduction (a load script or the slow scenario) against local services.
3. Baseline timing first (R-PROF-BASELINE-FIRST), then `py-spy record` for the duration of the scenario (U: `--duration` / `--rate` options, check `--help`).
4. Open the SVG; read self vs total, wide plateaus.
5. `py-spy dump` helps when the process hangs or the event loop looks blocked: the stack of the blocked thread shows the call.
6. After the change: same scenario, `after.svg`, compare.

## Memory

py-spy samples CPU stacks only. For memory, `tracemalloc` from the standard library (U: not in the research; verify the snapshot API in the Python docs) or the peak RSS from `/usr/bin/time -v` (U: GNU time availability).

## Permissions

- Attaching with `--pid` to a process that is not a child: root or relaxed `ptrace_scope` on Linux.
- Docker: the container needs `SYS_PTRACE` (`--cap-add SYS_PTRACE`).
- Not available: report the requirement, switch to launch mode. No `sudo`.
