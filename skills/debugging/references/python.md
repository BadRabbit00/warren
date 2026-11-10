# Python

Verified:

| Need | Command |
|---|---|
| Run a script under pdb without a prompt | `python -m pdb -c continue script.py` (`-c` is run as `.pdbrc` commands, since 3.2) |
| Stop at a line, print, quit | `python -m pdb -c 'break file.py:LINE' -c continue -c 'p expr' -c quit script.py` |
| `breakpoint()` in a temp copy | calls `sys.breakpointhook` (3.7+); `PYTHONBREAKPOINT=0` makes it a no-op, so a leftover call does not hang a run |
| Stable hash order | `PYTHONHASHSEED=0` |
| Logs | `LOG_LEVEL=DEBUG` (see the `logging` skill) |

Not usable by an agent: `debugpy` (`python -m debugpy --listen host:port [--wait-for-client] file.py`, `debugpy.breakpoint()`) waits for a DAP client.

(U) verify: pytest options for one test (`pytest path::test -x`), `pytest --pdb` behaviour without a terminal, how `-c` commands behave when the program ends before `quit`. Run once locally before using in a package.

After an uncaught exception, pdb post-mortem is a prompt: in a repro script catch the exception, print `traceback.format_exc()`, and exit non-zero instead.
