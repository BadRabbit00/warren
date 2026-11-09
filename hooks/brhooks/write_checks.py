"""Checks for Edit / Write / MultiEdit / NotebookEdit and Read. Each returns a deny reason or None."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .common import (AGENT_WRITES, EXECUTOR_TESTS, EXECUTORS_CODE, MAIN_WRITES, NO_TEST_WRITE, READ_ONLY_AGENTS,
                     READER_READ_ROOTS, READER_ROOT_AGENTS,
                     STEP_OF_AGENT, Event,
                     active_tasks, executor_scope, glob_match, is_orchestrated, is_test_path, rel)

TMP_PREFIXES = ("/tmp/", "/var/tmp/")
# Linter / formatter / type-checker / coverage configs. Executors fix the code, not the rules that judge it.
QUALITY_CONFIG = re.compile(
    r"^(\.?eslintrc(\.\w+)?|eslint\.config\.\w+|\.prettierrc(\.\w+)?|prettier\.config\.\w+|biome\.jsonc?"
    r"|\.stylelintrc(\.\w+)?|\.golangci\.(ya?ml|toml|json)|\.?ruff\.toml|\.?mypy\.ini|\.flake8|\.pylintrc"
    r"|pyrightconfig\.json|\.coveragerc|pytest\.ini|analysis_options\.yaml|\.?clippy\.toml|\.?rustfmt\.toml"
    r"|\.editorconfig|\.pre-commit-config\.ya?ml|\.markdownlint(\.\w+|-cli2\.\w+)?)$")
# ci-engineer is deliberately absent: it owns the quality configs inside its write set.
QUALITY_GUARDED = (NO_TEST_WRITE - {"ci-engineer"}) | {"test-writer"}


def target_path(ev: Event) -> str | None:
    ti = ev.tool_input
    return ti.get("file_path") or ti.get("notebook_path") or ti.get("path")


def _outside_project(r: str) -> bool:
    return r.startswith("/")


def _is_temp(r: str) -> bool:
    return r.startswith(TMP_PREFIXES) or "/scratchpad/" in r


def _explicit_write(agent: str, r: str, root) -> bool:
    """A path named literally (no wildcard) in Writes of the executor's active task: it beats the test-file pattern."""
    if agent not in EXECUTORS_CODE or agent not in STEP_OF_AGENT or not is_orchestrated(root):
        return False
    globs, _ = executor_scope(agent, active_tasks(root) or [])
    return any(r == g.strip() for g in globs if not re.search(r"[*?\[]", g))


def _fmt(globs: list[str]) -> str:
    return ", ".join(f"`{g}`" for g in globs[:8]) + (" …" if len(globs) > 8 else "")


def check_write(ev: Event) -> str | None:
    path = target_path(ev)
    if not path:
        return None
    root = ev.project_root
    r = rel(path, root)
    agent = ev.agent

    # ---- readers write nothing
    if agent in READ_ONLY_AGENTS:
        return f"`{agent}` is read-only: it writes no files (`{r}` is refused). Report what you found in the answer."

    # ---- subagents never write outside the project (temp dirs are fine)
    if agent and _outside_project(r) and not _is_temp(r):
        return f"`{agent}` writes only inside the project. `{path}` is outside it."

    # ---- test boundary (always on, with or without a plan)
    if agent in NO_TEST_WRITE and is_test_path(r) and not _explicit_write(agent, r, root):
        return (f"`{agent}` may read tests but never change them (`{r}`). If a test looks wrong, stop with "
                "STATUS: blocked and explain; the orchestrator returns it to test-writer.")
    if agent == EXECUTOR_TESTS and not is_test_path(r) and not _outside_project(r):
        return (f"test-writer writes only test files (`tests/` folders, `*_test.go`, `*.test.tsx`, …); `{r}` is production code. If the code needs a seam "
                "to be testable, report it as a question for the orchestrator.")

    # ---- quality configs (ported from upstream pre:config-protection)
    if agent in QUALITY_GUARDED and QUALITY_CONFIG.match(Path(r).name):
        return (f"`{agent}` does not change linter/formatter/type-check configs (`{r}`). Fix the code. If the rule "
                "itself is wrong, stop with STATUS: blocked and say which rule and why.")

    # ---- plan-driven scopes (only when the project is orchestrated)
    if not is_orchestrated(root):
        return None
    if agent and (agent in STEP_OF_AGENT) and _outside_project(r):   # temp dirs, checked above
        return None
    if agent is None:
        if _outside_project(r) or any(glob_match(r, g) for g in MAIN_WRITES):
            return None
        return (f"The orchestrator writes only docs and the plan ({_fmt(MAIN_WRITES)}); `{r}` is code. "
                "Dispatch it to an executor through a task in .plan/PLAN.md. "
                "For a quick session without the plan, switch with `/output-style default`.")
    if agent in AGENT_WRITES:
        if _outside_project(r) or any(glob_match(r, g) for g in AGENT_WRITES[agent]):   # temp dirs checked above
            return None
        return f"`{agent}` writes only {_fmt(AGENT_WRITES[agent]) or 'temp files (/tmp)'}."
    if agent in STEP_OF_AGENT:
        tasks = active_tasks(root) or []
        globs, ids = executor_scope(agent, tasks)
        step = STEP_OF_AGENT[agent]
        if not ids:
            return (f"No task in .plan/PLAN.md has status `{step}`, so `{agent}` has no write set. "
                    "The orchestrator sets the status before dispatching.")
        if any(glob_match(r, g) for g in globs):
            return None
        field = "Tests (test-writer)" if agent == EXECUTOR_TESTS else "Writes (exclusive)"
        return (f"`{r}` is outside the write set of {', '.join(ids)} ({field}: {_fmt(globs)}). "
                "If the task really needs this file, stop with STATUS: blocked and name it; the orchestrator "
                "updates the plan.")
    return None


# ---------------------------------------------------------------- read

SECRET_NAME = re.compile(r"^\.env(\.(?!example$)[\w.-]+)?$|\.(pem|key|p12|pfx)$|^id_(rsa|ed25519|ecdsa)$|^keys\.txt$")
ALLOWED_PUBLIC = re.compile(r"(\.pub|\.example|\.sample|\.template)$|(^|[-_.])public[-_.]")


def _under(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def _reader_outside_roots(ev: Event, path: str) -> bool:
    """True when `path` (relative to the event cwd, `~` = HOME) is outside the project and the temp dirs."""
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = ev.cwd / p
    candidates = {Path(os.path.normpath(p)), p.resolve()}
    roots = [ev.project_root, *(Path(r) for r in READER_READ_ROOTS)]
    allowed = {r for root in roots for r in (Path(os.path.normpath(root)), root.resolve())}
    return not all(any(_under(c, root) for root in allowed) for c in candidates)


def check_read(ev: Event) -> str | None:
    path = target_path(ev)
    if ev.agent in READER_ROOT_AGENTS and _reader_outside_roots(ev, path or "."):
        return (f"`{ev.agent}` reads only inside the project, /tmp, /var/tmp, and the scratchpad; "
                f"`{path or ev.cwd}` is outside them. Use the CLI commands for logs and status.")
    if not path:
        return None
    name = Path(path).name
    if ALLOWED_PUBLIC.search(name):
        return None
    if SECRET_NAME.search(name):
        return (f"`{name}` holds secrets and is not read into the context. Read `.env.example` for the variable "
                "names; check a value is set with `grep -q '^NAME=.' .env`.")
    return None
