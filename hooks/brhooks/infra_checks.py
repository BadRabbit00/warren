"""AC18: infrastructure-changing commands are never run by a subagent; the agent prepares them, the user runs them."""
from __future__ import annotations

import re
from pathlib import Path

from .common import Event

SHELL_NAMES = {"bash", "sh", "zsh", "dash", "ksh"}
XARGS_VALUE = {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"}
GH_VALUE_FLAGS = {"-R", "--repo", "--hostname"}


def _positionals(args: list[str], value_flags: frozenset[str] | set[str] = frozenset()) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_flags:
            i += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def _is_change(name: str, args: list[str]) -> bool:
    if name in {"tofu", "opentofu", "terraform"}:
        return _positionals(args)[:1] in (["apply"], ["destroy"])
    if name == "railway":
        return _positionals(args)[:1] in (["up"], ["redeploy"], ["down"])
    if name == "gh":
        return _positionals(args, GH_VALUE_FLAGS)[:2] in (["run", "rerun"], ["workflow", "run"])
    if name == "wrangler":
        pos = _positionals(args)
        if pos[:1] == ["rollback"] or pos[:2] == ["versions", "deploy"]:
            return True
        if pos[:1] == ["deploy"]:
            return not any(a == "--dry-run" or a == "--dry-run=true" for a in args)
        return False
    if name == "gcloud":
        pos = _positionals(args)
        return pos[:2] == ["run", "deploy"] or pos[:3] == ["run", "services", "delete"]
    if name == "doctl":
        pos = _positionals(args)
        return pos[:1] == ["apps"] and pos[1:2] in (["create"], ["update"], ["delete"])
    return False


def _reason(cmd: str, agent: str, depth: int = 0) -> str | None:
    from . import bash_checks as bc

    if depth > bc.MAX_DEPTH:
        return None
    try:
        commands = bc._split_commands(cmd.replace("\\\n", " "))
    except bc.NestingError:
        return None
    for command in commands:
        raw = bc.split_words(bc._scan_redirections(command.text)[1], comments=False)
        found = _words(bc._strip_redirections(bc._resolve(raw)[0]), agent, depth)
        if found:
            return found
    return None


def _words(w: list[str], agent: str, depth: int) -> str | None:
    from . import bash_checks as bc

    if not w or depth > bc.MAX_DEPTH:
        return None
    name = Path(w[0]).name
    args = w[1:]
    if name in SHELL_NAMES:
        script = bc._shell_script(w)
        return _reason(script, agent, depth + 1) if script is not None else None
    if name == "eval":
        return _reason(" ".join(args), agent, depth + 1)
    if name == "xargs":
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in XARGS_VALUE else 1
        return _words(bc._strip_redirections(bc._resolve(args[i:])[0]), agent, depth + 1)
    if name == "find":
        for sub in bc._find_exec_commands(w):
            found = _words(bc._strip_redirections(bc._resolve(sub)[0]), agent, depth + 1)
            if found:
                return found
        return None
    if _is_change(name, args):
        shown = " ".join(w)[:200]
        return (f"`{agent}` does not run infrastructure-changing commands: `{shown}` is refused. Prepare the exact "
                "command (with its arguments and the directory to run it in) and hand it to the user to run; "
                "the orchestrator may run it only after the user's approval. Plans and dry runs are allowed.")
    return None


def check_infra(ev: Event, cmd: str | None = None) -> str | None:
    """Reason to deny `cmd` (default: the event's Bash command) for a subagent, or None."""
    if not ev.agent:
        return None
    if cmd is None:
        cmd = ev.tool_input.get("command", "")
    return _reason(cmd, ev.agent)
