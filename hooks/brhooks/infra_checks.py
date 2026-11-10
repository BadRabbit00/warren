"""AC18: infrastructure-changing commands are never run by a subagent; the agent prepares them, the user runs them."""
from __future__ import annotations

import shlex
from pathlib import Path

from .common import Event

SHELL_NAMES = {"bash", "sh", "zsh", "dash", "ksh"}
XARGS_VALUE = {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"}


def _positionals(args: list[str]) -> list[str]:
    """Words that are not flags. A flag's value stays in the list on purpose: matching is fail-closed (see _has)."""
    return [a for a in args if not a.startswith("-")]


def _has(pos: list[str], *verbs: str) -> bool:
    """True if the verbs appear next to each other anywhere among the positionals, so that an unknown
    global flag with a value in front of the subcommand cannot hide it."""
    n = len(verbs)
    return any(tuple(pos[i:i + n]) == verbs for i in range(len(pos) - n + 1))


def _is_change(name: str, args: list[str]) -> bool:
    pos = _positionals(args)
    if name in {"tofu", "opentofu", "terraform"}:
        return any(v in pos for v in ("apply", "destroy"))
    if name == "railway":
        return any(v in pos for v in ("up", "redeploy", "down"))
    if name == "gh":
        return _has(pos, "run", "rerun") or _has(pos, "workflow", "run")
    if name == "wrangler":
        if "rollback" in pos or _has(pos, "versions", "deploy"):
            return True
        if "deploy" in pos:
            return not any(a == "--dry-run" or a == "--dry-run=true" for a in args)
        return False
    if name == "gcloud":
        return _has(pos, "run", "deploy") or _has(pos, "run", "services", "delete")
    if name == "doctl":
        return any(_has(pos, "apps", v) for v in ("create", "update", "delete", "create-deployment"))
    return False


def _unknowable(agent: str) -> str:
    return (f"`{agent}`: the command is too deeply nested or cannot be parsed, so it cannot be checked for "
            "infrastructure changes. Simplify it, or prepare the exact command for the user to run.")


def _substitution_depth(cmd: str) -> int:
    """Deepest nesting of `$( … )` (the splitter flattens unquoted ones without counting)."""
    depth = deepest = 0
    for i, ch in enumerate(cmd):
        if ch == "(" and cmd[i - 1:i] == "$":
            depth += 1
            deepest = max(deepest, depth)
        elif ch == ")" and depth:
            depth -= 1
    return deepest


def _reason(cmd: str, agent: str, depth: int = 0) -> str | None:
    from . import bash_checks as bc

    if depth > bc.MAX_DEPTH:
        return _unknowable(agent)
    if _substitution_depth(cmd) > bc.MAX_DEPTH:
        return _unknowable(agent)
    try:
        commands = bc._split_commands(cmd.replace("\\\n", " "))
        for command in commands:
            raw = bc.split_words(bc._scan_redirections(command.text)[1], comments=False)
            # split_words is lenient; an unterminated quote or substitution means we cannot tell what runs
            shlex.split(command.text, comments=True)
            if any(x.count("$(") > x.count(")") or x.count("`") % 2 for x in raw):
                return _unknowable(agent)
            found = _words(bc._strip_redirections(bc._resolve(raw)[0]), agent, depth)
            if found:
                return found
    except (bc.NestingError, ValueError):
        return _unknowable(agent)
    return None


def _words(w: list[str], agent: str, depth: int) -> str | None:
    from . import bash_checks as bc

    if not w:
        return None
    if depth > bc.MAX_DEPTH:
        return _unknowable(agent)
    name = Path(w[0]).name
    args = w[1:]
    if name in bc.LAUNCHER or (name in bc.LAUNCHER_SUBCOMMANDS and bc._is_interpreter(w)):
        # package launcher: any later word may start the real command; try every suffix (fail closed)
        for i in range(len(args)):
            if not args[i].startswith("-"):
                found = _words(args[i:], agent, depth + 1)
                if found:
                    return found
        return None
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
