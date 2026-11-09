"""Shared helpers for BR hooks. Standard library only."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGE_CODERS = {"python-coder", "go-coder", "ts-coder", "rust-coder"}
EXECUTORS_CODE = {"coder", "refactorer", "deploy-engineer", "ci-engineer"} | LANGUAGE_CODERS
EXECUTOR_TESTS = "test-writer"
NO_TEST_WRITE = EXECUTORS_CODE | {"build-fixer"}
READ_ONLY_AGENTS = {"deploy-error-reader", "log-collector", "web-researcher", "stand-operator", "janitor"}   # no Write/Edit anywhere
PROTECTED_BRANCHES = {"main", "master", "develop"}
# Test locations. Our layout puts tests in `tests/` folders (Flutter/Dart: `test/`); the other entries cover
# the native conventions of each language (`integration_test/`, Go `_test.go`, JS `*.test.*`) so the boundary
# holds in existing projects too.
TEST_DIR = re.compile(r"(^|/)(test|tests|__tests__|e2e|integration_test|testdata)(/|$)")
TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.(py|go|dart)|conftest\.py|[^/]*\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs))$")
# Which task status lets which executor write (status = the step being executed now).
STEP_OF_AGENT = {"test-writer": "red", "coder": "green", "refactorer": "refactor",
                 **{a: "green" for a in LANGUAGE_CODERS | {"deploy-engineer", "ci-engineer"}}}
# What the main thread (orchestrator) may write while the project is orchestrated (.plan/ exists).
MAIN_WRITES = ["docs/**", ".plan/**", "README.md", "CHANGELOG.md", "CLAUDE.md", ".claude/rules/**"]
# Fixed write scopes of non-executor agents that are allowed to write at all.
AGENT_WRITES = {
    "presenter": ["docs/slides/**", ".plan/PLAN.html"],
    "ui-verifier": [],   # scripts and screenshots go to /tmp only (writes outside the project are allowed above)
}


def is_test_path(rel_path: str) -> bool:
    return TEST_DIR.search(rel_path) is not None or TEST_FILE.search(rel_path) is not None


@dataclass
class Event:
    raw: dict
    tool: str = ""
    tool_input: dict = field(default_factory=dict)
    agent: str | None = None
    cwd: Path = field(default_factory=Path.cwd)

    @property
    def is_main(self) -> bool:
        return not self.agent

    @property
    def project_root(self) -> Path:
        env = os.environ.get("CLAUDE_PROJECT_DIR")
        return Path(env) if env else self.cwd


def read_event() -> Event:
    data = json.load(sys.stdin)
    return Event(
        raw=data,
        tool=data.get("tool_name", ""),
        tool_input=data.get("tool_input") or {},
        agent=data.get("agent_type") or None,
        cwd=Path(data.get("cwd") or os.getcwd()),
    )


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"[br-hook] {reason}",
    }}))
    sys.exit(0)


def post_block(reason: str) -> None:
    """PostToolUse: the tool already ran; tell the model it must fix something."""
    print(json.dumps({"decision": "block", "reason": f"[br-hook] {reason}"}))
    sys.exit(0)


def post_context(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"[br-hook] {text}"}}))
    sys.exit(0)


def rel(path: str | Path, root: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = (root / p)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def glob_match(path: str, pattern: str) -> bool:
    """fnmatch with `**` spanning directories and a trailing `/` meaning 'everything under'."""
    pattern = pattern.strip().strip("`")
    if pattern.endswith("/"):
        pattern += "**"
    regex = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.fullmatch(regex, path) is not None or fnmatch.fnmatch(path, pattern)


def git_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd,
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


# ---------------------------------------------------------------- PLAN.md

TASK_HEAD = re.compile(r"^###\s+(T[\w.-]+)\b", re.M)
FIELD = re.compile(r"^\s*-\s+\*\*(?P<k>[^*]+?):\*\*\s*(?P<v>.*)$", re.M)
ACTIVE = set(STEP_OF_AGENT.values())


@dataclass
class Task:
    id: str
    status: str = ""
    writes: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)


def parse_plan(text: str) -> list[Task]:
    tasks: list[Task] = []
    heads = list(TASK_HEAD.finditer(text))
    for i, h in enumerate(heads):
        chunk = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        t = Task(id=h.group(1))
        for m in FIELD.finditer(chunk):
            key, val = m.group("k").strip().lower(), m.group("v")
            paths = re.findall(r"`([^`]+)`", val)
            if key.startswith("writes"):
                t.writes = paths
            elif key.startswith("tests"):
                t.tests = paths
            elif key == "status":
                m = re.match(r"[\s`*]*([A-Za-z-]+)", val)   # `red`, red (round 2), `green` — second pass
                t.status = m.group(1).lower() if m else ""
        tasks.append(t)
    return tasks


def is_orchestrated(root: Path) -> bool:
    return (root / ".plan").is_dir()


def active_tasks(root: Path) -> list[Task] | None:
    """None = project is not orchestrated (no .plan/PLAN.md)."""
    plan = root / ".plan" / "PLAN.md"
    if not plan.exists():
        return None
    return [t for t in parse_plan(plan.read_text(encoding="utf-8", errors="replace")) if t.status in ACTIVE]


def executor_scope(agent: str, tasks: list[Task]) -> tuple[list[str], list[str]]:
    """(allowed globs, task ids) for an executor: union over tasks whose status is that executor's step."""
    step = STEP_OF_AGENT.get(agent)
    mine = [t for t in tasks if t.status == step]
    globs = [g for t in mine for g in (t.tests if agent == EXECUTOR_TESTS else t.writes)]
    return globs, [t.id for t in mine]


def run_guarded(fn) -> None:
    """Run a hook body; a bug in a hook must not brick the session (fail-open, loud on stderr)."""
    try:
        fn()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[br-hook] internal error, check skipped: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)   # non-blocking error: Claude Code shows it, the tool call proceeds
