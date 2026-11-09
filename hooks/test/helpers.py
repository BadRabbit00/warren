"""Run hook entry points the way Claude Code does: JSON on stdin, decision on stdout."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent


def call(entry: str, tool: str, tool_input: dict, *, agent: str | None = None, cwd: Path | None = None,
         project: Path | None = None, env: dict | None = None) -> dict:
    cwd = cwd or Path(tempfile.gettempdir())
    event = {"hook_event_name": "PostToolUse" if entry.startswith("check_") else "PreToolUse",
             "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd), "session_id": "t"}
    if agent:
        event["agent_type"] = agent
        event["agent_id"] = "a1"
    env = {**os.environ, **(env or {}), "CLAUDE_PROJECT_DIR": str(project or cwd)}
    out = subprocess.run([sys.executable, str(HOOKS / f"{entry}.py")], input=json.dumps(event),
                         capture_output=True, text=True, env=env, timeout=20)
    if out.returncode not in (0,):
        raise AssertionError(f"{entry} exited {out.returncode}: {out.stderr}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def denied(result: dict) -> bool:
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason(result: dict) -> str:
    return result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "") or result.get("reason", "")


def git_repo(branch: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="brhook-git-"))
    run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", branch)
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    return d
